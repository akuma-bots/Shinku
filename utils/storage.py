import os
import json
from pathlib import Path
from threading import Lock

import aiohttp


# =========================================================
# DIRETÓRIO LOCAL
# =========================================================

DATA_DIR = (
    Path(__file__).resolve().parent.parent / "data"
)

DATA_DIR.mkdir(
    exist_ok=True
)

_lock = Lock()


# =========================================================
# UPSTASH REDIS
# =========================================================

UPSTASH_URL = os.getenv(
    "UPSTASH_REDIS_REST_URL"
)

UPSTASH_TOKEN = os.getenv(
    "UPSTASH_REDIS_REST_TOKEN"
)

USANDO_UPSTASH = bool(
    UPSTASH_URL and UPSTASH_TOKEN
)


# =========================================================
# ERROS
# =========================================================

class ErroStorage(Exception):
    """Erro relacionado ao armazenamento."""


# =========================================================
# UPSTASH
# =========================================================

async def _comando_redis(*args):
    """
    Executa um comando Redis através da API REST do Upstash.
    """

    if not UPSTASH_URL or not UPSTASH_TOKEN:
        raise ErroStorage(
            "UPSTASH_REDIS_REST_URL e "
            "UPSTASH_REDIS_REST_TOKEN não estão configurados."
        )

    headers = {
        "Authorization": f"Bearer {UPSTASH_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(
            total=15
        )

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.post(
                UPSTASH_URL,
                headers=headers,
                json=list(args),
            ) as resposta:

                try:
                    dados = await resposta.json()
                except Exception:
                    texto = await resposta.text()

                    raise ErroStorage(
                        "O Upstash retornou uma resposta inválida: "
                        f"{texto}"
                    )

                if resposta.status != 200:
                    raise ErroStorage(
                        f"Erro do Upstash "
                        f"({resposta.status}): {dados}"
                    )

                return dados.get("result")

    except aiohttp.ClientError as erro:
        raise ErroStorage(
            f"Falha de conexão com o Upstash: {erro}"
        ) from erro

    except asyncio.TimeoutError as erro:
        raise ErroStorage(
            "Tempo limite excedido ao acessar o Upstash."
        ) from erro


# =========================================================
# ARQUIVOS LOCAIS
# =========================================================

def _path(nome_arquivo: str) -> Path:
    """
    Retorna o caminho de um arquivo dentro de data/.
    """

    return DATA_DIR / nome_arquivo


def _carregar_local(
    nome_arquivo: str,
    padrao,
):
    """
    Carrega um arquivo JSON localmente.

    Se o arquivo não existir, cria com o valor padrão.
    """

    caminho = _path(
        nome_arquivo
    )

    with _lock:

        if not caminho.exists():

            caminho.write_text(
                json.dumps(
                    padrao,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            return padrao

        try:

            with open(
                caminho,
                "r",
                encoding="utf-8",
            ) as arquivo:

                return json.load(
                    arquivo
                )

        except json.JSONDecodeError as erro:

            raise ErroStorage(
                f"O arquivo {nome_arquivo} "
                "possui JSON inválido."
            ) from erro


def _salvar_local(
    nome_arquivo: str,
    dados,
) -> None:
    """
    Salva dados em um arquivo JSON local.
    """

    caminho = _path(
        nome_arquivo
    )

    with _lock:

        with open(
            caminho,
            "w",
            encoding="utf-8",
        ) as arquivo:

            json.dump(
                dados,
                arquivo,
                ensure_ascii=False,
                indent=2,
            )


# =========================================================
# CARREGAR
# =========================================================

async def carregar(
    nome_arquivo: str,
    padrao,
):
    """
    Carrega dados.

    Com Upstash:
        GET nome_arquivo

    Sem Upstash:
        data/nome_arquivo
    """

    if USANDO_UPSTASH:

        valor = await _comando_redis(
            "GET",
            nome_arquivo,
        )

        if valor is None:

            await salvar(
                nome_arquivo,
                padrao,
            )

            return padrao

        try:

            return json.loads(
                valor
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ) as erro:

            raise ErroStorage(
                f"Os dados armazenados em "
                f"{nome_arquivo} são inválidos."
            ) from erro

    return _carregar_local(
        nome_arquivo,
        padrao,
    )


# =========================================================
# SALVAR
# =========================================================

async def salvar(
    nome_arquivo: str,
    dados,
) -> None:
    """
    Salva dados.

    Com Upstash:
        SET nome_arquivo JSON

    Sem Upstash:
        data/nome_arquivo
    """

    if USANDO_UPSTASH:

        conteudo = json.dumps(
            dados,
            ensure_ascii=False,
        )

        await _comando_redis(
            "SET",
            nome_arquivo,
            conteudo,
        )

        return

    _salvar_local(
        nome_arquivo,
        dados,
    )


# =========================================================
# CONFIGURAÇÕES ESTÁTICAS
# =========================================================

def carregar_config(
    nome_arquivo: str,
):
    """
    Carrega uma configuração estática
    localizada em config/.
    """

    caminho = (
        Path(__file__).resolve().parent.parent
        / "config"
        / nome_arquivo
    )

    if not caminho.exists():

        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: "
            f"{caminho}"
        )

    try:

        with open(
            caminho,
            "r",
            encoding="utf-8",
        ) as arquivo:

            return json.load(
                arquivo
            )

    except json.JSONDecodeError as erro:

        raise ErroStorage(
            f"O arquivo de configuração "
            f"{nome_arquivo} possui JSON inválido."
        ) from erro


# =========================================================
# TEXTOS DE CONFIGURAÇÃO
# =========================================================

def carregar_texto_config(
    nome_arquivo: str,
) -> str:
    """
    Carrega um arquivo de texto estático
    localizado em config/.
    """

    caminho = (
        Path(__file__).resolve().parent.parent
        / "config"
        / nome_arquivo
    )

    if not caminho.exists():

        raise FileNotFoundError(
            f"Arquivo de texto não encontrado: "
            f"{caminho}"
        )

    with open(
        caminho,
        "r",
        encoding="utf-8",
    ) as arquivo:

        return arquivo.read()