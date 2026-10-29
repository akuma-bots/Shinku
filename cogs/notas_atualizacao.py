from utils.apresentacao import criar_embed
import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)
GUILD_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
COLOR = 0xB3132B
SEND_DELAY = 1.0
MAX_RETRIES = 3

# Notas públicas: comunicar resultados e benefícios, nunca o histórico interno de execução.
VERSAO_PADRAO = "1.5.22"
RESUMO_PADRAO = "Proteção administrativa reforçada no AutoMod e auditoria mais clara das ações automáticas."
NOVIDADES_PADRAO = [
    "AutoMod interrompe a análise antes de qualquer ação para membros com permissões administrativas ou de moderação, incluindo permissões específicas do servidor.",
    "Verificação redundante imediatamente antes da exclusão da mensagem; ações canceladas pela proteção ficam registradas no log técnico.",
    "Arquivo de recordes reorganizado com categorias identificáveis, valores formatados e apresentação consistente com a identidade NÊMESIS.",
    "Configuração do canal de recordes agora confirma a alteração em um painel informativo padronizado.",
    "Painel /sistema status agora apresenta latência, tempo ativo, comandos do servidor e estado dos módulos em uma única leitura.",
    "Diagnóstico de armazenamento apresenta resultados com identidade visual consistente e instruções mais claras para cada cenário.",
    "Tutorial de perfil orienta quais informações enviar ao suporte para facilitar a investigação de divergências.",
    "AutoMod com verificação final de isenção administrativa imediatamente antes de excluir uma mensagem.",
    "Registro técnico quando uma ação automática é interrompida pela proteção administrativa.",
    "Sistema de notas reorganizado para destacar somente novidades, recursos e melhorias percebidas pelos membros.",
    "Atualizações apresentadas em linguagem clara, com foco no que mudou e no benefício para a comunidade.",
    "Identidade visual da NÊMESIS mantida em preto e vermelho, com títulos e seções mais consistentes.",
    "Sistema de avaliação de tickets aprimorado, com apresentação organizada da nota, comentário e responsável pelo atendimento.",
    "Experiência de entrada de novos integrantes redesenhada com orientações iniciais e informações essenciais.",
    "Ranking de convites aprimorado para exibir os integrantes convidados que ainda permanecem no servidor.",
    "Progressão competitiva organizada em 12 patentes, com requisitos graduais de experiência.",
    "Central de ajuda aprimorada para facilitar a localização de comandos e subcomandos.",
]
CORRECOES_PADRAO = [
    "Ampliada a proteção contra exclusões automáticas indevidas para cargos com gerência de canais, cargos, webhooks, auditoria, threads, expulsões, banimentos e timeout.",
    "Formatação numérica do arquivo de recordes ajustada para o padrão brasileiro, com separadores de milhar e decimais corretos.",
    "O sistema de recordes trata falhas de anúncio sem interromper o fluxo de atualização das estatísticas.",
    "Padronizada a apresentação do diagnóstico do sistema para diferenciar estados operacionais, alertas e falhas.",
    "Reforçada a barreira de segurança para reduzir exclusões automáticas indevidas em contas com permissões administrativas.",
    "Corrigida a apresentação das notas para reduzir repetições e evitar excesso de informações técnicas.",
    "Corrigido o limite de conteúdo dos embeds para prevenir falhas ao exibir atualizações extensas.",
    "Aprimorado o tratamento de falhas no envio para que problemas de entrega não interrompam todo o processo.",
    "Corrigida a exibição do ranking de convites para evitar erros ao limitar os resultados.",
    "Melhorada a consistência visual e textual entre as seções das notas de atualização.",
]


def _chunks(lines: list[str], prefix: str, limit: int = 950) -> list[str]:
    chunks: list[str] = []
    current = ""
    for raw in lines:
        safe = discord.utils.escape_markdown(raw.strip())
        if not safe:
            continue
        line = f"{prefix} {safe}"
        if len(line) > limit:
            line = line[: limit - 3] + "..."
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _adicionar_secao(embed: discord.Embed, titulo: str, linhas: list[str], prefixo: str):
    for index, bloco in enumerate(_chunks(linhas, prefixo)):
        nome = titulo if index == 0 else f"{titulo} • continuação {index + 1}"
        embed.add_field(name=nome[:256], value=bloco or "—", inline=False)


