import discord
from discord import app_commands
from discord.ext import commands

from utils import missoes
from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config
from utils.perfis import ARQUIVO_PERFIS, get_perfil, calcular_patente_atual, definir_patente

TIPO_CHOICES = [
    app_commands.Choice(name="PvP", value="pvp"),
    app_commands.Choice(name="PvE", value="pve"),
]


async def _adicionar_xp(guild_id: int, user_id: int, xp_ganho: int) -> dict:
    """Soma XP ao perfil do jogador. Fica aqui (em vez de mexer em
    utils/perfis.py) pra não duplicar/conflitar com a lógica já existente —
    usa o mesmo formato de dados que perfil.py já lê."""
    await get_perfil(guild_id, user_id)  # garante que o perfil já existe com os campos padrão
    todos = await carregar(ARQUIVO_PERFIS, {})
    perfis_guild = todos.setdefault(str(guild_id), {})
    perfil = perfis_guild[str(user_id)]
    patente_antiga = perfil.get("patente")
    perfil["xp"] = perfil.get("xp", 0) + xp_ganho
    await salvar(ARQUIVO_PERFIS, todos)
    return {"perfil": perfil, "patente_antiga": patente_antiga}


class Missoes(commands.Cog):
    """Missões PvP e PvE configuráveis pelos líderes. A conclusão passa pelo
    motor de revisão (print + aprovação manual em Provas-PVP/Provas-PVE) — só
    depois de aprovada é que o XP é somado automaticamente e a patente é
    reavaliada, igual já acontece em guerras.py."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.processadores_revisao["missao"] = self.processar_aprovacao

    async def processar_aprovacao(self, guild: discord.Guild, revisao: dict) -> str:
        missao = await missoes.get(guild.id, revisao["referencia_id"])
        if not missao:
            return "⚠️ Missão original não foi encontrada (pode ter sido removida)."

        resultado = await _adicionar_xp(guild.id, revisao["autor_id"], missao["recompensa_xp"])
        texto = f"+{missao['recompensa_xp']} XP para <@{revisao['autor_id']}>"

        nova_patente = await calcular_patente_atual(guild.id, resultado["perfil"]["xp"])
        if nova_patente and nova_patente["nome"] != resultado["patente_antiga"]:
            await definir_patente(guild.id, revisao["autor_id"], nova_patente["nome"])
            membro = guild.get_member(revisao["autor_id"])
            cargo_id = nova_patente.get("cargo_id")
            if membro and cargo_id:
                cargo = guild.get_role(cargo_id)
                if cargo:
                    try:
                        await membro.add_roles(cargo, reason="Promoção automática por missão")
                    except discord.Forbidden:
                        pass
            texto += f"\n⬆️ Promovido(a) para **{nova_patente['nome']}**"

        recordes_cog = self.bot.get_cog("Recordes")
        if recordes_cog:
            await recordes_cog.anunciar_se_recorde(guild, "xp_total", revisao["autor_id"], resultado["perfil"]["xp"])

        return texto

    # ---------------- Configuração de canais ----------------
    @app_commands.command(name="missao-canais", description="Define os canais de missões e provas pra PvP ou PvE.")
    @app_commands.describe(tipo="PvP ou PvE", canal_missoes="Onde as missões ativas são postadas",
                            canal_provas="Onde os jogadores mandam a print pra aprovação")
    @app_commands.choices(tipo=TIPO_CHOICES)
    @app_commands.checks.has_permissions(administrator=True)
    async def missao_canais(self, interaction: discord.Interaction, tipo: app_commands.Choice[str],
                             canal_missoes: discord.TextChannel, canal_provas: discord.TextChannel):
        await set_config(
            interaction.guild.id,
            **{f"canal_missoes_{tipo.value}_id": canal_missoes.id,
               f"canal_provas_{tipo.value}_id": canal_provas.id},
        )
        await interaction.response.send_message(
            f"✅ Canais de **{tipo.name}** configurados: missões em {canal_missoes.mention}, "
            f"provas em {canal_provas.mention}.", ephemeral=True
        )

    # ---------------- Missões ----------------
    @app_commands.command(name="missao-criar", description="Cria uma nova missão PvP ou PvE.")
    @app_commands.describe(tipo="PvP ou PvE", titulo="Título curto da missão",
                            descricao="O que o jogador precisa fazer", recompensa_xp="XP dado ao concluir")
    @app_commands.choices(tipo=TIPO_CHOICES)
    @app_commands.checks.has_permissions(administrator=True)
    async def missao_criar(self, interaction: discord.Interaction, tipo: app_commands.Choice[str],
                            titulo: str, descricao: str, recompensa_xp: int):
        missao = await missoes.criar(interaction.guild.id, tipo.value, titulo, descricao,
                                      recompensa_xp, interaction.user.id)

        config = await get_config(interaction.guild.id)
        canal_id = config.get(f"canal_missoes_{tipo.value}_id")
        canal = interaction.guild.get_channel(canal_id) if canal_id else interaction.channel

        embed = discord.Embed(title=f"🎯 Nova missão ({tipo.name})", description=titulo, color=0xFEE75C)
        embed.add_field(name="Objetivo", value=descricao, inline=False)
        embed.add_field(name="Recompensa", value=f"{recompensa_xp} XP", inline=True)
        embed.set_footer(text=f"ID: {missao['id']} • use /missao-completar pra enviar a prova")
        await canal.send(embed=embed)

        await interaction.response.send_message(f"✅ Missão criada em {canal.mention}.", ephemeral=True)

    @app_commands.command(name="missao-listar", description="Lista as missões ativas.")
    @app_commands.describe(tipo="(Opcional) filtra por PvP ou PvE")
    @app_commands.choices(tipo=TIPO_CHOICES)
    async def missao_listar(self, interaction: discord.Interaction, tipo: app_commands.Choice[str] = None):
        lista = await missoes.listar(interaction.guild.id, tipo=tipo.value if tipo else None)
        if not lista:
            await interaction.response.send_message("Nenhuma missão ativa no momento.", ephemeral=True)
            return

        linhas = [f"**[{m['tipo'].upper()}] {m['titulo']}** — {m['recompensa_xp']} XP (ID: `{m['id']}`)" for m in lista]
        embed = discord.Embed(title="🎯 Missões ativas", description="\n".join(linhas), color=0xFEE75C)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="missao-remover", description="Desativa uma missão.")
    @app_commands.describe(missao_id="ID da missão (aparece em /missao-listar)")
    @app_commands.checks.has_permissions(administrator=True)
    async def missao_remover(self, interaction: discord.Interaction, missao_id: str):
        ok = await missoes.desativar(interaction.guild.id, missao_id)
        if not ok:
            await interaction.response.send_message("Não achei nenhuma missão ativa com esse ID.", ephemeral=True)
            return
        await interaction.response.send_message("🗑️ Missão desativada.", ephemeral=True)

    @app_commands.command(name="missao-completar", description="Envia a prova de que você concluiu uma missão.")
    @app_commands.describe(missao_id="ID da missão (aparece em /missao-listar)", print="Print comprovando a conclusão")
    async def missao_completar(self, interaction: discord.Interaction, missao_id: str, print: discord.Attachment):
        missao = await missoes.get(interaction.guild.id, missao_id)
        if not missao or not missao["ativa"]:
            await interaction.response.send_message("Não achei nenhuma missão ativa com esse ID.", ephemeral=True)
            return

        config = await get_config(interaction.guild.id)
        canal_id = config.get(f"canal_provas_{missao['tipo']}_id")
        canal = interaction.guild.get_channel(canal_id) if canal_id else interaction.channel

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.response.send_message("⚠️ O sistema de revisão não está carregado. Avise um admin.", ephemeral=True)
            return

        await revisoes_cog.abrir_revisao(
            interaction.guild, canal,
            tipo="missao", autor_id=interaction.user.id, referencia_id=missao["id"],
            print_url=print.url, titulo=missao["titulo"],
            descricao=f"Enviado por {interaction.user.mention} para conclusão da missão.",
        )
        await interaction.response.send_message(f"✅ Prova enviada para revisão em {canal.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Missoes(bot))