import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import discord
from cogs.desafios import Desafios
from utils import desafios


class TestIntegridadeDesafios(unittest.IsolatedAsyncioTestCase):
    async def test_botao_de_desafio_retorna_erro_privado_se_storage_falhar(self):
        interaction = SimpleNamespace(
            type=discord.InteractionType.component,
            data={"custom_id": "desafio:aceitar:duelo-1"},
            guild=SimpleNamespace(id=123),
            user=SimpleNamespace(id=20),
            response=SimpleNamespace(defer=AsyncMock()),
            followup=SimpleNamespace(send=AsyncMock()),
        )
        cog = object.__new__(Desafios)
        with patch("cogs.desafios.desafios.get", AsyncMock(side_effect=RuntimeError("Redis offline"))):
            await Desafios.on_interaction(cog, interaction)
        interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
        interaction.followup.send.assert_awaited_once()
        self.assertTrue(interaction.followup.send.await_args.kwargs["ephemeral"])
        self.assertIn("Nenhuma ação foi aplicada", interaction.followup.send.await_args.args[0])

    async def test_rejeita_aposta_negativa_sem_gravar(self):
        with patch.object(desafios, "carregar", new=AsyncMock(return_value={})), patch.object(
            desafios, "salvar", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "não pode ser negativa"):
                await desafios.criar(123, 10, 20, -1)

        salvar.assert_not_awaited()

    async def test_rejeita_desafio_contra_si_proprio(self):
        with patch.object(desafios, "carregar", new=AsyncMock(return_value={})), patch.object(
            desafios, "salvar", new=AsyncMock()
        ) as salvar:
            with self.assertRaisesRegex(ValueError, "si mesmo"):
                await desafios.criar(123, 10, 10, 0)

        salvar.assert_not_awaited()

    async def test_criacoes_concorrentes_nao_criam_duelo_duplicado(self):
        dados = {}
        with patch.object(desafios, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            desafios, "salvar", new=AsyncMock()
        ) as salvar:
            resultados = await asyncio.gather(
                desafios.criar(123, 10, 20, 0),
                desafios.criar(123, 20, 10, 0),
                return_exceptions=True,
            )

        criados = [r for r in resultados if isinstance(r, dict)]
        erros = [r for r in resultados if isinstance(r, ValueError)]
        self.assertEqual(len(criados), 1)
        self.assertEqual(len(erros), 1)
        salvar.assert_awaited_once()

    async def test_dados_legados_corrompidos_nao_quebram_listagem(self):
        dados = {"123": [None, "texto", {"id": "ok", "status": "pendente", "timestamp": "inválido"}]}
        with patch.object(desafios, "carregar", new=AsyncMock(return_value=dados)):
            lista = await desafios._lista_guild(123)
            ultimo = await desafios.get_ultimo_entre(123, 10, 20)

        self.assertEqual(len(lista), 1)
        self.assertIsNone(ultimo)

    async def test_registro_global_de_duelo_so_e_marcado_uma_vez(self):
        dados = {"123": [{"id": "duelo-1", "status": "concluido"}]}
        with patch.object(desafios, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            desafios, "salvar", new=AsyncMock()
        ) as salvar:
            primeiro = await desafios.marcar_registro_global(123, "duelo-1")
            segundo = await desafios.marcar_registro_global(123, "duelo-1")

        self.assertTrue(primeiro)
        self.assertFalse(segundo)
        salvar.assert_awaited_once()

    async def test_resultado_so_aceita_participantes_do_duelo(self):
        dados = {
            "123": [{
                "id": "duelo-1",
                "status": "aceito",
                "desafiante_id": 10,
                "desafiado_id": 20,
            }]
        }
        with patch.object(desafios, "carregar", new=AsyncMock(return_value=dados)), patch.object(
            desafios, "salvar", new=AsyncMock()
        ) as salvar:
            resultado = await desafios.definir_resultado(123, "duelo-1", 99, 20)

        self.assertIsNone(resultado)
        salvar.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
