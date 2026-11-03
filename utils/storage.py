import os
import json
import asyncio
import copy
import tempfile
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
    parents=True,
    exist_ok=True,
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
UPSTASH_CONFIG_INCOMPLETA = bool(UPSTASH_URL) != bool(UPSTASH_TOKEN)

# Namespace exclusivo do bot; os dados não compartilham chaves operacionais com outros sistemas.
PREFIXO_CHAVES = "nemesis_bot:"
_redis_session = None
_redis_session_loop = None


def _obter_sessao_redis():
    """Reutiliza uma sessão HTTP por processo/event loop para conexões Redis."""
    global _redis_session, _redis_session_loop
    loop = asyncio.get_running_loop()
    if _redis_session is not None and not _redis_session.closed:
        if _redis_session_loop is not loop:
            raise ErroStorage("A sessão do Upstash foi solicitada fora do event loop proprietário.")
        return _redis_session
    _redis_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
    _redis_session_loop = loop
    return _redis_session


async def fechar_sessao_storage():
    """Fecha a sessão HTTP compartilhada durante o encerramento do bot."""
    global _redis_session, _redis_session_loop
    sessao = _redis_session
    _redis_session = None
    _redis_session_loop = None
    if sessao is not None and not sessao.closed:
        await sessao.close()


def _chave_bot(nome_arquivo: str) -> str:
    if not isinstance(nome_arquivo, str) or not nome_arquivo.strip():
        raise ErroStorage("O nome do arquivo de armazenamento é inválido.")
    return f"{PREFIXO_CHAVES}{nome_arquivo.strip()}"


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
        session = _obter_sessao_redis()
        async with session.post(
            UPSTASH_URL,
            headers=headers,
            json=list(args),
        ) as resposta:
            try:
                dados = await resposta.json()
            except Exception as erro:
                texto = await resposta.text()
                raise ErroStorage(
                    "O Upstash retornou uma resposta inválida: "
                    f"{texto}"
                ) from erro

            if resposta.status != 200:
                raise ErroStorage(
                    f"Erro do Upstash ({resposta.status}): {dados}"
                )

            if not isinstance(dados, dict):
                raise ErroStorage("O Upstash retornou uma estrutura inválida.")

            if dados.get("error"):
                raise ErroStorage(f"Erro retornado pelo Redis: {dados['error']}")

            return dados.get("result")

    except asyncio.TimeoutError as erro:
        raise ErroStorage(
            "Tempo limite excedido ao acessar o Upstash."
        ) from erro

    except aiohttp.ClientError as erro:
        raise ErroStorage(
            f"Falha de conexão com o Upstash: {erro}"
        ) from erro


# =========================================================
# ARQUIVOS LOCAIS
# =========================================================

def _path(nome_arquivo: str) -> Path:
    """
    Retorna um caminho validado dentro de data/.
    Os nomes de arquivos são internos; rejeitamos separadores para impedir
    que uma configuração acidental escape do diretório de dados.
    """
    if not isinstance(nome_arquivo, str) or not nome_arquivo.strip():
        raise ErroStorage("O nome do arquivo de armazenamento é inválido.")

    nome = nome_arquivo.strip()
    if nome in {".", ".."} or Path(nome).name != nome or "/" in nome or "\\" in nome:
        raise ErroStorage("O arquivo de armazenamento precisa estar dentro de data/.")

    caminho = (DATA_DIR / nome).resolve()
    if caminho.parent != DATA_DIR.resolve():
        raise ErroStorage("O caminho do armazenamento está fora de data/.")

    return caminho


def _escrever_json_atomico(caminho: Path, dados) -> None:
    """Escreve JSON em arquivo temporário e substitui o destino atomicamente."""
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=DATA_DIR,
            prefix=f".{caminho.name}.",
            suffix=".tmp",
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            arquivo.flush()
            os.fsync(arquivo.fileno())

        os.replace(temporario, caminho)
    finally:
        if temporario is not None and temporario.exists():
            try:
                temporario.unlink()
            except OSError:
                pass


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

            _escrever_json_atomico(caminho, padrao)
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
        _escrever_json_atomico(caminho, dados)


# =========================================================
# CARREGAR
# =========================================================

async def carregar(
    nome_arquivo: str,
    padrao,
):
    """
    Carrega dados.

    Com Upstash, usa chaves privadas do bot; dados antigos são importados
    uma única vez para o namespace isolado.

    Sem Upstash:
        data/nome_arquivo
    """

    if UPSTASH_CONFIG_INCOMPLETA:
        raise ErroStorage(
            "Configuração parcial do Upstash: configure URL e token juntos; "
            "o armazenamento local não será usado como fallback silencioso."
        )

    if USANDO_UPSTASH:

        chave = _chave_bot(nome_arquivo)
        valor = await _comando_redis("GET", chave)

        # Importação única de dados da chave legada, sem continuar lendo
        # alterações futuras na chave original.
        if valor is None:
            legado = await _comando_redis("GET", nome_arquivo)
            if legado is not None:
                await _comando_redis("SET", chave, legado)
                valor = legado

        if valor is None:
            await salvar(nome_arquivo, padrao)
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

    if UPSTASH_CONFIG_INCOMPLETA:
        raise ErroStorage(
            "Configuração parcial do Upstash: configure URL e token juntos; "
            "o armazenamento local não será usado como fallback silencioso."
        )

    if USANDO_UPSTASH:

        conteudo = json.dumps(
            dados,
            ensure_ascii=False,
        )

        await _comando_redis(
            "SET",
            _chave_bot(nome_arquivo),
            conteudo,
        )

        return

    _salvar_local(
        nome_arquivo,
        dados,
    )



