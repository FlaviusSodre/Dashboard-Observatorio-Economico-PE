"""
components/data_atividade.py
============================
Consultas do eixo Atividade Econômica: IBC-R, PIB trimestral, PIM-PF,
PMC, PMS, IPCA e agropecuária (LSPA, PAM e PPM).

Fontes: ver etl/atividade_etl.py.
"""

from functools import lru_cache

import pandas as pd

from config import (AGRO_LSPA, AGRO_PAM, AGRO_PPM, ATIVIDADE_MENSAL,
                    PIB_TRIMESTRAL)
from components.data_base import com_rd, ler

# Nomes curtos para exibição ------------------------------------------------
NOME_CURTO = {
    # PIM-PF
    'Indústrias extrativas': 'Extrativa',
    'Indústrias de transformação': 'Transformação',
    'Produtos alimentícios': 'Alimentos',
    'Celulose, papel e produtos de papel': 'Celulose e papel',
    'Coque, de produtos derivados do petróleo e de biocombustíveis':
        'Derivados de petróleo e biocombustíveis',
    'Produtos químicos': 'Químicos',
    'Produtos de borracha e de material plástico': 'Borracha e plástico',
    'Produtos de minerais não metálicos': 'Minerais não metálicos',
    'Produtos de metal, exceto máquinas e equipamentos': 'Produtos de metal',
    'Máquinas, aparelhos e materiais elétricos': 'Máquinas e materiais elétricos',
    'Veículos automotores, reboques e carrocerias': 'Veículos automotores',
    'Outros equipamentos de transporte, exceto veículos automotores':
        'Outros equipamentos de transporte',
    # PMC
    'Hipermercados, supermercados, produtos alimentícios, bebidas e fumo':
        'Super e hipermercados, alimentos e bebidas',
    'Hipermercados e supermercados': 'Hiper e supermercados',
    'Artigos farmacêuticos, médicos, ortopédicos, de perfumaria e cosméticos':
        'Farmácia, perfumaria e cosméticos',
    'Equipamentos e materiais para escritório, informática e comunicação':
        'Escritório, informática e comunicação',
    'Outros artigos de uso pessoal e doméstico': 'Outros artigos pessoais e domésticos',
    # PMS
    'Serviços prestados às famílias': 'Prestados às famílias',
    'Serviços de informação e comunicação': 'Informação e comunicação',
    'Serviços profissionais, administrativos e complementares':
        'Profissionais e administrativos',
    'Transportes, serviços auxiliares aos transportes e correio':
        'Transportes e correio',
}

# Atividades agregadas da PMC que se sobrepõem a outras (ficam fora dos rankings)
_PMC_AGREGADOS = {'Móveis e eletrodomésticos',
                  'Hipermercados, supermercados, produtos alimentícios, bebidas e fumo'}

INDICADORES = {
    'ibcr': 'Atividade econômica (IBC-R)',
    'pim': 'Indústria',
    'pmc_varejo': 'Varejo',
    'pmc_ampliado': 'Varejo ampliado',
    'pms': 'Serviços',
    'pms_turismo': 'Turismo',
}


def curto(nome: str) -> str:
    return NOME_CURTO.get(nome, nome)


# ============================================================================
# Séries mensais
# ============================================================================

@lru_cache(maxsize=None)
def mensal() -> pd.DataFrame:
    return ler(ATIVIDADE_MENSAL)


def disponivel() -> bool:
    return not mensal().empty


def serie(fonte: str, regiao: str = 'Pernambuco', categoria: str = None,
          medida: str = 'indice_sa', tipo: str = None) -> pd.Series:
    """Série temporal (índice = data). categoria None = total da pesquisa."""
    d = mensal()
    if d.empty:
        return pd.Series(dtype=float)
    f = (d['fonte'] == fonte) & (d['regiao'] == regiao) & (d['medida'] == medida)
    if categoria is None:
        categoria = {'pim': 'Indústria geral', 'ipca': 'Índice geral'}.get(fonte, 'Total')
    f &= d['categoria'] == categoria
    if tipo:
        f &= d['tipo'] == tipo
    return d[f].set_index('data')['valor'].sort_index()


def _tipo_padrao(fonte: str):
    return 'volume' if fonte.startswith(('pmc', 'pms')) else None


def ultima_data(fonte: str) -> pd.Timestamp:
    d = mensal()
    s = d.loc[d['fonte'] == fonte, 'data']
    return s.max() if len(s) else None


