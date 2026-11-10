"""Candidaturas e revisões oficiais de parcerias da NÊMESIS."""
from __future__ import annotations
import asyncio, logging, time, uuid
from urllib.parse import urlparse
import discord
from discord.ext import commands
from utils.storage import carregar, atualizar_json
from utils.guild_config import membro_tem_lideranca

LOG = logging.getLogger(__name__)
GUILD_ID = 1563995879981981817
CANAL_PAINEL_ID = 1563995881655509058
ARQ_CANDIDATURAS = "solicitacoes_parcerias.json"
ARQ_PARCERIAS = "parcerias.json"
REVISAO_SEGUNDOS = 15 * 86400
VERMELHO = 0x8F1D2C
DOURADO = 0xB58A45


def convite_valido(valor: str) -> bool:
    try:
        p = urlparse(str(valor).strip())
        host = (p.hostname or "").lower()
        return p.scheme == "https" and host in {"discord.gg", "www.discord.gg", "discord.com", "www.discord.com"} and (host.endswith("discord.gg") or p.path.startswith("/invite/"))
    except (TypeError, ValueError):
        return False


async def ler_candidaturas():
    dados = await carregar(ARQ_CANDIDATURAS, {"candidaturas": [], "painel_mensagem_id": None})
    if not isinstance(dados, dict):
        return {"candidaturas": [], "painel_mensagem_id": None}
    dados.setdefault("candidaturas", [])
    return dados


async def atualizar_candidaturas(fn):
    return await atualizar_json(ARQ_CANDIDATURAS, {"candidaturas": [], "painel_mensagem_id": None}, fn)


def embed_painel():
    e = discord.Embed(
        title="NÊMESIS  |  DIRETORIA DE RELAÇÕES INSTITUCIONAIS",
        description=(
            "## CENTRAL DE CANDIDATURAS DE PARCERIA\n"
            "A NÊMESIS estabelece alianças com comunidades que compartilham padrões elevados "
            "de integridade, organização e crescimento sustentável. Toda candidatura passa "
            "por avaliação administrativa; o envio não garante aprovação.\n\n"
            "### CRITÉRIOS DE ELEGIBILIDADE\n"
            "◈ **Estrutura:** identidade, canais e finalidade claramente definidos.\n"
            "◈ **Atividade:** participação recorrente e comunidade genuinamente ativa.\n"
            "◈ **Governança:** equipe administrativa responsável e acessível.\n"
            "◈ **Integridade:** sem evidências consistentes de golpes, fraudes ou práticas abusivas.\n"
            "◈ **Compatibilidade:** objetivos e público alinhados aos da NÊMESIS.\n"
            "◈ **Reciprocidade:** divulgação equilibrada, sem spam ou práticas artificiais.\n"
            "◈ **Transparência:** convite válido e informações verdadeiras.\n\n"
            "### PADRÃO DE SELEÇÃO — RIGOROSO\n"
            "A quantidade de membros, isoladamente, não garante aprovação. Serão avaliadas "
            "qualidade, atividade, reputação, organização e vantagem mútua. A administração "
            "poderá solicitar informações adicionais.\n\n"
            "### FLUXO INSTITUCIONAL\n"
            "**01** Candidatura  •  **02** Triagem  •  **03** Deliberação  •  "
            "**04** Formalização  •  **05** Revisão quinzenal"
        ),
        color=VERMELHO,
    )
    e.add_field(name="AUTORIDADE COMPETENTE", value="OCTÓGONO, Diretor Staff, Vice-Diretor Staff e Supervisor Staff, conforme a hierarquia oficial.", inline=False)
    e.add_field(name="CONFORMIDADE", value="Informações falsas, convites inválidos, publicidade enganosa ou violações dos critérios podem resultar em recusa ou encerramento da aliança.", inline=False)
    e.set_author(name="NÊMESIS • ALIANÇAS ESTRATÉGICAS")
    e.set_footer(text="DOCUMENTO INSTITUCIONAL • AVALIAÇÃO ADMINISTRATIVA")
    return e


