"""
components/data_comex.py
========================
Consultas do eixo Comércio Exterior (Comex Stat/MDIC, US$ FOB) e do
agronegócio (classificação Agrostat/MAPA). Ver etl/comex_etl.py.

Comparações anuais: num ano incompleto (ex.: 2026 até outubro), o ano
anterior é cortado nos mesmos meses, para comparar períodos iguais.
"""

import re
from functools import lru_cache

import pandas as pd

from config import (COMEX_MUN_MENSAL, COMEX_MUN_SH4_ANUAL, COMEX_NCM,
                    COMEX_NCM_MENSAL, COMEX_NCM_PAIS_ANUAL, COMEX_PAIS_MENSAL,
                    COMEX_UF_MENSAL)
from components.data_base import com_rd, ler, populacao, rotulo_ano

FLUXOS = [('Exportações', 'export'), ('Importações', 'import')]
NOME_FLUXO = {'export': 'exportações', 'import': 'importações'}


def nome_curto(desc: str, limite: int = 46) -> str:
    """Encurta descrições longas do SH/NCM para rótulos de gráfico."""
    if not isinstance(desc, str) or not desc:
        return '—'
    d = re.split(r'\s\(|;|, (?:exceto|incluíd|mesmo|e suas|com )', desc)[0].strip()
    if len(d) > limite:
        d = d[:limite].rsplit(' ', 1)[0].rstrip(',') + '…'
    return d


# ============================================================================
# Carga
# ============================================================================

@lru_cache(maxsize=None)
def uf_mensal():
    return ler(COMEX_UF_MENSAL)


@lru_cache(maxsize=None)
def ncm_mensal():
    d = ler(COMEX_NCM_MENSAL)
    if d.empty:
        return d
    d = d.merge(dim_ncm()[['ncm', 'sh4', 'agro', 'agro_setor', 'agro_produto']],
                on='ncm', how='left')
    d['agro'] = d['agro'].fillna(False).astype(bool)
    return d


@lru_cache(maxsize=None)
def pais_mensal():
    return ler(COMEX_PAIS_MENSAL)


@lru_cache(maxsize=None)
def ncm_pais_anual():
    d = ler(COMEX_NCM_PAIS_ANUAL)
    if d.empty:
        return d
    return d.merge(dim_ncm()[['ncm', 'sh4', 'agro', 'agro_setor']], on='ncm', how='left')


@lru_cache(maxsize=None)
def dim_ncm():
    return ler(COMEX_NCM)


@lru_cache(maxsize=None)
def dim_sh4() -> pd.DataFrame:
    d = dim_ncm()
    if d.empty:
        return d
    s = d.dropna(subset=['sh4_descricao']).drop_duplicates('sh4')[['sh4', 'sh4_descricao']]
    s['nome'] = s['sh4_descricao'].map(nome_curto)
    return s


@lru_cache(maxsize=None)
def mun_mensal():
    d = ler(COMEX_MUN_MENSAL)
    return com_rd(d) if not d.empty else d


@lru_cache(maxsize=None)
def mun_sh4_anual():
    return ler(COMEX_MUN_SH4_ANUAL)


def disponivel() -> bool:
    return not uf_mensal().empty


@lru_cache(maxsize=None)
def ultima_data() -> pd.Timestamp:
    return uf_mensal()['data'].max()


def anos() -> list:
    return sorted(uf_mensal()['ano'].unique().tolist(), reverse=True)


def meses_no_ano(ano: int) -> int:
    d = uf_mensal()
    return int(d.loc[d['ano'] == ano, 'mes'].max())


def rotulo(ano: int) -> str:
    return rotulo_ano(ano, meses_no_ano(ano))


def opcoes_anos() -> list:
    return [(rotulo(a), a) for a in anos()]


def _soma(df, ano, m, chaves=None, col='valor_fob'):
    d = df[(df['ano'] == ano) & (df['mes'] <= m)]
    if chaves:
        return d.groupby(chaves)[col].sum()
    return d[col].sum()


def _comparar(df, ano, chave, n=None):
    """Valor no ano (até o mês disponível) x mesmos meses do ano anterior."""
    m = meses_no_ano(ano)
    cur = _soma(df, ano, m, chave)
    ant = _soma(df, ano - 1, m, chave)
    out = pd.DataFrame({'valor': cur, 'valor_ant': ant}).fillna(0.0)
    out = out[out['valor'] > 0].reset_index()
    tot = out['valor'].sum()
    out['part_pct'] = 100 * out['valor'] / tot if tot else 0
    out['var_pct'] = 100 * (out['valor'] / out['valor_ant'].where(out['valor_ant'] > 0) - 1)
    out = out.sort_values('valor', ascending=False)
    return out.head(n) if n else out


