import logging

import discord

logger = logging.getLogger(__name__)

GUILD_NEMESIS_ID = 1563995879981981817
CANAL_GUIA_SERVIDOR_ID = 1563995880833421509
CARGO_VISITANTES_ID = 1563995879990624371
NOME_CARGO_VISITANTES = "Visitantes"
TAG_ORG_NEMESIS = "NΞM"
RODAPE_GUIA = "NÊMESIS • GUIA OFICIAL DO SERVIDOR"

# Somente áreas oficiais de orientação geral. Áreas privadas não são
# cadastradas aqui; o acesso a cada destino também é validado no clique.
CANAIS_GUIA_SERVIDORES = (
    ("Regras", 1563995880833421508, "📜", "Leia as normas, limites e responsabilidades de todos os integrantes."),
    ("Anúncios", 1564076387797569577, "📢", "Acompanhe comunicados oficiais, mudanças e avisos da organização."),
    ("Como funciona", 1563995880833421509, "🧭", "Entenda a NÊMESIS, seus objetivos e o caminho para começar."),
    ("Divisões", 1563995880833421511, "⚔️", "Conheça a estrutura de divisões e suas frentes de atuação."),
    ("Sistemas", 1563995880833421512, "⚙️", "Consulte orientações de uso dos recursos e ferramentas do servidor."),
    ("Agenda", 1563995880623841337, "🗓️", "Veja a programação de atividades, eventos e compromissos."),
    ("Inscrições", 1563995880623841338, "📝", "Acesse os espaços de candidatura e inscrição disponíveis."),
    ("Missões", 1563995881315897549, "🎯", "Confira objetivos e atividades propostas pela organização."),
    ("Progressão", 1563995881315897548, "📈", "Acompanhe sua evolução por XP e os critérios oficiais de progressão."),
    ("Ranking", 1563995881508831338, "🏆", "Consulte classificações e posições divulgadas oficialmente."),
    ("Parcerias", 1563995880833421513, "🤝", "Conheça as iniciativas e oportunidades de parceria."),
    ("Atendimento", 1563995881655509059, "🎫", "Procure a equipe pelos canais oficiais de atendimento."),
)

DESCRICOES_CANAIS_GUIA = {canal_id: descricao for _, canal_id, _, descricao in CANAIS_GUIA_SERVIDORES}


def criar_embed_guia_servidor() -> discord.Embed:
    """Apresentação institucional e roteiro inicial da NÊMESIS."""
    embed = discord.Embed(
        title="✦ NÊMESIS — GUIA OFICIAL DO SERVIDOR",
        description=(
            "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            "       **THE ART OF POWER & STRATEGY**\n"
            "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            "A **NÊMESIS** é uma organização construída em torno de competição, "
            "evolução, estratégia e comunidade. Este espaço reúne integrantes "
            "que desejam participar de uma estrutura organizada, desenvolver "
            "suas capacidades e construir resultados em conjunto.\n\n"
            "**TAG OFICIAL:** `NΞM`"
        ),
        colour=0xB3132B,
    )
    embed.add_field(
        name="◈ NOSSA IDENTIDADE",
        value=(
            "A NÊMESIS valoriza compromisso, respeito, disciplina, iniciativa "
            "e espírito competitivo. Cada integrante deve compreender seu papel, "
            "respeitar a organização e contribuir de forma positiva."
        ),
        inline=False,
    )
    embed.add_field(
        name="◈ NOSSO OBJETIVO",
        value=(
            "Manter uma comunidade ativa e estruturada, promover atividades e "
            "competições, incentivar a evolução individual e coletiva e reconhecer "
            "a participação por meio de critérios e processos oficiais."
        ),
        inline=False,
    )
    embed.add_field(
        name="◈ COMO A ORGANIZAÇÃO FUNCIONA",
        value=(
            "A comunidade é organizada por áreas e divisões, cada uma com sua "
            "finalidade. O OCTÓGONO é o núcleo de autoridade máxima e possui a "
            "gestão das missões. As divisões atuam em suas frentes específicas, "
            "conforme as responsabilidades designadas. Cargos e permissões definem "
            "responsabilidades e acessos; uma patente competitiva ou XP não concede "
            "permissões administrativas."
        ),
        inline=False,
    )
    embed.add_field(
        name="◈ SEU PRIMEIRO PERCURSO",
        value=(
            "**01.** Leia as regras e entenda as expectativas.\n"
            "**02.** Conheça a apresentação da organização e suas divisões.\n"
            "**03.** Acompanhe os anúncios e a agenda.\n"
            "**04.** Consulte as orientações antes de participar de missões, eventos ou inscrições.\n"
            "**05.** Em caso de dúvida, procure o Atendimento."
        ),
        inline=False,
    )
    embed.add_field(
        name="◈ COMO PARTICIPAR",
        value=(
            "Mantenha-se informado, participe das atividades para as quais estiver "
            "apto, respeite as orientações da equipe responsável e acompanhe seus "
            "resultados pelos espaços oficiais. Não presuma acesso ou autoridade "
            "que não tenham sido concedidos."
        ),
        inline=False,
    )
    embed.add_field(
        name="◈ NAVEGAÇÃO RÁPIDA",
        value=(
            "Use o menu abaixo para localizar cada área e abrir o canal correspondente. "
            "A lista apresenta os espaços gerais de orientação; canais internos ou "
            "restritos não são divulgados por este guia."
        ),
        inline=False,
    )
    embed.set_footer(text=RODAPE_GUIA)
    return embed


