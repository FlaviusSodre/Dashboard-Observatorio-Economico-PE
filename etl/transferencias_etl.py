"""
etl/transferencias_etl.py
=========================
Transferências constitucionais da União aos municípios de Pernambuco,
a partir dos arquivos mensais do Tesouro Transparente (STN).

Fonte: conjunto "Transferências Constitucionais para Municípios"
    https://www.tesourotransparente.gov.br/ckan/dataset/af4e7c47-2132-4d9a-bd7c-34e28a210b03
    Um CSV por mês com todos os municípios do país (latin1, separador ";"),
    colunas: Município;UF;ANO;Mês;1º Decêndio;2º Decêndio;3º Decêndio;
             Item transferência;Transferência

Cuidados que este ETL toma (e que explicam números diferentes da v1.x):
1. O nome do arquivo NÃO indica com segurança o mês dos dados: até 2022 o
   arquivo AAAAMM traz o próprio mês; depois passou a trazer o mês anterior,
   e há nomes repetidos (dois "202412", dois "202512"). Por isso o mês é
   lido do conteúdo (colunas ANO e Mês) e, se dois arquivos trouxerem o
   mesmo mês, fica o publicado por último.
2. As linhas "X | FUNDEB" são o que o município RECEBE do FUNDEB, separado
   pela origem do recurso (FPM, FPE, ICMS, IPVA...). Não são cota-parte
   desses impostos. A linha "DEDU | FUNDEB" é a retenção de 20% do FPM
   bruto para formar o FUNDEB.
3. A linha DEDU é 25% de (FPM + ITR creditados), ou seja, a retenção de
   20% do FUNDEB sobre o bruto dos dois. O ETL separa a parte do ITR.
   FPM bruto = FPM creditado + retenção FUNDEB do FPM + FPM 1%
   (parcelas extras de julho, setembro e dezembro, em linha própria a
   partir de 2025).

   Até 2024 a parcela de 1% vinha somada à linha do FPM nos meses de
   julho, setembro e dezembro; o ETL a separa (FPM ordinário líquido =
   4 x DEDU, pois a parcela de 1% não sofre retenção do FUNDEB).
4. Alguns arquivos mensais estão incompletos (faltam decêndios), um veio
   em centavos (set/2024) e out/2022 não foi publicado. O ETL lê os
   arquivos em centavos e confere FPM, FUNDEB, ITR, CIDE e LC 176 com a
   série consolidada do Tesouro ("Transferências Obrigatórias da União -
   por Município", um CSV por transferência com o total mensal de cada
   município). Onde o total do mês diverge, ou o mês falta, vale a série
   consolidada: entra uma linha com o total do mês, sem decêndios
   (coluna `origem` = "consolidado"), e as retenções do FUNDEB sobre FPM e
   ITR são calculadas como 25% do valor creditado. Royalties não têm série
   consolidada; os de out/2022 ficam faltando.

Categorias geradas (coluna `categoria`):
    fpm (creditado), fpm_deducao (retenção FUNDEB), fpm_1pct, itr,
    itr_deducao,
    fundeb (recebido, inclui complementação da União e ajustes),
    royalties (item: ANP, FEP, CFEM, CFH), cide, lei_kandir
    (LC 87/96 e LC 176/2020), apoio (AFM/AFE e LC 173/2020), iof_ouro,
    outras

Cache: data/cache/transferencias/ guarda só as linhas de PE de cada
arquivo já baixado; nas próximas execuções baixa apenas arquivos novos.

Output:
    data/processed/transferencias_pe.parquet
    Colunas: data, ano, mes, cod_ibge_6, municipio, categoria, item,
             dec1, dec2, dec3, valor, origem ("mensal" ou "consolidado")

Como rodar: python -m etl.transferencias_etl
"""

import io
import json
import re
import sys
import unicodedata
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_PROCESSED, TRANSFERENCIAS_PE  # noqa: E402
from etl._aliases import normaliza_municipio  # noqa: E402
from etl._fontes import (http, baixar_json, modo_offline, pasta_cache,  # noqa: E402
                         salvar, FonteIndisponivel)

