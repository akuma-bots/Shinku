from utils.apresentacao import criar_embed\nfrom utils.preferencias_notificacoes import desativar_todas
from utils.guia_servidores import (
    adicionar_botoes_guia,
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
CONVITE_NEMESIS = "https://discord.gg/WsfjRQPhAg"
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
        color=0x9F1239,
    )
    embed.add_field(name="TAG DA ORG", value=f"`{TAG_GANGUE}`", inline=True)
    embed.add_field(name="CARGO DE ENTRADA", value=f"<@&{CARGO_VISITANTES_ID}> (`{NOME_CARGO_VISITANTES}`) é atribuído automaticamente quando você entra.", inline=True)
    embed.add_field(name="PRIMEIROS PASSOS", value=(
        "01. Leia as regras e os comunicados oficiais.\n"
        "02. Ao entrar, você recebe automaticamente o cargo Visitantes.\n"
        "03. Explore os canais pelos botões de navegação abaixo.\n"
        "04. Abra #Sistemas e consulte o guia Começando na NÊMESIS.\n"
        "05. Use /help para localizar os comandos liberados ao seu cargo."
    ), inline=False)
    embed.add_field(name="◈ GUIA DE NAVEGAÇÃO", value="Os botões abaixo levam diretamente às áreas essenciais. Comece por Regras, Como funciona, Divisões e Sistemas; depois explore missões, progressão e atividades.", inline=False)
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
        return criar_embed(title="NÊMESIS ━ CÓDIGOS", description="O catálogo deste jogo está temporariamente indisponível.", color=0x9F1239)
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
        color=0x9F1239,
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
        view = BoasVindasView(self.autor_id, chave)
        embed = _embed_inicio(interaction.user) if chave == "inicio" else _embed_codigos(chave)
        await interaction.response.edit_message(embed=embed, view=view)


class OptOutView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DesativarAvisosButton())


class BoasVindasView(discord.ui.View):
    def __init__(self, autor_id: int, selecionado: str = "inicio"):
        super().__init__(timeout=900)
        adicionar_botoes_guia(self)
        self.add_item(SeletorBoasVindas(autor_id, selecionado))


class BoasVindasDM(commands.Cog):
    """Envia boas-vindas por DM quando uma pessoa entra no servidor da NÊMESIS."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="codigos", description="Consultar códigos de Shigaku, Gakuran e Fistborn.")
    @app_commands.guild_only()
    async def consultar_codigos(self, interaction: discord.Interaction):
        """Abre a central interativa de códigos para consulta a qualquer momento."""
        if interaction.guild_id != GUILD_NEMESIS_ID:
            await interaction.response.send_message(
                "Este sistema está disponível apenas no servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=_embed_codigos("shigaku"),
            view=BoasVindasView(interaction.user.id, "shigaku"),
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.Cog.listener()
    async def on_member_join(self, membro: discord.Member):
        if membro.bot or membro.guild.id != GUILD_NEMESIS_ID:
            return
        try:
            await membro.send(embed=_embed_inicio(membro), view=BoasVindasView(membro.id), allowed_mentions=discord.AllowedMentions.none())
            logger.info("DM de boas-vindas enviada (guild=%s, user=%s).", membro.guild.id, membro.id)
        except discord.Forbidden:
            logger.info("DM de boas-vindas bloqueada pelo usuário (guild=%s, user=%s).", membro.guild.id, membro.id)
        except discord.HTTPException:
            logger.exception("Falha HTTP ao enviar DM de boas-vindas (guild=%s, user=%s).", membro.guild.id, membro.id)


async def setup(bot: commands.Bot):
    await bot.add_cog(BoasVindasDM(bot))
