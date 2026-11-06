import asyncio
import logging

import discord
from discord.ext import commands

from utils.apresentacao import criar_embed, COR_PRIMARIA

GUILD_NEMESIS_ID = 1563995879981981817
CANAL_REGRAS_ID = 1563995880833421508
COR = COR_PRIMARIA
MARCADOR_PUBLICACAO = "NÊMESIS • Código de Conduta oficial"

# Os códigos 01–08 são consumidos pelo AutoMod. Não renumerar sem
# atualizar também as referências de infração em cogs/automod.py.
SECOES_REGRAS = (
    (
        "# 1° CONDUTA E RESPEITO",
        "**1.1° Respeito mútuo** — Trate todos com respeito, independentemente de cargo, opinião ou tempo de servidor.\n\n"
        "**1.2° Ofensas e discriminação** — São proibidos insultos, humilhações, ameaças, discriminação e ataques pessoais.\n\n"
        "**1.3° Assédio e perseguição** — Não persiga, intimide ou constranja membros, nem incentive terceiros a fazê-lo.\n\n"
        "**1.4° Convivência** — Provocações e brincadeiras não justificam hostilidade. Interrompa quando alguém demonstrar desconforto.\n\n"
        "**1.5° Orientações** — Respeite orientações legítimas da Staff. Discordâncias devem ser apresentadas sem tumulto ou intimidação.",
    ),
    (
        "# 2° COMUNICAÇÃO E ORGANIZAÇÃO",
        "**2.1° Uso dos canais** — Utilize cada canal conforme sua finalidade e siga as orientações de organização.\n\n"
        "**2.2° Spam e flood** — São proibidos envios excessivos, mensagens repetidas e poluição deliberada dos canais.\n\n"
        "**2.3° Menções** — Não abuse de menções a membros, cargos ou @everyone/@here.\n\n"
        "**2.4° Tumulto e raids** — É proibido coordenar invasões, tumultos ou perturbações deliberadas.\n\n"
        "**2.5° Evasão** — Não contorne filtros, restrições ou medidas de moderação.",
    ),
    (
        "# 3° CONTEÚDO E SEGURANÇA DIGITAL",
        "**3.1° Conteúdo impróprio** — Não publique pornografia, conteúdo sexual explícito ou violência gráfica extrema.\n\n"
        "**3.2° Proteção de menores** — É absolutamente proibido conteúdo de exploração ou sexualização de menores.\n\n"
        "**3.3° Golpes e phishing** — Não divulgue fraudes, links maliciosos, falsos sorteios ou tentativas de roubo de contas.\n\n"
        "**3.4° Malware** — É proibido compartilhar arquivos maliciosos, executáveis suspeitos ou ferramentas destinadas a comprometer dispositivos.\n\n"
        "**3.5° Dano digital** — Não utilize a comunidade para facilitar invasões ou prejudicar sistemas e terceiros.",
    ),
    (
        "# 4° PRIVACIDADE E IDENTIDADE",
        "**4.1° Dados pessoais** — Não exponha endereço, telefone, IP, documentos ou outros dados pessoais sem autorização.\n\n"
        "**4.2° Doxxing** — É proibido ameaçar ou realizar exposição de dados para intimidar, constranger ou prejudicar alguém.\n\n"
        "**4.3° Credenciais** — Nunca solicite ou publique senhas, tokens ou códigos de autenticação.\n\n"
        "**4.4° Conversas privadas** — Não divulgue conversas, imagens ou informações privadas sem autorização, salvo encaminhamento legítimo de denúncia.\n\n"
        "**4.5° Falsidade de identidade** — Não se passe por membros, Staff ou bots oficiais para enganar ou obter vantagem.",
    ),
    (
        "# 5° DIVULGAÇÃO E PARCERIAS",
        "**5.1° Divulgação autorizada** — Publicidade somente nos canais e formatos permitidos.\n\n"
        "**5.2° Mensagens privadas** — É proibido enviar anúncios não solicitados por DM ou insistir em divulgação.\n\n"
        "**5.3° Convites e links** — Não espalhe convites fraudulentos, links enganosos ou falsos sorteios.\n\n"
        "**5.4° Parcerias** — Toda parceria depende de análise e aprovação pelos responsáveis autorizados, conforme os requisitos oficiais.\n\n"
        "**5.5° Uso da comunidade** — Não utilize a NÊMESIS para autopromoção irregular ou obtenção enganosa de benefícios.",
    ),
    (
        "# 6° ATENDIMENTO E DENÚNCIAS",
        "**6.1° Uso do atendimento** — Abra solicitações para assuntos pertinentes e selecione a categoria correta.\n\n"
        "**6.2° Informações verdadeiras** — Apresente contexto claro e evidências originais.\n\n"
        "**6.3° Abuso de tickets** — Não abra solicitações duplicadas, não pressione a equipe com cobranças insistentes e não utilize o atendimento para tumultuar.\n\n"
        "**6.4° Denúncias falsas** — É proibido fabricar, adulterar ou manipular provas para prejudicar alguém.\n\n"
        "**6.5° Discrição** — Evite acusações públicas e exposição desnecessária. Uma denúncia será analisada, mas não implica punição automática.",
    ),
    (
        "# 7° STAFF, HIERARQUIA E AUTORIDADE",
        "**7.1° Imparcialidade** — A Staff deve agir com respeito, neutralidade e responsabilidade.\n\n"
        "**7.2° Abuso de autoridade** — É proibido usar cargos ou permissões para perseguir, retaliar, favorecer ou obter vantagens indevidas.\n\n"
        "**7.3° Confidencialidade** — Informações internas e dados restritos não devem ser divulgados sem autorização.\n\n"
        "**7.4° Responsabilização** — Condutas inadequadas de integrantes da equipe poderão ser denunciadas e analisadas pela instância competente.\n\n"
        "**7.5° Estrutura** — O OCTÓGONO é a instância máxima. Supervisores Staff exercem atribuições administrativas conforme a estrutura e as permissões oficiais.",
    ),
    (
        "# 8° COMPETIÇÕES, MISSÕES E SISTEMAS",
        "**8.1° Regras específicas** — Respeite as normas de jogos, eventos, competições, missões e atividades oficiais.\n\n"
        "**8.2° Vantagem indevida** — São proibidos cheats, exploits, scripts vedados e manipulação de resultados.\n\n"
        "**8.3° Integridade** — Não falsifique provas, atividade ou participação, nem sabote operações e competições.\n\n"
        "**8.4° Progressão** — Respeite os critérios oficiais de XP, avaliação e progressão.\n\n"
        "**8.5° Medidas complementares** — Infrações podem gerar medidas disciplinares e consequências específicas na atividade ou competição.",
    ),
    (
        "# 9° REINCIDÊNCIA E AGRAVANTES",
        "**9.1° Reincidência** — Infrações repetidas dentro do período de análise podem elevar a medida disciplinar.\n\n"
        "**9.2° Evasão de punição** — Usar contas alternativas, retornar durante banimento ou contornar restrições agrava a ocorrência.\n\n"
        "**9.3° Retaliação** — Ameaçar denunciantes, testemunhas ou participantes de uma apuração é agravante.\n\n"
        "**9.4° Obstrução** — Ocultar evidências, intimidar envolvidos ou atrapalhar deliberadamente uma investigação pode agravar a medida.\n\n"
        "**9.5° Circunstâncias** — Gravidade, intenção, dano, contexto, provas e histórico serão considerados. Casos críticos podem exigir ação imediata.",
    ),
    (
        "# 10° NÍVEIS E MEDIDAS DISCIPLINARES",
        "**10.1° Nível I — Normal:** advertência formal.\n\n"
        "**10.2° Nível II — Médio:** timeout de 10 minutos como medida padrão.\n\n"
        "**10.3° Nível III — Grave:** expulsão do servidor.\n\n"
        "**10.4° Nível IV — Muito grave:** banimento temporário de 24 horas como medida padrão.\n\n"
        "**10.5° Nível V — Crítico:** banimento permanente.\n\n"
        "**10.6° Aplicação** — As medidas e durações podem ser personalizadas por configuração autorizada do AutoMod. A gravidade pode justificar uma medida imediata, sem passagem obrigatória por todos os níveis.\n\n"
        "**10.7° Reincidência automática** — No cálculo atual do AutoMod, 2 ou mais registros recentes podem elevar um nível; 4 ou mais podem elevar dois, limitado ao nível V.\n\n"
        "**10.8° Revisão** — O membro poderá solicitar revisão pelos canais oficiais, apresentando justificativa e informações pertinentes.",
    ),
    (
        "# 11° DISPOSIÇÕES FINAIS",
        "**11.1° Abrangência** — Este regulamento aplica-se a todos, independentemente de cargo ou tempo de participação.\n\n"
        "**11.2° Regras complementares** — Normas específicas de sistemas, missões e competições complementam este Código.\n\n"
        "**11.3° Casos omissos** — Situações não previstas serão avaliadas com proporcionalidade, considerando a segurança e a integridade da organização.\n\n"
        "**11.4° Atualizações** — Alterações serão comunicadas pelos canais oficiais.\n\n"
        "**11.5° Responsabilidade** — O desconhecimento das regras não elimina a responsabilidade pelo seu cumprimento.",
    ),
)


