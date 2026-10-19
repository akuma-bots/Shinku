import unittest
from unittest.mock import AsyncMock, Mock

from cogs.tickets import _preparar_resposta_interacao


class TestPrepararRespostaInteracao(unittest.IsolatedAsyncioTestCase):
    async def test_adia_interacao_ainda_nao_respondida(self):
        interaction = Mock()
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()

        await _preparar_resposta_interacao(interaction)

        interaction.response.defer.assert_awaited_once_with(
            ephemeral=True,
            thinking=True,
        )

    async def test_nao_tenta_reconhecer_interacao_duas_vezes(self):
        interaction = Mock()
        interaction.response.is_done.return_value = True
        interaction.response.defer = AsyncMock()

        await _preparar_resposta_interacao(interaction)

        interaction.response.defer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
