import discord
from discord import app_commands
from discord.ext import commands

from utils import pve
from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config
from utils.perfis import ARQUIVO_PERFIS, get_perfil, calcular_patente_atual, definir_patente

CORES_DIFICULDADE = {"fácil": 0x57F287, "médio": 0xFEE75C, "difícil": 0xED4245}


async def _adicionar_xp(guild_id: int, user_id: int, xp_ganho: int) -> dict:
    await get_perfil(guild_id, user_id)
    todos = await carregar(ARQUIVO_PERFIS, {})
    perfis_guild = todos.setdefault(str(guild_id), {})
    perfil = perfis_guild[str(user_id)]
    patente_antiga = perfil.get("patente")
    perfil["xp"] = perfil.get("xp", 0) + xp_ganho
    perfil["vitorias"] = perfil.get("vitorias", 0) + 1
    await salvar(ARQUIVO_PERFIS, todos)
    return {"perfil": perfil, "patente_antiga": patente_antiga}


class PvE(commands.Cog):
    """PvE por sorteio: o bot sorteia um inimigo aleatório da lista
    configurada pelo servidor, o jogador enfrenta e manda a print do
    resultado, que passa pela revisão manual em Provas-PVE antes de aplicar
    XP e vitória automaticamente."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}
        bot.processadores_revisao["pve"] = self.processar_aprovacao_pve

    async def processar_aprovacao_pve(self, guild: discord.Guild, revisao: dict) -> str:
        encontro = await pve.get_encontro(guild.id, revisao["referencia_id"])
        if not encontro:
            return "⚠️ Encontro original não foi encontrado."

        xp = encontro["inimigo"]["recompensa_xp"]
        resultado = await _adicionar_xp(guild.id, revisao["autor_id"], xp)
        await pve.marcar_status(guild.id, encontro["id"], "concluido")
        texto = f"+{xp} XP e +1 vitória para <@{revisao['autor_id']}> (derrotou {encontro['inimigo']['nome']})"

        nova_patente = await calcular_patente_atual(guild.id, resultado["perfil"]["xp"])
        if nova_patente and nova_patente["nome"] != resultado["patente_antiga"]:
            await definir_patente(guild.id, revisao["autor_id"], nova_patente["nome"])
            membro = guild.get_member(revisao["autor_id"])
            cargo_id = nova_patente.get("cargo_id")
            if membro and cargo_id:
                cargo = guild.get_role(cargo_id)
                if cargo:
                    try:
                        await membro.add_roles(cargo, reason="Promoção automática por PvE")
                    except discord.Forbidden:
                        pass
            texto += f"\n⬆️ Promovido(a) para **{nova_patente['nome']}**"

        return texto

    @app_commands.command(name="pve-canais", description="Define os canais de encontros e provas de PvE.")
    @app_commands.describe(canal_pve="Onde os encontros são anunciados", canal_provas="Onde a print do resultado é enviada")
    @app_commands.checks.has_permissions(administrator=True)
    async def pve_canais(self, interaction: discord.Interaction,
                          canal_pve: discord.TextChannel, canal_provas: discord.TextChannel):
        await set_config(interaction.guild.id, canal_missoes_pve_id=canal_pve.id, canal_provas_pve_id=canal_provas.id)
        await interaction.response.send_message(
            f"✅ Encontros em {canal_pve.mention}, provas em {canal_provas.mention}.", ephemeral=True
        )

    @app_commands.command(name="pve-inimigo-adicionar", description="Adiciona um inimigo à lista de sorteio do PvE.")
    @app_commands.describe(nome="Nome do inimigo", dificuldade="fácil, médio ou difícil", recompensa_xp="XP dado ao vencer")
    @app_commands.choices(dificuldade=[
        app_commands.Choice(name="Fácil", value="fácil"),
        app_commands.Choice(name="Médio", value="médio"),
        app_commands.Choice(name="Difícil", value="difícil"),
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def pve_inimigo_adicionar(self, interaction: discord.Interaction, nome: str,
                                     dificuldade: app_commands.Choice[str], recompensa_xp: int):
        await pve.adicionar_inimigo(interaction.guild.id, nome, dificuldade.value, recompensa_xp)
        await interaction.response.send_message(f"✅ **{nome}** ({dificuldade.name}, {recompensa_xp} XP) adicionado.", ephemeral=True)

    @app_commands.command(name="pve-encontrar", description="Sorteia um inimigo pra você enfrentar.")
    async def pve_encontrar(self, interaction: discord.Interaction):
        encontro = await pve.criar_encontro(interaction.guild.id, interaction.user.id)
        inimigo = encontro["inimigo"]

        config = await get_config(interaction.guild.id)
        canal_id = config.get("canal_missoes_pve_id")
        canal = interaction.guild.get_channel(canal_id) if canal_id else interaction.channel

        embed = discord.Embed(
            title=f"👹 {inimigo['nome']}",
            description=f"{interaction.user.mention} está enfrentando um inimigo **{inimigo['dificuldade']}**!",
            color=CORES_DIFICULDADE.get(inimigo["dificuldade"], 0x5865F2),
        )
        embed.add_field(name="Recompensa", value=f"{inimigo['recompensa_xp']} XP")
        embed.set_footer(text=f"ID: {encontro['id']} • use /pve-completar pra enviar a prova")
        await canal.send(embed=embed)

        await interaction.response.send_message(f"⚔️ Encontro sorteado em {canal.mention}!", ephemeral=True)

    @app_commands.command(name="pve-completar", description="Envia a prova de que você venceu o encontro sorteado.")
    @app_commands.describe(encontro_id="ID do encontro (aparece em /pve-encontrar)", print="Print comprovando a vitória")
    async def pve_completar(self, interaction: discord.Interaction, encontro_id: str, print: discord.Attachment):
        encontro = await pve.get_encontro(interaction.guild.id, encontro_id)
        if not encontro or encontro["status"] != "aberto" or encontro["user_id"] != interaction.user.id:
            await interaction.response.send_message("Não achei esse encontro aberto pra você.", ephemeral=True)
            return

        config = await get_config(interaction.guild.id)
        canal_id = config.get("canal_provas_pve_id")
        canal = interaction.guild.get_channel(canal_id) if canal_id else interaction.channel

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.response.send_message("⚠️ O sistema de revisão não está carregado. Avise um admin.", ephemeral=True)
            return

        await revisoes_cog.abrir_revisao(
            interaction.guild, canal,
            tipo="pve", autor_id=interaction.user.id, referencia_id=encontro_id,
            print_url=print.url, titulo=f"Encontro: {encontro['inimigo']['nome']}",
        )
        await interaction.response.send_message(f"✅ Prova enviada para revisão em {canal.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(PvE(bot))