def ultimo(fonte: str, medida: str, regiao: str = 'Pernambuco',
           categoria: str = None):
    s = serie(fonte, regiao, categoria, medida, _tipo_padrao(fonte)).dropna()
    if s.empty:
        return None, None
    return s.index[-1], float(s.iloc[-1])


def indice_base(fonte: str, regiao: str, ano_base: int = 2019,
                categoria: str = None) -> pd.Series:
    """Índice dessazonalizado rebaseado: média do ano_base = 100."""
    s = serie(fonte, regiao, categoria, 'indice_sa', _tipo_padrao(fonte)).dropna()
    if s.empty:
        return s
    base = s[s.index.year == ano_base].mean()
    if pd.isna(base) or base == 0:
        base = s.iloc[0]
    return 100 * s / base


def termometro() -> pd.DataFrame:
    """
    Variação acumulada em 12 meses do último mês de cada indicador, para
    Pernambuco e Brasil (o IBC-R também tem Nordeste).
    """
    linhas = []
    for fonte, nome in INDICADORES.items():
        dt, pe = ultimo(fonte, 'var_acum_12m', 'Pernambuco')
        if dt is None:
            continue
        s_br = serie(fonte, 'Brasil', None, 'var_acum_12m', _tipo_padrao(fonte))
        br = float(s_br.get(dt)) if dt in s_br.index else None
        linhas.append({'fonte': fonte, 'indicador': nome, 'data': dt,
                       'pe': pe, 'br': br})
    return pd.DataFrame(linhas)


def ranking_atividades(fonte: str, medida: str = 'var_acum_12m',
                       data: pd.Timestamp = None) -> pd.DataFrame:
    """Variação por atividade (PE), com o Brasil ao lado quando houver."""
    d = mensal()
    d = d[(d['fonte'] == fonte) & (d['medida'] == medida)]
    if fonte == 'pim':
        d = d[~d['categoria'].isin(['Indústria geral'])]
    if fonte == 'pmc_atividades':
        d = d[~d['categoria'].isin(_PMC_AGREGADOS)]
    if fonte == 'pms_atividades':
        d = d[d['categoria'] != 'Total']
    if d.empty:
        return pd.DataFrame()
    data = data or d.loc[d['regiao'] == 'Pernambuco', 'data'].max()
    d = d[d['data'] == data]
    pe = d[d['regiao'] == 'Pernambuco'].set_index('categoria')['valor']
    br = d[d['regiao'] == 'Brasil'].set_index('categoria')['valor']
    out = pd.DataFrame({'pe': pe, 'br': br}).dropna(subset=['pe']).reset_index()
    out = out.rename(columns={'index': 'categoria'})
    out['nome'] = out['categoria'].map(curto)
    out['data'] = data
    return out


def categorias(fonte: str, regiao: str = 'Pernambuco') -> list:
    d = mensal()
    d = d[(d['fonte'] == fonte) & (d['regiao'] == regiao)]
    return sorted(d['categoria'].unique().tolist())


def ipca_grupos(data: pd.Timestamp = None) -> pd.DataFrame:
    """IPCA acumulado em 12 meses por grupo: RM do Recife x Brasil."""
    d = mensal()
    d = d[(d['fonte'] == 'ipca') & (d['medida'] == 'var_acum_12m')]
    if d.empty:
        return d
    data = data or d.loc[d['regiao'] == 'RM Recife', 'data'].max()
    d = d[d['data'] == data]
    out = d.pivot_table(index='categoria', columns='regiao', values='valor').reset_index()
    out['data'] = data
    return out


# ============================================================================
# PIB trimestral
# ============================================================================

@lru_cache(maxsize=None)
def pib_trimestral() -> pd.DataFrame:
    return ler(PIB_TRIMESTRAL)


def pib_ultimo() -> dict:
    d = pib_trimestral()
    if d.empty:
        return {}
    pe = d[d['regiao'] == 'Pernambuco'].sort_values('data')
    br = d[d['regiao'] == 'Brasil'].set_index('rotulo')
    u = pe.iloc[-1]
    r = u.to_dict()
    if u['rotulo'] in br.index:
        r['br_interanual'] = br.at[u['rotulo'], 'var_interanual']
        r['br_acum_4t'] = br.at[u['rotulo'], 'var_acum_4t']
    return r


