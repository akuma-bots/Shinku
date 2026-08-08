import os
import json
from pathlib import Path
from threading import Lock
import aiohttp

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
_lock = Lock()

UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")
USANDO_UPSTASH = bool(UPSTASH_URL and UPSTASH_TOKEN)


class ErroStorage(Exception):
    """Erro ao ler/gravar no Upstash (banco compartilhado com o painel web)."""


async def _comando_redis(*args):
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                UPSTASH_URL, headers=headers, json=list(args), timeout=aiohttp.ClientTimeout(total=15)
            ) as resposta:
                dados = await resposta.json()
                if resposta.status != 200:
                    raise ErroStorage(f"Erro do Upstash ({resposta.status}): {dados}")
                return dados.get("result")
    except aiohttp.ClientError as e:
        raise ErroStorage(f"Falha de conexão com o Upstash: {e}")


def _path(nome_arquivo: str) -> Path:
    return DATA_DIR / nome_arquivo


def _carregar_local(nome_arquivo: str, padrao):
    caminho = _path(nome_arquivo)
    with _lock:
        if not caminho.exists():
            caminho.write_text(json.dumps(padrao, ensure_ascii=False, indent=2), encoding="utf-8")
            return padrao
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)


def _salvar_local(nome_arquivo: str, dados) -> None:
    caminho = _path(nome_arquivo)
    with _lock:
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)


async def carregar(nome_arquivo: str, padrao):
    """Carrega uma configuração salva (por servidor, tickets, etc). Se o
    Upstash estiver configurado no .env, usa ele — assim o painel web (que
    também fala com o Upstash) enxerga exatamente os mesmos dados que o bot.
    Sem Upstash configurado, cai de volta pro arquivo local em data/ (o bot
    continua funcionando normalmente, só sem o painel web)."""
    if USANDO_UPSTASH:
        valor = await _comando_redis("GET", nome_arquivo)
        if valor is None:
            await salvar(nome_arquivo, padrao)
            return padrao
        return json.loads(valor)
    return _carregar_local(nome_arquivo, padrao)


async def salvar(nome_arquivo: str, dados) -> None:
    if USANDO_UPSTASH:
        await _comando_redis("SET", nome_arquivo, json.dumps(dados, ensure_ascii=False))
    else:
        _salvar_local(nome_arquivo, dados)


def carregar_config(nome_arquivo: str):
    """Config estática do jogo/regras (não muda pelo painel web) — sempre lida
    localmente, direto da pasta config/."""
    caminho = Path(__file__).resolve().parent.parent / "config" / nome_arquivo
    with open(caminho, "r", encoding="utf-8") as f:
        return json.load(f)


def carregar_texto_config(nome_arquivo: str) -> str:
    """Igual carregar_config, mas pra arquivos de texto puro (.txt), não JSON."""
    caminho = Path(__file__).resolve().parent.parent / "config" / nome_arquivo
    with open(caminho, "r", encoding="utf-8") as f:
        return f.read()
