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


def formatar_data(timestamp: float) -> str:
    return f"<t:{int(timestamp)}:F>"


def formatar_relativo(timestamp: float) -> str:
    return f"<t:{int(timestamp)}:R>"


class BotaoParticipar(discord.ui.View):
    """View persistente dos sorteios."""

    def __init__(self):
        super().__init__(timeout=None)

    async def obter_sorteio(self, mensagem_id: int):
        todos = await carregar(
            ARQUIVO,
            {},
        )

        return next(
            (
                sorteio
                for sorteio in todos.values()
                if str(sorteio.get("mensagem_id"))
                == str(mensagem_id)
            ),
            None,
        )

    async def atualizar_mensagem(
        self,
        interaction: discord.Interaction,
        sorteio: dict,
    ):
        participantes = sorteio.get(
            "participantes",
            [],
        )

        encerrado = sorteio.get(
            "encerrado",
            False,
        )

        view = BotaoParticipar()

        botao_participar = next(
            (
                item
                for item in view.children
                if item.custom_id
                == "sorteio_participar_btn"
            ),
            None,
        )

        botao_participantes = next(
            (
                item
                for item in view.children
                if item.custom_id
                == "sorteio_participantes_btn"
            ),
            None,
        )

        if botao_participar:
            botao_participar.label = (
                f"🎁 Participar ({len(participantes)})"
            )

            if encerrado:
                botao_participar.disabled = True
                botao_participar.label = "🎁 Encerrado"

        if botao_participantes:
            botao_participantes.label = (
                f"👥 Participantes ({len(participantes)})"
            )

        try:
            await interaction.message.edit(
                view=view,
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
                "Não encontrei os dados desse sorteio.",
                ephemeral=True,
            )
            return

        if sorteio.get("encerrado"):
            await interaction.response.send_message(
                "Esse sorteio já foi encerrado.",
                ephemeral=True,
            )
            return

        if (
            time.time()
            >= float(
                sorteio.get(
                    "fim",
                    0,
                )
            )
        ):
            await interaction.response.send_message(
                "Esse sorteio já terminou.",
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

        todos = await carregar(
            ARQUIVO,
            {},
        )

        todos[sorteio["id"]] = sorteio

        await salvar(
            ARQUIVO,
            todos,
        )

        await interaction.response.send_message(
            "✓ Você entrou no sorteio. Boa sorte!",
            ephemeral=True,
        )

        await self.atualizar_mensagem(
            interaction,
            sorteio,
        )

    @discord.ui.button(
        label="👥 Participantes (0)",
        style=discord.ButtonStyle.primary,
        custom_id="sorteio_participantes_btn",
    )
    async def participantes(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        sorteio = await self.obter_sorteio(
            interaction.message.id
        )

        if not sorteio:
            await interaction.response.send_message(
                "Não encontrei os dados desse sorteio.",
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

        total = len(participantes)

        linhas = []

        limite = 50

        for indice, usuario_id in enumerate(
            participantes[:limite],
            start=1,
        ):
            linhas.append(
                f"`{indice:02}` <@{usuario_id}>"
            )

        if total > limite:
            linhas.append(
                f"\n... e mais "
                f"**{total - limite}** participantes."
            )

        embed = discord.Embed(
            title="👥 Participantes",
            description="\n".join(linhas),
            color=COR_SORTEIO,
        )

        embed.set_footer(
            text=(
                f"{total} participante"
                f"{'s' if total != 1 else ''}"
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )


class Sorteios(commands.Cog):
    """
    Sistema de sorteios da NÊMESIS.

    Os sorteios são persistidos em sorteios.json
    e sincronizados com o Dashboard através do
    armazenamento compartilhado.
    """

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

    async def _obter_sorteio(
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

    async def _salvar_sorteio(
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

    def criar_embed(
        self,
        premio: str,
        descricao: str,
        requisito: str,
        fim: float,
        vencedores: int,
        criado_por: discord.Member,
        banner_url: str | None = None,
    ) -> discord.Embed:

        texto = ""

        if descricao:
            texto += (
                f"{descricao}\n\n"
            )

        if requisito:
            texto += (
                "⚠️ **Requisitos mínimos:**\n"
                f"{requisito}\n\n"
            )

        texto += (
            "🎁 **Prêmio:**\n"
            f"**{premio}**\n\n"
            "🏆 **Vencedores:** "
            f"**{vencedores}**\n\n"
            "⏰ **Termina:**\n"
            f"{formatar_data(fim)} "
            f"({formatar_relativo(fim)})\n\n"
            "Clique em **Participar** abaixo "
            "para entrar no sorteio."
        )

        embed = discord.Embed(
            title=f"🎁 {premio}",
            description=texto,
            color=COR_SORTEIO,
        )

        embed.set_author(
            name="NÊMESIS • SORTEIO"
        )

        if banner_url:
            embed.set_image(
                url=banner_url
            )

        embed.set_footer(
            text=(
                f"Sorteio criado por "
                f"{criado_por.display_name}"
            ),
            icon_url=(
                criado_por.display_avatar.url
            ),
        )

        return embed

    def criar_view(
        self,
        quantidade: int = 0,
        encerrado: bool = False,
    ):
        view = BotaoParticipar()

        for item in view.children:
            if (
                item.custom_id
                == "sorteio_participar_btn"
            ):
                item.label = (
                    "🎁 Encerrado"
                    if encerrado
                    else f"🎁 Participar ({quantidade})"
                )

                item.disabled = encerrado

            elif (
                item.custom_id
                == "sorteio_participantes_btn"
            ):
                item.label = (
                    f"👥 Participantes ({quantidade})"
                )

        return view

    @app_commands.command(
        name="sorteio-criar",
        description="Cria um sorteio visual da NÊMESIS.",
    )
    @app_commands.describe(
        premio="Prêmio do sorteio",
        duracao_minutos="Duração do sorteio em minutos",
        vencedores="Quantidade de vencedores",
        descricao="Descrição ou informações do sorteio",
        requisito="Requisito mínimo para participar",
        banner="URL da imagem/banner do sorteio",
        canal="Canal onde o sorteio será publicado",
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def sorteio_criar(
        self,
        interaction: discord.Interaction,
        premio: str,
        duracao_minutos: int,
        vencedores: int = 1,
        descricao: str = "",
        requisito: str = "",
        banner: str = "",
        canal: discord.TextChannel = None,
    ):
        if duracao_minutos <= 0:
            await interaction.response.send_message(
                "A duração precisa ser maior que 0 minutos.",
                ephemeral=True,
            )
            return

        if vencedores <= 0:
            await interaction.response.send_message(
                "A quantidade de vencedores precisa ser maior que 0.",
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

        fim = (
            time.time()
            + duracao_minutos * 60
        )

        sorteio_id = str(
            uuid.uuid4()
        )[:8]

        embed = self.criar_embed(
            premio=premio,
            descricao=descricao,
            requisito=requisito,
            fim=fim,
            vencedores=vencedores,
            criado_por=interaction.user,
            banner_url=(
                banner.strip()
                if banner
                else None
            ),
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

            "premio": premio,

            "descricao": descricao,
            "requisito": requisito,
            "banner": (
                banner.strip()
                if banner
                else None
            ),

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

        await self._salvar_sorteio(
            sorteio
        )

        await interaction.edit_original_response(
            content=(
                f"✓ Sorteio criado em "
                f"{canal_destino.mention}.\n"
                f"ID: `{sorteio_id}`"
            )
        )

    @app_commands.command(
        name="sorteio-encerrar",
        description="Encerra um sorteio e sorteia os vencedores.",
    )
    @app_commands.describe(
        id="ID do sorteio",
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def sorteio_encerrar(
        self,
        interaction: discord.Interaction,
        id: str,
    ):
        sorteio = await self._obter_sorteio(
            id
        )

        if (
            not sorteio
            or sorteio.get("guild_id")
            != interaction.guild.id
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
            "Encerrando sorteio...",
            ephemeral=True,
        )

        await self._sortear_vencedores(
            sorteio
        )

    @app_commands.command(
        name="sorteio-listar",
        description="Lista os sorteios ativos do servidor.",
    )
    async def sorteio_listar(
        self,
        interaction: discord.Interaction,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )

        ativos = [
            sorteio
            for sorteio in todos.values()
            if sorteio.get("guild_id")
            == interaction.guild.id
            and not sorteio.get("encerrado")
        ]

        if not ativos:
            await interaction.response.send_message(
                "Nenhum sorteio em andamento.",
                ephemeral=True,
            )
            return

        linhas = []

        for sorteio in ativos:
            participantes = len(
                sorteio.get(
                    "participantes",
                    [],
                )
            )

            linhas.append(
                f"**#{sorteio['id']}** — "
                f"{sorteio['premio']} "
                f"• **{participantes}** participantes "
                f"• termina "
                f"{formatar_relativo(sorteio['fim'])}"
            )

        embed = discord.Embed(
            title="🎁 Sorteios ativos",
            description="\n".join(linhas),
            color=COR_SORTEIO,
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
        )

    async def _atualizar_sorteio_discord(
        self,
        sorteio: dict,
    ):
        canal = self.bot.get_channel(
            sorteio.get("canal_id")
        )

        if not canal:
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

        participantes = len(
            sorteio.get(
                "participantes",
                [],
            )
        )

        view = self.criar_view(
            quantidade=participantes,
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

    async def _sortear_vencedores(
        self,
        sorteio: dict,
    ):
        if sorteio.get("encerrado"):
            return

        participantes = list(
            sorteio.get(
                "participantes",
                [],
            )
        )

        quantidade = min(
            int(
                sorteio.get(
                    "vencedores",
                    1,
                )
            ),
            len(participantes),
        )

        vencedores_ids = []

        if quantidade > 0:
            vencedores_ids = random.sample(
                participantes,
                quantidade,
            )

        sorteio["encerrado"] = True

        sorteio["vencedores_ids"] = (
            vencedores_ids
        )

        sorteio["encerrado_em"] = time.time()
        sorteio["atualizado_em"] = time.time()

        await self._salvar_sorteio(
            sorteio
        )

        canal = self.bot.get_channel(
            sorteio.get("canal_id")
        )

        if not canal:
            return

        try:
            mensagem = await canal.fetch_message(
                sorteio.get("mensagem_id")
            )

            await mensagem.edit(
                view=self.criar_view(
                    quantidade=len(
                        participantes
                    ),
                    encerrado=True,
                )
            )
        except (
            discord.NotFound,
            discord.Forbidden,
            discord.HTTPException,
        ):
            pass

        if not participantes:
            embed = discord.Embed(
                title="🎁 Sorteio encerrado",
                description=(
                    f"O sorteio de "
                    f"**{sorteio['premio']}** foi encerrado.\n\n"
                    "Ninguém participou."
                ),
                color=COR_ERRO,
            )

            await canal.send(
                embed=embed
            )
            return

        mencoes = ", ".join(
            f"<@{uid}>"
            for uid in vencedores_ids
        )

        embed = discord.Embed(
            title="🏆 Sorteio encerrado!",
            description=(
                f"🎁 **Prêmio:** "
                f"{sorteio['premio']}\n\n"
                f"🏆 **Vencedor(es):**\n"
                f"{mencoes}\n\n"
                f"👥 **Participantes:** "
                f"**{len(participantes)}**"
            ),
            color=COR_SUCESSO,
        )

        embed.set_footer(
            text="NÊMESIS • Sorteios"
        )

        await canal.send(
            embed=embed
        )

    @tasks.loop(seconds=30)
    async def verificar_sorteios(
        self,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )

        agora = time.time()

        for sorteio in list(
            todos.values()
        ):
            if (
                sorteio.get("encerrado")
                or agora
                < float(
                    sorteio.get(
                        "fim",
                        0,
                    )
                )
            ):
                continue

            await self._sortear_vencedores(
                sorteio
            )

    @verificar_sorteios.before_loop
    async def antes(
        self,
    ):
        await self.bot.wait_until_ready()


async def setup(
    bot: commands.Bot,
):
    await bot.add_cog