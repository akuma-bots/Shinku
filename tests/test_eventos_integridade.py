import unittest
from unittest.mock import AsyncMock, patch

from cogs import eventos


class TestIntegridadeEventos(unittest.IsolatedAsyncioTestCase):
    async def test_storage_raiz_invalido_retorna_dicionario_vazio(self):
        with patch.object(eventos, "carregar", new=AsyncMock(return_value=[])):
            dados = await eventos._todos_eventos()

        self.assertEqual(dados, {})

    async def test_salvamento_nao_persiste_estrutura_raiz_invalida(self):
        with patch.object(eventos, "salvar", new=AsyncMock()) as salvar:
            await eventos._salvar_eventos(["inválido"])

        salvar.assert_awaited_once_with(eventos.ARQUIVO, {})

    async def test_evento_corrompido_nao_pode_ser_reutilizado_como_registro(self):
        dados = {"123": "registro inválido"}
        with patch.object(eventos, "_todos_eventos", new=AsyncMock(return_value=dados)), patch.object(
            eventos, "_salvar_eventos", new=AsyncMock()
        ) as salvar:
            # A deleção de um evento sem registro válido deve terminar sem exceção.
            cog = object.__new__(eventos.Eventos)
            evento = type("Evento", (), {"id": 123})()
            await eventos.Eventos.on_scheduled_event_delete(cog, evento)

        salvar.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
