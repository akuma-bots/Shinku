import copy
import unittest
from unittest.mock import patch

from utils import preferencias_notificacoes as prefs


class TestPreferenciasNotificacoesAtomicas(unittest.IsolatedAsyncioTestCase):
    async def test_alterar_uma_categoria_preserva_as_demais(self):
        estado = {
            "guilds": {
                "10": {
                    "20": {
                        "avisos_comunidade": False,
                        "notas_atualizacao": True,
                    }
                }
            }
        }

        async def atualizar(nome, padrao, transformador):
            nonlocal estado
            novo = transformador(copy.deepcopy(estado))
            estado = novo if novo is not None else estado
            return copy.deepcopy(estado)

        async def carregar(nome, padrao):
            return copy.deepcopy(estado)

        with (
            patch.object(prefs, "atualizar_json", side_effect=atualizar) as atualizar_mock,
            patch.object(prefs, "carregar", side_effect=carregar),
        ):
            resultado = await prefs.definir_preferencia(10, 20, "notas_atualizacao", False)

        atualizar_mock.assert_awaited_once()
        self.assertFalse(resultado["notas_atualizacao"])
        self.assertFalse(resultado["avisos_comunidade"])

    async def test_desativar_todas_preserva_outros_membros(self):
        estado = {
            "guilds": {
                "10": {
                    "20": {"avisos_comunidade": True, "notas_atualizacao": True},
                    "30": {"avisos_comunidade": True, "notas_atualizacao": False},
                }
            }
        }

        async def atualizar(nome, padrao, transformador):
            nonlocal estado
            novo = transformador(copy.deepcopy(estado))
            estado = novo if novo is not None else estado
            return copy.deepcopy(estado)

        async def carregar(nome, padrao):
            return copy.deepcopy(estado)

        with (
            patch.object(prefs, "atualizar_json", side_effect=atualizar),
            patch.object(prefs, "carregar", side_effect=carregar),
        ):
            resultado = await prefs.desativar_todas(10, 20)

        self.assertFalse(resultado["avisos_comunidade"])
        self.assertFalse(resultado["notas_atualizacao"])
        self.assertTrue(estado["guilds"]["10"]["30"]["avisos_comunidade"])
        self.assertFalse(estado["guilds"]["10"]["30"]["notas_atualizacao"])


if __name__ == "__main__":
    unittest.main()
