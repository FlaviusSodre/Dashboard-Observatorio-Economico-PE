"""
app.py
======
Aplicação principal do Observatório Econômico de Pernambuco.

Este arquivo é deliberadamente curto. A maior parte do trabalho está em:
- config.py (paleta, caminhos, metadados)
- components/ (UI e gráficos reutilizáveis)
- tabs/ (cada arquivo é uma aba auto-registrada)

Para rodar:
    python app.py

Depois abra http://127.0.0.1:8050 no navegador.

Para adicionar novas abas, copie tabs/_template.py e implemente.
A aba aparece sozinha no menu.
"""

from datetime import datetime

from dash import Dash, Input, Output, dcc, html

import tabs
from tabs import home as tab_home
from components import data, ui
from config import META

# ============================================================================
# Inicialização do app
# ============================================================================

app = Dash(
    __name__,
    title=f"{META['titulo']} · Observatório Econômico",
    update_title=None,  # remove o "Updating..." do title bar
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport",
         "content": "width=device-width, initial-scale=1.0, viewport-fit=cover"},
        {"name": "theme-color", "content": "#5B7B9A"},
        {"name": "mobile-web-app-capable", "content": "yes"},
        {"name": "apple-mobile-web-app-capable", "content": "yes"},
        {"name": "apple-mobile-web-app-status-bar-style", "content": "default"},
        {"name": "apple-mobile-web-app-title", "content": "Observatório PE"},
        {"name": "description",
         "content": "Observatório Econômico de Pernambuco — indicadores econômicos em dados."},
    ],
)

# Necessário para deploy em produção (gunicorn, render, etc)
server = app.server

# PWA: injeta link do manifest e registro do service worker
app.index_string = '''<!DOCTYPE html>
<html lang="pt-BR">
  <head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    <link rel="manifest" href="/assets/manifest.json">
    <link rel="apple-touch-icon" href="/assets/Icone_App_2.png">
    {%css%}
  </head>
  <body>
    {%app_entry%}
    <footer>
      {%config%}
      {%scripts%}
      {%renderer%}
    </footer>
    <script>
      if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js')
          .catch(function(err) { console.warn('SW:', err); });
      }
    </script>
  </body>
</html>
'''

# PWA: serve o service worker na raiz (escopo global /sw.js)
import os as _os
from flask import send_from_directory as _send_from_directory

@server.route('/sw.js')
def _serve_sw():
    root = _os.path.dirname(__file__)
    return _send_from_directory(
        _os.path.join(root, 'assets'), 'sw.js',
        mimetype='application/javascript'
    )


# ============================================================================
# Descobre as abas dinamicamente
# ============================================================================
# Esta lista é construída em tempo de inicialização lendo a pasta tabs/.
# Para adicionar uma aba nova, basta criar o arquivo - este código não muda.

EIXOS = tabs.listar_eixos()
ABAS_TODAS = tabs.descobrir_abas()

# ABAS sem a Home - usado para navegação real do dashboard.
# A Home é uma aba especial: tem layout estático no DOM e nunca aparece
# na lista de abas "reais".
ABAS = [a for a in ABAS_TODAS if a['eixo'] != '__home__']


# ============================================================================
# Componente de navegação (eixos + sub-abas)
# ============================================================================

def construir_nav_eixos(eixo_ativo: str):
    """Constrói a barra superior de eixos."""
    # "Home" é o primeiro item — clicável, leva à capa
    home_ativo = eixo_ativo == '__home__'
    items = [html.A(
        "Home",
        id={'type': 'nav-eixo', 'index': '__home__'},
        n_clicks=0,
        className=f"nav-eixo nav-home {'ativo' if home_ativo else ''}",
    )]

    for eixo in EIXOS:
        # Pular eixo interno __home__ (não aparece no loop)
        if eixo['nome'] == '__home__':
            continue
        ativo = eixo['nome'] == eixo_ativo
        items.append(html.A(
            eixo['nome'],
            id={'type': 'nav-eixo', 'index': eixo['nome']},
            n_clicks=0,
            className=f"nav-eixo {'ativo' if ativo else ''}",
        ))

    return html.Nav(className="nav-eixos", children=items)


def construir_nav_subs(eixo_ativo: str, sub_ativa: str):
    """Constrói os chips de sub-abas para o eixo ativo."""
    subs = [a for a in ABAS if a['eixo'] == eixo_ativo]

    items = []
    for sub in subs:
        ativa = sub['sub'] == sub_ativa
        fonte = sub.get('fonte_legenda', '')
        items.append(html.A(
            children=[
                sub['sub'],
                html.Span(fonte, className="nav-sub-fonte") if fonte else "",
            ],
            id={'type': 'nav-sub', 'index': sub['id']},
            n_clicks=0,
            className=f"nav-sub {'ativo' if ativa else ''}",
        ))

    return html.Div(className="nav-subs", children=items)


