"""
tabs/atividade_economica_agropecuaria.py
========================================
Sub-aba Agropecuária (Atividade Econômica): lavouras (PAM), estimativas
de safra (LSPA) e pecuária (PPM) de Pernambuco.

Estrutura:
1. KPIs: valor da produção agrícola, produto líder, safra de grãos
   estimada, leite e rebanho de caprinos e ovinos
2. Principais lavouras (valor) e evolução de um produto
3. Mapa municipal de um produto agrícola
4. Safra do ano em curso (LSPA) e pecuária por município

Fonte: IBGE · PAM (SIDRA 5457), LSPA (6588), PPM (3939 e 74).
"""

import plotly.graph_objects as go
from dash import Input, Output, dcc, html, no_update

from components import data_atividade as da, ui, viz
from components.viz import CORES, moeda, num, pct

_PECUARIA = [('Bovinos', 'Bovinos'), ('Caprinos', 'Caprinos'), ('Ovinos', 'Ovinos'),
             ('Suínos', 'Suínos'), ('Galináceos', 'Galináceos'),
             ('Leite (mil litros)', 'Leite'), ('Ovos de galinha (mil dúzias)', 'Ovos de galinha'),
             ('Mel de abelha (kg)', 'Mel de abelha')]


def registrar():
    return {
        'eixo': 'Atividade Econômica',
        'sub': 'Agropecuária',
        'eixo_ordem': 4,
        'sub_ordem': 4,
        'ativa': True,
        'fonte_legenda': 'PAM · LSPA · PPM · IBGE',
    }


# ============================================================================
# KPIs
# ============================================================================

def _kpis():
    ano = da.pam_anos()[0]
    tot, tot_ant = da.pam_total(ano), da.pam_total(ano - 1)
    var = 100 * (tot / tot_ant - 1) if tot_ant else None
    est = da.pam_estado(ano)
    lider = est.iloc[0] if len(est) else None
    kpis = [
        viz.kpi(f"valor das lavouras · {ano}", moeda(tot),
                viz.variacao(var, f"vs {ano - 1} (nominal)"), destaque=True),
        viz.kpi("principal lavoura", lider['produto'] if lider is not None else '—',
                (f"{moeda(lider['valor_mil'] * 1000)} · {pct(lider['part_pct'])} do total",
                 'neutro') if lider is not None else None),
    ]
    ls = da.lspa_resumo()
    graos = ls[ls['produto'].str.startswith('Cereais')] if not ls.empty else ls
    if len(graos):
        g = graos.iloc[0]
        kpis.append(viz.kpi(f"safra de grãos {g['data'].year}",
                            f"{num(g['atual'] / 1000, 1)} mil t",
                            viz.variacao(g['var_pct'], f"vs {g['data'].year - 1} · "
                                         f"estimativa de {viz.mes_ano(g['data'])}")))
    else:
        kpis.append(viz.kpi("safra de grãos", '—'))
    anos_ppm = da.ppm_anos()
    if anos_ppm:
        a = anos_ppm[0]
        p, p_ant = da.ppm_estado(a), da.ppm_estado(a - 1)

        def q(df, prod):
            s = df.loc[df['produto'] == prod, 'quantidade']
            return float(s.sum()) if len(s) else None
        leite, leite_ant = q(p, 'Leite'), q(p_ant, 'Leite')
        kpis.append(viz.kpi(f"leite · {a}", f"{num(leite / 1e3, 0)} mi litros" if leite else '—',
                            viz.variacao(100 * (leite / leite_ant - 1) if leite and leite_ant else None,
                                         f"vs {a - 1}")))
        cap = (q(p, 'Caprinos') or 0) + (q(p, 'Ovinos') or 0)
        cap_ant = (q(p_ant, 'Caprinos') or 0) + (q(p_ant, 'Ovinos') or 0)
        kpis.append(viz.kpi(f"caprinos e ovinos · {a}", f"{num(cap / 1e6, 2)} mi cabeças",
                            viz.variacao(100 * (cap / cap_ant - 1) if cap_ant else None,
                                         f"vs {a - 1}")))
    return viz.faixa_kpis(kpis, contexto='Pernambuco')


# ============================================================================
# Lavouras
# ============================================================================

def _lavouras(ano: int):
    est = da.pam_estado(ano).head(12)
    if est.empty:
        return viz.grafico(viz.sem_dados_fig())
    est = est.assign(valor=est['valor_mil'] * 1000,
                     _txt=[f"{moeda(v * 1000)} · {pct(p)}" for v, p in
                           zip(est['valor_mil'], est['part_pct'])])
    fig = viz.fig_ranking(est, 'produto', 'valor', fmt=moeda, n=12,
                          cor=CORES['verde'], hover_extra='_txt')
    return viz.grafico(fig)


