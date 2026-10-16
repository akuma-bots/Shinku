import discord

from discord import app_commands
from discord.ext import commands

from utils.apresentacao import criar_embed


SISTEMAS = {
    "Missoes": ("🎯", "Missões"),
    "Desafios": ("⚔️", "PvP / Desafios"),
    "Guerras": ("🏰", "Guerras"),
    "Perfil": ("🎖️", "Perfil & Patentes"),
    "Roblox": ("🎮", "Conta Roblox"),
    "Tutorial": ("📚", "Tutoriais por sistema"),
    "RankingGeral": ("🌍", "Ranking Geral"),
    "Recordes": ("🏅", "Recordes"),
    "Temporadas": ("🏁", "Temporadas"),
    "Gangues": ("🏴", "Gangues"),
    "Loja": ("🛒", "Loja"),
    "Tickets": ("🎫", "Tickets"),
    "Formularios": ("📝", "Formulários"),
    "Revisoes": ("📋", "Revisão de Provas"),
    "Auditoria": ("🧾", "Auditoria"),
    "Ajuda": ("📖", "Ajuda"),
    "AvisosPrivados": ("🔔", "Avisos Privados"),
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


def _comando_tem_acesso_controlado(comando: app_commands.Command) -> bool:
    """Indica que o comando aplica verificações adicionais de acesso."""
    return bool(
        comando.checks
        or getattr(comando, "default_permissions", None)
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


        # Os comandos da NÊMESIS são registrados no escopo do servidor,
        # não no escopo global. Consultar get_commands() sem guild retornava
        # uma árvore vazia e fazia o /help afirmar que não havia comandos.
        for comando in sorted(
            self.bot.tree.get_commands(guild=membro.guild),
            key=lambda comando: comando.name,
        ):

            if not isinstance(
                comando,
                app_commands.Command,
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
                f"**/{comando.name}**"
                f"{' 〔acesso controlado〕' if _comando_tem_acesso_controlado(comando) else ''} — "
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

            embed = criar_embed(
                "N̷ÊMESIS ━ CENTRAL DE COMANDOS",
                texto,
                rodape=f"NÊMESIS • Página {numero}/{total}",
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