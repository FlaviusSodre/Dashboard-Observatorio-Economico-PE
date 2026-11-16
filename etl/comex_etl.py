"""
etl/comex_etl.py
================
Comércio exterior de Pernambuco a partir da API do Comex Stat (MDIC),
em US$ FOB, desde 2019, mais a classificação do agronegócio do Agrostat
(MAPA).

Duas óticas da mesma fonte
--------------------------
- "UF do produto" (endpoint /general): onde a mercadoria foi produzida
  (exportação) ou a que estado se destina (importação). É a ótica dos
  números oficiais de comércio exterior dos estados.
- "Município do domicílio fiscal da empresa" (endpoint /cities): usada
  para a abertura por município. Os totais das duas óticas diferem.

Atenção a um detalhe da API: o período "AAAA-MM a AAAA-MM" vale para
cada ano do intervalo (jan-out de 2019 a 2026 devolve jan-out de cada
ano). Por isso as consultas são feitas ano a ano.

Cache: data/cache/comex/. Anos fechados há mais de um ano não são
baixados de novo; o ano corrente e o anterior são sempre atualizados
(o MDIC revisa os meses recentes).

Outputs (data/processed/):
    comex_uf_mensal.parquet          data, ano, mes, fluxo, uf, regiao, valor_fob
    comex_pe_ncm_mensal.parquet      data, ano, mes, fluxo, ncm, valor_fob, kg
    comex_pe_pais_mensal.parquet     data, ano, mes, fluxo, pais, valor_fob
    comex_pe_ncm_pais_anual.parquet  ano, meses, fluxo, ncm, pais, valor_fob
    comex_ncm.parquet                ncm, descricao, sh4, sh4_descricao,
                                     agro, agro_setor, agro_subsetor, agro_produto
    comex_municipios_mensal.parquet  data, ano, mes, fluxo, cod_ibge_6, municipio, valor_fob
    comex_municipios_sh4_anual.parquet ano, meses, fluxo, cod_ibge_6, sh4, valor_fob

Como rodar: python -m etl.comex_etl
"""

import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (AGROSTAT_RAW, COMEX_MUN_MENSAL, COMEX_MUN_SH4_ANUAL,  # noqa: E402
                    COMEX_NCM, COMEX_NCM_MENSAL, COMEX_NCM_PAIS_ANUAL,
                    COMEX_PAIS_MENSAL, COMEX_UF_MENSAL, DATA_PROCESSED)
from etl._aliases import normaliza_municipio  # noqa: E402
from etl._fontes import (FonteIndisponivel, baixar_json, ler_json,  # noqa: E402
                         modo_offline, pasta_cache, salvar)

API = 'https://api-comexstat.mdic.gov.br'
ANO_INICIAL = 2019
UF_PE = 26
FLUXOS = ('export', 'import')
PAUSA = 1.0  # segundos entre consultas (gentileza com a API pública)

UF_NORDESTE = {'Alagoas', 'Bahia', 'Ceará', 'Maranhão', 'Paraíba', 'Pernambuco',
               'Piauí', 'Rio Grande do Norte', 'Sergipe'}

# Consultas feitas para cada ano e fluxo: nome -> (endpoint, detalhes,
# filtrar PE, detalhar mês, métricas)
CONSULTAS = {
    'uf_mes': ('/general', ['state'], False, True, ['metricFOB']),
    'pe_ncm_mes': ('/general', ['ncm'], True, True, ['metricFOB', 'metricKG']),
    'pe_pais_mes': ('/general', ['country'], True, True, ['metricFOB']),
    'pe_ncm_pais': ('/general', ['ncm', 'country'], True, False, ['metricFOB']),
    'pe_sh4': ('/general', ['heading'], True, False, ['metricFOB']),
    'mun_mes': ('/cities', ['city'], True, True, ['metricFOB']),
    'mun_sh4': ('/cities', ['city', 'heading'], True, False, ['metricFOB']),
}


# ============================================================================
# Download
# ============================================================================

def _ultimo_mes() -> tuple:
    """(ano, mês) mais recente divulgado pelo Comex Stat."""
    destino = pasta_cache('comex') / 'atualizacao.json'
    try:
        j = baixar_json(f"{API}/general/dates/updated", destino, rotulo='Comex atualização')
    except FonteIndisponivel:
        hoje = date.today()
        return hoje.year, max(hoje.month - 2, 1)
    d = j['data']
    return int(d['year']), int(d['monthNumber'])


