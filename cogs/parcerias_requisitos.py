"""Sistema oficial de requisitos e avaliação de parcerias da NÊMESIS."""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from urllib.parse import urlparse

import discord
from discord.ext import commands

from utils.storage import carregar, atualizar_json
from utils.guild_config import membro_tem_lideranca

GUILD_ID = 1563995879981981817
CANAL_PARcerias_ID = 1563995881655509058
ARQUIVO = "parcerias_requisitos.json"
INTERVALO_REVISAO = 15 * 24 * 60 * 60
COR = 0x9F2035
_LOG = logging.getLogger(__name__)
_LOCK = asyncio.Lock()


def _url_convite_valida(valor: str) -> bool:
    try:
        parsed = urlparse(valor.strip())
        return parsed.scheme == "https" and parsed.netloc.lower() in {
            "discord.gg", "www.discord.gg", "discord.com", "www.discord.com"
        } and (parsed.path.startswith("/invite/") or parsed.netloc.lower().endswith("discord.gg"))
    except Exception:
        return False


def _embed_painel() -> discord.Embed:
    embed = discord.Embed(
        title="NÊMESIS  ━  CENTRAL OFICIAL DE PARCERIAS",
        description=(
            "Estabeleça uma aliança com a NÊMESIS. Todas as solicitações passam por "
            "avaliação administrativa e devem cumprir integralmente os critérios abaixo.\n\n"
            "**REQUISITOS OBRIGATÓRIOS**\n"
            "◈ Comunidade organizada, com identidade e propósito definidos.\n"
            "◈ Atividade real e participação recorrente dos membros.\n"
            "◈ Administração responsável e canais de contato acessíveis.\n"
            "◈ Reputação íntegra, sem evidências de golpes, fraudes ou práticas abusivas.\n"
            "◈ Compatibilidade de objetivos e respeito às diretrizes da NÊMESIS.\n"
            "◈ Aceitar divulgação recíproca, sem spam ou publicidade enganosa.\n"
            "◈ Fornecer convite válido e evidências suficientes para análise.\n\n"
            "**PADRÃO DE AVALIAÇÃO — RIGOROSO**\n"
            "Número de membros, isoladamente, não garante aprovação. A equipe poderá "
            "solicitar informações adicionais ou recusar propostas incompatíveis.\n\n"
            "**PROCESSO**\n"
            "1. Envie a proposta pelo botão abaixo.\n"
            "2. A administração analisará os dados e as evidências.\n"
            "3. A decisão será registrada em auditoria.\n"
            "4. Parcerias aprovadas passam por revisão obrigatória a cada **15 dias**."
        ),
        color=COR,
    )
    embed.add_field(
        name="AUTORIDADE",
        value="OCTÓGONO e administração autorizada. Aprovação automática desativada.",
        inline=False,
    )
    embed.set_footer(text="NÊMESIS • INTEGRIDADE • RECIPROCIDADE • ALIANÇAS")
    return embed


async def _ler() -> dict:
    data = await carregar(ARQUIVO, {})
    return data if isinstance(data, dict) else {}


async def _atualizar(transformador):
    return await atualizar_json(ARQUIVO, {}, transformador)


def _embed_solicitacao(item: dict) -> discord.Embed:
    status = str(item.get("status", "pendente")).upper()
    embed = discord.Embed(
        title=f"NÊMESIS  ━  SOLICITAÇÃO {item.get('protocolo', '—')}",
        description=(
            f"**Servidor:** {item.get('nome', '—')}\n"
            f"**Responsável:** <@{item.get('responsavel_id')}>\n"
            f"**Membros declarados:** {item.get('membros', '—')}\n"
            f"**Segmento:** {item.get('segmento', '—')}\n"
            f"**Proposta:**\n{item.get('proposta', '—')}"
        ),
        color=COR if status == "PENDENTE" else (0x2ECC71 if status == "APROVADA" else 0xE74C3C),
    )
    embed.add_field(name="Convite", value=item.get("convite", "—"), inline=False)
    embed.add_field(name="Evidências / apresentação", value=item.get("evidencias", "Não fornecidas")[:1000], inline=False)
    embed.add_field(name="Situação", value=status, inline=True)
    embed.add_field(name="Recebida", value=f"<t:{int(item.get('criada_em', time.time()))}:F>", inline=True)
    if item.get("decisao_por"):
        embed.add_field(name="Decisão por", value=f"<@{item['decisao_por']}>", inline=True)
    if item.get("motivo"):
        embed.add_field(name="Justificativa", value=str(item["motivo"])[:1000], inline=False)
    if item.get("proxima_revisao"):
        embed.add_field(name="Próxima revisão", value=f"<t:{int(item['proxima_revisao'])}:F>", inline=False)
    embed.set_footer(text="NÊMESIS • AVALIAÇÃO ADMINISTRATIVA • REGISTRO AUDITÁVEL")
    return embed


