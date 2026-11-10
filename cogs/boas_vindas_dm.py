from utils.apresentacao import criar_embed, COR_PRIMARIA
from utils.preferencias_notificacoes import obter_preferencias, definir_preferencia
from utils.guia_servidores import (
    adicionar_seletor_guia,
    CARGO_VISITANTES_ID,
    NOME_CARGO_VISITANTES,
    TAG_ORG_NEMESIS,
)
import json
import logging
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = int(os.getenv("NEMESIS_GUILD_ID", "1563995879981981817"))
CONVITE_NEMESIS = "https://discord.gg/BJUNuajfrv"
TAG_GANGUE = TAG_ORG_NEMESIS
CAMINHO_CODIGOS = Path(__file__).resolve().parent.parent / "config" / "codigos_jogos.json"


def carregar_catalogo_codigos() -> dict:
    try:
        dados = json.loads(CAMINHO_CODIGOS.read_text(encoding="utf-8"))
        jogos = dados.get("jogos", {})
        if not {"shigaku", "gakuran", "fistborn"}.issubset(jogos):
            raise ValueError("O catálogo precisa conter Shigaku, Gakuran e Fistborn.")
        return dados
    except (OSError, json.JSONDecodeError, ValueError):
        logger.exception("Não foi possível carregar o catálogo de códigos dos jogos.")
        return {"atualizado_em": "indisponível", "jogos": {}}


def _embed_inicio(membro: discord.abc.User) -> discord.Embed:
    embed = criar_embed(
        title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ BEM-VINDO À ORGANIZAÇÃO",
        description=(
            f"Salve, **{discord.utils.escape_markdown(membro.display_name)}**. "
            "Sua entrada na NÊMESIS foi registrada.\n\n"
            "Somos uma organização voltada a jogos de luta, competitividade e interação "
            "entre jogadores. Respeite as regras, acompanhe os anúncios e procure a equipe "
            "pelos canais oficiais quando precisar de suporte."
        ),
        color=COR_PRIMARIA,
    )
    embed.add_field(name="TAG DA ORG", value=f"`{TAG_GANGUE}`", inline=True)
    embed.add_field(name="CARGO DE ENTRADA", value=f"<@&{CARGO_VISITANTES_ID}> (`{NOME_CARGO_VISITANTES}`) é atribuído automaticamente quando você entra.", inline=True)
    embed.add_field(name="PRIMEIROS PASSOS", value=(
        "01. Leia as regras e os comunicados oficiais.\n"
        "02. Ao entrar, você recebe automaticamente o cargo Visitantes.\n"
        "03. Explore os canais pelo seletor de navegação abaixo.\n"
        "04. Abra #Sistemas e consulte o guia Começando na NÊMESIS.\n"
        "05. Consulte os painéis oficiais para acessar os sistemas liberados ao seu cargo."
    ), inline=False)
    embed.add_field(name="◈ GUIA DE NAVEGAÇÃO", value="O seletor abaixo reúne as áreas essenciais em um único menu. Comece por Regras, Como funciona, Divisões e Sistemas; depois explore missões, progressão e atividades.", inline=False)
    embed.add_field(name="CONVITE DO SERVIDOR", value=f"[Entrar na NÊMESIS]({CONVITE_NEMESIS})", inline=False)
    embed.add_field(name="CÓDIGOS DOS JOGOS", value=(
        "Use o menu abaixo para abrir as abas de Shigaku, Gakuran ou Fistborn. "
        "Os códigos podem expirar sem aviso; consulte a fonte indicada em cada aba."
    ), inline=False)
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.set_footer(text="NÊMESIS • TAG DA ORG: NΞM • Integração oficial")
    return embed


def _embed_codigos(chave: str) -> discord.Embed:
    catalogo = carregar_catalogo_codigos()
    jogo = catalogo.get("jogos", {}).get(chave)
    if not jogo:
        return criar_embed(title="NÊMESIS ━ CÓDIGOS", description="O catálogo deste jogo está temporariamente indisponível.", color=COR_PRIMARIA)
    linhas = []
    for item in jogo.get("codigos", []):
        codigo = str(item.get("codigo", "")).strip()
        recompensa = str(item.get("recompensa", "Recompensa não confirmada")).strip()
        if codigo:
            linhas.append(f"`{codigo}` — {recompensa}")
    descricao_codigos = "\n".join(linhas) or "Nenhum código listado no momento."
    semana = catalogo.get("semana_referente", {})
    periodo = ""
    if semana.get("inicio") and semana.get("fim"):
        periodo = f"\n**Semana dos códigos:** {semana['inicio']} até {semana['fim']}"
    embed = criar_embed(
        title=f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ CÓDIGOS / {jogo['nome'].upper()}",
        description=(f"{jogo.get('descricao', '')}\n\n**Verificado em:** {catalogo.get('atualizado_em', 'indisponível')}{periodo}\n\n{descricao_codigos}")[:4096],
        color=COR_PRIMARIA,
        url=jogo.get("fonte"),
    )
    embed.add_field(name="REQUISITOS E COMO RESGATAR", value=str(jogo.get("requisitos", "Confira os requisitos dentro do jogo."))[:1024], inline=False)
    embed.add_field(name="ATENÇÃO", value=(
        "A lista é uma referência comunitária e não garante que cada código ainda funcione. "
        "Respeite maiúsculas/minúsculas e não inclua espaços extras. Se aparecer expirado "
        "ou já resgatado, o bot não consegue reativá-lo."
    ), inline=False)
    fonte = jogo.get("fonte")
    if fonte:
        embed.add_field(name="FONTE PARA CONFERIR ATUALIZAÇÕES", value=f"[Abrir lista de referência]({fonte})", inline=False)
    embed.set_footer(text=f"NÊMESIS • Códigos {jogo['nome']} • Consulte a fonte para mudanças recentes")
    return embed


