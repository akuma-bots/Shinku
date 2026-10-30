from utils.apresentacao import criar_embed
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import pontuacao_pve
from utils.guild_config import get_config, set_config


class PontuacaoPvE(commands.Cog):
    """Placar de pontuação exclusivo de PvE (missões PvE + encontros
    sorteados), separado do XP geral. Painel automático que se atualiza
    sozinho a cada 10 minutos no canal configurado (edita a mesma mensagem,
    sem lotar o canal)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.atualizar_painel_pve.start()

    def cog_unload(self):
        self.atualizar_painel_pve.cancel()

    async def _montar_embed(self, guild_id: int) -> discord.Embed:
        top = await pontuacao_pve.obter_ranking(guild_id)
        embed = criar_embed(
            title="🗡️ LIGA PvE · CLASSIFICAÇÃO OFICIAL",
            description=(
                "**DESEMPENHO NAS OPERAÇÕES PvE**\n"
                "A classificação considera somente pontuações registradas em provas aprovadas. "
                "O quadro é atualizado automaticamente a cada 10 minutos."
            ),
            cor=0x9F1239,
            rodape="NÊMESIS  •  CIRCUITO PvE",
        )
        if not top:
            embed.add_field(
                name="QUADRO AGUARDANDO REGISTROS",
                value="Ainda não há pontuações validadas. Conclua uma operação PvE e envie a prova para análise.",
                inline=False,
            )
            return embed

        medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
        for posicao, (uid, pontos) in enumerate(top[:10], start=1):
            selo = medalhas.get(posicao, f"#{posicao:02d}")
            embed.add_field(
                name=f"{selo}  POSIÇÃO {posicao:02d}",
                value=f"<@{uid}>\n**{int(pontos):,} pontos**".replace(",", "."),
                inline=True,
            )
        return embed

    async def _atualizar_painel(self, guild: discord.Guild):
        config = await get_config(guild.id)
        canal_id = config.get("canal_pontuacao_pve_id")
        if not canal_id:
            return
        canal = guild.get_channel(canal_id)
        if not canal:
            return

        embed = await self._montar_embed(guild.id)
        mensagem_id = config.get("pontuacao_pve_mensagem_id")

        if mensagem_id:
            try:
                msg = await canal.fetch_message(mensagem_id)
                await msg.edit(embed=embed)
                return
            except (discord.NotFound, discord.Forbidden):
                pass

        nova_msg = await canal.send(embed=embed)
        await set_config(guild.id, pontuacao_pve_mensagem_id=nova_msg.id)

    @tasks.loop(minutes=10)
    async def atualizar_painel_pve(self):
        for guild in self.bot.guilds:
            await self._atualizar_painel(guild)

    @atualizar_painel_pve.before_loop
    async def antes_de_comecar(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="pve-pontuacao-canal", description="Define o canal do placar automático de pontuação PvE.")
    @app_commands.describe(canal="Canal onde o placar fica fixado (ex: #pontuação)")
    @app_commands.checks.has_permissions(administrator=True)
    async def pve_pontuacao_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_pontuacao_pve_id=canal.id, pontuacao_pve_mensagem_id=None)
        await interaction.response.send_message(f"✅ Placar de pontuação PvE configurado em {canal.mention}.", ephemeral=True)
        await self._atualizar_painel(interaction.guild)

    @app_commands.command(name="pve-pontuacao", description="Mostra a pontuação PvE agora, sem esperar a atualização automática.")
    async def pve_pontuacao(self, interaction: discord.Interaction):
        embed = await self._montar_embed(interaction.guild.id)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(PontuacaoPvE(bot))