def embed_candidatura(item):
    status = str(item.get("status", "pendente"))
    cores = {"pendente": DOURADO, "aprovada": 0x2D9D68, "recusada": 0xB93636}
    e = discord.Embed(
        title=f"NÊMESIS  |  DOSSIÊ DE CANDIDATURA • {item.get('protocolo', '—')}",
        description=(
            f"**Comunidade:** {item.get('nome', '—')}\n"
            f"**Responsável:** <@{item.get('responsavel_id')}>\n"
            f"**Membros declarados:** {item.get('membros', '—')}\n"
            f"**Segmento:** {item.get('segmento', '—')}\n\n"
            f"**Proposta institucional**\n{item.get('proposta', '—')}"
        ),
        color=cores.get(status, VERMELHO),
        timestamp=discord.utils.utcnow(),
    )
    e.add_field(name="CONVITE", value=str(item.get("convite", "—"))[:1024], inline=False)
    e.add_field(name="PROTOCOLO", value=str(item.get("protocolo", "—")), inline=True)
    e.add_field(name="SITUAÇÃO", value=status.upper(), inline=True)
    e.add_field(name="RECEBIDA", value=f"<t:{int(item.get('criada_em', time.time()))}:F>", inline=True)
    if item.get("decidida_por"):
        e.add_field(name="DELIBERAÇÃO POR", value=f"<@{item['decidida_por']}>", inline=True)
    if item.get("motivo_decisao"):
        e.add_field(name="FUNDAMENTAÇÃO", value=str(item["motivo_decisao"])[:1024], inline=False)
    if item.get("parceria_id"):
        e.add_field(name="REGISTRO DA ALIANÇA", value=str(item["parceria_id"]), inline=False)
    e.set_author(name="NÊMESIS • COMITÊ DE PARCERIAS")
    e.set_footer(text="USO ADMINISTRATIVO • HISTÓRICO AUDITÁVEL")
    return e


async def registrar_log(guild, titulo, descricao, *, cor=VERMELHO, view=None):
    try:
        from utils.registro_global import registrar
        return await registrar(guild, "parcerias", titulo, descricao, cor=cor, view=view)
    except Exception:
        LOG.exception("Falha na auditoria de parceria: %s", titulo)
        return False



def _card_parceria_view(origem: discord.ui.View, embed: discord.Embed | None = None,
                        titulo: str = "COMITÊ DE PARCERIAS", descricao: str = "") -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    texto = _texto_embed_componentes(embed) if embed else f"## {titulo}\n{descricao}".strip()
    componentes = [
        discord.ui.TextDisplay(texto[:3900]),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ]
    botoes = []
    for item in origem.children:
        if isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
            botoes.append(novo)
    for inicio in range(0, len(botoes), 5):
        componentes.append(discord.ui.ActionRow(*botoes[inicio:inicio + 5]))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# NÊMESIS • Alianças e Parcerias"),
    ])
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


class FormularioCandidatura(discord.ui.Modal, title="Candidatura institucional NÊMESIS"):
    nome = discord.ui.TextInput(label="Nome oficial da comunidade", max_length=80)
    convite = discord.ui.TextInput(label="Convite permanente do Discord", max_length=200, placeholder="https://discord.gg/...")
    membros = discord.ui.TextInput(label="Quantidade aproximada de membros", max_length=12, placeholder="Ex.: 850")
    segmento = discord.ui.TextInput(label="Segmento e finalidade", max_length=100)
    proposta = discord.ui.TextInput(label="Apresentação e proposta de reciprocidade", style=discord.TextStyle.paragraph, min_length=30, max_length=900)

    async def on_submit(self, interaction):
        if interaction.guild_id != GUILD_ID:
            await interaction.response.send_message("Procedimento exclusivo da NÊMESIS.", ephemeral=True)
            return
        if not convite_valido(self.convite.value):
            await interaction.response.send_message("Convite inválido. Use um link HTTPS de discord.gg ou discord.com/invite.", ephemeral=True)
            return
        try:
            membros = int(str(self.membros.value).replace(".", "").replace(",", "").strip())
            if not 1 <= membros <= 10_000_000:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Informe uma quantidade válida de membros.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        protocolo = uuid.uuid4().hex[:10].upper()
        item = {
            "id": protocolo.lower(), "protocolo": protocolo, "guild_id": GUILD_ID,
            "nome": str(self.nome.value).strip(), "convite": str(self.convite.value).strip(),
            "membros": membros, "segmento": str(self.segmento.value).strip(),
            "proposta": str(self.proposta.value).strip(), "responsavel_id": interaction.user.id,
            "criada_em": int(time.time()), "status": "pendente",
        }
        def inserir(dados):
            if not isinstance(dados, dict):
                dados = {"candidaturas": [], "painel_mensagem_id": None}
            dados.setdefault("candidaturas", []).append(item)
            return dados
        await atualizar_candidaturas(inserir)
        descricao_log = (
            f"**Protocolo:** {protocolo}\n**Comunidade:** {item['nome']}\n"
            f"**Responsável:** {interaction.user.mention} (ID: {interaction.user.id})\n"
            f"**Membros declarados:** {membros}\n**Segmento:** {item['segmento']}\n"
            f"**Convite:** {item['convite']}\n**Proposta:** {item['proposta']}\n"
            "**Situação:** aguardando deliberação administrativa."
        )
        view = _card_parceria_view(
            DecisaoCandidaturaView(item["id"]), None,
            "NOVA CANDIDATURA DE PARCERIA", descricao_log,
        )
        await registrar_log(
            interaction.guild, "Nova candidatura de parceria recebida",
            descricao_log, cor=DOURADO, view=view,
        )
        await interaction.followup.send(
            f"Candidatura protocolada. Protocolo: **{protocolo}**. "
            "O envio não representa aprovação; aguarde a avaliação administrativa.",
            ephemeral=True,
        )


