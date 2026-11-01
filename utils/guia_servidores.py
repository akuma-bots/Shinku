import discord

GUILD_NEMESIS_ID = 1563995879981981817
CARGO_VISITANTES_ID = 1563995879990624371
NOME_CARGO_VISITANTES = "Visitantes"
TAG_ORG_NEMESIS = "NΞM"

# Áreas oficiais que ajudam um novo integrante a entender a estrutura da NÊMESIS.
CANAIS_GUIA_SERVIDORES = (
    ("Regras", 1563995880833421508, "📜"),
    ("Anúncios", 1564076387797569577, "📢"),
    ("Como funciona", 1563995880833421509, "🧭"),
    ("Divisões", 1563995880833421511, "⚔️"),
    ("Sistemas", 1563995880833421512, "⚙️"),
    ("Agenda", 1563995880623841337, "🗓️"),
    ("Inscrições", 1563995880623841338, "📝"),
    ("Missões", 1563995881315897549, "🎯"),
    ("Progressão", 1563995881315897548, "📈"),
    ("Ranking", 1563995881508831338, "🏆"),
    ("Parcerias", 1563995880833421513, "🤝"),
    ("Atendimento", 1563995881655509059, "🎫"),
)


DESCRICOES_CANAIS_GUIA = {
    1563995880833421508: "Consulte as diretrizes oficiais",
    1564076387797569577: "Acompanhe comunicados importantes",
    1563995880833421509: "Entenda a organização",
    1563995880833421511: "Conheça as divisões",
    1563995880833421512: "Veja os recursos disponíveis",
    1563995880623841337: "Confira eventos e atividades",
    1563995880623841338: "Acesse candidaturas e inscrições",
    1563995881315897549: "Consulte missões e objetivos",
    1563995881315897548: "Acompanhe sua evolução",
    1563995881508831338: "Veja a classificação geral",
    1563995880833421513: "Conheça as parcerias",
    1563995881655509059: "Fale com a equipe",
}


class GuiaCanaisSelect(discord.ui.Select):
    """Menu único para navegar pelas áreas oficiais da NÊMESIS."""

    def __init__(self):
        opcoes = [
            discord.SelectOption(
                label=nome,
                value=str(canal_id),
                emoji=emoji,
                description=DESCRICOES_CANAIS_GUIA[canal_id],
            )
            for nome, canal_id, emoji in CANAIS_GUIA_SERVIDORES
        ]
        super().__init__(
            placeholder="◈ Selecione uma área da NÊMESIS",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="nemesis:guia:canais",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        canal_id = int(self.values[0])
        selecionado = next(item for item in CANAIS_GUIA_SERVIDORES if item[1] == canal_id)
        nome, _, emoji = selecionado
        url = f"https://discord.com/channels/{GUILD_NEMESIS_ID}/{canal_id}"

        if interaction.message and interaction.message.embeds:
            embed = discord.Embed.from_dict(interaction.message.embeds[0].to_dict())
            campos = [field for field in embed.fields if field.name != "◈ DESTINO SELECIONADO"]
            embed.clear_fields()
            for field in campos:
                embed.add_field(name=field.name, value=field.value, inline=field.inline)
            embed.add_field(
                name="◈ DESTINO SELECIONADO",
                value=f"{emoji} **{nome}**\n[Abrir canal no Discord]({url})",
                inline=False,
            )
            await interaction.response.edit_message(embed=embed, view=self.view)
            return

        await interaction.response.send_message(
            f"{emoji} **{nome}**\n[Abrir canal no Discord]({url})",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


def adicionar_seletor_guia(view: discord.ui.View) -> discord.ui.View:
    view.add_item(GuiaCanaisSelect())
    return view


# Compatibilidade para módulos antigos que ainda importem o helper anterior.
def adicionar_botoes_guia(view: discord.ui.View) -> discord.ui.View:
    return adicionar_seletor_guia(view)


class GuiaServidoresView(discord.ui.View):
    """Seletor persistente para navegar pelas áreas oficiais da organização."""

    def __init__(self):
        super().__init__(timeout=None)
        adicionar_seletor_guia(self)
