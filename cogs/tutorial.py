import logging
import os

import discord
from discord.ext import commands

from utils.apresentacao import criar_embed, aplicar_identidade_servidor, COR_PRIMARIA
from utils.storage import carregar, salvar

logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
CANAL_TUTORIAIS_ID = 1563995880833421512
ARQUIVO_CENTRAL_TUTORIAIS = "central_tutoriais.json"
MARCADOR_CENTRAL_TUTORIAIS = "NÊMESIS • CENTRAL DE TUTORIAIS • V4"


TUTORIAIS = {
    "dados_atividade": {
        "titulo": "Dados e histórico de atividade",
        "descricao": "Entenda quais dados de atividade são registrados para segurança e moderação.",
        "passos": [
            "O Shinku registra mensagens enviadas nos canais e tópicos da NÊMESIS que o bot consegue acessar, incluindo o conteúdo atual, edições e exclusões.",
            "O histórico de mensagens mantém até 500 mensagens por membro, por no máximo 30 dias. São preservadas até duas versões anteriores de uma mensagem editada.",
            "O monitoramento também registra eventos do servidor, como entrada e saída, mudanças de apelido, timeout, banimento e movimentações em canais de voz.",
            "A consulta individual é privada e restrita à liderança autorizada. Os dados são usados para segurança, auditoria e moderação da comunidade.",
            "O bot não registra mensagens privadas (DMs), atividade em outros aplicativos ou o que acontece fora dos canais que ele pode acessar.",
            "O monitoramento começa após a implantação. Mensagens antigas, especialmente as já excluídas antes da ativação, não podem ser recuperadas pelo Discord.",
            "O evento de exclusão do Discord não informa com segurança quem apagou a mensagem; o registro confirma a exclusão, não identifica automaticamente o autor da ação.",
        ],
        "comandos": "Arquivo de Membros • Consulta privada pela liderança autorizada",
    },
    "musica": {
        "titulo": "Sistema de música",
        "descricao": "Como colocar o bot em call e controlar a reprodução.",
        "passos": [
            "Entre primeiro no canal de voz em que quer ouvir música.",
            "No Discord, use /play e informe o nome da música ou um link compatível do YouTube ou SoundCloud.",
            "O bot entra automaticamente no seu canal de voz e começa a tocar; você precisa estar conectado a um canal de voz.",
            "Use /queue para ver a fila e /nowplaying para conferir a música atual.",
            "Use /pause para pausar, /resume para continuar, /skip para pular e /volume para ajustar o volume entre 1 e 100.",
            "Use /stop para encerrar a reprodução, limpar a fila e desconectar o bot da call.",
            "Se o bot não entrar, confirme que ele tem as permissões Conectar, Falar e Ver canal; a hospedagem também precisa ter as dependências de voz instaladas.",
        ],
        "comandos": "/play · /queue · /nowplaying · /pause · /resume · /skip · /volume · /stop",
    },
    "inicio": {
        "titulo": "Começando na NÊMESIS",
        "descricao": "Guia de integração para novos integrantes: identidade, cargo inicial, canais e primeiros passos.",
        "passos": [
            "Ao entrar no servidor, o Shinku atribui automaticamente o cargo Visitantes. Se ele não aparecer, aguarde alguns segundos e procure a equipe pelo canal de Atendimento.",
            "A TAG oficial da organização é NΞM. Ela identifica a NÊMESIS e deve ser preservada conforme as orientações da liderança.",
            "Leia o canal Regras (categoria Informações) e acompanhe os comunicados em Anúncios antes de participar das atividades.",
            "Abra Como funciona para entender a proposta da organização e Divisões para conhecer a estrutura das equipes.",
            "Consulte #Sistemas: o painel Central de Tutoriais possui um seletor para abrir o guia de cada sistema sem precisar de comando.",
            "Use Inscrições para conhecer os formulários disponíveis e Missões para consultar atividades e requisitos.",
            "Acompanhe Progressão e Ranking para entender sua evolução. As recompensas e estatísticas seguem os critérios oficiais de cada sistema.",
            "Use /help para localizar apenas os comandos disponíveis ao seu cargo. Não possuir um comando significa que ele pode ser restrito a outra função.",
            "Se precisar de suporte, abra um atendimento pelo canal oficial. Nunca compartilhe senhas, tokens ou códigos de autenticação.",
        ],
        "comandos": "#Sistemas · #Regras · #Como-funciona · #Divisões · /help · /perfil",
    },
    "missoes": {
        "titulo": "Missões e Contribuições",
        "descricao": "Como consultar atividades, enviar evidências e receber XP após validação.",
        "passos": [
            "Abra o canal 𝖬𝗂𝗌𝗌𝗈̃𝖾𝗌 e consulte a Central de Operações. Use o seletor para alternar entre Missões, Contribuições e Operações especiais.",
            "Leia o objetivo, os requisitos, a dificuldade, o prazo e a recompensa em XP antes de iniciar.",
            "Conclua a atividade e clique em Enviar evidência no painel da categoria correspondente.",
            "No menu privado, selecione a atividade pelo título. Não é necessário copiar ou digitar o código.",
            "Informe o link da imagem hospedada no Discord. Se houver um auxiliar elegível, informe a menção ou o ID dele.",
            "Aguarde a análise do OCTÓGONO. O envio fica pendente e não concede XP imediatamente.",
            "Após aprovação, o XP é registrado no perfil e nos sistemas de progressão aplicáveis. O histórico evita créditos duplicados.",
            "Se a prova for recusada, leia o motivo enviado pela equipe, corrija a evidência e faça um novo envio quando permitido.",
        ],
        "comandos": "Central de Operações no canal 𝖬𝗂𝗌𝗌𝗈̃𝖾𝗌 · /perfil · /painel-provas (staff)",
    },
    "contribuicoes": {
        "titulo": "Contribuições",
        "descricao": "Atividades que ajudam a manter e desenvolver a NÊMESIS.",
        "passos": [
            "Confira no canal oficial quais ações são aceitas como contribuição.",
            "Leia a recompensa em XP, os limites e os requisitos antes de participar.",
            "Guarde a prova e envie pelo fluxo oficial quando a atividade exigir validação.",
            "Aguarde a aprovação do OCTÓGONO antes de considerar o XP confirmado.",
            "Não repita envios para tentar multiplicar pontos; em caso de divergência, abra um ticket.",
        ],
        "comandos": "Central de Tutoriais no canal #Sistemas · /perfil · /painel-provas (staff)",
    },
    "especiais": {
        "titulo": "Missões especiais",
        "descricao": "Atividades especiais com requisitos e validação próprios.",
        "passos": [
            "Leia o anúncio completo: missões especiais podem ter regras diferentes das comuns.",
            "Confirme prazo, elegibilidade, prova exigida e recompensa.",
            "Execute a atividade sem alterar ou recortar a prova de forma que esconda informações relevantes.",
            "Envie a prova pelo fluxo indicado e aguarde a decisão da staff.",
            "Se a missão estiver encerrada, não envie uma nova prova sem autorização.",
        ],
        "comandos": "/help · /painel-provas (staff)",
    },
    "pvp": {
        "titulo": "PvP e Desafios",
        "descricao": "Fluxo recomendado para duelos e resultados competitivos.",
        "passos": [
            "Combine o formato, as regras e o horário com o adversário antes da luta.",
            "Use os comandos de desafio disponíveis em /help para registrar o confronto.",
            "Guarde uma prova legível do resultado e envie-a pelo fluxo oficial.",
            "Se houver divergência, solicite revisão em vez de criar registros duplicados.",
            "Confira XP, vitórias e derrotas no perfil depois da confirmação.",
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
            "O OCTÓGONO decide provas de missões, contribuições, operações especiais e PvE; a liderança administrativa decide revisões competitivas.",
            "Se a aplicação da recompensa falhar, consulte os logs e reavalie a pendência; não conceda recompensa manualmente sem verificar o estado.",
            "Registre a decisão e o motivo de rejeição de forma objetiva.",
        ],
        "comandos": "/painel-provas · /help",
    },
    "perfil": {
        "titulo": "Perfil, XP e estatísticas",
        "descricao": "Como acompanhar seu desenvolvimento dentro da gangue.",
        "passos": [
            "Use /perfil para consultar XP de progressão, XP competitivo, patente, vitórias, derrotas, sequência e medalhas.",
            "Use os rankings disponíveis em /help para comparar resultados.",
            "O XP e as estatísticas exibidas seguem os critérios oficiais de cada sistema.",
            "O registro é salvo pelo bot; se houver divergência, abra um ticket com a prova e os detalhes do registro.",
            "Inclua o nome do sistema, o valor esperado e o momento aproximado da ocorrência para facilitar a conferência.",
        ],
        "comandos": "/perfil · /ranking-jogadores · /help",
    },
    "progressao": {
        "titulo": "Progressão e XP",
        "descricao": "Como evoluir nos ranks oficiais da NÊMESIS.",
        "passos": [
            "O XP de progressão da gangue é separado do XP competitivo; cada sistema mantém seu próprio histórico.",
            "Mensagens válidas concedem XP com intervalo de segurança entre registros. Spam não acelera a progressão.",
            "Missões são validadas pelo OCTÓGONO; contribuições e guerras seguem os fluxos oficiais de cada sistema.",
            "Os ranks vão de Lutador a Capitão Geral e são calculados pelos limiares oficiais de XP.",
            "Promoções e rebaixamentos manuais exigem justificativa, registro e autorização de cargo acima de Elite.",
            "Use /perfil para acompanhar sua evolução. Em caso de divergência, abra um ticket com o horário e o sistema envolvido.",
        ],
        "comandos": "/perfil · /help",
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
        "comandos": "/roblox-vincular · /roblox-confirmar · /roblox-perfil · /roblox-identificar · /roblox-desvincular",
    },
    "moderacao": {
        "titulo": "Proteção automática e conduta",
        "descricao": "Como o AutoMod protege a comunidade e como agir diante de uma infração.",
        "passos": [
            "Aplique as regras de forma consistente e sem favorecimento.",
            "Antes de punir, verifique contexto, evidências e histórico quando disponível.",
            "Registre um motivo claro e proporcional à infração.",
            "O AutoMod aplica automaticamente as medidas configuradas conforme as regras e a gravidade identificada.",
            "O AutoMod aplica medidas automáticas. Banimentos manuais usam /banir, exigem cargo acima de Elite, motivo e alvo abaixo da autoridade de quem executa.",
            "Em caso de falso positivo, reincidência ou situação excepcional, encaminhe as evidências à liderança para revisão da configuração. Não tente contornar o AutoMod.",
        ],
        "comandos": "AutoMod · /banir (cargos autorizados) · /help · /punicoes-historico (consulta autorizada)",
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
    "aliancas": {
        "titulo": "Alianças entre gangues",
        "descricao": "Como propor, avaliar e manter uma aliança oficial.",
        "passos": [
            "Use o formulário ou canal oficial indicado pela liderança para apresentar a proposta.",
            "Informe o nome da gangue, representante, objetivo da aliança e contato oficial.",
            "Aguarde a avaliação da liderança; enviar uma proposta não significa aprovação.",
            "Defina regras de cooperação, comunicação, eventos e resolução de conflitos antes de anunciar a aliança.",
            "Não fale em nome da NÊMESIS nem prometa apoio sem autorização da liderança.",
        ],
        "comandos": "Central de Tutoriais no canal #Sistemas · formulário oficial de aliança",
    },
    "gangues": {
        "titulo": "Organização da gangue",
        "descricao": "Estrutura, cargos, equipes e responsabilidades.",
        "passos": [
            "Respeite a hierarquia e encaminhe decisões ao responsável correto.",
            "Use os canais específicos para suporte, recrutamento, operações e anúncios.",
            "Cargos representam responsabilidades; não use permissões para benefício pessoal.",
            "A gestão de missões é exclusiva do OCTÓGONO. Promoções, rebaixamentos e banimentos são restritos aos cargos acima de Elite, sempre respeitando a posição hierárquica do alvo.",
            "Dúvidas sobre regras internas devem ser resolvidas nos canais oficiais, não por boatos.",
        ],
        "comandos": "/help · painel de atendimento",
    },
    "temporadas": {
        "titulo": "Temporadas competitivas",
        "descricao": "Como funciona a classificação por temporada.",
        "passos": [
            "Acompanhe o número da temporada e as datas publicadas pela staff.",
            "Consulte sua posição e seus resultados pelo /perfil e pelos rankings disponíveis.",
            "Só resultados válidos e aprovados devem contar para a classificação.",
            "No encerramento, a equipe publica o resultado e eventuais recompensas.",
            "Se houver divergência no resultado, envie o ID do registro em um ticket.",
        ],
        "comandos": "/perfil · /ranking-jogadores · /help",
    },
    "recordes": {
        "titulo": "Recordes e conquistas",
        "descricao": "Como registrar um recorde verificável.",
        "passos": [
            "Consulte as regras e o formato de prova exigido para aquele recorde.",
            "Inclua uma captura legível e contexto suficiente para validar o resultado.",
            "Não edite a imagem de modo a alterar o placar, a data ou a identidade.",
            "Aguarde a revisão antes de divulgar o recorde como oficial.",
            "Peça correção com o link do registro se notar erro no nome ou no resultado.",
        ],
        "comandos": "/help · painel oficial de recordes",
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
    "academia": {
        "titulo": "Academia e treinamentos",
        "descricao": "Como consultar treinamentos, se inscrever e acompanhar avaliações.",
        "passos": [
            "Use /academia listar para consultar os treinamentos abertos, objetivos, horários e vagas.",
            "Copie o código do treinamento desejado e use /academia inscrever para registrar sua participação.",
            "Acompanhe a data e as orientações informadas na descrição do treinamento.",
            "Depois da atividade, a liderança registra o resultado como aprovado, reprovado ou ausente, com uma observação quando necessário.",
            "Use /academia meu-historico para consultar seus treinamentos e resultados. A liderança também pode consultar o histórico individual.",
            "A inscrição não confirma presença física. O resultado depende da avaliação registrada pela equipe.",
            "A Academia registra avaliações, mas não concede XP automaticamente. Recompensas dependem de critérios oficiais definidos pela organização.",
        ],
        "comandos": "/academia listar · /academia inscrever · /academia meu-historico",
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
        "titulo": "Avisos oficiais por mensagem privada",
        "descricao": "Comunicados oficiais ficam nos canais; DMs podem ser desativadas individualmente pelo membro.",
        "passos": [
            "As notas de atualização automáticas são entregues por DM aos membros inscritos que mantêm a preferência ativa.",
            "O comando /notas-atualizacao é uma prévia somente leitura para a liderança; ele não envia mensagens.",
            "Na DM de boas-vindas ou nos comunicados privados, use o botão de preferências para desativar ou reativar mensagens privadas.",
            "As configurações de privacidade do Discord podem bloquear a entrega de uma DM; o bot registra falhas permanentes e resultados incertos sem repetir automaticamente uma entrega possivelmente concluída.",
        ],
        "comandos": "As preferências de DM são controladas pelo botão nas mensagens automáticas.",
    },
    "lideranca": {
        "titulo": "Liderança e staff",
        "descricao": "Boas práticas para operar os sistemas da NÊMESIS.",
        "passos": [
            "Use apenas comandos compatíveis com seu cargo e sua responsabilidade.",
            "Registre mudanças importantes, punições, decisões e correções com justificativa.",
            "Antes de editar um sistema, confira o estado atual no bot e nos registros oficiais.",
            "Evite conceder pontos, cargos ou prêmios manualmente sem registrar a operação.",
            "Em falhas, preserve IDs e logs, informe a equipe técnica e não repita a ação até confirmar se ela foi aplicada.",
        ],
        "comandos": "/help · /painel-provas · comandos administrativos liberados para seu cargo",
    },
}


def _embed_indice(guild: discord.Guild | None = None, bot: commands.Bot | None = None) -> discord.Embed:
    """Capa enxuta: o conteúdo didático só aparece após escolher um guia."""
    quebra = chr(10)
    embed = criar_embed(
        title="✦・ NÊMESIS — TUTORIAIS ・✦",
        description=(
            "**Central de orientação da NÊMESIS.**" + quebra
            + "Escolha um assunto no seletor abaixo para abrir o guia correspondente."
            + quebra * 2
            + "A consulta é privada e não altera esta mensagem."
        ),
        color=COR_PRIMARIA,
    )
    embed.add_field(
        name="COMO USAR",
        value="1. Selecione o sistema." + quebra
        + "2. Leia o passo a passo exibido." + quebra
        + "3. Use os canais oficiais indicados no guia.",
        inline=False,
    )
    embed.set_footer(text=MARCADOR_CENTRAL_TUTORIAIS)
    if guild is not None:
        aplicar_identidade_servidor(embed, guild, bot)
    return embed

def _embed_tutorial(chave: str, guild: discord.Guild | None = None, bot: commands.Bot | None = None) -> discord.Embed:
    tutorial = TUTORIAIS[chave]
    embed = criar_embed(
        title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ GUIA / {tutorial['titulo'].upper()}",
        description=f"⟡・{tutorial['descricao']}\n\nSiga as orientações abaixo e utilize somente os fluxos oficiais.",
        color=COR_PRIMARIA,
    )
    blocos = []
    atual = []
    tamanho = 0
    for numero, passo in enumerate(tutorial["passos"], 1):
        linha = f"**{numero:02d}.** {passo}"
        if atual and tamanho + len(linha) + 1 > 1000:
            blocos.append("\n".join(atual))
            atual = []
            tamanho = 0
        atual.append(linha)
        tamanho += len(linha) + 1
    if atual:
        blocos.append("\n".join(atual))
    for indice, bloco in enumerate(blocos, 1):
        nome = "◈ PASSO A PASSO" if indice == 1 else f"◈ CONTINUAÇÃO {indice:02d}"
        embed.add_field(name=nome, value=bloco, inline=False)
    embed.add_field(
        name="◈ COMANDOS E ATALHOS",
        value=str(tutorial.get("comandos") or "Consulte os canais oficiais e a central /help.")[:1024],
        inline=False,
    )
    embed.set_footer(text="NÊMESIS • Biblioteca oficial • Consulte o menu para trocar de guia")
    if guild is not None:
        aplicar_identidade_servidor(embed, guild, bot)
    return embed


class SeletorTutorialPublico(discord.ui.Select):
    def __init__(self):
        opcoes = [
            discord.SelectOption(
                label=dados["titulo"][:100],
                value=chave,
                description=dados["descricao"][:100],
            )
            for chave, dados in TUTORIAIS.items()
        ]
        super().__init__(
            placeholder="Selecione um tutorial para consultar",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="nemesis:tutoriais:publico",
        )

    async def callback(self, interaction: discord.Interaction):
        chave = self.values[0]
        await interaction.response.send_message(
            embed=_embed_tutorial(chave, interaction.guild, interaction.client),
            view=TutorialDetalheView(interaction.user.id, chave),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class TutorialPainelView(discord.ui.View):
    """View persistente do painel público de tutoriais."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SeletorTutorialPublico())


class SeletorTutorialDetalhe(discord.ui.Select):
    def __init__(self, autor_id: int, selecionado: str):
        self.autor_id = autor_id
        opcoes = [
            discord.SelectOption(
                label=dados["titulo"][:100],
                value=chave,
                description=dados["descricao"][:100],
                default=chave == selecionado,
            )
            for chave, dados in TUTORIAIS.items()
        ]
        super().__init__(
            placeholder="Trocar de tutorial",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id=f"nemesis:tutoriais:detalhe:{autor_id}",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message(
                "Este guia foi aberto por outra pessoa. Selecione um assunto no painel público de #Sistemas.",
                ephemeral=True,
            )
            return
        chave = self.values[0]
        await interaction.response.edit_message(
            embed=_embed_tutorial(chave, interaction.guild, interaction.client),
            view=TutorialDetalheView(self.autor_id, chave),
        )


class TutorialDetalheView(discord.ui.View):
    def __init__(self, autor_id: int, selecionado: str):
        super().__init__(timeout=900)
        self.autor_id = autor_id
        self.add_item(SeletorTutorialDetalhe(autor_id, selecionado))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message(
                "Este guia foi aberto por outra pessoa. Abra sua própria consulta pelo painel #Sistemas.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Voltar ao índice", style=discord.ButtonStyle.secondary, emoji="📚", row=1)
    async def voltar_indice(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_embed_indice(interaction.guild, interaction.client),
            view=TutorialDetalheIndiceView(self.autor_id),
        )


class SeletorTutorialIndice(discord.ui.Select):
    def __init__(self, autor_id: int):
        self.autor_id = autor_id
        opcoes = [
            discord.SelectOption(
                label=dados["titulo"][:100],
                value=chave,
                description=dados["descricao"][:100],
            )
            for chave, dados in TUTORIAIS.items()
        ]
        super().__init__(
            placeholder="Selecione outro tutorial",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id=f"nemesis:tutoriais:indice:{autor_id}",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("Esta consulta pertence a outra pessoa.", ephemeral=True)
            return
        chave = self.values[0]
        await interaction.response.edit_message(
            embed=_embed_tutorial(chave, interaction.guild, interaction.client),
            view=TutorialDetalheView(self.autor_id, chave),
        )


class TutorialDetalheIndiceView(discord.ui.View):
    def __init__(self, autor_id: int):
        super().__init__(timeout=900)
        self.autor_id = autor_id
        self.add_item(SeletorTutorialIndice(autor_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("Esta consulta pertence a outra pessoa.", ephemeral=True)
            return False
        return True

class Tutorial(commands.Cog):
    """Mantém a central pública e persistente de tutoriais da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._publicando = False
        self._view_registrada = False

    async def cog_load(self):
        if not self._view_registrada:
            self.bot.add_view(TutorialPainelView())
            self._view_registrada = True

    @commands.Cog.listener()
    async def on_ready(self):
        if self._publicando:
            return
        self._publicando = True
        try:
            guild = self.bot.get_guild(GUILD_NEMESIS_ID)
            if guild is None:
                logger.warning("Servidor da NÊMESIS ainda não está disponível para publicar a central de tutoriais.")
                return
            canal = guild.get_channel(CANAL_TUTORIAIS_ID)
            if canal is None:
                canal = await self.bot.fetch_channel(CANAL_TUTORIAIS_ID)
            if not isinstance(canal, discord.TextChannel) or canal.guild.id != GUILD_NEMESIS_ID:
                logger.error("Canal de tutoriais inválido; esperado o canal #Sistemas da NÊMESIS.")
                return
            permissoes = canal.permissions_for(guild.me)
            if not (permissoes.view_channel and permissoes.send_messages and permissoes.embed_links and permissoes.read_message_history):
                logger.error("Sem permissões para manter a central de tutoriais no canal #Sistemas.")
                return

            estado = await carregar(
                ARQUIVO_CENTRAL_TUTORIAIS,
                {"guild_id": GUILD_NEMESIS_ID, "message_id": None},
            )
            mensagem = None
            message_id = estado.get("message_id") if isinstance(estado, dict) else None
            if message_id:
                try:
                    mensagem = await canal.fetch_message(int(message_id))
                except discord.NotFound:
                    mensagem = None
                except (discord.Forbidden, discord.HTTPException):
                    logger.exception("Não foi possível recuperar a mensagem salva da central de tutoriais.")
                    return

            async for antiga in canal.history(limit=200):
                if antiga.author.id != self.bot.user.id:
                    continue
                if mensagem is not None and antiga.id == mensagem.id:
                    continue
                legado = any(
                    embed.footer and embed.footer.text.startswith("NÊMESIS • GUIA OFICIAL •")
                    for embed in antiga.embeds
                )
                if legado:
                    try:
                        await antiga.delete()
                        logger.info("Guia antigo removido do canal #Sistemas (message=%s).", antiga.id)
                    except discord.HTTPException:
                        logger.exception("Não foi possível remover um guia antigo (message=%s).", antiga.id)
                if mensagem is None and any(
                    embed.footer and embed.footer.text == MARCADOR_CENTRAL_TUTORIAIS
                    for embed in antiga.embeds
                ):
                    mensagem = antiga

            embed = _embed_indice(guild, self.bot)
            if mensagem is None:
                mensagem = await canal.send(
                    embed=embed,
                    view=TutorialPainelView(),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                logger.info("Central pública de tutoriais publicada em #Sistemas (message=%s).", mensagem.id)
            else:
                await mensagem.edit(
                    embed=embed,
                    view=TutorialPainelView(),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                logger.info("Central pública de tutoriais atualizada em #Sistemas (message=%s).", mensagem.id)

            await salvar(
                ARQUIVO_CENTRAL_TUTORIAIS,
                {"guild_id": GUILD_NEMESIS_ID, "message_id": mensagem.id},
            )
        except discord.Forbidden:
            logger.exception("O bot não tem permissão para publicar a central de tutoriais.")
        except discord.HTTPException:
            logger.exception("Falha de API ao manter a central de tutoriais.")
        except Exception:
            logger.exception("Erro inesperado ao manter a central de tutoriais.")
        finally:
            self._publicando = False


async def setup(bot: commands.Bot):
    await bot.add_cog(Tutorial(bot))
