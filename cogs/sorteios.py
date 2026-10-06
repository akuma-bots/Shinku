import time
import uuid
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import carregar, salvar


ARQUIVO = "sorteios.json"

COR_SORTEIO = 0x5865F2
COR_SUCESSO = 0x57F287
COR_ERRO = 0xED4245


def timestamp_discord(
    timestamp: float,
    formato: str = "F",
) -> str:
    return f"<t:{int(timestamp)}:{formato}>"


class BotaoParticipar(discord.ui.View):

    def __init__(
        self,
        participantes: int = 0,
        encerrado: bool = False,
    ):
        super().__init__(timeout=None)

        self.encerrado = encerrado
        self.participantes_total = participantes

    async def obter_sorteio(
        self,
        mensagem_id: int,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )

        for sorteio in todos.values():
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
        quantidade = len(
            sorteio.get(
                "participantes",
                [],
            )
        )

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

        if sorteio.get("encerrado"):
            await interaction.response.send_message(
                "Este sorteio já foi encerrado.",
                ephemeral=True,
            )
            return

        fim = float(
            sorteio.get(
                "fim",
                0,
            )
        )

        if time.time() >= fim:
            await interaction.response.send_message(
                "O período de participação deste sorteio já terminou.",
                ephemeral=True,
            )
            return

        participantes = sorteio.setdefault(
            "participantes",
            [],
        )

        usuario_id = interaction.user.id

        if usuario_id in participantes:
            await interaction.response.send_message(
                "Você já está participando deste sorteio.",
                ephemeral=True,
            )
            return

        participantes.append(
            usuario_id
        )

        sorteio["atualizado_em"] = time.time()

        await self.salvar_sorteio(
            sorteio
        )

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

        participantes = sorteio.get(
            "participantes",
            [],
        )

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


class Sorteios(commands.Cog):

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

        return todos.get(
            str(sorteio_id)
        )

    async def obter_sorteio_por_mensagem(
        self,
        mensagem_id: int,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )

        for sorteio in todos.values():
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

        quantidade = len(
            sorteio.get(
                "participantes",
                [],
            )
        )

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
            participantes = sorteio.get(
                "participantes",
                [],
            )

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

        if sorteio.get("encerrado"):
            await interaction.response.send_message(
                "Este sorteio já foi encerrado.",
                ephemeral=True,
            )
            return

        fim = float(
            sorteio.get(
                "fim",
                0,
            )
        )

        if time.time() >= fim:
            await self.sortear_vencedores(
                sorteio
            )

            await interaction.response.send_message(
                "O sorteio acabou e os vencedores foram selecionados.",
                ephemeral=True,
            )

            return

        participantes = sorteio.setdefault(
            "participantes",
            [],
        )

        usuario_id = interaction.user.id

        if usuario_id in participantes:
            await interaction.response.send_message(
                "Você já está participando deste sorteio.",
                ephemeral=True,
            )
            return

        participantes.append(
            usuario_id
        )

        sorteio["atualizado_em"] = time.time()

        await self.salvar_sorteio(
            sorteio
        )

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
        if vencedores <= 0:
            await interaction.response.send_message(
                "A quantidade de vencedores precisa ser maior que 0.",
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