class SeletorBoasVindas(discord.ui.Select):
    def __init__(self, autor_id: int, selecionado: str = "inicio"):
        self.autor_id = autor_id
        opcoes = [
            discord.SelectOption(label="Boas-vindas e tutorial", value="inicio", description="Conheça a NÊMESIS e veja como começar", default=selecionado == "inicio"),
            discord.SelectOption(label="Shigaku", value="shigaku", description="Códigos, requisitos e resgate", default=selecionado == "shigaku"),
            discord.SelectOption(label="Gakuran", value="gakuran", description="Códigos, requisitos e resgate", default=selecionado == "gakuran"),
            discord.SelectOption(label="Fistborn", value="fistborn", description="Códigos, requisitos e resgate", default=selecionado == "fistborn"),
        ]
        super().__init__(placeholder="Consulte também os códigos dos jogos", options=opcoes, min_values=1, max_values=1, row=4)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.autor_id:
            await interaction.response.send_message("Esta mensagem de boas-vindas foi enviada para outra pessoa.", ephemeral=True)
            return
        chave = self.values[0]
        await interaction.response.edit_message(
            view=BoasVindasLayoutView(interaction.user, self.autor_id, chave)
        )



def _reconstruir_cartao_preferencias(mensagem: discord.Message, botao: discord.ui.Button) -> discord.ui.LayoutView:
    """Preserva texto, seletores e atalhos ao atualizar a preferência por DM."""
    texto = ""
    pendentes = list(getattr(mensagem, "components", []) or [])
    while pendentes:
        item = pendentes.pop(0)
        conteudo = str(getattr(item, "content", "") or "").strip()
        if conteudo and not texto:
            texto = conteudo
        pendentes.extend(list(getattr(item, "children", []) or []))

    origem = getattr(botao, "view", None)
    itens = []
    pendentes = list(getattr(origem, "children", []) or [])
    while pendentes:
        item = pendentes.pop(0)
        if isinstance(item, (discord.ui.Button, discord.ui.Select)):
            itens.append(item)
        else:
            pendentes.extend(list(getattr(item, "children", []) or []))

    componentes = [
        discord.ui.TextDisplay(
            (texto or "## NÊMESIS • NOTAS DE ATUALIZAÇÃO\nConfigure o recebimento de comunicados automáticos.")[:3900]
        ),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ]
    seletores = []
    botoes_link = []
    botoes_acao = []
    for original in itens:
        if isinstance(original, discord.ui.UserSelect):
            novo = discord.ui.UserSelect(
                placeholder=original.placeholder, min_values=original.min_values,
                max_values=original.max_values, custom_id=original.custom_id,
                disabled=original.disabled,
            )
            async def callback(interaction, item=original, clone=novo):
                item._values = clone._values
                if hasattr(clone, "_resolved"):
                    item._resolved = clone._resolved
                await item.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(original, discord.ui.RoleSelect):
            novo = discord.ui.RoleSelect(
                placeholder=original.placeholder, min_values=original.min_values,
                max_values=original.max_values, custom_id=original.custom_id,
                disabled=original.disabled,
            )
            async def callback(interaction, item=original, clone=novo):
                item._values = clone._values
                if hasattr(clone, "_resolved"):
                    item._resolved = clone._resolved
                await item.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(original, discord.ui.ChannelSelect):
            novo = discord.ui.ChannelSelect(
                placeholder=original.placeholder, min_values=original.min_values,
                max_values=original.max_values, channel_types=list(original.channel_types),
                custom_id=original.custom_id, disabled=original.disabled,
            )
            async def callback(interaction, item=original, clone=novo):
                item._values = clone._values
                if hasattr(clone, "_resolved"):
                    item._resolved = clone._resolved
                await item.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(original, discord.ui.MentionableSelect):
            novo = discord.ui.MentionableSelect(
                placeholder=original.placeholder, min_values=original.min_values,
                max_values=original.max_values, custom_id=original.custom_id,
                disabled=original.disabled,
            )
            async def callback(interaction, item=original, clone=novo):
                item._values = clone._values
                if hasattr(clone, "_resolved"):
                    item._resolved = clone._resolved
                await item.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(original, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=original.placeholder, min_values=original.min_values,
                max_values=original.max_values, options=list(original.options),
                custom_id=original.custom_id, disabled=original.disabled,
            )
            async def callback(interaction, item=original, clone=novo):
                item._values = clone._values
                if hasattr(clone, "_resolved"):
                    item._resolved = clone._resolved
                await item.callback(interaction)
            novo.callback = callback
            seletores.append(novo)
        elif isinstance(original, discord.ui.Button):
            fonte = botao if original.custom_id == botao.custom_id else original
            novo = discord.ui.Button(
                label=fonte.label, style=fonte.style, disabled=fonte.disabled,
                custom_id=fonte.custom_id, url=fonte.url, emoji=fonte.emoji,
            )
            callback = getattr(fonte, "callback", None)
            if callback is not None and not fonte.url:
                novo.callback = callback
            (botoes_link if fonte.url else botoes_acao).append(novo)

    for seletor in seletores:
        componentes.append(discord.ui.ActionRow(seletor))
    if botoes_link:
        componentes.append(discord.ui.ActionRow(*botoes_link[:5]))
    for inicio in range(0, len(botoes_acao), 5):
        componentes.append(discord.ui.ActionRow(*botoes_acao[inicio:inicio + 5]))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# Nêmesis Systeam"),
    ])
    layout = discord.ui.LayoutView(timeout=None)
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    return layout

