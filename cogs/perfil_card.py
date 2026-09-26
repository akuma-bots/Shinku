import discord
from discord import app_commands
from discord.ext import commands

from utils.card_perfil import gerar_card
from utils.perfis import get_perfil, get_patentes, kdr


class PerfilCard(commands.Cog):
    """Versão visual do /perfil: imagem com avatar, patente, barra de
    progresso de XP e stats principais, gerada com Pillow."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="perfil-card", description="Mostra seu perfil de guerra como uma imagem.")
    @app_commands.describe(membro="De quem ver o card (padrão: você mesmo)")
    async def perfil_card(self, interaction: discord.Interaction, membro: discord.Member = None):
        await interaction.response.defer()
        alvo = membro or interaction.user
        p = await get_perfil(interaction.guild.id, alvo.id)
        patentes = await get_patentes(interaction.guild.id)
        proxima = next((pt for pt in patentes if pt["xp_minimo"] > p["xp"]), None)

        buffer = await gerar_card(
            nome=alvo.display_name,
            avatar_url=alvo.display_avatar.replace(size=256).url,
            patente=p["patente"],
            xp=p["xp"],
            xp_proximo=proxima["xp_minimo"] if proxima else None,
            vitorias=p["vitorias"],
            derrotas=p["derrotas"],
            sequencia_atual=p["sequencia_atual"],
            maior_sequencia=p["maior_sequencia"],
            kdr_valor=kdr(p),
            medalhas=len(p["medalhas"]),
        )
        await interaction.followup.send(file=discord.File(buffer, filename="perfil.png"))


async def setup(bot: commands.Bot):
    await bot.add_cog(PerfilCard(bot))