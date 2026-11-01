import unittest
from types import SimpleNamespace

from cogs.gestao_missoes import (
    CentralMissoesView,
    SeletorAtividade,
    _embed_central,
    _ordenar_atividades,
)


class TestCentralGestaoMissoes(unittest.TestCase):
    def setUp(self):
        self.atividades = [
            {
                "id": f"MS-{indice:03d}",
                "titulo": f"Atividade {indice:03d}",
                "tipo": "missao",
                "recompensa_xp": 100,
                "ativa": True,
            }
            for indice in range(63)
        ]

    def test_seletor_respeita_limite_e_pagina(self):
        view = CentralMissoesView(1, 2, pagina=2)
        seletor = SeletorAtividade(view, self.atividades)
        self.assertEqual(len(seletor.options), 13)
        self.assertEqual(seletor.options[0].value, "MS-050")
        self.assertEqual(seletor.options[-1].value, "MS-062")

    def test_pagina_intermediaria_tem_25_opcoes(self):
        view = CentralMissoesView(1, 2, pagina=1)
        seletor = SeletorAtividade(view, self.atividades)
        self.assertEqual(len(seletor.options), 25)
        self.assertEqual(seletor.options[0].value, "MS-025")
        self.assertEqual(seletor.options[-1].value, "MS-049")

    def test_view_tem_controles_de_navegacao_e_gestao(self):
        view = CentralMissoesView(1, 2)
        labels = {item.label for item in view.children}
        self.assertTrue({"Página anterior", "Próxima página", "Editar atividade",
                         "Arquivar / reativar", "Atualizar painel", "Atendimento",
                         "Ranking geral", "Temporadas"}.issubset(labels))

    def test_ordenacao_e_estavel(self):
        ordenadas = _ordenar_atividades(list(reversed(self.atividades)))
        self.assertEqual(ordenadas[0]["id"], "MS-000")
        self.assertEqual(ordenadas[-1]["id"], "MS-062")


    def test_embed_da_central_apresenta_quebras_de_linha_reais(self):
        atividade = {
            "id": "MS-001",
            "titulo": "Operação de teste",
            "tipo": "missao",
            "descricao": "Descrição da operação",
            "recompensa_xp": 120,
            "dificuldade": "Intermediária",
            "prazo": "7 dias",
            "requisitos": "Participar de uma partida",
            "ativa": True,
        }
        estatisticas = {
            "pendente": 1,
            "aprovada": 2,
            "rejeitada": 0,
            "total": 3,
            "participantes": 2,
            "xp_liberado_estimado": 240,
            "registros": [{"id": "REV-001", "autor_id": 123, "status": "aprovada", "timestamp": 1}],
        }
        embed = _embed_central([atividade], atividade, estatisticas)
        campos = {campo.name: campo.value for campo in embed.fields}
        self.assertIn("\n", campos["◈ PARÂMETROS DA ATIVIDADE"])
        self.assertNotIn("\\n", campos["◈ PARÂMETROS DA ATIVIDADE"])
        self.assertIn("\n", campos["◈ INDICADORES"])

    def test_embed_da_central_aplica_identidade_do_servidor_e_bot(self):
        guild = SimpleNamespace(
            icon=SimpleNamespace(url="https://example.com/server.png"),
            banner=SimpleNamespace(url="https://example.com/banner.png"),
        )
        bot = SimpleNamespace(
            user=SimpleNamespace(display_avatar=SimpleNamespace(url="https://example.com/bot.png"))
        )
        embed = _embed_central([], guild=guild, bot=bot)
        self.assertEqual(embed.thumbnail.url, "https://example.com/server.png")
        self.assertEqual(embed.image.url, "https://example.com/banner.png")
        self.assertEqual(embed.author.icon_url, "https://example.com/bot.png")


if __name__ == "__main__":
    unittest.main()
