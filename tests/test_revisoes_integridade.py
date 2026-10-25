import unittest
from unittest.mock import AsyncMock, patch

from utils import revisoes


class TestIntegridadeRevisoes(unittest.IsolatedAsyncioTestCase):
    async def test_listar_ignora_registros_legados_invalidos(self):
        dados = {
            "1563995879981981817": [
                None,
                "registro-inválido",
                {"id": "rev-1", "status": "pendente"},
                {"id": "rev-2", "status": "aprovada"},
            ]
        }

        with patch.object(revisoes, "carregar", new=AsyncMock(return_value=dados)):
            todas = await revisoes.listar(1563995879981981817)
            pendentes = await revisoes.listar(1563995879981981817, status="pendente")

        self.assertEqual([item["id"] for item in todas], ["rev-1", "rev-2"])
        self.assertEqual([item["id"] for item in pendentes], ["rev-1"])

    async def test_estrutura_invalida_de_guild_retorna_lista_vazia(self):
        with patch.object(revisoes, "carregar", new=AsyncMock(return_value={"1563995879981981817": {"nao": "lista"}})):
            resultado = await revisoes.listar(1563995879981981817)

        self.assertEqual(resultado, [])

    async def test_storage_raiz_invalido_e_tratado_como_vazio(self):
        with patch.object(revisoes, "carregar", new=AsyncMock(return_value=[])):
            resultado = await revisoes.listar(1563995879981981817)

        self.assertEqual(resultado, [])


if __name__ == "__main__":
    unittest.main()
