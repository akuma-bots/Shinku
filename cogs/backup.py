import io
import json
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.storage import carregar, salvar
from utils.guild_config import get_config

# Todo arquivo de dados guardado por servidor (guild_id como chave) entra no backup.
ARQUIVOS_COM_DADOS = [
    "guild_configs.json",
    "perfis.json",
    "patentes_config.json",
    "guerras.json",
    "punicoes.json",
    "denuncias.json",
    "parcerias.json",
    "roblox_vinculos.json",
    "roblox_grupo_config.json",
    "modmail_canais.json",
]


async def _montar_backup(guild_id: int) -> dict:
    resultado = {}
    for nome_arquivo in ARQUIVOS_COM_DADOS:
        todos = await carregar(nome_arquivo, {})
        dados_guild = todos.get(str(guild_id))
        if dados_guild is not None:
            resultado[nome_arquivo] = dados_guild
    return resultado


class Backup(commands.Cog):
    """Backup dos dados deste servidor especificamente (configurações,
    perfis, guerras, punições, denúncias, parcerias, vínculos Roblox, mod
    mail) — gera um arquivo .json que você baixa direto do Discord. Não
    inclui tokens nem chaves de API (isso nunca fica salvo em nenhum
    arquivo de dados, só em variáveis de ambiente da hospedagem)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.backup_automatico.start()

    def cog_unload(self):
        self.backup_automatico.cancel()

    async def _gerar_arquivo(self, guild: discord.Guild) -> discord.File:
        dados = await _montar_backup(guild.id)
        conteudo = json.dumps(dados, ensure_ascii=False, indent=2)
        buffer = io.BytesIO(conteudo.encode("utf-8"))
        nome_seguro = "".join(c if c.isalnum() else "_" for c in guild.name)
        nome = f"backup-{nome_seguro}-{guild.id}.json"
        return discord.File(buffer, filename=nome)

    @app_commands.command(name="backup-agora", description="Gera e envia um backup de todos os dados deste servidor, agora.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def backup_agora(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        arquivo = await self._gerar_arquivo(interaction.guild)
        await interaction.followup.send(
            "📦 Backup gerado. Guarda esse arquivo num lugar seguro — ele tem os dados do servidor, mas nenhum token ou senha.",
            file=arquivo,
            ephemeral=True,
        )

    @app_commands.command(name="backup-restaurar", description="Restaura os dados deste servidor a partir de um arquivo de backup (.json).")
    @app_commands.describe(arquivo="O arquivo .json gerado por /backup-agora ou pelo painel web")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def backup_restaurar(self, interaction: discord.Interaction, arquivo: discord.Attachment):
        await interaction.response.defer(ephemeral=True)

        if not arquivo.filename.lower().endswith(".json"):
            await interaction.followup.send("Isso não parece um arquivo de backup — precisa ser um `.json`.", ephemeral=True)
            return

        try:
            conteudo_bruto = await arquivo.read()
            dados = json.loads(conteudo_bruto)
        except (json.JSONDecodeError, UnicodeDecodeError):
            await interaction.followup.send("Não consegui ler esse arquivo. Confere se é um backup gerado pelo bot ou pelo painel, sem edição manual.", ephemeral=True)
            return

        if not isinstance(dados, dict):
            await interaction.followup.send("Formato de arquivo inesperado.", ephemeral=True)
            return

        restaurados = []
        for nome_arquivo, dados_guild in dados.items():
            if nome_arquivo not in ARQUIVOS_COM_DADOS:
                continue  # ignora qualquer chave que não seja um arquivo de dados reconhecido, por segurança
            todos = await carregar(nome_arquivo, {})
            todos[str(interaction.guild.id)] = dados_guild
            await salvar(nome_arquivo, todos)
            restaurados.append(nome_arquivo)

        if not restaurados:
            await interaction.followup.send("O arquivo não tinha nenhum dado reconhecido pra restaurar.", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ Restaurado: {', '.join(restaurados)}.\n"
            f"⚠️ Isso **sobrescreveu** os dados atuais desses sistemas — qualquer coisa que mudou depois desse backup foi perdida.",
            ephemeral=True,
        )

    @tasks.loop(hours=24 * 7)
    async def backup_automatico(self):
        for guild in self.bot.guilds:
            config = await get_config(guild.id)
            canal_id = config.get("log_channel_id")
            canal = guild.get_channel(canal_id) if canal_id else None
            if not canal:
                continue
            try:
                arquivo = await self._gerar_arquivo(guild)
                await canal.send("📦 Backup semanal automático dos dados deste servidor:", file=arquivo)
            except discord.Forbidden:
                pass

    @backup_automatico.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Backup(bot))
