"""
components/data_base.py
=======================
Funções de apoio comuns às abas da versão 2.0: população municipal,
deflator do IPCA, regiões de desenvolvimento e leitura segura de parquet.

Toda leitura passa por `ler()`, que devolve um DataFrame vazio quando o
arquivo ainda não foi gerado pelo ETL. Assim uma aba nova nunca derruba
o painel: ela mostra um aviso pedindo para rodar o ETL.
"""

from functools import lru_cache
from pathlib import Path

import pandas as pd

from config import ATIVIDADE_MENSAL, DATA_RAW, POPULACAO_MUNICIPAL
from components import data as _data


@lru_cache(maxsize=None)
def ler(path: Path) -> pd.DataFrame:
    """Lê um parquet processado (cache em memória). Vazio se não existir."""
    if not Path(path).exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def existe(path: Path) -> bool:
    return Path(path).exists()


# ============================================================================
# Municípios e RDs
# ============================================================================

@lru_cache(maxsize=None)
def municipios() -> pd.DataFrame:
    """cod_ibge_6, municipio, regiao_desenvolvimento (185 linhas)."""
    return _data.municipios_rd().copy()


def com_rd(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta a coluna regiao_desenvolvimento por cod_ibge_6."""
    m = municipios()[['cod_ibge_6', 'regiao_desenvolvimento']]
    out = df.drop(columns=['regiao_desenvolvimento'], errors='ignore')
    return out.merge(m, on='cod_ibge_6', how='left')


def nome_municipio(cod: int) -> str:
    m = municipios()
    s = m.loc[m['cod_ibge_6'] == cod, 'municipio']
    return s.iloc[0] if len(s) else str(cod)


def lista_rds() -> list:
    return _data.lista_rds()


# ============================================================================
# População
# ============================================================================

@lru_cache(maxsize=None)
def _populacao() -> pd.DataFrame:
    return ler(POPULACAO_MUNICIPAL)


def populacao(ano: int) -> pd.Series:
    """
    População por município (índice cod_ibge_6) no ano pedido. Se o ano for
    posterior ao último disponível, usa o último.
    """
    df = _populacao()
    if df.empty:
        return pd.Series(dtype=float)
    ano_ok = min(int(ano), int(df['ano'].max()))
    ano_ok = max(ano_ok, int(df['ano'].min()))
    s = df[df['ano'] == ano_ok].set_index('cod_ibge_6')['populacao']
    return s.astype(float)


def populacao_pe(ano: int) -> float:
    s = populacao(ano)
    return float(s.sum()) if len(s) else float('nan')


# ============================================================================
# IPCA e deflator
# ============================================================================

@lru_cache(maxsize=None)
def ipca_indice_mensal() -> pd.Series:
    """
    Número-índice do IPCA Brasil (base: último mês = 1), mensal, montado a
    partir da variação mensal (SIDRA 1737). Vazio se o ETL de atividade
    ainda não rodou.
    """
    df = ler(ATIVIDADE_MENSAL)
    if df.empty:
        return pd.Series(dtype=float)
    s = df[(df['fonte'] == 'ipca') & (df['regiao'] == 'Brasil')
           & (df['categoria'] == 'Índice geral')
           & (df['medida'] == 'var_mensal')].set_index('data')['valor'].sort_index()
    if s.empty:
        return s
    indice = (1 + s / 100).cumprod()
    return indice / indice.iloc[-1]


@lru_cache(maxsize=None)
def _ipca_anual() -> pd.Series:
    p = DATA_RAW / 'ipca_anual.csv'
    if not p.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(p)
    df.columns = [c.strip().lower() for c in df.columns]
    col_ano = [c for c in df.columns if 'ano' in c][0]
    col_val = [c for c in df.columns if c != col_ano][0]
    return df.set_index(col_ano)[col_val].astype(float)


def deflator_mensal(datas: pd.Series) -> pd.Series:
    """
    Fator que leva valores nominais de cada mês para preços do último mês
    com IPCA disponível. Sem IPCA mensal, devolve 1 (valores nominais).
    """
    idx = ipca_indice_mensal()
    if idx.empty:
        return pd.Series(1.0, index=datas.index)
    d = pd.to_datetime(datas).dt.to_period('M').dt.to_timestamp()
    fator = 1 / d.map(idx)
    # meses posteriores ao último IPCA: sem correção
    return fator.fillna(1.0)


def mes_referencia_ipca() -> pd.Timestamp:
    idx = ipca_indice_mensal()
    return idx.index.max() if len(idx) else None


# ============================================================================
# Períodos
# ============================================================================

def rotulo_ano(ano: int, ultimo_mes: int) -> str:
    """'2026 (jan–set)' quando o ano está incompleto; '2025' quando completo."""
    from components.viz import periodo_meses
    if ultimo_mes >= 12:
        return str(ano)
    return f"{ano} ({periodo_meses(1, ultimo_mes)})"
