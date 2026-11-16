"""
tabs/indicadores_sociais.py
===========================
Sub-aba Progresso social (Indicadores Sociais): Índice de Progresso Social
(IPS Brasil) dos 185 municípios de Pernambuco.

O IPS mede qualidade de vida só com resultados sociais e ambientais (sem
renda): 3 dimensões, 12 componentes e cerca de 57 indicadores, de 0 a 100.

Estrutura:
1. KPIs: média de PE x Nordeste x Brasil, posição entre as UFs, melhor e
   pior município, dimensão mais fraca
2. Mapa do IPS (ou de uma dimensão/componente)
3. Ranking e médias por RD
4. Riqueza x qualidade de vida: PIB per capita x IPS
5. Ficha do município clicado: dimensões, componentes e indicadores
6. Evolução 2024-2026 (com o aviso de comparabilidade da fonte)

Fonte: IPS Brasil (etl/ips_etl.py).
"""

import plotly.graph_objects as go
from dash import Input, Output, State, ctx, dcc, html, no_update

from components import data_social as ds, ui, viz
from components.data_base import nome_municipio
from components.viz import COR_REGIAO, CORES, num, pct


def registrar():
    return {
        'eixo': 'Indicadores Sociais',
        'sub': 'Progresso social',
        'eixo_ordem': 6,
        'sub_ordem': 1,
        'ativa': True,
        'fonte_legenda': 'IPS Brasil',
    }


def _n(v, casas=1):
    return num(v, casas)


def _kpis(ed):
    r = ds.ips_resumo(ed)
    mel, pio = r['melhor'], r['pior']
    dims = r['dims']
    fraca = min(dims, key=lambda k: dims[k] if dims[k] is not None else 999)
    return viz.faixa_kpis([
        viz.kpi(f"IPS médio · {ed}", _n(r['media_pe']),
                (f"Nordeste {_n(r['media_ne'])} · Brasil {_n(r['media_br'])}", 'neutro'),
                destaque=True),
        viz.kpi("posição entre as UFs", f"{r['rank_uf']}º" if r['rank_uf'] else '—',
                (f"de {r['n_ufs']} · média simples dos municípios", 'neutro')),
        viz.kpi("maior IPS", mel['municipio'] if mel else '—',
                (f"{_n(mel['valor'])} · {int(mel['rank_br'])}º do Brasil", 'neutro') if mel else None),
        viz.kpi("menor IPS", pio['municipio'] if pio else '—',
                (f"{_n(pio['valor'])} · {int(pio['rank_br'])}º do Brasil", 'neutro') if pio else None),
        viz.kpi("dimensão mais fraca", fraca,
                (f"média {_n(dims[fraca])} nos municípios de PE", 'neutro')),
    ], contexto='Pernambuco · escala de 0 a 100')


def _mapa(ed, indicador):
    d = ds.ips_municipios(ed, indicador).copy()
    if d.empty:
        return viz.sem_dados_fig()
    d['_v'] = d['valor'].map(_n)
    d['_rk'] = [f"{int(a)}º em PE · {int(b)}º no Brasil" if a == a and b == b else '—'
                for a, b in zip(d['rank_pe'], d['rank_br'])]
    d['_rd'] = d['regiao_desenvolvimento'].fillna('—')
    return viz.fig_mapa(d, 'valor', [('RD', '_rd'), ('pontuação', '_v'), ('posição', '_rk')],
                        legenda='0 a 100')


def _ranking(ed, indicador, ordem, destaque=None):
    d = ds.ips_municipios(ed, indicador)
    fig = viz.fig_ranking(d, 'municipio', 'valor', fmt=_n, n=10,
                          crescente=(ordem == 'piores'), destaque=destaque,
                          cor=CORES['azul'] if ordem == 'melhores' else CORES['terracota'])
    return viz.grafico(fig)


def _rds(ed, indicador):
    d = ds.ips_rds(ed, indicador)
    fig = viz.fig_ranking(d, 'regiao_desenvolvimento', 'valor', fmt=_n, n=12)
    return viz.grafico(fig)