DATASET_ID = 'af4e7c47-2132-4d9a-bd7c-34e28a210b03'
CKAN = 'https://www.tesourotransparente.gov.br/ckan/api/3/action/package_show'
ANO_INICIAL = 2019
UF = 'PE'

COLUNAS = ['municipio_stn', 'uf', 'ano', 'mes', 'dec1', 'dec2', 'dec3',
           'item', 'transferencia']

_RE_MENSAL = re.compile(r'Mensal_Municipios_(\d{6})', re.I)

# Série consolidada: recurso do CKAN (nome sem acento, minúsculo) -> série
DATASET_CONSOLIDADO = 'transferencias-obrigatorias-da-uniao-por-municipio'
SERIES_CONSOLIDADAS = {
    'fpm por municipio': 'fpm',           # FPM creditado, com as parcelas de 1%
    'fundeb por municipio': 'fundeb',
    'itr por municipio': 'itr',           # ITR creditado
    'cide-combustiveis por municipio': 'cide',
    'lc 176/2020 por municipio': 'lei_kandir',
}
# Categorias do detalhe que somam o mesmo que cada série consolidada
CATEGORIAS_DA_SERIE = {
    'fpm': ['fpm', 'fpm_1pct'], 'fundeb': ['fundeb'], 'itr': ['itr'],
    'cide': ['cide'], 'lei_kandir': ['lei_kandir'],
}
TOLERANCIA = 1.00  # R$ por município, mês e série


# ============================================================================
# Download (com cache incremental)
# ============================================================================

def _manifesto_path() -> Path:
    return pasta_cache('transferencias') / 'manifesto.json'


def _ler_manifesto() -> dict:
    p = _manifesto_path()
    if p.exists():
        return json.loads(p.read_text(encoding='utf-8'))
    return {}


def _gravar_manifesto(m: dict):
    _manifesto_path().write_text(json.dumps(m, ensure_ascii=False, indent=1),
                                 encoding='utf-8')


def _recursos_mensais(pacote: dict) -> list:
    """Recursos CSV mensais a partir de dez/2018 (o conteúdo decide o mês)."""
    saida = []
    for r in pacote['result']['resources']:
        m = _RE_MENSAL.search(r.get('name', '') or '')
        if not m or m.group(1) < f"{ANO_INICIAL - 1}12":
            continue
        saida.append({
            'id': r['id'], 'nome': r['name'], 'url': r['url'],
            'criado': r.get('created') or '',
            'modificado': r.get('last_modified') or r.get('created') or '',
        })
    return saida


def _baixar_recurso(rec: dict, destino: Path) -> dict:
    """Baixa o CSV nacional e guarda só o cabeçalho + linhas de PE."""
    r = http(rec['url'], timeout=300)
    texto = r.content.decode('latin1')
    linhas = texto.splitlines()
    cab = linhas[0]
    pe = [ln for ln in linhas[1:] if f';{UF};' in ln]
    destino.write_text('\n'.join([cab] + pe) + '\n', encoding='utf-8')
    meses = sorted({f"{ln.split(';')[2]}-{ln.split(';')[3].zfill(2)}"
                    for ln in pe if ln.count(';') >= 8})
    return {'nome': rec['nome'], 'criado': rec['criado'],
            'modificado': rec['modificado'], 'arquivo': destino.name,
            'meses': meses, 'linhas_pe': len(pe)}


def atualizar_cache():
    """
    Baixa os arquivos mensais ainda não guardados no cache. Devolve o
    manifesto e a lista dos arquivos que não baixaram.
    """
    manifesto = _ler_manifesto()
    if modo_offline():
        print("[TRF] modo offline: usando o cache")
        return manifesto, []

    pacote = baixar_json(f"{CKAN}?id={DATASET_ID}",
                         pasta_cache('transferencias') / 'pacote.json',
                         rotulo='CKAN Tesouro')
    recursos = _recursos_mensais(pacote)
    pasta = pasta_cache('transferencias')
    novos, falharam = 0, []
    for rec in recursos:
        atual = manifesto.get(rec['id'])
        destino = pasta / f"pe_{rec['id']}.csv"
        if (atual and destino.exists()
                and atual.get('modificado') == rec['modificado']):
            continue
        try:
            manifesto[rec['id']] = _baixar_recurso(rec, destino)
            novos += 1
            print(f"      ↓ {rec['nome']} → {', '.join(manifesto[rec['id']]['meses'])}")
            _gravar_manifesto(manifesto)  # salva a cada arquivo (retomável)
        except FonteIndisponivel as e:
            falharam.append(rec['nome'])
            print(f"      ! {rec['nome']}: {e}")
    print(f"[TRF] {novos} arquivo(s) novo(s); {len(manifesto)} no cache")
    return manifesto, falharam


