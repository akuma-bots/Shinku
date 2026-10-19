import unittest
from types import SimpleNamespace

from cogs.antiraid import AntiRaid


def membro(user_id=123, bot=False, owner_id=999, administrator=False, manage_guild=False):
    return SimpleNamespace(
        id=user_id,
        bot=bot,
        guild=SimpleNamespace(owner_id=owner_id),
        guild_permissions=SimpleNamespace(
            administrator=administrator,
            manage_guild=manage_guild,
        ),
    )


class TestGuardrailsAntiRaid(unittest.TestCase):
    def test_membro_comum_elegivel(self):
        self.assertTrue(AntiRaid._alvo_elegivel(membro()))

    def test_bot_nao_e_expulso(self):
        self.assertFalse(AntiRaid._alvo_elegivel(membro(bot=True)))

    def test_dono_nao_e_expulso(self):
        self.assertFalse(AntiRaid._alvo_elegivel(membro(user_id=999)))

    def test_administrador_nao_e_expulso(self):
        self.assertFalse(AntiRaid._alvo_elegivel(membro(administrator=True)))

    def test_membro_com_manage_guild_nao_e_expulso(self):
        self.assertFalse(AntiRaid._alvo_elegivel(membro(manage_guild=True)))


if __name__ == "__main__":
    unittest.main()
