"""
config.py
=========
Configuração central do Observatório Econômico de Pernambuco.

Tudo que é "decisão visual" ou "caminho" mora aqui. Isso é importante
porque permite mudar a paleta inteira do dashboard, ou trocar a pasta
de dados, sem mexer em nenhum outro arquivo.

Organização:
    PALETTE     -> cores da identidade visual
    SEMANTIC    -> cores com significado (positivo, negativo, neutro)
    PATHS       -> caminhos do sistema de arquivos
    META        -> metadados institucionais
    CHART       -> defaults para gráficos Plotly
"""

from pathlib import Path

# ============================================================================
# PALETA DE CORES - identidade visual do observatório
# ============================================================================
# Paleta sóbria e pastel definida pelo usuário, organizada em grupos.
# A regra de uso: neutros são a base (use generosamente), acentos frios
# são para o destaque principal (apenas 1 por gráfico), acentos quentes
# para contraste/segundo destaque.

PALETTE = {
    # neutros - base do design
    "grafite": "#3A3A3A",       # texto principal
    "cinza_medio": "#7A7A7A",   # texto secundário, eixos
    "cinza_claro": "#B8B8B8",   # bordas, dividers
    "cinza_neblina": "#E5E3DE", # bordas sutis, fundos secundários
    "bege_fundo": "#F5F3EE",    # fundo principal do app (não branco puro)
    "branco": "#FFFFFF",        # cartões, superfícies elevadas
    "preto_titulo": "#2C2C2A",  # títulos editoriais (mais escuro que grafite)

    # acentos frios - destaque principal
    "azul_ardosia": "#5B7B9A",      # ★ cor primária do observatório
    "azul_empoeirado": "#9DB4C7",   # secundário do mesmo gradiente
    "verde_salvia": "#8FA897",      # variações positivas
    "lilas_acinzentado": "#A8A0B5", # marcações editoriais (anotações)

    # acentos quentes - contraste e segundo destaque
    "terracota": "#C99383",         # série secundária, valores negativos suaves
    "rosa_empoeirado": "#D4A5A5",   # alternativa quente clara
    "mostarda_suave": "#D4BC8B",    # gradiente do mapa (faixa intermediária)
    "bege_quente": "#B9B098",       # gradiente do mapa (faixa intermediária)
}

# ============================================================================
# CORES SEMÂNTICAS - quando a cor precisa carregar significado
# ============================================================================
# Em vez de espalhar "verde salvia" pelo código quando queremos dizer
# "positivo", referenciamos por significado. Se um dia trocarmos a cor
# de positivo, mudamos só aqui.

SEMANTIC = {
    "positivo": PALETTE["verde_salvia"],
    "negativo": PALETTE["terracota"],
    "neutro": PALETTE["cinza_medio"],
    "destaque": PALETTE["azul_ardosia"],
    "destaque_suave": PALETTE["azul_empoeirado"],
    "anotacao": PALETTE["lilas_acinzentado"],
}

# Escala sequencial para o coroplético do mapa de PE.
# Vai do mais claro (menor saldo) ao mais escuro (maior saldo).
# Usar tons frios para valores positivos é uma convenção do observatório.
MAPA_ESCALA_POSITIVA = [
    [0.0, PALETTE["cinza_neblina"]],
    [0.25, PALETTE["mostarda_suave"]],
    [0.5, PALETTE["bege_quente"]],
    [0.75, PALETTE["azul_empoeirado"]],
    [1.0, PALETTE["azul_ardosia"]],
]

# Escala divergente quando há valores positivos E negativos
# (negativos em terracota, positivos em azul, neutro no bege neblina)
MAPA_ESCALA_DIVERGENTE = [
    [0.0, PALETTE["terracota"]],
    [0.5, PALETTE["cinza_neblina"]],
    [1.0, PALETTE["azul_ardosia"]],
]

# ============================================================================
# CAMINHOS - sistema de arquivos
# ============================================================================
# Path(__file__) é o caminho deste arquivo config.py.
# .parent dá a pasta que contém ele (raiz do projeto).
# Construindo a partir daqui, o projeto funciona em qualquer máquina,
# em qualquer sistema operacional, sem caminhos absolutos hardcoded.

ROOT = Path(__file__).parent
DATA_RAW = ROOT / "data" / "raw"          # arquivos originais (xlsx)
DATA_PROCESSED = ROOT / "data" / "processed"  # parquets prontos para uso
DATA_GEO = ROOT / "data" / "geo"          # geojsons
ASSETS = ROOT / "assets"                  # logos, css

# Arquivos de dados específicos
CAGED_RAW = DATA_RAW / "CAGED_PE.xlsx"
#PNAD_RAW = DATA_RAW / "PNAD_PE.xlsx"
PNAD_REGIONAL_RAW_DIR = DATA_RAW / "pnad_regional"

