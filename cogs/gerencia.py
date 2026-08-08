import discord
from discord import app_commands
from discord.ext import commands
from utils.storage import carregar_config
from utils.guild_config import (
    get_config,
    liberar_canal_para_regra,
    bloquear_canal_para_regra,
)


class Gerencia(commands.Cog):
    """Comandos de gerência do bot: escolher em quais canais cada regra de
    automod vale ou não (ex: liberar links num canal de divulgação, liberar
    linguagem mais solta numa sala livre etc). Vale só para este servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.regras = carregar_config("rules.json")["regras"]

    def _choices_regras(self) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=regra["titulo"], value=regra["id"])
            for regra in self.regras
        ][:25]  # limite de 25 opções do Discord

    def _regra_por_id(self, regra_id: str):
        return next((r for r in self.regras if r["id"] == regra_id), None)

    @app_commands.command(name="liberar-canal", description="Libera um canal para não seguir uma regra específica do automod (ex: permitir links).")
    @app_commands.describe(regra="Qual regra deixar de aplicar", canal="Em qual canal")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def liberar_canal(self, interaction: discord.Interaction, regra: str, canal: discord.TextChannel):
        regra_obj = self._regra_por_id(regra)
        if not regra_obj:
            await interaction.response.send_message("Regra não encontrada.", ephemeral=True)
            return

        await liberar_canal_para_regra(interaction.guild.id, regra, canal.id)
        await interaction.response.send_message(
            f"✅ {canal.mention} agora está **liberado** da regra **{regra_obj['titulo']}**.\n"
            f"Isso vale só para este servidor.",
            ephemeral=True,
        )

    @liberar_canal.autocomplete("regra")
    async def _autocomplete_regra_liberar(self, interaction: discord.Interaction, atual: str):
        return [c for c in self._choices_regras() if atual.lower() in c.name.lower()][:25]

    @app_commands.command(name="bloquear-canal", description="Volta a aplicar uma regra do automod num canal que estava liberado.")
    @app_commands.describe(regra="Qual regra voltar a aplicar", canal="Em qual canal")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def bloquear_canal(self, interaction: discord.Interaction, regra: str, canal: discord.TextChannel):
        regra_obj = self._regra_por_id(regra)
        if not regra_obj:
            await interaction.response.send_message("Regra não encontrada.", ephemeral=True)
            return

        await bloquear_canal_para_regra(interaction.guild.id, regra, canal.id)
        await interaction.response.send_message(
            f"🔒 {canal.mention} voltou a seguir a regra **{regra_obj['titulo']}**.",
            ephemeral=True,
        )

    @bloquear_canal.autocomplete("regra")
    async def _autocomplete_regra_bloquear(self, interaction: discord.Interaction, atual: str):
        return [c for c in self._choices_regras() if atual.lower() in c.name.lower()][:25]

    @app_commands.command(name="canais-liberados", description="Mostra quais canais estão liberados de quais regras neste servidor.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def canais_liberados(self, interaction: discord.Interaction):
        config = await get_config(interaction.guild.id)
        excecoes = config["canais_liberados"]

        if not any(excecoes.values()):
            await interaction.response.send_message("Nenhum canal liberado de nenhuma regra neste servidor ainda.", ephemeral=True)
            return

        linhas = []
        for regra_id, canal_ids in excecoes.items():
            if not canal_ids:
                continue
            regra_obj = self._regra_por_id(regra_id)
            titulo = regra_obj["titulo"] if regra_obj else regra_id
            mencoes = ", ".join(f"<#{cid}>" for cid in canal_ids)
            linhas.append(f"**{titulo}**\n{mencoes}")

        embed = discord.Embed(
            title="📋 Canais liberados por regra",
            description="\n\n".join(linhas),
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Gerencia(bot))
