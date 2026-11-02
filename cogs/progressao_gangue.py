from utils.apresentacao import criar_embed
import time
import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar
from utils.guild_config import octogono_only, hierarquia_only, membro_pode_gerenciar_membro, membro_pode_atribuir_cargo_hierarquico, CARGOS_RESERVADOS_PROGRESSAO_IDS, CARGO_ELITE_ID

log = logging.getLogger(__name__)

GUILD_ID = 1563995879981981817
CANAL_PROGRESSAO_ID = 1563995881315897548
CANAL_REGISTRO_ATIVIDADE_ID = 1545833111860936804
CARGO_NEMESIS_ID = 1563995879990624372
ARQUIVO = "progressao_gangue.json"
COOLDOWN_MENSAGENS = 60
XP_POR_MENSAGEM = 2

RANKS = [
    {"no": 12, "nome": "Lutador", "xp": 0},
    {"no": 11, "nome": "Subtenente", "xp": 800},
    {"no": 10, "nome": "Tenente", "xp": 2200},
    {"no": 9, "nome": "Executor", "xp": 4500},
    {"no": 8, "nome": "Especialista", "xp": 7500},
    {"no": 7, "nome": "Elite", "xp": 11500},
    {"no": 6, "nome": "Veterano", "xp": 16500},
    {"no": 5, "nome": "Treinador", "xp": 23000},
    {"no": 4, "nome": "Comandante", "xp": 31000},
    {"no": 3, "nome": "Vice Capitão", "xp": 41000},
    {"no": 2, "nome": "Capitão", "xp": 54000},
    {"no": 1, "nome": "Capitão Geral", "xp": 70000},
]

CARGOS_PROGRESSAO_PADRAO = {
    "12": 1563995879990624373,  # Lutador
    "11": 1563995879990624374,  # Subtenente
    "10": 1563995879990624375,  # Tenente
    "9": 1563995879990624376,   # Executor
    "8": 1563995879990624377,   # Especialista
    "7": CARGO_ELITE_ID,            # Elite
    "6": 1563995879998754938,   # Veterano
    "5": 1563995879998754939,   # Treinador
    "4": 1563995879998754940,   # Comandante
    "3": 1563995879998754941,   # Vice Capitão
    "2": 1563995879998754942,   # Capitão
    "1": 1563995879998754943,   # Capitão Geral
}

RANK_CHOICES = [
    app_commands.Choice(name=f"No. {rank['no']:02d} — {rank['nome']}", value=str(rank["no"]))
    for rank in RANKS
]


def rank_por_xp(xp: int) -> dict:
    atual = RANKS[0]
    for rank in RANKS:
        if xp >= rank["xp"]:
            atual = rank
    return atual


def proximo_rank(xp: int) -> Optional[dict]:
    for rank in RANKS:
        if rank["xp"] > xp:
            return rank
    return None


def barra_progresso(xp: int, rank: dict, proximo: Optional[dict]) -> str:
    if proximo is None:
        return "█" * 12 + " 100%"
    inicio = int(rank["xp"])
    alvo = int(proximo["xp"])
    proporcao = max(0.0, min(1.0, (xp - inicio) / max(1, alvo - inicio)))
    preenchido = int(proporcao * 12)
    return "█" * preenchido + "░" * (12 - preenchido) + f" {int(proporcao * 100)}%"