def construir_mobile_menu():
    """Conteúdo do drawer de navegação mobile."""
    items = [
        html.Div(className='mobile-menu-header', children=[
            html.Span('Navegação', className='mobile-menu-titulo'),
            html.Button('✕', id='btn-mobile-fechar',
                        className='btn-mobile-fechar', n_clicks=0),
        ]),
        html.A('Home',
               id={'type': 'mobile-nav-eixo', 'index': '__home__'},
               n_clicks=0, className='mobile-nav-home'),
    ]
    for eixo in EIXOS:
        if eixo['nome'] == '__home__':
            continue
        items.append(html.Div(eixo['nome'], className='mobile-nav-grupo'))
        for sub in [a for a in ABAS if a['eixo'] == eixo['nome']]:
            fonte = sub.get('fonte_legenda', '')
            items.append(html.A(
                children=[
                    sub['sub'],
                    html.Span(f' · {fonte}', className='mobile-nav-fonte') if fonte else '',
                ],
                id={'type': 'mobile-nav-sub', 'index': sub['id']},
                n_clicks=0, className='mobile-nav-sub',
            ))
    return items


# ============================================================================
# Layout principal
# ============================================================================

def construir_layout():
    """Layout estático do app. As mudanças de aba acontecem via callback."""
    aba_inicial_id = '__home__'
    eixo_inicial = '__home__'

    try:
        ultima = data.caged_municipal()['data'].max()
        atualizado_em = ultima.strftime("%b · %Y").lower()
    except Exception:
        atualizado_em = "—"

    return html.Div(className="app-shell", children=[
        # Header global
        ui.header(
            titulo=META['titulo'],
            sobretitulo=META['sobretitulo'],
            orgao=META['orgao'],
            atualizado_em=atualizado_em,
        ),

        # Overlay escuro do menu mobile
        html.Div(id='mobile-overlay', className='mobile-overlay', n_clicks=0),

        # Drawer lateral de navegação mobile
        html.Div(
            id='mobile-menu-container',
            className='mobile-menu',
            children=construir_mobile_menu(),
        ),

        # Navegação desktop — dois níveis (oculta na Home)
        html.Div(
            id='nav-container',
            style={'display': 'none'},
            children=[
                # Barra hambúrguer (visível apenas em mobile)
                html.Div(
                    className='mobile-hamburger-bar',
                    children=[
                        html.Button(
                            id='btn-hamburger',
                            className='btn-hamburger',
                            n_clicks=0,
                            children=[
                                html.Span(className='hamburger-linha'),
                                html.Span(className='hamburger-linha'),
                                html.Span(className='hamburger-linha'),
                            ],
                        )
                    ],
                ),
                construir_nav_eixos(eixo_inicial),
                construir_nav_subs(eixo_inicial, ''),
            ]
        ),

        # Store guarda qual aba está ativa
        dcc.Store(id='aba-ativa', data=aba_inicial_id),

        # Location (URL) para compatibilidade
        dcc.Location(id='url', refresh=False),

        # HOME estática no layout — sempre presente no DOM
        html.Div(
            id='home-container',
            children=tab_home.layout(),
        ),

        # Container do conteúdo das outras abas (oculto na Home)
        html.Div(
            id='conteudo-aba',
            style={'display': 'none'},
        ),
    ])


app.layout = construir_layout


# ============================================================================
# Callbacks de navegação
# ============================================================================

from dash import ALL, ctx, State


