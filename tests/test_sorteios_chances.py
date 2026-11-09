import unittest
from types import SimpleNamespace

from cogs.sorteios_painel import _calcular_chances


class TestCalculoChancesSorteio(unittest.TestCase):
    def test_chance_base_e_bonus_de_multiplos_cargos_sao_somados(self):
        membro = SimpleNamespace(roles=[SimpleNamespace(id=1), SimpleNamespace(id=2), SimpleNamespace(id=3)])
        sorteio = {"cargo_minimo_id": 1, "bonus_cargos": {"2": 1, "3": 2}}
        self.assertEqual(_calcular_chances(membro, sorteio), 4)

    def test_requisito_minimo_impede_participacao(self):
        membro = SimpleNamespace(roles=[SimpleNamespace(id=2)])
        sorteio = {"cargo_minimo_id": 1, "bonus_cargos": {"2": 1}}
        self.assertIsNone(_calcular_chances(membro, sorteio))

    def test_sem_requisito_ou_bonus_mantem_uma_chance(self):
        membro = SimpleNamespace(roles=[SimpleNamespace(id=2)])
        self.assertEqual(_calcular_chances(membro, {}), 1)


if __name__ == "__main__":
    unittest.main()