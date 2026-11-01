import unittest
from unittest.mock import AsyncMock, patch

from utils import temporadas_missoes


class TestTemporadasMissoes(unittest.IsolatedAsyncioTestCase):
    def test_normaliza_estado_corrompido_sem_perder_historico_valido(self):
        estado = temporadas_missoes._normalizar_estado({
            "numero_atual": -2,
            "duracao_dias": 900,
            "meta_xp": "invalida",
            "inicio_timestamp": "nan",
            "historico": [{"numero": 1}],
            "recompensas": None,
        })
        self.assertEqual(estado["numero_atual"], 1)
        self.assertEqual(estado["duracao_dias"], 365)
        self.assertEqual(estado["meta_xp"], 10000)
        self.assertIsNone(estado["inicio_timestamp"])
        self.assertEqual(estado["historico"], [{"numero": 1}])
        self.assertEqual(estado["recompensas"]["1"], "Distinção de Campeão da Temporada")

    async def test_rejeita_duracao_e_meta_fora_dos_limites(self):
        async def atualizar(_guild_id, transformador):
            return transformador(temporadas_missoes._normalizar_estado({}))

        with patch.object(temporadas_missoes, "_atualizar_estado", new=AsyncMock(side_effect=atualizar)) as salvar:
            with self.assertRaisesRegex(ValueError, "1 e 365"):
                await temporadas_missoes.configurar(123, duracao_dias=0)
            with self.assertRaisesRegex(ValueError, "1 e 100.000.000"):
                await temporadas_missoes.configurar(123, meta_xp=-1)
        salvar.assert_not_awaited()

    async def test_configuracao_inicia_temporada_e_define_prazo(self):
        estado = temporadas_missoes._normalizar_estado({})

        async def atualizar(_guild_id, transformador):
            return transformador(estado)

        with patch.object(temporadas_missoes, "_atualizar_estado", new=AsyncMock(side_effect=atualizar)) as salvar:
            resultado = await temporadas_missoes.configurar(
                123, agora=1000, duracao_dias=7, meta_xp=5000,
                recompensa_1="Medalha sazonal",
            )
        self.assertEqual(resultado["inicio_timestamp"], 1000)
        self.assertEqual(resultado["fim_timestamp"], 1000 + 7 * 86400)
        self.assertEqual(resultado["meta_xp"], 5000)
        self.assertEqual(resultado["recompensas"]["1"], "Medalha sazonal")
        salvar.assert_awaited_once()

    async def test_ranking_considera_apenas_missoes_aprovadas_no_periodo(self):
        registros = [
            {"id": "A", "tipo": "missao", "status": "aprovada", "autor_id": 10,
             "auxiliar_id": 20, "recompensa_xp": 100, "aprovado_em": 150},
            {"id": "B", "tipo": "especial", "status": "aprovada", "autor_id": 10,
             "recompensa_xp": 50, "aprovado_em": 180},
            {"id": "C", "tipo": "contribuicao", "status": "pendente", "autor_id": 30,
             "recompensa_xp": 900, "aprovado_em": 160},
            {"id": "D", "tipo": "pvp", "status": "aprovada", "autor_id": 40,
             "recompensa_xp": 900, "aprovado_em": 160},
            {"id": "E", "tipo": "missao", "status": "aprovada", "autor_id": 50,
             "recompensa_xp": 900, "aprovado_em": 99},
            {"id": "F", "tipo": "missao", "status": "aprovada", "autor_id": 60,
             "recompensa_xp": 900, "aprovado_em": 201},
            {"id": "A", "tipo": "missao", "status": "aprovada", "autor_id": 10,
             "auxiliar_id": 20, "recompensa_xp": 100, "aprovado_em": 150},
        ]
        with patch.object(temporadas_missoes.revisoes, "listar", new=AsyncMock(return_value=registros)):
            resultado = await temporadas_missoes.calcular_resultados(123, 100, 200, agora=200)

        self.assertEqual(
            resultado["ranking"],
            [
                {"user_id": 10, "xp": 110, "posicao": 1},
                {"user_id": 20, "xp": 40, "posicao": 2},
            ],
        )
        self.assertEqual(resultado["xp_coletivo"], 150)
        self.assertEqual(resultado["provas_aprovadas"], 2)
        self.assertEqual(resultado["participantes"], 2)

    async def test_encerramento_arquiva_resultados_e_abre_nova_sem_mexer_em_perfis(self):
        estado = temporadas_missoes._normalizar_estado({
            "numero_atual": 4,
            "inicio_timestamp": 100,
            "fim_timestamp": 200,
            "duracao_dias": 30,
            "meta_xp": 1000,
            "historico": [],
        })
        resultados = {
            "ranking": [{"user_id": 77, "xp": 300, "posicao": 1}],
            "xp_coletivo": 300,
            "provas_aprovadas": 2,
            "participantes": 1,
        }
        async def atualizar(_guild_id, transformador):
            return transformador(estado)

        with patch.object(temporadas_missoes, "get_estado", new=AsyncMock(return_value=estado)), patch.object(
            temporadas_missoes, "calcular_resultados", new=AsyncMock(return_value=resultados)
        ), patch.object(temporadas_missoes, "_atualizar_estado", new=AsyncMock(side_effect=atualizar)) as salvar:
            registro = await temporadas_missoes.encerrar_temporada(123, agora=200)

        self.assertEqual(registro["numero"], 4)
        self.assertEqual(registro["ranking"][0]["user_id"], 77)
        self.assertEqual(estado["historico"][-1]["numero"], 4)
        self.assertEqual(estado["numero_atual"], 5)
        self.assertEqual(estado["inicio_timestamp"], 200)
        self.assertEqual(estado["fim_timestamp"], 200 + 30 * 86400)
        self.assertEqual(len(estado["anuncios_pendentes"]), 1)
        salvar.assert_awaited_once()

    async def test_conquistas_pessoais_sao_lidas_do_historico_sazonal(self):
        estado = temporadas_missoes._normalizar_estado({
            "historico": [
                {
                    "numero": 2,
                    "encerrada_em": 300,
                    "meta_atingida": True,
                    "recompensas": {"1": "Medalha de ouro"},
                    "ranking": [{"user_id": 77, "xp": 900, "posicao": 1}],
                },
                {
                    "numero": 1,
                    "encerrada_em": 200,
                    "meta_atingida": False,
                    "recompensas": {"3": "Destaque"},
                    "ranking": [{"user_id": 77, "xp": 100, "posicao": 3}],
                },
            ]
        })
        with patch.object(temporadas_missoes, "get_estado", new=AsyncMock(return_value=estado)):
            conquistas = await temporadas_missoes.listar_recompensas_usuario(123, 77)
        self.assertEqual([item["temporada"] for item in conquistas], [2, 1])
        self.assertEqual(conquistas[0]["recompensa"], "Medalha de ouro")
        self.assertEqual(conquistas[1]["posicao"], 3)

    async def test_meta_coletiva_e_percentual_limitado_a_cem(self):
        estado = temporadas_missoes._normalizar_estado({
            "inicio_timestamp": 100,
            "fim_timestamp": 200,
            "meta_xp": 100,
        })
        resultado_base = {
            "ranking": [], "xp_coletivo": 250,
            "provas_aprovadas": 5, "participantes": 3,
        }
        with patch.object(temporadas_missoes, "get_estado", new=AsyncMock(return_value=estado)), patch.object(
            temporadas_missoes, "calcular_resultados", new=AsyncMock(return_value=resultado_base)
        ):
            resultado = await temporadas_missoes.obter_status(123, agora=150)
        self.assertTrue(resultado["meta_atingida"])
        self.assertEqual(resultado["progresso_percentual"], 100)


if __name__ == "__main__":
    unittest.main()


class TestCentralTemporadasSemComandos(unittest.TestCase):
    def test_cog_de_temporadas_nao_registra_comandos_slash(self):
        from cogs.temporadas_missoes import TemporadasMissoes
        self.assertEqual(TemporadasMissoes.__cog_app_commands__, [])
