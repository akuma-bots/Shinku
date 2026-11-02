import copy
import unittest
from unittest.mock import Mock

from cogs.progressao_gangue import ProgressaoGangue


class TestProgressaoAtomica(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dados = {}
        self.cog = ProgressaoGangue(Mock())

        async def carregar_dados():
            return copy.deepcopy(self.dados)

        async def salvar_dados(dados):
            self.dados = copy.deepcopy(dados)

        self.cog._dados = carregar_dados
        self.cog._salvar_dados = salvar_dados

    async def test_recompensa_com_mesmo_evento_so_aplica_uma_vez(self):
        primeiro = await self.cog._registrar_xp_atomico(
            123, 456, 75, evento_id="revisao:abc", tipo="missao",
        )
        segundo = await self.cog._registrar_xp_atomico(
            123, 456, 75, evento_id="revisao:abc", tipo="missao",
        )

        perfil = self.dados["123"]["membros"]["456"]
        self.assertTrue(primeiro[3])
        self.assertFalse(segundo[3])
        self.assertEqual(perfil["xp"], 75)
        self.assertEqual(perfil["missoes"], 1)
        self.assertEqual(perfil["eventos_recompensa"], ["revisao:abc"])

    async def test_recompensas_concorrentes_nao_sobrescrevem_xp(self):
        import asyncio

        resultados = await asyncio.gather(*[
            self.cog._registrar_xp_atomico(123, 456, 5, contar_mensagem=True)
            for _ in range(30)
        ])

        perfil = self.dados["123"]["membros"]["456"]
        self.assertEqual(perfil["xp"], 150)
        self.assertEqual(perfil["mensagens"], 30)
        self.assertEqual(sum(1 for resultado in resultados if resultado[3]), 30)


    async def test_leitura_de_perfil_existente_nao_persiste_sem_mudancas(self):
        self.dados = {
            "123": {
                "membros": {
                    "456": {
                        "xp": 250,
                        "mensagens": 4,
                        "missoes": 1,
                        "guerras": 0,
                        "rank_no": 8,
                        "ultimo_xp": 10,
                        "historico_ranks": [],
                    }
                }
            }
        }
        chamadas = 0
        salvar_original = self.cog._salvar_dados

        async def contar_salvamento(dados):
            nonlocal chamadas
            chamadas += 1
            await salvar_original(dados)

        self.cog._salvar_dados = contar_salvamento
        perfil = await self.cog._perfil(123, 456)

        self.assertEqual(perfil["xp"], 250)
        self.assertEqual(chamadas, 0)

    async def test_config_inicializa_cargos_padrao_sem_substituir_personalizados(self):
        self.dados = {"123": {"cargos": {"12": 999, "7": 111}}}

        config = await self.cog._config(123)

        self.assertEqual(config["cargos"]["12"], 999)
        self.assertEqual(config["cargos"]["7"], 111)
        self.assertEqual(config["cargos"]["11"], 1563995879990624374)
        self.assertEqual(config["cargos"]["1"], 1563995879998754943)
        self.assertEqual(self.dados["123"]["cargos"]["12"], 999)

    async def test_promocao_e_rebaixamento_manualmente_sao_atomicos_e_auditados(self):
        promovido, anterior, novo = await self.cog._definir_rank_atomico(
            123, 456, 16500,
            responsavel_id=1,
            motivo="Promoção aprovada",
            acao="Promoção",
        )
        self.assertEqual(anterior["nome"], "Lutador")
        self.assertEqual(novo["nome"], "Veterano")
        self.assertEqual(promovido["xp"], 16500)
        self.assertEqual(promovido["rank_no"], 6)
        registro = promovido["historico_ranks"][-1]
        self.assertEqual(registro["responsavel_id"], "1")
        self.assertEqual(registro["motivo"], "Promoção aprovada")

        rebaixado, anterior, novo = await self.cog._definir_rank_atomico(
            123, 456, 11500,
            responsavel_id=2,
            motivo="Revisão disciplinar",
            acao="Rebaixamento",
        )
        self.assertEqual(anterior["nome"], "Veterano")
        self.assertEqual(novo["nome"], "Elite")
        self.assertEqual(rebaixado["xp"], 11500)
        self.assertEqual(len(rebaixado["historico_ranks"]), 2)
        self.assertEqual(rebaixado["historico_ranks"][-1]["acao"], "Rebaixamento")

    async def test_perfil_legado_invalido_e_reparado(self):
        self.dados = {"123": {"membros": {"456": "dado-inválido"}}}

        perfil = await self.cog._perfil(123, 456)

        self.assertEqual(perfil["xp"], 0)
        self.assertEqual(perfil["historico_ranks"], [])
        self.assertIsInstance(self.dados["123"]["membros"]["456"], dict)


if __name__ == "__main__":
    unittest.main()
