import time
import asyncio
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.storage import carregar, salvar

log = logging.getLogger(__name__)

GUILD_ID = 1543381737961160910
CANAL_PROGRESSAO_ID = 1545832891681087628
ARQUIVO = "progressao_gangue.json"
COOLDOWN_MENSAGENS = 60
XP_POR_MENSAGEM = 5

RANKS = [
    {"no": 10, "nome": "Recruta", "xp": 0},
    {"no": 9, "nome": "Iniciado", "xp": 100},
    {"no": 8, "nome": "Operador", "xp": 250},
    {"no": 7, "nome": "Membro", "xp": 500},
    {"no": 6, "nome": "Veterano", "xp": 900},
    {"no": 5, "nome": "Especialista", "xp": 1400},
    {"no": 4, "nome": "Elite", "xp": 2100},
    {"no": 3, "nome": "Executor", "xp": 3000},
    {"no": 2, "nome": "Comandante", "xp": 4200},
    {"no": 1, "nome": "Lenda", "xp": 6000},
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
        async with self._lock:
            dados = await self._dados()
            guild = dados.setdefault(str(guild_id), {})
            membros = guild.setdefault("membros", {})
            perfil = membros.setdefault(str(user_id), {
                "xp": 0, "mensagens": 0, "missoes": 0, "guerras": 0,
                "rank_no": 10, "ultimo_xp": 0, "historico_ranks": [],
            })
            perfil.setdefault("xp", 0)
            perfil.setdefault("mensagens", 0)
            perfil.setdefault("missoes", 0)
            perfil.setdefault("guerras", 0)
            perfil.setdefault("rank_no", 10)
            perfil.setdefault("ultimo_xp", 0)
            perfil.setdefault("historico_ranks", [])
            await self._salvar_dados(dados)
            return dict(perfil)

    async def _atualizar_perfil(self, guild_id: int, user_id: int, perfil: dict):
        async with self._lock:
            dados = await self._dados()
            guild = dados.setdefault(str(guild_id), {})
            guild.setdefault("membros", {})[str(user_id)] = perfil
            await self._salvar_dados(dados)

    async def _transferir_xp(self, guild_id: int, origem_id: int, destino_id: int, quantidade: int) -> tuple[dict, dict]:
        """Executa a transferência como uma única operação de leitura/alteração/gravação."""
        async with self._lock:
            dados = await self._dados()
            guild = dados.setdefault(str(guild_id), {})
            membros = guild.setdefault("membros", {})

            def obter(uid: int) -> dict:
                perfil = membros.setdefault(str(uid), {
                    "xp": 0, "mensagens": 0, "missoes": 0, "guerras": 0,
                    "rank_no": 10, "ultimo_xp": 0, "historico_ranks": [],
                })
                perfil.setdefault("xp", 0)
                perfil.setdefault("mensagens", 0)
                perfil.setdefault("missoes", 0)
                perfil.setdefault("guerras", 0)
                perfil.setdefault("rank_no", 10)
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
        dados = await self._dados()
        guild = dados.setdefault(str(guild_id), {})
        guild.setdefault("membros", {})
        guild.setdefault("cargos", {})
        return guild

    async def _aplicar_cargo_rank(self, guild: discord.Guild, membro: discord.Member, rank: dict):
        config = await self._config(guild.id)
        cargos = config.get("cargos", {})
        cargo_alvo_id = cargos.get(str(rank["no"]))
        # Não mexe nos cargos atuais enquanto este rank não tiver cargo configurado.
        if not cargo_alvo_id:
            return
        ids_progressao = {int(cid) for cid in cargos.values() if str(cid).isdigit()}
        remover = [cargo for cargo in membro.roles if cargo.id in ids_progressao and cargo.id != int(cargo_alvo_id)]
        adicionar = guild.get_role(int(cargo_alvo_id))
        try:
            if remover:
                await membro.remove_roles(*remover, reason="Atualização automática da progressão da NÊMESIS")
            if adicionar and adicionar not in membro.roles:
                await membro.add_roles(adicionar, reason="Rank alcançado na progressão da NÊMESIS")
        except discord.Forbidden:
            log.warning("Sem hierarquia/permissão para atualizar cargo de progressão do membro %s.", membro.id)
        except discord.HTTPException:
            log.exception("Falha ao atualizar cargo de progressão do membro %s.", membro.id)

    async def _anunciar_rank(self, guild: discord.Guild, membro: discord.Member, rank: dict, xp: int):
        canal = guild.get_channel(CANAL_PROGRESSAO_ID)
        if not isinstance(canal, discord.TextChannel):
            try:
                canal = await self.bot.fetch_channel(CANAL_PROGRESSAO_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                log.error("Canal de progressão %s não encontrado/acessível.", CANAL_PROGRESSAO_ID)
                return
        embed = discord.Embed(
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
            color=0xB51F32,
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
        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  SISTEMA DE PROGRESSÃO",
            description=(
                "A sua posição na gangue evolui conforme a participação legítima e a experiência acumulada.\n\n"
                "**Como progredir**\n"
                f"・Participação no servidor: **+{XP_POR_MENSAGEM} XP** por mensagem válida, com intervalo de {COOLDOWN_MENSAGENS}s.\n"
                "・Missões, contribuições e guerras podem ser registradas pela liderança.\n"
                "・Ao atingir o requisito, o rank é atualizado e anunciado aqui.\n\n"
                "**Hierarquia de progressão**\n"
                + "\n".join(f"╭・𝐍̷𝐨.{r['no']} — **{r['nome']}** · {r['xp']:,} XP".replace(",", ".") for r in RANKS)
                + "\n╭・𝐍̷𝐨.0 — **Liderança** · atribuição exclusiva da direção"
            ),
            color=0xB51F32,
        )
        embed.set_footer(text="NÊMESIS • PROGRESSÃO OFICIAL • XP de progressão separado do XP competitivo")
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
        if message.channel.id == CANAL_PROGRESSAO_ID:
            return
        if not message.content.strip() and not message.attachments:
            return
        agora = time.time()
        chave = (message.guild.id, message.author.id)
        if agora - self._cooldowns.get(chave, 0) < COOLDOWN_MENSAGENS:
            return
        self._cooldowns[chave] = agora
        perfil = await self._perfil(message.guild.id, message.author.id)
        rank_antigo = rank_por_xp(int(perfil.get("xp", 0)))
        perfil["xp"] = int(perfil.get("xp", 0)) + XP_POR_MENSAGEM
        perfil["mensagens"] = int(perfil.get("mensagens", 0)) + 1
        perfil["ultimo_xp"] = agora
        rank_novo = rank_por_xp(perfil["xp"])
        perfil["rank_no"] = rank_novo["no"]
        await self._atualizar_perfil(message.guild.id, message.author.id, perfil)
        if rank_novo["no"] != rank_antigo["no"]:
            await self._aplicar_cargo_rank(message.guild, message.author, rank_novo)
            await self._anunciar_rank(message.guild, message.author, rank_novo, perfil["xp"])

    async def registrar_recompensa(self, guild: discord.Guild, user_id: int, quantidade: int, tipo: str = "missao", evento_id: str = ""):
        """Integra recompensas aprovadas à progressão sem duplicar a mesma revisão."""
        quantidade = max(0, int(quantidade))
        if quantidade <= 0:
            return
        perfil = await self._perfil(guild.id, user_id)
        eventos = list(perfil.get("eventos_recompensa", []))
        if evento_id and evento_id in eventos:
            return
        rank_antigo = rank_por_xp(int(perfil.get("xp", 0)))
        perfil["xp"] = int(perfil.get("xp", 0)) + quantidade
        if tipo in {"missao", "especial"}:
            perfil["missoes"] = int(perfil.get("missoes", 0)) + 1
        elif tipo == "guerra":
            perfil["guerras"] = int(perfil.get("guerras", 0)) + 1
        if evento_id:
            eventos.append(evento_id)
            perfil["eventos_recompensa"] = eventos[-1000:]
        rank_novo = rank_por_xp(perfil["xp"])
        perfil["rank_no"] = rank_novo["no"]
        await self._atualizar_perfil(guild.id, user_id, perfil)
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
        embed = discord.Embed(
            title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  PROGRESSO DE {alvo.display_name.upper()}",
            description=(
                f"**Rank atual:** ╭・𝐍̷𝐨.{rank['no']} — {rank['nome']}\n"
                f"**Experiência:** {xp:,} XP\n"
                f"**Progresso:** {progresso}\n"
                f"**Próximo rank:** {destino}\n\n"
                f"**Mensagens válidas:** {int(perfil.get('mensagens', 0)):,}\n"
                f"**Missões registradas:** {int(perfil.get('missoes', 0)):,}\n"
                f"**Guerras registradas:** {int(perfil.get('guerras', 0)):,}"
            ).replace(",", "."),
            color=0xB51F32,
        )
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
        linhas = [
            f"**#{posicao}** <@{uid}> — ╭・𝐍̷𝐨.{rank_por_xp(int(perfil.get('xp', 0)))['no']} "
            f"{rank_por_xp(int(perfil.get('xp', 0)))['nome']} · **{int(perfil.get('xp', 0)):,} XP**".replace(",", ".")
            for posicao, (uid, perfil) in enumerate(ranking, start=1)
        ]
        embed = discord.Embed(title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  RANKING DA GANGUE", description="\n".join(linhas), color=0xB51F32)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="gangue-banco", description="Consulta seu saldo de XP transferível da NÊMESIS.")
    async def gangue_banco(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        perfil = await self._perfil(interaction.guild.id, interaction.user.id)
        xp = max(0, int(perfil.get("xp", 0)))
        rank = rank_por_xp(xp)
        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  BANCO DE EXPERIÊNCIA",
            description=(
                f"**Titular:** {interaction.user.mention}\n"
                f"**Saldo disponível:** **{xp:,} XP**\n"
                f"**Rank atual:** ╭・𝐍̷𝐨.{rank['no']} — {rank['nome']}\n\n"
                "Use `/gangue-doar-xp` para transferir XP a outro membro. "
                "O valor doado sai do seu saldo e entra no saldo do destinatário."
            ).replace(",", "."),
            color=0xB51F32,
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

        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  TRANSFERÊNCIA CONCLUÍDA",
            description=(
                f"**Remetente:** {interaction.user.mention}\n"
                f"**Destinatário:** {destinatario.mention}\n"
                f"**Transferido:** **{int(quantidade):,} XP**\n\n"
                f"**Seu saldo após a transferência:** {int(perfil_origem['xp']):,} XP\n"
                f"**Saldo do destinatário:** {int(perfil_destino['xp']):,} XP"
            ).replace(",", "."),
            color=0xB51F32,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="NÊMESIS • BANCO DE XP • Operação registrada no histórico")
        await interaction.response.send_message(embed=embed, ephemeral=True)

        canal = interaction.guild.get_channel(CANAL_PROGRESSAO_ID)
        if isinstance(canal, discord.TextChannel):
            registro = discord.Embed(
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

    @app_commands.command(name="gangue-configurar-cargo", description="Vincula um cargo Discord a um rank de progressão.")
    @app_commands.describe(rank_no="Número do rank de membro (1 a 10)", cargo="Cargo atribuído automaticamente ao alcançar o rank")
    @app_commands.default_permissions(administrator=True)
    async def gangue_configurar_cargo(self, interaction: discord.Interaction, rank_no: app_commands.Range[int, 1, 10], cargo: discord.Role):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        bot_member = interaction.guild.me
        if cargo.is_default() or cargo.managed or (bot_member and cargo >= bot_member.top_role):
            await interaction.response.send_message("Esse cargo não pode ser atribuído pelo bot. Escolha um cargo abaixo do cargo mais alto do bot.", ephemeral=True)
            return
        dados = await self._dados()
        config = dados.setdefault(str(interaction.guild.id), {})
        cargos = config.setdefault("cargos", {})
        cargos[str(rank_no)] = cargo.id
        await self._salvar_dados(dados)
        nome_rank = next(r["nome"] for r in RANKS if r["no"] == rank_no)
        await interaction.response.send_message(
            f"Cargo {cargo.mention} vinculado ao rank **No.{rank_no} — {nome_rank}**.",
            ephemeral=True,
        )

    @app_commands.command(name="gangue-registrar-atividade", description="Registra missão, contribuição ou guerra concluída para a progressão.")
    @app_commands.describe(membro="Membro reconhecido", atividade="Tipo de atividade", quantidade="XP de recompensa", motivo="Prova ou motivo do registro")
    @app_commands.choices(atividade=[
        app_commands.Choice(name="Missão", value="missao"),
        app_commands.Choice(name="Contribuição", value="contribuicao"),
        app_commands.Choice(name="Guerra", value="guerra"),
    ])
    @app_commands.default_permissions(manage_guild=True)
    async def gangue_registrar_atividade(self, interaction: discord.Interaction, membro: discord.Member, atividade: app_commands.Choice[str], quantidade: app_commands.Range[int, 1, 5000], motivo: str):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if len(motivo.strip()) < 5 or len(motivo) > 300:
            await interaction.response.send_message("Informe um motivo entre 5 e 300 caracteres.", ephemeral=True)
            return
        perfil = await self._perfil(interaction.guild.id, membro.id)
        rank_antigo = rank_por_xp(int(perfil.get("xp", 0)))
        perfil["xp"] = int(perfil.get("xp", 0)) + int(quantidade)
        if atividade.value == "missao":
            perfil["missoes"] = int(perfil.get("missoes", 0)) + 1
        elif atividade.value == "guerra":
            perfil["guerras"] = int(perfil.get("guerras", 0)) + 1
        rank_novo = rank_por_xp(perfil["xp"])
        perfil["rank_no"] = rank_novo["no"]
        await self._atualizar_perfil(interaction.guild.id, membro.id, perfil)
        await self._aplicar_cargo_rank(interaction.guild, membro, rank_novo)
        if rank_novo["no"] != rank_antigo["no"]:
            await self._anunciar_rank(interaction.guild, membro, rank_novo, perfil["xp"])
        await interaction.response.send_message(
            f"Atividade registrada para {membro.mention}.\n"
            f"**Tipo:** {atividade.name}\n**Recompensa:** +{quantidade} XP\n"
            f"**Motivo:** {discord.utils.escape_markdown(motivo)}\n"
            f"**Total:** {perfil['xp']:,} XP · **Rank:** No.{rank_novo['no']} — {rank_novo['nome']}".replace(",", "."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(ProgressaoGangue(bot))
