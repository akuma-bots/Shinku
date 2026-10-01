import os
import json
import hashlib
import asyncio
import logging
import pkgutil
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


# ============================================================
# NÊMESIS — CONFIGURAÇÃO
# ============================================================

CAMINHO_ENV = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=CAMINHO_ENV)

TOKEN = os.getenv("DISCORD_TOKEN")
NEMESIS_GUILD_ID = os.getenv("NEMESIS_GUILD_ID")


if not TOKEN:
    print(f"Procurando .env em: {CAMINHO_ENV}")
    print(f"Esse arquivo existe? {CAMINHO_ENV.exists()}")
    raise RuntimeError(
        "DISCORD_TOKEN não configurado."
    )


if not NEMESIS_GUILD_ID:
    raise RuntimeError(
        "NEMESIS_GUILD_ID não configurado. "
        "O bot é exclusivo da NÊMESIS."
    )


try:
    NEMESIS_GUILD_ID = int(NEMESIS_GUILD_ID)
except ValueError as erro:
    raise RuntimeError(
        "NEMESIS_GUILD_ID precisa ser um ID numérico do servidor da NÊMESIS."
    ) from erro


# ============================================================
# DISCORD
# ============================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True
intents.presences = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents,
)


# ============================================================
# DESCOBRIR COGS
# ============================================================

def _descobrir_cogs() -> list:
    pasta_cogs = Path(__file__).resolve().parent / "cogs"

    if not pasta_cogs.exists():
        return []

    nomes = [
        modulo.name
        for modulo in pkgutil.iter_modules([str(pasta_cogs)])
        if not modulo.name.startswith("_")
    ]

    return [
        f"cogs.{nome}"
        for nome in sorted(nomes)
    ]


COGS = _descobrir_cogs()


# ============================================================
# CACHE DOS COMANDOS
# ============================================================

CAMINHO_CACHE_COMANDOS = (
    Path(__file__).resolve().parent
    / "data"
    / "comandos_sincronizados.json"
)


def _assinatura_comandos() -> str:
    comandos = []

    for comando in bot.tree.get_commands():
        parametros = sorted(
            getattr(parametro, "name", "")
            for parametro in getattr(
                comando,
                "parameters",
                [],
            )
        )

        comandos.append(
            f"{comando.name}:"
            f"{comando.description}:"
            f"{','.join(parametros)}"
        )

    texto = "|".join(sorted(comandos))

    return hashlib.sha256(
        texto.encode("utf-8")
    ).hexdigest()


def _carregar_cache_comandos() -> dict:
    if not CAMINHO_CACHE_COMANDOS.exists():
        return {}

    try:
        return json.loads(
            CAMINHO_CACHE_COMANDOS.read_text(
                encoding="utf-8"
            )
        )

    except (
        json.JSONDecodeError,
        OSError,
    ):
        return {}


def _salvar_cache_comandos(
    dados: dict,
) -> None:

    CAMINHO_CACHE_COMANDOS.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    CAMINHO_CACHE_COMANDOS.write_text(
        json.dumps(
            dados,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():

    print(
        f"NÊMESIS conectada como {bot.user}"
    )

    servidor = bot.get_guild(
        NEMESIS_GUILD_ID
    )

    if servidor is None:

        print(
            "ERRO: o servidor da NÊMESIS "
            f"({NEMESIS_GUILD_ID}) não foi encontrado."
        )

        return


    print(
        f"Servidor autorizado: "
        f"{servidor.name} ({servidor.id})"
    )


    # ========================================================
    # SEGURANÇA
    # ========================================================
    # O bot pertence exclusivamente à NÊMESIS.
    # Caso apareça em outro servidor, sai automaticamente.
    # ========================================================

    for guild in list(bot.guilds):

        if guild.id == NEMESIS_GUILD_ID:
            continue

        try:

            print(
                f"Servidor não autorizado detectado: "
                f"{guild.name} ({guild.id}). "
                "Saindo..."
            )

            await guild.leave()

        except Exception as erro:

            print(
                f"Erro ao sair de "
                f"'{guild.name}': {erro}"
            )


    # ========================================================
    # SINCRONIZAÇÃO
    # ========================================================

    cache = _carregar_cache_comandos()

    assinatura_atual = _assinatura_comandos()


    # Remove registros globais antigos.
    if not cache.get("globais_limpos"):

        try:

            await bot.http.bulk_upsert_global_commands(
                bot.application_id,
                [],
            )

            print(
                "Comandos globais antigos removidos."
            )

        except Exception as erro:

            print(
                f"Erro ao limpar comandos globais: {erro}"
            )

        cache["globais_limpos"] = True


    precisa_sincronizar = (
        cache.get("assinatura")
        != assinatura_atual
        or cache.get("guild_id")
        != NEMESIS_GUILD_ID
    )


    if precisa_sincronizar:

        try:

            bot.tree.copy_global_to(
                guild=servidor
            )

            sincronizados = await bot.tree.sync(
                guild=servidor
            )

            print(
                f"{len(sincronizados)} comandos "
                "sincronizados na NÊMESIS."
            )

            cache["assinatura"] = assinatura_atual
            cache["guild_id"] = NEMESIS_GUILD_ID

        except Exception as erro:

            print(
                "Erro ao sincronizar comandos "
                f"da NÊMESIS: {erro}"
            )

    else:

        print(
            "Comandos da NÊMESIS já estão "
            "atualizados. Sync ignorado."
        )


    _salvar_cache_comandos(cache)


# ============================================================
# HEALTH CHECK — RENDER
# ============================================================

async def iniciar_servidor_web():

    app = web.Application()


    async def handle(request):

        return web.Response(
            text=(
                f"{bot.user or 'Bot NÊMESIS'} "
                "está online."
            )
        )


    app.router.add_get(
        "/",
        handle,
    )


    runner = web.AppRunner(app)

    await runner.setup()


    porta = int(
        os.getenv(
            "PORT",
            8080,
        )
    )


    site = web.TCPSite(
        runner,
        "0.0.0.0",
        porta,
    )


    await site.start()


    print(
        f"Health check da NÊMESIS "
        f"escutando na porta {porta}."
    )


# ============================================================
# INICIALIZAÇÃO
# ============================================================

async def main():

    async with bot:

        for cog in COGS:

            try:

                await bot.load_extension(
                    cog
                )

                print(
                    f"Cog carregado: {cog}"
                )

            except Exception as erro:

                print(
                    f"Falha ao carregar "
                    f"{cog}: {erro}"
                )


        await asyncio.gather(
            bot.start(TOKEN),
            iniciar_servidor_web(),
        )


if __name__ == "__main__":
    asyncio.run(main())