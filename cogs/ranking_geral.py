from utils.apresentacao import criar_embed
import time

import discord

from discord import app_commands

from discord.ext import (
    commands,
    tasks,
)

from utils.storage import carregar

from utils.guild_config import (
    get_config,
    set_config,
    membro_tem_lideranca,
)

from utils.perfis import (
    ARQUIVO_PERFIS,
    resetar_perfis_globais,
)

from utils.competitivo_sync import (
    ARQUIVO_COMPETITIVO,
    migrar_perfil_se_necessario,
    registrar_tempo_top_global,
    reiniciar_temporada_global,
    atualizar_temporada_global,
)


# O cálculo de tempo no Top 10 roda a cada minuto, mas o painel do Discord
# não deve ser editado com essa frequência: mensagens antigas têm limite de edições.
INTERVALO_RANKING_MINUTOS = 1
INTERVALO_PAINEL_GERAL_SEGUNDOS = 20 * 60


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


class SeletorCanalRanking(discord.ui.ChannelSelect):
    def __init__(self, central):
        self.central = central
        super().__init__(
            placeholder="Selecionar canal do ranking geral",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.central.autorizar(interaction):
            return
        canal = self.values[0]
        await set_config(
            self.central.guild.id,
            canal_ranking_id=canal.id,
            ranking_mensagem_id=0,
        )
        cog_missoes = interaction.client.get_cog("Missoes")
        if cog_missoes is not None:
            await cog_missoes._atualizar_ranking_geral(self.central.guild)
        await interaction.response.edit_message(
            embed=await self.central.criar_embed(),
            view=self.central,
        )


class ConfirmarTemporadaRankingView(discord.ui.View):
    def __init__(self, central, numero_esperado: int):
        super().__init__(timeout=90)
        self.central = central
        self.numero_esperado = int(numero_esperado)

    @discord.ui.button(label="Confirmar encerramento", style=discord.ButtonStyle.danger, emoji="🏁", row=0)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.central.autorizar(interaction):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = await reiniciar_temporada_global(numero_esperado=self.numero_esperado)
        if not dados.get("_reinicio_aplicado"):
            await interaction.followup.send(
                "A temporada já foi alterada por outra operação. Reabra a central para consultar o estado atual.",
                ephemeral=True,
            )
            return
        cog_missoes = interaction.client.get_cog("Missoes")
        if cog_missoes is not None:
            await cog_missoes._atualizar_ranking_geral(self.central.guild)
        await interaction.followup.send(
            f"Temporada **#{self.numero_esperado}** encerrada. "
            f"A temporada **#{self.numero_esperado + 1}** foi iniciada; "
            "o XP total, as estatísticas permanentes e o histórico foram preservados.",
            ephemeral=True,
        )
        for item in self.children:
            item.disabled = True
        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="↩️", row=0)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.central.autorizar(interaction):
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Encerramento da temporada cancelado.",
            view=self,
        )


