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


def adicionar_botoes_guia(view: discord.ui.View) -> discord.ui.View:
    for indice, (nome, canal_id, emoji) in enumerate(CANAIS_GUIA_SERVIDORES):
        view.add_item(discord.ui.Button(
            label=nome,
            emoji=emoji,
            style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{GUILD_NEMESIS_ID}/{canal_id}",
            row=indice // 5,
        ))
    return view


class GuiaServidoresView(discord.ui.View):
    """Atalhos diretos para as áreas essenciais da organização."""

    def __init__(self):
        super().__init__(timeout=None)
        adicionar_botoes_guia(self)
