import unittest
from unittest.mock import AsyncMock, patch

from cogs.guerras import Guerras, _inteiro_seguro


class TestIntegridadeGuerras(unittest.IsolatedAsyncioTestCase):
    async def test_storage_raiz_invalido_usa_dados_padrao(self):
        cog = object.__new__(Guerras)
        with patch("cogs.guerras.carregar", new=AsyncMock(return_value=[])):
            dados = await cog._dados_guild(123)

        self.assertEqual(dados["guild_id"], 123)
        self.assertEqual(dados["temporada_atual"], 1)
        self.assertEqual(dados["guerras"], [])
        self.assertEqual(dados["agendamentos"], [])

    async def test_registros_corrompidos_sao_filtrados(self):
        cog = object.__new__(Guerras)
        storage = {
            "123": {
                "temporada_atual": "inválida",
                "guerras": [None, "texto", {"codigo": "G-1"}],
                "agendamentos": {"inválido": True},
                "regras": ["Regra válida", None, ""],
            }
        }
        with patch("cogs.guerras.carregar", new=AsyncMock(return_value=storage)):
            dados = await cog._dados_guild(123)

        self.assertEqual(dados["temporada_atual"], 1)
        self.assertEqual(dados["guerras"], [{"codigo": "G-1"}])
        self.assertEqual(dados["agendamentos"], [])
        self.assertEqual(dados["regras"], ["Regra válida"])

    async def test_salvamento_normaliza_dados_antes_de_persistir(self):
        cog = object.__new__(Guerras)
        with patch("cogs.guerras.carregar", new=AsyncMock(return_value={})), patch(
            "cogs.guerras.salvar", new=AsyncMock()
        ) as salvar:
            await cog._salvar_dados_guild(123, {
                "temporada_atual": -5,
                "guerras": [None, {"codigo": "G-1"}],
                "agendamentos": "inválido",
                "regras": "inválido",
            })

        dados_salvos = salvar.await_args.args[1]["123"]
        self.assertEqual(dados_salvos["temporada_atual"], 1)
        self.assertEqual(dados_salvos["guerras"], [{"codigo": "G-1"}])
        self.assertEqual(dados_salvos["agendamentos"], [])
        self.assertEqual(dados_salvos["regras"], [
            "Respeitar todos os participantes e a staff.",
            "É proibido usar cheats, exploits ou qualquer vantagem ilegal.",
            "A guerra deve seguir o formato combinado antes do início.",
            "O resultado deve ter prova válida quando a staff solicitar.",
            "É proibido falsificar placares ou provas.",
            "A staff pode anular resultados com evidências de irregularidades.",
        ])

    async def test_conversao_inteiro_segura(self):
        self.assertEqual(_inteiro_seguro("12"), 12)
        self.assertEqual(_inteiro_seguro("x", 7), 7)


if __name__ == "__main__":
    unittest.main()
