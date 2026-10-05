import time
import uuid
import random

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import carregar, salvar


ARQUIVO = "sorteios.json"


class BotaoParticipar(discord.ui.View):
    """View persistente dos sorteios."""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="🎉 Participar",
        style=discord.ButtonStyle.primary,
        custom_id="sorteio_participar_btn",
    )
    async def participar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        todos = await carregar(
            ARQUIVO,
            {},
        )

        sorteio = next(
            (
                s
                for s in todos.values()
                if str(s.get("mensagem_id"))
                == str(interaction.message.id)
            ),
            None,
        )

        if not sorteio or sorteio.get("encerrado"):
            await interaction.response.send_message(
                "Esse sorteio já acabou.",
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
                "Você já está participando!",
                ephemeral=True,
            )
            return

        participantes.append(
            usuario_id
        )

        sorteio["atualizado_em"] = time.time()

        todos[sorteio["id"]] = sorteio

        await salvar(
            ARQUIVO,
            todos,
        )

        await interaction.response.send_message(
            "✓ Você entrou no sorteio. Boa sorte!",
            ephemeral=True,
        )


class Sorteios(commands.Cog):
    """
    Sistema de sorteios da NÊMESIS.

    O sorteio continua sendo executado pelo Discord,
    mas todo o estado fica persistido em sorteios.json,
    permitindo que o Dashboard consulte os mesmos dados.
    """

    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot

        bot.add_view(
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
            sorteio_id
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

        todos[sorteio["id"]] = sorteio

        await salvar(
            ARQUIVO,
            todos,
        )

    @app_commands.command(
        name="sorteio-criar",
        description="Cria um sorteio com botão de participação.",
    )
    @app_commands.describe(
        premio="O que será sorteado",
        duracao_minutos="Duração do sorteio em minutos",
        vencedores="Quantidade de vencedores",
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

        embed = discord.Embed(
            title="🎉 SORTEIO!",
            description=(
                f"**Prêmio:** {premio}\n"
                f"**Vencedores:** {vencedores}\n"
                f"**Termina:** "
                f"<t:{int(fim)}:R>\n\n"
                "Clique no botão abaixo para participar."
            ),
            color=0xFEE75C,
        )

        embed.set_footer(
            text=(
                f"Sorteio criado por "
                f"{interaction.user}"
            )
        )

        await interaction.response.send_message(
            "Criando sorteio...",
            ephemeral=True,
        )

        mensagem = await canal_destino.send(
            embed=embed,
            view=BotaoParticipar(),
        )

        agora = time.time()

        sorteio = {
            "id": sorteio_id,
            "guild_id": interaction.guild.id,
            "canal_id": canal_destino.id,
            "mensagem_id": mensagem.id,
            "premio": premio,
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

        todos = await carregar(
            ARQUIVO,
            {},
        )

        todos[sorteio_id] = sorteio

        await salvar(
            ARQUIVO,
            todos,
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
            s
            for s in todos.values()
            if s.get("guild_id")
            == interaction.guild.id
            and not s.get("encerrado")
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
                f"({participantes} participantes) "
                f"— termina "
                f"<t:{int(sorteio['fim'])}:R>"
            )

        await interaction.response.send_message(
            "\n".join(linhas),
            ephemeral=True,
        )

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

        if not participantes:

            await canal.send(
                f"🎉 O sorteio de **"
                f"{sorteio['premio']}** foi encerrado, "
                "mas ninguém participou."
            )

            return

        mencoes = ", ".join(
            f"<@{uid}>"
            for uid in vencedores_ids
        )

        await canal.send(
            f"🎉 Sorteio de **"
            f"{sorteio['premio']}** encerrado!\n"
            f"Vencedor(es): {mencoes}"
        )

    @tasks.loop(seconds=60)
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
    await bot.add_cog(
        Sorteios(bot)
    )