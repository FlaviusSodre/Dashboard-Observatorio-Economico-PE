"""
etl/populacao_etl.py
====================
População residente dos 185 municípios de Pernambuco, ano a ano, usada
como denominador em indicadores per capita (FPM, transferências) e em
taxas por 100 mil habitantes (mortes violentas).

Fontes (API SIDRA/IBGE):
    - Tabela 6579: estimativas anuais (2001-2006, 2008-2009, 2011-2021,
      2024 em diante)
    - Tabela 4709: população do Censo 2022

Anos sem estimativa (2007, 2010, 2023) são interpolados geometricamente
entre os anos vizinhos. Coluna `origem` registra de onde veio o número.

Output:
    data/processed/populacao_municipal.parquet
    Colunas: cod_ibge_6, cod_ibge_7, ano, populacao, origem

Como rodar: python -m etl.populacao_etl
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import POPULACAO_MUNICIPAL  # noqa: E402
from etl._fontes import sidra, salvar  # noqa: E402


def _estimativas() -> pd.DataFrame:
    df = sidra('/t/6579/n6/in%20n3%2026/v/9324/p/all', 'pop_6579_pe')
    df = df[['D1C', 'D3C', 'valor']].rename(
        columns={'D1C': 'cod_ibge_7', 'D3C': 'ano', 'valor': 'populacao'})
    df['origem'] = 'estimativa'
    return df


def _censo_2022() -> pd.DataFrame:
    df = sidra('/t/4709/n6/in%20n3%2026/v/93/p/2022', 'pop_censo2022_pe')
    df = df[['D1C', 'D3C', 'valor']].rename(
        columns={'D1C': 'cod_ibge_7', 'D3C': 'ano', 'valor': 'populacao'})
    df['origem'] = 'censo'
    return df


def _interpolar(grupo: pd.DataFrame, anos: range) -> pd.DataFrame:
    """Completa os anos faltantes por interpolação geométrica (log-linear)."""
    g = grupo.set_index('ano').sort_index()
    serie = g['populacao'].reindex(anos)
    origem = g['origem'].reindex(anos)
    faltantes = serie.isna()
    log = np.log(serie.astype(float))
    log = log.interpolate(method='index', limit_area='inside')
    serie_int = np.exp(log)
    # Antes do primeiro / depois do último ano conhecido: repete a borda
    serie_int = serie_int.ffill().bfill()
    origem = origem.where(~faltantes, 'interpolada')
    out = pd.DataFrame({'ano': list(anos),
                        'populacao': serie_int.round().values,
                        'origem': origem.values})
    out['cod_ibge_7'] = grupo['cod_ibge_7'].iloc[0]
    return out


def main():
    print("[POP] Baixando população municipal (SIDRA 6579 + Censo 2022)...")
    partes = [_estimativas()]
    try:
        partes.append(_censo_2022())
    except Exception as e:  # o censo é complemento: sem ele, interpola
        print(f"      ! Censo 2022 indisponível ({e}); 2022 será interpolado")
    df = pd.concat(partes, ignore_index=True)
    df['ano'] = df['ano'].astype(int)
    df = df.dropna(subset=['populacao'])

    anos = range(int(df['ano'].min()), int(df['ano'].max()) + 1)
    completo = pd.concat(
        [_interpolar(g, anos) for _, g in df.groupby('cod_ibge_7')],
        ignore_index=True,
    )
    completo['cod_ibge_7'] = completo['cod_ibge_7'].astype(int)
    completo['cod_ibge_6'] = completo['cod_ibge_7'] // 10
    completo['populacao'] = completo['populacao'].astype('int64')
    completo = completo[['cod_ibge_6', 'cod_ibge_7', 'ano', 'populacao',
                         'origem']].sort_values(['ano', 'cod_ibge_6'])

    ult = completo['ano'].max()
    total = completo.loc[completo['ano'] == ult, 'populacao'].sum()
    total_fmt = f"{total:,.0f}".replace(',', '.')
    print(f"[POP] {completo['cod_ibge_6'].nunique()} municípios, "
          f"{anos.start}-{ult}; PE {ult}: {total_fmt} hab.")
    salvar(completo, POPULACAO_MUNICIPAL, 'POP')


if __name__ == '__main__':
    main()
