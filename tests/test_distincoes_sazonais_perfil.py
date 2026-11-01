import unittest

from cogs.perfil import _formatar_distincoes_sazonais


class TestDistincoesSazonaisPerfil(unittest.TestCase):
    def test_formata_medalhas_sazonais_sem_misturar_medalhas_permanentes(self):
        texto = _formatar_distincoes_sazonais([
            {"temporada": 4, "posicao": 1, "recompensa": "Campeão da Temporada"},
            {"temporada": 3, "posicao": 2, "recompensa": "Vice-Campeão"},
            {"temporada": 2, "posicao": 3, "recompensa": "Destaque"},
        ])
        self.assertIn("🥇 **Temporada #4**", texto)
        self.assertIn("🥈 **Temporada #3**", texto)
        self.assertIn("🥉 **Temporada #2**", texto)

    def test_perfil_sem_distincoes_mostra_estado_vazio(self):
        self.assertEqual(
            _formatar_distincoes_sazonais([]),
            "Nenhuma distinção sazonal conquistada ainda.",
        )

    def test_limita_quantidade_exibida(self):
        registros = [
            {"temporada": numero, "posicao": 1, "recompensa": "Campeão"}
            for numero in range(10, 0, -1)
        ]
        texto = _formatar_distincoes_sazonais(registros, limite=2)
        self.assertIn("Temporada #10", texto)
        self.assertIn("Temporada #9", texto)
        self.assertNotIn("Temporada #8", texto)
