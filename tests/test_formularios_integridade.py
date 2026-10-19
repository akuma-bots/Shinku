import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from utils import formularios


class TestIntegridadeFormularios(unittest.IsolatedAsyncioTestCase):
    async def test_storage_raiz_invalido_e_tratado_como_vazio(self):
        with patch.object(formularios, "carregar", new=AsyncMock(return_value=[])):
            self.assertEqual(await formularios._tudo_formularios(), {})
            self.assertEqual(await formularios._tudo_respostas(), {})

    async def test_listagem_filtra_registros_corrompidos(self):
        dados_formularios = {"123": [None, "inválido", {"id": "f1", "nome": "Form"}]}
        dados_respostas = {"123": [None, "inválido", {"id": "r1", "formulario_id": "f1", "status": "pendente"}]}
        with patch.object(formularios, "_tudo_formularios", new=AsyncMock(return_value=dados_formularios)), patch.object(
            formularios, "_tudo_respostas", new=AsyncMock(return_value=dados_respostas)
        ):
            forms = await formularios.listar_formularios(123)
            respostas = await formularios.listar_respostas(123, status="pendente")

        self.assertEqual([item["id"] for item in forms], ["f1"])
        self.assertEqual([item["id"] for item in respostas], ["r1"])

    async def test_decisoes_concorrentes_nao_aprovam_e_rejeitam_a_mesma_resposta(self):
        dados = {"123": [{
            "id": "r1",
            "formulario_id": "f1",
            "status": "pendente",
            "autor_id": 456,
        }]}
        with patch.object(formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "_salvar_respostas_guild", new=AsyncMock()
        ) as salvar:
            resultados = await asyncio.gather(
                formularios.definir_status_resposta(123, "r1", "aprovada", 1),
                formularios.definir_status_resposta(123, "r1", "recusada", 2),
            )

        aplicadas = [resultado for resultado in resultados if resultado is not None]
        self.assertEqual(len(aplicadas), 1)
        self.assertIn(dados["123"][0]["status"], {"aprovada", "recusada"})
        salvar.assert_awaited_once()

    async def test_criar_resposta_recupera_lista_corrompida(self):
        dados = {"123": "lista inválida"}
        with patch.object(formularios, "_tudo_respostas", new=AsyncMock(return_value=dados)), patch.object(
            formularios, "get_formulario", new=AsyncMock(return_value={"nome": "Form", "paginas": []})
        ), patch.object(formularios, "_salvar_respostas_guild", new=AsyncMock()) as salvar:
            resposta = await formularios.criar_resposta(123, "f1", 456, [], "Membro")

        self.assertEqual(resposta["status"], "pendente")
        salvar.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