# ============================================================================
# Balança comercial
# ============================================================================

def _regiao(df, regiao):
    if regiao == 'Pernambuco':
        return df[df['uf'] == 'Pernambuco']
    if regiao == 'Nordeste':
        return df[df['regiao'] == 'Nordeste']
    return df


def balanca_mensal(regiao: str = 'Pernambuco') -> pd.DataFrame:
    d = _regiao(uf_mensal(), regiao)
    p = d.pivot_table(index='data', columns='fluxo', values='valor_fob',
                      aggfunc='sum').reindex(columns=['export', 'import']).fillna(0.0)
    p['saldo'] = p['export'] - p['import']
    p['corrente'] = p['export'] + p['import']
    for c in ('export', 'import', 'saldo'):
        p[f'{c}_12m'] = p[c].rolling(12).sum()
    return p.reset_index()


def balanca_anual(regiao: str = 'Pernambuco') -> pd.DataFrame:
    m = balanca_mensal(regiao)
    m['ano'] = m['data'].dt.year
    g = m.groupby('ano').agg(export=('export', 'sum'), importacao=('import', 'sum'),
                             meses=('data', 'nunique')).reset_index()
    g = g.rename(columns={'importacao': 'import'})
    g['saldo'] = g['export'] - g['import']
    return g


def resumo(ano: int) -> dict:
    d = uf_mensal()
    m = meses_no_ano(ano)
    r = {'ano': ano, 'meses': m, 'rotulo': rotulo(ano)}
    for fluxo in ('export', 'import'):
        df = d[d['fluxo'] == fluxo]
        pe = df[df['uf'] == 'Pernambuco']
        r[fluxo] = _soma(pe, ano, m)
        r[f'{fluxo}_ant'] = _soma(pe, ano - 1, m)
        r[f'var_{fluxo}'] = (100 * (r[fluxo] / r[f'{fluxo}_ant'] - 1)
                             if r[f'{fluxo}_ant'] else None)
        ne = _soma(df[df['regiao'] == 'Nordeste'], ano, m)
        br = _soma(df, ano, m)
        r[f'part_ne_{fluxo}'] = 100 * r[fluxo] / ne if ne else None
        r[f'part_br_{fluxo}'] = 100 * r[fluxo] / br if br else None
    r['saldo'] = r['export'] - r['import']
    r['saldo_ant'] = r['export_ant'] - r['import_ant']
    r['corrente'] = r['export'] + r['import']
    r['corrente_ant'] = r['export_ant'] + r['import_ant']
    r['var_corrente'] = (100 * (r['corrente'] / r['corrente_ant'] - 1)
                         if r['corrente_ant'] else None)
    return r


def ranking_nordeste(ano: int, fluxo: str) -> pd.DataFrame:
    d = uf_mensal()
    d = d[(d['regiao'] == 'Nordeste') & (d['fluxo'] == fluxo)]
    return _comparar(d, ano, 'uf')


# ============================================================================
# Produtos e mercados
# ============================================================================

def produtos(ano: int, fluxo: str, n: int = None) -> pd.DataFrame:
    d = ncm_mensal()
    d = d[d['fluxo'] == fluxo]
    out = _comparar(d, ano, 'sh4', n)
    return out.merge(dim_sh4(), on='sh4', how='left').assign(
        nome=lambda x: x['nome'].fillna(x['sh4']))


def mercados(ano: int, fluxo: str, n: int = None) -> pd.DataFrame:
    d = pais_mensal()
    return _comparar(d[d['fluxo'] == fluxo], ano, 'pais', n)


def produto_mercados(ano: int, fluxo: str, sh4: str, n: int = 12) -> pd.DataFrame:
    d = ncm_pais_anual()
    d = d[(d['ano'] == ano) & (d['fluxo'] == fluxo) & (d['sh4'] == sh4)]
    g = d.groupby('pais', as_index=False)['valor_fob'].sum()
    tot = g['valor_fob'].sum()
    g['part_pct'] = 100 * g['valor_fob'] / tot if tot else 0
    return g.sort_values('valor_fob', ascending=False).head(n)


def mercado_produtos(ano: int, fluxo: str, pais: str, n: int = 12) -> pd.DataFrame:
    d = ncm_pais_anual()
    d = d[(d['ano'] == ano) & (d['fluxo'] == fluxo) & (d['pais'] == pais)]
    g = d.groupby('sh4', as_index=False)['valor_fob'].sum()
    tot = g['valor_fob'].sum()
    g['part_pct'] = 100 * g['valor_fob'] / tot if tot else 0
    g = g.merge(dim_sh4(), on='sh4', how='left')
    g['nome'] = g['nome'].fillna(g['sh4'])
    return g.sort_values('valor_fob', ascending=False).head(n)


