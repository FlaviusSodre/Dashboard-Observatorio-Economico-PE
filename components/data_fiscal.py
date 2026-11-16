"""
components/data_fiscal.py
=========================
Consultas das sub-abas FPM e Transferências (Gestão Pública), a partir de
data/processed/transferencias_pe.parquet (ver etl/transferencias_etl.py).

Conceitos usados no painel
--------------------------
FPM bruto     = FPM creditado + retenção do FUNDEB sobre o FPM + parcelas
                extras de 1% (julho, setembro e dezembro).
Total creditado (aba Transferências) = o que de fato entra na conta do
                município: todas as categorias, exceto as retenções do
                FUNDEB (que voltam ao município como "FUNDEB recebido").
Comparação anual: num ano incompleto, compara-se com os mesmos meses do
                ano anterior.
"""

from functools import lru_cache

import pandas as pd

from config import TRANSFERENCIAS_PE
from components import data as _data
from components.data_base import (com_rd, deflator_mensal, ler,
                                  mes_referencia_ipca, populacao, rotulo_ano)

CAT_FPM = ['fpm', 'fpm_deducao', 'fpm_1pct']
CAT_RETENCOES = ['fpm_deducao', 'itr_deducao']

GRUPO = {
    'fpm': 'FPM', 'fpm_1pct': 'FPM',
    'fundeb': 'FUNDEB',
    'royalties': 'Royalties',
    'itr': 'Demais', 'lei_kandir': 'Demais', 'apoio': 'Demais',
    'cide': 'Demais', 'iof_ouro': 'Demais', 'outras': 'Demais',
}
ORDEM_GRUPOS = ['FPM', 'FUNDEB', 'Royalties', 'Demais']

ROTULO_CATEGORIA = {
    'fpm': 'FPM (creditado)',
    'fpm_1pct': 'FPM · parcelas extras de 1%',
    'fundeb': 'FUNDEB recebido',
    'royalties': 'Royalties e compensações financeiras',
    'itr': 'ITR (cota-parte)',
    'lei_kandir': 'Lei Kandir · LC 87/96 e LC 176/2020',
    'apoio': 'Apoio financeiro · AFM/AFE e LC 173/2020',
    'cide': 'CIDE-Combustíveis',
    'iof_ouro': 'IOF-Ouro',
    'outras': 'Outras',
}

ROTULO_ROYALTIES = {
    'ANP': 'Petróleo e gás (ANP)',
    'FEP': 'Fundo Especial do Petróleo (FEP)',
    'CFEM': 'Mineração (CFEM)',
    'CFH': 'Recursos hídricos (CFH)',
}


# ============================================================================
# Base
# ============================================================================

@lru_cache(maxsize=None)
def trf() -> pd.DataFrame:
    df = ler(TRANSFERENCIAS_PE)
    if df.empty:
        return df
    df = com_rd(df)
    df['grupo'] = df['categoria'].map(GRUPO)
    return df


def disponivel() -> bool:
    return not trf().empty


@lru_cache(maxsize=None)
def ultima_data() -> pd.Timestamp:
    return trf()['data'].max()


@lru_cache(maxsize=None)
def anos() -> list:
    return sorted(trf()['ano'].unique().tolist(), reverse=True)


def meses_no_ano(ano: int) -> int:
    d = trf()
    return int(d.loc[d['ano'] == ano, 'mes'].max())


def rotulo(ano: int) -> str:
    return rotulo_ano(ano, meses_no_ano(ano))


def opcoes_anos() -> list:
    return [(rotulo(a), a) for a in anos()]


def _filtro(df, cod=None, rd=None):
    if cod:
        df = df[df['cod_ibge_6'] == cod]
    elif rd:
        df = df[df['regiao_desenvolvimento'] == rd]
    return df


def _periodo(df, ano, ate_mes):
    return df[(df['ano'] == ano) & (df['mes'] <= ate_mes)]


# ============================================================================
# FPM
# ============================================================================

