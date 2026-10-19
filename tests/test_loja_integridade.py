import unittest
from unittest.mock import AsyncMock, patch

from utils import loja


class TestIntegridadeLoja(unittest.IsolatedAsyncioTestCase):
    async def test_rejeita_preco_negativo_sem_gravar(self):
        with patch.object(loja, "carregar", new=AsyncMock(return_value={})), patch.object(
            loja, "salvar", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "não pode ser negativo"):
                await loja.adicionar(123, "Cargo", "Descrição", -10)

        salvar.assert_not_awaited()

    async def test_rejeita_nome_vazio(self):
        with patch.object(loja, "carregar", new=AsyncMock(return_value={})), patch.object(
            loja, "salvar", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "nome"):
                await loja.adicionar(123, "   ", "Descrição", 10)

        salvar.assert_not_awaited()

    async def test_listar_ignora_itens_corrompidos_e_precos_negativos(self):
        dados = {
            "123": [
                {"id": "a1", "nome": "Válido", "descricao": "ok", "preco_xp": "25"},
                {"id": "a2", "nome": "Exploit", "descricao": "XP grátis", "preco_xp": -100},
                None,
                {"id": "", "nome": "Sem ID", "preco_xp": 0},
                {"id": "a3", "nome": "Preço inválido", "preco_xp": "abc"},
            ]
        }

        with patch.object(loja, "carregar", new=AsyncMock(return_value=dados)):
            itens = await loja.listar(123)

        self.assertEqual(len(itens), 1)
        self.assertEqual(itens[0]["id"], "a1")
        self.assertEqual(itens[0]["preco_xp"], 25)

    async def test_adiciona_e_remove_item(self):
        dados = {}
        with patch.object(loja, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            loja, "salvar", new=AsyncMock()
        ) as salvar:
            item = await loja.adicionar(123, "Emblema", "Item cosmético", 50)
            encontrado = await loja.get(123, item["id"])
            removido = await loja.remover(123, item["id"])

        self.assertEqual(encontrado["nome"], "Emblema")
        self.assertTrue(removido)
        salvar.assert_awaited()


if __name__ == "__main__":
    unittest.main()
