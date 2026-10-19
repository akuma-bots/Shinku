import unittest
from types import SimpleNamespace

from cogs.autocargo import _cargo_atribuivel


class Cargo:
    def __init__(self, position=1, default=False, managed=False):
        self.position = position
        self.managed = managed
        self.default = default

    def is_default(self):
        return self.default

    def __lt__(self, other):
        return self.position < other.position


def guild(manage_roles=True, top_position=10):
    return SimpleNamespace(
        me=SimpleNamespace(
            guild_permissions=SimpleNamespace(manage_roles=manage_roles),
            top_role=Cargo(position=top_position),
        )
    )


class TestSegurancaCargoAutomatico(unittest.TestCase):
    def test_aceita_cargo_abaixo_do_bot(self):
        self.assertTrue(_cargo_atribuivel(guild(), Cargo(position=3)))

    def test_rejeita_cargo_acima_ou_igual_ao_bot(self):
        self.assertFalse(_cargo_atribuivel(guild(top_position=3), Cargo(position=3)))
        self.assertFalse(_cargo_atribuivel(guild(top_position=3), Cargo(position=5)))

    def test_rejeita_cargo_padrao_ou_gerenciado(self):
        self.assertFalse(_cargo_atribuivel(guild(), Cargo(default=True)))
        self.assertFalse(_cargo_atribuivel(guild(), Cargo(managed=True)))

    def test_rejeita_sem_permissao_ou_membro_do_bot(self):
        self.assertFalse(_cargo_atribuivel(guild(manage_roles=False), Cargo()))
        self.assertFalse(_cargo_atribuivel(SimpleNamespace(me=None), Cargo()))


if __name__ == "__main__":
    unittest.main()