# =========================================================
# ATUALIZAÇÃO JSON ATÔMICA
# =========================================================

_SCRIPT_CAS_JSON = (
    "local atual = redis.call('GET', KEYS[1]); "
    "if ARGV[1] == '__NEMESIS_NIL__' then "
    "if atual ~= false then return 0 end "
    "elseif atual ~= ARGV[1] then return 0 end; "
    "redis.call('SET', KEYS[1], ARGV[2]); return 1"
)


async def atualizar_json(
    nome_arquivo: str,
    padrao,
    transformador,
    max_tentativas: int = 8,
):
    """Atualiza um documento JSON sem janela de perda entre leitura e gravação.

    No Upstash usa compare-and-set via EVAL, com repetição limitada em caso
    de concorrência. No armazenamento local mantém leitura, transformação e
    substituição dentro do mesmo lock. O transformador deve ser síncrono,
    determinístico e seguro para ser executado novamente.
    """
    if not callable(transformador):
        raise TypeError("O transformador do armazenamento precisa ser chamável.")
    tentativas = max(1, min(int(max_tentativas), 32))

    if UPSTASH_CONFIG_INCOMPLETA:
        raise ErroStorage(
            "Configuração parcial do Upstash: configure URL e token juntos; "
            "o armazenamento local não será usado como fallback silencioso."
        )

    if USANDO_UPSTASH:
        chave = _chave_bot(nome_arquivo)
        for _ in range(tentativas):
            bruto = await _comando_redis("GET", chave)
            esperado = bruto
            if bruto is None:
                # Migração legada somente como origem de leitura; a gravação
                # no namespace privado ainda ocorre por CAS contra chave ausente.
                esperado = "__NEMESIS_NIL__"
                bruto = await _comando_redis("GET", nome_arquivo)
            if bruto is None:
                atual = copy.deepcopy(padrao)
                esperado = "__NEMESIS_NIL__"
            else:
                try:
                    atual = json.loads(bruto)
                except (json.JSONDecodeError, TypeError) as erro:
                    raise ErroStorage(
                        f"Os dados armazenados em {nome_arquivo} são inválidos."
                    ) from erro

            novo = transformador(atual)
            if novo is None:
                novo = atual
            try:
                conteudo = json.dumps(novo, ensure_ascii=False, separators=(",", ":"))
            except (TypeError, ValueError) as erro:
                raise ErroStorage(
                    f"Não foi possível serializar os dados de {nome_arquivo}."
                ) from erro

            confirmado = await _comando_redis(
                "EVAL", _SCRIPT_CAS_JSON, "1", chave, esperado, conteudo
            )
            if str(confirmado) == "1":
                return novo

        raise ErroStorage(
            f"Conflito concorrente ao atualizar {nome_arquivo}; "
            "nenhuma gravação foi confirmada após várias tentativas."
        )

    caminho = _path(nome_arquivo)
    with _lock:
        if not caminho.exists():
            atual = copy.deepcopy(padrao)
        else:
            try:
                with open(caminho, "r", encoding="utf-8") as arquivo:
                    atual = json.load(arquivo)
            except json.JSONDecodeError as erro:
                raise ErroStorage(
                    f"O arquivo {nome_arquivo} possui JSON inválido."
                ) from erro

        novo = transformador(atual)
        if novo is None:
            novo = atual
        _escrever_json_atomico(caminho, novo)
        return novo


async def salvar_com_expiracao(nome_arquivo: str, dados, segundos: int) -> None:
    """Salva um documento e aplica TTL na mesma operação Redis."""
    if UPSTASH_CONFIG_INCOMPLETA:
        raise ErroStorage("Configuração parcial do Upstash: configure URL e token juntos.")
    ttl = max(1, int(segundos))
    if USANDO_UPSTASH:
        conteudo = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
        await _comando_redis("SET", _chave_bot(nome_arquivo), conteudo, "EX", ttl)
        return
    _salvar_local(nome_arquivo, dados)


async def definir_expiracao(nome_arquivo: str, segundos: int) -> bool:
    """Define TTL de uma chave privada do bot no Redis/Upstash."""
    if UPSTASH_CONFIG_INCOMPLETA:
        raise ErroStorage("Configuração parcial do Upstash: configure URL e token juntos.")
    if not USANDO_UPSTASH:
        return False
    ttl = max(1, int(segundos))
    resultado = await _comando_redis("EXPIRE", _chave_bot(nome_arquivo), ttl)
    return str(resultado) == "1"


# =========================================================
# VERIFICAÇÃO DO ARMAZENAMENTO PRIVADO
# =========================================================

async def verificar_conexao_storage() -> bool:
    """Confirma acesso ao Redis usado como armazenamento privado do bot."""
    resultado = await _comando_redis("PING")
    if str(resultado).upper() != "PONG":
        raise ErroStorage("O Upstash não confirmou a conexão de armazenamento.")
    return True


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