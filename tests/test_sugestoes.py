import unittest
from types import SimpleNamespace
from unittest.mock import patch

from cogs.sugestoes import (
    CATEGORIAS,
    STATUS,
    STATUS_TERMINAIS,
    _contagem_votos,
    _normalizar_categoria,
    _registrar_voto,
    _embed_sugestao,
    _embed_painel_administrativo,
    PainelSugestoesView,
    PublicacaoSugestaoView,
    _esta_no_canal_sugestoes,
    CANAL_SUGESTOES_ID,
    GUILD_NEMESIS_ID,
)


class TestSistemaSugestoes(unittest.TestCase):
    def test_categorias_oficiais_estao_disponiveis(self):
        self.assertIn("Sistemas", CATEGORIAS)
        self.assertIn("Comunidade", CATEGORIAS)
        self.assertIn("Outros", CATEGORIAS)

    def test_painel_em_thread_de_forum_e_reconhecido_como_canal_oficial(self):
        class FakeThread:
            def __init__(self, parent_id):
                self.parent_id = parent_id
                self.id = 900

        interacao = SimpleNamespace(
            guild_id=GUILD_NEMESIS_ID,
            channel=FakeThread(CANAL_SUGESTOES_ID),
        )
        with patch("cogs.sugestoes.discord.Thread", FakeThread):
            self.assertTrue(_esta_no_canal_sugestoes(interacao))

    def test_categoria_aceita_acentos_e_apelidos(self):
        self.assertEqual(_normalizar_categoria("Missões"), "Missões e operações")
        self.assertEqual(_normalizar_categoria("operacoes"), "Missões e operações")
        self.assertEqual(_normalizar_categoria("categoria desconhecida"), "Outros")

    def test_voto_unico_pode_ser_alterado_ou_removido(self):
        votos = _registrar_voto({}, 10, "apoia")
        self.assertEqual(votos, {"10": "apoia"})
        votos = _registrar_voto(votos, 10, "nao_apoia")
        self.assertEqual(votos, {"10": "nao_apoia"})
        votos = _registrar_voto(votos, 10, "nao_apoia")
        self.assertEqual(votos, {})

    def test_contagem_e_percentual_refletem_votos(self):
        votos = {"1": "apoia", "2": "apoia", "3": "nao_apoia"}
        self.assertEqual(_contagem_votos(votos), (2, 1))
        registro = {
            "id": 123, "titulo": "Ideia", "descricao": "Descrição",
            "autor_id": 1, "categoria": "Sistemas", "status": "pendente",
            "votos": votos,
        }
        embed = _embed_sugestao(registro)
        self.assertIn("67%", embed.fields[5].value)

    def test_status_terminais_encerram_votacao(self):
        self.assertEqual(STATUS_TERMINAIS, {"rejeitada", "implementada"})
        self.assertIn("aprovada", STATUS)
        self.assertIn("analise", STATUS)

    def test_paineis_publicos_sao_persistentes_e_nao_criam_comandos(self):
        painel = PainelSugestoesView()
        publicacao = PublicacaoSugestaoView()
        self.assertIsNone(painel.timeout)
        self.assertIsNone(publicacao.timeout)
        self.assertEqual(len(painel.children), 2)
        self.assertEqual(len(publicacao.children), 4)
        self.assertTrue(all(item.custom_id for item in painel.children + publicacao.children))

    def test_painel_administrativo_exibe_contagens_e_populares(self):
        registros = {
            "101": {"id": 101, "titulo": "Sistema novo", "status": "pendente", "votos": {"1": "apoia"}},
            "102": {"id": 102, "titulo": "Evento", "status": "implementada", "votos": {"1": "apoia", "2": "apoia"}},
        }
        embed = _embed_painel_administrativo(registros, "populares")
        self.assertIn("2", embed.fields[0].value)
        self.assertIn("Evento", embed.fields[-1].value)


if __name__ == "__main__":
    unittest.main()

