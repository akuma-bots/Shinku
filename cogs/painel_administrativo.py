"""Central administrativa interativa da NÊMESIS, integrada ao Registro Global."""
from __future__ import annotations

import asyncio
import logging
import time

import discord
from discord.ext import commands

from cogs.status_sistema import _resumo_tarefas_automaticas
from utils.apresentacao import COR_AVISO, COR_ERRO, COR_SUCESSO, criar_embed
from utils.guild_config import (
    CARGOS_LIDERANCA_IDS, GUILD_NEMESIS_ID,
    membro_tem_lideranca, membro_tem_octogono,
)
from utils.registro_global import CATEGORIAS, obter_topico
from utils.storage import UPSTASH_CONFIG_INCOMPLETA, USANDO_UPSTASH, carregar, verificar_conexao_storage

_LOG = logging.getLogger(__name__)
_ARQUIVO_TOPICOS = "registro_global_topicos.json"
_COR_NEMESIS = 0x9F2035

SECOES_ADMINISTRATIVAS = {
    "visao_geral": {
        "titulo": "📊 VISÃO GERAL DA ORGANIZAÇÃO",
        "descricao": "Resumo operacional atualizado no momento da consulta, com acesso às áreas administrativas da NÊMESIS.",
        "topicos": (),
        "canais": (),
    },
    "membros": {
        "titulo": "👥 GESTÃO DE MEMBROS E HIERARQUIA",
        "descricao": "Consulte o dossiê individual, a progressão e a linha do tempo de participação. A auditoria de cargos permanece separada no tópico administrativo.",
        "topicos": ("historico_membros",),
        "canais": (("Progressão e XP", 1563995881315897548),),
    },
    "operacoes": {
        "titulo": "🎯 OPERAÇÕES E DESENVOLVIMENTO",
        "descricao": "Abra as centrais interativas de missões, provas e processos seletivos. A inteligência avançada continua exclusiva do OCTÓGONO.",
        "topicos": ("missoes", "competitivo", "eventos", "parcerias"),
        "canais": (
            ("Missões", 1563995881315897549),
            ("Central de missões", 1556543214885019668),
            ("Envio de provas", 1556543417843056641),
            ("Desafios competitivos", 1545834386128375909),
            ("Agenda", 1563995880623841337),
            ("Inscrições", 1563995880623841338),
            ("Divisões", 1563995880833421511),
            ("Parcerias", 1563995880833421513),
        ),
    },
    "seguranca": {
        "titulo": "🛡️ SEGURANÇA E CONTROLE ADMINISTRATIVO",
        "descricao": "Acompanhe ocorrências de segurança, AutoMod, moderação e decisões administrativas. A central não amplia permissões nem substitui as confirmações dos sistemas existentes.",
        "topicos": ("seguranca", "moderacao", "administracao"),
        "canais": (),
    },
    "sistemas": {
        "titulo": "⚙️ SISTEMAS E INFRAESTRUTURA",
        "descricao": "Consulte a saúde do Shinku e execute verificações do armazenamento. Os diagnósticos são privados e restritos à liderança.",
        "topicos": ("integracoes",),
        "canais": (),
    },
    "registros": {
        "titulo": "📚 AUDITORIA E REGISTROS",
        "descricao": "Consulte auditoria de mensagens, atendimento e registros operacionais consolidados, sem áreas duplicadas.",
        "topicos": ("mensagens", "atendimento", "historico_membros", "eventos", "sugestoes"),
        "canais": (("Canal oficial de sugestões", 1563995881508831336),),
    },
}

# Carmesim e preto em variações profundas; sem cores fora da identidade.
CORES_SECOES = {
    "visao_geral": 0x8B1E2D,
    "membros": 0x991B33,
    "operacoes": 0x741629,
    "seguranca": 0xB3263E,
    "sistemas": 0x252126,
    "registros": 0x5C101F,
}

_ROTULOS_TOPICOS = {
    "historico_membros": "👥 Arquivo de Membros",
    "mensagens": "💬 Comunicação Geral",
    "atendimento": "🎫 Central de Atendimento",
    "moderacao": "⚖️ Tribunal de Moderação",
    "seguranca": "🛡️ Muralha de Segurança",
    "missoes": "🎯 Operações e Missões",
    "competitivo": "🏆 Arena Competitiva",
    "eventos": "🎉 Eventos e Celebrações",
    "administracao": "👑 Central de Administração",
    "parcerias": "🤝 Alianças e Parcerias",
    "integracoes": "⚙️ Sistemas e Integrações",
    "sugestoes": "📋 Sugestões e Ideias",
}


