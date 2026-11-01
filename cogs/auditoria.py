from discord.ext import commands


class Auditoria(commands.Cog):
    """Auditoria centralizada no Fórum fixo do Registro Global."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot


async def setup(bot: commands.Bot):
    await bot.add_cog(Auditoria(bot))
