from utils.apresentacao import criar_embed
import time

import discord

from discord import app_commands

from discord.ext import (
    commands,
    tasks,
)

from utils.storage import carregar, salvar

from utils.guild_config import (
    get_config,
    set_config,
)

from utils.perfis import (
    ARQUIVO_PERFIS,
)

from utils.competitivo_sync import (
    ARQUIVO_COMPETITIVO,
    migrar_perfil_se_necessario,
    registrar_tempo_top_global,
    reiniciar_temporada_global,
)


# O cálculo de tempo no Top 10 roda a cada minuto, mas o painel do Discord
# não deve ser editado com essa frequência: mensagens antigas têm limite de edições.
INTERVALO_RANKING_MINUTOS = 1
INTERVALO_PAINEL_JOGOS_SEGUNDOS = 20 * 60


def _negrito(
    texto: str,
) -> str:

    resultado = []

    for ch in texto:

        if "A" <= ch <= "Z":

            resultado.append(
                chr(
                    0x1D400
                    + (
                        ord(ch)
                        - ord("A")
                    )
                )
            )

        elif "a" <= ch <= "z":

            resultado.append(
                chr(
                    0x1D41A
                    + (
                        ord(ch)
                        - ord("a")
                    )
                )
            )

        elif "0" <= ch <= "9":

            resultado.append(
                chr(
                    0x1D7CE
                    + (
                        ord(ch)
                        - ord("0")
                    )
                )
            )

        else:

            resultado.append(ch)

    return "".join(resultado)


