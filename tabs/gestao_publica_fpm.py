"""
tabs/gestao_publica_fpm.py
==========================
Sub-aba FPM (Gestão Pública): Fundo de Participação dos Municípios
recebido pelos 184 municípios de Pernambuco (Fernando de Noronha é
distrito estadual e não recebe FPM).

Estrutura:
1. KPIs do estado ou do município clicado no mapa: FPM bruto e variação
   nominal, crescimento real (IPCA), per capita, FPM/PIB e último decêndio
2. Mapa: per capita, total ou variação
3. Rankings: municípios e regiões de desenvolvimento
4. Mês a mês: ano escolhido x ano anterior, com as parcelas extras de 1%
5. Decêndios recentes e série anual (nominal e real)

Fonte: STN · Tesouro Transparente (etl/transferencias_etl.py).
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update

from components import data_fiscal as df_, ui, viz
from components.viz import CORES, moeda, pct, num, reais


def registrar():
    return {
        'eixo': 'Gestão Pública',
        'sub': 'FPM',
        'eixo_ordem': 3,
        'sub_ordem': 2,
        'ativa': True,
        'fonte_legenda': 'STN · Tesouro Nacional',
    }


# ============================================================================
# KPIs
# ============================================================================

def _kpis(ano: int, cod: int = None):
    r = df_.fpm_resumo(ano, cod)
    ref = f"vs {viz.periodo_meses(1, r['meses'])}/{ano - 1}" if r['meses'] < 12 \
        else f"vs {ano - 1}"
    ipca_txt = (f"descontado o IPCA (até {viz.mes_ano(r['ipca_ref'])})"
                if r.get('ipca_ref') is not None else "IPCA indisponível")

    if cod and r.get('municipio'):
        sub_pc = (f"{r['rank_pc']}º maior de {r['n_municipios']} no estado", 'neutro')
        contexto = r['municipio']
    else:
        sub_pc = (f"{num(r['populacao'])} habitantes", 'neutro')
        contexto = 'Pernambuco'

    if r.get('fpm_pib') is not None:
        k_pib = viz.kpi("FPM em relação ao PIB", pct(r['fpm_pib']),
                        (f"FPM bruto ÷ PIB municipal de {r['ano_pib']}", 'neutro'))
    else:
        k_pib = viz.kpi("FPM em relação ao PIB", "—", ("PIB indisponível", 'neutro'))

    u = r.get('ult_dec')
    if u:
        k_dec = viz.kpi(f"{int(u['decendio'])}º decêndio · {viz.mes_ano(u['data'])}",
                        moeda(u['valor']),
                        viz.variacao(u.get('var_pct'), 'vs mesmo decêndio de '
                                     f"{pd.Timestamp(u['data']).year - 1}"))
    else:
        k_dec = viz.kpi("último decêndio", "—")

    return viz.faixa_kpis([
        viz.kpi(f"FPM bruto · {r['rotulo']}", moeda(r['bruto']),
                viz.variacao(r['var_nominal'], ref), destaque=True),
        viz.kpi("crescimento real", pct(r['var_real'], sinal=True), (ipca_txt, 'neutro')),
        viz.kpi("FPM per capita", reais(r['per_capita']), sub_pc),
        k_pib,
        k_dec,
    ], contexto=contexto)


# ============================================================================
# Mapa e rankings
# ============================================================================

_VISOES_MAPA = [('per capita', 'pc'), ('total', 'total'), ('variação', 'var')]


def _mapa(ano: int, visao: str):
    d = df_.fpm_por_municipio(ano).copy()
    if d.empty:
        return viz.sem_dados_fig()
    d['_total'] = d['bruto'].map(moeda)
    d['_pc'] = d['per_capita'].map(reais)
    d['_var'] = d['var_pct'].map(lambda v: pct(v, sinal=True))
    d['_rd'] = d['regiao_desenvolvimento'].fillna('—')
    hover = [('RD', '_rd'), ('FPM bruto', '_total'), ('per capita', '_pc'),
             (f'variação vs {ano - 1}', '_var')]
    if visao == 'total':
        return viz.fig_mapa(d, 'bruto', hover, legenda='R$')
    if visao == 'var':
        lim = max(5.0, d['var_pct'].abs().quantile(0.95))
        return viz.fig_mapa(d, 'var_pct', hover, legenda='%', escala='div',
                            zmin=-lim, zmax=lim)
    return viz.fig_mapa(d, 'per_capita', hover, legenda='R$/hab.')


def _ranking(ano: int, visao: str, destaque=None):
    if visao == 'rd':
        d = df_.fpm_rds(ano)
        fig = viz.fig_ranking(d, 'regiao_desenvolvimento', 'per_capita',
                              fmt=reais, n=12)
        return viz.grafico(fig)
    d = df_.fpm_por_municipio(ano)
    col = 'per_capita' if visao == 'pc' else 'bruto'
    fmt = reais if visao == 'pc' else moeda
    fig = viz.fig_ranking(d, 'municipio', col, fmt=fmt, n=10, destaque=destaque)
    return viz.grafico(fig)


# ============================================================================
# Mês a mês, decêndios e série anual
# ============================================================================

def _mensal(ano: int, cod: int = None):
    s = df_.fpm_mensal(cod)
    cur = s[s['ano'] == ano].set_index('mes')
    ant = s[s['ano'] == ano - 1].set_index('mes')
    if cur.empty:
        return viz.grafico(viz.sem_dados_fig())
    meses = range(1, 13)
    x = [viz.MESES[m - 1] for m in meses]
    ordin = cur['ordinario'].reindex(meses)
    extra = cur['extra_1pct'].reindex(meses)
    tot_ant = ant['bruto'].reindex(meses)
    div, suf = viz.escala_monetaria(max(cur['bruto'].max(), ant['bruto'].max()
                                        if len(ant) else 0))
    fig = go.Figure()
    for serie, nome, cor in ((ordin, f'FPM ordinário {ano}', CORES['azul']),
                             (extra, 'parcelas extras de 1%', CORES['mostarda'])):
        fig.add_trace(go.Bar(x=x, y=serie / div, name=nome,
                             marker=dict(color=cor, line=dict(color='#FFFFFF', width=1)),
                             customdata=[moeda(v) for v in serie],
                             hovertemplate=f'{nome}: %{{customdata}}<extra></extra>'))
    fig.add_trace(go.Scatter(x=x, y=tot_ant / div, name=f'total {ano - 1}',
                             mode='lines+markers',
                             line=dict(color=CORES['cinza'], width=2, dash='dot'),
                             marker=dict(size=7, color=CORES['cinza'],
                                         line=dict(color='#FFFFFF', width=1)),
                             customdata=[moeda(v) for v in tot_ant],
                             hovertemplate=f'total {ano - 1}: %{{customdata}}<extra></extra>'))
    viz.layout_padrao(fig, altura=330, legenda=True, y_prefixo='R$ ', y_sufixo=suf)
    fig.update_layout(barmode='stack')
    return viz.grafico(fig)


_CORES_DECENDIO = ['#1F4F86', '#4F83BD', '#8FB0D5']


def _decendios(cod: int = None):
    d = df_.fpm_decendios(cod, n_meses=12)
    if d.empty:
        return viz.grafico(viz.sem_dados_fig())
    datas = sorted(d['data'].unique())
    x = [viz.mes_ano(dt) for dt in datas]
    series = []
    for k in (1, 2, 3):
        sub = d[d['decendio'] == k].set_index('data')['valor'].reindex(datas)
        series.append({'y': sub.tolist(), 'nome': f'{k}º decêndio',
                       'cor': _CORES_DECENDIO[k - 1]})
    fig = viz.fig_barras_series(x, series, altura=300, monetario='R$')
    fig.update_xaxes(tickangle=-45, tickfont=dict(size=9))
    return viz.grafico(fig)


def _anual(cod: int = None):
    a = df_.fpm_anual(cod)
    if a.empty:
        return viz.grafico(viz.sem_dados_fig())
    rot = [str(r.ano) if r.meses == 12 else f"{r.ano}*" for r in a.itertuples()]
    div, suf = viz.escala_monetaria(max(a['nominal'].max(), a['real'].max()))
    fig = go.Figure()
    fig.add_trace(go.Bar(x=rot, y=a['nominal'] / div, name='nominal',
                         marker=dict(color=CORES['azul']),
                         customdata=[moeda(v) for v in a['nominal']],
                         hovertemplate='nominal: %{customdata}<extra></extra>'))
    fig.add_trace(go.Scatter(x=rot, y=a['real'] / div, name='real (IPCA)',
                             mode='lines+markers',
                             line=dict(color=CORES['terracota'], width=2),
                             marker=dict(size=8, color=CORES['terracota'],
                                         line=dict(color='#FFFFFF', width=1)),
                             customdata=[moeda(v) for v in a['real']],
                             hovertemplate='real: %{customdata}<extra></extra>'))
    viz.layout_padrao(fig, altura=300, legenda=True, y_prefixo='R$ ', y_sufixo=suf)
    return viz.grafico(fig)


# ============================================================================
# Layout
# ============================================================================

def layout():
    if not df_.disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Gestão Pública", "FPM · Fundo de Participação dos Municípios"),
            viz.aviso("Os dados de transferências ainda não foram gerados. "
                      "Rode o ETL:", "python -m etl.run_all"),
        ])
    anos = df_.anos()
    ano = anos[0]
    ult = df_.ultima_data()

    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba(
            "Gestão Pública",
            f"FPM · Fundo de Participação dos Municípios · 184 municípios · "
            f"{anos[-1]}—{viz.mes_ano(ult)}",
            dica="clique em um município no mapa para ver os números dele",
            botao_limpar='gpf-limpar'),

        dcc.Store(id='gpf-sel', data=None),

        viz.linha_filtros(
            viz.filtro("ANO:", viz.dropdown('gpf-ano', df_.opcoes_anos(), ano)),
        ),

        html.Div(id='gpf-kpis', children=_kpis(ano)),

        viz.secao(
            "FPM por município",
            "FPM bruto (inclui a retenção de 20% para o FUNDEB e as parcelas "
            "extras de 1%) · passe o mouse para ver os valores",
            viz.botoes('gpf-mapa-visao', _VISOES_MAPA, 'pc'),
            dcc.Graph(id='gpf-mapa', figure=_mapa(ano, 'pc'),
                      config=viz.GRAPH_CONFIG),
        ),

        viz.grade(
            viz.secao(
                "ranking municipal", "maiores valores no ano escolhido",
                viz.botoes('gpf-rank-visao', [('per capita', 'pc'), ('total', 'total')], 'pc'),
                html.Div(id='gpf-ranking', children=_ranking(ano, 'pc')),
            ),
            viz.secao(
                "regiões de desenvolvimento", "FPM per capita por RD",
                html.Div(id='gpf-ranking-rd', children=_ranking(ano, 'rd')),
            ),
        ),

        viz.secao(
            "mês a mês",
            "FPM bruto por mês no ano escolhido (barras) e total do ano anterior "
            "(linha) · em amarelo, as parcelas extras de 1% de julho, setembro e "
            "dezembro",
            html.Div(id='gpf-mensal', children=_mensal(ano)),
        ),

        viz.grade(
            viz.secao(
                "decêndios", "FPM bruto nos últimos 12 meses, por decêndio "
                "(créditos dos dias 10, 20 e 30)",
                html.Div(id='gpf-decendios', children=_decendios()),
            ),
            viz.secao(
                "série anual",
                "FPM bruto por ano, nominal e real (preços do último mês com "
                "IPCA) · * ano incompleto",
                html.Div(id='gpf-anual', children=_anual()),
            ),
        ),

        viz.nota("Como ler: o FPM bruto soma o valor creditado ao município, a "
                 "retenção de 20% destinada ao FUNDEB (que volta ao município "
                 "conforme as matrículas) e as parcelas extras de 1%. Até 2024 "
                 "as parcelas de 1% vinham somadas ao FPM; o painel as separa "
                 "usando a retenção do FUNDEB, que não incide sobre elas. Nos "
                 "meses em que o arquivo mensal do Tesouro veio incompleto ou "
                 "não foi publicado (como out/2022), vale o total da série "
                 "consolidada do Tesouro, sem o detalhe por decêndio."),

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
        Output('gpf-sel', 'data'),
        Input('gpf-mapa', 'clickData'),
        Input('gpf-limpar', 'n_clicks'),
        State('gpf-sel', 'data'),
        prevent_initial_call=True,
    )
    def selecionar(click, _n, atual):
        if ctx.triggered_id == 'gpf-limpar':
            return None
        if click:
            try:
                cod = int(str(click['points'][0]['location']))
            except (KeyError, TypeError, ValueError):
                return no_update
            return None if cod == atual else cod
        return no_update

    @app.callback(
        Output('gpf-limpar', 'className'),
        Input('gpf-sel', 'data'),
    )
    def botao(cod):
        return 'btn-link' if cod else 'btn-link hidden'

    @app.callback(
        Output('gpf-kpis', 'children'),
        Output('gpf-mensal', 'children'),
        Input('gpf-ano', 'value'),
        Input('gpf-sel', 'data'),
    )
    def kpis_mensal(ano, cod):
        if not ano:
            return no_update, no_update
        return _kpis(ano, cod), _mensal(ano, cod)

    @app.callback(
        Output('gpf-decendios', 'children'),
        Output('gpf-anual', 'children'),
        Input('gpf-sel', 'data'),
    )
    def series(cod):
        return _decendios(cod), _anual(cod)

    @app.callback(
        Output('gpf-mapa', 'figure'),
        Input('gpf-ano', 'value'),
        Input('gpf-mapa-visao', 'value'),
    )
    def mapa(ano, visao):
        if not ano:
            return no_update
        return _mapa(ano, visao or 'pc')

    @app.callback(
        Output('gpf-ranking', 'children'),
        Output('gpf-ranking-rd', 'children'),
        Input('gpf-ano', 'value'),
        Input('gpf-rank-visao', 'value'),
        Input('gpf-sel', 'data'),
    )
    def rankings(ano, visao, cod):
        if not ano:
            return no_update, no_update
        nome = None
        if cod:
            from components.data_base import nome_municipio
            nome = nome_municipio(cod)
        return _ranking(ano, visao or 'pc', nome), _ranking(ano, 'rd')
