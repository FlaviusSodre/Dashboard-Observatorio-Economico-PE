"""
tabs/comercio_exterior_agronegocio.py
=====================================
Sub-aba Agronegócio (Comércio Exterior): exportações do agronegócio de
Pernambuco, pela classificação de produtos do Agrostat (MAPA).

Estrutura:
1. KPIs: valor exportado, peso no total, principal setor, produto e destino
2. Setores do agronegócio e série anual (agro x demais)
3. Principais produtos e destinos
4. Sazonalidade: exportações mês a mês, um traço por ano

Fontes: Comex Stat · MDIC (valores) e Agrostat · MAPA (lista de NCMs do
agronegócio, em data/raw/agrostat_ncm_agronegocio.xlsx).
"""

from dash import Input, Output, html, no_update

from components import data_comex as dc, ui, viz
from components.viz import CORES, SERIES, pct, usd


def registrar():
    return {
        'eixo': 'Comércio Exterior',
        'sub': 'Agronegócio',
        'eixo_ordem': 5,
        'sub_ordem': 4,
        'ativa': True,
        'fonte_legenda': 'Comex Stat · Agrostat',
    }


def _kpis(ano):
    r = dc.agro_resumo(ano)
    m = dc.meses_no_ano(ano)
    ref = f"vs {viz.periodo_meses(1, m)}/{ano - 1}" if m < 12 else f"vs {ano - 1}"
    s = dc.agro_setores(ano)
    p = dc.agro_produtos(ano, 1)
    d = dc.agro_destinos(ano, 1)
    return viz.faixa_kpis([
        viz.kpi(f"exportações do agro · {r['rotulo']}", usd(r['valor']),
                viz.variacao(r['var_pct'], ref), destaque=True),
        viz.kpi("peso do agro", pct(r['part_pct']), ("das exportações de PE", 'neutro')),
        viz.kpi("principal setor", s.iloc[0]['agro_setor'] if len(s) else '—',
                (f"{usd(s.iloc[0]['valor'])} · {pct(s.iloc[0]['part_pct'])} do agro", 'neutro')
                if len(s) else None),
        viz.kpi("principal produto", p.iloc[0]['agro_produto'] if len(p) else '—',
                (usd(p.iloc[0]['valor']), 'neutro') if len(p) else None),
        viz.kpi("principal destino", d.iloc[0]['pais'] if len(d) else '—',
                (f"{pct(d.iloc[0]['part_pct'])} do agro", 'neutro') if len(d) else None),
    ], contexto='Pernambuco · agronegócio')


def _setores(ano):
    s = dc.agro_setores(ano)
    if s.empty:
        return viz.grafico(viz.sem_dados_fig())
    s = s.assign(_txt=[f"{usd(v)} · {pct(p)} · {pct(vv, sinal=True)} no período"
                       for v, p, vv in zip(s['valor'], s['part_pct'], s['var_pct'])])
    return viz.grafico(viz.fig_ranking(s, 'agro_setor', 'valor', fmt=usd, n=12,
                                       cor=CORES['verde'], hover_extra='_txt'))


def _anual():
    a = dc.agro_anual()
    x = [str(r.ano) if r.meses == 12 else f"{r.ano}*" for r in a.itertuples()]
    fig = viz.fig_barras_series(x, [{'y': a['agro'], 'nome': 'agronegócio', 'cor': CORES['verde']},
                                    {'y': a['demais'], 'nome': 'demais produtos',
                                     'cor': CORES['cinza_claro']}],
                                altura=320, empilhado=True, monetario='US$')
    return viz.grafico(fig)


def _produtos(ano):
    p = dc.agro_produtos(ano, 12)
    if p.empty:
        return viz.grafico(viz.sem_dados_fig())
    p = p.assign(_txt=[f"{usd(v)} · {pct(s)} do agro" for v, s in zip(p['valor'], p['part_pct'])])
    return viz.grafico(viz.fig_ranking(p, 'agro_produto', 'valor', fmt=usd, n=12,
                                       cor=CORES['verde'], hover_extra='_txt'))


