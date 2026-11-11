from utils.apresentacao import criar_embed
import asyncio
import datetime
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.guild_config import lideranca_only
from utils.storage import carregar, salvar


ARQUIVO = "eventos.json"
CANAL_EVENTOS_PADRAO_ID = 1563995880623841337
CANAL_EVENTOS_LEGADO_ID = 1545835097830334536
ARQUIVO_AGENDA_PUBLICACAO = "agenda_publicacao.json"
ARQUIVO_METAS_MEMBROS = "agenda_metas_membros.json"
GUILD_NEMESIS_ID = 1563995879981981817
_EVENTOS_LOCK = asyncio.Lock()
_AGENDA_ATUALIZAR_CUSTOM_ID = "nemesis:agenda:atualizar"
_LOG = logging.getLogger(__name__)

FUSO_BRASIL = datetime.timezone(
    datetime.timedelta(hours=-3)
)


async def _todos_eventos():
    dados = await carregar(ARQUIVO, {})
    return dados if isinstance(dados, dict) else {}


async def _salvar_eventos(dados):
    await salvar(ARQUIVO, dados if isinstance(dados, dict) else {})


def _evento_para_dados(
    evento: discord.ScheduledEvent,
    guild_id: int,
    criado_por_id: int | None = None,
) -> dict:

    inicio = (
        evento.start_time.timestamp()
        if evento.start_time
        else None
    )

    fim = (
        evento.end_time.timestamp()
        if evento.end_time
        else None
    )

    return {
        "id": str(evento.id),
        "guild_id": guild_id,
        "evento_id": str(evento.id),
        "nome": evento.name,
        "descricao": evento.description or "",
        "canal_id": (
            evento.channel.id
            if evento.channel
            else None
        ),
        "canal_voz_id": (
            evento.channel.id
            if evento.channel
            and isinstance(
                evento.channel,
                discord.VoiceChannel,
            )
            else None
        ),
        "local": (
            str(evento.location)
            if evento.location
            else None
        ),
        "inicio": inicio,
        "fim": fim,
        "inicio_iso": (
            evento.start_time.isoformat()
            if evento.start_time
            else None
        ),
        "fim_iso": (
            evento.end_time.isoformat()
            if evento.end_time
            else None
        ),
        "status": evento.status.name,
        "entidade": evento.entity_type.name,
        "url": evento.url,
        "capa": (
            evento.cover_image.url
            if evento.cover_image
            else None
        ),
        "criado_por_id": criado_por_id,
        "atualizado_em": time.time(),
    }


def _atualizar_participantes(
    registro: dict,
    user_id: int,
    inscrito: bool,
    *,
    timestamp: float | None = None,
) -> tuple[dict, bool]:
    """Atualiza inscrições sem confundir RSVP com presença efetiva."""
    agora = float(timestamp or time.time())
    registro = dict(registro or {})
    historico = registro.get("participantes", [])
    atuais = registro.get("inscritos_ids", [])

    # Compatibilidade com registros antigos que guardavam apenas uma lista.
    if not isinstance(historico, list):
        historico = []
    if not isinstance(atuais, list):
        atuais = []

    historico_ids = []
    for item in historico:
        valor = item.get("user_id") if isinstance(item, dict) else item
        try:
            valor = int(valor)
        except (TypeError, ValueError):
            continue
        if valor not in historico_ids:
            historico_ids.append(valor)

    inscritos_ids = []
    for item in atuais:
        try:
            valor = int(item)
        except (TypeError, ValueError):
            continue
        if valor not in inscritos_ids:
            inscritos_ids.append(valor)

    participacoes = registro.get("historico_inscricoes", [])
    if not isinstance(participacoes, list):
        participacoes = []

    user_id = int(user_id)
    estava_inscrito = user_id in inscritos_ids
    if inscrito == estava_inscrito:
        registro["participantes"] = historico_ids
        registro["inscritos_ids"] = inscritos_ids
        registro["historico_inscricoes"] = participacoes[-500:]
        registro["total_inscritos"] = len(inscritos_ids)
        return registro, False

    if inscrito:
        inscritos_ids.append(user_id)
        if user_id not in historico_ids:
            historico_ids.append(user_id)
        participacoes.append({
            "user_id": user_id,
            "acao": "inscricao",
            "timestamp": agora,
        })
    else:
        inscritos_ids.remove(user_id)
        participacoes.append({
            "user_id": user_id,
            "acao": "cancelamento",
            "timestamp": agora,
        })

    registro["participantes"] = historico_ids
    registro["inscritos_ids"] = inscritos_ids
    registro["historico_inscricoes"] = participacoes[-500:]
    registro["total_inscritos"] = len(inscritos_ids)
    registro["atualizado_em"] = agora
    return registro, True