def _tem_acesso(interaction: discord.Interaction, owner_id: int | None = None) -> bool:
    return bool(
        interaction.guild_id == GUILD_NEMESIS_ID
        and (owner_id is None or interaction.user.id == owner_id)
        and membro_tem_lideranca(interaction.user)
    )


def _formatar_uptime(bot: commands.Bot) -> str:
    inicio = getattr(bot.get_cog("StatusSistema"), "_inicio", None)
    if inicio is None:
        return "Indisponível"
    total = max(0, int(time.monotonic() - inicio))
    horas, resto = divmod(total, 3600)
    minutos, segundos = divmod(resto, 60)
    return f"{horas}h {minutos}m {segundos}s"


async def _embed_visao_geral(bot: commands.Bot, guild: discord.Guild) -> discord.Embed:
    falhas_cogs = getattr(bot, "cogs_falhos", [])
    total_tarefas, tarefas_ativas, tarefas_com_falha = _resumo_tarefas_automaticas(bot)
    latencia = round(bot.latency * 1000) if bot.latency is not None else None

    armazenamento = "Não configurado"
    armazenamento_ok = False
    if UPSTASH_CONFIG_INCOMPLETA:
        armazenamento = "Configuração incompleta"
    elif USANDO_UPSTASH:
        try:
            await asyncio.wait_for(verificar_conexao_storage(), timeout=6)
            armazenamento, armazenamento_ok = "Conectado", True
        except Exception as erro:
            armazenamento = f"Indisponível ({type(erro).__name__})"
    else:
        armazenamento = "Local • persistência limitada"

    try:
        dados = await carregar(_ARQUIVO_TOPICOS, {})
        mapa = dados.get(str(guild.id), {}) if isinstance(dados, dict) else {}
        total_topicos = sum(1 for chave in CATEGORIAS if mapa.get(chave))
    except Exception:
        total_topicos = 0

    registro_pronto = bool(getattr(bot.get_cog("Logs"), "_topicos_prontos", False))
    registro_estado = f"{total_topicos}/{len(CATEGORIAS)} áreas" if total_topicos else (
        "Sincronizado" if registro_pronto else "Aguardando sincronização"
    )
    lideranca = sum(
        1 for membro in guild.members
        if any(cargo.id in CARGOS_LIDERANCA_IDS for cargo in getattr(membro, "roles", ()))
    )
    estado_ok = bool(
        bot.is_ready() and not falhas_cogs and armazenamento_ok
        and registro_pronto and tarefas_com_falha == 0
    )
    cor = COR_SUCESSO if estado_ok else COR_AVISO if bot.is_ready() else COR_ERRO
    embed = criar_embed(
        "NÊMESIS • CENTRAL ADMINISTRATIVA",
        "Visão consolidada da organização. Os atalhos levam aos painéis e registros oficiais já existentes.",
        cor=cor, rodape="NÊMESIS • PAINEL ADMINISTRATIVO CENTRAL", timestamp=True,
    )
    embed.add_field(name="◈ ESTADO DO SHINKU", value="🟢 Online" if bot.is_ready() else "🔴 Inicializando", inline=True)
    embed.add_field(name="◈ LATÊNCIA", value=f"{latencia} ms" if latencia is not None else "Indisponível", inline=True)
    embed.add_field(name="◈ TEMPO ATIVO", value=_formatar_uptime(bot), inline=True)
    embed.add_field(name="◈ EFETIVO", value=f"{guild.member_count or len(guild.members):,} membros\n{lideranca:,} em cargos de liderança", inline=True)
    embed.add_field(name="◈ MÓDULOS", value=f"{len(bot.cogs)} carregados\n{len(falhas_cogs)} falhas de carregamento", inline=True)
    embed.add_field(name="◈ TAREFAS", value=f"{tarefas_ativas}/{total_tarefas} em execução\n{tarefas_com_falha} paradas/com falha", inline=True)
    embed.add_field(name="◈ UPSTASH", value=("🟢 " if armazenamento_ok else "🟡 ") + armazenamento, inline=True)
    embed.add_field(name="◈ REGISTRO GLOBAL", value=("🟢 " if registro_pronto else "🟡 ") + registro_estado, inline=True)
    embed.add_field(
        name="◈ PRINCÍPIOS DE AUTORIDADE",
        value=(
            "• Supervisor Staff permanece incluído na liderança administrativa.\n"
            "• Gestão de missões permanece exclusiva do OCTÓGONO.\n"
            "• Promoções, rebaixamentos e banimentos respeitam os cargos acima de Elite e a hierarquia do alvo.\n"
            "• A central apenas organiza o acesso; não concede permissões adicionais."
        ),
        inline=False,
    )
    if falhas_cogs:
        nomes = [str(item.get("cog", "desconhecido")) for item in falhas_cogs[:8] if isinstance(item, dict)]
        embed.add_field(
            name="⚠️ MÓDULOS COM FALHA",
            value="\n".join(f"• {discord.utils.escape_markdown(nome)}" for nome in nomes)[:1024] or "Falha sem identificação.",
            inline=False,
        )
    return embed


