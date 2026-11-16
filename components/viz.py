"""
components/viz.py
=================
Blocos reutilizáveis das abas da versão 2.0: formatação brasileira,
cartões de KPI, filtros e figuras Plotly no padrão visual do observatório.

Convenções de cor (validadas para daltonismo com o método de dataviz do
projeto; ver nota no README):
    - uma entidade tem sempre a mesma cor em todo o painel: Pernambuco em
      azul, Nordeste em terracota, Brasil em cinza escuro; exportação em
      azul, importação em terracota;
    - escala sequencial (magnitude) em um só tom de azul, do claro ao
      escuro; escala divergente (crescimento/queda) terracota-cinza-azul;
    - nenhum gráfico tem dois eixos Y.
"""

from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
from dash import dcc, html

from components import charts, ui
from config import CHART_LAYOUT_DEFAULTS, PALETTE, SEMANTIC

# ============================================================================
# Cores
# ============================================================================

CORES = {
    'azul': '#2F6DB0',
    'terracota': '#CC5F3C',
    'violeta': '#8064BF',
    'verde': '#22895A',
    'mostarda': '#B4841A',
    'cinza': '#5F5E5A',
    'cinza_claro': '#B8B8B8',
    'azul_claro': '#9DB4C7',
}
SERIES = [CORES[k] for k in ('azul', 'terracota', 'violeta', 'verde', 'mostarda')]

COR_REGIAO = {
    'Pernambuco': CORES['azul'],
    'RM Recife': CORES['azul'],
    'Nordeste': CORES['terracota'],
    'Brasil': CORES['cinza'],
}
COR_FLUXO = {'export': CORES['azul'], 'import': CORES['terracota']}

ESCALA_SEQ = [[0.0, '#EEF3F8'], [0.25, '#C6D7EA'], [0.5, '#8FB0D5'],
              [0.75, '#4F83BD'], [1.0, '#1F4F86']]
ESCALA_DIV = [[0.0, CORES['terracota']], [0.5, '#EEEBE6'], [1.0, CORES['azul']]]
# Magnitude de algo ruim (ex.: taxa de homicídios): um só tom quente
ESCALA_SEQ_QUENTE = [[0.0, '#FBEFEA'], [0.25, '#F2CDBF'], [0.5, '#E3A189'],
                     [0.75, '#D47A5C'], [1.0, '#A8462A']]

MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
         'jul', 'ago', 'set', 'out', 'nov', 'dez']

GRAPH_CONFIG = {'displayModeBar': False, 'scrollZoom': False,
                'locale': 'pt-BR'}


# ============================================================================
# Formatação (padrão brasileiro)
# ============================================================================

def _vazio(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v)


def num(v, casas: int = 0) -> str:
    """1234.5 -> '1.234,5'."""
    if _vazio(v):
        return '—'
    s = f"{v:,.{casas}f}"
    return s.replace(',', '_').replace('.', ',').replace('_', '.')


def pct(v, casas: int = 1, sinal: bool = False) -> str:
    """3.25 -> '3,3%' (ou '+3,3%' com sinal=True)."""
    if _vazio(v):
        return '—'
    s = num(abs(v) if sinal else v, casas) + '%'
    if sinal:
        s = ('+' if v > 0 else '−' if v < 0 else '') + s
    return s


def moeda(v, simbolo: str = 'R$', casas: int = None) -> str:
    """Valor monetário abreviado: R$ 1,23 bi · R$ 456,7 mi · R$ 12,3 mil."""
    if _vazio(v):
        return '—'
    a = abs(v)
    neg = '−' if v < 0 else ''
    if a >= 1e9:
        return f"{neg}{simbolo} {num(a / 1e9, 2 if casas is None else casas)} bi"
    if a >= 1e6:
        return f"{neg}{simbolo} {num(a / 1e6, 1 if casas is None else casas)} mi"
    if a >= 1e3:
        return f"{neg}{simbolo} {num(a / 1e3, 1 if casas is None else casas)} mil"
    return f"{neg}{simbolo} {num(a, 0 if casas is None else casas)}"