class RankingGeral(
    commands.Cog
):

    def __init__(
        self,
        bot: commands.Bot,
    ):

        self.bot = bot
        self._ultima_atualizacao_painel_jogos = {}

        self.atualizar_ranking_automatico.start()


    def cog_unload(self):

        self.atualizar_ranking_automatico.cancel()


    async def _sincronizar_migracao(
        self,
        guild: discord.Guild,
    ):

        dados = await carregar(
            ARQUIVO_COMPETITIVO,
            {
                "catalogo": [],
                "perfis": {},
            },
        )

        dados.setdefault(
            "perfis",
            {},
        )

        existentes = set(
            dados["perfis"].keys()
        )

        perfis = await carregar(
            ARQUIVO_PERFIS,
            {},
        )

        perfis_guild = perfis.get(
            str(guild.id),
            {},
        )

        for uid, perfil in perfis_guild.items():

            if uid in existentes:
                continue

            membro = guild.get_member(
                int(uid)
            )

            nome = (
                membro.display_name
                if membro
                else ""
            )

            await migrar_perfil_se_necessario(
                user_id=int(uid),
                nome=nome,
                perfil_bot=perfil,
            )


    async def _montar_embed(self, guild: discord.Guild) -> discord.Embed:
        """Painel global sazonal com quadro de líderes e estatísticas em cartões."""
        await self._sincronizar_migracao(guild)
        dados = await registrar_tempo_top_global()
        perfis = dados.get("perfis", {})
        pontuados = []
        for uid, perfil in perfis.items():
            try:
                user_id = int(uid)
            except (TypeError, ValueError):
                continue
            pontos = int(perfil.get("pontos_temporada", perfil.get("pontos", 0)) or 0)
            xp = int(perfil.get("xp", 0) or 0)
            vitorias = int(perfil.get("vitorias", 0) or 0)
            derrotas = int(perfil.get("derrotas", 0) or 0)
            tempo_top = int(perfil.get("tempo_top_global_segundos", 0) or 0)
            pontuados.append((user_id, pontos, vitorias, xp, derrotas, tempo_top))

        top = sorted(pontuados, key=lambda item: (item[1], item[2]), reverse=True)[:10]
        estado = dados.get("temporada_global", {})
        inicio = float(estado.get("inicio_timestamp") or 0)
        duracao = int(estado.get("duracao_dias", 30) or 30) * 86400
        restante = max(0, int(inicio + duracao - __import__("time").time()))
        dias, resto = divmod(restante, 86400)
        horas = resto // 3600
        numero_temporada = int(estado.get("numero", 1) or 1)

        embed = criar_embed(
            title="🏆 RANKING GLOBAL · TEMPORADA COMPETITIVA",
            description=(
                "**CLASSIFICAÇÃO OFICIAL NÊMESIS**\n"
                "A posição é definida pela pontuação sazonal. XP, vitórias, derrotas e permanência no Top 10 "
                "são métricas complementares; o histórico das temporadas concluídas é preservado."
            ),
            color=0xB51F32,
            rodape=None,
        )
        embed.set_author(name="NÊMESIS  /  LIGA GLOBAL")
        embed.add_field(name="TEMPORADA", value=f"**#{numero_temporada}**", inline=True)
        embed.add_field(name="REINÍCIO EM", value=f"**{dias}d {horas}h**", inline=True)
        embed.add_field(name="CLASSIFICADOS", value=f"**{len(pontuados)}**", inline=True)

        if not top:
            embed.add_field(
                name="QUADRO AINDA VAZIO",
                value="Nenhum jogador possui pontos nesta temporada. Participe das atividades competitivas oficiais para entrar na classificação.",
                inline=False,
            )
        else:
            medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
            for posicao, (uid, pontos, vitorias, xp, derrotas, tempo_top) in enumerate(top, start=1):
                minutos = max(0, tempo_top) // 60
                horas_top, minutos_restantes = divmod(minutos, 60)
                tempo_texto = f"{horas_top}h {minutos_restantes}min"
                selo = medalhas.get(posicao, f"#{posicao:02d}")
                membro = guild.get_member(uid)
                nome = membro.display_name if membro else f"Jogador {uid}"
                embed.add_field(
                    name=f"{selo}  {nome[:70]}  ·  {pontos:,} P.C.".replace(",", ".")[:256],
                    value=(
                        f"<@{uid}>\n"
                        f"**VITÓRIAS** {vitorias}  ·  **DERROTAS** {derrotas}\n"
                        f"**XP TOTAL** {xp:,}  ·  **TEMPO NO TOP 10** {tempo_texto}"
                    ).replace(",", ".")[:1024],
                    inline=False,
                )

        embed.set_footer(text=f"{guild.name}  •  Temporadas preservadas no histórico  •  Atualização automática")
        return embed

    @tasks.loop(
        minutes=INTERVALO_RANKING_MINUTOS
    )
    async def atualizar_ranking_automatico(
        self,
    ):

        try:
            # A temporada global continua avançando mesmo sem canal de ranking configurado.
            await registrar_tempo_top_global()
        except Exception as erro:
            print(f"[RankingGeral] Falha ao atualizar temporada global: {erro}")

        for guild in self.bot.guilds:

            try:

                await self._atualizar_painel(
                    guild
                )

                # O tempo de permanência no Top 10 precisa ser contabilizado por minuto.
                # A edição da mensagem pública é limitada separadamente para evitar 429/30046.
                from utils import ranking_missoes_jogos
                await ranking_missoes_jogos.atualizar_tempo_top_jogos(guild.id)

                cog_missoes = self.bot.get_cog("Missoes")
                if cog_missoes is not None:
                    agora = time.monotonic()
                    ultima = self._ultima_atualizacao_painel_jogos.get(guild.id)
                    if ultima is None:
                        # A sincronização inicial do cog Missoes publica/atualiza o painel.
                        self._ultima_atualizacao_painel_jogos[guild.id] = agora
                    elif agora - ultima >= INTERVALO_PAINEL_JOGOS_SEGUNDOS:
                        await cog_missoes._atualizar_ranking_jogo(guild, "shigaku")
                        self._ultima_atualizacao_painel_jogos[guild.id] = agora

            except Exception as erro:

                print(
                    "[RankingGeral] "
                    f"Falha ao atualizar "
                    f"{guild.id}: {erro}"
                )


    @atualizar_ranking_automatico.before_loop
    async def antes_de_comecar(
        self,
    ):

        await self.bot.wait_until_ready()


    async def _atualizar_painel(
        self,
        guild: discord.Guild,
    ):
        """Remove o painel antigo; o ranking por jogo é gerenciado por cogs.missoes."""
        config = await get_config(guild.id)
        mensagem_id = config.get("ranking_mensagem_id")
        if not mensagem_id:
            return
        try:
            mensagem_id = int(mensagem_id)
        except (TypeError, ValueError):
            await set_config(guild.id, ranking_mensagem_id=0)
            return

        candidatos = [config.get("canal_ranking_id"), 1545834182406574241]
        vistos = set()
        mensagem_removida = False
        for valor in candidatos:
            try:
                canal_id = int(valor) if valor else None
            except (TypeError, ValueError):
                canal_id = None
            if not canal_id or canal_id in vistos:
                continue
            vistos.add(canal_id)
            canal = guild.get_channel(canal_id)
            if canal is None:
                try:
                    canal = await guild.fetch_channel(canal_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue
            try:
                mensagem = await canal.fetch_message(mensagem_id)
                await mensagem.delete()
                mensagem_removida = True
                break
            except discord.NotFound:
                mensagem_removida = True
                break
            except (discord.Forbidden, discord.HTTPException) as erro:
                print(f"[RankingGeral] Não foi possível remover o ranking antigo: {erro}")

        if mensagem_removida:
            await set_config(guild.id, ranking_mensagem_id=0)
            print(f"[RankingGeral] Referência do ranking antigo removida em {guild.id}.")


    @app_commands.command(
        name="ranking-canal",
        description=(
            "Define o canal do ranking automático."
        ),
    )
    @app_commands.describe(
        canal=(
            "Canal onde o ranking "
            "ficará publicado."
        ),
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def ranking_canal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ):

        await set_config(
            interaction.guild.id,
            canal_ranking_id=canal.id,
            ranking_mensagem_id=None,
        )

        await interaction.response.send_message(
            f"Ranking automático configurado "
            f"em {canal.mention}.",
            ephemeral=True,
        )

        await self._atualizar_painel(
            interaction.guild
        )


    @app_commands.command(
        name="resetar-perfis-global",
        description="Zera os perfis e o Top Global da NÊMESIS.",
    )
    @app_commands.describe(
        confirmacao="Selecione a confirmação para executar o reset completo."
    )
    @app_commands.choices(confirmacao=[
        app_commands.Choice(
            name="CONFIRMAR RESET COMPLETO",
            value="CONFIRMAR RESET COMPLETO",
        )
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def resetar_perfis_global(
        self,
        interaction: discord.Interaction,
        confirmacao: app_commands.Choice[str],
    ):
        if confirmacao.value != "CONFIRMAR RESET COMPLETO":
            await interaction.response.send_message(
                "Reset cancelado: confirmação inválida.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        import time
        agora = time.time()

        # Zera perfis locais usados pelo /perfil em todos os servidores.
        todos_perfis = await carregar(ARQUIVO_PERFIS, {})
        quantidade_local = 0
        campos_zero = {
            "xp": 0,
            "vitorias": 0,
            "derrotas": 0,
            "kills": 0,
            "deaths": 0,
            "mvps": 0,
            "sequencia_atual": 0,
            "maior_sequencia": 0,
            "medalhas": [],
            "patente": None,
        }
        for dados_guilda in todos_perfis.values():
            if not isinstance(dados_guilda, dict):
                continue
            for perfil in dados_guilda.values():
                if not isinstance(perfil, dict):
                    continue
                for campo, valor in campos_zero.items():
                    perfil[campo] = list(valor) if isinstance(valor, list) else valor
                quantidade_local += 1
        await salvar(ARQUIVO_PERFIS, todos_perfis)

        # Preserva o catálogo competitivo e as identidades já registradas.
        competitivo = await carregar(
            ARQUIVO_COMPETITIVO,
            {"catalogo": [], "perfis": {}},
        )
        competitivo.setdefault("catalogo", [])
        competitivo.setdefault("perfis", {})
        quantidade_global = 0
        for perfil in competitivo["perfis"].values():
            if not isinstance(perfil, dict):
                continue
            perfil["pontos"] = 0
            perfil["pontos_temporada"] = 0
            perfil["xp"] = 0
            perfil["vitorias"] = 0
            perfil["derrotas"] = 0
            perfil["kills"] = 0
            perfil["deaths"] = 0
            perfil["mvps"] = 0
            perfil["sequencia_atual"] = 0
            perfil["maior_sequencia"] = 0
            perfil["medalhas"] = []
            perfil["patente"] = None
            perfil["kdr"] = 0
            perfil["tempo_top_global_segundos"] = 0
            perfil["em_top_global"] = False
            perfil["ultima_verificacao_top_global"] = agora
            quantidade_global += 1

        competitivo["temporada_global"] = {
            "numero": 1,
            "inicio_timestamp": agora,
            "duracao_dias": 30,
            "historico": [],
        }
        await salvar(ARQUIVO_COMPETITIVO, competitivo)

        # O ranking por jogo usa um armazenamento próprio; reseta-o junto dos perfis globais.
        from utils import ranking_missoes_jogos
        quantidade_rankings_jogo = await ranking_missoes_jogos.resetar_pontuacoes_jogos(
            interaction.guild.id
        )
        cog_missoes = interaction.client.get_cog("Missoes")
        if cog_missoes is not None:
            for slug in ranking_missoes_jogos.JOGOS:
                await cog_missoes._atualizar_ranking_jogo(interaction.guild, slug)

        await interaction.followup.send(
            "RESET COMPLETO EXECUTADO.\n"
            f"Perfis locais zerados: **{quantidade_local}**.\n"
            f"Perfis do ranking competitivo zerados: **{quantidade_global}**.\n"
            "P.C., XP, vitórias, derrotas, K/D, MVPs, sequências, medalhas e "
            "tempo no Top 10 foram zerados. Os rankings de Shigaku, Gakuran e Fistborn "
            f"também foram limpos ({quantidade_rankings_jogo} rankings). O histórico sazonal "
            "foi limpo e uma nova temporada de 30 dias foi iniciada. O catálogo de missões foi preservado.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ranking-geral",
        description="Mostra onde acessar o novo ranking por jogo.",
    )
    async def ranking_geral(
        self,
        interaction: discord.Interaction,
    ):
        config = await get_config(interaction.guild.id)
        canal_id = config.get("canal_ranking_id") or 1545834182406574241
        canal = interaction.guild.get_channel(int(canal_id))
        mention = canal.mention if canal is not None else f"<#{canal_id}>"
        await interaction.response.send_message(
            f"O ranking global antigo foi substituído. Acesse {mention} e use os botões "
            "**Ranking anterior** e **Próximo ranking** para alternar entre Shigaku, Gakuran e Fistborn.",
            ephemeral=True,
        )
    @app_commands.command(
        name="temporada-reiniciar",
        description="Encerra a temporada atual e inicia outra sem apagar estatísticas acumuladas.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def temporada_reiniciar(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            dados = await reiniciar_temporada_global()
            estado = dados.get("temporada_global", {})
            numero = int(estado.get("numero", 2) or 2)
            await interaction.followup.send(
                f"Temporada reiniciada. A nova temporada é **#{numero}** e dura 30 dias. "
                "Pontos sazonais foram zerados; o histórico da temporada anterior, "
                "P.C. acumulados, XP, vitórias, derrotas e tempo no Top 10 foram preservados.",
                ephemeral=True,
            )
            if interaction.guild:
                await self._atualizar_painel(interaction.guild)
        except Exception as erro:
            print(f"[RankingGeral] Falha ao reiniciar temporada: {erro}")
            await interaction.followup.send(
                "Não foi possível reiniciar a temporada. Verifique os logs do bot.",
                ephemeral=True,
            )


async def setup(
    bot: commands.Bot,
):

    await bot.add_cog(
        RankingGeral(bot)
    )