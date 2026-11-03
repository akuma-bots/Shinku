import unittest
from unittest.mock import AsyncMock, Mock

from cogs.tickets import _preparar_resposta_interacao, Tickets, CUSTOM_ID_SELECT
from unittest.mock import patch


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

    async def test_seletor_de_ticket_adia_antes_de_consultar_categorias(self):
        interaction = Mock()
        interaction.type = __import__("discord").InteractionType.component
        interaction.data = {"custom_id": CUSTOM_ID_SELECT, "values": ["suporte"]}
        interaction.guild.id = 1563995879981981817
        interaction.user.bot = False
        interaction.response.is_done.return_value = False
        interaction.response.defer = AsyncMock()
        interaction.followup.send = AsyncMock()
        cog = object.__new__(Tickets)
        async def falhar_depois_do_ack(_guild_id):
            interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
            raise RuntimeError("Redis temporariamente indisponível")
        with patch("cogs.tickets.tickets.get_tipos", AsyncMock(side_effect=falhar_depois_do_ack)):
            await Tickets.on_interaction(cog, interaction)
        interaction.followup.send.assert_awaited_once()
        self.assertTrue(interaction.followup.send.await_args.kwargs["ephemeral"])

    async def test_nao_tenta_reconhecer_interacao_duas_vezes(self):
        interaction = Mock()
        interaction.response.is_done.return_value = True
        interaction.response.defer = AsyncMock()

        await _preparar_resposta_interacao(interaction)

        interaction.response.defer.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
