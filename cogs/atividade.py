import asyncio
import logging
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.storage import carregar, salvar

log = logging.getLogger(__name__)

GUILD_ID = 1543381737961160910
CANAL_ATIVIDADE_ID = 1545833111860936804
ARQUIVO = "atividade_check.json"
MAX_SESSOES_HISTORICO = 500


def _dados_padrao() -> dict:
    return {"sessoes": {}, "membros": {}}


class BotaoRegistrarAtividade(discord.ui.View):
    """Botão persistente: continua funcional depois de reiniciar o bot."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Registrar atividade",
        style=discord.ButtonStyle.success,
        emoji="✓",
        custom_id="nemesis:atividade:registrar:v1",
    )
    async def registrar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        await self.cog.registrar_participacao(interaction)


class SistemaAtividade(commands.Cog):
    """Activity Check persistente da NÊMESIS no canal definido."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        self._view = BotaoRegistrarAtividade(self)

    async def cog_load(self):
        self.bot.add_view(self._view)
        if not self._verificar_expiracoes.is_running():
            self._verificar_expiracoes.start()

    def cog_unload(self):
        self._verificar_expiracoes.cancel()

    async def _carregar(self) -> dict:
        dados = await carregar(ARQUIVO, _dados_padrao())
        if not isinstance(dados, dict):
            dados = _dados_padrao()
        dados.setdefault("sessoes", {})
        dados.setdefault("membros", {})
        return dados

    async def _salvar(self, dados: dict):
        await salvar(ARQUIVO, dados)

    async def _fechar_sessao(self, message_id: str, motivo: str = "prazo"):
        async with self._lock:
            dados = await self._carregar()
            sessao = dados["sessoes"].get(message_id)
            if not isinstance(sessao, dict) or sessao.get("status") != "aberta":
                return False
            sessao["status"] = "encerrada"
            sessao["encerrada_em"] = time.time()
            sessao["motivo_encerramento"] = motivo
            await self._salvar(dados)
            sessao_final = dict(sessao)

        canal = self.bot.get_channel(int(sessao_final.get("canal_id", 0)))
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(int(sessao_final.get("canal_id", 0)))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                canal = None

        if canal is not None:
            try:
                mensagem = await canal.fetch_message(int(message_id))
                embed = self._embed_sessao(sessao_final, encerrada=True)
                await mensagem.edit(embed=embed, view=None)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                log.warning("Não foi possível atualizar a mensagem de atividade %s.", message_id)
        return True

    def _embed_sessao(self, sessao: dict, encerrada: bool = False) -> discord.Embed:
        participantes = sessao.get("participantes", [])
        prazo = int(sessao.get("expira_em", time.time()))
        status = "ENCERRADA" if encerrada or sessao.get("status") != "aberta" else "EM ANDAMENTO"
        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ ACTIVITY CHECK",
            description=(
                "Confirme sua presença clicando no botão abaixo. "
                "Cada membro pode registrar sua participação uma única vez nesta chamada."
            ),
            color=0xB51F32 if status == "EM ANDAMENTO" else 0x747F8D,
        )
        embed.add_field(name="◈ STATUS", value=status, inline=True)
        embed.add_field(name="◈ PARTICIPANTES", value=str(len(participantes)), inline=True)
        embed.add_field(name="◈ PRAZO", value=f"<t:{prazo}:R>", inline=True)
        observacao = str(sessao.get("observacao", "")).strip()
        if observacao:
            embed.add_field(name="◈ INFORMAÇÕES", value=discord.utils.escape_mentions(observacao)[:1024], inline=False)
        embed.set_footer(text="NÊMESIS • Registro de atividade")
        return embed

    @app_commands.command(
        name="atividade-iniciar",
        description="Abre um Activity Check no canal oficial da NÊMESIS.",
    )
    @app_commands.describe(
        duracao="Duração da chamada em minutos (5 a 1440)",
        observacao="Recado ou instrução opcional para os membros",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def atividade_iniciar(
        self,
        interaction: discord.Interaction,
        duracao: app_commands.Range[int, 5, 1440] = 30,
        observacao: str = "",
    ):
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            await interaction.response.send_message(
                "Este sistema só pode ser usado no servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        canal = interaction.guild.get_channel(CANAL_ATIVIDADE_ID)
        if not isinstance(canal, discord.TextChannel):
            await interaction.response.send_message(
                "O canal configurado para atividade não foi encontrado ou não é um canal de texto.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        agora = time.time()
        expira_em = agora + int(duracao) * 60

        async with self._lock:
            dados = await self._carregar()
            aberta = next(
                (
                    sessao for sessao in dados["sessoes"].values()
                    if isinstance(sessao, dict)
                    and sessao.get("status") == "aberta"
                    and int(sessao.get("expira_em", 0) or 0) > agora
                ),
                None,
            )
        if aberta:
            await interaction.followup.send(
                "Já existe um Activity Check em andamento. Aguarde o encerramento antes de abrir outro.",
                ephemeral=True,
            )
            return

        sessao = {
            "guild_id": GUILD_ID,
            "canal_id": canal.id,
            "criador_id": interaction.user.id,
            "criado_em": agora,
            "expira_em": expira_em,
            "status": "aberta",
            "observacao": observacao[:1000].strip(),
            "participantes": [],
        }
        mensagem = await canal.send(embed=self._embed_sessao(sessao))
        sessao["message_id"] = str(mensagem.id)

        async with self._lock:
            dados = await self._carregar()
            # Segunda verificação para evitar duas chamadas simultâneas.
            existe_aberta = any(
                isinstance(item, dict)
                and item.get("status") == "aberta"
                and int(item.get("expira_em", 0) or 0) > time.time()
                for item in dados["sessoes"].values()
            )
            if existe_aberta:
                try:
                    await mensagem.delete()
                except discord.HTTPException:
                    pass
                await interaction.followup.send(
                    "Outra chamada foi aberta ao mesmo tempo. Nenhuma chamada duplicada foi mantida.",
                    ephemeral=True,
                )
                return
            dados["sessoes"][str(mensagem.id)] = sessao
            if len(dados["sessoes"]) > MAX_SESSOES_HISTORICO:
                encerradas = sorted(
                    (
                        (key, value) for key, value in dados["sessoes"].items()
                        if isinstance(value, dict) and value.get("status") != "aberta"
                    ),
                    key=lambda item: float(item[1].get("encerrada_em", item[1].get("criado_em", 0)) or 0),
                )
                for key, _ in encerradas[:len(dados["sessoes"]) - MAX_SESSOES_HISTORICO]:
                    dados["sessoes"].pop(key, None)
            await self._salvar(dados)

        await mensagem.edit(embed=self._embed_sessao(sessao), view=self._view)
        await interaction.followup.send(
            f"Activity Check publicado em {canal.mention}, com encerramento em <t:{int(expira_em)}:R>.",
            ephemeral=True,
        )

    async def registrar_participacao(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            await interaction.response.send_message(
                "Este botão pertence ao servidor da NÊMESIS.",
                ephemeral=True,
            )
            return
        if interaction.channel_id != CANAL_ATIVIDADE_ID or interaction.message is None:
            await interaction.response.send_message(
                "A participação só pode ser registrada no canal oficial de atividade.",
                ephemeral=True,
            )
            return

        message_id = str(interaction.message.id)
        usuario_id = str(interaction.user.id)
        agora = time.time()

        async with self._lock:
            dados = await self._carregar()
            sessao = dados["sessoes"].get(message_id)
            if not isinstance(sessao, dict):
                await interaction.response.send_message(
                    "Esta chamada não foi encontrada no registro. Se ela estiver antiga, peça à Staff para abrir outra.",
                    ephemeral=True,
                )
                return
            if sessao.get("status") != "aberta" or agora >= float(sessao.get("expira_em", 0) or 0):
                await interaction.response.send_message(
                    "O prazo desta chamada terminou.",
                    ephemeral=True,
                )
                return

            participantes = sessao.setdefault("participantes", [])
            if usuario_id in participantes:
                await interaction.response.send_message(
                    "Sua participação já está registrada nesta chamada.",
                    ephemeral=True,
                )
                return

            participantes.append(usuario_id)
            membros = dados["membros"].setdefault(usuario_id, {
                "registros": 0,
                "ultima_participacao": None,
                "historico": [],
            })
            membros["registros"] = int(membros.get("registros", 0) or 0) + 1
            membros["ultima_participacao"] = agora
            historico = membros.setdefault("historico", [])
            historico.append({
                "message_id": message_id,
                "guild_id": GUILD_ID,
                "registrado_em": agora,
            })
            membros["historico"] = historico[-MAX_SESSOES_HISTORICO:]
            await self._salvar(dados)
            sessao_atualizada = dict(sessao)

        await interaction.response.send_message(
            "Participação registrada. Sua presença foi salva no sistema de atividade da NÊMESIS.",
            ephemeral=True,
        )
        try:
            await interaction.message.edit(
                embed=self._embed_sessao(sessao_atualizada),
                view=self._view,
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            log.warning("Não foi possível atualizar a contagem da chamada %s.", message_id)

    @app_commands.command(
        name="atividade-ranking",
        description="Mostra o ranking geral, semanal ou mensal de atividade.",
    )
    @app_commands.describe(
        limite="Quantidade de membros no ranking (1 a 20)",
        periodo="Período usado para calcular as participações",
    )
    @app_commands.choices(periodo=[
        app_commands.Choice(name="Geral", value="geral"),
        app_commands.Choice(name="Últimos 7 dias", value="semanal"),
        app_commands.Choice(name="Últimos 30 dias", value="mensal"),
    ])
    async def atividade_ranking(
        self,
        interaction: discord.Interaction,
        limite: app_commands.Range[int, 1, 20] = 10,
        periodo: app_commands.Choice[str] = None,
    ):
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            await interaction.response.send_message(
                "Este comando só pode ser usado no servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        periodo_valor = periodo.value if periodo else "geral"
        agora = time.time()
        janela = {"semanal": 7 * 86400, "mensal": 30 * 86400}.get(periodo_valor)
        dados = await self._carregar()
        ordenados = []
        for uid, perfil in dados["membros"].items():
            if not isinstance(perfil, dict):
                continue
            if janela is None:
                total = int(perfil.get("registros", 0) or 0)
            else:
                total = sum(
                    1 for registro in perfil.get("historico", [])
                    if isinstance(registro, dict)
                    and agora - janela < float(registro.get("registrado_em", 0) or 0) <= agora
                )
            if total:
                ordenados.append((uid, perfil, total))

        ordenados.sort(
            key=lambda item: (
                item[2],
                float(item[1].get("ultima_participacao", 0) or 0),
            ),
            reverse=True,
        )
        ordenados = ordenados[:int(limite)]

        rotulos = {"geral": "GERAL", "semanal": "SEMANAL · 7 DIAS", "mensal": "MENSAL · 30 DIAS"}
        embed = discord.Embed(
            title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ RANKING {rotulos[periodo_valor]}",
            description="Participações confirmadas nos Activity Checks oficiais.",
            color=0xB51F32,
        )
        if not ordenados:
            embed.description = "Nenhuma participação encontrada para este período."
        else:
            linhas = []
            for posicao, (uid, perfil, total) in enumerate(ordenados, start=1):
                membro = interaction.guild.get_member(int(uid))
                nome = membro.mention if membro else f"<@{uid}>"
                linhas.append(f"**{posicao}.** {nome} — **{total}** participação(ões)")
            embed.add_field(name="◈ CLASSIFICAÇÃO", value="\n".join(linhas)[:1024], inline=False)
        embed.set_footer(text="NÊMESIS • Ranking calculado a partir dos registros persistidos.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="atividade-consultar",
        description="Consulta o total de participações de um membro nos Activity Checks.",
    )
    @app_commands.describe(membro="Membro que deseja consultar")
    async def atividade_consultar(
        self,
        interaction: discord.Interaction,
        membro: discord.Member = None,
    ):
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            await interaction.response.send_message(
                "Este comando só pode ser usado no servidor da NÊMESIS.",
                ephemeral=True,
            )
            return
        alvo = membro or interaction.user
        dados = await self._carregar()
        perfil = dados["membros"].get(str(alvo.id), {})
        registros = int(perfil.get("registros", 0) or 0) if isinstance(perfil, dict) else 0
        ultima = perfil.get("ultima_participacao") if isinstance(perfil, dict) else None
        embed = discord.Embed(
            title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ ATIVIDADE DE {alvo.display_name.upper()}"[:256],
            color=0xB51F32,
        )
        embed.set_thumbnail(url=alvo.display_avatar.url)
        embed.add_field(name="◈ PARTICIPAÇÕES", value=str(registros), inline=True)
        embed.add_field(
            name="◈ ÚLTIMO REGISTRO",
            value=f"<t:{int(ultima)}:R>" if ultima else "Nenhum registro",
            inline=True,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="atividade-encerrar",
        description="Encerra imediatamente a chamada de atividade em andamento.",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def atividade_encerrar(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            await interaction.response.send_message(
                "Este comando só pode ser usado no servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        async with self._lock:
            dados = await self._carregar()
            agora = time.time()
            aberta = next(
                (
                    (message_id, sessao)
                    for message_id, sessao in dados["sessoes"].items()
                    if isinstance(sessao, dict)
                    and sessao.get("status") == "aberta"
                    and float(sessao.get("expira_em", 0) or 0) > agora
                ),
                None,
            )
        if aberta is None:
            await interaction.followup.send("Não há nenhuma chamada de atividade em andamento.", ephemeral=True)
            return

        fechada = await self._fechar_sessao(aberta[0], motivo=f"encerrada_por:{interaction.user.id}")
        if fechada:
            await interaction.followup.send("A chamada de atividade foi encerrada e o botão de registro foi desativado.", ephemeral=True)
        else:
            await interaction.followup.send("A chamada já havia sido encerrada.", ephemeral=True)

    @app_commands.command(
        name="atividade-relatorio",
        description="Mostra um resumo administrativo do sistema de atividade.",
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    async def atividade_relatorio(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != GUILD_ID:
            await interaction.response.send_message(
                "Este comando só pode ser usado no servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        dados = await self._carregar()
        sessoes = [s for s in dados["sessoes"].values() if isinstance(s, dict)]
        agora = time.time()
        abertas = sum(
            1 for s in sessoes
            if s.get("status") == "aberta" and float(s.get("expira_em", 0) or 0) > agora
        )
        encerradas = sum(1 for s in sessoes if s.get("status") == "encerrada")
        total_presencas = sum(
            len(set(s.get("participantes", [])))
            for s in sessoes
            if isinstance(s.get("participantes", []), list)
        )
        ativos_7_dias = sum(
            1 for perfil in dados["membros"].values()
            if isinstance(perfil, dict)
            and any(
                isinstance(registro, dict)
                and agora - 7 * 86400 < float(registro.get("registrado_em", 0) or 0) <= agora
                for registro in perfil.get("historico", [])
            )
        )
        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ RELATÓRIO DE ATIVIDADE",
            description="Resumo do funcionamento e das participações registradas.",
            color=0xB51F32,
        )
        embed.add_field(name="◈ CHAMADAS REGISTRADAS", value=str(len(sessoes)), inline=True)
        embed.add_field(name="◈ EM ANDAMENTO", value=str(abertas), inline=True)
        embed.add_field(name="◈ ENCERRADAS", value=str(encerradas), inline=True)
        embed.add_field(name="◈ PRESENÇAS REGISTRADAS", value=str(total_presencas), inline=True)
        embed.add_field(name="◈ MEMBROS ATIVOS · 7 DIAS", value=str(ativos_7_dias), inline=True)
        embed.add_field(name="◈ MEMBROS NO HISTÓRICO", value=str(len(dados["membros"])), inline=True)
        embed.set_footer(text="Relatório administrativo • acesso restrito à Staff")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tasks.loop(seconds=30)
    async def _verificar_expiracoes(self):
        agora = time.time()
        async with self._lock:
            dados = await self._carregar()
            expiradas = [
                message_id for message_id, sessao in dados["sessoes"].items()
                if isinstance(sessao, dict)
                and sessao.get("status") == "aberta"
                and float(sessao.get("expira_em", 0) or 0) <= agora
            ]
        for message_id in expiradas:
            try:
                await self._fechar_sessao(message_id)
            except Exception:
                log.exception("Falha ao encerrar Activity Check %s.", message_id)

    @_verificar_expiracoes.before_loop
    async def _antes_verificar_expiracoes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(SistemaAtividade(bot))
