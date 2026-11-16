"""
tabs/indicadores_sociais_seguranca.py
=====================================
Sub-aba Segurança pública (Indicadores Sociais): mortes violentas
intencionais (MVI) em Pernambuco, a partir dos microdados da SDS-PE.

Estrutura:
1. KPIs do estado ou do município clicado: MVI no período e variação,
   taxa por 100 mil hab. em 12 meses, feminicídios, jovens, municípios
   sem MVI
2. Série mensal desde 2004 (mensal ou média móvel de 12 meses)
3. Mapa da taxa por 100 mil hab. e ranking
4. Taxas por RD e perfil das vítimas (sexo, idade, natureza)
5. Série anual com taxa por 100 mil

Fonte: SDS-PE · microdados de MVI (etl/seguranca_etl.py). População:
IBGE (etl/populacao_etl.py).
"""

from dash import Input, Output, State, ctx, dcc, html, no_update

from components import data_social as ds, ui, viz
from components.data_base import nome_municipio
from components.viz import CORES, num, pct

ORDEM_FAIXAS = ['0 a 11', '12 a 17', '18 a 24', '25 a 29', '30 a 39', '40 a 49',
                '50 a 59', '60 ou mais', 'Não informada']


def registrar():
    return {
        'eixo': 'Indicadores Sociais',
        'sub': 'Segurança pública',
        'eixo_ordem': 6,
        'sub_ordem': 2,
        'ativa': True,
        'fonte_legenda': 'SDS-PE',
    }


def _kpis(ano, cod=None):
    r = ds.mvi_resumo(ano, cod)
    ref = (f"vs {viz.periodo_meses(1, r['meses'])}/{ano - 1}" if r['meses'] < 12
           else f"vs {ano - 1}")
    ult = ds.mvi_ultima_data()
    k = [
        viz.kpi(f"mortes violentas · {r['rotulo']}", num(r['total']),
                viz.variacao(r['var_pct'], ref, inverter=True), destaque=True),
        viz.kpi("taxa em 12 meses", num(r['taxa_12m'], 1) if r['taxa_12m'] else '—',
                (f"por 100 mil hab. · até {viz.mes_ano(ult)} ({num(r['ult12'])} vítimas)",
                 'neutro')),
        viz.kpi("feminicídios", num(r['feminicidios']),
                (f"{num(r['mulheres'])} mulheres vítimas no período", 'neutro')),
        viz.kpi("jovens de 18 a 29 anos", pct(r['jovens_pct']),
                ("das vítimas com idade informada", 'neutro')),
    ]
    if cod:
        k.append(viz.kpi("mortes por intervenção do Estado", num(r['intervencao']),
                         ("no período", 'neutro')))
        contexto = nome_municipio(cod)
    else:
        k.append(viz.kpi("municípios sem MVI", num(r['municipios_sem']),
                         ("de 185, no período", 'neutro')))
        contexto = 'Pernambuco'
    return viz.faixa_kpis(k, contexto=contexto)


def _serie(visao, cod=None):
    s = ds.mvi_mensal(cod)
    if s.empty:
        return viz.grafico(viz.sem_dados_fig())
    if visao == 'mm12':
        y = s.rolling(12).mean()
        nome = 'média móvel de 12 meses'
    else:
        y = s
        nome = 'vítimas no mês'
    fig = viz.fig_linhas([{'x': s.index, 'y': y.values, 'nome': nome,
                           'cor': CORES['terracota']}], altura=300, hover_fmt=',.0f')
    return viz.grafico(fig)


def _mapa(ano):
    d = ds.mvi_municipios(ano).copy()
    d['_v'] = d['vitimas'].map(num)
    d['_t'] = d['taxa'].map(lambda v: num(v, 1))
    d['_rd'] = d['regiao_desenvolvimento'].fillna('—')
    lim = d['taxa'].quantile(0.97)
    return viz.fig_mapa(d, 'taxa', [('RD', '_rd'), ('vítimas', '_v'),
                                    ('taxa por 100 mil', '_t')],
                        legenda='por 100 mil', zmin=0, zmax=lim, escala='quente')


