"""
etl/pnad_etl.py
===============
Lê o arquivo PNAD_PE.xlsx (7 abas, uma por indicador) e produz um único
parquet em formato "long" (uma linha por trimestre × indicador).

Por que long? Porque é o formato natural para gráficos com múltiplas
séries no Plotly e para filtros dinâmicos. Em formato wide, adicionar
um novo indicador exigiria mudar o schema; em long, é só adicionar
linhas.

Schema final:
    data            -> último mês do trimestre (ex: 2024-03-01 para 1ºT/2024)
    trimestre       -> string legível (ex: "2024-T1")
    ano             -> ano numérico (útil para filtros)
    uf              -> "PE"
    indicador       -> chave técnica (ex: "taxa_desocupacao")
    indicador_nome  -> nome legível (ex: "Taxa de desocupação")
    valor           -> valor numérico
    unidade         -> unidade ("%", "pessoas", "R$")

Como rodar:
    python -m etl.pnad_etl
"""

import pandas as pd
import sys
import re
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import PNAD_REGIONAL_RAW_DIR, PNAD_PE


INDICADORES = {
    "SALDO OCUPAÇÃO": {
        "chave": "ocupados",
        "nome": "População ocupada",
        "unidade": "pessoas",
        "mult": 1,
        "arquivos_possiveis": [
            "SALDO OCUPAÇÃO.xlsx",
            "SALDO OCUPACAO.xlsx",
            "OCUPADOS.xlsx",
        ],
    },
    "SALDO DESOCUPAÇÃO": {
        "chave": "desocupados",
        "nome": "População desocupada",
        "unidade": "pessoas",
        "mult": 1,
        "arquivos_possiveis": [
            "SALDO DESOCUPAÇÃO.xlsx",
            "SALDO DESOCUPACAO.xlsx",
            "DESOCUPADOS.xlsx",
        ],
    },
    "NIVEL DE OCUPAÇÃO": {
        "chave": "nivel_ocupacao",
        "nome": "Nível de ocupação",
        "unidade": "%",
        "mult": 1,
        "arquivos_possiveis": [
            "NIVEL DE OCUPAÇÃO.xlsx",
            "NÍVEL DE OCUPAÇÃO.xlsx",
            "NIVEL DE OCUPACAO.xlsx",
        ],
    },
    "TAXA DE DESOCUPAÇÃO": {
        "chave": "taxa_desocupacao",
        "nome": "Taxa de desocupação",
        "unidade": "%",
        "mult": 1,
        "arquivos_possiveis": [
            "TAXA DE DESOCUPAÇÃO.xlsx",
            "TAXA DE DESOCUPACAO.xlsx",
        ],
    },
    "INFORMALIDADE": {
        "chave": "informalidade",
        "nome": "Taxa de informalidade",
        "unidade": "%",
        "mult": 1,
        "arquivos_possiveis": [
            "INFORMALIDADE.xlsx",
        ],
    },
    "RENDIMENTO MÉDIO MENSAL": {
        "chave": "rendimento_medio",
        "nome": "Rendimento médio mensal",
        "unidade": "R$",
        "mult": 1,
        "arquivos_possiveis": [
            "RENDIMENTO MÉDIO MENSAL.xlsx",
            "RENDIMENTO MEDIO MENSAL.xlsx",
        ],
    },
    "DESALENTADOS": {
        "chave": "desalentados",
        "nome": "Pessoas desalentadas",
        "unidade": "pessoas",
        "mult": 1,
        "arquivos_possiveis": [
            "DESALENTADOS.xlsx",
        ],
    },
}


def normalizar_texto(texto: str) -> str:
    texto = str(texto).strip().lower()

    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))

    texto = re.sub(r"[^a-z0-9]+", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()

    return texto


def normalizar_colunas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [
        normalizar_texto(c).replace(" ", "_")
        for c in df.columns
    ]
    return df


def localizar_arquivo(meta: dict) -> Path:
    arquivos = [
        p for p in PNAD_REGIONAL_RAW_DIR.glob("*.xls*")
        if not p.name.startswith("~$")
    ]

    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum arquivo Excel encontrado em {PNAD_REGIONAL_RAW_DIR}"
        )

    nomes_disponiveis = {
        normalizar_texto(p.name): p
        for p in arquivos
    }

    for nome in meta["arquivos_possiveis"]:
        nome_norm = normalizar_texto(nome)

        if nome_norm in nomes_disponiveis:
            return nomes_disponiveis[nome_norm]

    disponiveis = [p.name for p in arquivos]

    raise FileNotFoundError(
        "Arquivo não encontrado. "
        f"Procurei por {meta['arquivos_possiveis']}. "
        f"Arquivos disponíveis: {disponiveis}"
    )


