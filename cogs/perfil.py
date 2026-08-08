import discord
from discord import app_commands
from discord.ext import commands
from utils.storage import carregar
from utils.perfis import get_perfil, get_patentes, salvar_patentes, definir_patente, kdr, ARQUIVO_PERFIS


class Perfil(commands.Cog):
    """Perfil do jogador (patente, vitórias, derrotas, KDR, medalhas),
    configuração de patentes por XP com promoção automática ou manual, e
    rankings gerais do servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- Perfil ----------------
    @app_commands.command(name="perfil", description="Mostra o perfil de guerra de um membro.")
    @app_commands.describe(membro="De quem ver o perfil (padrão: você mesmo)")
    async def perfil(self, interaction: discord.Interaction, membro: discord.Member = None):
        alvo = membro or interaction.user
        p = await get_perfil(interaction.guild.id, alvo.id)
        patentes = await get_patentes(interaction.guild.id)

        proxima = next((pt for pt in patentes if pt["xp_minimo"] > p["xp"]), None)
        progresso = f"\nPróxima patente: **{proxima['nome']}** em {proxima['xp_minimo'] - p['xp']} XP" if proxima else ""

        embed = discord.Embed(title=f"🎖️ Perfil de {alvo.display_name}", color=0x5865F2)
        embed.set_thumbnail(url=alvo.display_avatar.url)
        embed.add_field(name="Patente", value=p["patente"] or "Sem patente", inline=True)
        embed.add_field(name="XP", value=str(p["xp"]) + progresso, inline=True)
        embed.add_field(name="Vitórias", value=str(p["vitorias"]), inline=True)
        embed.add_field(name="Derrotas", value=str(p["derrotas"]), inline=True)
        embed.add_field(name="MVPs", value=str(p["mvps"]), inline=True)
        embed.add_field(name="Sequência atual / recorde", value=f"{p['sequencia_atual']} / {p['maior_sequencia']}", inline=True)
        if p["kills"] or p["deaths"]:
            embed.add_field(name="KDR (PvP)", value=f"{kdr(p)} ({p['kills']}/{p['deaths']})", inline=True)
        embed.add_field(name="Medalhas", value="\n".join(p["medalhas"]) if p["medalhas"] else "Nenhuma ainda", inline=False)

        await interaction.response.send_message(embed=embed)

    # ---------------- Patentes ----------------
    @app_commands.command(name="patente-configurar", description="Cria ou atualiza uma patente (evolução automática por XP).")
    @app_commands.describe(nome="Nome da patente", xp_minimo="XP mínimo pra alcançar essa patente", cargo_recompensa="Cargo dado automaticamente ao alcançar (opcional)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def patente_configurar(self, interaction: discord.Interaction, nome: str, xp_minimo: int, cargo_recompensa: discord.Role = None):
        patentes = await get_patentes(interaction.guild.id)
        patentes = [p for p in patentes if p["nome"].lower() != nome.lower()]
        patentes.append({"nome": nome, "xp_minimo": xp_minimo, "cargo_id": cargo_recompensa.id if cargo_recompensa else None})
        await salvar_patentes(interaction.guild.id, patentes)
        await interaction.response.send_message(f"✅ Patente **{nome}** configurada (a partir de {xp_minimo} XP).", ephemeral=True)

    @app_commands.command(name="patente-remover", description="Remove uma patente configurada.")
    @app_commands.describe(nome="Nome exato da patente")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def patente_remover(self, interaction: discord.Interaction, nome: str):
        patentes = await get_patentes(interaction.guild.id)
        nova_lista = [p for p in patentes if p["nome"].lower() != nome.lower()]
        if len(nova_lista) == len(patentes):
            await interaction.response.send_message("Não achei nenhuma patente com esse nome.", ephemeral=True)
            return
        await salvar_patentes(interaction.guild.id, nova_lista)
        await interaction.response.send_message(f"🗑️ Patente **{nome}** removida.", ephemeral=True)

    @app_commands.command(name="patente-listar", description="Lista as patentes configuradas neste servidor.")
    async def patente_listar(self, interaction: discord.Interaction):
        patentes = await get_patentes(interaction.guild.id)
        if not patentes:
            await interaction.response.send_message("Nenhuma patente configurada ainda.", ephemeral=True)
            return
        linhas = [f"**{p['nome']}** — a partir de {p['xp_minimo']} XP" + (f" (cargo: <@&{p['cargo_id']}>)" if p.get("cargo_id") else "") for p in patentes]
        embed = discord.Embed(title="🎖️ Patentes configuradas", description="\n".join(linhas), color=0x5865F2)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="patente-promover", description="Define a patente de um membro manualmente (ignora o XP).")
    @app_commands.describe(membro="Quem promover", patente="Nome exato da patente configurada")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def patente_promover(self, interaction: discord.Interaction, membro: discord.Member, patente: str):
        patentes = await get_patentes(interaction.guild.id)
        alvo = next((p for p in patentes if p["nome"].lower() == patente.lower()), None)
        if not alvo:
            await interaction.response.send_message("Não achei essa patente configurada. Use `/patente-listar` pra ver as opções.", ephemeral=True)
            return

        await definir_patente(interaction.guild.id, membro.id, alvo["nome"])
        if alvo.get("cargo_id"):
            cargo = interaction.guild.get_role(alvo["cargo_id"])
            if cargo:
                try:
                    await membro.add_roles(cargo, reason=f"Promovido manualmente por {interaction.user}")
                except discord.Forbidden:
                    pass
        await interaction.response.send_message(f"✅ {membro.mention} agora é **{alvo['nome']}**.")

    # ---------------- Rankings ----------------
    @app_commands.command(name="ranking-jogadores", description="Top jogadores do servidor por uma métrica.")
    @app_commands.describe(metrica="Por qual métrica ordenar")
    @app_commands.choices(metrica=[
        app_commands.Choice(name="Vitórias", value="vitorias"),
        app_commands.Choice(name="MVPs", value="mvps"),
        app_commands.Choice(name="Maior sequência", value="maior_sequencia"),
        app_commands.Choice(name="XP", value="xp"),
    ])
    async def ranking_jogadores(self, interaction: discord.Interaction, metrica: str = "vitorias"):
        todos = await carregar(ARQUIVO_PERFIS, {})
        perfis_guild = todos.get(str(interaction.guild.id), {})

        if not perfis_guild:
            await interaction.response.send_message("Ninguém tem perfil registrado ainda.", ephemeral=True)
            return

        top = sorted(perfis_guild.items(), key=lambda item: item[1].get(metrica, 0), reverse=True)[:10]
        nomes_metrica = {"vitorias": "vitórias", "mvps": "MVPs", "maior_sequencia": "maior sequência", "xp": "XP"}
        linhas = [f"**#{i+1}** <@{uid}> — {perfil.get(metrica, 0)} {nomes_metrica[metrica]}" for i, (uid, perfil) in enumerate(top)]

        embed = discord.Embed(title=f"🏆 Ranking por {nomes_metrica[metrica]}", description="\n".join(linhas), color=0xFEE75C)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Perfil(bot))
