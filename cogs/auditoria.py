import discord
from discord import app_commands
from discord.ext import commands
from utils.guild_config import set_config


class Auditoria(commands.Cog):
    """Define o canal de log de auditoria — usado pelo motor de revisão e
    pelos formulários pra registrar quem aprovou/recusou o quê e quando,
    útil se alguém contestar uma decisão depois."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="auditoria-canal", description="Define o canal de log de auditoria (aprovações/recusas).")
    @app_commands.describe(canal="Canal onde os logs de auditoria serão postados")
    @app_commands.checks.has_permissions(administrator=True)
    async def auditoria_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_auditoria_id=canal.id)
        await interaction.response.send_message(f"✅ Log de auditoria configurado em {canal.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Auditoria(bot))