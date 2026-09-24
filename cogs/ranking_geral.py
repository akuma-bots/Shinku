import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import carregar
from utils.guild_config import get_config, set_config
from utils.perfis import ARQUIVO_PERFIS

PESOS_PADRAO = {"xp": 1, "vitoria": 10, "mvp": 20}


def _negrito(texto: str) -> str:
    """Converte letras/números ASCII pra Unicode Mathematical Bold (𝐀𝐁𝐂...𝟎𝟏𝟐).
    Usado só em rótulos e números — dígitos em negrito matemático têm largura
    consistente entre si, então a coluna de pontos fica alinhada mesmo com
    nomes (menções) de tamanhos diferentes."""
    resultado = []
    for ch in texto:
        if 'A' <= ch <= 'Z':
            resultado.append(chr(0x1D400 + (ord(ch) - ord('A'))))
        elif 'a' <= ch <= 'z':
            resultado.append(chr(0x1D41A + (ord(ch) - ord('a'))))
        elif '0' <= ch <= '9':
            resultado.append(chr(0x1D7CE + (ord(ch) - ord('0'))))
        else:
            resultado.append(ch)
    return ''.join(resultado)


class RankingGeral(commands.Cog):
    """Top global do servidor (P.C. — Pontos de Competição: XP + vitórias +
    MVPs combinados, com pesos ajustáveis). Painel automático que se atualiza
    sozinho a cada 10 minutos, editando a mesma mensagem, com menção clicável
    de cada jogador."""

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

    async def _montar_embed(self, guild: discord.Guild) -> discord.Embed:
        pesos = await self._pesos(guild.id)
        todos = await carregar(ARQUIVO_PERFIS, {})
        perfis_guild = todos.get(str(guild.id), {})

        pontuados = [(int(uid), self._pontuacao(perfil, pesos)) for uid, perfil in perfis_guild.items()]
        top = sorted(pontuados, key=lambda item: item[1], reverse=True)[:10]

        cabecalho = (
            f"╔═════════════════════════════════╗\n"
            f"║        {guild.name} | {_negrito('TOP 10')}        ║\n"
            f"╚═════════════════════════════════╝\n\n"
            f"「 {_negrito('RANKING COMPETITIVO')} 」\n\n"
        )

        if not top:
            descricao = cabecalho + "Ninguém pontuou ainda. Os primeiros resultados aprovados já entram no placar."
            return discord.Embed(description=descricao, color=0xFFD700)

        linhas_top = []
        for i, (uid, pontos) in enumerate(top, start=1):
            linhas_top.append(f"│ {_negrito('No.')}{_negrito(f'{i:02d}')}  — <@{uid}>")
            linhas_top.append(f"│           {_negrito(f'{int(pontos):03d}')} {_negrito('P.C.')}")
            if i != len(top):
                linhas_top.append("│")
        corpo = "\n".join(linhas_top)

        descricao = (
            f"{cabecalho}"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{_negrito('TOP 10')} — 𝐂𝐋𝐀𝐒𝐒𝐈𝐅𝐈𝐂𝐀𝐂̧𝐀̃𝐎\n\n"
            f"╭──────────────────────────────────────╮\n"
            f"{corpo}\n"
            f"╰──────────────────────────────────────╯\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"「 𝐀𝐓𝐔𝐀𝐋𝐈𝐙𝐀𝐂̧𝐀̃𝐎 」\n\n"
            f"A classificação é definida pela quantidade de P.C. — Pontos de Competição "
            f"acumulados por cada membro.\n\n"
            f"Novos resultados poderão alterar a posição dos participantes no Top 10.\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"「 {guild.name} | {_negrito('TOP 10')} 」"
        )
        return discord.Embed(description=descricao, color=0xFFD700)

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

        embed = await self._montar_embed(guild)
        mensagem_id = config.get("ranking_mensagem_id")

        if mensagem_id:
            try:
                msg = await canal.fetch_message(mensagem_id)
                await msg.edit(embed=embed)
                return
            except (discord.NotFound, discord.Forbidden):
                pass

        nova_msg = await canal.send(embed=embed)
        await set_config(guild.id, ranking_mensagem_id=nova_msg.id)

    @app_commands.command(name="ranking-canal", description="Define o canal do placar automático (atualiza sozinho a cada 10 min).")
    @app_commands.describe(canal="Canal onde o placar fica fixado")
    @app_commands.checks.has_permissions(administrator=True)
    async def ranking_canal(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_ranking_id=canal.id, ranking_mensagem_id=None)
        await interaction.response.send_message(f"✅ Placar automático configurado em {canal.mention}.", ephemeral=True)
        await self._atualizar_painel(interaction.guild)

    @app_commands.command(name="ranking-pesos", description="Define os pesos usados no cálculo de P.C. (Pontos de Competição).")
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

    @app_commands.command(name="ranking-geral", description="Mostra o Top 10 agora, sem esperar a atualização automática.")
    async def ranking_geral(self, interaction: discord.Interaction):
        embed = await self._montar_embed(interaction.guild)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(RankingGeral(bot))