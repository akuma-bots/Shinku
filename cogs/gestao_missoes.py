import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils import missoes, revisoes
from utils.apresentacao import criar_embed


log = logging.getLogger(__name__)

TIPOS_LABEL = {
    "missao": "Missões",
    "contribuicao": "Contribuições",
    "especial": "Missões especiais",
}
STATUS_LABEL = {
    "pendente": "Pendentes",
    "aprovada": "Aprovadas",
    "rejeitada": "Rejeitadas",
}


def _administrador(interaction: discord.Interaction) -> bool:
    return bool(
        interaction.guild
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


def _formatar_xp(valor) -> str:
    try:
        return f"{max(0, int(valor or 0)):,}".replace(",", ".")
    except (TypeError, ValueError, OverflowError):
        return "0"


async def _estatisticas(guild_id: int, atividade: dict) -> dict:
    registros = await revisoes.listar(guild_id)
    relacionados = [
        item for item in registros
        if str(item.get("referencia_id", "")) == str(atividade.get("id", ""))
        and item.get("tipo") in {"missao", "contribuicao", "especial"}
    ]
    resultado = {status: 0 for status in STATUS_LABEL}
    participantes = set()
    xp_liberado = 0
    for item in relacionados:
        status = item.get("status")
        if status in resultado:
            resultado[status] += 1
        autor = item.get("autor_id")
        if autor:
            participantes.add(int(autor))
        if status == "aprovada":
            try:
                xp_liberado += max(0, int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0))
            except (TypeError, ValueError, OverflowError):
                pass
    return {
        **resultado,
        "total": len(relacionados),
        "participantes": len(participantes),
        "xp_liberado_estimado": xp_liberado,
        "registros": relacionados,
    }


def _embed_central(atividades: list, selecionada: dict = None, estatisticas: dict = None) -> discord.Embed:
    ativas = sum(1 for item in atividades if item.get("ativa", True) is not False)
    arquivadas = len(atividades) - ativas
    embed = criar_embed(
        "✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — CENTRAL DE GESTÃO DE MISSÕES ・✦",
        "⟡・ Administração do catálogo, acompanhamento de provas e controle do ciclo de vida das atividades.",
        cor=0x9F2035,
        rodape=None,
    )
    embed.add_field(name="◈ CATÁLOGO", value=f"**{len(atividades)}** atividades", inline=True)
    embed.add_field(name="◈ ATIVAS", value=f"**{ativas}**", inline=True)
    embed.add_field(name="◈ ARQUIVADAS", value=f"**{arquivadas}**", inline=True)
    if selecionada is None:
        embed.add_field(
            name="◈ SELECIONE UMA ATIVIDADE",
            value="Escolha uma atividade no seletor abaixo para consultar indicadores, editar informações ou arquivar/reativar o registro.",
            inline=False,
        )
        embed.set_footer(text="NÊMESIS • GESTÃO OPERACIONAL • Acesso restrito à administração")
        return embed

    tipo = str(selecionada.get("tipo", "missao")).lower()
    ativa = selecionada.get("ativa", True) is not False
    embed.add_field(
        name="◈ ATIVIDADE SELECIONADA",
        value=(
            f"**{str(selecionada.get('titulo') or 'Sem título')[:180]}**\n"
            f"**Código:** `{selecionada.get('id', '—')}`\n"
            f"**Categoria:** {TIPOS_LABEL.get(tipo, tipo.title())}\n"
            f"**Estado:** {'🟢 Ativa' if ativa else '⛔ Arquivada'}\n"
            f"**Recompensa:** {_formatar_xp(selecionada.get('recompensa_xp', selecionada.get('pontos', 0)))} XP"
        ),
        inline=False,
    )
    embed.add_field(
        name="◈ DESCRIÇÃO",
        value=(str(selecionada.get("descricao") or "Sem descrição cadastrada.")[:1000]),
        inline=False,
    )
    if estatisticas:
        embed.add_field(name="⏳ PENDENTES", value=f"**{estatisticas['pendente']}**", inline=True)
        embed.add_field(name="✓ APROVADAS", value=f"**{estatisticas['aprovada']}**", inline=True)
        embed.add_field(name="✕ REJEITADAS", value=f"**{estatisticas['rejeitada']}**", inline=True)
        embed.add_field(
            name="◈ INDICADORES",
            value=(
                f"**Provas registradas:** {estatisticas['total']}\n"
                f"**Participantes únicos:** {estatisticas['participantes']}\n"
                f"**XP aprovado estimado:** {estatisticas['xp_liberado_estimado']:,}".replace(",", ".")
            ),
            inline=False,
        )
        ultimos = sorted(
            estatisticas["registros"],
            key=lambda item: float(item.get("timestamp", 0) or 0),
            reverse=True,
        )[:5]
        if ultimos:
            linhas = []
            for item in ultimos:
                membro = f"<@{item.get('autor_id')}>" if item.get("autor_id") else "Membro desconhecido"
                estado = STATUS_LABEL.get(item.get("status"), str(item.get("status", "—")))
                linhas.append(f"• {membro} — **{estado}** — `{item.get('id', '—')}`")
            embed.add_field(name="◈ ATIVIDADE RECENTE", value="\n".join(linhas), inline=False)
    embed.set_footer(text="NÊMESIS • GESTÃO OPERACIONAL • Alterações preservam o histórico")
    return embed