def usd(v, casas: int = None) -> str:
    return moeda(v, 'US$', casas)


def reais(v, simbolo: str = 'R$') -> str:
    """Valor sem abreviar (para per capita): R$ 2.874."""
    if _vazio(v):
        return '—'
    return f"{'−' if v < 0 else ''}{simbolo} {num(abs(v))}"


def escala_monetaria(vmax: float):
    """Divisor e sufixo do eixo para valores monetários: (1e9, ' bi')..."""
    a = abs(vmax or 0)
    if a >= 1e9:
        return 1e9, ' bi'
    if a >= 1e6:
        return 1e6, ' mi'
    if a >= 1e4:
        return 1e3, ' mil'
    return 1.0, ''


def mes_ano(ts) -> str:
    """Timestamp -> 'set/2026'."""
    if _vazio(ts):
        return '—'
    ts = pd.Timestamp(ts)
    return f"{MESES[ts.month - 1]}/{ts.year}"


def periodo_meses(m_ini: int, m_fim: int) -> str:
    """(1, 9) -> 'jan–set'."""
    if m_ini == m_fim:
        return MESES[m_ini - 1]
    return f"{MESES[m_ini - 1]}–{MESES[m_fim - 1]}"


def variacao(v, referencia: str = 'vs ano anterior', casas: int = 1,
             inverter: bool = False):
    """
    Texto de variação para o sub do KPI, com cor semântica.
    inverter=True quando subir é ruim (ex.: homicídios).
    """
    if _vazio(v):
        return (f"sem base de comparação", 'neutro')
    seta = '▲' if v > 0 else '▼' if v < 0 else '='
    bom = (v > 0) != inverter if v != 0 else None
    cor = 'neutro' if bom is None else ('positivo' if bom else 'negativo')
    return (f"{seta} {pct(abs(v), casas)} {referencia}", cor)


# ============================================================================
# Estrutura da aba
# ============================================================================

def titulo_aba(titulo: str, subtitulo: str, dica: str = None,
               botao_limpar: str = None):
    acoes = []
    if dica:
        acoes.append(html.Span(dica, className="aba-dica"))
    if botao_limpar:
        acoes.append(html.Button("limpar seleção", id=botao_limpar,
                                 className="btn-link hidden"))
    return html.Div(className="aba-titulo-bloco", children=[
        html.Div([html.P(titulo, className="aba-titulo"),
                  html.P(subtitulo, className="aba-subtitulo")]),
        html.Div(className="aba-acoes", children=acoes) if acoes else None,
    ])


def kpi(label, valor, sub=None, destaque: bool = False, texto: bool = None):
    """KPI; quando o valor é um nome (texto longo), usa fonte menor."""
    if texto is None:
        texto = isinstance(valor, str) and len(valor) > 14 and not any(
            ch.isdigit() for ch in valor)
    return ui.kpi_simples(label=label, valor=valor, sub=sub,
                          accent=SEMANTIC['destaque'] if destaque else None,
                          classe_extra='kpi-texto' if texto else '')


def faixa_kpis(kpis: list, contexto: str = None):
    """Faixa de KPIs; o contexto (estado ou município) vai numa etiqueta acima."""
    classe = {3: 'kpi-faixa kpi-faixa-tres', 4: 'kpi-faixa kpi-faixa-quatro',
              5: 'kpi-faixa kpi-faixa-cinco'}.get(len(kpis), 'kpi-faixa')
    faixa = html.Div(className=classe, children=list(kpis))
    if not contexto:
        return faixa
    return html.Div([html.P(contexto, className="kpi-contexto-v2"), faixa])


def filtro(label: str, componente, largo: bool = False):
    return html.Div(className="filtro-item",
                    style={'flex': '1 1 260px'} if largo else None,
                    children=[html.Label(label, className="filtro-label"),
                              componente])


