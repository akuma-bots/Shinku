import hashlib
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from utils import revisoes, auditoria

CORES = {"pvp": 0xED4245, "pve": 0x57F287, "missao": 0xFEE75C}


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


def _embed_revisao(revisao: dict) -> discord.Embed:
    embed = discord.Embed(
        title=f"📋 Revisão pendente — {revisao['titulo']}",
        description=revisao.get("descricao") or "Sem descrição.",
        color=CORES.get(revisao["tipo"], 0x5865F2),
    )
    embed.add_field(name="Enviado por", value=f"<@{revisao['autor_id']}>", inline=True)
    embed.add_field(name="Tipo", value=revisao["tipo"].upper(), inline=True)
    embed.set_image(url=revisao["print_url"])
    embed.set_footer(text=f"ID: {revisao['id']}")
    return embed


def _view_revisao(revisao_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Aprovar", style=discord.ButtonStyle.success,
                                     emoji="✅", custom_id=f"revisao:aprovar:{revisao_id}"))
    view.add_item(discord.ui.Button(label="Rejeitar", style=discord.ButtonStyle.danger,
                                     emoji="❌", custom_id=f"revisao:rejeitar:{revisao_id}"))
    return view


STATUS_LABELS = {
    "pendente": ("⏳ Pendentes", 0xFEE75C),
    "aprovada": ("✅ Aprovadas", 0x57F287),
    "rejeitada": ("❌ Recusadas", 0xED4245),
}


def _embed_painel_provas(guild: discord.Guild, status: str, itens: list[dict]) -> discord.Embed:
    label, cor = STATUS_LABELS[status]
    embed = discord.Embed(
        title=f"✦・NÊMESIS — ACOMPANHAMENTO DE PROVAS",
        description=f"**Filtro:** {label}\n**Registros encontrados:** {len(itens)}",
        color=cor,
    )
    if not itens:
        embed.add_field(name="Nenhuma prova encontrada", value="Não há provas com este status.", inline=False)
        return embed

    for item in itens[:10]:
        tipo = str(item.get("tipo", "—")).upper()
        autor = f"<@{item.get('autor_id')}>" if item.get("autor_id") else "Desconhecido"
        referencia = str(item.get("referencia_id") or "—")
        enviado = item.get("timestamp")
        data = f"<t:{int(enviado)}:R>" if isinstance(enviado, (int, float)) else "Data indisponível"
        revisor = f"<@{item.get('revisor_id')}>" if item.get("revisor_id") else "—"
        embed.add_field(
            name=f"{item.get('titulo', 'Prova sem título')}"[:256],
            value=(
                f"**ID da prova:** `{item.get('id', '—')}`\n"
                f"**ID da missão/atividade:** `{referencia}`\n"
                f"**Membro:** {autor} • **Tipo:** {tipo}\n"
                f"**Enviada:** {data} • **Revisor:** {revisor}"
            )[:1024],
            inline=False,
        )
    if len(itens) > 10:
        embed.set_footer(text=f"Mostrando 10 de {len(itens)} registros. Use o filtro para consultar cada status.")
    return embed


