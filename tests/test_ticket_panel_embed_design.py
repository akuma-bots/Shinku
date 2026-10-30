import unittest
from unittest.mock import AsyncMock, patch

from cogs.tickets import _montar_embed_painel, FecharTicketView


class TestTicketPanelEmbedDesign(unittest.IsolatedAsyncioTestCase):
    async def test_painel_padrao_tem_orientacoes_e_privacidade_separadas(self):
        with patch("cogs.tickets.get_config", new=AsyncMock(return_value={})):
            embed = await _montar_embed_painel(1563995879981981817)

        self.assertIn("CENTRAL DE ATENDIMENTO", embed.title)
        self.assertIn("Selecione abaixo a categoria", embed.description)
        nomes = [field.name for field in embed.fields]
        self.assertEqual(len(nomes), 12)
        self.assertIn("✦  01  /  Recrutamento e Admissão", nomes)
        self.assertIn("♟️  02  /  Estrutura e Hierarquia", nomes)
        self.assertIn("♜  PRIVACIDADE E SEGURANÇA", nomes)
        self.assertIn("◈  CATÁLOGO DE ATENDIMENTO", nomes)
        self.assertIn("⏱️  ATENDIMENTO", nomes)
        self.assertIn("▰  COMO FUNCIONA", nomes)
        self.assertEqual(embed.color.value, 0x9F1239)


    def test_controles_persistentes_incluem_acoes_de_atendimento(self):
        view = FecharTicketView()
        ids = {item.custom_id for item in view.children}
        self.assertIn("ticket:assumir", ids)
        self.assertIn("fechar_ticket_btn", ids)
        self.assertIn("ticket:adicionar_participante", ids)
        self.assertIn("ticket:solicitar_equipe", ids)


if __name__ == "__main__":
    unittest.main()
