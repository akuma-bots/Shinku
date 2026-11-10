import logging
import time

import discord
from discord.ext import commands, tasks

from utils import temporadas_missoes
from utils.apresentacao import criar_embed, aplicar_identidade_servidor
from utils.guild_config import membro_tem_octogono

log = logging.getLogger(__name__)
EMOJIS_POSICAO = {1: "🥇", 2: "🥈", 3: "🥉"}



def _card_temporada(origem: discord.ui.View, embed: discord.Embed | None = None,
                    titulo: str = "CENTRAL DE TEMPORADAS", descricao: str = "") -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    partes = [f"## {embed.title if embed and embed.title else titulo}"]
    if embed and embed.description:
        partes.append(embed.description)
    elif descricao:
        partes.append(descricao)
    if embed:
        for campo in embed.fields:
            partes.append(f"**{campo.name}**\n{campo.value}")
        if embed.footer and embed.footer.text:
            partes.append(f"-# {embed.footer.text}")
    componentes = [
        discord.ui.TextDisplay("\n\n".join(partes)[:3900]),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ]
    botoes, seletores = [], []
    for item in origem.children:
        if isinstance(item, discord.ui.ChannelSelect):
            novo = discord.ui.ChannelSelect(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, channel_types=list(item.channel_types),
                custom_id=item.custom_id, disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, options=list(item.options),
                custom_id=item.custom_id, disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
            botoes.append(novo)
    for seletor in seletores:
        componentes.append(discord.ui.ActionRow(seletor))
    for inicio in range(0, len(botoes), 5):
        componentes.append(discord.ui.ActionRow(*botoes[inicio:inicio + 5]))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# NÊMESIS • Temporadas e Competitivo"),
    ])
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


def _xp(valor):
    try:
        return f"{max(0, int(valor or 0)):,}".replace(",", ".")
    except (TypeError, ValueError, OverflowError):
        return "0"


def _data(valor):
    try:
        return f"<t:{int(float(valor))}:f>"
    except (TypeError, ValueError, OverflowError):
        return "—"


def _autorizado(interaction, owner_id=None):
    return bool(interaction.guild and isinstance(interaction.user, discord.Member)
                and membro_tem_octogono(interaction.user)
                and (owner_id is None or interaction.user.id == int(owner_id)))


def _embed_status(guild, bot, resultado):
    if not resultado.get("configurada"):
        embed = criar_embed(
            "🏆 TEMPORADAS DE MISSÕES · NÊMESIS",
            "Nenhuma temporada foi iniciada.\n\nA liderança pode configurar duração, meta coletiva, reconhecimentos e canal de encerramento pela Central de Gestão de Missões.",
            cor=0x9F2035,
            rodape="◈ TEMPORADAS SAZONAIS • PROGRESSÃO PERMANENTE INDEPENDENTE",
        )
        return aplicar_identidade_servidor(embed, guild, bot, banner=True)
    estado = resultado["estado"]
    restante = int(resultado["restante_segundos"])
    dias, horas = restante // 86400, (restante % 86400) // 3600
    progresso = resultado["progresso_percentual"]
    preenchido = min(16, max(0, round(progresso / 100 * 16)))
    barra = "█" * preenchido + "░" * (16 - preenchido)
    linhas = [
        f"{EMOJIS_POSICAO.get(item['posicao'], '#' + str(item['posicao']))} <@{item['user_id']}> — **{_xp(item['xp'])} XP sazonal**"
        for item in resultado["ranking"][:10]
    ]
    embed = criar_embed(
        f"🏆 TEMPORADA DE MISSÕES · #{estado['numero_atual']}",
        (
            f"⟡・ **Período:** {_data(estado['inicio_timestamp'])} até {_data(estado['fim_timestamp'])}\n"
            f"⟡・ **Tempo restante:** {dias}d {horas}h\n\n"
            f"**META COLETIVA**\n**{barra}** · **{progresso:.1f}%**\n"
            f"**{_xp(resultado['xp_coletivo'])} / {_xp(estado['meta_xp'])} XP**\n\n"
            f"Provas aprovadas: **{resultado['provas_aprovadas']}** · Participantes: **{resultado['participantes']}**\n\n"
            "**RANKING SAZONAL · TOP 10**\n"
            + ("\n".join(linhas) if linhas else "Ainda não há pontuação nesta temporada.")
        ),
        cor=0x9F2035,
        rodape="◈ Apenas missões aprovadas no período • XP permanente não é alterado",
    )
    return aplicar_identidade_servidor(embed, guild, bot, banner=True)


