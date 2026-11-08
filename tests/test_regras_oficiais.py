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

    def test_numeracao_simples_dos_artigos_e_itens(self):
        embed = construir_embed_regras()
        self.assertEqual(
            [campo.name for campo in embed.fields],
            [
                "1 Conduta", "2 Comunicação e organização",
                "3 Conteúdo e segurança digital", "4 Privacidade e identidade",
                "5 Divulgação e parcerias", "6 Atendimento e denúncias",
                "7 Staff, hierarquia e autoridade",
                "8 Competições, missões e sistemas",
                "9 Reincidência e agravantes", "10 Punições",
                "11 Disposições finais",
            ],
        )
        self.assertTrue(embed.fields[0].value.startswith("1 "))
        self.assertIn("\n\n2 ", embed.fields[0].value)

    def test_sete_niveis_de_punicao_na_ordem_solicitada(self):
        texto = construir_embed_regras().fields[9].value
        esperado = (
            "1 Punições Níveis:",
            "Nível I: Silenciamento",
            "Nível II: Remoção de cargo",
            "Nível III: Suspensão de atividades",
            "Nível IV: Expulsão do servidor",
            "Nível V: Banimento temporário de 24 horas",
            "Nível VI: Banimento temporário de 7 dias",
            "Nível VII: Banimento permanente",
        )
        for trecho in esperado:
            self.assertIn(trecho.casefold(), texto.casefold())

    def test_regras_nao_dependem_de_comando_slash_para_publicacao(self):
        from cogs.regras_oficiais import RegrasOficiais
        self.assertTrue(hasattr(RegrasOficiais, "sincronizar_regras"))
        self.assertFalse(hasattr(RegrasOficiais, "regras_publicar"))


if __name__ == "__main__":
    unittest.main()