class FiltroPainelProvas(discord.ui.Select):
    def __init__(self, cog: "Revisoes", guild_id: int, owner_id: int, status: str = "pendente"):
        self.cog = cog
        self.guild_id = guild_id
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label="Pendentes", value="pendente", emoji="⏳", default=status == "pendente"),
            discord.SelectOption(label="Aprovadas", value="aprovada", emoji="✅", default=status == "aprovada"),
            discord.SelectOption(label="Recusadas", value="rejeitada", emoji="❌", default=status == "rejeitada"),
        ]
        super().__init__(placeholder="Filtrar provas por status", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este painel foi aberto por outro administrador.", ephemeral=True)
            return
        status = self.values[0]
        itens = await revisoes.listar(self.guild_id, status=status)
        itens.sort(key=lambda x: float(x.get("timestamp", 0) or 0), reverse=True)
        view = PainelProvasView(self.cog, self.guild_id, self.owner_id, status)
        await interaction.response.edit_message(embed=_embed_painel_provas(interaction.guild, status, itens), view=view)


class PainelProvasView(discord.ui.View):
    def __init__(self, cog: "Revisoes", guild_id: int, owner_id: int, status: str = "pendente"):
        super().__init__(timeout=300)
        self.add_item(FiltroPainelProvas(cog, guild_id, owner_id, status))


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


    @app_commands.command(name="painel-provas", description="Acompanhar provas de missões e atividades por status.")
    @app_commands.default_permissions(administrator=True)
    async def painel_provas(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Só administradores podem abrir este painel.", ephemeral=True)
            return
        itens = await revisoes.listar(interaction.guild.id, status="pendente")
        itens.sort(key=lambda x: float(x.get("timestamp", 0) or 0), reverse=True)
        await interaction.response.send_message(
            embed=_embed_painel_provas(interaction.guild, "pendente", itens),
            view=PainelProvasView(self, interaction.guild.id, interaction.user.id),
            ephemeral=True,
        )

    async def abrir_revisao(self, guild: discord.Guild, canal: discord.abc.Messageable, *,
                             tipo: str, autor_id: int, referencia_id: str, print_url: str,
                             titulo: str, descricao: str = None) -> dict:
        revisao = await revisoes.criar_pendencia(
            guild.id, tipo, autor_id, referencia_id, print_url, titulo, descricao
        )

        hash_imagem = await _hash_imagem(print_url)
        duplicata = None
        if hash_imagem:
            await revisoes.definir_hash(guild.id, revisao["id"], hash_imagem)
            encontradas = await revisoes.buscar_por_hash(guild.id, hash_imagem, excluir_id=revisao["id"])
            if encontradas:
                duplicata = encontradas[0]

        embed = _embed_revisao(revisao)
        if duplicata:
            embed.add_field(
                name="⚠️ Possível print repetida",
                value=f"Esta mesma imagem já apareceu na revisão `{duplicata['id']}` ({duplicata['status']}). Confira com atenção antes de aprovar.",
                inline=False,
            )

        msg = await canal.send(embed=embed, view=_view_revisao(revisao["id"]))
        await revisoes.definir_mensagem(guild.id, revisao["id"], canal.id, msg.id)
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
        if permissoes is None or not permissoes.administrator:
            await interaction.response.send_message("Só administradores podem revisar isso.", ephemeral=True)
            return

        partes = custom_id.split(":", 2)
        if len(partes) != 3 or partes[1] not in {"aprovar", "rejeitar"} or not partes[2]:
            await interaction.response.send_message("Ação de revisão inválida.", ephemeral=True)
            return
        _, acao, revisao_id = partes
        revisao = await revisoes.get(interaction.guild.id, revisao_id)
        if not revisao:
            await interaction.response.send_message("Essa revisão não existe mais.", ephemeral=True)
            return
        if revisao["status"] != "pendente":
            await interaction.response.send_message(f"Essa revisão já foi **{revisao['status']}**.", ephemeral=True)
            return

        await interaction.response.defer()

        if acao == "aprovar":
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

            embed = _embed_revisao(revisao)
            embed.color = 0x57F287
            embed.add_field(name="✅ Aprovado por", value=interaction.user.mention, inline=False)
            if resultado_texto:
                embed.add_field(name="Resultado aplicado", value=resultado_texto, inline=False)
            await interaction.message.edit(embed=embed, view=None)

            await auditoria.registrar(
                interaction.guild, "📋 Revisão aprovada",
                f"Tipo: **{revisao['tipo']}**\nAutor: <@{revisao['autor_id']}>\n"
                f"Aprovado por: {interaction.user.mention}\nID: `{revisao['id']}`",
                cor=0x57F287,
            )

        else:
            revisao = await revisoes.rejeitar(interaction.guild.id, revisao_id, interaction.user.id)
            embed = _embed_revisao(revisao)
            embed.color = 0xED4245
            embed.add_field(name="❌ Rejeitado por", value=interaction.user.mention, inline=False)
            await interaction.message.edit(embed=embed, view=None)

            await auditoria.registrar(
                interaction.guild, "📋 Revisão rejeitada",
                f"Tipo: **{revisao['tipo']}**\nAutor: <@{revisao['autor_id']}>\n"
                f"Rejeitado por: {interaction.user.mention}\nID: `{revisao['id']}`",
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