def _ranking(ano, visao, destaque=None):
    d = ds.mvi_municipios(ano)
    if visao == 'taxa':
        d = d[d['populacao'] >= 20000]
        fig = viz.fig_ranking(d, 'municipio', 'taxa', fmt=lambda v: num(v, 1), n=12,
                              cor=CORES['terracota'], destaque=destaque)
        nota = "Taxa por 100 mil hab., municípios com 20 mil habitantes ou mais."
    else:
        fig = viz.fig_ranking(d, 'municipio', 'vitimas', fmt=num, n=12,
                              cor=CORES['terracota'], destaque=destaque)
        nota = "Número de vítimas no período."
    return html.Div([viz.grafico(fig), viz.nota(nota)])


def _rds(ano):
    d = ds.mvi_rds(ano)
    fig = viz.fig_ranking(d, 'regiao_desenvolvimento', 'taxa', fmt=lambda v: num(v, 1),
                          n=12, cor=CORES['terracota'])
    return viz.grafico(fig)


def _perfil(ano, dim, cod=None):
    d = ds.mvi_perfil(ano, dim, cod)
    if d.empty:
        return viz.grafico(viz.sem_dados_fig())
    if dim == 'faixa_etaria':
        d = d.set_index(dim).reindex(ORDEM_FAIXAS).dropna(subset=['vitimas']).reset_index()
        fig = viz.fig_barras(d[dim], d['vitimas'], cor=CORES['terracota'], altura=300,
                             texto=[pct(p) for p in d['part_pct']], hover_fmt=',.0f')
        return viz.grafico(fig)
    d = d.assign(_txt=[f"{num(v)} · {pct(p)}" for v, p in zip(d['vitimas'], d['part_pct'])])
    fig = viz.fig_ranking(d, dim, 'vitimas', fmt=num, n=10, cor=CORES['terracota'],
                          hover_extra='_txt')
    return viz.grafico(fig)


def _anual(cod=None):
    a = ds.mvi_anual(cod)
    x = [str(r.ano) if r.meses == 12 else f"{r.ano}*" for r in a.itertuples()]
    fig = viz.fig_barras(x, a['taxa'], cor=CORES['terracota'], altura=300,
                         hover_fmt=',.1f', y_sufixo='')
    fig.data[0].customdata = [f"{num(t, 1)} por 100 mil · {num(v)} vítimas"
                              for t, v in zip(a['taxa'], a['vitimas'])]
    fig.data[0].hovertemplate = '%{x}: %{customdata}<extra></extra>'
    return viz.grafico(fig)


