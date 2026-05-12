"""
etl/caged_etl.py
================
Lê o arquivo CAGED_PE.xlsx (duas abas) e produz dois parquets limpos:

    caged_municipal.parquet  -> aba Plan1 (saldo por município, mensal)
    caged_genero.parquet     -> aba Caged MF (saldo por sexo, estadual)

Por que dois arquivos? Granularidades diferentes (município vs estado).
Misturar isso em um arquivo só traria muitos NaN e atrapalharia.

Como rodar:
    python -m etl.caged_etl

(O `-m` faz o Python tratar o arquivo como módulo, o que permite os
imports relativos como `from config import ...` funcionarem.)
"""

import pandas as pd
import sys
from pathlib import Path

# Adiciona a raiz do projeto ao sys.path para conseguir importar `config`
# quando este script é executado diretamente.
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CAGED_RAW, CAGED_MUNICIPAL, CAGED_GENERO


def converter_data_coluna(coluna: pd.Series) -> pd.Series:
    """
    Converte uma coluna de datas para datetime.

    Aceita datas no formato:
    - 01/01/2020
    - 01/04/2020
    - Timestamp do pandas
    - serial number do Excel, se ainda aparecer em alguma aba
    """

    # Caso a coluna venha como número serial do Excel
    if pd.api.types.is_numeric_dtype(coluna):
        data = pd.to_datetime(
            coluna,
            origin='1899-12-30',
            unit='D',
            errors='coerce'
        )
    else:
        # Caso venha como texto ou Timestamp
        data = pd.to_datetime(
            coluna,
            dayfirst=True,
            errors='coerce'
        )

    # Normalizar para o primeiro dia do mês
    data = data.dt.to_period('M').dt.to_timestamp()

    return data


def processar_municipal() -> pd.DataFrame:
    """Lê a aba Plan1 (dados por município) e retorna DataFrame limpo."""
    df = pd.read_excel(CAGED_RAW, sheet_name='Plan1')

    # Renomear colunas para nomes técnicos (sem acentos, sem espaços).
    df.columns = [
        'uf', 'cod_ibge_6', 'municipio', 'admissoes',
        'desligamentos', 'saldo', 'var_relativa', 'data_str'
    ]

    # Converter data no formato 01/01/2020, 01/04/2020 etc.
    df['data'] = converter_data_coluna(df['data_str'])

    # Verificar se alguma data não foi convertida
    if df['data'].isna().any():
        exemplos_invalidos = df.loc[df['data'].isna(), 'data_str'].head(10).tolist()
        raise ValueError(
            f"Existem datas inválidas na aba Plan1. "
            f"Exemplos: {exemplos_invalidos}"
        )

    # Adicionar coluna ano e mes
    df['ano'] = df['data'].dt.year
    df['mes'] = df['data'].dt.month

    # Garantir tipos corretos
    df['cod_ibge_6'] = df['cod_ibge_6'].astype(int)

    # Ordenar
    df = df.sort_values(['data', 'municipio']).reset_index(drop=True)

    # Selecionar e ordenar colunas finais
    return df[[
        'data', 'ano', 'mes', 'uf', 'cod_ibge_6', 'municipio',
        'admissoes', 'desligamentos', 'saldo', 'var_relativa'
    ]]


def processar_genero() -> pd.DataFrame:
    """Lê a aba Caged MF (dados estaduais por gênero)."""
    df = pd.read_excel(CAGED_RAW, sheet_name='Caged MF')

    # Agora aceita tanto data no formato 01/01/2020 quanto serial number do Excel
    df['data'] = converter_data_coluna(df['DATA'])

    # Verificar se alguma data não foi convertida
    if df['data'].isna().any():
        exemplos_invalidos = df.loc[df['data'].isna(), 'DATA'].head(10).tolist()
        raise ValueError(
            f"Existem datas inválidas na aba Caged MF. "
            f"Exemplos: {exemplos_invalidos}"
        )

    # Renomear colunas
    df = df.rename(columns={
        'SEXO': 'sexo',
        'ADMISSÂO': 'admissoes',
        'DESLIGAMENTO': 'desligamentos',
        'SALDO': 'saldo',
        'UF': 'uf',
    })

    df['ano'] = df['data'].dt.year
    df['mes'] = df['data'].dt.month

    df = df.sort_values(['data', 'sexo']).reset_index(drop=True)

    return df[[
        'data', 'ano', 'mes', 'uf', 'sexo',
        'admissoes', 'desligamentos', 'saldo'
    ]]


def main():
    print("[CAGED] Lendo aba Plan1 (municipal)...")
    df_mun = processar_municipal()
    print(f"        {len(df_mun):,} registros, "
          f"{df_mun['municipio'].nunique()} municípios, "
          f"período {df_mun['data'].min().date()} a {df_mun['data'].max().date()}")

    print("[CAGED] Lendo aba Caged MF (gênero)...")
    df_gen = processar_genero()
    print(f"        {len(df_gen):,} registros, "
          f"período {df_gen['data'].min().date()} a {df_gen['data'].max().date()}")

    # Garantir que a pasta processed existe
    CAGED_MUNICIPAL.parent.mkdir(parents=True, exist_ok=True)

    df_mun.to_parquet(CAGED_MUNICIPAL, index=False)
    df_gen.to_parquet(CAGED_GENERO, index=False)

    print(f"[CAGED] Gerado: {CAGED_MUNICIPAL.name}")
    print(f"[CAGED] Gerado: {CAGED_GENERO.name}")


if __name__ == '__main__':
    main()