import discord
from discord import app_commands
from discord.ext import commands

GUILD_NEMESIS_ID = 1563995879981981817
CANAL_REGRAS_ID = 1563995880833421508
COR = 0xB3132B

REGRAS = [
"""╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮
　　　　𝐍̷ — 𝐍Ê𝐌𝐄𝐒𝐈𝐒
　　　𝐂𝐎́𝐃𝐈𝐆𝐎 𝐃𝐄 𝐂𝐎𝐍𝐃𝐔𝐓𝐀
╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯

「 ✦ 」𝐏𝐑𝐄𝐀̂𝐌𝐁𝐔𝐋𝐎

A NÊMESIS é construída sobre princípios de respeito, lealdade, disciplina e responsabilidade. A permanência nesta comunidade exige comprometimento com seus valores e respeito às normas estabelecidas.

Este regulamento determina os padrões de conduta aplicáveis a todos os membros, independentemente de cargo, influência ou tempo de participação.""",
"""╭────────── ◈ ──────────╮
　　　𝐈 — 𝐂𝐎𝐍𝐃𝐔𝐓𝐀
╰────────── ◈ ──────────╯

▸ 01. Respeito mútuo
Mantenha uma postura respeitosa com todos os membros. Assédio, ameaças, perseguição, discriminação e humilhações não serão tolerados.

▸ 02. Comportamento
Provocações, brincadeiras e desentendimentos não justificam ofensas ou ataques pessoais. Preserve a ordem e evite conflitos desnecessários.

▸ 03. Convivência
É proibido incentivar hostilidade, organizar perseguições ou agir deliberadamente para prejudicar a experiência de outros membros.

▸ 04. Autoridade
Orientações legítimas da Staff devem ser respeitadas. Discordâncias devem ser apresentadas de maneira apropriada, sem tumulto ou intimidação.""",
"""╭────────── ◈ ──────────╮
　　𝐈𝐈 — 𝐂𝐎𝐌𝐔𝐍𝐈𝐂𝐀𝐂̧𝐀̃𝐎
╰────────── ◈ ──────────╯

▸ 01. Organização
Utilize os canais conforme suas respectivas finalidades e siga as orientações de organização do servidor.

▸ 02. Spam e menções
Flood, mensagens repetitivas, publicidade insistente e menções abusivas são proibidos.

▸ 03. Privacidade
Não divulgue dados pessoais de terceiros nem exponha conversas privadas sem autorização. Denúncias devem ser encaminhadas pelos meios apropriados.

▸ 04. Conteúdo externo
Links e arquivos suspeitos não devem ser compartilhados. A Staff poderá remover materiais que representem riscos à comunidade.""",
"""╭────────── ◈ ──────────╮
　　　𝐈𝐈𝐈 — 𝐂𝐎𝐍𝐓𝐄𝐔́𝐃𝐎
╰────────── ◈ ──────────╯

▸ 01. Conteúdo impróprio
É proibido compartilhar pornografia, conteúdo sexual explícito ou material incompatível com as regras da comunidade.

▸ 02. Proteção de menores
Qualquer conteúdo de exploração ou sexualização de menores é terminantemente proibido.

▸ 03. Segurança digital
Golpes, phishing, malware, arquivos maliciosos e tentativas de roubo de informações são infrações graves.

▸ 04. Integridade
É proibido utilizar a NÊMESIS para facilitar atividades ilícitas, contornar sistemas de segurança ou prejudicar deliberadamente terceiros.""",
"""╭────────── ◈ ──────────╮
　　　𝐈𝐕 — 𝐒𝐄𝐆𝐔𝐑𝐀𝐍𝐂̧𝐀
╰────────── ◈ ──────────╯

▸ 01. Credenciais
Nunca solicite ou compartilhe senhas, tokens, códigos de autenticação ou credenciais de terceiros.

▸ 02. Identidade
É proibido se passar por membros, integrantes da Staff ou bots oficiais com a intenção de enganar.

▸ 03. Doxxing e invasões
Expor dados pessoais, ameaçar fazê-lo ou tentar invadir contas e sistemas é expressamente proibido.

▸ 04. Proteção coletiva
Atividades suspeitas, tentativas de fraude e possíveis vulnerabilidades devem ser comunicadas à Staff pelos canais oficiais.""",
"""╭────────── ◈ ──────────╮
　　　𝐕 — 𝐃𝐈𝐕𝐔𝐋𝐆𝐀𝐂̧𝐀̃𝐎
╰────────── ◈ ──────────╯

▸ 01. Publicidade
Divulgações são permitidas somente nos canais e formatos autorizados.

▸ 02. Mensagens privadas
É proibido enviar publicidade não solicitada por DM ou utilizar membros como alvo de divulgação insistente.

▸ 03. Parcerias
Toda parceria deve seguir os requisitos e procedimentos oficiais da NÊMESIS.

▸ 04. Má-fé
Divulgação enganosa, convites fraudulentos e uso indevido da comunidade para autopromoção poderão resultar em punição.""",
"""╭────────── ◈ ──────────╮
　　　𝐕𝐈 — 𝐀𝐓𝐄𝐍𝐃𝐈𝐌𝐄𝐍𝐓𝐎
╰────────── ◈ ──────────╯

▸ 01. Abertura
Abra tickets somente quando necessário e selecione a categoria correspondente ao assunto.

▸ 02. Clareza
Apresente informações objetivas e verdadeiras. Quando necessário, forneça contexto e provas.

▸ 03. Responsabilidade
Não abra tickets duplicados nem pressione a Staff com cobranças ou menções repetitivas.

▸ 04. Encerramento
Tickets resolvidos, duplicados, abandonados ou utilizados indevidamente poderão ser encerrados.""",
"""╭────────── ◈ ──────────╮
　　　𝐕𝐈𝐈 — 𝐀𝐔𝐓𝐎𝐑𝐈𝐃𝐀𝐃𝐄
╰────────── ◈ ──────────╯

▸ 01. Dever da Staff
Integrantes da Staff devem agir com imparcialidade, discrição e responsabilidade.

▸ 02. Uso de permissões
Cargos e permissões não podem ser utilizados para perseguir membros, obter vantagens indevidas ou exercer autoridade de maneira abusiva.

▸ 03. Confidencialidade
Informações internas e dados restritos não devem ser divulgados sem autorização, ressalvadas comunicações legítimas de denúncia.

▸ 04. Revisão administrativa
Condutas inadequadas da Staff poderão ser denunciadas pelos meios oficiais e analisadas por responsáveis competentes.""",
"""╭────────── ◈ ──────────╮
　　　𝐕𝐈𝐈𝐈 — 𝐂𝐎𝐌𝐏𝐄𝐓𝐈𝐂̧𝐎̃𝐄𝐒
╰────────── ◈ ──────────╯

▸ 01. Regras
Respeite as regras específicas de cada jogo, evento, competição ou atividade oficial.

▸ 02. Vantagens indevidas
Cheats, exploits, scripts proibidos, fraudes e manipulação de resultados são vedados nas atividades abrangidas pelas regras aplicáveis.

▸ 03. Integridade competitiva
Sabotagem deliberada, fraude e condutas destinadas a comprometer uma competição poderão resultar em desclassificação e outras medidas disciplinares.""",
"""╭────────── ◈ ──────────╮
　　　𝐈𝐗 — 𝐃𝐄𝐍𝐔́𝐍𝐂𝐈𝐀𝐒
╰────────── ◈ ──────────╯

▸ 01. Procedimento
Encaminhe denúncias pelos canais oficiais, apresentando contexto, envolvidos e provas disponíveis.

▸ 02. Discrição
Evite acusações públicas e exposições desnecessárias. Casos sensíveis devem ser tratados em ambiente privado.

▸ 03. Veracidade
É proibido fabricar, adulterar ou manipular provas com a intenção de prejudicar alguém.

▸ 04. Análise
Cada denúncia será avaliada conforme as evidências disponíveis. A apresentação de uma denúncia não garante, por si só, uma punição.""",
"""╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮
　　　𝐗 — 𝐒𝐈𝐒𝐓𝐄𝐌𝐀 𝐃𝐈𝐒𝐂𝐈𝐏𝐋𝐈𝐍𝐀𝐑
╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯

A violação deste regulamento poderá resultar nas seguintes medidas:

«Ⅰ. Advertência formal
Ⅱ. Silenciamento temporário
Ⅲ. Restrição de acesso
Ⅳ. Remoção de cargos ou privilégios
Ⅴ. Suspensão de atividades
Ⅵ. Expulsão do servidor
Ⅶ. Banimento temporário
Ⅷ. Banimento permanente»

𝐂𝐑𝐈𝐓𝐄́𝐑𝐈𝐎𝐒 𝐃𝐄 𝐀𝐕𝐀𝐋𝐈𝐀𝐂̧𝐀̃𝐎

A medida disciplinar será definida considerando a gravidade da infração, o contexto, os danos causados e a reincidência. Infrações graves poderão justificar medidas imediatas.

Tentativas de evasão de punições, utilização de contas alternativas para contornar restrições ou incentivo à quebra das medidas aplicadas poderão agravar as consequências.

Quando cabível, o membro poderá solicitar uma revisão pelos canais oficiais.""",
"""╭────────── ◈ ──────────╮
　　　𝐗𝐈 — 𝐃𝐈𝐒𝐏𝐎𝐒𝐈𝐂̧𝐎̃𝐄𝐒
╰────────── ◈ ──────────╯

▸ 01. Obrigatoriedade
Todos os membros estão sujeitos a este regulamento, independentemente de cargo ou tempo de participação.

▸ 02. Atualizações
A administração poderá revisar as normas e publicar alterações pelos canais oficiais.

▸ 03. Casos omissos
Situações não previstas serão analisadas individualmente, considerando a segurança e a integridade da comunidade.

▸ 04. Responsabilidade
O desconhecimento das regras não elimina a responsabilidade pelo seu cumprimento."""
]


