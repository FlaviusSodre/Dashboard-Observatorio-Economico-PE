"""
tabs/atividade_economica_comercio_servicos.py
=============================================
Sub-aba Comércio e serviços (Atividade Econômica): Pesquisa Mensal de
Comércio (PMC) e Pesquisa Mensal de Serviços (PMS) do IBGE.

Estrutura:
1. KPIs (12 meses): varejo, varejo ampliado, serviços e turismo
2. Série escolhida: índice dessazonalizado ou variação em 12 meses, PE x BR
3. Varejo por atividade e serviços por atividade (rankings)

Fonte: IBGE · PMC (SIDRA 8880, 8881, 8882) e PMS (5906, 8693, 8694).
"""

import plotly.graph_objects as go
from dash import Input, Output, html

from components import data_atividade as da, ui, viz
from components.viz import COR_REGIAO, CORES, pct

_INDICADORES = [('Varejo', 'pmc_varejo'), ('Varejo ampliado', 'pmc_ampliado'),
                ('Serviços', 'pms'), ('Turismo', 'pms_turismo')]


def registrar():
    return {
        'eixo': 'Atividade Econômica',
        'sub': 'Comércio e serviços',
        'eixo_ordem': 4,
        'sub_ordem': 3,
        'ativa': True,
        'fonte_legenda': 'PMC · PMS · IBGE',
    }


def _kpis():
    kpis = []
    for i, (nome, fonte) in enumerate(_INDICADORES):
        dt, v = da.ultimo(fonte, 'var_acum_12m')
        _, br = da.ultimo(fonte, 'var_acum_12m', 'Brasil')
        _, ia = da.ultimo(fonte, 'var_interanual')
        kpis.append(viz.kpi(f"{nome} · 12 meses", pct(v, sinal=True),
                            (f"Brasil {pct(br, sinal=True)} · {viz.mes_ano(dt)}: "
                             f"{pct(ia, sinal=True)} no mês", 'neutro'),
                            destaque=(i == 0)))
    return viz.faixa_kpis(kpis, contexto='Pernambuco · volume')


def _serie(fonte: str, visao: str):
    series = []
    for reg in ('Pernambuco', 'Brasil'):
        if visao == 'indice':
            s = da.serie(fonte, reg, None, 'indice_sa', 'volume')
        else:
            s = da.serie(fonte, reg, None, 'var_acum_12m', 'volume')
        s = s[s.index.year >= 2012]
        if s.empty:
            continue
        series.append({'x': s.index, 'y': s.values, 'nome': reg,
                       'cor': COR_REGIAO[reg], 'largura': 2.5 if reg == 'Pernambuco' else 2})
    if not series:
        return viz.grafico(viz.sem_dados_fig())
    if visao == 'indice':
        return viz.grafico(viz.fig_linhas(series, altura=320, hover_fmt=',.1f'))
    return viz.grafico(viz.fig_linhas(series, altura=320, y_sufixo='%', linha_zero=True))


def _ranking(fonte: str, com_brasil: bool = True):
    r = da.ranking_atividades(fonte, 'var_acum_12m')
    if r.empty:
        return viz.grafico(viz.sem_dados_fig())
    r = r.sort_values('pe')
    cores = [CORES['terracota'] if v < 0 else CORES['azul'] for v in r['pe']]
    br_txt = [pct(v, sinal=True) for v in r['br']] if com_brasil else ['—'] * len(r)
    fig = go.Figure(go.Bar(
        y=r['nome'], x=r['pe'], orientation='h', marker=dict(color=cores),
        text=[pct(v, sinal=True) for v in r['pe']], textposition='outside',
        cliponaxis=False, textfont=dict(size=10.5, color='#3A3A3A'),
        customdata=br_txt,
        hovertemplate=('<b>%{y}</b><br>Pernambuco: %{x:.1f}%'
                       + ('<br>Brasil: %{customdata}' if com_brasil else '')
                       + '<extra></extra>'),
    ))
    lim = max(abs(r['pe'].min()), abs(r['pe'].max()), 1) * 1.4
    viz.layout_padrao(fig, altura=max(240, 30 * len(r) + 40), legenda=False,
                      hovermode='closest')
    fig.update_xaxes(range=[-lim, lim], ticksuffix='%', showgrid=True,
                     gridcolor='#E5E3DE', zeroline=True, zerolinecolor='#B8B8B8')
    fig.update_yaxes(showgrid=False, ticks='', automargin=True)
    return html.Div([viz.grafico(fig),
                     viz.nota(f"Variação acumulada em 12 meses até "
                              f"{viz.mes_ano(r['data'].iloc[0])}, em volume.")])


def layout():
    if not da.disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Atividade Econômica", "Comércio e serviços"),
            viz.aviso("Os dados de comércio e serviços ainda não foram gerados. "
                      "Rode o ETL:", "python -m etl.run_all"),
        ])
    dt = da.ultima_data('pmc_varejo')
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Atividade Econômica",
                       f"Comércio e serviços · vendas no varejo, serviços e turismo "
                       f"· Pernambuco e Brasil · até {viz.mes_ano(dt)}"),
        _kpis(),
        viz.secao(
            "evolução", "volume de vendas ou de serviços · Pernambuco x Brasil",
            viz.linha_filtros(
                viz.filtro("INDICADOR:", viz.dropdown('cs-ind', _INDICADORES, 'pmc_varejo')),
            ),
            viz.botoes('cs-visao', [('índice dessazonalizado (2022 = 100)', 'indice'),
                                    ('variação em 12 meses', 'var')], 'var'),
            html.Div(id='cs-serie', children=_serie('pmc_varejo', 'var')),
        ),
        viz.grade(
            viz.secao("varejo por atividade", "volume de vendas em Pernambuco",
                      _ranking('pmc_atividades')),
            viz.secao("serviços por atividade", "volume de serviços em Pernambuco",
                      _ranking('pms_atividades', com_brasil=False)),
        ),
        viz.nota("Como ler: o varejo ampliado soma ao varejo os veículos e peças, "
                 "o material de construção e o atacado de alimentos. Turismo reúne "
                 "alojamento, alimentação fora de casa, transporte de passageiros, "
                 "agências e locação de veículos. Todas as séries em volume, "
                 "descontada a inflação."),
        ui.footer(fonte_principal="IBGE · Pesquisa Mensal de Comércio e Pesquisa "
                                  "Mensal de Serviços (tabelas SIDRA 8880, 8881, 8882, "
                                  "5906, 8693 e 8694)",
                  atualizacao=viz.mes_ano(dt)),
    ])


def callbacks(app):

    @app.callback(Output('cs-serie', 'children'),
                  Input('cs-ind', 'value'), Input('cs-visao', 'value'))
    def serie(fonte, visao):
        return _serie(fonte or 'pmc_varejo', visao or 'var')