# ============================================================================
# Processamento
# ============================================================================

def _ler_cache(manifesto: dict) -> pd.DataFrame:
    """
    Junta os arquivos do cache. Para cada mês, usa só o arquivo publicado
    por último (resolve os nomes repetidos/deslocados do Tesouro).
    """
    pasta = pasta_cache('transferencias')
    escolha = {}  # 'AAAA-MM' -> (criado, id)
    for rid, info in manifesto.items():
        for mes in info.get('meses', []):
            if int(mes[:4]) < ANO_INICIAL:
                continue
            chave = (info.get('criado', ''), rid)
            if mes not in escolha or chave > escolha[mes]:
                escolha[mes] = chave

    partes = []
    for mes, (_, rid) in sorted(escolha.items()):
        arq = pasta / manifesto[rid]['arquivo']
        if not arq.exists():
            continue
        df = pd.read_csv(arq, sep=';', dtype=str, header=0,
                         usecols=range(9), names=COLUNAS, encoding='utf-8')
        df['_mes'] = df['ano'].str.strip() + '-' + df['mes'].str.strip().str.zfill(2)
        df = df[df['_mes'] == mes].copy()
        df['_escala'] = _escala(df)
        if df['_escala'].iloc[0] != 1.0:
            print(f"      ! {manifesto[rid].get('nome', arq.name)}: valores em centavos "
                  f"({mes}); convertidos para reais")
        partes.append(df)
    if not partes:
        return pd.DataFrame(columns=COLUNAS)
    return pd.concat(partes, ignore_index=True).drop(columns='_mes')


def _escala(df: pd.DataFrame) -> float:
    """
    O arquivo de set/2024 veio com os valores em centavos, sem separador
    decimal (ex.: 4304034789 em vez de 43040347.89). Se nenhum valor do mês
    tem ponto ou vírgula, o arquivo está em centavos.
    """
    if len(df) < 50:
        return 1.0
    valores = pd.concat([df[c] for c in ('dec1', 'dec2', 'dec3')]).fillna('').astype(str)
    return 1.0 if valores.str.contains(r'[.,]', regex=True).any() else 0.01


def classificar(item: str, transferencia: str) -> str:
    """Categoria analítica de cada linha do Tesouro (ver docstring do módulo)."""
    it = (item or '').strip().upper()
    tr = (transferencia or '').strip().upper()
    if it == 'DEDU':
        return 'fpm_deducao'
    if it == 'FPM 1%' or tr == 'FPM 1%':
        return 'fpm_1pct'
    if tr == 'FPM' and it == 'FPM':
        return 'fpm'
    if tr in ('FUNDEB', 'AJUSTE FUNDEB'):
        return 'fundeb'
    if tr == 'ITR':
        return 'itr'
    if tr == 'ROYALTIES':
        return 'royalties'
    if tr.startswith('CIDE'):
        return 'cide'
    if 'LC 176' in tr or 'ADO25' in tr.replace(' ', '') or 'KANDIR' in tr or 'LC 87' in tr:
        return 'lei_kandir'
    if tr.startswith('AFM') or 'AFE' in tr or 'LC 173' in tr or 'PFEC' in tr or it == 'AUX':
        return 'apoio'
    if 'IOF' in tr:
        return 'iof_ouro'
    return 'outras'


# Nomes antigos de itens de royalties
_ITEM_ROYALTIES = {'CFM': 'CFEM'}