def fpm_mensal(cod: int = None) -> pd.DataFrame:
    """Série mensal do FPM (estado ou município): ordinário bruto, extra 1%."""
    d = _filtro(trf(), cod)
    d = d[d['categoria'].isin(CAT_FPM)]
    piv = (d.pivot_table(index='data', columns='categoria', values='valor',
                         aggfunc='sum')
             .reindex(columns=CAT_FPM).fillna(0.0))
    out = pd.DataFrame({
        'ordinario': piv['fpm'] + piv['fpm_deducao'],
        'extra_1pct': piv['fpm_1pct'],
        'creditado': piv['fpm'] + piv['fpm_1pct'],
        'retencao_fundeb': piv['fpm_deducao'],
    })
    out['bruto'] = out['ordinario'] + out['extra_1pct']
    out = out.reset_index()
    out['ano'] = out['data'].dt.year
    out['mes'] = out['data'].dt.month
    out['bruto_real'] = out['bruto'] * deflator_mensal(out['data']).values
    return out


def fpm_por_municipio(ano: int) -> pd.DataFrame:
    """FPM bruto no ano (ou nos meses disponíveis) por município, com
    comparação com os mesmos meses do ano anterior e valor per capita."""
    m = meses_no_ano(ano)
    d = trf()
    d = d[d['categoria'].isin(CAT_FPM)]
    atual = _periodo(d, ano, m).groupby('cod_ibge_6')['valor'].sum()
    ant = _periodo(d, ano - 1, m).groupby('cod_ibge_6')['valor'].sum()
    extra = (_periodo(d[d['categoria'] == 'fpm_1pct'], ano, m)
             .groupby('cod_ibge_6')['valor'].sum())
    out = pd.DataFrame({'bruto': atual, 'bruto_ant': ant, 'extra_1pct': extra})
    out = out[out['bruto'].notna()].fillna({'extra_1pct': 0.0}).reset_index()
    out['var_pct'] = 100 * (out['bruto'] / out['bruto_ant'] - 1)
    pop = populacao(ano)
    out['populacao'] = out['cod_ibge_6'].map(pop)
    out['per_capita'] = out['bruto'] / out['populacao']
    nomes = (trf()[['cod_ibge_6', 'municipio', 'regiao_desenvolvimento']]
             .drop_duplicates('cod_ibge_6'))
    out = out.merge(nomes, on='cod_ibge_6', how='left')
    out['rank_total'] = out['bruto'].rank(ascending=False, method='min')
    out['rank_pc'] = out['per_capita'].rank(ascending=False, method='min')
    return out


def fpm_rds(ano: int) -> pd.DataFrame:
    df = fpm_por_municipio(ano)
    g = df.groupby('regiao_desenvolvimento', as_index=False)[
        ['bruto', 'bruto_ant', 'populacao']].sum()
    g['per_capita'] = g['bruto'] / g['populacao']
    g['var_pct'] = 100 * (g['bruto'] / g['bruto_ant'] - 1)
    return g


def _pib_municipio(cod: int):
    """PIB municipal mais recente (para a razão FPM/PIB)."""
    try:
        pib = _data.pib_municipal()
    except Exception:
        return None, None
    s = pib[pib['cod_ibge_6'] == cod] if cod else pib
    if s.empty:
        return None, None
    ano = int(s['ano'].max())
    return float(s.loc[s['ano'] == ano, 'pib'].sum()), ano


def fpm_resumo(ano: int, cod: int = None) -> dict:
    """Números dos KPIs da sub-aba FPM (estado ou município)."""
    m = meses_no_ano(ano)
    s = fpm_mensal(cod)
    cur = _periodo(s, ano, m)
    ant = _periodo(s, ano - 1, m)
    r = {'ano': ano, 'meses': m, 'rotulo': rotulo(ano),
         'bruto': cur['bruto'].sum(), 'bruto_ant': ant['bruto'].sum(),
         'extra_1pct': cur['extra_1pct'].sum(),
         'retencao_fundeb': cur['retencao_fundeb'].sum()}
    r['var_nominal'] = (100 * (r['bruto'] / r['bruto_ant'] - 1)
                        if r['bruto_ant'] else None)
    real_cur, real_ant = cur['bruto_real'].sum(), ant['bruto_real'].sum()
    r['ipca_ref'] = mes_referencia_ipca()
    r['var_real'] = (100 * (real_cur / real_ant - 1)
                     if (real_ant and r['ipca_ref'] is not None) else None)

    pop = populacao(ano)
    r['populacao'] = float(pop.get(cod, float('nan'))) if cod else float(pop.sum())
    r['per_capita'] = r['bruto'] / r['populacao'] if r['populacao'] else None

    # Razão FPM/PIB no último ano com PIB
    pib, ano_pib = _pib_municipio(cod)
    if pib and ano_pib in s['ano'].values:
        fpm_ano_pib = s.loc[s['ano'] == ano_pib, 'bruto'].sum()
        r['fpm_pib'] = 100 * fpm_ano_pib / pib
        r['ano_pib'] = ano_pib
    else:
        r['fpm_pib'], r['ano_pib'] = None, None

    # Último decêndio com valor
    dec = fpm_decendios(cod, n_meses=13)
    if not dec.empty:
        u = dec.iloc[-1]
        r['ult_dec'] = u.to_dict()
    else:
        r['ult_dec'] = None

    if cod:
        tab = fpm_por_municipio(ano).set_index('cod_ibge_6')
        if cod in tab.index:
            r['municipio'] = tab.at[cod, 'municipio']
            r['rd'] = tab.at[cod, 'regiao_desenvolvimento']
            r['rank_total'] = int(tab.at[cod, 'rank_total'])
            r['rank_pc'] = int(tab.at[cod, 'rank_pc'])
            r['n_municipios'] = len(tab)
    return r


