import unittest
from unittest.mock import AsyncMock, patch

from cogs import parcerias


class TestIntegridadeParcerias(unittest.IsolatedAsyncioTestCase):
    async def test_storage_raiz_invalido_usa_estrutura_vazia(self):
        with patch.object(parcerias, "carregar", new=AsyncMock(return_value=[])):
            dados = await parcerias._todas()

        self.assertEqual(dados, {})

    async def test_lista_filtra_registros_corrompidos(self):
        dados = {"123": [None, "inválido", {"id": "p1", "nome": "Parceiro"}]}
        with patch.object(parcerias, "_todas", new=AsyncMock(return_value=dados)):
            lista = await parcerias._da_guild(123)

        self.assertEqual(len(lista), 1)
        self.assertEqual(lista[0]["id"], "p1")

    async def test_normalizacao_preserva_registro_legado(self):
        lista = [{"id": "p1", "nome": "Parceiro", "status": "ativa"}]
        with patch.object(parcerias, "_da_guild", new=AsyncMock(return_value=lista)), patch.object(
            parcerias, "_salvar_da_guild", new=AsyncMock()
        ) as salvar:
            resultado = await parcerias._normalizar_todas_guild(123)

        self.assertEqual(resultado[0]["id"], "p1")
        self.assertEqual(resultado[0]["guild_id"], 123)
        self.assertIn("criado_em", resultado[0])
        salvar.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
