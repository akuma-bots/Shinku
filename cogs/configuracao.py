import discord
from discord import app_commands
from discord.ext import commands


TIPOS_ATIVIDADE = {
    "jogando": discord.ActivityType.playing,
    "assistindo": discord.ActivityType.watching,
    "ouvindo": discord.ActivityType.listening,
    "competindo": discord.ActivityType.competing,
}


class Customizacao(commands.Cog):
    """Personalização visual do bot oficial da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="definir-status",
        description="[Dono do bot] Altera a atividade exibida pelo bot da NÊMESIS.",
    )
    @app_commands.describe(
        tipo="Tipo de atividade",
        texto="Texto exibido pelo bot",
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(name=nome, value=nome)
            for nome in TIPOS_ATIVIDADE
        ]
    )
    async def definir_status(
        self,
        interaction: discord.Interaction,
        tipo: str,
        texto: str,
    ):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                "Este comando é restrito ao responsável pelo bot da NÊMESIS.",
                ephemeral=True,
            )
            return

        atividade = discord.Activity(
            type=TIPOS_ATIVIDADE[tipo],
            name=texto,
        )

        await self.bot.change_presence(activity=atividade)

        await interaction.response.send_message(
            f"Status da NÊMESIS atualizado para: "
            f"**{tipo} — {texto}**",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Customizacao(bot))