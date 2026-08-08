import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.guild_config import get_config, adicionar_contador, remover_contador

TIPOS_VALIDOS = ["membros", "online", "bots", "boosts", "cargo"]
INTERVALO_ATUALIZACAO_MINUTOS = 10  # o Discord limita a 2 mudanças de nome por canal a cada 10 min


class Contadores(commands.Cog):
    """Canais de voz 'somente leitura' que mostram, no próprio nome, uma
    contagem ao vivo: total de membros, membros online, bots, boosts do
    servidor, ou quantos membros têm um cargo específico."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.atualizar_contadores.start()

    def cog_unload(self):
        self.atualizar_contadores.cancel()

    def _rotulo(self, tipo: str, cargo: discord.Role = None) -> str:
        return {
            "membros": "👥 Membros",
            "online": "🟢 Online",
            "bots": "🤖 Bots",
            "boosts": "🚀 Boosts",
            "cargo": f"🏷️ {cargo.name}" if cargo else "🏷️ Cargo",
        }[tipo]

    def _calcular_valor(self, guild: discord.Guild, tipo: str, cargo_id: int = None) -> int:
        if tipo == "membros":
            return guild.member_count
        if tipo == "bots":
            return sum(1 for m in guild.members if m.bot)
        if tipo == "online":
            return sum(1 for m in guild.members if m.status != discord.Status.offline and not m.bot)
        if tipo == "boosts":
            return guild.premium_subscription_count or 0
        if tipo == "cargo":
            cargo = guild.get_role(cargo_id) if cargo_id else None
            return len(cargo.members) if cargo else 0
        return 0

    @app_commands.command(name="criar-contador", description="Cria um canal de voz que mostra uma contagem ao vivo no nome.")
    @app_commands.describe(tipo="O que contar", cargo="Só se o tipo for 'cargo': qual cargo contar")
    @app_commands.choices(tipo=[app_commands.Choice(name=t, value=t) for t in TIPOS_VALIDOS])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def criar_contador(self, interaction: discord.Interaction, tipo: str, cargo: discord.Role = None):
        if tipo == "cargo" and cargo is None:
            await interaction.response.send_message("Pra contar por cargo, informe também o parâmetro `cargo`.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        valor = self._calcular_valor(interaction.guild, tipo, cargo.id if cargo else None)
        nome_canal = f"{self._rotulo(tipo, cargo)}: {valor}"

        canal = await interaction.guild.create_voice_channel(
            name=nome_canal,
            reason="Contador criado via /criar-contador",
        )
        # trava pra ninguém entrar/mexer no canal
        await canal.set_permissions(interaction.guild.default_role, connect=False)

        await adicionar_contador(interaction.guild.id, tipo, canal.id, cargo.id if cargo else None)
        await interaction.followup.send(f"✅ Contador criado: {canal.mention}. Ele se atualiza a cada {INTERVALO_ATUALIZACAO_MINUTOS} minutos.", ephemeral=True)

    @app_commands.command(name="remover-contador", description="Remove um contador (e apaga o canal de voz dele).")
    @app_commands.describe(canal="O canal de voz do contador")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remover_contador_cmd(self, interaction: discord.Interaction, canal: discord.VoiceChannel):
        await remover_contador(interaction.guild.id, canal.id)
        try:
            await canal.delete(reason="Contador removido via /remover-contador")
        except discord.HTTPException:
            pass
        await interaction.response.send_message("🗑️ Contador removido.", ephemeral=True)

    @app_commands.command(name="contadores", description="Lista os contadores ativos neste servidor.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def contadores(self, interaction: discord.Interaction):
        config = await get_config(interaction.guild.id)
        lista = config["contadores"]
        if not lista:
            await interaction.response.send_message("Nenhum contador configurado ainda.", ephemeral=True)
            return
        linhas = [f"<#{c['canal_id']}> — tipo `{c['tipo']}`" for c in lista]
        await interaction.response.send_message("\n".join(linhas), ephemeral=True)

    @tasks.loop(minutes=INTERVALO_ATUALIZACAO_MINUTOS)
    async def atualizar_contadores(self):
        for guild in self.bot.guilds:
            config = await get_config(guild.id)
            lista = config["contadores"]
            for item in lista:
                canal = guild.get_channel(item["canal_id"])
                if not canal:
                    continue
                valor = self._calcular_valor(guild, item["tipo"], item.get("cargo_id"))
                cargo = guild.get_role(item["cargo_id"]) if item.get("cargo_id") else None
                novo_nome = f"{self._rotulo(item['tipo'], cargo)}: {valor}"
                if canal.name != novo_nome:
                    try:
                        await canal.edit(name=novo_nome, reason="Atualização automática de contador")
                    except discord.HTTPException:
                        pass  # provavelmente bateu no limite de renomeações do Discord, tenta de novo no próximo ciclo

    @atualizar_contadores.before_loop
    async def antes_de_atualizar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Contadores(bot))