def _dispersao(ed, destaque=None):
    d = ds.ips_municipios(ed).copy()
    col_pib = 'pib_per_capita'
    if col_pib not in d:
        return viz.grafico(viz.sem_dados_fig("PIB per capita indisponível nesta edição."))
    d['_pib'] = d[col_pib].map(lambda v: viz.reais(v))
    d['_ips'] = d['valor'].map(_n)
    d['_rd'] = d['regiao_desenvolvimento'].fillna('—')
    fig = viz.fig_dispersao(d, col_pib, 'valor', 'municipio',
                            'PIB per capita (R$, escala log)', 'IPS',
                            hover=[('RD', '_rd'), ('IPS', '_ips'), ('PIB per capita', '_pib')],
                            destaque=destaque, x_log=True)
    media = ds.ips_resumo(ed)['media_pe']
    fig.add_hline(y=media, line=dict(color=CORES['cinza_claro'], width=1, dash='dot'),
                  annotation_text=f"média de PE {_n(media)}", annotation_position='top left',
                  annotation_font=dict(size=10, color='#888780'))
    return viz.grafico(fig)


def _ficha(ed, cod):
    f = ds.ips_ficha(ed, cod)
    if f.empty:
        return viz.grafico(viz.sem_dados_fig())
    f = f.iloc[::-1]
    rot = [f"<b>{i}</b>" if n in ('indice', 'dimensao') else i
           for i, n in zip(f['indicador'], f['nivel'])]
    fig = go.Figure()
    series = [('br', 'média do Brasil', COR_REGIAO['Brasil']),
              ('pe', 'média de PE', COR_REGIAO['Pernambuco'])]
    if cod:
        series = [('br', 'média do Brasil', COR_REGIAO['Brasil']),
                  ('pe', 'média de PE', '#9DB4C7'),
                  ('municipio', nome_municipio(cod), CORES['mostarda'])]
    for col, nome, cor in series:
        fig.add_trace(go.Bar(y=rot, x=f[col], name=nome, orientation='h',
                             marker=dict(color=cor),
                             hovertemplate=f'{nome}: %{{x:.1f}}<extra></extra>'))
    viz.layout_padrao(fig, altura=max(420, 30 * len(f)), legenda=True, hovermode='y unified')
    fig.update_layout(barmode='group', bargap=0.25, bargroupgap=0.05,
                      legend_traceorder='reversed')
    fig.update_xaxes(range=[0, 100], showgrid=True, gridcolor='#E5E3DE')
    fig.update_yaxes(showgrid=False, ticks='', automargin=True, tickfont=dict(size=10.5))
    filhos = [viz.grafico(fig)]
    if cod:
        ind = ds.ips_indicadores(ed, cod)
        if not ind.empty:
            ind = ind.copy()
            ind['_v'] = [f"{_n(v)}" for v in ind['valor']]
            ind['_pe'] = ind['pe'].map(_n)
            ind['_br'] = ind['br'].map(_n)
            filhos.append(viz.tabela(ind, [('indicador', 'indicador', 'esq'),
                                           ('unidade', 'unidade', 'esq'),
                                           (nome_municipio(cod), '_v', 'dir'),
                                           ('média PE', '_pe', 'dir'),
                                           ('média Brasil', '_br', 'dir')]))
    return html.Div(filhos)


def _evolucao(cod=None):
    e = ds.ips_evolucao(cod)
    x = [str(a) for a in e['edicao']]
    series = [{'y': e['br'], 'nome': 'Brasil', 'cor': COR_REGIAO['Brasil']},
              {'y': e['ne'], 'nome': 'Nordeste', 'cor': COR_REGIAO['Nordeste']},
              {'y': e['pe'], 'nome': 'Pernambuco (média)', 'cor': COR_REGIAO['Pernambuco']}]
    if cod and 'municipio' in e:
        series.append({'y': e['municipio'], 'nome': nome_municipio(cod), 'cor': CORES['mostarda']})
    fig = viz.fig_barras_series(x, series, altura=300, hover_fmt=',.1f')
    vals = [v for s in series for v in s['y'] if v == v and v is not None]
    if vals:
        fig.update_yaxes(range=[max(0, min(vals) - 8), min(100, max(vals) + 4)])
    return viz.grafico(fig)