class GuiaCanaisSelect(discord.ui.Select):
    """Menu para navegar pelos canais gerais da NÊMESIS."""

    def __init__(self):
        opcoes = [
            discord.SelectOption(
                label=nome,
                value=str(canal_id),
                emoji=emoji,
                description=descricao[:100],
            )
            for nome, canal_id, emoji, descricao in CANAIS_GUIA_SERVIDORES
        ]
        super().__init__(
            placeholder="◈ Escolha uma área para conhecer",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="nemesis:guia:canais",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != GUILD_NEMESIS_ID:
            await interaction.response.send_message(
                "Este guia está disponível exclusivamente na NÊMESIS.",
                ephemeral=True,
            )
            return

        canal_id = int(self.values[0])
        selecionado = next(
            (item for item in CANAIS_GUIA_SERVIDORES if item[1] == canal_id),
            None,
        )
        if selecionado is None:
            await interaction.response.send_message(
                "Esta área não está disponível no guia.",
                ephemeral=True,
            )
            return

        nome, _, emoji, descricao = selecionado
        canal = interaction.guild.get_channel(canal_id)
        if canal is None:
            try:
                canal = await interaction.guild.fetch_channel(canal_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                canal = None

        if canal is None:
            await interaction.response.send_message(
                "Não foi possível localizar esse canal. Avise a equipe pelo Atendimento.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        permissoes = canal.permissions_for(interaction.user)
        if not permissoes.view_channel:
            await interaction.response.send_message(
                "Este espaço não está disponível para sua conta. O guia não revela canais internos ou acessos restritos.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        url = f"https://discord.com/channels/{GUILD_NEMESIS_ID}/{canal_id}"
        resposta = discord.Embed(
            title=f"{emoji} {nome.upper()}",
            description=(
                f"{descricao}\n\n"
                "Ao acessar o canal, confira as mensagens fixadas e siga as orientações "
                "publicadas pela equipe responsável."
            ),
            colour=0xB3132B,
        )
        resposta.add_field(
            name="◈ ACESSO DIRETO",
            value=f"[**Abrir {nome} no Discord**]({url})",
            inline=False,
        )
        resposta.set_footer(text="NÊMESIS • Orientação do servidor")
        await interaction.response.send_message(
            embed=resposta,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


def adicionar_seletor_guia(view: discord.ui.View) -> discord.ui.View:
    view.add_item(GuiaCanaisSelect())
    return view


# Compatibilidade com módulos antigos.
def adicionar_botoes_guia(view: discord.ui.View) -> discord.ui.View:
    return adicionar_seletor_guia(view)


class GuiaServidoresView(discord.ui.View):
    """Navegação persistente do guia oficial da NÊMESIS."""

    def __init__(self):
        super().__init__(timeout=None)
        adicionar_seletor_guia(self)
        self.add_item(discord.ui.Button(
            label="Regras", emoji="📜", style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{GUILD_NEMESIS_ID}/1563995880833421508",
            row=1,
        ))
        self.add_item(discord.ui.Button(
            label="Divisões", emoji="⚔️", style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{GUILD_NEMESIS_ID}/1563995880833421511",
            row=1,
        ))
        self.add_item(discord.ui.Button(
            label="Atendimento", emoji="🎫", style=discord.ButtonStyle.link,
            url=f"https://discord.com/channels/{GUILD_NEMESIS_ID}/1563995881655509059",
            row=1,
        ))


async def publicar_guia_servidor(bot) -> bool:
    """Cria o guia no canal oficial ou atualiza a mensagem existente, sem duplicar."""
    guild = bot.get_guild(GUILD_NEMESIS_ID)
    if guild is None:
        logger.warning("Servidor NÊMESIS indisponível; publicação do guia adiada.")
        return False

    canal = guild.get_channel(CANAL_GUIA_SERVIDOR_ID)
    if canal is None:
        try:
            canal = await bot.fetch_channel(CANAL_GUIA_SERVIDOR_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.exception("Canal oficial do guia indisponível.")
            return False

    if not isinstance(canal, discord.TextChannel) or canal.guild.id != GUILD_NEMESIS_ID:
        logger.error("O destino configurado para o guia não é um canal de texto da NÊMESIS.")
        return False

    bot_member = guild.me or guild.get_member(bot.user.id)
    if bot_member is None:
        logger.error("Não foi possível resolver o membro do Shinku na NÊMESIS.")
        return False
    permissoes_bot = canal.permissions_for(bot_member)
    if not (permissoes_bot.view_channel and permissoes_bot.send_messages and permissoes_bot.read_message_history):
        logger.error("Shinku precisa de Ver canal, Enviar mensagens e Ler histórico para manter o guia sem duplicações.")
        return False

    embed = criar_embed_guia_servidor()
    try:
        async for mensagem in canal.history(limit=75):
            if mensagem.author.id != bot.user.id:
                continue
            if any(
                item.footer and item.footer.text == RODAPE_GUIA
                for item in mensagem.embeds
            ):
                await mensagem.edit(
                    embed=embed,
                    view=GuiaServidoresView(),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                logger.info("Guia oficial da NÊMESIS atualizado (message=%s).", mensagem.id)
                return True

        await canal.send(
            embed=embed,
            view=GuiaServidoresView(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        logger.info("Guia oficial da NÊMESIS publicado (channel=%s).", canal.id)
        return True
    except (discord.Forbidden, discord.HTTPException):
        logger.exception("Falha ao publicar/atualizar o guia oficial da NÊMESIS.")
        return False
