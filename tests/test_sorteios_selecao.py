import unittest
from unittest.mock import patch

from cogs.sorteios import _selecionar_vencedores


class TestSelecaoVencedoresSorteio(unittest.TestCase):
    def test_reutiliza_vencedores_apos_falha_de_anuncio(self):
        resultado = _selecionar_vencedores(
            participantes=[10, 20, 30],
            quantidade_solicitada=2,
            vencedores_salvos=[20, 10],
            resultado_ja_sorteado=True,
        )
        self.assertEqual(resultado, [20, 10])

    def test_remove_vencedores_salvos_que_nao_participaram_mais(self):
        resultado = _selecionar_vencedores(
            participantes=[10, 30],
            quantidade_solicitada=2,
            vencedores_salvos=[20, 10, 10, "inválido"],
            resultado_ja_sorteado=True,
        )
        self.assertEqual(resultado, [10])

    def test_faz_sorteio_novo_quando_nao_existe_resultado_salvo(self):
        with patch("cogs.sorteios.random.sample", return_value=[30, 10]) as sample:
            resultado = _selecionar_vencedores(
                participantes=[10, 20, 30],
                quantidade_solicitada=2,
                vencedores_salvos=[],
                resultado_ja_sorteado=False,
            )
        self.assertEqual(resultado, [30, 10])
        sample.assert_called_once_with([10, 20, 30], 2)

    def test_lista_vazia_nao_gera_erro(self):
        resultado = _selecionar_vencedores(
            participantes=[],
            quantidade_solicitada=1,
        )
        self.assertEqual(resultado, [])

    def test_participantes_duplicados_nao_geram_vencedores_duplicados(self):
        with patch("cogs.sorteios.random.sample", return_value=[20, 10]) as sample:
            resultado = _selecionar_vencedores(
                participantes=[10, 20, 10, "20", 30],
                quantidade_solicitada=2,
            )
        self.assertEqual(resultado, [20, 10])
        sample.assert_called_once_with([10, 20, 30], 2)

    def test_quantidade_invalida_nao_interrompe_o_sorteio(self):
        resultado = _selecionar_vencedores(
            participantes=[10, 20],
            quantidade_solicitada="inválida",
        )
        self.assertEqual(resultado, [])

    def test_chances_ponderadas_sao_usadas_sem_repetir_vencedor(self):
        with patch("cogs.sorteios.random.choices", side_effect=[[20], [10]]) as choices:
            resultado = _selecionar_vencedores(
                participantes=[10, 20, 30],
                quantidade_solicitada=2,
                chances_por_usuario={"10": 1, "20": 5, "30": 2},
            )
        self.assertEqual(resultado, [20, 10])
        self.assertEqual(choices.call_count, 2)
        choices.assert_any_call([10, 20, 30], weights=[1, 5, 2], k=1)
        choices.assert_any_call([10, 30], weights=[1, 2], k=1)

    def test_chance_invalida_volta_para_uma_chance(self):
        with patch("cogs.sorteios.random.choices", return_value=[10]) as choices:
            resultado = _selecionar_vencedores(
                participantes=[10, 20],
                quantidade_solicitada=1,
                chances_por_usuario={"10": "invalida", "20": 3},
            )
        self.assertEqual(resultado, [10])
        choices.assert_called_once_with([10, 20], weights=[1, 3], k=1)



if __name__ == "__main__":
    unittest.main()