def _embed_config(guild, bot, estado):
    canal = f"<#{estado['canal_id']}>" if estado.get("canal_id") else "Não definido"
    embed = criar_embed(
        "⚙️ CENTRAL DE TEMPORADAS · CONFIGURAÇÃO",
        (
            f"**Temporada:** #{estado['numero_atual']}\n**Duração:** {estado['duracao_dias']} dias\n"
            f"**Meta coletiva:** {_xp(estado['meta_xp'])} XP\n**Início:** {_data(estado.get('inicio_timestamp'))}\n"
            f"**Encerramento:** {_data(estado.get('fim_timestamp'))}\n**Canal de anúncio:** {canal}\n\n"
            "**RECONHECIMENTOS SAZONAIS**\n"
            f"🥇 {estado['recompensas'].get('1') or 'Não configurado'}\n"
            f"🥈 {estado['recompensas'].get('2') or 'Não configurado'}\n"
            f"🥉 {estado['recompensas'].get('3') or 'Não configurado'}\n\n"
            "Distinções sazonais não concedem XP permanente, patente ou cargo organizacional."
        ),
        cor=0x9F2035,
        rodape="◈ ACESSO EXCLUSIVO À LIDERANÇA DO OCTÓGONO",
    )
    return aplicar_identidade_servidor(embed, guild, bot, banner=True)


def _embed_historico(guild, bot, historico):
    linhas = []
    for registro in historico:
        primeiro = next(iter(registro.get("ranking", [])), None)
        campeao = f"<@{primeiro['user_id']}> · {_xp(primeiro['xp'])} XP" if primeiro else "Sem pontuação"
        meta = "Meta coletiva alcançada" if registro.get("meta_atingida") else "Meta não alcançada"
        linhas.append(
            f"**TEMPORADA #{registro['numero']}** · {meta}\nCampeão: {campeao}\n"
            f"Resultado coletivo: {_xp(registro.get('xp_coletivo'))}/{_xp(registro.get('meta_xp'))} XP\n"
            f"Encerrada: {_data(registro.get('encerrada_em'))}"
        )
    embed = criar_embed(
        "📚 ARQUIVO · TEMPORADAS DE MISSÕES",
        "\n\n".join(linhas)[:4000] if linhas else "Nenhuma temporada foi encerrada ainda.",
        cor=0x9F2035,
        rodape="◈ HISTÓRICO SAZONAL PRESERVADO",
    )
    return aplicar_identidade_servidor(embed, guild, bot, banner=True)


class ConfigurarTemporadaModal(discord.ui.Modal, title="Configurar temporada de missões"):
    duracao = discord.ui.TextInput(label="Duração em dias (1–365)", default="30", max_length=3)
    meta = discord.ui.TextInput(label="Meta coletiva em XP", default="10000", max_length=9)
    ouro = discord.ui.TextInput(label="Reconhecimento do 1º lugar", default="Distinção de Campeão da Temporada", max_length=100)
    prata = discord.ui.TextInput(label="Reconhecimento do 2º lugar", default="Distinção de Vice-Campeão", max_length=100)
    bronze = discord.ui.TextInput(label="Reconhecimento do 3º lugar", default="Distinção de Destaque", max_length=100)

    def __init__(self, cog, owner_id, mensagem, estado):
        super().__init__(timeout=300)
        self.cog, self.owner_id, self.mensagem = cog, int(owner_id), mensagem
        self.duracao.default = str(estado.get("duracao_dias", 30))
        self.meta.default = str(estado.get("meta_xp", 10000))
        recompensas = estado.get("recompensas", {})
        self.ouro.default = str(recompensas.get("1") or "Distinção de Campeão da Temporada")[:100]
        self.prata.default = str(recompensas.get("2") or "Distinção de Vice-Campeão")[:100]
        self.bronze.default = str(recompensas.get("3") or "Distinção de Destaque")[:100]

    async def on_submit(self, interaction):
        if not _autorizado(interaction, self.owner_id):
            await interaction.response.send_message("Acesso não autorizado.", ephemeral=True)
            return
        try:
            await temporadas_missoes.configurar(
                interaction.guild.id, duracao_dias=int(self.duracao.value),
                meta_xp=int(self.meta.value), recompensa_1=self.ouro.value,
                recompensa_2=self.prata.value, recompensa_3=self.bronze.value,
            )
        except (ValueError, TypeError) as erro:
            await interaction.response.send_message(f"Configuração inválida: {erro}", ephemeral=True)
            return
        await interaction.response.send_message("Configuração da temporada atualizada.", ephemeral=True)
        await self.cog._editar_central(self.mensagem, interaction.guild, self.owner_id)


class CanalTemporadaSelect(discord.ui.ChannelSelect):
    def __init__(self, view):
        self.pai = view
        super().__init__(channel_types=[discord.ChannelType.text],
                         placeholder="◈ Selecionar canal de anúncios da temporada",
                         min_values=1, max_values=1, row=0)

    async def callback(self, interaction):
        if not _autorizado(interaction, self.pai.owner_id):
            await interaction.response.send_message("Acesso não autorizado.", ephemeral=True)
            return
        await temporadas_missoes.configurar(interaction.guild.id, canal_id=self.values[0].id)
        await self.pai.cog._atualizar_interacao(interaction, self.pai.owner_id)


