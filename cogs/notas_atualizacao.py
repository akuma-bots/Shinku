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

# Modelo pronto referente às melhorias já aplicadas ao bot da NÊMESIS.
VERSAO_PADRAO = "1.4.6"
RESUMO_PADRAO = "Correção de segurança no AutoMod e auditoria de mensagens mais clara."
NOVIDADES_PADRAO = [
    "AutoMod agora ignora mensagens do proprietário e de membros com permissão Administrador, evitando exclusões e punições automáticas indevidas.",
    "Permissões parciais de moderação não concedem isenção total do AutoMod; a exceção é restrita ao proprietário e administradores do servidor.",
    "Logs de mensagens são registros de auditoria: não executam exclusão nem punição, e continuam documentando mensagens removidas por outros agentes quando o evento é recebido.",
    "Central /help aprimorada para listar também subcomandos dentro de grupos slash, com caminho completo do comando para facilitar a identificação.",
    "Anti-raid aprimorado: picos de entrada e contas recentes geram alerta para revisão da equipe, sem expulsão automática baseada apenas na idade da conta.",
    "Alertas de segurança explicam o motivo da sinalização e registram o caso nos logs técnicos para facilitar a investigação.",
    "Sistema de entrada integrado ao rastreamento de convites, reunindo membro e convidador em uma única mensagem quando identificável.",
    "Comando /convites para consultar convidados que continuam no servidor.",
    "Ranking de convites baseado apenas nos convidados atualmente presentes na NÊMESIS.",
    "Histórico persistente por ID do Discord: sair desconta o membro e reentrar restaura o vínculo original sem duplicar.",
    "Mensagem de entrada redesenhada com ícone da NÊMESIS, avatar, membro, convidador identificado e guia /tutorial.",
    "Falhas ao enviar a mensagem de entrada agora ficam registradas explicitamente nos logs técnicos.",
    "Canal oficial de progressão atualizado para o ID fornecido pela liderança.",
    "Embed de novo membro com ícone da NÊMESIS, avatar do membro, título, descrição, convidador e orientação para o guia do servidor.",
    "Atribuição automática dos três cargos-base aos membros humanos que entram no servidor.",
    "Verificação dos membros existentes para completar a atribuição dos cargos-base em caso de ausência.",
    "Registro de entrada enviado ao canal de logs configurado, com falhas de canal e permissão registradas nos logs técnicos.",
    "Modelo de notas da versão atual mantido pronto para revisão e envio pelo comando administrativo.",
    "Ranking de convites corrigido para filtrar e limitar os resultados sem erro de execução.",
    "Mensagem de entrada direcionada ao canal oficial 1563995880623841331, independentemente do canal geral de logs.",
    "Sistema de entrada redesenhado com identidade visual preto e vermelho, identificação do membro, total de integrantes, registro temporal e próximos passos.",
]
CORRECOES_PADRAO = [
    "Corrigida a execução do listener principal do AutoMod para encerrar a análise antes de acumular histórico, aplicar cooldown ou tentar excluir mensagens administrativas.",
    "A central de ajuda não omite mais subcomandos apenas por estarem agrupados em comandos slash.",
    "Reduzido o risco de expulsões indevidas durante falsos positivos de raid; a decisão de punição permanece com a equipe responsável.",
    "Contagem de convites alterada para considerar somente membros presentes no servidor.",
    "Saída de membro remove sua participação da contagem ativa, preservando o convidador original para uma eventual reentrada.",
    "Comando pessoal renomeado para /convites; entradas repetidas do mesmo ID não criam convites duplicados.",
    "A atribuição de convites só contabiliza casos identificados com segurança, evitando atribuições ambíguas.",
    "Falhas ao publicar a mensagem de entrada ficam explícitas nos logs técnicos.",
    "Corrigido o ID antigo do canal de progressão que causava erro na inicialização e nos anúncios de rank.",
    "Corrigido o filtro dos 10 primeiros colocados no ranking de convites: o gerador agora é materializado antes do fatiamento.",
    "Validação do destino de entrada para evitar publicação em canal inválido ou fora da NÊMESIS.",
    "Conteúdo da mensagem de entrada reorganizado para melhorar legibilidade, apresentação e orientação inicial sem alterar o destino configurado.",
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
    embed = discord.Embed(
        title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOTAS DE ATUALIZAÇÃO ・✦",
        description=f"⟡・ **{discord.utils.escape_markdown(versao)}**\n{discord.utils.escape_markdown(resumo)}",
        color=COLOR,
        timestamp=datetime.now(timezone.utc),
    )
    _adicionar_secao(embed, "✦ NOVIDADES", novidades, "➜")
    if correcoes:
        _adicionar_secao(embed, "⚙ CORREÇÕES E MELHORIAS", correcoes, "✓")
    embed.set_footer(text="NÊMESIS • Notas oficiais de atualização")
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
