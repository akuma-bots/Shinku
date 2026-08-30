import time
import unicodedata
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.storage import carregar_config
from utils.guild_config import get_config

CANAIS_ESCALADOS = set()        # tickets já entregues para atendimento humano
ULTIMA_ATIVIDADE = {}           # channel_id -> timestamp da última mensagem
CANAIS_FECHANDO = set()         # evita fechar o mesmo canal duas vezes ao mesmo tempo

FRASES_FECHAR = ["fechar o ticket", "fechar ticket", "encerrar o ticket", "encerrar ticket"]
TEMPO_INATIVIDADE_SEGUNDOS = 10 * 60  # 10 minutos


def _normalizar(texto: str) -> str:
    texto = texto.lower()
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return texto


def _resolver_problema(mensagem: str, base: list):
    texto = _normalizar(mensagem)
    melhor_entrada = None
    melhor_pontuacao = 0

    for entrada in base:
        pontuacao = 0
        for frase in entrada["palavras_chave"]:
            palavras = _normalizar(frase).split()
            if all(p in texto for p in palavras):
                pontuacao += len(palavras)
        if pontuacao > melhor_pontuacao:
            melhor_pontuacao = pontuacao
            melhor_entrada = entrada

    return melhor_entrada if melhor_pontuacao > 0 else None


async def fechar_canal_ticket(canal: discord.TextChannel, motivo: str, delay: int = 5):
    if canal.id in CANAIS_FECHANDO:
        return
    CANAIS_FECHANDO.add(canal.id)
    ULTIMA_ATIVIDADE.pop(canal.id, None)
    CANAIS_ESCALADOS.discard(canal.id)
    try:
        await canal.send(f"🔒 Fechando este ticket em {delay}s. Motivo: {motivo}")
        import asyncio
        await asyncio.sleep(delay)
        await canal.delete(reason=motivo)
    except discord.NotFound:
        pass
    finally:
        CANAIS_FECHANDO.discard(canal.id)


class AbrirTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Abrir Ticket", style=discord.ButtonStyle.primary, custom_id="abrir_ticket_btn")
    async def abrir_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        config = await get_config(interaction.guild.id)
        categoria_id = config["ticket_category_id"]
        categoria = interaction.guild.get_channel(categoria_id) if categoria_id else None

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        cargo_suporte_id = config["support_role_id"]
        if cargo_suporte_id:
            cargo = interaction.guild.get_role(cargo_suporte_id)
            if cargo:
                overwrites[cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        nome_canal = f"ticket-{interaction.user.name}"[:95]
        canal = await interaction.guild.create_text_channel(
            name=nome_canal,
            category=categoria,
            overwrites=overwrites,
            topic=f"ticket-owner:{interaction.user.id}",
            reason=f"Ticket aberto por {interaction.user}",
        )

        embed = discord.Embed(
            description="Olá bem vindo, Como posso ajudar?",
            color=0x5865F2,
        )
        await canal.send(content=interaction.user.mention, embed=embed, view=FecharTicketView())
        ULTIMA_ATIVIDADE[canal.id] = time.time()

        await interaction.response.send_message(f"✅ Ticket criado: {canal.mention}", ephemeral=True)


class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fechar Ticket", style=discord.ButtonStyle.danger, custom_id="fechar_ticket_btn")
    async def fechar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Fechando o ticket...", ephemeral=True)
        await fechar_canal_ticket(interaction.channel, f"Fechado por {interaction.user} via botão.", delay=5)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_conhecimento = carregar_config("knowledge_base.json")["entradas"]
        bot.add_view(AbrirTicketView())
        bot.add_view(FecharTicketView())
        self.verificar_inatividade.start()

    def cog_unload(self):
        self.verificar_inatividade.cancel()

    @app_commands.command(name="ticket-painel", description="Publica o painel de abertura de tickets neste canal.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_painel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎫 Central de Suporte",
            description="Clique no botão abaixo pra abrir um ticket com a nossa equipe.",
            color=0x5865F2,
        )
        await interaction.channel.send(embed=embed, view=AbrirTicketView())
        await interaction.response.send_message("✅ Painel publicado.", ephemeral=True)

    async def _chamar_suporte(self, message: discord.Message, motivo: str):
        CANAIS_ESCALADOS.add(message.channel.id)
        config = await get_config(message.guild.id)
        cargo_id = config["support_role_id"]
        mencao = f"<@&{cargo_id}>" if cargo_id else "Equipe de suporte"
        await message.channel.send(f"🔔 {mencao} — {motivo}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if not message.channel.topic or not message.channel.topic.startswith("ticket-owner:"):
            return

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

        if "falar com atendente" in texto or "quero um humano" in texto or "atendente" in texto:
            await self._chamar_suporte(message, "Cliente solicitou atendimento humano.")
            return

        resultado = _resolver_problema(message.content, self.base_conhecimento)
        if not resultado:
            await self._chamar_suporte(message, "Não consegui identificar automaticamente o seu problema.")
            return

        await message.reply(embed=discord.Embed(
            description=resultado["resposta"],
            color=0x5865F2,
        ).set_footer(text="Resposta automática • Se não resolveu, digite 'falar com atendente'."))

        if resultado.get("escalar_sempre"):
            await self._chamar_suporte(message, "Este assunto precisa da revisão de um atendente humano.")

    @tasks.loop(seconds=60)
    async def verificar_inatividade(self):
        agora = time.time()
        for channel_id, ultima in list(ULTIMA_ATIVIDADE.items()):
            if agora - ultima >= TEMPO_INATIVIDADE_SEGUNDOS:
                canal = self.bot.get_channel(channel_id)
                if canal:
                    await fechar_canal_ticket(canal, "Ticket fechado por 10 minutos de inatividade.", delay=5)
                else:
                    ULTIMA_ATIVIDADE.pop(channel_id, None)

    @verificar_inatividade.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
