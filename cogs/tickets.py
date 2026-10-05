import time
import asyncio
import unicodedata
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.storage import carregar_config
from utils.guild_config import get_config, set_config
from utils import tickets


CANAIS_ESCALADOS = set()        # tickets já entregues para atendimento humano
ULTIMA_ATIVIDADE = {}           # channel_id -> timestamp da última mensagem
CANAIS_FECHANDO = set()         # evita fechar o mesmo canal duas vezes ao mesmo tempo

FRASES_FECHAR = [
    "fechar o ticket",
    "fechar ticket",
    "encerrar o ticket",
    "encerrar ticket",
]

TEMPO_INATIVIDADE_SEGUNDOS = 10 * 60  # 10 minutos

CUSTOM_ID_SELECT = "ticket:abrir_select"

TITULO_PADRAO = "🎫 Central de Suporte"
DESCRICAO_PADRAO = (
    "Selecione o tipo de atendimento abaixo pra abrir um ticket com a nossa equipe."
)


def _normalizar(texto: str) -> str:
    texto = texto.lower()
    texto = "".join(
        c
        for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
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


async def fechar_canal_ticket(
    canal: discord.TextChannel,
    motivo: str,
    delay: int = 5,
    fechado_por_id: int | None = None,
):
    if canal.id in CANAIS_FECHANDO:
        return

    CANAIS_FECHANDO.add(canal.id)

    ULTIMA_ATIVIDADE.pop(canal.id, None)
    CANAIS_ESCALADOS.discard(canal.id)

    try:
        # Registra o fechamento no armazenamento compartilhado
        ticket = await tickets.get_ticket_por_canal(canal.id)

        if ticket:
            await tickets.fechar_ticket(
                ticket["id"],
                fechado_por_id=fechado_por_id,
                motivo=motivo,
            )

        await canal.send(
            f"🔒 Fechando este ticket em {delay}s. Motivo: {motivo}"
        )

        await asyncio.sleep(delay)

        await canal.delete(reason=motivo)

    except discord.NotFound:
        # Mesmo que o canal já tenha sido apagado, tenta manter
        # o registro persistente como fechado.
        try:
            ticket = await tickets.get_ticket_por_canal(canal.id)

            if ticket:
                await tickets.fechar_ticket(
                    ticket["id"],
                    fechado_por_id=fechado_por_id,
                    motivo=motivo,
                )
        except Exception:
            pass

    except Exception:
        raise

    finally:
        CANAIS_FECHANDO.discard(canal.id)


async def _montar_select(guild_id: int) -> discord.ui.View:
    tipos = await tickets.get_tipos(guild_id)

    options = [
        discord.SelectOption(
            label=t["label"],
            value=t["valor"],
            description=t["descricao"][:100],
            emoji=t.get("emoji"),
        )
        for t in tipos
    ]

    select = discord.ui.Select(
        placeholder="Selecione o tipo de atendimento",
        options=options,
        custom_id=CUSTOM_ID_SELECT,
    )

    view = discord.ui.View(timeout=None)
    view.add_item(select)

    return view


async def _montar_embed_painel(guild_id: int) -> discord.Embed:
    config = await get_config(guild_id)

    embed = discord.Embed(
        title=config.get("ticket_painel_titulo") or TITULO_PADRAO,
        description=config.get("ticket_painel_descricao") or DESCRICAO_PADRAO,
        color=0x5865F2,
    )

    banner_url = config.get("ticket_painel_banner_url")

    if banner_url:
        embed.set_image(url=banner_url)

    return embed


class FecharTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🔒 Fechar Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="fechar_ticket_btn",
    )
    async def fechar_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await interaction.response.send_message(
            "Fechando o ticket...",
            ephemeral=True,
        )

        await fechar_canal_ticket(
            interaction.channel,
            f"Fechado por {interaction.user} via botão.",
            delay=5,
            fechado_por_id=interaction.user.id,
        )


