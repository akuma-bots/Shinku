import os
import json
import hashlib
import asyncio
import logging
import pkgutil
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord import app_commands
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

from utils.storage import (
    USANDO_UPSTASH,
    salvar,
    verificar_conexao_compartilhada,
)

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


class NemesisBot(commands.Bot):
    """Registra todos os comandos de Cogs diretamente no servidor da NÊMESIS.

    Comandos globais têm um limite de 100 por aplicação. Como este bot é
    exclusivo de um servidor, o escopo de servidor evita esse limite global.
    """

    async def add_cog(
        self,
        cog,
        *,
        override=False,
        guild=discord.utils.MISSING,
        guilds=discord.utils.MISSING,
    ):
        if guild is discord.utils.MISSING and guilds is discord.utils.MISSING:
            guild = discord.Object(id=NEMESIS_GUILD_ID)

        return await super().add_cog(
            cog,
            override=override,
            guild=guild,
            guilds=guilds,
        )


bot = NemesisBot(
    command_prefix="!",
    intents=intents,
)


@bot.tree.error
async def tratar_erro_comando(
    interaction: discord.Interaction,
    erro: app_commands.AppCommandError,
):
    """Registra falhas de slash commands e retorna uma mensagem segura ao usuário."""
    original = getattr(erro, "original", erro)

    if isinstance(erro, app_commands.MissingPermissions):
        mensagem = "Você não tem as permissões necessárias para usar este comando."
    elif isinstance(erro, app_commands.CommandOnCooldown):
        mensagem = f"Este comando está em cooldown. Tente novamente em {erro.retry_after:.1f} s."
    elif isinstance(erro, app_commands.CheckFailure):
        mensagem = "Você não atende aos requisitos para usar este comando."
    else:
        mensagem = "Ocorreu um erro ao executar o comando. A equipe técnica foi registrada para investigar."
        logging.error(
            "Falha em slash command %s (usuário=%s, servidor=%s): %s",
            getattr(interaction.command, "qualified_name", "desconhecido"),
            getattr(interaction.user, "id", "desconhecido"),
            getattr(interaction.guild, "id", "DM"),
            original,
            exc_info=(type(original), original, original.__traceback__),
        )

    try:
        if interaction.response.is_done():
            await interaction.followup.send(mensagem, ephemeral=True)
        else:
            await interaction.response.send_message(mensagem, ephemeral=True)
    except (discord.HTTPException, discord.InteractionResponded):
        logging.exception("Não foi possível responder ao erro do comando.")


# ============================================================
# DESCOBRIR COGS
# ============================================================

