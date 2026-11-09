import unittest
from types import SimpleNamespace

from cogs.sorteios_painel import _calcular_chances


class TestCalculoChancesSorteio(unittest.TestCase):
    def test_todos_os_participantes_recebem_uma_chance_igual(self):
        membro = SimpleNamespace(roles=[])
        sorteio = {"cargo_minimo_id": 1, "bonus_cargos": {"2": 99}}
        self.assertEqual(_calcular_chances(membro, sorteio), 1)

    def test_cargos_nao_bloqueiam_participacao(self):
        membro = SimpleNamespace(roles=[SimpleNamespace(id=2)])
        sorteio = {"cargo_minimo_id": 1, "bonus_cargos": {"2": 1}}
        self.assertEqual(_calcular_chances(membro, sorteio), 1)

    def test_sem_requisito_ou_bonus_mantem_uma_chance(self):
        membro = SimpleNamespace(roles=[SimpleNamespace(id=2)])
        self.assertEqual(_calcular_chances(membro, {}), 1)


if __name__ == "__main__":
    unittest.main()