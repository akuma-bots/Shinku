import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils import guild_config


class FakeMember:
    def __init__(self, role_ids):
        self.guild = SimpleNamespace(id=guild_config.GUILD_NEMESIS_ID)
        self.roles = [SimpleNamespace(id=role_id) for role_id in role_ids]


class TestHierarquiaNemesis(unittest.TestCase):
    def _member(self, role_ids):
        return FakeMember(role_ids)

    def setUp(self):
        self.patch_member = patch.object(guild_config.discord, "Member", FakeMember)
        self.patch_member.start()
        self.addCleanup(self.patch_member.stop)

    def test_supervisor_staff_nao_e_cargo_administrativo(self):
        membro = self._member([1563995880007139422])
        self.assertFalse(guild_config.membro_tem_lideranca(membro))
        self.assertFalse(guild_config.membro_tem_octogono(membro))

    def test_direcao_staff_tem_acesso_administrativo_sem_gerir_missoes(self):
        membro = self._member([1563995880007139424])
        self.assertTrue(guild_config.membro_tem_lideranca(membro))
        self.assertFalse(guild_config.membro_tem_octogono(membro))
        self.assertFalse(guild_config.membro_pode_revisar_categoria(membro, "missao"))
        self.assertTrue(guild_config.membro_pode_revisar_categoria(membro, "pvp"))

    def test_octogono_e_o_unico_cargo_autorizado_a_gerir_missoes(self):
        membro = self._member([guild_config.CARGO_OCTOGONO_ID])
        self.assertTrue(guild_config.membro_tem_lideranca(membro))
        self.assertTrue(guild_config.membro_tem_octogono(membro))
        self.assertTrue(guild_config.membro_pode_revisar_categoria(membro, "missao"))

    def test_cargos_acima_de_elite_podem_executar_acoes_hierarquicas(self):
        elite = self._member([1563995879998754937])
        self.assertFalse(guild_config.membro_pode_promover_rebaixar_banir(elite))
        for role_id in guild_config.CARGOS_ACIMA_ELITE_IDS:
            with self.subTest(role_id=role_id):
                membro = self._member([role_id])
                self.assertTrue(guild_config.membro_pode_promover_rebaixar_banir(membro))
                self.assertFalse(guild_config.membro_tem_lideranca(membro))


if __name__ == "__main__":
    unittest.main()
