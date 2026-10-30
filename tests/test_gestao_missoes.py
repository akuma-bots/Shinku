import unittest

from cogs.gestao_missoes import CentralMissoesView, SeletorAtividade, _ordenar_atividades


class TestCentralGestaoMissoes(unittest.TestCase):
    def setUp(self):
        self.atividades = [
            {
                "id": f"MS-{indice:03d}",
                "titulo": f"Atividade {indice:03d}",
                "tipo": "missao",
                "recompensa_xp": 100,
                "ativa": True,
            }
            for indice in range(63)
        ]

    def test_seletor_respeita_limite_e_pagina(self):
        view = CentralMissoesView(1, 2, pagina=2)
        seletor = SeletorAtividade(view, self.atividades)
        self.assertEqual(len(seletor.options), 13)
        self.assertEqual(seletor.options[0].value, "MS-050")
        self.assertEqual(seletor.options[-1].value, "MS-062")

    def test_pagina_intermediaria_tem_25_opcoes(self):
        view = CentralMissoesView(1, 2, pagina=1)
        seletor = SeletorAtividade(view, self.atividades)
        self.assertEqual(len(seletor.options), 25)
        self.assertEqual(seletor.options[0].value, "MS-025")
        self.assertEqual(seletor.options[-1].value, "MS-049")

    def test_view_tem_controles_de_navegacao_e_gestao(self):
        view = CentralMissoesView(1, 2)
        labels = {item.label for item in view.children}
        self.assertTrue({"Página anterior", "Próxima página", "Editar atividade",
                         "Arquivar / reativar", "Atualizar painel"}.issubset(labels))

    def test_ordenacao_e_estavel(self):
        ordenadas = _ordenar_atividades(list(reversed(self.atividades)))
        self.assertEqual(ordenadas[0]["id"], "MS-000")
        self.assertEqual(ordenadas[-1]["id"], "MS-062")


if __name__ == "__main__":
    unittest.main()
