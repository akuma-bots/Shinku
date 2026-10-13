import discord
from discord import app_commands
from discord.ext import commands


TUTORIAIS = {
    "inicio": {
        "titulo": "Começando na NÊMESIS",
        "descricao": "Guia inicial para novos membros.",
        "passos": [
            "Leia as regras e acompanhe os anúncios oficiais.",
            "Use /perfil para consultar sua progressão e estatísticas.",
            "Use /roblox-vincular e depois /roblox-confirmar para associar sua conta Roblox.",
            "Consulte /help para ver os comandos disponíveis para seu cargo.",
            "Use /avisos-privados para escolher se quer receber novidades por DM.",
        ],
        "comandos": "/help · /perfil · /roblox-vincular · /avisos-privados",
    },
    "missoes": {
        "titulo": "Missões e Contribuições",
        "descricao": "Como participar das atividades e registrar progresso.",
        "passos": [
            "Consulte os canais oficiais de Missões, Contribuições e Missões Especiais.",
            "Leia os requisitos da atividade antes de começar.",
            "Conclua a atividade e envie a prova pelo comando indicado na descrição da missão.",
            "Aguarde a revisão da staff; não envie a mesma prova repetidamente.",
            "Confira o resultado no perfil e no ranking após a aprovação.",
        ],
        "comandos": "/help · /perfil · /painel-provas (staff)",
    },
    "pvp": {
        "titulo": "PvP e Desafios",
        "descricao": "Fluxo recomendado para duelos e resultados competitivos.",
        "passos": [
            "Combine o formato, as regras e o horário com o adversário antes da luta.",
            "Use os comandos de desafio disponíveis em /help para registrar o confronto.",
            "Guarde uma prova legível do resultado e envie-a pelo fluxo oficial.",
            "Se houver divergência, solicite revisão em vez de criar registros duplicados.",
            "Confira vitórias, derrotas e P.C. no perfil depois da confirmação.",
        ],
        "comandos": "/help · /perfil · /painel-provas (staff)",
    },
    "guerras": {
        "titulo": "Guerras entre gangues",
        "descricao": "Como organizar e registrar uma guerra oficial.",
        "passos": [
            "Defina a gangue adversária, formato, placar esperado e regras antes do confronto.",
            "Confirme os participantes e a autorização da liderança.",
            "Após a guerra, registre o placar e anexe uma prova quando disponível.",
            "Use o histórico oficial para evitar registros repetidos ou conflitantes.",
            "Cancelamentos e correções devem ser feitos pela equipe autorizada, com justificativa.",
        ],
        "comandos": "/guerra-registrar · /help",
    },
    "revisoes": {
        "titulo": "Revisão de provas",
        "descricao": "Procedimento para quem envia provas e para a equipe revisora.",
        "passos": [
            "Envie uma imagem acessível, nítida e relacionada à atividade registrada.",
            "Não reutilize a mesma captura para comprovar atividades diferentes.",
            "A staff deve conferir contexto, autor, data e requisitos antes de decidir.",
            "Se a aplicação da recompensa falhar, consulte os logs e reavalie a pendência; não conceda recompensa manualmente sem verificar o estado.",
            "Registre a decisão e o motivo de rejeição de forma objetiva.",
        ],
        "comandos": "/painel-provas · /help",
    },
    "perfil": {
        "titulo": "Perfil, XP e P.C.",
        "descricao": "Como acompanhar seu desenvolvimento dentro da gangue.",
        "passos": [
            "Use /perfil para consultar patente, XP, vitórias, derrotas, sequência e medalhas.",
            "Use os rankings disponíveis em /help para comparar resultados.",
            "P.C. representa Pontos de Contribuição da temporada competitiva.",
            "O registro pode levar alguns instantes para aparecer no site se houver atraso de sincronização.",
            "Se um dado estiver incorreto, abra um ticket com a prova e os detalhes do registro.",
        ],
        "comandos": "/perfil · /ranking-jogadores · /help",
    },
    "roblox": {
        "titulo": "Vincular conta Roblox",
        "descricao": "Verificação de propriedade e identificação de membros.",
        "passos": [
            "Execute /roblox-vincular e informe seu nome de usuário Roblox.",
            "Copie o código gerado e coloque temporariamente na descrição Sobre do perfil Roblox.",
            "Execute /roblox-confirmar para o bot verificar o código.",
            "Depois da confirmação, você pode remover o código da descrição.",
            "Use /roblox-perfil para consultar o vínculo ou /roblox-desvincular para removê-lo.",
        ],
        "comandos": "/roblox-vincular · /roblox-confirmar · /roblox-perfil · /roblox-desvincular",
    },
    "moderacao": {
        "titulo": "Moderação e conduta",
        "descricao": "Orientações para membros e equipe de moderação.",
        "passos": [
            "Aplique as regras de forma consistente e sem favorecimento.",
            "Antes de punir, verifique contexto, evidências e histórico quando disponível.",
            "Registre um motivo claro e proporcional à infração.",
            "Ações administrativas devem respeitar as permissões e a hierarquia do Discord.",
            "Em caso de dúvida ou conflito de interesse, encaminhe o caso à liderança.",
        ],
        "comandos": "/help · /ban · /kick · /timeout (equipe autorizada)",
    },
    "sorteios": {
        "titulo": "Sorteios",
        "descricao": "Como participar e como a equipe deve configurar sorteios.",
        "passos": [
            "Leia o prêmio, os requisitos e o horário de encerramento no anúncio.",
            "Use o botão de participação da mensagem oficial; reações ou mensagens não substituem o botão.",
            "Confira se você atende aos requisitos informados.",
            "Ao encerrar, o bot seleciona os vencedores conforme o sorteio registrado.",
            "Se houver erro, guarde o link da mensagem e abra um ticket; não crie outro sorteio para substituir sem registrar o motivo.",
        ],
        "comandos": "/help · comandos de sorteio listados na central de comandos",
    },
    "tickets": {
        "titulo": "Atendimento e tickets",
        "descricao": "Como pedir suporte sem perder o histórico.",
        "passos": [
            "Abra um ticket pela mensagem ou painel oficial de atendimento.",
            "Escolha a categoria correta e explique o problema de forma objetiva.",
            "Inclua IDs, links e capturas relevantes; nunca envie tokens ou senhas.",
            "Aguarde a equipe e responda no mesmo ticket para preservar o contexto.",
            "Quando o atendimento terminar, confirme a solução antes do fechamento.",
        ],
        "comandos": "/help · painel de atendimento",
    },
    "eventos": {
        "titulo": "Eventos e campeonatos",
        "descricao": "Como acompanhar e organizar atividades agendadas.",
        "passos": [
            "Confira o canal de eventos e o horário anunciado.",
            "Leia formato, requisitos de participação e regras específicas.",
            "Confirme presença no evento oficial quando essa opção estiver disponível.",
            "Chegue preparado e siga as orientações da organização.",
            "Problemas de horário ou inscrição devem ser comunicados à staff antes do início.",
        ],
        "comandos": "/help · /campeonato-agendar (staff)",
    },
    "formularios": {
        "titulo": "Formulários e recrutamento",
        "descricao": "Como preencher candidaturas e solicitações.",
        "passos": [
            "Leia a descrição do formulário: ela contém requisitos e instruções importantes.",
            "Abra o botão [Preencher Formulário] e responda às perguntas dentro dele.",
            "Revise as respostas antes de enviar; não envie candidaturas duplicadas.",
            "Aguarde a análise da equipe responsável.",
            "A aprovação não é automática e pode depender de entrevista ou avaliação.",
        ],
        "comandos": "Use o painel de formulários oficial da NÊMESIS.",
    },
    "avisos": {
        "titulo": "Novidades por mensagem privada",
        "descricao": "Controle os comunicados enviados por DM.",
        "passos": [
            "Use /avisos-privados e escolha Ativar para receber novidades, sistemas, eventos e avisos importantes.",
            "Escolha Desativar a qualquer momento para interromper os comunicados.",
            "Mensagens privadas dependem das configurações de privacidade do Discord.",
            "Os comunicados automáticos são destinados apenas aos membros inscritos.",
        ],
        "comandos": "/avisos-privados",
    },
    "lideranca": {
        "titulo": "Liderança e staff",
        "descricao": "Boas práticas para operar os sistemas da NÊMESIS.",
        "passos": [
            "Use apenas comandos compatíveis com seu cargo e sua responsabilidade.",
            "Registre mudanças importantes, punições, decisões e correções com justificativa.",
            "Antes de editar um sistema, confira o estado atual no bot e no site.",
            "Evite conceder pontos, cargos ou prêmios manualmente sem registrar a operação.",
            "Em falhas, preserve IDs e logs, informe a equipe técnica e não repita a ação até confirmar se ela foi aplicada.",
        ],
        "comandos": "/help · /painel-provas · comandos administrativos liberados para seu cargo",
    },
}