class FormularioParceria(discord.ui.Modal, title="Solicitação de parceria NÊMESIS"):
    nome = discord.ui.TextInput(label="Nome do servidor", max_length=80, placeholder="Nome oficial da comunidade")
    convite = discord.ui.TextInput(label="Convite permanente", max_length=200, placeholder="https://discord.gg/...")
    membros = discord.ui.TextInput(label="Quantidade aproximada de membros", max_length=12, placeholder="Ex.: 850")
    segmento = discord.ui.TextInput(label="Segmento / objetivo", max_length=120, placeholder="Ex.: comunidade gamer, RP, tecnologia...")
    proposta = discord.ui.TextInput(label="Proposta de parceria", style=discord.TextStyle.paragraph, min_length=20, max_length=900, placeholder="Explique o que sua comunidade oferece e como será a reciprocidade.")
    evidencias = discord.ui.TextInput(label="Atividade e evidências (opcional)", style=discord.TextStyle.paragraph, required=False, max_length=700, placeholder="Links de apresentação, redes sociais, prints ou informações relevantes.")

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID:
            await interaction.response.send_message("Este formulário pertence exclusivamente à NÊMESIS.", ephemeral=True)
            return
        convite = str(self.convite.value).strip()
        if not _url_convite_valida(convite):
            await interaction.response.send_message("Informe um convite válido do Discord começando com https://discord.gg/ ou https://discord.com/invite/.", ephemeral=True)
            return
        try:
            membros = int(str(self.membros.value).replace(".", "").replace(",", "").strip())
            if membros < 1 or membros > 10_000_000:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Informe uma quantidade válida de membros.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        protocolo = uuid.uuid4().hex[:8].upper()
        item = {
            "id": protocolo.lower(),
            "protocolo": protocolo,
            "guild_id": GUILD_ID,
            "nome": str(self.nome.value).strip(),
            "convite": convite,
            "membros": membros,
            "segmento": str(self.segmento.value).strip(),
            "proposta": str(self.proposta.value).strip(),
            "evidencias": str(self.evidencias.value).strip(),
            "responsavel_id": interaction.user.id,
            "criada_em": int(time.time()),
            "status": "pendente",
            "decisao_por": None,
            "proxima_revisao": None,
        }
        canal = interaction.client.get_channel(CANAL_PARcerias_ID)
        if not isinstance(canal, discord.TextChannel):
            await interaction.followup.send("O canal oficial de parcerias não está acessível. Avise a administração.", ephemeral=True)
            return
        try:
            mensagem = await canal.send(embed=_embed_solicitacao(item), view=DecisaoParceriaView(protocolo.lower()))
        except (discord.Forbidden, discord.HTTPException):
            _LOG.exception("Falha ao publicar solicitação de parceria %s", protocolo)
            await interaction.followup.send("Não consegui encaminhar sua solicitação. Tente novamente mais tarde.", ephemeral=True)
            return
        item["mensagem_id"] = mensagem.id
        item["canal_id"] = canal.id

        def gravar(data):
            if not isinstance(data, dict):
                data = {}
            data.setdefault("solicitacoes", [])
            data["solicitacoes"].append(item)
            return data
        await _atualizar(gravar)
        try:
            from utils.registro_global import registrar as registrar_global
            await registrar_global(
                interaction.guild, "parcerias", "Nova solicitação de parceria",
                f"**Protocolo:** {protocolo}\n**Servidor:** {item['nome']}\n"
                f"**Responsável:** {interaction.user.mention} (ID: {interaction.user.id})\n"
                f"**Situação:** Pendente de avaliação",
                cor=COR,
            )
        except Exception:
            _LOG.exception("Falha ao registrar auditoria da solicitação %s", protocolo)
        await interaction.followup.send(f"Sua solicitação foi encaminhada para avaliação. Protocolo: **{protocolo}**. O envio não representa aprovação.", ephemeral=True)


