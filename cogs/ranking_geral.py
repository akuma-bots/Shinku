import discord

from discord import app_commands

from discord.ext import (
    commands,
    tasks,
)

from utils.storage import carregar, salvar

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
    registrar_tempo_top_global,
    reiniciar_temporada_global,
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

        dados = await registrar_tempo_top_global()

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
                    "pontos_temporada",
                    perfil.get("pontos", 0),
                )
                or 0
            )
            xp = int(perfil.get("xp", 0) or 0)
            vitorias = int(perfil.get("vitorias", 0) or 0)
            derrotas = int(perfil.get("derrotas", 0) or 0)
            tempo_top = int(perfil.get("tempo_top_global_segundos", 0) or 0)

            pontuados.append(
                (
                    user_id,
                    pontos,
                    vitorias,
                    xp,
                    derrotas,
                    tempo_top,
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
            f"「 {_negrito('RANKING GLOBAL — TEMPORADA')} 」\n"
        )

        estado_temporada = dados.get("temporada_global", {})
        inicio_temporada = float(estado_temporada.get("inicio_timestamp") or 0)
        fim_temporada = inicio_temporada + int(estado_temporada.get("duracao_dias", 30) or 30) * 86400
        restante = max(0, int(fim_temporada - __import__("time").time()))
        dias_restantes, resto = divmod(restante, 86400)
        horas_restantes = resto // 3600
        cabecalho += (
            f"Temporada **#{int(estado_temporada.get('numero', 1) or 1)}**"
            f" — reinicia em **{dias_restantes}d {horas_restantes}h**.\n\n"
        )


        if not top:

            descricao = (
                cabecalho
                + "Nenhum membro possui pontuação "
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
            vitorias,
            xp,
            derrotas,
            tempo_top,
        ) in enumerate(
            top,
            start=1,
        ):

            linhas_top.append(
                f"│ {_negrito('No.')}"
                f"{_negrito(f'{i:02d}')}"
                f" — <@{uid}>"
            )

            minutos_top = tempo_top // 60
            horas_top, minutos_restantes = divmod(minutos_top, 60)
            linhas_top.append(
                f"│           {_negrito(str(pontos))} PONTOS SAZONAIS"
            )
            linhas_top.append(
                f"│           XP {_negrito(str(xp))} | "
                f"V {_negrito(str(vitorias))} | D {_negrito(str(derrotas))}"
            )
            linhas_top.append(
                f"│           TOP 10: {_negrito(f'{horas_top}h {minutos_restantes}min')}"
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
            "XP, vitórias e derrotas são estatísticas acumuladas. "
            "A pontuação sazonal reinicia automaticamente a cada 30 dias; "
            "o histórico das temporadas fica preservado.\n\n"
            "O ranking usa os dados compartilhados com o Dashboard da NÊMESIS.\n\n"
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

        try:
            # A temporada global continua avançando mesmo sem canal de ranking configurado.
            await registrar_tempo_top_global()
        except Exception as erro:
            print(f"[RankingGeral] Falha ao atualizar temporada global: {erro}")

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

        try:
            canal_id = int(canal_id)
        except (TypeError, ValueError):
            return

        candidatos = [canal_id, 1545834182406574241]
        canal = None
        vistos = set()
        for valor in candidatos:
            try:
                identificador = int(valor) if valor else None
            except (TypeError, ValueError):
                identificador = None
            if not identificador or identificador in vistos:
                continue
            vistos.add(identificador)
            canal = guild.get_channel(identificador)
            if canal is None:
                try:
                    canal = await guild.fetch_channel(identificador)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException) as erro:
                    print(f"[RankingGeral] Canal {identificador} inacessível: {erro}")
                    canal = None
            if canal is not None and callable(getattr(canal, "send", None)):
                canal_id = identificador
                break
            canal = None

        if canal is None:
            print("[RankingGeral] Nenhum canal de ranking configurado/acessível.")
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
            "a pontuação compartilhada do Dashboard. "
            "Os pesos antigos não alteram o placar.",
            ephemeral=True,
        )


    @app_commands.command(
        name="resetar-perfis-global",
        description="Zera os perfis e o Top Global da NÊMESIS.",
    )
    @app_commands.describe(
        confirmacao="Selecione a confirmação para executar o reset completo."
    )
    @app_commands.choices(confirmacao=[
        app_commands.Choice(
            name="CONFIRMAR RESET COMPLETO",
            value="CONFIRMAR RESET COMPLETO",
        )
    ])
    @app_commands.checks.has_permissions(administrator=True)
    async def resetar_perfis_global(
        self,
        interaction: discord.Interaction,
        confirmacao: app_commands.Choice[str],
    ):
        if confirmacao.value != "CONFIRMAR RESET COMPLETO":
            await interaction.response.send_message(
                "Reset cancelado: confirmação inválida.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        import time
        agora = time.time()

        # Zera perfis locais usados pelo /perfil em todos os servidores.
        todos_perfis = await carregar(ARQUIVO_PERFIS, {})
        quantidade_local = 0
        campos_zero = {
            "xp": 0,
            "vitorias": 0,
            "derrotas": 0,
            "kills": 0,
            "deaths": 0,
            "mvps": 0,
            "sequencia_atual": 0,
            "maior_sequencia": 0,
            "medalhas": [],
            "patente": None,
        }
        for dados_guilda in todos_perfis.values():
            if not isinstance(dados_guilda, dict):
                continue
            for perfil in dados_guilda.values():
                if not isinstance(perfil, dict):
                    continue
                for campo, valor in campos_zero.items():
                    perfil[campo] = list(valor) if isinstance(valor, list) else valor
                quantidade_local += 1
        await salvar(ARQUIVO_PERFIS, todos_perfis)

        # competitivo.json é compartilhado com o site; preserva catálogo e identidades.
        competitivo = await carregar(
            ARQUIVO_COMPETITIVO,
            {"catalogo": [], "perfis": {}},
        )
        competitivo.setdefault("catalogo", [])
        competitivo.setdefault("perfis", {})
        quantidade_global = 0
        for perfil in competitivo["perfis"].values():
            if not isinstance(perfil, dict):
                continue
            perfil["pontos"] = 0
            perfil["pontos_temporada"] = 0
            perfil["xp"] = 0
            perfil["vitorias"] = 0
            perfil["derrotas"] = 0
            perfil["kills"] = 0
            perfil["deaths"] = 0
            perfil["mvps"] = 0
            perfil["sequencia_atual"] = 0
            perfil["maior_sequencia"] = 0
            perfil["medalhas"] = []
            perfil["patente"] = None
            perfil["kdr"] = 0
            perfil["tempo_top_global_segundos"] = 0
            perfil["em_top_global"] = False
            perfil["ultima_verificacao_top_global"] = agora
            quantidade_global += 1

        competitivo["temporada_global"] = {
            "numero": 1,
            "inicio_timestamp": agora,
            "duracao_dias": 30,
            "historico": [],
        }
        await salvar(ARQUIVO_COMPETITIVO, competitivo)

        await interaction.followup.send(
            "RESET COMPLETO EXECUTADO.\n"
            f"Perfis locais zerados: **{quantidade_local}**.\n"
            f"Perfis do Top Global/site zerados: **{quantidade_global}**.\n"
            "P.C., XP, vitórias, derrotas, K/D, MVPs, sequências, medalhas e "
            "tempo no Top 10 foram zerados. O histórico sazonal foi limpo e "
            "uma nova temporada de 30 dias foi iniciada. O catálogo foi preservado.",
            ephemeral=True,
        )

    @app_commands.command(
        name="ranking-geral",
        description=(
            "Mostra o Top 10 atual de pontuação."
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


    @app_commands.command(
        name="temporada-reiniciar",
        description="Encerra a temporada atual e inicia outra sem apagar estatísticas acumuladas.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def temporada_reiniciar(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            dados = await reiniciar_temporada_global()
            estado = dados.get("temporada_global", {})
            numero = int(estado.get("numero", 2) or 2)
            await interaction.followup.send(
                f"Temporada reiniciada. A nova temporada é **#{numero}** e dura 30 dias. "
                "Pontos sazonais foram zerados; o histórico da temporada anterior, "
                "P.C. acumulados, XP, vitórias, derrotas e tempo no Top 10 foram preservados.",
                ephemeral=True,
            )
            if interaction.guild:
                await self._atualizar_painel(interaction.guild)
        except Exception as erro:
            print(f"[RankingGeral] Falha ao reiniciar temporada: {erro}")
            await interaction.followup.send(
                "Não foi possível reiniciar a temporada. Verifique os logs do bot.",
                ephemeral=True,
            )


async def setup(
    bot: commands.Bot,
):

    await bot.add_cog(
        RankingGeral(bot)
    )