import unittest

from utils.perfis import _normalizar_perfil


class TestNormalizacaoPerfil(unittest.TestCase):
    def test_campos_numericos_invalidos_nao_quebram_o_perfil(self):
        perfil = _normalizar_perfil({
            "xp": "inválido",
            "vitorias": -3,
            "derrotas": "4",
            "sequencia_atual": 7,
            "maior_sequencia": 2,
        })

        self.assertEqual(perfil["xp"], 0)
        self.assertEqual(perfil["vitorias"], 0)
        self.assertEqual(perfil["derrotas"], 4)
        self.assertEqual(perfil["maior_sequencia"], 7)

    def test_medalha_em_texto_nao_vira_lista_de_caracteres(self):
        perfil = _normalizar_perfil({"medalhas": "🥇 Lenda"})

        self.assertEqual(perfil["medalhas"], ["🥇 Lenda"])

    def test_ledger_de_eventos_e_normalizado_e_deduplicado(self):
        perfil = _normalizar_perfil({
            "recompensas_missoes_aplicadas": "missao:123",
            "resultados_pvp_aplicados": ["pvp:1", "pvp:1", "", "pvp:2"],
            "eventos_recompensa": None,
        })

        self.assertEqual(perfil["recompensas_missoes_aplicadas"], ["missao:123"])
        self.assertEqual(perfil["resultados_pvp_aplicados"], ["pvp:1", "pvp:2"])
        self.assertEqual(perfil["eventos_recompensa"], [])

    def test_preserva_campos_extras_e_medalhas_unicas(self):
        perfil = _normalizar_perfil({
            "campo_legado": {"preservar": True},
            "medalhas": ["Primeira", "Primeira", " ", "Segunda"],
        })

        self.assertEqual(perfil["campo_legado"], {"preservar": True})
        self.assertEqual(perfil["medalhas"], ["Primeira", "Segunda"])

    def test_perfil_com_estrutura_invalida_usa_padroes(self):
        perfil = _normalizar_perfil(None)

        self.assertEqual(perfil["xp"], 0)
        self.assertEqual(perfil["vitorias"], 0)
        self.assertEqual(perfil["medalhas"], [])


if __name__ == "__main__":
    unittest.main()
