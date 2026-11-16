"""
tabs/comercio_exterior_municipios.py
====================================
Sub-aba Municípios (Comércio Exterior): exportações e importações por
município de Pernambuco.

A abertura municipal do Comex Stat usa o domicílio fiscal da empresa
exportadora ou importadora, e não a UF do produto, por isso o total dos
municípios não coincide com o da aba Balança comercial.

Estrutura:
1. KPIs: municípios com comércio, maior município, concentração
2. Mapa (escala logarítmica, porque o comércio é muito concentrado)
3. Ranking e, ao clicar no mapa, produtos e série do município

Fonte: Comex Stat · MDIC, endpoint de municípios (etl/comex_etl.py).
"""

import numpy as np
from dash import Input, Output, State, ctx, dcc, html, no_update

from components import data_comex as dc, ui, viz
from components.data_base import nome_municipio
from components.viz import COR_FLUXO, pct, usd


def registrar():
    return {
        'eixo': 'Comércio Exterior',
        'sub': 'Municípios',
        'eixo_ordem': 5,
        'sub_ordem': 3,
        'ativa': True,
        'fonte_legenda': 'Comex Stat · MDIC',
    }


def _kpis(ano, fluxo, cod=None):
    d = dc.municipios(ano, fluxo)
    nome = dc.NOME_FLUXO[fluxo]
    if d.empty:
        return viz.faixa_kpis([viz.kpi("sem dados", "—")])
    top = d.iloc[0]
    top3 = d['part_pct'].head(3).sum()
    kpis = [
        viz.kpi(f"{nome} · {dc.rotulo(ano)}", usd(d['valor'].sum()),
                ("soma dos municípios (domicílio da empresa)", 'neutro'), destaque=True),
        viz.kpi("municípios com comércio", str(len(d)), ("de 185", 'neutro')),
        viz.kpi("maior município", top['municipio'],
                (f"{usd(top['valor'])} · {pct(top['part_pct'])} do total", 'neutro')),
        viz.kpi("concentração", pct(top3), ("do valor nos 3 maiores municípios", 'neutro')),
    ]
    contexto = f"Pernambuco · {nome}"
    if cod:
        s = d[d['cod_ibge_6'] == cod]
        if len(s):
            r = s.iloc[0]
            pos = int(d.reset_index(drop=True).index[d['cod_ibge_6'].values == cod][0]) + 1
            kpis = [
                viz.kpi(f"{nome} · {dc.rotulo(ano)}", usd(r['valor']),
                        viz.variacao(r['var_pct'], 'vs mesmo período do ano anterior'),
                        destaque=True),
                viz.kpi("posição no estado", f"{pos}º", (f"de {len(d)} municípios", 'neutro')),
                viz.kpi("participação", pct(r['part_pct'], 2), ("do total dos municípios", 'neutro')),
                viz.kpi("por habitante", viz.reais(r['per_capita'], 'US$'),
                        ("valor ÷ população", 'neutro')),
            ]
            contexto = r['municipio']
        else:
            contexto = f"{nome_municipio(cod)} · sem {nome} no período"
    return viz.faixa_kpis(kpis, contexto=contexto)


def _mapa(ano, fluxo):
    d = dc.municipios(ano, fluxo).copy()
    if d.empty:
        return viz.sem_dados_fig()
    d['log'] = np.log10(d['valor'].clip(lower=1))
    d['_v'] = d['valor'].map(usd)
    d['_p'] = d['part_pct'].map(lambda v: pct(v, 2))
    d['_var'] = d['var_pct'].map(lambda v: pct(v, sinal=True))
    d['_rd'] = d['regiao_desenvolvimento'].fillna('—')
    fig = viz.fig_mapa(d, 'log', [('RD', '_rd'), (dc.NOME_FLUXO[fluxo], '_v'),
                                  ('% do total', '_p'), ('variação', '_var')],
                       legenda='US$ (escala log)')
    vmin, vmax = int(np.floor(d['log'].min())), int(np.ceil(d['log'].max()))
    vals = list(range(vmin, vmax + 1))
    rot = {3: 'mil', 4: '10 mil', 5: '100 mil', 6: '1 mi', 7: '10 mi', 8: '100 mi',
           9: '1 bi', 10: '10 bi'}
    fig.update_traces(colorbar=dict(tickvals=vals, ticktext=[rot.get(v, str(v)) for v in vals]))
    return fig


def _ranking(ano, fluxo, destaque=None):
    d = dc.municipios(ano, fluxo)
    d = d.assign(_txt=[f"{usd(v)} · {pct(p)}" for v, p in zip(d['valor'], d['part_pct'])])
    return viz.grafico(viz.fig_ranking(d, 'municipio', 'valor', fmt=usd, n=12,
                                       cor=COR_FLUXO[fluxo], destaque=destaque,
                                       hover_extra='_txt'))


