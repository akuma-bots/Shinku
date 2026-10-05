import datetime
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.guild_config import get_config, set_config
from utils.storage import carregar, salvar


ARQUIVO = "eventos.json"

FUSO_BRASIL = datetime.timezone(
    datetime.timedelta(hours=-3)
)


async def _todos_eventos():
    return await carregar(
        ARQUIVO,
        {},
    )


async def _salvar_eventos(dados):
    await salvar(
        ARQUIVO,
        dados,
    )


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


class Eventos(commands.Cog):
    """
    Sistema de eventos da NÊMESIS.

    Os eventos do Discord continuam sendo eventos nativos,
    mas seus dados também são persistidos em eventos.json,
    permitindo que o Dashboard consulte o mesmo estado pelo Upstash.
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
        )

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

        dados = await _todos_eventos()

        antigo = dados.get(
            str(evento.id),
            {},
        )

        registro = _evento_para_dados(
            evento,
            evento.guild.id,
            criado_por_id
            or antigo.get(
                "criado_por_id"
            ),
        )

        if antigo.get(
            "criado_em"
        ):
            registro["criado_em"] = antigo[
                "criado_em"
            ]
        else:
            registro["criado_em"] = time.time()

        if antigo.get(
            "participantes"
        ) is not None:
            registro["participantes"] = antigo[
                "participantes"
            ]
        else:
            registro["participantes"] = []

        dados[str(evento.id)] = registro

        await _salvar_eventos(
            dados
        )

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
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
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
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
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

    def _embed_evento(
        self,
        evento: discord.ScheduledEvent,
        titulo: str,
    ) -> discord.Embed:

        embed = discord.Embed(
            title=titulo,
            description=(
                evento.description
                or "Sem descrição."
            ),
            color=0x5865F2,
        )

        embed.add_field(
            name="Nome",
            value=evento.name,
            inline=False,
        )

        embed.add_field(
            name="Início",
            value=discord.utils.format_dt(
                evento.start_time,
                style="F",
            ),
            inline=True,
        )

        if evento.end_time:

            embed.add_field(
                name="Fim",
                value=discord.utils.format_dt(
                    evento.end_time,
                    style="F",
                ),
                inline=True,
            )

        if evento.location:

            embed.add_field(
                name="Local",
                value=str(
                    evento.location
                ),
                inline=True,
            )

        if evento.cover_image:

            embed.set_image(
                url=evento.cover_image.url
            )

        embed.set_footer(
            text=(
                f"ID do evento: {evento.id}"
            )
        )

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

        dados = await _todos_eventos()

        registro = dados.get(
            str(evento.id)
        )

        if registro:

            registro["status"] = "deleted"
            registro["atualizado_em"] = time.time()

            dados[str(evento.id)] = registro

            await _salvar_eventos(
                dados
            )

    @app_commands.command(
        name="eventos-sincronizar",
        description=(
            "Sincroniza os eventos atuais do Discord "
            "com o Dashboard."
        ),
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
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
            "sincronizado(s) com o Dashboard.",
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot
):
    await bot.add_cog(
        Eventos(bot)
    )