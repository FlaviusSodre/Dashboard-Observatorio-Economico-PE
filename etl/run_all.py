"""
etl/run_all.py
==============
Orquestrador. Roda todos os ETLs em ordem, gera o catálogo de dados e
atualiza a tabela de períodos do README.

Como rodar (na pasta do projeto, com o ambiente virtual ativo):

    python -m etl.run_all              # baixa o que for automático e processa tudo
    python -m etl.run_all --offline    # sem internet: usa a última cópia baixada
    python -m etl.run_all --so comex,seguranca   # só algumas etapas

Etapas que baixam dados sozinhas (v2.0): população, transferências,
atividade, comex e segurança, além da malha municipal e do complemento
do PIB pelo SIDRA. As demais leem planilhas de data/raw/ mantidas à mão.

Cada etapa roda isolada: se uma fonte estiver fora do ar, as outras
continuam e o resumo final aponta o que falhou.

O catálogo (data/processed/catalogo.json) lista cada base, sua fonte, o
período coberto e quando foi gerada. A partir dele o README ganha a tabela
"Períodos disponíveis" (entre as marcas PERIODOS:INICIO e PERIODOS:FIM).
"""

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (  # noqa: E402
    AGRO_LSPA, AGRO_PAM, AGRO_PPM, ATIVIDADE_MENSAL, CAGED_GENERO,
    CAGED_MUNICIPAL, CAGED_SETOR, CATALOGO, COMEX_MUN_MENSAL, COMEX_UF_MENSAL,
    GEO_MUNICIPIOS, IPS_PE, MUNICIPIOS_RD, MVI_PE, PIB_MUNICIPAL, PIB_TRIMESTRAL,
    PNAD_PE, PNAD_REGIONAL, POBREZA_REGIONAL, POPULACAO_MUNICIPAL, PREFEITOS,
    TRANSFERENCIAS_PE, VEREADORES,
)

ROOT = Path(__file__).parent.parent
README = ROOT / 'README.md'
MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

# (etapa, módulo, baixa da internet?)
ETAPAS = [
    ('geo', 'geo_etl', True),
    ('caged', 'caged_etl', False),
    ('pnad', 'pnad_etl', False),
    ('setor', 'setor_etl', False),
    ('pnad_regional', 'pnad_regional_etl', False),
    ('rd', 'rd_etl', False),
    ('prefeitos', 'prefeitos_etl', False),
    ('pib', 'pib_etl', True),
    ('populacao', 'populacao_etl', True),
    ('transferencias', 'transferencias_etl', True),
    ('atividade', 'atividade_etl', True),
    ('comex', 'comex_etl', True),
    ('ips', 'ips_etl', False),
    ('seguranca', 'seguranca_etl', True),
]