def layout():
    if not ds.mvi_disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Indicadores Sociais", "Segurança pública"),
            viz.aviso("Os dados de segurança ainda não foram gerados. Rode o ETL:",
                      "python -m etl.run_all"),
        ])
    anos = ds.mvi_anos()
    ano = anos[0]
    ult = ds.mvi_ultima_data()
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Indicadores Sociais",
                       f"Segurança pública · mortes violentas intencionais (MVI) · "
                       f"{anos[-1]}—{viz.mes_ano(ult)}",
                       dica="clique em um município no mapa para ver os números dele",
                       botao_limpar='seg-limpar'),
        dcc.Store(id='seg-sel', data=None),
        viz.linha_filtros(viz.filtro("ANO:", viz.dropdown('seg-ano', ds.mvi_opcoes_anos(), ano))),
        html.Div(id='seg-kpis', children=_kpis(ano)),
        viz.secao("evolução mensal", "vítimas de mortes violentas intencionais desde 2004 · "
                  "estado ou município clicado",
                  viz.botoes('seg-visao', [('média móvel de 12 meses', 'mm12'),
                                           ('mensal', 'mes')], 'mm12'),
                  html.Div(id='seg-serie', children=_serie('mm12'))),
        viz.secao("taxa por município", "vítimas por 100 mil habitantes no ano escolhido "
                  "(anualizada em ano incompleto)",
                  dcc.Graph(id='seg-mapa', figure=_mapa(ano), config=viz.GRAPH_CONFIG)),
        viz.grade(
            viz.secao("ranking municipal", "maiores taxas ou maiores números absolutos",
                      viz.botoes('seg-rank-visao', [('taxa', 'taxa'), ('vítimas', 'vitimas')],
                                 'taxa'),
                      html.Div(id='seg-ranking', children=_ranking(ano, 'taxa'))),
            viz.secao("regiões de desenvolvimento", "taxa por 100 mil habitantes",
                      html.Div(id='seg-rds', children=_rds(ano))),
        ),
        viz.grade(
            viz.secao("perfil das vítimas", "no ano escolhido · estado ou município clicado",
                      viz.botoes('seg-perfil-dim', [('idade', 'faixa_etaria'),
                                                    ('natureza', 'natureza'), ('sexo', 'sexo')],
                                 'faixa_etaria'),
                      html.Div(id='seg-perfil', children=_perfil(ano, 'faixa_etaria'))),
            viz.secao("série anual", "taxa por 100 mil habitantes · * ano incompleto, anualizado",
                      html.Div(id='seg-anual', children=_anual())),
        ),
        viz.nota("Como ler: mortes violentas intencionais (MVI) somam homicídios, "
                 "feminicídios, latrocínios, lesões corporais seguidas de morte e mortes por "
                 "intervenção de agente do Estado. A SDS consolida cada mês até o dia 15 do "
                 "mês seguinte. Em municípios pequenos, poucas mortes mudam muito a taxa; "
                 "por isso o ranking de taxas considera só municípios com 20 mil habitantes "
                 "ou mais."),
        ui.footer(fonte_principal="SDS-PE · Secretaria de Defesa Social · microdados de MVI · "
                                  "população: IBGE",
                  atualizacao=viz.mes_ano(ult)),
    ])


def callbacks(app):

    @app.callback(Output('seg-sel', 'data'),
                  Input('seg-mapa', 'clickData'), Input('seg-limpar', 'n_clicks'),
                  State('seg-sel', 'data'), prevent_initial_call=True)
    def selecionar(click, _n, atual):
        if ctx.triggered_id == 'seg-limpar':
            return None
        if click:
            try:
                cod = int(str(click['points'][0]['location']))
            except (KeyError, TypeError, ValueError):
                return no_update
            return None if cod == atual else cod
        return no_update

    @app.callback(Output('seg-limpar', 'className'), Input('seg-sel', 'data'))
    def botao(cod):
        return 'btn-link' if cod else 'btn-link hidden'

    @app.callback(Output('seg-kpis', 'children'), Output('seg-perfil', 'children'),
                  Input('seg-ano', 'value'), Input('seg-perfil-dim', 'value'),
                  Input('seg-sel', 'data'))
    def kpis(ano, dim, cod):
        if not ano:
            return no_update, no_update
        return _kpis(ano, cod), _perfil(ano, dim or 'faixa_etaria', cod)

    @app.callback(Output('seg-serie', 'children'), Output('seg-anual', 'children'),
                  Input('seg-visao', 'value'), Input('seg-sel', 'data'))
    def series(visao, cod):
        return _serie(visao or 'mm12', cod), _anual(cod)

    @app.callback(Output('seg-mapa', 'figure'), Output('seg-rds', 'children'),
                  Input('seg-ano', 'value'))
    def mapa(ano):
        if not ano:
            return no_update, no_update
        return _mapa(ano), _rds(ano)

    @app.callback(Output('seg-ranking', 'children'),
                  Input('seg-ano', 'value'), Input('seg-rank-visao', 'value'),
                  Input('seg-sel', 'data'))
    def ranking(ano, visao, cod):
        if not ano:
            return no_update
        return _ranking(ano, visao or 'taxa', nome_municipio(cod) if cod else None)
