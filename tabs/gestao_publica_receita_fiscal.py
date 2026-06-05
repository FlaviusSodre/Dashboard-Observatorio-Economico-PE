"""
tabs/gestao_publica_receita_fiscal.py
======================================
Sub-aba Receita Fiscal (Gestão Pública) — transferências fiscais da STN
para os municípios de Pernambuco.

Itens considerados: FPM, ITR, FPE, ICMS, IPI-EXP, IPVA, ITCMD, FEP.
Total mensal = soma dos 3 decêndios; total anual = soma dos meses.

Estrutura (espelho de indices_socioeconomicos.py):
1. KPIs reativos (estadual ou municipal ao clicar no mapa)
2. Mapa coroplético por total de transferências (filtro de ano)
3. Rankings: top 10 municípios + ranking 12 RDs
4. Evolução temporal: total PE por ano, uma linha por tipo de transferência
5. Composição de transferências: donut por tipo + ranking de municípios da RD

Fonte: STN · Tesouro Nacional (via FPMfinalPE.parquet).
"""

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, State, dcc, html, no_update, ctx

from components import data, ui, charts
from config import PALETTE, SEMANTIC, CHART_FONT


def registrar():
    return {
        'eixo': 'Gestão Pública',
        'sub': 'Receita Fiscal',
        'eixo_ordem': 3,
        'sub_ordem': 2,
        'ativa': True,
        'fonte_legenda': 'STN · Tesouro Nacional',
    }


# ============================================================================
# Paleta de cores por tipo de transferência
# ============================================================================

ITEM_CORES = {
    'FPM':     SEMANTIC['destaque'],
    'FPE':     PALETTE['terracota'],
    'ICMS':    PALETTE['verde_salvia'],
    'ITR':     PALETTE['lilas_acinzentado'],
    'IPI-EXP': PALETTE['mostarda_suave'],
    'IPVA':    PALETTE['azul_empoeirado'],
    'ITCMD':   PALETTE['bege_quente'],
    'FEP':     PALETTE['rosa_empoeirado'],
}

_ITENS_ORDEM = ['FPM', 'FPE', 'ICMS', 'IPVA', 'ITR', 'IPI-EXP', 'ITCMD', 'FEP']


# ============================================================================
# Helpers de formatação
# ============================================================================

def _fmt_brl(v):
    if v is None or pd.isna(v):
        return "—"
    abs_v = abs(v)
    if abs_v >= 1e9:
        s = f"R$ {v/1e9:.2f} bi"
    elif abs_v >= 1e6:
        s = f"R$ {v/1e6:.1f} mi"
    elif abs_v >= 1e3:
        s = f"R$ {v/1e3:.0f} mil"
    else:
        s = f"R$ {v:.2f}"
    return s.replace('.', ',')


def _fmt_pct(v, casas=1):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.{casas}f}%".replace('.', ',')


def _ordinal(n):
    return f"{n}º"


# ============================================================================
# KPIs
# ============================================================================

def _kpis_estaduais(ano: int):
    k = data.fpm_kpis_estaduais(ano)

    cresc_str = None
    if k['cresc_pct'] is not None:
        seta = '▲' if k['cresc_pct'] > 0 else '▼' if k['cresc_pct'] < 0 else '—'
        cor = 'positivo' if k['cresc_pct'] > 0 else 'negativo'
        cresc_str = (f"{seta} {abs(k['cresc_pct']):.1f}% vs ano anterior".replace('.', ','), cor)

    return html.Div(className="kpi-faixa kpi-faixa-cinco", children=[
        html.Div(className="kpi-contexto-tag", children="Pernambuco"),
        ui.kpi_simples(
            label=f"transferências · {ano}",
            valor=_fmt_brl(k['total']),
            sub=cresc_str,
            accent=SEMANTIC['destaque'],
        ),
        ui.kpi_simples(
            label="maior receptor",
            valor=k['top_municipio'],
            sub=(f"{_fmt_brl(k['top_municipio_total'])} "
                 f"({_fmt_pct(k['top_municipio_pct'])} do estado)",
                 "neutro"),
        ),
        ui.kpi_simples(
            label="tipo com maior volume",
            valor=k['tipo_maior'],
            sub=("maior transferência do estado", "neutro"),
        ),
        ui.kpi_simples(
            label="tipos de transferência",
            valor=str(k['n_itens']),
            sub=("FPM · FPE · ICMS · IPVA · outros", "neutro"),
        ),
        ui.kpi_simples(
            label="municípios cobertos",
            valor="184",
            sub=("municípios com dados de transferência", "neutro"),
        ),
    ])