def layout():
    if not ds.ips_disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Indicadores Sociais", "Progresso social"),
            viz.aviso("Os dados do IPS ainda não foram gerados. Salve os arquivos do "
                      "IPS Brasil em data/raw/ips/ e rode o ETL:", "python -m etl.run_all"),
        ])
    eds = ds.edicoes()
    ed = eds[0]
    ops = ds.opcoes_indicadores()
    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Indicadores Sociais",
                       f"Progresso social · Índice de Progresso Social (IPS Brasil) · 185 "
                       f"municípios · edições {eds[-1]}—{ed}",
                       dica="clique em um município no mapa para ver a ficha dele",
                       botao_limpar='ips-limpar'),
        dcc.Store(id='ips-sel', data=None),
        viz.linha_filtros(
            viz.filtro("EDIÇÃO:", viz.dropdown('ips-ed', eds, ed)),
            viz.filtro("INDICADOR:", viz.dropdown('ips-ind', ops, ds.INDICE, busca=True),
                       largo=True),
        ),
        html.Div(id='ips-kpis', children=_kpis(ed)),
        viz.secao("mapa", "pontuação de 0 a 100 · quanto mais escuro, melhor",
                  dcc.Graph(id='ips-mapa', figure=_mapa(ed, ds.INDICE), config=viz.GRAPH_CONFIG)),
        viz.grade(
            viz.secao("ranking municipal", "10 maiores ou 10 menores pontuações",
                      viz.botoes('ips-rank-ordem', [('maiores', 'melhores'),
                                                    ('menores', 'piores')], 'melhores'),
                      html.Div(id='ips-ranking', children=_ranking(ed, ds.INDICE, 'melhores'))),
            viz.secao("regiões de desenvolvimento", "média dos municípios de cada RD",
                      html.Div(id='ips-rds', children=_rds(ed, ds.INDICE))),
        ),
        viz.grade(
            viz.secao("riqueza e qualidade de vida",
                      "PIB per capita x IPS · cada ponto é um município",
                      html.Div(id='ips-disp', children=_dispersao(ed))),
            viz.secao("evolução", "IPS por edição · as edições não são estritamente "
                      "comparáveis",
                      html.Div(id='ips-evol', children=_evolucao())),
        ),
        viz.secao("ficha", "dimensões e componentes · município clicado x médias de PE e "
                  "do Brasil",
                  html.Div(id='ips-ficha', children=_ficha(ed, None))),
        viz.nota("Como ler: o IPS vai de 0 a 100 e usa só resultados sociais e ambientais "
                 "(sem renda). As médias de PE, do Nordeste e do Brasil são médias simples "
                 "dos municípios. A própria fonte avisa que as edições 2024, 2025 e 2026 "
                 "não são estritamente comparáveis, por mudanças de indicadores e de "
                 "tratamento estatístico. Para incluir uma edição nova, salve o XLSX do IPS "
                 "Brasil em data/raw/ips/ e rode o ETL."),
        ui.footer(fonte_principal="IPS Brasil · Índice de Progresso Social "
                                  "(ipsbrasil.org.br)",
                  atualizacao=str(ed)),
    ])


def callbacks(app):

    @app.callback(Output('ips-sel', 'data'),
                  Input('ips-mapa', 'clickData'), Input('ips-limpar', 'n_clicks'),
                  State('ips-sel', 'data'), prevent_initial_call=True)
    def selecionar(click, _n, atual):
        if ctx.triggered_id == 'ips-limpar':
            return None
        if click:
            try:
                cod = int(str(click['points'][0]['location']))
            except (KeyError, TypeError, ValueError):
                return no_update
            return None if cod == atual else cod
        return no_update

    @app.callback(Output('ips-limpar', 'className'), Input('ips-sel', 'data'))
    def botao(cod):
        return 'btn-link' if cod else 'btn-link hidden'

    @app.callback(Output('ips-kpis', 'children'), Output('ips-mapa', 'figure'),
                  Output('ips-rds', 'children'),
                  Input('ips-ed', 'value'), Input('ips-ind', 'value'))
    def principal(ed, ind):
        if not ed or not ind:
            return no_update, no_update, no_update
        return _kpis(ed), _mapa(ed, ind), _rds(ed, ind)

    @app.callback(Output('ips-ranking', 'children'), Output('ips-disp', 'children'),
                  Output('ips-ficha', 'children'), Output('ips-evol', 'children'),
                  Input('ips-ed', 'value'), Input('ips-ind', 'value'),
                  Input('ips-rank-ordem', 'value'), Input('ips-sel', 'data'))
    def detalhe(ed, ind, ordem, cod):
        if not ed or not ind:
            return no_update, no_update, no_update, no_update
        dest = nome_municipio(cod) if cod else None
        return (_ranking(ed, ind, ordem or 'melhores', dest), _dispersao(ed, dest),
                _ficha(ed, cod), _evolucao(cod))
