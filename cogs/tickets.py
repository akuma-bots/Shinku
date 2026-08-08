import re
import time
import datetime
import asyncio
import unicodedata
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.storage import carregar_config
from utils.guild_config import get_config
from utils.ia import perguntar_ia, ErroIA

CANAIS_ESCALADOS = set()        # tickets já entregues para atendimento humano
ULTIMA_ATIVIDADE = {}           # channel_id -> timestamp da última mensagem
CANAIS_FECHANDO = set()         # evita fechar o mesmo canal duas vezes ao mesmo tempo

FRASES_FECHAR = ["fechar o ticket", "fechar ticket", "encerrar o ticket", "encerrar ticket"]
TEMPO_INATIVIDADE_SEGUNDOS = 10 * 60  # 10 minutos
MARCADOR_ESCALAR = "ESCALAR_SUPORTE"

FUSO_BRASIL = datetime.timezone(datetime.timedelta(hours=-3))
DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]


def _agora_formatado() -> str:
    agora = datetime.datetime.now(FUSO_BRASIL)
    dia_semana = DIAS_SEMANA[agora.weekday()]
    return agora.strftime(f"%d/%m/%Y %H:%M ({dia_semana}, horário de Brasília)")


SYSTEM_PROMPT_TICKET = """Você é um atendente de suporte por ticket no Discord. Responda em \
português, curto e direto. Use SOMENTE as informações abaixo pra ajudar o cliente — nunca \
invente informação que não está nelas.

Agora são: %%AGORA%% — use isso se o cliente perguntar sobre prazo, horário de atendimento ou algo relacionado a tempo.

Se a dúvida do cliente estiver coberta pelas informações abaixo, responda ajudando a resolver.
Se NÃO estiver coberta, ou for um assunto sensível (ex: banimento de conta, disputa de \
pagamento não resolvida, algo que exige decisão humana), responda EXATAMENTE e SOMENTE com \
a palavra {marcador} — sem mais nada, nem explicação.

=== INFORMAÇÕES DE SUPORTE ===
{conhecimento}
=== FIM DAS INFORMAÇÕES ==="""


def _normalizar(texto: str) -> str:
    texto = texto.lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return texto


async def fechar_canal_ticket(channel: discord.TextChannel, motivo: str, delay: int = 5):
    """Fecha (apaga) um canal de ticket, evitando fechamento duplicado."""
    if channel.id in CANAIS_FECHANDO:
        return
    CANAIS_FECHANDO.add(channel.id)

    try:
        await channel.send(embed=discord.Embed(
            description=f"🔒 {motivo}\nEste ticket será fechado em {delay} segundos.",
            color=0xED4245,
        ))
    except discord.HTTPException:
        pass

    CANAIS_ESCALADOS.discard(channel.id)
    ULTIMA_ATIVIDADE.pop(channel.id, None)

    await asyncio.sleep(delay)
    try:
        await channel.delete()
    except discord.NotFound:
        pass
    finally:
        CANAIS_FECHANDO.discard(channel.id)


class AbrirTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Abrir Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="abrir_ticket_persistente")
    async def abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        nome_canal = f"ticket-{interaction.user.name}".lower()
        nome_canal = re.sub(r"[^a-z0-9-]", "", nome_canal)

        existente = discord.utils.find(
            lambda c: c.topic == f"ticket-owner:{interaction.user.id}", guild.text_channels
        )
        if existente:
            await interaction.followup.send(f"Você já tem um ticket aberto: {existente.mention}", ephemeral=True)
            return

        config = await get_config(guild.id)
        categoria_id = config["ticket_category_id"]
        categoria = guild.get_channel(categoria_id) if categoria_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        cargo_suporte_id = config["support_role_id"]
        if cargo_suporte_id:
            cargo = guild.get_role(cargo_suporte_id)
            if cargo:
                overwrites[cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        canal = await guild.create_text_channel(
            name=nome_canal,
            category=categoria,
            topic=f"ticket-owner:{interaction.user.id}",
            overwrites=overwrites,
        )

        ULTIMA_ATIVIDADE[canal.id] = time.time()

        await canal.send(content=interaction.user.mention, embed=discord.Embed(
            description="Olá bem vindo, Como posso ajudar?", color=0x57F287
        ).set_footer(text="Diga 'fechar o ticket' a qualquer momento, ou fica 10 min sem resposta que eu fecho sozinho."),
        view=FecharTicketView())

        await interaction.followup.send(f"Ticket criado: {canal.mention}", ephemeral=True)


class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="fechar_ticket_persistente")
    async def fechar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Fechando o ticket em 5 segundos...")
        await fechar_canal_ticket(interaction.channel, f"Fechado por {interaction.user.mention}.", delay=5)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        entradas = carregar_config("knowledge_base.json")["entradas"]
        conhecimento = "\n".join(
            f"- {e['resposta']}" + (" (assunto sensível — sempre escalar pra humano)" if e.get("escalar_sempre") else "")
            for e in entradas
        )
        self.system_prompt = SYSTEM_PROMPT_TICKET.format(marcador=MARCADOR_ESCALAR, conhecimento=conhecimento)
        bot.add_view(AbrirTicketView())
        bot.add_view(FecharTicketView())
        self.verificar_inatividade.start()

    def cog_unload(self):
        self.verificar_inatividade.cancel()

    @app_commands.command(name="ticket-painel", description="Publica o painel para abrir tickets de suporte.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_painel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎫 Central de Suporte",
            description="Precisa de ajuda? Clique no botão abaixo para abrir um ticket.",
            color=0x5865F2,
        )
        await interaction.response.send_message(embed=embed, view=AbrirTicketView())

    async def _chamar_suporte(self, message: discord.Message, motivo: str):
        CANAIS_ESCALADOS.add(message.channel.id)
        config = await get_config(message.guild.id)
        cargo_suporte_id = config["support_role_id"]
        mencao = f"<@&{cargo_suporte_id}>" if cargo_suporte_id else "Equipe de suporte"
        await message.channel.send(
            content=mencao,
            embed=discord.Embed(description=f"⚠️ {motivo}\nUm atendente vai continuar o atendimento por aqui.", color=0xED4245),
        )

    @staticmethod
    def _eh_canal_ticket(channel) -> bool:
        return bool(getattr(channel, "topic", None)) and channel.topic.startswith("ticket-owner:")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not self._eh_canal_ticket(message.channel):
            return

        # Qualquer mensagem no ticket (cliente OU atendente) conta como atividade
        # e é escaneada para o pedido de fechamento.
        ULTIMA_ATIVIDADE[message.channel.id] = time.time()

        texto = _normalizar(message.content)
        if any(frase in texto for frase in FRASES_FECHAR):
            await fechar_canal_ticket(
                message.channel,
                f"{message.author.mention} pediu para fechar o ticket.",
                delay=5,
            )
            return

        # A partir daqui, só reage a mensagens do dono do ticket (o cliente),
        # não a mensagens da equipe de suporte.
        dono_id = message.channel.topic.replace("ticket-owner:", "")
        if str(message.author.id) != dono_id:
            return
        if message.channel.id in CANAIS_ESCALADOS:
            return

        async with message.channel.typing():
            prompt_com_hora = self.system_prompt.replace("%%AGORA%%", _agora_formatado())
            try:
                resposta = await perguntar_ia(prompt_com_hora, message.content)
            except ErroIA:
                await self._chamar_suporte(message, "Não consegui pensar numa resposta agora (erro técnico).")
                return

        if resposta.strip() == MARCADOR_ESCALAR:
            await self._chamar_suporte(message, "Este assunto precisa da revisão de um atendente humano.")
            return

        await message.reply(embed=discord.Embed(
            description=resposta,
            color=0x5865F2,
        ).set_footer(text="Resposta automática • Se não resolveu, é só continuar explicando aqui."))

    @tasks.loop(seconds=60)
    async def verificar_inatividade(self):
        agora = time.time()
        # cópia da lista pra evitar problema de alterar o dict durante o loop
        for channel_id, ultima in list(ULTIMA_ATIVIDADE.items()):
            if agora - ultima < TEMPO_INATIVIDADE_SEGUNDOS:
                continue
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                ULTIMA_ATIVIDADE.pop(channel_id, None)
                continue
            await fechar_canal_ticket(
                channel,
                f"Nenhuma mensagem nos últimos {TEMPO_INATIVIDADE_SEGUNDOS // 60} minutos.",
                delay=5,
            )

    @verificar_inatividade.before_loop
    async def antes_de_verificar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
