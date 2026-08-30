import discord
from discord import app_commands
from discord.ext import commands
from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config

ARQUIVO = "modmail_canais.json"  # { guild_id: { user_id: channel_id } }
FRASES_FECHAR = ["fechar dm", "fechar o dm", "encerrar dm", "encerrar o dm", "fechar conversa", "encerrar conversa"]


async def _mapa_guild(guild_id: int) -> dict:
    todos = await carregar(ARQUIVO, {})
    return todos.get(str(guild_id), {})


async def _salvar_mapa_guild(guild_id: int, mapa: dict):
    todos = await carregar(ARQUIVO, {})
    todos[str(guild_id)] = mapa
    await salvar(ARQUIVO, todos)


class ModMail(commands.Cog):
    """Quem manda DM pro bot tem a mensagem encaminhada pra um canal privado
    (visível só à equipe) dentro do servidor configurado. A equipe responde
    normalmente naquele canal, e a resposta volta pra DM da pessoa sozinha —
    sem precisar abrir um canal público nem a pessoa entrar no servidor."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._aguardando_escolha = {}  # user_id -> [guild_id, ...] (quando a pessoa está em vários servidores com isso ativado)

    @app_commands.command(name="configurar-canal-modmail", description="Define a categoria onde os canais de DM/mod mail são criados.")
    @app_commands.describe(categoria="Categoria do servidor onde os canais de conversa por DM vão aparecer")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_canal_modmail(self, interaction: discord.Interaction, categoria: discord.CategoryChannel):
        await set_config(interaction.guild.id, categoria_modmail_id=categoria.id)
        await interaction.response.send_message(f"✅ A partir de agora, DMs pro bot viram canais dentro de **{categoria.name}**.", ephemeral=True)

    @app_commands.command(name="fechar-dm", description="Fecha a conversa de DM associada a este canal (uso dentro do próprio canal).")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fechar_dm(self, interaction: discord.Interaction):
        fechou = await self._fechar_por_canal(interaction.guild.id, interaction.channel)
        if fechou:
            await interaction.response.send_message("Fechando essa conversa de DM...", ephemeral=True)
        else:
            await interaction.response.send_message("Esse canal não parece ser uma conversa de mod mail.", ephemeral=True)

    async def _fechar_por_canal(self, guild_id: int, canal: discord.TextChannel) -> bool:
        mapa = await _mapa_guild(guild_id)
        user_id_encontrado = next((uid for uid, cid in mapa.items() if cid == canal.id), None)
        if not user_id_encontrado:
            return False

        mapa.pop(user_id_encontrado, None)
        await _salvar_mapa_guild(guild_id, mapa)

        usuario = self.bot.get_user(int(user_id_encontrado))
        if usuario:
            try:
                await usuario.send(f"🔒 Sua conversa com a equipe de **{canal.guild.name}** foi encerrada. Pode mandar outra DM a qualquer momento se precisar de novo.")
            except discord.Forbidden:
                pass

        await canal.send("🔒 Encerrando esta conversa...")
        try:
            await canal.delete(reason="Conversa de mod mail encerrada.")
        except discord.NotFound:
            pass
        return True

    async def _guilds_candidatas(self, user_id: int) -> list:
        candidatas = []
        for guild in self.bot.guilds:
            if guild.get_member(user_id) is None:
                continue
            config = await get_config(guild.id)
            if config["categoria_modmail_id"]:
                candidatas.append(guild)
        return candidatas

    async def _encaminhar_para_canal(self, guild: discord.Guild, autor: discord.User, mensagem: discord.Message):
        mapa = await _mapa_guild(guild.id)
        canal_id = mapa.get(str(autor.id))
        canal = guild.get_channel(canal_id) if canal_id else None

        if not canal:
            config = await get_config(guild.id)
            categoria = guild.get_channel(config["categoria_modmail_id"])
            cargo_suporte_id = config["support_role_id"]

            overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
            if cargo_suporte_id:
                cargo = guild.get_role(cargo_suporte_id)
                if cargo:
                    overwrites[cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

            canal = await guild.create_text_channel(
                name=f"dm-{autor.name}"[:95],
                category=categoria,
                overwrites=overwrites,
                topic=f"modmail-user:{autor.id}",
                reason=f"Nova conversa de DM com {autor}",
            )
            mapa[str(autor.id)] = canal.id
            await _salvar_mapa_guild(guild.id, mapa)

            embed_intro = discord.Embed(
                description=f"📩 Nova conversa de DM com {autor.mention} (`{autor}`).\nResponda aqui — a mensagem vai direto pra DM da pessoa. Pra encerrar, digite **\"fechar dm\"** ou use `/fechar-dm`.",
                color=0x5865F2,
            )
            await canal.send(embed=embed_intro)

        conteudo = mensagem.content or "*(sem texto — pode ser um anexo)*"
        embed = discord.Embed(description=conteudo, color=0x2B2D31)
        embed.set_author(name=str(autor), icon_url=autor.display_avatar.url)
        arquivos = [await a.to_file() for a in mensagem.attachments] if mensagem.attachments else []
        await canal.send(embed=embed, files=arquivos)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # --- Mensagem recebida por DM (o usuário falando com o bot) ---
        if message.guild is None:
            autor = message.author

            if autor.id in self._aguardando_escolha:
                opcoes = self._aguardando_escolha[autor.id]
                guilds_reais = [self.bot.get_guild(gid) for gid in opcoes]
                guilds_reais = [g for g in guilds_reais if g]
                try:
                    indice = int(message.content.strip()) - 1
                except ValueError:
                    indice = -1
                if 0 <= indice < len(guilds_reais):
                    del self._aguardando_escolha[autor.id]
                    await self._encaminhar_para_canal(guilds_reais[indice], autor, message)
                else:
                    await message.channel.send("Não entendi — responde só com o número do servidor da lista.")
                return

            candidatas = await self._guilds_candidatas(autor.id)
            if not candidatas:
                await message.channel.send("Nenhum dos servidores que a gente tem em comum tem esse sistema de DM ativado no momento.")
                return

            if len(candidatas) == 1:
                await self._encaminhar_para_canal(candidatas[0], autor, message)
                return

            self._aguardando_escolha[autor.id] = [g.id for g in candidatas]
            lista = "\n".join(f"{i+1}. {g.name}" for i, g in enumerate(candidatas))
            await message.channel.send(f"Você está em mais de um servidor com esse sistema. Pra qual deles é a sua mensagem? Responde só com o número:\n{lista}")
            return

        # --- Mensagem dentro de um canal de mod mail (a equipe respondendo) ---
        if not message.channel.topic or not message.channel.topic.startswith("modmail-user:"):
            return

        conteudo_normalizado = (message.content or "").strip().lower()
        if conteudo_normalizado in FRASES_FECHAR:
            await self._fechar_por_canal(message.guild.id, message.channel)
            return

        user_id = int(message.channel.topic.replace("modmail-user:", ""))
        usuario = self.bot.get_user(user_id)
        if not usuario:
            return

        embed = discord.Embed(description=message.content or "*(sem texto)*", color=0x57F287)
        embed.set_author(name=f"Resposta de {message.guild.name}", icon_url=message.guild.icon.url if message.guild.icon else None)
        try:
            await usuario.send(embed=embed)
        except discord.Forbidden:
            await message.channel.send("⚠️ Não consegui mandar DM pra essa pessoa — ela deve ter DMs fechadas ou saiu do servidor.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ModMail(bot))