class ProgressaoGangue(commands.Cog):
    """Progressão independente da NÊMESIS, com XP, ranks, cargos e anúncios."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        self._cooldowns = {}
        self._prontos = set()

    async def _dados(self) -> dict:
        dados = await carregar(ARQUIVO, {})
        return dados if isinstance(dados, dict) else {}

    async def _salvar_dados(self, dados: dict):
        await salvar(ARQUIVO, dados)

    async def _perfil(self, guild_id: int, user_id: int) -> dict:
        """Lê um perfil e persiste apenas quando cria ou corrige dados legados."""
        async with self._lock:
            dados = await self._dados()
            chave_guild = str(guild_id)
            guild = dados.get(chave_guild)
            mudou = False
            if not isinstance(guild, dict):
                guild = {}
                dados[chave_guild] = guild
                mudou = True

            membros = guild.get("membros")
            if not isinstance(membros, dict):
                membros = {}
                guild["membros"] = membros
                mudou = True

            chave_usuario = str(user_id)
            perfil = membros.get(chave_usuario)
            if not isinstance(perfil, dict):
                perfil = {
                    "xp": 0, "mensagens": 0, "missoes": 0, "guerras": 0,
                    "rank_no": 12, "ultimo_xp": 0, "historico_ranks": [],
                }
                membros[chave_usuario] = perfil
                mudou = True

            padroes = {
                "xp": 0,
                "mensagens": 0,
                "missoes": 0,
                "guerras": 0,
                "rank_no": 12,
                "ultimo_xp": 0,
                "historico_ranks": [],
            }
            for campo, padrao in padroes.items():
                if campo not in perfil:
                    perfil[campo] = list(padrao) if isinstance(padrao, list) else padrao
                    mudou = True

            if mudou:
                await self._salvar_dados(dados)
            return dict(perfil)

    async def _atualizar_perfil(self, guild_id: int, user_id: int, perfil: dict):
        async with self._lock:
            dados = await self._dados()
            guild = dados.setdefault(str(guild_id), {})
            guild.setdefault("membros", {})[str(user_id)] = perfil
            await self._salvar_dados(dados)

    async def _registrar_xp_atomico(
        self,
        guild_id: int,
        user_id: int,
        quantidade: int,
        *,
        evento_id: str = "",
        tipo: str = "",
        contar_mensagem: bool = False,
    ) -> tuple[dict, dict, dict, bool]:
        """Atualiza XP e contadores em uma única seção crítica; deduplica eventos identificados."""
        quantidade = max(0, int(quantidade))
        async with self._lock:
            dados = await self._dados()
            guild = dados.setdefault(str(guild_id), {})
            membros = guild.setdefault("membros", {})
            perfil = membros.setdefault(str(user_id), {
                "xp": 0, "mensagens": 0, "missoes": 0, "guerras": 0,
                "rank_no": 12, "ultimo_xp": 0, "historico_ranks": [],
            })
            perfil.setdefault("xp", 0)
            perfil.setdefault("mensagens", 0)
            perfil.setdefault("missoes", 0)
            perfil.setdefault("guerras", 0)
            perfil.setdefault("rank_no", 12)
            perfil.setdefault("eventos_recompensa", [])
            eventos = perfil["eventos_recompensa"]
            if evento_id and evento_id in eventos:
                rank = rank_por_xp(max(0, int(perfil.get("xp", 0) or 0)))
                return dict(perfil), rank, rank, False

            rank_antigo = rank_por_xp(max(0, int(perfil.get("xp", 0) or 0)))
            perfil["xp"] = max(0, int(perfil.get("xp", 0) or 0)) + quantidade
            if contar_mensagem:
                perfil["mensagens"] = int(perfil.get("mensagens", 0) or 0) + 1
                perfil["ultimo_xp"] = time.time()
            if tipo in {"missao", "especial"}:
                perfil["missoes"] = int(perfil.get("missoes", 0) or 0) + 1
            elif tipo == "guerra":
                perfil["guerras"] = int(perfil.get("guerras", 0) or 0) + 1
            if evento_id:
                eventos.append(evento_id)
                perfil["eventos_recompensa"] = eventos[-1000:]

            rank_novo = rank_por_xp(perfil["xp"])
            perfil["rank_no"] = rank_novo["no"]
            membros[str(user_id)] = perfil
            await self._salvar_dados(dados)
            if hasattr(self.bot, "dispatch"):
                self.bot.dispatch("nemesis_conquistas_verificar", guild_id, user_id)
            return dict(perfil), rank_antigo, rank_novo, True

    async def _transferir_xp(self, guild_id: int, origem_id: int, destino_id: int, quantidade: int) -> tuple[dict, dict]:
        """Executa a transferência como uma única operação de leitura/alteração/gravação."""
        async with self._lock:
            dados = await self._dados()
            guild = dados.setdefault(str(guild_id), {})
            membros = guild.setdefault("membros", {})

            def obter(uid: int) -> dict:
                perfil = membros.setdefault(str(uid), {
                    "xp": 0, "mensagens": 0, "missoes": 0, "guerras": 0,
                    "rank_no": 12, "ultimo_xp": 0, "historico_ranks": [],
                })
                perfil.setdefault("xp", 0)
                perfil.setdefault("mensagens", 0)
                perfil.setdefault("missoes", 0)
                perfil.setdefault("guerras", 0)
                perfil.setdefault("rank_no", 12)
                perfil.setdefault("ultimo_xp", 0)
                perfil.setdefault("historico_ranks", [])
                return perfil

            origem = obter(origem_id)
            destino = obter(destino_id)
            saldo_origem = max(0, int(origem.get("xp", 0)))
            if quantidade <= 0:
                raise ValueError("A quantidade precisa ser maior que zero.")
            if saldo_origem < quantidade:
                raise ValueError(f"Saldo insuficiente. Você possui {saldo_origem:,} XP.".replace(",", "."))
            origem["xp"] = saldo_origem - quantidade
            destino["xp"] = max(0, int(destino.get("xp", 0))) + quantidade
            origem["rank_no"] = rank_por_xp(origem["xp"])["no"]
            destino["rank_no"] = rank_por_xp(destino["xp"])["no"]

            historico = guild.setdefault("transferencias_xp", [])
            historico.append({
                "de": str(origem_id),
                "para": str(destino_id),
                "quantidade": quantidade,
                "timestamp": int(time.time()),
            })
            guild["transferencias_xp"] = historico[-500:]
            await self._salvar_dados(dados)
            return dict(origem), dict(destino)

    async def _config(self, guild_id: int) -> dict:
        async with self._lock:
            dados = await self._dados()
            chave_guild = str(guild_id)
            guild = dados.get(chave_guild)
            if not isinstance(guild, dict):
                guild = {}
                dados[chave_guild] = guild
            membros = guild.get("membros")
            if not isinstance(membros, dict):
                guild["membros"] = {}
            cargos = guild.get("cargos")
            if not isinstance(cargos, dict):
                cargos = {}
                guild["cargos"] = cargos
            alterado = False
            for rank_no, cargo_id in CARGOS_PROGRESSAO_PADRAO.items():
                if not str(cargos.get(rank_no, "")).isdigit():
                    cargos[rank_no] = cargo_id
                    alterado = True
            if alterado:
                await self._salvar_dados(dados)
            return guild

    async def _aplicar_cargo_rank(self, guild: discord.Guild, membro: discord.Member, rank: dict) -> bool:
        config = await self._config(guild.id)
        cargos = config.get("cargos", {})
        cargo_alvo_id = cargos.get(str(rank["no"]))
        # Não mexe nos cargos atuais enquanto este rank não tiver cargo configurado.
        if not cargo_alvo_id:
            return True
        if not str(cargo_alvo_id).isdigit():
            log.error("ID inválido configurado para o rank %s: %r", rank["nome"], cargo_alvo_id)
            return False
        adicionar = guild.get_role(int(cargo_alvo_id))
        if adicionar is None:
            log.error("Cargo configurado para o rank %s não existe mais: %s", rank["nome"], cargo_alvo_id)
            return False
        ids_progressao = {int(cid) for cid in cargos.values() if str(cid).isdigit()}
        legados = config.get("cargos_legados", [])
        if isinstance(legados, list):
            ids_progressao.update(int(cid) for cid in legados if str(cid).isdigit())
        remover = [cargo for cargo in membro.roles if cargo.id in ids_progressao and cargo.id != adicionar.id]
        cargo_adicionado = False
        try:
            # Adiciona o novo cargo antes de remover o anterior para evitar
            # deixar o membro sem rank caso a atribuição seja recusada.
            if adicionar not in membro.roles:
                await membro.add_roles(adicionar, reason="Atualização da progressão da NÊMESIS")
                cargo_adicionado = True
            if remover:
                await membro.remove_roles(*remover, reason="Atualização da progressão da NÊMESIS")
            return True
        except (discord.Forbidden, discord.HTTPException):
            if cargo_adicionado:
                try:
                    await membro.remove_roles(adicionar, reason="Reversão após falha na atualização de rank")
                except (discord.Forbidden, discord.HTTPException):
                    log.exception("Falha ao reverter o novo cargo de rank do membro %s.", membro.id)
            log.exception("Falha ao atualizar cargo de progressão do membro %s.", membro.id)
            return False

    async def _definir_rank_atomico(
        self,
        guild_id: int,
        user_id: int,
        novo_xp: int,
        *,
        responsavel_id: int,
        motivo: str,
        acao: str,
    ) -> tuple[dict, dict, dict]:
        async with self._lock:
            dados = await self._dados()
            chave_guild = str(guild_id)
            guild = dados.get(chave_guild)
            if not isinstance(guild, dict):
                guild = {}
                dados[chave_guild] = guild
            membros = guild.get("membros")
            if not isinstance(membros, dict):
                membros = {}
                guild["membros"] = membros
            perfil = membros.get(str(user_id))
            if not isinstance(perfil, dict):
                perfil = {
                    "xp": 0, "mensagens": 0, "missoes": 0, "guerras": 0,
                    "rank_no": 12, "ultimo_xp": 0, "historico_ranks": [],
                }
            xp_anterior = max(0, int(perfil.get("xp", 0) or 0))
            rank_anterior = rank_por_xp(xp_anterior)
            perfil["xp"] = max(0, int(novo_xp))
            rank_novo = rank_por_xp(perfil["xp"])
            perfil["rank_no"] = rank_novo["no"]
            historico = perfil.get("historico_ranks", [])
            if not isinstance(historico, list):
                historico = []
            historico.append({
                "acao": acao,
                "de": rank_anterior["nome"],
                "para": rank_novo["nome"],
                "xp_anterior": xp_anterior,
                "xp_novo": perfil["xp"],
                "responsavel_id": str(responsavel_id),
                "motivo": str(motivo)[:300],
                "timestamp": int(time.time()),
            })
            perfil["historico_ranks"] = historico[-200:]
            membros[str(user_id)] = perfil
            await self._salvar_dados(dados)
            return dict(perfil), rank_anterior, rank_novo

    async def _anunciar_rank(self, guild: discord.Guild, membro: discord.Member, rank: dict, xp: int):
        canal = guild.get_channel(CANAL_PROGRESSAO_ID)
        if not isinstance(canal, discord.TextChannel):
            try:
                canal = await self.bot.fetch_channel(CANAL_PROGRESSAO_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                log.error("Canal de progressão %s não encontrado/acessível.", CANAL_PROGRESSAO_ID)
                return
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  PROMOÇÃO DE RANK",
            description=(
                "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "       PROGRESSÃO CONFIRMADA\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"**Membro:** {membro.mention}\n"
                f"**Novo rank:** ╭・𝐍̷𝐨.{rank['no']} — {rank['nome']}\n"
                f"**Experiência de gangue:** {xp:,} XP".replace(",", ".")
                + "\n\nO avanço foi registrado automaticamente pelo sistema da NÊMESIS."
            ),
            color=0x9F1239,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_thumbnail(url=membro.display_avatar.url)
        embed.set_footer(text="NÊMESIS • PROGRESSÃO • A atividade válida impulsiona a hierarquia")
        try:
            await canal.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Falha ao anunciar promoção no canal de progressão.")

    async def _garantir_painel(self, guild: discord.Guild):
        if guild.id in self._prontos:
            return
        canal = guild.get_channel(CANAL_PROGRESSAO_ID)
        if not isinstance(canal, discord.TextChannel):
            try:
                canal = await self.bot.fetch_channel(CANAL_PROGRESSAO_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                log.error("Canal de progressão %s não encontrado/acessível.", CANAL_PROGRESSAO_ID)
                return
        dados = await self._dados()
        config = dados.setdefault(str(guild.id), {})
        embed = criar_embed(
            title="⚔️ PROGRESSÃO · HIERARQUIA NÊMESIS",
            description=(
                "**SUA EVOLUÇÃO É CONQUISTADA EM ATIVIDADE REAL.**\n"
                "A progressão registra participação legítima, missões e guerras. "
                "Missões são validadas pelo OCTÓGONO; promoções e rebaixamentos manuais exigem justificativa "
                "e respeito à autoridade hierárquica."
            ),
            cor=0x9F1239,
            rodape=None,
        )
        embed.set_author(name="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  SISTEMA DE MÉRITO")
        embed.add_field(
            name="01  /  PARTICIPAÇÃO",
            value=f"**+{XP_POR_MENSAGEM} XP** por mensagem válida\nIntervalo de {COOLDOWN_MENSAGENS}s entre registros",
            inline=True,
        )
        embed.add_field(
            name="02  /  ATIVIDADES OFICIAIS",
            value="Missões são validadas pelo OCTÓGONO; contribuições e guerras seguem os fluxos oficiais.",
            inline=True,
        )
        hierarquia = "\n".join(
            f"{r['no']:02d}  **{r['nome']}**  ·  {r['xp']:,} XP".replace(",", ".")
            for r in RANKS
        )
        hierarquia += "\n00  **Liderança**  ·  atribuição exclusiva da direção"
        embed.add_field(name="03  /  ESCALA DE PATENTES", value=hierarquia[:1024], inline=False)
        embed.set_footer(text="NÊMESIS • PROGRESSÃO OFICIAL • XP separado do competitivo • Ações manuais auditadas")
        msg_id = config.get("painel_mensagem_id")
        if msg_id:
            try:
                msg = await canal.fetch_message(int(msg_id))
                await msg.edit(embed=embed)
                self._prontos.add(guild.id)
                return
            except discord.NotFound:
                pass
            except (discord.Forbidden, discord.HTTPException):
                log.exception("Não foi possível atualizar o painel de progressão.")
                return
        try:
            msg = await canal.send(embed=embed)
            config["painel_mensagem_id"] = msg.id
            await self._salvar_dados(dados)
            try:
                await msg.pin(reason="Painel oficial permanente da progressão da NÊMESIS")
            except (discord.Forbidden, discord.HTTPException):
                pass
            self._prontos.add(guild.id)
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Não foi possível publicar o painel de progressão.")

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(GUILD_ID)
        if guild:
            await self._garantir_painel(guild)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.guild.id != GUILD_ID or message.author.bot:
            return
        # Somente integrantes com o cargo oficial podem acumular XP de gangue.
        if not isinstance(message.author, discord.Member) or not any(
            cargo.id == CARGO_NEMESIS_ID for cargo in message.author.roles
        ):
            return
        if message.channel.id == CANAL_PROGRESSAO_ID:
            return
        if not message.content.strip() and not message.attachments:
            return
        agora = time.time()
        chave = (message.guild.id, message.author.id)
        if agora - self._cooldowns.get(chave, 0) < COOLDOWN_MENSAGENS:
            return
        self._cooldowns[chave] = agora
        perfil, rank_antigo, rank_novo, aplicada = await self._registrar_xp_atomico(
            message.guild.id, message.author.id, XP_POR_MENSAGEM, contar_mensagem=True,
        )
        if not aplicada:
            return
        if rank_novo["no"] != rank_antigo["no"]:
            await self._aplicar_cargo_rank(message.guild, message.author, rank_novo)
            await self._anunciar_rank(message.guild, message.author, rank_novo, perfil["xp"])

    async def registrar_recompensa(self, guild: discord.Guild, user_id: int, quantidade: int, tipo: str = "missao", evento_id: str = ""):
        """Aplica recompensa com deduplicação e atualização atômica do saldo."""
        membro_autorizado = guild.get_member(user_id)
        if membro_autorizado is None or not any(
            cargo.id == CARGO_NEMESIS_ID for cargo in membro_autorizado.roles
        ):
            log.info(
                "Recompensa de progressão bloqueada: membro sem cargo oficial (guild=%s user=%s).",
                guild.id, user_id,
            )
            return
        quantidade = max(0, int(quantidade))
        if quantidade <= 0:
            return
        perfil, rank_antigo, rank_novo, aplicada = await self._registrar_xp_atomico(
            guild.id, user_id, quantidade, evento_id=evento_id, tipo=tipo,
        )
        if not aplicada:
            log.info("Recompensa duplicada ignorada: guild=%s user=%s evento=%s", guild.id, user_id, evento_id)
            return
        membro = guild.get_member(user_id)
        if membro is not None:
            await self._aplicar_cargo_rank(guild, membro, rank_novo)
            if rank_novo["no"] != rank_antigo["no"]:
                await self._anunciar_rank(guild, membro, rank_novo, perfil["xp"])

    @app_commands.command(name="gangue-perfil", description="Mostra o progresso de um membro na hierarquia da NÊMESIS.")
    @app_commands.describe(membro="Membro para consultar; padrão: você")
    async def gangue_perfil(self, interaction: discord.Interaction, membro: discord.Member = None):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        alvo = membro or interaction.user
        perfil = await self._perfil(interaction.guild.id, alvo.id)
        xp = int(perfil.get("xp", 0))
        rank = rank_por_xp(xp)
        proximo = proximo_rank(xp)
        progresso = barra_progresso(xp, rank, proximo)
        destino = f"╭・𝐍̷𝐨.{proximo['no']} — {proximo['nome']} · faltam **{max(0, proximo['xp'] - xp)} XP**" if proximo else "Rank máximo de progressão alcançado."
        embed = criar_embed(
            title=f"📊 DOSSIÊ DE PROGRESSÃO · {alvo.display_name.upper()[:90]}",
            description=(
                f"**POSTO ATUAL**\nNº {rank['no']:02d}  **{rank['nome']}**\n"
                f"**EXPERIÊNCIA ACUMULADA** · {xp:,} XP\n"
                f"{progresso}\n"
                f"**PRÓXIMO OBJETIVO** · {destino}"
            ).replace(",", "."),
            cor=0x9F1239,
            rodape="NÊMESIS  •  PROGRESSÃO INDIVIDUAL",
        )
        embed.add_field(name="MENSAGENS VÁLIDAS", value=f"**{int(perfil.get('mensagens', 0)):,}**".replace(",", "."), inline=True)
        embed.add_field(name="MISSÕES", value=f"**{int(perfil.get('missoes', 0)):,}**".replace(",", "."), inline=True)
        embed.add_field(name="GUERRAS", value=f"**{int(perfil.get('guerras', 0)):,}**".replace(",", "."), inline=True)
        embed.set_thumbnail(url=alvo.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gangue-ranking", description="Mostra o ranking de progressão da NÊMESIS.")
    async def gangue_ranking(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        dados = await self._dados()
        membros = dados.get(str(interaction.guild.id), {}).get("membros", {})
        ranking = sorted(
            ((int(uid), perfil) for uid, perfil in membros.items() if isinstance(perfil, dict)),
            key=lambda item: (int(item[1].get("xp", 0)), int(item[1].get("mensagens", 0))),
            reverse=True,
        )[:10]
        if not ranking:
            await interaction.response.send_message("Ainda não há membros no ranking de progressão.", ephemeral=True)
            return
        embed = criar_embed(
            title="🏆 CLASSIFICAÇÃO · HIERARQUIA NÊMESIS",
            description="**TOP 10 DE PROGRESSÃO**\nClassificação ordenada por XP acumulado e, em caso de empate, por participação registrada.",
            cor=0x9F1239,
            rodape="NÊMESIS  •  QUADRO DE MÉRITO",
        )
        medalhas = {1: "🥇", 2: "🥈", 3: "🥉"}
        for posicao, (uid, perfil) in enumerate(ranking, start=1):
            xp = int(perfil.get("xp", 0))
            rank = rank_por_xp(xp)
            membro = interaction.guild.get_member(uid)
            nome = membro.display_name if membro else f"Membro {uid}"
            selo = medalhas.get(posicao, f"#{posicao:02d}")
            embed.add_field(
                name=f"{selo}  {nome[:70]}  ·  {rank['nome']}",
                value=f"<@{uid}>\n**{xp:,} XP**  ·  **{int(perfil.get('mensagens', 0)):,} mensagens**".replace(",", "."),
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="gangue-banco", description="Consulta seu saldo de XP transferível da NÊMESIS.")
    async def gangue_banco(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        perfil = await self._perfil(interaction.guild.id, interaction.user.id)
        xp = max(0, int(perfil.get("xp", 0)))
        rank = rank_por_xp(xp)
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  BANCO DE EXPERIÊNCIA",
            description=(
                f"**Titular:** {interaction.user.mention}\n"
                f"**Saldo disponível:** **{xp:,} XP**\n"
                f"**Rank atual:** ╭・𝐍̷𝐨.{rank['no']} — {rank['nome']}\n\n"
                "Use `/gangue-doar-xp` para transferir XP a outro membro. "
                "O valor doado sai do seu saldo e entra no saldo do destinatário."
            ).replace(",", "."),
            color=0x9F1239,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="NÊMESIS • BANCO DE XP • Transferências registradas")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="gangue-doar-xp", description="Transfere XP do seu saldo para outro membro da NÊMESIS.")
    @app_commands.describe(destinatario="Membro que receberá a transferência", quantidade="Quantidade de XP a transferir")
    async def gangue_doar_xp(
        self,
        interaction: discord.Interaction,
        destinatario: discord.Member,
        quantidade: app_commands.Range[int, 1, 10000],
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if destinatario.bot:
            await interaction.response.send_message("Não é possível transferir XP para bots.", ephemeral=True)
            return
        if destinatario.id == interaction.user.id:
            await interaction.response.send_message("Você não pode transferir XP para si mesmo.", ephemeral=True)
            return

        try:
            perfil_origem, perfil_destino = await self._transferir_xp(
                interaction.guild.id, interaction.user.id, destinatario.id, int(quantidade)
            )
        except ValueError as erro:
            await interaction.response.send_message(str(erro), ephemeral=True)
            return

        rank_origem = rank_por_xp(int(perfil_origem["xp"]))
        rank_destino = rank_por_xp(int(perfil_destino["xp"]))
        membro_origem = interaction.guild.get_member(interaction.user.id)
        if membro_origem:
            await self._aplicar_cargo_rank(interaction.guild, membro_origem, rank_origem)
        await self._aplicar_cargo_rank(interaction.guild, destinatario, rank_destino)

        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  TRANSFERÊNCIA CONCLUÍDA",
            description=(
                f"**Remetente:** {interaction.user.mention}\n"
                f"**Destinatário:** {destinatario.mention}\n"
                f"**Transferido:** **{int(quantidade):,} XP**\n\n"
                f"**Seu saldo após a transferência:** {int(perfil_origem['xp']):,} XP\n"
                f"**Saldo do destinatário:** {int(perfil_destino['xp']):,} XP"
            ).replace(",", "."),
            color=0x9F1239,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="NÊMESIS • BANCO DE XP • Operação registrada no histórico")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        canal = interaction.guild.get_channel(CANAL_PROGRESSAO_ID)
        if isinstance(canal, discord.TextChannel):
            registro = criar_embed(
                title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  REGISTRO BANCÁRIO",
                description=(
                    f"**De:** {interaction.user.mention}\n"
                    f"**Para:** {destinatario.mention}\n"
                    f"**Valor:** {int(quantidade):,} XP"
                ).replace(",", "."),
                color=0x454545,
                timestamp=discord.utils.utcnow(),
            )
            try:
                await canal.send(
                    embed=registro,
                    allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
                )
            except (discord.Forbidden, discord.HTTPException):
                log.warning("Transferência salva, mas não foi possível publicar o registro bancário.")

    @app_commands.command(name="gangue-configurar-cargo", description="Vincula um cargo do Discord a um rank de progressão.")
    @app_commands.describe(rank="Rank que receberá o cargo", cargo="Cargo que será atribuído ao alcançar o rank")
    @app_commands.choices(rank=RANK_CHOICES)
    @octogono_only()
    async def gangue_configurar_cargo(
        self,
        interaction: discord.Interaction,
        rank: app_commands.Choice[str],
        cargo: discord.Role,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        bot_member = interaction.guild.me
        if (
            bot_member is None
            or cargo >= bot_member.top_role
            or cargo.managed
            or cargo.is_default()
            or cargo.id in CARGOS_RESERVADOS_PROGRESSAO_IDS
            or not membro_pode_atribuir_cargo_hierarquico(interaction.user, cargo)
        ):
            await interaction.response.send_message(
                "O cargo escolhido precisa estar abaixo da autoridade do OCTÓGONO e do cargo mais alto do bot, e não pode ser gerenciado por integração.",
                ephemeral=True,
            )
            return
        rank_no = int(rank.value)
        async with self._lock:
            dados = await self._dados()
            chave_guild = str(interaction.guild.id)
            guild_data = dados.get(chave_guild)
            if not isinstance(guild_data, dict):
                guild_data = {}
                dados[chave_guild] = guild_data
            cargos = guild_data.get("cargos")
            if not isinstance(cargos, dict):
                cargos = {}
                guild_data["cargos"] = cargos
            for numero, cargo_padrao in CARGOS_PROGRESSAO_PADRAO.items():
                if not str(cargos.get(numero, "")).isdigit():
                    cargos[numero] = cargo_padrao
            duplicado = next(
                (numero for numero, cargo_id in cargos.items()
                 if str(cargo_id) == str(cargo.id) and str(numero) != str(rank_no)),
                None,
            )
            if duplicado is not None:
                await interaction.response.send_message(
                    "Esse cargo já está vinculado a outro rank. Remova ou altere o vínculo anterior antes de reutilizá-lo.",
                    ephemeral=True,
                )
                return
            cargo_anterior = cargos.get(str(rank_no))
            if cargo_anterior and str(cargo_anterior) != str(cargo.id):
                legados = guild_data.get("cargos_legados")
                if not isinstance(legados, list):
                    legados = []
                if str(cargo_anterior).isdigit() and int(cargo_anterior) not in legados:
                    legados.append(int(cargo_anterior))
                guild_data["cargos_legados"] = legados[-100:]
            cargos[str(rank_no)] = cargo.id
            await self._salvar_dados(dados)
        try:
            from utils.registro_global import registrar
            await registrar(
                interaction.guild,
                "configuracoes",
                "Vínculo de cargo de progressão alterado",
                f"**Responsável:** {interaction.user.mention}\n"
                f"**Rank:** No. {rank_no:02d} — {rank.name}\n"
                f"**Cargo novo:** {cargo.mention}\n"
                f"**Cargo anterior:** {cargo_anterior or 'Nenhum'}",
                cor=0x9F1239,
            )
        except Exception:
            log.exception("Não foi possível registrar a alteração de cargo de progressão.")
        await interaction.response.send_message(
            f"Vínculo salvo: No. {rank_no:02d} — {rank.name} → {cargo.mention}.",
            ephemeral=True,
        )

    async def _ajustar_rank_manual(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        rank: app_commands.Choice[str],
        motivo: str,
        acao: str,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if membro.bot or membro.id == interaction.guild.owner_id:
            await interaction.response.send_message("Este membro não pode receber uma alteração manual de rank.", ephemeral=True)
            return
        if not membro_pode_gerenciar_membro(interaction.user, membro):
            await interaction.response.send_message(
                "Você só pode alterar o rank de membros abaixo da sua posição hierárquica.",
                ephemeral=True,
            )
            return
        if len(motivo.strip()) < 5 or len(motivo) > 300:
            await interaction.response.send_message("Informe um motivo entre 5 e 300 caracteres.", ephemeral=True)
            return

        rank_alvo = next((item for item in RANKS if item["no"] == int(rank.value)), None)
        if rank_alvo is None:
            await interaction.response.send_message("Rank inválido.", ephemeral=True)
            return
        config = await self._config(interaction.guild.id)
        cargo_id = config.get("cargos", {}).get(str(rank_alvo["no"]))
        cargo_alvo = interaction.guild.get_role(int(cargo_id)) if cargo_id else None
        if cargo_alvo is None:
            await interaction.response.send_message(
                f"O cargo do rank {rank_alvo['nome']} ainda não está configurado. O OCTÓGONO deve usar /gangue-configurar-cargo antes da alteração.",
                ephemeral=True,
            )
            return
        if not membro_pode_atribuir_cargo_hierarquico(interaction.user, cargo_alvo):
            await interaction.response.send_message(
                "O rank escolhido está acima da sua autoridade hierárquica.",
                ephemeral=True,
            )
            return
        bot_member = interaction.guild.me
        maior_cargo_alvo = max(membro.roles, key=lambda item: item.position, default=None)
        if bot_member is None or (maior_cargo_alvo and bot_member.top_role <= maior_cargo_alvo):
            await interaction.response.send_message(
                "O cargo do bot precisa estar acima dos cargos do membro para executar a alteração com segurança.",
                ephemeral=True,
            )
            return

        perfil_atual = await self._perfil(interaction.guild.id, membro.id)
        xp_atual = max(0, int(perfil_atual.get("xp", 0) or 0))
        rank_atual = rank_por_xp(xp_atual)
        if acao == "Promoção" and rank_alvo["no"] >= rank_atual["no"]:
            await interaction.response.send_message("O rank escolhido não é superior ao rank atual.", ephemeral=True)
            return
        if acao == "Rebaixamento" and rank_alvo["no"] <= rank_atual["no"]:
            await interaction.response.send_message("O rank escolhido não é inferior ao rank atual.", ephemeral=True)
            return

        xp_novo = max(xp_atual, int(rank_alvo["xp"])) if acao == "Promoção" else int(rank_alvo["xp"])
        perfil, rank_anterior, rank_novo = await self._definir_rank_atomico(
            interaction.guild.id,
            membro.id,
            xp_novo,
            responsavel_id=interaction.user.id,
            motivo=motivo.strip(),
            acao=acao,
        )
        aplicado = await self._aplicar_cargo_rank(interaction.guild, membro, rank_novo)
        if not aplicado:
            await self._definir_rank_atomico(
                interaction.guild.id,
                membro.id,
                xp_atual,
                responsavel_id=interaction.user.id,
                motivo="Reversão automática: o Discord não aceitou a atualização do cargo.",
                acao="Reversão",
            )
            await interaction.response.send_message(
                "A alteração foi revertida porque o Discord não aceitou a troca do cargo. O XP foi revertido; confira o cargo do membro se o Discord também recusou a reversão do cargo.",
                ephemeral=True,
            )
            return

        try:
            from utils.registro_global import registrar
            await registrar(
                interaction.guild,
                "progressao",
                f"{acao} manual de rank",
                f"**Membro:** {membro.mention}\n**Responsável:** {interaction.user.mention}\n"
                f"**Rank anterior:** {rank_anterior['nome']}\n**Novo rank:** {rank_novo['nome']}\n"
                f"**XP anterior:** {xp_atual:,}\n**XP atual:** {int(perfil['xp']):,}\n"
                f"**Motivo:** {discord.utils.escape_markdown(motivo.strip())}".replace(",", "."),
                cor=0x9F1239,
            )
        except Exception:
            log.exception("Não foi possível registrar a alteração manual de rank no Registro Global.")
        await interaction.response.send_message(
            f"{acao} concluída. {membro.mention}: {rank_anterior['nome']} → {rank_novo['nome']} · "
            f"{int(perfil['xp']):,} XP".replace(",", "."),
            ephemeral=True,
        )

    @app_commands.command(name="gangue-promover", description="Promove um membro para um rank superior da NÊMESIS.")
    @app_commands.describe(membro="Membro que será promovido", rank="Novo rank", motivo="Justificativa da promoção")
    @app_commands.choices(rank=RANK_CHOICES)
    @hierarquia_only()
    async def gangue_promover(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        rank: app_commands.Choice[str],
        motivo: app_commands.Range[str, 5, 300],
    ):
        await self._ajustar_rank_manual(interaction, membro, rank, motivo, "Promoção")

    @app_commands.command(name="gangue-rebaixar", description="Rebaixa um membro para um rank inferior da NÊMESIS.")
    @app_commands.describe(membro="Membro que será rebaixado", rank="Novo rank", motivo="Justificativa do rebaixamento")
    @app_commands.choices(rank=RANK_CHOICES)
    @hierarquia_only()
    async def gangue_rebaixar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member,
        rank: app_commands.Choice[str],
        motivo: app_commands.Range[str, 5, 300],
    ):
        await self._ajustar_rank_manual(interaction, membro, rank, motivo, "Rebaixamento")

    @app_commands.command(name="gangue-registrar-atividade", description="Registra missão, contribuição ou guerra concluída para a progressão.")
    @app_commands.describe(membro="Membro reconhecido", atividade="Tipo de atividade", quantidade="XP de recompensa", motivo="Prova ou motivo do registro")
    @app_commands.choices(atividade=[
        app_commands.Choice(name="Missão", value="missao"),
        app_commands.Choice(name="Contribuição", value="contribuicao"),
        app_commands.Choice(name="Guerra", value="guerra"),
    ])
    @octogono_only()
    async def gangue_registrar_atividade(self, interaction: discord.Interaction, membro: discord.Member, atividade: app_commands.Choice[str], quantidade: app_commands.Range[int, 1, 5000], motivo: str):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if len(motivo.strip()) < 5 or len(motivo) > 300:
            await interaction.response.send_message("Informe um motivo entre 5 e 300 caracteres.", ephemeral=True)
            return
        perfil, rank_antigo, rank_novo, aplicada = await self._registrar_xp_atomico(
            interaction.guild.id,
            membro.id,
            int(quantidade),
            tipo=atividade.value,
        )
        await self._aplicar_cargo_rank(interaction.guild, membro, rank_novo)
        if rank_novo["no"] != rank_antigo["no"]:
            await self._anunciar_rank(interaction.guild, membro, rank_novo, perfil["xp"])
        total_xp = int(perfil["xp"])
        motivo_seguro = discord.utils.escape_markdown(motivo)
        canal_registro = interaction.guild.get_channel(CANAL_REGISTRO_ATIVIDADE_ID)
        if not isinstance(canal_registro, discord.TextChannel):
            try:
                canal_registro = await self.bot.fetch_channel(CANAL_REGISTRO_ATIVIDADE_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                canal_registro = None

        if isinstance(canal_registro, discord.TextChannel):
            registro = criar_embed(
                title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  ATIVIDADE REGISTRADA",
                description=(
                    f"**Membro:** {membro.mention}\n"
                    f"**Registrado por:** {interaction.user.mention}\n"
                    f"**Tipo:** {atividade.name}\n"
                    f"**Recompensa:** +{quantidade} XP\n"
                    f"**Motivo:** {motivo_seguro}\n"
                    f"**Experiência total:** {total_xp:,} XP\n"
                    f"**Rank atual:** ╭・𝐍̷𝐨.{rank_novo['no']} — {rank_novo['nome']}"
                ).replace(",", "."),
                color=0x9F1239,
                timestamp=discord.utils.utcnow(),
            )
            registro.set_thumbnail(url=membro.display_avatar.url)
            registro.set_footer(text="NÊMESIS • REGISTRO OFICIAL DE ATIVIDADES")
            try:
                await canal_registro.send(
                    embed=registro,
                    allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
                )
            except (discord.Forbidden, discord.HTTPException):
                log.exception(
                    "Atividade de gangue registrada, mas não foi possível publicar no canal %s.",
                    CANAL_REGISTRO_ATIVIDADE_ID,
                )
        else:
            log.error("Canal de registro de atividade %s não encontrado/acessível.", CANAL_REGISTRO_ATIVIDADE_ID)

        await interaction.response.send_message(
            f"Atividade registrada para {membro.mention}.\n"
            f"**Tipo:** {atividade.name}\n**Recompensa:** +{quantidade} XP\n"
            f"**Motivo:** {motivo_seguro}\n"
            f"**Total:** {total_xp:,} XP · **Rank:** No.{rank_novo['no']} — {rank_novo['nome']}".replace(",", "."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ProgressaoGangue(bot))
