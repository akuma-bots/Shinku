import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config


ARQUIVO = "modmail_canais.json"

FRASES_FECHAR = [
    "fechar dm",
    "fechar o dm",
    "encerrar dm",
    "encerrar o dm",
    "fechar conversa",
    "encerrar conversa",
]


async def _mapa_nemesis(guild_id: int) -> dict:
    dados = await carregar(ARQUIVO, {})
    return dados.get(str(guild_id), {})


async def _salvar_mapa_nemesis(guild_id: int, mapa: dict):
    dados = await carregar(ARQUIVO, {})
    dados[str(guild_id)] = mapa
    await salvar(ARQUIVO, dados)


class ModMail(commands.Cog):
    """Sistema de atendimento por DM exclusivo da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="configurar-canal-modmail",
        description="Define a categoria usada pelo atendimento privado da NÊMESIS.",
    )
    @app_commands.describe(
        categoria="Categoria onde os atendimentos privados serão criados",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_canal_modmail(
        self,
        interaction: discord.Interaction,
        categoria: discord.CategoryChannel,
    ):
        await set_config(
            interaction.guild.id,
            categoria_modmail_id=categoria.id,
        )

        await interaction.response.send_message(
            f"Atendimento privado configurado na categoria "
            f"**{categoria.name}**.",
            ephemeral=True,
        )

    @app_commands.command(
        name="fechar-dm",
        description="Fecha o atendimento privado associado a este canal.",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def fechar_dm(self, interaction: discord.Interaction):
        fechou = await self._fechar_por_canal(
            interaction.guild.id,
            interaction.channel,
        )

        if fechou:
            await interaction.response.send_message(
                "Encerrando este atendimento privado...",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                "Este canal não corresponde a um atendimento privado da NÊMESIS.",
                ephemeral=True,
            )

    async def _fechar_por_canal(
        self,
        guild_id: int,
        canal: discord.TextChannel,
    ) -> bool:
        mapa = await _mapa_nemesis(guild_id)

        user_id = next(
            (
                uid
                for uid, channel_id in mapa.items()
                if channel_id == canal.id
            ),
            None,
        )

        if not user_id:
            return False

        mapa.pop(user_id, None)
        await _salvar_mapa_nemesis(guild_id, mapa)

        usuario = self.bot.get_user(int(user_id))

        if usuario:
            try:
                await usuario.send(
                    "🔒 Seu atendimento com a equipe da **NÊMESIS** "
                    "foi encerrado.\n\n"
                    "Você pode enviar outra mensagem caso precise de ajuda novamente."
                )
            except discord.Forbidden:
                pass

        try:
            await canal.send("🔒 Encerrando este atendimento...")
            await canal.delete(
                reason="Atendimento privado da NÊMESIS encerrado."
            )
        except discord.NotFound:
            pass

        return True

    async def _encaminhar_para_canal(
        self,
        guild: discord.Guild,
        autor: discord.User,
        mensagem: discord.Message,
    ):
        mapa = await _mapa_nemesis(guild.id)

        canal_id = mapa.get(str(autor.id))
        canal = guild.get_channel(canal_id) if canal_id else None

        if not canal:
            config = await get_config(guild.id)

            categoria_id = config.get("categoria_modmail_id")

            if not categoria_id:
                try:
                    await autor.send(
                        "O atendimento privado da NÊMESIS "
                        "não está configurado no momento."
                    )
                except discord.Forbidden:
                    pass

                return

            categoria = guild.get_channel(categoria_id)
            cargo_suporte_id = config.get("support_role_id")

            if not categoria:
                try:
                    await autor.send(
                        "A configuração do atendimento privado da NÊMESIS "
                        "está incompleta."
                    )
                except discord.Forbidden:
                    pass

                return

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=False
                )
            }

            if cargo_suporte_id:
                cargo = guild.get_role(cargo_suporte_id)

                if cargo:
                    overwrites[cargo] = discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        read_message_history=True,
                    )

            canal = await guild.create_text_channel(
                name=f"dm-{autor.name}"[:95],
                category=categoria,
                overwrites=overwrites,
                topic=f"nemesis-modmail-user:{autor.id}",
                reason=f"Novo atendimento privado da NÊMESIS: {autor}",
            )

            mapa[str(autor.id)] = canal.id
            await _salvar_mapa_nemesis(guild.id, mapa)

            embed_intro = discord.Embed(
                title="NÊMESIS — Atendimento",
                description=(
                    f"Novo atendimento privado de {autor.mention} (`{autor}`).\n\n"
                    "A equipe pode responder diretamente neste canal. "
                    "As respostas serão encaminhadas para a DM do usuário.\n\n"
                    "Para encerrar, utilize `/fechar-dm`."
                ),
                color=0x5865F2,
            )

            await canal.send(embed=embed_intro)

        conteudo = (
            mensagem.content
            if mensagem.content
            else "*(sem texto — pode ser um anexo)*"
        )

        embed = discord.Embed(
            description=conteudo,
            color=0x2B2D31,
        )

        embed.set_author(
            name=str(autor),
            icon_url=autor.display_avatar.url,
        )

        arquivos = (
            [await anexo.to_file() for anexo in mensagem.attachments]
            if mensagem.attachments
            else []
        )

        await canal.send(
            embed=embed,
            files=arquivos,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # Mensagem recebida por DM.
        if message.guild is None:
            guild = next(iter(self.bot.guilds), None)

            if guild is None:
                return

            config = await get_config(guild.id)

            if not config.get("categoria_modmail_id"):
                try:
                    await message.channel.send(
                        "O atendimento privado da NÊMESIS "
                        "não está disponível no momento."
                    )
                except discord.Forbidden:
                    pass

                return

            await self._encaminhar_para_canal(
                guild,
                message.author,
                message,
            )

            return

        # Mensagem dentro de um canal de atendimento.
        topic = message.channel.topic or ""

        if not topic.startswith("nemesis-modmail-user:"):
            return

        conteudo_normalizado = (
            message.content or ""
        ).strip().lower()

        if conteudo_normalizado in FRASES_FECHAR:
            await self._fechar_por_canal(
                message.guild.id,
                message.channel,
            )
            return

        try:
            user_id = int(
                topic.replace(
                    "nemesis-modmail-user:",
                    "",
                )
            )
        except ValueError:
            return

        usuario = self.bot.get_user(user_id)

        if not usuario:
            return

        embed = discord.Embed(
            description=message.content or "*(sem texto)*",
            color=0x57F287,
        )

        embed.set_author(
            name="Resposta da equipe da NÊMESIS",
            icon_url=(
                message.guild.icon.url
                if message.guild.icon
                else None
            ),
        )

        try:
            await usuario.send(embed=embed)
        except discord.Forbidden:
            await message.channel.send(
                "Não foi possível enviar a resposta por DM. "
                "As mensagens privadas do usuário podem estar desativadas."
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ModMail(bot))