@app.callback(
    Output('aba-ativa', 'data'),
    Output('nav-container', 'children'),
    Output('nav-container', 'style'),
    Output('home-container', 'style'),
    Output('conteudo-aba', 'children'),
    Output('conteudo-aba', 'style'),
    Output('mobile-menu-container', 'className'),
    Output('mobile-overlay', 'className'),
    Input({'type': 'nav-sub',        'index': ALL}, 'n_clicks'),
    Input({'type': 'nav-eixo',       'index': ALL}, 'n_clicks'),
    Input({'type': 'mobile-nav-sub', 'index': ALL}, 'n_clicks'),
    Input({'type': 'mobile-nav-eixo','index': ALL}, 'n_clicks'),
    Input('btn-entrar',           'n_clicks'),
    Input('btn-hamburger',        'n_clicks'),
    Input('btn-mobile-fechar',    'n_clicks'),
    Input('mobile-overlay',       'n_clicks'),
    Input('btn-home-header-mobile','n_clicks'),
    State('mobile-menu-container', 'className'),
    prevent_initial_call=True,
)
def navegar(_cs, _ce, _mcs, _mce, _entrar, _ham, _fechar, _ovl, _home_mob,
            menu_class):
    """
    Gerencia navegação desktop e mobile.

    Outputs 1-6: lógica de aba existente (inalterada).
    Output 7: classe CSS do drawer mobile ('mobile-menu' | 'mobile-menu aberto').
    Output 8: classe CSS do overlay ('mobile-overlay' | 'mobile-overlay visivel').
    """
    from dash import no_update
    triggered = ctx.triggered_id

    STYLE_VISIVEL = {'display': 'block'}
    STYLE_OCULTO  = {'display': 'none'}
    MENU_ABERTO   = 'mobile-menu aberto'
    MENU_FECHADO  = 'mobile-menu'
    OVL_VISIVEL   = 'mobile-overlay visivel'
    OVL_OCULTO    = 'mobile-overlay'

    def nav_para_aba(aba):
        nav = [
            html.Div(
                className='mobile-hamburger-bar',
                children=[html.Button(
                    id='btn-hamburger', className='btn-hamburger', n_clicks=0,
                    children=[html.Span(className='hamburger-linha')] * 3,
                )],
            ),
            construir_nav_eixos(aba['eixo']),
            construir_nav_subs(aba['eixo'], aba['sub']),
        ]
        return nav

    # --- Hambúrguer: toggle abrir/fechar ---
    if triggered == 'btn-hamburger':
        aberto = MENU_ABERTO not in (menu_class or '')
        return ([no_update] * 6
                + [MENU_ABERTO if aberto else MENU_FECHADO,
                   OVL_VISIVEL if aberto else OVL_OCULTO])

    # --- Fechar drawer sem navegar ---
    if triggered in ('btn-mobile-fechar', 'mobile-overlay'):
        return [no_update] * 6 + [MENU_FECHADO, OVL_OCULTO]

    # --- Home pelo link do header mobile ---
    if triggered == 'btn-home-header-mobile':
        return (no_update, no_update,
                STYLE_OCULTO, STYLE_VISIVEL,
                no_update, STYLE_OCULTO,
                MENU_FECHADO, OVL_OCULTO)

    # --- Botão "Acessar o Observatório" da capa ---
    if triggered == 'btn-entrar':
        aba = ABAS[0]
        return (aba['id'], nav_para_aba(aba),
                STYLE_VISIVEL, STYLE_OCULTO,
                aba['module'].layout(), STYLE_VISIVEL,
                MENU_FECHADO, OVL_OCULTO)

    # --- Cliques em itens de navegação (desktop e mobile) ---
    if isinstance(triggered, dict):
        tipo = triggered.get('type')

        if tipo in ('nav-eixo', 'mobile-nav-eixo'):
            eixo_clicado = triggered['index']
            if eixo_clicado == '__home__':
                return (no_update, no_update,
                        STYLE_OCULTO, STYLE_VISIVEL,
                        no_update, STYLE_OCULTO,
                        MENU_FECHADO, OVL_OCULTO)
            primeiras = [a for a in ABAS if a['eixo'] == eixo_clicado]
            if not primeiras:
                return [no_update] * 6 + [MENU_FECHADO, OVL_OCULTO]
            aba_id = primeiras[0]['id']

        elif tipo in ('nav-sub', 'mobile-nav-sub'):
            aba_id = triggered['index']

        else:
            return [no_update] * 6 + [no_update, no_update]
    else:
        return [no_update] * 6 + [no_update, no_update]

    aba = tabs.aba_por_id(aba_id)
    if aba is None:
        return [no_update] * 6 + [no_update, no_update]

    return (aba['id'], nav_para_aba(aba),
            STYLE_VISIVEL, STYLE_OCULTO,
            aba['module'].layout(), STYLE_VISIVEL,
            MENU_FECHADO, OVL_OCULTO)


# ============================================================================
# Registrar callbacks de cada aba
# ============================================================================

for aba in ABAS:
    if hasattr(aba['module'], 'callbacks'):
        aba['module'].callbacks(app)


# ============================================================================
# Run
# ============================================================================

if __name__ == '__main__':
    import os

    # DEBUG controlável via variável de ambiente.
    # Em desenvolvimento: `DASH_DEBUG=1 python app.py` ativa o devtools.
    # Em produção (default): roda sem o painel de debug.
    debug = os.environ.get('DASH_DEBUG', '0') == '1'

    print()
    print("=" * 60)
    print(f"  {META['titulo']} · Observatório Econômico")
    print(f"  {META['orgao']}")
    print("=" * 60)
    print(f"  Abas registradas: {len(ABAS)}")
    for aba in ABAS:
        print(f"    · {aba['eixo']} > {aba['sub']}")
    print()
    print("  Servidor: http://127.0.0.1:8050")
    print(f"  Debug: {'ON' if debug else 'OFF'}"
          f"{' (DASH_DEBUG=1 para ativar)' if not debug else ''}")
    print("  (Ctrl+C para parar)")
    print("=" * 60)
    print()

    #app.run(debug=debug, host='127.0.0.1', port=8050)
    app.run(debug=debug, host="0.0.0.0", port=int(os.environ.get("PORT", 8050)))