from utils.apresentacao import criar_embed
import asyncio
import hashlib
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from utils import revisoes, auditoria

CORES = {"pvp": 0x9F2035, "pve": 0x8B6A35, "missao": 0x9F2035, "contribuicao": 0x8B6A35, "especial": 0x754A9E}
_ABRIR_REVISAO_LOCK = asyncio.Lock()


async def _hash_imagem(url: str):
    """Baixa a imagem e calcula um hash do conteúdo — usado pra detectar se
    a mesma print está sendo reaproveitada em outra prova."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resposta:
                if resposta.status != 200:
                    return None
                dados = await resposta.read()
                return hashlib.sha256(dados).hexdigest()
    except Exception:
        return None


def _embed_revisao(revisao: dict) -> discord.Embed:
    tipo = str(revisao.get("tipo") or "missao").lower()
    autor_id = revisao.get("autor_id")
    auxiliar_id = revisao.get("auxiliar_id")
    titulo = str(revisao.get("titulo") or "Comprovante de atividade")
    descricao = str(revisao.get("descricao") or "Sem observações adicionais.")
    embed = criar_embed(
        title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  CENTRAL DE VALIDAÇÃO",
        description=(
            f"**◈ COMPROVANTE RECEBIDO**  ·  **{tipo.replace('_', ' ').upper()}**\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"**Atividade:** {titulo}\n"
            f"**Relato do participante:**\n{descricao[:1200]}"
        ),
        color=CORES.get(tipo, 0x9F2035),
    )
    embed.set_author(name="NÊMESIS  /  AUDITORIA DE OPERAÇÕES")
    embed.add_field(name="◈ PARTICIPANTE", value=f"<@{autor_id}>" if autor_id else "Não identificado", inline=True)
    embed.add_field(name="◈ CATEGORIA", value=tipo.replace("_", " ").title(), inline=True)
    embed.add_field(name="◈ PROTOCOLO", value=f"`{revisao.get('id', '—')}`", inline=True)
    embed.add_field(name="◈ REFERÊNCIA", value=f"`{revisao.get('referencia_id') or '—'}`", inline=True)
    if auxiliar_id:
        embed.add_field(name="◈ COLABORADOR", value=f"<@{int(auxiliar_id)}>", inline=True)
    enviado = revisao.get("timestamp")
    if isinstance(enviado, (int, float)):
        embed.add_field(name="◈ RECEBIDO", value=f"<t:{int(enviado)}:F>\n<t:{int(enviado)}:R>", inline=True)
    if revisao.get("motivo_rejeicao"):
        embed.add_field(
            name="◈ MOTIVO DA REJEIÇÃO",
            value=str(revisao.get("motivo_rejeicao"))[:800],
            inline=False,
        )
    if revisao.get("status") == "pendente":
        embed.add_field(
            name="◈ DIRETRIZES DE ANÁLISE",
            value="Confira a autenticidade, a correspondência com o objetivo e a legibilidade da evidência. A recompensa em XP só será aplicada após aprovação.",
            inline=False,
        )
    embed.set_image(url=revisao["print_url"])
    embed.set_footer(text="NÊMESIS  •  CENTRAL DE VALIDAÇÃO  •  DECISÃO REGISTRADA EM AUDITORIA")
    return embed

def _view_revisao(revisao_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Aprovar", style=discord.ButtonStyle.success,
                                     emoji="✅", custom_id=f"revisao:aprovar:{revisao_id}"))
    view.add_item(discord.ui.Button(label="Rejeitar", style=discord.ButtonStyle.danger,
                                     emoji="❌", custom_id=f"revisao:rejeitar:{revisao_id}"))
    return view


STATUS_LABELS = {
    "pendente": ("⏳ Pendentes", 0xFEE75C),
    "aprovada": ("✅ Aprovadas", 0x57F287),
    "rejeitada": ("❌ Recusadas", 0xED4245),
}


def _embed_painel_provas(guild: discord.Guild, status: str, itens: list[dict]) -> discord.Embed:
    label, cor = STATUS_LABELS[status]
    embed = criar_embed(
        title=f"✦・NÊMESIS — ACOMPANHAMENTO DE PROVAS",
        description=f"**Filtro:** {label}\n**Registros encontrados:** {len(itens)}",
        color=cor,
    )
    if not itens:
        embed.add_field(name="Nenhuma prova encontrada", value="Não há provas com este status.", inline=False)
        return embed

    for item in itens[:10]:
        tipo = str(item.get("tipo", "—")).upper()
        autor = f"<@{item.get('autor_id')}>" if item.get("autor_id") else "Desconhecido"
        referencia = str(item.get("referencia_id") or "—")
        enviado = item.get("timestamp")
        data = f"<t:{int(enviado)}:R>" if isinstance(enviado, (int, float)) else "Data indisponível"
        revisor = f"<@{item.get('revisor_id')}>" if item.get("revisor_id") else "—"
        motivo = str(item.get("motivo_rejeicao") or "").strip()
        detalhe = (
            f"**ID da prova:** `{item.get('id', '—')}`\n"
            f"**ID da missão/atividade:** `{referencia}`\n"
            f"**Membro:** {autor} • **Tipo:** {tipo}\n"
            f"**Enviada:** {data} • **Revisor:** {revisor}"
        )
        if status == "rejeitada" and motivo:
            detalhe += f"\n**Motivo:** {motivo[:500]}"
        embed.add_field(
            name=f"{item.get('titulo', 'Prova sem título')}"[:256],
            value=detalhe[:1024],
            inline=False,
        )
    if len(itens) > 10:
        embed.set_footer(text=f"Mostrando 10 de {len(itens)} registros. Use o filtro para consultar cada status.")
    return embed


class FiltroPainelProvas(discord.ui.Select):
    def __init__(self, cog: "Revisoes", guild_id: int, owner_id: int, status: str = "pendente"):
        self.cog = cog
        self.guild_id = guild_id
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label="Pendentes", value="pendente", emoji="⏳", default=status == "pendente"),
            discord.SelectOption(label="Aprovadas", value="aprovada", emoji="✅", default=status == "aprovada"),
            discord.SelectOption(label="Recusadas", value="rejeitada", emoji="❌", default=status == "rejeitada"),
        ]
        super().__init__(placeholder="Filtrar provas por status", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Este painel foi aberto por outro administrador.", ephemeral=True)
            return
        status = self.values[0]
        itens = await revisoes.listar(self.guild_id, status=status)
        itens.sort(key=lambda x: float(x.get("timestamp", 0) or 0), reverse=True)
        view = PainelProvasView(self.cog, self.guild_id, self.owner_id, status)
        await interaction.response.edit_message(embed=_embed_painel_provas(interaction.guild, status, itens), view=view)


class PainelProvasView(discord.ui.View):
    def __init__(self, cog: "Revisoes", guild_id: int, owner_id: int, status: str = "pendente"):
        super().__init__(timeout=300)
        self.add_item(FiltroPainelProvas(cog, guild_id, owner_id, status))

class MotivoRejeicaoModal(discord.ui.Modal, title="Rejeitar comprovante"):
    motivo = discord.ui.TextInput(
        label="Motivo da rejeição",
        placeholder="Explique o que precisa ser corrigido na evidência ou no cumprimento do objetivo.",
        style=discord.TextStyle.paragraph,
        min_length=8,
        max_length=800,
        required=True,
    )

    def __init__(self, guild: discord.Guild, revisao_id: str, mensagem: discord.Message, revisor: discord.Member):
        super().__init__(timeout=300)
        self.guild = guild
        self.revisao_id = revisao_id
        self.mensagem = mensagem
        self.revisor = revisor

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            motivo = str(self.motivo.value).strip()
            revisao = await revisoes.rejeitar(self.guild.id, self.revisao_id, self.revisor.id, motivo)
            if not revisao:
                await interaction.followup.send("Esta prova já foi processada ou não está mais disponível.", ephemeral=True)
                return
            embed = _embed_revisao(revisao)
            embed.color = 0x9F2035
            embed.add_field(name="✕ DECISÃO", value="**REJEITADA**", inline=True)
            embed.add_field(name="◈ RESPONSÁVEL PELA ANÁLISE", value=self.revisor.mention, inline=True)
            embed.add_field(name="◈ JUSTIFICATIVA", value=motivo[:800], inline=False)
            await self.mensagem.edit(embed=embed, view=None)
            await auditoria.registrar(
                self.guild,
                "✕ Comprovante rejeitado",
                f"Atividade: {revisao.get('titulo', '—')}\nTipo: {revisao.get('tipo', '—')}\n"
                f"Participante: <@{revisao.get('autor_id')}>\nRevisor: {self.revisor.mention}\n"
                f"Protocolo: {revisao.get('id', '—')}\nMotivo: {motivo}",
                cor=0x9F2035,
            )
            autor = self.guild.get_member(int(revisao.get("autor_id") or 0))
            if autor:
                try:
                    await autor.send(f"Sua prova para {revisao.get('titulo', 'atividade')} foi rejeitada.\nMotivo: {motivo}\nCorrija os pontos indicados e envie uma nova evidência.")
                except discord.Forbidden:
                    pass
            await interaction.followup.send("A prova foi rejeitada. A justificativa foi registrada na auditoria e enviada ao participante.", ephemeral=True)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Falha ao concluir rejeição da revisão %s.", self.revisao_id)
            await interaction.followup.send("Não foi possível concluir a rejeição. Confira os registros e tente novamente.", ephemeral=True)



class Revisoes(commands.Cog):
    """Motor de aprovação manual por print. Outros cogs (missões, PvP, PvE)
    chamam `abrir_revisao(...)` pra criar a pendência e postar o embed com
    botões no canal certo. Ao abrir, calcula um hash da imagem e avisa o
    revisor se a mesma print já foi usada antes. Quando um admin aprova ou
    rejeita, o processador do tipo é chamado automaticamente, e a decisão
    fica registrada no canal de auditoria (se configurado)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}


    @app_commands.command(name="painel-provas", description="Acompanhar provas de missões e atividades por status.")
    @app_commands.default_permissions(administrator=True)
    async def painel_provas(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Só administradores podem abrir este painel.", ephemeral=True)
            return
        itens = await revisoes.listar(interaction.guild.id, status="pendente")
        itens.sort(key=lambda x: float(x.get("timestamp", 0) or 0), reverse=True)
        await interaction.response.send_message(
            embed=_embed_painel_provas(interaction.guild, "pendente", itens),
            view=PainelProvasView(self, interaction.guild.id, interaction.user.id),
            ephemeral=True,
        )

    async def abrir_revisao(
        self, guild: discord.Guild, canal: discord.abc.Messageable, *,
        tipo: str, autor_id: int, referencia_id: str, print_url: str,
        titulo: str, descricao: str = None, auxiliar_id: int = None
    ) -> dict:
        # Serializa o ciclo completo de localizar/criar/publicar a prova.
        # O lock no storage evita registros duplicados; este lock também evita
        # duas mensagens Discord para o mesmo registro em chamadas concorrentes.
        async with _ABRIR_REVISAO_LOCK:
            return await self._abrir_revisao_sem_lock(
                guild, canal, tipo=tipo, autor_id=autor_id,
                referencia_id=referencia_id, print_url=print_url,
                titulo=titulo, descricao=descricao, auxiliar_id=auxiliar_id,
            )

    async def _abrir_revisao_sem_lock(self, guild: discord.Guild, canal: discord.abc.Messageable, *,
                             tipo: str, autor_id: int, referencia_id: str, print_url: str,
                             titulo: str, descricao: str = None,
                             auxiliar_id: int = None) -> dict:
        # Um desafio PvP só pode gerar uma revisão ativa. Se a publicação
        # falhar depois de persistir a pendência, a nova tentativa reutiliza
        # o mesmo registro em vez de criar uma segunda prova para a mesma luta.
        revisao = None
        if tipo == "pvp":
            existentes = await revisoes.listar(guild.id, status="pendente")
            revisao = next(
                (
                    item for item in existentes
                    if isinstance(item, dict)
                    and item.get("tipo") == "pvp"
                    and str(item.get("referencia_id")) == str(referencia_id)
                ),
                None,
            )
            if revisao and revisao.get("mensagem_id"):
                return revisao

        if revisao is None:
            revisao = await revisoes.criar_pendencia(
                guild.id, tipo, autor_id, referencia_id, print_url, titulo, descricao,
                auxiliar_id=auxiliar_id,
            )

        hash_imagem = await _hash_imagem(revisao.get("print_url") or print_url)
        duplicata = None
        if hash_imagem:
            await revisoes.definir_hash(guild.id, revisao["id"], hash_imagem)
            encontradas = await revisoes.buscar_por_hash(guild.id, hash_imagem, excluir_id=revisao["id"])
            if encontradas:
                duplicata = encontradas[0]

        embed = _embed_revisao(revisao)
        if duplicata:
            embed.add_field(
                name="⚠️ Possível print repetida",
                value=f"Esta mesma imagem já apareceu na revisão `{duplicata['id']}` ({duplicata['status']}). Confira com atenção antes de aprovar.",
                inline=False,
            )

        msg = await canal.send(embed=embed, view=_view_revisao(revisao["id"]))
        await revisoes.definir_mensagem(guild.id, revisao["id"], canal.id, msg.id)
        return revisao

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        data = interaction.data or {}
        custom_id = data.get("custom_id", "")
        if not isinstance(custom_id, str) or not custom_id.startswith("revisao:"):
            return

        if interaction.guild is None:
            return

        permissoes = getattr(interaction.user, "guild_permissions", None)
        if permissoes is None or not permissoes.administrator:
            await interaction.response.send_message("Só administradores podem revisar isso.", ephemeral=True)
            return

        partes = custom_id.split(":", 2)
        if len(partes) != 3 or partes[1] not in {"aprovar", "rejeitar"} or not partes[2]:
            await interaction.response.send_message("Ação de revisão inválida.", ephemeral=True)
            return
        _, acao, revisao_id = partes

        if acao == "rejeitar":
            await interaction.response.send_modal(
                MotivoRejeicaoModal(interaction.guild, revisao_id, interaction.message, interaction.user)
            )
            return

        # A consulta ao storage pode demorar; confirme a interação antes do I/O.
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            revisao = await revisoes.get(interaction.guild.id, revisao_id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Falha ao consultar a revisão %s antes da decisão.", revisao_id
            )
            await interaction.followup.send(
                "Não consegui consultar esta revisão no armazenamento. Nenhuma decisão foi aplicada; tente novamente.",
                ephemeral=True,
            )
            return
        if not revisao:
            await interaction.followup.send("Essa revisão não existe mais.", ephemeral=True)
            return
        if revisao["status"] != "pendente":
            await interaction.followup.send(f"Essa revisão já foi **{revisao['status']}**.", ephemeral=True)
            return

        if acao == "aprovar":
            revisao = await revisoes.aprovar(interaction.guild.id, revisao_id, interaction.user.id)
            if not revisao:
                await interaction.followup.send(
                    "Esta revisão já foi processada por outra interação. Atualize a mensagem antes de tentar novamente.",
                    ephemeral=True,
                )
                return
            processador = self.bot.processadores_revisao.get(revisao["tipo"])
            try:
                if processador is None:
                    raise RuntimeError(
                        f"Não existe processador registrado para revisão do tipo {revisao.get('tipo')!r}."
                    )
                resultado_texto = await processador(interaction.guild, revisao)
            except Exception as erro:
                import logging
                logging.getLogger(__name__).exception(
                    "Falha ao aplicar recompensa da revisão %s (tipo=%s).",
                    revisao_id,
                    revisao.get("tipo"),
                )
                try:
                    reaberta = await revisoes.reabrir_apos_falha_aplicacao(
                        interaction.guild.id,
                        revisao_id,
                        type(erro).__name__,
                    )
                except Exception:
                    reaberta = None
                    logging.getLogger(__name__).exception(
                        "Não foi possível reabrir a revisão %s após falha de aplicação.",
                        revisao_id,
                    )

                mensagem = (
                    "A aplicação falhou e a prova voltou para **pendente**. "
                    "A staff pode clicar em Aprovar novamente após verificar a falha; "
                    "as recompensas de missões e PvP têm proteção contra duplicação."
                    if reaberta
                    else "A aplicação falhou e não consegui reabrir a prova automaticamente. "
                    "A equipe técnica precisa conferir os logs e o estado da revisão."
                )
                await interaction.followup.send(mensagem, ephemeral=True)
                return

            embed = _embed_revisao(revisao)
            embed.color = 0x57F287
            embed.add_field(name="✅ Aprovado por", value=interaction.user.mention, inline=False)
            if resultado_texto:
                embed.add_field(name="Resultado aplicado", value=resultado_texto, inline=False)
            await interaction.message.edit(embed=embed, view=None)

            await auditoria.registrar(
                interaction.guild, "📋 Revisão aprovada",
                f"Tipo: **{revisao['tipo']}**\nAutor: <@{revisao['autor_id']}>\n"
                f"Aprovado por: {interaction.user.mention}\nID: `{revisao['id']}`",
                cor=0x57F287,
            )

        else:
            revisao = await revisoes.rejeitar(interaction.guild.id, revisao_id, interaction.user.id)
            if not revisao:
                await interaction.followup.send(
                    "Esta revisão já foi processada por outra interação. Atualize a mensagem antes de tentar novamente.",
                    ephemeral=True,
                )
                return
            embed = _embed_revisao(revisao)
            embed.color = 0xED4245
            embed.add_field(name="❌ Rejeitado por", value=interaction.user.mention, inline=False)
            await interaction.message.edit(embed=embed, view=None)

            await auditoria.registrar(
                interaction.guild, "📋 Revisão rejeitada",
                f"Tipo: **{revisao['tipo']}**\nAutor: <@{revisao['autor_id']}>\n"
                f"Rejeitado por: {interaction.user.mention}\nID: `{revisao['id']}`",
                cor=0xED4245,
            )

            autor = interaction.guild.get_member(revisao["autor_id"])
            if autor:
                try:
                    await autor.send(
                        f"Sua prova para **{revisao['titulo']}** foi rejeitada. "
                        "Você pode reenviar com uma nova print."
                    )
                except discord.Forbidden:
                    pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Revisoes(bot))