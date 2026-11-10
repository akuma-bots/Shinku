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
    "RankingGeral": ("🌍", "Ranking Geral"),
    "Recordes": ("🏅", "Recordes"),
    "Temporadas": ("🏁", "Temporadas"),
    "Gangues": ("🏴", "Gangues"),
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


def _iterar_comandos(comandos):
    """Percorre comandos e subcomandos, incluindo grupos slash aninhados."""
    for comando in comandos:
        if isinstance(comando, app_commands.Group):
            yield from _iterar_comandos(comando.commands)
        elif isinstance(comando, app_commands.Command):
            yield comando



def _card_ajuda(origem: discord.ui.View, embed: discord.Embed) -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    partes = [f"## {embed.title or 'CENTRAL DE AJUDA'}"]
    if embed.description:
        partes.append(embed.description)
    for campo in embed.fields:
        partes.append(f"**{campo.name}**\n{campo.value}")
    if embed.footer and embed.footer.text:
        partes.append(f"-# {embed.footer.text}")
    componentes = [
        discord.ui.TextDisplay("\n\n".join(partes)[:3900]),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ]
    botoes = []
    for item in origem.children:
        if isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
            botoes.append(novo)
    for inicio in range(0, len(botoes), 5):
        componentes.append(discord.ui.ActionRow(*botoes[inicio:inicio + 5]))
    componentes.append(discord.ui.TextDisplay("-# NÊMESIS • Central de Orientação"))
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


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
                "Abra sua própria consulta pelo painel oficial de orientação.",
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
            view=_card_ajuda(self, self.paginas[self.indice]),
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
            view=_card_ajuda(self, self.paginas[self.indice]),
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
        comandos = _iterar_comandos(
            self.bot.tree.get_commands(guild=membro.guild)
        )
        for comando in sorted(
            comandos,
            key=lambda comando: comando.qualified_name,
        ):



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
            cabecalho = f"**{grupo['emoji']} {grupo['titulo']}**"
            bloco_atual = cabecalho

            for comando in grupo["comandos"]:
                acesso = (
                    " 〔acesso controlado〕"
                    if _comando_tem_acesso_controlado(comando)
                    else ""
                )
                linha = (
                    f"**/{comando.qualified_name}**{acesso} — "
                    f"{comando.description}"
                )
                candidato = f"{bloco_atual}\n{linha}"

                if len(candidato) > LIMITE_DESCRICAO and bloco_atual != cabecalho:
                    blocos.append(bloco_atual)
                    bloco_atual = f"{cabecalho}\n{linha}"
                else:
                    bloco_atual = candidato

            if bloco_atual:
                blocos.append(bloco_atual)


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
            view=_card_ajuda(view, paginas[0]),
            ephemeral=True,
        )


async def setup(
    bot: commands.Bot,
):

    await bot.add_cog(
        Ajuda(bot)
    )