"""
tabs/gestao_publica_transferencias.py
=====================================
Sub-aba Transferências (Gestão Pública): tudo o que a União credita aos
municípios de Pernambuco por transferências constitucionais e legais.
Substitui a antiga sub-aba "Receita Fiscal" (v1.x), que somava como
"ICMS", "IPVA" e "FPE" o que na verdade é FUNDEB recebido.

Grupos:
    FPM        FPM creditado + parcelas extras de 1%
    FUNDEB     FUNDEB recebido (todas as origens, complementação da União
               e ajustes anuais)
    Royalties  petróleo e gás (ANP), FEP, mineração (CFEM), recursos hídricos
    Demais     ITR, Lei Kandir/LC 176, apoio financeiro (AFM, LC 173), CIDE,
               IOF-Ouro

Valores creditados: as retenções para o FUNDEB não entram no total, porque
voltam ao município como "FUNDEB recebido".

Fonte: STN · Tesouro Transparente (etl/transferencias_etl.py).
"""

import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update

from components import data_fiscal as df_, ui, viz
from components.data_base import nome_municipio
from components.viz import CORES, moeda, pct, num, reais

CORES_GRUPOS = {'FPM': CORES['azul'], 'FUNDEB': CORES['terracota'],
                'Royalties': CORES['violeta'], 'Demais': CORES['verde']}


def registrar():
    return {
        'eixo': 'Gestão Pública',
        'sub': 'Transferências',
        'eixo_ordem': 3,
        'sub_ordem': 3,
        'ativa': True,
        'fonte_legenda': 'STN · Tesouro Nacional',
    }


# ============================================================================
# KPIs
# ============================================================================

def _kpis(ano: int, cod: int = None):
    r = df_.trf_resumo(ano, cod)
    m = df_.meses_no_ano(ano)
    ref = f"vs {viz.periodo_meses(1, m)}/{ano - 1}" if m < 12 else f"vs {ano - 1}"
    g = r['grupos']

    def k_grupo(nome, label):
        v = g.get(nome, {})
        return viz.kpi(label, moeda(v.get('valor')),
                       viz.variacao(v.get('var_pct'), ref))

    if cod and r.get('municipio'):
        sub_pc = (f"{r['rank_pc']}º maior de {r['n_municipios']} no estado", 'neutro')
        contexto = r['municipio']
    else:
        sub_pc = ("total creditado ÷ população", 'neutro')
        contexto = 'Pernambuco'

    return viz.faixa_kpis([
        viz.kpi(f"total creditado · {r['rotulo']}", moeda(r['total']),
                viz.variacao(r['var_pct'], ref), destaque=True),
        k_grupo('FUNDEB', 'FUNDEB recebido'),
        k_grupo('Royalties', 'royalties'),
        viz.kpi("per capita", reais(r['per_capita']), sub_pc),
        viz.kpi("peso do FPM", pct(r['part_fpm']), ("do total creditado", 'neutro')),
    ], contexto=contexto)


# ============================================================================
# Mapa, composição e evolução
# ============================================================================

def _mapa(ano: int, grupo: str, visao: str):
    d = df_.trf_municipal(ano, grupo).copy()
    if d.empty:
        return viz.sem_dados_fig()
    d['_v'] = d['valor'].map(moeda)
    d['_pc'] = d['per_capita'].map(reais)
    d['_var'] = d['var_pct'].map(lambda v: pct(v, sinal=True))
    d['_rd'] = d['regiao_desenvolvimento'].fillna('—')
    rot = 'total creditado' if grupo == 'Total' else grupo
    hover = [('RD', '_rd'), (rot, '_v'), ('per capita', '_pc'),
             (f'variação vs {ano - 1}', '_var')]
    if visao == 'total':
        return viz.fig_mapa(d, 'valor', hover, legenda='R$')
    return viz.fig_mapa(d, 'per_capita', hover, legenda='R$/hab.')


