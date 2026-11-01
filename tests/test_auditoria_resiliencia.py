import unittest
from unittest.mock import AsyncMock, Mock, patch

from utils import auditoria


class TestResilienciaAuditoria(unittest.IsolatedAsyncioTestCase):
    async def test_delega_para_topico_global_de_administracao(self):
        guild = Mock()
        guild.id = 1563995879981981817
        with patch("utils.registro_global.registrar", new=AsyncMock(return_value=True)) as registrar:
            resultado = await auditoria.registrar(guild, "Teste", "Detalhes <@999>")
        self.assertTrue(resultado)
        registrar.assert_awaited_once_with(
            guild, "administracao", "Teste", "Detalhes <@999>", cor=0x99AAB5,
        )

    async def test_permite_especificar_categoria(self):
        guild = Mock()
        guild.id = 1563995879981981817
        with patch("utils.registro_global.registrar", new=AsyncMock(return_value=True)) as registrar:
            resultado = await auditoria.registrar(
                guild, "Revisão aprovada", "Detalhes", categoria="sistemas",
            )
        self.assertTrue(resultado)
        self.assertEqual(registrar.await_args.args[1], "sistemas")

    async def test_retorna_false_quando_registro_global_falha(self):
        guild = Mock()
        guild.id = 1563995879981981817
        with patch("utils.registro_global.registrar", new=AsyncMock(return_value=False)):
            resultado = await auditoria.registrar(guild, "Teste", "Detalhes")
        self.assertFalse(resultado)


if __name__ == "__main__":
    unittest.main()
