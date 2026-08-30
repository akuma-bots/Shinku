import os
import json
import hashlib
import asyncio
from pathlib import Path
import discord
from discord.ext import commands
from dotenv import load_dotenv
from aiohttp import web

# Usa o caminho absoluto do .env, na mesma pasta deste arquivo — evita
# que o load_dotenv() falhe quando o diretório de trabalho atual (cwd)
# é diferente da pasta do projeto (comum em apps como o Pydroid 3).
CAMINHO_ENV = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=CAMINHO_ENV)

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print(f"Procurando .env em: {CAMINHO_ENV}")
    print(f"Esse arquivo existe? {CAMINHO_ENV.exists()}")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True  # necessário pro contador de "membros online"

bot = commands.Bot(command_prefix="!", intents=intents)

COGS = [
    "cogs.tickets", "cogs.moderacao", "cogs.automod", "cogs.configuracao",
    "cogs.logs", "cogs.antiraid", "cogs.gerencia", "cogs.autocargo",
    "cogs.contadores", "cogs.eventos", "cogs.parcerias", "cogs.embeds", "cogs.customizacao",
    "cogs.guerras", "cogs.perfil", "cogs.denuncias", "cogs.sorteios", "cogs.roblox",
    "cogs.modmail", "cogs.backup",
]

# --- "Salvar" os comandos entre reinícios --------------------------------
CAMINHO_CACHE_COMANDOS = Path(__file__).resolve().parent / "data" / "comandos_sincronizados.json"


def _assinatura_comandos() -> str:
    comandos = []
    for cmd in bot.tree.get_commands():
        parametros = sorted(getattr(p, "name", "") for p in getattr(cmd, "parameters", []))
        comandos.append(f"{cmd.name}:{cmd.description}:{','.join(parametros)}")
    texto = "|".join(sorted(comandos))
    return hashlib.sha256(texto.encode()).hexdigest()


def _carregar_cache_comandos() -> dict:
    if CAMINHO_CACHE_COMANDOS.exists():
        try:
            return json.loads(CAMINHO_CACHE_COMANDOS.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _salvar_cache_comandos(dados: dict):
    CAMINHO_CACHE_COMANDOS.parent.mkdir(parents=True, exist_ok=True)
    CAMINHO_CACHE_COMANDOS.write_text(json.dumps(dados))


@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")

    assinatura_atual = _assinatura_comandos()
    cache = _carregar_cache_comandos()
    try:
        if cache.get("assinatura") != assinatura_atual:
            synced_global = await bot.tree.sync()
            print(f"{len(synced_global)} comandos sincronizados globalmente (o conjunto de comandos mudou).")
            _salvar_cache_comandos({"assinatura": assinatura_atual})
        else:
            print("Comandos idênticos aos da última vez — sync global pulado (evita limite de taxa do Discord).")
    except Exception as e:
        print(f"Erro ao sincronizar comandos globalmente: {e}")

    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced_guild = await bot.tree.sync(guild=guild)
            print(f"{len(synced_guild)} comandos sincronizados instantaneamente em '{guild.name}'.")
        except Exception as e:
            print(f"Erro ao sincronizar comandos em '{guild.name}': {e}")


async def iniciar_servidor_web():
    """Servidor HTTP mínimo — só existe pra plataformas como o Render, que
    precisam de uma porta respondendo pra considerar o app 'saudável' (e pra
    um serviço tipo UptimeRobot ter algo pra pingar e evitar hibernação)."""
    app = web.Application()

    async def handle(request):
        return web.Response(text=f"{bot.user or 'Bot'} está online.")

    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    porta = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", porta)
    await site.start()
    print(f"Servidor web de 'health check' escutando na porta {porta}.")


async def main():
    async with bot:
        for cog in COGS:
            await bot.load_extension(cog)
            print(f"Cog carregado: {cog}")
        await asyncio.gather(
            bot.start(TOKEN),
            iniciar_servidor_web(),
        )


if __name__ == "__main__":
    asyncio.run(main())
