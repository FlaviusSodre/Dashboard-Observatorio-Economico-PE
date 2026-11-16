"""
tabs/comercio_exterior_produtos.py
==================================
Sub-aba Produtos e mercados (Comércio Exterior): o que Pernambuco vende e
compra, e de/para onde.

Estrutura:
1. KPIs: principal produto, principal mercado, concentração
2. Rankings de produtos (posição SH4) e de mercados (países)
3. Cruzamentos: mercados de um produto e produtos de um mercado
4. Evolução mensal do produto escolhido

Fonte: Comex Stat · MDIC (etl/comex_etl.py).
"""

from dash import Input, Output, html, no_update

from components import data_comex as dc, ui, viz
from components.viz import COR_FLUXO, pct, usd


def registrar():
    return {
        'eixo': 'Comércio Exterior',
        'sub': 'Produtos e mercados',
        'eixo_ordem': 5,
        'sub_ordem': 2,
        'ativa': True,
        'fonte_legenda': 'Comex Stat · MDIC',
    }


def _kpis(ano: int, fluxo: str):
    p = dc.produtos(ano, fluxo)
    m = dc.mercados(ano, fluxo)
    if p.empty or m.empty:
        return viz.faixa_kpis([viz.kpi("sem dados", "—")])
    top5 = p['part_pct'].head(5).sum()
    nome = dc.NOME_FLUXO[fluxo]
    p0, m0 = p.iloc[0], m.iloc[0]
    rot = dc.rotulo(ano)
    return viz.faixa_kpis([
        viz.kpi(f"{nome} · {rot}", usd(p['valor'].sum()), destaque=True),
        viz.kpi("principal produto", p0['nome'],
                (f"{usd(p0['valor'])} · {pct(p0['part_pct'])} do total", 'neutro')),
        viz.kpi("principal mercado" if fluxo == 'export' else "principal origem",
                m0['pais'], (f"{usd(m0['valor'])} · {pct(m0['part_pct'])} do total", 'neutro')),
        viz.kpi("concentração", pct(top5),
                ("do valor nos 5 maiores produtos", 'neutro')),
        viz.kpi("produtos e países", f"{len(p)} · {len(m)}",
                ("posições SH4 · países com comércio", 'neutro')),
    ], contexto=f"Pernambuco · {nome}")


def _ranking_produtos(ano: int, fluxo: str):
    p = dc.produtos(ano, fluxo, n=15)
    if p.empty:
        return viz.grafico(viz.sem_dados_fig())
    p = p.assign(_txt=[f"{usd(v)} · {pct(s)} · {pct(vv, sinal=True)} no período"
                       for v, s, vv in zip(p['valor'], p['part_pct'], p['var_pct'])])
    fig = viz.fig_ranking(p, 'nome', 'valor', fmt=usd, n=15, cor=COR_FLUXO[fluxo],
                          hover_extra='_txt')
    return viz.grafico(fig)


def _ranking_mercados(ano: int, fluxo: str):
    m = dc.mercados(ano, fluxo, n=15)
    if m.empty:
        return viz.grafico(viz.sem_dados_fig())
    m = m.assign(_txt=[f"{usd(v)} · {pct(s)} · {pct(vv, sinal=True)} no período"
                       for v, s, vv in zip(m['valor'], m['part_pct'], m['var_pct'])])
    fig = viz.fig_ranking(m, 'pais', 'valor', fmt=usd, n=15, cor=COR_FLUXO[fluxo],
                          hover_extra='_txt')
    return viz.grafico(fig)


def _opcoes_produtos(ano, fluxo):
    p = dc.produtos(ano, fluxo, n=40)
    return [(f"{r.sh4} · {r.nome}", r.sh4) for r in p.itertuples()]


def _opcoes_mercados(ano, fluxo):
    m = dc.mercados(ano, fluxo, n=40)
    return [(r.pais, r.pais) for r in m.itertuples()]


def _cruz_produto(ano, fluxo, sh4):
    d = dc.produto_mercados(ano, fluxo, sh4)
    if d.empty:
        return viz.grafico(viz.sem_dados_fig())
    d = d.assign(_txt=[f"{usd(v)} · {pct(s)}" for v, s in zip(d['valor_fob'], d['part_pct'])])
    return viz.grafico(viz.fig_ranking(d, 'pais', 'valor_fob', fmt=usd, n=12,
                                       cor=COR_FLUXO[fluxo], hover_extra='_txt'))


def _cruz_mercado(ano, fluxo, pais):
    d = dc.mercado_produtos(ano, fluxo, pais)
    if d.empty:
        return viz.grafico(viz.sem_dados_fig())
    d = d.assign(_txt=[f"{usd(v)} · {pct(s)}" for v, s in zip(d['valor_fob'], d['part_pct'])])
    return viz.grafico(viz.fig_ranking(d, 'nome', 'valor_fob', fmt=usd, n=12,
                                       cor=COR_FLUXO[fluxo], hover_extra='_txt'))