def _descobrir_cogs() -> list:
    pasta_cogs = Path(__file__).resolve().parent / "cogs"

    if not pasta_cogs.exists():
        return []

    # configuracao.py já fornece o comando /definir-status.
    # customizacao.py duplica o Cog/comando existente.
    # pontuacao_pve.py é legado: o ranking PvE separado foi removido da estrutura oficial.
    nomes = [
        modulo.name
        for modulo in pkgutil.iter_modules([str(pasta_cogs)])
        if not modulo.name.startswith("_")
        and modulo.name not in {"customizacao", "pontuacao_pve"}
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


def _assinatura_comandos(guild=None) -> str:
    """
    Gera uma assinatura determinística da árvore inteira de comandos.
    Inclui subcomandos e detalhes dos parâmetros para que alterações
    internas em grupos também provoquem uma nova sincronização.
    """
    comandos = []

    def registrar(comando, caminho=""):
        nome = getattr(comando, "name", "")
        nome_completo = f"{caminho} {nome}".strip()
        parametros = []

        for parametro in getattr(comando, "parameters", []):
            tipo = getattr(parametro, "type", None)
            parametros.append({
                "name": getattr(parametro, "name", ""),
                "description": getattr(parametro, "description", ""),
                "required": bool(getattr(parametro, "required", False)),
                "type": getattr(tipo, "value", str(tipo) if tipo is not None else ""),
            })

        comandos.append({
            "name": nome_completo,
            "description": getattr(comando, "description", ""),
            "parameters": parametros,
        })

        filhos = getattr(comando, "commands", [])
        for filho in sorted(filhos, key=lambda item: getattr(item, "name", "")):
            registrar(filho, nome_completo)

    for comando in sorted(
        bot.tree.get_commands(guild=guild),
        key=lambda item: getattr(item, "name", ""),
    ):
        registrar(comando)

    texto = json.dumps(
        comandos,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


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
    else:
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


    # Se o servidor autorizado não estiver acessível, já removemos as
    # associações não autorizadas acima e não tentamos sincronizar comandos.
    if servidor is None:
        return

    # ========================================================
    # SINCRONIZAÇÃO
    # ========================================================

    cache = _carregar_cache_comandos()

    assinatura_atual = _assinatura_comandos(servidor)


    # Remove registros globais antigos.
    if not cache.get("globais_limpos"):

        try:
            await bot.http.bulk_upsert_global_commands(
                bot.application_id,
                [],
            )
            cache["globais_limpos"] = True
            print("Comandos globais antigos removidos.")

        except Exception:
            # Não marcar como concluído: a próxima inicialização deve
            # tentar novamente em vez de deixar comandos globais órfãos.
            cache["globais_limpos"] = False
            logging.exception("Erro ao limpar comandos globais antigos.")


    precisa_sincronizar = (
        cache.get("assinatura")
        != assinatura_atual
        or cache.get("guild_id")
        != NEMESIS_GUILD_ID
    )


    if precisa_sincronizar:

        try:

            # Os comandos já foram registrados no escopo da NÊMESIS
            # por NemesisBot.add_cog; não copie comandos globais para cá.
            sincronizados = await bot.tree.sync(guild=servidor)

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
# PONTE DE SINCRONIZAÇÃO — DASHBOARD ↔ BOT
# ============================================================

async def monitorar_integracao():
    """
    Publica um heartbeat no Redis compartilhado.
    O Dashboard usa este registro para confirmar que está lendo
    o mesmo banco acessado pelo bot.
    """
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            servidor = bot.get_guild(NEMESIS_GUILD_ID)
            await salvar(
                "integracao_bot_status.json",
                {
                    "guild_id": str(NEMESIS_GUILD_ID),
                    "bot_id": str(bot.user.id) if bot.user else None,
                    "bot_name": str(bot.user) if bot.user else "NÊMESIS",
                    "guild_name": servidor.name if servidor else None,
                    "online": bool(servidor and bot.is_ready()),
                    "storage_backend": "upstash" if USANDO_UPSTASH else "local",
                    "ready": bot.is_ready(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            logging.info(
                "Heartbeat Dashboard: online=%s guild_id=%s guild_encontrada=%s storage=%s",
                bool(servidor and bot.is_ready()),
                NEMESIS_GUILD_ID,
                bool(servidor),
                "upstash" if USANDO_UPSTASH else "local",
            )
        except Exception:
            logging.exception("Falha ao atualizar heartbeat de integração.")
        await asyncio.sleep(60)


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

    async def health(request):
        falhas = [
            item.get("cog")
            for item in getattr(bot, "cogs_falhos", [])
        ]
        status = (
            "starting" if not bot.is_ready()
            else "degraded" if falhas
            else "online"
        )
        # Endpoint público sem autenticação: expõe somente o estado operacional.
        # IDs internos e detalhes de falhas permanecem disponíveis apenas nos logs.
        return web.json_response(
            {"status": status},
            status=200 if status == "online" else 503 if status == "degraded" else 202,
        )

    app.router.add_get("/", handle)
    app.router.add_get("/health", health)


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

    # Em produção, o bot precisa usar o mesmo Upstash do Dashboard.
    # Sem isso, os dados ficariam apenas no disco local e não sincronizariam.
    if os.getenv("RENDER") and not USANDO_UPSTASH:
        raise RuntimeError(
            "Sincronização NÊMESIS indisponível: configure "
            "UPSTASH_REDIS_REST_URL e UPSTASH_REDIS_REST_TOKEN "
            "no ambiente do Render, usando o mesmo banco do Netlify."
        )

    if USANDO_UPSTASH:
        await verificar_conexao_compartilhada()
        logging.info("Conexão com o Redis compartilhado confirmada.")
    else:
        logging.warning(
            "Upstash não configurado; usando armazenamento local. "
            "A sincronização com o Dashboard não estará ativa."
        )

    async with bot:
        bot.cogs_falhos = []

        for cog in COGS:
            try:
                await bot.load_extension(cog)
                print(f"Cog carregado: {cog}")
            except Exception as erro:
                bot.cogs_falhos.append({
                    "cog": cog,
                    "erro": str(erro),
                })
                logging.exception("Falha ao carregar o cog %s", cog)

        if bot.cogs_falhos:
            logging.error(
                "Inicialização incompleta: %s cog(s) falharam: %s",
                len(bot.cogs_falhos),
                ", ".join(item["cog"] for item in bot.cogs_falhos),
            )
        else:
            logging.info("Todos os %s cogs foram carregados.", len(bot.cogs))


        await asyncio.gather(
            bot.start(TOKEN),
            iniciar_servidor_web(),
            monitorar_integracao(),
        )


if __name__ == "__main__":
    asyncio.run(main())