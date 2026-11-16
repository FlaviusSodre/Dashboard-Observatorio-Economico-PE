"""
components/data_social.py
=========================
Consultas do eixo Indicadores Sociais: Índice de Progresso Social (IPS
Brasil) e mortes violentas intencionais (SDS-PE).

Fontes: ver etl/ips_etl.py e etl/seguranca_etl.py.
"""

from functools import lru_cache

import pandas as pd

from config import IPS_PE, IPS_REFERENCIAS, MVI_PE
from components.data_base import com_rd, ler, municipios, populacao, rotulo_ano

INDICE = 'Índice de Progresso Social'
DIMENSOES = ['Necessidades Humanas Básicas', 'Fundamentos do Bem-estar', 'Oportunidades']

# Indicadores mostrados na ficha do município (nome no IPS, rótulo, unidade,
# True quando um valor maior é melhor)
INDICADORES_FICHA = [
    ('Homicídios', 'Homicídios', 'por 100 mil hab.', False),
    ('Mortalidade Infantil até 5 anos', 'Mortalidade até 5 anos', 'por mil nascidos', False),
    ('Esgotamento Sanitário Adequado', 'Esgotamento sanitário adequado', '% dos domicílios', True),
    ('Abastecimento de Água Via Rede de Distribuição', 'Água por rede de distribuição',
     '% dos domicílios', True),
    ('Ideb Ensino Fundamental', 'Ideb do ensino fundamental', 'nota', True),
    ('Expectativa de Vida', 'Expectativa de vida', 'anos', True),
    ('Gravidez na Adolescência (<19)', 'Gravidez na adolescência', '% dos nascidos', False),
    ('Cobertura de Internet Móvel (4G/5G)', 'Cobertura 4G/5G', '% da área', True),
]


# ============================================================================
# IPS
# ============================================================================

@lru_cache(maxsize=None)
def ips() -> pd.DataFrame:
    d = ler(IPS_PE)
    return com_rd(d) if not d.empty else d


@lru_cache(maxsize=None)
def ips_ref() -> pd.DataFrame:
    return ler(IPS_REFERENCIAS)


def ips_disponivel() -> bool:
    return not ips().empty


def edicoes() -> list:
    return sorted(ips()['edicao'].unique().tolist(), reverse=True)


def opcoes_indicadores() -> list:
    """IPS, dimensões e componentes, na ordem da metodologia."""
    d = ips()
    ops = [(INDICE, INDICE)]
    for dim in DIMENSOES:
        ops.append((dim, dim))
        comps = (d[(d['nivel'] == 'componente') & (d['dimensao'] == dim)]['indicador']
                 .drop_duplicates().tolist())
        ops += [(f"   · {c}", c) for c in comps]
    return ops


def _ref(edicao, recorte, indicador, col='media'):
    r = ips_ref()
    s = r[(r['edicao'] == edicao) & (r['recorte'] == recorte) & (r['indicador'] == indicador)]
    return float(s[col].iloc[0]) if len(s) else None


def ips_municipios(edicao: int, indicador: str = INDICE) -> pd.DataFrame:
    d = ips()
    d = d[d['edicao'] == edicao]
    base = d[d['indicador'] == indicador][['cod_ibge_6', 'municipio', 'regiao_desenvolvimento',
                                           'valor', 'rank_br', 'rank_pe']]
    ctx = (d[d['nivel'] == 'contexto'].pivot_table(index='cod_ibge_6', columns='indicador',
                                                    values='valor').reset_index())
    ips_geral = d[d['indicador'] == INDICE][['cod_ibge_6', 'valor']].rename(
        columns={'valor': 'ips'})
    return base.merge(ctx, on='cod_ibge_6', how='left').merge(ips_geral, on='cod_ibge_6',
                                                              how='left')


def ips_resumo(edicao: int) -> dict:
    r = ips_ref()
    r = r[(r['edicao'] == edicao) & (r['indicador'] == INDICE)]
    ufs = r[r['recorte'].str.len() == 2].sort_values('media', ascending=False).reset_index(drop=True)
    pos = ufs.index[ufs['recorte'] == 'PE']
    m = ips_municipios(edicao).sort_values('valor', ascending=False)
    dims = {dim: _ref(edicao, 'PE', dim) for dim in DIMENSOES}
    return {
        'edicao': edicao,
        'media_pe': _ref(edicao, 'PE', INDICE), 'media_ne': _ref(edicao, 'Nordeste', INDICE),
        'media_br': _ref(edicao, 'Brasil', INDICE),
        'pond_pe': _ref(edicao, 'PE', INDICE, 'media_ponderada'),
        'rank_uf': int(pos[0]) + 1 if len(pos) else None, 'n_ufs': len(ufs),
        'melhor': m.iloc[0].to_dict() if len(m) else None,
        'pior': m.iloc[-1].to_dict() if len(m) else None,
        'dims': dims,
        'top1000': int((m['rank_br'] <= 1000).sum()),
    }