# Bases registradas no catálogo: (arquivo, descrição, fonte, periodicidade, onde aparece)
BASES = [
    (CAGED_MUNICIPAL, 'Emprego formal por município', 'Novo CAGED · MTE', 'mensal',
     'Mercado de trabalho · Emprego formal'),
    (CAGED_GENERO, 'Emprego formal por sexo', 'Novo CAGED · MTE', 'mensal',
     'Mercado de trabalho · Emprego formal'),
    (CAGED_SETOR, 'Emprego formal por grande setor', 'Novo CAGED · MTE', 'mensal',
     'Mercado de trabalho · Emprego formal'),
    (PNAD_PE, 'Mercado de trabalho de Pernambuco', 'PNAD Contínua · IBGE', 'trimestral',
     'Mercado de trabalho · Desemprego'),
    (PNAD_REGIONAL, 'Mercado de trabalho nos estados do NE', 'PNAD Contínua · IBGE',
     'trimestral', 'Mercado de trabalho · Desemprego'),
    (POBREZA_REGIONAL, 'Pobreza e extrema pobreza', 'PNAD Contínua · IBGE', 'trimestral',
     'Mercado de trabalho · Desemprego'),
    (PIB_MUNICIPAL, 'PIB dos municípios', 'SEPLAG-PE / IBGE · Contas Regionais', 'anual',
     'Índices Socioeconômicos · PIB municipal'),
    (MUNICIPIOS_RD, 'Municípios e Regiões de Desenvolvimento', 'SEPLAG-PE', 'estática',
     'todas as abas'),
    (PREFEITOS, 'Prefeitos eleitos', 'TSE', 'a cada 4 anos',
     'Gestão Pública · Eleições municipais'),
    (VEREADORES, 'Vereadores eleitos', 'TSE', 'a cada 4 anos',
     'Gestão Pública · Eleições municipais'),
    (POPULACAO_MUNICIPAL, 'População dos municípios', 'IBGE · estimativas e Censo 2022',
     'anual', 'per capita e taxas'),
    (TRANSFERENCIAS_PE, 'Transferências constitucionais (FPM, FUNDEB, royalties...)',
     'STN · Tesouro Transparente', 'mensal', 'Gestão Pública · FPM e Transferências'),
    (ATIVIDADE_MENSAL, 'IBC-R, indústria, comércio, serviços e IPCA',
     'BCB · IBGE (PIM-PF, PMC, PMS, IPCA)', 'mensal', 'Atividade Econômica'),
    (PIB_TRIMESTRAL, 'PIB trimestral', 'CONDEPE/FIDEM · SEPLAG-PE (planilha)', 'trimestral',
     'Atividade Econômica · Visão geral'),
    (AGRO_PAM, 'Produção agrícola municipal', 'IBGE · PAM', 'anual',
     'Atividade Econômica · Agropecuária'),
    (AGRO_LSPA, 'Estimativas de safra', 'IBGE · LSPA', 'mensal',
     'Atividade Econômica · Agropecuária'),
    (AGRO_PPM, 'Pecuária municipal', 'IBGE · PPM', 'anual',
     'Atividade Econômica · Agropecuária'),
    (COMEX_UF_MENSAL, 'Exportações e importações (UF do produto)', 'Comex Stat · MDIC',
     'mensal', 'Comércio Exterior'),
    (COMEX_MUN_MENSAL, 'Exportações e importações por município', 'Comex Stat · MDIC',
     'mensal', 'Comércio Exterior · Municípios'),
    (IPS_PE, 'Índice de Progresso Social', 'IPS Brasil', 'anual (edições)',
     'Indicadores Sociais · Progresso social'),
    (MVI_PE, 'Mortes violentas intencionais', 'SDS-PE · microdados', 'mensal',
     'Indicadores Sociais · Segurança pública'),
]


# ============================================================================
# Catálogo
# ============================================================================

def _periodo(df, periodicidade: str) -> tuple:
    """(início, fim, rótulo legível) do período coberto pela base."""
    import pandas as pd
    if 'data' in df.columns and pd.api.types.is_datetime64_any_dtype(df['data']):
        ini, fim = df['data'].min(), df['data'].max()
        if periodicidade == 'trimestral':
            rot = f"{ini.year}T{(ini.month - 1) // 3 + 1} a {fim.year}T{(fim.month - 1) // 3 + 1}"
        else:
            rot = f"{MESES[ini.month - 1]}/{ini.year} a {MESES[fim.month - 1]}/{fim.year}"
        return str(ini.date()), str(fim.date()), rot
    if 'edicao' in df.columns:
        a, b = int(df['edicao'].min()), int(df['edicao'].max())
        return str(a), str(b), f"edições {a} a {b}"
    if 'ano' in df.columns:
        a, b = int(df['ano'].min()), int(df['ano'].max())
        return str(a), str(b), f"{a} a {b}" if a != b else str(a)
    return None, None, '—'


def gerar_catalogo() -> dict:
    import pandas as pd
    catalogo = {'gerado_em': datetime.now().isoformat(timespec='seconds'), 'datasets': []}
    for path, descricao, fonte, periodicidade, abas in BASES:
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        ini, fim, rot = _periodo(df, periodicidade)
        catalogo['datasets'].append({
            'arquivo': path.name, 'descricao': descricao, 'fonte': fonte,
            'periodicidade': periodicidade, 'usado_em': abas,
            'periodo_inicio': ini, 'periodo_fim': fim, 'periodo': rot,
            'n_registros': len(df), 'colunas': df.columns.tolist(),
            'tamanho_kb': round(path.stat().st_size / 1024, 1),
            'gerado_em': datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d'),
        })
    if GEO_MUNICIPIOS.exists():
        catalogo['datasets'].append({
            'arquivo': GEO_MUNICIPIOS.name, 'descricao': 'Malha dos municípios de PE',
            'fonte': 'API de Malhas · IBGE', 'periodicidade': 'estática',
            'usado_em': 'mapas', 'periodo': '—',
            'tamanho_kb': round(GEO_MUNICIPIOS.stat().st_size / 1024, 1),
        })
    with open(CATALOGO, 'w', encoding='utf-8') as f:
        json.dump(catalogo, f, ensure_ascii=False, indent=2)
    return catalogo


