"""
etl/ips_etl.py
==============
Índice de Progresso Social (IPS Brasil) dos municípios de Pernambuco.

Fonte: IPS Brasil (https://ipsbrasil.org.br/explore/data), arquivos XLSX
"Dataset completo" de cada edição, baixados à mão e salvos em
data/raw/ips/ (ex.: ips-brasil-2026-tabela.xlsx). Cada arquivo traz os
5.570 municípios com o índice, 3 dimensões, 12 componentes e cerca de 57
indicadores.

Para incluir uma edição nova, basta salvar o XLSX nessa pasta e rodar o
ETL. O ano da edição é lido do nome do arquivo.

Aviso da própria fonte: as edições 2024, 2025 e 2026 não são estritamente
comparáveis (mudanças de indicadores e de tratamento estatístico).

Outputs:
    data/processed/ips_pe.parquet
        edicao, cod_ibge_6, municipio, nivel, dimensao, indicador, valor,
        rank_br (1 = melhor entre 5.570), rank_pe (1 = melhor entre 185)
        nivel: indice | dimensao | componente | indicador | contexto
    data/processed/ips_referencias.parquet
        edicao, recorte (Brasil, Nordeste e cada UF pela sigla: PE, BA...),
        nivel, indicador, media, mediana, media_ponderada

Como rodar: python -m etl.ips_etl
"""

import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_PROCESSED, IPS_PE, IPS_RAW_DIR, IPS_REFERENCIAS  # noqa: E402
from etl._aliases import normaliza_municipio  # noqa: E402
from etl._fontes import salvar  # noqa: E402

UF_NORDESTE = {'AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE'}

ESTRUTURA = {
    'Necessidades Humanas Básicas': [
        'Nutrição e Cuidados Médicos Básicos', 'Água e Saneamento', 'Moradia',
        'Segurança Pessoal'],
    'Fundamentos do Bem-estar': [
        'Acesso ao Conhecimento Básico', 'Acesso à Informação e Comunicação',
        'Saúde e Bem-estar', 'Qualidade do Meio Ambiente'],
    'Oportunidades': [
        'Direitos Individuais', 'Liberdades Individuais e de Escolha',
        'Inclusão Social', 'Acesso à Educação Superior'],
}
INDICE = 'Índice de Progresso Social'

# Indicadores com nome diferente entre edições -> nome único
SINONIMOS = {
    'Domicílios com Piso Adequado': 'Domicílios com Pisos Adequados',
    'Mortes por Acidente de Transporte': 'Mortes por Acidentes de Transporte',
    'Densidade de Telefonia Móvel': 'Densidade Telefonia Móvel',
    'Mortalidade por Doenças Crônicas Não Transmissíveis':
        'Mortalidades por Doenças Crônicas Não Transmissíveis',
    'Índice de Vulnerabilidade Climática dos Municípios':
        'Índice de Vulnerabilidade Climática dos Municípios (IVCM)',
    'Taxa de Congestionamento Líquido de Processos':
        'Taxa de Congestionamento Líquida de Processos',
    'Gravidez na Adolescência (<19 anos)': 'Gravidez na Adolescência (<19)',
    'Consumo de Alimentos Ultraprocessados': 'Consumo de ultraprocessados',
    'Nota Mediana do Enem': 'Nota Mediana no Enem',
}


def _norm(s) -> str:
    s = unicodedata.normalize('NFKD', str(s))
    return ''.join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _edicao(path: Path) -> int:
    m = re.search(r'(20\d\d)', path.name)
    if not m:
        raise ValueError(f"ano da edição não encontrado no nome: {path.name}")
    return int(m.group(1))


def _numero(v):
    """Converte células com '-' (sem dado) ou vírgula decimal."""
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip()
    if t in ('', '-', '–', '—', 'nan', 'None', 'NA', 'n/d'):
        return float('nan')
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    try:
        return float(t)
    except ValueError:
        return float('nan')


def _ler(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path)
    # cabeçalho pode vir com espaços/maiúsculas diferentes
    ren = {}
    for c in df.columns:
        n = _norm(c)
        if n == 'municipio':
            ren[c] = 'municipio'
        elif n == 'uf':
            ren[c] = 'uf'
        elif n.startswith('populacao'):
            ren[c] = 'populacao'
        elif n.startswith('area km'):
            ren[c] = 'area_km2'
        elif n.startswith('pib per capita'):
            ren[c] = 'pib_per_capita'
        elif n.startswith('codigo ibge'):
            ren[c] = 'codigo_ibge'
    df = df.rename(columns=ren)
    # nomes canônicos (caixa da edição mais recente) para dimensões/componentes
    canon = {_norm(x): x for x in [INDICE] + list(ESTRUTURA) +
             [c for cs in ESTRUTURA.values() for c in cs]}
    df = df.rename(columns={c: canon.get(_norm(c), c) for c in df.columns})
    df = df.rename(columns=SINONIMOS)
    for c in df.columns:
        if c not in ('municipio', 'uf', 'codigo_ibge') and df[c].dtype == object:
            df[c] = df[c].map(_numero)
    return df