def ips_ficha(edicao: int, cod: int = None) -> pd.DataFrame:
    """Dimensões e componentes: município (se houver), média de PE e do Brasil."""
    d = ips()
    d = d[(d['edicao'] == edicao) & d['nivel'].isin(['indice', 'dimensao', 'componente'])]
    ordem = [INDICE]
    for dim in DIMENSOES:
        ordem.append(dim)
        ordem += (d[(d['nivel'] == 'componente') & (d['dimensao'] == dim)]['indicador']
                  .drop_duplicates().tolist())
    linhas = []
    for ind in ordem:
        sub = d[d['indicador'] == ind]
        nivel = sub['nivel'].iloc[0] if len(sub) else 'componente'
        mun = sub[sub['cod_ibge_6'] == cod]['valor'] if cod else pd.Series(dtype=float)
        rk = sub[sub['cod_ibge_6'] == cod]['rank_pe'] if cod else pd.Series(dtype=float)
        linhas.append({'indicador': ind, 'nivel': nivel,
                       'municipio': float(mun.iloc[0]) if len(mun) else None,
                       'rank_pe': int(rk.iloc[0]) if len(rk) and pd.notna(rk.iloc[0]) else None,
                       'pe': _ref(edicao, 'PE', ind), 'br': _ref(edicao, 'Brasil', ind)})
    return pd.DataFrame(linhas)


def ips_indicadores(edicao: int, cod: int) -> pd.DataFrame:
    d = ips()
    d = d[(d['edicao'] == edicao) & (d['cod_ibge_6'] == cod)].set_index('indicador')['valor']
    linhas = []
    for nome, rot, un, maior_melhor in INDICADORES_FICHA:
        if nome not in d.index:
            continue
        linhas.append({'indicador': rot, 'unidade': un, 'valor': d[nome],
                       'pe': _ref(edicao, 'PE', nome), 'br': _ref(edicao, 'Brasil', nome),
                       'maior_melhor': maior_melhor})
    return pd.DataFrame(linhas)


def ips_rds(edicao: int, indicador: str = INDICE) -> pd.DataFrame:
    m = ips_municipios(edicao, indicador)
    g = m.groupby('regiao_desenvolvimento', as_index=False)['valor'].mean()
    return g.sort_values('valor', ascending=False)


def ips_evolucao(cod: int = None) -> pd.DataFrame:
    """IPS por edição: município (se houver), média de PE, Nordeste e Brasil."""
    linhas = []
    for ed in sorted(edicoes()):
        lin = {'edicao': ed, 'pe': _ref(ed, 'PE', INDICE), 'ne': _ref(ed, 'Nordeste', INDICE),
               'br': _ref(ed, 'Brasil', INDICE)}
        if cod:
            d = ips()
            s = d[(d['edicao'] == ed) & (d['cod_ibge_6'] == cod) & (d['indicador'] == INDICE)]
            lin['municipio'] = float(s['valor'].iloc[0]) if len(s) else None
        linhas.append(lin)
    return pd.DataFrame(linhas)


# ============================================================================
# Mortes violentas intencionais
# ============================================================================

@lru_cache(maxsize=None)
def mvi() -> pd.DataFrame:
    return ler(MVI_PE)


def mvi_disponivel() -> bool:
    return not mvi().empty


@lru_cache(maxsize=None)
def mvi_ultima_data() -> pd.Timestamp:
    return mvi()['data'].max()


def mvi_anos() -> list:
    return sorted(mvi()['ano'].unique().tolist(), reverse=True)


def mvi_meses(ano: int) -> int:
    d = mvi()
    return int(d.loc[d['ano'] == ano, 'mes'].max())


def mvi_rotulo(ano: int) -> str:
    return rotulo_ano(ano, mvi_meses(ano))


def mvi_opcoes_anos() -> list:
    return [(mvi_rotulo(a), a) for a in mvi_anos()]


