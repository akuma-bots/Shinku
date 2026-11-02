import unittest
from unittest.mock import AsyncMock, patch
from utils import competitivo_sync

class TestCompetitivoSync(unittest.IsolatedAsyncioTestCase):
    async def test_pontos_legados_nao_sao_mais_acumulados_e_preserva_campos_do_site(self):
        dados = {'catalogo': [], 'perfis': {'123': {'discordId': '123', 'nome': 'Site', 'pontos': 80, 'elo': 1250, 'vitorias': 4, 'derrotas': 2, 'extra': 'manter'}}}
        async def atualizar(_arquivo, _padrao, transformador):
            return transformador(dados)

        with patch.object(competitivo_sync, 'atualizar_json', new=AsyncMock(side_effect=atualizar)) as atualizar_mock:
            perfil = await competitivo_sync.somar_pontos_competitivo(123, 'Atualizado', 15)
        self.assertEqual(perfil['pontos'], 80)
        self.assertEqual(perfil['elo'], 1250)
        self.assertEqual(perfil['extra'], 'manter')
        atualizar_mock.assert_awaited_once()

    async def test_evento_competitivo_nao_duplica_pontuacao(self):
        dados = {'catalogo': [], 'perfis': {}}

        async def atualizar(_arquivo, _padrao, transformador):
            return transformador(dados)

        with patch.object(competitivo_sync, 'atualizar_json', new=AsyncMock(side_effect=atualizar)):
            primeira = await competitivo_sync.somar_pontos_competitivo(
                321, "Membro", 40, evento_id="guerra:77"
            )
            segunda = await competitivo_sync.somar_pontos_competitivo(
                321, "Membro", 40, evento_id="guerra:77"
            )

        self.assertEqual(primeira["pontos"], 0)
        self.assertEqual(segunda["pontos"], 0)
        self.assertEqual(segunda["eventos_pontos_aplicados"], ["guerra:77"])

    async def test_migracao_nao_sobrescreve_perfil_existente(self):
        existente = {'discordId': '456', 'nome': 'Site', 'pontos': 900, 'elo': 1400, 'vitorias': 20, 'derrotas': 3}
        dados = {'catalogo': [], 'perfis': {'456': existente}}
        async def atualizar(_arquivo, _padrao, transformador):
            return transformador(dados)

        with patch.object(competitivo_sync, 'atualizar_json', new=AsyncMock(side_effect=atualizar)):
            perfil = await competitivo_sync.migrar_perfil_se_necessario(456, 'Discord', {'xp': 10, 'vitorias': 1, 'mvps': 2, 'derrotas': 8})
        self.assertEqual(perfil, existente)
        self.assertEqual(perfil['pontos'], 900)

    async def test_migracao_cria_perfil_ausente(self):
        dados = {'catalogo': [], 'perfis': {}}
        async def atualizar(_arquivo, _padrao, transformador):
            return transformador(dados)

        with patch.object(competitivo_sync, 'atualizar_json', new=AsyncMock(side_effect=atualizar)):
            perfil = await competitivo_sync.migrar_perfil_se_necessario(789, 'Novo membro', {'xp': 50, 'vitorias': 3, 'mvps': 2, 'derrotas': 1})
        self.assertEqual(perfil['discordId'], '789')
        self.assertEqual(perfil['pontos'], 0)\n        self.assertEqual(perfil['xp'], 50)\n        self.assertEqual(perfil['xp_temporada'], 50)

if __name__ == '__main__':
    unittest.main()
