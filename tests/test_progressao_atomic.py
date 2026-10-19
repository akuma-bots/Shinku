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

    async def test_perfil_legado_invalido_e_reparado(self):
        self.dados = {"123": {"membros": {"456": "dado-inválido"}}}

        perfil = await self.cog._perfil(123, 456)

        self.assertEqual(perfil["xp"], 0)
        self.assertEqual(perfil["historico_ranks"], [])
        self.assertIsInstance(self.dados["123"]["membros"]["456"], dict)


if __name__ == "__main__":
    unittest.main()
