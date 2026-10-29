import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.apresentacao import embed_erro, embed_info, embed_sucesso
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
_LOG = logging.getLogger(__name__)


def _contador_registrado(config: dict, canal_id: int) -> bool:
    contadores = config.get("contadores", []) if isinstance(config, dict) else []
    return any(
        isinstance(item, dict) and item.get("canal_id") == canal_id
        for item in contadores
    )


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
                embed=embed_erro(
                    "PARÂMETRO OBRIGATÓRIO",
                    "Para criar um contador por cargo, selecione também o cargo que será contabilizado.",
                ),
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

        canal = None
        try:
            canal = await guild.create_voice_channel(
                name=nome_canal,
                reason="Contador criado via /criar-contador",
            )
            await canal.set_permissions(guild.default_role, connect=False)
            await adicionar_contador(
                guild.id,
                tipo,
                canal.id,
                cargo.id if cargo else None,
            )
        except Exception:
            _LOG.exception("Falha ao criar contador (guild=%s, tipo=%s).", guild.id, tipo)
            # Se a configuração falhar depois da criação do canal, evita deixar
            # um canal órfão que não será mais gerenciado pelo bot.
            if canal is not None:
                try:
                    await canal.delete(reason="Rollback de contador não configurado")
                except (discord.Forbidden, discord.HTTPException):
                    pass
            await interaction.followup.send(
                embed=embed_erro(
                    "NÃO FOI POSSÍVEL CRIAR",
                    "A criação do contador falhou. Confira as permissões Gerenciar canais e tente novamente. "
                    "Se o canal chegou a ser criado, o bot tentou removê-lo para evitar um contador órfão.",
                ),
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=embed_sucesso(
                "CONTADOR ATIVADO",
                f"**Canal:** {canal.mention}\n"
                f"**Tipo:** {self._rotulo(tipo, cargo)}\n"
                f"**Valor inicial:** {valor:,}\n"
                f"**Atualização:** a cada {INTERVALO_ATUALIZACAO_MINUTOS} minutos",
            ),
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

        config = await get_config(interaction.guild.id)
        if not _contador_registrado(config, canal.id):
            await interaction.response.send_message(
                embed=embed_erro(
                    "CONTADOR NÃO ENCONTRADO",
                    "Esse canal não está registrado pelo sistema. Nenhum canal foi apagado.",
                ),
                ephemeral=True,
            )
            return

        try:
            await canal.delete(reason="Contador removido via /remover-contador")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=embed_erro(
                    "PERMISSÃO INSUFICIENTE",
                    "Não tenho permissão para apagar esse canal. O contador continua registrado e não foi removido da configuração.",
                ),
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                embed=embed_erro(
                    "FALHA AO REMOVER CANAL",
                    "O Discord recusou a exclusão. O contador continua registrado na configuração.",
                ),
                ephemeral=True,
            )
            return

        await remover_contador(interaction.guild.id, canal.id)
        await interaction.response.send_message(
            embed=embed_sucesso("CONTADOR REMOVIDO", f"O canal {discord.utils.escape_markdown(canal.name)} foi removido e a configuração foi atualizada."),
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
                embed=embed_info(
                    "NENHUM CONTADOR ATIVO",
                    "Este servidor ainda não possui contadores registrados. Use /criar-contador para configurar o primeiro.",
                ),
                ephemeral=True,
            )
            return

        embed = embed_info(
            "CONTADORES DO SERVIDOR",
            f"**Contadores registrados:** {len(lista)}\n"
            f"**Atualização automática:** a cada {INTERVALO_ATUALIZACAO_MINUTOS} minutos",
        )
        for item in lista[:25]:
            canal_id = item.get("canal_id")
            tipo = item.get("tipo", "desconhecido")
            canal = interaction.guild.get_channel(canal_id) if canal_id else None
            embed.add_field(
                name=(canal.name if canal else f"Canal indisponível • {canal_id}"),
                value=f"**Canal:** <#{canal_id}>\n**Tipo:** {tipo}",
                inline=True,
            )
        if len(lista) > 25:
            embed.add_field(name="Lista parcial", value=f"Mais {len(lista) - 25} contador(es) não exibidos nesta página.", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

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

                    tipo = item.get("tipo")
                    if tipo not in TIPOS_VALIDOS:
                        continue

                    valor = self._calcular_valor(
                        guild,
                        tipo,
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