# Observatório Econômico de Pernambuco

<!-- Depois de gerar o DOI no Zenodo, troque XXXXXXX pelo número e apague as marcas de comentário desta linha -->
<!-- [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.XXXXXXX.svg)](https://doi.org/10.5281/zenodo.XXXXXXX) -->

Painel interativo de acesso aberto com indicadores econômicos e sociais de Pernambuco e de seus 185 municípios, desenvolvido em Python/Dash por Flavius Sodré.

**Acesse:** https://www.observatorioeconomicope.com.br

![Preview do dashboard](screenshots/Dashboard-Home.png)

## Por que existe

Os indicadores econômicos de Pernambuco estão espalhados por bases de vários órgãos, com formatos e periodicidades diferentes. O observatório coleta, padroniza e integra essas bases num único painel, com recorte por município e por Região de Desenvolvimento, para quem precisa acompanhar a economia do estado: gestores, empresas, entidades, estudantes e pesquisadores.

## Onde é usado

- Como recurso didático em disciplinas da Universidade Católica de Pernambuco (Unicap), como o Projeto Integrador V do curso de Administração.
- No projeto de extensão "Dados Abertos a Serviço da Gestão – Workshop de Dashboards Gerenciais" (Unicap).

## O que o painel mostra

| Eixo | Conteúdo | Fonte | Período | Atualização |
| --- | --- | --- | --- | --- |
| Mercado de trabalho · Emprego formal | Admissões, desligamentos e saldo por município, gênero e setor; mapa dos 185 municípios | Novo Caged · MTE | jan/2020 a mar/2026 | Mensal |
| Mercado de trabalho · Desemprego | Taxa de desocupação, ocupação, rendimento médio, desalento e informalidade; comparação com os nove estados do Nordeste | PNAD Contínua · IBGE | 2012 a 2025 | Trimestral |
| Índices socioeconômicos | PIB municipal nominal e real (IPCA), PIB per capita, VAB setorial, dependência de impostos; pobreza e extrema pobreza | SEPLAG-PE · IBGE (Contas Regionais); PNAD Contínua | 2010 a 2023 | Anual |
| Gestão pública | Prefeitos e vereadores eleitos; transferências constitucionais aos municípios (FPM, FPE, ICMS, IPVA) | TSE; STN · Tesouro Nacional | Eleições municipais; 2023 a 2026 | A cada eleição; mensal |
| Atividade econômica | Em preparação | – | – | – |
| Comércio exterior | Em preparação | – | – | – |

<!-- Períodos da versão 1.20: atualize esta tabela a cada nova carga de dados. -->

Cobertura: 185 municípios (184 e o distrito estadual de Fernando de Noronha) e as 12 Regiões de Desenvolvimento de Pernambuco.

## Como rodar localmente

```bash
git clone https://github.com/FlaviusSodre/Dashboard-Observatorio_Economico.git
cd Dashboard-Observatorio_Economico
python -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m etl.run_all            # processa os dados (uma vez)
python app.py                    # abre em http://127.0.0.1:8050
```

## Estrutura do projeto

```
app.py                  entrada principal
config.py               paleta, caminhos e metadados
requirements.txt
data/
  raw/                  arquivos originais das fontes
  processed/            parquets gerados pelo ETL + catalogo.json
  geo/                  malha municipal (GeoJSON do IBGE)
etl/                    tratamento de cada base (CAGED, PNAD, PIB, RDs, prefeitos, malha)
  run_all.py            orquestrador
components/             acesso a dados (com cache), gráficos e componentes de interface
tabs/                   uma aba por arquivo; _template.py é o modelo para novas abas
assets/                 CSS, ícones e manifesto do aplicativo instalável (PWA)
```

O observatório é extensível: cada nova temática entra como um arquivo em `tabs/`, sem refatorar o restante.

## Fontes de dados

Todos os dados vêm de bases públicas oficiais. Os direitos e as condições de uso de cada base são os do órgão de origem; cite a fonte original ao reutilizar os dados. O painel usa apenas dados agregados e não trata dados pessoais sensíveis; nomes de prefeitos e vereadores eleitos são informação pública do TSE.

- Ministério do Trabalho e Emprego – Novo Caged
- IBGE – PNAD Contínua, Contas Regionais e malha municipal
- Secretaria de Planejamento e Gestão de Pernambuco (SEPLAG-PE) – PIB municipal
- Tribunal Superior Eleitoral – resultados das eleições municipais
- Secretaria do Tesouro Nacional – transferências constitucionais
- Pernambuco em números – Regiões de Desenvolvimento

## Nota metodológica

- **Valores reais do PIB:** PIB e PIB per capita a preços de 2023, deflacionados pelo IPCA.
- **Saldo de emprego:** admissões menos desligamentos no mês, segundo o Novo Caged.
- [Complete com fórmula, unidade e período de cada indicador calculado pelo painel.]

## Privacidade

O site conta acessos de forma anônima, sem cookies e sem coletar dados pessoais.

## Como citar

Use o botão "Cite this repository", na coluna da direita do GitHub, ou:

> SODRÉ, Flavius Raymundo Arruda. **Observatório Econômico de Pernambuco**. Versão 2.0. Recife, 2026. Software. Disponível em: https://doi.org/10.5281/zenodo.XXXXXXX.

## Autoria

Projeto pessoal de Flavius Raymundo Arruda Sodré, professor da Universidade Católica de Pernambuco (Unicap), responsável pela concepção, pelo desenvolvimento e pela manutenção do painel.

## Licença

Copyright (C) 2026 Flavius Raymundo Arruda Sodré.

Este programa é software livre, distribuído sob a GNU Affero General Public License, versão 3 ou posterior (arquivo `LICENSE`). Você pode usá-lo, estudá-lo e modificá-lo. Se distribuir uma versão modificada ou colocá-la no ar como serviço na internet, deve disponibilizar o código-fonte completo sob a mesma licença e manter este aviso de autoria. O programa é oferecido sem nenhuma garantia.

Os dados exibidos seguem as condições de uso de cada órgão de origem.
