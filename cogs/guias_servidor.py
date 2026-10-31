import logging
import os

import discord
from discord.ext import commands

from utils.apresentacao import criar_embed, aplicar_identidade_servidor

logger = logging.getLogger(__name__)

CANAL_GUIAS_ID = 1563995880833421512
VERSAO_GUIA = "2026-10-v2"

# Conteúdo público: instruções operacionais, sem expor rotinas internas ou permissões.
GUIAS = [
    ("COMECE POR AQUI", "Orientação para novos membros", [
        "Leia as regras oficiais e os avisos fixados antes de participar.",
        "Consulte este guia para entender os sistemas e use /help para localizar os comandos liberados ao seu cargo.",
        "Use /perfil para acompanhar sua progressão e seus registros.",
        "Entre nos canais de Missões, Contribuições, eventos e atendimento conforme sua necessidade.",
        "Se encontrar um erro ou tiver uma dúvida individual, abra um ticket pela Central de Atendimento."
    ], "/help · /tutorial · /perfil"),
    ("PERFIL E PROGRESSÃO", "Como acompanhar sua evolução na NÊMESIS", [
        "Use /perfil para consultar seus dados e estatísticas disponíveis.",
        "O XP é concedido conforme as regras dos sistemas e as atividades validadas.",
        "Rankings apresentam classificações; confira sempre a temporada e o critério exibido.",
        "Aguarde a validação de uma atividade antes de considerar a recompensa confirmada.",
        "Se algum dado parecer incorreto, abra um ticket e informe o sistema, o valor esperado e quando ocorreu."
    ], "/perfil · /help"),
    ("MISSÕES", "Atividades oficiais com recompensa em XP", [
        "Abra o catálogo de Missões e escolha uma atividade disponível.",
        "Leia a descrição, os requisitos, a dificuldade e o prazo antes de começar.",
        "Execute a atividade conforme as regras e reúna uma prova legível e completa.",
        "Envie a prova pelo fluxo indicado na atividade e aguarde a revisão.",
        "A recompensa em XP só é confirmada após a aprovação; não envie a mesma prova repetidamente."
    ], "/tutorial · /help"),
    ("CONTRIBUIÇÕES", "Como participar das atividades de contribuição", [
        "Consulte as atividades disponíveis no espaço oficial de Contribuições.",
        "Confira os critérios de participação e a evidência exigida em cada atividade.",
        "Realize a contribuição e reúna os registros necessários para demonstrá-la.",
        "Envie a comprovação pelo procedimento indicado e aguarde a análise.",
        "Em caso de dúvida sobre elegibilidade ou resultado, procure a equipe pelo ticket."
    ], "/tutorial · /help"),
    ("MISSÕES ESPECIAIS", "Atividades com regras próprias", [
        "Leia o anúncio completo: uma missão especial pode ter condições diferentes das atividades regulares.",
        "Verifique elegibilidade, prazo, objetivo, formato da prova e recompensa.",
        "Não presuma que regras de outra missão também se aplicam à atividade especial.",
        "Envie a comprovação somente pelo fluxo indicado no anúncio.",
        "Após o encerramento, novas submissões dependem de autorização da organização."
    ], "/tutorial · /help"),
    ("PVP E DESAFIOS", "Orientações para confrontos competitivos", [
        "Combine com o adversário o formato, as regras e as condições do confronto antes de jogar.",
        "Utilize o sistema oficial de desafios quando ele estiver disponível para a modalidade.",
        "Registre o resultado com evidência clara, preservando placar e contexto.",
        "Aguarde a confirmação do resultado antes de considerar estatísticas ou recompensas definitivas.",
        "Se houver divergência, solicite revisão pelo atendimento em vez de criar registros duplicados."
    ], "/help · /perfil"),
    ("PROVAS E REVISÕES", "Como enviar uma comprovação válida", [
        "Envie uma captura ou registro nítido, completo e relacionado à atividade.",
        "A prova deve permitir identificar o resultado e o contexto necessário para a conferência.",
        "Não reutilize a mesma evidência para atividades diferentes nem altere informações relevantes.",
        "A equipe revisora pode aprovar ou rejeitar a submissão conforme os critérios publicados.",
        "Uma rejeição deve ser acompanhada de justificativa; se discordar, abra um ticket com o protocolo e a evidência."
    ], "/help · /perfil"),
    ("RANKINGS E TEMPORADAS", "Como interpretar classificações", [
        "Confira qual ranking está sendo consultado e qual critério determina a posição.",
        "Observe a temporada ou o período indicado no painel.",
        "Somente registros válidos e confirmados devem compor resultados oficiais.",
        "Acompanhe os anúncios para conhecer datas de encerramento e divulgações.",
        "Se identificar divergência, envie à equipe o link ou identificador do registro."
    ], "/perfil · /help"),
    ("CONTA ROBLOX", "Vinculação e identificação de perfil", [
        "Use o comando de vinculação indicado em /help e informe seu usuário Roblox corretamente.",
        "Se o bot fornecer um código de verificação, siga exatamente as instruções exibidas.",
        "Conclua a confirmação pelo comando indicado pelo próprio bot.",
        "Consulte o vínculo pelo comando de perfil Roblox disponível em /help.",
        "Nunca compartilhe senha, cookie, token ou código de acesso da sua conta."
    ], "/help"),
    ("ATENDIMENTO E TICKETS", "Como solicitar suporte", [
        "Abra a Central de Atendimento e selecione a categoria que melhor representa seu assunto.",
        "Descreva o problema de forma objetiva, incluindo o que aconteceu e o resultado esperado.",
        "Anexe links, IDs e capturas relevantes; oculte informações privadas.",
        "Continue a conversa no mesmo ticket para preservar o histórico do atendimento.",
        "Ao receber a solução, confirme se o problema foi resolvido antes do encerramento."
    ], "Central de Atendimento · /help"),
    ("EVENTOS E CAMPEONATOS", "Participação em atividades organizadas", [
        "Acompanhe os anúncios e o canal oficial de eventos.",
        "Leia horário, formato, regras, requisitos e limite de participantes.",
        "Confirme sua presença pelo mecanismo indicado no anúncio, quando existir.",
        "Respeite as orientações da organização durante toda a atividade.",
        "Se não puder comparecer ou encontrar um problema, avise a equipe com antecedência."
    ], "/help"),
    ("FORMULÁRIOS E RECRUTAMENTO", "Como enviar uma candidatura", [
        "Leia os requisitos e as instruções apresentados no painel do formulário.",
        "Abra o formulário oficial e responda com informações verdadeiras e completas.",
        "Revise as respostas antes de enviar e evite candidaturas duplicadas.",
        "Aguarde a análise da equipe responsável; o envio não representa aprovação automática.",
        "Se a equipe solicitar complemento, responda pelo canal ou ticket indicado."
    ], "Painel de Formulários · /help"),
    ("PARCERIAS E ALIANÇAS", "Como apresentar uma proposta institucional", [
        "Consulte o painel ou canal oficial de parcerias para verificar o procedimento vigente.",
        "Apresente a comunidade, o representante responsável e os meios oficiais de contato.",
        "Explique o objetivo da parceria e o benefício esperado para ambas as comunidades.",
        "Aguarde a avaliação da liderança; uma proposta enviada não significa parceria aprovada.",
        "Não anuncie uma aliança nem fale em nome da NÊMESIS antes da autorização oficial."
    ], "Painel de Parcerias · /help"),
    ("MODERAÇÃO E CONDUTA", "Regras de convivência e atuação da equipe", [
        "Mantenha respeito aos membros e siga as regras oficiais em todos os canais.",
        "Não provoque conflitos, assedie outros membros ou tente contornar medidas de moderação.",
        "Se presenciar uma infração, reúna contexto e encaminhe a situação à equipe.",
        "A equipe deve avaliar evidências e aplicar medidas proporcionais, registrando a justificativa.",
        "Dúvidas ou contestações devem ser tratadas pela Central de Atendimento."
    ], "Regras oficiais · Central de Atendimento"),
    ("GUERRAS E OPERAÇÕES", "Orientações para atividades entre equipes", [
        "Confirme que a operação foi autorizada pelos responsáveis antes de anunciá-la como oficial.",
        "Defina equipes, formato, regras, horário e critérios de resultado antecipadamente.",
        "Registre participantes e placar de forma clara após a atividade.",
        "Correções ou cancelamentos devem ser comunicados à equipe responsável.",
        "Em caso de conflito, preserve as evidências e solicite análise pelo atendimento."
    ], "/help · Central de Atendimento"),
]