def _f(cod=None):
    d = mvi()
    return d[d['cod_ibge_6'] == cod] if cod else d


def _periodo(d, ano, m):
    return d[(d['ano'] == ano) & (d['mes'] <= m)]


def mvi_mensal(cod: int = None) -> pd.Series:
    d = _f(cod)
    idx = pd.date_range(mvi()['data'].min(), mvi_ultima_data(), freq='MS')
    return d.groupby('data')['vitimas'].sum().reindex(idx, fill_value=0)


def _pop(ano, cod=None):
    p = populacao(ano)
    if p.empty:
        return None
    return float(p.get(cod, float('nan'))) if cod else float(p.sum())


def mvi_resumo(ano: int, cod: int = None) -> dict:
    m = mvi_meses(ano)
    d = _f(cod)
    cur, ant = _periodo(d, ano, m), _periodo(d, ano - 1, m)
    tot, tot_ant = cur['vitimas'].sum(), ant['vitimas'].sum()
    serie = mvi_mensal(cod)
    ult12 = serie.iloc[-12:].sum()
    pop = _pop(mvi_ultima_data().year, cod)
    jovens = cur[cur['faixa_etaria'].isin(['18 a 24', '25 a 29'])]['vitimas'].sum()
    idade_inf = cur[cur['faixa_etaria'] != 'Não informada']['vitimas'].sum()
    r = {'ano': ano, 'meses': m, 'rotulo': mvi_rotulo(ano), 'total': int(tot),
         'total_ant': int(tot_ant),
         'var_pct': 100 * (tot / tot_ant - 1) if tot_ant else None,
         'ult12': int(ult12), 'taxa_12m': 1e5 * ult12 / pop if pop else None,
         'feminicidios': int(cur[cur['natureza'] == 'Feminicídio']['vitimas'].sum()),
         'intervencao': int(cur[cur['natureza'] == 'Intervenção de agente do Estado']['vitimas'].sum()),
         'jovens_pct': 100 * jovens / idade_inf if idade_inf else None,
         'mulheres': int(cur[cur['sexo'] == 'Feminino']['vitimas'].sum())}
    if not cod:
        com = set(cur.loc[cur['vitimas'] > 0, 'cod_ibge_6'].dropna().astype(int))
        r['municipios_sem'] = 185 - len(com)
    return r


def mvi_municipios(ano: int) -> pd.DataFrame:
    """Vítimas e taxa por 100 mil hab. (anualizada em ano incompleto)."""
    m = mvi_meses(ano)
    d = mvi().dropna(subset=['cod_ibge_6'])
    cur = _periodo(d, ano, m).groupby('cod_ibge_6')['vitimas'].sum()
    ant = _periodo(d, ano - 1, m).groupby('cod_ibge_6')['vitimas'].sum()
    base = municipios()[['cod_ibge_6', 'municipio', 'regiao_desenvolvimento']].copy()
    base['vitimas'] = base['cod_ibge_6'].map(cur).fillna(0).astype(int)
    base['vitimas_ant'] = base['cod_ibge_6'].map(ant).fillna(0).astype(int)
    pop = populacao(ano)
    base['populacao'] = base['cod_ibge_6'].map(pop)
    base['taxa'] = 1e5 * base['vitimas'] / base['populacao'] * (12 / m)
    return base


def mvi_rds(ano: int) -> pd.DataFrame:
    m = mvi_meses(ano)
    b = mvi_municipios(ano)
    g = b.groupby('regiao_desenvolvimento', as_index=False)[['vitimas', 'populacao']].sum()
    g['taxa'] = 1e5 * g['vitimas'] / g['populacao'] * (12 / m)
    return g.sort_values('taxa', ascending=False)


def mvi_perfil(ano: int, dim: str, cod: int = None) -> pd.DataFrame:
    m = mvi_meses(ano)
    d = _periodo(_f(cod), ano, m)
    g = d.groupby(dim, as_index=False)['vitimas'].sum()
    tot = g['vitimas'].sum()
    g['part_pct'] = 100 * g['vitimas'] / tot if tot else 0
    return g


def mvi_anual(cod: int = None) -> pd.DataFrame:
    d = _f(cod)
    g = d.groupby('ano').agg(vitimas=('vitimas', 'sum'), meses=('mes', 'max')).reset_index()
    g['populacao'] = [_pop(a, cod) for a in g['ano']]
    g['taxa'] = 1e5 * g['vitimas'] / g['populacao'] * (12 / g['meses'])
    return g