def _kpis_municipal(cod_ibge_6: int, ano: int):
    d = data.fpm_municipio_detalhe(cod_ibge_6, ano)
    if d is None:
        return _kpis_estaduais(ano)

    rank_est = _ordinal(d['rank_estadual'])
    rank_rd  = _ordinal(d['rank_na_rd'])

    tipo_maior = max(d['composicao'], key=d['composicao'].get) if d['composicao'] else "—"
    v_tipo_maior = d['composicao'].get(tipo_maior, 0)

    return html.Div(className="kpi-faixa kpi-faixa-cinco", children=[
        html.Div(className="kpi-contexto-tag", children=d['municipio']),
        ui.kpi_simples(
            label=f"transferências · {ano}",
            valor=_fmt_brl(d['total']),
            sub=(f"{rank_est} de {d['n_municipios_estado']} no estado", "neutro"),
            accent=SEMANTIC['destaque'],
        ),
        ui.kpi_simples(
            label="participação na RD",
            valor=_fmt_pct(d['pct_na_rd']),
            sub=(f"{rank_rd} de {d['n_municipios_rd']} na RD", "neutro"),
        ),
        ui.kpi_simples(
            label="participação no estado",
            valor=_fmt_pct(d['pct_no_estado'], 3),
            sub=("do total de transferências PE", "neutro"),
        ),
        ui.kpi_simples(
            label="principal transferência",
            valor=tipo_maior,
            sub=(_fmt_brl(v_tipo_maior), "neutro"),
        ),
        ui.kpi_simples(
            label="região de desenvolvimento",
            valor=d['regiao_desenvolvimento'],
            sub=("RD de Pernambuco", "neutro"),
        ),
    ])


def _construir_kpis(ano: int, cod_ibge_6: int = None):
    if cod_ibge_6:
        return _kpis_municipal(cod_ibge_6, ano)
    return _kpis_estaduais(ano)


# ============================================================================
# Mapa
# ============================================================================

def _construir_mapa_figura(ano: int):
    df = data.fpm_municipal_ano(ano).copy()
    df['regiao_desenvolvimento'] = df['regiao_desenvolvimento'].fillna('—')
    geo = data.geojson_municipios()

    df['_total_str']  = df['total'].apply(_fmt_brl)
    df['_total_rd']   = df.groupby('regiao_desenvolvimento')['total'].transform('sum')
    df['_total_rd_str'] = df['_total_rd'].apply(_fmt_brl)
    df['_pct_rd']     = df['pct_na_rd'].apply(lambda v: _fmt_pct(v, 2))
    df['_pct_est']    = df['pct_no_estado'].apply(lambda v: _fmt_pct(v, 3))

    hovertemplate = (
        '<b>%{text}</b><br>'
        '<i>RD %{customdata[0]}</i><br>'
        '────────<br>'
        'Transferências: %{customdata[1]}<br>'
        'Total da RD: %{customdata[2]}<br>'
        '%{customdata[3]} do total da RD<br>'
        '%{customdata[4]} do total do estado'
    )

    return charts.mapa_municipios_pe(
        df=df,
        geojson=geo,
        valor_col='total',
        hovertemplate=hovertemplate,
        customdata_cols=['regiao_desenvolvimento', '_total_str',
                         '_total_rd_str', '_pct_rd', '_pct_est'],
        altura=480,
        titulo_legenda='Transferências (R$)',
    )


def _construir_mapa(ano: int):
    from config import GEO_MUNICIPIOS
    if not GEO_MUNICIPIOS.exists():
        return html.Div(
            className="aviso-dados",
            style={"padding": "40px", "text-align": "center"},
            children=[
                html.P("ⓘ Mapa indisponível: GeoJSON não encontrado.",
                       style={"font-size": "13px"}),
                html.Code("python -m etl.geo_etl"),
            ]
        )
    fig = _construir_mapa_figura(ano)
    return dcc.Graph(
        id='mapa-fpm',
        figure=fig,
        config={'displayModeBar': False, 'scrollZoom': False},
        clickData=None,
    )


