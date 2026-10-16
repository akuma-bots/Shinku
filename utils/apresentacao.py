"""Padrões visuais compartilhados para mensagens e embeds da NÊMESIS."""

import discord

COR_PRIMARIA = 0xB51F32
COR_SUCESSO = 0x2D9D78
COR_AVISO = 0xD69E2E
COR_ERRO = 0xC0392B
COR_NEUTRA = 0x36393F
RODAPE_PADRAO = "NÊMESIS • Sistema integrado"


def criar_embed(
    titulo: str,
    descricao: str | None = None,
    *,
    cor: int = COR_PRIMARIA,
    rodape: str | None = RODAPE_PADRAO,
    timestamp: bool = False,
) -> discord.Embed:
    """Cria uma embed com cores e rodapé consistentes em todos os sistemas."""
    embed = discord.Embed(
        title=(titulo or "NÊMESIS")[:256],
        description=descricao or None,
        color=cor,
        timestamp=discord.utils.utcnow() if timestamp else None,
    )
    if rodape:
        embed.set_footer(text=rodape[:2048])
    return embed


def cor_por_estado(sucesso: bool, *, aviso: bool = False) -> int:
    """Retorna uma cor semântica consistente para sucesso, aviso ou erro."""
    if sucesso:
        return COR_SUCESSO
    return COR_AVISO if aviso else COR_ERRO
