import discord

from utils.apresentacao import (
    COR_ERRO,
    COR_PRIMARIA,
    COR_SUCESSO,
    cor_por_estado,
    criar_embed,
)


def test_criar_embed_aplica_padrao_visual():
    embed = criar_embed("Teste", "Descrição")

    assert embed.title == "Teste"
    assert embed.description == "Descrição"
    assert embed.color.value == COR_PRIMARIA
    assert embed.footer.text == "𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  •  SISTEMA INTEGRADO"


def test_criar_embed_respeita_cor_rodape_e_timestamp():
    embed = criar_embed("Teste", cor=COR_SUCESSO, rodape="Administração", timestamp=True)

    assert embed.color.value == COR_SUCESSO
    assert embed.footer.text == "Administração"
    assert embed.timestamp is not None


def test_cores_semanticas():
    assert cor_por_estado(True) == COR_SUCESSO
    assert cor_por_estado(False) == COR_ERRO
    assert cor_por_estado(False, aviso=True) != COR_ERRO