class PainelSolicitarParceria(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Solicitar parceria", style=discord.ButtonStyle.primary, emoji="🤝", custom_id="nemesis:parcerias:solicitar")
    async def solicitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != GUILD_ID:
            await interaction.response.send_message("Ação exclusiva da NÊMESIS.", ephemeral=True)
            return
        await interaction.response.send_modal(FormularioParceria())


class DecisaoParceriaView(discord.ui.View):
    def __init__(self, protocolo: str):
        super().__init__(timeout=None)
        self.protocolo = protocolo
        aprovar = discord.ui.Button(label="Aprovar", style=discord.ButtonStyle.success, emoji="✅", custom_id=f"nemesis:parcerias:aprovar:{protocolo}")
        recusar = discord.ui.Button(label="Recusar", style=discord.ButtonStyle.danger, emoji="✖️", custom_id=f"nemesis:parcerias:recusar:{protocolo}")
        aprovar.callback = self._aprovar
        recusar.callback = self._recusar
        self.add_item(aprovar)
        self.add_item(recusar)

    async def _decidir(self, interaction: discord.Interaction, aprovado: bool):
        if interaction.guild_id != GUILD_ID or not isinstance(interaction.user, discord.Member) or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Apenas o OCTÓGONO e a administração autorizada podem decidir solicitações.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        data = await _ler()
        itens = data.get("solicitacoes", []) if isinstance(data, dict) else []
        item = next((x for x in itens if isinstance(x, dict) and x.get("id") == self.protocolo), None)
        if not item or item.get("status") != "pendente":
            await interaction.followup.send("Esta solicitação já foi processada ou não existe.", ephemeral=True)
            return
        agora = int(time.time())
        item["status"] = "aprovada" if aprovado else "recusada"
        item["decisao_por"] = interaction.user.id
        item["decidida_em"] = agora
        item["proxima_revisao"] = agora + INTERVALO_REVISAO if aprovado else None
        data["solicitacoes"] = itens
        await _atualizar(lambda _: data)
        try:
            await interaction.message.edit(embed=_embed_solicitacao(item), view=None)
        except (discord.Forbidden, discord.HTTPException):
            _LOG.exception("Não foi possível atualizar mensagem da parceria %s", self.protocolo)
        try:
            from utils.registro_global import registrar as registrar_global
            await registrar_global(
                interaction.guild, "parcerias",
                "Parceria aprovada" if aprovado else "Solicitação de parceria recusada",
                f"**Protocolo:** {self.protocolo.upper()}\n**Servidor:** {item.get('nome')}\n"
                f"**Responsável:** <@{item.get('responsavel_id')}>\n"
                f"**Decisão:** {'Aprovada' if aprovado else 'Recusada'}\n"
                f"**Decisor:** {interaction.user.mention}\n"
                f"**Próxima revisão:** {'<t:' + str(item['proxima_revisao']) + ':F>' if aprovado else 'Não aplicável'}",
                cor=0x2ECC71 if aprovado else 0xE74C3C,
            )
        except Exception:
            _LOG.exception("Falha na auditoria da decisão %s", self.protocolo)
        await interaction.followup.send("Decisão registrada e auditada.", ephemeral=True)

    async def _aprovar(self, interaction: discord.Interaction):
        await self._decidir(interaction, True)

    async def _recusar(self, interaction: discord.Interaction):
        await self._decidir(interaction, False)


class ParceriasRequisitos(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._task = None

    async def cog_load(self):
        self.bot.add_view(PainelSolicitarParceria())
        data = await _ler()
        for item in data.get("solicitacoes", []):
            if isinstance(item, dict) and item.get("status") == "pendente" and item.get("id"):
                self.bot.add_view(DecisaoParceriaView(str(item["id"])))
        self._task = asyncio.create_task(self._rotina_revisoes())

    async def cog_unload(self):
        if self._task:
            self._task.cancel()

    async def _garantir_painel(self):
        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            return
        canal = guild.get_channel(CANAL_PARcerias_ID)
        if not isinstance(canal, discord.TextChannel):
            _LOG.error("Canal oficial de parcerias %s não encontrado.", CANAL_PARcerias_ID)
            return
        data = await _ler()
        painel_id = data.get("painel_mensagem_id")
        mensagem = None
        if painel_id:
            try:
                mensagem = await canal.fetch_message(int(painel_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                mensagem = None
        if mensagem:
            await mensagem.edit(embed=_embed_painel(), view=PainelSolicitarParceria())
        else:
            mensagem = await canal.send(embed=_embed_painel(), view=PainelSolicitarParceria())
            await _atualizar(lambda atual: {**(atual if isinstance(atual, dict) else {}), "painel_mensagem_id": mensagem.id})

    async def _rotina_revisoes(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                guild = self.bot.get_guild(GUILD_ID)
                if guild:
                    agora = int(time.time())
                    data = await _ler()
                    itens = data.get("solicitacoes", []) if isinstance(data, dict) else []
                    alterou = False
                    canal = guild.get_channel(CANAL_PARcerias_ID)
                    for item in itens:
                        if not isinstance(item, dict) or item.get("status") != "aprovada":
                            continue
                        vencimento = int(item.get("proxima_revisao") or 0)
                        if vencimento and vencimento <= agora:
                            item["status"] = "revisao_pendente"
                            item["revisao_solicitada_em"] = agora
                            alterou = True
                            if isinstance(canal, discord.TextChannel):
                                aviso = discord.Embed(
                                    title="NÊMESIS  ━  REVISÃO QUINZENAL DE PARCERIA",
                                    description=f"A parceria **{item.get('nome')}** atingiu o prazo de revisão de 15 dias. A administração deve verificar atividade, reciprocidade, reputação e cumprimento dos requisitos.",
                                    color=0xD4A017,
                                )
                                aviso.add_field(name="Protocolo", value=f"`{item.get('protocolo')}`", inline=True)
                                aviso.add_field(name="Responsável", value=f"<@{item.get('responsavel_id')}>", inline=True)
                                aviso.add_field(name="Convite", value=item.get("convite", "—"), inline=False)
                                aviso.set_footer(text="A revisão deve ser concluída pela administração autorizada.")
                                await canal.send(embed=aviso)
                    if alterou:
                        data["solicitacoes"] = itens
                        await _atualizar(lambda _: data)
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOG.exception("Falha na rotina de revisão quinzenal de parcerias.")
                await asyncio.sleep(300)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self._garantir_painel()
        except Exception:
            _LOG.exception("Não foi possível publicar/atualizar o painel de parcerias.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ParceriasRequisitos(bot))
