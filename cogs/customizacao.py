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
    """Customização visual do bot (status/atividade exibida). Como o status
    é global — o mesmo em todos os servidores onde o bot está — só o dono
    da aplicação do bot pode mudar."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="definir-status", description="[Dono do bot] Muda o texto de atividade exibido pelo bot (vale pra todos os servidores).")
    @app_commands.describe(tipo="Tipo de atividade", texto="Texto exibido")
    @app_commands.choices(tipo=[app_commands.Choice(name=t, value=t) for t in TIPOS_ATIVIDADE])
    async def definir_status(self, interaction: discord.Interaction, tipo: str, texto: str):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message("Esse comando é restrito ao dono do bot — o status é o mesmo em todos os servidores.", ephemeral=True)
            return

        atividade = discord.Activity(type=TIPOS_ATIVIDADE[tipo], name=texto)
        await self.bot.change_presence(activity=atividade)
        await interaction.response.send_message(f"✅ Status atualizado para: {tipo} {texto}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Customizacao(bot))
