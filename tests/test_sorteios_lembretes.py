import copy
import unittest
from unittest.mock import patch

from cogs.sorteios_painel import _salvar_estado_lembretes


class TestPersistenciaLembretesSorteios(unittest.IsolatedAsyncioTestCase):
    async def test_atualiza_lembretes_sem_apagar_participantes_concorrentes(self):
        persistido = {
            "sorteio-1": {
                "id": "sorteio-1",
                "participantes": [111, 222],
                "chances_por_usuario": {"111": 1, "222": 1},
                "titulo": "Sorteio atualizado",
            }
        }
        sorteio_local_desatualizado = {
            "id": "sorteio-1",
            "participantes": [111],
            "titulo": "Sorteio antigo",
            "lembrete_fila_ids": [111, 222, 333],
            "lembrete_fila_indice": 2,
            "lembrete_jump_url": "https://discord.com/channels/1/2/3",
            "lembrete_proximo_em": 7200,
        }

        resultado_atualizado = {}

        async def atualizar(nome_arquivo, padrao, transformador):
            dados = copy.deepcopy(persistido)
            resultado = transformador(dados)
            resultado_atualizado.update(dados if resultado is None else resultado)
            return resultado_atualizado

        with patch("cogs.sorteios_painel.atualizar_json", side_effect=atualizar):
            await _salvar_estado_lembretes(sorteio_local_desatualizado)

        atual = resultado_atualizado["sorteio-1"]
        self.assertEqual(atual["participantes"], [111, 222])
        self.assertEqual(
            atual["chances_por_usuario"],
            {"111": 1, "222": 1},
        )
        self.assertEqual(atual["titulo"], "Sorteio atualizado")
        self.assertEqual(atual["lembrete_fila_ids"], [111, 222, 333])
        self.assertEqual(atual["lembrete_fila_indice"], 2)
        self.assertEqual(
            sorteio_local_desatualizado["lembrete_jump_url"],
            "https://discord.com/channels/1/2/3",
        )

    async def test_nao_cria_registro_quando_sorteio_ja_foi_removido(self):
        resultado_atualizado = {}

        async def atualizar(nome_arquivo, padrao, transformador):
            dados = {}
            resultado = transformador(dados)
            resultado_atualizado.update(dados if resultado is None else resultado)
            return resultado_atualizado

        sorteio = {
            "id": "removido",
            "lembrete_fila_ids": [123],
            "lembrete_fila_indice": 0,
        }
        with patch("cogs.sorteios_painel.atualizar_json", side_effect=atualizar):
            await _salvar_estado_lembretes(sorteio)
        self.assertEqual(resultado_atualizado, {})


if __name__ == "__main__":
    unittest.main()
