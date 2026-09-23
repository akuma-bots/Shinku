import discord
from discord import app_commands
from discord.ext import commands

from utils import recordes
from utils.guild_config import get_config, set_config

NOMES_CATEGORIA = {
    "vitorias_pvp": ("⚔️ Mais vitórias em PvP", "vitória(s)"),
    "xp_total": ("✨ Mais XP acumulado", "XP"),
    "vitorias_guerra": ("🏰 Mais vitórias em guerra", "vitória(s)"),
}


class Recordes(commands.Cog):
    """Recordes globais do servidor. Outros cogs chamam `anunciar_se_recorde(...)`
    depois de atualizar um stat — se for uma marca inédita, posta
    automaticamente no canal Recordes, sem precisar de comando manual."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def anunciar_se_recorde(self, guild: discord.Guild, categoria: str, user_id: int, valor: float):
        novo = await recordes.verificar_e_atualizar(guild.id, categoria, user_id, valor)
        if not novo:
            return
        nome, unidade = NOMES_CATEGORIA.get(categoria, (categoria, ""))

        config = await get_config(guild.id)
        canal_id = config.get("canal_recordes_id")
        canal = guild.get_channel(canal_id) if canal_id else None
        if not canal:
            return

        embed = discord.Embed(
            title="🏅 Novo recorde!",
            description=f"{nome}\n<@{user_id}> agora tem **{valor} {unidade}**!",
            color=0xFEE75C,
        )
        await canal.send(embed=embed)

    @app_commands.command(name="recordes-canal", description="Define o canal onde novos recordes são anunciados.")
    @app_commands.describe(canal="Canal de recordes")
    @app_commands.checks.has_permissions(administrator=True)
    async def recordes_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_recordes_id=canal.id)
        await interaction.response.send_message(f"✅ Recordes serão anunciados em {canal.mention}.", ephemeral=True)

    @app_commands.command(name="recordes", description="Mostra os recordes atuais do servidor.")
    async def recordes_listar(self, interaction: discord.Interaction):
        todos = await recordes.obter_todos(interaction.guild.id)
        if not todos:
            await interaction.response.send_message("Nenhum recorde registrado ainda.", ephemeral=True)
            return
        linhas = []
        for categoria, dado in todos.items():
            nome, unidade = NOMES_CATEGORIA.get(categoria, (categoria, ""))
            linhas.append(f"{nome}: <@{dado['user_id']}> — **{dado['valor']} {unidade}**")
        embed = discord.Embed(title="🏅 Recordes do servidor", description="\n".join(linhas), color=0xFEE75C)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Recordes(bot))