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
        "**1.1° Respeito** — Trate todos com dignidade, sem ataques por cargo, opinião ou tempo de servidor.\n\n"
        "**1.2° Ofensas** — São proibidos insultos, ameaças, humilhação e discriminação.\n\n"
        "**1.3° Assédio** — Não persiga, intimide ou constranja membros, nem incentive terceiros.\n\n"
        "**1.4° Convivência** — Interrompa brincadeiras quando causarem desconforto.\n\n"
        "**1.5° Orientações** — Cumpra orientações legítimas da Staff e apresente discordâncias com respeito.",
    ),
    (
        "# 2° COMUNICAÇÃO E ORGANIZAÇÃO",
        "**2.1° Canais** — Use cada canal para sua finalidade.\n\n"
        "**2.2° Spam** — Não envie mensagens repetidas, excessivas ou destinadas a poluir canais.\n\n"
        "**2.3° Menções** — Não abuse de menções a membros, cargos ou @everyone/@here.\n\n"
        "**2.4° Tumulto** — É proibido organizar raids, invasões ou perturbações.\n\n"
        "**2.5° Evasão** — Não burle filtros, restrições ou punições.",
    ),
    (
        "# 3° CONTEÚDO E SEGURANÇA DIGITAL",
        "**3.1° Conteúdo** — Não publique pornografia, conteúdo sexual explícito ou violência gráfica extrema.\n\n"
        "**3.2° Menores** — É proibido qualquer conteúdo de exploração ou sexualização de menores.\n\n"
        "**3.3° Fraudes** — Não divulgue golpes, phishing, links maliciosos ou falsos sorteios.\n\n"
        "**3.4° Malware** — Não compartilhe arquivos ou ferramentas destinados a comprometer dispositivos.\n\n"
        "**3.5° Dano digital** — Não facilite invasões ou ataques contra sistemas e terceiros.",
    ),
    (
        "# 4° PRIVACIDADE E IDENTIDADE",
        "**4.1° Dados pessoais** — Não exponha endereço, telefone, IP, documentos ou dados privados sem autorização.\n\n"
        "**4.2° Doxxing** — É proibido expor dados para ameaçar, constranger ou prejudicar alguém.\n\n"
        "**4.3° Credenciais** — Não solicite nem publique senhas, tokens ou códigos de autenticação.\n\n"
        "**4.4° Conversas** — Não divulgue conteúdo privado sem autorização, salvo denúncia legítima.\n\n"
        "**4.5° Identidade** — Não se passe por membros, Staff ou bots para enganar ou obter vantagem.",
    ),
    (
        "# 5° DIVULGAÇÃO E PARCERIAS",
        "**5.1° Publicidade** — Divulgue somente nos canais e formatos autorizados.\n\n"
        "**5.2° Mensagens privadas** — Não envie anúncios não solicitados nem insista por DM.\n\n"
        "**5.3° Convites** — Não espalhe convites fraudulentos ou links enganosos.\n\n"
        "**5.4° Parcerias** — Toda parceria depende de análise e aprovação da autoridade responsável.\n\n"
        "**5.5° Uso da comunidade** — Não utilize a NÊMESIS para autopromoção irregular.",
    ),
    (
        "# 6° ATENDIMENTO E DENÚNCIAS",
        "**6.1° Solicitações** — Use a categoria correta e trate assuntos pertinentes.\n\n"
        "**6.2° Evidências** — Forneça contexto claro e provas originais.\n\n"
        "**6.3° Abuso** — Não abra tickets duplicados nem pressione a equipe com cobranças insistentes.\n\n"
        "**6.4° Denúncias falsas** — Não fabrique, adultere ou manipule provas.\n\n"
        "**6.5° Discrição** — Evite acusações públicas; denúncia não implica punição automática.",
    ),
    (
        "# 7° STAFF, HIERARQUIA E AUTORIDADE",
        "**7.1° Imparcialidade** — A Staff deve agir com respeito, neutralidade e responsabilidade.\n\n"
        "**7.2° Abuso de poder** — É proibido perseguir, retaliar, favorecer ou obter vantagem pelo cargo.\n\n"
        "**7.3° Confidencialidade** — Não divulgue informações internas sem autorização.\n\n"
        "**7.4° Responsabilização** — Condutas da equipe podem ser denunciadas e apuradas.\n\n"
        "**7.5° Estrutura** — O OCTÓGONO é a instância máxima; Supervisores Staff exercem atribuições administrativas conforme suas permissões.",
    ),
    (
        "# 8° COMPETIÇÕES, MISSÕES E SISTEMAS",
        "**8.1° Normas específicas** — Cumpra regras de jogos, eventos, competições e missões.\n\n"
        "**8.2° Vantagem indevida** — São proibidos cheats, exploits e scripts vedados.\n\n"
        "**8.3° Integridade** — Não falsifique provas, participação ou resultados, nem sabote atividades.\n\n"
        "**8.4° Progressão** — Respeite os critérios oficiais de XP e avaliação.\n\n"
        "**8.5° Consequências** — Infrações também podem gerar medidas na atividade ou competição.",
    ),
    (
        "# 9° REINCIDÊNCIA E AGRAVANTES",
        "**9.1° Reincidência** — Infrações repetidas no período de análise podem elevar a medida.\n\n"
        "**9.2° Evasão** — Contas alternativas ou tentativa de contornar punições agravam a ocorrência.\n\n"
        "**9.3° Retaliação** — Ameaças contra denunciantes ou testemunhas são agravantes.\n\n"
        "**9.4° Obstrução** — Ocultar provas ou interferir em apurações pode agravar a medida.\n\n"
        "**9.5° Análise** — Gravidade, intenção, dano, contexto, provas e histórico serão considerados; casos críticos podem exigir ação imediata.",
    ),
    (
        "# 10° NÍVEIS E MEDIDAS DISCIPLINARES",
        "**10.1° Nível I — Normal:** advertência formal.\n\n"
        "**10.2° Nível II — Médio:** timeout padrão de 10 minutos.\n\n"
        "**10.3° Nível III — Grave:** expulsão do servidor.\n\n"
        "**10.4° Nível IV — Muito grave:** banimento temporário padrão de 24 horas.\n\n"
        "**10.5° Nível V — Crítico:** banimento permanente.\n\n"
        "**10.6° Ajustes** — Durações podem ser personalizadas por configuração autorizada. Casos críticos admitem ação imediata.\n\n"
        "**10.7° Reincidência automática** — 2 registros recentes podem elevar um nível; 4 ou mais, dois níveis, limitado ao V.\n\n"
        "**10.8° Revisão** — Solicite revisão nos canais oficiais, com justificativa e informações pertinentes.",
    ),
    (
        "# 11° DISPOSIÇÕES FINAIS",
        "**11.1° Abrangência** — As regras valem para todos, sem distinção de cargo.\n\n"
        "**11.2° Complementos** — Normas de sistemas, missões e competições complementam este Código.\n\n"
        "**11.3° Omissões** — Casos não previstos serão avaliados com proporcionalidade e foco na integridade da organização.\n\n"
        "**11.4° Atualizações** — Mudanças serão comunicadas nos canais oficiais.\n\n"
        "**11.5° Responsabilidade** — Desconhecer as regras não elimina a responsabilidade por cumpri-las.",
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
