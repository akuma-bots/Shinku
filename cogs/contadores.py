import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.guild_config import (
    get_config,
    adicionar_contador,
    remover_contador,
)
from utils.storage import carregar, salvar


ARQUIVO_CONTADORES = "contadores.json"

TIPOS_VALIDOS = [
    "membros",
    "online",
    "bots",
    "boosts",
    "cargo",
]

INTERVALO_ATUALIZACAO_MINUTOS = 10


async def _tudo_contadores():
    return await carregar(
        ARQUIVO_CONTADORES,
        {},
    )


async def _salvar_contadores(dados):
    await salvar(
        ARQUIVO_CONTADORES,
        dados,
    )


async def _sincronizar_contadores_guild(
    guild_id: int,
    lista: list,
):
    dados = await _tudo_contadores()

    dados[str(guild_id)] = {
        "guildId": str(guild_id),
        "contadores": [
            {
                "tipo": item.get("tipo"),
                "canalId": str(item.get("canal_id")),
                "cargoId": (
                    str(item["cargo_id"])
                    if item.get("cargo_id")
                    else None
                ),
                "atualizadoEm": time.time(),
            }
            for item in lista
        ],
    }

    await _salvar_contadores(dados)


async def sincronizar_todos_site(bot: commands.Bot):
    """
    Sincroniza os contadores configurados em guild_config.json
    para contadores.json, usado pelo Dashboard.
    """

    total = 0

    for guild in bot.guilds:
        try:
            config = await get_config(guild.id)
            lista = config.get("contadores", [])

            await _sincronizar_contadores_guild(
                guild.id,
                lista,
            )

            total += len(lista)

        except Exception as erro:
            print(
                "[CONTADORES] "
                f"Falha ao sincronizar guild {guild.id}: "
                f"{erro}"
            )

    return total


class Contadores(commands.Cog):
    """
    Canais de voz que exibem contagens atualizadas
    automaticamente e mantêm os dados sincronizados
    com o Dashboard da NÊMESIS.
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

        config = await get_config(guild.id)

        await _sincronizar_contadores_guild(
            guild.id,
            config.get("contadores", []),
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

        config = await get_config(
            interaction.guild.id
        )

        await _sincronizar_contadores_guild(
            interaction.guild.id,
            config.get("contadores", []),
        )

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

    @app_commands.command(
        name="contadores-sincronizar",
        description=(
            "Sincroniza os contadores "
            "com o Dashboard da NÊMESIS."
        ),
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def contadores_sincronizar(
        self,
        interaction: discord.Interaction,
    ):

        await interaction.response.defer(
            ephemeral=True
        )

        quantidade = await sincronizar_todos_site(
            self.bot
        )

        await interaction.followup.send(
            f"✅ {quantidade} contador(es) "
            "sincronizado(s) com o Dashboard.",
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

                await _sincronizar_contadores_guild(
                    guild.id,
                    lista,
                )

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