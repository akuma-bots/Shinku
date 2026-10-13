import re
import time
import uuid
import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar
from utils.guild_config import get_config

ARQUIVO_GUERRAS = "guerras.json"
COR_NEMESIS = 0xB51F32
REGRAS_PADRAO = [
    "Respeitar todos os participantes e a staff.",
    "É proibido usar cheats, exploits ou qualquer vantagem ilegal.",
    "A guerra deve seguir o formato combinado antes do início.",
    "O resultado deve ter prova válida quando a staff solicitar.",
    "É proibido falsificar placares ou provas.",
    "A staff pode anular resultados com evidências de irregularidades.",
]


def _resultado(placar_nemesis: int, placar_inimiga: int) -> str:
    if placar_nemesis > placar_inimiga:
        return "VITÓRIA DA NÊMESIS"
    if placar_nemesis < placar_inimiga:
        return "DERROTA DA NÊMESIS"
    return "EMPATE"


class Guerras(commands.Cog):
    """Sistema oficial de registro, regras e histórico de guerras da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _dados_guild(self, guild_id: int) -> dict:
        todos = await carregar(ARQUIVO_GUERRAS, {})
        dados = todos.get(str(guild_id), {})
        dados.setdefault("guild_id", guild_id)
        dados.setdefault("temporada_atual", 1)
        dados.setdefault("guerras", [])
        dados.setdefault("agendamentos", [])
        dados.setdefault("regras", REGRAS_PADRAO.copy())
        return dados

    async def _salvar_dados_guild(self, guild_id: int, dados: dict):
        todos = await carregar(ARQUIVO_GUERRAS, {})
        dados["guild_id"] = guild_id
        dados.setdefault("temporada_atual", 1)
        dados.setdefault("guerras", [])
        dados.setdefault("agendamentos", [])
        dados.setdefault("regras", REGRAS_PADRAO.copy())
        todos[str(guild_id)] = dados
        await salvar(ARQUIVO_GUERRAS, todos)

    async def _canal_guerras(self, interaction: discord.Interaction):
        config = await get_config(interaction.guild.id)
        canal_id = config.get("canal_guerras_id")
        canal = interaction.guild.get_channel(canal_id) if canal_id else None
        return canal or interaction.channel

    def _embed_regras(self, regras: list) -> discord.Embed:
        linhas = [f"**{i}.** {regra}" for i, regra in enumerate(regras, 1)]
        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ REGRAS OFICIAIS DE GUERRA",
            description="\n".join(linhas)[:4000],
            color=COR_NEMESIS,
        )
        embed.set_footer(text="As regras oficiais se aplicam a todos os confrontos.")
        return embed

    @app_commands.command(
        name="guerra-registrar",
        description="Registra o placar oficial da NÊMESIS contra uma gangue inimiga.",
    )
    @app_commands.describe(
        gangue_inimiga="Nome da gangue que enfrentou a NÊMESIS",
        placar_nemesis="Placar conquistado pela NÊMESIS",
        placar_inimiga="Placar conquistado pela gangue inimiga",
        prova_url="Link da prova ou print do resultado (opcional)",
        formato="Formato disputado, por exemplo 5v5 MD3 (opcional)",
        observacoes="Observações oficiais sobre o confronto (opcional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def guerra_registrar(
        self,
        interaction: discord.Interaction,
        gangue_inimiga: str,
        placar_nemesis: app_commands.Range[int, 0, 9999],
        placar_inimiga: app_commands.Range[int, 0, 9999],
        prova_url: str = None,
        formato: str = None,
        observacoes: str = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Este comando só pode ser usado dentro do servidor.", ephemeral=True
            )
            return

        gangue_inimiga = gangue_inimiga.strip()
        if not gangue_inimiga or len(gangue_inimiga) > 80:
            await interaction.response.send_message(
                "Informe o nome da gangue inimiga (até 80 caracteres).", ephemeral=True
            )
            return
        if gangue_inimiga.casefold() in {"nêmesis", "nemesis", "n̷êmesis"}:
            await interaction.response.send_message(
                "A gangue inimiga não pode ser a própria NÊMESIS.", ephemeral=True
            )
            return
        if prova_url and not re.match(r"^https?://\S+$", prova_url.strip(), re.IGNORECASE):
            await interaction.response.send_message(
                "O link da prova precisa começar com http:// ou https://.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = await self._dados_guild(interaction.guild.id)
        registro_id = uuid.uuid4().hex[:8].upper()
        status = _resultado(placar_nemesis, placar_inimiga)
        registro = {
            "id": registro_id,
            "guild_id": interaction.guild.id,
            "gangue_a": "NÊMESIS",
            "gangue_b": gangue_inimiga,
            "gangue_inimiga": gangue_inimiga,
            "placar_a": int(placar_nemesis),
            "placar_b": int(placar_inimiga),
            "placar_nemesis": int(placar_nemesis),
            "placar_inimiga": int(placar_inimiga),
            "vencedor": "NÊMESIS" if placar_nemesis > placar_inimiga else (
                gangue_inimiga if placar_inimiga > placar_nemesis else "Empate"
            ),
            "resultado": status,
            "prova_url": prova_url.strip() if prova_url else None,
            "formato": formato.strip()[:100] if formato else None,
            "observacoes": observacoes.strip()[:800] if observacoes else None,
            "temporada": dados.get("temporada_atual", 1),
            "registrado_por_id": interaction.user.id,
            "timestamp": time.time(),
            "status": "finalizada",
        }
        dados["guerras"].append(registro)
        await self._salvar_dados_guild(interaction.guild.id, dados)

        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ RELATÓRIO OFICIAL DE GUERRA",
            description=(
                f"**NÊMESIS**  **{placar_nemesis} × {placar_inimiga}**  "
                f"**{discord.utils.escape_markdown(gangue_inimiga)}**\n\n"
                f"**RESULTADO: {status}**"
            ),
            color=COR_NEMESIS if placar_nemesis >= placar_inimiga else 0x555555,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="CÓDIGO", value=f"**{registro_id}**", inline=True)
        embed.add_field(name="TEMPORADA", value=str(registro["temporada"]), inline=True)
        if formato:
            embed.add_field(name="FORMATO", value=discord.utils.escape_markdown(formato[:100]), inline=True)
        if observacoes:
            embed.add_field(name="OBSERVAÇÕES", value=discord.utils.escape_markdown(observacoes[:800]), inline=False)
        if prova_url:
            embed.add_field(name="PROVA DO RESULTADO", value=f"[Abrir evidência]({prova_url.strip()})", inline=False)
        embed.add_field(
            name="REGRAS APLICÁVEIS",
            value="As regras oficiais de guerra da NÊMESIS se aplicam a este registro. Use /guerra-regras para consultá-las.",
            inline=False,
        )
        embed.set_footer(text=f"Registrado por {interaction.user} • NÊMESIS")

        canal = await self._canal_guerras(interaction)
        try:
            mensagem = await canal.send(embed=embed)
            registro["mensagem_id"] = mensagem.id
            registro["canal_id"] = canal.id
            await self._salvar_dados_guild(interaction.guild.id, dados)
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(
                "O resultado foi salvo no histórico, mas não consegui publicar no canal de guerras. Verifique as permissões do bot.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"Registro {registro_id} salvo e publicado em {canal.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="guerra-regras",
        description="Mostra as regras oficiais para guerras da NÊMESIS.",
    )
    async def guerra_regras(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        dados = await self._dados_guild(interaction.guild.id)
        await interaction.response.send_message(
            embed=self._embed_regras(dados.get("regras") or REGRAS_PADRAO)
        )

    @app_commands.command(
        name="guerra-regras-definir",
        description="Define as regras oficiais de guerra (staff).",
    )
    @app_commands.describe(
        regra_1="Regra principal",
        regra_2="Segunda regra (opcional)",
        regra_3="Terceira regra (opcional)",
        regra_4="Quarta regra (opcional)",
        regra_5="Quinta regra (opcional)",
        regra_6="Sexta regra (opcional)",
        regra_7="Sétima regra (opcional)",
        regra_8="Oitava regra (opcional)",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def guerra_regras_definir(
        self,
        interaction: discord.Interaction,
        regra_1: str,
        regra_2: str = None,
        regra_3: str = None,
        regra_4: str = None,
        regra_5: str = None,
        regra_6: str = None,
        regra_7: str = None,
        regra_8: str = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        regras = []
        for regra in (regra_1, regra_2, regra_3, regra_4, regra_5, regra_6, regra_7, regra_8):
            if regra and regra.strip():
                texto = regra.strip()
                if len(texto) > 350:
                    await interaction.response.send_message(
                        "Cada regra pode ter no máximo 350 caracteres.", ephemeral=True
                    )
                    return
                regras.append(texto)
        if not regras:
            await interaction.response.send_message("Informe pelo menos uma regra.", ephemeral=True)
            return
        dados = await self._dados_guild(interaction.guild.id)
        dados["regras"] = regras
        await self._salvar_dados_guild(interaction.guild.id, dados)
        await interaction.response.send_message(
            "Regras oficiais de guerra atualizadas.", ephemeral=True
        )

    @app_commands.command(
        name="guerra-historico",
        description="Mostra os registros recentes de guerras da NÊMESIS.",
    )
    @app_commands.describe(gangue="Filtra pelo nome da gangue adversária (opcional)")
    async def guerra_historico(
        self,
        interaction: discord.Interaction,
        gangue: str = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        dados = await self._dados_guild(interaction.guild.id)
        guerras = dados.get("guerras", [])
        if gangue:
            termo = gangue.casefold()
            guerras = [
                guerra for guerra in guerras
                if termo in str(guerra.get("gangue_inimiga", guerra.get("gangue_b", ""))).casefold()
            ]
        guerras = sorted(guerras, key=lambda guerra: guerra.get("timestamp", 0), reverse=True)[:10]
        if not guerras:
            await interaction.response.send_message("Nenhuma guerra encontrada.", ephemeral=True)
            return

        linhas = []
        for guerra in guerras:
            inimiga = guerra.get("gangue_inimiga", guerra.get("gangue_b", "Gangue desconhecida"))
            pn = guerra.get("placar_nemesis", guerra.get("placar_a", 0))
            pi = guerra.get("placar_inimiga", guerra.get("placar_b", 0))
            resultado = guerra.get("resultado") or _resultado(int(pn), int(pi))
            linha = f"**{guerra.get('id', 'SEM-ID')}** · **NÊMESIS {pn} × {pi} {discord.utils.escape_markdown(inimiga)}** — {resultado}"
            if guerra.get("prova_url"):
                linha += f" · [prova]({guerra['prova_url']})"
            linhas.append(linha)

        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ HISTÓRICO DE GUERRAS",
            description="\n".join(linhas)[:4000],
            color=COR_NEMESIS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="guerra-ranking-gangues",
        description="Mostra o desempenho da NÊMESIS contra cada gangue registrada.",
    )
    async def guerra_ranking_gangues(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        dados = await self._dados_guild(interaction.guild.id)
        stats = {}
        for guerra in dados.get("guerras", []):
            nome = str(guerra.get("gangue_inimiga", guerra.get("gangue_b", ""))).strip()
            if not nome:
                continue
            item = stats.setdefault(nome.casefold(), {
                "nome": nome, "vitorias": 0, "derrotas": 0, "empates": 0, "jogos": 0
            })
            item["jogos"] += 1
            resultado = guerra.get("resultado") or _resultado(
                int(guerra.get("placar_nemesis", guerra.get("placar_a", 0))),
                int(guerra.get("placar_inimiga", guerra.get("placar_b", 0))),
            )
            if resultado == "VITÓRIA DA NÊMESIS":
                item["vitorias"] += 1
            elif resultado == "DERROTA DA NÊMESIS":
                item["derrotas"] += 1
            else:
                item["empates"] += 1

        ranking = sorted(
            stats.values(),
            key=lambda item: (item["vitorias"], -item["derrotas"], item["empates"]),
            reverse=True,
        )[:10]
        if not ranking:
            await interaction.response.send_message("Ainda não há guerras suficientes para montar o ranking.", ephemeral=True)
            return
        linhas = [
            f"**#{i}. {discord.utils.escape_markdown(item['nome'])}** — {item['vitorias']}V / {item['derrotas']}D / {item['empates']}E · {item['jogos']} confronto(s)"
            for i, item in enumerate(ranking, 1)
        ]
        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ DESEMPENHO POR GANGUE",
            description="\n".join(linhas),
            color=COR_NEMESIS,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="guerra-remover",
        description="Remove do histórico um registro de guerra incorreto (staff).",
    )
    @app_commands.describe(codigo="Código exibido no registro oficial")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def guerra_remover(self, interaction: discord.Interaction, codigo: str):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        dados = await self._dados_guild(interaction.guild.id)
        codigo = codigo.strip().upper()
        guerras = dados.get("guerras", [])
        alvo = next((g for g in guerras if str(g.get("id", "")).upper() == codigo), None)
        if alvo is None:
            await interaction.response.send_message("Não encontrei uma guerra com esse código.", ephemeral=True)
            return
        guerras.remove(alvo)
        await self._salvar_dados_guild(interaction.guild.id, dados)
        await interaction.response.send_message(
            f"Registro {codigo} removido do histórico. A mensagem publicada no canal não é apagada.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Guerras(bot))