def _detalhe(ano, fluxo, cod):
    if not cod:
        return viz.aviso("Clique em um município no mapa para ver os produtos e a "
                         "evolução mensal dele.")
    p = dc.municipio_produtos(ano, fluxo, cod)
    s = dc.municipio_serie(cod)
    filhos = []
    if not p.empty:
        p = p.assign(_txt=[f"{usd(v)} · {pct(q)}" for v, q in zip(p['valor_fob'], p['part_pct'])])
        filhos.append(viz.grafico(viz.fig_ranking(p, 'nome', 'valor_fob', fmt=usd, n=10,
                                                  cor=COR_FLUXO[fluxo], hover_extra='_txt')))
    else:
        filhos.append(viz.aviso(f"Sem {dc.NOME_FLUXO[fluxo]} registradas em {dc.rotulo(ano)}."))
    if not s.empty:
        fig = viz.fig_linhas([{'x': s['data'], 'y': s['export'], 'nome': 'exportações',
                               'cor': COR_FLUXO['export']},
                              {'x': s['data'], 'y': s['import'], 'nome': 'importações',
                               'cor': COR_FLUXO['import']}], altura=260, monetario='US$')
        filhos.append(viz.grafico(fig))
    return html.Div(filhos)


def layout():
    if not dc.disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Comércio Exterior", "Municípios"),
            viz.aviso("Os dados de comércio exterior ainda não foram gerados. "
                      "Rode o ETL:", "python -m etl.run_all"),
        ])
    ano, fluxo = dc.anos()[0], 'export'
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Comércio Exterior",
                       "Municípios · exportações e importações pelo domicílio da empresa · "
                       "US$ FOB",
                       dica="clique em um município no mapa para ver o detalhe",
                       botao_limpar='cxm-limpar'),
        dcc.Store(id='cxm-sel', data=None),
        viz.linha_filtros(
            viz.filtro("ANO:", viz.dropdown('cxm-ano', dc.opcoes_anos(), ano)),
            viz.filtro("FLUXO:", viz.dropdown('cxm-fluxo', dc.FLUXOS, fluxo)),
        ),
        html.Div(id='cxm-kpis', children=_kpis(ano, fluxo)),
        viz.secao("mapa", "valor por município · cores em escala logarítmica, porque "
                  "poucos municípios concentram quase todo o comércio",
                  dcc.Graph(id='cxm-mapa', figure=_mapa(ano, fluxo), config=viz.GRAPH_CONFIG)),
        viz.grade(
            viz.secao("ranking", "12 maiores municípios no período",
                      html.Div(id='cxm-ranking', children=_ranking(ano, fluxo))),
            viz.secao("município em detalhe", "principais produtos (SH4) e evolução mensal",
                      html.Div(id='cxm-detalhe', children=_detalhe(ano, fluxo, None))),
        ),
        viz.nota("Como ler: nesta aba o comércio é atribuído ao município onde a empresa "
                 "tem domicílio fiscal. Uma empresa com sede no Recife que exporta "
                 "produto feito no interior aparece no Recife. Por isso a soma dos "
                 "municípios difere do total da aba Balança comercial."),
        ui.footer(fonte_principal="Comex Stat · MDIC · dados por município",
                  atualizacao=viz.mes_ano(dc.ultima_data())),
    ])


def callbacks(app):

    @app.callback(Output('cxm-sel', 'data'),
                  Input('cxm-mapa', 'clickData'), Input('cxm-limpar', 'n_clicks'),
                  State('cxm-sel', 'data'), prevent_initial_call=True)
    def selecionar(click, _n, atual):
        if ctx.triggered_id == 'cxm-limpar':
            return None
        if click:
            try:
                cod = int(str(click['points'][0]['location']))
            except (KeyError, TypeError, ValueError):
                return no_update
            return None if cod == atual else cod
        return no_update

    @app.callback(Output('cxm-limpar', 'className'), Input('cxm-sel', 'data'))
    def botao(cod):
        return 'btn-link' if cod else 'btn-link hidden'

    @app.callback(Output('cxm-mapa', 'figure'),
                  Input('cxm-ano', 'value'), Input('cxm-fluxo', 'value'))
    def mapa(ano, fluxo):
        return _mapa(ano, fluxo) if (ano and fluxo) else no_update

    @app.callback(Output('cxm-kpis', 'children'), Output('cxm-ranking', 'children'),
                  Output('cxm-detalhe', 'children'),
                  Input('cxm-ano', 'value'), Input('cxm-fluxo', 'value'),
                  Input('cxm-sel', 'data'))
    def atualizar(ano, fluxo, cod):
        if not ano or not fluxo:
            return no_update, no_update, no_update
        destaque = nome_municipio(cod) if cod else None
        return _kpis(ano, fluxo, cod), _ranking(ano, fluxo, destaque), _detalhe(ano, fluxo, cod)