def _resumo_servidor(guild: discord.Guild) -> dict:
    """Métricas em tempo real calculadas a partir do cache atualizado pelo Gateway."""
    membros = list(getattr(guild, "members", []) or [])
    humanos = [m for m in membros if not getattr(m, "bot", False)]
    bots = [m for m in membros if getattr(m, "bot", False)]
    status_online = {discord.Status.online, discord.Status.idle, discord.Status.dnd}
    online = sum(getattr(m, "status", discord.Status.offline) in status_online for m in humanos)
    ausentes = sum(getattr(m, "status", discord.Status.offline) == discord.Status.idle for m in humanos)
    ocupados = sum(getattr(m, "status", discord.Status.offline) == discord.Status.dnd for m in humanos)
    canais_voz = list(getattr(guild, "voice_channels", []) or []) + list(getattr(guild, "stage_channels", []) or [])
    em_voz = {membro.id for canal in canais_voz for membro in (getattr(canal, "members", []) or []) if not getattr(membro, "bot", False)}
    total = int(getattr(guild, "member_count", 0) or len(membros))
    return {"total": total, "humanos_cache": len(humanos), "bots_cache": len(bots), "online": online, "ausentes": ausentes, "ocupados": ocupados, "offline_cache": max(0, len(humanos) - online), "voz": len(em_voz), "cache_completo": len(membros) >= total}


def _barra_progresso(atual: int, alvo: int, largura: int = 10) -> str:
    if alvo <= 0:
        return "░" * largura
    preenchido = max(0, min(largura, int((atual / alvo) * largura)))
    return "█" * preenchido + "░" * (largura - preenchido)


def _componentes_sao_agenda(componentes) -> bool:
    pendentes = list(componentes or [])
    while pendentes:
        componente = pendentes.pop()
        if getattr(componente, "custom_id", None) == _AGENDA_ATUALIZAR_CUSTOM_ID:
            return True
        if "NEMESIS_AGENDA_LIVE" in str(getattr(componente, "content", "") or ""):
            return True
        pendentes.extend(list(getattr(componente, "children", []) or []))
    return False


class AgendaAtualizarButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(label="Atualizar agora", emoji="🔄", style=discord.ButtonStyle.secondary, custom_id=_AGENDA_ATUALIZAR_CUSTOM_ID)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este painel pertence à NÊMESIS.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        atualizado = await self.cog.atualizar_agenda(interaction.guild, force=True)
        mensagem = "Agenda atualizada com os dados mais recentes do servidor." if atualizado else "Não foi possível atualizar a Agenda. Verifique as permissões do canal."
        await interaction.followup.send(mensagem, ephemeral=True)


class AgendaLayoutView(discord.ui.LayoutView):
    """Cartão Components V2 persistente da Agenda ao Vivo."""
    def __init__(self, cog, texto: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(texto[:3900]),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(AgendaAtualizarButton(cog)),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Nêmesis Systeam • NEMESIS_AGENDA_LIVE"),
            accent_colour=0x9F1239,
        ))