def converter_valor(valor):
    """
    Converte valores vindos da planilha.

    Exemplos:
    - '114.111'    -> 114111
    - '1.043.788'  -> 1043788
    - '10,5'       -> 10.5
    - 289518       -> 289518
    """

    if pd.isna(valor):
        return pd.NA

    if isinstance(valor, (int, float)):
        return valor

    texto = str(valor).strip()

    texto = texto.replace("R$", "").replace("%", "").strip()

    # Caso brasileiro com decimal: 10,5
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
        return pd.to_numeric(texto, errors="coerce")

    # Caso de milhares: 1.043.788 ou 114.111
    if "." in texto:
        texto = texto.replace(".", "")
        return pd.to_numeric(texto, errors="coerce")

    return pd.to_numeric(texto, errors="coerce")


def criar_data_trimestre(ano, trimestre) -> pd.Timestamp:
    """
    Converte Ano + Trimestre para data.

    Exemplo:
    2025, 1 -> 2025-03-01
    2025, 2 -> 2025-06-01
    2025, 3 -> 2025-09-01
    2025, 4 -> 2025-12-01
    """

    ano = int(ano)
    trimestre = int(trimestre)

    mes_final_trimestre = trimestre * 3

    return pd.Timestamp(
        year=ano,
        month=mes_final_trimestre,
        day=1
    )


def trimestre_label(data: pd.Timestamp) -> str:
    q = (data.month - 1) // 3 + 1
    return f"{data.year}-T{q}"


def processar_arquivo(meta: dict) -> pd.DataFrame:
    arquivo = localizar_arquivo(meta)

    df = pd.read_excel(arquivo)
    df = normalizar_colunas(df)

    colunas_necessarias = {"ano", "trimestre", "regiao", "valor"}

    faltantes = colunas_necessarias - set(df.columns)

    if faltantes:
        raise ValueError(
            f"O arquivo {arquivo.name} não possui as colunas esperadas. "
            f"Faltando: {faltantes}. "
            f"Colunas encontradas: {list(df.columns)}"
        )

    # Filtrar apenas Pernambuco
    df = df[df["regiao"].astype(str).str.strip().str.lower() == "pernambuco"].copy()

    if df.empty:
        raise ValueError(
            f"Nenhuma linha de Pernambuco encontrada em {arquivo.name}"
        )

    df["data"] = df.apply(
        lambda row: criar_data_trimestre(row["ano"], row["trimestre"]),
        axis=1
    )

    df["valor"] = df["valor"].apply(converter_valor)

    if df["valor"].isna().any():
        exemplos = df.loc[df["valor"].isna()].head(10)
        raise ValueError(
            f"Existem valores inválidos no arquivo {arquivo.name}.\n"
            f"Exemplos:\n{exemplos}"
        )

    df["valor"] = df["valor"] * meta["mult"]

    df["uf"] = "PE"
    df["indicador"] = meta["chave"]
    df["indicador_nome"] = meta["nome"]
    df["unidade"] = meta["unidade"]
    df["ano"] = df["data"].dt.year
    df["trimestre"] = df["data"].apply(trimestre_label)

    df = df.sort_values("data").reset_index(drop=True)

    return df[
        [
            "data",
            "trimestre",
            "ano",
            "uf",
            "indicador",
            "indicador_nome",
            "valor",
            "unidade",
        ]
    ]


def main():
    print("[PNAD_PE] Processando indicadores a partir de pnad_regional...")
    print(f"[PNAD_PE] Pasta fonte: {PNAD_REGIONAL_RAW_DIR}")

    dfs = []

    for nome_indicador, meta in INDICADORES.items():
        try:
            df_indicador = processar_arquivo(meta)

            print(
                f"        {meta['chave']:20s} "
                f"{len(df_indicador):4d} registros | "
                f"{df_indicador['data'].min().date()} a "
                f"{df_indicador['data'].max().date()}"
            )

            dfs.append(df_indicador)

        except Exception as e:
            print(f"        ✗ ERRO em {nome_indicador}: {e}")

    if not dfs:
        raise RuntimeError(
            "Nenhum indicador foi processado. "
            "Verifique os arquivos dentro da pasta pnad_regional."
        )

    pnad = pd.concat(dfs, ignore_index=True)

    pnad = pnad.sort_values(
        ["indicador", "data"]
    ).reset_index(drop=True)

    # Aviso sobre Informalidade zerada
    inf = pnad[pnad["indicador"] == "informalidade"]

    if not inf.empty and (inf["valor"] == 0).all():
        print()
        print("[PNAD_PE] ⚠ AVISO: Indicador 'informalidade' está com todos os")
        print("[PNAD_PE]   valores zerados na fonte. Será mantido no parquet.")
        print("[PNAD_PE]   O dashboard pode marcar como 'sem dados'.")

    PNAD_PE.parent.mkdir(parents=True, exist_ok=True)

    pnad.to_parquet(PNAD_PE, index=False)

    print()
    print(f"[PNAD_PE] Gerado: {PNAD_PE.name} ({len(pnad)} linhas)")
    print(f"[PNAD_PE] Caminho: {PNAD_PE}")


if __name__ == "__main__":
    main()