def fpm_decendios(cod: int = None, n_meses: int = 12) -> pd.DataFrame:
    """
    FPM bruto por decêndio nos últimos n meses, com o mesmo decêndio do
    ano anterior. Decêndios: 1º (dia 10), 2º (dia 20) e 3º (último dia útil).
    """
    d = _filtro(trf(), cod)
    d = d[d['categoria'].isin(CAT_FPM)]
    # Meses que vieram da série consolidada não têm decêndios: ficam de fora
    sem_detalhe = d.groupby('data')['dec1'].apply(lambda s: s.isna().any())
    d = d[~d['data'].isin(sem_detalhe[sem_detalhe].index)]
    g = d.groupby('data')[['dec1', 'dec2', 'dec3']].sum()
    longo = (g.stack().rename('valor').reset_index()
               .rename(columns={'level_1': 'decendio'}))
    longo['decendio'] = longo['decendio'].str[-1].astype(int)
    longo = longo.sort_values(['data', 'decendio'])
    ant = longo.copy()
    ant['data'] = ant['data'] + pd.DateOffset(years=1)
    longo = longo.merge(ant.rename(columns={'valor': 'valor_ant'}),
                        on=['data', 'decendio'], how='left')
    longo = longo[longo['valor'].abs() > 0.5]
    datas = sorted(longo['data'].unique())[-n_meses:]
    longo = longo[longo['data'].isin(datas)].reset_index(drop=True)
    longo['var_pct'] = 100 * (longo['valor'] / longo['valor_ant'] - 1)
    return longo


def fpm_anual(cod: int = None) -> pd.DataFrame:
    """FPM bruto por ano, nominal e real (preços do último mês com IPCA)."""
    s = fpm_mensal(cod)
    g = s.groupby('ano').agg(nominal=('bruto', 'sum'), real=('bruto_real', 'sum'),
                             extra_1pct=('extra_1pct', 'sum'),
                             meses=('mes', 'nunique')).reset_index()
    return g


# ============================================================================
# Transferências (todas as categorias)
# ============================================================================

def trf_grupos(ano: int, cod: int = None, rd: str = None) -> pd.DataFrame:
    """Total creditado por grupo no ano (e nos mesmos meses do ano anterior)."""
    m = meses_no_ano(ano)
    d = _filtro(trf(), cod, rd)
    d = d[~d['categoria'].isin(CAT_RETENCOES)]
    cur = _periodo(d, ano, m).groupby('grupo')['valor'].sum()
    ant = _periodo(d, ano - 1, m).groupby('grupo')['valor'].sum()
    out = (pd.DataFrame({'valor': cur, 'valor_ant': ant})
             .reindex(ORDEM_GRUPOS).fillna(0.0).reset_index())
    out['var_pct'] = 100 * (out['valor'] / out['valor_ant'].where(out['valor_ant'] != 0) - 1)
    return out