async def _embed_secao(bot: commands.Bot, guild: discord.Guild, chave: str):
    secao = SECOES_ADMINISTRATIVAS[chave]
    embed = criar_embed(
        f"NÊMESIS • {secao['titulo']}", secao["descricao"], cor=CORES_SECOES.get(chave, _COR_NEMESIS),
        rodape="NÊMESIS • CENTRAL ADMINISTRATIVA • ACESSO RESTRITO", timestamp=True,
    )
    try:
        dados = await carregar(_ARQUIVO_TOPICOS, {})
        topicos = dados.get(str(guild.id), {}) if isinstance(dados, dict) else {}
    except Exception:
        topicos = {}

    atalhos = []
    for categoria in secao["topicos"]:
        try:
            thread_id = int(topicos.get(categoria)) if topicos.get(categoria) else None
        except (TypeError, ValueError):
            thread_id = None
        if thread_id:
            nome = _ROTULOS_TOPICOS.get(categoria, categoria.replace("_", " ").title())
            atalhos.append((nome, f"https://discord.com/channels/{guild.id}/{thread_id}"))
    for rotulo, canal_id in secao["canais"]:
        atalhos.append((rotulo, f"https://discord.com/channels/{guild.id}/{canal_id}"))

    embed.add_field(
        name="◈ ATALHOS DISPONÍVEIS",
        value="\n".join(f"• {discord.utils.escape_markdown(nome)}" for nome, _ in atalhos)
        if atalhos else "Nenhum destino desta área foi localizado.",
        inline=False,
    )
    embed.add_field(
        name="◈ INTEGRIDADE",
        value="Os fluxos de aprovação e as verificações de autoridade continuam nos sistemas originais.",
        inline=False,
    )
    return embed, atalhos


def _texto_embed_componentes(embed: discord.Embed) -> str:
    """Converte o conteúdo institucional do embed em texto nativo de Components V2."""
    partes = []
    autor = getattr(getattr(embed, "author", None), "name", None)
    titulo = getattr(embed, "title", None)
    descricao = getattr(embed, "description", None)
    if autor:
        partes.append(f"-# {autor}")
    if titulo:
        partes.append(f"## {titulo}")
    if descricao:
        partes.append(descricao)
    for campo in getattr(embed, "fields", ()) or ():
        partes.append(f"**{campo.name}**\n{campo.value}")
    rodape = getattr(getattr(embed, "footer", None), "text", None)
    if rodape:
        partes.append(f"-# {rodape}")
    return "\n\n".join(partes)[:4000] or "Central administrativa da NÊMESIS."


