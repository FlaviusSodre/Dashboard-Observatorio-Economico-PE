# Observatório Econômico de Pernambuco

Dashboard institucional desenvolvido em Python/Dash para a Secretaria de Desenvolvimento Econômico do Estado de Pernambuco.

![Preview do dashboard](screenshots/Dashboard-Home.png)

## O que é

Plataforma de visualização de indicadores econômicos de Pernambuco, projetada como **observatório extensível**: cada nova temática (PIB, comércio exterior, demografia, etc.) entra como um novo arquivo na pasta `tabs/`, sem refatoração.

A primeira versão possui uma aba **Mercado de Trabalho** com duas sub abas:

- **Emprego formal** (CAGED): saldo, admissões e desligamentos a nível municipal, com mapa interativo dos 185 municípios
- **Desemprego** (PNAD Contínua): taxa de desocupação, rendimento médio, ocupação e desalentados a nível estadual

 e duas abas com **Índices Socioeconômicos** e **Gestão Pública**. 

## Estrutura do projeto

```
observatorio_pe/
├── app.py                  # entrada principal
├── config.py               # paleta, caminhos, metadados
├── requirements.txt
│
├── data/
│   ├── raw/                # arquivos originais (xlsx)
│   ├── processed/          # parquets gerados pelo ETL
│   └── geo/                # geojson de municípios
│
├── etl/
│   ├── caged_etl.py        # ETL CAGED
│   ├── pnad_etl.py         # ETL PNAD
│   ├── geo_etl.py          # baixa GeoJSON do IBGE
│   └── run_all.py          # orquestrador
│
├── components/
│   ├── data.py             # acesso aos dados (com cache)
│   ├── charts.py           # gráficos Plotly padronizados
│   └── ui.py               # componentes de UI (cards, headers)
│
├── tabs/                   # ★ adicione novas abas aqui
│   ├── _template.py        # modelo para criar abas
│   ├── desemprego.py
│   └── emprego_formal.py
│
└── assets/
    ├── style.css           # CSS principal
    └── logo.jpeg           # logos institucionais
```

## Como rodar localmente

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Processar os dados (uma vez só)

```bash
python -m etl.run_all
```

Isso vai:
- Baixar o GeoJSON dos municípios de PE direto do IBGE
- Ler `data/raw/CAGED_PE.xlsx` e `data/raw/PNAD_PE.xlsx`
- Gerar os parquets em `data/processed/`
- Criar o catálogo de metadados

### 3. Iniciar o app

```bash
python app.py
```

Abrir <http://127.0.0.1:8050> no navegador.


## Identidade visual

Paleta sóbria e pastel definida em `config.py`.
## Acessar Dashboard na Web

https://observatorio-economico-pe.onrender.com

## Licença e autoria

Projeto desenvolvido por Flavius Sodré para a Secretaria de Desenvolvimento Econômico do Governo do Estado de Pernambuco.
