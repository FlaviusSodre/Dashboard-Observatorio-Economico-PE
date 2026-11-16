"""
tabs/comercio_exterior.py
=========================
Sub-aba Balança comercial (Comércio Exterior): exportações, importações e
saldo de Pernambuco em US$ FOB, desde 2019.

Estrutura:
1. KPIs do ano escolhido: exportações, importações, saldo, corrente de
   comércio e participação no Nordeste
2. Série mensal (ou acumulada em 12 meses) de exportações e importações
3. Série anual e comparação com os estados do Nordeste

Fonte: Comex Stat · MDIC, ótica "UF do produto" (etl/comex_etl.py).
"""

import plotly.graph_objects as go
from dash import Input, Output, html, no_update

from components import data_comex as dc, ui, viz
from components.viz import COR_FLUXO, CORES, pct, usd


def registrar():
    return {
        'eixo': 'Comércio Exterior',
        'sub': 'Balança comercial',
        'eixo_ordem': 5,
        'sub_ordem': 1,
        'ativa': True,
        'fonte_legenda': 'Comex Stat · MDIC',
    }


def _ref(r):
    return (f"vs {viz.periodo_meses(1, r['meses'])}/{r['ano'] - 1}" if r['meses'] < 12
            else f"vs {r['ano'] - 1}")


def _kpis(ano: int):
    r = dc.resumo(ano)
    ref = _ref(r)
    saldo_txt = 'superávit' if r['saldo'] >= 0 else 'déficit'
    return viz.faixa_kpis([
        viz.kpi(f"exportações · {r['rotulo']}", usd(r['export']),
                viz.variacao(r['var_export'], ref), destaque=True),
        viz.kpi("importações", usd(r['import']), viz.variacao(r['var_import'], ref)),
        viz.kpi("saldo comercial", usd(r['saldo']),
                (f"{saldo_txt} · antes {usd(r['saldo_ant'])}", 'neutro')),
        viz.kpi("corrente de comércio", usd(r['corrente']),
                viz.variacao(r['var_corrente'], ref)),
        viz.kpi("peso no Nordeste", pct(r['part_ne_export']),
                (f"das exportações do NE · {pct(r['part_br_export'], 2)} do Brasil",
                 'neutro')),
    ], contexto='Pernambuco · US$ FOB')


def _serie(visao: str):
    m = dc.balanca_mensal('Pernambuco')
    sufixo = '_12m' if visao == '12m' else ''
    if visao == '12m':
        m = m.dropna(subset=['export_12m'])
    series = [{'x': m['data'], 'y': m[f'export{sufixo}'], 'nome': 'exportações',
               'cor': COR_FLUXO['export'], 'largura': 2.5},
              {'x': m['data'], 'y': m[f'import{sufixo}'], 'nome': 'importações',
               'cor': COR_FLUXO['import']}]
    fig = viz.fig_linhas(series, altura=330, monetario='US$')
    return viz.grafico(fig)


def _anual():
    a = dc.balanca_anual('Pernambuco')
    x = [str(r.ano) if r.meses == 12 else f"{r.ano}*" for r in a.itertuples()]
    series = [{'y': a['export'], 'nome': 'exportações', 'cor': COR_FLUXO['export']},
              {'y': a['import'], 'nome': 'importações', 'cor': COR_FLUXO['import']}]
    fig = viz.fig_barras_series(x, series, altura=320, monetario='US$')
    div, _ = viz.escala_monetaria(max(a['export'].max(), a['import'].max()))
    fig.add_trace(go.Scatter(x=x, y=a['saldo'] / div, name='saldo', mode='lines+markers',
                             line=dict(color=CORES['cinza'], width=2, dash='dot'),
                             marker=dict(size=7, color=CORES['cinza'],
                                         line=dict(color='#FFFFFF', width=1)),
                             customdata=[usd(v) for v in a['saldo']],
                             hovertemplate='saldo: %{customdata}<extra></extra>'))
    fig.add_hline(y=0, line=dict(color='#B8B8B8', width=1))
    return viz.grafico(fig)


def _nordeste(ano: int, fluxo: str):
    d = dc.ranking_nordeste(ano, fluxo)
    if d.empty:
        return viz.grafico(viz.sem_dados_fig())
    d = d.assign(_txt=[f"{usd(v)} · {pct(p)} do NE" for v, p in zip(d['valor'], d['part_pct'])])
    fig = viz.fig_ranking(d, 'uf', 'valor', fmt=usd, n=9, destaque='Pernambuco',
                          hover_extra='_txt')
    return viz.grafico(fig)


def layout():
    if not dc.disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Comércio Exterior", "Balança comercial"),
            viz.aviso("Os dados de comércio exterior ainda não foram gerados. "
                      "Rode o ETL:", "python -m etl.run_all"),
        ])
    anos = dc.anos()
    ano = anos[0]
    ult = dc.ultima_data()
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Comércio Exterior",
                       f"Balança comercial de Pernambuco · US$ FOB · {anos[-1]}—"
                       f"{viz.mes_ano(ult)}"),
        viz.linha_filtros(viz.filtro("ANO:", viz.dropdown('cx-ano', dc.opcoes_anos(), ano))),
        html.Div(id='cx-kpis', children=_kpis(ano)),
        viz.secao(
            "exportações e importações", "valores mensais ou acumulados em 12 meses",
            viz.botoes('cx-visao', [('mensal', 'mes'), ('acumulado em 12 meses', '12m')], 'mes'),
            html.Div(id='cx-serie', children=_serie('mes')),
        ),
        viz.grade(
            viz.secao("série anual", "exportações, importações e saldo · * ano incompleto",
                      _anual()),
            viz.secao(
                "Pernambuco no Nordeste", "valor no ano escolhido, estados do Nordeste",
                viz.botoes('cx-ne-fluxo', [('exportações', 'export'),
                                           ('importações', 'import')], 'export'),
                html.Div(id='cx-ne', children=_nordeste(ano, 'export')),
            ),
        ),
        viz.nota("Como ler: os valores estão em dólares (US$ FOB, sem frete e seguro) e "
                 "seguem a ótica \"UF do produto\" do Comex Stat: a exportação conta "
                 "para o estado onde a mercadoria foi produzida e a importação, para o "
                 "estado de destino. Num ano incompleto, a comparação usa os mesmos "
                 "meses do ano anterior."),
        ui.footer(fonte_principal="Comex Stat · Ministério do Desenvolvimento, "
                                  "Indústria, Comércio e Serviços (MDIC)",
                  atualizacao=viz.mes_ano(ult)),
    ])


def callbacks(app):

    @app.callback(Output('cx-kpis', 'children'), Input('cx-ano', 'value'))
    def kpis(ano):
        return _kpis(ano) if ano else no_update

    @app.callback(Output('cx-serie', 'children'), Input('cx-visao', 'value'))
    def serie(visao):
        return _serie(visao or 'mes')

    @app.callback(Output('cx-ne', 'children'),
                  Input('cx-ano', 'value'), Input('cx-ne-fluxo', 'value'))
    def nordeste(ano, fluxo):
        return _nordeste(ano, fluxo or 'export') if ano else no_update