def _embed_tutorial(chave: str) -> discord.Embed:
    tutorial = TUTORIAIS[chave]
    embed = discord.Embed(
        title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ TUTORIAL / {tutorial['titulo'].upper()}",
        description=tutorial["descricao"],
        color=0xB3132B,
    )
    embed.add_field(
        name="Como funciona",
        value="\n".join(f"**{i}.** {passo}" for i, passo in enumerate(tutorial["passos"], 1)),
        inline=False,
    )
    embed.add_field(name="Comandos e atalhos", value=tutorial["comandos"][:1024], inline=False)
    embed.set_footer(text="NÊMESIS • Tutorial interativo | Use o menu para trocar de assunto")
    return embed


class SeletorTutorial(discord.ui.Select):
    def __init__(self, autor_id: int, selecionado: str = "inicio"):
        self.autor_id = autor_id
        opcoes = [
            discord.SelectOption(
                label=conteudo["titulo"][:100],
                value=chave,
                description=conteudo["descricao"][:100],
                default=chave == selecionado,
            )
            for chave, conteudo in TUTORIAIS.items()
        ]
        super().__init__(placeholder="Escolha um sistema para aprender", options=opcoes, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("Este tutorial foi aberto por outro membro. Use /tutorial para abrir o seu.", ephemeral=True)
            return
        chave = self.values[0]
        view = TutorialView(self.autor_id, chave)
        await interaction.response.edit_message(embed=_embed_tutorial(chave), view=view)


class TutorialView(discord.ui.View):
    def __init__(self, autor_id: int, selecionado: str = "inicio"):
        super().__init__(timeout=300)
        self.add_item(SeletorTutorial(autor_id, selecionado))


class Tutorial(commands.Cog):
    """Central interativa de orientação dos sistemas da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="tutorial", description="Abre os tutoriais de missões, guerras, moderação e outros sistemas.")
    async def tutorial(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=_embed_tutorial("inicio"),
            view=TutorialView(interaction.user.id),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Tutorial(bot))
