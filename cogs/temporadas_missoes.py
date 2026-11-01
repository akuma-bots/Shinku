import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils import temporadas_missoes
from utils.apresentacao import criar_embed, aplicar_identidade_servidor
from utils.guild_config import lideranca_only


log = logging.getLogger(__name__)
EMOJIS_POSICAO = {1: "🥇", 2: "🥈", 3: "🥉"}


def _formatar_xp(valor):
    try:
        return f"{max(0, int(valor or 0)):,}".replace(",", ".")
    except (TypeError, ValueError, OverflowError):
        return "0"


def _formatar_data(timestamp):
    try:
        return f"<t:{int(float(timestamp))}:f>"
    except (TypeError, ValueError, OverflowError):
        return "—"


class TemporadasMissoes(commands.GroupCog, group_name="temporadas-missoes",
                         group_description="Temporadas, metas coletivas e ranking sazonal de missões."):
    """Temporadas de missões independentes da progressão permanente."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verificar_temporadas.start()

    def cog_unload(self):
        self.verificar_temporadas.cancel()

    def _identidade(self, embed, guild):
        return aplicar_identidade_servidor(embed, guild, self.bot)

    async def _anunciar_resultado(self, guild: discord.Guild, registro: dict) -> bool:
        canal_id = registro.get("canal_id")
        if not canal_id:
            return True
        canal = guild.get_channel(int(canal_id))
        if canal is None:
            try:
                canal = await guild.fetch_channel(int(canal_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                log.warning("Canal de anúncio da temporada de missões não encontrado (guild=%s).", guild.id)
                return False

        linhas = []
        for item in registro.get("ranking", [])[:10]:
            posicao = int(item.get("posicao", 0) or 0)
            emoji = EMOJIS_POSICAO.get(posicao, f"#{posicao}")
            recompensa = (registro.get("recompensas") or {}).get(str(posicao))
            linha = f"{emoji} <@{int(item['user_id'])}> — **{_formatar_xp(item['xp'])} XP sazonal**"
            if recompensa:
                linha += f"\n└ {recompensa}"
            linhas.append(linha)

        meta = _formatar_xp(registro.get("meta_xp", 0))
        coletado = _formatar_xp(registro.get("xp_coletivo", 0))
        estado_meta = "Meta coletiva alcançada" if registro.get("meta_atingida") else "Meta coletiva não alcançada"
        descricao = (
            f"**{estado_meta}** · {coletado}/{meta} XP\n"
            f"Provas aprovadas: **{registro.get('provas_aprovadas', 0)}** · "
            f"Participantes: **{registro.get('participantes', 0)}**\n\n"
            + ("\n".join(linhas) if linhas else "Nenhum participante pontuou nesta temporada.")
        )
        embed = criar_embed(
            title=f"🏁 TEMPORADA DE MISSÕES {registro['numero']} · ENCERRADA",
            description=descricao[:4000],
            cor=0x9F2035,
            rodape="◈ NÊMESIS • HISTÓRICO SAZONAL PRESERVADO",
        )
        self._identidade(embed, guild)
        try:
            await canal.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Falha ao publicar encerramento da temporada de missões (guild=%s).", guild.id)
            return False

    async def _processar_anuncios_pendentes(self, guild: discord.Guild):
        pendentes = await temporadas_missoes.listar_anuncios_pendentes(guild.id)
        for registro in pendentes:
            enviado = await self._anunciar_resultado(guild, registro)
            if enviado:
                await temporadas_missoes.marcar_anuncio_enviado(guild.id, registro["numero"])

    @tasks.loop(minutes=15)
    async def verificar_temporadas(self):
        for guild in self.bot.guilds:
            try:
                estado = await temporadas_missoes.get_estado(guild.id)
                fim = estado.get("fim_timestamp")
                if estado.get("inicio_timestamp") is not None and fim is not None and time.time() >= fim:
                    await temporadas_missoes.encerrar_temporada(guild.id)
                await self._processar_anuncios_pendentes(guild)
            except Exception:
                log.exception("Falha ao verificar temporada de missões (guild=%s).", guild.id)

    @verificar_temporadas.before_loop
    async def antes_de_verificar(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name="configurar", description="Configura duração, meta coletiva e recompensas da temporada de missões.")
    @app_commands.describe(
        duracao_dias="Duração da temporada (1 a 365 dias)",
        meta_xp="Meta coletiva de XP de missões aprovadas",
        canal="Canal para anunciar o encerramento",
        recompensa_ouro="Reconhecimento do 1º lugar",
        recompensa_prata="Reconhecimento do 2º lugar",
        recompensa_bronze="Reconhecimento do 3º lugar",
    )
    @lideranca_only()
    async def configurar(
        self,
        interaction: discord.Interaction,
        duracao_dias: app_commands.Range[int, 1, 365] = None,
        meta_xp: app_commands.Range[int, 1, 100000000] = None,
        canal: discord.TextChannel = None,
        recompensa_ouro: str = None,
        recompensa_prata: str = None,
        recompensa_bronze: str = None,
    ):
        try:
            estado = await temporadas_missoes.configurar(
                interaction.guild.id,
                duracao_dias=duracao_dias,
                meta_xp=meta_xp,
                canal_id=canal.id if canal else None,
                recompensa_1=recompensa_ouro,
                recompensa_2=recompensa_prata,
                recompensa_3=recompensa_bronze,
            )
        except (ValueError, TypeError) as erro:
            await interaction.response.send_message(f"❌ {erro}", ephemeral=True)
            return

        canal_texto = f"<#{estado['canal_id']}>" if estado.get("canal_id") else "Não definido"
        embed = criar_embed(
            title="⚙️ CONFIGURAÇÃO · TEMPORADAS DE MISSÕES",
            description=(
                f"**Temporada ativa:** #{estado['numero_atual']}\n"
                f"**Duração:** {estado['duracao_dias']} dias\n"
                f"**Meta coletiva:** {_formatar_xp(estado['meta_xp'])} XP\n"
                f"**Encerramento:** {_formatar_data(estado['fim_timestamp'])}\n"
                f"**Canal de anúncio:** {canal_texto}\n\n"
                "**Reconhecimentos**\n"
                f"🥇 {estado['recompensas'].get('1') or 'Não configurado'}\n"
                f"🥈 {estado['recompensas'].get('2') or 'Não configurado'}\n"
                f"🥉 {estado['recompensas'].get('3') or 'Não configurado'}"
            ),
            cor=0x9F2035,
        )
        self._identidade(embed, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="status", description="Consulta a temporada de missões, a meta coletiva e o ranking sazonal.")
    async def status(self, interaction: discord.Interaction):
        resultado = await temporadas_missoes.obter_status(interaction.guild.id)
        if not resultado["configurada"]:
            await interaction.response.send_message(
                "Nenhuma temporada de missões foi iniciada. A liderança pode usar /temporadas-missoes configurar.",
                ephemeral=True,
            )
            return

        estado = resultado["estado"]
        restante = int(resultado["restante_segundos"])
        dias = restante // 86400
        horas = (restante % 86400) // 3600
        progresso = resultado["progresso_percentual"]
        preenchido = min(16, max(0, round(progresso / 100 * 16)))
        barra = "█" * preenchido + "░" * (16 - preenchido)
        linhas = []
        for item in resultado["ranking"][:10]:
            posicao = item["posicao"]
            marca = EMOJIS_POSICAO.get(posicao, f"#{posicao}")
            linhas.append(f"{marca} <@{item['user_id']}> — **{_formatar_xp(item['xp'])} XP**")

        embed = criar_embed(
            title=f"🏆 TEMPORADA DE MISSÕES · #{estado['numero_atual']}",
            description=(
                f"⟡・ **Período:** {_formatar_data(estado['inicio_timestamp'])} até {_formatar_data(estado['fim_timestamp'])}\n"
                f"⟡・ **Tempo restante:** {dias}d {horas}h\n\n"
                f"**META COLETIVA**\n"
                f"{barra} **{progresso:.1f}%**\n"
                f"**{_formatar_xp(resultado['xp_coletivo'])} / {_formatar_xp(estado['meta_xp'])} XP**\n\n"
                f"Provas aprovadas: **{resultado['provas_aprovadas']}** · "
                f"Participantes: **{resultado['participantes']}**\n\n"
                "**RANKING SAZONAL**\n"
                + ("\n".join(linhas) if linhas else "Ainda não há pontuação nesta temporada.")
            ),
            cor=0x9F2035,
            rodape="◈ Pontuação calculada apenas com missões aprovadas nesta temporada",
        )
        self._identidade(embed, interaction.guild)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="historico", description="Consulta os resultados das temporadas de missões encerradas.")
    async def historico(self, interaction: discord.Interaction):
        historico = await temporadas_missoes.listar_historico(interaction.guild.id, limite=10)
        if not historico:
            await interaction.response.send_message("Ainda não há temporadas de missões encerradas.", ephemeral=True)
            return
        linhas = []
        for registro in historico:
            primeiro = next(iter(registro.get("ranking", [])), None)
            campeao = f"<@{primeiro['user_id']}> · {_formatar_xp(primeiro['xp'])} XP" if primeiro else "Sem pontuação"
            meta = "Meta alcançada" if registro.get("meta_atingida") else "Meta não alcançada"
            linhas.append(
                f"**Temporada #{registro['numero']}** · {meta}\n"
                f"Campeão: {campeao}\n"
                f"Resultado coletivo: {_formatar_xp(registro.get('xp_coletivo'))}/"
                f"{_formatar_xp(registro.get('meta_xp'))} XP"
            )
        embed = criar_embed(
            title="📚 HISTÓRICO · TEMPORADAS DE MISSÕES",
            description="\n\n".join(linhas)[:4000],
            cor=0x9F2035,
            rodape="◈ Resultados arquivados • XP histórico preservado",
        )
        self._identidade(embed, interaction.guild)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="conquistas", description="Consulta suas distinções e recompensas das temporadas encerradas.")
    async def conquistas(self, interaction: discord.Interaction):
        registros = await temporadas_missoes.listar_recompensas_usuario(
            interaction.guild.id, interaction.user.id, limite=20
        )
        if not registros:
            await interaction.response.send_message(
                "Você ainda não possui distinções registradas em temporadas de missões.",
                ephemeral=True,
            )
            return
        linhas = []
        for item in registros:
            emoji = EMOJIS_POSICAO.get(item["posicao"], f"#{item['posicao']}")
            recompensa = item["recompensa"] or "Distinção sazonal registrada"
            linhas.append(
                f"{emoji} **Temporada #{item['temporada']}** · "
                f"{_formatar_xp(item['xp_sazonal'])} XP sazonal\\n"
                f"└ {recompensa}"
            )
        embed = criar_embed(
            title="🏅 MINHAS DISTINÇÕES · TEMPORADAS DE MISSÕES",
            description="\\n\\n".join(linhas)[:4000],
            cor=0x9F2035,
            rodape="◈ Reconhecimentos sazonais • Não alteram XP ou patente permanente",
        )
        self._identidade(embed, interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="encerrar", description="Encerra a temporada de missões e inicia a próxima.")
    @lideranca_only()
    async def encerrar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            registro = await temporadas_missoes.encerrar_temporada(interaction.guild.id)
        except ValueError as erro:
            await interaction.followup.send(f"❌ {erro}", ephemeral=True)
            return
        await self._processar_anuncios_pendentes(interaction.guild)
        await interaction.followup.send(
            f"✅ Temporada de missões #{registro['numero']} encerrada e arquivada. "
            f"A temporada #{registro['numero'] + 1} já foi iniciada. "
            "O XP histórico e a progressão organizacional não foram alterados.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TemporadasMissoes(bot))
