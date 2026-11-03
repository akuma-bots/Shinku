import unittest
from types import SimpleNamespace

from cogs.status_sistema import _resumo_tarefas_automaticas


class FakeLoop:
    def __init__(self, running):
        self.running = running

    def is_running(self):
        return self.running


class CogComLoops:
    loop_ativo = FakeLoop(True)
    loop_parado = FakeLoop(False)


class TestResumoTarefasSistema(unittest.TestCase):
    def test_conta_loops_ativos_e_parados(self):
        cog = CogComLoops()
        total, ativas, falhas = _resumo_tarefas_automaticas(SimpleNamespace(cogs={"Teste": cog}))
        self.assertEqual((total, ativas, falhas), (2, 1, 1))

    def test_bot_sem_cogs_nao_gera_falha(self):
        self.assertEqual(_resumo_tarefas_automaticas(SimpleNamespace(cogs={})), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