def _composicao(ano: int, cod: int = None, rd: str = None):
    g = df_.trf_grupos(ano, cod, rd)
    g = g[g['valor'] > 0]
    if g.empty:
        return viz.grafico(viz.sem_dados_fig())
    tot = g['valor'].sum()
    fig = viz.fig_donut(g['grupo'].tolist(), g['valor'].tolist(),
                        cores=[CORES_GRUPOS[x] for x in g['grupo']],
                        centro=f"<b>{moeda(tot)}</b><br>"
                               f"<span style='font-size:10px'>{df_.rotulo(ano)}</span>")
    cat = df_.trf_categorias(ano, cod, rd)
    cat['_v'] = cat['valor'].map(moeda)
    cat['_p'] = cat['part_pct'].map(pct)
    cat['_var'] = cat['var_pct'].map(lambda v: pct(v, sinal=True))
    tab = viz.tabela(cat, [('categoria', 'rotulo', 'esq'), ('valor', '_v', 'dir'),
                           ('% do total', '_p', 'dir'), ('variação', '_var', 'dir')])
    return html.Div([viz.grafico(fig), tab])


def _evolucao(cod: int = None, rd: str = None):
    a = df_.trf_anual_grupos(cod, rd)
    if a.empty:
        return viz.grafico(viz.sem_dados_fig())
    x = [str(r.ano) if r.meses == 12 else f"{r.ano}*" for r in a.itertuples()]
    series = [{'y': a[gr], 'nome': gr, 'cor': CORES_GRUPOS[gr]}
              for gr in df_.ORDEM_GRUPOS if gr in a.columns]
    fig = viz.fig_barras_series(x, series, altura=340, empilhado=True,
                                monetario='R$')
    return viz.grafico(fig)


def _royalties(ano: int, cod: int = None):
    t = df_.royalties_tipos(ano, cod)
    if t.empty or t['valor'].sum() == 0:
        return viz.grafico(viz.sem_dados_fig("Sem royalties no período."))
    fig = viz.fig_ranking(t, 'rotulo', 'valor', fmt=moeda, n=6,
                          cor=CORES['violeta'])
    return viz.grafico(fig)


def _ranking(ano: int, grupo: str, destaque=None):
    d = df_.trf_municipal(ano, grupo)
    fig = viz.fig_ranking(d, 'municipio', 'per_capita', fmt=reais, n=10,
                          destaque=destaque)
    return viz.grafico(fig)


# ============================================================================
# Layout
# ============================================================================

_GRUPOS_OPCOES = [('Total creditado', 'Total'), ('FPM', 'FPM'), ('FUNDEB', 'FUNDEB'),
                  ('Royalties', 'Royalties'), ('Demais', 'Demais')]


