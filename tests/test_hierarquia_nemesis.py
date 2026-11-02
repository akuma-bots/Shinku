import unittest
from types import SimpleNamespace
from unittest.mock import patch

from utils import guild_config


class FakeMember:
    def __init__(self, role_ids, positions=None, user_id=123):
        self.id = user_id
        self.guild = SimpleNamespace(
            id=guild_config.GUILD_NEMESIS_ID,
            owner_id=999,
            default_role=SimpleNamespace(id=0),
        )
        positions = positions or {}
        self.roles = [
            SimpleNamespace(id=role_id, position=positions.get(role_id, 1))
            for role_id in role_ids
        ]


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

    def test_hierarquia_impede_acao_contra_cargo_igual_ou_superior(self):
        veterano_id = 1563995879998754938
        elite_id = 1563995879995874937
        comandante_id = 1563995879998754940
        autor = FakeMember([veterano_id], user_id=1)
        alvo_inferior = FakeMember([elite_id], user_id=2)
        alvo_superior = FakeMember([comandante_id], user_id=3)
        autor.roles[0].position = 20
        alvo_inferior.roles[0].position = 10
        alvo_superior.roles[0].position = 30
        self.assertTrue(guild_config.membro_pode_gerenciar_membro(autor, alvo_inferior))
        self.assertFalse(guild_config.membro_pode_gerenciar_membro(autor, alvo_superior))

    def test_nao_pode_atribuir_cargo_acima_da_propria_autoridade(self):
        veterano_id = 1563995879998754938
        comandante_id = 1563995879998754940
        elite_id = 1563995879995874937
        autor = FakeMember([veterano_id], user_id=1)
        cargo_comandante = SimpleNamespace(id=comandante_id, position=30)
        cargo_elite = SimpleNamespace(id=elite_id, position=10)
        autor.roles[0].position = 20
        self.assertFalse(guild_config.membro_pode_atribuir_cargo_hierarquico(autor, cargo_comandante))
        self.assertTrue(guild_config.membro_pode_atribuir_cargo_hierarquico(autor, cargo_elite))

    def test_octogono_e_o_unico_cargo_autorizado_a_gerir_missoes(self):
        membro = self._member([guild_config.CARGO_OCTOGONO_ID])
        self.assertTrue(guild_config.membro_tem_lideranca(membro))
        self.assertTrue(guild_config.membro_tem_octogono(membro))
        self.assertTrue(guild_config.membro_pode_promover_rebaixar_banir(membro))
        self.assertTrue(guild_config.membro_pode_revisar_categoria(membro, "missao"))

    def test_cargos_acima_de_elite_podem_executar_acoes_hierarquicas(self):
        elite = self._member([1563995879995874937])
        self.assertFalse(guild_config.membro_pode_promover_rebaixar_banir(elite))
        for role_id in guild_config.CARGOS_ACIMA_ELITE_IDS:
            with self.subTest(role_id=role_id):
                membro = self._member([role_id])
                self.assertTrue(guild_config.membro_pode_promover_rebaixar_banir(membro))
                self.assertFalse(guild_config.membro_tem_lideranca(membro))


if __name__ == "__main__":
    unittest.main()
