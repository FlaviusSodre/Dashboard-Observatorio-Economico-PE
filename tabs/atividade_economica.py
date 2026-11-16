"""
tabs/atividade_economica.py
===========================
Sub-aba Visão geral (Atividade Econômica): o termômetro da economia de
Pernambuco.

Estrutura:
1. KPIs: IBC-R, PIB trimestral, indústria, varejo e serviços
2. IBC-R: Pernambuco x Nordeste x Brasil (índice ou variação em 12 meses)
3. PIB trimestral (CONDEPE/FIDEM) e termômetro setorial (12 meses)
4. Inflação: IPCA da RM do Recife x Brasil, geral e por grupo

Fontes: BCB (IBC-R), Agência CONDEPE/FIDEM via SEPLAG-PE (PIB trimestral),
IBGE (PIM-PF, PMC, PMS, IPCA). Ver etl/atividade_etl.py.
"""

import plotly.graph_objects as go
from dash import Input, Output, dcc, html, no_update

from components import data_atividade as da, ui, viz
from components.viz import COR_REGIAO, CORES, pct


def registrar():
    return {
        'eixo': 'Atividade Econômica',
        'sub': 'Visão geral',
        'eixo_ordem': 4,
        'sub_ordem': 1,
        'ativa': True,
        'fonte_legenda': 'BCB · IBGE · SEPLAG-PE',
    }


# ============================================================================
# KPIs
# ============================================================================

def _kpi_12m(fonte: str, label: str):
    dt, v = da.ultimo(fonte, 'var_acum_12m')
    if dt is None:
        return viz.kpi(label, '—')
    _, br = da.ultimo(fonte, 'var_acum_12m', 'Brasil')
    return viz.kpi(f"{label} · 12 meses", pct(v, sinal=True),
                   (f"até {viz.mes_ano(dt)} · Brasil {pct(br, sinal=True)}", 'neutro'))


def _kpis():
    pib = da.pib_ultimo()
    if pib:
        k_pib = viz.kpi(f"PIB · {pib['rotulo']}", pct(pib['var_interanual'], sinal=True),
                        (f"vs mesmo trimestre de {pib['ano'] - 1} · Brasil "
                         f"{pct(pib.get('br_interanual'), sinal=True)}", 'neutro'))
    else:
        k_pib = viz.kpi("PIB trimestral", '—', ("planilha não encontrada", 'neutro'))
    dt, v = da.ultimo('ibcr', 'var_acum_12m')
    _, br = da.ultimo('ibcr', 'var_acum_12m', 'Brasil')
    k_ibc = viz.kpi("IBC-R · 12 meses", pct(v, sinal=True),
                    (f"até {viz.mes_ano(dt)} · IBC-Br {pct(br, sinal=True)}", 'neutro'),
                    destaque=True)
    return viz.faixa_kpis([
        k_ibc, k_pib,
        _kpi_12m('pim', 'indústria'),
        _kpi_12m('pmc_varejo', 'varejo'),
        _kpi_12m('pms', 'serviços'),
    ], contexto='Pernambuco')


# ============================================================================
# Gráficos
# ============================================================================

def _ibcr(visao: str):
    series = []
    for reg in ('Pernambuco', 'Nordeste', 'Brasil'):
        if visao == 'indice':
            s = da.indice_base('ibcr', reg, 2019)
        else:
            s = da.serie('ibcr', reg, None, 'var_acum_12m')
        s = s[s.index.year >= 2012]
        series.append({'x': s.index, 'y': s.values, 'nome': reg,
                       'cor': COR_REGIAO[reg], 'largura': 2.5 if reg == 'Pernambuco' else 2})
    if visao == 'indice':
        fig = viz.fig_linhas(series, altura=340, hover_fmt=',.1f')
        fig.add_hline(y=100, line=dict(color='#B8B8B8', width=1, dash='dot'))
    else:
        fig = viz.fig_linhas(series, altura=340, y_sufixo='%', hover_fmt=',.1f',
                             linha_zero=True)
    return viz.grafico(fig)


def _pib(medida: str):
    d = da.pib_trimestral()
    if d.empty:
        return viz.aviso("Preencha data/raw/pib_trimestral_pe.csv e rode o ETL.")
    rotulos = d[d['regiao'] == 'Pernambuco'].sort_values('data')['rotulo'].tolist()
    series = []
    for reg in ('Pernambuco', 'Brasil'):
        s = d[d['regiao'] == reg].set_index('rotulo')[medida].reindex(rotulos)
        series.append({'y': s.tolist(), 'nome': reg, 'cor': COR_REGIAO[reg]})
    fig = viz.fig_barras_series(rotulos, series, altura=320, y_sufixo='%',
                                hover_fmt=',.1f')
    fig.add_hline(y=0, line=dict(color='#B8B8B8', width=1))
    return viz.grafico(fig)


def _termometro():
    t = da.termometro()
    if t.empty:
        return viz.grafico(viz.sem_dados_fig())
    t = t.iloc[::-1]
    fig = go.Figure()
    for col, nome, cor in (('br', 'Brasil', COR_REGIAO['Brasil']),
                           ('pe', 'Pernambuco', COR_REGIAO['Pernambuco'])):
        fig.add_trace(go.Bar(
            y=t['indicador'], x=t[col], name=nome, orientation='h',
            marker=dict(color=cor), text=[pct(v, sinal=True) for v in t[col]],
            textposition='outside', cliponaxis=False,
            textfont=dict(size=10, color='#3A3A3A'),
            customdata=[viz.mes_ano(d) for d in t['data']],
            hovertemplate=f'{nome}: %{{x:.1f}}% · até %{{customdata}}<extra></extra>',
        ))
    viz.layout_padrao(fig, altura=320, legenda=True, hovermode='closest')
    fig.update_layout(barmode='group', bargap=0.3, legend_traceorder='reversed')
    vals = [v for v in list(t['pe']) + list(t['br']) if v is not None and v == v]
    vmin, vmax = min(vals + [0]), max(vals + [0])
    folga = (vmax - vmin) * 0.22 or 1
    fig.update_xaxes(ticksuffix='%', showgrid=True, gridcolor='#E5E3DE',
                     zeroline=True, zerolinecolor='#B8B8B8',
                     range=[vmin - folga if vmin < 0 else 0, vmax + folga])
    fig.update_yaxes(showgrid=False, ticks='', automargin=True)
    return viz.grafico(fig)


