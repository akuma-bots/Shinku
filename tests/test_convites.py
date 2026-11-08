import unittest

from cogs.convites import (
    PainelConsultaConvitesView,
    SeletorConvitesView,
    _resumo,
    _total_paginas,
)
from cogs.convites import CANAL_CONVITES_ID


class TestConsultaIndividualConvites(unittest.TestCase):
    def test_painel_persistente_e_seletor_privado(self):
        painel = PainelConsultaConvitesView()
        seletor = SeletorConvitesView(123)
        self.assertIsNone(painel.timeout)
        self.assertEqual(painel.children[0].custom_id, "nemesis:convites:abrir")
        self.assertEqual(
            seletor.children[0].custom_id, "nemesis:convites:membro:selecionar"
        )

    def test_painel_aponta_para_canal_oficial_de_convites(self):
        self.assertEqual(CANAL_CONVITES_ID, 1563995880623841332)

    def test_resumo_separa_historico_de_convidados_ativos(self):
        servidor = {
            "_historico": {"10": "99", "11": "99"},
            "_membros": {
                "10": {
                    "inviter_id": "99",
                    "code": "abc",
                    "url": "https://discord.gg/abc",
                    "active": True,
                },
                "11": {
                    "inviter_id": "99",
                    "code": "xyz",
                    "url": "https://discord.gg/xyz",
                    "active": False,
                },
            },
            "99": {"membros": ["10"]},
        }
        itens = _resumo(servidor, 99)
        self.assertEqual(len(itens), 2)
        self.assertEqual(sum(1 for item in itens if item.get("active")), 1)
        self.assertEqual({item.get("code") for item in itens}, {"abc", "xyz"})

    def test_migra_vinculos_legados_sem_inventar_link(self):
        servidor = {
            "_historico": {"10": "99"},
            "_membros": {},
            "99": {"membros": ["10"]},
        }
        itens = _resumo(servidor, 99)
        self.assertEqual(len(itens), 1)
        self.assertTrue(itens[0]["legacy"])
        self.assertIsNone(itens[0].get("url"))

    def test_paginacao_conta_links_unicos_e_nao_convidados(self):
        servidor = {
            "_historico": {str(i): "99" for i in range(25)},
            "_membros": {
                str(i): {"inviter_id": "99", "code": f"link-{i % 10}", "active": True}
                for i in range(25)
            },
            "99": {"membros": [str(i) for i in range(25)]},
        }
        self.assertEqual(_total_paginas(servidor, 99), 2)

    def test_preserva_convidado_legado_que_ja_saiu(self):
        servidor = {
            "_historico": {"10": "99"},
            "_membros": {},
            "99": {"membros": []},
        }
        itens = _resumo(servidor, 99)
        self.assertEqual(len(itens), 1)
        self.assertFalse(itens[0]["active"])


if __name__ == "__main__":
    unittest.main()
