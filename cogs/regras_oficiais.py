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
        "1 - Conduta e respeito",
        ""
        "**1.1° RESPEITO** — Trate todos com dignidade, sem ataques por cargo, opinião ou tempo de servidor.\n\n"
        "**1.2° OFENSAS** — São proibidos insultos, ameaças, humilhação e discriminação.\n\n"
        "**1.3° ASSÉDIO** — Não persiga, intimide ou constranja membros, nem incentive terceiros.\n\n"
        "**1.4° CONVIVÊNCIA** — Interrompa brincadeiras quando causarem desconforto.\n\n"
        "**1.5° ORIENTAÇÕES** — Cumpra orientações legítimas da Staff e apresente discordâncias com respeito.",
    ),
    (
        "2 - Comunicação e organização",
        ""
        "**2.1° CANAIS** — Use cada canal para sua finalidade.\n\n"
        "**2.2° SPAM** — Não envie mensagens repetidas, excessivas ou destinadas a poluir canais.\n\n"
        "**2.3° MENÇÕES** — Não abuse de menções a membros, cargos ou @everyone/@here.\n\n"
        "**2.4° TUMULTO** — É proibido organizar raids, invasões ou perturbações.\n\n"
        "**2.5° EVASÃO** — Não burle filtros, restrições ou punições.",
    ),
    (
        "3 - Conteúdo e segurança digital",
        ""
        "**3.1° CONTEÚDO** — Não publique pornografia, conteúdo sexual explícito ou violência gráfica extrema.\n\n"
        "**3.2° MENORES** — É proibido qualquer conteúdo de exploração ou sexualização de menores.\n\n"
        "**3.3° FRAUDES** — Não divulgue golpes, phishing, links maliciosos ou falsos sorteios.\n\n"
        "**3.4° MALWARE** — Não compartilhe arquivos ou ferramentas destinados a comprometer dispositivos.\n\n"
        "**3.5° DANO DIGITAL** — Não facilite invasões ou ataques contra sistemas e terceiros.",
    ),
    (
        "4 - Privacidade e identidade",
        ""
        "**4.1° DADOS PESSOAIS** — Não exponha endereço, telefone, IP, documentos ou dados privados sem autorização.\n\n"
        "**4.2° DOXXING** — É proibido expor dados para ameaçar, constranger ou prejudicar alguém.\n\n"
        "**4.3° CREDENCIAIS** — Não solicite nem publique senhas, tokens ou códigos de autenticação.\n\n"
        "**4.4° CONVERSAS** — Não divulgue conteúdo privado sem autorização, salvo denúncia legítima.\n\n"
        "**4.5° IDENTIDADE** — Não se passe por membros, Staff ou bots para enganar ou obter vantagem.",
    ),
    (
        "5 - Divulgação e parcerias",
        ""
        "**5.1° PUBLICIDADE** — Divulgue somente nos canais e formatos autorizados.\n\n"
        "**5.2° MENSAGENS PRIVADAS** — Não envie anúncios não solicitados nem insista por DM.\n\n"
        "**5.3° CONVITES** — Não espalhe convites fraudulentos ou links enganosos.\n\n"
        "**5.4° PARCERIAS** — Toda parceria depende de análise e aprovação da autoridade responsável.\n\n"
        "**5.5° USO DA COMUNIDADE** — Não utilize a NÊMESIS para autopromoção irregular.",
    ),
    (
        "6 - Atendimento e denúncias",
        ""
        "**6.1° SOLICITAÇÕES** — Use a categoria correta e trate assuntos pertinentes.\n\n"
        "**6.2° EVIDÊNCIAS** — Forneça contexto claro e provas originais.\n\n"
        "**6.3° ABUSO** — Não abra tickets duplicados nem pressione a equipe com cobranças insistentes.\n\n"
        "**6.4° DENÚNCIAS FALSAS** — Não fabrique, adultere ou manipule provas.\n\n"
        "**6.5° DISCRIÇÃO** — Evite acusações públicas; denúncia não implica punição automática.",
    ),
    (
        "7 - Staff, hierarquia e autoridade",
        ""
        "**7.1° IMPARCIALIDADE** — A Staff deve agir com respeito, neutralidade e responsabilidade.\n\n"
        "**7.2° ABUSO DE PODER** — É proibido perseguir, retaliar, favorecer ou obter vantagem pelo cargo.\n\n"
        "**7.3° CONFIDENCIALIDADE** — Não divulgue informações internas sem autorização.\n\n"
        "**7.4° RESPONSABILIZAÇÃO** — Condutas da equipe podem ser denunciadas e apuradas.\n\n"
        "**7.5° ESTRUTURA** — O OCTÓGONO é a instância máxima; Supervisores Staff exercem atribuições administrativas conforme suas permissões.",
    ),
    (
        "8 - Competições, missões e sistemas",
        ""
        "**8.1° NORMAS ESPECÍFICAS** — Cumpra regras de jogos, eventos, competições e missões.\n\n"
        "**8.2° VANTAGEM INDEVIDA** — São proibidos cheats, exploits e scripts vedados.\n\n"
        "**8.3° INTEGRIDADE** — Não falsifique provas, participação ou resultados, nem sabote atividades.\n\n"
        "**8.4° PROGRESSÃO** — Respeite os critérios oficiais de XP e avaliação.\n\n"
        "**8.5° CONSEQUÊNCIAS** — Infrações também podem gerar medidas na atividade ou competição.",
    ),
    (
        "9 - Reincidência e agravantes",
        ""
        "**9.1° REINCIDÊNCIA** — Infrações repetidas no período de análise podem elevar a medida.\n\n"
        "**9.2° EVASÃO** — Contas alternativas ou tentativa de contornar punições agravam a ocorrência.\n\n"
        "**9.3° RETALIAÇÃO** — Ameaças contra denunciantes ou testemunhas são agravantes.\n\n"
        "**9.4° OBSTRUÇÃO** — Ocultar provas ou interferir em apurações pode agravar a medida.\n\n"
        "**9.5° ANÁLISE** — Gravidade, intenção, dano, contexto, provas e histórico serão considerados; casos críticos podem exigir ação imediata.",
    ),
    (
        "10 - Níveis e medidas disciplinares",
        ""
        "**10.1° NÍVEL I — NORMAL:** advertência formal.\n\n"
        "**10.2° NÍVEL II — MÉDIO:** timeout de 10 minutos.\n\n"
        "**10.3° NÍVEL III — GRAVE:** expulsão do servidor.\n\n"
        "**10.4° NÍVEL IV — MUITO GRAVE:** banimento temporário de 24 horas.\n\n"
        "**10.5° NÍVEL V — CRÍTICO:** banimento permanente.\n\n"
        "**10.6° AJUSTES** — Durações podem ser personalizadas por configuração autorizada. Casos críticos admitem ação imediata.\n\n"
        "**10.7° REINCIDÊNCIA AUTOMÁTICA** — 2 registros recentes podem elevar um nível; 4 ou mais, dois níveis, limitado ao V.\n\n"
        "**10.8° REVISÃO** — Solicite revisão nos canais oficiais, com justificativa e informações pertinentes.",
    ),
    (
        "11 - Disposições finais",
        ""
        "**11.1° ABRANGÊNCIA** — As regras valem para todos, sem distinção de cargo.\n\n"
        "**11.2° COMPLEMENTOS** — Normas de sistemas, missões e competições complementam este Código.\n\n"
        "**11.3° OMISSÕES** — Casos não previstos serão avaliados com proporcionalidade e foco na integridade da organização.\n\n"
        "**11.4° ATUALIZAÇÕES** — Mudanças serão comunicadas nos canais oficiais.\n\n"
        "**11.5° RESPONSABILIDADE** — Desconhecer as regras não elimina a responsabilidade por cumpri-las.",
    ),
)