def linha_filtros(*filtros):
    return html.Div(className="filtros-row", children=list(filtros))


def dropdown(id_, opcoes, valor, multi: bool = False, busca: bool = False,
             limpar: bool = False, placeholder: str = None):
    """opcoes: lista de valores ou de (rótulo, valor)."""
    ops = [o if isinstance(o, dict) else
           ({'label': o[0], 'value': o[1]} if isinstance(o, (tuple, list))
            else {'label': str(o), 'value': o}) for o in opcoes]
    return dcc.Dropdown(id=id_, options=ops, value=valor, multi=multi,
                        clearable=limpar, searchable=busca,
                        placeholder=placeholder, className="filtro-dropdown")


def botoes(id_, opcoes, valor):
    """Seletor em pílulas (RadioItems) para alternar visões de um gráfico."""
    ops = [{'label': o[0], 'value': o[1]} if isinstance(o, (tuple, list))
           else {'label': str(o), 'value': o} for o in opcoes]
    return dcc.RadioItems(id=id_, options=ops, value=valor, inline=True,
                          className="seletor-pilulas",
                          inputClassName="seletor-pilulas-input",
                          labelClassName="seletor-pilulas-label")


def grafico(fig, id_: str = None):
    kwargs = {'figure': fig, 'config': GRAPH_CONFIG}
    if id_:
        kwargs['id'] = id_
    return dcc.Graph(**kwargs)


def nota(*partes):
    return html.P(className="nota-grafico", children=list(partes))


def aviso(texto: str, comando: str = None):
    filhos = [html.P(texto, style={'margin': '0'})]
    if comando:
        filhos.append(html.Code(comando))
    return html.Div(className="aviso-dados", children=filhos)


def grade(*filhos, proporcao: str = '1-1'):
    classe = {'1-1': 'grid-duplo grid-1-1', '2-1': 'grid-duplo',
              '3': 'grid-triplo'}[proporcao]
    return html.Div(className=classe, children=list(filhos))


def secao(etiqueta: str, descricao: str, *filhos, titulo: str = ''):
    return ui.secao(etiqueta=etiqueta, titulo=titulo, descricao=descricao,
                    children=html.Div(list(filhos)))


def tabela(df: pd.DataFrame, colunas: list, classe: str = 'tabela-v2'):
    """
    Tabela HTML simples. colunas: lista de (cabeçalho, coluna, alinhamento)
    com alinhamento 'esq' ou 'dir'. Valores já devem vir formatados.
    """
    cab = html.Thead(html.Tr([html.Th(c[0], className=f"td-{c[2]}")
                              for c in colunas]))
    linhas = [html.Tr([html.Td(r[c[1]], className=f"td-{c[2]}") for c in colunas])
              for _, r in df.iterrows()]
    return html.Div(className="tabela-v2-wrap",
                    children=html.Table(className=classe,
                                        children=[cab, html.Tbody(linhas)]))


# ============================================================================
# Figuras
# ============================================================================

def layout_padrao(fig: go.Figure, altura: int = 320, legenda: bool = True,
                  y_sufixo: str = '', y_prefixo: str = '', y_formato: str = None,
                  x_formato: str = None, margem: dict = None,
                  hovermode: str = 'x unified', y_zero: bool = True,
                  y_titulo: str = '') -> go.Figure:
    yaxis = dict(CHART_LAYOUT_DEFAULTS['yaxis'])
    yaxis.update(ticksuffix=y_sufixo, tickprefix=y_prefixo,
                 separatethousands=True, zeroline=y_zero,
                 title=dict(text=y_titulo, font=dict(size=10)))
    if y_formato:
        yaxis['tickformat'] = y_formato
    xaxis = dict(CHART_LAYOUT_DEFAULTS['xaxis'])
    if x_formato:
        xaxis['tickformat'] = x_formato
    charts.aplicar_layout_default(
        fig, height=altura, showlegend=legenda,
        separators=',.',
        margin=margem or dict(l=50, r=20, t=30 if legenda else 12, b=40),
        legend=dict(orientation='h', yanchor='bottom', y=1.0, xanchor='left',
                    x=0, font=dict(size=11, color=PALETTE['grafite']),
                    bgcolor='rgba(0,0,0,0)', traceorder='normal'),
        hovermode=hovermode, xaxis=xaxis, yaxis=yaxis,
        barcornerradius=3, bargap=0.25,
    )
    return fig


