import unittest
from unittest.mock import AsyncMock, patch
from utils import formularios

class TestStatusCandidatura(unittest.IsolatedAsyncioTestCase):
    async def test_revisao_pendente_atualiza_status(self):
        resposta = {'id': 'resp-1', 'status': 'pendente'}
        dados = {'1543381737961160910': [resposta]}
        with patch.object(formularios, '_tudo_respostas', new=AsyncMock(return_value=dados)), patch.object(formularios, '_salvar_respostas_guild', new=AsyncMock()) as salvar:
            resultado = await formularios.definir_status_resposta(1543381737961160910, 'resp-1', 'aprovada', 99)
        self.assertEqual(resultado['status'], 'aprovada')
        self.assertEqual(resultado['revisor_id'], 99)
        salvar.assert_awaited_once()

    async def test_nao_permite_sobrescrever_decisao_existente(self):
        resposta = {'id': 'resp-2', 'status': 'aprovada', 'revisor_id': 10}
        dados = {'1543381737961160910': [resposta]}
        with patch.object(formularios, '_tudo_respostas', new=AsyncMock(return_value=dados)), patch.object(formularios, '_salvar_respostas_guild', new=AsyncMock()) as salvar:
            resultado = await formularios.definir_status_resposta(1543381737961160910, 'resp-2', 'recusada', 20)
        self.assertIsNone(resultado)
        self.assertEqual(resposta['status'], 'aprovada')
        salvar.assert_not_awaited()

    async def test_rejeita_status_desconhecido(self):
        dados = {'1543381737961160910': [{'id': 'resp-3', 'status': 'pendente'}]}
        with patch.object(formularios, '_tudo_respostas', new=AsyncMock(return_value=dados)):
            with self.assertRaises(ValueError):
                await formularios.definir_status_resposta(1543381737961160910, 'resp-3', 'qualquer', 20)

if __name__ == '__main__':
    unittest.main()
