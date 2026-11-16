"""
etl/_fontes.py
==============
Funções comuns aos ETLs da versão 2.0, que baixam os dados direto das
fontes oficiais: APIs do IBGE (SIDRA), do Banco Central (SGS), do Comex
Stat (MDIC), do Tesouro Transparente (CKAN) e da SDS-PE.

Regras de funcionamento
-----------------------
1. Todo download vai para data/cache/ (pasta fora do git). O processamento
   sempre lê do cache. Assim o ETL também roda sem internet:

       python -m etl.run_all --offline

   usa a última cópia baixada de cada fonte.
2. Se uma fonte estiver fora do ar, o ETL avisa e segue com o cache
   existente. Só falha se nunca houve download daquela fonte.
3. Requisições têm novas tentativas com espera crescente, porque as APIs
   públicas às vezes recusam a primeira conexão. Quando a API avisa que o
   limite de consultas foi atingido (HTTP 429, comum no Comex Stat), o ETL
   espera o tempo que ela pede antes de tentar de novo.

Certificados: se o pacote `truststore` estiver instalado (está no
requirements.txt), o Python passa a validar os certificados HTTPS pelo
sistema operacional, como o navegador faz. Isso evita o erro
"certificate verify failed" em sites do governo com cadeia incompleta,
sem desligar a verificação.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_CACHE  # noqa: E402

try:  # validação de certificados pelo sistema operacional (opcional)
    import truststore
    truststore.inject_into_ssl()
except Exception:  # pragma: no cover - pacote opcional
    pass

import requests  # noqa: E402  (importado depois do truststore, de propósito)


USER_AGENT = ("Mozilla/5.0 (compatible; ObservatorioEconomicoPE/2.0; "
              "+https://www.observatorioeconomicope.com.br)")

# Códigos de "sem valor" usados pelo IBGE no SIDRA
_SIDRA_NULOS = {'...', '..', 'X', 'x', '', None}


class FonteIndisponivel(RuntimeError):
    """A fonte não respondeu e não há cópia em cache."""


# ============================================================================
# Modo offline e cache
# ============================================================================

def modo_offline() -> bool:
    """True quando o ETL deve usar só o cache (variável OBS_OFFLINE=1)."""
    return os.environ.get('OBS_OFFLINE', '0') == '1'


def pasta_cache(*partes: str) -> Path:
    """Devolve (e cria) uma subpasta de data/cache/."""
    p = DATA_CACHE.joinpath(*partes)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _gravar_atomico(destino: Path, conteudo: bytes):
    """Grava num arquivo temporário e renomeia: nunca deixa cache pela metade."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + '.tmp')
    tmp.write_bytes(conteudo)
    tmp.replace(destino)


# ============================================================================
# HTTP com novas tentativas
# ============================================================================

def _espera_pedida(r: requests.Response) -> float:
    """
    Segundos que a API pede para esperar depois de um HTTP 429: cabeçalho
    Retry-After ou o texto da resposta (o Comex Stat responde "tente
    novamente em 10 segundos"). Sem indicação, 10 s.
    """
    try:
        return float(r.headers.get('Retry-After', ''))
    except (TypeError, ValueError):
        pass
    m = re.search(r'(\d+)\s*segundos', r.text or '')
    return float(m.group(1)) if m else 10.0


def http(url: str, *, metodo: str = 'GET', json_body=None,
         timeout: int = 120, tentativas: int = 4, espera: float = 3.0,
         headers: dict = None) -> requests.Response:
    """
    Faz a requisição e devolve a resposta (status 2xx). Em caso de erro de
    rede ou 5xx, tenta de novo esperando 3 s, 6 s, 12 s... Em caso de 429
    (limite de consultas), espera o tempo pedido pela API e tenta até 6 vezes.
    """
    h = {'User-Agent': USER_AGENT, 'Accept': '*/*'}
    if headers:
        h.update(headers)
    ultimo_erro = None
    i, limite = 0, tentativas
    while i < limite:
        pausa = espera * (2 ** i)
        try:
            r = requests.request(metodo, url, json=json_body, headers=h,
                                 timeout=timeout)
            if r.status_code == 429:
                ultimo_erro = "HTTP 429 (limite de consultas da API)"
                limite = max(limite, 6)
                pausa = max(pausa, _espera_pedida(r) + 1)
            elif r.status_code >= 500:
                ultimo_erro = f"HTTP {r.status_code}"
            elif r.status_code >= 400:
                # erro do pedido (404, 400): não adianta repetir
                raise FonteIndisponivel(
                    f"HTTP {r.status_code} em {url}: {r.text[:200]}")
            else:
                return r
        except requests.RequestException as e:
            ultimo_erro = f"{type(e).__name__}: {e}"
        i += 1
        if i < limite:
            time.sleep(min(pausa, 120))
    raise FonteIndisponivel(f"{url} não respondeu ({ultimo_erro})")