def _evolucao_produto(produto: str):
    s = da.pam_serie(produto)
    if s.empty:
        return viz.grafico(viz.sem_dados_fig())
    fig = viz.fig_barras(s['ano'].astype(str), s['valor_mil'] * 1000, cor=CORES['verde'],
                         altura=260)
    div, suf = viz.escala_monetaria((s['valor_mil'] * 1000).max())
    fig.data[0].y = (s['valor_mil'] * 1000 / div).tolist()
    fig.data[0].customdata = [moeda(v * 1000) for v in s['valor_mil']]
    fig.data[0].hovertemplate = '%{x}: %{customdata}<extra></extra>'
    fig.update_yaxes(tickprefix='R$ ', ticksuffix=suf)
    q = s.dropna(subset=['quantidade_t'])
    extra = []
    if len(q):
        ult = q.iloc[-1]
        extra = [viz.nota(f"{produto} em {int(ult['ano'])}: {num(ult['quantidade_t'])} "
                          f"toneladas em {num(ult.get('area_colhida_ha'))} hectares "
                          "colhidos. Valores nominais.")]
    return html.Div([viz.grafico(fig)] + extra)


def _mapa_lavoura(ano: int, produto: str):
    d = da.pam_municipios(ano, produto)
    d = d[d['valor_mil'] > 0].copy()
    if d.empty:
        return viz.sem_dados_fig("Sem produção municipal para esta seleção.")
    d['_v'] = (d['valor_mil'] * 1000).map(moeda)
    d['_q'] = d['quantidade_t'].map(lambda v: f"{num(v)} t") if 'quantidade_t' in d else '—'
    d['_p'] = d['part_pct'].map(lambda v: pct(v, 2))
    d['_rd'] = d['regiao_desenvolvimento'].fillna('—')
    hover = [('RD', '_rd'), ('valor da produção', '_v'), ('quantidade', '_q'),
             ('% do estado', '_p')]
    return viz.fig_mapa(d, 'valor_mil', hover, legenda='R$ mil')


# ============================================================================
# Safra e pecuária
# ============================================================================

def _lspa():
    ls = da.lspa_resumo()
    if ls.empty:
        return viz.aviso("Estimativas de safra indisponíveis.")
    ls = ls[~ls['produto'].str.startswith('Cereais')]
    d = ls.copy()
    d['_atual'] = d['atual'].map(lambda v: f"{num(v)} t")
    d['_ant'] = d['anterior'].map(lambda v: f"{num(v)} t")
    d['_var'] = d['var_pct'].map(lambda v: pct(v, sinal=True))
    ano = d['data'].iloc[0].year
    tab = viz.tabela(d, [('produto', 'produto', 'esq'),
                         (f'estimativa {ano}', '_atual', 'dir'),
                         (f'{ano - 1} (dez.)', '_ant', 'dir'),
                         ('variação', '_var', 'dir')])
    return html.Div([tab, viz.nota(
        f"Estimativa de {viz.mes_ano(d['data'].iloc[0])} para a safra de {ano}, "
        f"contra a estimativa de {viz.mes_ano(d['data_ant'].iloc[0])} para {ano - 1} "
        "(Levantamento Sistemático da Produção Agrícola).")])


def _mapa_pecuaria(ano: int, produto: str):
    d = da.ppm_municipios(ano, produto)
    d = d[d['quantidade'] > 0].copy()
    if d.empty:
        return viz.sem_dados_fig()
    un = d['unidade'].iloc[0]
    d['_q'] = d['quantidade'].map(lambda v: f"{num(v)} {un}")
    d['_p'] = d['part_pct'].map(lambda v: pct(v, 2))
    d['_rd'] = d['regiao_desenvolvimento'].fillna('—')
    return viz.fig_mapa(d, 'quantidade', [('RD', '_rd'), ('quantidade', '_q'),
                                          ('% do estado', '_p')], legenda=un,
                        altura=380, zoom=5.9)


def _serie_pecuaria(produto: str):
    s = da.ppm_serie(produto)
    if s.empty:
        return viz.grafico(viz.sem_dados_fig())
    un = s['unidade'].iloc[0]
    fig = viz.fig_barras(s['ano'].astype(str), s['quantidade'], cor=CORES['verde'],
                         altura=340, hover_fmt=',.0f', y_sufixo=f' {un}')
    fig.update_yaxes(ticksuffix='', tickformat=',.0f')
    return html.Div([viz.grafico(fig),
                     viz.nota(f"{produto} em Pernambuco, por ano ({un}).")])


