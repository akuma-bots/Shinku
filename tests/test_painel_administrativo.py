import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cogs.painel_administrativo import (
    CentralAdministrativaView,
    PainelAdministrativo,
    PainelAdministrativoView,
    SECOES_ADMINISTRATIVAS,
    _tem_acesso,
)


class TestPainelAdministrativoCentral(unittest.TestCase):
    def test_painel_publico_e_persistente_sem_comando_slash(self):
        painel = PainelAdministrativoView(SimpleNamespace())
        self.assertIsNone(painel.timeout)
        self.assertEqual(len(painel.children), 1)
        self.assertEqual(
            painel.children[0].custom_id,
            "nemesis:administracao:central:abrir",
        )
        self.assertEqual(PainelAdministrativo.__cog_app_commands__, [])

    def test_central_privada_tem_seis_areas_de_navegacao(self):
        view = CentralAdministrativaView(
            SimpleNamespace(),
            owner_id=123,
            guild=SimpleNamespace(id=1563995879981981817),
        )
        self.assertEqual(view.timeout, 300)
        self.assertEqual(len(view.seletor.options), 6)
        self.assertEqual(
            {opcao.value for opcao in view.seletor.options},
            set(SECOES_ADMINISTRATIVAS),
        )

    def test_areas_tem_destinos_de_auditoria_e_descricao(self):
        for chave, secao in SECOES_ADMINISTRATIVAS.items():
            with self.subTest(secao=chave):
                self.assertTrue(secao["titulo"])
                self.assertTrue(secao["descricao"])
                self.assertIsInstance(secao["topicos"], tuple)
                self.assertIsInstance(secao["canais"], tuple)
        self.assertIn("historico_membros", SECOES_ADMINISTRATIVAS["membros"]["topicos"])
        self.assertIn("missoes", SECOES_ADMINISTRATIVAS["operacoes"]["topicos"])
        self.assertIn("seguranca", SECOES_ADMINISTRATIVAS["seguranca"]["topicos"])
        self.assertNotIn("automod", SECOES_ADMINISTRATIVAS["seguranca"]["topicos"])
        self.assertIn("infraestrutura", SECOES_ADMINISTRATIVAS["sistemas"]["topicos"])

    def test_autorizacao_exige_servidor_e_lideranca(self):
        membro = SimpleNamespace(id=123)
        with patch("cogs.painel_administrativo.membro_tem_lideranca", return_value=True):
            self.assertTrue(_tem_acesso(SimpleNamespace(guild_id=1563995879981981817, user=membro)))
            self.assertFalse(_tem_acesso(SimpleNamespace(guild_id=1, user=membro)))
            self.assertFalse(_tem_acesso(SimpleNamespace(guild_id=1563995879981981817, user=membro), owner_id=456))
        with patch("cogs.painel_administrativo.membro_tem_lideranca", return_value=False):
            self.assertFalse(_tem_acesso(SimpleNamespace(guild_id=1563995879981981817, user=membro)))


if __name__ == "__main__":
    unittest.main()