# ============================================================================
# Rankings
# ============================================================================

def _ranking_municipios_fpm(ano: int):
    df = data.fpm_ranking_municipios(ano, top_n=10)
    fig = charts.barras_ranking(
        df=df, label_col='municipio', valor_col='total',
        altura=320, top_n=10,
    )
    fig.update_traces(text=df['total'].apply(_fmt_brl)[::-1])
    return dcc.Graph(figure=fig, config={'displayModeBar': False})


def _ranking_rds_fpm(ano: int):
    df = data.fpm_ranking_rds(ano)
    fig = charts.barras_ranking(
        df=df, label_col='regiao_desenvolvimento', valor_col='total',
        altura=320, top_n=12,
    )
    fig.update_traces(text=df.head(12)['total'].apply(_fmt_brl)[::-1])
    return dcc.Graph(figure=fig, config={'displayModeBar': False})


# ============================================================================
# Evolução temporal mensal por tipo de transferência
# ============================================================================

def _construir_evolucao_temporal(itens_selecionados: list = None):
    """
    Linhas mensais com total de transferências de PE por tipo.
    itens_selecionados filtra quais tipos exibir (default: todos).
    """
    df = data.fpm_evolucao_mensal_por_tipo()
    if df.empty:
        return html.Div("Sem dados.", className="aviso-dados")

    if not itens_selecionados:
        itens_selecionados = _ITENS_ORDEM

    fig = go.Figure()

    for i, item in enumerate(_ITENS_ORDEM):
        if item not in itens_selecionados:
            continue
        sub = df[df['item'] == item].sort_values('data')
        if sub.empty:
            continue
        cor = ITEM_CORES.get(item, PALETTE['cinza_medio'])
        fig.add_trace(go.Scatter(
            x=sub['data'],
            y=sub['total'] / 1e6,
            mode='lines+markers',
            name=item,
            line=dict(color=cor, width=2.5 if i == 0 else 2),
            marker=dict(size=5, color=cor),
            hovertemplate=(
                f'<b>{item}</b><br>'
                '%{x|%b/%Y}<br>'
                'R$ %{y:.1f} mi<extra></extra>'
            ),
        ))

    n_itens = len(itens_selecionados)
    altura = 380 if n_itens > 1 else 320

    charts.aplicar_layout_default(fig,
        height=altura,
        showlegend=True,
        legend=dict(
            orientation='h',
            yanchor='bottom', y=1.02,
            xanchor='right', x=1,
            font=dict(size=10, color=PALETTE['cinza_medio']),
        ),
        margin=dict(l=50, r=20, t=40, b=50),
        xaxis=dict(
            showgrid=False,
            tickformat='%b/%Y',
            tickangle=-30,
            tickfont=dict(size=9, color=PALETTE['cinza_medio']),
            dtick='M3',
        ),
        yaxis=dict(
            ticksuffix=' mi',
            tickprefix='R$ ',
            showgrid=True,
            gridcolor=PALETTE['cinza_neblina'],
            gridwidth=0.5,
            tickfont=dict(size=10, color=PALETTE['cinza_medio']),
        ),
    )
    return dcc.Graph(id='fpm-evolucao-grafico', figure=fig,
                     config={'displayModeBar': False})


# ============================================================================
# Composição de transferências (donut + ranking municípios da RD)
# ============================================================================