def _destinos(ano):
    d = dc.agro_destinos(ano, 12)
    if d.empty:
        return viz.grafico(viz.sem_dados_fig())
    d = d.assign(_txt=[f"{usd(v)} · {pct(s)} do agro" for v, s in zip(d['valor_fob'], d['part_pct'])])
    return viz.grafico(viz.fig_ranking(d, 'pais', 'valor_fob', fmt=usd, n=12,
                                       cor=CORES['verde'], hover_extra='_txt'))


def _sazonalidade(setor):
    s = dc.agro_sazonalidade(setor if setor != '__todos__' else None)
    if s.empty:
        return viz.grafico(viz.sem_dados_fig())
    anos = sorted(s['ano'].unique())[-4:]
    tons = ['#CFE6D8', '#93C7A6', '#56A577', CORES['verde']]
    series = []
    for i, a in enumerate(anos):
        t = s[s['ano'] == a].set_index('mes')['valor_fob'].reindex(range(1, 13))
        series.append({'x': viz.MESES, 'y': t.tolist(), 'nome': str(a),
                       'cor': tons[i - len(anos)] if len(anos) < 4 else tons[i],
                       'largura': 2.5 if a == anos[-1] else 1.6,
                       'marcadores': a == anos[-1]})
    fig = viz.fig_linhas(series, altura=320, monetario='US$', x_hover='')
    return viz.grafico(fig)


def layout():
    if not dc.disponivel() or not dc.agro_disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Comércio Exterior", "Agronegócio"),
            viz.aviso("Faltam os dados do agronegócio. Confira se o arquivo "
                      "data/raw/agrostat_ncm_agronegocio.xlsx existe e rode o ETL:",
                      "python -m etl.run_all"),
        ])
    ano = dc.anos()[0]
    setores = dc.agro_setores(ano)['agro_setor'].tolist()
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Comércio Exterior",
                       "Agronegócio · exportações do agronegócio de Pernambuco · US$ FOB · "
                       "classificação Agrostat (MAPA)"),
        viz.linha_filtros(viz.filtro("ANO:", viz.dropdown('cxa-ano', dc.opcoes_anos(), ano))),
        html.Div(id='cxa-kpis', children=_kpis(ano)),
        viz.grade(
            viz.secao("setores", "exportações por setor do agronegócio no período",
                      html.Div(id='cxa-setores', children=_setores(ano))),
            viz.secao("série anual", "agronegócio e demais produtos · * ano incompleto",
                      _anual()),
        ),
        viz.grade(
            viz.secao("produtos", "12 maiores produtos do agronegócio",
                      html.Div(id='cxa-produtos', children=_produtos(ano))),
            viz.secao("destinos", "12 maiores países de destino do agronegócio",
                      html.Div(id='cxa-destinos', children=_destinos(ano))),
        ),
        viz.secao(
            "sazonalidade", "exportações do agronegócio mês a mês nos últimos anos",
            viz.linha_filtros(viz.filtro("SETOR:", viz.dropdown(
                'cxa-setor', [('Todos os setores', '__todos__')] + [(s, s) for s in setores],
                '__todos__', busca=True), largo=True)),
            html.Div(id='cxa-sazonal', children=_sazonalidade('__todos__')),
        ),
        viz.nota("Como ler: o agronegócio segue a lista de produtos (NCM) do Agrostat, "
                 "do Ministério da Agricultura. Para atualizar a lista, baixe de novo a "
                 "tabela de agrupamentos do Agrostat (passo a passo no README) e rode o ETL."),
        ui.footer(fonte_principal="Comex Stat · MDIC · Agrostat · MAPA",
                  atualizacao=viz.mes_ano(dc.ultima_data())),
    ])


def callbacks(app):

    @app.callback(Output('cxa-kpis', 'children'), Output('cxa-setores', 'children'),
                  Output('cxa-produtos', 'children'), Output('cxa-destinos', 'children'),
                  Input('cxa-ano', 'value'))
    def atualizar(ano):
        if not ano:
            return [no_update] * 4
        return _kpis(ano), _setores(ano), _produtos(ano), _destinos(ano)

    @app.callback(Output('cxa-sazonal', 'children'), Input('cxa-setor', 'value'))
    def sazonal(setor):
        return _sazonalidade(setor or '__todos__')