class EditarMissaoModal(discord.ui.Modal, title="Editar atividade"):
    titulo = discord.ui.TextInput(label="Título", max_length=100, required=True)
    descricao = discord.ui.TextInput(label="Descrição e objetivo", style=discord.TextStyle.paragraph, max_length=4000, required=True)
    recompensa = discord.ui.TextInput(label="Recompensa em XP", max_length=8, required=True)
    dificuldade = discord.ui.TextInput(label="Dificuldade (opcional)", max_length=30, required=False)
    requisitos = discord.ui.TextInput(label="Requisitos (opcional)", style=discord.TextStyle.paragraph, max_length=1000, required=False)
    prazo = discord.ui.TextInput(label="Prazo (opcional)", max_length=100, required=False)

    def __init__(self, guild_id: int, atividade: dict, owner_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.atividade_id = str(atividade["id"])
        self.owner_id = owner_id
        self.titulo.default = str(atividade.get("titulo") or "")[:100]
        self.descricao.default = str(atividade.get("descricao") or "")[:4000]
        self.recompensa.default = str(atividade.get("recompensa_xp", atividade.get("pontos", 0)))
        self.dificuldade.default = str(atividade.get("dificuldade") or "")[:30]
        self.requisitos.default = str(atividade.get("requisitos") or "")[:1000]
        self.prazo.default = str(atividade.get("prazo") or "")[:100]

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id or not _administrador(interaction):
            await interaction.response.send_message("Acesso não autorizado para esta alteração.", ephemeral=True)
            return
        try:
            xp = int(str(self.recompensa.value).strip())
            if xp < 0 or xp > 1000000:
                raise ValueError
        except (TypeError, ValueError):
            await interaction.response.send_message("A recompensa deve ser um número inteiro entre 0 e 1.000.000 XP.", ephemeral=True)
            return
        async with missoes._MISSOES_LOCK:
            dados = await missoes._guild(self.guild_id)
            alvo = next((item for item in dados["missoes"] if str(item.get("id")) == self.atividade_id), None)
            if alvo is None:
                await interaction.response.send_message("A atividade não existe mais no catálogo.", ephemeral=True)
                return
            alvo.update({
                "titulo": str(self.titulo.value).strip(),
                "descricao": str(self.descricao.value).strip(),
                "recompensa_xp": xp,
                "pontos": xp,
                "dificuldade": str(self.dificuldade.value or "").strip(),
                "requisitos": str(self.requisitos.value or "").strip(),
                "prazo": str(self.prazo.value or "").strip(),
                "atualizado_em": __import__("time").time(),
                "atualizado_por": interaction.user.id,
            })
            await missoes._salvar_guild(self.guild_id, dados)
        await interaction.response.send_message("Atividade atualizada. O histórico de provas e recompensas foi preservado. Use Atualizar painel para conferir a publicação.", ephemeral=True)


class SeletorAtividade(discord.ui.Select):
    def __init__(self, view: "CentralMissoesView", atividades: list, selecionada_id: str = None):
        self.central = view
        opcoes = []
        for item in atividades[:25]:
            estado = "Ativa" if item.get("ativa", True) is not False else "Arquivada"
            tipo = TIPOS_LABEL.get(str(item.get("tipo", "missao")), "Atividade")
            nome = f"{item.get('titulo', 'Sem título')} · {estado}"
            opcoes.append(discord.SelectOption(
                label=nome[:100],
                value=str(item.get("id", ""))[:100],
                description=f"{tipo} • {_formatar_xp(item.get('recompensa_xp', item.get('pontos', 0)))} XP"[:100],
                default=str(item.get("id")) == str(selecionada_id),
            ))
        super().__init__(placeholder="Selecione uma atividade para gerenciar", min_values=1, max_values=1, options=opcoes, disabled=not opcoes)

    async def callback(self, interaction: discord.Interaction):
        if not await self.central.autorizar(interaction):
            return
        self.central.selecionada_id = self.values[0]
        await self.central.atualizar(interaction)


class CentralMissoesView(discord.ui.View):
    def __init__(self, guild_id: int, owner_id: int, selecionada_id: str = None):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.owner_id = owner_id
        self.selecionada_id = selecionada_id
        self.add_item(SeletorAtividade(self, [], selecionada_id))

    async def atividades(self) -> list:
        dados = await missoes._guild(self.guild_id)
        return sorted(
            dados.get("missoes", []),
            key=lambda item: (item.get("tipo", ""), str(item.get("titulo", "")).casefold()),
        )

    async def autorizar(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id or not _administrador(interaction):
            await interaction.response.send_message("Este painel pertence a outro administrador ou seu acesso expirou.", ephemeral=True)
            return False
        return True

    async def atualizar(self, interaction: discord.Interaction):
        atividades = await self.atividades()
        selecionada = next((item for item in atividades if str(item.get("id")) == str(self.selecionada_id)), None)
        stats = await _estatisticas(self.guild_id, selecionada) if selecionada else None
        nova = CentralMissoesView(self.guild_id, self.owner_id, self.selecionada_id)
        nova.clear_items()
        nova.add_item(SeletorAtividade(nova, atividades, self.selecionada_id))
        await interaction.response.edit_message(embed=_embed_central(atividades, selecionada, stats), view=nova)

    @discord.ui.button(label="Editar atividade", style=discord.ButtonStyle.primary, emoji="✏️", row=1)
    async def editar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        atividade = await missoes.get(self.guild_id, self.selecionada_id) if self.selecionada_id else None
        if not atividade:
            await interaction.response.send_message("Selecione uma atividade válida antes de editar.", ephemeral=True)
            return
        await interaction.response.send_modal(EditarMissaoModal(self.guild_id, atividade, self.owner_id))

    @discord.ui.button(label="Arquivar / reativar", style=discord.ButtonStyle.secondary, emoji="◈", row=1)
    async def alternar_estado(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        if not self.selecionada_id:
            await interaction.response.send_message("Selecione uma atividade antes de alterar o estado.", ephemeral=True)
            return
        async with missoes._MISSOES_LOCK:
            dados = await missoes._guild(self.guild_id)
            alvo = next((item for item in dados["missoes"] if str(item.get("id")) == str(self.selecionada_id)), None)
            if alvo is None:
                await interaction.response.send_message("A atividade não foi encontrada.", ephemeral=True)
                return
            alvo["ativa"] = alvo.get("ativa", True) is False
            alvo["atualizado_em"] = __import__("time").time()
            alvo["atualizado_por"] = interaction.user.id
            await missoes._salvar_guild(self.guild_id, dados)
        await self.atualizar(interaction)

    @discord.ui.button(label="Atualizar painel", style=discord.ButtonStyle.success, emoji="🔄", row=1)
    async def atualizar_painel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.autorizar(interaction):
            return
        await self.atualizar(interaction)


class GestaoMissoes(commands.Cog):
    """Central administrativa para o ciclo de vida e indicadores do catálogo."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="central-missoes", description="Abrir a central administrativa de gestão de missões.")
    @app_commands.default_permissions(administrator=True)
    async def central_missoes(self, interaction: discord.Interaction):
        if interaction.guild is None or not _administrador(interaction):
            await interaction.response.send_message("A central é restrita aos administradores autorizados da NÊMESIS.", ephemeral=True)
            return
        atividades = await missoes._guild(interaction.guild.id)
        lista = sorted(
            atividades.get("missoes", []),
            key=lambda item: (item.get("tipo", ""), str(item.get("titulo", "")).casefold()),
        )
        if not lista:
            await interaction.response.send_message("O catálogo ainda não possui atividades cadastradas.", ephemeral=True)
            return
        view = CentralMissoesView(interaction.guild.id, interaction.user.id)
        view.clear_items()
        view.add_item(SeletorAtividade(view, lista))
        await interaction.response.send_message(
            embed=_embed_central(lista),
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(GestaoMissoes(bot))