class Eventos(commands.Cog):
    """
    Sistema de eventos da NÊMESIS.

    Os eventos do Discord continuam sendo eventos nativos,
    e seus dados também são persistidos em eventos.json para histórico
    interno e recuperação após reinicializações.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._agenda_lock = asyncio.Lock()
        self._ultima_atualizacao_agenda = 0.0
        self.bot.add_view(AgendaLayoutView(self, "## 𓂀 NÊMESIS · AGENDA AO VIVO\n\nSincronizando os dados do servidor..."))
        self.atualizacao_periodica.start()

    def cog_unload(self):
        self.atualizacao_periodica.cancel()

    @tasks.loop(seconds=60)
    async def atualizacao_periodica(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is not None:
            await self.atualizar_agenda(guild, force=True)

    @atualizacao_periodica.before_loop
    async def antes_da_atualizacao_periodica(self):
        await self.bot.wait_until_ready()

    async def _canal_eventos(self, guild: discord.Guild):
        """Retorna o canal fixo da Agenda, sem misturá-lo com publicações de sorteios."""
        return guild.get_channel(CANAL_EVENTOS_PADRAO_ID)

    @app_commands.command(
        name="campeonato-agendar",
        description=(
            "Cria um campeonato como Evento Agendado "
            "do Discord."
        ),
    )
    @app_commands.describe(
        nome="Nome do campeonato",
        data_hora=(
            "Data e hora no formato "
            "DD/MM/AAAA HH:MM"
        ),
        descricao="Descrição do campeonato",
        canal_voz=(
            "Canal de voz onde o campeonato vai ocorrer"
        ),
    )
    @lideranca_only()
    async def campeonato_agendar(
        self,
        interaction: discord.Interaction,
        nome: str,
        data_hora: str,
        descricao: str,
        canal_voz: discord.VoiceChannel = None,
    ):

        try:

            dt_ingenuo = datetime.datetime.strptime(
                data_hora,
                "%d/%m/%Y %H:%M",
            )

        except ValueError:

            await interaction.response.send_message(
                "Data inválida. Use "
                "`DD/MM/AAAA HH:MM`.",
                ephemeral=True,
            )
            return

        inicio = dt_ingenuo.replace(
            tzinfo=FUSO_BRASIL
        )

        if inicio <= discord.utils.utcnow():

            await interaction.response.send_message(
                "Essa data já passou. "
                "Escolha uma data futura.",
                ephemeral=True,
            )
            return

        fim = (
            inicio
            + datetime.timedelta(
                hours=2
            )
        )

        try:

            if canal_voz:

                evento = (
                    await interaction.guild.create_scheduled_event(
                        name=nome,
                        description=descricao,
                        start_time=inicio,
                        end_time=fim,
                        channel=canal_voz,
                        entity_type=discord.EntityType.voice,
                        privacy_level=discord.PrivacyLevel.guild_only,
                    )
                )

            else:

                evento = (
                    await interaction.guild.create_scheduled_event(
                        name=nome,
                        description=descricao,
                        start_time=inicio,
                        end_time=fim,
                        entity_type=discord.EntityType.external,
                        location="A definir",
                        privacy_level=discord.PrivacyLevel.guild_only,
                    )
                )

        except discord.Forbidden:

            await interaction.response.send_message(
                "Não tenho permissão para criar "
                "eventos agendados neste servidor.",
                ephemeral=True,
            )
            return

        except discord.HTTPException:

            await interaction.response.send_message(
                "O Discord recusou a criação do evento.",
                ephemeral=True,
            )
            return

        await self._sincronizar_evento(
            evento,
            interaction.user.id,
        )

        await interaction.response.send_message(
            f"✓ Campeonato **{nome}** criado!\n"
            f"Evento: {evento.url}",
            ephemeral=True,
        )

    async def atualizar_agenda(self, guild: discord.Guild, *, force: bool = False):
        """Atualiza um único cartão com métricas do Gateway, eventos, sorteios e marcos."""
        if guild.id != GUILD_NEMESIS_ID:
            return False
        agora = time.time()
        async with self._agenda_lock:
            if not force and agora - self._ultima_atualizacao_agenda < 10:
                return True
            canal = guild.get_channel(CANAL_EVENTOS_PADRAO_ID)
            if canal is None:
                try:
                    canal = await guild.fetch_channel(CANAL_EVENTOS_PADRAO_ID)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    _LOG.exception("Canal Agenda não encontrado ou inacessível.")
                    return False
            if not isinstance(canal, discord.TextChannel):
                _LOG.error("O canal Agenda precisa ser um canal de texto.")
                return False

            resumo = _resumo_servidor(guild)
            eventos = sorted([
                evento for evento in (getattr(guild, "scheduled_events", []) or [])
                if evento.start_time and evento.start_time.timestamp() >= agora
                and str(getattr(evento.status, "name", evento.status)).lower() not in {"cancelled", "completed"}
            ], key=lambda evento: evento.start_time.timestamp())

            sorteios = await carregar("sorteios.json", {})
            sorteios = sorteios if isinstance(sorteios, dict) else {}
            sorteios_abertos = [item for item in sorteios.values() if isinstance(item, dict) and int(item.get("guild_id", 0) or 0) == guild.id and not item.get("encerrado") and float(item.get("fim") or 0) >= agora]
            sorteios_abertos.sort(key=lambda item: float(item.get("fim") or 0))

            metas_dados = await carregar(ARQUIVO_METAS_MEMBROS, {})
            metas_dados = metas_dados if isinstance(metas_dados, dict) else {}
            metas = metas_dados.get(str(guild.id), [])
            metas = [item for item in metas if isinstance(item, dict)] if isinstance(metas, list) else []
            metas.sort(key=lambda item: int(item.get("alvo", 0) or 0))
            metas_alteradas = False
            for meta in metas:
                alvo = int(meta.get("alvo", 0) or 0)
                if alvo > 0 and not meta.get("atingido_em") and resumo["total"] >= alvo:
                    meta["atingido_em"] = agora
                    meta["atingido_por_sincronizacao"] = True
                    metas_alteradas = True
            if metas_alteradas:
                metas_dados[str(guild.id)] = metas
                await salvar(ARQUIVO_METAS_MEMBROS, metas_dados)

            humanos_label = "humanos" if resumo["cache_completo"] else "humanos em cache"
            bots_label = "bots" if resumo["cache_completo"] else "bots em cache"
            linhas = [
                "## 𓂀 NÊMESIS · AGENDA AO VIVO",
                "Acompanhamento automático da comunidade, atividades e próximos compromissos.",
                "### 👥 MOVIMENTO DO SERVIDOR",
                f"**{resumo['total']:,} membros no servidor**".replace(",", "."),
                f"👤 {resumo['humanos_cache']:,} {humanos_label}  ·  🤖 {resumo['bots_cache']:,} {bots_label}".replace(",", "."),
                f"🟢 {resumo['online']:,} online  ·  🌙 {resumo['ausentes']:,} ausentes  ·  ⛔ {resumo['ocupados']:,} ocupados".replace(",", "."),
                f"⚫ {resumo['offline_cache']:,} offline no cache  ·  🔊 {resumo['voz']:,} em canais de voz".replace(",", "."),
            ]
            if not resumo["cache_completo"]:
                linhas.append("-# Presenças e divisão humano/bot consideram os membros atualmente carregados pelo Gateway.")
            linhas.append("### 📅 PRÓXIMOS EVENTOS")
            if eventos:
                for evento in eventos[:5]:
                    inicio = int(evento.start_time.timestamp())
                    nome = discord.utils.escape_markdown(str(evento.name)[:100])
                    linhas.append(f"**{nome}** · <t:{inicio}:F> (<t:{inicio}:R>)")
            else:
                linhas.append("Nenhum evento futuro publicado no Discord.")
            linhas.append("### 🎁 SORTEIOS EM ANDAMENTO")
            if sorteios_abertos:
                for sorteio in sorteios_abertos[:5]:
                    fim = int(float(sorteio.get("fim") or 0))
                    premio = discord.utils.escape_markdown(str(sorteio.get("premio") or "Sorteio")[:90])
                    linhas.append(f"**{premio}** · encerra <t:{fim}:R>")
            else:
                linhas.append("Nenhum sorteio ativo no momento.")
            linhas.append("### 🎯 MARCOS DA COMUNIDADE")
            if metas:
                for meta in metas[:6]:
                    alvo = int(meta.get("alvo", 0) or 0)
                    if alvo <= 0:
                        continue
                    atingido = bool(meta.get("atingido_em")) or resumo["total"] >= alvo
                    status = "✓ ALCANÇADO" if atingido else "◷ EM PROGRESSO"
                    barra = _barra_progresso(resumo["total"], alvo)
                    descricao = discord.utils.escape_markdown(str(meta.get("descricao") or "Marco da comunidade")[:80])
                    linhas.append(f"**{alvo:,} membros** · {status}\n**{barra}** · {min(resumo['total'], alvo):,}/{alvo:,}\n{descricao}".replace(",", "."))
            else:
                linhas.append("Nenhum marco cadastrado. A liderança pode registrar metas de crescimento.")
            linhas.extend(["### ⏱️ SINCRONIZAÇÃO", f"Dados recebidos do Discord · <t:{int(agora)}:R>"])
            texto = "\n\n".join(linhas)
            view = AgendaLayoutView(self, texto)

            estado = await carregar(ARQUIVO_AGENDA_PUBLICACAO, {})
            estado = estado if isinstance(estado, dict) else {}
            registro = estado.get(str(guild.id), {})
            mensagem = None
            if isinstance(registro, dict) and registro.get("message_id"):
                try:
                    mensagem = await canal.fetch_message(int(registro["message_id"]))
                except discord.NotFound:
                    mensagem = None
                except (discord.Forbidden, discord.HTTPException):
                    _LOG.exception("Não foi possível recuperar a mensagem existente da Agenda.")
                    return False
            if mensagem is None:
                try:
                    async for antiga in canal.history(limit=50):
                        if antiga.author.id == self.bot.user.id and (_componentes_sao_agenda(getattr(antiga, "components", [])) or any(embed.title == "𓂀 NÊMESIS · AGENDA" for embed in (antiga.embeds or []))):
                            mensagem = antiga
                            break
                except (discord.Forbidden, discord.HTTPException):
                    _LOG.exception("Falha ao procurar publicação anterior da Agenda.")
            try:
                if mensagem is None:
                    mensagem = await canal.send(view=view)
                else:
                    await mensagem.edit(content=None, embeds=[], attachments=[], view=view)
            except (discord.Forbidden, discord.HTTPException):
                _LOG.exception("Falha ao publicar/atualizar a Agenda.")
                return False
            estado[str(guild.id)] = {"channel_id": canal.id, "message_id": mensagem.id, "atualizado_em": agora, "versao": 2}
            await salvar(ARQUIVO_AGENDA_PUBLICACAO, estado)
            self._ultima_atualizacao_agenda = agora
            return True

    @app_commands.command(name="agenda", description="Publica ou atualiza o painel ao vivo da NÊMESIS.")
    @lideranca_only()
    async def agenda(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este sistema pertence à NÊMESIS.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        atualizado = await self.atualizar_agenda(interaction.guild, force=True)
        await interaction.followup.send("A Agenda ao Vivo foi sincronizada no canal oficial." if atualizado else "Não foi possível sincronizar a Agenda. Confira as permissões do canal.", ephemeral=True)

    @app_commands.command(
        name="agenda-meta-membros",
        description="Adiciona um marco à Agenda para uma quantidade de membros.",
    )
    @app_commands.describe(alvo="Quantidade de membros que marca o objetivo", descricao="Descrição do marco ou celebração")
    @lideranca_only()
    async def agenda_meta_membros(
        self,
        interaction: discord.Interaction,
        alvo: app_commands.Range[int, 1, 1000000],
        descricao: app_commands.Range[str, 3, 200],
    ):
        dados = await carregar(ARQUIVO_METAS_MEMBROS, {})
        dados = dados if isinstance(dados, dict) else {}
        metas = dados.get(str(interaction.guild.id), [])
        metas = metas if isinstance(metas, list) else []
        if any(isinstance(item, dict) and int(item.get("alvo", 0) or 0) == int(alvo) for item in metas):
            await interaction.response.send_message("Já existe um marco cadastrado para essa quantidade de membros.", ephemeral=True)
            return
        meta = {
            "id": f"META-{int(alvo)}",
            "alvo": int(alvo),
            "descricao": str(descricao).strip(),
            "criado_por": interaction.user.id,
            "criado_em": time.time(),
            "atingido_em": time.time() if (interaction.guild.member_count or 0) >= int(alvo) else None,
        }
        metas.append(meta)
        dados[str(interaction.guild.id)] = metas[-100:]
        await salvar(ARQUIVO_METAS_MEMBROS, dados)
        await self.atualizar_agenda(interaction.guild)
        situacao = "Esse marco já foi alcançado." if meta["atingido_em"] else "O marco aparecerá como em progresso na Agenda."
        await interaction.response.send_message(f"Marco de **{alvo:,} membros** registrado. {situacao}".replace(",", "."), ephemeral=True)

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        if membro.guild.id != GUILD_NEMESIS_ID:
            return
        dados = await carregar(ARQUIVO_METAS_MEMBROS, {})
        dados = dados if isinstance(dados, dict) else {}
        metas = dados.get(str(membro.guild.id), [])
        alterado = False
        for meta in metas if isinstance(metas, list) else []:
            if not isinstance(meta, dict) or meta.get("atingido_em"):
                continue
            if (membro.guild.member_count or 0) >= int(meta.get("alvo", 0) or 0):
                meta["atingido_em"] = time.time()
                meta["atingido_com_membro_id"] = membro.id
                alterado = True
        if alterado:
            dados[str(membro.guild.id)] = metas
            await salvar(ARQUIVO_METAS_MEMBROS, dados)
        await self.atualizar_agenda(membro.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, membro: discord.Member):
        if membro.guild.id == GUILD_NEMESIS_ID:
            await self.atualizar_agenda(membro.guild)

    @commands.Cog.listener()
    async def on_presence_update(self, antes: discord.Member, depois: discord.Member):
        if depois.guild.id == GUILD_NEMESIS_ID:
            await self.atualizar_agenda(depois.guild)

    @commands.Cog.listener()
    async def on_voice_state_update(self, membro: discord.Member, antes: discord.VoiceState, depois: discord.VoiceState):
        if membro.guild.id == GUILD_NEMESIS_ID and antes.channel != depois.channel:
            await self.atualizar_agenda(membro.guild)

    def _embed_evento(
        self,
        evento: discord.ScheduledEvent,
        titulo: str,
    ) -> discord.Embed:

        embed = criar_embed(
            title=f"📅 AGENDA NÊMESIS · {titulo.upper()[:120]}",
            description=(
                evento.description
                or "Este evento não possui uma descrição adicional."
            ),
            color=0x9F1239,
            rodape=None,
        )
        embed.set_author(name="NÊMESIS  /  EVENTOS E CAMPEONATOS")
        embed.add_field(name="EVENTO", value=f"**{evento.name[:200]}**", inline=False)
        embed.add_field(name="SITUAÇÃO", value=f"🟢 {str(evento.status).replace('_', ' ').title()}", inline=True)
        embed.add_field(name="FORMATO", value=str(evento.entity_type).replace('_', ' ').title(), inline=True)

        embed.add_field(
            name="🕒 INÍCIO",
            value=discord.utils.format_dt(
                evento.start_time,
                style="F",
            ),
            inline=True,
        )

        if evento.end_time:

            embed.add_field(
                name="🏁 ENCERRAMENTO",
                value=discord.utils.format_dt(
                    evento.end_time,
                    style="F",
                ),
                inline=True,
            )

        if evento.location:

            embed.add_field(
                name="📍 LOCAL",
                value=str(
                    evento.location
                ),
                inline=True,
            )

        if evento.cover_image:

            embed.set_image(
                url=evento.cover_image.url
            )

        embed.set_footer(text=f"EVENTO {evento.id}  •  Consulte o Discord para confirmar presença")

        return embed

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, evento: discord.ScheduledEvent):
        await self._sincronizar_evento(evento)
        await self.atualizar_agenda(evento.guild)

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, antes: discord.ScheduledEvent, depois: discord.ScheduledEvent):
        await self._sincronizar_evento(depois)
        await self.atualizar_agenda(depois.guild)

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, evento: discord.ScheduledEvent):
        async with _EVENTOS_LOCK:
            dados = await _todos_eventos()
            registro = dados.get(str(evento.id))
            if isinstance(registro, dict):
                registro["status"] = "deleted"
                registro["atualizado_em"] = time.time()
                dados[str(evento.id)] = registro
                await _salvar_eventos(dados)
        guild = getattr(evento, "guild", None)
        if guild is not None:
            await self.atualizar_agenda(guild)

    async def _registrar_inscricao(
        self,
        evento: discord.ScheduledEvent,
        usuario: discord.User | discord.Member,
        inscrito: bool,
    ) -> bool:
        """Persiste inscrição/cancelamento recebido pelo Gateway do Discord."""
        await self._sincronizar_evento(evento)
        async with _EVENTOS_LOCK:
            dados = await _todos_eventos()
            chave = str(evento.id)
            registro = dados.get(chave, {})
            if not isinstance(registro, dict):
                registro = _evento_para_dados(evento, evento.guild.id)
            registro, alterado = _atualizar_participantes(
                registro,
                usuario.id,
                inscrito,
            )
            if alterado:
                dados[chave] = registro
                await _salvar_eventos(dados)
            return alterado

    @commands.Cog.listener()
    async def on_scheduled_event_user_add(
        self,
        evento: discord.ScheduledEvent,
        usuario: discord.User,
    ):
        await self._registrar_inscricao(evento, usuario, True)

    @commands.Cog.listener()
    async def on_scheduled_event_user_remove(
        self,
        evento: discord.ScheduledEvent,
        usuario: discord.User,
    ):
        await self._registrar_inscricao(evento, usuario, False)

    @app_commands.command(
        name="evento-relatorio",
        description="Consulta inscrições e histórico de um evento.",
    )
    @app_commands.describe(evento_id="ID do evento agendado no Discord")
    @lideranca_only()
    async def evento_relatorio(
        self,
        interaction: discord.Interaction,
        evento_id: str,
    ):
        dados = await _todos_eventos()
        registro = dados.get(str(evento_id).strip())
        if not isinstance(registro, dict):
            await interaction.response.send_message(
                "Não encontrei esse evento no arquivo interno. "
                "Confira o ID ou sincronize os eventos atuais.",
                ephemeral=True,
            )
            return

        inscritos = registro.get("inscritos_ids", [])
        historico = registro.get("participantes", [])
        inscricoes = registro.get("historico_inscricoes", [])
        inscritos = inscritos if isinstance(inscritos, list) else []
        historico = historico if isinstance(historico, list) else []
        inscricoes = inscricoes if isinstance(inscricoes, list) else []

        embed = criar_embed(
            title="📅 RELATÓRIO DE EVENTO · NÊMESIS",
            description=(
                f"**{str(registro.get('nome') or 'Evento sem nome')[:200]}**\n"
                f"Situação: **{str(registro.get('status') or 'desconhecida').replace('_', ' ').title()}**"
            ),
            color=0x9F1239,
            rodape=None,
        )
        embed.add_field(name="INSCRITOS ATUAIS", value=str(len(inscritos)), inline=True)
        embed.add_field(name="JÁ SE INSCREVERAM", value=str(len(historico)), inline=True)
        embed.add_field(name="REGISTROS DE ALTERAÇÃO", value=str(len(inscricoes)), inline=True)

        if inscritos:
            linhas = [f"• <@{int(user_id)}>" for user_id in inscritos[:25]]
            embed.add_field(
                name="INSCRIÇÕES ATIVAS",
                value="\n".join(linhas),
                inline=False,
            )
        else:
            embed.add_field(
                name="INSCRIÇÕES ATIVAS",
                value="Nenhuma inscrição ativa registrada.",
                inline=False,
            )

        embed.set_footer(text=f"Evento {evento_id} · Inscrição não confirma presença física")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="eventos-sincronizar",
        description=(
            "Atualiza o registro interno dos eventos atuais do Discord."
        ),
    )
    @lideranca_only()
    async def eventos_sincronizar(
        self,
        interaction: discord.Interaction,
    ):

        eventos = (
            interaction.guild.scheduled_events
        )

        for evento in eventos:
            await self._sincronizar_evento(evento)

        await self.atualizar_agenda(interaction.guild)
        await interaction.response.send_message(
            f"✓ {len(eventos)} evento(s) "
            "sincronizado(s) no armazenamento interno do bot.",
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot
):
    await bot.add_cog(
        Eventos(bot)
    )