from utils.apresentacao import criar_embed
import asyncio
import datetime
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.guild_config import get_config, set_config, lideranca_only
from utils.storage import carregar, salvar


ARQUIVO = "eventos.json"
CANAL_EVENTOS_PADRAO_ID = 1563995880623841337
CANAL_EVENTOS_LEGADO_ID = 1545835097830334536
ARQUIVO_AGENDA_PUBLICACAO = "agenda_publicacao.json"
ARQUIVO_METAS_MEMBROS = "agenda_metas_membros.json"
_EVENTOS_LOCK = asyncio.Lock()
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


class Eventos(commands.Cog):
    """
    Sistema de eventos da NÊMESIS.

    Os eventos do Discord continuam sendo eventos nativos,
    e seus dados também são persistidos em eventos.json para histórico
    interno e recuperação após reinicializações.
    """

    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot

    async def _canal_eventos(
        self,
        guild: discord.Guild,
    ):

        config = await get_config(
            guild.id
        )

        canal_id = config.get(
            "canal_eventos_id"
        ) or CANAL_EVENTOS_PADRAO_ID
        if int(canal_id) == CANAL_EVENTOS_LEGADO_ID:
            canal_id = CANAL_EVENTOS_PADRAO_ID

        return (
            guild.get_channel(canal_id)
            if canal_id
            else None
        )

    async def _sincronizar_evento(
        self,
        evento: discord.ScheduledEvent,
        criado_por_id: int | None = None,
    ):

        async with _EVENTOS_LOCK:
            dados = await _todos_eventos()
            antigo = dados.get(str(evento.id), {})
            if not isinstance(antigo, dict):
                antigo = {}

            registro = _evento_para_dados(
                evento,
                evento.guild.id,
                criado_por_id or antigo.get("criado_por_id"),
            )
            registro["criado_em"] = antigo.get("criado_em") or time.time()
            participantes = antigo.get("participantes", [])
            registro["participantes"] = participantes if isinstance(participantes, list) else []

            dados[str(evento.id)] = registro
            await _salvar_eventos(dados)
            return registro

    @app_commands.command(
        name="configurar-canal-eventos",
        description=(
            "Define onde o bot anuncia os eventos agendados."
        ),
    )
    @app_commands.describe(
        canal=(
            "Canal de texto para os anúncios de evento"
        ),
    )
    @lideranca_only()
    async def configurar_canal_eventos(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ):

        await set_config(
            interaction.guild.id,
            canal_eventos_id=canal.id,
        )

        await interaction.response.send_message(
            f"✓ Eventos agendados agora são anunciados "
            f"em {canal.mention}.",
            ephemeral=True,
        )

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

    async def atualizar_agenda(self, guild: discord.Guild):
        """Mantém uma única publicação de agenda com eventos, sorteios e marcos."""
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

        agora = time.time()
        eventos = await _todos_eventos()
        eventos_abertos = [
            item for item in eventos.values()
            if isinstance(item, dict)
            and int(item.get("guild_id", guild.id) or guild.id) == guild.id
            and item.get("status") not in {"cancelled", "completed", "deleted"}
            and float(item.get("inicio") or 0) >= agora
        ]
        eventos_abertos.sort(key=lambda item: float(item.get("inicio") or 0))

        sorteios = await carregar("sorteios.json", {})
        sorteios = sorteios if isinstance(sorteios, dict) else {}
        sorteios_abertos = [
            item for item in sorteios.values()
            if isinstance(item, dict)
            and int(item.get("guild_id", 0) or 0) == guild.id
            and not item.get("encerrado")
            and float(item.get("fim") or 0) >= agora
        ]
        sorteios_abertos.sort(key=lambda item: float(item.get("fim") or 0))

        metas_dados = await carregar(ARQUIVO_METAS_MEMBROS, {})
        metas_dados = metas_dados if isinstance(metas_dados, dict) else {}
        metas = metas_dados.get(str(guild.id), [])
        metas = metas if isinstance(metas, list) else []
        metas.sort(key=lambda item: int(item.get("alvo", 0) or 0) if isinstance(item, dict) else 0)

        embed = criar_embed(
            "𓂀 NÊMESIS · AGENDA",
            "Calendário central de eventos, encerramentos de sorteios e marcos da comunidade.",
            color=0x9F1239,
            rodape="NÊMESIS • AGENDA OFICIAL • Atualização automática",
        )
        if eventos_abertos:
            linhas = [
                f"**{item.get('nome', 'Evento')[:100]}**\n"
                f"Início: <t:{int(float(item.get('inicio') or 0))}:F> "
                f"(<t:{int(float(item.get('inicio') or 0))}:R>)"
                for item in eventos_abertos[:10]
            ]
            embed.add_field(name="📅 EVENTOS PROGRAMADOS", value="\n\n".join(linhas)[:1024], inline=False)
        else:
            embed.add_field(name="📅 EVENTOS PROGRAMADOS", value="Nenhum evento futuro registrado.", inline=False)

        if sorteios_abertos:
            linhas = [
                f"**{item.get('premio', 'Sorteio')[:100]}** · "
                f"encerra <t:{int(float(item.get('fim') or 0))}:R> "
                f"(<t:{int(float(item.get('fim') or 0))}:F>)"
                for item in sorteios_abertos[:10]
            ]
            embed.add_field(name="🎁 SORTEIOS EM ANDAMENTO", value="\n".join(linhas)[:1024], inline=False)
        else:
            embed.add_field(name="🎁 SORTEIOS EM ANDAMENTO", value="Nenhum sorteio ativo no momento.", inline=False)

        if metas:
            linhas = []
            for meta in metas[:10]:
                if not isinstance(meta, dict):
                    continue
                alvo = int(meta.get("alvo", 0) or 0)
                estado = "✓ ALCANÇADO" if meta.get("atingido_em") else "◷ EM PROGRESSO"
                descricao = str(meta.get("descricao") or "Marco da comunidade")[:90]
                linhas.append(f"**{alvo:,} membros** · {estado}\n{descricao}".replace(",", "."))
            embed.add_field(name="👥 MARCOS DA COMUNIDADE", value="\n\n".join(linhas)[:1024] or "Nenhum marco cadastrado.", inline=False)
        else:
            embed.add_field(name="👥 MARCOS DA COMUNIDADE", value="Nenhum marco cadastrado.", inline=False)

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
                async for antiga in canal.history(limit=30):
                    if antiga.author.id == self.bot.user.id and antiga.embeds and antiga.embeds[0].title == "𓂀 NÊMESIS · AGENDA":
                        mensagem = antiga
                        break
            except (discord.Forbidden, discord.HTTPException):
                _LOG.exception("Falha ao procurar publicação anterior da Agenda.")
        try:
            if mensagem is None:
                mensagem = await canal.send(embed=embed)
            else:
                await mensagem.edit(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            _LOG.exception("Falha ao publicar/atualizar a Agenda.")
            return False
        estado[str(guild.id)] = {"channel_id": canal.id, "message_id": mensagem.id, "atualizado_em": agora}
        await salvar(ARQUIVO_AGENDA_PUBLICACAO, estado)
        return True

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
    async def on_scheduled_event_create(
        self,
        evento: discord.ScheduledEvent,
    ):

        await self._sincronizar_evento(
            evento
        )

        canal = await self._canal_eventos(
            evento.guild
        )

        if not canal:
            return

        try:

            await canal.send(
                content="📅 **Novo evento agendado!**",
                embed=self._embed_evento(
                    evento,
                    "Evento agendado",
                ),
            )

        except (
            discord.Forbidden,
            discord.HTTPException,
        ):
            pass

    @commands.Cog.listener()
    async def on_scheduled_event_update(
        self,
        antes: discord.ScheduledEvent,
        depois: discord.ScheduledEvent,
    ):

        await self._sincronizar_evento(
            depois
        )

        canal = await self._canal_eventos(
            depois.guild
        )

        if not canal:
            return

        try:

            if (
                antes.status
                != discord.EventStatus.active
                and depois.status
                == discord.EventStatus.active
            ):

                await canal.send(
                    content=(
                        "🟢 **O evento começou agora!**"
                    ),
                    embed=self._embed_evento(
                        depois,
                        "Evento em andamento",
                    ),
                )

            elif (
                depois.status
                == discord.EventStatus.cancelled
            ):

                await canal.send(
                    f"❌ O evento **{depois.name}** "
                    "foi cancelado."
                )

        except (
            discord.Forbidden,
            discord.HTTPException,
        ):
            pass

    @commands.Cog.listener()
    async def on_scheduled_event_delete(
        self,
        evento: discord.ScheduledEvent,
    ):

        async with _EVENTOS_LOCK:
            dados = await _todos_eventos()
            registro = dados.get(str(evento.id))
            if not isinstance(registro, dict):
                return
            registro["status"] = "deleted"
            registro["atualizado_em"] = time.time()
            dados[str(evento.id)] = registro
            await _salvar_eventos(dados)

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

            await self._sincronizar_evento(
                evento
            )

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