def _ajustar_fpm(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dois ajustes no FPM, ambos com base na linha DEDU (retenção do FUNDEB):

    a) DEDU = 25% de (FPM creditado + ITR creditado): a retenção de 20% do
       FUNDEB incide sobre o bruto do FPM e do ITR. A parte do ITR
       (ITR/4) vira a categoria `itr_deducao`; o resto é `fpm_deducao`.
    b) Até 2024 a parcela extra de 1% do FPM (julho, setembro e dezembro)
       vinha somada à linha do FPM. Como ela não sofre retenção do FUNDEB,
       o FPM ordinário líquido é 4 x DEDU - ITR em cada decêndio; o que
       passar disso (acima de R$ 1 mil) é a parcela de 1%. Só vale para
       meses sem linha própria de "FPM 1%".

    Os ajustes entram como linhas extras (positivas e negativas) que se
    compensam na agregação final, sem alterar o total do município.
    """
    chave = ['ano', 'mes', 'municipio_stn']
    decs = ['dec1', 'dec2', 'dec3']

    def soma(cat):
        return df[df['categoria'] == cat].groupby(chave)[decs].sum()

    base = (soma('fpm')
            .join(soma('fpm_deducao').add_suffix('_d'), how='inner')
            .join(soma('itr').add_suffix('_i'), how='left')
            .fillna(0.0))
    tem_1pct = set(df.loc[df['categoria'] == 'fpm_1pct', chave]
                     .itertuples(index=False, name=None))
    modelo = df.iloc[0].copy()
    novas = []

    def linha(k, categoria, valores, sinal):
        n = modelo.copy()
        n['ano'], n['mes'], n['municipio_stn'] = k
        n['categoria'] = n['item'] = categoria
        for d in decs:
            n[d] = sinal * valores[d]
        novas.append(n)

    for k, r in base.iterrows():
        itr_ded = {d: r[f'{d}_i'] / 4 for d in decs}
        if any(abs(v) >= 0.01 for v in itr_ded.values()):
            linha(k, 'itr_deducao', itr_ded, +1)
            linha(k, 'fpm_deducao', itr_ded, -1)
        if k not in tem_1pct:
            extra = {d: r[d] - (4 * r[f'{d}_d'] - r[f'{d}_i']) for d in decs}
            extra = {d: (v if v > 1000 else 0.0) for d, v in extra.items()}
            if sum(extra.values()) > 0:
                linha(k, 'fpm_1pct', extra, +1)
                linha(k, 'fpm', extra, -1)
    if novas:
        df = pd.concat([df, pd.DataFrame(novas)], ignore_index=True)
    return df


def _num(s: pd.Series) -> pd.Series:
    """Valores vêm com ponto decimal (ex.: 2348521.79); trata vírgula por via das dúvidas."""
    s = s.fillna('0').astype(str).str.strip()
    tem_virgula = s.str.contains(',', regex=False)
    s = s.where(~tem_virgula, s.str.replace('.', '', regex=False)
                               .str.replace(',', '.', regex=False))
    return pd.to_numeric(s, errors='coerce').fillna(0.0)


def processar(bruto: pd.DataFrame) -> pd.DataFrame:
    df = bruto.copy()
    df = df[df['uf'].str.strip() == UF]
    df['ano'] = df['ano'].astype(int)
    df['mes'] = df['mes'].astype(int)
    escala = df['_escala'] if '_escala' in df.columns else 1.0
    for c in ('dec1', 'dec2', 'dec3'):
        df[c] = _num(df[c]) * escala
    df['categoria'] = [classificar(i, t) for i, t in
                       zip(df['item'], df['transferencia'])]
    df['item'] = df['item'].str.strip().replace(_ITEM_ROYALTIES)
    df = _ajustar_fpm(df)
    # Detalhe por item só onde ele importa (royalties: petróleo, mineração...)
    df.loc[df['categoria'] != 'royalties', 'item'] = df['categoria']

    df = _codigos(df)

    agg = (df.groupby(['ano', 'mes', 'cod_ibge_6', 'municipio', 'categoria',
                       'item'], as_index=False)[['dec1', 'dec2', 'dec3']]
             .sum())
    agg['valor'] = agg['dec1'] + agg['dec2'] + agg['dec3']
    agg['data'] = pd.to_datetime(dict(year=agg['ano'], month=agg['mes'], day=1))
    agg['origem'] = 'mensal'
    agg = agg[COLUNAS_SAIDA]
    return agg.sort_values(['data', 'cod_ibge_6', 'categoria']).reset_index(drop=True)


COLUNAS_SAIDA = ['data', 'ano', 'mes', 'cod_ibge_6', 'municipio', 'categoria',
                 'item', 'dec1', 'dec2', 'dec3', 'valor', 'origem']


def _codigos(df: pd.DataFrame) -> pd.DataFrame:
    """Código IBGE e nome oficial pelo nome do Tesouro (mesma normalização das outras bases)."""
    rd = pd.read_parquet(DATA_PROCESSED / 'municipios_rd.parquet')
    mapa = {normaliza_municipio(n): (c, n) for c, n in
            zip(rd['cod_ibge_6'], rd['municipio'])}
    chaves = df['municipio_stn'].map(normaliza_municipio)
    df = df.copy()
    df['cod_ibge_6'] = chaves.map(lambda k: mapa.get(k, (None, None))[0])
    df['municipio'] = chaves.map(lambda k: mapa.get(k, (None, None))[1])
    sem = sorted(df.loc[df['cod_ibge_6'].isna(), 'municipio_stn'].unique())
    if sem:
        print(f"[TRF] AVISO: {len(sem)} nome(s) sem código IBGE: {sem[:10]}")
    df = df.dropna(subset=['cod_ibge_6'])
    df['cod_ibge_6'] = df['cod_ibge_6'].astype(int)
    return df


# ============================================================================
# Série consolidada: confere e completa os arquivos mensais
# ============================================================================

def _sem_acento(s: str) -> str:
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c)).lower().strip()


def atualizar_consolidado() -> list:
    """Baixa os CSVs da série consolidada que mudaram. Devolve os que falharam."""
    if modo_offline():
        return []
    pasta = pasta_cache('transferencias', 'consolidado')
    man_path = pasta / 'manifesto.json'
    man = json.loads(man_path.read_text(encoding='utf-8')) if man_path.exists() else {}
    falharam = []
    try:
        pacote = baixar_json(f"{CKAN}?id={DATASET_CONSOLIDADO}", pasta / 'pacote.json',
                             rotulo='CKAN Tesouro (série consolidada)')
    except FonteIndisponivel as e:
        print(f"      ! série consolidada: {e}")
        return ['pacote da série consolidada']
    for r in pacote['result']['resources']:
        serie = SERIES_CONSOLIDADAS.get(_sem_acento(r.get('name', '')))
        if not serie:
            continue
        destino = pasta / f"{serie}.csv"
        modificado = r.get('last_modified') or r.get('created') or ''
        if destino.exists() and man.get(serie) == modificado:
            continue
        try:
            texto = http(r['url'], timeout=300).content.decode('latin1')
            linhas = texto.splitlines()
            pe = [ln for ln in linhas[1:] if ln.split(';')[2:3] == [UF]]
            if not pe:
                raise FonteIndisponivel("arquivo sem linhas de PE")
            destino.write_text('\n'.join([linhas[0]] + pe) + '\n', encoding='utf-8')
            man[serie] = modificado
            man_path.write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding='utf-8')
            print(f"      ↓ {r['name']}: {len(pe)} linhas de PE")
        except FonteIndisponivel as e:
            falharam.append(r['name'])
            print(f"      ! {r['name']}: {e}")
    return falharam


def _valor_br(s: str) -> float:
    """' 4.427.150,47 ' -> 4427150.47; '-' ou vazio -> 0; '361301' -> 361301.0."""
    s = (s or '').strip()
    if s in ('', '-'):
        return 0.0
    s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return float('nan')


def ler_consolidado() -> pd.DataFrame:
    """Série consolidada no formato longo: cod_ibge_6, municipio, data, serie, valor."""
    pasta = pasta_cache('transferencias', 'consolidado')
    regs = []
    for serie in sorted(set(SERIES_CONSOLIDADAS.values())):
        arq = pasta / f"{serie}.csv"
        if not arq.exists():
            continue
        linhas = arq.read_text(encoding='utf-8').splitlines()
        cab = [_sem_acento(c) for c in linhas[0].split(';')]
        i_mun, i_uf, i_mes = cab.index('municipio'), cab.index('uf'), cab.index('mes')
        anos = [(i, int(c)) for i, c in enumerate(cab)
                if re.fullmatch(r'\d{4}', c) and int(c) >= ANO_INICIAL]
        for ln in linhas[1:]:
            c = ln.split(';')
            if len(c) <= i_mes or c[i_uf].strip() != UF or not c[i_mes].strip().isdigit():
                continue
            mes = int(c[i_mes])
            for i, ano in anos:
                if i < len(c):
                    regs.append((c[i_mun].strip(), ano, mes, serie, _valor_br(c[i])))
    df = pd.DataFrame(regs, columns=['municipio_stn', 'ano', 'mes', 'serie', 'valor'])
    if df.empty:
        return pd.DataFrame(columns=['cod_ibge_6', 'municipio', 'data', 'serie', 'valor'])
    df = _codigos(df)
    df['data'] = pd.to_datetime(dict(year=df['ano'], month=df['mes'], day=1))
    return df[['cod_ibge_6', 'municipio', 'data', 'serie', 'valor']]


def conciliar(det: pd.DataFrame, cons: pd.DataFrame) -> tuple:
    """
    Confere o total mensal de cada município com a série consolidada e,
    onde diverge (ou o mês falta), troca pelo valor consolidado.
    Devolve (base corrigida, resumo das trocas).
    """
    if cons.empty:
        return det, pd.DataFrame(columns=['serie', 'data', 'cod_ibge_6', 'antes', 'depois'])
    ini, fim = det['data'].min(), det['data'].max()
    nomes = dict(zip(cons['cod_ibge_6'], cons['municipio']))
    um_pct = det[det['categoria'] == 'fpm_1pct'].groupby(['cod_ibge_6', 'data'])['valor'].sum()
    trocas, remover, novas = [], [], []

    def linha(cod, data, categoria, valor):
        novas.append({'data': data, 'ano': data.year, 'mes': data.month,
                      'cod_ibge_6': cod, 'municipio': nomes[cod],
                      'categoria': categoria, 'item': categoria,
                      'dec1': float('nan'), 'dec2': float('nan'), 'dec3': float('nan'),
                      'valor': round(valor, 2), 'origem': 'consolidado'})

    for serie, cats in CATEGORIAS_DA_SERIE.items():
        c = cons[cons['serie'] == serie]
        estado = c.groupby('data')['valor'].sum()
        com_valor = estado[estado.abs() > 0].index
        if len(com_valor) == 0:
            continue
        # só os meses que a série consolidada cobre e que o detalhe também cobre
        lo, hi = max(com_valor.min(), ini), min(com_valor.max(), fim)
        c = c[(c['data'] >= lo) & (c['data'] <= hi)]
        oficial = c.groupby(['cod_ibge_6', 'data'])['valor'].sum()
        d = det[det['categoria'].isin(cats) & (det['data'] >= lo) & (det['data'] <= hi)
                & det['cod_ibge_6'].isin(oficial.index.get_level_values(0))]
        nosso = d.groupby(['cod_ibge_6', 'data'])['valor'].sum()
        idx = oficial.index.union(nosso.index)
        dif = oficial.reindex(idx, fill_value=0.0) - nosso.reindex(idx, fill_value=0.0)
        for (cod, data), _ in dif[dif.abs() > TOLERANCIA].items():
            v_of = float(oficial.get((cod, data), 0.0))
            v_nosso = float(nosso.get((cod, data), 0.0))
            trocas.append((serie, data, cod, v_nosso, v_of))
            if serie == 'fpm':
                um = float(um_pct.get((cod, data), 0.0))
                if um > v_of:  # parcela de 1% inconsistente: fica tudo como FPM
                    remover.append((cod, data, 'fpm_1pct'))
                    um = 0.0
                for cat in ('fpm', 'fpm_deducao'):
                    remover.append((cod, data, cat))
                ordinario = v_of - um
                if abs(ordinario) > 0:
                    linha(cod, data, 'fpm', ordinario)
                    linha(cod, data, 'fpm_deducao', ordinario / 4)
            elif serie == 'itr':
                for cat in ('itr', 'itr_deducao'):
                    remover.append((cod, data, cat))
                if abs(v_of) > 0:
                    linha(cod, data, 'itr', v_of)
                    linha(cod, data, 'itr_deducao', v_of / 4)
            else:
                remover.append((cod, data, cats[0]))
                if abs(v_of) > 0:
                    linha(cod, data, cats[0], v_of)

    if remover:
        chave = pd.MultiIndex.from_frame(det[['cod_ibge_6', 'data', 'categoria']])
        tirar = pd.MultiIndex.from_tuples(remover, names=['cod_ibge_6', 'data', 'categoria'])
        det = det[~chave.isin(tirar)]
    if novas:
        det = pd.concat([det, pd.DataFrame(novas)[COLUNAS_SAIDA]], ignore_index=True)
    det = det.sort_values(['data', 'cod_ibge_6', 'categoria']).reset_index(drop=True)
    resumo = pd.DataFrame(trocas, columns=['serie', 'data', 'cod_ibge_6', 'antes', 'depois'])
    return det, resumo


def main():
    print("[TRF] Transferências constitucionais (Tesouro Transparente)...")
    manifesto, falharam = atualizar_cache()
    bruto = _ler_cache(manifesto)
    if bruto.empty:
        raise FonteIndisponivel("nenhum arquivo de transferências no cache")
    df = processar(bruto)

    print("[TRF] Conferindo com a série consolidada do Tesouro...")
    falharam += atualizar_consolidado()
    cons = ler_consolidado()
    if cons.empty:
        print("[TRF] AVISO: sem a série consolidada; os meses incompletos ficam como vieram")
    df, trocas = conciliar(df, cons)
    if len(trocas):
        por_serie = trocas.groupby('serie')['data'].nunique().to_dict()
        print(f"[TRF] {len(trocas)} total(is) mensais trocados pela série consolidada "
              f"(meses por série: {por_serie})")
        dif_estado = (trocas.assign(dif=trocas['depois'] - trocas['antes'])
                      .groupby(['serie', 'data'])['dif'].sum())
        grandes = dif_estado[dif_estado.abs() > 1e6]
        for (serie, data), v in grandes.items():
            valor = f"{v / 1e6:+,.1f}".replace(',', '_').replace('.', ',').replace('_', '.')
            print(f"      {serie:10s} {data:%Y-%m}: {valor} mi")

    meses = sorted(df['data'].dt.strftime('%Y-%m').unique().tolist())
    esperados = pd.period_range(df['data'].min(), df['data'].max(), freq='M')
    faltam = [str(p) for p in esperados if str(p) not in set(meses)]
    print(f"[TRF] {df['cod_ibge_6'].nunique()} municípios · "
          f"{meses[0]} a {meses[-1]} · {len(meses)} meses")
    if faltam:
        print(f"[TRF] AVISO: meses sem arquivo no Tesouro: {', '.join(faltam)}")

    ult = df[df['ano'] == df['ano'].max() - 1]
    fpm_bruto = ult[ult['categoria'].isin(['fpm', 'fpm_deducao', 'fpm_1pct'])]['valor'].sum()
    print(f"[TRF] FPM bruto PE {df['ano'].max() - 1}: "
          f"R$ {fpm_bruto / 1e9:.2f} bi".replace('.', ','))
    salvar(df, TRANSFERENCIAS_PE, 'TRF')
    if falharam:
        raise FonteIndisponivel(
            f"{len(falharam)} arquivo(s) do Tesouro não baixaram "
            f"({', '.join(falharam[:4])}{'...' if len(falharam) > 4 else ''}). "
            "Os demais meses foram gravados; rode de novo esta etapa para completar")


if __name__ == '__main__':
    main()