def _criar_embed(titulo: str, descricao: str, passos: list[str], comandos: str, numero: int, guild: discord.Guild, bot: commands.Bot) -> discord.Embed:
    embed = criar_embed(
        title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ {titulo}",
        description=descricao,
        color=0x780D22,
        rodape=None,
    )
    embed.add_field(
        name="◈ PASSO A PASSO",
        value="\n".join(f"**{i}.** {passo}" for i, passo in enumerate(passos, 1)),
        inline=False,
    )
    embed.add_field(name="◈ ACESSO RÁPIDO", value=comandos, inline=False)
    embed.set_footer(text=f"NÊMESIS • GUIA OFICIAL • {VERSAO_GUIA} • TUTORIAL {numero:02d}")
    return aplicar_identidade_servidor(embed, guild, bot)

class GuiasServidor(commands.Cog):
    """Publica e mantém os guias oficiais no canal de tutoriais."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._publicando = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._publicando:
            return
        self._publicando = True
        try:
            canal = self.bot.get_channel(CANAL_GUIAS_ID)
            if canal is None:
                canal = await self.bot.fetch_channel(CANAL_GUIAS_ID)
            if not isinstance(canal, discord.TextChannel):
                logger.error("O canal configurado para os guias não é um canal de texto.")
                return

            guild_id = os.getenv("NEMESIS_GUILD_ID")
            if guild_id and canal.guild.id != int(guild_id):
                logger.error("Canal de guias ignorado: ele não pertence ao servidor configurado.")
                return

            permissoes = canal.permissions_for(canal.guild.me)
            if not (permissoes.view_channel and permissoes.send_messages and permissoes.embed_links and permissoes.read_message_history):
                logger.error("Sem permissões necessárias no canal de guias (ver canal, histórico, enviar mensagens e incorporar links).")
                return

            marcadores = {
                f"NÊMESIS • GUIA OFICIAL • {VERSAO_GUIA} • PARTE {parte}"
                for parte in (1, 2)
            }
            existentes = set()
            async for mensagem in canal.history(limit=200):
                if mensagem.author.id != self.bot.user.id:
                    continue
                for embed in mensagem.embeds:
                    if embed.footer and embed.footer.text.startswith("NÊMESIS • GUIA OFICIAL •"):
                        if embed.footer.text in marcadores:
                            existentes.add(embed.footer.text)
                        else:
                            try:
                                await mensagem.delete()
                                logger.info("Guia antigo removido para substituir a documentação desatualizada.")
                            except discord.HTTPException:
                                logger.exception("Não foi possível remover uma mensagem antiga de guias.")
                        break

            partes = [GUIAS[:8], GUIAS[8:]]
            for indice, guias in enumerate(partes, start=1):
                marcador = f"NÊMESIS • GUIA OFICIAL • {VERSAO_GUIA} • PARTE {indice}"
                if marcador in existentes:
                    continue
                embeds = [
                    _criar_embed(titulo, descricao, passos, comandos, (indice - 1) * 8 + posicao, canal.guild, self.bot)
                    for posicao, (titulo, descricao, passos, comandos) in enumerate(guias, start=1)
                ]
                embeds[0].set_footer(text=marcador)
                await canal.send(
                    content=(
                        "✦・ **𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — CENTRAL DE GUIAS E TUTORIAIS** ・✦\n"
                        f"Consulte os tutoriais abaixo para aprender os sistemas do servidor. "
                        f"Use **/help** para localizar os comandos disponíveis. 〔{indice}/2〕"
                    ),
                    embeds=embeds,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                logger.info("Parte %s dos guias oficiais publicada no canal %s.", indice, CANAL_GUIAS_ID)
        except discord.Forbidden:
            logger.exception("O bot não tem permissão para publicar ou consultar os guias.")
        except discord.HTTPException:
            logger.exception("Falha de API ao publicar os guias no canal configurado.")
        except Exception:
            logger.exception("Erro inesperado ao publicar os guias da NÊMESIS.")
        finally:
            self._publicando = False

async def setup(bot: commands.Bot):
    await bot.add_cog(GuiasServidor(bot))
