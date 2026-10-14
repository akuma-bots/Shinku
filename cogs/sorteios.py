import asyncio
import time
import uuid
import random
import re
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import carregar, salvar


ARQUIVO = "sorteios.json"

COR_SORTEIO = 0x5865F2
COR_SUCESSO = 0x57F287
COR_ERRO = 0xED4245

logger = logging.getLogger(__name__)


def _selecionar_vencedores(
    participantes: list,
    quantidade_solicitada: int,
    vencedores_salvos=None,
    resultado_ja_sorteado: bool = False,
) -> list[int]:
    """Seleciona uma vez e mantém a seleção estável durante tentativas de anúncio."""
    if resultado_ja_sorteado and isinstance(vencedores_salvos, list):
        participantes_ids = {int(uid) for uid in participantes if str(uid).isdigit()}
        resultado = []
        for user_id in vencedores_salvos:
            try:
                user_id = int(user_id)
            except (TypeError, ValueError):
                continue
            if user_id in participantes_ids and user_id not in resultado:
                resultado.append(user_id)
        return resultado

    participantes_ids = [int(uid) for uid in participantes if str(uid).isdigit()]
    quantidade = max(0, min(len(participantes_ids), int(quantidade_solicitada)))
    return random.sample(participantes_ids, quantidade) if quantidade else []


def timestamp_discord(
    timestamp: float,
    formato: str = "F",
) -> str:
    return f"<t:{int(timestamp)}:{formato}>"


# Serializa alterações de participantes dentro do processo para evitar que
# cliques simultâneos sobrescrevam inscrições umas das outras.
_SORTEIOS_LOCK = asyncio.Lock()


async def _registrar_participacao(
    sorteio_id: str | None,
    usuario_id: int,
    mensagem_id: int | None = None,
) -> tuple[str, dict | None]:
    async with _SORTEIOS_LOCK:
        todos = await carregar(ARQUIVO, {})
        if not isinstance(todos, dict):
            return "indisponivel", None

        sorteio = todos.get(str(sorteio_id)) if sorteio_id else None
        if sorteio is None and mensagem_id is not None:
            sorteio = next(
                (
                    item for item in todos.values()
                    if isinstance(item, dict)
                    and str(item.get("mensagem_id")) == str(mensagem_id)
                ),
                None,
            )

        if not isinstance(sorteio, dict):
            return "nao_encontrado", None
        if mensagem_id is not None and str(sorteio.get("mensagem_id")) != str(mensagem_id):
            return "mensagem_invalida", None
        if sorteio.get("encerrado"):
            return "encerrado", sorteio
        try:
            fim = float(sorteio.get("fim", 0) or 0)
        except (TypeError, ValueError):
            return "indisponivel", sorteio
        if time.time() >= fim:
            return "expirado", sorteio

        participantes = sorteio.get("participantes")
        if not isinstance(participantes, list):
            participantes = []
            sorteio["participantes"] = participantes

        if any(str(uid) == str(usuario_id) for uid in participantes):
            return "duplicado", sorteio

        participantes.append(int(usuario_id))
        sorteio["atualizado_em"] = time.time()
        todos[str(sorteio["id"])] = sorteio
        await salvar(ARQUIVO, todos)
        return "ok", sorteio