def _y_monetario(series: list, monetario: str):
    """Reescala as séries monetárias (bi/mi/mil) e prepara o texto do hover."""
    vmax = max((pd.Series(list(s['y'])).abs().max() for s in series), default=0)
    div, suf = escala_monetaria(vmax)
    novas = []
    for s in series:
        ys = list(s['y'])
        n = dict(s)
        n['y'] = [None if _vazio(v) else v / div for v in ys]
        n['_hover'] = [moeda(v, monetario) for v in ys]
        novas.append(n)
    return novas, f"{monetario} ", suf


def fig_linhas(series: list, altura: int = 320, y_sufixo: str = '',
               y_prefixo: str = '', hover_fmt: str = ',.1f',
               x_hover: str = '%b/%Y', legenda: bool = None,
               linha_zero: bool = False, y_zero: bool = False,
               monetario: str = None) -> go.Figure:
    """
    series: lista de dicts {x, y, nome, cor, tracejado(bool), largura,
            marcadores(bool)}.
    monetario: 'R$' ou 'US$' para eixo em bi/mi/mil e hover por extenso.
    """
    if monetario:
        series, y_prefixo, y_sufixo = _y_monetario(series, monetario)
    fig = go.Figure()
    for i, s in enumerate(series):
        cor = s.get('cor') or SERIES[i % len(SERIES)]
        if monetario:
            hov = f"{s.get('nome', '')}: %{{customdata}}<extra></extra>"
        else:
            hov = (f"{s.get('nome', '')}: {y_prefixo}%{{y:{hover_fmt}}}"
                   f"{y_sufixo}<extra></extra>")
        fig.add_trace(go.Scatter(
            x=s['x'], y=s['y'], name=s.get('nome', ''),
            mode='lines+markers' if s.get('marcadores') else 'lines',
            line=dict(color=cor, width=s.get('largura', 2),
                      dash='dot' if s.get('tracejado') else 'solid'),
            marker=dict(size=7, color=cor, line=dict(color='#FFFFFF', width=1)),
            customdata=s.get('_hover'),
            hovertemplate=hov,
            connectgaps=False,
        ))
    if legenda is None:
        legenda = len(series) > 1
    layout_padrao(fig, altura=altura, legenda=legenda, y_sufixo=y_sufixo,
                  y_prefixo=y_prefixo, y_zero=y_zero)
    fig.update_xaxes(hoverformat=x_hover, showspikes=True, spikemode='across',
                     spikethickness=1, spikedash='dot',
                     spikecolor=PALETTE['cinza_claro'])
    if linha_zero:
        fig.add_hline(y=0, line=dict(color=PALETTE['cinza_claro'], width=1))
    return fig