class TemporadaPublicaView(discord.ui.View):
    def __init__(self, cog, owner_id):
        super().__init__(timeout=180)
        self.cog, self.owner_id = cog, int(owner_id)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este painel pertence a outro integrante.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.success)
    async def atualizar(self, interaction, button):
        resultado = await temporadas_missoes.obter_status(interaction.guild.id)
        await interaction.response.edit_message(
            view=_card_temporada(
                TemporadaPublicaView(self.cog, self.owner_id),
                _embed_status(interaction.guild, self.cog.bot, resultado),
            )
        )

    @discord.ui.button(label="Histórico", emoji="📚", style=discord.ButtonStyle.secondary)
    async def historico(self, interaction, button):
        dados = await temporadas_missoes.listar_historico(interaction.guild.id, limite=10)
        await interaction.response.edit_message(
            view=_card_temporada(
                TemporadaPublicaView(self.cog, self.owner_id),
                _embed_historico(interaction.guild, self.cog.bot, dados),
            )
        )

    @discord.ui.button(label="Fechar", emoji="❌", style=discord.ButtonStyle.danger)
    async def fechar(self, interaction, button):
        await interaction.response.edit_message(content="Consulta de temporada encerrada.", embed=None, view=None)


class ConfirmarEncerramentoTemporadaView(discord.ui.View):
    def __init__(self, cog, owner_id):
        super().__init__(timeout=60)
        self.cog, self.owner_id = cog, int(owner_id)

    async def interaction_check(self, interaction):
        if not _autorizado(interaction, self.owner_id):
            await interaction.response.send_message("Apenas a liderança que abriu esta central pode encerrar a temporada.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmar encerramento", emoji="🏁", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction, button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            registro = await temporadas_missoes.encerrar_temporada(interaction.guild.id)
        except ValueError as erro:
            await interaction.followup.send(f"Não foi possível encerrar: {erro}", ephemeral=True)
            return
        await self.cog._processar_anuncios_pendentes(interaction.guild)
        await interaction.followup.send(
            f"Temporada **#{registro['numero']}** arquivada. A temporada **#{registro['numero'] + 1}** começou. "
            "O XP histórico e a progressão organizacional permaneceram intactos.", ephemeral=True,
        )
        try:
            await interaction.message.edit(content="Encerramento concluído.", embed=None, view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    @discord.ui.button(label="Cancelar", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction, button):
        await interaction.response.edit_message(content="Encerramento cancelado.", embed=None, view=None)


class TemporadasMissoesCentralView(discord.ui.View):
    def __init__(self, cog, owner_id):
        super().__init__(timeout=300)
        self.cog, self.owner_id = cog, int(owner_id)
        self.add_item(CanalTemporadaSelect(self))

    async def interaction_check(self, interaction):
        if not _autorizado(interaction, self.owner_id):
            await interaction.response.send_message("A Central de Temporadas é exclusiva da liderança do OCTÓGONO e da sessão que a abriu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Configurar", emoji="⚙️", style=discord.ButtonStyle.primary, row=1)
    async def configurar(self, interaction, button):
        estado = await temporadas_missoes.get_estado(interaction.guild.id)
        await interaction.response.send_modal(
            ConfigurarTemporadaModal(self.cog, self.owner_id, interaction.message, estado)
        )

    @discord.ui.button(label="Histórico", emoji="📚", style=discord.ButtonStyle.secondary, row=1)
    async def historico(self, interaction, button):
        dados = await temporadas_missoes.listar_historico(interaction.guild.id, limite=10)
        await interaction.response.edit_message(
            view=_card_temporada(
                TemporadasMissoesCentralView(self.cog, self.owner_id),
                _embed_historico(interaction.guild, self.cog.bot, dados),
            )
        )

    @discord.ui.button(label="Encerrar agora", emoji="🏁", style=discord.ButtonStyle.danger, row=1)
    async def encerrar(self, interaction, button):
        estado = await temporadas_missoes.get_estado(interaction.guild.id)
        if estado.get("inicio_timestamp") is None:
            await interaction.response.send_message("Não existe uma temporada ativa para encerrar.", ephemeral=True)
            return
        await interaction.response.send_message(
            view=_card_temporada(
                ConfirmarEncerramentoTemporadaView(self.cog, self.owner_id),
                None, "CONFIRMAR ENCERRAMENTO",
                "Confirme o encerramento. O resultado será arquivado e uma nova temporada começará imediatamente.",
            ), ephemeral=True,
        )

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.success, row=2)
    async def atualizar(self, interaction, button):
        await self.cog._atualizar_interacao(interaction, self.owner_id)

    @discord.ui.button(label="Fechar", emoji="✕", style=discord.ButtonStyle.secondary, row=2)
    async def fechar(self, interaction, button):
        await interaction.response.edit_message(content="Central de Temporadas encerrada.", embed=None, view=None)


class TemporadasMissoes(commands.Cog):
    """Automação sazonal e interface integrada às centrais de Missões."""

    def __init__(self, bot):
        self.bot = bot
        self.verificar_temporadas.start()

    def cog_unload(self):
        self.verificar_temporadas.cancel()

    async def _anunciar_resultado(self, guild, registro):
        canal_id = registro.get("canal_id")
        if not canal_id:
            return True
        canal = guild.get_channel(int(canal_id))
        if canal is None:
            try:
                canal = await guild.fetch_channel(int(canal_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                log.warning("Canal de anúncio da temporada não encontrado (guild=%s).", guild.id)
                return False
        linhas = []
        for item in registro.get("ranking", [])[:10]:
            posicao = int(item.get("posicao", 0) or 0)
            linha = f"{EMOJIS_POSICAO.get(posicao, '#' + str(posicao))} <@{int(item['user_id'])}> — **{_xp(item['xp'])} XP sazonal**"
            recompensa = (registro.get("recompensas") or {}).get(str(posicao))
            if recompensa:
                linha += f"\n└ {recompensa}"
            linhas.append(linha)
        estado_meta = "Meta coletiva alcançada" if registro.get("meta_atingida") else "Meta coletiva não alcançada"
        descricao = (
            f"**{estado_meta}** · {_xp(registro.get('xp_coletivo'))}/{_xp(registro.get('meta_xp'))} XP\n"
            f"Provas aprovadas: **{registro.get('provas_aprovadas', 0)}** · Participantes: **{registro.get('participantes', 0)}**\n\n"
            + ("\n".join(linhas) if linhas else "Nenhum participante pontuou nesta temporada.")
        )
        embed = criar_embed(f"🏁 TEMPORADA DE MISSÕES {registro['numero']} · ENCERRADA", descricao[:4000],
                            cor=0x9F2035, rodape="◈ NÊMESIS • HISTÓRICO SAZONAL PRESERVADO")
        aplicar_identidade_servidor(embed, guild, self.bot, banner=True)
        try:
            await canal.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Falha ao publicar encerramento da temporada (guild=%s).", guild.id)
            return False

    async def _processar_anuncios_pendentes(self, guild):
        for registro in await temporadas_missoes.listar_anuncios_pendentes(guild.id):
            if await self._anunciar_resultado(guild, registro):
                await temporadas_missoes.marcar_anuncio_enviado(guild.id, registro["numero"])

    async def _montar_central(self, guild):
        estado = await temporadas_missoes.get_estado(guild.id)
        resultado = await temporadas_missoes.obter_status(guild.id)
        return _embed_status(guild, self.bot, resultado) if resultado.get("configurada") else _embed_config(guild, self.bot, estado)

    async def _editar_central(self, mensagem, guild, owner_id):
        if mensagem is None:
            return
        try:
            await mensagem.edit(content=None, embeds=[], attachments=[])
            await mensagem.edit(
                view=_card_temporada(
                    TemporadasMissoesCentralView(self, owner_id),
                    await self._montar_central(guild),
                )
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            log.exception("Falha ao atualizar a Central de Temporadas.")

    async def _atualizar_interacao(self, interaction, owner_id):
        await interaction.response.edit_message(
            view=_card_temporada(
                TemporadasMissoesCentralView(self, owner_id),
                await self._montar_central(interaction.guild),
            )
        )

    async def abrir_central(self, interaction, owner_id=None):
        responsavel = int(owner_id or interaction.user.id)
        if not _autorizado(interaction, responsavel):
            await interaction.response.send_message("A Central de Temporadas é restrita à liderança do OCTÓGONO.", ephemeral=True)
            return
        await interaction.response.send_message(
            view=_card_temporada(
                TemporadasMissoesCentralView(self, responsavel),
                await self._montar_central(interaction.guild),
            ), ephemeral=True,
        )

    async def abrir_status_publico(self, interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Este painel só funciona dentro do servidor.", ephemeral=True)
            return
        resultado = await temporadas_missoes.obter_status(interaction.guild.id)
        await interaction.response.send_message(
            view=_card_temporada(
                TemporadaPublicaView(self, interaction.user.id),
                _embed_status(interaction.guild, self.bot, resultado),
            ), ephemeral=True,
        )

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


async def setup(bot):
    await bot.add_cog(TemporadasMissoes(bot))