def _criar_embed(versao: str, resumo: str, novidades: list[str], correcoes: list[str]) -> discord.Embed:
    """Monta um embed com margem de segurança abaixo do limite de 6.000 caracteres."""
    embed = criar_embed(
        title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOTAS DE ATUALIZAÇÃO ・✦",
        description=f"⟡・ **{discord.utils.escape_markdown(versao)}**\\n{discord.utils.escape_markdown(resumo)[:700]}",
        color=COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    _adicionar_secao(embed, "✦ NOVIDADES RECENTES", novidades[:8], "➜")
    if correcoes:
        _adicionar_secao(embed, "⚙ CORREÇÕES E MELHORIAS", correcoes[:5], "✓")
    embed.set_footer(text="NÊMESIS • Notas oficiais de atualização")
    while len(embed) > 5700 and embed.fields:
        embed.remove_field(len(embed.fields) - 1)
    if len(embed) > 5900:
        embed.description = (embed.description or "")[:500]
    return embed

async def _enviar_nota(member: discord.Member, embed: discord.Embed) -> str:
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            await member.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return "enviada"
        except (discord.Forbidden, discord.NotFound):
            return "bloqueada"
        except discord.HTTPException as erro:
            if erro.status and 400 <= erro.status < 500 and erro.status != 429:
                return "bloqueada"
            if tentativa == MAX_RETRIES:
                log.warning("Falha ao enviar nota (guild=%s, member=%s).", member.guild.id, member.id, exc_info=True)
                return "falha"
            espera = min(2 ** (tentativa - 1), 8)
            retry_after = getattr(erro, "retry_after", None)
            if isinstance(retry_after, (int, float)):
                espera = max(espera, min(float(retry_after), 30))
            await asyncio.sleep(espera)
        except (asyncio.TimeoutError, OSError, discord.ConnectionClosed):
            if tentativa == MAX_RETRIES:
                log.warning("Falha de conexão ao enviar nota (guild=%s, member=%s).", member.guild.id, member.id, exc_info=True)
                return "falha"
            await asyncio.sleep(min(2 ** (tentativa - 1), 8))
    return "falha"


class ConfirmarEnvioNotas(discord.ui.View):
    def __init__(self, cog: "NotasAtualizacao", guild_id: int, autor_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.autor_id = autor_id

    @discord.ui.button(label="Enviar atualização por DM", style=discord.ButtonStyle.danger, emoji="📨")
    async def enviar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("Somente quem preparou esta nota pode confirmar o envio.", ephemeral=True)
            return
        if interaction.guild_id != self.guild_id or not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Apenas um administrador da NÊMESIS pode confirmar o envio.", ephemeral=True)
            return
        if self.guild_id in self.cog._sending:
            await interaction.response.send_message("Já existe um envio de notas em andamento.", ephemeral=True)
            return

        self.cog._sending.add(self.guild_id)
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Envio confirmado. Preparando a lista de membros…", view=self)
        try:
            guild = interaction.guild
            membros = [m async for m in guild.fetch_members(limit=None) if not m.bot]
        except discord.HTTPException:
            self.cog._sending.discard(self.guild_id)
            log.exception("Falha ao carregar membros para envio das notas.")
            await interaction.followup.send("Não consegui carregar todos os membros. Nenhuma nota foi enviada.", ephemeral=True)
            return

        embed = _criar_embed(VERSAO_PADRAO, RESUMO_PADRAO, NOVIDADES_PADRAO, CORRECOES_PADRAO)
        entregues = bloqueadas = falhas = 0
        try:
            total = len(membros)
            for index, member in enumerate(membros, start=1):
                resultado = await _enviar_nota(member, embed)
                if resultado == "enviada":
                    entregues += 1
                elif resultado == "bloqueada":
                    bloqueadas += 1
                else:
                    falhas += 1
                if index % 25 == 0 and index < total:
                    try:
                        await interaction.edit_original_response(content=f"**Enviando notas {VERSAO_PADRAO}**\nProcessados: **{index}/{total}** · Entregues: **{entregues}** · Bloqueadas: **{bloqueadas}** · Falhas: **{falhas}**", view=self)
                    except discord.HTTPException:
                        log.debug("Não foi possível atualizar o progresso do envio.")
                await asyncio.sleep(SEND_DELAY)
        finally:
            self.cog._sending.discard(self.guild_id)

        log.info("Notas concluídas (guild=%s, versao=%s, total=%s, entregues=%s, bloqueadas=%s, falhas=%s, autor=%s).", self.guild_id, VERSAO_PADRAO, len(membros), entregues, bloqueadas, falhas, interaction.user.id)
        await interaction.edit_original_response(
            content=f"**Notas processadas — {VERSAO_PADRAO}**\n"
            f"• Membros humanos: **{len(membros)}**\n• Entregues: **{entregues}**\n"
            f"• DMs bloqueadas/indisponíveis: **{bloqueadas}**\n• Falhas após tentativas: **{falhas}**",
            view=self,
        )

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary, emoji="✖")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("Somente quem preparou esta nota pode cancelar.", ephemeral=True)
            return
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(content="Envio cancelado. Nenhuma DM foi enviada.", view=self)
        self.stop()


class NotasAtualizacao(commands.Cog):
    """Prepara um modelo oficial pronto e envia após confirmação explícita."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sending: set[int] = set()

    @app_commands.command(name="notas-atualizacao", description="Abrir as notas prontas da última atualização da NÊMESIS.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def notas_atualizacao(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID or interaction.guild is None:
            await interaction.response.send_message("Comando exclusivo da NÊMESIS.", ephemeral=True)
            return
        if not isinstance(interaction.user, discord.Member) or not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Somente administradores podem usar este comando.", ephemeral=True)
            return
        if interaction.guild_id in self._sending:
            await interaction.response.send_message("Já existe um envio de notas em andamento. Aguarde a conclusão.", ephemeral=True)
            return

        embed = _criar_embed(VERSAO_PADRAO, RESUMO_PADRAO, NOVIDADES_PADRAO, CORRECOES_PADRAO)
        view = ConfirmarEnvioNotas(self, interaction.guild_id, interaction.user.id)
        await interaction.response.send_message(
            "Modelo da atualização pronto. Revise a nota abaixo e clique em **Enviar atualização por DM** para enviar a todos os membros humanos. Nenhuma DM será enviada antes da confirmação.",
            embed=embed,
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(NotasAtualizacao(bot))