class AlternarAvisosButton(discord.ui.Button):
    """Alterna o recebimento das notas automáticas diretamente pela mensagem."""

    def __init__(self):
        super().__init__(
            label="Configurar recebimento de notas",
            style=discord.ButtonStyle.secondary,
            emoji="🔔",
            custom_id="nemesis:alternar_notas_dm",
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        preferencias = await obter_preferencias(GUILD_NEMESIS_ID, interaction.user.id)
        novo_estado = not preferencias["notas_atualizacao"]
        await definir_preferencia(
            GUILD_NEMESIS_ID, interaction.user.id, "notas_atualizacao", novo_estado
        )
        self.label = "Desativar notas por DM" if novo_estado else "Ativar notas por DM"
        self.emoji = "🔕" if novo_estado else "🔔"
        self.style = (
            discord.ButtonStyle.success if novo_estado
            else discord.ButtonStyle.secondary
        )
        await interaction.response.edit_message(
            view=_reconstruir_cartao_preferencias(interaction.message, self)
        )
        estado = "ativadas" if novo_estado else "desativadas"
        await interaction.followup.send(
            f"**Notas automáticas por DM {estado}.** "
            "Você pode alterar essa preferência novamente pelo mesmo botão nesta mensagem.",
            ephemeral=True,
        )


class OptOutView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(AlternarAvisosButton())


class BoasVindasView(discord.ui.View):
    def __init__(self, autor_id: int, selecionado: str = "inicio"):
        super().__init__(timeout=900)
        adicionar_seletor_guia(self)
        self.add_item(SeletorBoasVindas(autor_id, selecionado))
        self.add_item(AlternarAvisosButton())



class BoasVindasLayoutView(discord.ui.LayoutView):
    """Cartão de integração com navegação e preferências dentro do próprio painel."""

    def __init__(self, membro: discord.abc.User, autor_id: int, selecionado: str = "inicio"):
        super().__init__(timeout=900)
        embed = _embed_inicio(membro) if selecionado == "inicio" else _embed_codigos(selecionado)
        linhas = [f"## {embed.title or 'INTEGRAÇÃO NÊMESIS'}"]
        if embed.description:
            linhas.append(embed.description)
        for campo in embed.fields:
            linhas.append(f"**{campo.name}**\n{campo.value}")
        guia = adicionar_seletor_guia(discord.ui.View(timeout=900)).children[0]
        seletor = SeletorBoasVindas(autor_id, selecionado)
        avisos = AlternarAvisosButton()
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay("\n\n".join(linhas)[:3900]),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("### ◈ NAVEGAÇÃO DA ORGANIZAÇÃO"),
            discord.ui.ActionRow(guia),
            discord.ui.ActionRow(seletor),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(avisos),
            discord.ui.TextDisplay("-# NÊMESIS • INTEGRAÇÃO OFICIAL • NΞM"),
            accent_colour=0x9F1239,
        ))


class BoasVindasDM(commands.Cog):
    """Envia boas-vindas por DM quando uma pessoa entra no servidor da NÊMESIS."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        if membro.bot or membro.guild.id != GUILD_NEMESIS_ID:
            return
        try:
            await membro.send(view=BoasVindasLayoutView(membro, membro.id), allowed_mentions=discord.AllowedMentions.none())
            logger.info("DM de boas-vindas enviada (guild=%s, user=%s).", membro.guild.id, membro.id)
        except discord.Forbidden:
            logger.info("DM de boas-vindas bloqueada pelo usuário (guild=%s, user=%s).", membro.guild.id, membro.id)
        except discord.HTTPException:
            logger.exception("Falha HTTP ao enviar DM de boas-vindas (guild=%s, user=%s).", membro.guild.id, membro.id)


async def setup(bot: commands.Bot):
    bot.add_view(OptOutView())
    await bot.add_cog(BoasVindasDM(bot))