def baixar_para_cache(url: str, destino: Path, *, metodo: str = 'GET',
                      json_body=None, timeout: int = 120,
                      validar=None, rotulo: str = '') -> Path:
    """
    Baixa `url` para `destino` (sobrescrevendo). Em modo offline ou se o
    download falhar, mantém o arquivo que já estava no cache.

    validar : função opcional que recebe os bytes baixados e levanta
        exceção se o conteúdo não for o esperado (ex.: página de erro).
    """
    rotulo = rotulo or destino.name
    if modo_offline():
        if destino.exists():
            return destino
        raise FonteIndisponivel(f"{rotulo}: modo offline e sem cache")
    try:
        r = http(url, metodo=metodo, json_body=json_body, timeout=timeout)
        conteudo = r.content
        if validar is not None:
            validar(conteudo)
        _gravar_atomico(destino, conteudo)
    except Exception as e:
        if destino.exists():
            print(f"      ! {rotulo}: download falhou ({e}); usando o cache")
            return destino
        raise FonteIndisponivel(f"{rotulo}: {e}") from e
    return destino


def ler_json(path: Path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def baixar_json(url: str, destino: Path, *, metodo: str = 'GET',
                json_body=None, timeout: int = 120, rotulo: str = '',
                validar=None):
    """Baixa um JSON para o cache e devolve o objeto lido."""
    def _valida(conteudo: bytes):
        obj = json.loads(conteudo.decode('utf-8'))
        if validar is not None:
            validar(obj)
    baixar_para_cache(url, destino, metodo=metodo, json_body=json_body,
                      timeout=timeout, validar=_valida, rotulo=rotulo)
    return ler_json(destino)


# ============================================================================
# IBGE · SIDRA
# ============================================================================

SIDRA_BASE = 'https://apisidra.ibge.gov.br/values'


def _valor_sidra(v):
    # "-" deveria significar zero, mas o IBGE também o usa para "não
    # publicado" (ex.: índice dessazonalizado das atividades da PIM-PF nos
    # estados). Tratar como ausente é o seguro: somas ignoram NaN.
    if v in _SIDRA_NULOS or v == '-':
        return float('nan')
    try:
        return float(v)
    except (TypeError, ValueError):
        return float('nan')


def sidra(caminho: str, cache_nome: str) -> pd.DataFrame:
    """
    Consulta a API de valores do SIDRA, com cache em data/cache/sidra/.

    caminho : parte da URL a partir de /t/, ex.
        '/t/8888/n3/26/v/12606/p/all/c544/all'
    Devolve DataFrame com as colunas originais do SIDRA (NC, NN, MC, MN, V,
    D1C, D1N, D2C...) mais 'valor' (float; '-', '...', '..' e 'X' viram NaN).
    """
    destino = pasta_cache('sidra') / f"{cache_nome}.json"

    def _valida(obj):
        if not isinstance(obj, list) or not obj or 'V' not in obj[0]:
            raise ValueError("resposta inesperada do SIDRA")

    dados = baixar_json(SIDRA_BASE + caminho, destino, rotulo=f"SIDRA {cache_nome}",
                        timeout=180, validar=_valida)
    if not dados or len(dados) < 2:
        return pd.DataFrame()
    df = pd.DataFrame(dados[1:])
    df['valor'] = df['V'].map(_valor_sidra)
    return df


def periodo_mensal(cod: str) -> pd.Timestamp:
    """'202609' -> Timestamp('2026-09-01')."""
    cod = str(cod)
    return pd.Timestamp(year=int(cod[:4]), month=int(cod[4:6]), day=1)


# ============================================================================
# Banco Central · SGS
# ============================================================================

def sgs(codigo: int, data_inicial: str = '01/01/2003') -> pd.DataFrame:
    """
    Série do SGS/BCB com cache em data/cache/bcb/. Devolve DataFrame com
    colunas data (Timestamp) e valor (float).
    """
    url = (f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
           f"?formato=json&dataInicial={data_inicial}")
    destino = pasta_cache('bcb') / f"sgs_{codigo}.json"

    def _valida(obj):
        if not isinstance(obj, list) or not obj or 'valor' not in obj[0]:
            raise ValueError("resposta inesperada do SGS")

    dados = baixar_json(url, destino, rotulo=f"SGS {codigo}", validar=_valida)
    df = pd.DataFrame(dados)
    df['data'] = pd.to_datetime(df['data'], format='%d/%m/%Y')
    df['valor'] = pd.to_numeric(df['valor'], errors='coerce')
    return df[['data', 'valor']]


# ============================================================================
# Utilidades
# ============================================================================

def cod6(cod7) -> int:
    """Código IBGE de 7 dígitos -> 6 dígitos (padrão do observatório)."""
    return int(str(cod7)[:6])


def salvar(df: pd.DataFrame, destino: Path, rotulo: str):
    """Grava o parquet e imprime um resumo."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(destino, index=False)
    print(f"      → {destino.name}: {len(df):,} linhas".replace(',', '.'))