def _nivel(col: str) -> tuple:
    if col == INDICE:
        return 'indice', None
    if col in ESTRUTURA:
        return 'dimensao', col
    for dim, comps in ESTRUTURA.items():
        if col in comps:
            return 'componente', dim
    if col in ('populacao', 'area_km2', 'pib_per_capita'):
        return 'contexto', None
    return 'indicador', None


def processar() -> tuple:
    arquivos = sorted(IPS_RAW_DIR.glob('*.xlsx')) if IPS_RAW_DIR.exists() else []
    if not arquivos:
        raise FileNotFoundError(
            f"nenhum XLSX do IPS Brasil em {IPS_RAW_DIR} (veja o README)")
    rd = pd.read_parquet(DATA_PROCESSED / 'municipios_rd.parquet')
    mapa = {normaliza_municipio(n): (c, n) for c, n in zip(rd['cod_ibge_6'], rd['municipio'])}

    pe_partes, ref_partes = [], []
    for arq in arquivos:
        ed = _edicao(arq)
        df = _ler(arq)
        df['uf'] = df['uf'].astype(str).str.strip().str.upper()
        valores = [c for c in df.columns
                   if c not in ('municipio', 'uf', 'codigo_ibge')
                   and pd.api.types.is_numeric_dtype(df[c])]
        # Ranks nacionais (1 = melhor) do índice, dimensões e componentes
        pontuacoes = [c for c in valores if _nivel(c)[0] in ('indice', 'dimensao', 'componente')]
        ranks_br = df[pontuacoes].rank(ascending=False, method='min')

        # Referências: Brasil, Nordeste e cada UF
        for nome, filtro in ([('Brasil', df['uf'].notna()),
                              ('Nordeste', df['uf'].isin(UF_NORDESTE))]
                             + [(uf, df['uf'] == uf) for uf in sorted(df['uf'].unique())]):
            sub = df[filtro]
            pesos = sub['populacao'] if 'populacao' in sub else None
            for c in valores:
                niv = _nivel(c)[0]
                s = sub[c]
                mp = ((s * pesos).sum() / pesos[s.notna()].sum()
                      if pesos is not None and pesos[s.notna()].sum() else None)
                ref_partes.append({'edicao': ed, 'recorte': nome,
                                   'nivel': niv, 'indicador': c, 'media': s.mean(),
                                   'mediana': s.median(), 'media_ponderada': mp})

        pe = df[df['uf'] == 'PE'].copy()
        chaves = pe['municipio'].map(normaliza_municipio)
        pe['cod_ibge_6'] = chaves.map(lambda k: mapa.get(k, (None, None))[0])
        pe['municipio_canon'] = chaves.map(lambda k: mapa.get(k, (None, None))[1])
        sem = pe.loc[pe['cod_ibge_6'].isna(), 'municipio'].tolist()
        if sem:
            print(f"[IPS] AVISO {ed}: sem código IBGE: {sem}")
        pe = pe.dropna(subset=['cod_ibge_6'])
        ranks_pe = pe[pontuacoes].rank(ascending=False, method='min')
        longo = pe[['cod_ibge_6', 'municipio_canon'] + valores].melt(
            id_vars=['cod_ibge_6', 'municipio_canon'], var_name='indicador',
            value_name='valor')
        rk_br = (ranks_br.loc[pe.index].assign(cod_ibge_6=pe['cod_ibge_6'])
                 .melt(id_vars='cod_ibge_6', var_name='indicador', value_name='rank_br'))
        rk_pe = (ranks_pe.assign(cod_ibge_6=pe['cod_ibge_6'])
                 .melt(id_vars='cod_ibge_6', var_name='indicador', value_name='rank_pe'))
        longo = (longo.merge(rk_br, on=['cod_ibge_6', 'indicador'], how='left')
                      .merge(rk_pe, on=['cod_ibge_6', 'indicador'], how='left'))
        niveis = longo['indicador'].map(_nivel)
        longo['nivel'] = niveis.str[0]
        longo['dimensao'] = niveis.str[1]
        longo['edicao'] = ed
        pe_partes.append(longo.rename(columns={'municipio_canon': 'municipio'}))
        print(f"[IPS] edição {ed}: {pe['cod_ibge_6'].nunique()} municípios de PE, "
              f"{len(valores)} colunas numéricas")

    pe = pd.concat(pe_partes, ignore_index=True)
    pe['cod_ibge_6'] = pe['cod_ibge_6'].astype(int)
    pe = pe[['edicao', 'cod_ibge_6', 'municipio', 'nivel', 'dimensao', 'indicador',
             'valor', 'rank_br', 'rank_pe']]
    ref = pd.DataFrame(ref_partes)
    return pe, ref


def main():
    print("[IPS] Índice de Progresso Social (IPS Brasil)...")
    pe, ref = processar()
    salvar(pe, IPS_PE, 'IPS')
    salvar(ref, IPS_REFERENCIAS, 'IPS')
    ult = pe['edicao'].max()
    m = ref[(ref['edicao'] == ult) & (ref['indicador'] == INDICE)].set_index('recorte')['media']
    print(f"[IPS] {ult}: média dos municípios · PE {m.get('PE', float('nan')):.2f} "
          f"· NE {m.get('Nordeste', float('nan')):.2f} · BR {m.get('Brasil', float('nan')):.2f}")


if __name__ == '__main__':
    main()
