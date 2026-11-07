import re
import unittest

from cogs.regras_oficiais import (
    MARCADOR_PUBLICACAO,
    SECOES_REGRAS,
    agrupar_embeds_regras,
    construir_embed_regras,
    construir_embeds_regras,
)


class TestRegrasOficiais(unittest.TestCase):
    def test_cada_artigo_usa_o_titulo_nativo_da_embed(self):
        embeds = construir_embeds_regras()
        self.assertEqual(len(embeds), 11)
        self.assertEqual([embed.title for embed in embeds], [titulo for titulo, _ in SECOES_REGRAS])
        self.assertTrue(all(not embed.fields for embed in embeds))
        self.assertTrue(all(embed.description for embed in embeds))
        self.assertTrue(all(
            embed.footer.text.startswith(MARCADOR_PUBLICACAO)
            for embed in embeds
        ))
        self.assertTrue(all(len(embed) <= 6000 for embed in embeds))

    def test_artigos_sao_agrupados_dentro_dos_limites_de_cada_mensagem(self):
        lotes = agrupar_embeds_regras(construir_embeds_regras())
        self.assertGreaterEqual(len(lotes), 2)
        self.assertEqual(sum(len(lote) for lote in lotes), 11)
        for lote in lotes:
            self.assertLessEqual(len(lote), 10)
            self.assertLessEqual(sum(len(embed) for embed in lote), 6000)

    def test_codigos_das_regras_consumidos_pelo_automod_foram_preservados(self):
        texto = "\\n".join(
            [embed.title or "", embed.description or ""]
            for embed in construir_embeds_regras()
        )
        encontrados = re.findall(r"(?m)^(\\d+)\\s+-\\s+([^\\n]+)", texto)
        self.assertEqual([numero for numero, _ in encontrados], [str(i) for i in range(1, 12)])
        self.assertEqual(len(SECOES_REGRAS), 11)

    def test_niveis_disciplinares_correspondem_a_medidas_padrao_do_automod(self):
        texto = construir_embeds_regras()[9].description
        esperado = (
            "10.1° Nível I — Normal",
            "advertência formal",
            "10.2° Nível II — Médio",
            "timeout de 10 minutos",
            "10.3° Nível III — Grave",
            "expulsão do servidor",
            "10.4° Nível IV — Muito grave",
            "banimento temporário de 24 horas",
            "10.5° Nível V — Crítico",
            "banimento permanente",
        )
        for trecho in esperado:
            self.assertIn(trecho.casefold(), texto.casefold())

    def test_compatibilidade_com_a_funcao_antiga(self):
        self.assertEqual(construir_embed_regras().title, SECOES_REGRAS[0][0])

    def test_regras_nao_dependem_de_comando_slash_para_publicacao(self):
        from cogs.regras_oficiais import RegrasOficiais
        self.assertTrue(hasattr(RegrasOficiais, "sincronizar_regras"))
        self.assertFalse(hasattr(RegrasOficiais, "regras_publicar"))


if __name__ == "__main__":
    unittest.main()
