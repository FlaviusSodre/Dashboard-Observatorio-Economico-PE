"""
etl/seguranca_etl.py
====================
Mortes Violentas Intencionais (MVI) em Pernambuco, a partir dos
microdados da Secretaria de Defesa Social (SDS-PE).

Fonte: https://www.sds.pe.gov.br/estatisticas/indicadores-criminais/mortes-violentas-intencionais-mvi
    Planilha "MICRODADOS_DE_MVI_JAN_2004_A_<MÊS>_<ANO>.xlsx", uma linha por
    vítima, com município, região, sexo, natureza jurídica, data e idade.
    O nome do arquivo muda todo mês; o ETL lê a página e pega o link atual.
    A SDS consolida o mês até o dia 15 do mês seguinte.

MVI reúne homicídio, feminicídio, latrocínio, lesão corporal seguida de
morte e morte por intervenção de agente do Estado. CVLI (crimes violentos
letais intencionais) = MVI sem as mortes por intervenção do Estado.

Output:
    data/processed/mvi_pe.parquet  (vítimas agregadas)
    Colunas: data, ano, mes, cod_ibge_6, municipio, sexo, faixa_etaria,
             natureza, vitimas

Como rodar: python -m etl.seguranca_etl
"""

import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_PROCESSED, MVI_PE  # noqa: E402
from etl._aliases import normaliza_basico, normaliza_municipio  # noqa: E402
from etl._fontes import (FonteIndisponivel, baixar_para_cache, http,  # noqa: E402
                         modo_offline, pasta_cache, salvar)

PAGINA = ('https://www.sds.pe.gov.br/estatisticas/indicadores-criminais/'
          'mortes-violentas-intencionais-mvi')
_RE_LINK = re.compile(r'href="([^"]*MICRODADOS[^"]*MVI[^"]*\.xlsx)"', re.I)

NATUREZA = {
    'homicidio': 'Homicídio',
    'feminicidio': 'Feminicídio',
    'latrocinio': 'Latrocínio',
    'lesoes corporais seguida de morte': 'Lesão corporal seguida de morte',
    'lesao corporal seguida de morte': 'Lesão corporal seguida de morte',
    'morte por intervencao legal de agente do estado': 'Intervenção de agente do Estado',
}
SEXO = {'masculino': 'Masculino', 'feminino': 'Feminino'}
FAIXAS = [(0, 11, '0 a 11'), (12, 17, '12 a 17'), (18, 24, '18 a 24'),
          (25, 29, '25 a 29'), (30, 39, '30 a 39'), (40, 49, '40 a 49'),
          (50, 59, '50 a 59'), (60, 200, '60 ou mais')]


def _faixa(idade) -> str:
    try:
        i = int(float(idade))
    except (TypeError, ValueError):
        return 'Não informada'
    for a, b, rot in FAIXAS:
        if a <= i <= b:
            return rot
    return 'Não informada'


# ============================================================================
# Download
# ============================================================================

def _baixar() -> Path:
    pasta = pasta_cache('seguranca')
    existentes = sorted(pasta.glob('*.xlsx'), key=lambda p: p.stat().st_mtime)
    if modo_offline():
        if existentes:
            return existentes[-1]
        raise FonteIndisponivel("modo offline e sem planilha da SDS no cache")
    try:
        html = http(PAGINA, timeout=60).text
        m = _RE_LINK.search(html)
        if not m:
            raise FonteIndisponivel("link dos microdados não encontrado na página da SDS")
        url = urljoin(PAGINA, m.group(1))
        nome = Path(m.group(1)).name
        destino = pasta / nome
        if not destino.exists():
            print(f"      ↓ {nome}")

            def _valida(conteudo: bytes):
                if not conteudo.startswith(b'PK'):
                    raise ValueError("o arquivo baixado não é uma planilha xlsx")
            baixar_para_cache(url, destino, timeout=300, validar=_valida,
                              rotulo='microdados MVI')
        else:
            print(f"      = {nome} (já no cache)")
        return destino
    except Exception as e:
        if existentes:
            print(f"      ! SDS indisponível ({e}); usando {existentes[-1].name}")
            return existentes[-1]
        raise