CAGED_MUNICIPAL = DATA_PROCESSED / "caged_municipal.parquet"
CAGED_GENERO = DATA_PROCESSED / "caged_genero.parquet"
CAGED_SETOR = DATA_PROCESSED / "caged_setor.parquet"
PNAD_PE = DATA_PROCESSED / "pnad_pe.parquet"
PNAD_REGIONAL = DATA_PROCESSED / "pnad_regional.parquet"
POBREZA_REGIONAL = DATA_PROCESSED / "pobreza_regional.parquet"
MUNICIPIOS_RD = DATA_PROCESSED / "municipios_rd.parquet"
PREFEITOS = DATA_PROCESSED / "prefeitos.parquet"
VEREADORES = DATA_PROCESSED / "vereadores.parquet"
PIB_MUNICIPAL = DATA_PROCESSED / "pib_municipal.parquet"
GEO_MUNICIPIOS = DATA_GEO / "pe_municipios.geojson"
CATALOGO = DATA_PROCESSED / "catalogo.json"

# Versão 2.0 ----------------------------------------------------------------
# Downloads automáticos (APIs do IBGE, BCB, Comex Stat, Tesouro e SDS-PE)
# ficam em data/cache/, fora do git. O ETL lê dali quando roda com --offline
# ou quando uma fonte está fora do ar.
DATA_CACHE = ROOT / "data" / "cache"

POPULACAO_MUNICIPAL = DATA_PROCESSED / "populacao_municipal.parquet"

# Gestão Pública: transferências constitucionais (STN)
TRANSFERENCIAS_PE = DATA_PROCESSED / "transferencias_pe.parquet"

# Atividade Econômica
ATIVIDADE_MENSAL = DATA_PROCESSED / "atividade_mensal.parquet"
PIB_TRIMESTRAL = DATA_PROCESSED / "pib_trimestral.parquet"
PIB_TRIMESTRAL_RAW = DATA_RAW / "pib_trimestral_pe.csv"
AGRO_LSPA = DATA_PROCESSED / "agro_lspa.parquet"
AGRO_PAM = DATA_PROCESSED / "agro_pam.parquet"
AGRO_PPM = DATA_PROCESSED / "agro_ppm.parquet"

# Comércio Exterior
COMEX_UF_MENSAL = DATA_PROCESSED / "comex_uf_mensal.parquet"
COMEX_NCM_MENSAL = DATA_PROCESSED / "comex_pe_ncm_mensal.parquet"
COMEX_PAIS_MENSAL = DATA_PROCESSED / "comex_pe_pais_mensal.parquet"
COMEX_NCM_PAIS_ANUAL = DATA_PROCESSED / "comex_pe_ncm_pais_anual.parquet"
COMEX_NCM = DATA_PROCESSED / "comex_ncm.parquet"
COMEX_MUN_MENSAL = DATA_PROCESSED / "comex_municipios_mensal.parquet"
COMEX_MUN_SH4_ANUAL = DATA_PROCESSED / "comex_municipios_sh4_anual.parquet"
AGROSTAT_RAW = DATA_RAW / "agrostat_ncm_agronegocio.xlsx"

# Indicadores Sociais
IPS_RAW_DIR = DATA_RAW / "ips"
IPS_PE = DATA_PROCESSED / "ips_pe.parquet"
IPS_REFERENCIAS = DATA_PROCESSED / "ips_referencias.parquet"
MVI_PE = DATA_PROCESSED / "mvi_pe.parquet"

# ============================================================================
# METADADOS INSTITUCIONAIS
# ============================================================================

META = {
    "titulo": "Pernambuco em números",
    "sobretitulo": "Observatório Econômico",
    "orgao": "Desenvolvido por Flavius Sodré",
    "uf": "PE",
    "uf_codigo": 26,  # código IBGE
    "n_municipios": 185,  # 184 + Fernando de Noronha
}

# ============================================================================
# DEFAULTS PARA GRÁFICOS PLOTLY
# ============================================================================
# Centraliza os defaults estéticos. Cada gráfico no projeto começa com
# uma chamada a `apply_default_layout(fig)` (ver components/charts.py),
# que aplica essas configurações.

CHART_FONT = "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
CHART_FONT_SERIF = "Source Serif Pro, Georgia, serif"

CHART_LAYOUT_DEFAULTS = dict(
    font=dict(family=CHART_FONT, size=12, color=PALETTE["grafite"]),
    plot_bgcolor=PALETTE["branco"],
    paper_bgcolor=PALETTE["branco"],
    margin=dict(l=40, r=20, t=20, b=40),
    xaxis=dict(
        showgrid=False,
        showline=True,
        linecolor=PALETTE["cinza_neblina"],
        linewidth=1,
        ticks="outside",
        tickcolor=PALETTE["cinza_neblina"],
        tickfont=dict(size=10, color=PALETTE["cinza_medio"]),
    ),
    yaxis=dict(
        showgrid=True,
        gridcolor=PALETTE["cinza_neblina"],
        gridwidth=0.5,
        zeroline=True,
        zerolinecolor=PALETTE["cinza_claro"],
        zerolinewidth=1,
        tickfont=dict(size=10, color=PALETTE["cinza_medio"]),
    ),
    hoverlabel=dict(
        bgcolor=PALETTE["preto_titulo"],
        bordercolor=PALETTE["preto_titulo"],
        font=dict(family=CHART_FONT, size=11, color=PALETTE["branco"]),
    ),
)