def serie_produto(fluxo: str, sh4: str) -> pd.Series:
    d = ncm_mensal()
    d = d[(d['fluxo'] == fluxo) & (d['sh4'] == sh4)]
    return d.groupby('data')['valor_fob'].sum().sort_index()


# ============================================================================
# Municípios
# ============================================================================

def municipios(ano: int, fluxo: str) -> pd.DataFrame:
    d = mun_mensal()
    d = d[d['fluxo'] == fluxo]
    out = _comparar(d, ano, 'cod_ibge_6')
    nomes = d.drop_duplicates('cod_ibge_6')[['cod_ibge_6', 'regiao_desenvolvimento']]
    from components.data_base import municipios as _mun
    out = out.merge(_mun()[['cod_ibge_6', 'municipio']], on='cod_ibge_6', how='left')
    out = out.merge(nomes, on='cod_ibge_6', how='left')
    pop = populacao(ano)
    out['per_capita'] = out['valor'] / out['cod_ibge_6'].map(pop)
    return out


def municipio_produtos(ano: int, fluxo: str, cod: int, n: int = 10) -> pd.DataFrame:
    d = mun_sh4_anual()
    d = d[(d['ano'] == ano) & (d['fluxo'] == fluxo) & (d['cod_ibge_6'] == cod)]
    g = d.groupby('sh4', as_index=False)['valor_fob'].sum()
    tot = g['valor_fob'].sum()
    g['part_pct'] = 100 * g['valor_fob'] / tot if tot else 0
    g = g.merge(dim_sh4(), on='sh4', how='left')
    g['nome'] = g['nome'].fillna(g['sh4'])
    return g.sort_values('valor_fob', ascending=False).head(n)


def municipio_serie(cod: int) -> pd.DataFrame:
    d = mun_mensal()
    d = d[d['cod_ibge_6'] == cod]
    return (d.pivot_table(index='data', columns='fluxo', values='valor_fob',
                          aggfunc='sum').reindex(columns=['export', 'import'])
             .fillna(0.0).reset_index())


# ============================================================================
# Agronegócio (exportações)
# ============================================================================

def agro_disponivel() -> bool:
    d = dim_ncm()
    return not d.empty and bool(d['agro'].any())


def agro_anual() -> pd.DataFrame:
    d = ncm_mensal()
    d = d[d['fluxo'] == 'export']
    g = d.groupby(['ano', 'agro'])['valor_fob'].sum().unstack('agro').fillna(0.0)
    g = g.rename(columns={True: 'agro', False: 'demais'})
    for c in ('agro', 'demais'):
        if c not in g:
            g[c] = 0.0
    g['total'] = g['agro'] + g['demais']
    g['part_pct'] = 100 * g['agro'] / g['total']
    g['meses'] = d.groupby('ano')['mes'].max()
    return g.reset_index()


def agro_resumo(ano: int) -> dict:
    d = ncm_mensal()
    d = d[d['fluxo'] == 'export']
    m = meses_no_ano(ano)
    ag = d[d['agro']]
    r = {'ano': ano, 'rotulo': rotulo(ano), 'valor': _soma(ag, ano, m),
         'valor_ant': _soma(ag, ano - 1, m), 'total': _soma(d, ano, m)}
    r['var_pct'] = 100 * (r['valor'] / r['valor_ant'] - 1) if r['valor_ant'] else None
    r['part_pct'] = 100 * r['valor'] / r['total'] if r['total'] else None
    return r


def agro_setores(ano: int) -> pd.DataFrame:
    d = ncm_mensal()
    d = d[(d['fluxo'] == 'export') & d['agro']]
    return _comparar(d, ano, 'agro_setor')


def agro_produtos(ano: int, n: int = 12) -> pd.DataFrame:
    d = ncm_mensal()
    d = d[(d['fluxo'] == 'export') & d['agro']]
    return _comparar(d, ano, 'agro_produto', n)


def agro_destinos(ano: int, n: int = 12) -> pd.DataFrame:
    d = ncm_pais_anual()
    d = d[(d['ano'] == ano) & (d['fluxo'] == 'export') & (d['agro'] == True)]  # noqa: E712
    g = d.groupby('pais', as_index=False)['valor_fob'].sum()
    tot = g['valor_fob'].sum()
    g['part_pct'] = 100 * g['valor_fob'] / tot if tot else 0
    return g.sort_values('valor_fob', ascending=False).head(n)


def agro_sazonalidade(setor: str = None) -> pd.DataFrame:
    """Exportações do agronegócio por mês (linhas = anos)."""
    d = ncm_mensal()
    d = d[(d['fluxo'] == 'export') & d['agro']]
    if setor:
        d = d[d['agro_setor'] == setor]
    return d.groupby(['ano', 'mes'], as_index=False)['valor_fob'].sum()
