import discord
from discord import app_commands
from discord.ext import commands
from utils.storage import carregar
from utils.perfis import get_perfil, get_patentes, salvar_patentes, definir_patente, kdr, ARQUIVO_PERFIS
from utils.competitivo_sync import ARQUIVO_COMPETITIVO

ARQUIVO_VINCULOS_ROBLOX = "roblox_vinculos.json"


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
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use este comando dentro do servidor da NÊMESIS.", ephemeral=True
            )
            return

        p = await get_perfil(interaction.guild.id, alvo.id)
        patentes = await get_patentes(interaction.guild.id)
        vinculos_roblox = await carregar(ARQUIVO_VINCULOS_ROBLOX, {})
        vinculo_roblox = (
            vinculos_roblox.get(str(interaction.guild.id), {}).get(str(alvo.id), {})
            if isinstance(vinculos_roblox, dict) else {}
        )

        competitivo = await carregar(
            ARQUIVO_COMPETITIVO,
            {"catalogo": [], "perfis": {}},
        )
        perfis_competitivos = competitivo.get("perfis", {})
        perfil_global = perfis_competitivos.get(str(alvo.id), {})
        estado_temporada = competitivo.get("temporada_global", {})
        ordenados = sorted(
            (
                (str(uid), dados)
                for uid, dados in perfis_competitivos.items()
                if isinstance(dados, dict)
            ),
            key=lambda item: (
                int(item[1].get("pontos_temporada", item[1].get("pontos", 0)) or 0),
                int(item[1].get("vitorias", 0) or 0),
            ),
            reverse=True,
        )
        posicao_global = next(
            (i for i, (uid, _) in enumerate(ordenados, start=1) if uid == str(alvo.id)),
            None,
        )
        pontos_temporada = int(
            perfil_global.get("pontos_temporada", perfil_global.get("pontos", 0)) or 0
        )
        tempo_top = max(0, int(perfil_global.get("tempo_top_global_segundos", 0) or 0))
        minutos_top = tempo_top // 60
        horas_top, minutos_restantes = divmod(minutos_top, 60)
        dias_top, horas_restantes = divmod(horas_top, 24)
        tempo_top_texto = (
            f"{dias_top}d {horas_restantes}h {minutos_restantes}min"
            if dias_top else f"{horas_top}h {minutos_restantes}min"
        )

        proxima = next((pt for pt in patentes if pt["xp_minimo"] > p["xp"]), None)
        progresso = f"\nPróxima patente: **{proxima['nome']}** em {proxima['xp_minimo'] - p['xp']} XP" if proxima else ""

        embed = discord.Embed(title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  PERFIL DE {alvo.display_name.upper()}"[:256], color=0xB51F32)
        embed.set_thumbnail(url=alvo.display_avatar.url)
        embed.add_field(name="◈ PATENTE", value=p["patente"] or "Sem patente", inline=True)
        embed.add_field(name="◈ XP", value=str(p["xp"]) + progresso, inline=True)
        embed.add_field(name="◈ POSIÇÃO GLOBAL", value=f"#{posicao_global}" if posicao_global else "Sem posição", inline=True)
        embed.add_field(name="◈ P.C. DA TEMPORADA", value=f"{pontos_temporada:,}".replace(",", "."), inline=True)
        embed.add_field(name="◈ TEMPORADA", value=f"#{int(estado_temporada.get('numero', 1) or 1)}", inline=True)
        embed.add_field(name="◈ TEMPO NO TOP 10", value=tempo_top_texto, inline=True)
        embed.add_field(name="◈ VITÓRIAS", value=str(p["vitorias"]), inline=True)
        embed.add_field(name="◈ DERROTAS", value=str(p["derrotas"]), inline=True)
        embed.add_field(name="◈ MVPs", value=str(p["mvps"]), inline=True)
        embed.add_field(name="Sequência atual / recorde", value=f"{p['sequencia_atual']} / {p['maior_sequencia']}", inline=True)
        if p["kills"] or p["deaths"]:
            embed.add_field(name="KDR (PvP)", value=f"{kdr(p)} ({p['kills']}/{p['deaths']})", inline=True)
        if isinstance(vinculo_roblox, dict) and vinculo_roblox.get("roblox_id") and vinculo_roblox.get("roblox_username"):
            roblox_id = int(vinculo_roblox["roblox_id"])
            nome_roblox = str(vinculo_roblox["roblox_username"])[:100]
            embed.add_field(
                name="◈ CONTA ROBLOX VERIFICADA",
                value=f"**{discord.utils.escape_markdown(nome_roblox)}** · [Abrir perfil](https://www.roblox.com/users/{roblox_id}/profile)",
                inline=False,
            )
        else:
            embed.add_field(
                name="◈ CONTA ROBLOX",
                value="Não vinculada · use /roblox-vincular para verificar sua conta.",
                inline=False,
            )
        embed.add_field(name="◈ MEDALHAS", value="\n".join(p["medalhas"]) if p["medalhas"] else "Nenhuma ainda", inline=False)

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
        embed = discord.Embed(title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  HIERARQUIA DE PATENTES", description="\n".join(linhas), color=0xB51F32)
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

        embed = discord.Embed(title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  RANKING / {nomes_metrica[metrica].upper()}", description="\n".join(linhas), color=0xB51F32)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Perfil(bot))