class Tickets(commands.Cog):
    """
    Sistema de tickets por categoria.

    O painel mostra um menu suspenso configurável com /ticket-tipo-*.
    Cada opção cria um canal já identificado pelo tipo escolhido.

    Os tickets agora também são persistidos em tickets.json através
    de utils.tickets, permitindo que o Dashboard NÊMESIS enxergue:
    - tickets abertos;
    - tickets fechados;
    - usuário;
    - tipo;
    - canal;
    - atendente;
    - datas;
    - motivo do fechamento.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.base_conhecimento = carregar_config(
            "knowledge_base.json"
        )["entradas"]

        bot.add_view(FecharTicketView())

        self.verificar_inatividade.start()

    def cog_unload(self):
        self.verificar_inatividade.cancel()

    async def _criar_canal_ticket(
        self,
        guild: discord.Guild,
        user: discord.Member,
        tipo: dict,
    ) -> discord.TextChannel:

        config = await get_config(guild.id)

        categoria_id = config["ticket_category_id"]

        categoria = (
            guild.get_channel(categoria_id)
            if categoria_id
            else None
        )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
            ),
        }

        cargo_suporte_id = config["support_role_id"]

        cargo_suporte = (
            guild.get_role(cargo_suporte_id)
            if cargo_suporte_id
            else None
        )

        if cargo_suporte:
            overwrites[cargo_suporte] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
            )

        nome_canal = f"ticket-{tipo['valor']}-{user.name}"[:95]

        canal = await guild.create_text_channel(
            name=nome_canal,
            category=categoria,
            overwrites=overwrites,
            topic=tickets.construir_topic(
                user.id,
                tipo["valor"],
            ),
            reason=f"Ticket ({tipo['label']}) aberto por {user}",
        )

        embed = discord.Embed(
            title=f"{tipo.get('emoji', '🎫')} {tipo['label']}",
            description=(
                "Olá, bem-vindo(a)! Descreva com detalhes o que você "
                "precisa — nossa equipe vai te atender em breve."
            ),
            color=0x5865F2,
        )

        mensagem = await canal.send(
            content=user.mention,
            embed=embed,
            view=FecharTicketView(),
        )

        # Salva o ticket no armazenamento compartilhado.
        await tickets.criar_ticket(
            guild_id=guild.id,
            usuario_id=user.id,
            tipo=tipo["valor"],
            canal_id=canal.id,
            mensagem_id=mensagem.id,
        )

        ULTIMA_ATIVIDADE[canal.id] = time.time()

        if not tipo["usa_ia"] and cargo_suporte:
            await canal.send(
                f"🔔 {cargo_suporte.mention} — novo ticket de "
                f"**{tipo['label']}**."
            )

        return canal

    @app_commands.command(
        name="ticket-painel",
        description=(
            "Publica o painel de abertura de tickets "
            "(menu por categoria) neste canal."
        ),
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_painel(
        self,
        interaction: discord.Interaction,
    ):
        view = await _montar_select(interaction.guild.id)

        embed = await _montar_embed_painel(
            interaction.guild.id
        )

        await interaction.channel.send(
            embed=embed,
            view=view,
        )

        await interaction.response.send_message(
            "✅ Painel publicado.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ticket-painel-customizar",
        description="Define título, descrição e banner do painel de tickets.",
    )
    @app_commands.describe(
        titulo="Título do painel (deixe em branco pra manter o atual)",
        descricao="Descrição do painel (deixe em branco pra manter a atual)",
        banner="Imagem de banner (opcional)",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_painel_customizar(
        self,
        interaction: discord.Interaction,
        titulo: str = None,
        descricao: str = None,
        banner: discord.Attachment = None,
    ):
        campos = {}

        if titulo is not None:
            campos["ticket_painel_titulo"] = titulo

        if descricao is not None:
            campos["ticket_painel_descricao"] = descricao

        if banner is not None:
            campos["ticket_painel_banner_url"] = banner.url

        if not campos:
            await interaction.response.send_message(
                "Você não passou nada pra alterar.",
                ephemeral=True,
            )
            return

        await set_config(
            interaction.guild.id,
            **campos,
        )

        await interaction.response.send_message(
            "✅ Painel customizado. Rode `/ticket-painel` de novo "
            "pra publicar a versão atualizada.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ticket-painel-resetar",
        description=(
            "Volta o título, descrição e banner do painel pro padrão."
        ),
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_painel_resetar(
        self,
        interaction: discord.Interaction,
    ):
        await set_config(
            interaction.guild.id,
            ticket_painel_titulo="",
            ticket_painel_descricao="",
            ticket_painel_banner_url="",
        )

        await interaction.response.send_message(
            "✅ Painel restaurado pro padrão. "
            "Rode `/ticket-painel` de novo pra publicar.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ticket-tipo-adicionar",
        description="Adiciona (ou atualiza) uma categoria de ticket no menu.",
    )
    @app_commands.describe(
        label="Nome mostrado no menu",
        descricao="Descrição curta (aparece embaixo do nome)",
        emoji="Emoji da categoria (opcional)",
        usa_ia="Se essa categoria usa a resposta automática por IA",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_tipo_adicionar(
        self,
        interaction: discord.Interaction,
        label: str,
        descricao: str,
        emoji: str = None,
        usa_ia: bool = False,
    ):
        tipo = await tickets.adicionar_tipo(
            interaction.guild.id,
            label,
            descricao,
            emoji,
            usa_ia,
        )

        await interaction.response.send_message(
            f"✅ Categoria **{tipo['label']}** salva. "
            "Rode `/ticket-painel` de novo pra atualizar o menu já publicado.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ticket-tipo-remover",
        description="Remove uma categoria de ticket do menu.",
    )
    @app_commands.describe(
        valor="Identificador da categoria (aparece em /ticket-tipo-listar)"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_tipo_remover(
        self,
        interaction: discord.Interaction,
        valor: str,
    ):
        ok = await tickets.remover_tipo(
            interaction.guild.id,
            valor,
        )

        if not ok:
            await interaction.response.send_message(
                "Não achei nenhuma categoria com esse identificador.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "🗑️ Categoria removida. "
            "Rode `/ticket-painel` de novo pra atualizar o menu.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ticket-tipo-listar",
        description="Lista as categorias de ticket configuradas.",
    )
    async def ticket_tipo_listar(
        self,
        interaction: discord.Interaction,
    ):
        tipos = await tickets.get_tipos(
            interaction.guild.id
        )

        linhas = [
            (
                f"{t.get('emoji', '🎫')} **{t['label']}** "
                f"(`{t['valor']}`) — IA: "
                f"{'sim' if t['usa_ia'] else 'não'}"
            )
            for t in tipos
        ]

        embed = discord.Embed(
            title="🎫 Categorias de ticket",
            description="\n".join(linhas),
            color=0x5865F2,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_interaction(
        self,
        interaction: discord.Interaction,
    ):
        if interaction.type != discord.InteractionType.component:
            return

        if interaction.data.get("custom_id") != CUSTOM_ID_SELECT:
            return

        valor_escolhido = interaction.data["values"][0]

        tipos = await tickets.get_tipos(
            interaction.guild.id
        )

        tipo = next(
            (
                t
                for t in tipos
                if t["valor"] == valor_escolhido
            ),
            None,
        )

        if not tipo:
            await interaction.response.send_message(
                "Essa categoria não existe mais. Avise um admin.",
                ephemeral=True,
            )
            return

        # Evita criar outro ticket caso já exista um aberto
        # para o mesmo usuário.
        ticket_aberto = await tickets.get_ticket_aberto_usuario(
            interaction.guild.id,
            interaction.user.id,
        )

        if ticket_aberto:
            canal_existente = interaction.guild.get_channel(
                int(ticket_aberto.get("canal_id", 0))
            )

            if canal_existente:
                await interaction.response.send_message(
                    f"Você já possui um ticket aberto: "
                    f"{canal_existente.mention}",
                    ephemeral=True,
                )
                return

            # Canal foi apagado manualmente. Fecha o registro antigo
            # antes de permitir um novo.
            await tickets.fechar_ticket(
                ticket_aberto["id"],
                fechado_por_id=interaction.user.id,
                motivo="Canal do ticket não foi encontrado.",
            )

        await interaction.response.defer(
            ephemeral=True
        )

        canal = await self._criar_canal_ticket(
            interaction.guild,
            interaction.user,
            tipo,
        )

        await interaction.followup.send(
            f"✅ Ticket criado: {canal.mention}",
            ephemeral=True,
        )

    async def _chamar_suporte(
        self,
        message: discord.Message,
        motivo: str,
    ):
        CANAIS_ESCALADOS.add(
            message.channel.id
        )

        config = await get_config(
            message.guild.id
        )

        cargo_id = config["support_role_id"]

        mencao = (
            f"<@&{cargo_id}>"
            if cargo_id
            else "Equipe de suporte"
        )

        await message.channel.send(
            f"🔔 {mencao} — {motivo}"
        )

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message,
    ):
        if message.author.bot or not message.guild:
            return

        info_topic = tickets.parse_topic(
            message.channel.topic
        )

        if not info_topic:
            return

        ULTIMA_ATIVIDADE[
            message.channel.id
        ] = time.time()

        # Registra quem realizou o atendimento.
        config = await get_config(
            message.guild.id
        )

        cargo_suporte_id = config.get(
            "support_role_id"
        )

        eh_suporte = (
            cargo_suporte_id
            and isinstance(message.author, discord.Member)
            and message.author.get_role(
                int(cargo_suporte_id)
            ) is not None
        )

        ticket_atual = await tickets.get_ticket_por_canal(
            message.channel.id
        )

        if ticket_atual and eh_suporte:
            await tickets.registrar_atendimento(
                ticket_atual["id"],
                message.author.id,
            )

        texto = _normalizar(
            message.content
        )

        if any(
            frase in texto
            for frase in FRASES_FECHAR
        ):
            await fechar_canal_ticket(
                message.channel,
                f"{message.author.mention} pediu para fechar o ticket.",
                delay=5,
                fechado_por_id=message.author.id,
            )
            return

        # A partir daqui, só reage a mensagens do dono
        # do ticket (o cliente), não a mensagens da equipe.
        if str(message.author.id) != info_topic["owner_id"]:
            return

        if message.channel.id in CANAIS_ESCALADOS:
            return

        tipos = await tickets.get_tipos(
            message.guild.id
        )

        tipo = next(
            (
                t
                for t in tipos
                if t["valor"] == info_topic["tipo"]
            ),
            None,
        )

        if not tipo or not tipo["usa_ia"]:
            return

        if (
            "falar com atendente" in texto
            or "quero um humano" in texto
            or "atendente" in texto
        ):
            await self._chamar_suporte(
                message,
                "Cliente solicitou atendimento humano.",
            )
            return

        resultado = _resolver_problema(
            message.content,
            self.base_conhecimento,
        )

        if not resultado:
            await self._chamar_suporte(
                message,
                "Não consegui identificar automaticamente o seu problema.",
            )
            return

        embed = discord.Embed(
            description=resultado["resposta"],
            color=0x5865F2,
        )

        embed.set_footer(
            text=(
                "Resposta automática • "
                "Se não resolveu, digite "
                "'falar com atendente'."
            )
        )

        await message.reply(
            embed=embed
        )

        if resultado.get("escalar_sempre"):
            await self._chamar_suporte(
                message,
                "Este assunto precisa da revisão de um atendente humano.",
            )

    @tasks.loop(seconds=60)
    async def verificar_inatividade(self):
        agora = time.time