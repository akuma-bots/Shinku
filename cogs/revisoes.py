import hashlib
import aiohttp
import discord
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
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("revisao:"):
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Só administradores podem revisar isso.", ephemeral=True)
            return

        _, acao, revisao_id = custom_id.split(":", 2)
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
            processador = self.bot.processadores_revisao.get(revisao["tipo"])
            resultado_texto = await processador(interaction.guild, revisao) if processador else None

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