class CentralAdministrativaView(discord.ui.LayoutView):
    """Central privada com navegação e ações contidas no cartão Components V2."""

    def __init__(
        self,
        bot: commands.Bot,
        owner_id: int,
        guild: discord.Guild,
        embed: discord.Embed | None = None,
        *,
        chave: str = "visao_geral",
        atalhos: list[tuple[str, str]] | None = None,
        octogono: bool = False,
    ):
        super().__init__(timeout=300)
        self.bot, self.owner_id, self.guild = bot, owner_id, guild
        if embed is None:
            embed = criar_embed(
                "NÊMESIS • CENTRAL ADMINISTRATIVA",
                "Selecione uma área para consultar os sistemas e registros da organização.",
                rodape="NÊMESIS • PAINEL ADMINISTRATIVO CENTRAL",
            )
        self.chave = chave
        self.seletor = discord.ui.Select(
            placeholder="Navegar pela central administrativa",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Visão geral", value="visao_geral", emoji="📊"),
                discord.SelectOption(label="Membros e hierarquia", value="membros", emoji="👥"),
                discord.SelectOption(label="Operações", value="operacoes", emoji="🎯"),
                discord.SelectOption(label="Segurança", value="seguranca", emoji="🛡️"),
                discord.SelectOption(label="Sistemas e infraestrutura", value="sistemas", emoji="⚙️"),
                discord.SelectOption(label="Auditoria e registros", value="registros", emoji="📚"),
            ],
        )
        self.seletor.callback = self._selecionar_secao

        itens: list = [
            discord.ui.TextDisplay(_texto_embed_componentes(embed)),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("### ◈ NAVEGAÇÃO DA CENTRAL"),
            discord.ui.ActionRow(self.seletor),
        ]

        links = [
            discord.ui.Button(label=rotulo[:80], url=url, style=discord.ButtonStyle.link)
            for rotulo, url in (atalhos or [])[:10]
        ]
        for inicio in range(0, len(links), 5):
            itens.append(discord.ui.ActionRow(*links[inicio:inicio + 5]))

        botoes_acao: list[discord.ui.Button] = []

        def adicionar_acao(label: str, emoji: str, callback):
            botao = discord.ui.Button(
                label=label[:80],
                emoji=emoji,
                style=discord.ButtonStyle.primary,
            )

            async def executar(clique: discord.Interaction):
                if not _tem_acesso(clique, self.owner_id):
                    await clique.response.send_message(
                        "Acesso restrito à liderança autorizada da NÊMESIS.",
                        ephemeral=True,
                    )
                    return
                await callback(clique)

            botao.callback = executar
            botoes_acao.append(botao)

        if chave == "operacoes":
            if octogono:
                async def abrir_inteligencia(clique: discord.Interaction):
                    cog_missoes = self.bot.get_cog("Missoes")
                    if cog_missoes is None:
                        await clique.response.send_message(
                            "O módulo de operações não está disponível no momento.",
                            ephemeral=True,
                        )
                        return
                    await cog_missoes.enviar_painel_inteligencia(clique)
                adicionar_acao("Inteligência de operações", "📈", abrir_inteligencia)

            formularios = bot.get_cog("Formularios")
            if formularios is not None:
                adicionar_acao("Processos seletivos", "📋", formularios.formulario_central)
            gestao = bot.get_cog("GestaoMissoes")
            if gestao is not None and octogono:
                adicionar_acao("Gestão de missões", "🎯", gestao.central_missoes)
            revisoes = bot.get_cog("Revisoes")
            if revisoes is not None:
                adicionar_acao("Revisão de provas", "🧾", revisoes.painel_provas)

        if chave == "sistemas":
            status = bot.get_cog("StatusSistema")
            if status is not None:
                adicionar_acao("Saúde do sistema", "📡", status.status)
                adicionar_acao("Diagnóstico do armazenamento", "🗄️", status.diagnostico)

        for inicio in range(0, len(botoes_acao), 5):
            itens.append(discord.ui.ActionRow(*botoes_acao[inicio:inicio + 5]))

        itens.extend([
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Nêmesis Systeam"),
        ])
        self.add_item(discord.ui.Container(*itens, accent_colour=CORES_SECOES.get(chave, _COR_NEMESIS)))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not _tem_acesso(interaction, self.owner_id):
            await interaction.response.send_message(
                "Acesso restrito à liderança autorizada da NÊMESIS. Abra sua própria central para continuar.",
                ephemeral=True,
            )
            return False
        return True

    async def _selecionar_secao(self, interaction: discord.Interaction):
        chave = self.seletor.values[0]
        await interaction.response.defer()
        try:
            if chave == "visao_geral":
                embed = await _embed_visao_geral(self.bot, self.guild)
                atalhos = []
            else:
                embed, atalhos = await _embed_secao(self.bot, self.guild, chave)
            nova_view = CentralAdministrativaView(
                self.bot,
                self.owner_id,
                self.guild,
                embed,
                chave=chave,
                atalhos=atalhos,
                octogono=membro_tem_octogono(getattr(interaction, "user", None)),
            )
            await interaction.edit_original_response(view=nova_view)
        except Exception:
            _LOG.exception("Falha ao abrir seção %s da Central Administrativa.", chave)
            await interaction.followup.send(
                "Não consegui carregar esta área agora. Tente selecionar novamente.",
                ephemeral=True,
            )