def _texto_embed_componentes(embed: discord.Embed) -> str:
    partes = []
    if embed.author and embed.author.name:
        partes.append(f"-# {embed.author.name}")
    if embed.title:
        partes.append(f"## {embed.title}")
    if embed.description:
        partes.append(embed.description)
    for campo in embed.fields:
        partes.append(f"### {campo.name}\n{campo.value}")
    if embed.footer and embed.footer.text:
        partes.append(f"-# {embed.footer.text}")
    return "\n\n".join(partes)


class PainelCandidaturaView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        botao = discord.ui.Button(label="Apresentar candidatura", style=discord.ButtonStyle.primary, emoji="🤝", custom_id="nemesis:parcerias:candidatar")
        botao.callback = self.candidatar
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(_texto_embed_componentes(embed_painel())),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(botao),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Nêmesis Systeam"),
            accent_colour=VERMELHO,
        ))

    async def candidatar(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID:
            await interaction.response.send_message("Ação exclusiva da NÊMESIS.", ephemeral=True)
            return
        await interaction.response.send_modal(FormularioCandidatura())


class ModalRecusa(discord.ui.Modal, title="Fundamentação da recusa"):
    motivo = discord.ui.TextInput(label="Motivo da decisão", style=discord.TextStyle.paragraph, min_length=8, max_length=700)

    def __init__(self, protocolo, origem, mensagem_id, canal_id):
        super().__init__()
        self.protocolo = protocolo
        self.origem = origem
        self.mensagem_id = mensagem_id
        self.canal_id = canal_id

    async def on_submit(self, interaction):
        await self.origem._decidir(
            interaction, False, str(self.motivo.value).strip(),
            mensagem_id=self.mensagem_id, canal_id=self.canal_id,
        )


class DecisaoCandidaturaView(discord.ui.View):
    def __init__(self, protocolo):
        super().__init__(timeout=None)
        self.protocolo = protocolo
        b1 = discord.ui.Button(label="Aprovar e formalizar", style=discord.ButtonStyle.success, emoji="✅", custom_id=f"nemesis:parcerias:aprovar:{protocolo}")
        b2 = discord.ui.Button(label="Recusar candidatura", style=discord.ButtonStyle.danger, emoji="❌", custom_id=f"nemesis:parcerias:recusar:{protocolo}")
        b1.callback = self._aprovar
        b2.callback = self._recusar
        self.add_item(b1)
        self.add_item(b2)

    def autorizado(self, interaction):
        return interaction.guild_id == GUILD_ID and isinstance(interaction.user, discord.Member) and membro_tem_lideranca(interaction.user)

    async def _aprovar(self, interaction):
        await self._decidir(interaction, True)

    async def _recusar(self, interaction):
        if not self.autorizado(interaction):
            await interaction.response.send_message("Somente o OCTÓGONO e a administração autorizada podem deliberar.", ephemeral=True)
            return
        mensagem_id = interaction.message.id if interaction.message else None
        canal_id = interaction.channel_id
        await interaction.response.send_modal(ModalRecusa(self.protocolo, self, mensagem_id, canal_id))

    async def _decidir(self, interaction, aprovar, motivo=None, mensagem_id=None, canal_id=None):
        if not self.autorizado(interaction):
            if not interaction.response.is_done():
                await interaction.response.send_message("Somente o OCTÓGONO e a administração autorizada podem deliberar.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = await ler_candidaturas()
        item = next((x for x in dados.get("candidaturas", []) if isinstance(x, dict) and x.get("id") == self.protocolo), None)
        if not item or item.get("status") != "pendente":
            await interaction.followup.send("Candidatura já processada ou indisponível.", ephemeral=True)
            return
        parceria = None
        aviso_cargo = None
        if aprovar:
            from cogs.parcerias import registrar_parceria_aprovada
            parceria, aviso_cargo = await registrar_parceria_aprovada(interaction.guild, item, interaction.user)
            if parceria is None:
                await interaction.followup.send("Não foi possível formalizar a aliança. A candidatura continua pendente.", ephemeral=True)
                return
        agora = int(time.time())
        status = "aprovada" if aprovar else "recusada"
        def salvar_decisao(atual):
            if not isinstance(atual, dict):
                atual = {"candidaturas": [], "painel_mensagem_id": None}
            for registro in atual.get("candidaturas", []):
                if isinstance(registro, dict) and registro.get("id") == self.protocolo and registro.get("status") == "pendente":
                    registro.update({
                        "status": status, "decidida_em": agora, "decidida_por": interaction.user.id,
                        "motivo_decisao": motivo or "Aprovada após avaliação administrativa.",
                        "parceria_id": parceria.get("id") if parceria else None,
                    })
                    break
            return atual
        await atualizar_candidaturas(salvar_decisao)
        item.update({"status": status, "decidida_em": agora, "decidida_por": interaction.user.id, "motivo_decisao": motivo or "Aprovada após avaliação administrativa."})
        if parceria:
            item["parceria_id"] = parceria.get("id")
        try:
            mensagem_origem = interaction.message
            if mensagem_origem is None and mensagem_id and canal_id:
                canal_origem = await interaction.guild.fetch_channel(int(canal_id))
                mensagem_origem = await canal_origem.fetch_message(int(mensagem_id))
            if mensagem_origem is not None:
                await mensagem_origem.edit(
                    view=_card_parceria_view(
                        discord.ui.View(timeout=120), embed_candidatura(item)
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError, TypeError, ValueError):
            LOG.exception("Falha ao atualizar dossiê %s", self.protocolo)
        await registrar_log(
            interaction.guild, "Candidatura aprovada e aliança formalizada" if aprovar else "Candidatura recusada",
            f"**Protocolo:** {self.protocolo.upper()}\n**Comunidade:** {item.get('nome')}\n"
            f"**Decisão:** {status.upper()}\n**Autoridade:** {interaction.user.mention}\n"
            f"**Fundamentação:** {item.get('motivo_decisao')}\n"
            f"**Registro da parceria:** {parceria.get('id') if parceria else 'Não aplicável'}",
            cor=0x2D9D68 if aprovar else 0xB93636,
        )
        extra = f" Aviso: {aviso_cargo}" if aviso_cargo else ""
        await interaction.followup.send(("Parceria aprovada, registrada e publicada." if aprovar else "Candidatura recusada com justificativa registrada.") + extra, ephemeral=True)


class RevisaoParceriaView(discord.ui.View):
    def __init__(self, parceria_id):
        super().__init__(timeout=None)
        self.parceria_id = parceria_id
        b1 = discord.ui.Button(label="Manter por mais 15 dias", style=discord.ButtonStyle.success, emoji="✅", custom_id=f"nemesis:parcerias:manter:{parceria_id}")
        b2 = discord.ui.Button(label="Suspender aliança", style=discord.ButtonStyle.danger, emoji="⛔", custom_id=f"nemesis:parcerias:suspender:{parceria_id}")
        b1.callback = self._manter
        b2.callback = self._suspender
        self.add_item(b1)
        self.add_item(b2)

    async def concluir(self, interaction, manter):
        if interaction.guild_id != GUILD_ID or not isinstance(interaction.user, discord.Member) or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Somente o OCTÓGONO e a administração autorizada podem concluir revisões.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        agora = int(time.time())
        resultado = {}
        def aplicar(dados):
            if not isinstance(dados, dict):
                dados = {}
            lista = dados.get(str(GUILD_ID), [])
            for item in lista:
                if isinstance(item, dict) and item.get("id") == self.parceria_id and item.get("status") == "revisao_pendente":
                    item.update({
                        "status": "ativa" if manter else "suspensa",
                        "revisado_por_id": interaction.user.id, "revisado_em": agora,
                        "proxima_revisao": agora + REVISAO_SEGUNDOS if manter else None,
                        "atualizado_em": agora,
                    })
                    resultado.update(item)
                    break
            dados[str(GUILD_ID)] = lista
            return dados
        await atualizar_json(ARQ_PARCERIAS, {}, aplicar)
        if not resultado:
            await interaction.followup.send("Revisão já concluída ou parceria indisponível.", ephemeral=True)
            return
        try:
            await interaction.message.edit(
                view=_card_parceria_view(
                    discord.ui.View(timeout=120),
                    discord.Embed(
                        title="NÊMESIS  |  RESULTADO DA REVISÃO QUINZENAL",
                        description="**Comunidade:** " + str(resultado.get("nome")) + "\n**Resultado:** " + ("Mantida por mais 15 dias" if manter else "Suspensa") + "\n**Responsável:** " + interaction.user.mention,
                        color=0x2D9D68 if manter else 0xB93636,
                    ),
                ),
            )
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            LOG.exception("Falha ao atualizar cartão de revisão %s", self.parceria_id)
        try:
            canal_id = resultado.get("canal_id")
            mensagem_id = resultado.get("mensagem_id")
            canal_publico = interaction.guild.get_channel(int(canal_id)) if canal_id else None
            if isinstance(canal_publico, discord.TextChannel) and mensagem_id:
                mensagem_publica = await canal_publico.fetch_message(int(mensagem_id))
                from cogs.parcerias import _embed_parceria_publica, ParceriaLayoutView
                embed_publico = _embed_parceria_publica(resultado, interaction.guild)
                await mensagem_publica.edit(content=None, embeds=[], attachments=[])
                await mensagem_publica.edit(
                    view=ParceriaLayoutView(
                        int(resultado["cargo_id"]) if manter and resultado.get("cargo_id") else None,
                        embed_publico,
                    ),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
            LOG.exception("Falha ao sincronizar anúncio público da parceria revisada %s", self.parceria_id)
        await registrar_log(interaction.guild, "Revisão quinzenal concluída", f"**Parceria:** {resultado.get('nome')}\n**Resultado:** {'Mantida por 15 dias' if manter else 'Suspensa'}\n**Responsável:** {interaction.user.mention}", cor=0x2D9D68 if manter else 0xB93636)
        await interaction.followup.send("Revisão registrada e auditada.", ephemeral=True)

    async def _manter(self, interaction):
        await self.concluir(interaction, True)

    async def _suspender(self, interaction):
        await self.concluir(interaction, False)


class RequisitosParcerias(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tarefa = None
        self._painel_lock = asyncio.Lock()

    async def cog_load(self):
        self.bot.add_view(PainelCandidaturaView())
        dados = await ler_candidaturas()
        for item in dados.get("candidaturas", []):
            if isinstance(item, dict) and item.get("status") == "pendente" and item.get("id"):
                self.bot.add_view(_card_parceria_view(
                    DecisaoCandidaturaView(str(item["id"])), None,
                    "CANDIDATURA DE PARCERIA", "Painel administrativo de deliberação.",
                ))
        parcerias = await carregar(ARQ_PARCERIAS, {})
        if isinstance(parcerias, dict):
            for lista in parcerias.values():
                if isinstance(lista, list):
                    for item in lista:
                        if isinstance(item, dict) and item.get("status") == "revisao_pendente" and item.get("id"):
                            self.bot.add_view(_card_parceria_view(
                                RevisaoParceriaView(str(item["id"])), None,
                                "REVISÃO QUINZENAL DE ALIANÇA",
                                "Painel administrativo para renovar ou suspender a parceria.",
                            ))
        self.tarefa = asyncio.create_task(self.rotina_revisoes())

    async def cog_unload(self):
        if self.tarefa:
            self.tarefa.cancel()

    async def garantir_painel(self):
        async with self._painel_lock:
            await self._garantir_painel_unico()

    async def _garantir_painel_unico(self):
        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            return
        canal = guild.get_channel(CANAL_PAINEL_ID)
        if canal is None:
            try:
                canal = await guild.fetch_channel(CANAL_PAINEL_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                LOG.error("Canal de parcerias não acessível: %s", CANAL_PAINEL_ID)
                return
        if not isinstance(canal, discord.TextChannel):
            LOG.error("Canal de requisitos não é canal de texto: %s", CANAL_PAINEL_ID)
            return
        dados = await ler_candidaturas()
        mensagem = None
        if dados.get("painel_mensagem_id"):
            try:
                mensagem = await canal.fetch_message(int(dados["painel_mensagem_id"]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                mensagem = None
        if mensagem is None and self.bot.user:
            try:
                async for candidata in canal.history(limit=60):
                    if (
                        candidata.author.id == self.bot.user.id
                        and candidata.embeds
                        and candidata.embeds[0].title == "NÊMESIS  |  DIRETORIA DE RELAÇÕES INSTITUCIONAIS"
                    ):
                        mensagem = candidata
                        break
            except (discord.Forbidden, discord.HTTPException):
                LOG.exception("Não foi possível procurar um painel de parcerias anterior.")
        if mensagem:
            await mensagem.edit(content=None, embeds=[], attachments=[], view=PainelCandidaturaView(), allowed_mentions=discord.AllowedMentions.none())
            await atualizar_candidaturas(lambda atual: {**(atual if isinstance(atual, dict) else {}), "painel_mensagem_id": mensagem.id})
        else:
            mensagem = await canal.send(view=PainelCandidaturaView(), allowed_mentions=discord.AllowedMentions.none())
            await atualizar_candidaturas(lambda atual: {**(atual if isinstance(atual, dict) else {}), "painel_mensagem_id": mensagem.id})

    async def rotina_revisoes(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                agora = int(time.time())
                vencidas = []
                def marcar(dados):
                    if not isinstance(dados, dict):
                        dados = {}
                    lista = dados.get(str(GUILD_ID), [])
                    for item in lista:
                        if not isinstance(item, dict) or item.get("status") != "ativa":
                            continue
                        prazo = int(item.get("proxima_revisao") or 0)
                        if not prazo:
                            referencia = int(item.get("atualizado_em") or item.get("criado_em") or agora)
                            prazo = referencia + REVISAO_SEGUNDOS
                            item["proxima_revisao"] = prazo
                        if prazo <= agora:
                            item["status"] = "revisao_pendente"
                            item["revisao_solicitada_em"] = agora
                            vencidas.append(dict(item))
                    dados[str(GUILD_ID)] = lista
                    return dados
                await atualizar_json(ARQ_PARCERIAS, {}, marcar)
                guild = self.bot.get_guild(GUILD_ID)
                if guild:
                    for item in vencidas:
                        descricao_revisao = (
                            f"**Comunidade:** {item.get('nome')}\n**Registro:** {item.get('id')}\n"
                            "**Ação necessária:** verificar atividade, reputação, reciprocidade e conformidade."
                        )
                        view_revisao = _card_parceria_view(
                            RevisaoParceriaView(str(item.get("id"))), None,
                            "REVISÃO QUINZENAL DE ALIANÇA", descricao_revisao,
                        )
                        await registrar_log(
                            guild, "Revisão quinzenal de aliança pendente",
                            descricao_revisao, cor=DOURADO, view=view_revisao,
                        )
                await asyncio.sleep(1800)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("Falha na rotina de revisão de parcerias.")
                await asyncio.sleep(300)

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            await self.garantir_painel()
        except Exception:
            LOG.exception("Não foi possível publicar/atualizar o painel de parcerias.")


async def setup(bot):
    await bot.add_cog(RequisitosParcerias(bot))
