import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import missoes, missoes_npc
from utils.guild_config import get_config

QUANTIDADE_DIARIA = 3  # ajuste esse número como preferir


class MissoesDiarias(commands.Cog):
    """Gera automaticamente QUANTIDADE_DIARIA missões de NPC por dia (não
    são criadas por líderes). À meia-noite, desativa as missões NPC do dia
    anterior e sorteia novas, postando nos canais de missões já configurados
    por /missao-canais. Missões criadas manualmente por líderes nunca são
    tocadas por esse reset."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.gerar_missoes_diarias.start()

    def cog_unload(self):
        self.gerar_missoes_diarias.cancel()

    @tasks.loop(time=datetime.time(hour=0, minute=0))
    async def gerar_missoes_diarias(self):
        for guild in self.bot.guilds:
            await self._gerar_para_guild(guild)

    @gerar_missoes_diarias.before_loop
    async def antes_de_comecar(self):
        await self.bot.wait_until_ready()

    async def _gerar_para_guild(self, guild: discord.Guild):
        await missoes.desativar_todas_por_origem(guild.id, "npc")

        config = await get_config(guild.id)
        for template in missoes_npc.sortear(QUANTIDADE_DIARIA):
            missao = await missoes.criar(
                guild.id, template["tipo"], template["titulo"], template["descricao"],
                template["recompensa_xp"], criado_por=None, origem="npc",
            )
            canal_id = config.get(f"canal_missoes_{template['tipo']}_id")
            canal = guild.get_channel(canal_id) if canal_id else None
            if not canal:
                continue

            embed = discord.Embed(
                title=f"🎯 Missão diária ({template['tipo'].upper()})",
                description=missao["titulo"],
                color=0xFEE75C,
            )
            embed.add_field(name="Objetivo", value=missao["descricao"], inline=False)
            embed.add_field(name="Recompensa", value=f"{missao['recompensa_xp']} XP", inline=True)
            embed.set_footer(text=f"ID: {missao['id']} • gerada automaticamente • use /missao-completar")
            await canal.send(embed=embed)

    @app_commands.command(name="missoes-diarias-gerar", description="Força a geração das missões diárias agora (teste).")
    @app_commands.checks.has_permissions(administrator=True)
    async def missoes_diarias_gerar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._gerar_para_guild(interaction.guild)
        await interaction.followup.send(f"✅ {QUANTIDADE_DIARIA} missões diárias geradas.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MissoesDiarias(bot))