def _construir_composicao(rd_nome: str, ano: int):
    """
    Donut com composição % por tipo de transferência para a RD + ano
    selecionados, acompanhado de ranking dos municípios da RD.
    """
    comp = data.fpm_composicao_por_tipo_e_rd(rd_nome, ano)
    if comp.empty:
        return html.Div("Sem dados para esta RD/ano.", className="aviso-dados")

    total_rd = float(comp['total'].sum())
    labels = comp['item'].tolist()
    cores_donut = [ITEM_CORES.get(it, PALETTE['cinza_medio']) for it in labels]

    fig_donut = go.Figure(go.Pie(
        labels=labels,
        values=comp['total'],
        hole=0.55,
        marker=dict(colors=cores_donut,
                    line=dict(color=PALETTE['branco'], width=2)),
        textposition='outside',
        textinfo='label+percent',
        textfont=dict(size=11, color=PALETTE['grafite']),
        hovertemplate='<b>%{label}</b><br>%{customdata}<br>%{percent}<extra></extra>',
        customdata=comp['total'].apply(_fmt_brl).tolist(),
        sort=False,
        showlegend=False,
    ))
    fig_donut.add_annotation(
        x=0.5, y=0.5, xref='paper', yref='paper',
        text=f"<b>{_fmt_brl(total_rd)}</b><br>"
             f"<span style='font-size:10px;color:#7A7A7A'>"
             f"total · {ano}</span>",
        showarrow=False,
        xanchor='center', yanchor='middle',
        font=dict(size=14, color=PALETTE['preto_titulo']),
    )
    charts.aplicar_layout_default(fig_donut,
        height=360,
        showlegend=False,
        margin=dict(l=30, r=30, t=20, b=20),
    )

    # Ranking de municípios da RD por total de transferências
    df_mun = data.fpm_municipal_ano(ano)
    if rd_nome != '__todas__':
        df_mun = df_mun[df_mun['regiao_desenvolvimento'] == rd_nome]
    df_mun = df_mun.sort_values('total', ascending=True)
    n_munis = len(df_mun)
    altura_barras = max(360, 30 * n_munis + 60)

    fig_barras = go.Figure(go.Bar(
        x=df_mun['total'],
        y=df_mun['municipio'],
        orientation='h',
        marker=dict(color=SEMANTIC['destaque']),
        text=df_mun['total'].apply(_fmt_brl),
        textposition='outside',
        textfont=dict(size=10, color=PALETTE['grafite']),
        cliponaxis=False,
        hovertemplate='<b>%{y}</b><br>%{x:,.0f}<extra></extra>',
        showlegend=False,
    ))
    fig_barras.update_xaxes(visible=False,
                             range=[0, df_mun['total'].max() * 1.30])
    fig_barras.update_yaxes(
        showgrid=False,
        tickfont=dict(size=11, color=PALETTE['grafite']),
        ticks='', showline=False,
        automargin=True,
    )
    charts.aplicar_layout_default(fig_barras,
        height=altura_barras,
        showlegend=False,
        margin=dict(l=10, r=40, t=20, b=20),
    )

    return html.Div(
        className="vab-setorial-grid",
        children=[
            html.Div(className="vab-donut-wrap",
                     children=dcc.Graph(figure=fig_donut,
                                        config={'displayModeBar': False})),
            html.Div(className="vab-barras-wrap",
                     children=dcc.Graph(figure=fig_barras,
                                        config={'displayModeBar': False})),
        ],
    )


# ============================================================================
# Layout
# ============================================================================

