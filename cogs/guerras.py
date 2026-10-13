import re
import time
import uuid
import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar
from utils.guild_config import get_config
from utils.perfis import (
    registrar_resultado_guerra,
    registrar_empate_guerra,
    calcular_patente_atual,
    definir_patente,
)


ARQUIVO_GUERRAS = "guerras.json"


def _extrair_mencoes(texto: str) -> list:
    if not texto:
        return []

    return [
        int(m)
        for m in re.findall(r"<@!?(\d+)>", texto)
    ]


class Guerras(commands.Cog):
    """
    Sistema de guerras da NÊMESIS.

    Os registros ficam persistidos em guerras.json, permitindo ao
    Dashboard acessar o histórico, temporadas, participantes,
    resultados e guerras agendadas.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _dados_guild(self, guild_id: int) -> dict:
        todos = await carregar(
            ARQUIVO_GUERRAS,
            {},
        )

        dados = todos.get(
            str(guild_id),
            {
                "guild_id": guild_id,
                "temporada_atual": 1,
                "guerras": [],
                "agendamentos": [],
            },
        )

        dados.setdefault("guild_id", guild_id)
        dados.setdefault("temporada_atual", 1)
        dados.setdefault("guerras", [])
        dados.setdefault("agendamentos", [])

        return dados

    async def _salvar_dados_guild(
        self,
        guild_id: int,
        dados: dict,
    ):
        todos = await carregar(
            ARQUIVO_GUERRAS,
            {},
        )

        dados["guild_id"] = guild_id
        dados.setdefault("temporada_atual", 1)
        dados.setdefault("guerras", [])
        dados.setdefault("agendamentos", [])

        todos[str(guild_id)] = dados

        await salvar(
            ARQUIVO_GUERRAS,
            todos,
        )

    @app_commands.command(
        name="guerra-agendar",
        description="Anuncia uma guerra agendada entre duas gangues.",
    )
    @app_commands.describe(
        gangue_a="Nome da primeira gangue",
        gangue_b="Nome da segunda gangue",
        quando="Quando vai ser (ex: sábado 20h)",
        formato="Formato da guerra (ex: 5v5 MD3)",
        servidor="Jogo ou servidor onde será disputada",
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def guerra_agendar(
        self,
        interaction: discord.Interaction,
        gangue_a: str,
        gangue_b: str,
        quando: str,
        formato: str = None,
        servidor: str = None,
    ):
        config = await get_config(
            interaction.guild.id
        )

        # Canal oficial de guerras da NÊMESIS.
        canal_id = config.get("canal_guerras_id")

        canal = (
            interaction.guild.get_channel(canal_id)
            if canal_id
            else interaction.channel
        )

        if canal is None:
            await interaction.response.send_message(
                "❌ O canal oficial de guerras não foi encontrado.",
                ephemeral=True,
            )
            return

        if not gangue_a.strip() or not gangue_b.strip() or gangue_a.strip().casefold() == gangue_b.strip().casefold():
            await interaction.response.send_message("❌ Informe duas gangues diferentes.", ephemeral=True)
            return

        registro_id = str(uuid.uuid4())[:8]

        agendamento = {
            "id": registro_id,
            "guild_id": interaction.guild.id,
            "gangue_a": gangue_a,
            "gangue_b": gangue_b,
            "quando": quando.strip(),
            "formato": formato.strip() if formato else None,
            "servidor": servidor.strip() if servidor else None,
            "agendado_por_id": interaction.user.id,
            "canal_id": canal.id,
            "timestamp": time.time(),
            "status": "agendada",
        }

        dados = await self._dados_guild(
            interaction.guild.id
        )

        dados["agendamentos"].append(
            agendamento
        )

        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  GUERRA AGENDADA",
            description=(
                f"**{gangue_a}** vs **{gangue_b}**"
            ),
            color=0xB51F32,
        )

        embed.add_field(name="◈ DATA / HORÁRIO", value=quando.strip()[:1024], inline=True)
        if formato:
            embed.add_field(name="◈ FORMATO", value=formato.strip()[:1024], inline=True)
        if servidor:
            embed.add_field(name="◈ JOGO / SERVIDOR", value=servidor.strip()[:1024], inline=True)

        embed.add_field(
            name="◈ CÓDIGO DA GUERRA",
            value=f"`{registro_id}`",
            inline=True,
        )

        embed.set_footer(
            text=f"NÊMESIS • OPERAÇÕES OFICIAIS • Agendada por {interaction.user}"
        )

        try:
            mensagem = await canal.send(
                embed=embed
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Não tenho permissão para enviar mensagens no canal oficial de guerras.",
                ephemeral=True,
            )
            return
        except discord.HTTPException:
            await interaction.response.send_message(
                "❌ Não foi possível publicar a guerra no canal oficial.",
                ephemeral=True,
            )
            return

        agendamento["mensagem_id"] = mensagem.id

        await self._salvar_dados_guild(
            interaction.guild.id,
            dados,
        )

        await interaction.response.send_message(
            f"✅ Guerra anunciada em {canal.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="guerra-registrar",
        description="Registra o resultado de uma guerra já disputada.",
    )
    @app_commands.describe(
        gangue_a="Nome da primeira gangue",
        gangue_b="Nome da segunda gangue",
        placar_a="Placar da gangue A",
        placar_b="Placar da gangue B",
        mvp="Quem foi o MVP da guerra (opcional)",
        participantes_a="Mencione os participantes da gangue A, separados por espaço",
        participantes_b="Mencione os participantes da gangue B, separados por espaço",
        prova_url="Link da prova/print da guerra (opcional)",
        formato="Formato disputado (ex: 5v5 MD3)",
        servidor="Jogo ou servidor usado",
        arbitro="Staff que acompanhou a guerra (opcional)",
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def guerra_registrar(
        self,
        interaction: discord.Interaction,
        gangue_a: str,
        gangue_b: str,
        placar_a: int,
        placar_b: int,
        mvp: discord.Member = None,
        participantes_a: str = None,
        participantes_b: str = None,
        prova_url: str = None,
        formato: str = None,
        servidor: str = None,
        arbitro: discord.Member = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("Este comando só pode ser usado dentro do servidor.", ephemeral=True)
            return
        gangue_a = gangue_a.strip()
        gangue_b = gangue_b.strip()
        if not gangue_a or not gangue_b or gangue_a.casefold() == gangue_b.casefold():
            await interaction.response.send_message("❌ Informe duas gangues diferentes.", ephemeral=True)
            return
        if placar_a < 0 or placar_b < 0:
            await interaction.response.send_message("❌ O placar não pode ser negativo.", ephemeral=True)
            return
        if prova_url and not re.match(r"^https?://\S+$", prova_url.strip(), re.IGNORECASE):
            await interaction.response.send_message("❌ O link da prova precisa começar com http:// ou https://.", ephemeral=True)
            return
        ids_a = list(dict.fromkeys(_extrair_mencoes(participantes_a)))
        ids_b = list(dict.fromkeys(_extrair_mencoes(participantes_b)))
        if not ids_a or not ids_b:
            await interaction.response.send_message("❌ Informe pelo menos um participante de cada gangue para atualizar o histórico individual.", ephemeral=True)
            return
        if set(ids_a) & set(ids_b):
            await interaction.response.send_message("❌ Um participante não pode estar nas duas gangues.", ephemeral=True)
            return
        todos_ids = set(ids_a + ids_b)
        if mvp and mvp.id not in todos_ids:
            await interaction.response.send_message("❌ O MVP precisa estar entre os participantes informados.", ephemeral=True)
            return
        await interaction.response.defer()

        if placar_a > placar_b:
            vencedor = gangue_a
        elif placar_b > placar_a:
            vencedor = gangue_b
        else:
            vencedor = "Empate"

        medalhas_ganhas_texto = []
        promocoes_texto = []

        async def _processar(
            ids,
            gangue,
            venceu,
            empatou=False,
        ):
            for user_id in ids:
                foi_mvp = (
                    mvp is not None
                    and mvp.id == user_id
                )

                if empatou:
                    resultado = await registrar_empate_guerra(interaction.guild.id, user_id, foi_mvp)
                else:
                    resultado = await registrar_resultado_guerra(interaction.guild.id, user_id, venceu, foi_mvp)

                if resultado["medalhas_novas"]:
                    medalhas_ganhas_texto.append(
                        f"<@{user_id}>: "
                        f"{', '.join(resultado['medalhas_novas'])}"
                    )

                nova_patente = (
                    await calcular_patente_atual(
                        interaction.guild.id,
                        resultado["perfil"]["xp"],
                    )
                )

                if (
                    nova_patente
                    and nova_patente["nome"]
                    != resultado["patente_antiga"]
                ):
                    await definir_patente(
                        interaction.guild.id,
                        user_id,
                        nova_patente["nome"],
                    )

                    membro = (
                        interaction.guild.get_member(
                            user_id
                        )
                    )

                    cargo_id = nova_patente.get(
                        "cargo_id"
                    )

                    if membro and cargo_id:
                        cargo = (
                            interaction.guild.get_role(
                                cargo_id
                            )
                        )

                        if cargo:
                            try:
                                await membro.add_roles(
                                    cargo,
                                    reason=(
                                        "Promoção automática "
                                        "de patente"
                                    ),
                                )
                            except discord.Forbidden:
                                pass

                    promocoes_texto.append(
                        f"<@{user_id}> → "
                        f"**{nova_patente['nome']}**"
                    )

        empate = vencedor == "Empate"
        await _processar(ids_a, gangue_a, vencedor == gangue_a, empate)
        await _processar(ids_b, gangue_b, vencedor == gangue_b, empate)

        dados = await self._dados_guild(
            interaction.guild.id
        )

        registro = {
            "id": str(uuid.uuid4())[:8],
            "guild_id": interaction.guild.id,
            "gangue_a": gangue_a,
            "gangue_b": gangue_b,
            "placar_a": placar_a,
            "placar_b": placar_b,
            "vencedor": vencedor,
            "mvp_id": mvp.id if mvp else None,
            "prova_url": prova_url.strip() if prova_url else None,
            "formato": formato.strip() if formato else None,
            "servidor": servidor.strip() if servidor else None,
            "arbitro_id": arbitro.id if arbitro else None,
            "participantes_a": ids_a,
            "participantes_b": ids_b,
            "temporada": dados["temporada_atual"],
            "registrado_por_id": interaction.user.id,
            "timestamp": time.time(),
            "status": "finalizada",
        }

        dados["guerras"].append(
            registro
        )

        for agendamento in reversed(
            dados["agendamentos"]
        ):
            if (
                agendamento.get("status")
                == "agendada"
                and agendamento.get("gangue_a", "").lower()
                == gangue_a.lower()
                and agendamento.get("gangue_b", "").lower()
                == gangue_b.lower()
            ):
                agendamento["status"] = "finalizada"
                agendamento["guerra_id"] = registro["id"]
                break

        await self._salvar_dados_guild(
            interaction.guild.id,
            dados,
        )

        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  RESULTADO OFICIAL",
            description=(
                f"**{gangue_a}** {placar_a} x "
                f"{placar_b} **{gangue_b}**\n"
                f"Vencedor: **{vencedor}**"
            ),
            color=0xB51F32,
        )

        if mvp:
            embed.add_field(name="MVP", value=mvp.mention, inline=True)
        if formato:
            embed.add_field(name="Formato", value=formato.strip()[:1024], inline=True)
        if servidor:
            embed.add_field(name="Jogo / servidor", value=servidor.strip()[:1024], inline=True)
        if arbitro:
            embed.add_field(name="Staff responsável", value=arbitro.mention, inline=True)
        if prova_url:
            embed.add_field(name="Prova oficial", value=f"[Abrir evidência]({prova_url.strip()})", inline=False)
        embed.add_field(name="Participantes", value=f"**{gangue_a}:** {len(ids_a)} jogador(es)\n**{gangue_b}:** {len(ids_b)} jogador(es)", inline=False)

        if medalhas_ganhas_texto:
            embed.add_field(
                name="🎖️ Medalhas conquistadas",
                value="\n".join(
                    medalhas_ganhas_texto
                ),
                inline=False,
            )

        if promocoes_texto:
            embed.add_field(
                name="⬆️ Promoções",
                value="\n".join(
                    promocoes_texto
                ),
                inline=False,
            )

        await interaction.followup.send(
            embed=embed
        )

    @app_commands.command(
        name="guerra-historico",
        description="Mostra as últimas guerras registradas.",
    )
    @app_commands.describe(
        gangue="(Opcional) filtra só guerras dessa gangue"
    )
    async def guerra_historico(
        self,
        interaction: discord.Interaction,
        gangue: str = None,
    ):
        dados = await self._dados_guild(
            interaction.guild.id
        )

        guerras = dados["guerras"]

        if gangue:
            guerras = [
                g
                for g in guerras
                if gangue.lower()
                in g["gangue_a"].lower()
                or gangue.lower()
                in g["gangue_b"].lower()
            ]

        guerras = sorted(
            guerras,
            key=lambda g: g.get("timestamp", 0),
            reverse=True,
        )[:10]

        if not guerras:
            await interaction.response.send_message(
                "Nenhuma guerra registrada ainda.",
                ephemeral=True,
            )
            return

        linhas = []
        for g in guerras:
            linha = (
                f"**{g.get('gangue_a', 'Gangue A')}** "
                f"{g.get('placar_a', 0)} x "
                f"{g.get('placar_b', 0)} "
                f"**{g.get('gangue_b', 'Gangue B')}** — "
                f"vencedor: {g.get('vencedor', 'Não informado')} "
                f"(temporada {g.get('temporada', 1)})"
            )
            if g.get("formato"):
                linha += f" · {g['formato']}"
            if g.get("prova_url"):
                linha += f" · [prova]({g['prova_url']})"
            linhas.append(linha)

        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  ARQUIVO DE GUERRAS",
            description="\n".join(linhas),
            color=0xB51F32,
        )

        await interaction.response.send_message(
            embed=embed
        )

    @app_commands.command(
        name="guerra-ranking-gangues",
        description="Mostra o ranking de gangues por resultados oficiais.",
    )
    @app_commands.describe(
        temporada="Filtra uma temporada específica (opcional)",
    )
    async def guerra_ranking_gangues(
        self,
        interaction: discord.Interaction,
        temporada: int = None,
    ):
        dados = await self._dados_guild(interaction.guild.id)
        estatisticas = {}

        for guerra in dados.get("guerras", []):
            if temporada is not None and guerra.get("temporada", 1) != temporada:
                continue
            nome_a = str(guerra.get("gangue_a", "")).strip()
            nome_b = str(guerra.get("gangue_b", "")).strip()
            if not nome_a or not nome_b:
                continue

            chave_a, chave_b = nome_a.casefold(), nome_b.casefold()
            estatisticas.setdefault(chave_a, {"nome": nome_a, "vitorias": 0, "derrotas": 0, "empates": 0, "guerras": 0})
            estatisticas.setdefault(chave_b, {"nome": nome_b, "vitorias": 0, "derrotas": 0, "empates": 0, "guerras": 0})
            a, b = estatisticas[chave_a], estatisticas[chave_b]
            a["guerras"] += 1
            b["guerras"] += 1
            vencedor = str(guerra.get("vencedor", ""))

            if vencedor.casefold() == nome_a.casefold():
                a["vitorias"] += 1
                b["derrotas"] += 1
            elif vencedor.casefold() == nome_b.casefold():
                b["vitorias"] += 1
                a["derrotas"] += 1
            else:
                a["empates"] += 1
                b["empates"] += 1

        ranking = sorted(
            estatisticas.values(),
            key=lambda item: (item["vitorias"], item["empates"], item["guerras"]),
            reverse=True,
        )[:10]

        if not ranking:
            alvo = f" na temporada {temporada}" if temporada is not None else ""
            await interaction.response.send_message(
                f"Nenhuma guerra registrada{alvo}.",
                ephemeral=True,
            )
            return

        linhas = [
            f"**#{i + 1} · {item['nome']}** — {item['vitorias']}V / {item['derrotas']}D / {item['empates']}E · {item['guerras']} guerra(s)"
            for i, item in enumerate(ranking)
        ]
        sufixo = f" · TEMPORADA {temporada}" if temporada is not None else " · GERAL"
        embed = discord.Embed(
            title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ RANKING DE GANGUES{sufixo}",
            description="\\n".join(linhas),
            color=0xB51F32,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="temporada-nova",
        description=(
            "Encerra a temporada atual e começa uma nova "
            "(o histórico não é apagado)."
        ),
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def temporada_nova(
        self,
        interaction: discord.Interaction,
    ):
        dados = await self._dados_guild(
            interaction.guild.id
        )

        dados["temporada_atual"] += 1

        await self._salvar_dados_guild(
            interaction.guild.id,
            dados,
        )

        await interaction.response.send_message(
            f"🆕 Temporada **{dados['temporada_atual']}** começou! "
            "O histórico de temporadas anteriores continua salvo."
        )

    @app_commands.command(
        name="ranking-temporada",
        description="Ranking de vitórias em guerras de uma temporada.",
    )
    @app_commands.describe(
        temporada="Número da temporada (padrão: a atual)"
    )
    async def ranking_temporada(
        self,
        interaction: discord.Interaction,
        temporada: int = None,
    ):
        dados = await self._dados_guild(
            interaction.guild.id
        )

        alvo = (
            temporada
            or dados["temporada_atual"]
        )

        guerras_da_temporada = [
            g
            for g in dados["guerras"]
            if g["temporada"] == alvo
        ]

        contagem = {}

        for guerra in guerras_da_temporada:
            vencedores_ids = (
                guerra["participantes_a"]
                if guerra["vencedor"]
                == guerra["gangue_a"]
                else (
                    guerra["participantes_b"]
                    if guerra["vencedor"]
                    == guerra["gangue_b"]
                    else []
                )
            )

            for uid in vencedores_ids:
                contagem[uid] = (
                    contagem.get(uid, 0) + 1
                )

        if not contagem:
            await interaction.response.send_message(
                f"Nenhum resultado registrado "
                f"na temporada {alvo} ainda.",
                ephemeral=True,
            )
            return

        top = sorted(
            contagem.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        linhas = [
            f"**#{i + 1}** <@{uid}> — "
            f"{vitorias} vitória(s)"
            for i, (uid, vitorias)
            in enumerate(top)
        ]

        embed = discord.Embed(
            title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  GUERRAS / TEMPORADA {alvo}",
            description="\n".join(linhas),
            color=0xB51F32,
        )

        await interaction.response.send_message(
            embed=embed
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(
        Guerras(bot)
    )