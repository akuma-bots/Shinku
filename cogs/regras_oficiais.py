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
        "1 Conduta",
        "1 Respeite todos os integrantes, independentemente de cargo, opinião ou tempo de servidor.\n\n2 Não são permitidos insultos, ameaças, humilhação ou discriminação.\n\n3 Não persiga, intimide ou constranja membros, nem incentive terceiros a fazê-lo.\n\n4 Interrompa brincadeiras quando causarem desconforto.\n\n5 Cumpra orientações legítimas da Staff e apresente discordâncias com respeito.",
    ),
    (
        "2 Comunicação e organização",
        "1 Use cada canal para sua finalidade.\n\n2 Não envie mensagens repetidas, excessivas ou destinadas a poluir os canais.\n\n3 Não abuse de menções a membros, cargos, @everyone ou @here.\n\n4 É proibido organizar raids, invasões ou perturbações.\n\n5 Não burle filtros, restrições ou punições.",
    ),
    (
        "3 Conteúdo e segurança digital",
        "1 Não publique pornografia, conteúdo sexual explícito ou violência gráfica extrema.\n\n2 É proibido qualquer conteúdo de exploração ou sexualização de menores.\n\n3 Não divulgue golpes, phishing, links maliciosos ou falsos sorteios.\n\n4 Não compartilhe arquivos ou ferramentas destinados a comprometer dispositivos.\n\n5 Não facilite invasões ou ataques contra sistemas e terceiros.",
    ),
    (
        "4 Privacidade e identidade",
        "1 Não exponha endereço, telefone, IP, documentos ou dados privados sem autorização.\n\n2 É proibido expor dados para ameaçar, constranger ou prejudicar alguém.\n\n3 Não solicite nem publique senhas, tokens ou códigos de autenticação.\n\n4 Não divulgue conteúdo privado sem autorização, salvo para uma denúncia legítima.\n\n5 Não se passe por membros, Staff ou bots para enganar ou obter vantagem.",
    ),
    (
        "5 Divulgação e parcerias",
        "1 Divulgue somente nos canais e formatos autorizados.\n\n2 Não envie anúncios não solicitados por mensagem privada nem insista após uma recusa.\n\n3 Não espalhe convites fraudulentos ou links enganosos.\n\n4 Toda parceria depende de análise e aprovação da autoridade responsável.\n\n5 Não utilize a NÊMESIS para autopromoção irregular.",
    ),
    (
        "6 Atendimento e denúncias",
        "1 Use a categoria correta e trate assuntos pertinentes.\n\n2 Forneça contexto claro e provas originais.\n\n3 Não abra tickets duplicados nem pressione a equipe com cobranças insistentes.\n\n4 Não fabrique, adultere ou manipule provas.\n\n5 Evite acusações públicas; uma denúncia não implica punição automática.",
    ),
    (
        "7 Staff, hierarquia e autoridade",
        "1 A Staff deve agir com respeito, neutralidade e responsabilidade.\n\n2 É proibido perseguir, retaliar, favorecer ou obter vantagem pelo cargo.\n\n3 Não divulgue informações internas sem autorização.\n\n4 Condutas da equipe podem ser denunciadas e apuradas.\n\n5 O OCTÓGONO é a instância máxima; Supervisores Staff exercem atribuições administrativas conforme suas permissões.",
    ),
    (
        "8 Competições, missões e sistemas",
        "1 Cumpra as regras específicas de jogos, eventos, competições e missões.\n\n2 São proibidos cheats, exploits e scripts vedados.\n\n3 Não falsifique provas, participação ou resultados, nem sabote atividades.\n\n4 Respeite os critérios oficiais de XP e avaliação.\n\n5 Infrações também podem gerar medidas na atividade ou competição.",
    ),
    (
        "9 Reincidência e agravantes",
        "1 Infrações repetidas no período de análise podem elevar a medida disciplinar.\n\n2 Contas alternativas ou tentativas de contornar punições agravam a ocorrência.\n\n3 Ameaças contra denunciantes ou testemunhas são agravantes.\n\n4 Ocultar provas ou interferir em apurações pode agravar a medida.\n\n5 Gravidade, intenção, dano, contexto, provas e histórico serão considerados; casos críticos podem exigir ação imediata.",
    ),
    (
        "10 Punições",
        "1 1 Punições Níveis:\n\n2 Nível I: Silenciamento ou advertência formal.\n\n3 Nível II: Remoção de cargo, quando aplicável.\n\n4 Nível III: Suspensão de atividades, missões ou competições.\n\n5 Nível IV: Expulsão do servidor.\n\n6 Nível V: Banimento temporário de 24 horas.\n\n7 Nível VI: Banimento temporário de 7 dias.\n\n8 Nível VII: Banimento permanente.\n\n9 As medidas podem ser ajustadas conforme gravidade, contexto, reincidência e evidências. Casos críticos podem receber ação imediata.\n\n10 Solicitações de revisão devem ser feitas pelos canais oficiais, com justificativa e informações pertinentes.",
    ),
    (
        "11 Disposições finais",
        "1 As regras valem para todos, sem distinção de cargo.\n\n2 Normas de sistemas, missões e competições complementam este Código.\n\n3 Casos não previstos serão avaliados com proporcionalidade e foco na integridade da organização.\n\n4 Mudanças serão comunicadas nos canais oficiais.\n\n5 Desconhecer as regras não elimina a responsabilidade por cumpri-las.",
    )
)


