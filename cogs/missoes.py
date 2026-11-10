import asyncio
import csv
import io
import logging
import re
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from utils.apresentacao import criar_embed, aplicar_identidade_servidor

from utils import missoes
from utils.catalogo_missoes import (
    carregar_catalogo,
    sincronizar_catalogo,
    salvar_mensagem_discord,
    obter_mensagem_discord,
)
from utils.guild_config import get_config, octogono_only, membro_tem_octogono
from utils import ranking_missoes_jogos
from utils.perfis import (
    get_perfil,
    atualizar_perfil,
    calcular_patente_atual,
    definir_patente,
)


log = logging.getLogger(__name__)


class EnviarProvaMissaoModal(discord.ui.Modal, title="Enviar evidência da atividade"):
    imagem_url = discord.ui.TextInput(
        label="Link da imagem da prova (Discord)",
        placeholder="Envie a imagem no Discord e cole o link da imagem",
        required=True,
        max_length=1000,
    )
    auxiliar = discord.ui.TextInput(
        label="Auxiliar (opcional)",
        placeholder="Mencione o membro ou informe o ID do Discord",
        required=False,
        max_length=30,
    )

    def __init__(self, cog, missao_id: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.missao_id_selecionada = str(missao_id)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.receber_prova_modal(
            interaction,
            self.missao_id_selecionada,
            str(self.imagem_url.value),
            str(self.auxiliar.value or ""),
        )


class SeletorMissaoProva(discord.ui.Select):
    def __init__(self, view: "SeletorMissaoProvaView"):
        self.pai = view
        inicio = view.pagina * 25
        opcoes = []
        for atividade in view.atividades[inicio:inicio + 25]:
            codigo = str(atividade.get("id") or "").strip()
            if not codigo:
                continue
            titulo = str(atividade.get("titulo") or "Atividade sem título").strip()
            try:
                xp = max(0, int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0))
            except (TypeError, ValueError, OverflowError):
                xp = 0
            opcoes.append(discord.SelectOption(
                label=titulo[:100],
                value=codigo[:100],
                description=f"{codigo} • Recompensa: {xp:,} XP".replace(",", ".")[:100],
            ))
        super().__init__(
            placeholder="◈ Selecione a atividade que deseja comprovar",
            min_values=1,
            max_values=1,
            options=opcoes or [discord.SelectOption(label="Nenhuma atividade disponível", value="indisponivel")],
            disabled=not opcoes,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.pai.owner_id:
            await interaction.response.send_message("Esta seleção pertence a outro integrante.", ephemeral=True)
            return
        codigo = self.values[0]
        if codigo == "indisponivel":
            await interaction.response.send_message("Não há atividades disponíveis nesta categoria.", ephemeral=True)
            return
        await interaction.response.send_modal(EnviarProvaMissaoModal(self.pai.cog, codigo))


class SeletorMissaoProvaView(discord.ui.View):
    def __init__(self, cog, owner_id: int, categoria: str, atividades: list, pagina: int = 0):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.categoria = categoria if categoria in TIPOS else "missao"
        self.atividades = atividades
        self.total_paginas = max(1, (len(atividades) + 24) // 25)
        self.pagina = max(0, min(pagina, self.total_paginas - 1))
        self.add_item(SeletorMissaoProva(self))
        self.pagina_anterior.disabled = self.pagina == 0
        self.proxima_pagina.disabled = self.pagina >= self.total_paginas - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Esta seleção pertence a outro integrante.", ephemeral=True)
            return False
        return True

    async def _mudar_pagina(self, interaction: discord.Interaction, delta: int):
        self.pagina = max(0, min(self.total_paginas - 1, self.pagina + delta))
        nova = SeletorMissaoProvaView(
            self.cog, self.owner_id, self.categoria, self.atividades, self.pagina
        )
        await interaction.response.edit_message(
            embed=self.cog._embed_selecao_prova(self.categoria, self.pagina, self.total_paginas, self.atividades, interaction.guild),
            view=nova,
        )

    @discord.ui.button(label="Página anterior", style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def pagina_anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._mudar_pagina(interaction, -1)

    @discord.ui.button(label="Próxima página", style=discord.ButtonStyle.secondary, emoji="▶️", row=1)
    async def proxima_pagina(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._mudar_pagina(interaction, 1)


class EnviarProvaMissaoView(discord.ui.View):
    """Botão persistente para abrir o formulário de envio de provas."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="ENVIAR PROVAS",
        style=discord.ButtonStyle.primary,
        emoji="📨",
        custom_id="nemesis:missao:enviar_provas",
    )
    async def enviar_provas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.abrir_seletor_prova(interaction, "missao")


class CategoriaMissoesSelect(discord.ui.Select):
    """Seletor persistente para alternar entre departamentos."""
    def __init__(self, cog, categoria_atual="missao"):
        self.cog = cog
        opcoes = [
            discord.SelectOption(label="Missões", value="missao", description="Atividades competitivas", default=categoria_atual == "missao"),
            discord.SelectOption(label="Contribuições", value="contribuicao", description="Mérito e desenvolvimento", default=categoria_atual == "contribuicao"),
            discord.SelectOption(label="Operações especiais", value="especial", description="Protocolos especiais", default=categoria_atual == "especial"),
        ]
        super().__init__(
            placeholder="◈ Selecionar departamento",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="nemesis:missoes:categoria",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.message is None:
            await interaction.response.send_message("Este painel só pode ser utilizado no servidor.", ephemeral=True)
            return
        categoria = self.values[0]
        embed = await self.cog._montar_painel_missoes(interaction.guild, "todos", categoria, pagina=0)
        match = re.search(r"PAGINA:(\d+)/(\d+)", embed.footer.text or "")
        total = int(match.group(2)) if match else 1
        await interaction.response.edit_message(
            view=NavegacaoMissoesView(self.cog, categoria=categoria, pagina=0, total_paginas=total, embed=embed),
        )


class PaginaMissoesSelect(discord.ui.Select):
    """Seletor direto de página do catálogo global."""
    def __init__(self, cog, categoria="missao", pagina=0, total_paginas=1):
        self.cog = cog
        self.categoria = categoria
        total = max(1, min(int(total_paginas), 25))
        opcoes = [
            discord.SelectOption(
                label=f"Página {numero}",
                value=str(numero - 1),
                description=f"Exibir atividades {((numero - 1) * 8) + 1}–{min(numero * 8, total_paginas * 8)}",
                default=numero - 1 == pagina,
            )
            for numero in range(1, total + 1)
        ]
        super().__init__(
            placeholder="◈ Ir para página do catálogo",
            min_values=1,
            max_values=1,
            options=opcoes,
            custom_id="nemesis:missoes:pagina",
            row=1,
            disabled=total == 1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Este painel só pode ser utilizado no servidor.", ephemeral=True)
            return
        pagina = int(self.values[0])
        embed = await self.cog._montar_painel_missoes(
            interaction.guild, "todos", self.categoria, pagina=pagina
        )
        footer = embed.footer.text or ""
        match = re.search(r"PAGINA:(\d+)/(\d+)", footer)
        total = int(match.group(2)) if match else 1
        await interaction.response.edit_message(
            view=NavegacaoMissoesView(self.cog, categoria=self.categoria, pagina=pagina, total_paginas=total, embed=embed),
        )



def _resumir_desempenho_missoes(revisoes: list, user_id: int, limite: int = 5) -> dict:
    """Resume o histórico de missões do participante, inclusive como auxiliar."""
    uid = str(user_id)
    registros = [
        item for item in revisoes
        if isinstance(item, dict)
        and (str(item.get("autor_id")) == uid or str(item.get("auxiliar_id")) == uid)
        and str(item.get("tipo", "")).lower() in {"missao", "contribuicao", "especial", "pve"}
        and item.get("status") in {"aprovada", "rejeitada", "pendente"}
    ]
    def _data_ordenacao(item):
        for campo in ("aprovado_em", "rejeitada_em", "atualizado_em", "timestamp"):
            try:
                valor = item.get(campo)
                if valor is not None:
                    return float(valor)
            except (TypeError, ValueError, OverflowError):
                continue
        return 0.0

    registros.sort(key=_data_ordenacao, reverse=True)
    xp_rastreavel = 0
    xp_registros = 0
    for item in registros:
        if item.get("status") != "aprovada" or item.get("recompensa_xp") is None:
            continue
        try:
            recompensa = max(0, int(item.get("recompensa_xp") or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        autor_id = str(item.get("autor_id") or "")
        auxiliar_id = str(item.get("auxiliar_id") or "")
        if auxiliar_id and auxiliar_id != autor_id:
            parte_autor = (recompensa * 60 + 50) // 100
            parte = parte_autor if uid == autor_id else recompensa - parte_autor
        else:
            parte = recompensa if uid == autor_id else 0
        xp_rastreavel += parte
        xp_registros += 1
    return {
        "aprovadas": sum(item.get("status") == "aprovada" for item in registros),
        "rejeitadas": sum(item.get("status") == "rejeitada" for item in registros),
        "pendentes": sum(item.get("status") == "pendente" for item in registros),
        "xp_missoes": xp_rastreavel,
        "registros_com_xp": xp_registros,
        "recentes": registros[:max(0, int(limite))],
        "historico": registros,
    }


def _ranking_xp_missoes(revisoes: list, limite: int = 5) -> list:
    """Classifica XP de missões com recompensa persistida, sem estimar registros legados."""
    totais = {}
    for item in revisoes:
        if not isinstance(item, dict) or item.get("status") != "aprovada":
            continue
        if str(item.get("tipo", "")).lower() not in {"missao", "contribuicao", "especial", "pve"}:
            continue
        try:
            recompensa = max(0, int(item.get("recompensa_xp") or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        autor = str(item.get("autor_id") or "")
        auxiliar = str(item.get("auxiliar_id") or "")
        if not autor:
            continue
        if auxiliar and auxiliar != autor:
            parte_autor = (recompensa * 60 + 50) // 100
            distribuicao = ((autor, parte_autor), (auxiliar, recompensa - parte_autor))
        else:
            distribuicao = ((autor, recompensa),)
        for uid, quantidade in distribuicao:
            if uid and quantidade > 0:
                totais[uid] = totais.get(uid, 0) + quantidade
    try:
        limite = max(0, int(limite))
    except (TypeError, ValueError, OverflowError):
        limite = 5
    return sorted(totais.items(), key=lambda item: (-item[1], item[0]))[:limite]



def _calcular_inteligencia_missoes(revisoes: list, agora: float = None) -> dict:
    """Agrega métricas administrativas sem estimar recompensas de registros legados."""
    import time

    agora = float(agora if agora is not None else time.time())
    tipos = {"missao", "contribuicao", "especial", "pve"}
    validas = [
        item for item in revisoes
        if isinstance(item, dict)
        and str(item.get("tipo", "")).lower() in tipos
        and item.get("status") in {"aprovada", "rejeitada", "pendente"}
    ]
    aprovadas = [item for item in validas if item.get("status") == "aprovada"]
    rejeitadas = [item for item in validas if item.get("status") == "rejeitada"]
    pendentes = [item for item in validas if item.get("status") == "pendente"]
    finalizadas = len(aprovadas) + len(rejeitadas)
    xp_total = 0
    participantes = set()
    ativos_7d = set()
    envios_7d = 0
    categorias = {}
    ranking = {}

    def _timestamp(item, campos):
        for campo in campos:
            try:
                valor = item.get(campo)
                if valor is not None:
                    return float(valor)
            except (TypeError, ValueError, OverflowError):
                continue
        return None

    for item in validas:
        autor = str(item.get("autor_id") or "")
        auxiliar = str(item.get("auxiliar_id") or "")
        if autor:
            participantes.add(autor)
        if auxiliar:
            participantes.add(auxiliar)
        momento_envio = _timestamp(item, ("timestamp", "criado_em"))
        if momento_envio is not None and momento_envio >= agora - 7 * 86400:
            envios_7d += 1
            if autor:
                ativos_7d.add(autor)
            if auxiliar:
                ativos_7d.add(auxiliar)

        tipo = str(item.get("tipo") or "missao").lower()
        bucket = categorias.setdefault(tipo, {"aprovadas": 0, "rejeitadas": 0, "pendentes": 0})
        bucket[{"aprovada": "aprovadas", "rejeitada": "rejeitadas", "pendente": "pendentes"}[item["status"]]] += 1

        if item.get("status") != "aprovada" or item.get("recompensa_xp") is None:
            continue
        try:
            recompensa = max(0, int(item.get("recompensa_xp") or 0))
        except (TypeError, ValueError, OverflowError):
            continue
        if not autor:
            continue
        if auxiliar and auxiliar != autor:
            parte_autor = (recompensa * 60 + 50) // 100
            distribuicao = ((autor, parte_autor), (auxiliar, recompensa - parte_autor))
        else:
            distribuicao = ((autor, recompensa),)
        for uid, quantidade in distribuicao:
            if uid and quantidade > 0:
                xp_total += quantidade
                ranking[uid] = ranking.get(uid, 0) + quantidade

    return {
        "total": len(validas),
        "aprovadas": len(aprovadas),
        "rejeitadas": len(rejeitadas),
        "pendentes": len(pendentes),
        "taxa_aprovacao": (len(aprovadas) / finalizadas * 100) if finalizadas else 0.0,
        "xp_distribuido": xp_total,
        "participantes": len(participantes),
        "ativos_7d": len(ativos_7d),
        "envios_7d": envios_7d,
        "categorias": categorias,
        "ranking": sorted(ranking.items(), key=lambda par: (-par[1], par[0]))[:5],
    }



def _calcular_inteligencia_participantes(
    revisoes: list, agora: float = None, limite: int = 8
) -> dict:
    """Resume atividade individual usando apenas evidências oficiais de missões."""
    import time

    agora = float(agora if agora is not None else time.time())
    limite = max(1, min(int(limite), 25))
    tipos = {"missao", "contribuicao", "especial", "pve"}
    participantes = {}

    def _momento(item):
        for campo in ("timestamp", "criado_em"):
            try:
                valor = item.get(campo)
                if valor is not None:
                    return float(valor)
            except (TypeError, ValueError, OverflowError):
                continue
        return None

    for item in revisoes:
        if (
            not isinstance(item, dict)
            or str(item.get("tipo", "")).lower() not in tipos
            or item.get("status") not in {"aprovada", "rejeitada", "pendente"}
        ):
            continue
        autor = str(item.get("autor_id") or "")
        auxiliar = str(item.get("auxiliar_id") or "")
        envolvidos = [uid for uid in dict.fromkeys((autor, auxiliar)) if uid]
        if not envolvidos:
            continue
        momento = _momento(item)
        status = item["status"]
        recompensa = None
        if status == "aprovada" and item.get("recompensa_xp") is not None:
            try:
                recompensa = max(0, int(item.get("recompensa_xp") or 0))
            except (TypeError, ValueError, OverflowError):
                recompensa = None

        for uid in envolvidos:
            perfil = participantes.setdefault(uid, {
                "user_id": uid, "envios": 0, "aprovadas": 0,
                "rejeitadas": 0, "pendentes": 0, "xp_missoes": 0,
                "xp_ultimos_30d": 0, "xp_30d_anteriores": 0,
                "ultima_atividade": None,
            })
            perfil["envios"] += 1
            perfil[{"aprovada": "aprovadas", "rejeitada": "rejeitadas", "pendente": "pendentes"}[status]] += 1
            if momento is not None and (
                perfil["ultima_atividade"] is None or momento > perfil["ultima_atividade"]
            ):
                perfil["ultima_atividade"] = momento

        if recompensa is not None and autor:
            if auxiliar and auxiliar != autor:
                parte_autor = (recompensa * 60 + 50) // 100
                distribuicao = ((autor, parte_autor), (auxiliar, recompensa - parte_autor))
            else:
                distribuicao = ((autor, recompensa),)
            momento_aprovacao = _momento({"timestamp": item.get("aprovado_em")})
            for uid, xp in distribuicao:
                if uid not in participantes:
                    continue
                perfil = participantes[uid]
                perfil["xp_missoes"] += xp
                if momento_aprovacao is not None:
                    if momento_aprovacao >= agora - 30 * 86400:
                        perfil["xp_ultimos_30d"] += xp
                    elif momento_aprovacao >= agora - 60 * 86400:
                        perfil["xp_30d_anteriores"] += xp

    ordenados = list(participantes.values())
    for perfil in ordenados:
        ultima = perfil["ultima_atividade"]
        perfil["dias_sem_atividade"] = (
            max(0, int((agora - ultima) // 86400)) if ultima is not None else None
        )
    ativos_7d = [
        p for p in ordenados
        if p["ultima_atividade"] is not None
        and p["ultima_atividade"] >= agora - 7 * 86400
    ]
    inativos_14d = [
        p for p in ordenados
        if p["ultima_atividade"] is None
        or p["ultima_atividade"] < agora - 14 * 86400
    ]
    ativos_7d.sort(
        key=lambda p: (-p["envios"], -p["xp_missoes"], p["user_id"])
    )
    inativos_14d.sort(
        key=lambda p: (
            p["ultima_atividade"] if p["ultima_atividade"] is not None else 0,
            p["user_id"],
        )
    )
    return {
        "total": len(ordenados),
        "ativos_7d": len(ativos_7d),
        "inativos_14d": len(inativos_14d),
        "mais_ativos": ativos_7d[:limite],
        "inativos": inativos_14d[:limite],
        "perfis": {p["user_id"]: p for p in ordenados},
    }


def _texto_embed_missoes(embed: discord.Embed | None) -> str:
    if embed is None:
        return "## 🎯 NÊMESIS • CENTRAL DE MISSÕES\nSelecione uma categoria ou página para consultar as atividades."
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



def _card_view_missoes(origem: discord.ui.View, embed: discord.Embed | None = None,
                       titulo: str = "CENTRAL NÊMESIS", descricao: str = "") -> discord.ui.LayoutView:
    """Envolve fluxos privados legados em cartão sem perder os callbacks originais."""
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    texto = _texto_embed_missoes(embed) if embed else f"## {titulo}\n{descricao}".strip()
    componentes = [
        discord.ui.TextDisplay(texto[:3900]),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ]
    botoes = []
    seletores = []
    for item in origem.children:
        if isinstance(item, discord.ui.UserSelect):
            novo = discord.ui.UserSelect(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, custom_id=item.custom_id,
                disabled=item.disabled,
            )
            async def selecionar(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = selecionar
            seletores.append(novo)
        elif isinstance(item, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, options=list(item.options),
                custom_id=item.custom_id, disabled=item.disabled,
            )
            async def selecionar(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = selecionar
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
        discord.ui.TextDisplay("-# NÊMESIS • Gestão de Missões"),
    ])
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


class NavegacaoMissoesView(discord.ui.LayoutView):
    """Painel de missões em Components V2; todos os controles ficam no cartão."""
    def __init__(self, cog, categoria="missao", pagina=0, total_paginas=1, embed=None):
        super().__init__(timeout=None)
        self.cog = cog
        self.categoria = categoria if categoria in TIPOS else "missao"
        self.pagina = max(0, int(pagina))
        self.total_paginas = max(1, int(total_paginas))

        seletor_categoria = CategoriaMissoesSelect(cog, self.categoria)
        seletor_pagina = PaginaMissoesSelect(cog, self.categoria, self.pagina, self.total_paginas)
        botoes = []

        def botao(label, emoji, custom_id, callback, style=discord.ButtonStyle.secondary):
            item = discord.ui.Button(label=label, emoji=emoji, custom_id=custom_id, style=style)
            item.callback = callback
            botoes.append(item)

        botao("Enviar evidência", "📨", "nemesis:missoes:provas", self._enviar_provas, discord.ButtonStyle.success)
        botao("Temporada atual", "🏆", "nemesis:missoes:temporada", self._temporada_atual)
        botao("Meu desempenho", "📊", "nemesis:missoes:desempenho", self._meu_desempenho)
        botao("Central OCTÓGONO", "📈", "nemesis:missoes:inteligencia", self._central_inteligencia)

        itens = [
            discord.ui.TextDisplay(_texto_embed_missoes(embed)),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("### ◈ NAVEGAÇÃO DO CATÁLOGO"),
            discord.ui.ActionRow(seletor_categoria),
            discord.ui.ActionRow(seletor_pagina),
        ]
        for inicio in range(0, len(botoes), 2):
            itens.append(discord.ui.ActionRow(*botoes[inicio:inicio + 2]))
        itens.extend([
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Nêmesis Systeam"),
        ])
        self.add_item(discord.ui.Container(*itens, accent_colour=0x9F1239))

    async def _enviar_provas(self, interaction: discord.Interaction):
        await self.cog.abrir_seletor_prova(interaction, self.categoria)

    async def _temporada_atual(self, interaction: discord.Interaction):
        central = self.cog.bot.get_cog("TemporadasMissoes")
        if central is None:
            await interaction.response.send_message("O módulo de temporadas está temporariamente indisponível.", ephemeral=True)
            return
        await central.abrir_status_publico(interaction)

    async def _meu_desempenho(self, interaction: discord.Interaction):
        await self.cog.enviar_painel_desempenho(interaction)

    async def _central_inteligencia(self, interaction: discord.Interaction):
        await self.cog.enviar_painel_inteligencia(interaction)


class InteligenciaMissoesView(discord.ui.View):
    """Navegação privada da central administrativa de inteligência."""

    def __init__(self, cog, owner_id: int, pagina: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = int(owner_id)
        self.pagina = max(0, min(int(pagina), 3))
        self.anterior.disabled = self.pagina == 0
        self.proxima.disabled = self.pagina == 3

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (
            interaction.guild is None
            or not isinstance(interaction.user, discord.Member)
            or not membro_tem_octogono(interaction.user)
        ):
            await interaction.response.send_message(
                "A Central de Inteligência é restrita à cargo OCTÓGONO.",
                ephemeral=True,
            )
            return False
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Esta sessão administrativa foi aberta por outro integrante.",
                ephemeral=True,
            )
            return False
        return True

    async def _navegar(self, interaction: discord.Interaction, delta: int):
        self.pagina = max(0, min(3, self.pagina + delta))
        embed = await self.cog._montar_embed_inteligencia(interaction.guild, self.pagina)
        await interaction.response.edit_message(
            view=_card_view_missoes(
                InteligenciaMissoesView(self.cog, self.owner_id, self.pagina), embed
            ),
        )

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._navegar(interaction, -1)

    @discord.ui.button(label="Próxima", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._navegar(interaction, 1)

    @discord.ui.button(label="Relatórios", emoji="📑", style=discord.ButtonStyle.primary, row=1)
    async def abrir_relatorios(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.enviar_painel_relatorios(interaction)

    @discord.ui.button(label="Atualizar", emoji="🔄", style=discord.ButtonStyle.success)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = await self.cog._montar_embed_inteligencia(interaction.guild, self.pagina)
        await interaction.response.edit_message(
            embed=embed,
            view=InteligenciaMissoesView(self.cog, self.owner_id, self.pagina),
        )

    @discord.ui.button(label="Fechar", emoji="❌", style=discord.ButtonStyle.danger)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Central administrativa encerrada.",
            embed=None,
            view=None,
        )


PERIODOS_RELATORIOS = {
    "7": ("Últimos 7 dias", 7 * 86400),
    "30": ("Últimos 30 dias", 30 * 86400),
    "90": ("Últimos 90 dias", 90 * 86400),
    "total": ("Todo o histórico", None),
}


def _filtrar_relatorio_missoes(revisoes: list, periodo: str = "30", agora: float = None) -> list:
    """Filtra evidências por data de envio; registros sem data só entram no histórico total."""
    import time
    agora = float(agora if agora is not None else time.time())
    periodo = str(periodo or "30")
    if periodo not in PERIODOS_RELATORIOS:
        periodo = "30"
    duracao = PERIODOS_RELATORIOS[periodo][1]
    validas = [
        item for item in revisoes
        if isinstance(item, dict)
        and str(item.get("tipo", "")).lower() in {"missao", "contribuicao", "especial", "pve"}
        and item.get("status") in {"aprovada", "rejeitada", "pendente"}
    ]
    if duracao is None:
        return sorted(validas, key=lambda item: _timestamp_relatorio(item) or 0, reverse=True)
    limite = agora - duracao
    return sorted(
        [item for item in validas if (_timestamp_relatorio(item) is not None and _timestamp_relatorio(item) >= limite)],
        key=lambda item: _timestamp_relatorio(item) or 0,
        reverse=True,
    )


def _timestamp_relatorio(item: dict, campo: str = "timestamp"):
    for chave in ((campo, "criado_em") if campo == "timestamp" else (campo,)):
        try:
            valor = item.get(chave)
            if valor is not None:
                return float(valor)
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def _linhas_csv_relatorio_missoes(revisoes: list) -> str:
    """Exporta os registros filtrados com XP distribuído somente quando auditável."""
    arquivo = io.StringIO(newline="")
    campos = [
        "protocolo", "titulo", "categoria", "status", "autor_id", "auxiliar_id",
        "revisor_id", "enviado_em", "aprovado_em", "rejeitada_em",
        "recompensa_xp_registrada", "xp_responsavel", "xp_auxiliar",
        "motivo_rejeicao",
    ]
    escritor = csv.DictWriter(arquivo, fieldnames=campos, delimiter=";")
    escritor.writeheader()
    for item in revisoes:
        recompensa = item.get("recompensa_xp")
        try:
            recompensa = max(0, int(recompensa)) if recompensa is not None and item.get("status") == "aprovada" else None
        except (TypeError, ValueError, OverflowError):
            recompensa = None
        autor = str(item.get("autor_id") or "")
        auxiliar = str(item.get("auxiliar_id") or "")
        xp_autor = xp_auxiliar = ""
        if recompensa is not None and autor:
            if auxiliar and auxiliar != autor:
                xp_autor = (recompensa * 60 + 50) // 100
                xp_auxiliar = recompensa - xp_autor
            else:
                xp_autor = recompensa
                xp_auxiliar = 0 if auxiliar else ""
        escritor.writerow({
            "protocolo": item.get("id", ""),
            "titulo": item.get("titulo", ""),
            "categoria": item.get("tipo", ""),
            "status": item.get("status", ""),
            "autor_id": autor,
            "auxiliar_id": auxiliar,
            "revisor_id": item.get("revisor_id") or "",
            "enviado_em": _timestamp_relatorio(item),
            "aprovado_em": _timestamp_relatorio(item, "aprovado_em") or "",
            "rejeitada_em": _timestamp_relatorio(item, "rejeitada_em") or "",
            "recompensa_xp_registrada": recompensa if recompensa is not None else "",
            "xp_responsavel": xp_autor,
            "xp_auxiliar": xp_auxiliar,
            "motivo_rejeicao": item.get("motivo_rejeicao") or "",
        })
    return arquivo.getvalue()


class PeriodoRelatorioSelect(discord.ui.Select):
    def __init__(self, view):
        self.pai = view
        opcoes = [
            discord.SelectOption(label=nome, value=valor, default=valor == view.periodo)
            for valor, (nome, _) in PERIODOS_RELATORIOS.items()
        ]
        super().__init__(
            placeholder="◈ Período de apuração", min_values=1, max_values=1,
            options=opcoes, row=0, custom_id="nemesis:relatorios:periodo",
        )

    async def callback(self, interaction: discord.Interaction):
        await self.pai._selecionar_periodo(interaction, self.values[0])


class IntegranteRelatorioSelect(discord.ui.UserSelect):
    def __init__(self, view):
        self.pai = view
        super().__init__(
            placeholder="◈ Relatório individual (opcional)", min_values=1, max_values=1, row=1
        )

    async def callback(self, interaction: discord.Interaction):
        selecionado = self.values[0]
        await self.pai._selecionar_integrante(
            interaction, int(getattr(selecionado, "id", selecionado))
        )


class RelatoriosMissoesView(discord.ui.View):
    """Central privada de relatórios administrativos e exportação CSV."""

    def __init__(self, cog, owner_id: int, periodo: str = "30", user_id: int = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = int(owner_id)
        self.periodo = periodo if periodo in PERIODOS_RELATORIOS else "30"
        self.user_id = int(user_id) if user_id else None
        self.add_item(PeriodoRelatorioSelect(self))
        self.add_item(IntegranteRelatorioSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (
            interaction.guild is None
            or not isinstance(interaction.user, discord.Member)
            or not membro_tem_octogono(interaction.user)
        ):
            await interaction.response.send_message(
                "Os relatórios administrativos são exclusivos da cargo OCTÓGONO.",
                ephemeral=True,
            )
            return False
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Esta sessão de relatórios foi aberta por outro integrante.",
                ephemeral=True,
            )
            return False
        return True

    async def _selecionar_periodo(self, interaction: discord.Interaction, periodo: str):
        self.periodo = periodo if periodo in PERIODOS_RELATORIOS else "30"
        await self._atualizar(interaction)

    async def _selecionar_integrante(self, interaction: discord.Interaction, user_id: int):
        self.user_id = int(user_id)
        await self._atualizar(interaction)

    async def _atualizar(self, interaction: discord.Interaction):
        embed = await self.cog._montar_embed_relatorio_missoes(
            interaction.guild, self.periodo, self.user_id
        )
        await interaction.response.edit_message(
            view=_card_view_missoes(
                RelatoriosMissoesView(self.cog, self.owner_id, self.periodo, self.user_id), embed
            ),
        )

    @discord.ui.button(label="Atualizar relatório", emoji="🔄", style=discord.ButtonStyle.success, row=2)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._atualizar(interaction)

    @discord.ui.button(label="Exportar CSV", emoji="📄", style=discord.ButtonStyle.primary, row=2)
    async def exportar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        from utils import revisoes as revisoes_storage
        registros = _filtrar_relatorio_missoes(
            await revisoes_storage.listar(interaction.guild.id), self.periodo
        )
        if self.user_id:
            uid = str(self.user_id)
            registros = [
                item for item in registros
                if uid in {str(item.get("autor_id") or ""), str(item.get("auxiliar_id") or "")}
            ]
        conteudo = _linhas_csv_relatorio_missoes(registros)
        nome_periodo = self.periodo if self.periodo != "total" else "historico"
        arquivo = discord.File(
            io.BytesIO(conteudo.encode("utf-8-sig")),
            filename=f"nemesis_relatorio_missoes_{nome_periodo}.csv",
        )
        await interaction.followup.send(
            content=f"Exportação concluída · **{len(registros)}** protocolos incluídos.",
            file=arquivo,
            ephemeral=True,
        )

    @discord.ui.button(label="Fechar", emoji="❌", style=discord.ButtonStyle.danger, row=2)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Central de relatórios encerrada.", embed=None, view=None)

    @discord.ui.button(label="Auditoria de integridade", emoji="🛡️", style=discord.ButtonStyle.secondary, row=3)
    async def abrir_auditoria(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await self.cog._montar_embed_auditoria_integridade(interaction.guild, 0)
        await interaction.followup.send(
            view=_card_view_missoes(
                AuditoriaIntegridadeView(self.cog, self.owner_id, 0), embed
            ),
            ephemeral=True,
        )




class AuditoriaIntegridadeView(discord.ui.View):
    """Consulta privada de inconsistências e trilhas de decisão dos protocolos."""

    def __init__(self, cog, owner_id: int, pagina: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = int(owner_id)
        self.pagina = max(0, int(pagina))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (
            interaction.guild is None
            or not isinstance(interaction.user, discord.Member)
            or not membro_tem_octogono(interaction.user)
        ):
            await interaction.response.send_message(
                "A auditoria de integridade é exclusiva da cargo OCTÓGONO.",
                ephemeral=True,
            )
            return False
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Esta sessão de auditoria foi aberta por outro integrante.",
                ephemeral=True,
            )
            return False
        return True

    async def _atualizar(self, interaction: discord.Interaction, pagina: int = None):
        if pagina is not None:
            self.pagina = max(0, pagina)
        embed = await self.cog._montar_embed_auditoria_integridade(
            interaction.guild, self.pagina
        )
        await interaction.response.edit_message(
            view=_card_view_missoes(
                AuditoriaIntegridadeView(self.cog, self.owner_id, self.pagina), embed
            ),
        )

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary, row=0)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._atualizar(interaction, self.pagina - 1)

    @discord.ui.button(label="Próxima", emoji="▶️", style=discord.ButtonStyle.secondary, row=0)
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._atualizar(interaction, self.pagina + 1)

    @discord.ui.button(label="Reanalisar", emoji="🔄", style=discord.ButtonStyle.success, row=0)
    async def reanalisar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._atualizar(interaction, self.pagina)

    @discord.ui.button(label="Fechar", emoji="❌", style=discord.ButtonStyle.danger, row=0)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Auditoria de integridade encerrada.", embed=None, view=None
        )


class HistoricoDesempenhoView(discord.ui.View):
    """Paginação privada do histórico completo de evidências de um integrante."""

    def __init__(self, cog, owner_id: int, registros: list, pagina: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = int(owner_id)
        self.registros = list(registros)
        self.total_paginas = max(1, (len(self.registros) + 4) // 5)
        self.pagina = max(0, min(int(pagina), self.total_paginas - 1))
        self.anterior.disabled = self.pagina == 0
        self.proxima.disabled = self.pagina >= self.total_paginas - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Este histórico pertence a outro integrante.",
                ephemeral=True,
            )
            return False
        return True

    async def _navegar(self, interaction: discord.Interaction, delta: int):
        self.pagina = max(0, min(self.total_paginas - 1, self.pagina + delta))
        embed = self.cog._montar_embed_historico_desempenho(
            interaction.guild, self.owner_id, self.registros, self.pagina
        )
        nova_view = HistoricoDesempenhoView(
            self.cog, self.owner_id, self.registros, self.pagina
        )
        await interaction.response.edit_message(
            view=_card_view_missoes(nova_view, embed)
        )

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._navegar(interaction, -1)

    @discord.ui.button(label="Próxima", emoji="▶️", style=discord.ButtonStyle.secondary)
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._navegar(interaction, 1)

    @discord.ui.button(label="Fechar", emoji="❌", style=discord.ButtonStyle.danger)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Histórico encerrado.",
            embed=None,
            view=None,
        )


TIPOS = {
    "missao": {
        "nome": "Missão",
        "plural": "MISSÕES",
        "emoji": "🎯",
        "cor": 0x9F2035,
        "assinatura": "AÇÃO • DESEMPENHO • COMPETITIVIDADE",
    },
    # O valor interno antigo é mantido para compatibilidade com os dados existentes.
    "contribuicao": {
        "nome": "Contribuição",
        "plural": "CONTRIBUIÇÕES",
        "emoji": "✦",
        "cor": 0x9A7836,
        "assinatura": "APOIO • EVOLUÇÃO • COMPROMISSO",
    },
    "especial": {
        "nome": "Missão especial",
        "plural": "OPERAÇÕES ESPECIAIS",
        "emoji": "✧",
        "cor": 0x754A9E,
        "assinatura": "ACESSO ESPECIAL • OBJETIVOS DE DESTAQUE",
    },
}

CANAIS_PADRAO = {
    "canal_missoes_missao_id": 1556543214885019668,
    "canal_missoes_contribuicao_id": 1556543539213639760,
    "canal_missoes_especial_id": 1556543708478972015,
    "canal_provas_missao_id": 1556543417843056641,
    "canal_provas_contribuicao_id": 1556543628296593448,
    "canal_provas_especial_id": 1556543872534839336,
}

NOMES_CANAIS = {}


class Missoes(commands.Cog):
    """Missões permanentes definidas no GitHub e revisão de provas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sync_lock = asyncio.Lock()
        self._reward_lock = asyncio.Lock()
        # O custom_id fixo mantém o botão funcional mesmo após reinícios do bot.
        self.bot.add_view(EnviarProvaMissaoView(self))
        self.bot.add_view(NavegacaoMissoesView(self))
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}
        for tipo in ("missao", "contribuicao", "especial"):
            bot.processadores_revisao[tipo] = self.processar_aprovacao

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(1563995879981981817)
        if guild is None:
            log.warning("Missões padrão: servidor NÊMESIS não encontrado no cache.")
            return
        await self.sincronizar_missoes_discord(guild)

    async def _resolver_canal(self, guild: discord.Guild, canal_id: int):
        canal = guild.get_channel(int(canal_id))
        if canal is None:
            try:
                canal = await guild.fetch_channel(int(canal_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as erro:
                log.warning("Não foi possível resolver o canal %s: %s", canal_id, erro)
                return None
        return canal if isinstance(canal, discord.TextChannel) else None

    async def _renomear_canais_pontuacao(self, guild: discord.Guild, config: dict):
        bot_member = guild.me
        if bot_member is None:
            return
        for chave, nome_novo in NOMES_CANAIS.items():
            canal_id = config.get(chave) or CANAIS_PADRAO.get(chave)
            if not canal_id:
                continue
            canal = await self._resolver_canal(guild, canal_id)
            if canal is None or canal.name == nome_novo:
                continue
            if not canal.permissions_for(bot_member).manage_channels:
                log.warning("Sem permissão para renomear o canal %s para %s.", canal.id, nome_novo)
                continue
            try:
                await canal.edit(name=nome_novo, reason="Padronização do sistema de missões da NÊMESIS")
            except discord.HTTPException:
                log.exception("Falha ao renomear o canal %s.", canal.id)

    @staticmethod
    def _dividir_descricao(descricao: str, limite: int = 3800) -> list[str]:
        """Divide descrições longas em blocos compatíveis com o limite do Discord."""
        texto = str(descricao if descricao is not None else "")
        if not texto:
            texto = "Consulte a descrição com a liderança."
        if len(texto) > 20000:
            texto = texto[:20000]

        partes = []
        while texto:
            if len(texto) <= limite:
                partes.append(texto)
                break

            corte = texto.rfind(chr(10), 0, limite)
            if corte < limite // 2:
                corte = texto.rfind(" ", 0, limite)
            if corte < limite // 2:
                corte = limite
            elif corte < limite:
                # Mantém a quebra de linha/espaço para não perder caracteres.
                corte += 1

            partes.append(texto[:corte])
            texto = texto[corte:]

        return partes or ["Consulte a descrição com a liderança."]

    @classmethod
    def _montar_embeds(cls, atividade: dict) -> list[discord.Embed]:
        """Cria cartões consistentes para o catálogo público de missões."""
        tipo_chave = str(atividade.get("tipo", "missao")).strip().lower()
        tipo = TIPOS.get(tipo_chave, TIPOS["missao"])
        ativa = atividade.get("ativa", True) is not False

        try:
            recompensa = max(
                0,
                int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0),
            )
        except (TypeError, ValueError):
            recompensa = 0

        missao_id = str(atividade.get("id") or "—").strip()
        titulo_original = str(atividade.get("titulo") or "Operação sem título").strip()
        descricao_original = str(atividade.get("descricao") or "").strip()
        if not descricao_original:
            descricao_original = (
                "Os detalhes desta operação ainda não foram definidos. "
                "Consulte a liderança antes de iniciar."
            )

        origem = str(atividade.get("origem") or "oficial").strip().replace("_", " ").title()
        status = "OPERAÇÃO DISPONÍVEL" if ativa else "OPERAÇÃO ENCERRADA"
        status_icone = "◉" if ativa else "■"
        cores = {
            "missao": 0x9F2035,
            "contribuicao": 0x8B6A35,
            "especial": 0xC19A45,
        }
        cor = cores.get(tipo_chave, 0x9F2035)

        # A dificuldade é informativa e derivada dos dados existentes.
        # Um valor explícito no catálogo sempre tem prioridade.
        dificuldade = str(atividade.get("dificuldade") or "").strip()
        if not dificuldade:
            if tipo_chave == "especial" or recompensa >= 60:
                dificuldade = "Alta"
            elif recompensa >= 25:
                dificuldade = "Intermediária"
            else:
                dificuldade = "Moderada"

        requisitos = str(atividade.get("requisitos") or "").strip()
        prazo = str(atividade.get("prazo") or "").strip()
        partes = cls._dividir_descricao(descricao_original, limite=3000)
        embeds = []

        for indice, parte in enumerate(partes, start=1):
            sufixo = f"  ━  PARTE {indice}/{len(partes)}" if len(partes) > 1 else ""
            titulo = f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  {titulo_original}{sufixo}"[:256]
            cabecalho = (
                f"**{status_icone} {status}**  ·  **{tipo['nome'].upper()}**\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            embed = criar_embed(
                titulo,
                f"{cabecalho}\n\n{parte}",
                cor=cor,
                rodape=None,
            )
            embed.set_author(name="NÊMESIS  /  CENTRAL DE OPERAÇÕES")

            if indice == 1:
                jogo_slug = str(atividade.get("jogo") or "").strip().lower()
                jogo_nome = ranking_missoes_jogos.JOGOS.get(
                    jogo_slug, {}
                ).get("nome")
                identificacao = (
                    f"**Código**  `{missao_id}`\n"
                    f"**Categoria**  {tipo['nome']}\n"
                    f"**Origem**  {origem}"
                )
                if jogo_nome:
                    identificacao += f"\n**Jogo**  {jogo_nome}"
                embed.add_field(
                    name="◈ IDENTIFICAÇÃO",
                    value=identificacao,
                    inline=True,
                )
                embed.add_field(
                    name="◈ CLASSIFICAÇÃO",
                    value=(
                        f"**Dificuldade**  {dificuldade}\n"
                        f"**Estado**  {'Aberta' if ativa else 'Arquivada'}"
                    ),
                    inline=True,
                )
                embed.add_field(
                    name="◈ RECOMPENSA",
                    value=f"**{recompensa:,} XP** por aprovação".replace(",", "."),
                    inline=True,
                )

                if requisitos:
                    embed.add_field(
                        name="◈ REQUISITOS",
                        value=requisitos[:1024],
                        inline=False,
                    )
                if prazo:
                    embed.add_field(
                        name="◈ PRAZO",
                        value=prazo[:1024],
                        inline=True,
                    )

                if ativa:
                    embed.add_field(
                        name="◈ DIRETRIZES DA OPERAÇÃO",
                        value=(
                            "Leia o objetivo por completo e cumpra as condições descritas. "
                            "A evidência precisa corresponder à atividade e permitir a conferência."
                        ),
                        inline=False,
                    )
                    embed.add_field(
                        name="◈ CRITÉRIOS DE RECOMPENSA",
                        value=(
                            f"Responsável sem auxiliar: **{recompensa:,} XP** após aprovação.\n"
                            "Com auxiliar opcional: **60%** para o responsável e **40%** para o auxiliar.\n"
                            "A recompensa não é duplicada; a validação da staff continua obrigatória."
                        ).replace(",", "."),
                        inline=False,
                    )
                    embed.set_footer(
                        text="NÊMESIS  •  CATÁLOGO OFICIAL  •  Participação sujeita à validação da staff"
                    )
                else:
                    embed.add_field(
                        name="◈ REGISTRO DE ENCERRAMENTO",
                        value=(
                            "Esta operação foi encerrada. O cartão permanece disponível "
                            "para consulta e referência do catálogo."
                        ),
                        inline=False,
                    )
                    embed.set_footer(text="NÊMESIS  •  ARQUIVO DE OPERAÇÕES  •  SOMENTE CONSULTA")
            else:
                embed.set_footer(
                    text=f"NÊMESIS  •  CONTINUAÇÃO DA OPERAÇÃO  •  {indice}/{len(partes)}"
                )

            embeds.append(embed)

        return embeds

    @staticmethod
    def _slug_da_mensagem(mensagem, prefixo: str, padrao: str = "shigaku") -> str:
        if not mensagem or not getattr(mensagem, "embeds", None):
            return padrao
        rodape = str(mensagem.embeds[0].footer.text or "")
        marcador = prefixo + ":"
        for slug in ranking_missoes_jogos.JOGOS:
            if marcador + slug in rodape:
                return slug
        return padrao

    async def _montar_painel_missoes(
        self,
        guild: discord.Guild,
        jogo: str = "todos",
        categoria: str = "missao",
        pagina: int = 0,
    ) -> discord.Embed:
        """Central global: as atividades são válidas para todos os jogos."""
        categoria = categoria if categoria in TIPOS else "missao"
        tipo = TIPOS[categoria]
        dados = await missoes._guild(guild.id)
        atividades = [
            item for item in dados.get("missoes", [])
            if isinstance(item, dict)
            and str(item.get("tipo") or "missao").strip().lower() == categoria
            and not str(item.get("id") or "").startswith(("SHI-", "GAK-", "FIS-"))
        ]
        atividades.sort(key=lambda item: (
            item.get("ativa", True) is False,
            str(item.get("titulo") or "").casefold(),
            str(item.get("id") or ""),
        ))
        abertas = [item for item in atividades if item.get("ativa", True) is not False]
        encerradas = len(atividades) - len(abertas)

        def recompensa_da(atividade: dict) -> int:
            try:
                return max(0, int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0))
            except (TypeError, ValueError, OverflowError):
                return 0

        xp_disponivel = sum(recompensa_da(item) for item in abertas)
        # Oito atividades por página mantêm a embed legível e abaixo dos
        # limites de campos/caracteres do Discord, mesmo com catálogos grandes.
        itens_por_pagina = 8
        total_paginas = max(1, (len(atividades) + itens_por_pagina - 1) // itens_por_pagina)
        pagina = max(0, min(int(pagina), total_paginas - 1))
        inicio = pagina * itens_por_pagina
        nome_categoria = tipo["plural"].upper()
        embed = criar_embed(
            "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — CENTRAL DE MISSÕES E OPERAÇÕES ・✦",
            (
                "╭────────────── ◈ ──────────────╮\n"
                f"                 **{nome_categoria}  /  TODOS OS JOGOS**\n"
                "╰────────────── ◈ ──────────────╯\n\n"
                "Um catálogo unificado de operações da **NÊMESIS**. "
                "Todas as atividades são válidas para qualquer jogo compatível com a organização. "
                "Não existe divisão de missões por título de jogo.\n\n"
                f"**✧ XP em recompensas abertas**  {xp_disponivel:,} XP\n".replace(",", ".")
                + "**✧ Envio de evidências**  Escolha uma atividade no botão de envio, anexe a imagem e informe um auxiliar, se houver.\n"
                "**✧ Progressão**  O XP é liberado somente após aprovação da equipe.\n"
                "**✧ Integridade**  Uma prova pendente por membro e atividade; envios repetidos são bloqueados."
            ),
            cor=tipo["cor"], rodape=None,
        )
        embed.set_author(name="N̷ÊMESIS  •  DEPARTAMENTO GLOBAL DE OPERAÇÕES")
        embed.add_field(name="◈ OPERAÇÕES ATIVAS", value=f"**{len(abertas):02d}**\nDisponíveis para execução", inline=True)
        embed.add_field(name="◈ ARQUIVADAS", value=f"**{encerradas:02d}**\nMantidas em histórico", inline=True)
        embed.add_field(name="◈ TOTAL REGISTRADO", value=f"**{len(atividades):02d}**\nTodos os jogos", inline=True)
        if not atividades:
            embed.add_field(
                name="╭・CATÁLOGO EM PREPARAÇÃO",
                value="Esta categoria ainda não possui atividades publicadas. Novas operações serão disponibilizadas pela administração.",
                inline=False,
            )
        exibidas = atividades[inicio:inicio + itens_por_pagina]
        for indice, item in enumerate(exibidas, start=inicio + 1):
            recompensa = recompensa_da(item)
            ativa = item.get("ativa", True) is not False
            titulo = str(item.get("titulo") or "Operação sem título").strip()
            descricao = str(item.get("descricao") or "Objetivo não informado.").strip()
            identificador = str(item.get("id") or "—")
            dificuldade = str(item.get("dificuldade") or "").strip()
            if not dificuldade:
                if categoria == "especial" or recompensa >= 60:
                    dificuldade = "Alta"
                elif recompensa >= 25:
                    dificuldade = "Intermediária"
                else:
                    dificuldade = "Moderada"

            linhas = [
                descricao[:145],
                "",
                f"**Código**  `{identificador[:32]}`  ·  **Nível**  {dificuldade[:36]}",
                f"**Recompensa**  {recompensa:,} XP  ·  **Situação**  {'◉ DISPONÍVEL' if ativa else '■ ARQUIVADA'}".replace(",", "."),
            ]
            requisitos = str(item.get("requisitos") or "").strip()
            prazo = str(item.get("prazo") or "").strip()
            if requisitos:
                linhas.append(f"**Requisitos**  {requisitos[:180]}")
            if prazo:
                linhas.append(f"**Prazo**  {prazo[:80]}")
            valor = "\n".join(linhas)[:1024]
            embed.add_field(name=f"◈ {indice:02d}  /  {titulo[:58]}"[:256], value=valor, inline=False)
        if len(atividades) > len(exibidas):
            embed.add_field(
                name="✧ NAVEGAÇÃO DO CATÁLOGO",
                value=(
                    f"Exibindo **{inicio + 1}–{inicio + len(exibidas)}** de "
                    f"**{len(atividades)}** atividades. Utilize o seletor de páginas "
                    "para acessar diretamente qualquer parte do catálogo."
                ),
                inline=False,
            )
        embed.set_footer(
            text=f"CATEGORIA:{categoria} • PAGINA:{pagina + 1}/{total_paginas} • NÊMESIS / TODOS OS JOGOS"
        )
        def tamanho() -> int:
            return len(embed.title or "") + len(embed.description or "") + len(embed.author.name or "") + len(embed.footer.text or "") + sum(len(field.name) + len(field.value) for field in embed.fields)
        while embed.fields and (tamanho() > 5900 or len(embed.fields) > 25):
            embed.remove_field(len(embed.fields) - 1)
        aplicar_identidade_servidor(embed, guild, getattr(self, 'bot', None))
        return embed

    def _embed_selecao_prova(self, categoria: str, pagina: int, total_paginas: int, atividades: list, guild: discord.Guild = None) -> discord.Embed:
        tipo = TIPOS.get(categoria, TIPOS["missao"])
        embed = criar_embed(
            "𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ ENVIO DE EVIDÊNCIAS",
            (
                f"⟡・Selecione a atividade da categoria **{tipo['plural']}** que deseja comprovar.\n\n"
                "Após a seleção, informe o link da imagem hospedada no Discord. "
                "A equipe analisará a evidência antes de liberar o XP."
            ),
            cor=tipo["cor"],
            rodape=None,
        )
        inicio = pagina * 25
        embed.add_field(name="◈ ATIVIDADES DISPONÍVEIS", value=f"**{len(atividades)}** atividades ativas", inline=True)
        embed.add_field(name="◈ PÁGINA", value=f"**{pagina + 1}/{total_paginas}**", inline=True)
        embed.add_field(name="◈ RECOMPENSA", value="XP após aprovação", inline=True)
        if not atividades:
            embed.add_field(name="CATÁLOGO VAZIO", value="Não existem atividades ativas nesta categoria no momento.", inline=False)
        else:
            linhas = []
            for item in atividades[inicio:inicio + 8]:
                codigo = str(item.get("id") or "—")
                titulo = str(item.get("titulo") or "Atividade sem título")
                try:
                    xp = max(0, int(item.get("recompensa_xp", item.get("pontos", 0)) or 0))
                except (TypeError, ValueError, OverflowError):
                    xp = 0
                linhas.append(f"• **{titulo[:58]}** — {codigo} · **{xp:,} XP**".replace(",", "."))
            if len(atividades[inicio:inicio + 25]) > 8:
                linhas.append(f"*+ {len(atividades[inicio:inicio + 25]) - 8} opções nesta página; consulte o seletor.*")
            embed.add_field(name="◈ SELEÇÃO", value="\n".join(linhas)[:1024], inline=False)
        embed.set_footer(text="NÊMESIS • CENTRAL DE OPERAÇÕES • Evidências sujeitas à validação")
        return aplicar_identidade_servidor(embed, guild, self.bot, banner=False)

    async def abrir_seletor_prova(self, interaction: discord.Interaction, categoria: str = "missao"):
        if interaction.guild is None:
            await interaction.response.send_message("Este recurso só pode ser utilizado no servidor da NÊMESIS.", ephemeral=True)
            return
        categoria = categoria if categoria in TIPOS else "missao"
        dados = await missoes._guild(interaction.guild.id)
        atividades = [
            item for item in dados.get("missoes", [])
            if isinstance(item, dict)
            and str(item.get("tipo") or "missao").lower() == categoria
            and item.get("ativa", True) is not False
            and str(item.get("id") or "").strip()
        ]
        atividades.sort(key=lambda item: (str(item.get("titulo") or "").casefold(), str(item.get("id") or "")))
        total_paginas = max(1, (len(atividades) + 24) // 25)
        await interaction.response.send_message(
            view=_card_view_missoes(
                SeletorMissaoProvaView(self, interaction.user.id, categoria, atividades),
                self._embed_selecao_prova(categoria, 0, total_paginas, atividades, interaction.guild),
            ),
            ephemeral=True,
        )

    async def navegar_painel_missoes(self, interaction: discord.Interaction, delta: int) -> None:
        """Percorre páginas da categoria atual sem misturar departamentos."""
        footer = interaction.message.embeds[0].footer.text if interaction.message.embeds else ""
        categoria_match = re.search(r"CATEGORIA:([a-z_]+)", footer)
        pagina_match = re.search(r"PAGINA:(\d+)/(\d+)", footer)
        categoria = categoria_match.group(1) if categoria_match else "missao"
        if categoria not in TIPOS:
            categoria = "missao"
        pagina_atual = int(pagina_match.group(1)) - 1 if pagina_match else 0
        total_paginas = int(pagina_match.group(2)) if pagina_match else 1
        total_paginas = max(1, total_paginas)
        pagina_alvo = (pagina_atual + delta) % total_paginas
        embed = await self._montar_painel_missoes(
            interaction.guild, "todos", categoria, pagina=pagina_alvo
        )
        footer = embed.footer.text or ""
        match = re.search(r"PAGINA:(\d+)/(\d+)", footer)
        total = int(match.group(2)) if match else 1
        await interaction.response.edit_message(
            view=NavegacaoMissoesView(self, categoria=categoria, pagina=pagina_alvo, total_paginas=total, embed=embed),
        )

    async def _limpar_mensagens_missoes_duplicadas(self, guild: discord.Guild) -> int:
        """Remove mensagens antigas do bot sobre missões no canal central, preservando o painel oficial."""
        canal = await self._resolver_canal(guild, 1563995881315897549)
        if canal is None:
            return 0

        paineis = await ranking_missoes_jogos.obter_paineis(guild.id)
        painel_id = int(paineis.get("missoes") or 0)
        bot_id = self.bot.user.id if self.bot.user else 0
        termos = ("miss", "missão", "missões", "operação", "operações", "catálogo de operações")
        removidas = 0

        try:
            async for mensagem in canal.history(limit=1000):
                if mensagem.id == painel_id or mensagem.author.id != bot_id:
                    continue
                if not mensagem.embeds and not mensagem.content:
                    continue

                partes = [mensagem.content or ""]
                for embed in mensagem.embeds:
                    partes.extend([
                        embed.title or "",
                        embed.description or "",
                        embed.author.name if embed.author else "",
                        embed.footer.text or "",
                    ])
                    partes.extend(campo.name + " " + campo.value for campo in embed.fields)
                texto = " ".join(partes).casefold()
                if not any(termo in texto for termo in termos):
                    continue
                try:
                    await mensagem.delete(reason="Limpeza de mensagens duplicadas do sistema de missões NÊMESIS")
                    removidas += 1
                except discord.NotFound:
                    continue
                except (discord.Forbidden, discord.HTTPException):
                    log.warning("Não foi possível remover a mensagem duplicada de missões %s.", mensagem.id)
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Não foi possível consultar o histórico do canal central de missões.")
        return removidas

    async def _atualizar_painel_missoes(self, guild: discord.Guild) -> None:
        # Canal fixo oficial da Central de Missões da NÊMESIS.
        canal_id = 1563995881315897549
        canal = await self._resolver_canal(guild, canal_id)
        if canal is None:
            log.warning("Canal atual de missões não encontrado; painel não publicado.")
            return
        paineis = await ranking_missoes_jogos.obter_paineis(guild.id)
        mensagem = None
        if paineis.get("missoes"):
            try:
                mensagem = await canal.fetch_message(int(paineis["missoes"]))
            except discord.NotFound:
                mensagem = None
            except (discord.Forbidden, discord.HTTPException) as erro:
                log.warning("Não foi possível buscar o painel de missões: %s", erro)
                return
        embed = await self._montar_painel_missoes(guild, "todos", "missao")
        match = re.search(r"PAGINA:(\d+)/(\d+)", embed.footer.text or "")
        total_paginas = int(match.group(2)) if match else 1
        view = NavegacaoMissoesView(self, categoria="missao", pagina=0, total_paginas=total_paginas, embed=embed)
        try:
            if mensagem is None:
                mensagem = await canal.send(view=view)
                await ranking_missoes_jogos.salvar_painel(guild.id, "missoes", mensagem.id)
                try:
                    await mensagem.pin(reason="Painel de navegação de missões NÊMESIS")
                except discord.HTTPException:
                    pass
            else:
                await mensagem.edit(content=None, embeds=[], attachments=[], view=view)
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Não foi possível atualizar o painel de missões.")
            raise

    async def _montar_painel_ranking(self, guild: discord.Guild) -> discord.Embed:
        """Classificação única da NÊMESIS, somando XP de missões em todos os jogos."""
        linhas = await ranking_missoes_jogos.obter_ranking_geral(guild.id, limite=10)
        embed = criar_embed(
            "🏆 RANKING GERAL · NÊMESIS",
            "**CLASSIFICAÇÃO OFICIAL DA ORGANIZAÇÃO**\n"
            "Pontuação consolidada de missões, contribuições e operações especiais em todos os jogos. "
            "A classificação não possui filtros ou categorias separadas por jogo.",
            cor=0x9F2035, rodape=None,
        )
        embed.set_author(name="NÊMESIS  /  CLASSIFICAÇÃO GERAL")
        aplicar_identidade_servidor(embed, guild, getattr(self, "bot", None))
        embed.add_field(name="ESCOPO", value="**Todos os jogos**", inline=True)
        embed.add_field(name="CLASSIFICADOS", value=f"**{len(linhas)}**", inline=True)
        embed.add_field(name="CRITÉRIO", value="**XP acumulado**", inline=True)

        if not linhas:
            embed.description += "\n\nAinda não há participantes classificados. Conclua missões e atividades oficiais e aguarde a validação das evidências."
            embed.add_field(
                name="QUADRO AINDA VAZIO",
                value="As recompensas aprovadas serão somadas automaticamente, independentemente do jogo em que foram conquistadas.",
                inline=False,
            )
        else:
            estatisticas = await ranking_missoes_jogos.obter_estatisticas_jogadores(
                guild.id, [uid for uid, _, _ in linhas], jogo=None
            )
            medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
            for posicao, (uid, nome, pontos) in enumerate(linhas, start=1):
                stats = estatisticas.get(str(uid), {})
                minutos = max(0, int(stats.get("tempo_top", 0))) // 60
                dias, resto = divmod(minutos, 1440)
                horas, minutos = divmod(resto, 60)
                tempo = f"{dias}d {horas}h" if dias else f"{horas}h {minutos}min"
                selo = medalhas.get(posicao, f"#{posicao:02d}")
                embed.description += f"\n\n{selo} <@{uid}> · **{pontos:,} XP**".replace(",", ".")
                embed.add_field(
                    name=f"{selo}  {nome[:70]}  ·  {pontos:,} XP".replace(",", ".")[:256],
                    value=(
                        f"<@{uid}>\n"
                        f"**V / E / D**  `{stats.get('vitorias', 0)} / {stats.get('empates', 0)} / {stats.get('derrotas', 0)}`  ·  "
                        f"**K/D**  `{stats.get('kills', 0)}/{stats.get('deaths', 0)}` ({stats.get('kdr', 0):.2f})\n"
                        f"**XP DE PERFIL**  `{int(stats.get('xp', 0)):,}`  ·  **MVP**  `{stats.get('mvps', 0)}`  ·  "
                        f"**Patente**  `{str(stats.get('patente', '—'))[:40]}`\n"
                        f"**Tempo no Top 10 geral**  `{tempo}`  ·  **Sequência**  `{stats.get('sequencia', 0)}/{stats.get('maior_sequencia', 0)}`"
                    ).replace(",", ".")[:1024],
                    inline=False,
                )
        embed.set_footer(text="NÊMESIS • RANKING GERAL • TODOS OS JOGOS • ATUALIZAÇÃO AUTOMÁTICA")
        return embed

    async def _atualizar_ranking_geral(self, guild: discord.Guild) -> None:
        """Atualiza o painel único de ranking geral sem seletor por jogo."""
        config = await get_config(guild.id)
        canal_id = config.get("canal_ranking_id") or 1545834182406574241
        canal = await self._resolver_canal(guild, int(canal_id))
        if canal is None:
            log.warning("Canal de ranking atual não encontrado; painel não atualizado.")
            return
        paineis = await ranking_missoes_jogos.obter_paineis(guild.id)
        mensagem = None
        if paineis.get("ranking"):
            try:
                mensagem = await canal.fetch_message(int(paineis["ranking"]))
            except discord.NotFound:
                mensagem = None
            except (discord.Forbidden, discord.HTTPException) as erro:
                log.warning("Não foi possível buscar o painel de ranking geral: %s", erro)
                return
        embed = await self._montar_painel_ranking(guild)
        try:
            if mensagem is None:
                mensagem = await canal.send(embed=embed)
                await ranking_missoes_jogos.salvar_painel(guild.id, "ranking", mensagem.id)
                try:
                    await mensagem.pin(reason="Painel de ranking geral NÊMESIS")
                except discord.HTTPException:
                    pass
            else:
                await mensagem.edit(embed=embed, view=None)
        except (discord.Forbidden, discord.HTTPException) as erro:
            if getattr(erro, "code", None) == 30046 and mensagem is not None:
                try:
                    nova_mensagem = await canal.send(embed=embed)
                    await ranking_missoes_jogos.salvar_painel(guild.id, "ranking", nova_mensagem.id)
                except Exception:
                    log.exception("Não foi possível substituir o painel de ranking geral após o limite de edições.")
                    return
                try:
                    await nova_mensagem.pin(reason="Painel de ranking geral NÊMESIS")
                except discord.HTTPException:
                    log.warning("Não foi possível fixar o novo painel de ranking geral.")
                try:
                    await mensagem.delete(reason="Substituição do painel após limite de edições do Discord")
                except (discord.Forbidden, discord.HTTPException):
                    log.warning("O painel antigo de ranking geral não pôde ser removido.")
            else:
                log.exception("Falha ao atualizar o painel de ranking geral.")

    # Compatibilidade temporária para chamadas legadas que ainda passam o slug do jogo.
    async def _atualizar_ranking_jogo(self, guild: discord.Guild, jogo: str = "") -> None:
        await self._atualizar_ranking_geral(guild)

    @staticmethod
    def _expandir_catalogo_por_jogo(catalogo: list) -> list:
        """Compatibilidade histórica: o catálogo agora é único e global."""
        return [dict(item) for item in catalogo if isinstance(item, dict)]

    async def _sincronizar_cartoes_missoes(self, guild: discord.Guild, atividades: list) -> dict:
        """Publica ou edita os cartões individuais, preservando referências existentes."""
        config = await get_config(guild.id)
        canais_por_tipo = {
            "missao": config.get("canal_missoes_missao_id") or CANAIS_PADRAO["canal_missoes_missao_id"],
            "contribuicao": config.get("canal_missoes_contribuicao_id") or CANAIS_PADRAO["canal_missoes_contribuicao_id"],
            "especial": config.get("canal_missoes_especial_id") or CANAIS_PADRAO["canal_missoes_especial_id"],
        }
        resultado = {"publicadas": 0, "atualizadas": 0, "falhas": 0}

        for atividade in atividades:
            missao_id = str(atividade.get("id") or "").strip()
            tipo = str(atividade.get("tipo") or "missao").strip().lower()
            canal_id = canais_por_tipo.get(tipo)
            if not missao_id or not canal_id:
                resultado["falhas"] += 1
                log.error("Missão sem ID ou canal de destino válido: %r", atividade)
                continue

            canal = await self._resolver_canal(guild, int(canal_id))
            if canal is None:
                resultado["falhas"] += 1
                log.error("Canal de publicação da missão %s não encontrado: %s", missao_id, canal_id)
                continue

            embeds = self._montar_embeds(atividade)
            registro = await obter_mensagem_discord(guild.id, missao_id)
            ids_antigos = registro.get("discord_message_ids") or []
            if not ids_antigos and registro.get("discord_message_id"):
                ids_antigos = [registro["discord_message_id"]]
            ids_antigos = [int(valor) for valor in ids_antigos if str(valor).isdigit()]
            canal_antigo_id = registro.get("discord_channel_id")

            try:
                # Se a categoria/canal mudou, cria e registra o novo cartão antes
                # de tentar remover o antigo, evitando perda da publicação.
                mesmo_canal = str(canal_antigo_id or "") == str(canal.id)
                mensagens = []
                if mesmo_canal:
                    for mensagem_id in ids_antigos:
                        try:
                            mensagens.append(await canal.fetch_message(mensagem_id))
                        except discord.NotFound:
                            continue
                    # Não compacta páginas faltantes: isso deslocaria embeds e
                    # poderia atualizar a missão errada. Recria o conjunto inteiro.
                    if len(mensagens) != len(ids_antigos):
                        mensagens = []

                ids_novos = []
                if mensagens:
                    for indice, embed in enumerate(embeds):
                        if indice < len(mensagens):
                            mensagem = mensagens[indice]
                            await mensagem.edit(embed=embed, view=EnviarProvaMissaoView(self) if indice == 0 else None)
                            ids_novos.append(mensagem.id)
                            resultado["atualizadas"] += 1
                        else:
                            mensagem = await canal.send(
                                embed=embed,
                                view=EnviarProvaMissaoView(self) if indice == 0 else None,
                            )
                            ids_novos.append(mensagem.id)
                            resultado["publicadas"] += 1
                    for mensagem_extra in mensagens[len(embeds):]:
                        try:
                            await mensagem_extra.delete(reason="Cartão de missão atualizado pela sincronização NÊMESIS")
                        except (discord.Forbidden, discord.HTTPException):
                            log.warning("Não foi possível remover página excedente da missão %s.", missao_id)
                else:
                    novas = []
                    for indice, embed in enumerate(embeds):
                        mensagem = await canal.send(
                            embed=embed,
                            view=EnviarProvaMissaoView(self) if indice == 0 else None,
                        )
                        novas.append(mensagem)
                        ids_novos.append(mensagem.id)
                        resultado["publicadas"] += 1

                await salvar_mensagem_discord(guild.id, missao_id, canal.id, ids_novos)

                if canal_antigo_id and ids_antigos:
                    canal_limpeza = canal if mesmo_canal else await self._resolver_canal(guild, int(canal_antigo_id))
                    if canal_limpeza is not None:
                        for mensagem_id in ids_antigos:
                            if mesmo_canal and mensagem_id in ids_novos:
                                continue
                            try:
                                antiga = await canal_limpeza.fetch_message(mensagem_id)
                                await antiga.delete(reason="Substituição do cartão pela sincronização oficial NÊMESIS")
                            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                                log.warning("Não foi possível limpar cartão antigo da missão %s (%s).", missao_id, mensagem_id)

            except (discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                resultado["falhas"] += 1
                log.exception("Falha ao sincronizar cartão da missão %s.", missao_id)

        return resultado

    async def _limpar_cartoes_individuais_antigos(self, guild: discord.Guild, atividades: list) -> int:
        """Remove os cartões individuais antigos após a adoção do painel único."""
        removidas = 0
        registros_vistos = set()
        for atividade in atividades:
            missao_id = str(atividade.get("id") or "")
            if not missao_id or missao_id in registros_vistos:
                continue
            registros_vistos.add(missao_id)
            registro = await obter_mensagem_discord(guild.id, missao_id)
            canal_id = registro.get("discord_channel_id")
            ids = registro.get("discord_message_ids") or []
            if not ids and registro.get("discord_message_id"):
                ids = [registro["discord_message_id"]]
            if not canal_id or not ids:
                continue
            canal = await self._resolver_canal(guild, int(canal_id))
            if canal is None:
                continue
            for mensagem_id in ids:
                try:
                    mensagem = await canal.fetch_message(int(mensagem_id))
                    await mensagem.delete(reason="Migração para a central única de missões NÊMESIS")
                    removidas += 1
                except discord.NotFound:
                    continue
                except (discord.Forbidden, discord.HTTPException):
                    log.exception("Não foi possível remover o cartão antigo da missão %s.", missao_id)
        return removidas

    async def sincronizar_missoes_discord(self, guild: discord.Guild) -> dict:
        """Sincroniza o catálogo e mantém painéis navegáveis nos canais existentes."""
        if self._sync_lock.locked():
            return {"atualizadas": 0, "publicadas": 0, "falhas": 0, "ignorada": True}
        async with self._sync_lock:
            catalogo = self._expandir_catalogo_por_jogo(carregar_catalogo())
            atividades = await sincronizar_catalogo(guild.id, catalogo)
            resultado = {"publicadas": 0, "atualizadas": 0, "falhas": 0,
                         "registros_catalogo": len(atividades), "painel_atualizado": False}
            try:
                await self._atualizar_painel_missoes(guild)
                resultado["painel_atualizado"] = True
                resultado["atualizadas"] = 1
                resultado["mensagens_duplicadas_removidas"] = await self._limpar_mensagens_missoes_duplicadas(guild)
                resultado["cartoes_antigos_removidos"] = await self._limpar_cartoes_individuais_antigos(guild, atividades)
            except Exception:
                resultado["falhas"] += 1
                log.exception("Falha ao atualizar o painel único ou limpar mensagens antigas de missões.")
            try:
                await self._atualizar_ranking_geral(guild)
            except Exception:
                resultado["falhas"] += 1
                log.exception("Falha ao atualizar o ranking de missões.")
            log.info(
                "Central única sincronizada: %s missões no catálogo; painel atualizado=%s; falhas=%s.",
                resultado["registros_catalogo"], resultado["painel_atualizado"], resultado["falhas"],
            )
            return resultado
    @app_commands.command(
        name="missoes-sincronizar",
        description="Publica ou atualiza as missões padrão nos canais oficiais.",
    )
    @octogono_only()
    async def missoes_sincronizar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild is None:
            await interaction.followup.send("Use este comando dentro do servidor.", ephemeral=True)
            return
        try:
            resultado = await self.sincronizar_missoes_discord(interaction.guild)
        except Exception as erro:
            log.exception("Erro na sincronização manual das missões.")
            await interaction.followup.send(f"Falha ao sincronizar as missões: `{type(erro).__name__}`.", ephemeral=True)
            return
        await interaction.followup.send(
            "Sincronização concluída. "
            f"Publicadas: **{resultado.get('publicadas', 0)}** · "
            f"Atualizadas: **{resultado.get('atualizadas', 0)}** · "
            f"Falhas: **{resultado.get('falhas', 0)}** · "
            f"Registros do catálogo: **{resultado.get('registros_catalogo', resultado.get('atualizadas', 0))}** · "
            f"Painel geral: **{'atualizado' if resultado.get('painel_atualizado') else 'não confirmado'}**.",
            ephemeral=True,
        )




    async def enviar_painel_relatorios(self, interaction: discord.Interaction) -> None:
        if (
            interaction.guild is None
            or not isinstance(interaction.user, discord.Member)
            or not membro_tem_octogono(interaction.user)
        ):
            await interaction.response.send_message(
                "Os relatórios administrativos são exclusivos da cargo OCTÓGONO.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await self._montar_embed_relatorio_missoes(interaction.guild, "30")
        await interaction.followup.send(
            view=_card_view_missoes(
                RelatoriosMissoesView(self, interaction.user.id, "30"), embed
            ),
            ephemeral=True,
        )


    async def _montar_embed_auditoria_integridade(
        self, guild: discord.Guild, pagina: int = 0
    ) -> discord.Embed:
        from utils import revisoes as revisoes_storage
        revisoes = await revisoes_storage.listar(guild.id)
        resultado = revisoes_storage.analisar_integridade(revisoes, guild.id)
        ocorrencias = resultado["ocorrencias"]
        por_pagina = 5
        total_paginas = max(1, (len(ocorrencias) + por_pagina - 1) // por_pagina)
        pagina = max(0, min(int(pagina), total_paginas - 1))
        inicio = pagina * por_pagina
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  AUDITORIA DE INTEGRIDADE",
            description=(
                "**ACESSO RESTRITO · OCTÓGONO**\n"
                "Diagnóstico somente leitura dos protocolos de missão e suas trilhas de decisão.\n"
                f"**Página:** {pagina + 1}/{total_paginas} · **Ocorrências:** {resultado['total_ocorrencias']}"
            ),
            cor=0x9F2035,
            rodape="NÊMESIS • AUDITORIA DE OPERAÇÕES • SOMENTE LEITURA",
        )
        aplicar_identidade_servidor(embed, guild, self.bot, banner=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else self.bot.user.display_avatar.url)
        embed.add_field(
            name="◈ INTEGRIDADE GERAL",
            value=f"**{resultado['integridade_percentual']:.1f}%** · {resultado['protocolos_analisados']} protocolos analisados",
            inline=False,
        )
        embed.add_field(name="🔴 CRÍTICAS", value=f"**{resultado['criticas']}**", inline=True)
        embed.add_field(name="🟠 ALTAS", value=f"**{resultado['altas']}**", inline=True)
        embed.add_field(name="🟡 MODERADAS", value=f"**{resultado['medias']}**", inline=True)
        embed.add_field(
            name="◈ COMPATIBILIDADE HISTÓRICA",
            value=f"**{resultado['sem_trilha']}** protocolos sem trilha nova (registros legados preservados).",
            inline=False,
        )
        rotulos_eventos = {
            "protocolo_criado": "Protocolo criado",
            "protocolo_aprovado": "Evidência aprovada",
            "protocolo_rejeitado": "Evidência rejeitada",
            "aplicacao_reaberta_apos_falha": "Reaberta após falha de aplicação",
        }
        eventos_recentes = []
        for registro in revisoes:
            trilha = registro.get("trilha_auditoria")
            if not isinstance(trilha, list):
                continue
            for evento in reversed(trilha):
                if not isinstance(evento, dict) or evento.get("evento") not in rotulos_eventos:
                    continue
                try:
                    instante = int(float(evento.get("em")))
                except (TypeError, ValueError, OverflowError):
                    instante = None
                data = f"<t:{instante}:R>" if instante else "data indisponível"
                ator = f"<@{evento['ator_id']}>" if evento.get("ator_id") else "sistema"
                eventos_recentes.append((
                    instante or 0,
                    f"**{rotulos_eventos[evento['evento']]}** · [{registro.get('id', '—')}] · {ator} · {data}"
                ))
        eventos_recentes.sort(key=lambda item: item[0], reverse=True)
        embed.add_field(
            name="◈ HISTÓRICO RECENTE DE DECISÕES",
            value="\n".join(item[1] for item in eventos_recentes[:5])[:1024]
            if eventos_recentes else "Nenhuma decisão nova registrada na trilha. Protocolos antigos permanecem preservados.",
            inline=False,
        )
        if not ocorrencias:
            embed.add_field(
                name="◈ NENHUMA INCONSISTÊNCIA DETECTADA",
                value="Os protocolos analisados não apresentaram divergências nos critérios disponíveis.",
                inline=False,
            )
        for ocorrencia in ocorrencias[inicio:inicio + por_pagina]:
            nivel = {"critica": "🔴 CRÍTICA", "alta": "🟠 ALTA", "media": "🟡 MODERADA"}.get(
                ocorrencia["severidade"], "⚪ INFORMATIVA"
            )
            embed.add_field(
                name=f"{nivel} · {ocorrencia['codigo']}"[:256],
                value=(
                    f"**Protocolo:** `{ocorrencia['protocolo']}` · **{ocorrencia['titulo']}**\n"
                    f"{ocorrencia['descricao']}\n"
                    f"**Participante:** <@{ocorrencia['autor_id']}>"
                    if ocorrencia.get("autor_id") else
                    f"**Protocolo:** `{ocorrencia['protocolo']}` · **{ocorrencia['titulo']}**\n{ocorrencia['descricao']}"
                )[:1024],
                inline=False,
            )
        embed.set_footer(text=f"NÊMESIS • DIAGNÓSTICO SOMENTE LEITURA • Página {pagina + 1}/{total_paginas}")
        return embed

    async def _montar_embed_relatorio_missoes(
        self, guild: discord.Guild, periodo: str = "30", user_id: int = None
    ) -> discord.Embed:
        from utils import revisoes as revisoes_storage
        import time
        todos = await revisoes_storage.listar(guild.id)
        registros = _filtrar_relatorio_missoes(todos, periodo, time.time())
        if user_id:
            uid = str(user_id)
            registros = [
                item for item in registros
                if uid in {str(item.get("autor_id") or ""), str(item.get("auxiliar_id") or "")}
            ]
        aprovadas = [item for item in registros if item.get("status") == "aprovada"]
        rejeitadas = [item for item in registros if item.get("status") == "rejeitada"]
        pendentes = [item for item in registros if item.get("status") == "pendente"]
        xp_total = 0
        for item in aprovadas:
            recompensa = item.get("recompensa_xp")
            if recompensa is None:
                continue
            try:
                recompensa = max(0, int(recompensa))
            except (TypeError, ValueError, OverflowError):
                continue
            autor = str(item.get("autor_id") or "")
            auxiliar = str(item.get("auxiliar_id") or "")
            if user_id:
                uid = str(user_id)
                if auxiliar and auxiliar != autor:
                    parte_autor = (recompensa * 60 + 50) // 100
                    xp_total += parte_autor if uid == autor else recompensa - parte_autor if uid == auxiliar else 0
                elif uid == autor:
                    xp_total += recompensa
            else:
                xp_total += recompensa
        nome_periodo = PERIODOS_RELATORIOS.get(periodo, PERIODOS_RELATORIOS["30"])[0]
        membro = guild.get_member(int(user_id)) if user_id else None
        titulo = "RELATÓRIO INDIVIDUAL" if user_id else "RELATÓRIO EXECUTIVO"
        descricao = (
            f"**INTEGRANTE** · {membro.mention if membro else f'<@{user_id}>'}\n"
            if user_id else "**ACESSO RESTRITO · OCTÓGONO**\n"
        )
        descricao += f"Apuração: **{nome_periodo}** · Base: evidências oficiais de missões."
        embed = criar_embed(
            title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  {titulo}",
            description=descricao,
            cor=0x9F2035,
            rodape="NÊMESIS • RELATÓRIOS ADMINISTRATIVOS • DADOS AUDITÁVEIS",
        )
        aplicar_identidade_servidor(embed, guild, self.bot, banner=True)
        if membro:
            embed.set_thumbnail(url=membro.display_avatar.url)
        embed.add_field(name="◈ VOLUME", value=f"**{len(registros)}** protocolos", inline=True)
        embed.add_field(
            name="◈ RESULTADOS",
            value=f"**{len(aprovadas)}** aprovadas\n**{len(rejeitadas)}** rejeitadas\n**{len(pendentes)}** pendentes",
            inline=True,
        )
        embed.add_field(
            name="◈ XP REGISTRADO",
            value=f"**{xp_total:,} XP** em recompensas persistidas".replace(",", "."),
            inline=True,
        )
        por_categoria = {}
        for item in registros:
            tipo = str(item.get("tipo") or "missao")
            por_categoria.setdefault(tipo, {"aprovada": 0, "rejeitada": 0, "pendente": 0})
            por_categoria[tipo][item["status"]] += 1
        linhas = []
        rotulos = {"missao": "Missões", "contribuicao": "Contribuições", "especial": "Operações especiais", "pve": "PvE"}
        for tipo, dados in sorted(por_categoria.items()):
            linhas.append(
                f"**{rotulos.get(tipo, tipo.title())}** · {dados['aprovada']} aprovadas · "
                f"{dados['rejeitada']} rejeitadas · {dados['pendente']} pendentes"
            )
        embed.add_field(
            name="◈ PRODUTIVIDADE POR CATEGORIA",
            value="\n".join(linhas)[:1024] if linhas else "Nenhum protocolo no período selecionado.",
            inline=False,
        )
        embed.add_field(
            name="◈ CRITÉRIOS DE AUDITORIA",
            value=(
                "O período filtra pela data de envio da evidência. Protocolos sem data confiável "
                "só aparecem em Todo o histórico. XP contabilizado apenas em aprovações com "
                "recompensa persistida; a exportação detalha a divisão de 60%/40% quando há auxiliar."
            ),
            inline=False,
        )
        embed.set_footer(text="NÊMESIS • EXPORTAÇÃO CSV DISPONÍVEL • ACESSO EXCLUSIVO À LIDERANÇA")
        return embed

    async def _montar_embed_inteligencia(
        self, guild: discord.Guild, pagina: int = 0
    ) -> discord.Embed:
        from utils import revisoes as revisoes_storage
        import time

        revisoes = await revisoes_storage.listar(guild.id)
        metricas = _calcular_inteligencia_missoes(revisoes, time.time())
        pagina = max(0, min(int(pagina), 3))
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  INTELIGÊNCIA DE OPERAÇÕES",
            description=(
                "**ACESSO RESTRITO · OCTÓGONO**\n"
                "Visão consolidada da execução, validação e distribuição de recompensas das missões."
            ),
            cor=0x9F2035,
            rodape=f"NÊMESIS • INTELIGÊNCIA ADMINISTRATIVA • Página {pagina + 1}/4",
        )
        aplicar_identidade_servidor(embed, guild, self.bot, banner=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else self.bot.user.display_avatar.url)

        if pagina == 0:
            embed.add_field(
                name="◈ VOLUME OPERACIONAL",
                value=(
                    f"**{metricas['total']}** evidências registradas\n"
                    f"**{metricas['aprovadas']}** aprovadas · **{metricas['rejeitadas']}** rejeitadas\n"
                    f"**{metricas['pendentes']}** aguardando análise"
                ),
                inline=True,
            )
            embed.add_field(
                name="◈ EFICIÊNCIA DE VALIDAÇÃO",
                value=(
                    f"**{metricas['taxa_aprovacao']:.1f}%** de aprovação\n"
                    f"Base: {metricas['aprovadas'] + metricas['rejeitadas']} decisões concluídas"
                ),
                inline=True,
            )
            embed.add_field(
                name="◈ RECOMPENSAS DISTRIBUÍDAS",
                value=f"**{metricas['xp_distribuido']:,} XP** confirmados".replace(",", "."),
                inline=True,
            )
            embed.add_field(
                name="◈ PARTICIPAÇÃO",
                value=(
                    f"**{metricas['participantes']}** participantes no histórico\n"
                    f"**{metricas['ativos_7d']}** participantes envolvidos nos últimos 7 dias\n"
                    f"**{metricas['envios_7d']}** evidências recebidas nos últimos 7 dias"
                ),
                inline=False,
            )
            embed.add_field(
                name="◈ LEITURA EXECUTIVA",
                value=(
                    "A taxa de aprovação considera apenas decisões concluídas. "
                    "Evidências pendentes não entram no denominador. "
                    "O XP considera exclusivamente recompensas persistidas em protocolos aprovados."
                ),
                inline=False,
            )
        elif pagina == 1:
            nomes = {
                "missao": "Missões",
                "contribuicao": "Contribuições",
                "especial": "Missões especiais",
                "pve": "PvE",
            }
            linhas = []
            for tipo, dados in sorted(metricas["categorias"].items()):
                linhas.append(
                    f"**{nomes.get(tipo, tipo.title())}**\n"
                    f"Aprovadas: {dados['aprovadas']} · Rejeitadas: {dados['rejeitadas']} · Pendentes: {dados['pendentes']}"
                )
            embed.add_field(
                name="◈ DESEMPENHO POR CATEGORIA",
                value="\n\n".join(linhas)[:1024] if linhas else "Nenhuma evidência de missão registrada.",
                inline=False,
            )
            ranking = metricas["ranking"]
            if ranking:
                medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
                linhas_ranking = [
                    f"{medalhas.get(pos, f'#{pos:02d}')} <@{uid}> · **{xp:,} XP**".replace(",", ".")
                    for pos, (uid, xp) in enumerate(ranking, start=1)
                ]
                embed.add_field(
                    name="◈ MAIORES CONTRIBUINTES",
                    value="\n".join(linhas_ranking),
                    inline=False,
                )
            embed.add_field(
                name="◈ CRITÉRIOS DE APURAÇÃO",
                value=(
                    "Participante ativo: integrante vinculado a uma evidência enviada nos últimos 7 dias. "
                    "Contribuições com auxiliar seguem a divisão oficial de 60%/40%. "
                    "Registros antigos sem recompensa persistida não são estimados."
                ),
                inline=False,
            )
        elif pagina == 2:
            participantes = _calcular_inteligencia_participantes(revisoes, time.time())
            embed.add_field(
                name="◈ VISÃO DE PARTICIPANTES",
                value=(
                    f"**{participantes['total']}** integrantes com histórico de missões\n"
                    f"**{participantes['ativos_7d']}** com atividade nos últimos 7 dias\n"
                    f"**{participantes['inativos_14d']}** sem envio há pelo menos 14 dias"
                ),
                inline=False,
            )
            linhas_ativos = []
            for pos, perfil in enumerate(participantes["mais_ativos"][:5], start=1):
                membro = guild.get_member(int(perfil["user_id"]))
                nome = membro.mention if membro else f"<@{perfil['user_id']}>"
                linhas_ativos.append(
                    (
                        f"**#{pos:02d}** {nome} · **{perfil['envios']}** envios · "
                        f"**{perfil['xp_missoes']:,} XP** acumulados\n"
                        f"Últimos 30 dias: **{perfil['xp_ultimos_30d']:,} XP** · "
                        f"30 dias anteriores: **{perfil['xp_30d_anteriores']:,} XP**"
                    ).replace(",", ".")
                )
            embed.add_field(
                name="◈ PARTICIPANTES MAIS ATIVOS",
                value="\n".join(linhas_ativos)[:1024] if linhas_ativos else "Sem atividade nos últimos 7 dias.",
                inline=False,
            )
            linhas_inativos = []
            for perfil in participantes["inativos"]:
                nome = f"<@{perfil['user_id']}>"
                dias = perfil["dias_sem_atividade"]
                detalhe = f"{dias} dias sem envio" if dias is not None else "Data de atividade indisponível"
                linhas_inativos.append(
                    f"{nome} · {perfil['envios']} envios históricos · {detalhe}"
                )
            embed.add_field(
                name="◈ ACOMPANHAMENTO DE INATIVIDADE",
                value="\n".join(linhas_inativos)[:1024] if linhas_inativos else "Nenhum participante com inatividade superior a 14 dias.",
                inline=False,
            )
            embed.add_field(
                name="◈ NOTA DE LEITURA",
                value=(
                    "A análise considera somente participantes que já enviaram evidências oficiais. "
                    "Inatividade é medida desde o último envio de evidência, não desde mensagens gerais do servidor. "
                    "XP apresentado é exclusivo de missões e não substitui a progressão organizacional."
                ),
                inline=False,
            )
        elif pagina == 3:
            qualidade = revisoes_storage.analisar_qualidade(revisoes, time.time(), 30)
            embed.add_field(name="◈ AMOSTRA ANALISADA", value=f"**{qualidade['evidencias_analisadas']}** evidências · últimos 30 dias", inline=True)
            embed.add_field(name="◈ EVIDÊNCIAS REPETIDAS", value=f"**{len(qualidade['duplicidades'])}** grupos com hash idêntico", inline=True)
            embed.add_field(name="◈ PADRÕES DE ENVIO", value=f"**{len(qualidade['padroes_envio'])}** padrões de alta frequência", inline=True)
            duplicadas = qualidade["duplicidades"][:5]
            linhas = [
                f"Hash `{x['hash_prefixo']}` · **{x['quantidade']}** protocolos · "
                f"{', '.join(x['participantes'][:4]) or 'participante não identificado'} · "
                f"{', '.join(x['protocolos'][:4])}"
                for x in duplicadas
            ]
            embed.add_field(name="◈ REUTILIZAÇÃO DE EVIDÊNCIAS · HISTÓRICO", value="\n".join(linhas)[:1024] if linhas else "Nenhum hash de imagem repetido identificado.", inline=False)
            linhas = [f"<@{x['autor_id']}> · **{x['envios_10min']}** envios em 10 min" for x in qualidade["padroes_envio"][:5]]
            embed.add_field(name="◈ FREQUÊNCIA DE ENVIOS", value="\n".join(linhas)[:1024] if linhas else "Nenhum padrão de alta frequência identificado.", inline=False)
            linhas = []
            for x in qualidade["revisores"][:6]:
                mediana = f"{x['mediana_minutos']:.0f} min" if x["mediana_minutos"] is not None else "tempo indisponível"
                alerta = " · amostra com rejeições elevadas" if x["alerta_amostra"] else ""
                linhas.append(f"<@{x['revisor_id']}> · {x['decisoes']} decisões · mediana {mediana} · {x['taxa_rejeicao']:.0f}% rejeições{alerta}")
            embed.add_field(name="◈ INDICADORES DE REVISÃO", value="\n".join(linhas)[:1024] if linhas else "Sem decisões com timestamps confiáveis no período.", inline=False)
            embed.add_field(name="◈ PROTOCOLO DE INTERPRETAÇÃO", value="Envios e decisões: últimos 30 dias. Hashes: histórico completo. Indicadores sinalizam padrões para conferência humana; hash idêntico pode ocorrer por reenvio legítimo, e frequência ou taxa de rejeição não comprova irregularidade. Tempos usam apenas datas válidas.", inline=False)

        embed.set_footer(text="NÊMESIS • DADOS DE REVISÕES OFICIAIS • ACESSO EXCLUSIVO À LIDERANÇA")
        return embed

    async def enviar_painel_inteligencia(self, interaction: discord.Interaction) -> None:
        if (
            interaction.guild is None
            or not isinstance(interaction.user, discord.Member)
            or not membro_tem_octogono(interaction.user)
        ):
            await interaction.response.send_message(
                "A Central de Inteligência é restrita à cargo OCTÓGONO.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        embed = await self._montar_embed_inteligencia(interaction.guild, 0)
        await interaction.followup.send(
            view=_card_view_missoes(
                InteligenciaMissoesView(self, interaction.user.id, 0), embed
            ),
            ephemeral=True,
        )

    def _montar_embed_historico_desempenho(
        self, guild: discord.Guild, user_id: int, registros: list, pagina: int
    ) -> discord.Embed:
        """Monta uma página do histórico completo com motivo de rejeição."""
        inicio = pagina * 5
        itens = registros[inicio:inicio + 5]
        membro = guild.get_member(int(user_id)) if guild else None
        nome = membro.mention if membro else f"<@{user_id}>"
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  HISTÓRICO DE EVIDÊNCIAS",
            description=(
                f"**INTEGRANTE** · {nome}\n"
                "Registro cronológico de protocolos enviados para validação."
            ),
            cor=0x9F2035,
            rodape=f"NÊMESIS • HISTÓRICO PRIVADO • Página {pagina + 1}/{max(1, (len(registros) + 4) // 5)}",
        )
        aplicar_identidade_servidor(embed, guild, self.bot, banner=True)
        if membro:
            embed.set_thumbnail(url=membro.display_avatar.url)
        if not itens:
            embed.description += "\n\nNenhuma evidência foi registrada para este integrante."
            return embed

        rotulos = {
            "missao": "Missão",
            "contribuicao": "Contribuição",
            "especial": "Operação especial",
            "pve": "PvE",
        }
        for indice, registro in enumerate(itens, start=inicio + 1):
            status = str(registro.get("status") or "desconhecido").lower()
            status_texto = {
                "aprovada": "✓ APROVADA",
                "rejeitada": "✕ REJEITADA",
                "pendente": "◷ EM ANÁLISE",
            }.get(status, status.upper())
            autor_id = str(registro.get("autor_id") or "")
            auxiliar_id = str(registro.get("auxiliar_id") or "")
            papel = "Auxiliar" if auxiliar_id == str(user_id) and autor_id != str(user_id) else "Responsável"
            titulo = str(registro.get("titulo") or "Atividade sem título").strip()[:100]
            protocolo = str(registro.get("id") or "—")[:24]
            tipo = rotulos.get(str(registro.get("tipo") or "").lower(), "Atividade")
            data = (
                registro.get("aprovado_em") if status == "aprovada"
                else registro.get("rejeitada_em") if status == "rejeitada"
                else registro.get("timestamp")
            )
            try:
                data_texto = f"<t:{int(float(data))}:f>" if data else "Data não registrada"
            except (TypeError, ValueError, OverflowError):
                data_texto = "Data não registrada"
            linhas = [
                f"**{status_texto}** · {tipo} · {papel}",
                f"Protocolo: `{protocolo}` · {data_texto}",
            ]
            if auxiliar_id and autor_id != auxiliar_id:
                outro_id = autor_id if papel == "Auxiliar" else auxiliar_id
                linhas.append(f"Participante vinculado: <@{outro_id}>")
            recompensa = registro.get("recompensa_xp")
            if recompensa is not None:
                try:
                    linhas.append(f"Recompensa registrada: **{max(0, int(recompensa)):,} XP**".replace(",", "."))
                except (TypeError, ValueError, OverflowError):
                    pass
            motivo = str(registro.get("motivo_rejeicao") or "").strip()
            if status == "rejeitada":
                linhas.append(f"Justificativa: {motivo[:500]}" if motivo else "Justificativa: não registrada no histórico legado.")
            embed.add_field(
                name=f"{indice:02d} · {titulo}",
                value="\n".join(linhas)[:1024],
                inline=False,
            )
        return embed

    async def enviar_painel_desempenho(self, interaction: discord.Interaction) -> None:
        """Abre um dossiê privado de desempenho sem adicionar comando slash."""
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Este painel só pode ser consultado dentro do servidor da NÊMESIS.",
                ephemeral=True,
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        from utils import revisoes as revisoes_storage
        from cogs.progressao_gangue import rank_por_xp, proximo_rank, barra_progresso

        revisoes = await revisoes_storage.listar(guild.id)
        resumo = _resumir_desempenho_missoes(revisoes, interaction.user.id, limite=5)
        progressao = self.bot.get_cog("ProgressaoGangue")
        perfil_progressao = (
            await progressao._perfil(guild.id, interaction.user.id)
            if progressao is not None else {}
        )
        try:
            xp_progressao = max(0, int(perfil_progressao.get("xp", 0) or 0))
        except (TypeError, ValueError, OverflowError):
            xp_progressao = 0
        rank = rank_por_xp(xp_progressao)
        proximo = proximo_rank(xp_progressao)
        progresso = barra_progresso(xp_progressao, rank, proximo)
        destino = (
            f"**{proximo['nome']}** · faltam **{max(0, int(proximo['xp']) - xp_progressao):,} XP**".replace(",", ".")
            if proximo else "**Posto máximo alcançado**"
        )

        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  DOSSIÊ DE DESEMPENHO",
            description=(
                f"**INTEGRANTE** · {interaction.user.mention}\n"
                "Acompanhamento individual de missões validadas, evidências e progressão organizacional."
            ),
            cor=0x9F2035,
            rodape="NÊMESIS • CENTRAL DE DESEMPENHO • Dados de evidências oficiais",
        )
        aplicar_identidade_servidor(embed, guild, self.bot, banner=True)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.add_field(
            name="◈ RESULTADO DAS MISSÕES",
            value=(
                f"**{resumo['aprovadas']}** aprovadas\n"
                f"**{resumo['rejeitadas']}** recusadas\n"
                f"**{resumo['pendentes']}** em análise"
            ),
            inline=True,
        )
        embed.add_field(
            name="◈ XP DE MISSÕES",
            value=(
                f"**+{resumo['xp_missoes']:,} XP** rastreáveis\n"
                f"{resumo['registros_com_xp']} aprovações com recompensa registrada"
            ).replace(",", "."),
            inline=True,
        )
        embed.add_field(
            name="◈ PROGRESSÃO ORGANIZACIONAL",
            value=(
                f"**Nº {rank['no']:02d} · {rank['nome']}**\n"
                f"**{xp_progressao:,} XP totais**\n{progresso}\nPróximo posto: {destino}"
            ).replace(",", "."),
            inline=False,
        )

        recentes = resumo["recentes"]
        if recentes:
            linhas = []
            for registro in recentes:
                status = {
                    "aprovada": "✓ Aprovada",
                    "rejeitada": "✕ Recusada",
                    "pendente": "◷ Em análise",
                }[registro["status"]]
                titulo = str(registro.get("titulo") or "Atividade")[:55]
                protocolo = str(registro.get("id") or "—")[:12]
                papel = "Auxiliar" if str(registro.get("auxiliar_id")) == str(interaction.user.id) else "Responsável"
                data = registro.get("aprovado_em") or registro.get("rejeitada_em") or registro.get("timestamp")
                data_texto = f" · <t:{int(float(data))}:d>" if data else ""
                linhas.append(f"**{status}** · {titulo}\n{protocolo} · {papel}{data_texto}")
            embed.add_field(name="◈ HISTÓRICO RECENTE", value="\n".join(linhas)[:1024], inline=False)

        tipos_validos = {"missao", "contribuicao", "especial", "pve"}
        aprovadas_gerais = sum(
            1 for item in revisoes if isinstance(item, dict)
            and item.get("status") == "aprovada"
            and str(item.get("tipo", "")).lower() in tipos_validos
        )
        pendentes_gerais = sum(
            1 for item in revisoes if isinstance(item, dict)
            and item.get("status") == "pendente"
            and str(item.get("tipo", "")).lower() in tipos_validos
        )
        embed.add_field(
            name="◈ OPERAÇÃO DA COMUNIDADE",
            value=f"**{aprovadas_gerais}** evidências aprovadas · **{pendentes_gerais}** aguardando análise",
            inline=False,
        )
        ranking = _ranking_xp_missoes(revisoes, limite=5)
        if ranking:
            linhas_ranking = []
            medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
            for posicao, (uid, xp) in enumerate(ranking, start=1):
                selo = medalhas.get(posicao, f"#{posicao:02d}")
                linhas_ranking.append(f"{selo} <@{uid}> · **{xp:,} XP**".replace(",", "."))
            embed.add_field(
                name="◈ CLASSIFICAÇÃO DE MISSÕES",
                value="\n".join(linhas_ranking),
                inline=False,
            )
        embed.set_footer(text="NÊMESIS • XP de missões calculado apenas com recompensas persistidas")
        await interaction.followup.send(
            view=_card_view_missoes(
                HistoricoDesempenhoView(self, interaction.user.id, resumo["historico"]), embed
            ),
            ephemeral=True,
        )

    async def processar_aprovacao(self, guild: discord.Guild, revisao: dict) -> str:
        atividade = await missoes.get(guild.id, revisao.get("referencia_id", ""))
        if not atividade:
            return "⚠️ A atividade original não foi encontrada; nenhuma recompensa foi aplicada."

        revisao_id = str(revisao.get("id", "")).strip()
        if not revisao_id:
            return "⚠️ Esta revisão não possui um identificador válido; nenhuma recompensa foi aplicada."

        autor_id = int(revisao.get("autor_id", 0) or 0)
        if not autor_id:
            return "⚠️ Não foi possível identificar o participante."

        try:
            auxiliar_id = int(revisao.get("auxiliar_id") or 0)
        except (TypeError, ValueError):
            auxiliar_id = 0
        if auxiliar_id == autor_id:
            auxiliar_id = 0

        # A recompensa registrada na evidência é a referência imutável do protocolo.
        # Missões editadas depois do envio não podem alterar o XP prometido ao participante.
        recompensa_registrada = revisao.get("recompensa_xp")
        try:
            recompensa = max(
                0,
                int(
                    recompensa_registrada
                    if recompensa_registrada is not None
                    else atividade.get("recompensa_xp", atividade.get("pontos", 0))
                    or 0
                ),
            )
        except (TypeError, ValueError, OverflowError):
            recompensa = 0

        # Sem auxiliar, mantém compatibilidade com o marcador histórico da revisão.
        # Com auxiliar, cada participante recebe um evento próprio e recuperável.
        atividade_ja_aplicada = revisao_id in atividade.get("recompensas_aplicadas", [])
        if auxiliar_id:
            distribuicao = [
                (autor_id, ((recompensa * 60 + 50) // 100)),
                (auxiliar_id, recompensa - ((recompensa * 60 + 50) // 100)),
            ]
        else:
            distribuicao = [(autor_id, recompensa)]

        resultados = []
        async with self._reward_lock:
            for usuario_id, quantidade in distribuicao:
                evento_perfil = (
                    f"{revisao_id}:{usuario_id}"
                    if auxiliar_id
                    else revisao_id
                )
                estado_aplicacao = {"aplicada": False}

                def aplicar_recompensa(perfil):
                    eventos_aplicados = list(
                        perfil.get("recompensas_missoes_aplicadas", [])
                    )
                    marcador_novo = evento_perfil not in eventos_aplicados
                    recompensa_aplicada = (
                        marcador_novo
                        and (bool(auxiliar_id) or not atividade_ja_aplicada)
                    )
                    if marcador_novo:
                        eventos_aplicados.append(evento_perfil)
                        perfil["recompensas_missoes_aplicadas"] = eventos_aplicados[-1000:]
                    if recompensa_aplicada:
                        perfil["xp"] = int(perfil.get("xp", 0) or 0) + quantidade
                    estado_aplicacao["aplicada"] = bool(recompensa_aplicada)
                    return perfil

                perfil = await atualizar_perfil(
                    guild.id, usuario_id, aplicar_recompensa
                )
                recompensa_aplicada = estado_aplicacao["aplicada"]

                resultados.append({
                    "user_id": usuario_id,
                    "quantidade": quantidade,
                    "perfil": perfil,
                    "aplicada": bool(recompensa_aplicada),
                    "evento_perfil": evento_perfil,
                })

        # Registra XP na progressão interna com chave idempotente por membro.
        progressao = self.bot.get_cog("ProgressaoGangue")
        tipo_progressao = str(atividade.get("tipo", "missao")).lower()
        if tipo_progressao not in {"missao", "contribuicao", "especial"}:
            tipo_progressao = "missao"

        for resultado in resultados:
            usuario_id = resultado["user_id"]
            quantidade = resultado["quantidade"]
            evento_id = (
                f"missao:{revisao_id}:{usuario_id}"
                if auxiliar_id
                else f"missao:{revisao_id}"
            )

            if resultado["aplicada"] and quantidade > 0:
                membro_ranking = guild.get_member(usuario_id)
                try:
                    await ranking_missoes_jogos.registrar_pontos_gerais(
                        guild_id=guild.id,
                        user_id=usuario_id,
                        nome=membro_ranking.display_name if membro_ranking else "",
                        pontos=quantidade,
                        evento_id=f"missao:{revisao_id}:{usuario_id}",
                    )
                    await self._atualizar_ranking_geral(guild)
                except Exception as erro:
                    log.exception(
                        "Falha ao atualizar ranking geral para %s: %s",
                        usuario_id,
                        erro,
                    )

            if progressao is not None and quantidade > 0:
                try:
                    await progressao.registrar_recompensa(
                        guild=guild,
                        user_id=usuario_id,
                        quantidade=quantidade,
                        tipo=tipo_progressao,
                        evento_id=evento_id,
                    )
                except Exception as erro:
                    log.exception(
                        "Falha ao registrar recompensa da missão para %s: %s",
                        usuario_id,
                        erro,
                    )


        await missoes.registrar_recompensa_aplicada(
            guild.id, str(atividade.get("id")), str(revisao_id)
        )

        mensagens = []
        for resultado in resultados:
            usuario_id = resultado["user_id"]
            quantidade = resultado["quantidade"]
            perfil = resultado["perfil"]
            membro = guild.get_member(usuario_id)

            if resultado["aplicada"]:
                mensagens.append(
                    f"<@{usuario_id}> recebeu **+{quantidade} XP**"
                )
            else:
                mensagens.append(
                    f"<@{usuario_id}> já tinha a recompensa registrada; nenhum crédito duplicado foi adicionado"
                )

            nova_patente = await calcular_patente_atual(guild.id, perfil["xp"])
            if nova_patente and nova_patente.get("nome") != perfil.get("patente"):
                await definir_patente(guild.id, usuario_id, nova_patente["nome"])
                cargo_id = nova_patente.get("cargo_id")
                cargo = guild.get_role(int(cargo_id)) if cargo_id else None
                if membro and cargo:
                    try:
                        await membro.add_roles(
                            cargo,
                            reason="Promoção automática por conclusão de missão",
                        )
                    except discord.Forbidden:
                        pass
                mensagens[-1] += f" • Nova patente: **{nova_patente['nome']}**"

        if auxiliar_id:
            cabecalho = (
                f"✅ Recompensa dividida: **{((recompensa * 60 + 50) // 100)} XP** para o responsável "
                f"e **{recompensa - ((recompensa * 60 + 50) // 100)} XP** para o auxiliar.\n"
            )
        else:
            cabecalho = "✅ Recompensa da missão aprovada.\n"
        return cabecalho + "\n".join(mensagens)

    @app_commands.command(
        name="missao-enviar-prova",
        description="Envie a prova de uma missão com anexo, sem copiar links ou IDs."
    )
    @app_commands.describe(
        missao_id="Escolha a missão pelo nome ou código",
        prova="Anexe a imagem da prova diretamente aqui",
        auxiliar="Selecione o auxiliar (opcional)"
    )
    async def missao_enviar_prova(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        prova: discord.Attachment,
        auxiliar: discord.Member = None,
    ):
        """Recebe a imagem como anexo e seleciona missão/auxiliar pelo Discord."""
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use este comando dentro do servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        if not (prova.content_type or "").lower().startswith("image/"):
            await interaction.response.send_message(
                "O arquivo precisa ser uma imagem. Anexe PNG, JPG, JPEG, WEBP ou outro formato de imagem.",
                ephemeral=True,
            )
            return

        if prova.size > 10 * 1024 * 1024:
            await interaction.response.send_message(
                "A imagem ultrapassa o limite de 10 MB. Envie uma versão menor.",
                ephemeral=True,
            )
            return

        # O seletor de usuário nativo elimina a necessidade de copiar IDs.
        auxiliar_texto = str(auxiliar.id) if auxiliar else ""
        await self.receber_prova_modal(
            interaction,
            str(missao_id),
            str(prova.url),
            auxiliar_texto,
        )

    @missao_enviar_prova.autocomplete("missao_id")
    async def autocomplete_missao_id(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Sugere missões ativas por título e código para evitar digitação de IDs."""
        if interaction.guild is None:
            return []
        try:
            dados = await missoes._guild(interaction.guild.id)
            atividades = [
                item for item in dados.get("missoes", [])
                if isinstance(item, dict) and item.get("ativa", True) is not False
            ]
            termo = current.casefold().strip()
            atividades = [
                item for item in atividades
                if termo in str(item.get("id", "")).casefold()
                or termo in str(item.get("titulo", "")).casefold()
            ]
            atividades.sort(key=lambda item: (
                str(item.get("jogo", "")).casefold(),
                str(item.get("titulo", "")).casefold(),
            ))
            escolhas = []
            for item in atividades[:25]:
                codigo = str(item.get("id", "")).strip()
                titulo = str(item.get("titulo", "Missão")).strip()
                if not codigo:
                    continue
                label = f"{titulo} — {codigo}"[:100]
                escolhas.append(app_commands.Choice(name=label, value=codigo[:100]))
            return escolhas
        except Exception:
            log.exception("Falha ao carregar sugestões de missões para autocomplete.")
            return []

    async def receber_prova_modal(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        imagem_url: str,
        auxiliar_texto: str = "",
    ):
        """Valida a missão, o auxiliar opcional e encaminha a prova para revisão."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Use este botão dentro do servidor da NÊMESIS.", ephemeral=True)
            return

        auxiliar_id = None
        auxiliar_valor = auxiliar_texto.strip()
        if auxiliar_valor:
            mencao = re.fullmatch(r"<@!?(\d+)>", auxiliar_valor)
            id_direto = re.fullmatch(r"\d{15,22}", auxiliar_valor)
            if mencao:
                auxiliar_id = int(mencao.group(1))
            elif id_direto:
                auxiliar_id = int(auxiliar_valor)
            else:
                await interaction.followup.send(
                    "❌ Auxiliar inválido. Informe uma menção como @membro ou o ID numérico do Discord.",
                    ephemeral=True,
                )
                return

            if auxiliar_id == interaction.user.id:
                await interaction.followup.send(
                    "❌ Você não pode selecionar a si mesmo como auxiliar.",
                    ephemeral=True,
                )
                return

            try:
                auxiliar = await guild.fetch_member(auxiliar_id)
            except discord.NotFound:
                await interaction.followup.send(
                    "❌ Esse auxiliar não é membro deste servidor.",
                    ephemeral=True,
                )
                return
            except (discord.Forbidden, discord.HTTPException):
                log.exception("Não foi possível validar o auxiliar %s no servidor %s.", auxiliar_id, guild.id)
                await interaction.followup.send(
                    "❌ Não consegui validar o auxiliar agora. Tente novamente em instantes.",
                    ephemeral=True,
                )
                return

            if auxiliar.bot:
                await interaction.followup.send(
                    "❌ O auxiliar precisa ser uma pessoa, não um bot.",
                    ephemeral=True,
                )
                return

        atividade = await missoes.get(guild.id, missao_id.strip())
        if not atividade or not atividade.get("ativa", True):
            await interaction.followup.send(
                "❌ Não encontrei uma missão ativa com esse ID. Confira o ID na publicação da missão.",
                ephemeral=True,
            )
            return

        tipo = str(atividade.get("tipo", "missao")).lower()
        if tipo not in TIPOS:
            await interaction.followup.send(
                "❌ O tipo desta atividade está inválido. Avise a staff.",
                ephemeral=True,
            )
            return

        url = imagem_url.strip()
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or host not in {"cdn.discordapp.com", "media.discordapp.net"}
            or not parsed.path
        ):
            await interaction.followup.send(
                "❌ O link precisa ser de uma imagem hospedada no Discord. Envie a imagem em um canal permitido, abra a imagem, copie o link e cole aqui.",
                ephemeral=True,
            )
            return

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.followup.send(
                "❌ O sistema de revisão não está carregado. Avise a staff.",
                ephemeral=True,
            )
            return

        from utils import revisoes

        pendentes = await revisoes.listar(guild.id, status="pendente")
        ja_enviada = any(
            int(item.get("autor_id", 0) or 0) == interaction.user.id
            and str(item.get("referencia_id", "")) == str(atividade["id"])
            and item.get("tipo") == tipo
            for item in pendentes
        )
        if ja_enviada:
            await interaction.followup.send(
                "⏳ Você já tem uma prova pendente para esta missão. Aguarde a análise da staff antes de enviar outra.",
                ephemeral=True,
            )
            return

        info = TIPOS[tipo]
        recompensa = max(
            0,
            int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0),
        )
        if auxiliar_id and recompensa < 2:
            await interaction.followup.send(
                "❌ Esta missão oferece menos de 2 XP; não é possível dividir a recompensa entre duas pessoas.",
                ephemeral=True,
            )
            return

        canal_config = await get_config(guild.id)
        chave_prova = {
            "missao": "canal_provas_missao_id",
            "contribuicao": "canal_provas_contribuicao_id",
            "especial": "canal_provas_especial_id",
        }[tipo]
        canal_id = canal_config.get(chave_prova) or CANAIS_PADRAO.get(chave_prova)
        canal = await self._resolver_canal(guild, canal_id) if canal_id else None
        if canal is None:
            await interaction.followup.send(
                "❌ O canal de provas deste tipo não foi encontrado. Avise a staff.",
                ephemeral=True,
            )
            return

        try:
            protocolo = await revisoes_cog.abrir_revisao(
                guild,
                canal,
                tipo=tipo,
                autor_id=interaction.user.id,
                referencia_id=str(atividade["id"]),
                print_url=url,
                titulo=f"{info['emoji']} {info['nome']} — {atividade.get('titulo', 'Atividade')}",
                descricao=(
                    f"Prova enviada por {interaction.user.mention}. "
                    f"ID da missão: `{atividade['id']}`. "
                    + (
                        f"Recompensa total: {recompensa} XP, dividida em 60% para o responsável e 40% para o auxiliar "
                        f"<@{auxiliar_id}> após aprovação."
                        if auxiliar_id
                        else f"Recompensa após aprovação: +{recompensa} XP."
                    )
                ),
                auxiliar_id=auxiliar_id,
                recompensa_xp=recompensa,
            )
            if protocolo.get("_ja_existente"):
                await interaction.followup.send(
                    "⏳ Você já tem uma prova pendente para esta atividade. "
                    "A equipe precisa concluir a análise antes de um novo envio.",
                    ephemeral=True,
                )
                return
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Falha ao criar revisão da missão %s.", atividade.get("id"))
            await interaction.followup.send(
                "❌ Não consegui publicar a prova para revisão. Verifique se o bot tem permissão para enviar mensagens e Embeds no canal de provas.",
                ephemeral=True,
            )
            return
        except Exception:
            log.exception("Erro inesperado ao receber prova da missão %s.", atividade.get("id"))
            await interaction.followup.send(
                "❌ Ocorreu um erro ao enviar sua prova. Tente novamente mais tarde.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Prova enviada para {canal.mention}. A recompensa será aplicada somente após a aprovação da staff.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Missoes(bot))
