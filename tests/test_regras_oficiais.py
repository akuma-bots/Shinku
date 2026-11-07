import re
import unittest

from cogs.regras_oficiais import SECOES_REGRAS, construir_embeds_regras


class TestRegrasOficiais(unittest.TestCase):
    def test_cada_artigo_tem_titulo_nativo_em_embed_propria(self):
        embeds = construir_embeds_regras()
        self.assertEqual(len(embeds), 11)
        self.assertEqual(embeds[0].title, "1 - Conduta e respeito")
        self.assertEqual(embeds[-1].title, "11 - Disposições finais")
        self.assertTrue(all(embed.description for embed in embeds))
        self.assertTrue(all(not (embed.description or "").lstrip().startswith("#") for embed in embeds))
        self.assertTrue(all(len(embed.description or "") <= 4096 for embed in embeds))
        self.assertTrue(all((embed.footer.text or "").startswith("NÊMESIS • Código de Conduta oficial") for embed in embeds))

    def test_publicacao_respeita_limite_de_dez_embeds_por_mensagem(self):
        embeds = construir_embeds_regras()
        lotes = [embeds[:10], embeds[10:]]
        self.assertEqual([len(lote) for lote in lotes], [10, 1])

    def test_codigos_das_regras_consumidos_pelo_automod_foram_preservados(self):
        embeds = construir_embeds_regras()
        texto = "\n".join([embed.title or "" for embed in embeds] + [
            embed.description or "" for embed in embeds
        ])
        encontrados = re.findall(r"(?:^|\n)#\s*(\d+)\s+-\s+([^\n]+)", texto)
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

    def test_regras_nao_dependem_de_comando_slash_para_publicacao(self):
        from cogs.regras_oficiais import RegrasOficiais
        self.assertTrue(hasattr(RegrasOficiais, "sincronizar_regras"))
        self.assertFalse(hasattr(RegrasOficiais, "regras_publicar"))


if __name__ == "__main__":
    unittest.main()