def fig_barras(x, y, cor=None, texto=None, altura: int = 300,
               y_sufixo: str = '', y_prefixo: str = '', hover_fmt: str = ',.1f',
               nome: str = '', horizontal: bool = False,
               cores_por_valor: bool = False) -> go.Figure:
    """Barras simples (uma série). cores_por_valor pinta negativos de terracota."""
    y = list(y)
    if cores_por_valor:
        cor = [CORES['terracota'] if (v is not None and v < 0) else CORES['azul']
               for v in y]
    fig = go.Figure(go.Bar(
        x=y if horizontal else x, y=x if horizontal else y,
        orientation='h' if horizontal else 'v',
        marker=dict(color=cor or CORES['azul']),
        text=texto, textposition='outside' if texto is not None else None,
        textfont=dict(size=10, color=PALETTE['grafite']), cliponaxis=False,
        name=nome,
        hovertemplate=(f"%{{{'y' if horizontal else 'x'}}}: {y_prefixo}"
                       f"%{{{'x' if horizontal else 'y'}:{hover_fmt}}}{y_sufixo}"
                       "<extra></extra>"),
    ))
    layout_padrao(fig, altura=altura, legenda=False, y_sufixo=y_sufixo,
                  y_prefixo=y_prefixo, hovermode='closest')
    return fig


def fig_barras_series(x, series: list, altura: int = 320, empilhado: bool = False,
                      y_sufixo: str = '', y_prefixo: str = '',
                      hover_fmt: str = ',.1f', legenda: bool = True,
                      monetario: str = None) -> go.Figure:
    """
    Várias séries de barras (agrupadas ou empilhadas).
    series: lista de dicts {y, nome, cor}.
    monetario: 'R$' ou 'US$' para eixo em bi/mi/mil e hover por extenso.
    """
    if monetario:
        if empilhado:  # a escala depende do total empilhado
            tot = pd.DataFrame([list(s['y']) for s in series]).fillna(0).sum()
            div, suf = escala_monetaria(tot.abs().max())
            novas = []
            for s in series:
                n = dict(s)
                n['_hover'] = [moeda(v, monetario) for v in s['y']]
                n['y'] = [None if _vazio(v) else v / div for v in s['y']]
                novas.append(n)
            series, y_prefixo, y_sufixo = novas, f"{monetario} ", suf
        else:
            series, y_prefixo, y_sufixo = _y_monetario(series, monetario)
    fig = go.Figure()
    for i, s in enumerate(series):
        cor = s.get('cor') or SERIES[i % len(SERIES)]
        hov = (f"{s['nome']}: %{{customdata}}<extra></extra>" if monetario else
               f"{s['nome']}: {y_prefixo}%{{y:{hover_fmt}}}{y_sufixo}<extra></extra>")
        fig.add_trace(go.Bar(
            x=x, y=s['y'], name=s['nome'], customdata=s.get('_hover'),
            marker=dict(color=cor, line=dict(color='#FFFFFF', width=1 if empilhado else 0)),
            hovertemplate=hov,
        ))
    layout_padrao(fig, altura=altura, legenda=legenda, y_sufixo=y_sufixo,
                  y_prefixo=y_prefixo)
    fig.update_layout(barmode='stack' if empilhado else 'group',
                      bargroupgap=0.08)
    return fig


def fig_ranking(df: pd.DataFrame, rotulo: str, valor: str, fmt=None,
                n: int = 10, cor: str = None, destaque=None,
                altura: int = None, crescente: bool = False,
                hover_extra: str = None) -> go.Figure:
    """
    Barras horizontais ordenadas, maior no topo (ou menor, se crescente).
    destaque: rótulo a pintar com a cor de destaque (ex.: município clicado).
    Negativos ficam em terracota.
    """
    fmt = fmt or (lambda v: num(v))
    d = df.dropna(subset=[valor]).sort_values(valor, ascending=crescente).head(n)
    d = d.iloc[::-1]  # Plotly desenha de baixo para cima
    base = cor or CORES['azul']
    cores = []
    for r, v in zip(d[rotulo], d[valor]):
        if destaque is not None and r == destaque:
            cores.append(CORES['mostarda'])
        elif v < 0:
            cores.append(CORES['terracota'])
        else:
            cores.append(base)
    textos = [fmt(v) for v in d[valor]]
    vmax = d[valor].abs().max() if len(d) else 1
    vmin = min(0, d[valor].min()) if len(d) else 0
    fig = go.Figure(go.Bar(
        x=d[valor], y=d[rotulo], orientation='h', marker=dict(color=cores),
        text=textos, textposition='outside', cliponaxis=False,
        textfont=dict(size=10.5, color=PALETTE['grafite']),
        customdata=d[[hover_extra]].values if hover_extra else textos,
        hovertemplate=('<b>%{y}</b><br>%{customdata[0]}<extra></extra>'
                       if hover_extra else '<b>%{y}</b><br>%{customdata}<extra></extra>'),
    ))
    charts.aplicar_layout_default(
        fig, height=altura or max(120, 28 * len(d) + 24), showlegend=False,
        margin=dict(l=10, r=20, t=6, b=6), separators=',.',
        xaxis=dict(visible=False,
                   range=[vmin * 1.35 if vmin < 0 else 0, vmax * 1.32]),
        yaxis=dict(showgrid=False, ticks='', showline=False, automargin=True,
                   tickfont=dict(size=11, color=PALETTE['grafite'])),
        barcornerradius=3,
    )
    return fig


