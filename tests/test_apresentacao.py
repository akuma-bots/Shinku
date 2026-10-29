import discord

from utils.apresentacao import (
    COR_ERRO,
    COR_PRIMARIA,
    COR_SUCESSO,
    cor_por_estado,
    criar_embed,
    embed_aviso,
    embed_erro,
    embed_info,
    embed_sucesso,
)


def test_criar_embed_aplica_padrao_visual():
    embed = criar_embed("Teste", "Descrição")

    assert embed.title == "✦・ Teste ・✦"
    assert embed.description == "Descrição"
    assert embed.color.value == COR_PRIMARIA
    assert embed.author.name == "✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  CENTRAL DE SISTEMAS"
    assert embed.timestamp is not None
    assert embed.footer.text == "◈ NÊMESIS  •  SISTEMAS INTEGRADOS"


def test_criar_embed_respeita_cor_rodape_e_timestamp():
    embed = criar_embed("Teste", cor=COR_SUCESSO, rodape="Administração", timestamp=True)

    assert embed.color.value == COR_SUCESSO
    assert embed.footer.text == "Administração"
    assert embed.timestamp is not None


def test_cores_semanticas():
    assert cor_por_estado(True) == COR_SUCESSO
    assert cor_por_estado(False) == COR_ERRO
    assert cor_por_estado(False, aviso=True) != COR_ERRO


def test_respostas_semanticas_usam_cores_consistentes():
    assert embed_sucesso("OK", "Concluído").color.value == COR_SUCESSO
    assert embed_erro("Falha", "Não concluído").color.value == COR_ERRO
    assert embed_aviso("Atenção", "Verifique").color.value != COR_ERRO
    assert embed_info("Informação", "Detalhes").color.value == COR_PRIMARIA


def test_respostas_semanticas_preservam_assinatura_visual():
    for embed in (
        embed_sucesso("OK", "Concluído"),
        embed_erro("Falha", "Não concluído"),
        embed_aviso("Atenção", "Verifique"),
        embed_info("Informação", "Detalhes"),
    ):
        assert embed.footer.text == "◈ NÊMESIS  •  SISTEMAS INTEGRADOS"
        assert embed.author.name == "✦・𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  /  CENTRAL DE SISTEMAS"
        assert embed.title.endswith("・✦")
