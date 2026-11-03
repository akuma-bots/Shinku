import unittest

from utils.historico_membros import filtrar_revisoes_membro, _resumo_revisoes


class TestHistoricoMembros(unittest.TestCase):
    def test_inclui_autor_e_auxiliar_sem_duplicar_protocolo(self):
        registros = [
            {"id": "a", "autor_id": 10, "auxiliar_id": 20, "status": "aprovada", "tipo": "missao", "timestamp": 100},
            {"id": "b", "autor_id": 30, "auxiliar_id": 10, "status": "pendente", "tipo": "pvp", "timestamp": 200},
            {"id": "c", "autor_id": 40, "auxiliar_id": None, "status": "rejeitada", "tipo": "contribuicao", "timestamp": 300},
            {"id": "b", "autor_id": 10, "auxiliar_id": None, "status": "aprovada", "tipo": "pvp", "timestamp": 250},
        ]
        resultado = filtrar_revisoes_membro(registros, 10)
        self.assertEqual([item["id"] for item in resultado], ["b", "a"])

    def test_resumo_separa_status_e_categoria(self):
        resumo = _resumo_revisoes([
            {"status": "aprovada", "tipo": "missao"},
            {"status": "aprovada", "tipo": "missao"},
            {"status": "pendente", "tipo": "pvp"},
            {"status": "rejeitada", "tipo": "contribuicao"},
        ])
        self.assertEqual(resumo["total"], 4)
        self.assertEqual(resumo["aprovadas"], 2)
        self.assertEqual(resumo["pendentes"], 1)
        self.assertEqual(resumo["rejeitadas"], 1)
        self.assertEqual(resumo["por_tipo"]["missao"], 2)

    def test_ignora_registros_invalidos_e_nao_correlacionados(self):
        resultado = filtrar_revisoes_membro([None, "invalido", {"id": "x", "autor_id": 99}], 10)
        self.assertEqual(resultado, [])


if __name__ == "__main__":
    unittest.main()

class TestHistoricoEmbeds(unittest.TestCase):
    def test_linha_do_tempo_respeita_limite_de_campos_discord(self):
        from utils.historico_membros import _embed_registros

        eventos = [
            {
                "categoria": "historico_membros",
                "titulo": f"Evento {i}",
                "descricao": "Detalhes do evento " * 20,
                "timestamp": 1_700_000_000 + i,
                "url": f"https://discord.com/channels/1/2/{i}",
            }
            for i in range(18)
        ]
        embed = _embed_registros({"eventos": eventos})
        self.assertTrue(embed.fields)
        self.assertTrue(all(len(campo.value) <= 1024 for campo in embed.fields))
        self.assertLessEqual(len(embed.fields), 25)


class TestPainelHistoricoRegistro(unittest.TestCase):
    def test_painel_persistente_sem_comando_slash(self):
        from cogs.logs import PainelHistoricoMembrosView, SeletorMembroRegistroView
        from utils import historico_membros

        painel = PainelHistoricoMembrosView()
        seletor = SeletorMembroRegistroView(123)
        self.assertIsNone(painel.timeout)
        self.assertEqual(painel.children[0].custom_id, "nemesis:registro:membro:abrir")
        self.assertEqual(seletor.children[0].custom_id, "nemesis:registro:membro:selecionar")
        self.assertFalse(hasattr(historico_membros, "HistoricoMembros"))


class TestTimeoutCompatibilidade(unittest.TestCase):
    def test_usa_atributo_timed_out_until_do_discord_py(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from utils.historico_membros import _timeout_membro

        data = datetime(2026, 11, 3, tzinfo=timezone.utc)
        self.assertEqual(_timeout_membro(SimpleNamespace(timed_out_until=data)), data)

    def test_fallback_para_forks_com_communication_disabled_until(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from utils.historico_membros import _timeout_membro

        data = datetime(2026, 11, 3, tzinfo=timezone.utc)
        self.assertEqual(_timeout_membro(SimpleNamespace(communication_disabled_until=data)), data)

    def test_membro_sem_timeout(self):
        from types import SimpleNamespace
        from utils.historico_membros import _timeout_membro

        self.assertIsNone(_timeout_membro(SimpleNamespace()))