def _serie_produto(fluxo, sh4):
    s = dc.serie_produto(fluxo, sh4)
    if s.empty:
        return viz.grafico(viz.sem_dados_fig())
    fig = viz.fig_linhas([{'x': s.index, 'y': s.values, 'nome': dc.NOME_FLUXO[fluxo],
                           'cor': COR_FLUXO[fluxo], 'marcadores': len(s) < 40}],
                         altura=280, monetario='US$')
    return viz.grafico(fig)


def layout():
    if not dc.disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Comércio Exterior", "Produtos e mercados"),
            viz.aviso("Os dados de comércio exterior ainda não foram gerados. "
                      "Rode o ETL:", "python -m etl.run_all"),
        ])
    ano = dc.anos()[0]
    fluxo = 'export'
    ops_p = _opcoes_produtos(ano, fluxo)
    ops_m = _opcoes_mercados(ano, fluxo)
    p0 = ops_p[0][1] if ops_p else None
    m0 = ops_m[0][1] if ops_m else None
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Comércio Exterior",
                       "Produtos e mercados · o que Pernambuco vende e compra, e de onde · "
                       "US$ FOB"),
        viz.linha_filtros(
            viz.filtro("ANO:", viz.dropdown('cxp-ano', dc.opcoes_anos(), ano)),
            viz.filtro("FLUXO:", viz.dropdown('cxp-fluxo', dc.FLUXOS, fluxo)),
        ),
        html.Div(id='cxp-kpis', children=_kpis(ano, fluxo)),
        viz.grade(
            viz.secao("produtos", "15 maiores posições do Sistema Harmonizado (SH4)",
                      html.Div(id='cxp-produtos', children=_ranking_produtos(ano, fluxo))),
            viz.secao("mercados", "15 maiores países de destino ou de origem",
                      html.Div(id='cxp-mercados', children=_ranking_mercados(ano, fluxo))),
        ),
        viz.grade(
            viz.secao("para onde vai um produto", "países do produto escolhido",
                      viz.linha_filtros(viz.filtro("PRODUTO:", viz.dropdown(
                          'cxp-prod', ops_p, p0, busca=True), largo=True)),
                      html.Div(id='cxp-prod-paises', children=_cruz_produto(ano, fluxo, p0))),
            viz.secao("o que vai para um país", "produtos do país escolhido",
                      viz.linha_filtros(viz.filtro("PAÍS:", viz.dropdown(
                          'cxp-pais', ops_m, m0, busca=True), largo=True)),
                      html.Div(id='cxp-pais-prods', children=_cruz_mercado(ano, fluxo, m0))),
        ),
        viz.secao("evolução do produto escolhido", "valor mensal desde 2019",
                  html.Div(id='cxp-prod-serie', children=_serie_produto(fluxo, p0))),
        viz.nota("Como ler: os produtos estão agrupados pela posição de 4 dígitos do "
                 "Sistema Harmonizado (SH4). Os cruzamentos produto x país usam o ano "
                 "inteiro (ou os meses disponíveis no ano em curso)."),
        ui.footer(fonte_principal="Comex Stat · MDIC",
                  atualizacao=viz.mes_ano(dc.ultima_data())),
    ])


def callbacks(app):

    @app.callback(
        Output('cxp-kpis', 'children'), Output('cxp-produtos', 'children'),
        Output('cxp-mercados', 'children'),
        Output('cxp-prod', 'options'), Output('cxp-prod', 'value'),
        Output('cxp-pais', 'options'), Output('cxp-pais', 'value'),
        Input('cxp-ano', 'value'), Input('cxp-fluxo', 'value'),
    )
    def atualizar(ano, fluxo):
        if not ano or not fluxo:
            return [no_update] * 7
        ops_p = _opcoes_produtos(ano, fluxo)
        ops_m = _opcoes_mercados(ano, fluxo)
        return (_kpis(ano, fluxo), _ranking_produtos(ano, fluxo),
                _ranking_mercados(ano, fluxo),
                [{'label': a, 'value': b} for a, b in ops_p],
                ops_p[0][1] if ops_p else None,
                [{'label': a, 'value': b} for a, b in ops_m],
                ops_m[0][1] if ops_m else None)

    @app.callback(Output('cxp-prod-paises', 'children'), Output('cxp-prod-serie', 'children'),
                  Input('cxp-prod', 'value'), Input('cxp-ano', 'value'),
                  Input('cxp-fluxo', 'value'))
    def produto(sh4, ano, fluxo):
        if not sh4 or not ano or not fluxo:
            return no_update, no_update
        return _cruz_produto(ano, fluxo, sh4), _serie_produto(fluxo, sh4)

    @app.callback(Output('cxp-pais-prods', 'children'),
                  Input('cxp-pais', 'value'), Input('cxp-ano', 'value'),
                  Input('cxp-fluxo', 'value'))
    def pais(p, ano, fluxo):
        if not p or not ano or not fluxo:
            return no_update
        return _cruz_mercado(ano, fluxo, p)
