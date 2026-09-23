import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import carregar
from utils.guild_config import get_config, set_config
from utils.perfis import ARQUIVO_PERFIS

PESOS_PADRAO = {"xp": 1, "vitoria": 10, "mvp": 20}


class RankingGeral(commands.Cog):
    """Top global do servidor: junta XP, vitórias (PvP + PvE + guerra, já
    que todas usam o mesmo campo `vitorias` do perfil) e MVPs de guerra numa
    única pontuação combinada. Depois de configurado com /ranking-canal, o
    placar fica 100% automático: a cada 10 minutos o bot edita a mesma
    mensagem com as posições atualizadas, sem precisar de comando manual."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.atualizar_ranking_automatico.start()

    def cog_unload(self):
        self.atualizar_ranking_automatico.cancel()

    async def _pesos(self, guild_id: int) -> dict:
        config = await get_config(guild_id)
        return {
            "xp": config.get("peso_ranking_xp", PESOS_PADRAO["xp"]),
            "vitoria": config.get("peso_ranking_vitoria", PESOS_PADRAO["vitoria"]),
            "mvp": config.get("peso_ranking_mvp", PESOS_PADRAO["mvp"]),
        }

    def _pontuacao(self, perfil: dict, pesos: dict) -> float:
        return (perfil.get("xp", 0) * pesos["xp"]
                + perfil.get("vitorias", 0) * pesos["vitoria"]
                + perfil.get("mvps", 0) * pesos["mvp"])

    async def _montar_embed(self, guild_id: int) -> discord.Embed:
        pesos = await self._pesos(guild_id)
        todos = await carregar(ARQUIVO_PERFIS, {})
        perfis_guild = todos.get(str(guild_id), {})

        if not perfis_guild:
            return discord.Embed(title="🌍 Top Global do Servidor",
                                  description="Ninguém tem perfil registrado ainda.", color=0x5865F2)

        pontuados = [(uid, self._pontuacao(perfil, pesos)) for uid, perfil in perfis_guild.items()]
        top = sorted(pontuados, key=lambda item: item[1], reverse=True)[:10]

        linhas = [f"**#{i+1}** <@{uid}> — {pontos:.0f} pts" for i, (uid, pontos) in enumerate(top)]
        embed = discord.Embed(title="🌍 Top Global do Servidor", description="\n".join(linhas), color=0x5865F2)
        embed.set_footer(text=f"Pontuação: XP×{pesos['xp']} + Vitórias×{pesos['vitoria']} + MVPs×{pesos['mvp']} • atualiza a cada 10 min")
        return embed

    @tasks.loop(minutes=10)
    async def atualizar_ranking_automatico(self):
        for guild in self.bot.guilds:
            await self._atualizar_painel(guild)

    @atualizar_ranking_automatico.before_loop
    async def antes_de_comecar(self):
        await self.bot.wait_until_ready()

    async def _atualizar_painel(self, guild: discord.Guild):
        config = await get_config(guild.id)
        canal_id = config.get("canal_ranking_id")
        if not canal_id:
            return
        canal = guild.get_channel(canal_id)
        if not canal:
            return

        embed = await self._montar_embed(guild.id)
        mensagem_id = config.get("ranking_mensagem_id")

        if mensagem_id:
            try:
                msg = await canal.fetch_message(mensagem_id)
                await msg.edit(embed=embed)
                return
            except (discord.NotFound, discord.Forbidden):
                pass  # a mensagem foi apagada — cria uma nova abaixo

        nova_msg = await canal.send(embed=embed)
        await set_config(guild.id, ranking_mensagem_id=nova_msg.id)

    @app_commands.command(name="ranking-canal", description="Define o canal do placar automático (atualiza sozinho a cada 10 min).")
    @app_commands.describe(canal="Canal onde o placar fica fixado")
    @app_commands.checks.has_permissions(administrator=True)
    async def ranking_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_ranking_id=canal.id, ranking_mensagem_id=None)
        await interaction.response.send_message(f"✅ Placar automático configurado em {canal.mention}.", ephemeral=True)
        await self._atualizar_painel(interaction.guild)

    @app_commands.command(name="ranking-pesos", description="Define os pesos usados no ranking geral combinado.")
    @app_commands.describe(peso_xp="Peso do XP (padrão: 1)", peso_vitoria="Peso por vitória (padrão: 10)",
                            peso_mvp="Peso por MVP de guerra (padrão: 20)")
    @app_commands.checks.has_permissions(administrator=True)
    async def ranking_pesos(self, interaction: discord.Interaction,
                             peso_xp: int = None, peso_vitoria: int = None, peso_mvp: int = None):
        campos = {}
        if peso_xp is not None:
            campos["peso_ranking_xp"] = peso_xp
        if peso_vitoria is not None:
            campos["peso_ranking_vitoria"] = peso_vitoria
        if peso_mvp is not None:
            campos["peso_ranking_mvp"] = peso_mvp
        await set_config(interaction.guild.id, **campos)

        pesos = await self._pesos(interaction.guild.id)
        await interaction.response.send_message(
            f"✅ Pesos atualizados — XP: {pesos['xp']}, Vitória: {pesos['vitoria']}, MVP: {pesos['mvp']}",
            ephemeral=True,
        )

    @app_commands.command(name="ranking-geral", description="Mostra o top global agora, sem esperar a atualização automática.")
    async def ranking_geral(self, interaction: discord.Interaction):
        embed = await self._montar_embed(interaction.guild.id)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RankingGeral(bot))