def fig_mapa(df: pd.DataFrame, valor: str, hover: list, legenda: str = '',
             escala: str = 'seq', zmin=None, zmax=None, altura: int = 420,
             geojson: dict = None, zoom: float = None) -> go.Figure:
    """
    Coroplético dos municípios de PE.
    df precisa de cod_ibge_6, municipio e a coluna `valor`.
    hover: lista de (rótulo, coluna_já_formatada).
    escala: 'seq' (magnitude), 'quente' (magnitude de algo ruim) ou 'div'
        (variação, centrada em zero).
    """
    from components import data as _data
    geo = geojson or _data.geojson_municipios()
    d = df.copy()
    linhas = ['<b>%{text}</b>']
    for i, (rot, _) in enumerate(hover):
        linhas.append(f"{rot}: %{{customdata[{i}]}}")
    divergente = escala == 'div'
    fig = charts.mapa_municipios_pe(
        df=d, geojson=geo, valor_col=valor,
        hovertemplate='<br>'.join(linhas),
        customdata_cols=[c for _, c in hover],
        cor_escala=(ESCALA_DIV if divergente else
                    ESCALA_SEQ_QUENTE if escala == 'quente' else ESCALA_SEQ),
        divergente=divergente, zmin=zmin, zmax=zmax,
        altura=altura, titulo_legenda=legenda,
    )
    fig.update_layout(separators=',.')
    fig.update_traces(colorbar_tickformat=',.0f')
    # Municípios sem dado: desenhados em cinza claro, para o mapa não ficar
    # com buracos (o coroplético só pinta quem tem valor).
    presentes = set(d['cod_ibge_6'].astype(str))
    faltam = [f['properties']['cod_ibge_6'] for f in geo.get('features', [])
              if str(f['properties'].get('cod_ibge_6')) not in presentes]
    if faltam:
        from components.data_base import municipios as _mun
        nomes = dict(zip(_mun()['cod_ibge_6'].astype(str), _mun()['municipio']))
        base = go.Choroplethmapbox(
            geojson=geo, featureidkey='properties.cod_ibge_6',
            locations=[str(c) for c in faltam], z=[0] * len(faltam),
            colorscale=[[0, '#EEEBE6'], [1, '#EEEBE6']], showscale=False,
            marker=dict(line=dict(color='#FFFFFF', width=0.5), opacity=0.9),
            text=[nomes.get(str(c), str(c)) for c in faltam],
            hovertemplate='<b>%{text}</b><br>sem registro<extra></extra>')
        fig.add_trace(base)
        fig.data = (fig.data[-1],) + fig.data[:-1]
    if zoom:
        fig.update_layout(mapbox_zoom=zoom, mapbox_center=dict(lat=-8.35, lon=-37.95))
    return fig