def layout():
    ano_default = data.fpm_ultimo_ano()
    anos_disponiveis = data.fpm_anos_disponiveis()
    rds = data.lista_rds()
    rd_default = 'Metropolitana'

    return html.Div(className="aba-conteudo", children=[

        html.Div(className="aba-titulo-bloco", children=[
            html.Div([
                html.P("Gestão Pública",
                       className="aba-titulo"),
                html.P(f"Receita Fiscal · transferências STN · "
                       f"FPM · FPE · ICMS · IPVA · ITR · IPI-EXP · ITCMD · FEP · "
                       f"{anos_disponiveis[-1]}—{ano_default}",
                       className="aba-subtitulo"),
            ]),
            html.Div(className="aba-acoes", children=[
                html.Span("clique em um município no mapa para filtrar os KPIs",
                          className="aba-dica"),
                html.Button("limpar seleção", id="btn-limpar-fpm",
                            className="btn-link hidden"),
            ]),
        ]),

        dcc.Store(id='fpm-municipio-selecionado', data=None),

        html.Div(id='fpm-kpis', children=_kpis_estaduais(ano_default)),

        ui.secao(
            etiqueta="transferências por município",
            titulo="",
            descricao=f"default: {ano_default} · "
                      f"clique em um município para filtrar os KPIs · "
                      f"hover mostra participação na RD e no estado",
            children=html.Div([
                html.Div(className="filtros-row", children=[
                    html.Div(className="filtro-item", children=[
                        html.Label("ANO:", className="filtro-label"),
                        dcc.Dropdown(
                            id='filtro-fpm-ano',
                            options=[{'label': str(a), 'value': a}
                                     for a in anos_disponiveis],
                            value=ano_default,
                            clearable=False,
                            searchable=False,
                            className="filtro-dropdown",
                        ),
                    ]),
                ]),
                _construir_mapa(ano_default),
            ]),
        ),

        html.Div(className="grid-duplo grid-1-1", children=[
            ui.secao(
                etiqueta="ranking municipal",
                titulo="",
                descricao=f"top 10 municípios por transferências · {ano_default}",
                children=html.Div(id='ranking-fpm-mun-container',
                                  children=_ranking_municipios_fpm(ano_default)),
            ),
            ui.secao(
                etiqueta="ranking regional",
                titulo="",
                descricao=f"total de transferências por RD · {ano_default}",
                children=html.Div(id='ranking-fpm-rd-container',
                                  children=_ranking_rds_fpm(ano_default)),
            ),
        ]),

        ui.secao(
            etiqueta="evolução temporal",
            titulo="",
            descricao="total de transferências para Pernambuco por mês · "
                      "uma linha por tipo · use o filtro para isolar tipos",
            children=html.Div([
                html.Div(className="filtros-row", children=[
                    html.Div(className="filtro-item", style={"flex": "1 1 auto"}, children=[
                        html.Label("TIPO:", className="filtro-label"),
                        dcc.Dropdown(
                            id='filtro-fpm-evol-tipo',
                            options=[{'label': it, 'value': it}
                                     for it in _ITENS_ORDEM],
                            value=_ITENS_ORDEM,
                            multi=True,
                            clearable=False,
                            searchable=False,
                            className="filtro-dropdown",
                            placeholder="Selecione os tipos...",
                        ),
                    ]),
                ]),
                html.Div(id='fpm-evolucao-container',
                         children=_construir_evolucao_temporal(_ITENS_ORDEM)),
            ]),
        ),

        html.Div(className="grid-duplo grid-1-1", children=[
            ui.secao(
                etiqueta="composição de transferências",
                titulo="",
                descricao="distribuição % por tipo de transferência na RD · "
                          "com ranking dos municípios",
                children=html.Div([
                    html.Div(className="filtros-row", children=[
                        html.Div(className="filtro-item", children=[
                            html.Label("RD:", className="filtro-label"),
                            dcc.Dropdown(
                                id='filtro-fpm-comp-rd',
                                options=([{'label': 'Todas (estado)', 'value': '__todas__'}]
                                         + [{'label': r, 'value': r} for r in rds]),
                                value=rd_default,
                                clearable=False,
                                searchable=True,
                                className="filtro-dropdown",
                            ),
                        ]),
                        html.Div(className="filtro-item", children=[
                            html.Label("ANO:", className="filtro-label"),
                            dcc.Dropdown(
                                id='filtro-fpm-comp-ano',
                                options=[{'label': str(a), 'value': a}
                                         for a in anos_disponiveis],
                                value=ano_default,
                                clearable=False,
                                searchable=False,
                                className="filtro-dropdown",
                            ),
                        ]),
                    ]),
                    html.Div(id='fpm-composicao-container',
                             children=_construir_composicao(rd_default, ano_default)),
                ]),
            ),
            ui.secao(
                etiqueta="transferências por município na RD",
                titulo="",
                descricao="total de transferências por município na RD selecionada",
                children=html.Div([
                    html.Div(className="filtros-row", children=[
                        html.Div(className="filtro-item", children=[
                            html.Label("ANO:", className="filtro-label"),
                            dcc.Dropdown(
                                id='filtro-fpm-mun-ano',
                                options=[{'label': str(a), 'value': a}
                                         for a in anos_disponiveis],
                                value=ano_default,
                                clearable=False,
                                searchable=False,
                                className="filtro-dropdown",
                            ),
                        ]),
                        html.Div(className="filtro-item", children=[
                            html.Label("RD:", className="filtro-label"),
                            dcc.Dropdown(
                                id='filtro-fpm-mun-rd',
                                options=[{'label': r, 'value': r} for r in rds],
                                value=rd_default,
                                clearable=False,
                                searchable=True,
                                className="filtro-dropdown",
                            ),
                        ]),
                    ]),
                    html.Div(id='fpm-municipio-composicao-container',
                             children=_construir_ranking_municipios_rd(
                                 rd_default, ano_default)),
                ]),
            ),
        ]),

        ui.footer(
            fonte_principal="STN · Secretaria do Tesouro Nacional · "
                            "Transferências constitucionais e legais",
            atualizacao=str(ano_default),
        ),
    ])


