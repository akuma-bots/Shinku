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


class TestRevisaoDuplicadaDeMissao(unittest.IsolatedAsyncioTestCase):
    async def test_reutiliza_prova_pendente_sem_publicar_mensagem_duplicada(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from cogs.revisoes import Revisoes

        existente = {
            "id": "rev-existente",
            "tipo": "missao",
            "autor_id": 77,
            "referencia_id": "missao-1",
            "status": "pendente",
            "mensagem_id": 1234,
            "canal_id": 5678,
        }
        cog = object.__new__(Revisoes)
        canal = SimpleNamespace(send=AsyncMock())
        guild = SimpleNamespace(id=999)
        with patch("cogs.revisoes.revisoes.listar", new=AsyncMock(return_value=[existente])):
            resultado = await cog._abrir_revisao_sem_lock(
                guild, canal,
                tipo="missao", autor_id=77, referencia_id="missao-1",
                print_url="https://cdn.discordapp.com/attachments/nova.png",
                titulo="Missão repetida",
            )

        self.assertTrue(resultado["_ja_existente"])
        self.assertEqual(resultado["id"], "rev-existente")
        canal.send.assert_not_awaited()
