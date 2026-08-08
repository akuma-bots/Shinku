import time
import uuid
import discord
from discord import app_commands
from discord.ext import commands
from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config
from utils.punicoes import registrar_punicao

ARQUIVO = "denuncias.json"  # { guild_id: [ {id, denunciante_id, denunciado_id, motivo, status, timestamp, resolucao} ] }


async def _lista(guild_id: int) -> list:
    todos = await carregar(ARQUIVO, {})
    return todos.get(str(guild_id), [])


async def _salvar_lista(guild_id: int, lista: list):
    todos = await carregar(ARQUIVO, {})
    todos[str(guild_id)] = lista
    await salvar(ARQUIVO, todos)


class Denuncias(commands.Cog):
    """Sistema de denúncias: qualquer membro pode denunciar outro de forma
    privada (ephemeral), a equipe revisa numa fila e marca como resolvida."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="configurar-canal-denuncias", description="Define onde as denúncias chegam pra equipe revisar.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_canal_denuncias(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_denuncias_id=canal.id)
        await interaction.response.send_message(f"✅ Denúncias agora chegam em {canal.mention}.", ephemeral=True)

    @app_commands.command(name="denunciar", description="Denuncia um membro pra equipe (privado, só a equipe vê).")
    @app_commands.describe(membro="Quem você está denunciando", motivo="O que aconteceu")
    async def denunciar(self, interaction: discord.Interaction, membro: discord.Member, motivo: str):
        config = await get_config(interaction.guild.id)
        canal_id = config.get("canal_denuncias_id") or config["log_channel_id"]
        canal = interaction.guild.get_channel(canal_id) if canal_id else None
        if not canal:
            await interaction.response.send_message(
                "A equipe ainda não configurou onde as denúncias chegam. Avise um admin.", ephemeral=True
            )
            return

        lista = await _lista(interaction.guild.id)
        registro = {
            "id": str(uuid.uuid4())[:8],
            "denunciante_id": interaction.user.id,
            "denunciado_id": membro.id,
            "motivo": motivo,
            "status": "pendente",
            "timestamp": time.time(),
            "resolucao": None,
        }
        lista.append(registro)
        await _salvar_lista(interaction.guild.id, lista)

        embed = discord.Embed(title=f"🚩 Nova denúncia — #{registro['id']}", color=0xED4245)
        embed.add_field(name="Denunciado", value=membro.mention, inline=True)
        embed.add_field(name="Denunciante", value=interaction.user.mention, inline=True)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        embed.set_footer(text=f"Use /denuncia-resolver id:{registro['id']} pra marcar como resolvida")
        await canal.send(embed=embed)

        await interaction.response.send_message("✅ Denúncia enviada pra equipe. Obrigado por avisar.", ephemeral=True)

    @app_commands.command(name="denuncias-listar", description="Lista denúncias (padrão: só as pendentes).")
    @app_commands.describe(status="Filtrar por status")
    @app_commands.choices(status=[
        app_commands.Choice(name="Pendentes", value="pendente"),
        app_commands.Choice(name="Resolvidas", value="resolvida"),
        app_commands.Choice(name="Todas", value="todas"),
    ])
    @app_commands.checks.has_permissions(moderate_members=True)
    async def denuncias_listar(self, interaction: discord.Interaction, status: str = "pendente"):
        lista = await _lista(interaction.guild.id)
        if status != "todas":
            lista = [d for d in lista if d["status"] == status]
        lista = sorted(lista, key=lambda d: d["timestamp"], reverse=True)[:15]

        if not lista:
            await interaction.response.send_message("Nenhuma denúncia encontrada com esse filtro.", ephemeral=True)
            return

        linhas = [
            f"**#{d['id']}** — <@{d['denunciado_id']}> por <@{d['denunciante_id']}>: {d['motivo']} ({d['status']})"
            for d in lista
        ]
        embed = discord.Embed(title="🚩 Denúncias", description="\n".join(linhas), color=0xED4245)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="denuncia-resolver", description="Marca uma denúncia como resolvida.")
    @app_commands.describe(id="ID da denúncia (aparece no /denuncias-listar)", acao="O que foi feito (ex: 'advertido', 'banido', 'sem provas suficientes')")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def denuncia_resolver(self, interaction: discord.Interaction, id: str, acao: str):
        lista = await _lista(interaction.guild.id)
        registro = next((d for d in lista if d["id"] == id), None)
        if not registro:
            await interaction.response.send_message("Não achei denúncia com esse ID.", ephemeral=True)
            return

        registro["status"] = "resolvida"
        registro["resolucao"] = acao
        await _salvar_lista(interaction.guild.id, lista)
        await registrar_punicao(interaction.guild.id, registro["denunciado_id"], "denuncia_resolvida", acao, interaction.user.id)

        await interaction.response.send_message(f"✅ Denúncia #{id} marcada como resolvida: {acao}", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Denuncias(bot))
