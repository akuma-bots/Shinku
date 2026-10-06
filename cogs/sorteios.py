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


def timestamp_discord(timestamp: float, formato: str = "F") -> str:
    return f"<t:{int(timestamp)}:{formato}>"


class BotaoParticipar(discord.ui.View):
    """
    View persistente dos sorteios.

    Os dados são recuperados do sorteios.json,
    permitindo que os botões continuem funcionando
    mesmo depois que o bot reiniciar.
    """

    def __init__(
        self,
        participantes: int = 0,
        encerrado: bool = False,
    ):
        super().__init__(timeout=None)

        self.encerrado = encerrado
        self.participantes_total = participantes

        for item in self.children:
            if item.custom_id == "sorteio_participar_btn":
                item.label = (
                    "🎁 Encerrado"
                    if encerrado
                    else f"🎁 Participar ({participantes})"
                )

                item.disabled = encerrado

            elif item.custom_id == "sorteio_participantes_btn":
                item.label = (
                    f"👥 Participantes ({participantes})"
                )

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
            linhas.append(
                ""
            )

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
    """
    Sistema de sorteios da NÊMESIS.

    Cada sorteio possui:
    - texto/descrição;
    - requisitos;
    - prêmio;
    - quantidade de vencedores;
    - data de término;
    - participantes;
    - seleção automática dos vencedores.
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

    def criar_view(
        self,
        quantidade: int = 0,
        encerrado: bool = False,
    ) -> BotaoParticipar:

        return BotaoParticipar(
            participantes=quantidade,
            encerrado=encerrado,
        )

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
    async def atualizar_mensagem(
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

        quantidade = len(
            sorteio.get(
                "participantes",
                [],
            )
        )

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

        ativos = []

        for sorteio in todos.values():
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

    async def sortear_vencedores(
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

        quantidade_solicitada = int(
            sorteio.get(
                "vencedores",
                1,
            )
        )

        quantidade_real = min(
            quantidade_solicitada,
            len(participantes),
        )

        vencedores_ids = []

        if quantidade_real > 0:
            vencedores_ids = random.sample(
                participantes,
                quantidade_real,
            )

        agora = time.time()

        sorteio["encerrado"] = True

        sorteio["vencedores_ids"] = (
            vencedores_ids
        )

        sorteio["encerrado_em"] = agora
        sorteio["atualizado_em"] = agora

        await self.salvar_sorteio(
            sorteio
        )

        await self.atualizar_mensagem(
            sorteio
        )

        canal = self.bot.get_channel(
            sorteio.get("canal_id")
        )

        if not canal:
            return

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

            await canal.send(
                embed=embed
            )

            return

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
            if sorteio.get(
                "encerrado"
            ):
                continue

            fim = float(
                sorteio.get(
                    "fim",
                    0,
                )
            )

            if agora < fim:
                continue

            await self.sortear_vencedores(
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
    await bot.add_cog(
        Sorteios(bot)
    )