class BotaoParticipar(discord.ui.View):

    def __init__(
        self,
        participantes: int = 0,
        encerrado: bool = False,
    ):
        super().__init__(timeout=None)

        self.encerrado = encerrado
        self.participantes_total = participantes

        for item in self.children:
            if not isinstance(item, discord.ui.Button):
                continue
            if item.custom_id == "sorteio_participar_btn":
                item.label = (
                    "🎁 Encerrado"
                    if encerrado
                    else f"🎁 Participar ({participantes})"
                )
                item.disabled = encerrado
            elif item.custom_id == "sorteio_participantes_btn":
                item.label = f"👥 Participantes ({participantes})"

    async def obter_sorteio(
        self,
        mensagem_id: int,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )
        if not isinstance(todos, dict):
            return None

        for sorteio in todos.values():
            if not isinstance(sorteio, dict):
                continue
            if (
                str(sorteio.get("mensagem_id"))
                == str(mensagem_id)
            ):
                return sorteio

        return None

    async def salvar_sorteio(
        self,
        sorteio: dict,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )

        sorteio["atualizado_em"] = time.time()

        todos[str(sorteio["id"])] = sorteio

        await salvar(
            ARQUIVO,
            todos,
        )

    async def atualizar_botoes(
        self,
        interaction: discord.Interaction,
        sorteio: dict,
    ):
        participantes = sorteio.get("participantes", [])
        if not isinstance(participantes, list):
            participantes = []
            sorteio["participantes"] = participantes
        quantidade = len(participantes)

        view = BotaoParticipar(
            participantes=quantidade,
            encerrado=sorteio.get(
                "encerrado",
                False,
            ),
        )

        try:
            await interaction.message.edit(
                view=view
            )
        except discord.HTTPException:
            pass

    @discord.ui.button(
        label="🎁 Participar (0)",
        style=discord.ButtonStyle.success,
        custom_id="sorteio_participar_btn",
    )
    async def participar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        sorteio = await self.obter_sorteio(
            interaction.message.id
        )

        if not sorteio:
            await interaction.response.send_message(
                "Não foi possível encontrar este sorteio.",
                ephemeral=True,
            )
            return

        status, sorteio = await _registrar_participacao(
            str(sorteio.get("id")),
            interaction.user.id,
            mensagem_id=interaction.message.id,
        )
        mensagens = {
            "nao_encontrado": "Não foi possível encontrar este sorteio.",
            "mensagem_invalida": "Este botão não pertence a este sorteio.",
            "encerrado": "Este sorteio já foi encerrado.",
            "expirado": "O período de participação deste sorteio já terminou.",
            "duplicado": "Você já está participando deste sorteio.",
            "indisponivel": "Não foi possível registrar sua participação agora.",
        }
        if status != "ok":
            await interaction.response.send_message(
                mensagens.get(status, "Não foi possível registrar sua participação."),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "✓ Você entrou no sorteio. Boa sorte!",
            ephemeral=True,
        )

        await self.atualizar_botoes(
            interaction,
            sorteio,
        )

    @discord.ui.button(
        label="👥 Participantes (0)",
        style=discord.ButtonStyle.primary,
        custom_id="sorteio_participantes_btn",
    )
    async def mostrar_participantes(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        sorteio = await self.obter_sorteio(
            interaction.message.id
        )

        if not sorteio:
            await interaction.response.send_message(
                "Não foi possível encontrar este sorteio.",
                ephemeral=True,
            )
            return

        participantes = sorteio.get("participantes", [])
        if not isinstance(participantes, list):
            participantes = []

        if not participantes:
            await interaction.response.send_message(
                "Ainda não há participantes neste sorteio.",
                ephemeral=True,
            )
            return

        linhas = []

        limite = 50

        for indice, usuario_id in enumerate(
            participantes[:limite],
            start=1,
        ):
            linhas.append(
                f"`{indice:02}` <@{usuario_id}>"
            )

        if len(participantes) > limite:
            linhas.append("")
            linhas.append(
                f"... e mais "
                f"**{len(participantes) - limite}** participantes."
            )

        embed = discord.Embed(
            title="👥 Participantes",
            description="\n".join(linhas),
            color=COR_SORTEIO,
        )

        embed.set_footer(
            text=(
                f"{len(participantes)} participante"
                f"{'s' if len(participantes) != 1 else ''}"
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


class Sorteios(commands.GroupCog, group_name="sorteios", group_description="Gerenciamento dos sorteios da NÊMESIS."):

    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot

        self.bot.add_view(
            BotaoParticipar()
        )

        self.verificar_sorteios.start()

    def cog_unload(self):
        self.verificar_sorteios.cancel()

    # =========================================================
    # STORAGE
    # =========================================================

    async def obter_sorteio(
        self,
        sorteio_id: str,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )
        if not isinstance(todos, dict):
            return None

        sorteio = todos.get(str(sorteio_id))
        return sorteio if isinstance(sorteio, dict) else None

    async def obter_sorteio_por_mensagem(
        self,
        mensagem_id: int,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )
        if not isinstance(todos, dict):
            return None

        for sorteio in todos.values():
            if not isinstance(sorteio, dict):
                continue
            if (
                str(sorteio.get("mensagem_id"))
                == str(mensagem_id)
            ):
                return sorteio

        return None

    async def salvar_sorteio(
        self,
        sorteio: dict,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )

        sorteio["atualizado_em"] = time.time()

        todos[str(sorteio["id"])] = sorteio

        await salvar(
            ARQUIVO,
            todos,
        )

    # =========================================================
    # EMBED
    # =========================================================

    def criar_embed(
        self,
        *,
        texto: str,
        requisitos: str,
        premio: str,
        vencedores: int,
        fim: float,
        criado_por: discord.Member,
        banner: str = "",
    ) -> discord.Embed:

        descricao = ""

        if texto.strip():
            descricao += (
                f"{texto.strip()}\n\n"
            )

        if requisitos.strip():
            descricao += (
                "⚠️ **Requisitos mínimos:**\n"
                f"{requisitos.strip()}\n\n"
            )

        descricao += (
            "🎁 **Prêmio:**\n"
            f"{premio.strip()}\n\n"
            "🏆 **Vencedores:**\n"
            f"**{vencedores}**\n\n"
            "⏰ **Sorteio termina:**\n"
            f"{timestamp_discord(fim, 'F')} "
            f"({timestamp_discord(fim, 'R')})\n\n"
            "Clique em **Participar** abaixo "
            "para entrar no sorteio."
        )

        embed = discord.Embed(
            title="🎁 SORTEIO",
            description=descricao,
            color=COR_SORTEIO,
        )

        embed.set_author(
            name="NÊMESIS"
        )

        if banner.strip():
            embed.set_image(
                url=banner.strip()
            )

        embed.set_footer(
            text=(
                f"Sorteio criado por "
                f"{criado_por.display_name}"
            ),
            icon_url=criado_por.display_avatar.url,
        )

        return embed

    # =========================================================
    # VIEW ANTIGA
    # =========================================================

    def criar_view(
        self,
        quantidade: int = 0,
        encerrado: bool = False,
    ) -> BotaoParticipar:

        return BotaoParticipar(
            participantes=quantidade,
            encerrado=encerrado,
        )

    # =========================================================
    # VIEW DO DASHBOARD
    # =========================================================

    def criar_view_site(
        self,
        sorteio: dict,
    ) -> discord.ui.View:

        participantes = sorteio.get("participantes", [])
        if not isinstance(participantes, list):
            participantes = []
        # Dados antigos ou corrompidos não devem derrubar a renderização.
        sorteio["participantes"] = participantes
        quantidade = len(participantes)

        encerrado = bool(
            sorteio.get(
                "encerrado",
                False,
            )
        )

        view = discord.ui.View(
            timeout=None
        )

        botao_participar = discord.ui.Button(
            label=(
                "🎁 Encerrado"
                if encerrado
                else f"🎁 Participar ({quantidade})"
            ),
            style=discord.ButtonStyle.success,
            custom_id=(
                f"sorteio_participar:"
                f"{sorteio['id']}"
            ),
            disabled=encerrado,
        )

        botao_participantes = discord.ui.Button(
            label=(
                f"👥 Participantes "
                f"({quantidade})"
            ),
            style=discord.ButtonStyle.primary,
            custom_id=(
                f"sorteio_participantes:"
                f"{sorteio['id']}"
            ),
        )

        view.add_item(
            botao_participar
        )

        view.add_item(
            botao_participantes
        )

        return view

    # =========================================================
    # INTERAÇÕES DOS SORTEIOS DO SITE
    # =========================================================

    @commands.Cog.listener(
        "on_interaction"
    )
    async def sorteio_site_interaction(
        self,
        interaction: discord.Interaction,
    ):
        if (
            interaction.type
            != discord.InteractionType.component
        ):
            return

        data = interaction.data or {}

        custom_id = data.get(
            "custom_id",
            "",
        )

        if not isinstance(
            custom_id,
            str,
        ):
            return

        if not (
            custom_id.startswith(
                "sorteio_participar:"
            )
            or custom_id.startswith(
                "sorteio_participantes:"
            )
        ):
            return

        try:
            acao, sorteio_id = (
                custom_id.split(
                    ":",
                    1,
                )
            )
        except ValueError:
            return

        sorteio = await self.obter_sorteio(
            sorteio_id
        )

        if not sorteio:
            await interaction.response.send_message(
                "Não foi possível encontrar este sorteio.",
                ephemeral=True,
            )
            return

        if (
            str(
                sorteio.get(
                    "mensagem_id"
                )
            )
            != str(
                interaction.message.id
            )
        ):
            await interaction.response.send_message(
                "Este botão não pertence a este sorteio.",
                ephemeral=True,
            )
            return

        # =====================================================
        # BOTÃO: PARTICIPANTES
        # =====================================================

        if (
            acao
            == "sorteio_participantes"
        ):
            participantes = sorteio.get("participantes", [])
            if not isinstance(participantes, list):
                participantes = []
            sorteio["participantes"] = participantes

            if not participantes:
                await interaction.response.send_message(
                    "Ainda não há participantes neste sorteio.",
                    ephemeral=True,
                )
                return

            linhas = []

            limite = 50

            for indice, usuario_id in enumerate(
                participantes[:limite],
                start=1,
            ):
                linhas.append(
                    f"`{indice:02}` <@{usuario_id}>"
                )

            if len(participantes) > limite:
                linhas.extend(
                    [
                        "",
                        (
                            f"... e mais "
                            f"**{len(participantes) - limite}** "
                            f"participantes."
                        ),
                    ]
                )

            embed = discord.Embed(
                title="👥 Participantes",
                description="\n".join(
                    linhas
                ),
                color=COR_SORTEIO,
            )

            embed.set_footer(
                text=(
                    f"{len(participantes)} participante"
                    f"{'s' if len(participantes) != 1 else ''}"
                )
            )

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True,
            )

            return

        # =====================================================
        # BOTÃO: PARTICIPAR
        # =====================================================

        status, sorteio = await _registrar_participacao(
            str(sorteio.get("id")),
            interaction.user.id,
            mensagem_id=interaction.message.id,
        )
        mensagens = {
            "nao_encontrado": "Não foi possível encontrar este sorteio.",
            "mensagem_invalida": "Este botão não pertence a este sorteio.",
            "encerrado": "Este sorteio já foi encerrado.",
            "expirado": "O sorteio terminou; o encerramento automático será processado.",
            "duplicado": "Você já está participando deste sorteio.",
            "indisponivel": "Não foi possível registrar sua participação agora.",
        }
        if status == "expirado":
            await self.sortear_vencedores(sorteio)
            await interaction.response.send_message(mensagens[status], ephemeral=True)
            return
        if status != "ok":
            await interaction.response.send_message(
                mensagens.get(status, "Não foi possível registrar sua participação."),
                ephemeral=True,
            )
            return

        try:
            await interaction.message.edit(
                view=self.criar_view_site(
                    sorteio
                )
            )
        except discord.HTTPException:
            pass

        await interaction.response.send_message(
            "✓ Você entrou no sorteio. Boa sorte!",
            ephemeral=True,
        )

    # =========================================================
    # COMANDO: CRIAR
    # =========================================================

    @app_commands.command(
        name="sorteio-criar",
        description="Cria um sorteio da NÊMESIS.",
    )
    @app_commands.describe(
        texto="Texto apresentado no sorteio.",
        requisitos="Requisitos mínimos para participar.",
        premio="Prêmio que será sorteado.",
        vencedores="Quantidade de vencedores.",
        duracao_minutos="Tempo até o encerramento do sorteio.",
        banner="URL da imagem/banner do sorteio.",
        canal="Canal onde o sorteio será publicado.",
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def sorteio_criar(
        self,
        interaction: discord.Interaction,
        texto: str,
        requisitos: str,
        premio: str,
        vencedores: int,
        duracao_minutos: int,
        banner: str = "",
        canal: discord.TextChannel = None,
    ):
        texto = (texto or "").strip()
        requisitos = (requisitos or "").strip()
        premio = (premio or "").strip()
        banner = (banner or "").strip()

        if not premio or len(premio) > 500:
            await interaction.response.send_message(
                "O prêmio é obrigatório e deve ter até 500 caracteres.",
                ephemeral=True,
            )
            return

        if len(texto) > 1500:
            await interaction.response.send_message(
                "O texto do sorteio pode ter até 1.500 caracteres.",
                ephemeral=True,
            )
            return

        if len(requisitos) > 1000:
            await interaction.response.send_message(
                "Os requisitos podem ter até 1.000 caracteres.",
                ephemeral=True,
            )
            return

        # Mantém a descrição dentro dos limites dos embeds do Discord.
        if len(texto) + len(requisitos) + len(premio) > 3000:
            await interaction.response.send_message(
                "O conteúdo está muito longo. Reduza o texto, os requisitos ou o prêmio.",
                ephemeral=True,
            )
            return

        if banner and not re.match(r"^https?://\S+$", banner, re.IGNORECASE):
            await interaction.response.send_message(
                "O banner precisa ser uma URL válida iniciada por http:// ou https://.",
                ephemeral=True,
            )
            return

        if vencedores <= 0 or vencedores > 100:
            await interaction.response.send_message(
                "A quantidade de vencedores deve ficar entre 1 e 100.",
                ephemeral=True,
            )
            return

        if duracao_minutos <= 0:
            await interaction.response.send_message(
                "A duração precisa ser maior que 0 minutos.",
                ephemeral=True,
            )
            return

        if duracao_minutos > 43200:
            await interaction.response.send_message(
                "A duração máxima é de 30 dias.",
                ephemeral=True,
            )
            return

        canal_destino = (
            canal
            or interaction.channel
        )

        if not isinstance(
            canal_destino,
            discord.TextChannel,
        ):
            await interaction.response.send_message(
                "Não foi possível determinar o canal do sorteio.",
                ephemeral=True,
            )
            return

        fim = (
            time.time()
            + (
                duracao_minutos
                * 60
            )
        )

        sorteio_id = str(
            uuid.uuid4()
        )[:8]

        embed = self.criar_embed(
            texto=texto,
            requisitos=requisitos,
            premio=premio,
            vencedores=vencedores,
            fim=fim,
            criado_por=interaction.user,
            banner=banner,
        )

        view = self.criar_view(
            quantidade=0,
        )

        await interaction.response.send_message(
            "Criando sorteio...",
            ephemeral=True,
        )

        try:
            mensagem = await canal_destino.send(
                embed=embed,
                view=view,
            )

        except discord.Forbidden:
            await interaction.edit_original_response(
                content=(
                    "Não tenho permissão para enviar "
                    "mensagens nesse canal."
                )
            )
            return

        agora = time.time()

        sorteio = {
            "id": sorteio_id,
            "guild_id": interaction.guild.id,

            "canal_id": canal_destino.id,
            "mensagem_id": mensagem.id,

            "texto": texto,
            "requisitos": requisitos,
            "premio": premio,
            "banner": banner.strip() or None,

            "fim": fim,
            "vencedores": vencedores,

            "participantes": [],
            "vencedores_ids": [],

            "encerrado": False,

            "criado_por_id": interaction.user.id,

            "criado_em": agora,
            "atualizado_em": agora,
            "encerrado_em": None,
        }

        await self.salvar_sorteio(
            sorteio
        )

        await interaction.edit_original_response(
            content=(
                f"✓ Sorteio criado em "
                f"{canal_destino.mention}.\n"
                f"ID: `{sorteio_id}`"
            )
        )
    # =========================================================
    # ATUALIZAR MENSAGEM
    # =========================================================

    async def atualizar_mensagem(
        self,
        sorteio: dict,
    ):
        try:
            canal_id = int(sorteio.get("canal_id") or 0)
        except (TypeError, ValueError):
            return

        canal = self.bot.get_channel(canal_id)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(canal_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as erro:
                print(f"[SORTEIOS] Canal {canal_id} inacessível ao atualizar mensagem: {erro}")
                return

        if not isinstance(canal, discord.TextChannel):
            return

        try:
            mensagem = await canal.fetch_message(
                sorteio.get("mensagem_id")
            )

        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            return

        participantes = sorteio.get("participantes", [])
        if not isinstance(participantes, list):
            participantes = []
        # Dados antigos ou corrompidos não devem derrubar a renderização.
        sorteio["participantes"] = participantes
        quantidade = len(participantes)

        # Sorteios vindos do Dashboard utilizam
        # os custom_ids vinculados ao ID do sorteio.
        #
        # Sorteios antigos criados pelo comando
        # continuam utilizando a view tradicional.
        if (
            sorteio.get("criado_por_id")
            is None
        ):
            view = self.criar_view_site(
                sorteio
            )

        else:
            view = self.criar_view(
                quantidade=quantidade,
                encerrado=sorteio.get(
                    "encerrado",
                    False,
                ),
            )

        try:
            await mensagem.edit(
                view=view
            )

        except discord.HTTPException:
            pass

    # =========================================================
    # COMANDO: ENCERRAR
    # =========================================================

    @app_commands.command(
        name="sorteio-encerrar",
        description="Encerra um sorteio e seleciona os vencedores.",
    )
    @app_commands.describe(
        id="ID do sorteio.",
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def sorteio_encerrar(
        self,
        interaction: discord.Interaction,
        id: str,
    ):
        sorteio = await self.obter_sorteio(
            id
        )

        if (
            not sorteio
            or str(
                sorteio.get("guild_id")
            )
            != str(
                interaction.guild.id
            )
        ):
            await interaction.response.send_message(
                "Não encontrei esse sorteio.",
                ephemeral=True,
            )
            return

        if sorteio.get("encerrado"):
            await interaction.response.send_message(
                "Esse sorteio já foi encerrado.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Encerrando sorteio e selecionando os vencedores...",
            ephemeral=True,
        )

        await self.sortear_vencedores(
            sorteio
        )

    # =========================================================
    # COMANDO: LISTAR
    # =========================================================

    @app_commands.command(
        name="sorteio-listar",
        description="Lista os sorteios ativos da NÊMESIS.",
    )
    async def sorteio_listar(
        self,
        interaction: discord.Interaction,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )
        if not isinstance(todos, dict):
            await interaction.response.send_message(
                "Não consegui carregar os dados dos sorteios agora.",
                ephemeral=True,
            )
            return

        ativos = []

        for sorteio in todos.values():

            if not isinstance(sorteio, dict):
                continue

            if (
                str(
                    sorteio.get("guild_id")
                )
                != str(
                    interaction.guild.id
                )
            ):
                continue

            if sorteio.get("encerrado"):
                continue

            ativos.append(
                sorteio
            )

        if not ativos:
            await interaction.response.send_message(
                "Nenhum sorteio está em andamento.",
                ephemeral=True,
            )
            return

        linhas = []

        for sorteio in ativos:

            quantidade = len(
                sorteio.get(
                    "participantes",
                    [],
                )
            )

            linhas.append(
                f"**#{sorteio['id']}** — "
                f"**{sorteio['premio']}**\n"
                f"👥 {quantidade} participantes "
                f"• termina "
                f"{timestamp_discord(sorteio['fim'], 'R')}"
            )

        embed = discord.Embed(
            title="🎁 Sorteios ativos",
            description="\n\n".join(
                linhas
            ),
            color=COR_SORTEIO,
        )

        embed.set_footer(
            text="NÊMESIS • Sorteios"
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    async def _reabrir_apos_falha_de_anuncio(
        self,
        sorteio: dict,
        erro: Exception,
    ):
        # Preserve os vencedores escolhidos antes da falha. Se o Discord
        # tiver aceitado a mensagem e a resposta tiver falhado, o retry não
        # pode sortear pessoas diferentes nem duplicar a seleção.
        sorteio["encerrado"] = False
        sorteio["resultado_sorteado"] = True
        await self.salvar_sorteio(sorteio)
        try:
            await self.atualizar_mensagem(sorteio)
        except Exception as erro_atualizacao:
            # O estado pendente já foi persistido; o próximo ciclo tentará
            # novamente sem alterar a seleção de vencedores.
            print(
                f"[SORTEIOS] Não consegui atualizar o painel do sorteio "
                f"{sorteio.get('id')}: {erro_atualizacao}"
            )
        print(
            f"[SORTEIOS] Falha ao anunciar resultado de "
            f"{sorteio.get('id')}; o encerramento será tentado novamente: {erro}"
        )

    async def _resultado_ja_anunciado(
        self,
        canal: discord.TextChannel,
        sorteio_id: str,
    ) -> bool | None:
        """Detecta anúncio já aceito pelo Discord após timeout/resposta perdida."""
        marcador = f"SORTEIO-ID:{sorteio_id}"
        try:
            async for mensagem in canal.history(limit=100):
                if not self.bot.user or mensagem.author.id != self.bot.user.id:
                    continue
                if any(
                    embed.footer
                    and marcador in (embed.footer.text or "")
                    for embed in mensagem.embeds
                ):
                    return True
            return False
        except (discord.Forbidden, discord.HTTPException):
            logger.exception(
                "Não foi possível verificar anúncios anteriores do sorteio %s.",
                sorteio_id,
            )
            return None

    # =========================================================
    # SORTEAR VENCEDORES
    # =========================================================

    async def sortear_vencedores(
        self,
        sorteio: dict,
    ):
        if sorteio.get("encerrado"):
            return

        try:
            canal_id = int(sorteio.get("canal_id") or 0)
        except (TypeError, ValueError):
            canal_id = 0

        canal = self.bot.get_channel(canal_id) if canal_id else None
        if canal is None and canal_id:
            try:
                canal = await self.bot.fetch_channel(canal_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as erro:
                print(f"[SORTEIOS] Não encerrei {sorteio.get('id')}: canal {canal_id} inacessível: {erro}")
                return

        if not isinstance(canal, discord.TextChannel):
            print(f"[SORTEIOS] Não encerrei {sorteio.get('id')}: canal de anúncio indisponível.")
            return

        async with _SORTEIOS_LOCK:
            todos = await carregar(ARQUIVO, {})
            atual = todos.get(str(sorteio.get("id"))) if isinstance(todos, dict) else None
            if not isinstance(atual, dict):
                print(f"[SORTEIOS] Registro {sorteio.get('id')} não encontrado ao encerrar.")
                return
            if atual.get("encerrado"):
                return

            participantes = list(atual.get("participantes", []))
            try:
                quantidade_solicitada = max(1, min(100, int(atual.get("vencedores", 1))))
            except (TypeError, ValueError):
                quantidade_solicitada = 1

            vencedores_ids = _selecionar_vencedores(
                participantes,
                quantidade_solicitada,
                vencedores_salvos=atual.get("vencedores_ids"),
                resultado_ja_sorteado=atual.get("resultado_sorteado") is True,
            )
            agora = time.time()

            atual["encerrado"] = True
            atual["resultado_sorteado"] = True
            atual["vencedores_ids"] = vencedores_ids
            atual["encerrado_em"] = agora
            atual["atualizado_em"] = agora
            todos[str(atual["id"])] = atual
            await salvar(ARQUIVO, todos)

            # Propaga o estado mais recente ao restante do fluxo de anúncio.
            sorteio.clear()
            sorteio.update(atual)

        # Atualiza os botões da mensagem original. Se a edição falhar depois
        # de persistir o encerramento, reabre o sorteio para o próximo ciclo.
        try:
            await self.atualizar_mensagem(sorteio)
        except Exception as erro:
            await self._reabrir_apos_falha_de_anuncio(sorteio, erro)
            return

        # O canal foi resolvido antes de marcar o sorteio como encerrado.
        # Assim, falhas temporárias de cache/API permitem nova tentativa no próximo ciclo.

        # Confere se o Discord já aceitou o anúncio numa tentativa anterior.
        sorteio_id = str(sorteio.get("id"))
        ja_anunciado = await self._resultado_ja_anunciado(canal, sorteio_id)
        if ja_anunciado is None:
            await self._reabrir_apos_falha_de_anuncio(
                sorteio,
                RuntimeError("Não foi possível verificar o histórico do canal."),
            )
            return
        if ja_anunciado:
            logger.info(
                "Resultado do sorteio %s já estava publicado; anúncio duplicado evitado.",
                sorteio_id,
            )
            return

        # =====================================================
        # SEM PARTICIPANTES
        # =====================================================

        if not participantes:

            embed = discord.Embed(
                title="🎁 SORTEIO ENCERRADO",
                description=(
                    f"O sorteio de "
                    f"**{sorteio['premio']}** terminou.\n\n"
                    "Não houve participantes."
                ),
                color=COR_ERRO,
            )

            embed.set_footer(
                text=f"NÊMESIS • Sorteios • SORTEIO-ID:{sorteio_id}"
            )

            try:
                await canal.send(embed=embed)
            except (discord.Forbidden, discord.HTTPException) as erro:
                await self._reabrir_apos_falha_de_anuncio(sorteio, erro)
                return

            return

        # =====================================================
        # COM PARTICIPANTES
        # =====================================================

        mencoes = ", ".join(
            f"<@{usuario_id}>"
            for usuario_id in vencedores_ids
        )

        if vencedores_ids:
            resultado = mencoes
        else:
            resultado = (
                "Não foi possível selecionar "
                "um vencedor."
            )

        embed = discord.Embed(
            title="🏆 SORTEIO ENCERRADO",
            description=(
                f"🎁 **Prêmio:**\n"
                f"{sorteio['premio']}\n\n"
                f"🏆 **Vencedor(es):**\n"
                f"{resultado}\n\n"
                f"👥 **Participantes:** "
                f"**{len(participantes)}**"
            ),
            color=COR_SUCESSO,
        )

        embed.set_footer(
            text=f"NÊMESIS • Sorteios • SORTEIO-ID:{sorteio_id}"
        )

        try:
            await canal.send(
                content=mencoes if vencedores_ids else None,
                embed=embed,
            )
        except (discord.Forbidden, discord.HTTPException) as erro:
            await self._reabrir_apos_falha_de_anuncio(sorteio, erro)

    # =========================================================
    # ENCERRAMENTO AUTOMÁTICO
    # =========================================================

    @tasks.loop(seconds=30)
    async def verificar_sorteios(self):
        # Erros de storage não devem matar o loop de encerramento automático.
        try:
            todos = await carregar(ARQUIVO, {})
        except Exception:
            logger.exception("Falha ao carregar sorteios para verificar encerramentos.")
            return

        if not isinstance(todos, dict):
            logger.error("Estrutura inválida em %s: esperado um objeto.", ARQUIVO)
            return

        agora = time.time()
        for sorteio in list(todos.values()):
            if not isinstance(sorteio, dict) or sorteio.get("encerrado"):
                continue

            try:
                fim = float(sorteio.get("fim", 0) or 0)
            except (TypeError, ValueError):
                logger.error(
                    "Sorteio com horário de término inválido (id=%s).",
                    sorteio.get("id", "desconhecido"),
                )
                continue

            if agora < fim:
                continue

            try:
                await self.sortear_vencedores(sorteio)
            except Exception:
                logger.exception(
                    "Falha inesperada ao encerrar sorteio id=%s; será reavaliado no próximo ciclo.",
                    sorteio.get("id", "desconhecido"),
                )

    @verificar_sorteios.before_loop
    async def antes(
        self,
    ):
        await self.bot.wait_until_ready()


async def setup(
    bot: commands.Bot,
):
    await bot.add_cog(
        Sorteios(bot)
    )