def _construir_ranking_municipios_rd(rd_nome: str, ano: int):
    """Ranking de todos os municípios de uma RD por total de transferências."""
    df = data.fpm_municipal_ano(ano)
    df = df[df['regiao_desenvolvimento'] == rd_nome].sort_values('total', ascending=True)

    if df.empty:
        return html.Div("Sem dados para esta RD/ano.", className="aviso-dados")

    n_munis = len(df)
    altura = max(320, 30 * n_munis + 60)

    fig = go.Figure(go.Bar(
        x=df['total'],
        y=df['municipio'],
        orientation='h',
        marker=dict(color=SEMANTIC['destaque']),
        text=df['total'].apply(_fmt_brl),
        textposition='outside',
        textfont=dict(size=10, color=PALETTE['grafite']),
        cliponaxis=False,
        hovertemplate='<b>%{y}</b><br>%{x:,.0f}<extra></extra>',
        showlegend=False,
    ))
    fig.update_xaxes(visible=False, range=[0, df['total'].max() * 1.30])
    fig.update_yaxes(
        showgrid=False,
        tickfont=dict(size=11, color=PALETTE['grafite']),
        ticks='', showline=False,
        automargin=True,
    )
    charts.aplicar_layout_default(fig,
        height=altura,
        showlegend=False,
        margin=dict(l=10, r=40, t=20, b=20),
    )
    return dcc.Graph(figure=fig, config={'displayModeBar': False})


# ============================================================================
# Callbacks
# ============================================================================

def callbacks(app):

    @app.callback(
        Output('mapa-fpm', 'figure'),
        Output('ranking-fpm-mun-container', 'children'),
        Output('ranking-fpm-rd-container', 'children'),
        Input('filtro-fpm-ano', 'value'),
    )
    def atualizar_ano(ano):
        if not ano:
            return [no_update] * 3
        return (
            _construir_mapa_figura(ano),
            _ranking_municipios_fpm(ano),
            _ranking_rds_fpm(ano),
        )

    @app.callback(
        Output('fpm-municipio-selecionado', 'data'),
        Input('mapa-fpm', 'clickData'),
        Input('btn-limpar-fpm', 'n_clicks'),
        State('fpm-municipio-selecionado', 'data'),
        prevent_initial_call=True,
    )
    def gerenciar_selecao(click_data, n_limpar, atual):
        trigger = ctx.triggered_id
        if trigger == 'btn-limpar-fpm':
            return None
        if trigger == 'mapa-fpm' and click_data:
            cod = click_data['points'][0].get('location')
            if cod is None:
                return no_update
            try:
                cod = int(str(cod).strip())
            except (TypeError, ValueError):
                return no_update
            return None if atual == cod else cod
        return no_update

    @app.callback(
        Output('fpm-kpis', 'children'),
        Input('filtro-fpm-ano', 'value'),
        Input('fpm-municipio-selecionado', 'data'),
    )
    def atualizar_kpis(ano, cod):
        if not ano:
            return no_update
        return _construir_kpis(ano, cod_ibge_6=cod)

    @app.callback(
        Output('btn-limpar-fpm', 'className'),
        Input('fpm-municipio-selecionado', 'data'),
    )
    def toggle_btn(cod):
        return 'btn-link' if cod else 'btn-link hidden'

    @app.callback(
        Output('fpm-evolucao-container', 'children'),
        Input('filtro-fpm-evol-tipo', 'value'),
    )
    def atualizar_evolucao(itens):
        return _construir_evolucao_temporal(itens or _ITENS_ORDEM)

    @app.callback(
        Output('fpm-composicao-container', 'children'),
        Input('filtro-fpm-comp-rd', 'value'),
        Input('filtro-fpm-comp-ano', 'value'),
    )
    def atualizar_composicao(rd, ano):
        if not rd or not ano:
            return no_update
        return _construir_composicao(rd, ano)

    @app.callback(
        Output('fpm-municipio-composicao-container', 'children'),
        Input('filtro-fpm-mun-rd', 'value'),
        Input('filtro-fpm-mun-ano', 'value'),
    )
    def atualizar_municipios_rd(rd, ano):
        if not rd or not ano:
            return no_update
        return _construir_ranking_municipios_rd(rd, ano)
