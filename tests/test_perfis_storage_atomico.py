import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import perfis, storage


class TestPerfisStorageAtomico(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.patchers = [
            patch.object(storage, "DATA_DIR", Path(self.tempdir.name)),
            patch.object(storage, "USANDO_UPSTASH", False),
            patch.object(storage, "UPSTASH_CONFIG_INCOMPLETA", False),
        ]
        for item in self.patchers:
            item.start()
            self.addCleanup(item.stop)

    async def test_atualizacoes_concorrentes_preservam_xp(self):
        async def incrementar(_):
            return await perfis.atualizar_perfil(
                100, 200,
                lambda perfil: {**perfil, "xp": perfil["xp"] + 1},
            )
        await asyncio.gather(*(incrementar(i) for i in range(60)))
        perfil = await perfis.get_perfil(100, 200)
        self.assertEqual(perfil["xp"], 60)

    async def test_atualizacao_preserva_perfil_que_existia_apenas_no_competitivo(self):
        await storage.salvar("competitivo.json", {
            "catalogo": [],
            "perfis": {
                "404": {
                    "discordId": "404", "xp": 125,
                    "vitorias": 4, "derrotas": 2, "kills": 9,
                }
            },
        })
        perfil = await perfis.atualizar_perfil(
            103, 404, lambda atual: {**atual, "xp": atual["xp"] + 5}
        )
        self.assertEqual(perfil["xp"], 130)
        self.assertEqual(perfil["vitorias"], 4)
        self.assertEqual(perfil["kills"], 9)

    async def test_resultado_de_guerra_com_evento_e_idempotente(self):
        primeira = await perfis.registrar_resultado_guerra(
            101, 201, True, foi_mvp=True, evento_id="guerra:temporada-1:partida-4"
        )
        segunda = await perfis.registrar_resultado_guerra(
            101, 201, True, foi_mvp=True, evento_id="guerra:temporada-1:partida-4"
        )
        self.assertEqual(primeira["perfil"]["xp"], 50)
        self.assertEqual(segunda["perfil"]["xp"], 50)
        self.assertEqual(segunda["perfil"]["vitorias"], 1)
        self.assertEqual(segunda["perfil"]["mvps"], 1)
        competitivo = await storage.carregar("competitivo.json", {})
        registro = competitivo["perfis"]["201"]
        self.assertEqual(registro["pontos"], 60)
        self.assertEqual(registro["xp"], 50)

    async def test_bonus_de_empate_e_pvp_nao_sobrescrevem_outros_campos(self):
        await perfis.atualizar_perfil(
            102, 202, lambda perfil: {**perfil, "xp": 250, "pontos_pve": 18}
        )
        await perfis.registrar_empate_guerra(
            102, 202, evento_id="guerra:empate-1"
        )
        await perfis.registrar_pvp(
            102, 202, 203, evento_id="duelo:abc"
        )
        await perfis.registrar_pvp(
            102, 202, 203, evento_id="duelo:abc"
        )
        perfil = await perfis.get_perfil(102, 202)
        self.assertEqual(perfil["xp"], 265)
        self.assertEqual(perfil["empates"], 1)
        self.assertEqual(perfil["kills"], 1)
        self.assertEqual(perfil["pontos_pve"], 18)


if __name__ == "__main__":
    unittest.main()
