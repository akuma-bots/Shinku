import discord
from discord.ext import commands
from utils import revisoes

CORES = {"pvp": 0xED4245, "pve": 0x57F287, "missao": 0xFEE75C}


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
    botões no canal certo (Provas-PVP / Provas-PVE). Quando um admin aprova,
    o processador registrado em `bot.processadores_revisao[tipo]` é chamado
    automaticamente pra aplicar o resultado (XP, vitórias, medalhas, etc) —
    cada cog novo só precisa registrar o seu processador, sem mexer aqui.

    Os botões usam custom_id fixo (não view registrada em memória), então
    continuam funcionando normalmente mesmo depois de um restart do bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}  # tipo -> async def(guild, revisao) -> str | None

    async def abrir_revisao(self, guild: discord.Guild, canal: discord.abc.Messageable, *,
                             tipo: str, autor_id: int, referencia_id: str, print_url: str,
                             titulo: str, descricao: str = None) -> dict:
        revisao = await revisoes.criar_pendencia(
            guild.id, tipo, autor_id, referencia_id, print_url, titulo, descricao
        )
        msg = await canal.send(embed=_embed_revisao(revisao), view=_view_revisao(revisao["id"]))
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

        else:
            revisao = await revisoes.rejeitar(interaction.guild.id, revisao_id, interaction.user.id)
            embed = _embed_revisao(revisao)
            embed.color = 0xED4245
            embed.add_field(name="❌ Rejeitado por", value=interaction.user.mention, inline=False)
            await interaction.message.edit(embed=embed, view=None)

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
