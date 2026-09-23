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
        if not top:
            return discord.Embed(title="🗡️ Pontuação PvE", description="Ninguém pontuou em PvE ainda.", color=0x57F287)

        linhas = [f"**#{i+1}** <@{uid}> — {pontos} pts" for i, (uid, pontos) in enumerate(top)]
        embed = discord.Embed(title="🗡️ Pontuação PvE", description="\n".join(linhas), color=0x57F287)
        embed.set_footer(text="Pontos de missões e encontros PvE aprovados • atualiza a cada 10 min")
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