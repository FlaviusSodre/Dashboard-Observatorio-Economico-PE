"""
tabs/atividade_economica_industria.py
=====================================
Sub-aba Indústria (Atividade Econômica): Pesquisa Industrial Mensal -
Produção Física (PIM-PF) do IBGE, Pernambuco x Brasil.

Estrutura:
1. KPIs da indústria geral de PE no último mês
2. Índice dessazonalizado (2022 = 100) ou variação em 12 meses, PE x Brasil
3. Ranking das atividades (12 meses, no ano ou mês contra mesmo mês)
4. Uma atividade em detalhe, PE x Brasil

Fonte: IBGE · PIM-PF Regional (SIDRA 8888).
"""

import plotly.graph_objects as go
from dash import Input, Output, html, no_update

from components import data_atividade as da, ui, viz
from components.viz import COR_REGIAO, CORES, pct

_MEDIDAS = [('12 meses', 'var_acum_12m'), ('no ano', 'var_acum_ano'),
            ('mês contra mesmo mês', 'var_interanual')]


def registrar():
    return {
        'eixo': 'Atividade Econômica',
        'sub': 'Indústria',
        'eixo_ordem': 4,
        'sub_ordem': 2,
        'ativa': True,
        'fonte_legenda': 'PIM-PF · IBGE',
    }


def _kpis():
    dt, _ = da.ultimo('pim', 'indice')
    itens = [('var_mensal_sa', 'vs mês anterior', 'com ajuste sazonal'),
             ('var_interanual', f'vs {viz.MESES[dt.month - 1]}/{dt.year - 1}' if dt else 'interanual',
              'mesmo mês do ano anterior'),
             ('var_acum_ano', 'acumulado no ano', 'vs mesmo período do ano anterior'),
             ('var_acum_12m', 'acumulado em 12 meses', 'vs 12 meses anteriores')]
    kpis = []
    for i, (med, label, sub) in enumerate(itens):
        _, v = da.ultimo('pim', med)
        _, br = da.ultimo('pim', med, 'Brasil')
        kpis.append(viz.kpi(label, pct(v, sinal=True),
                            (f"Brasil {pct(br, sinal=True)} · {sub}", 'neutro'),
                            destaque=(i == 3)))
    _, idx = da.ultimo('pim', 'indice_sa')
    kpis.append(viz.kpi(f"índice · {viz.mes_ano(dt)}", viz.num(idx, 1),
                        ("dessazonalizado · 2022 = 100", 'neutro')))
    return viz.faixa_kpis(kpis, contexto='Indústria geral · PE')


def _serie(visao: str, categoria: str = 'Indústria geral'):
    series = []
    for reg in ('Pernambuco', 'Brasil'):
        med = 'indice_sa' if visao == 'indice' else 'var_acum_12m'
        s = da.serie('pim', reg, categoria, med)
        if visao == 'indice' and s.empty:   # atividades sem ajuste sazonal
            s = da.serie('pim', reg, categoria, 'indice')
        s = s[s.index.year >= 2012]
        if s.empty:
            continue
        series.append({'x': s.index, 'y': s.values, 'nome': reg,
                       'cor': COR_REGIAO[reg], 'largura': 2.5 if reg == 'Pernambuco' else 2})
    if not series:
        return viz.grafico(viz.sem_dados_fig())
    if visao == 'indice':
        fig = viz.fig_linhas(series, altura=330, hover_fmt=',.1f')
    else:
        fig = viz.fig_linhas(series, altura=330, y_sufixo='%', linha_zero=True)
    return viz.grafico(fig)