class PainelAdministrativoView(discord.ui.LayoutView):
    """Painel persistente com o botão de acesso dentro do cartão Components V2."""

    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot
        botao = discord.ui.Button(
            label="Abrir Central Administrativa",
            emoji="🏛️",
            style=discord.ButtonStyle.primary,
            custom_id="nemesis:administracao:central:abrir",
        )
        botao.callback = self.abrir_central
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                "## 🏛️ NÊMESIS • CENTRAL ADMINISTRATIVA\n"
                "Área de gestão restrita à liderança autorizada. "
                "Acesse a visão operacional, os membros, as operações, a segurança e os registros."
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(botao),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Nêmesis Systeam"),
            accent_colour=_COR_NEMESIS,
        ))

    async def abrir_central(self, interaction: discord.Interaction):
        if not _tem_acesso(interaction):
            await interaction.response.send_message(
                "Acesso restrito à liderança autorizada da NÊMESIS.", ephemeral=True,
            )
            return
        if interaction.guild is None:
            await interaction.response.send_message(
                "Esta central só funciona dentro da NÊMESIS.", ephemeral=True,
            )
            return
        embed = await _embed_visao_geral(self.bot, interaction.guild)
        await interaction.response.send_message(
            view=CentralAdministrativaView(
                self.bot,
                interaction.user.id,
                interaction.guild,
                embed,
                octogono=membro_tem_octogono(interaction.user),
            ),
            ephemeral=True,
        )



def _mensagem_tem_cartao_administrativo(mensagem: discord.Message) -> bool:
    pendentes = list(getattr(mensagem, "components", []) or [])
    while pendentes:
        item = pendentes.pop()
        conteudo = str(getattr(item, "content", "") or "").casefold()
        if "central administrativa" in conteudo or "centro administrativo" in conteudo:
            return True
        pendentes.extend(list(getattr(item, "children", []) or []))
    return False


class PainelAdministrativo(commands.Cog):
    """Publica e mantém o painel central no tópico canônico de Administração."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._painel_atualizado = False
        self._lock = asyncio.Lock()
        self.bot.add_view(PainelAdministrativoView(bot))

    @commands.Cog.listener()
    async def on_ready(self):
        if self._painel_atualizado:
            return
        async with self._lock:
            if self._painel_atualizado:
                return
            guild = self.bot.get_guild(GUILD_NEMESIS_ID)
            if guild is None:
                _LOG.error("Guild NÊMESIS indisponível; painel administrativo aguardará reconexão.")
                return
            try:
                logs = self.bot.get_cog("Logs")
                for _ in range(120):
                    if bool(getattr(logs, "_topicos_prontos", False)):
                        break
                    if not self.bot.is_ready():
                        return
                    await asyncio.sleep(1)
                else:
                    _LOG.error("Registro Global não ficou pronto a tempo; painel aguardará a próxima conexão.")
                    return

                thread = await obter_topico(guild, "administracao")
                if thread.archived or thread.locked:
                    await thread.edit(
                        archived=False, locked=False,
                        reason="Atualizar painel administrativo central",
                    )
                mensagem = await thread.fetch_message(thread.id)
                if not _mensagem_tem_cartao_administrativo(mensagem):
                    await mensagem.edit(content=None, embeds=[], attachments=[])
                await mensagem.edit(
                    view=PainelAdministrativoView(self.bot),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                self._painel_atualizado = True
                _LOG.info(
                    "Painel Administrativo Central atualizado no tópico Administração (%s).",
                    thread.id,
                )
            except Exception:
                _LOG.exception("Não foi possível atualizar o Painel Administrativo Central.")


async def setup(bot: commands.Bot):
    await bot.add_cog(PainelAdministrativo(bot))