def construir_embeds_regras() -> list[discord.Embed]:
    """Cria uma embed por artigo para usar o título nativo, visualmente maior, do Discord."""
    introducao = (
        "Regulamento oficial da organização. Aplica-se a todos os integrantes, "
        "sem distinção de cargo. Leia as diretrizes e consulte a equipe pelos "
        "canais oficiais em caso de dúvida ou denúncia."
    )
    embeds = []
    for indice, (titulo, texto) in enumerate(SECOES_REGRAS, start=1):
        descricao = texto.strip()
        if indice == 1:
            descricao = f"{introducao}\\n\\n{descricao}"

        embed = criar_embed(
            title=titulo,
            description=descricao,
            color=COR,
        )
        embed.set_footer(text=f"{MARCADOR_PUBLICACAO} • Artigo {indice}/11")

        if len(embed.title or "") > 256 or len(embed.description or "") > 4096:
            raise ValueError(f"O artigo {indice} excede os limites de uma embed do Discord.")
        if len(embed) > 6000:
            raise ValueError(f"O artigo {indice} excede o limite total de caracteres da embed.")
        embeds.append(embed)

    if len(embeds) != 11:
        raise ValueError("O Código de Conduta deve conter exatamente 11 artigos.")
    return embeds


def agrupar_embeds_regras(embeds: list[discord.Embed]) -> list[list[discord.Embed]]:
    """Agrupa artigos sem ultrapassar 10 embeds ou 6.000 caracteres por mensagem."""
    lotes: list[list[discord.Embed]] = []
    lote_atual: list[discord.Embed] = []
    total_atual = 0

    for embed in embeds:
        tamanho = len(embed)
        if tamanho > 6000:
            raise ValueError("Um artigo excede o limite de caracteres de uma mensagem do Discord.")
        if lote_atual and (len(lote_atual) >= 10 or total_atual + tamanho > 6000):
            lotes.append(lote_atual)
            lote_atual = []
            total_atual = 0
        lote_atual.append(embed)
        total_atual += tamanho

    if lote_atual:
        lotes.append(lote_atual)
    return lotes


