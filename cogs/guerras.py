from utils.apresentacao import criar_embed
import re
import time
import uuid
import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar
from utils.guild_config import get_config

ARQUIVO_GUERRAS = "guerras.json"
COR_NEMESIS = 0x9F1239
REGRAS_PADRAO = [
    "Respeitar todos os participantes e a staff.",
    "É proibido usar cheats, exploits ou qualquer vantagem ilegal.",
    "A guerra deve seguir o formato combinado antes do início.",
    "O resultado deve ter prova válida quando a staff solicitar.",
    "É proibido falsificar placares ou provas.",
    "A staff pode anular resultados com evidências de irregularidades.",
]


def _inteiro_seguro(valor, padrao=0):
    try:
        return int(valor)
    except (TypeError, ValueError, OverflowError):
        return padrao


def _resultado(placar_nemesis: int, placar_inimiga: int) -> str:
    if placar_nemesis > placar_inimiga:
        return "VITÓRIA DA NÊMESIS"
    if placar_nemesis < placar_inimiga:
        return "DERROTA DA NÊMESIS"
    return "EMPATE"


class Guerras(commands.GroupCog, group_name="guerra", group_description="Guerras oficiais da NÊMESIS"):
    """Sistema oficial de registro, regras e histórico de guerras da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _dados_guild(self, guild_id: int) -> dict:
        todos = await carregar(ARQUIVO_GUERRAS, {})
        if not isinstance(todos, dict):
            todos = {}
        dados = todos.get(str(guild_id), {})
        if not isinstance(dados, dict):
            dados = {}
        guerras = dados.get("guerras", [])
        agendamentos = dados.get("agendamentos", [])
        regras = dados.get("regras", REGRAS_PADRAO.copy())
        dados["guild_id"] = guild_id
        dados["temporada_atual"] = max(1, _inteiro_seguro(dados.get("temporada_atual", 1), 1))
        dados["guerras"] = [item for item in guerras if isinstance(item, dict)] if isinstance(guerras, list) else []
        dados["agendamentos"] = [item for item in agendamentos if isinstance(item, dict)] if isinstance(agendamentos, list) else []
        dados["regras"] = [str(item).strip() for item in regras if item is not None and str(item).strip()] if isinstance(regras, list) else REGRAS_PADRAO.copy()
        return dados

    async def _salvar_dados_guild(self, guild_id: int, dados: dict):
        todos = await carregar(ARQUIVO_GUERRAS, {})
        if not isinstance(todos, dict):
            todos = {}
        if not isinstance(dados, dict):
            dados = {}
        dados["guild_id"] = guild_id
        dados["temporada_atual"] = max(1, _inteiro_seguro(dados.get("temporada_atual", 1), 1))
        for campo in ("guerras", "agendamentos"):
            valor = dados.get(campo, [])
            dados[campo] = [item for item in valor if isinstance(item, dict)] if isinstance(valor, list) else []
        regras = dados.get("regras", REGRAS_PADRAO.copy())
        dados["regras"] = [str(item) for item in regras if str(item).strip()] if isinstance(regras, list) else REGRAS_PADRAO.copy()
        todos[str(guild_id)] = dados
        await salvar(ARQUIVO_GUERRAS, todos)

    async def _canal_guerras(self, interaction: discord.Interaction):
        config = await get_config(interaction.guild.id)
        canal_id = config.get("canal_guerras_id")
        canal = interaction.guild.get_channel(canal_id) if canal_id else None
        return canal or interaction.channel

    def _embed_regras(self, regras: list) -> discord.Embed:
        linhas = [f"**{i}.** {regra}" for i, regra in enumerate(regras, 1)]
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ REGRAS OFICIAIS DE GUERRA",
            description="\n".join(linhas)[:4000],
            color=COR_NEMESIS,
        )
        embed.set_footer(text="As regras oficiais se aplicam a todos os confrontos.")
        return embed

    @app_commands.command(
        name="registrar",
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

        embed = criar_embed(
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
        regras_atuais = dados.get("regras") or REGRAS_PADRAO
        regras_no_relatorio = "\n".join(
            f"{i}. {regra}" for i, regra in enumerate(regras_atuais, 1)
        )[:1000]
        embed.add_field(
            name="REGRAS APLICÁVEIS",
            value=regras_no_relatorio or "Consulte /guerra-regras.",
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
        name="regras",
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
        name="regras-definir",
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
        name="historico",
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
            resultado = "EM ANDAMENTO" if guerra.get("status") == "ativa" else ("CANCELADA" if guerra.get("status") == "cancelada" else (guerra.get("resultado") or _resultado(int(pn), int(pi))))
            linha = f"**{guerra.get('id', 'SEM-ID')}** · **NÊMESIS {pn} × {pi} {discord.utils.escape_markdown(inimiga)}** — {resultado}"
            if guerra.get("prova_url"):
                linha += f" · [prova]({guerra['prova_url']})"
            linhas.append(linha)

        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ HISTÓRICO DE GUERRAS",
            description="\n".join(linhas)[:4000],
            color=COR_NEMESIS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="ranking-gangues",
        description="Mostra o desempenho da NÊMESIS contra cada gangue registrada.",
    )
    async def guerra_ranking_gangues(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        dados = await self._dados_guild(interaction.guild.id)
        stats = {}
        for guerra in dados.get("guerras", []):
            if guerra.get("status") in {"ativa", "cancelada"}:
                continue
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
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ DESEMPENHO POR GANGUE",
            description="\n".join(linhas),
            color=COR_NEMESIS,
        )
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="iniciar", description="Abre uma guerra e permite acompanhar o placar até o encerramento.")
    @app_commands.describe(gangue_inimiga="Nome da gangue adversária", formato="Formato combinado", observacoes="Observações iniciais")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def guerra_iniciar(self, interaction: discord.Interaction, gangue_inimiga: str, formato: str = None, observacoes: str = None):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        nome = gangue_inimiga.strip()
        if not nome or len(nome) > 80 or nome.casefold() in {"nêmesis", "nemesis", "n̷êmesis"}:
            await interaction.response.send_message("Informe uma gangue adversária válida, com até 80 caracteres.", ephemeral=True)
            return
        if formato and len(formato.strip()) > 100:
            await interaction.response.send_message("O formato pode ter até 100 caracteres.", ephemeral=True)
            return
        if observacoes and len(observacoes.strip()) > 800:
            await interaction.response.send_message("As observações podem ter até 800 caracteres.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = await self._dados_guild(interaction.guild.id)
        ativa = next((g for g in dados["guerras"] if g.get("status") == "ativa" and str(g.get("gangue_inimiga", "")).casefold() == nome.casefold()), None)
        if ativa:
            await interaction.followup.send(f"Já existe uma guerra ativa contra {discord.utils.escape_markdown(nome)} (código {ativa.get('id')}).", ephemeral=True)
            return
        codigo, agora = uuid.uuid4().hex[:8].upper(), time.time()
        registro = {
            "id": codigo, "guild_id": interaction.guild.id, "gangue_a": "NÊMESIS",
            "gangue_b": nome, "gangue_inimiga": nome, "placar_a": 0, "placar_b": 0,
            "placar_nemesis": 0, "placar_inimiga": 0, "resultado": "EM ANDAMENTO",
            "vencedor": None, "prova_url": None, "formato": formato.strip()[:100] if formato else None,
            "observacoes": observacoes.strip()[:800] if observacoes else None,
            "temporada": dados.get("temporada_atual", 1), "registrado_por_id": interaction.user.id,
            "timestamp": agora, "iniciado_em": agora, "status": "ativa",
        }
        dados["guerras"].append(registro)
        await self._salvar_dados_guild(interaction.guild.id, dados)
        embed = criar_embed(
            title="⚔️ GUERRA OFICIAL · CONFRONTO INICIADO",
            description="**A OPERAÇÃO COMPETITIVA ESTÁ ATIVA**\nO placar será atualizado neste registro até o encerramento oficial.",
            color=COR_NEMESIS, timestamp=discord.utils.utcnow(), rodape=None,
        )
        embed.set_author(name="NÊMESIS  /  COMANDO DE GUERRA")
        embed.add_field(name="NÊMESIS", value="**0** pontos", inline=True)
        embed.add_field(name="ADVERSÁRIA", value=f"**{discord.utils.escape_markdown(nome)[:100]}**\n**0** pontos", inline=True)
        embed.add_field(name="ESTADO", value="🟢 EM ANDAMENTO", inline=True)
        embed.add_field(name="CÓDIGO OPERACIONAL", value=f"`{codigo}`", inline=True)
        if formato:
            embed.add_field(name="FORMATO", value=discord.utils.escape_markdown(formato.strip()[:100]), inline=True)
        if observacoes:
            embed.add_field(name="OBSERVAÇÕES", value=discord.utils.escape_markdown(observacoes.strip()[:800]), inline=False)
        embed.set_footer(text=f"Temporada {registro['temporada']} • Aberta por {interaction.user}")
        canal = await self._canal_guerras(interaction)
        try:
            mensagem = await canal.send(embed=embed)
            registro["mensagem_id"], registro["canal_id"] = mensagem.id, canal.id
            await self._salvar_dados_guild(interaction.guild.id, dados)
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(f"A guerra {codigo} foi salva, mas não consegui publicar no canal. Confira as permissões do bot.", ephemeral=True)
            return
        await interaction.followup.send(f"Guerra aberta contra **{discord.utils.escape_markdown(nome)}**. Código: **{codigo}**. Use /guerra-placar para atualizar e /guerra-encerrar ao finalizar.", ephemeral=True)

    @app_commands.command(name="placar", description="Atualiza o placar de uma guerra em andamento.")
    @app_commands.describe(codigo="Código da guerra ativa", placar_nemesis="Placar atual da NÊMESIS", placar_inimiga="Placar atual da gangue adversária", observacoes="Observação opcional")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def guerra_placar(self, interaction: discord.Interaction, codigo: str, placar_nemesis: app_commands.Range[int, 0, 9999], placar_inimiga: app_commands.Range[int, 0, 9999], observacoes: str = None):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        if observacoes and len(observacoes.strip()) > 500:
            await interaction.response.send_message("A observação pode ter até 500 caracteres.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = await self._dados_guild(interaction.guild.id)
        registro = next((g for g in dados["guerras"] if str(g.get("id", "")).upper() == codigo.strip().upper()), None)
        if not registro:
            await interaction.followup.send("Não encontrei uma guerra com esse código.", ephemeral=True)
            return
        if registro.get("status") != "ativa":
            await interaction.followup.send("Essa guerra não está ativa. O placar não foi alterado.", ephemeral=True)
            return
        registro["placar_a"] = registro["placar_nemesis"] = int(placar_nemesis)
        registro["placar_b"] = registro["placar_inimiga"] = int(placar_inimiga)
        registro["resultado"] = "EM ANDAMENTO"
        registro["atualizado_em"] = time.time()
        if observacoes and observacoes.strip():
            registro["ultima_observacao"] = observacoes.strip()[:500]
        historico_placar = registro.setdefault("historico_placar", [])
        historico_placar.append({
            "placar_nemesis": int(placar_nemesis),
            "placar_inimiga": int(placar_inimiga),
            "observacao": observacoes.strip()[:500] if observacoes and observacoes.strip() else None,
            "atualizado_por_id": interaction.user.id,
            "timestamp": registro["atualizado_em"],
        })
        registro["historico_placar"] = historico_placar[-100:]
        await self._salvar_dados_guild(interaction.guild.id, dados)
        nome = registro.get("gangue_inimiga", registro.get("gangue_b", "Gangue desconhecida"))
        embed = criar_embed(
            title="📊 GUERRA OFICIAL · ATUALIZAÇÃO DE PLACAR",
            description="O registro da guerra foi atualizado. O histórico das alterações continua preservado.",
            color=COR_NEMESIS, timestamp=discord.utils.utcnow(), rodape=None,
        )
        embed.set_author(name="NÊMESIS  /  COMANDO DE GUERRA")
        embed.add_field(name="NÊMESIS", value=f"**{placar_nemesis}** pontos", inline=True)
        embed.add_field(name="ADVERSÁRIA", value=f"**{discord.utils.escape_markdown(nome)[:100]}**\n**{placar_inimiga}** pontos", inline=True)
        embed.add_field(name="ESTADO", value="🟢 EM ANDAMENTO", inline=True)
        embed.add_field(name="CÓDIGO OPERACIONAL", value=f"`{registro['id']}`", inline=True)
        if registro.get("formato"):
            embed.add_field(name="FORMATO", value=discord.utils.escape_markdown(registro["formato"]), inline=True)
        if registro.get("ultima_observacao"):
            embed.add_field(name="ATUALIZAÇÃO", value=discord.utils.escape_markdown(registro["ultima_observacao"]), inline=False)
        embed.set_footer(text=f"Atualizado por {interaction.user} • Temporada {registro.get('temporada', 1)}")
        canal = await self._canal_guerras(interaction)
        try:
            mensagem = None
            if registro.get("mensagem_id") and str(registro.get("canal_id")) == str(canal.id):
                try:
                    mensagem = await canal.fetch_message(int(registro["mensagem_id"]))
                except discord.NotFound:
                    mensagem = None
            if mensagem is not None:
                await mensagem.edit(embed=embed)
            else:
                mensagem = await canal.send(embed=embed)
                registro["mensagem_id"] = mensagem.id
                registro["canal_id"] = canal.id
            registro["ultima_mensagem_id"] = mensagem.id
            await self._salvar_dados_guild(interaction.guild.id, dados)
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("Placar salvo no histórico, mas não consegui atualizar o painel da guerra.", ephemeral=True)
            return
        await interaction.followup.send(f"Placar da guerra {registro['id']} atualizado. O histórico das alterações foi preservado.", ephemeral=True)

    @app_commands.command(name="encerrar", description="Encerra uma guerra ativa e publica o resultado definitivo.")
    @app_commands.describe(codigo="Código da guerra ativa", placar_nemesis="Placar final da NÊMESIS", placar_inimiga="Placar final da gangue adversária", prova_url="Link da prova (opcional)", observacoes="Observações finais (opcional)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def guerra_encerrar(self, interaction: discord.Interaction, codigo: str, placar_nemesis: app_commands.Range[int, 0, 9999], placar_inimiga: app_commands.Range[int, 0, 9999], prova_url: str = None, observacoes: str = None):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        if prova_url and not re.match(r"^https?://\S+$", prova_url.strip(), re.IGNORECASE):
            await interaction.response.send_message("O link da prova precisa começar com http:// ou https://.", ephemeral=True)
            return
        if observacoes and len(observacoes.strip()) > 800:
            await interaction.response.send_message("As observações podem ter até 800 caracteres.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = await self._dados_guild(interaction.guild.id)
        registro = next((g for g in dados["guerras"] if str(g.get("id", "")).upper() == codigo.strip().upper()), None)
        if not registro:
            await interaction.followup.send("Não encontrei uma guerra com esse código.", ephemeral=True)
            return
        if registro.get("status") != "ativa":
            await interaction.followup.send("Essa guerra já foi encerrada ou não está ativa.", ephemeral=True)
            return
        resultado = _resultado(int(placar_nemesis), int(placar_inimiga))
        nome = registro.get("gangue_inimiga", registro.get("gangue_b", "Gangue desconhecida"))
        registro["placar_a"] = registro["placar_nemesis"] = int(placar_nemesis)
        registro["placar_b"] = registro["placar_inimiga"] = int(placar_inimiga)
        registro["resultado"] = resultado
        registro["vencedor"] = "NÊMESIS" if placar_nemesis > placar_inimiga else (nome if placar_inimiga > placar_nemesis else "Empate")
        registro["prova_url"] = prova_url.strip() if prova_url else registro.get("prova_url")
        if observacoes and observacoes.strip():
            registro["observacoes_finais"] = observacoes.strip()[:800]
        registro["status"], registro["encerrado_em"], registro["encerrado_por_id"] = "finalizada", time.time(), interaction.user.id
        await self._salvar_dados_guild(interaction.guild.id, dados)
        embed = criar_embed(
            title="🏁 GUERRA OFICIAL · RESULTADO DEFINITIVO",
            description=f"**RESULTADO FINAL: {resultado}**\nO registro foi encerrado e permanece disponível no histórico competitivo.",
            color=COR_NEMESIS if placar_nemesis >= placar_inimiga else 0x555555,
            timestamp=discord.utils.utcnow(), rodape=None,
        )
        embed.set_author(name="NÊMESIS  /  ARQUIVO DE CONFRONTOS")
        embed.add_field(name="NÊMESIS", value=f"**{placar_nemesis}** pontos", inline=True)
        embed.add_field(name="ADVERSÁRIA", value=f"**{discord.utils.escape_markdown(nome)[:100]}**\n**{placar_inimiga}** pontos", inline=True)
        embed.add_field(name="VENCEDOR", value=f"**{discord.utils.escape_markdown(registro['vencedor'])[:150]}**", inline=False)
        embed.add_field(name="CÓDIGO OPERACIONAL", value=f"`{registro['id']}`", inline=True)
        if registro.get("formato"):
            embed.add_field(name="FORMATO", value=discord.utils.escape_markdown(registro["formato"]), inline=True)
        if registro.get("prova_url"):
            embed.add_field(name="PROVA DO RESULTADO", value=f"[Abrir evidência]({registro['prova_url']})", inline=False)
        if registro.get("observacoes_finais"):
            embed.add_field(name="OBSERVAÇÕES FINAIS", value=discord.utils.escape_markdown(registro["observacoes_finais"]), inline=False)
        regras = dados.get("regras") or REGRAS_PADRAO
        embed.add_field(name="REGRAS APLICÁVEIS", value="\n".join(f"{i}. {regra}" for i, regra in enumerate(regras, 1))[:1000], inline=False)
        embed.set_footer(text=f"Encerrada por {interaction.user} • Temporada {registro.get('temporada', 1)}")
        canal = await self._canal_guerras(interaction)
        try:
            mensagem = None
            if registro.get("mensagem_id") and str(registro.get("canal_id")) == str(canal.id):
                try:
                    mensagem = await canal.fetch_message(int(registro["mensagem_id"]))
                except discord.NotFound:
                    mensagem = None

            # Mantém um único painel por guerra: o encerramento substitui
            # a mensagem de placar, em vez de deixar um painel antigo ativo.
            if mensagem is not None:
                await mensagem.edit(embed=embed)
            else:
                mensagem = await canal.send(embed=embed)

            registro["mensagem_id"] = mensagem.id
            registro["mensagem_final_id"] = mensagem.id
            registro["canal_id"] = canal.id
            await self._salvar_dados_guild(interaction.guild.id, dados)
        except (discord.Forbidden, discord.HTTPException):
            # Se o relatório não puder ser publicado, reabre o registro para permitir nova tentativa.
            registro["status"] = "ativa"
            registro["resultado"] = "EM ANDAMENTO"
            registro["vencedor"] = None
            registro.pop("encerrado_em", None)
            registro.pop("encerrado_por_id", None)
            registro.pop("mensagem_final_id", None)
            await self._salvar_dados_guild(interaction.guild.id, dados)
            await interaction.followup.send("Não consegui publicar o relatório final. A guerra foi mantida como ativa para que a staff possa tentar encerrar novamente.", ephemeral=True)
            return
        await interaction.followup.send(f"Guerra {registro['id']} encerrada. Resultado: **{resultado}**.", ephemeral=True)

    @app_commands.command(name="em-andamento", description="Lista os confrontos que ainda estão ativos.")
    async def guerra_em_andamento(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        dados = await self._dados_guild(interaction.guild.id)
        ativas = [g for g in dados.get("guerras", []) if g.get("status") == "ativa"]
        ativas.sort(key=lambda g: g.get("iniciado_em", g.get("timestamp", 0)))
        if not ativas:
            await interaction.response.send_message("Não há guerras em andamento.", ephemeral=True)
            return
        linhas = []
        for guerra in ativas[:15]:
            nome = guerra.get("gangue_inimiga", guerra.get("gangue_b", "Gangue desconhecida"))
            pn = guerra.get("placar_nemesis", guerra.get("placar_a", 0))
            pi = guerra.get("placar_inimiga", guerra.get("placar_b", 0))
            linhas.append(f"**{guerra.get('id', 'SEM-ID')}** — NÊMESIS **{pn} × {pi}** **{discord.utils.escape_markdown(nome)}**")
        embed = criar_embed(title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ GUERRAS EM ANDAMENTO", description="\n".join(linhas), color=COR_NEMESIS)
        embed.set_footer(text=f"{len(ativas)} guerra(s) ativa(s)")
        await interaction.response.send_message(embed=embed, ephemeral=True)


    @app_commands.command(name="cancelar", description="Cancela uma guerra ativa sem apagar o registro do histórico.")
    @app_commands.describe(codigo="Código da guerra ativa", motivo="Motivo do cancelamento")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def guerra_cancelar(self, interaction: discord.Interaction, codigo: str, motivo: str):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando no servidor.", ephemeral=True)
            return
        motivo = motivo.strip()
        if not motivo or len(motivo) > 500:
            await interaction.response.send_message("Informe um motivo de até 500 caracteres.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        dados = await self._dados_guild(interaction.guild.id)
        registro = next((g for g in dados.get("guerras", []) if str(g.get("id", "")).upper() == codigo.strip().upper()), None)
        if not registro:
            await interaction.followup.send("Não encontrei uma guerra com esse código.", ephemeral=True)
            return
        if registro.get("status") != "ativa":
            await interaction.followup.send("Só é possível cancelar guerras em andamento.", ephemeral=True)
            return
        registro["status"] = "cancelada"
        registro["resultado"] = "CANCELADA"
        registro["motivo_cancelamento"] = motivo
        registro["cancelada_em"] = time.time()
        registro["cancelada_por_id"] = interaction.user.id
        await self._salvar_dados_guild(interaction.guild.id, dados)
        nome = registro.get("gangue_inimiga", registro.get("gangue_b", "Gangue desconhecida"))
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ GUERRA CANCELADA",
            description=f"Confronto contra **{discord.utils.escape_markdown(nome)}** cancelado.\nCódigo: **{registro['id']}**\nMotivo: {discord.utils.escape_markdown(motivo)}",
            color=0x777777, timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text=f"Cancelada por {interaction.user}")
        canal = await self._canal_guerras(interaction)
        try:
            mensagem = None
            if registro.get("mensagem_id") and str(registro.get("canal_id")) == str(canal.id):
                try:
                    mensagem = await canal.fetch_message(int(registro["mensagem_id"]))
                except discord.NotFound:
                    mensagem = None

            # O painel é atualizado no próprio lugar, evitando mostrar uma
            # guerra cancelada junto de uma mensagem antiga ainda ativa.
            if mensagem is not None:
                await mensagem.edit(embed=embed)
            else:
                mensagem = await canal.send(embed=embed)

            registro["mensagem_id"] = mensagem.id
            registro["canal_id"] = canal.id
            await self._salvar_dados_guild(interaction.guild.id, dados)
        except (discord.Forbidden, discord.HTTPException):
            await interaction.followup.send("Guerra cancelada no histórico, mas não consegui atualizar/publicar o painel.", ephemeral=True)
            return
        await interaction.followup.send(f"Guerra {registro['id']} cancelada. O registro foi preservado para auditoria.", ephemeral=True)

    @app_commands.command(
        name="remover",
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
