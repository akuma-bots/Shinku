import discord

from discord import app_commands
from discord.ext import commands


SISTEMAS = {
    "Missoes": ("🎯", "Missões"),
    "Desafios": ("⚔️", "PvP / Desafios"),
    "PvE": ("👹", "Contribuição"),
    "Guerras": ("🏰", "Guerras"),
    "Perfil": ("🎖️", "Perfil & Patentes"),
    "PerfilCard": ("🖼️", "Perfil Visual"),
    "RankingGeral": ("🌍", "Ranking Geral"),
    "PontuacaoPvE": ("🗡️", "Pontuação"),
    "Recordes": ("🏅", "Recordes"),
    "Temporadas": ("🏁", "Temporadas"),
    "Gangues": ("🏴", "Gangues"),
    "Loja": ("🛒", "Loja"),
    "Tickets": ("🎫", "Tickets"),
    "Formularios": ("📝", "Formulários"),
    "Revisoes": ("📋", "Revisão de Provas"),
    "Auditoria": ("🧾", "Auditoria"),
    "Ajuda": ("📖", "Ajuda"),
}


ORDEM = list(
    SISTEMAS.keys()
)


LIMITE_DESCRICAO = 3800


def _sistema_do_comando(
    comando: app_commands.Command,
):

    cog = comando.binding

    nome_cog = (
        cog.qualified_name
        if cog
        else "Outros"
    )

    emoji, titulo = SISTEMAS.get(
        nome_cog,
        ("🔧", nome_cog),
    )

    return (
        nome_cog,
        emoji,
        titulo,
    )


def _pode_ver(
    comando: app_commands.Command,
    membro: discord.Member,
) -> bool:

    if not comando.checks:
        return True

    return (
        membro.guild_permissions.administrator
        or membro.guild_permissions.manage_guild
    )


class PaginacaoAjuda(
    discord.ui.View
):

    def __init__(
        self,
        paginas: list,
        autor_id: int,
    ):

        super().__init__(
            timeout=120
        )

        self.paginas = paginas
        self.autor_id = autor_id
        self.indice = 0

        self._atualizar_botoes()


    def _atualizar_botoes(
        self,
    ):

        self.botao_anterior.disabled = (
            self.indice == 0
        )

        self.botao_proxima.disabled = (
            self.indice
            == len(self.paginas) - 1
        )


    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:

        if interaction.user.id != self.autor_id:

            await interaction.response.send_message(
                "Esse menu não é seu. "
                "Use `/help` para abrir o seu.",
                ephemeral=True,
            )

            return False

        return True


    @discord.ui.button(
        label="⬅️ Anterior",
        style=discord.ButtonStyle.secondary,
    )
    async def botao_anterior(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        self.indice -= 1

        self._atualizar_botoes()

        await interaction.response.edit_message(
            embed=self.paginas[self.indice],
            view=self,
        )


    @discord.ui.button(
        label="Próxima ➡️",
        style=discord.ButtonStyle.secondary,
    )
    async def botao_proxima(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):

        self.indice += 1

        self._atualizar_botoes()

        await interaction.response.edit_message(
            embed=self.paginas[self.indice],
            view=self,
        )


class Ajuda(commands.Cog):

    def __init__(
        self,
        bot: commands.Bot,
    ):

        self.bot = bot


    def _montar_agrupado(
        self,
        membro: discord.Member,
    ) -> dict:

        agrupado = {}


        for comando in sorted(
            self.bot.tree.get_commands(),
            key=lambda comando: comando.name,
        ):

            if not isinstance(
                comando,
                app_commands.Command,
            ):
                continue


            if not _pode_ver(
                comando,
                membro,
            ):
                continue


            nome_cog, emoji, titulo = (
                _sistema_do_comando(
                    comando
                )
            )


            agrupado.setdefault(
                nome_cog,
                {
                    "emoji": emoji,
                    "titulo": titulo,
                    "comandos": [],
                },
            )


            agrupado[
                nome_cog
            ][
                "comandos"
            ].append(
                comando
            )


        return agrupado


    def _montar_paginas(
        self,
        agrupado: dict,
    ) -> list:

        chaves_ordenadas = (
            [
                chave
                for chave in ORDEM
                if chave in agrupado
            ]
            +
            [
                chave
                for chave in agrupado
                if chave not in ORDEM
            ]
        )


        blocos = []


        for chave in chaves_ordenadas:

            grupo = agrupado[chave]

            linhas = "\n".join(
                f"**/{comando.name}** — "
                f"{comando.description}"
                for comando in grupo["comandos"]
            )


            blocos.append(
                f"**{grupo['emoji']} "
                f"{grupo['titulo']}**\n"
                f"{linhas}"
            )


        paginas_texto = []

        atual = ""


        for bloco in blocos:

            candidato = (
                f"{atual}\n\n{bloco}"
                if atual
                else bloco
            )


            if len(candidato) > LIMITE_DESCRICAO:

                if atual:
                    paginas_texto.append(
                        atual
                    )

                atual = bloco

            else:

                atual = candidato


        if atual:
            paginas_texto.append(
                atual
            )


        embeds = []

        total = len(
            paginas_texto
        )


        for numero, texto in enumerate(
            paginas_texto,
            start=1,
        ):

            embed = discord.Embed(
                title="✦ NÊMESIS — Comandos",
                description=texto,
                color=0x5865F2,
            )

            embed.set_footer(
                text=(
                    f"NÊMESIS • Página "
                    f"{numero}/{total}"
                )
            )

            embeds.append(
                embed
            )


        return embeds


    @app_commands.command(
        name="help",
        description=(
            "Exibe os comandos disponíveis "
            "da NÊMESIS."
        ),
    )
    async def help_cmd(
        self,
        interaction: discord.Interaction,
    ):

        agrupado = self._montar_agrupado(
            interaction.user
        )

        paginas = self._montar_paginas(
            agrupado
        )


        if not paginas:

            await interaction.response.send_message(
                "Nenhum comando disponível.",
                ephemeral=True,
            )

            return


        if len(paginas) == 1:

            await interaction.response.send_message(
                embed=paginas[0],
                ephemeral=True,
            )

            return


        view = PaginacaoAjuda(
            paginas,
            interaction.user.id,
        )


        await interaction.response.send_message(
            embed=paginas[0],
            view=view,
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
):

    await bot.add_cog(
        Ajuda(bot)
    )