def _ranking(medida: str):
    r = da.ranking_atividades('pim', medida)
    if r.empty:
        return viz.grafico(viz.sem_dados_fig())
    r = r.sort_values('pe')
    cores = [CORES['terracota'] if v < 0 else CORES['azul'] for v in r['pe']]
    fig = go.Figure(go.Bar(
        y=r['nome'], x=r['pe'], orientation='h', marker=dict(color=cores),
        text=[pct(v, sinal=True) for v in r['pe']], textposition='outside',
        cliponaxis=False, textfont=dict(size=10.5, color='#3A3A3A'),
        customdata=[pct(v, sinal=True) for v in r['br']],
        hovertemplate='<b>%{y}</b><br>Pernambuco: %{x:.1f}%<br>Brasil: '
                      '%{customdata}<extra></extra>',
    ))
    lim = max(abs(r['pe'].min()), abs(r['pe'].max())) * 1.35
    viz.layout_padrao(fig, altura=max(300, 28 * len(r) + 40), legenda=False,
                      hovermode='closest')
    fig.update_xaxes(range=[-lim, lim], ticksuffix='%', showgrid=True,
                     gridcolor='#E5E3DE', zeroline=True, zerolinecolor='#B8B8B8')
    fig.update_yaxes(showgrid=False, ticks='', automargin=True)
    return html.Div([viz.grafico(fig),
                     viz.nota(f"Último mês: {viz.mes_ano(r['data'].iloc[0])}. "
                              "Em vermelho, atividades em queda.")])


def layout():
    if not da.disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Atividade Econômica", "Indústria"),
            viz.aviso("Os dados da indústria ainda não foram gerados. Rode o ETL:",
                      "python -m etl.run_all"),
        ])
    dt = da.ultima_data('pim')
    cats = [c for c in da.categorias('pim') if c != 'Indústria geral']
    opcoes = [('Indústria geral', 'Indústria geral')] + [(da.curto(c), c) for c in cats]
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Atividade Econômica",
                       f"Indústria · produção física industrial · Pernambuco e Brasil "
                       f"· até {viz.mes_ano(dt)}"),
        _kpis(),
        viz.secao(
            "produção industrial",
            "indústria geral de Pernambuco e do Brasil",
            viz.botoes('ind-visao', [('índice dessazonalizado (2022 = 100)', 'indice'),
                                     ('variação em 12 meses', 'var')], 'indice'),
            html.Div(id='ind-serie', children=_serie('indice')),
        ),
        viz.grade(
            viz.secao(
                "atividades", "variação da produção por atividade em Pernambuco",
                viz.botoes('ind-rank-medida', _MEDIDAS, 'var_acum_12m'),
                html.Div(id='ind-ranking', children=_ranking('var_acum_12m')),
            ),
            viz.secao(
                "atividade em detalhe", "variação em 12 meses · Pernambuco x Brasil",
                viz.linha_filtros(viz.filtro("ATIVIDADE:", viz.dropdown(
                    'ind-ativ', opcoes, 'Indústria geral', busca=True), largo=True)),
                html.Div(id='ind-ativ-serie', children=_serie('var', 'Indústria geral')),
            ),
        ),
        viz.nota("Como ler: a PIM-PF mede o volume produzido pela indústria, sem "
                 "efeito de preços. Em Pernambuco o IBGE divulga a indústria de "
                 "transformação e 13 atividades; a indústria extrativa só aparece "
                 "no Brasil."),
        ui.footer(fonte_principal="IBGE · Pesquisa Industrial Mensal - Produção "
                                  "Física Regional (tabela SIDRA 8888)",
                  atualizacao=viz.mes_ano(dt)),
    ])


def callbacks(app):

    @app.callback(Output('ind-serie', 'children'), Input('ind-visao', 'value'))
    def serie(visao):
        return _serie(visao or 'indice')

    @app.callback(Output('ind-ranking', 'children'), Input('ind-rank-medida', 'value'))
    def ranking(medida):
        return _ranking(medida or 'var_acum_12m')

    @app.callback(Output('ind-ativ-serie', 'children'), Input('ind-ativ', 'value'))
    def atividade(cat):
        return _serie('var', cat) if cat else no_update
