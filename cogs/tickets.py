import time
import asyncio
import logging
import unicodedata
import discord
from discord.ext import commands, tasks
from utils.storage import carregar_config
from utils.guild_config import get_config, set_config
from utils import tickets


CANAIS_ESCALADOS = set()        # tickets já entregues para atendimento humano
ULTIMA_ATIVIDADE = {}           # channel_id -> timestamp da última mensagem
CANAIS_FECHANDO = set()         # evita fechar o mesmo canal duas vezes ao mesmo tempo
ABERTURA_TICKET_LOCK = asyncio.Lock()  # serializa abertura para o mesmo processo

FRASES_FECHAR = [
    "fechar o ticket",
    "fechar ticket",
    "encerrar o ticket",
    "encerrar ticket",
]

TEMPO_INATIVIDADE_SEGUNDOS = 10 * 60  # 10 minutos

CUSTOM_ID_SELECT = "ticket:abrir_select"
TICKET_PAINEL_CANAL_ID = 1545836351596011570

TITULO_PADRAO = "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — CENTRAL DE ATENDIMENTO ・✦"
DESCRICAO_PADRAO = (
    "A Central de Atendimento é o canal oficial para tratar de assuntos da "
    "gangue NÊMESIS e da comunidade. Selecione a categoria que melhor "
    "representa sua solicitação para abrir um atendimento privado com a equipe.\n\n"
    "╭────────────── ◈ ORIENTAÇÕES ◈ ──────────────╮\n"
    "・Escolha a categoria correta e explique o caso com clareza.\n"
    "・Inclua nomes, contexto, links ou provas quando forem relevantes.\n"
    "・Não abra vários tickets para o mesmo assunto.\n"
    "・Denúncias e informações sensíveis devem ser tratadas somente no ticket.\n"
    "・Aguarde a equipe; não marque cargos repetidamente.\n"
    "╰────────────────────────────────────────────╯\n\n"
    "Cada ticket é privado e visível apenas para você e a equipe responsável. "
    "Use este espaço com respeito; solicitações sem contexto podem atrasar o atendimento."
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
        ticket = await tickets.get_ticket_por_canal(canal.guild.id, canal.id)

        if ticket:
            await tickets.fechar_ticket(
                canal.guild.id,
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
            ticket = await tickets.get_ticket_por_canal(canal.guild.id, canal.id)

            if ticket:
                await tickets.fechar_ticket(
                    canal.guild.id,
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

    # Emojis decorativos (◈, ✦, ◇ etc.) não são aceitos como emojis
    # de SelectOption pelo Discord. Usa apenas emojis Unicode válidos.
    emojis_validos = {
        "recrutamento": "⚔️",
        "hierarquia_divisoes": "🎖️",
        "conflitos_denuncias": "⚖️",
        "guerras_desafios": "🎯",
        "suporte_comunidade": "🛟",
        "aliancas": "🤝",
        "eventos_atividades": "🎉",
        "sugestoes_projetos": "💡",
    }
    options = [
        discord.SelectOption(
            label=t["label"],
            value=t["valor"],
            description=t["descricao"][:100],
            emoji=(
                t.get("emoji")
                if t.get("emoji") in {"⚔️", "🎖️", "⚖️", "🎯", "🛟", "🤝", "🎉", "💡"}
                else emojis_validos.get(t["valor"])
            ),
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
        color=0xB51F32,
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
        canal = interaction.channel
        guild = interaction.guild
        membro = interaction.user

        if not guild or not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message(
                "Este botão só pode ser usado dentro de um ticket do servidor.",
                ephemeral=True,
            )
            return

        info_topic = tickets.parse_topic(canal.topic)
        registro = await tickets.get_ticket_por_canal(guild.id, canal.id)
        if (
            not info_topic
            or not registro
            or registro.get("status") != "aberto"
            or str(registro.get("usuario_id")) != str(info_topic.get("owner_id"))
        ):
            await interaction.response.send_message(
                "Este canal não é um ticket aberto válido.",
                ephemeral=True,
            )
            return

        config = await get_config(guild.id)
        suporte_id = config.get("support_role_id")
        try:
            suporte_id = int(suporte_id) if suporte_id else None
        except (TypeError, ValueError):
            suporte_id = None

        eh_suporte = (
            isinstance(membro, discord.Member)
            and suporte_id is not None
            and membro.get_role(suporte_id) is not None
        )
        eh_dono = str(membro.id) == str(registro.get("usuario_id"))
        eh_admin = (
            isinstance(membro, discord.Member)
            and membro.guild_permissions.manage_channels
        )

        if not (eh_dono or eh_suporte or eh_admin):
            await interaction.response.send_message(
                "Somente o dono deste ticket ou a equipe autorizada pode fechá-lo.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Fechando o ticket...",
            ephemeral=True,
        )

        await fechar_canal_ticket(
            canal,
            f"Fechamento autorizado pelo usuário {membro.id}.",
            delay=5,
            fechado_por_id=membro.id,
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
        self.verificar_painel_permanente.start()

    def cog_unload(self):
        self.verificar_inatividade.cancel()
        self.verificar_painel_permanente.cancel()

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
            color=0xB51F32,
        )

        try:
            mensagem = await canal.send(
                content=user.mention,
                embed=embed,
                view=FecharTicketView(),
            )

            # Salva o registro depois de publicar a mensagem inicial.
            ticket_salvo = await tickets.criar_ticket(
                guild_id=guild.id,
                usuario_id=user.id,
                tipo=tipo["valor"],
                canal_id=canal.id,
                mensagem_id=mensagem.id,
            )

            # Protege também contra duas instâncias do bot: se a persistência
            # retornar um ticket anterior, removemos o canal recém-criado.
            if str(ticket_salvo.get("canal_id")) != str(canal.id):
                canal_existente_id = int(ticket_salvo.get("canal_id") or 0)
                try:
                    await canal.delete(reason="Ticket duplicado detectado")
                except (discord.Forbidden, discord.HTTPException):
                    logging.getLogger(__name__).exception(
                        "Falha ao remover ticket duplicado %s.",
                        canal.id,
                    )
                canal_existente = guild.get_channel(canal_existente_id)
                if canal_existente is not None:
                    return canal_existente
                raise RuntimeError("Já havia um ticket aberto, mas seu canal não foi encontrado.")
        except Exception:
            # Sem registro persistido, não deixamos um canal privado órfão.
            try:
                await canal.delete(reason="Falha ao inicializar/persistir ticket NÊMESIS")
            except (discord.Forbidden, discord.HTTPException):
                logging.getLogger(__name__).exception(
                    "Falha ao remover canal órfão de ticket %s.",
                    canal.id,
                )
            raise

        ULTIMA_ATIVIDADE[canal.id] = time.time()

        if not tipo["usa_ia"] and cargo_suporte:
            await canal.send(
                f"🔔 {cargo_suporte.mention} — novo ticket de "
                f"**{tipo['label']}**."
            )

        return canal

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

        # Responde antes de acessar o armazenamento/criar canal, para não
        # deixar a interação do Discord expirar enquanto aguarda a operação.
        await interaction.response.defer(ephemeral=True, thinking=True)

        async with ABERTURA_TICKET_LOCK:
            # A consulta fica dentro do lock: dois cliques simultâneos do
            # mesmo usuário não criam dois canais.
            ticket_aberto = await tickets.get_ticket_aberto_usuario(
                interaction.guild.id,
                interaction.user.id,
            )

            if ticket_aberto:
                try:
                    canal_existente_id = int(ticket_aberto.get("canal_id", 0) or 0)
                except (TypeError, ValueError):
                    canal_existente_id = 0
                canal_existente = interaction.guild.get_channel(canal_existente_id)

                if canal_existente:
                    await interaction.followup.send(
                        f"Você já possui um ticket aberto: {canal_existente.mention}",
                        ephemeral=True,
                    )
                    return

                # Canal apagado manualmente: encerra o registro antigo.
                await tickets.fechar_ticket(
                    interaction.guild.id,
                    ticket_aberto["id"],
                    fechado_por_id=interaction.user.id,
                    motivo="Canal do ticket não foi encontrado.",
                )

            try:
                canal = await self._criar_canal_ticket(
                    interaction.guild,
                    interaction.user,
                    tipo,
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Falha ao criar ticket para usuário %s (tipo=%s).",
                    interaction.user.id,
                    tipo.get("valor"),
                )
                await interaction.followup.send(
                    "Não consegui criar o ticket. Verifique as permissões do bot e tente novamente.",
                    ephemeral=True,
                )
                return

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

        try:
            cargo_suporte_id = int(cargo_suporte_id) if cargo_suporte_id else None
        except (TypeError, ValueError):
            cargo_suporte_id = None

        eh_suporte = (
            cargo_suporte_id is not None
            and isinstance(message.author, discord.Member)
            and message.author.get_role(cargo_suporte_id) is not None
        )

        ticket_atual = await tickets.get_ticket_por_canal(
            message.guild.id,
            message.channel.id,
        )

        if ticket_atual and eh_suporte:
            await tickets.registrar_atendimento(
                message.guild.id,
                ticket_atual["id"],
                message.author.id,
            )

        texto = _normalizar(
            message.content
        )

        pediu_fechamento = any(
            frase in texto
            for frase in FRASES_FECHAR
        )
        eh_dono_ticket = (
            ticket_atual is not None
            and ticket_atual.get("status") == "aberto"
            and str(message.author.id) == str(ticket_atual.get("usuario_id"))
        )
        eh_admin_ticket = (
            isinstance(message.author, discord.Member)
            and message.author.guild_permissions.manage_channels
        )

        if (
            pediu_fechamento
            and ticket_atual is not None
            and ticket_atual.get("status") == "aberto"
            and (eh_dono_ticket or eh_suporte or eh_admin_ticket)
        ):
            await fechar_canal_ticket(
                message.channel,
                f"Fechamento solicitado por usuário autorizado ({message.author.id}).",
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
            color=0xB51F32,
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

    @tasks.loop(seconds=300)
    async def verificar_painel_permanente(self):
        for guild in self.bot.guilds:
            try:
                config = await get_config(guild.id)

                # Migra o menu padrão sem exigir comandos administrativos.
                if not config.get("ticket_modelo_v3"):
                    await tickets.set_tipos(
                        guild.id,
                        list(tickets.TIPOS_PADRAO),
                    )
                    await set_config(
                        guild.id,
                        ticket_modelo_v2=True,
                        ticket_modelo_v3=True,
                    )
                    config = await get_config(guild.id)

                canal_id = TICKET_PAINEL_CANAL_ID
                mensagem_id = config.get("ticket_painel_mensagem_id")
                canal = guild.get_channel(int(canal_id))
                if not isinstance(canal, discord.TextChannel):
                    continue

                if mensagem_id:
                    try:
                        await canal.fetch_message(int(mensagem_id))
                        continue
                    except discord.NotFound:
                        pass
                    except (discord.Forbidden, discord.HTTPException):
                        continue

                embed = await _montar_embed_painel(guild.id)
                view = await _montar_select(guild.id)
                mensagem = await canal.send(
                    embed=embed,
                    view=view,
                )
                try:
                    await mensagem.pin(
                        reason="Restaurando o painel permanente de tickets NÊMESIS"
                    )
                except (discord.Forbidden, discord.HTTPException):
                    pass

                await set_config(
                    guild.id,
                    ticket_painel_canal_id=canal.id,
                    ticket_painel_mensagem_id=mensagem.id,
                )
            except Exception as erro:
                print(
                    f"[Tickets] Falha ao restaurar painel no servidor {guild.id}: {erro}"
                )

    @verificar_painel_permanente.before_loop
    async def antes_de_verificar_painel_permanente(self):
        await self.bot.wait_until_ready()

    @tasks.loop(seconds=60)
    async def verificar_inatividade(self):
        agora = time.time()

        for guild in self.bot.guilds:
            try:
                abertos = await tickets.listar_tickets(
                    guild.id,
                    status="aberto",
                )

                for ticket in abertos:
                    try:
                        canal_id = int(ticket.get("canal_id") or 0)
                    except (TypeError, ValueError):
                        canal_id = 0

                    if not canal_id:
                        continue

                    canal = guild.get_channel(canal_id)
                    if canal is None:
                        try:
                            canal = await guild.fetch_channel(canal_id)
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            await tickets.fechar_ticket(
                                guild.id,
                                ticket["id"],
                                motivo="Canal do ticket removido ou inacessível.",
                            )
                            continue

                    if not isinstance(canal, discord.TextChannel):
                        continue

                    ultima = ULTIMA_ATIVIDADE.get(canal.id)
                    if ultima is None:
                        # Após reiniciar, inicia a contagem no primeiro ciclo,
                        # evitando fechar tickets antigos sem verificar atividade.
                        ULTIMA_ATIVIDADE[canal.id] = agora
                        continue

                    if agora - ultima >= TEMPO_INATIVIDADE_SEGUNDOS:
                        await fechar_canal_ticket(
                            canal,
                            "Fechado automaticamente por 10 minutos de inatividade.",
                            delay=5,
                        )

            except Exception as erro:
                print(
                    "[Tickets] Falha ao verificar inatividade "
                    f"no servidor {guild.id}: {erro}"
                )

    @verificar_inatividade.before_loop
    async def antes_de_verificar_inatividade(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
