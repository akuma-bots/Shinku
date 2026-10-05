import discord

from discord import app_commands

from discord.ext import (
    commands,
    tasks,
)

from utils.storage import carregar

from utils.guild_config import (
    get_config,
    set_config,
)

from utils.perfis import (
    ARQUIVO_PERFIS,
)

from utils.competitivo_sync import (
    ARQUIVO_COMPETITIVO,
    migrar_perfil_se_necessario,
)


INTERVALO_RANKING_MINUTOS = 1


def _negrito(
    texto: str,
) -> str:

    resultado = []

    for ch in texto:

        if "A" <= ch <= "Z":

            resultado.append(
                chr(
                    0x1D400
                    + (
                        ord(ch)
                        - ord("A")
                    )
                )
            )

        elif "a" <= ch <= "z":

            resultado.append(
                chr(
                    0x1D41A
                    + (
                        ord(ch)
                        - ord("a")
                    )
                )
            )

        elif "0" <= ch <= "9":

            resultado.append(
                chr(
                    0x1D7CE
                    + (
                        ord(ch)
                        - ord("0")
                    )
                )
            )

        else:

            resultado.append(ch)

    return "".join(resultado)


class RankingGeral(
    commands.Cog
):

    def __init__(
        self,
        bot: commands.Bot,
    ):

        self.bot = bot

        self.atualizar_ranking_automatico.start()


    def cog_unload(self):

        self.atualizar_ranking_automatico.cancel()


    async def _sincronizar_migracao(
        self,
        guild: discord.Guild,
    ):

        dados = await carregar(
            ARQUIVO_COMPETITIVO,
            {
                "catalogo": [],
                "perfis": {},
            },
        )

        dados.setdefault(
            "perfis",
            {},
        )

        existentes = set(
            dados["perfis"].keys()
        )

        perfis = await carregar(
            ARQUIVO_PERFIS,
            {},
        )

        perfis_guild = perfis.get(
            str(guild.id),
            {},
        )

        for uid, perfil in perfis_guild.items():

            if uid in existentes:
                continue

            membro = guild.get_member(
                int(uid)
            )

            nome = (
                membro.display_name
                if membro
                else ""
            )

            await migrar_perfil_se_necessario(
                user_id=int(uid),
                nome=nome,
                perfil_bot=perfil,
            )


    async def _montar_embed(
        self,
        guild: discord.Guild,
    ) -> discord.Embed:

        await self._sincronizar_migracao(
            guild
        )

        dados = await carregar(
            ARQUIVO_COMPETITIVO,
            {
                "catalogo": [],
                "perfis": {},
            },
        )

        perfis = dados.get(
            "perfis",
            {},
        )

        pontuados = []

        for uid, perfil in perfis.items():

            try:

                user_id = int(uid)

            except (
                TypeError,
                ValueError,
            ):

                continue

            pontos = int(
                perfil.get(
                    "pontos",
                    0,
                )
                or 0
            )

            vitorias = int(
                perfil.get(
                    "vitorias",
                    0,
                )
                or 0
            )

            pontuados.append(
                (
                    user_id,
                    pontos,
                    vitorias,
                )
            )

        top = sorted(
            pontuados,
            key=lambda item: (
                item[1],
                item[2],
            ),
            reverse=True,
        )[:10]


        cabecalho = (
            "╔═════════════════════════════════╗\n"
            f"║        {guild.name} | "
            f"{_negrito('TOP 10')}        ║\n"
            "╚═════════════════════════════════╝\n\n"
            f"「 {_negrito('RANKING DE P.C.')} 」\n\n"
        )


        if not top:

            descricao = (
                cabecalho
                + "Nenhum membro possui P.C. "
                  "registrado ainda."
            )

            return discord.Embed(
                description=descricao,
                color=0xFFD700,
            )


        linhas_top = []

        for i, (
            uid,
            pontos,
            _vitorias,
        ) in enumerate(
            top,
            start=1,
        ):

            linhas_top.append(
                f"│ {_negrito('No.')}"
                f"{_negrito(f'{i:02d}')}"
                f" — <@{uid}>"
            )

            linhas_top.append(
                f"│           "
                f"{_negrito(str(pontos))} "
                f"{_negrito('P.C.')}"
            )

            if i != len(top):

                linhas_top.append("│")


        corpo = "\n".join(
            linhas_top
        )


        descricao = (
            f"{cabecalho}"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{_negrito('TOP 10')} — "
            f"{_negrito('CLASSIFICAÇÃO')}\n\n"
            "╭──────────────────────────────────────╮\n"
            f"{corpo}\n"
            "╰──────────────────────────────────────╯\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"「 {_negrito('ATUALIZAÇÃO')} 」\n\n"
            "O placar utiliza o mesmo P.C. "
            "armazenado pelo Dashboard da NÊMESIS.\n\n"
            "Alterações feitas no site serão "
            "refletidas no próximo ciclo de "
            "atualização do bot.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"「 {guild.name} | "
            f"{_negrito('TOP 10')} 」"
        )


        return discord.Embed(
            description=descricao,
            color=0xFFD700,
        )


    @tasks.loop(
        minutes=INTERVALO_RANKING_MINUTOS
    )
    async def atualizar_ranking_automatico(
        self,
    ):

        for guild in self.bot.guilds:

            try:

                await self._atualizar_painel(
                    guild
                )

            except Exception as erro:

                print(
                    "[RankingGeral] "
                    f"Falha ao atualizar "
                    f"{guild.id}: {erro}"
                )


    @atualizar_ranking_automatico.before_loop
    async def antes_de_comecar(
        self,
    ):

        await self.bot.wait_until_ready()


    async def _atualizar_painel(
        self,
        guild: discord.Guild,
    ):

        config = await get_config(
            guild.id
        )

        canal_id = config.get(
            "canal_ranking_id"
        )

        if not canal_id:
            return

        canal = guild.get_channel(
            canal_id
        )

        if not canal:
            return

        embed = await self._montar_embed(
            guild
        )

        mensagem_id = config.get(
            "ranking_mensagem_id"
        )


        if mensagem_id:

            try:

                msg = await canal.fetch_message(
                    mensagem_id
                )

                await msg.edit(
                    embed=embed
                )

                return

            except (
                discord.NotFound,
                discord.Forbidden,
            ):

                pass


        nova_msg = await canal.send(
            embed=embed
        )

        await set_config(
            guild.id,
            ranking_mensagem_id=nova_msg.id,
        )


    @app_commands.command(
        name="ranking-canal",
        description=(
            "Define o canal do ranking automático."
        ),
    )
    @app_commands.describe(
        canal=(
            "Canal onde o ranking "
            "ficará publicado."
        ),
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def ranking_canal(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ):

        await set_config(
            interaction.guild.id,
            canal_ranking_id=canal.id,
            ranking_mensagem_id=None,
        )

        await interaction.response.send_message(
            f"Ranking automático configurado "
            f"em {canal.mention}.",
            ephemeral=True,
        )

        await self._atualizar_painel(
            interaction.guild
        )


    @app_commands.command(
        name="ranking-pesos",
        description=(
            "Mantido para compatibilidade "
            "com a configuração antiga."
        ),
    )
    @app_commands.describe(
        peso_xp=(
            "Peso antigo de XP."
        ),
        peso_vitoria=(
            "Peso antigo de vitória."
        ),
        peso_mvp=(
            "Peso antigo de MVP."
        ),
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def ranking_pesos(
        self,
        interaction: discord.Interaction,
        peso_xp: int | None = None,
        peso_vitoria: int | None = None,
        peso_mvp: int | None = None,
    ):

        campos = {}

        if peso_xp is not None:

            campos[
                "peso_ranking_xp"
            ] = peso_xp

        if peso_vitoria is not None:

            campos[
                "peso_ranking_vitoria"
            ] = peso_vitoria

        if peso_mvp is not None:

            campos[
                "peso_ranking_mvp"
            ] = peso_mvp


        if campos:

            await set_config(
                interaction.guild.id,
                **campos,
            )


        await interaction.response.send_message(
            "O ranking agora usa exclusivamente "
            "o P.C. compartilhado do Dashboard. "
            "Os pesos antigos não alteram o placar.",
            ephemeral=True,
        )


    @app_commands.command(
        name="ranking-geral",
        description=(
            "Mostra o Top 10 atual de P.C."
        ),
    )
    async def ranking_geral(
        self,
        interaction: discord.Interaction,
    ):

        embed = await self._montar_embed(
            interaction.guild
        )

        await interaction.response.send_message(
            embed=embed
        )


async def setup(
    bot: commands.Bot,
):

    await bot.add_cog(
        RankingGeral(bot)
    )