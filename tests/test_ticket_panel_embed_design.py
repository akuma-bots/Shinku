import unittest
from unittest.mock import AsyncMock, patch

from cogs.tickets import _montar_embed_painel


class TestTicketPanelEmbedDesign(unittest.IsolatedAsyncioTestCase):
    async def test_painel_padrao_tem_orientacoes_e_privacidade_separadas(self):
        with patch("cogs.tickets.get_config", new=AsyncMock(return_value={})):
            embed = await _montar_embed_painel(1543381737961160910)

        self.assertIn("CENTRAL DE ATENDIMENTO", embed.title)
        self.assertIn("Selecione abaixo a categoria", embed.description)
        self.assertEqual(
            [field.name for field in embed.fields],
            ["◈ ANTES DE ABRIR", "🔒 PRIVACIDADE"],
        )
        self.assertEqual(embed.color.value, 0x8B0000)
        self.assertIn("ticket é privado", embed.fields[1].value)


if __name__ == "__main__":
    unittest.main()