def _consultar(nome: str, ano: int, mes_fim: int, fluxo: str, atualizar: bool) -> list:
    endpoint, detalhes, so_pe, por_mes, metricas = CONSULTAS[nome]
    destino = pasta_cache('comex') / f"{nome}_{fluxo}_{ano}.json"
    if destino.exists() and (not atualizar or modo_offline()):
        return ler_json(destino)['data']['list']
    corpo = {
        'flow': fluxo, 'monthDetail': por_mes,
        'period': {'from': f'{ano}-01', 'to': f'{ano}-{mes_fim:02d}'},
        'filters': [{'filter': 'state', 'values': [UF_PE]}] if so_pe else [],
        'details': detalhes, 'metrics': metricas,
    }

    def _valida(obj):
        if 'data' not in obj or 'list' not in obj['data']:
            raise ValueError(f"resposta inesperada: {str(obj)[:200]}")

    j = baixar_json(f"{API}{endpoint}", destino, metodo='POST', json_body=corpo,
                    rotulo=f"Comex {nome} {fluxo} {ano}", validar=_valida, timeout=180)
    if not modo_offline():
        time.sleep(PAUSA)
    return j['data']['list']


def baixar_tudo() -> tuple:
    """
    Devolve {(nome, fluxo, ano): lista}, (ano, mês) mais recentes e a lista
    das consultas que não baixaram e não tinham cópia no cache.
    """
    ano_fim, mes_fim = _ultimo_mes()
    print(f"[CMX] Comex Stat atualizado até {mes_fim:02d}/{ano_fim}")
    dados, faltando = {}, []
    for ano in range(ANO_INICIAL, ano_fim + 1):
        ultimo_mes = mes_fim if ano == ano_fim else 12
        atualizar = ano >= ano_fim - 1
        for nome in CONSULTAS:
            for fluxo in FLUXOS:
                try:
                    dados[(nome, fluxo, ano)] = _consultar(nome, ano, ultimo_mes,
                                                           fluxo, atualizar)
                except FonteIndisponivel as e:
                    faltando.append(f"{nome} {fluxo} {ano}")
                    print(f"      ! {nome} {fluxo} {ano}: {e}")
    return dados, (ano_fim, mes_fim), faltando


# ============================================================================
# Processamento
# ============================================================================

def _df(dados: dict, nome: str) -> pd.DataFrame:
    partes = []
    for (n, fluxo, ano), lista in dados.items():
        if n != nome or not lista:
            continue
        d = pd.DataFrame(lista)
        d['fluxo'] = fluxo
        partes.append(d)
    if not partes:
        return pd.DataFrame()
    d = pd.concat(partes, ignore_index=True)
    for c in ('metricFOB', 'metricKG'):
        if c in d:
            d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0.0)
    d = d.rename(columns={'ncm': 'ncm_desc', 'coNcm': 'ncm',
                          'heading': 'sh4_descricao', 'headingCode': 'sh4'})
    d['ano'] = d['year'].astype(int)
    if 'monthNumber' in d:
        d['mes'] = d['monthNumber'].astype(int)
        d['data'] = pd.to_datetime(dict(year=d['ano'], month=d['mes'], day=1))
    return d.rename(columns={'metricFOB': 'valor_fob', 'metricKG': 'kg'})


def _meses_por_ano(ult: tuple) -> dict:
    ano_fim, mes_fim = ult
    return {a: (mes_fim if a == ano_fim else 12) for a in range(ANO_INICIAL, ano_fim + 1)}


def _municipio_cod(nomes: pd.Series) -> pd.Series:
    rd = pd.read_parquet(DATA_PROCESSED / 'municipios_rd.parquet')
    mapa = {normaliza_municipio(n): c for c, n in zip(rd['cod_ibge_6'], rd['municipio'])}
    chave = nomes.str.replace(r'\s*-\s*PE$', '', regex=True).map(normaliza_municipio)
    return chave.map(mapa)


def _agrostat() -> pd.DataFrame:
    """NCMs do agronegócio (Agrostat/MAPA), baixadas pelo usuário em data/raw."""
    if not AGROSTAT_RAW.exists():
        print(f"      ! {AGROSTAT_RAW.name} não encontrado: aba Agronegócio ficará vazia")
        return pd.DataFrame(columns=['ncm', 'agro_setor', 'agro_subsetor', 'agro_produto'])
    df = pd.read_excel(AGROSTAT_RAW, header=None, dtype=str)
    col_ncm = df.columns[3]
    m = df[col_ncm].fillna('').str.extract(r'^(\d{8})\s*-')
    df = df.assign(ncm=m[0]).dropna(subset=['ncm'])

    def bonito(s):
        s = re.sub(r'\s+', ' ', str(s)).strip().capitalize()
        return re.sub(r'\(([a-z])', lambda x: '(' + x.group(1), s)
    return pd.DataFrame({'ncm': df['ncm'], 'agro_setor': df[0].map(bonito),
                         'agro_subsetor': df[1].map(bonito),
                         'agro_produto': df[2].map(bonito)}).drop_duplicates('ncm')


