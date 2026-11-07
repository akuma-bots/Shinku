import re
import unittest

from cogs.regras_oficiais import (
    MARCADOR_PUBLICACAO,
    SECOES_REGRAS,
    construir_embed_regras,
)


class TestRegrasOficiais(unittest.TestCase):
    def test_todos_os_artigos_ficam_em_uma_unica_embed(self):
        embed = construir_embed_regras()
        self.assertEqual(len(embed.fields), 11)
        self.assertEqual([campo.name for campo in embed.fields], [titulo for titulo, _ in SECOES_REGRAS])
        self.assertTrue(all(campo.value for campo in embed.fields))
        self.assertTrue(all(len(campo.name) <= 256 for campo in embed.fields))
        self.assertTrue(all(len(campo.value) <= 1024 for campo in embed.fields))
        self.assertLessEqual(len(embed), 6000)
        self.assertTrue(embed.footer.text.startswith(MARCADOR_PUBLICACAO))

    def test_codigos_das_regras_consumidos_pelo_automod_foram_preservados(self):
        texto = "\n".join(campo.name + "\n" + campo.value for campo in construir_embed_regras().fields)
        encontrados = re.findall(r"(?m)^(\d+)\s+-\s+([^\n]+)", texto)
        self.assertEqual([numero for numero, _ in encontrados], [str(i) for i in range(1, 12)])
        self.assertEqual(len(SECOES_REGRAS), 11)

    def test_niveis_disciplinares_correspondem_a_medidas_padrao_do_automod(self):
        texto = construir_embed_regras().fields[9].value
        esperado = (
            "10.1° NÍVEL I — NORMAL",
            "advertência formal",
            "10.2° NÍVEL II — MÉDIO",
            "timeout de 10 minutos",
            "10.3° NÍVEL III — GRAVE",
            "expulsão do servidor",
            "10.4° NÍVEL IV — MUITO GRAVE",
            "banimento temporário de 24 horas",
            "10.5° NÍVEL V — CRÍTICO",
            "banimento permanente",
        )
        for trecho in esperado:
            self.assertIn(trecho.casefold(), texto.casefold())

    def test_todos_os_artigos_sao_campos_na_ordem_oficial(self):
        embed = construir_embed_regras()
        self.assertEqual(embed.fields[0].name, "1 - Conduta e respeito")
        self.assertEqual(embed.fields[-1].name, "11 - Disposições finais")

    def test_regras_nao_dependem_de_comando_slash_para_publicacao(self):
        from cogs.regras_oficiais import RegrasOficiais
        self.assertTrue(hasattr(RegrasOficiais, "sincronizar_regras"))
        self.assertFalse(hasattr(RegrasOficiais, "regras_publicar"))


if __name__ == "__main__":
    unittest.main()