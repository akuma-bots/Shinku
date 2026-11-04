import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cogs.eventos import (
    CANAL_EVENTOS_PADRAO_ID,
    Eventos,
    _atualizar_participantes,
)


class TestCanalAgenda(unittest.IsolatedAsyncioTestCase):
    async def test_usa_canal_oficial_quando_nao_ha_configuracao(self):
        canal = object()
        guild = SimpleNamespace(
            id=1563995879981981817,
            get_channel=lambda canal_id: canal if canal_id == CANAL_EVENTOS_PADRAO_ID else None,
        )
        cog = object.__new__(Eventos)
        with patch("cogs.eventos.get_config", new=AsyncMock(return_value={})):
            resultado = await cog._canal_eventos(guild)
        self.assertIs(resultado, canal)

    async def test_configuracao_personalizada_tem_precedencia(self):
        canal_personalizado = object()
        guild = SimpleNamespace(
            id=1563995879981981817,
            get_channel=lambda canal_id: canal_personalizado if canal_id == 123 else None,
        )
        cog = object.__new__(Eventos)
        with patch(
            "cogs.eventos.get_config",
            new=AsyncMock(return_value={"canal_eventos_id": 123}),
        ):
            resultado = await cog._canal_eventos(guild)
        self.assertIs(resultado, canal_personalizado)


class TestParticipacaoEventos(unittest.TestCase):
    def test_inscricao_adiciona_usuario_uma_vez(self):
        registro, alterado = _atualizar_participantes(
            {"participantes": [], "inscritos_ids": []},
            123,
            True,
            timestamp=100,
        )
        self.assertTrue(alterado)
        self.assertEqual(registro["participantes"], [123])
        self.assertEqual(registro["inscritos_ids"], [123])
        self.assertEqual(registro["total_inscritos"], 1)
        self.assertEqual(registro["historico_inscricoes"], [{
            "user_id": 123,
            "acao": "inscricao",
            "timestamp": 100.0,
        }])

    def test_evento_reentregue_nao_duplica_inscricao(self):
        inicial = {
            "participantes": [123],
            "inscritos_ids": [123],
            "historico_inscricoes": [{
                "user_id": 123,
                "acao": "inscricao",
                "timestamp": 100,
            }],
        }
        registro, alterado = _atualizar_participantes(
            inicial,
            123,
            True,
            timestamp=200,
        )
        self.assertFalse(alterado)
        self.assertEqual(registro["inscritos_ids"], [123])
        self.assertEqual(len(registro["historico_inscricoes"]), 1)

    def test_cancelamento_preserva_historico_e_remove_inscricao_ativa(self):
        inicial = {
            "participantes": [123],
            "inscritos_ids": [123],
            "historico_inscricoes": [{
                "user_id": 123,
                "acao": "inscricao",
                "timestamp": 100,
            }],
        }
        registro, alterado = _atualizar_participantes(
            inicial,
            123,
            False,
            timestamp=200,
        )
        self.assertTrue(alterado)
        self.assertEqual(registro["participantes"], [123])
        self.assertEqual(registro["inscritos_ids"], [])
        self.assertEqual(registro["total_inscritos"], 0)
        self.assertEqual(
            [item["acao"] for item in registro["historico_inscricoes"]],
            ["inscricao", "cancelamento"],
        )

    def test_reinscricao_nao_duplica_historico_de_pessoas(self):
        inicial = {
            "participantes": [123],
            "inscritos_ids": [],
            "historico_inscricoes": [{
                "user_id": 123,
                "acao": "inscricao",
                "timestamp": 100,
            }, {
                "user_id": 123,
                "acao": "cancelamento",
                "timestamp": 200,
            }],
        }
        registro, alterado = _atualizar_participantes(
            inicial,
            123,
            True,
            timestamp=300,
        )
        self.assertTrue(alterado)
        self.assertEqual(registro["participantes"], [123])
        self.assertEqual(registro["inscritos_ids"], [123])
        self.assertEqual(len(registro["historico_inscricoes"]), 3)

    def test_migra_lista_antiga_de_participantes(self):
        inicial = {"participantes": [123, "456", 123]}
        registro, alterado = _atualizar_participantes(
            inicial,
            789,
            True,
            timestamp=400,
        )
        self.assertTrue(alterado)
        self.assertEqual(registro["participantes"], [123, 456, 789])
        self.assertEqual(registro["inscritos_ids"], [789])


if __name__ == "__main__":
    unittest.main()
