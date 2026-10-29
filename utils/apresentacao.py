"""Padrões visuais compartilhados para mensagens e embeds da NÊMESIS.

O construtor compatível mantém os argumentos de discord.Embed e aplica uma
assinatura visual comum sem interferir em campos, cores semânticas ou ações.
"""

import discord

COR_PRIMARIA = 0xB51F32
COR_SUCESSO = 0x2D9D78
COR_AVISO = 0xD69E2E
COR_ERRO = 0xC0392B
COR_NEUTRA = 0x24252B
RODAPE_PADRAO = "𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  •  SISTEMA INTEGRADO"


def criar_embed(
    title: str | None = None,
    description: str | None = None,
    *,
    cor: int | None = None,
    rodape: str | None = RODAPE_PADRAO,
    **kwargs,
) -> discord.Embed:
    """Cria uma embed Discord com identidade visual padrão da NÊMESIS.

    Aceita os argumentos posicionais e nomeados de discord.Embed para facilitar
    a adoção gradual em todos os módulos, mantendo compatibilidade com chamadas
    existentes. O parâmetro cor é um alias em português para color.
    """
    if cor is not None:
        kwargs["color"] = cor
    elif "color" not in kwargs and "colour" not in kwargs:
        kwargs["color"] = COR_PRIMARIA

    # Compatibilidade com a API anterior, que aceitava timestamp=True/False.
    if isinstance(kwargs.get("timestamp"), bool):
        kwargs["timestamp"] = discord.utils.utcnow() if kwargs["timestamp"] else None

    embed = discord.Embed(title=title, description=description, **kwargs)
    if rodape and not embed.footer.text:
        embed.set_footer(text=rodape[:2048])
    return embed


def cor_por_estado(sucesso: bool, *, aviso: bool = False) -> int:
    """Retorna uma cor semântica consistente para sucesso, aviso ou erro."""
    if sucesso:
        return COR_SUCESSO
    return COR_AVISO if aviso else COR_ERRO


def embed_sucesso(titulo: str, descricao: str, **kwargs) -> discord.Embed:
    """Resposta visual de conclusão, com cor semântica de sucesso."""
    return criar_embed(titulo, descricao, cor=COR_SUCESSO, **kwargs)


def embed_erro(titulo: str, descricao: str, **kwargs) -> discord.Embed:
    """Resposta visual de falha ou operação recusada."""
    return criar_embed(titulo, descricao, cor=COR_ERRO, **kwargs)


def embed_aviso(titulo: str, descricao: str, **kwargs) -> discord.Embed:
    """Resposta visual para alertas que exigem atenção."""
    return criar_embed(titulo, descricao, cor=COR_AVISO, **kwargs)


def embed_info(titulo: str, descricao: str, **kwargs) -> discord.Embed:
    """Resposta visual informativa no padrão primário da NÊMESIS."""
    return criar_embed(titulo, descricao, cor=COR_PRIMARIA, **kwargs)
