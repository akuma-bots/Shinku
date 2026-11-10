from utils.apresentacao import criar_embed, aplicar_identidade_servidor
import asyncio
import logging
import hashlib
import aiohttp
import discord
from discord.ext import commands
from utils import revisoes, auditoria
from utils.guild_config import membro_tem_lideranca, membro_pode_revisar_categoria

CORES = {"pvp": 0x9F2035, "pve": 0x8B6A35, "missao": 0x9F2035, "contribuicao": 0x8B6A35, "especial": 0x754A9E}
_ABRIR_REVISAO_LOCK = asyncio.Lock()


async def _hash_imagem(url: str):
    """Baixa a imagem e calcula um hash do conteúdo — usado pra detectar se
    a mesma print está sendo reaproveitada em outra prova."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resposta:
                if resposta.status != 200:
                    return None
                dados = await resposta.read()
                return hashlib.sha256(dados).hexdigest()
    except Exception:
        return None


def _embed_revisao(revisao: dict, guild: discord.Guild = None, bot: commands.Bot = None) -> discord.Embed:
    tipo = str(revisao.get("tipo") or "missao").lower()
    autor_id = revisao.get("autor_id")
    auxiliar_id = revisao.get("auxiliar_id")
    titulo = str(revisao.get("titulo") or "Comprovante de atividade")
    descricao = str(revisao.get("descricao") or "Sem observações adicionais.")
    embed = criar_embed(
        title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  CENTRAL DE VALIDAÇÃO",
        description=(
            f"**◈ COMPROVANTE RECEBIDO**  ·  **{tipo.replace('_', ' ').upper()}**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Atividade:** {titulo}\n"
            f"**Relato do participante:**\n{descricao[:1200]}"
        ),
        color=CORES.get(tipo, 0x9F2035),
    )
    embed.set_author(name="NÊMESIS  /  AUDITORIA DE OPERAÇÕES")
    embed.add_field(name="◈ PARTICIPANTE", value=f"<@{autor_id}>" if autor_id else "Não identificado", inline=True)
    embed.add_field(name="◈ CATEGORIA", value=tipo.replace("_", " ").title(), inline=True)
    embed.add_field(name="◈ PROTOCOLO", value=f"`{revisao.get('id', '—')}`", inline=True)
    embed.add_field(name="◈ REFERÊNCIA", value=f"`{revisao.get('referencia_id') or '—'}`", inline=True)
    if auxiliar_id:
        embed.add_field(name="◈ COLABORADOR", value=f"<@{int(auxiliar_id)}>", inline=True)
    recompensa = revisao.get("recompensa_xp")
    if recompensa is not None:
        try:
            recompensa = max(0, int(recompensa))
        except (TypeError, ValueError, OverflowError):
            recompensa = 0
        embed.add_field(
            name="◈ RECOMPENSA PREVISTA",
            value=f"**+{recompensa:,} XP**".replace(",", "."),
            inline=True,
        )
    enviado = revisao.get("timestamp")
    if isinstance(enviado, (int, float)):
        embed.add_field(name="◈ RECEBIDO", value=f"<t:{int(enviado)}:F>\n<t:{int(enviado)}:R>", inline=True)
    if revisao.get("motivo_rejeicao"):
        embed.add_field(
            name="◈ MOTIVO DA REJEIÇÃO",
            value=str(revisao.get("motivo_rejeicao"))[:800],
            inline=False,
        )
    if revisao.get("status") == "pendente":
        embed.add_field(
            name="◈ DIRETRIZES DE ANÁLISE",
            value="Confira a autenticidade, a correspondência com o objetivo e a legibilidade da evidência. A recompensa em XP só será aplicada após aprovação.",
            inline=False,
        )
    embed.set_image(url=revisao["print_url"])
    embed.set_footer(text="NÊMESIS  •  CENTRAL DE VALIDAÇÃO  •  DECISÃO REGISTRADA EM AUDITORIA")
    return aplicar_identidade_servidor(embed, guild, bot, banner=False)

def _view_link_revisao(url: str) -> discord.ui.View:
    """Dá ao registro um atalho direto para a evidência com os controles ativos."""
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Button(
            label="Abrir evidência e revisar",
            style=discord.ButtonStyle.link,
            emoji="🔎",
            url=url,
        )
    )
    return view


def _view_revisao(revisao_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Aprovar", style=discord.ButtonStyle.success,
                                     emoji="✅", custom_id=f"revisao:aprovar:{revisao_id}"))
    view.add_item(discord.ui.Button(label="Rejeitar", style=discord.ButtonStyle.danger,
                                     emoji="❌", custom_id=f"revisao:rejeitar:{revisao_id}"))
    return view



def _card_revisao_view(origem: discord.ui.View, embed: discord.Embed | None = None,
                       titulo: str = "CENTRAL DE VALIDAÇÃO", descricao: str = "") -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    partes = [f"## {embed.title if embed and embed.title else titulo}"]
    if embed and embed.description:
        partes.append(embed.description)
    elif descricao:
        partes.append(descricao)
    if embed:
        for campo in embed.fields:
            partes.append(f"**{campo.name}**\n{campo.value}")
        if embed.image and embed.image.url:
            partes.append(f"[Abrir evidência anexada]({embed.image.url})")
        if embed.footer and embed.footer.text:
            partes.append(f"-# {embed.footer.text}")
    componentes = [
        discord.ui.TextDisplay("\n\n".join(partes)[:3900]),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ]
    seletores, botoes = [], []
    for item in origem.children:
        if isinstance(item, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, options=list(item.options),
                custom_id=item.custom_id, disabled=item.disabled,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
            botoes.append(novo)
    for seletor in seletores:
        componentes.append(discord.ui.ActionRow(seletor))
    for inicio in range(0, len(botoes), 5):
        componentes.append(discord.ui.ActionRow(*botoes[inicio:inicio + 5]))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# NÊMESIS • Auditoria de Operações"),
    ])
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


STATUS_LABELS = {
    "pendente": ("⏳ Pendentes", 0xFEE75C),
    "aprovada": ("✅ Aprovadas", 0x57F287),
    "rejeitada": ("❌ Recusadas", 0xED4245),
}
TIPO_LABELS = {
    "todos": "Todas as categorias",
    "missao": "Missões",
    "contribuicao": "Contribuições",
    "especial": "Operações especiais",
    "pvp": "PvP",
    "pve": "PvE",
}
ITENS_POR_PAGINA = 8


def _contagens_provas(itens: list[dict]) -> dict:
    return {
        status: sum(1 for item in itens if item.get("status") == status)
        for status in STATUS_LABELS
    }


def _filtrar_provas(itens: list[dict], status: str, tipo: str = "todos") -> list[dict]:
    resultado = [
        item for item in itens
        if isinstance(item, dict)
        and item.get("status") == status
        and (tipo == "todos" or str(item.get("tipo") or "").lower() == tipo)
    ]
    return sorted(resultado, key=lambda item: float(item.get("timestamp", 0) or 0), reverse=True)


def _embed_painel_provas(
    guild: discord.Guild,
    status: str,
    itens: list[dict],
    tipo: str = "todos",
    pagina: int = 0,
    total: int = None,
    contagens: dict = None,
    bot: commands.Bot = None,
) -> discord.Embed:
    label, cor = STATUS_LABELS.get(status, STATUS_LABELS["pendente"])
    total = len(itens) if total is None else max(0, int(total))
    total_paginas = max(1, (total + ITENS_POR_PAGINA - 1) // ITENS_POR_PAGINA)
    pagina = max(0, min(int(pagina), total_paginas - 1))
    inicio = pagina * ITENS_POR_PAGINA
    exibidos = itens[inicio:inicio + ITENS_POR_PAGINA]
    contagens = contagens or _contagens_provas(itens)
    embed = criar_embed(
        title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — CENTRAL DE VALIDAÇÃO ・✦",
        description=(
            "⟡・Acompanhamento operacional de evidências, decisões e histórico de análise.\n"
            f"**Status:** {label}  •  **Categoria:** {TIPO_LABELS.get(tipo, tipo.title())}\n"
            f"**Registros encontrados:** {total}  •  **Página:** {pagina + 1}/{total_paginas}"
        ),
        color=cor,
    )
    embed.add_field(name="⏳ PENDENTES", value=f"**{contagens.get('pendente', 0)}**", inline=True)
    embed.add_field(name="✓ APROVADAS", value=f"**{contagens.get('aprovada', 0)}**", inline=True)
    embed.add_field(name="✕ RECUSADAS", value=f"**{contagens.get('rejeitada', 0)}**", inline=True)
    if not exibidos:
        embed.add_field(
            name="◈ NENHUM REGISTRO",
            value="Não há provas correspondentes aos filtros selecionados.",
            inline=False,
        )
    for item in exibidos:
        tipo_item = str(item.get("tipo") or "—").lower()
        autor = f"<@{item.get('autor_id')}>" if item.get("autor_id") else "Não identificado"
        auxiliar = f"<@{item.get('auxiliar_id')}>" if item.get("auxiliar_id") else "Não informado"
        revisor = f"<@{item.get('revisor_id')}>" if item.get("revisor_id") else "Aguardando análise"
        timestamp = item.get("timestamp")
        data = f"<t:{int(timestamp)}:F> · <t:{int(timestamp)}:R>" if isinstance(timestamp, (int, float)) else "Data indisponível"
        recompensa = item.get("recompensa_xp")
        linha_recompensa = ""
        if recompensa is not None:
            try:
                recompensa = max(0, int(recompensa))
            except (TypeError, ValueError, OverflowError):
                recompensa = 0
            linha_recompensa = f"**Recompensa:** +{recompensa:,} XP  •  ".replace(",", ".")
        detalhes = (
            f"**Protocolo:** `{item.get('id', '—')}`  •  **Referência:** `{str(item.get('referencia_id') or '—')[:60]}`\n"
            f"**Participante:** {autor}  •  **Auxiliar:** {auxiliar}\n"
            f"**Categoria:** {TIPO_LABELS.get(tipo_item, tipo_item.upper())}  •  {linha_recompensa}**Enviado:** {data}\n"
            f"**Revisor:** {revisor}"
        )
        motivo = str(item.get("motivo_rejeicao") or "").strip()
        if status == "rejeitada" and motivo:
            detalhes += f"\n**Justificativa:** {motivo[:300]}"
        embed.add_field(
            name=f"◈ {str(item.get('titulo') or 'Comprovante sem título')[:245]}",
            value=detalhes[:1024],
            inline=False,
        )
    embed.set_footer(
        text=f"NÊMESIS • AUDITORIA OPERACIONAL • Exibindo {len(exibidos)} de {total} registros"
    )
    return aplicar_identidade_servidor(embed, guild, bot, banner=True)


class FiltroPainelProvas(discord.ui.Select):
    def __init__(
        self,
        cog: "Revisoes",
        guild_id: int,
        owner_id: int,
        status: str = "pendente",
        tipo: str = "todos",
    ):
        self.cog = cog
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.status = status
        self.tipo = tipo
        options = [
            discord.SelectOption(label=STATUS_LABELS[chave][0].split(" ", 1)[1], value=chave, emoji=STATUS_LABELS[chave][0].split(" ", 1)[0], default=status == chave)
            for chave in STATUS_LABELS
        ]
        super().__init__(
            placeholder="◈ Filtrar por situação",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.cog._autorizar_painel(interaction, self.owner_id):
            return
        await self.cog._atualizar_painel(
            interaction, self.owner_id, self.values[0], self.tipo, 0
        )


class FiltroTipoProvas(discord.ui.Select):
    def __init__(
        self,
        cog: "Revisoes",
        guild_id: int,
        owner_id: int,
        status: str = "pendente",
        tipo: str = "todos",
    ):
        self.cog = cog
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.status = status
        options = [
            discord.SelectOption(label=nome, value=chave, default=tipo == chave)
            for chave, nome in TIPO_LABELS.items()
        ]
        super().__init__(
            placeholder="◈ Filtrar por categoria",
            min_values=1,
            max_values=1,
            options=options,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.cog._autorizar_painel(interaction, self.owner_id):
            return
        await self.cog._atualizar_painel(
            interaction, self.owner_id, self.status, self.values[0], 0
        )


class PainelProvasView(discord.ui.View):
    def __init__(
        self,
        cog: "Revisoes",
        guild_id: int,
        owner_id: int,
        status: str = "pendente",
        tipo: str = "todos",
        pagina: int = 0,
        total: int = 0,
    ):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.status = status
        self.tipo = tipo
        self.pagina = pagina
        self.total = total
        self.add_item(FiltroPainelProvas(cog, guild_id, owner_id, status, tipo))
        self.add_item(FiltroTipoProvas(cog, guild_id, owner_id, status, tipo))
        paginas = max(1, (total + ITENS_POR_PAGINA - 1) // ITENS_POR_PAGINA)
        self.anterior.disabled = pagina <= 0
        self.proxima.disabled = pagina >= paginas - 1

    async def _mudar_pagina(self, interaction: discord.Interaction, delta: int):
        if not await self.cog._autorizar_painel(interaction, self.owner_id):
            return
        await self.cog._atualizar_painel(
            interaction, self.owner_id, self.status, self.tipo, self.pagina + delta
        )

    @discord.ui.button(label="Anterior", style=discord.ButtonStyle.secondary, emoji="◀️", row=2)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._mudar_pagina(interaction, -1)

    @discord.ui.button(label="Próxima", style=discord.ButtonStyle.secondary, emoji="▶️", row=2)
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._mudar_pagina(interaction, 1)

    @discord.ui.button(label="Atualizar", style=discord.ButtonStyle.success, emoji="🔄", row=2)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog._autorizar_painel(interaction, self.owner_id):
            return
        await self.cog._atualizar_painel(
            interaction, self.owner_id, self.status, self.tipo, self.pagina
        )


class MotivoRejeicaoModal(discord.ui.Modal, title="Rejeitar comprovante"):
    motivo = discord.ui.TextInput(
        label="Motivo da rejeição",
        placeholder="Explique o que precisa ser corrigido na evidência ou no cumprimento do objetivo.",
        style=discord.TextStyle.paragraph,
        min_length=8,
        max_length=800,
        required=True,
    )

    def __init__(self, guild: discord.Guild, revisao_id: str, mensagem: discord.Message, revisor: discord.Member, bot: commands.Bot = None):
        super().__init__(timeout=300)
        self.guild = guild
        self.revisao_id = revisao_id
        self.mensagem = mensagem
        self.revisor = revisor
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            revisao_atual = await revisoes.get(self.guild.id, self.revisao_id)
            if not revisao_atual:
                await interaction.followup.send("Esta prova já foi processada ou não está mais disponível.", ephemeral=True)
                return
            if not membro_pode_revisar_categoria(interaction.user, revisao_atual.get("tipo")):
                await interaction.followup.send("Somente o OCTÓGONO pode decidir sobre provas de missão.", ephemeral=True)
                return
            motivo = str(self.motivo.value).strip()
            revisao = await revisoes.rejeitar(self.guild.id, self.revisao_id, self.revisor.id, motivo)
            if not revisao:
                await interaction.followup.send("Esta prova já foi processada ou não está mais disponível.", ephemeral=True)
                return
            embed = _embed_revisao(revisao, self.guild, self.bot)
            embed.color = 0x9F2035
            embed.add_field(name="✕ DECISÃO", value="**REJEITADA**", inline=True)
            embed.add_field(name="◈ RESPONSÁVEL PELA ANÁLISE", value=self.revisor.mention, inline=True)
            embed.add_field(name="◈ JUSTIFICATIVA", value=motivo[:800], inline=False)
            await self.mensagem.edit(embed=embed, view=None)
            await auditoria.registrar(
                self.guild,
                "✕ Comprovante rejeitado",
                f"Atividade: {revisao.get('titulo', '—')}\nTipo: {revisao.get('tipo', '—')}\n"
                f"Participante: <@{revisao.get('autor_id')}>\nRevisor: {self.revisor.mention}\n"
                f"Protocolo: {revisao.get('id', '—')}\nMotivo: {motivo}",
                cor=0x9F2035,
                categoria="sistemas",
            )
            autor = self.guild.get_member(int(revisao.get("autor_id") or 0))
            if autor:
                try:
                    await autor.send(f"Sua prova para {revisao.get('titulo', 'atividade')} foi rejeitada.\nMotivo: {motivo}\nCorrija os pontos indicados e envie uma nova evidência.")
                except discord.Forbidden:
                    pass
            await interaction.followup.send("A prova foi rejeitada. A justificativa foi registrada na auditoria e enviada ao participante.", ephemeral=True)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Falha ao concluir rejeição da revisão %s.", self.revisao_id)
            await interaction.followup.send("Não foi possível concluir a rejeição. Confira os registros e tente novamente.", ephemeral=True)



class Revisoes(commands.Cog):
    """Motor de aprovação manual por print. Outros cogs (missões, PvP, PvE)
    chamam `abrir_revisao(...)` pra criar a pendência e postar o embed com
    botões no canal certo. Ao abrir, calcula um hash da imagem e avisa o
    revisor se a mesma print já foi usada antes. Quando um admin aprova ou
    rejeita, o processador do tipo é chamado automaticamente, e a decisão
    fica registrada no canal de auditoria (se configurado)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}


    async def painel_provas(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if not await self._autorizar_painel(interaction, interaction.user.id):
            return
        todos = await revisoes.listar(interaction.guild.id)
        pendentes = _filtrar_provas(todos, "pendente", "todos")
        contagens = _contagens_provas(todos)
        embed = _embed_painel_provas(
            interaction.guild, "pendente", pendentes,
            total=len(pendentes), contagens=contagens, bot=self.bot,
        )
        await interaction.response.send_message(
            view=_card_revisao_view(
                PainelProvasView(self, interaction.guild.id, interaction.user.id, "pendente", "todos", 0, len(pendentes)),
                embed,
            ),
            ephemeral=True,
        )

    async def _autorizar_painel(self, interaction: discord.Interaction, owner_id: int) -> bool:
        permissoes = getattr(interaction.user, "guild_permissions", None)
        if (
            interaction.guild is None
            or interaction.user.id != owner_id
            or permissoes is None
            or not membro_tem_lideranca(interaction.user)
        ):
            await interaction.response.send_message(
                "Este painel é restrito ao administrador que o abriu. Reabra a Central Administrativa e selecione Revisão de provas.",
                ephemeral=True,
            )
            return False
        return True

    async def _atualizar_painel(
        self,
        interaction: discord.Interaction,
        owner_id: int,
        status: str,
        tipo: str,
        pagina: int,
    ):
        todos = await revisoes.listar(interaction.guild.id)
        filtrados = _filtrar_provas(todos, status, tipo)
        contagens = _contagens_provas(todos)
        total = len(filtrados)
        paginas = max(1, (total + ITENS_POR_PAGINA - 1) // ITENS_POR_PAGINA)
        pagina = max(0, min(int(pagina), paginas - 1))
        view = PainelProvasView(
            self, interaction.guild.id, owner_id, status, tipo, pagina, total
        )
        embed = _embed_painel_provas(
            interaction.guild, status, filtrados, tipo, pagina, total, contagens, self.bot
        )
        await interaction.response.edit_message(
            view=_card_revisao_view(view, embed)
        )

    async def abrir_revisao(
        self, guild: discord.Guild, canal: discord.abc.Messageable, *,
        tipo: str, autor_id: int, referencia_id: str, print_url: str,
        titulo: str, descricao: str = None, auxiliar_id: int = None,
        recompensa_xp: int = None,
    ) -> dict:
        # Serializa o ciclo completo de localizar/criar/publicar a prova.
        # O lock no storage evita registros duplicados; este lock também evita
        # duas mensagens Discord para o mesmo registro em chamadas concorrentes.
        async with _ABRIR_REVISAO_LOCK:
            return await self._abrir_revisao_sem_lock(
                guild, canal, tipo=tipo, autor_id=autor_id,
                referencia_id=referencia_id, print_url=print_url,
                titulo=titulo, descricao=descricao, auxiliar_id=auxiliar_id,
                recompensa_xp=recompensa_xp,
            )

    async def _abrir_revisao_sem_lock(self, guild: discord.Guild, canal: discord.abc.Messageable, *,
                             tipo: str, autor_id: int, referencia_id: str, print_url: str,
                             titulo: str, descricao: str = None,
                             auxiliar_id: int = None,
                             recompensa_xp: int = None) -> dict:
        # Só pode existir uma revisão pendente por referência e participante.
        # PvP é único por desafio; missões e demais categorias são únicas por
        # participante + atividade. A verificação fica dentro do lock que cobre
        # o ciclo completo, evitando duas mensagens para envios simultâneos.
        revisao = None
        existentes = await revisoes.listar(guild.id, status="pendente")
        revisao = next(
            (
                item for item in existentes
                if isinstance(item, dict)
                and str(item.get("tipo", "")).lower() == str(tipo).lower()
                and str(item.get("referencia_id")) == str(referencia_id)
                and (
                    tipo == "pvp"
                    or str(item.get("autor_id")) == str(autor_id)
                )
            ),
            None,
        )
        if revisao and revisao.get("mensagem_id"):
            return {**revisao, "_ja_existente": True}

        if revisao is None:
            revisao = await revisoes.criar_pendencia(
                guild.id, tipo, autor_id, referencia_id, print_url, titulo, descricao,
                auxiliar_id=auxiliar_id,
                recompensa_xp=recompensa_xp,
            )

        hash_imagem = await _hash_imagem(revisao.get("print_url") or print_url)
        duplicata = None
        if hash_imagem:
            await revisoes.definir_hash(guild.id, revisao["id"], hash_imagem)
            encontradas = await revisoes.buscar_por_hash(guild.id, hash_imagem, excluir_id=revisao["id"])
            if encontradas:
                duplicata = encontradas[0]

        embed = _embed_revisao(revisao, guild, self.bot)
        if duplicata:
            embed.add_field(
                name="⚠️ Possível print repetida",
                value=f"Esta mesma imagem já apareceu na revisão `{duplicata['id']}` ({duplicata['status']}). Confira com atenção antes de aprovar.",
                inline=False,
            )

        msg = await canal.send(view=_card_revisao_view(_view_revisao(revisao["id"]), embed))
        await revisoes.definir_mensagem(guild.id, revisao["id"], canal.id, msg.id)
        try:
            from utils.registro_global import registrar
            await registrar(
                guild,
                "missoes",
                f"Evidência enviada para revisão • {revisao.get('titulo', 'Atividade')}",
                f"Protocolo: `{revisao.get('id', '—')}`\n"
                f"Tipo: **{revisao.get('tipo', '—')}**\n"
                f"Participante: <@{revisao.get('autor_id')}> (`{revisao.get('autor_id')}`)\n"
                f"Status: **Pendente de revisão**\n"
                f"Prova original: {msg.jump_url}",
                cor=0xFEE75C,
                view=_card_revisao_view(
                    _view_link_revisao(msg.jump_url), embed,
                ),
            )
            await registrar(
                guild,
                "historico_membros",
                "Membro enviou evidência de missão",
                (
                    f"**Membro:** <@{revisao.get('autor_id')}> (ID: {revisao.get('autor_id')})\n"
                    f"**Atividade:** {revisao.get('titulo', 'Atividade')}\n"
                    f"**Protocolo:** {revisao.get('id', '—')}\n"
                    "**Situação:** Pendente de revisão."
                ),
                cor=0xFEE75C,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "Falha ao arquivar evidência %s no Registro Global.", revisao.get("id")
            )
        return revisao

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        data = interaction.data or {}
        custom_id = data.get("custom_id", "")
        if not isinstance(custom_id, str) or not custom_id.startswith("revisao:"):
            return

        if interaction.guild is None:
            return

        permissoes = getattr(interaction.user, "guild_permissions", None)
        if permissoes is None or not membro_tem_lideranca(interaction.user):
            await interaction.response.send_message("Somente a liderança autorizada pode revisar isso.", ephemeral=True)
            return

        partes = custom_id.split(":", 2)
        if len(partes) != 3 or partes[1] not in {"aprovar", "rejeitar", "confirmar_aprovar", "cancelar_aprovar"} or not partes[2]:
            await interaction.response.send_message("Ação de revisão inválida.", ephemeral=True)
            return
        _, acao, revisao_id = partes

        try:
            revisao_permissao = await revisoes.get(interaction.guild.id, revisao_id)
        except Exception:
            logging.getLogger(__name__).exception("Falha ao validar permissões da revisão %s.", revisao_id)
            await interaction.response.send_message("Não consegui validar esta revisão. Nenhuma decisão foi aplicada.", ephemeral=True)
            return
        if not revisao_permissao:
            await interaction.response.send_message("Essa revisão não existe mais.", ephemeral=True)
            return
        if not membro_pode_revisar_categoria(interaction.user, revisao_permissao.get("tipo")):
            await interaction.response.send_message("Somente o OCTÓGONO pode decidir sobre provas de missão.", ephemeral=True)
            return

        if acao == "cancelar_aprovar":
            await interaction.response.edit_message(
                view=_card_revisao_view(
                    discord.ui.View(timeout=120), None,
                    "APROVAÇÃO CANCELADA",
                    "A evidência continua pendente e poderá ser analisada novamente.",
                ),
            )
            return

        if acao == "aprovar":
            view = discord.ui.View(timeout=120)
            view.add_item(discord.ui.Button(
                label="Confirmar aprovação",
                style=discord.ButtonStyle.success,
                emoji="✅",
                custom_id=f"revisao:confirmar_aprovar:{revisao_id}",
            ))
            view.add_item(discord.ui.Button(
                label="Cancelar",
                style=discord.ButtonStyle.secondary,
                custom_id=f"revisao:cancelar_aprovar:{revisao_id}",
            ))
            await interaction.response.send_message(
                view=_card_revisao_view(
                    view, None, "CONFIRMAR APROVAÇÃO",
                    f"Protocolo: **{revisao_id}**\nA recompensa em XP será aplicada após a confirmação. Esta ação ficará registrada na auditoria.",
                ),
                ephemeral=True,
            )
            return

        if acao == "rejeitar":
            await interaction.response.send_modal(
                MotivoRejeicaoModal(interaction.guild, revisao_id, interaction.message, interaction.user, self.bot)
            )
            return

        # A consulta ao storage pode demorar; confirme a interação antes do I/O.
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            revisao = await revisoes.get(interaction.guild.id, revisao_id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Falha ao consultar a revisão %s antes da decisão.", revisao_id
            )
            await interaction.followup.send(
                "Não consegui consultar esta revisão no armazenamento. Nenhuma decisão foi aplicada; tente novamente.",
                ephemeral=True,
            )
            return
        if not revisao:
            await interaction.followup.send("Essa revisão não existe mais.", ephemeral=True)
            return
        if revisao["status"] != "pendente":
            await interaction.followup.send(f"Essa revisão já foi **{revisao['status']}**.", ephemeral=True)
            return

        mensagem_decisao = interaction.message
        if acao == "confirmar_aprovar":
            canal_id = int(revisao.get("canal_id") or 0)
            mensagem_id = int(revisao.get("mensagem_id") or 0)
            canal = interaction.guild.get_channel(canal_id) if canal_id else None
            if canal is None and canal_id:
                try:
                    canal = await interaction.guild.fetch_channel(canal_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    canal = None
            if canal is None or not mensagem_id:
                await interaction.followup.send(
                    "Não consegui localizar a mensagem original da evidência. Nenhuma decisão foi aplicada.",
                    ephemeral=True,
                )
                return
            try:
                mensagem_decisao = await canal.fetch_message(mensagem_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.followup.send(
                    "A mensagem original da evidência não está acessível. Nenhuma decisão foi aplicada.",
                    ephemeral=True,
                )
                return

        if acao in {"aprovar", "confirmar_aprovar"}:
            revisao = await revisoes.aprovar(interaction.guild.id, revisao_id, interaction.user.id)
            if not revisao:
                await interaction.followup.send(
                    "Esta revisão já foi processada por outra interação. Atualize a mensagem antes de tentar novamente.",
                    ephemeral=True,
                )
                return
            processador = self.bot.processadores_revisao.get(revisao["tipo"])
            try:
                if processador is None:
                    raise RuntimeError(
                        f"Não existe processador registrado para revisão do tipo {revisao.get('tipo')!r}."
                    )
                resultado_texto = await processador(interaction.guild, revisao)
            except Exception as erro:
                import logging
                logging.getLogger(__name__).exception(
                    "Falha ao aplicar recompensa da revisão %s (tipo=%s).",
                    revisao_id,
                    revisao.get("tipo"),
                )
                try:
                    reaberta = await revisoes.reabrir_apos_falha_aplicacao(
                        interaction.guild.id,
                        revisao_id,
                        type(erro).__name__,
                    )
                except Exception:
                    reaberta = None
                    logging.getLogger(__name__).exception(
                        "Não foi possível reabrir a revisão %s após falha de aplicação.",
                        revisao_id,
                    )

                mensagem = (
                    "A aplicação falhou e a prova voltou para **pendente**. "
                    "A staff pode clicar em Aprovar novamente após verificar a falha; "
                    "as recompensas de missões e PvP têm proteção contra duplicação."
                    if reaberta
                    else "A aplicação falhou e não consegui reabrir a prova automaticamente. "
                    "A equipe técnica precisa conferir os logs e o estado da revisão."
                )
                await interaction.followup.send(mensagem, ephemeral=True)
                return

            embed = _embed_revisao(revisao, interaction.guild, self.bot)
            embed.color = 0x57F287
            embed.add_field(name="✅ Aprovado por", value=interaction.user.mention, inline=False)
            if resultado_texto:
                embed.add_field(name="Resultado aplicado", value=resultado_texto, inline=False)
            await mensagem_decisao.edit(
                view=_card_revisao_view(discord.ui.View(timeout=120), embed)
            )
            await interaction.message.edit(
                view=_card_revisao_view(
                    discord.ui.View(timeout=120), None,
                    "APROVAÇÃO CONFIRMADA",
                    "A decisão foi registrada e a recompensa foi processada.",
                )
            )
            await interaction.edit_original_response(
                content="Aprovação confirmada. A decisão foi registrada e a recompensa foi processada.",
                view=None,
            )

            await auditoria.registrar(
                interaction.guild, "📋 Revisão aprovada",
                f"Tipo: **{revisao['tipo']}**\nAutor: <@{revisao['autor_id']}>\n"
                f"Aprovado por: {interaction.user.mention}\nID: `{revisao['id']}`\n"
                f"Resultado: {resultado_texto or 'Aprovação registrada.'}",
                cor=0x57F287,
                categoria="sistemas",
            )

            from utils.registro_global import registrar as registrar_global
            for membro_id in {int(revisao["autor_id"]), int(revisao.get("auxiliar_id") or 0)} - {0}:
                await registrar_global(
                    interaction.guild,
                    "historico_membros",
                    "Evidência de missão aprovada",
                    (
                        f"**Membro:** <@{membro_id}> (ID: {membro_id})\n"
                        f"**Atividade:** {revisao.get('titulo', 'Atividade')}\n"
                        f"**Revisor:** {interaction.user.mention}\n"
                        f"**Protocolo:** {revisao['id']}\n"
                        f"**Resultado:** {resultado_texto or 'Aprovação registrada.'}"
                    ),
                    cor=0x57F287,
                )

            destinatarios = {
                int(membro_id)
                for membro_id in (revisao.get("autor_id"), revisao.get("auxiliar_id"))
                if membro_id
            }
            for membro_id in destinatarios:
                membro = interaction.guild.get_member(membro_id)
                if membro is None:
                    try:
                        membro = await interaction.guild.fetch_member(membro_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        continue
                try:
                    contexto = (
                        "Sua evidência"
                        if membro_id == int(revisao.get("autor_id") or 0)
                        else "Uma evidência em que você foi registrado como auxiliar"
                    )
                    await membro.send(
                        f"✅ {contexto} para **{revisao.get('titulo', 'atividade')}** foi aprovada pela equipe da NÊMESIS.\n"
                        f"Protocolo: `{revisao.get('id', '—')}`\n"
                        f"{resultado_texto or 'A validação foi concluída.'}"
                    )
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    logging.getLogger(__name__).exception("Falha ao notificar o membro %s sobre a aprovação %s.", membro_id, revisao_id)

        else:
            revisao = await revisoes.rejeitar(interaction.guild.id, revisao_id, interaction.user.id)
            if not revisao:
                await interaction.followup.send(
                    "Esta revisão já foi processada por outra interação. Atualize a mensagem antes de tentar novamente.",
                    ephemeral=True,
                )
                return
            embed = _embed_revisao(revisao, interaction.guild, self.bot)
            embed.color = 0xED4245
            embed.add_field(name="❌ Rejeitado por", value=interaction.user.mention, inline=False)
            await interaction.message.edit(embed=embed, view=None)

            await auditoria.registrar(
                interaction.guild, "📋 Revisão rejeitada",
                f"Tipo: **{revisao['tipo']}**\nAutor: <@{revisao['autor_id']}>\n"
                f"Rejeitado por: {interaction.user.mention}\nID: `{revisao['id']}`",
                cor=0xED4245,
                categoria="sistemas",
            )

            from utils.registro_global import registrar as registrar_global
            await registrar_global(
                interaction.guild,
                "historico_membros",
                "Evidência de missão rejeitada",
                (
                    f"**Membro:** <@{revisao['autor_id']}> (ID: {revisao['autor_id']})\n"
                    f"**Atividade:** {revisao.get('titulo', 'Atividade')}\n"
                    f"**Revisor:** {interaction.user.mention}\n"
                    f"**Protocolo:** {revisao['id']}"
                ),
                cor=0xED4245,
            )

            autor = interaction.guild.get_member(revisao["autor_id"])
            if autor:
                try:
                    await autor.send(
                        f"Sua prova para **{revisao['titulo']}** foi rejeitada. "
                        "Você pode reenviar com uma nova print."
                    )
                except discord.Forbidden:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Revisoes(bot))