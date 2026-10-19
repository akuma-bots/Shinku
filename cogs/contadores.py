import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.guild_config import (
    get_config,
    adicionar_contador,
    remover_contador,
)

TIPOS_VALIDOS = [
    "membros",
    "online",
    "bots",
    "boosts",
    "cargo",
]

INTERVALO_ATUALIZACAO_MINUTOS = 10


class Contadores(commands.Cog):
    """
    Canais de voz atualizados automaticamente com dados internos do bot.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.atualizar_contadores.start()

    def cog_unload(self):
        self.atualizar_contadores.cancel()

    def _rotulo(
        self,
        tipo: str,
        cargo: discord.Role = None,
    ) -> str:
        return {
            "membros": "👥 Membros",
            "online": "🟢 Online",
            "bots": "🤖 Bots",
            "boosts": "🚀 Boosts",
            "cargo": (
                f"🏷️ {cargo.name}"
                if cargo
                else "🏷️ Cargo"
            ),
        }[tipo]

    def _calcular_valor(
        self,
        guild: discord.Guild,
        tipo: str,
        cargo_id: int = None,
    ) -> int:

        if tipo == "membros":
            return guild.member_count or 0

        if tipo == "bots":
            return sum(
                1
                for membro in guild.members
                if membro.bot
            )

        if tipo == "online":
            return sum(
                1
                for membro in guild.members
                if (
                    membro.status != discord.Status.offline
                    and not membro.bot
                )
            )

        if tipo == "boosts":
            return (
                guild.premium_subscription_count
                or 0
            )

        if tipo == "cargo":
            cargo = (
                guild.get_role(cargo_id)
                if cargo_id
                else None
            )

            return (
                len(cargo.members)
                if cargo
                else 0
            )

        return 0

    @app_commands.command(
        name="criar-contador",
        description=(
            "Cria um canal de voz que mostra "
            "uma contagem ao vivo."
        ),
    )
    @app_commands.describe(
        tipo="O que contar",
        cargo=(
            "Só se o tipo for 'cargo': "
            "qual cargo contar"
        ),
    )
    @app_commands.choices(
        tipo=[
            app_commands.Choice(
                name=tipo,
                value=tipo,
            )
            for tipo in TIPOS_VALIDOS
        ]
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def criar_contador(
        self,
        interaction: discord.Interaction,
        tipo: str,
        cargo: discord.Role = None,
    ):

        if tipo == "cargo" and cargo is None:
            await interaction.response.send_message(
                "Pra contar por cargo, informe também "
                "o parâmetro `cargo`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        guild = interaction.guild

        valor = self._calcular_valor(
            guild,
            tipo,
            cargo.id if cargo else None,
        )

        nome_canal = (
            f"{self._rotulo(tipo, cargo)}: {valor}"
        )

        canal = await guild.create_voice_channel(
            name=nome_canal,
            reason="Contador criado via /criar-contador",
        )

        await canal.set_permissions(
            guild.default_role,
            connect=False,
        )

        await adicionar_contador(
            guild.id,
            tipo,
            canal.id,
            cargo.id if cargo else None,
        )

        await interaction.followup.send(
            f"✅ Contador criado: {canal.mention}. "
            f"Ele se atualiza a cada "
            f"{INTERVALO_ATUALIZACAO_MINUTOS} minutos.",
            ephemeral=True,
        )

    @app_commands.command(
        name="remover-contador",
        description=(
            "Remove um contador e apaga "
            "o canal de voz dele."
        ),
    )
    @app_commands.describe(
        canal="O canal de voz do contador"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def remover_contador_cmd(
        self,
        interaction: discord.Interaction,
        canal: discord.VoiceChannel,
    ):

        await remover_contador(
            interaction.guild.id,
            canal.id,
        )

        try:
            await canal.delete(
                reason=(
                    "Contador removido via "
                    "/remover-contador"
                )
            )
        except discord.HTTPException:
            pass

        await interaction.response.send_message(
            "🗑️ Contador removido.",
            ephemeral=True,
        )

    @app_commands.command(
        name="contadores",
        description=(
            "Lista os contadores ativos "
            "neste servidor."
        ),
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def contadores(
        self,
        interaction: discord.Interaction,
    ):

        config = await get_config(
            interaction.guild.id
        )

        lista = config.get(
            "contadores",
            [],
        )

        if not lista:
            await interaction.response.send_message(
                "Nenhum contador configurado ainda.",
                ephemeral=True,
            )
            return

        linhas = [
            (
                f"<#{item['canal_id']}> — "
                f"tipo `{item['tipo']}`"
            )
            for item in lista
        ]

        await interaction.response.send_message(
            "\n".join(linhas),
            ephemeral=True,
        )

    @tasks.loop(
        minutes=INTERVALO_ATUALIZACAO_MINUTOS
    )
    async def atualizar_contadores(self):

        for guild in self.bot.guilds:

            try:
                config = await get_config(
                    guild.id
                )

                lista = config.get(
                    "contadores",
                    [],
                )

                for item in lista:

                    canal = guild.get_channel(
                        item["canal_id"]
                    )

                    if not canal:
                        continue

                    valor = self._calcular_valor(
                        guild,
                        item["tipo"],
                        item.get("cargo_id"),
                    )

                    cargo = (
                        guild.get_role(
                            item["cargo_id"]
                        )
                        if item.get("cargo_id")
                        else None
                    )

                    novo_nome = (
                        f"{self._rotulo(item['tipo'], cargo)}"
                        f": {valor}"
                    )

                    if canal.name != novo_nome:

                        try:
                            await canal.edit(
                                name=novo_nome,
                                reason=(
                                    "Atualização automática "
                                    "de contador"
                                ),
                            )

                        except discord.HTTPException:
                            pass

            except Exception as erro:
                print(
                    "[CONTADORES] "
                    f"Erro na atualização da guild "
                    f"{guild.id}: {erro}"
                )

    @atualizar_contadores.before_loop
    async def antes_de_atualizar(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(
        Contadores(bot)
    )