def fig_donut(rotulos, valores, cores=None, centro: str = '', fmt=None,
              altura: int = 300) -> go.Figure:
    fmt = fmt or moeda
    cores = cores or SERIES[:len(rotulos)]
    tot = sum(v for v in valores if not _vazio(v)) or 1
    textos = [pct(100 * v / tot) if v / tot >= 0.02 else '' for v in valores]
    fig = go.Figure(go.Pie(
        labels=rotulos, values=valores, hole=0.58, sort=False,
        marker=dict(colors=cores, line=dict(color='#FFFFFF', width=2)),
        text=textos, textinfo='text', textposition='outside',
        textfont=dict(size=11, color=PALETTE['grafite']),
        customdata=[fmt(v) for v in valores],
        hovertemplate='<b>%{label}</b><br>%{customdata} · %{percent:.1%}<extra></extra>',
    ))
    if centro:
        fig.add_annotation(text=centro, x=0.5, y=0.5, showarrow=False,
                           font=dict(size=13, color=PALETTE['preto_titulo']))
    charts.aplicar_layout_default(
        fig, height=altura, showlegend=True, separators=',.',
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation='v', x=1.0, xanchor='left', y=0.5,
                    font=dict(size=11, color=PALETTE['grafite'])),
    )
    return fig


def fig_dispersao(df: pd.DataFrame, x: str, y: str, texto: str,
                  x_titulo: str, y_titulo: str, cor: str = None,
                  hover: list = None, destaque=None, altura: int = 380,
                  x_log: bool = False) -> go.Figure:
    """Dispersão com hover por ponto; destaque pinta um ponto de mostarda."""
    d = df.dropna(subset=[x, y])
    cores = [CORES['mostarda'] if (destaque is not None and t == destaque)
             else (cor or CORES['azul']) for t in d[texto]]
    tamanhos = [13 if (destaque is not None and t == destaque) else 8
                for t in d[texto]]
    linhas = ['<b>%{text}</b>']
    cd = None
    if hover:
        linhas += [f"{r}: %{{customdata[{i}]}}" for i, (r, _) in enumerate(hover)]
        cd = d[[c for _, c in hover]].values
    fig = go.Figure(go.Scatter(
        x=d[x], y=d[y], mode='markers', text=d[texto], customdata=cd,
        marker=dict(color=cores, size=tamanhos, opacity=0.85,
                    line=dict(color='#FFFFFF', width=1)),
        hovertemplate='<br>'.join(linhas) + '<extra></extra>',
    ))
    layout_padrao(fig, altura=altura, legenda=False, hovermode='closest',
                  y_zero=False)
    fig.update_xaxes(title=dict(text=x_titulo, font=dict(size=10)),
                     type='log' if x_log else 'linear', showgrid=True,
                     gridcolor=PALETTE['cinza_neblina'], gridwidth=0.5)
    if x_log and len(d):
        lo, hi = d[x].min(), d[x].max()
        marcas = [m * 10 ** e for e in range(0, 10) for m in (1, 2, 5)]
        marcas = [v for v in marcas if lo / 1.5 <= v <= hi * 1.5]

        def curto(v):
            if v >= 1e6:
                return f"{num(v / 1e6)} mi"
            if v >= 1e3:
                return f"{num(v / 1e3)} mil"
            return num(v)
        fig.update_xaxes(tickvals=marcas, ticktext=[curto(v) for v in marcas])
    fig.update_yaxes(title=dict(text=y_titulo, font=dict(size=10)))
    return fig


def sem_dados_fig(texto: str = 'Sem dados para esta seleção.',
                  altura: int = 220) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=texto, x=0.5, y=0.5, xref='paper', yref='paper',
                       showarrow=False,
                       font=dict(size=12, color=PALETTE['cinza_medio']))
    charts.aplicar_layout_default(fig, height=altura,
                                  xaxis=dict(visible=False),
                                  yaxis=dict(visible=False),
                                  margin=dict(l=10, r=10, t=10, b=10))
    return fig