def processar(dados: dict, ult: tuple) -> dict:
    meses = _meses_por_ano(ult)
    saida = {}

    uf = _df(dados, 'uf_mes')
    uf = uf.rename(columns={'state': 'uf'})
    uf['regiao'] = uf['uf'].map(lambda u: 'Nordeste' if u in UF_NORDESTE else 'Outras')
    saida['uf'] = uf[['data', 'ano', 'mes', 'fluxo', 'uf', 'regiao', 'valor_fob']]

    ncm = _df(dados, 'pe_ncm_mes')
    saida['ncm_mes'] = ncm[['data', 'ano', 'mes', 'fluxo', 'ncm', 'valor_fob', 'kg']]

    pais = _df(dados, 'pe_pais_mes').rename(columns={'country': 'pais'})
    saida['pais_mes'] = pais[['data', 'ano', 'mes', 'fluxo', 'pais', 'valor_fob']]

    np_ = _df(dados, 'pe_ncm_pais').rename(columns={'country': 'pais'})
    np_['meses'] = np_['ano'].map(meses)
    saida['ncm_pais'] = np_[['ano', 'meses', 'fluxo', 'ncm', 'pais', 'valor_fob']]

    # Dimensão NCM: descrição mais recente, SH4 e classificação Agrostat
    base = (pd.concat([ncm[['ncm', 'ncm_desc', 'ano']], np_[['ncm', 'ncm_desc', 'ano']]])
              .sort_values('ano').drop_duplicates('ncm', keep='last'))
    dim = pd.DataFrame({'ncm': base['ncm'], 'descricao': base['ncm_desc']})
    dim['sh4'] = dim['ncm'].str[:4]
    sh4 = pd.concat([_df(dados, 'pe_sh4'), _df(dados, 'mun_sh4')])
    sh4 = (sh4.sort_values('ano').drop_duplicates('sh4', keep='last')
              [['sh4', 'sh4_descricao']])
    dim = dim.merge(sh4, on='sh4', how='left')
    dim = dim.merge(_agrostat(), on='ncm', how='left')
    dim['agro'] = dim['agro_setor'].notna()
    saida['ncm'] = dim.reset_index(drop=True)

    mun = _df(dados, 'mun_mes')
    mun['cod_ibge_6'] = _municipio_cod(mun['noMunMinsgUf'])
    sem = sorted(mun.loc[mun['cod_ibge_6'].isna(), 'noMunMinsgUf'].unique())
    if sem:
        print(f"[CMX] AVISO: municípios sem código: {sem[:8]}")
    mun = mun.dropna(subset=['cod_ibge_6'])
    mun['cod_ibge_6'] = mun['cod_ibge_6'].astype(int)
    mun['municipio'] = mun['noMunMinsgUf'].str.replace(r'\s*-\s*PE$', '', regex=True)
    saida['mun_mes'] = mun[['data', 'ano', 'mes', 'fluxo', 'cod_ibge_6', 'municipio',
                            'valor_fob']]

    ms = _df(dados, 'mun_sh4')
    ms['cod_ibge_6'] = _municipio_cod(ms['noMunMinsgUf'])
    ms = ms.dropna(subset=['cod_ibge_6'])
    ms['cod_ibge_6'] = ms['cod_ibge_6'].astype(int)
    ms['meses'] = ms['ano'].map(meses)
    saida['mun_sh4'] = ms[['ano', 'meses', 'fluxo', 'cod_ibge_6', 'sh4', 'valor_fob']]
    return saida


def main():
    print("[CMX] Comércio exterior (Comex Stat/MDIC, US$ FOB)...")
    dados, ult, faltando = baixar_tudo()
    if not dados:
        raise FonteIndisponivel("nenhum dado do Comex Stat no cache")
    if faltando:
        # Sem uma consulta, o ano dela sairia com valor menor que o real. Melhor
        # não gravar e repetir: o que já baixou fica no cache e não é pedido de novo.
        raise FonteIndisponivel(
            f"{len(faltando)} consulta(s) não baixaram ({', '.join(faltando[:6])}"
            f"{'...' if len(faltando) > 6 else ''}). As bases do Comex não foram "
            "gravadas; rode de novo esta etapa para completar")
    s = processar(dados, ult)
    destinos = {'uf': COMEX_UF_MENSAL, 'ncm_mes': COMEX_NCM_MENSAL,
                'pais_mes': COMEX_PAIS_MENSAL, 'ncm_pais': COMEX_NCM_PAIS_ANUAL,
                'ncm': COMEX_NCM, 'mun_mes': COMEX_MUN_MENSAL,
                'mun_sh4': COMEX_MUN_SH4_ANUAL}
    for k, destino in destinos.items():
        salvar(s[k].reset_index(drop=True), destino, 'CMX')

    pe = s['uf'][s['uf']['uf'] == 'Pernambuco']
    a = ult[0] - 1
    exp = pe[(pe['ano'] == a) & (pe['fluxo'] == 'export')]['valor_fob'].sum()
    imp = pe[(pe['ano'] == a) & (pe['fluxo'] == 'import')]['valor_fob'].sum()
    print(f"[CMX] PE {a}: exportações US$ {exp / 1e9:.2f} bi · "
          f"importações US$ {imp / 1e9:.2f} bi".replace('.', ','))
    agro = s['ncm']['agro'].sum()
    print(f"[CMX] {len(s['ncm'])} NCMs de PE, {agro} classificadas como agronegócio")


if __name__ == '__main__':
    main()