# ============================================================================
# README: tabela de períodos
# ============================================================================

MARCA_INI = '<!-- PERIODOS:INICIO -->'
MARCA_FIM = '<!-- PERIODOS:FIM -->'


def atualizar_readme(catalogo: dict) -> bool:
    """Reescreve a tabela entre as marcas do README. Devolve True se mudou."""
    if not README.exists():
        return False
    texto = README.read_text(encoding='utf-8')
    if MARCA_INI not in texto or MARCA_FIM not in texto:
        print("[CAT] README sem as marcas da tabela de períodos; nada a fazer")
        return False
    linhas = [MARCA_INI,
              '<!-- Tabela gerada por etl/run_all.py a partir do catálogo. Não edite à mão. -->',
              '',
              '| Base | Onde aparece | Fonte | Período | Gerada em |',
              '|---|---|---|---|---|']
    for d in catalogo['datasets']:
        if d.get('periodicidade') == 'estática':
            continue
        gerado = d.get('gerado_em', '')
        if gerado:
            a, m, dia = gerado.split('-')
            gerado = f"{dia}/{m}/{a}"
        linhas.append(f"| {d['descricao']} | {d.get('usado_em', '')} | {d['fonte']} | "
                      f"{d.get('periodo', '—')} | {gerado} |")
    linhas += ['', MARCA_FIM]
    ini = texto.index(MARCA_INI)
    fim = texto.index(MARCA_FIM) + len(MARCA_FIM)
    novo = texto[:ini] + '\n'.join(linhas) + texto[fim:]
    if novo != texto:
        README.write_text(novo, encoding='utf-8')
        return True
    return False


# ============================================================================
# Main
# ============================================================================

def main(argv=None):
    p = argparse.ArgumentParser(description='Roda os ETLs do Observatório PE.')
    p.add_argument('--offline', action='store_true',
                   help='não baixa nada: usa a última cópia em data/cache/')
    p.add_argument('--so', default='',
                   help='etapas separadas por vírgula (ex.: comex,seguranca)')
    args = p.parse_args(argv)
    if args.offline:
        os.environ['OBS_OFFLINE'] = '1'
    escolhidas = {e.strip() for e in args.so.split(',') if e.strip()}
    desconhecidas = escolhidas - {e[0] for e in ETAPAS}
    if desconhecidas:
        p.error(f"etapa(s) desconhecida(s): {', '.join(sorted(desconhecidas))}")

    print("=" * 64)
    print("OBSERVATÓRIO PE · ETL" + (" (offline)" if args.offline else ""))
    print("=" * 64)

    import importlib
    falhas, t0 = [], time.time()
    for nome, modulo, baixa in ETAPAS:
        if escolhidas and nome not in escolhidas:
            continue
        if nome == 'geo' and args.offline and GEO_MUNICIPIOS.exists():
            continue
        print()
        t = time.time()
        try:
            importlib.import_module(f'etl.{modulo}').main()
            print(f"   ({time.time() - t:.0f} s)")
        except Exception as e:  # uma etapa com erro não derruba as outras
            falhas.append((nome, e))
            print(f"\n   ✗ etapa '{nome}' falhou: {type(e).__name__}: {e}")
            if os.environ.get('OBS_DEBUG'):
                traceback.print_exc()

    print()
    print("[CAT] Gerando catálogo de metadados...")
    catalogo = gerar_catalogo()
    print(f"[CAT] {len(catalogo['datasets'])} bases registradas em {CATALOGO.name}")
    if atualizar_readme(catalogo):
        print("[CAT] README: tabela de períodos atualizada")

    print()
    minutos = (time.time() - t0) / 60
    if falhas:
        print(f"⚠ ETL concluído em {minutos:.1f} min, com {len(falhas)} etapa(s) com erro:")
        for nome, e in falhas:
            print(f"   - {nome}: {e}")
        print("  As demais bases foram atualizadas. Rode de novo mais tarde só as etapas "
              "com erro, por exemplo:  python -m etl.run_all --so " +
              ','.join(n for n, _ in falhas))
        return 1
    print(f"✓ ETL concluído em {minutos:.1f} min.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
