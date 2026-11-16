"""
etl/atividade_etl.py
====================
Indicadores de atividade econômica de Pernambuco (eixo Atividade
Econômica), baixados das APIs do Banco Central e do IBGE.

Séries mensais (data/processed/atividade_mensal.parquet)
    ibcr            IBC-R Pernambuco, IBC-R Nordeste e IBC-Br (BCB/SGS
                    25417, 25418, 25388, 25389, 24363, 24364)
    pim             Produção física industrial, PE e Brasil (SIDRA 8888)
    pmc_varejo      Vendas no varejo, PE e Brasil (SIDRA 8880)
    pmc_ampliado    Varejo ampliado (veículos, material de construção,
                    atacado de alimentos), PE e Brasil (SIDRA 8881)
    pmc_atividades  Varejo por atividade, PE e Brasil (SIDRA 8882)
    pms             Volume e receita de serviços, PE e Brasil (SIDRA 5906)
    pms_atividades  Serviços por atividade, PE (SIDRA 8693)
    pms_turismo     Atividades turísticas, PE e Brasil (SIDRA 8694)
    ipca            IPCA Brasil (SIDRA 1737, base do deflator do painel) e
                    RM do Recife por grupo (SIDRA 7060)
    Colunas: data, fonte, regiao, categoria, tipo, medida, valor
    medida: indice, indice_sa, var_mensal_sa, var_interanual, var_acum_ano,
            var_acum_12m, var_mensal

Agropecuária
    agro_lspa.parquet  Estimativas mensais de safra do LSPA (SIDRA 6588)
    agro_pam.parquet   Produção agrícola municipal (SIDRA 5457)
    agro_ppm.parquet   Pecuária municipal: rebanhos (3939) e produção de
                       origem animal (74)

PIB trimestral (data/processed/pib_trimestral.parquet)
    Lido de data/raw/pib_trimestral_pe.csv, mantido à mão a partir do
    painel da SEPLAG-PE/Agência CONDEPE-FIDEM (não há API).

Como rodar: python -m etl.atividade_etl
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (AGRO_LSPA, AGRO_PAM, AGRO_PPM, ATIVIDADE_MENSAL,  # noqa: E402
                    PIB_TRIMESTRAL, PIB_TRIMESTRAL_RAW)
from etl._fontes import periodo_mensal, salvar, sgs, sidra  # noqa: E402

ANO_INICIAL = 2012
PERIODO = f"{ANO_INICIAL}01-{date.today().year}12"
REGIAO = {'26': 'Pernambuco', '1': 'Brasil', '2601': 'RM Recife'}

MEDIDAS_PIM = {'12606': 'indice', '12607': 'indice_sa', '11601': 'var_mensal_sa',
               '11602': 'var_interanual', '11603': 'var_acum_ano',
               '11604': 'var_acum_12m'}
MEDIDAS_PMC = {'7169': 'indice', '7170': 'indice_sa', '11708': 'var_mensal_sa',
               '11709': 'var_interanual', '11710': 'var_acum_ano',
               '11711': 'var_acum_12m'}
MEDIDAS_PMS = {'7167': 'indice', '7168': 'indice_sa', '11623': 'var_mensal_sa',
               '11624': 'var_interanual', '11625': 'var_acum_ano',
               '11626': 'var_acum_12m'}
MEDIDAS_IPCA = {'63': 'var_mensal', '69': 'var_acum_ano', '2265': 'var_acum_12m',
                '2266': 'indice'}
TIPO_INDICE = {'56733': 'receita', '56734': 'volume', '56725': 'receita',
               '56726': 'volume', '56727': 'receita', '56728': 'volume'}

# Atividades da PIM-PF com dado para Pernambuco (as demais aparecem só no
# Brasil). Indústria geral e transformação primeiro.
PIM_CATEGORIAS = ['129314', '129315', '129316', '129317', '129318', '129324',
                  '129326', '56689', '129331', '129332', '129333', '129334',
                  '129336', '129338', '129339']

IPCA_GRUPOS = ['7169', '7170', '7445', '7486', '7558', '7625', '7660', '7712',
               '7766', '7786']


def _limpa_categoria(nome: str) -> str:
    """'3.10 Fabricação de produtos alimentícios' -> 'Produtos alimentícios'."""
    import re
    nome = re.sub(r'^[\d.]+\s+', '', str(nome)).strip()
    nome = nome.replace('Fabricação de ', '')
    nome = re.sub(r'^\d+\.', '', nome).strip()  # '1.Alimentação e bebidas'
    return nome[:1].upper() + nome[1:]


def _formatar(df: pd.DataFrame, fonte: str, medidas: dict,
              col_regiao='D1C', col_var='D2C', col_per='D3C',
              col_cat=None, col_tipo=None, categoria_fixa='Total') -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        'data': df[col_per].map(periodo_mensal),
        'fonte': fonte,
        'regiao': df[col_regiao].astype(str).map(REGIAO).fillna(df[col_regiao]),
        'categoria': (df[col_cat.replace('C', 'N')].map(_limpa_categoria)
                      if col_cat else categoria_fixa),
        'tipo': df[col_tipo].astype(str).map(TIPO_INDICE) if col_tipo else None,
        'medida': df[col_var].astype(str).map(medidas),
        'valor': df['valor'],
    })
    return out.dropna(subset=['valor', 'medida'])


# ============================================================================
# Séries mensais
# ============================================================================

def _ibcr() -> pd.DataFrame:
    series = {25417: ('Pernambuco', 'indice'), 25418: ('Pernambuco', 'indice_sa'),
              25388: ('Nordeste', 'indice'), 25389: ('Nordeste', 'indice_sa'),
              24363: ('Brasil', 'indice'), 24364: ('Brasil', 'indice_sa')}
    partes = []
    for cod, (reg, med) in series.items():
        s = sgs(cod)
        s['fonte'], s['regiao'], s['categoria'], s['tipo'], s['medida'] = \
            'ibcr', reg, 'Total', None, med
        partes.append(s)
    df = pd.concat(partes, ignore_index=True)
    # variações calculadas a partir dos índices
    extra = []
    for reg, g in df.groupby('regiao'):
        bruto = g[g['medida'] == 'indice'].set_index('data')['valor'].sort_index()
        sa = g[g['medida'] == 'indice_sa'].set_index('data')['valor'].sort_index()
        variacoes = {
            'var_mensal_sa': 100 * sa.pct_change(),
            'var_interanual': 100 * bruto.pct_change(12),
            'var_acum_12m': 100 * (bruto.rolling(12).sum()
                                   / bruto.rolling(12).sum().shift(12) - 1),
        }
        ytd = bruto.groupby(bruto.index.year).cumsum()
        variacoes['var_acum_ano'] = 100 * (ytd / ytd.shift(12) - 1)
        for med, s in variacoes.items():
            t = s.dropna().rename('valor').reset_index()
            t['fonte'], t['regiao'], t['categoria'], t['tipo'], t['medida'] = \
                'ibcr', reg, 'Total', None, med
            extra.append(t)
    return pd.concat([df] + extra, ignore_index=True)


def _pim() -> pd.DataFrame:
    cats = ','.join(PIM_CATEGORIAS)
    v = ','.join(MEDIDAS_PIM)
    partes = []
    for nivel, nome in (('n3/26', 'pim_pe'), ('n1/1', 'pim_br')):
        df = sidra(f"/t/8888/{nivel}/v/{v}/p/{PERIODO}/c544/{cats}", nome)
        partes.append(_formatar(df, 'pim', MEDIDAS_PIM, col_cat='D4C'))
    out = pd.concat(partes, ignore_index=True)
    out['categoria'] = out['categoria'].replace({'Indústria geral': 'Indústria geral'})
    return out


def _pmc() -> pd.DataFrame:
    v = ','.join(MEDIDAS_PMC)
    partes = []
    for tab, fonte in (('8880', 'pmc_varejo'), ('8881', 'pmc_ampliado')):
        df = sidra(f"/t/{tab}/n3/26/n1/1/v/{v}/p/{PERIODO}/c11046/all",
                   f"{fonte}")
        partes.append(_formatar(df, fonte, MEDIDAS_PMC, col_tipo='D4C'))
    df = sidra(f"/t/8882/n3/26/n1/1/v/7169,11709,11711/p/{PERIODO}"
               f"/c11046/56734/c85/all", 'pmc_atividades')
    partes.append(_formatar(df, 'pmc_atividades', MEDIDAS_PMC,
                            col_tipo='D4C', col_cat='D5C'))
    return pd.concat(partes, ignore_index=True)


def _pms() -> pd.DataFrame:
    v = ','.join(MEDIDAS_PMS)
    partes = []
    df = sidra(f"/t/5906/n3/26/n1/1/v/{v}/p/{PERIODO}/c11046/all", 'pms')
    partes.append(_formatar(df, 'pms', MEDIDAS_PMS, col_tipo='D4C'))
    df = sidra(f"/t/8693/n3/26/v/7167,11624,11626/p/{PERIODO}/c11046/56726"
               f"/c12355/all", 'pms_atividades')
    partes.append(_formatar(df, 'pms_atividades', MEDIDAS_PMS,
                            col_tipo='D4C', col_cat='D5C'))
    df = sidra(f"/t/8694/n3/26/n1/1/v/{v}/p/{PERIODO}/c11046/all", 'pms_turismo')
    partes.append(_formatar(df, 'pms_turismo', MEDIDAS_PMS, col_tipo='D4C'))
    out = pd.concat(partes, ignore_index=True)
    out['categoria'] = out['categoria'].replace({'Total': 'Total'})
    return out


def _ipca() -> pd.DataFrame:
    partes = []
    df = sidra(f"/t/1737/n1/1/v/63,69,2265,2266/p/{PERIODO}", 'ipca_brasil')
    t = _formatar(df, 'ipca', MEDIDAS_IPCA, categoria_fixa='Índice geral')
    partes.append(t)
    grupos = ','.join(IPCA_GRUPOS)
    df = sidra(f"/t/7060/n7/2601/n1/1/v/63,69,2265/p/all/c315/{grupos}",
               'ipca_recife_grupos')
    t = _formatar(df, 'ipca', MEDIDAS_IPCA, col_cat='D4C')
    # o índice geral do Brasil já vem da 1737 (série mais longa)
    t = t[~((t['regiao'] == 'Brasil') & (t['categoria'] == 'Índice geral'))]
    partes.append(t)
    return pd.concat(partes, ignore_index=True)


# ============================================================================
# Agropecuária
# ============================================================================

def _lspa() -> pd.DataFrame:
    df = sidra("/t/6588/n3/26/v/35,109,216,36/p/last%2036/c48/all", 'lspa_pe')
    if df.empty:
        return df
    var = {'35': 'producao_t', '109': 'area_plantada_ha', '216': 'area_colhida_ha',
           '36': 'rendimento_kg_ha'}
    out = pd.DataFrame({
        'data': df['D3C'].map(periodo_mensal),
        'produto': df['D4N'].map(_limpa_produto),
        'cod_produto': df['D4C'].astype(int),
        'variavel': df['D2C'].astype(str).map(var),
        'valor': df['valor'],
    }).dropna(subset=['valor'])
    return out[out['cod_produto'] != 0]


def _limpa_produto(nome: str) -> str:
    import re
    return re.sub(r'^[\d./]+\s+', '', str(nome)).replace('*', '').strip()


def _pam() -> pd.DataFrame:
    var = {'214': 'quantidade_t', '215': 'valor_mil', '216': 'area_colhida_ha'}
    est = sidra("/t/5457/n3/26/v/214,215,216/p/last%2011/c782/all", 'pam_pe')
    est = est.assign(nivel='estado', cod_ibge_6=26)
    # produtos principais: os 16 de maior valor no último ano + feijão e milho
    v = est[(est['D2C'] == '215') & (est['D4C'] != '0')]
    ult = v['D3C'].max()
    top = (v[v['D3C'] == ult].sort_values('valor', ascending=False)['D4C']
           .head(16).tolist())
    for basico in ('40112', '40122'):   # feijão (em grão), milho (em grão)
        if basico not in top:
            top.append(basico)
    partes = [est]
    for cod in ['0'] + top:
        vv = '215' if cod == '0' else '214,215,216'
        m = sidra(f"/t/5457/n6/in%20n3%2026/v/{vv}/p/last%2011/c782/{cod}",
                  f"pam_mun_{cod}")
        if not m.empty:
            m = m.assign(nivel='municipio',
                         cod_ibge_6=m['D1C'].astype(str).str[:6].astype(int))
            partes.append(m)
    df = pd.concat(partes, ignore_index=True)
    out = pd.DataFrame({
        'ano': df['D3C'].astype(int), 'nivel': df['nivel'],
        'cod_ibge_6': df['cod_ibge_6'].astype(int),
        'cod_produto': df['D4C'].astype(int),
        'produto': df['D4N'].map(_limpa_produto).replace({'Total': 'Total (todas as lavouras)'}),
        'variavel': df['D2C'].astype(str).map(var), 'valor': df['valor'],
    })
    out = out.dropna(subset=['variavel'])
    larga = (out.pivot_table(index=['ano', 'nivel', 'cod_ibge_6', 'cod_produto', 'produto'],
                             columns='variavel', values='valor', aggfunc='first')
                .reset_index())
    larga.columns.name = None
    return larga


def _ppm() -> pd.DataFrame:
    partes = []
    reb = {'2670': 'Bovinos', '2681': 'Caprinos', '2677': 'Ovinos',
           '32794': 'Suínos', '32796': 'Galináceos'}
    for nivel, nome in (('n3/26', 'ppm_rebanhos_pe'), ('n6/in%20n3%2026', 'ppm_rebanhos_mun')):
        df = sidra(f"/t/3939/{nivel}/v/105/p/last%2011/c79/{','.join(reb)}", nome)
        if df.empty:
            continue
        partes.append(pd.DataFrame({
            'ano': df['D3C'].astype(int),
            'cod_ibge_6': df['D1C'].astype(str).str[:6].astype(int),
            'tipo': 'rebanho', 'produto': df['D4C'].astype(str).map(reb),
            'unidade': 'cabeças', 'quantidade': df['valor'], 'valor_mil': None,
        }))
    prod = {'2682': ('Leite', 'mil litros'), '2685': ('Ovos de galinha', 'mil dúzias'),
            '2687': ('Mel de abelha', 'kg')}
    for nivel, nome in (('n3/26', 'ppm_producao_pe'), ('n6/in%20n3%2026', 'ppm_producao_mun')):
        df = sidra(f"/t/74/{nivel}/v/106,215/p/last%2011/c80/{','.join(prod)}", nome)
        if df.empty:
            continue
        piv = df.pivot_table(index=['D1C', 'D3C', 'D4C'], columns='D2C',
                             values='valor', aggfunc='first').reset_index()
        partes.append(pd.DataFrame({
            'ano': piv['D3C'].astype(int),
            'cod_ibge_6': piv['D1C'].astype(str).str[:6].astype(int),
            'tipo': 'producao',
            'produto': piv['D4C'].astype(str).map(lambda c: prod[c][0]),
            'unidade': piv['D4C'].astype(str).map(lambda c: prod[c][1]),
            'quantidade': piv.get('106'), 'valor_mil': piv.get('215'),
        }))
    out = pd.concat(partes, ignore_index=True)
    out['nivel'] = out['cod_ibge_6'].map(lambda c: 'estado' if c == 26 else 'municipio')
    return out


# ============================================================================
# PIB trimestral (planilha mantida à mão)
# ============================================================================

def _pib_trimestral() -> pd.DataFrame:
    if not PIB_TRIMESTRAL_RAW.exists():
        print(f"      ! {PIB_TRIMESTRAL_RAW.name} não encontrado; PIB trimestral fica vazio")
        return pd.DataFrame()
    df = pd.read_csv(PIB_TRIMESTRAL_RAW, comment='#', dtype=str)
    df.columns = [c.strip().lower() for c in df.columns]
    for c in ('var_interanual', 'var_acum_ano', 'var_acum_4t', 'var_trimestre_anterior'):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c].str.replace(',', '.', regex=False), errors='coerce')
    df['ano'] = df['ano'].astype(int)
    df['trimestre'] = df['trimestre'].astype(int)
    df['regiao'] = df['regiao'].str.strip()
    df['data'] = pd.to_datetime(dict(year=df['ano'], month=df['trimestre'] * 3, day=1))
    df['rotulo'] = df['trimestre'].astype(str) + 'T' + df['ano'].astype(str)
    return df.sort_values(['regiao', 'data']).reset_index(drop=True)


# ============================================================================
# Main
# ============================================================================

def main():
    print("[ATV] Atividade econômica: BCB (IBC-R) e IBGE (PIM, PMC, PMS, IPCA)...")
    partes, falhas = [], []
    for nome, func in (('IBC-R', _ibcr), ('PIM-PF', _pim), ('PMC', _pmc),
                       ('PMS', _pms), ('IPCA', _ipca)):
        try:
            p = func()
            partes.append(p)
            print(f"      {nome}: {len(p):,} valores".replace(',', '.'))
        except Exception as e:  # uma fonte fora do ar não derruba as demais
            falhas.append(nome)
            print(f"      ! {nome}: {e}")
    if partes:
        mensal = pd.concat(partes, ignore_index=True)
        mensal['tipo'] = mensal['tipo'].astype('object')
        mensal = mensal.sort_values(['fonte', 'regiao', 'categoria', 'medida', 'data'])
        ult = mensal.groupby('fonte')['data'].max().dt.strftime('%m/%Y').to_dict()
        print(f"[ATV] último mês por fonte: {ult}")
        salvar(mensal.reset_index(drop=True), ATIVIDADE_MENSAL, 'ATV')

    print("[ATV] Agropecuária: LSPA, PAM e PPM (IBGE)...")
    for nome, func, destino in (('LSPA', _lspa, AGRO_LSPA), ('PAM', _pam, AGRO_PAM),
                                ('PPM', _ppm, AGRO_PPM)):
        try:
            salvar(func(), destino, 'ATV')
        except Exception as e:
            falhas.append(nome)
            print(f"      ! {nome}: {e}")

    print("[ATV] PIB trimestral (planilha da SEPLAG-PE/CONDEPE-FIDEM)...")
    pib = _pib_trimestral()
    if not pib.empty:
        print(f"      até {pib['rotulo'].iloc[-1]}")
        salvar(pib, PIB_TRIMESTRAL, 'ATV')

    if falhas:
        raise RuntimeError(f"fontes com erro: {', '.join(falhas)}")


if __name__ == '__main__':
    main()
