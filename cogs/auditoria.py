import discord
from discord import app_commands
from discord.ext import commands

from utils.apresentacao import embed_erro, embed_sucesso
from utils.guild_config import set_config


class Auditoria(commands.Cog):
    """Define o canal de auditoria usado para registrar decisões administrativas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="auditoria-canal",
        description="Define o canal de log de auditoria (aprovações/recusas).",
    )
    @app_commands.describe(canal="Canal onde os logs de auditoria serão postados")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def auditoria_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=embed_erro("CONFIGURAÇÃO INDISPONÍVEL", "Este comando só pode ser usado dentro de um servidor."),
                ephemeral=True,
            )
            return
        await set_config(interaction.guild.id, canal_auditoria_id=canal.id)
        embed = embed_sucesso(
            "AUDITORIA CONFIGURADA",
            f"Os registros administrativos serão enviados para {canal.mention}.\n\n"
            "A equipe poderá consultar decisões de aprovação e recusa neste canal.",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Auditoria(bot))
