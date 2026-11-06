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
        "01. CONDUTA E RESPEITO",
        "Trate todos com respeito. São proibidos assédio, perseguição, humilhação, ameaças, discriminação, ataques pessoais e incentivo à hostilidade. Brincadeiras não justificam insistência após pedido para parar. Respeite orientações legítimas da Staff; discordâncias devem ser tratadas pelos meios apropriados.",
    ),
    (
        "02. COMUNICAÇÃO E ORGANIZAÇÃO",
        "Use cada canal conforme sua finalidade. São proibidos spam, flood, repetição excessiva, menções abusivas, raids, provocações coordenadas, evasão de filtros e perturbação deliberada. Publicidade só é permitida nos espaços e formatos autorizados. Não contorne restrições aplicadas pela equipe.",
    ),
    (
        "03. CONTEÚDO E SEGURANÇA DIGITAL",
        "Não publique pornografia, conteúdo sexual explícito, violência gráfica extrema, exploração ou sexualização de menores, golpes, phishing, malware, arquivos maliciosos ou instruções destinadas a causar dano. Conteúdos perigosos poderão ser removidos e encaminhados à análise. A proteção de menores é inegociável.",
    ),
    (
        "04. PRIVACIDADE E IDENTIDADE",
        "É proibido expor dados pessoais, IP, endereço, telefone, credenciais, tokens ou conversas privadas sem autorização; ameaçar doxxing; solicitar senhas ou códigos; tentar invadir contas; ou falsificar a identidade de membros, Staff ou bots. Nunca compartilhe credenciais. Comunique riscos pelos canais oficiais.",
    ),
    (
        "05. DIVULGAÇÃO E PARCERIAS",
        "Divulgação só nos canais e formatos autorizados. São proibidos anúncios por DM sem consentimento, spam de convites, links fraudulentos, falsos sorteios e promessas enganosas. Toda parceria depende de análise e aprovação pelos responsáveis autorizados e deve seguir os requisitos oficiais da NÊMESIS.",
    ),
    (
        "06. ATENDIMENTO E DENÚNCIAS",
        "Use o atendimento para assuntos pertinentes e apresente informações verdadeiras, contexto e evidências originais. São proibidos tickets duplicados ou abusivos, cobranças insistentes, denúncias deliberadamente falsas, provas fabricadas ou adulteradas e exposição pública desnecessária. Uma denúncia será analisada; não implica punição automática.",
    ),
    (
        "07. STAFF, HIERARQUIA E AUTORIDADE",
        "A Staff deve agir com imparcialidade, discrição e responsabilidade. É proibido abusar de cargos ou permissões, perseguir, retaliar, favorecer pessoas ou divulgar informações restritas. Denúncias contra integrantes da equipe serão encaminhadas à instância competente. O OCTÓGONO é a instância máxima; Supervisores Staff exercem atribuições administrativas conforme a estrutura e as permissões oficiais.",
    ),
    (
        "08. COMPETIÇÕES, MISSÕES E SISTEMAS",
        "Respeite as regras específicas de jogos, competições, eventos e missões. São proibidos cheats, exploits, manipulação de resultados, fraude em provas, sabotagem, falsificação de atividade e obtenção de vantagem indevida. Os critérios oficiais de XP e progressão devem ser respeitados. Medidas competitivas podem ser aplicadas além das disciplinares.",
    ),
    (
        "09. REINCIDÊNCIA E EVASÃO",
        "A reincidência dentro do período de análise poderá elevar a medida disciplinar. É agravante usar contas alternativas para escapar de sanções, retornar durante banimento, incentivar a evasão, retaliar denunciantes ou obstruir apurações. A gravidade pode justificar uma medida imediata, sem exigir passagem por todos os níveis.",
    ),
    (
        "10. NÍVEIS E MEDIDAS DISCIPLINARES",
        "**NÍVEL I — NORMAL:** advertência formal.\n**NÍVEL II — MÉDIO:** timeout de 10 minutos (padrão).\n**NÍVEL III — GRAVE:** expulsão do servidor.\n**NÍVEL IV — MUITO GRAVE:** banimento temporário de 24 horas (padrão).\n**NÍVEL V — CRÍTICO:** banimento permanente.\n\nAs durações e medidas padrão podem ser alteradas pela configuração autorizada do AutoMod. A equipe considera gravidade, contexto, intenção, dano, provas e histórico. No cálculo atual de reincidência do AutoMod, 2 ou mais registros recentes podem elevar um nível; 4 ou mais podem elevar dois, limitado ao nível V. Casos críticos podem receber ação imediata. Decisões podem ser contestadas pelos canais oficiais.",
    ),
    (
        "11. DISPOSIÇÕES FINAIS",
        "Este regulamento vale para todos, independentemente de cargo ou tempo de participação. As regras específicas de sistemas e competições complementam este Código. Casos omissos serão avaliados com proporcionalidade e foco na segurança da organização. Atualizações serão comunicadas nos canais oficiais. O desconhecimento das regras não afasta a responsabilidade pelo seu cumprimento.",
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
            await self.sincronizar_regras()
            self._sincronizado = True

    async def sincronizar_regras(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            logging.warning("Código de Conduta: servidor oficial ainda não está disponível.")
            return

        canal = guild.get_channel(CANAL_REGRAS_ID)
        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_REGRAS_ID)
            except discord.HTTPException:
                logging.exception("Código de Conduta: não foi possível localizar o canal oficial.")
                return
        if not isinstance(canal, discord.TextChannel):
            logging.error("Código de Conduta: o canal configurado não é um canal de texto.")
            return

        membro_bot = guild.me or (guild.get_member(self.bot.user.id) if self.bot.user else None)
        if membro_bot is None:
            logging.warning("Código de Conduta: não foi possível validar as permissões do bot.")
            return
        permissoes = canal.permissions_for(membro_bot)
        if not (permissoes.view_channel and permissoes.read_message_history
                and permissoes.send_messages and permissoes.embed_links):
            logging.error(
                "Código de Conduta: faltam permissões no canal %s "
                "(visualizar, ler histórico, enviar mensagens e inserir links).",
                CANAL_REGRAS_ID,
            )
            return

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
            return

        if existentes:
            principal = existentes[0]
            try:
                await principal.edit(content=None, embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logging.exception("Código de Conduta: falha ao atualizar a publicação existente.")
                return
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
            return

        try:
            await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logging.exception("Código de Conduta: falha ao publicar a embed oficial.")
            return
        logging.info("Código de Conduta publicado em uma única embed no canal %s.", CANAL_REGRAS_ID)


async def setup(bot: commands.Bot):
    await bot.add_cog(RegrasOficiais(bot))