# ============================================================================
# Processamento
# ============================================================================

def _ler_planilha(path: Path) -> pd.DataFrame:
    """Acha a aba de microdados (a que tem MUNICIPIO e NATUREZA)."""
    abas = pd.read_excel(path, sheet_name=None)
    for nome, df in abas.items():
        cols = {normaliza_basico(c): c for c in df.columns}
        if 'municipio' in cols and any(k.startswith('natureza') for k in cols):
            return df.rename(columns={v: k for k, v in cols.items()})
    raise ValueError(f"aba de microdados não encontrada em {path.name}: {list(abas)}")


def processar(path: Path) -> pd.DataFrame:
    df = _ler_planilha(path)
    col_nat = [c for c in df.columns if c.startswith('natureza')][0]
    col_vit = [c for c in df.columns if c.startswith('total')]
    data = df['data']
    if not pd.api.types.is_datetime64_any_dtype(data):
        num = pd.to_numeric(data, errors='coerce')
        data = pd.to_datetime(num, unit='D', origin='1899-12-30').where(
            num.notna(), pd.to_datetime(df['data'], errors='coerce', dayfirst=True))
    out = pd.DataFrame({
        'data': pd.to_datetime(data).dt.to_period('M').dt.to_timestamp(),
        'municipio_sds': df['municipio'].astype(str).str.strip(),
        'sexo': df['sexo'].map(lambda s: SEXO.get(normaliza_basico(s), 'Não informado')),
        'faixa_etaria': df['idade'].map(_faixa) if 'idade' in df else 'Não informada',
        'natureza': df[col_nat].map(lambda s: NATUREZA.get(normaliza_basico(s), 'Outras')),
        'vitimas': pd.to_numeric(df[col_vit[0]], errors='coerce').fillna(1) if col_vit else 1,
    })
    out = out.dropna(subset=['data'])

    rd = pd.read_parquet(DATA_PROCESSED / 'municipios_rd.parquet')
    mapa = {normaliza_municipio(n): (c, n) for c, n in zip(rd['cod_ibge_6'], rd['municipio'])}
    chaves = out['municipio_sds'].map(normaliza_municipio)
    out['cod_ibge_6'] = chaves.map(lambda k: mapa.get(k, (None, None))[0])
    out['municipio'] = chaves.map(lambda k: mapa.get(k, (None, None))[1])
    sem = out.loc[out['cod_ibge_6'].isna(), 'municipio_sds'].value_counts()
    nao_inf = sem[sem.index.str.upper().str.contains('INFORMAD')].sum()
    outros = sem[~sem.index.str.upper().str.contains('INFORMAD')]
    if len(outros):
        print(f"[SEG] AVISO: municípios sem código IBGE: {outros.to_dict()}")
    if nao_inf:
        print(f"[SEG] {int(nao_inf)} vítimas sem município informado (entram só no total do estado)")
    out['municipio'] = out['municipio'].fillna('Não informado')
    out['cod_ibge_6'] = out['cod_ibge_6'].astype('Int64')

    agg = (out.groupby(['data', 'cod_ibge_6', 'municipio', 'sexo', 'faixa_etaria',
                        'natureza'], dropna=False, as_index=False)['vitimas'].sum())
    agg['ano'] = agg['data'].dt.year
    agg['mes'] = agg['data'].dt.month
    agg['vitimas'] = agg['vitimas'].astype(int)
    return agg[['data', 'ano', 'mes', 'cod_ibge_6', 'municipio', 'sexo',
                'faixa_etaria', 'natureza', 'vitimas']].sort_values('data')


def main():
    print("[SEG] Mortes violentas intencionais (microdados SDS-PE)...")
    arq = _baixar()
    df = processar(arq)
    ult = df['data'].max()
    tot_ano = df[df['ano'] == ult.year]['vitimas'].sum()
    print(f"[SEG] {int(df['vitimas'].sum()):,} vítimas de "
          f"{df['data'].min():%m/%Y} a {ult:%m/%Y}; {ult.year} até agora: "
          f"{int(tot_ano):,}".replace(',', '.'))
    salvar(df.reset_index(drop=True), MVI_PE, 'SEG')


if __name__ == '__main__':
    main()