class ResetarRankingGlobalModal(discord.ui.Modal, title="Reset global da NÊMESIS"):
    confirmacao = discord.ui.TextInput(
        label="Digite RESETAR NÊMESIS para confirmar",
        placeholder="RESETAR NÊMESIS",
        required=True,
        max_length=32,
    )

    def __init__(self, central):
        super().__init__(timeout=120)
        self.central = central

    async def on_submit(self, interaction: discord.Interaction):
        if (
            interaction.guild is None
            or interaction.guild.id != self.central.guild.id
            or interaction.user.id != self.central.owner_id
            or not membro_tem_lideranca(interaction.user)
        ):
            await interaction.response.send_message(
                "Acesso não autorizado para executar o reset global.",
                ephemeral=True,
            )
            return
        if str(self.confirmacao.value).strip().upper() != "RESETAR NÊMESIS":
            await interaction.response.send_message(
                "Confirmação inválida. Nenhum dado foi alterado.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        operation_id = self.central.reset_operation_id
        resultado = await resetar_perfis_globais(operation_id=operation_id)
        from utils import ranking_missoes_jogos
        quantidade_jogos = await ranking_missoes_jogos.resetar_pontuacoes_jogos(
            self.central.guild.id,
            operation_id=operation_id,
        )

        painel_atualizado = True
        cog_missoes = interaction.client.get_cog("Missoes")
        if cog_missoes is not None:
            try:
                await cog_missoes._atualizar_ranking_geral(self.central.guild)
            except Exception:
                painel_atualizado = False

        mensagem = (
            "RESET GLOBAL EXECUTADO.\n"
            f"Perfis locais: **{resultado['quantidade_local']}**.\n"
            f"Perfis competitivos: **{resultado['quantidade_global']}**.\n"
            f"Rankings por jogo reiniciados: **{quantidade_jogos}**.\n"
            "XP, estatísticas, medalhas, patentes, pontuação PvE e histórico sazonal foram zerados. "
            "O catálogo de missões, identidades e configurações foram preservados."
        )
        if not painel_atualizado:
            mensagem += "\nO reset foi salvo, mas o painel público não pôde ser atualizado automaticamente."
        await interaction.followup.send(mensagem, ephemeral=True)
        import uuid
        self.central.reset_operation_id = uuid.uuid4().hex


class CentralRankingGeralView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild, owner_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.owner_id = int(owner_id)
        import uuid
        self.reset_operation_id = uuid.uuid4().hex
        self.add_item(SeletorCanalRanking(self))

    async def autorizar(self, interaction: discord.Interaction) -> bool:
        if (
            interaction.guild is None
            or interaction.guild.id != self.guild.id
            or interaction.user.id != self.owner_id
            or not membro_tem_lideranca(interaction.user)
        ):
            await interaction.response.send_message(
                "Esta central pertence à liderança que a abriu ou seu acesso expirou.",
                ephemeral=True,
            )
            return False
        return True

    async def criar_embed(self) -> discord.Embed:
        config = await get_config(self.guild.id)
        dados = await atualizar_temporada_global()
        estado = dados.get("temporada_global", {})
        numero = int(estado.get("numero", 1) or 1)
        inicio = float(estado.get("inicio_timestamp") or time.time())
        duracao = max(1, int(estado.get("duracao_dias", 30) or 30)) * 86400
        restante = max(0, int(inicio + duracao - time.time()))
        dias, resto = divmod(restante, 86400)
        horas = resto // 3600
        canal_id = config.get("canal_ranking_id")
        canal_texto = f"<#{canal_id}>" if canal_id else "Não configurado"
        historico = estado.get("historico", [])
        embed = criar_embed(
            "Central de Ranking Competitivo",
            "Gerencie o canal público e o ciclo sazonal do ranking global. "
            "O encerramento preserva as estatísticas permanentes.",
        )
        embed.add_field(name="Temporada atual", value=f"**#{numero}**", inline=True)
        embed.add_field(name="Tempo restante", value=f"**{dias}d {horas}h**", inline=True)
        embed.add_field(
            name="Histórico preservado",
            value=f"**{len(historico) if isinstance(historico, list) else 0} temporadas**",
            inline=True,
        )
        embed.add_field(name="Canal do ranking", value=canal_texto, inline=False)
        embed.set_footer(text="Acesso exclusivo à liderança • NÊMESIS")
        return embed

    @discord.ui.button(label="Reiniciar temporada", style=discord.ButtonStyle.danger, emoji="🏁", row=1)
    async def solicitar_reinicio(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        dados = await atualizar_temporada_global()
        numero = int(dados.get("temporada_global", {}).get("numero", 1) or 1)
        await interaction.response.send_message(
            f"Confirme o encerramento da temporada **#{numero}**. "
            "O Top 10 será arquivado e uma nova temporada começará. O XP total permanece; apenas o XP sazonal reinicia.",
            view=ConfirmarTemporadaRankingView(self, numero),
            ephemeral=True,
        )

    @discord.ui.button(label="Atualizar ranking", style=discord.ButtonStyle.success, emoji="🔄", row=1)
    async def atualizar_ranking(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        cog_missoes = interaction.client.get_cog("Missoes")
        if cog_missoes is not None:
            await cog_missoes._atualizar_ranking_geral(self.guild)
        await interaction.response.edit_message(
            embed=await self.criar_embed(),
            view=self,
        )

    @discord.ui.button(label="Resetar dados globais", style=discord.ButtonStyle.danger, emoji="⚠️", row=2)
    async def solicitar_reset_global(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        await interaction.response.send_modal(ResetarRankingGlobalModal(self))

    @discord.ui.button(label="Fechar central", style=discord.ButtonStyle.secondary, emoji="❌", row=1)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Central de Ranking Competitivo encerrada.",
            embed=None,
            view=self,
        )


class RankingGeral(
    commands.Cog
):

    def __init__(
        self,
        bot: commands.Bot,
    ):

        self.bot = bot
        self._ultima_atualizacao_painel_geral = {}

        self.atualizar_ranking_automatico.start()


    def cog_unload(self):

        self.atualizar_ranking_automatico.cancel()


    async def abrir_central(self, interaction: discord.Interaction, owner_id: int):
        if (
            interaction.guild is None
            or interaction.user.id != int(owner_id)
            or not membro_tem_lideranca(interaction.user)
        ):
            await interaction.response.send_message(
                "A central de ranking é restrita à liderança autorizada.",
                ephemeral=True,
            )
            return
        view = CentralRankingGeralView(self, interaction.guild, owner_id)
        await interaction.response.send_message(
            embed=await view.criar_embed(),
            view=view,
            ephemeral=True,
        )


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
            xp_temporada = int(perfil.get("xp_temporada", perfil.get("xp", 0)) or 0)
            xp = int(perfil.get("xp", 0) or 0)
            vitorias = int(perfil.get("vitorias", 0) or 0)
            derrotas = int(perfil.get("derrotas", 0) or 0)
            tempo_top = int(perfil.get("tempo_top_global_segundos", 0) or 0)
            pontuados.append((user_id, xp_temporada, vitorias, xp, derrotas, tempo_top))

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
                "A posição é definida pelo XP acumulado na temporada. Vitórias, derrotas e permanência no Top 10 "
                "são métricas complementares; o histórico das temporadas concluídas é preservado."
            ),
            color=0x9F1239,
            rodape=None,
        )
        embed.set_author(name="NÊMESIS  /  LIGA GLOBAL")
        embed.add_field(name="TEMPORADA", value=f"**#{numero_temporada}**", inline=True)
        embed.add_field(name="REINÍCIO EM", value=f"**{dias}d {horas}h**", inline=True)
        embed.add_field(name="CLASSIFICADOS", value=f"**{len(pontuados)}**", inline=True)

        if not top:
            embed.add_field(
                name="QUADRO AINDA VAZIO",
                value="Nenhum jogador possui XP competitivo nesta temporada. Participe das atividades competitivas oficiais para entrar na classificação.",
                inline=False,
            )
        else:
            medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
            for posicao, (uid, xp_temporada, vitorias, xp, derrotas, tempo_top) in enumerate(top, start=1):
                minutos = max(0, tempo_top) // 60
                horas_top, minutos_restantes = divmod(minutos, 60)
                tempo_texto = f"{horas_top}h {minutos_restantes}min"
                selo = medalhas.get(posicao, f"#{posicao:02d}")
                membro = guild.get_member(uid)
                nome = membro.display_name if membro else f"Jogador {uid}"
                embed.add_field(
                    name=f"{selo}  {nome[:70]}  ·  {xp_temporada:,} XP".replace(",", ".")[:256],
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
                cog_missoes = self.bot.get_cog("Missoes")
                if cog_missoes is not None:
                    agora = time.monotonic()
                    ultima = self._ultima_atualizacao_painel_geral.get(guild.id)
                    if ultima is None:
                        self._ultima_atualizacao_painel_geral[guild.id] = agora
                    elif agora - ultima >= INTERVALO_PAINEL_GERAL_SEGUNDOS:
                        await cog_missoes._atualizar_ranking_geral(guild)
                        self._ultima_atualizacao_painel_geral[guild.id] = agora

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
        name="ranking-geral",
        description="Mostra onde acessar o ranking geral da NÊMESIS.",
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
            f"Acesse {mention} para consultar o **Ranking Geral da NÊMESIS**, que soma as pontuações de missões em todos os jogos em uma única classificação.",
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
):

    await bot.add_cog(
        RankingGeral(bot)
    )