# Compatibilidade para módulos e testes que ainda consultam a primeira embed.
def construir_embed_regras() -> discord.Embed:
    """Retorna o primeiro artigo no formato de embed."""
    return construir_embeds_regras()[0]


class RegrasOficiais(commands.Cog):
    """Mantém os 11 artigos do Código de Conduta em uma única embed no canal oficial de regras."""

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
        if not (
            permissoes.view_channel
            and permissoes.read_message_history
            and permissoes.send_messages
            and permissoes.embed_links
        ):
            logging.error(
                "Código de Conduta: faltam permissões no canal %s "
                "(visualizar, ler histórico, enviar mensagens e inserir links).",
                CANAL_REGRAS_ID,
            )
            return False

        lotes = agrupar_embeds_regras(construir_embeds_regras())
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

        existentes.sort(key=lambda mensagem: mensagem.created_at)
        mensagens_atualizadas = []
        for indice, lote in enumerate(lotes):
            if indice < len(existentes):
                mensagem = existentes[indice]
                try:
                    await mensagem.edit(
                        content=None,
                        embeds=lote,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    logging.exception(
                        "Código de Conduta: falha ao atualizar o bloco %s.",
                        indice + 1,
                    )
                    return False
                mensagens_atualizadas.append(mensagem)
            else:
                try:
                    mensagem = await canal.send(
                        embeds=lote,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    logging.exception(
                        "Código de Conduta: falha ao publicar o bloco %s.",
                        indice + 1,
                    )
                    return False
                mensagens_atualizadas.append(mensagem)

        for duplicada in existentes[len(lotes):]:
            try:
                await duplicada.delete()
            except discord.HTTPException:
                logging.warning(
                    "Código de Conduta: não foi possível remover publicação antiga (message_id=%s).",
                    duplicada.id,
                )

        logging.info(
            "Código de Conduta atualizado em %s mensagens com 11 títulos nativos no canal %s.",
            len(lotes),
            CANAL_REGRAS_ID,
        )
        return True


async def setup(bot: commands.Bot):
    await bot.add_cog(RegrasOficiais(bot))
