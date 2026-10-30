"""Sistema visual unificado da NÊMESIS para embeds do Discord.

A camada aplica identidade visual visível a todas as embeds que usam criar_embed,
sem substituir a informação específica, os campos ou as ações de cada sistema.
"""
from __future__ import annotations

import discord

COR_PRIMARIA = 0x9F1239  # Carmesim NÊMESIS
COR_SUCESSO = 0x2D9D78
COR_AVISO = 0xD69E2E
COR_ERRO = 0x7F1D2D
COR_NEUTRA = 0x202127
MARCA = "𝐍̷Ê𝐌𝐄𝐒𝐈𝐒"
AUTOR_PADRAO = "✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  CENTRAL DE SISTEMAS"
RODAPE_PADRAO = "◈ NÊMESIS  •  SISTEMAS INTEGRADOS"


def criar_embed(
    title: str | None = None,
    description: str | None = None,
    *,
    cor: int | None = None,
    rodape: str | None = RODAPE_PADRAO,
    **kwargs,
) -> discord.Embed:
    """Cria uma embed com cabeçalho, título e assinatura visual da NÊMESIS."""
    if cor is not None:
        kwargs["color"] = cor
    elif "color" not in kwargs and "colour" not in kwargs:
        kwargs["color"] = COR_PRIMARIA

    if isinstance(kwargs.get("timestamp"), bool):
        kwargs["timestamp"] = discord.utils.utcnow() if kwargs["timestamp"] else None

    # Todos os sistemas recebem timestamp por padrão; chamadas explícitas
    # ainda podem desligá-lo com timestamp=None.
    if "timestamp" not in kwargs:
        kwargs["timestamp"] = discord.utils.utcnow()

    # Um tratamento de título uniforme torna a mudança perceptível, sem duplicar
    # a moldura em títulos que já usam a identidade NÊMESIS.
    if title:
        titulo = title.strip()
        if not titulo.startswith(("✦・", "✦ ", "◈ ", "𝐍̷Ê𝐌𝐄𝐒𝐈𝐒")):
            titulo = f"✦・ {titulo} ・✦"
        title = titulo[:256]

    embed = discord.Embed(title=title, description=description, **kwargs)

    # Autor e rodapé criam uma assinatura visual consistente mesmo quando o
    # sistema define um rodapé próprio.
    if not embed.author.name:
        embed.set_author(name=AUTOR_PADRAO)

    if rodape and not embed.footer.text:
        embed.set_footer(text=rodape[:2048])

    return embed


def cor_por_estado(sucesso: bool, *, aviso: bool = False) -> int:
    if sucesso:
        return COR_SUCESSO
    return COR_AVISO if aviso else COR_ERRO


def embed_sucesso(titulo: str, descricao: str, **kwargs) -> discord.Embed:
    return criar_embed(titulo, descricao, cor=COR_SUCESSO, **kwargs)


def embed_erro(titulo: str, descricao: str, **kwargs) -> discord.Embed:
    return criar_embed(titulo, descricao, cor=COR_ERRO, **kwargs)


def embed_aviso(titulo: str, descricao: str, **kwargs) -> discord.Embed:
    return criar_embed(titulo, descricao, cor=COR_AVISO, **kwargs)


def embed_info(titulo: str, descricao: str, **kwargs) -> discord.Embed:
    return criar_embed(titulo, descricao, cor=COR_PRIMARIA, **kwargs)



def aplicar_identidade_servidor(
    embed: discord.Embed,
    guild: discord.Guild | None,
    bot: discord.Client | None = None,
    *,
    banner: bool = True,
) -> discord.Embed:
    """Aplica banner, ícone do servidor e avatar do bot sem exigir assets configurados."""
    if guild is None:
        return embed

    icone = getattr(guild, "icon", None)
    icone_servidor = icone.url if icone else None
    avatar_bot = None
    usuario_bot = getattr(bot, "user", None) if bot else None
    if usuario_bot:
        avatar = getattr(usuario_bot, "display_avatar", None)
        avatar_bot = avatar.url if avatar else None

    # O ícone do servidor identifica a organização; o avatar do bot assina o painel.
    if icone_servidor:
        embed.set_thumbnail(url=icone_servidor)
    elif avatar_bot:
        embed.set_thumbnail(url=avatar_bot)

    if avatar_bot:
        autor = embed.author
        embed.set_author(
            name=autor.name or "N̷ÊMESIS  •  CENTRAL DE SISTEMAS",
            url=autor.url or discord.Embed.Empty,
            icon_url=avatar_bot,
        )

    banner_servidor = getattr(guild, "banner", None)
    if banner and banner_servidor:
        embed.set_image(url=banner_servidor.url)

    return embed
