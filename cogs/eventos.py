import datetime
import discord
from discord import app_commands
from discord.ext import commands
from utils.guild_config import get_config, set_config

FUSO_BRASIL = datetime.timezone(datetime.timedelta(hours=-3))  # Brasil não usa horário de verão desde 2019


class Eventos(commands.Cog):
    """Anuncia automaticamente, num canal escolhido, quando um evento agendado
    do Discord é criado e quando ele começa. Também permite criar
    campeonatos direto pelo bot (vira um Evento Agendado de verdade do
    Discord, com RSVP e lembrete nativo)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _canal_eventos(self, guild: discord.Guild):
        config = await get_config(guild.id)
        canal_id = config["canal_eventos_id"]
        return guild.get_channel(canal_id) if canal_id else None

    @app_commands.command(name="configurar-canal-eventos", description="Define onde o bot anuncia os eventos agendados do servidor.")
    @app_commands.describe(canal="Canal de texto para os anúncios de evento")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_canal_eventos(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_eventos_id=canal.id)
        await interaction.response.send_message(f"✅ Eventos agendados agora são anunciados em {canal.mention}.", ephemeral=True)

    @app_commands.command(name="campeonato-agendar", description="Cria um campeonato como Evento Agendado do Discord (com RSVP e lembrete nativo).")
    @app_commands.describe(
        nome="Nome do campeonato",
        data_hora="Data e hora no formato DD/MM/AAAA HH:MM (horário de Brasília)",
        descricao="Descrição do campeonato",
        canal_voz="(Opcional) canal de voz onde vai rolar — sem isso, fica como 'local externo'",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def campeonato_agendar(
        self,
        interaction: discord.Interaction,
        nome: str,
        data_hora: str,
        descricao: str,
        canal_voz: discord.VoiceChannel = None,
    ):
        try:
            dt_ingenuo = datetime.datetime.strptime(data_hora, "%d/%m/%Y %H:%M")
        except ValueError:
            await interaction.response.send_message(
                "Data inválida. Use o formato `DD/MM/AAAA HH:MM`, exemplo: `25/12/2026 20:00`.", ephemeral=True
            )
            return

        inicio = dt_ingenuo.replace(tzinfo=FUSO_BRASIL)
        if inicio <= discord.utils.utcnow():
            await interaction.response.send_message("Essa data já passou — escolha uma data futura.", ephemeral=True)
            return
        fim = inicio + datetime.timedelta(hours=2)

        try:
            if canal_voz:
                evento = await interaction.guild.create_scheduled_event(
                    name=nome,
                    description=descricao,
                    start_time=inicio,
                    end_time=fim,
                    channel=canal_voz,
                    entity_type=discord.EntityType.voice,
                    privacy_level=discord.PrivacyLevel.guild_only,
                )
            else:
                evento = await interaction.guild.create_scheduled_event(
                    name=nome,
                    description=descricao,
                    start_time=inicio,
                    end_time=fim,
                    entity_type=discord.EntityType.external,
                    location="A definir",
                    privacy_level=discord.PrivacyLevel.guild_only,
                )
        except discord.Forbidden:
            await interaction.response.send_message("Não tenho permissão pra criar eventos agendados neste servidor.", ephemeral=True)
            return

        await interaction.response.send_message(f"✅ Campeonato **{nome}** criado! Evento: {evento.url}")

    def _embed_evento(self, evento: discord.ScheduledEvent, titulo: str) -> discord.Embed:
        embed = discord.Embed(title=titulo, description=evento.description or "Sem descrição.", color=0x5865F2)
        embed.add_field(name="Nome", value=evento.name, inline=False)
        embed.add_field(name="Início", value=discord.utils.format_dt(evento.start_time, style="F"), inline=True)
        if evento.location:
            embed.add_field(name="Local", value=str(evento.location), inline=True)
        if evento.cover_image:
            embed.set_image(url=evento.cover_image.url)
        embed.set_footer(text=f"ID do evento: {evento.id}")
        return embed

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, evento: discord.ScheduledEvent):
        canal = await self._canal_eventos(evento.guild)
        if not canal:
            return
        await canal.send(
            content="📅 **Novo evento agendado!**",
            embed=self._embed_evento(evento, "Evento agendado"),
        )

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, antes: discord.ScheduledEvent, depois: discord.ScheduledEvent):
        canal = await self._canal_eventos(depois.guild)
        if not canal:
            return
        if antes.status != discord.EventStatus.active and depois.status == discord.EventStatus.active:
            await canal.send(
                content="🟢 **O evento começou agora!**",
                embed=self._embed_evento(depois, "Evento em andamento"),
            )
        elif depois.status == discord.EventStatus.cancelled:
            await canal.send(f"❌ O evento **{depois.name}** foi cancelado.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Eventos(bot))