def construir_embed_regras() -> discord.Embed:
    """Monta o regulamento completo em uma única embed dentro dos limites do Discord."""
    embed = criar_embed(
        title="𓂀 NÊMESIS — CÓDIGO DE CONDUTA",
        description=(
            "Regulamento oficial da organização. Aplica-se a todos os integrantes, "
            "sem distinção de cargo. Leia as diretrizes e consulte a equipe pelos "
            "canais oficiais em caso de dúvida ou denúncia."
        ),
        color=COR,
    )
    for titulo, texto in SECOES_REGRAS:
        embed.add_field(name=titulo, value=texto, inline=False)
    embed.set_footer(
        text=f"{MARCADOR_PUBLICACAO} • Documento integral • 11 seções"
    )

    total = len(embed.title or "") + len(embed.description or "")
    total += sum(len(field.name) + len(field.value) for field in embed.fields)
    total += len(embed.footer.text or "")
    if len(embed.fields) > 25 or total > 6000:
        raise ValueError("O Código de Conduta excede os limites de uma única embed do Discord.")
    if any(len(field.name) > 256 or len(field.value) > 1024 for field in embed.fields):
        raise ValueError("Uma seção do Código de Conduta excede o limite de campos do Discord.")
    return embed


class RegrasOficiais(commands.Cog):
    """Mantém o Código de Conduta oficial em uma única embed no canal de regras."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sincronizacao_lock = asyncio.Lock()
        self._sincronizado = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._sincronizado:
            return
        async with self._sincronizacao_lock:
            if self._sincronizado:
                return
            self._sincronizado = await self.sincronizar_regras()

    async def sincronizar_regras(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            logging.warning("Código de Conduta: servidor oficial ainda não está disponível.")
            return False

        canal = guild.get_channel(CANAL_REGRAS_ID)
        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_REGRAS_ID)
            except discord.HTTPException:
                logging.exception("Código de Conduta: não foi possível localizar o canal oficial.")
                return False
        if not isinstance(canal, discord.TextChannel):
            logging.error("Código de Conduta: o canal configurado não é um canal de texto.")
            return False

        membro_bot = guild.me or (guild.get_member(self.bot.user.id) if self.bot.user else None)
        if membro_bot is None:
            logging.warning("Código de Conduta: não foi possível validar as permissões do bot.")
            return False
        permissoes = canal.permissions_for(membro_bot)
        if not (permissoes.view_channel and permissoes.read_message_history
                and permissoes.send_messages and permissoes.embed_links):
            logging.error(
                "Código de Conduta: faltam permissões no canal %s "
                "(visualizar, ler histórico, enviar mensagens e inserir links).",
                CANAL_REGRAS_ID,
            )
            return False

        embed = construir_embed_regras()
        existentes = []
        try:
            async for mensagem in canal.history(limit=200, oldest_first=False):
                if self.bot.user is None or mensagem.author.id != self.bot.user.id:
                    continue
                if any(
                    item.footer and (item.footer.text or "").startswith(MARCADOR_PUBLICACAO)
                    for item in mensagem.embeds
                ):
                    existentes.append(mensagem)
        except discord.HTTPException:
            logging.exception("Código de Conduta: falha ao consultar publicações anteriores.")
            return False

        if existentes:
            principal = existentes[0]
            try:
                await principal.edit(content=None, embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logging.exception("Código de Conduta: falha ao atualizar a publicação existente.")
                return False
            for duplicada in existentes[1:]:
                try:
                    await duplicada.delete()
                except discord.HTTPException:
                    logging.warning(
                        "Código de Conduta: não foi possível remover uma publicação duplicada do bot (message_id=%s).",
                        duplicada.id,
                    )
            logging.info(
                "Código de Conduta atualizado em uma única embed no canal %s; publicações antigas do bot consolidadas.",
                CANAL_REGRAS_ID,
            )
            return True

        try:
            await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logging.exception("Código de Conduta: falha ao publicar a embed oficial.")
            return False
        logging.info("Código de Conduta publicado em uma única embed no canal %s.", CANAL_REGRAS_ID)
        return True


async def setup(bot: commands.Bot):
    await bot.add_cog(RegrasOficiais(bot))