class RegrasOficiais(commands.Cog):
    """Publica o Código de Conduta padrão no canal oficial da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="regras-publicar",
        description="Publica o Código de Conduta oficial da NÊMESIS no canal de regras."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def regras_publicar(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None or guild.id != GUILD_NEMESIS_ID:
            await interaction.response.send_message(
                "Este comando está disponível somente no servidor oficial da NÊMESIS.",
                ephemeral=True,
            )
            return
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Somente administradores do servidor podem publicar o Código de Conduta.",
                ephemeral=True,
            )
            return

        canal = guild.get_channel(CANAL_REGRAS_ID)
        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_REGRAS_ID)
            except discord.HTTPException:
                canal = None
        if not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message(
                f"Não encontrei o canal de regras configurado (<#{CANAL_REGRAS_ID}>). Nenhuma mensagem foi publicada.",
                ephemeral=True,
            )
            return

        permissoes = canal.permissions_for(guild.me)
        if not (permissoes.send_messages and permissoes.embed_links):
            await interaction.response.send_message(
                "Preciso das permissões **Enviar mensagens** e **Inserir links** no canal de regras.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Publicando o Código de Conduta em {canal.mention}. As mensagens anteriores não serão apagadas.",
            ephemeral=True,
        )
        enviados = 0
        try:
            for indice, texto in enumerate(REGRAS, start=1):
                embed = discord.Embed(
                    description=texto,
                    color=COR,
                )
                embed.set_footer(text=f"NÊMESIS • Código de Conduta oficial • Parte {indice}/{len(REGRAS)}")
                await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
                enviados += 1
        except discord.HTTPException:
            await interaction.followup.send(
                f"Publicação interrompida após {enviados}/{len(REGRAS)} partes. Confira as permissões e execute o comando novamente após corrigir.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"**Código de Conduta publicado:** {enviados} partes em {canal.mention}. Não apaguei mensagens antigas.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(RegrasOficiais(bot))