def layout():
    if not df_.disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Gestão Pública", "Transferências constitucionais"),
            viz.aviso("Os dados de transferências ainda não foram gerados. "
                      "Rode o ETL:", "python -m etl.run_all"),
        ])
    anos = df_.anos()
    ano = anos[0]
    ult = df_.ultima_data()
    rds = df_.trf()['regiao_desenvolvimento'].dropna().unique().tolist()

    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba(
            "Gestão Pública",
            f"Transferências constitucionais da União · FPM · FUNDEB · royalties "
            f"· {anos[-1]}—{viz.mes_ano(ult)}",
            dica="clique em um município no mapa para ver os números dele",
            botao_limpar='gpt-limpar'),

        dcc.Store(id='gpt-sel', data=None),

        viz.linha_filtros(
            viz.filtro("ANO:", viz.dropdown('gpt-ano', df_.opcoes_anos(), ano)),
            viz.filtro("TRANSFERÊNCIA:", viz.dropdown('gpt-grupo', _GRUPOS_OPCOES, 'Total')),
        ),

        html.Div(id='gpt-kpis', children=_kpis(ano)),

        viz.secao(
            "transferências por município",
            "valor creditado no ano escolhido · use os filtros acima para trocar "
            "o tipo de transferência",
            viz.botoes('gpt-mapa-visao', [('per capita', 'pc'), ('total', 'total')], 'pc'),
            dcc.Graph(id='gpt-mapa', figure=_mapa(ano, 'Total', 'pc'),
                      config=viz.GRAPH_CONFIG),
        ),

        viz.grade(
            viz.secao(
                "composição", "participação de cada grupo no total creditado · "
                "estado, RD ou município clicado",
                viz.linha_filtros(viz.filtro("RD:", viz.dropdown(
                    'gpt-rd', [('Todas (estado)', '__todas__')] +
                    [(r, r) for r in sorted(rds)], '__todas__', busca=True))),
                html.Div(id='gpt-composicao', children=_composicao(ano)),
            ),
            viz.secao(
                "evolução", "total creditado por ano e grupo · * ano incompleto",
                html.Div(id='gpt-evolucao', children=_evolucao()),
            ),
        ),

        viz.grade(
            viz.secao(
                "ranking per capita", "maiores valores por habitante no ano",
                html.Div(id='gpt-ranking', children=_ranking(ano, 'Total')),
            ),
            viz.secao(
                "royalties", "royalties e compensações financeiras por tipo",
                html.Div(id='gpt-royalties', children=_royalties(ano)),
            ),
        ),

        viz.nota("Como ler: as linhas que o Tesouro chama de \"FPE\", \"ICMS\", "
                 "\"IPVA\" etc. dentro do FUNDEB são o FUNDEB que o município "
                 "recebe, separado pela origem do recurso, e não cota-parte "
                 "desses impostos. A cota-parte do ICMS e do IPVA é repassada "
                 "pelo Estado e não está nesta base. Nos meses em que o arquivo "
                 "mensal do Tesouro veio incompleto ou não foi publicado (como "
                 "out/2022), FPM, FUNDEB, ITR, CIDE e LC 176 vêm da série "
                 "consolidada do Tesouro; os royalties de out/2022 não estão "
                 "disponíveis."),

        ui.footer(
            fonte_principal="STN · Tesouro Transparente · Transferências "
                            "constitucionais para municípios",
            atualizacao=viz.mes_ano(ult),
        ),
    ])


# ============================================================================
# Callbacks
# ============================================================================

def callbacks(app):

    @app.callback(
        Output('gpt-sel', 'data'),
        Input('gpt-mapa', 'clickData'),
        Input('gpt-limpar', 'n_clicks'),
        State('gpt-sel', 'data'),
        prevent_initial_call=True,
    )
    def selecionar(click, _n, atual):
        if ctx.triggered_id == 'gpt-limpar':
            return None
        if click:
            try:
                cod = int(str(click['points'][0]['location']))
            except (KeyError, TypeError, ValueError):
                return no_update
            return None if cod == atual else cod
        return no_update

    @app.callback(Output('gpt-limpar', 'className'), Input('gpt-sel', 'data'))
    def botao(cod):
        return 'btn-link' if cod else 'btn-link hidden'

    @app.callback(
        Output('gpt-kpis', 'children'),
        Input('gpt-ano', 'value'),
        Input('gpt-sel', 'data'),
    )
    def kpis(ano, cod):
        return _kpis(ano, cod) if ano else no_update

    @app.callback(
        Output('gpt-mapa', 'figure'),
        Output('gpt-ranking', 'children'),
        Input('gpt-ano', 'value'),
        Input('gpt-grupo', 'value'),
        Input('gpt-mapa-visao', 'value'),
        Input('gpt-sel', 'data'),
    )
    def mapa_ranking(ano, grupo, visao, cod):
        if not ano:
            return no_update, no_update
        grupo = grupo or 'Total'
        destaque = nome_municipio(cod) if cod else None
        mapa = no_update if ctx.triggered_id == 'gpt-sel' else _mapa(ano, grupo, visao or 'pc')
        return mapa, _ranking(ano, grupo, destaque)

    @app.callback(
        Output('gpt-composicao', 'children'),
        Output('gpt-evolucao', 'children'),
        Output('gpt-royalties', 'children'),
        Input('gpt-ano', 'value'),
        Input('gpt-rd', 'value'),
        Input('gpt-sel', 'data'),
    )
    def detalhe(ano, rd, cod):
        if not ano:
            return no_update, no_update, no_update
        rd = None if (not rd or rd == '__todas__') else rd
        if cod:
            rd = None
        return (_composicao(ano, cod, rd), _evolucao(cod, rd),
                _royalties(ano, cod))