def trf_categorias(ano: int, cod: int = None, rd: str = None) -> pd.DataFrame:
    """Detalhe por categoria (para a tabela da aba)."""
    m = meses_no_ano(ano)
    d = _filtro(trf(), cod, rd)
    d = d[~d['categoria'].isin(CAT_RETENCOES)]
    cur = _periodo(d, ano, m).groupby('categoria')['valor'].sum()
    ant = _periodo(d, ano - 1, m).groupby('categoria')['valor'].sum()
    out = pd.DataFrame({'valor': cur, 'valor_ant': ant}).fillna(0.0)
    out = out[(out['valor'] != 0) | (out['valor_ant'] != 0)].reset_index()
    out['rotulo'] = out['categoria'].map(ROTULO_CATEGORIA).fillna(out['categoria'])
    out['grupo'] = out['categoria'].map(GRUPO)
    tot = out['valor'].sum()
    out['part_pct'] = 100 * out['valor'] / tot if tot else 0.0
    out['var_pct'] = 100 * (out['valor'] / out['valor_ant'].where(out['valor_ant'] != 0) - 1)
    out['_ord'] = out['grupo'].map({g: i for i, g in enumerate(ORDEM_GRUPOS)})
    return out.sort_values(['_ord', 'valor'], ascending=[True, False]).drop(columns='_ord')


def trf_municipal(ano: int, grupo: str = 'Total') -> pd.DataFrame:
    """Total creditado (ou de um grupo) por município, com per capita."""
    m = meses_no_ano(ano)
    d = trf()
    d = d[~d['categoria'].isin(CAT_RETENCOES)]
    if grupo != 'Total':
        d = d[d['grupo'] == grupo]
    cur = _periodo(d, ano, m).groupby('cod_ibge_6')['valor'].sum()
    ant = _periodo(d, ano - 1, m).groupby('cod_ibge_6')['valor'].sum()
    out = pd.DataFrame({'valor': cur, 'valor_ant': ant}).reset_index()
    out = out[out['valor'].notna()]
    out['var_pct'] = 100 * (out['valor'] / out['valor_ant'].where(out['valor_ant'] > 0) - 1)
    pop = populacao(ano)
    out['populacao'] = out['cod_ibge_6'].map(pop)
    out['per_capita'] = out['valor'] / out['populacao']
    nomes = (trf()[['cod_ibge_6', 'municipio', 'regiao_desenvolvimento']]
             .drop_duplicates('cod_ibge_6'))
    return out.merge(nomes, on='cod_ibge_6', how='left')


def trf_anual_grupos(cod: int = None, rd: str = None) -> pd.DataFrame:
    """Total creditado por ano e grupo (para a evolução)."""
    d = _filtro(trf(), cod, rd)
    d = d[~d['categoria'].isin(CAT_RETENCOES)]
    g = d.groupby(['ano', 'grupo'])['valor'].sum().unstack('grupo')
    g = g.reindex(columns=ORDEM_GRUPOS).fillna(0.0)
    g['meses'] = d.groupby('ano')['mes'].nunique()
    return g.reset_index()


def royalties_tipos(ano: int, cod: int = None) -> pd.DataFrame:
    m = meses_no_ano(ano)
    d = _filtro(trf(), cod)
    d = _periodo(d[d['categoria'] == 'royalties'], ano, m)
    g = d.groupby('item', as_index=False)['valor'].sum()
    g['rotulo'] = g['item'].map(ROTULO_ROYALTIES).fillna(g['item'])
    return g.sort_values('valor', ascending=False)


def royalties_municipios(ano: int, n: int = 10) -> pd.DataFrame:
    m = meses_no_ano(ano)
    d = _periodo(trf()[trf()['categoria'] == 'royalties'], ano, m)
    g = d.groupby(['cod_ibge_6', 'municipio'], as_index=False)['valor'].sum()
    return g.sort_values('valor', ascending=False).head(n)


def trf_resumo(ano: int, cod: int = None) -> dict:
    g = trf_grupos(ano, cod).set_index('grupo')
    tot, tot_ant = g['valor'].sum(), g['valor_ant'].sum()
    pop = populacao(ano)
    popv = float(pop.get(cod, float('nan'))) if cod else float(pop.sum())
    r = {'ano': ano, 'rotulo': rotulo(ano), 'total': tot, 'total_ant': tot_ant,
         'var_pct': 100 * (tot / tot_ant - 1) if tot_ant else None,
         'per_capita': tot / popv if popv else None,
         'grupos': g.to_dict('index')}
    r['part_fpm'] = 100 * g.at['FPM', 'valor'] / tot if tot else None
    if cod:
        tab = trf_municipal(ano).set_index('cod_ibge_6')
        if cod in tab.index:
            r['municipio'] = tab.at[cod, 'municipio']
            r['rd'] = tab.at[cod, 'regiao_desenvolvimento']
            r['rank_pc'] = int(tab['per_capita'].rank(ascending=False,
                                                      method='min').at[cod])
            r['n_municipios'] = len(tab)
    return r