def construir_embed_regras() -> discord.Embed:
    """Reúne os 11 artigos em uma única embed, com títulos como campos."""
    embed = criar_embed(
        title="CÓDIGO DE CONDUTA • NÊMESIS",
        description="Código oficial da NÊMESIS. As regras se aplicam a todos os integrantes, sem distinção de cargo.\n\nCada artigo apresenta suas determinações em ordem numérica.",
        color=COR,
    )
    for titulo, texto in SECOES_REGRAS:
        valor = texto.strip()
        if len(titulo) > 256 or len(valor) > 1024:
            raise ValueError(f"O artigo {titulo!r} excede os limites de campo do Discord.")
        embed.add_field(name=titulo, value=valor, inline=False)
    embed.set_footer(text=MARCADOR_PUBLICACAO)
    total = len(embed.title or "") + len(embed.description or "") + len(embed.author.name if embed.author else "") + len(embed.footer.text if embed.footer else "") + sum(len(campo.name) + len(campo.value) for campo in embed.fields)
    if len(embed.fields) > 25 or total > 6000:
        raise ValueError(f"O Código de Conduta excede o limite de uma embed ({total}/6000 caracteres).")
    if len(embed.fields) != 11:
        raise ValueError("O Código de Conduta deve conter exatamente 11 artigos.")
    return embed

class RegrasOficiais(commands.Cog):
    """Mantém os 11 artigos em uma única embed no canal oficial de regras."""

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

        embed = construir_embed_regras()
        existentes = []
        try:
            async for mensagem in canal.history(limit=200, oldest_first=False):
                if self.bot.user is None or mensagem.author.id != self.bot.user.id:
                    continue
                titulos_artigos = {titulo for titulo, _ in SECOES_REGRAS}
                eh_publicacao_oficial = any(
                    (
                        item.footer
                        and (item.footer.text or "").startswith(MARCADOR_PUBLICACAO)
                    )
                    or item.title == "CÓDIGO DE CONDUTA • NÊMESIS"
                    or any(campo.name in titulos_artigos for campo in item.fields)
                    for item in mensagem.embeds
                )
                if eh_publicacao_oficial:
                    existentes.append(mensagem)
        except discord.HTTPException:
            logging.exception("Código de Conduta: falha ao consultar publicações anteriores.")
            return False

        existentes.sort(key=lambda mensagem: mensagem.created_at)
        if existentes:
            principal = existentes[0]
            try:
                await principal.edit(content=None, embeds=[embed], allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logging.exception("Código de Conduta: falha ao atualizar a embed única.")
                return False
        else:
            try:
                await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                logging.exception("Código de Conduta: falha ao publicar a embed única.")
                return False

        for duplicada in existentes[1:]:
            try:
                await duplicada.delete()
            except discord.HTTPException:
                logging.warning("Código de Conduta: não foi possível remover publicação antiga (message_id=%s).", duplicada.id)

        logging.info("Código de Conduta atualizado em uma única embed com 11 artigos no canal %s.", CANAL_REGRAS_ID)
        return True



async def setup(bot: commands.Bot):
    await bot.add_cog(RegrasOficiais(bot))