# ============================================================================
# Agropecuária
# ============================================================================

@lru_cache(maxsize=None)
def pam() -> pd.DataFrame:
    return ler(AGRO_PAM)


@lru_cache(maxsize=None)
def ppm() -> pd.DataFrame:
    return ler(AGRO_PPM)


@lru_cache(maxsize=None)
def lspa() -> pd.DataFrame:
    return ler(AGRO_LSPA)


def agro_disponivel() -> bool:
    return not pam().empty


def pam_anos() -> list:
    return sorted(pam()['ano'].unique().tolist(), reverse=True)


def pam_estado(ano: int) -> pd.DataFrame:
    """Lavouras de PE no ano, por produto (sem o total), com participação."""
    d = pam()
    d = d[(d['nivel'] == 'estado') & (d['ano'] == ano)]
    tot = d.loc[d['cod_produto'] == 0, 'valor_mil'].sum()
    d = d[(d['cod_produto'] != 0) & (d['valor_mil'] > 0)].copy()
    d['part_pct'] = 100 * d['valor_mil'] / tot if tot else None
    return d.sort_values('valor_mil', ascending=False)


def pam_total(ano: int) -> float:
    d = pam()
    s = d[(d['nivel'] == 'estado') & (d['ano'] == ano) & (d['cod_produto'] == 0)]
    return float(s['valor_mil'].sum()) * 1000


def pam_serie(produto: str) -> pd.DataFrame:
    d = pam()
    return (d[(d['nivel'] == 'estado') & (d['produto'] == produto)]
            .sort_values('ano'))


def pam_produtos_municipais() -> list:
    """Produtos com dado municipal (os principais do estado)."""
    d = pam()
    d = d[(d['nivel'] == 'municipio') & (d['cod_produto'] != 0)]
    ult = d['ano'].max()
    ordem = (d[d['ano'] == ult].groupby('produto')['valor_mil'].sum()
             .sort_values(ascending=False))
    return ['Total (todas as lavouras)'] + ordem.index.tolist()


def pam_municipios(ano: int, produto: str) -> pd.DataFrame:
    d = pam()
    d = d[(d['nivel'] == 'municipio') & (d['ano'] == ano) & (d['produto'] == produto)]
    d = com_rd(d.copy())
    from components.data_base import municipios
    d = d.merge(municipios()[['cod_ibge_6', 'municipio']], on='cod_ibge_6', how='left')
    tot = d['valor_mil'].sum()
    d['part_pct'] = 100 * d['valor_mil'] / tot if tot else 0
    return d


def lspa_resumo() -> pd.DataFrame:
    """
    Estimativa mais recente da safra do ano corrente x estimativa final
    (dezembro) do ano anterior, por produto.
    """
    d = lspa()
    if d.empty:
        return d
    p = d[d['variavel'] == 'producao_t']
    ult = p['data'].max()
    ano = ult.year
    cur = p[p['data'] == ult].set_index('produto')['valor']
    ant_data = p.loc[p['data'].dt.year == ano - 1, 'data'].max()
    ant = p[p['data'] == ant_data].set_index('produto')['valor']
    out = pd.DataFrame({'atual': cur, 'anterior': ant}).dropna(subset=['atual'])
    out['var_pct'] = 100 * (out['atual'] / out['anterior'] - 1)
    out = out.reset_index().rename(columns={'index': 'produto'})
    out['data'] = ult
    out['data_ant'] = ant_data
    return out.sort_values('atual', ascending=False)


def ppm_anos() -> list:
    return sorted(ppm()['ano'].unique().tolist(), reverse=True)


def ppm_estado(ano: int) -> pd.DataFrame:
    d = ppm()
    return d[(d['nivel'] == 'estado') & (d['ano'] == ano)]


def ppm_serie(produto: str) -> pd.DataFrame:
    d = ppm()
    return d[(d['nivel'] == 'estado') & (d['produto'] == produto)].sort_values('ano')


def ppm_municipios(ano: int, produto: str) -> pd.DataFrame:
    d = ppm()
    d = d[(d['nivel'] == 'municipio') & (d['ano'] == ano) & (d['produto'] == produto)]
    from components.data_base import municipios
    d = d.merge(municipios(), on='cod_ibge_6', how='left')
    tot = d['quantidade'].sum()
    d['part_pct'] = 100 * d['quantidade'] / tot if tot else 0
    return d
