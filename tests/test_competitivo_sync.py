import unittest
from unittest.mock import AsyncMock, patch
from utils import competitivo_sync

class TestCompetitivoSync(unittest.IsolatedAsyncioTestCase):
    async def test_delta_preserva_campos_do_site(self):
        dados = {'catalogo': [], 'perfis': {'123': {'discordId': '123', 'nome': 'Site', 'pontos': 80, 'elo': 1250, 'vitorias': 4, 'derrotas': 2, 'extra': 'manter'}}}
        with patch.object(competitivo_sync, 'carregar', new=AsyncMock(return_value=dados)), patch.object(competitivo_sync, 'salvar', new=AsyncMock()) as salvar:
            perfil = await competitivo_sync.somar_pontos_competitivo(123, 'Atualizado', 15)
        self.assertEqual(perfil['pontos'], 95)
        self.assertEqual(perfil['elo'], 1250)
        self.assertEqual(perfil['extra'], 'manter')
        salvar.assert_awaited_once_with('competitivo.json', dados)

    async def test_migracao_nao_sobrescreve_perfil_existente(self):
        existente = {'discordId': '456', 'nome': 'Site', 'pontos': 900, 'elo': 1400, 'vitorias': 20, 'derrotas': 3}
        dados = {'catalogo': [], 'perfis': {'456': existente}}
        with patch.object(competitivo_sync, 'carregar', new=AsyncMock(return_value=dados)), patch.object(competitivo_sync, 'salvar', new=AsyncMock()) as salvar:
            perfil = await competitivo_sync.migrar_perfil_se_necessario(456, 'Discord', {'xp': 10, 'vitorias': 1, 'mvps': 2, 'derrotas': 8})
        self.assertIs(perfil, existente)
        self.assertEqual(perfil['pontos'], 900)
        salvar.assert_not_awaited()

    async def test_migracao_cria_perfil_ausente(self):
        dados = {'catalogo': [], 'perfis': {}}
        with patch.object(competitivo_sync, 'carregar', new=AsyncMock(return_value=dados)), patch.object(competitivo_sync, 'salvar', new=AsyncMock()) as salvar:
            perfil = await competitivo_sync.migrar_perfil_se_necessario(789, 'Novo membro', {'xp': 50, 'vitorias': 3, 'mvps': 2, 'derrotas': 1})
        self.assertEqual(perfil['discordId'], '789')
        self.assertEqual(perfil['pontos'], 120)
        salvar.assert_awaited_once_with('competitivo.json', dados)

if __name__ == '__main__':
    unittest.main()
