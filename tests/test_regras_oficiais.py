import re
import unittest

from cogs.regras_oficiais import SECOES_REGRAS, construir_embed_regras


class TestRegrasOficiais(unittest.TestCase):
    def test_todos_os_artigos_ficam_em_uma_unica_embed(self):
        embed = construir_embed_regras()
        self.assertEqual(len(embed.fields), 11)
        self.assertEqual(embed.fields[0].name, "1 - Conduta e respeito")
        self.assertEqual(embed.fields[-1].name, "11 - Disposições finais")
        self.assertTrue(all(field.value for field in embed.fields))
        self.assertTrue(all(len(field.value) <= 1024 for field in embed.fields))
        total = len(embed.title or "") + len(embed.description or "") + len(embed.footer.text or "")
        total += sum(len(field.name) + len(field.value) for field in embed.fields)
        self.assertLessEqual(total, 6000)
    def test_codigos_das_regras_consumidos_pelo_automod_foram_preservados(self):
        embed = construir_embed_regras()
        texto = "\n".join([embed.title or "", embed.description or ""] + [
            parte for field in embed.fields for parte in (field.name, field.value)
        ])
        encontrados = re.findall(r"(?:^|\n)(\d+)\s+-\s+([^\n]+)", texto)
        self.assertEqual([numero for numero, _ in encontrados], [str(i) for i in range(1, 12)])
        self.assertEqual(len(SECOES_REGRAS), 11)

    def test_niveis_disciplinares_correspondem_a_medidas_padrao_do_automod(self):
        texto = construir_embed_regras().fields[9].value
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