# ============================================================================
# Layout
# ============================================================================

def layout():
    if not da.agro_disponivel():
        return html.Div(className="aba-conteudo", children=[
            viz.titulo_aba("Atividade Econômica", "Agropecuária"),
            viz.aviso("Os dados da agropecuária ainda não foram gerados. Rode o ETL:",
                      "python -m etl.run_all"),
        ])
    anos = da.pam_anos()
    ano = anos[0]
    produtos = da.pam_produtos_municipais()
    est = da.pam_estado(ano)
    produto_def = est['produto'].iloc[0] if len(est) else produtos[0]
    anos_ppm = da.ppm_anos()

    return html.Div(className="aba-conteudo", children=[
        viz.titulo_aba("Atividade Econômica",
                       f"Agropecuária · lavouras, safra e pecuária de Pernambuco · "
                       f"{anos[-1]}—{ano}"),
        _kpis(),

        viz.grade(
            viz.secao("principais lavouras",
                      f"valor da produção em {ano} · 12 maiores",
                      _lavouras(ano)),
            viz.secao("safra do ano", "estimativas de produção do IBGE para o ano em curso",
                      _lspa()),
        ),

        viz.secao("evolução de um produto", "valor da produção por ano (nominal)",
                  viz.linha_filtros(viz.filtro("PRODUTO:", viz.dropdown(
                      'agro-prod', [p for p in produtos if p != 'Total (todas as lavouras)'],
                      produto_def, busca=True), largo=True)),
                  html.Div(id='agro-prod-serie', children=_evolucao_produto(produto_def))),

        viz.secao(
            "lavouras por município",
            "valor da produção agrícola municipal · escolha o produto e o ano",
            viz.linha_filtros(
                viz.filtro("PRODUTO:", viz.dropdown('agro-mapa-prod', produtos,
                                                    'Total (todas as lavouras)', busca=True),
                           largo=True),
                viz.filtro("ANO:", viz.dropdown('agro-mapa-ano', anos, ano)),
            ),
            dcc.Graph(id='agro-mapa', figure=_mapa_lavoura(ano, 'Total (todas as lavouras)'),
                      config=viz.GRAPH_CONFIG),
        ),

        viz.secao(
            "pecuária", "rebanhos e produção de origem animal: mapa municipal no ano "
            "escolhido e evolução no estado",
            viz.linha_filtros(
                viz.filtro("PRODUTO:", viz.dropdown('agro-pec', _PECUARIA, 'Caprinos'),
                           largo=True),
                viz.filtro("ANO:", viz.dropdown('agro-pec-ano', anos_ppm,
                                                anos_ppm[0] if anos_ppm else None)),
            ),
            viz.grade(
                dcc.Graph(id='agro-pec-mapa', figure=_mapa_pecuaria(anos_ppm[0], 'Caprinos')
                          if anos_ppm else viz.sem_dados_fig(), config=viz.GRAPH_CONFIG),
                html.Div(id='agro-pec-serie', children=_serie_pecuaria('Caprinos')),
                proporcao='2-1',
            ),
        ),

        viz.nota("Como ler: o valor da produção é nominal (em reais de cada ano). "
                 "A PAM e a PPM saem uma vez por ano, com cerca de nove meses de "
                 "defasagem; o LSPA é revisto todo mês ao longo da safra."),
        ui.footer(fonte_principal="IBGE · Produção Agrícola Municipal, Levantamento "
                                  "Sistemático da Produção Agrícola e Pesquisa da "
                                  "Pecuária Municipal",
                  atualizacao=str(ano)),
    ])


def callbacks(app):

    @app.callback(Output('agro-prod-serie', 'children'), Input('agro-prod', 'value'))
    def produto(p):
        return _evolucao_produto(p) if p else no_update

    @app.callback(Output('agro-mapa', 'figure'),
                  Input('agro-mapa-prod', 'value'), Input('agro-mapa-ano', 'value'))
    def mapa(p, ano):
        if not p or not ano:
            return no_update
        return _mapa_lavoura(ano, p)

    @app.callback(Output('agro-pec-mapa', 'figure'), Output('agro-pec-serie', 'children'),
                  Input('agro-pec', 'value'), Input('agro-pec-ano', 'value'))
    def pecuaria(p, ano):
        if not p or not ano:
            return no_update, no_update
        return _mapa_pecuaria(ano, p), _serie_pecuaria(p)