def _ipca_linhas():
    series = []
    for reg in ('RM Recife', 'Brasil'):
        s = da.serie('ipca', reg, 'Índice geral', 'var_acum_12m')
        s = s[s.index.year >= 2020]
        series.append({'x': s.index, 'y': s.values, 'nome': reg,
                       'cor': COR_REGIAO[reg]})
    fig = viz.fig_linhas(series, altura=300, y_sufixo='%', hover_fmt=',.2f')
    return viz.grafico(fig)


def _ipca_grupos():
    g = da.ipca_grupos()
    if g.empty or 'RM Recife' not in g:
        return viz.grafico(viz.sem_dados_fig())
    g = g[g['categoria'] != 'Índice geral'].sort_values('RM Recife')
    fig = go.Figure()
    for reg in ('Brasil', 'RM Recife'):
        fig.add_trace(go.Bar(
            y=g['categoria'], x=g[reg], name=reg, orientation='h',
            marker=dict(color=COR_REGIAO[reg]),
            hovertemplate=f'{reg}: %{{x:.2f}}%<extra></extra>',
        ))
    viz.layout_padrao(fig, altura=360, legenda=True, hovermode='y unified')
    fig.update_layout(barmode='group', bargap=0.3, legend_traceorder='reversed')
    fig.update_xaxes(ticksuffix='%', showgrid=True, gridcolor='#E5E3DE')
    fig.update_yaxes(showgrid=False, ticks='', automargin=True)
    return viz.grafico(fig)


# ============================================================================
# Layout
# ============================================================================

def layout():
    if not da.disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Atividade Econômica", "Visão geral"),
            viz.aviso("Os indicadores de atividade ainda não foram gerados. "
                      "Rode o ETL:", "python -m etl.run_all"),
        ])
    dt_ibc = da.ultima_data('ibcr')
    dt_ipca = da.ultima_data('ipca')
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba(
            "Atividade Econômica",
            "Visão geral · IBC-R · PIB trimestral · indústria · comércio · "
            f"serviços · inflação · dados até {viz.mes_ano(dt_ibc)}"),

        _kpis(),

        viz.secao(
            "IBC-R · atividade econômica mensal",
            "Índice de Atividade Econômica Regional do Banco Central, uma "
            "prévia mensal do PIB · Pernambuco, Nordeste e Brasil",
            viz.botoes('ativ-ibcr-visao', [('índice (2019 = 100)', 'indice'),
                                           ('variação em 12 meses', 'var')], 'indice'),
            html.Div(id='ativ-ibcr', children=_ibcr('indice')),
        ),

        viz.grade(
            viz.secao(
                "PIB trimestral",
                "variação do PIB em volume · Pernambuco (CONDEPE/FIDEM) e Brasil (IBGE)",
                viz.botoes('ativ-pib-medida', [('vs mesmo trimestre', 'var_interanual'),
                                               ('acumulado em 4 trimestres', 'var_acum_4t'),
                                               ('acumulado no ano', 'var_acum_ano')],
                           'var_interanual'),
                html.Div(id='ativ-pib', children=_pib('var_interanual')),
            ),
            viz.secao(
                "termômetro setorial",
                "variação acumulada em 12 meses no último mês disponível · "
                "volume, sem efeito de preços",
                _termometro(),
            ),
        ),

        viz.grade(
            viz.secao(
                "inflação",
                f"IPCA acumulado em 12 meses · RM do Recife x Brasil · até "
                f"{viz.mes_ano(dt_ipca)}",
                _ipca_linhas(),
            ),
            viz.secao(
                "inflação por grupo",
                "IPCA acumulado em 12 meses no último mês, por grupo de despesa",
                _ipca_grupos(),
            ),
        ),

        viz.nota("Como ler: IBC-R e IBC-Br são índices do Banco Central que "
                 "antecipam o PIB mês a mês; o índice está dessazonalizado e "
                 "rebaseado para a média de 2019 = 100. O PIB trimestral de "
                 "Pernambuco é calculado pela Agência CONDEPE/FIDEM e é mantido "
                 "no painel a partir de uma planilha (data/raw/pib_trimestral_pe.csv). "
                 "Indústria, varejo e serviços medem volume (descontada a inflação)."),

        ui.footer(
            fonte_principal="Banco Central (IBC-R) · Agência CONDEPE/FIDEM e "
                            "SEPLAG-PE (PIB trimestral) · IBGE (PIM-PF, PMC, PMS, IPCA)",
            atualizacao=viz.mes_ano(dt_ibc),
        ),
    ])


def callbacks(app):

    @app.callback(Output('ativ-ibcr', 'children'), Input('ativ-ibcr-visao', 'value'))
    def ibcr(visao):
        return _ibcr(visao or 'indice')

    @app.callback(Output('ativ-pib', 'children'), Input('ativ-pib-medida', 'value'))
    def pib(medida):
        return _pib(medida or 'var_interanual') if medida else no_update
