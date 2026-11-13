import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import discord

from cogs.tutorial import (
    TUTORIAIS, Tutorial, CANAL_TUTORIAIS_ID, TutorialDetalheLayoutView,
    TutorialIndiceLayoutView, _embed_indice, _embed_tutorial, _texto_embed_tutorial,
)
from utils.guia_servidores import CANAIS_GUIA_SERVIDORES, CARGO_VISITANTES_ID, TAG_ORG_NEMESIS


def test_tutorial_catalog_has_core_systems():
    assert len(TUTORIAIS) <= 25
    assert {"missoes", "guerras", "moderacao", "roblox", "avisos", "academia"}.issubset(TUTORIAIS)


def test_release_manifest_is_valid():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "config" / "novidades.json").read_text(encoding="utf-8"))
    assert data["release_id"]
    assert data["titulo"]
    assert data["mensagem"]


def test_tutorial_is_channel_panel_not_slash_command():
    assert CANAL_TUTORIAIS_ID == 1563995880833421512
    assert not hasattr(Tutorial, "tutorial")
    assert len(TUTORIAIS) <= 25


def test_welcome_guide_links_only_known_nemesis_channels():
    ids = [canal_id for _, canal_id, *_ in CANAIS_GUIA_SERVIDORES]
    assert len(ids) == len(set(ids))
    assert len(CANAIS_GUIA_SERVIDORES) <= 25
    assert all(canal_id > 0 for canal_id in ids)


def test_start_tutorial_explains_visitor_role_and_org_tag():
    texto = " ".join(TUTORIAIS["inicio"]["passos"])
    assert "Visitantes" in texto
    assert "NΞM" in texto
    assert CARGO_VISITANTES_ID == 1563995879990624371
    assert TAG_ORG_NEMESIS == "NΞM"


def test_visitor_role_is_part_of_automatic_entry_roles():
    from cogs.autocargo import CargoAutomatico

    assert CARGO_VISITANTES_ID in CargoAutomatico.CARGOS_ENTRADA


def test_tutorial_index_is_short_and_keeps_teaching_content_behind_selector():
    embed = _embed_indice()
    assert len(embed.fields) == 1
    assert "seletor" in embed.description.lower()
    assert "Começando na NÊMESIS" not in embed.description
    assert all(item["descricao"] not in embed.description for item in TUTORIAIS.values())



def _container_da_view(view):
    assert len(view.children) == 1
    container = view.children[0]
    assert isinstance(container, discord.ui.Container)
    return container


def test_todos_os_tutoriais_preservam_texto_e_controles_no_mesmo_cartao():
    for chave in TUTORIAIS:
        embed = _embed_tutorial(chave)
        esperado = _texto_embed_tutorial(embed)
        view = TutorialDetalheLayoutView(123, chave)
        container = _container_da_view(view)
        displays = [
            item for item in container.children
            if isinstance(item, discord.ui.TextDisplay)
        ]
        assert len(displays) >= 2
        assert "".join(item.content for item in displays[:-1]) == esperado
        assert all(len(item.content) <= 4000 for item in displays)

        linhas = [
            item for item in container.children
            if isinstance(item, discord.ui.ActionRow)
        ]
        assert len(linhas) == 2
        seletor, voltar = linhas[0].children[0], linhas[1].children[0]
        assert isinstance(seletor, discord.ui.Select)
        assert isinstance(voltar, discord.ui.Button)
        assert seletor.custom_id == f"nemesis:tutoriais:detalhe:123"
        assert voltar.custom_id == "nemesis:tutoriais:voltar:123"
        assert view.timeout == 900


def test_tutorial_longo_nao_perde_conteudo_ao_montar_components_v2():
    embed = discord.Embed(
        title="GUIA EXTENSO",
        description="Orientações completas para consulta.",
    )
    for indice in range(4):
        embed.add_field(name=f"ETAPA {indice + 1}", value=(f"conteudo-{indice}-" * 90), inline=False)
    esperado = _texto_embed_tutorial(embed)
    assert len(esperado) > 3900

    with patch("cogs.tutorial._embed_tutorial", return_value=embed):
        view = TutorialDetalheLayoutView(456, "inicio")

    container = _container_da_view(view)
    displays = [
        item for item in container.children
        if isinstance(item, discord.ui.TextDisplay)
    ]
    assert "".join(item.content for item in displays[:-1]) == esperado
    assert len(displays) >= 3
    assert all(len(item.content) <= 4000 for item in displays)


def test_indice_privado_mantem_seletor_aninhado_no_cartao():
    view = TutorialIndiceLayoutView(789)
    container = _container_da_view(view)
    linhas = [
        item for item in container.children
        if isinstance(item, discord.ui.ActionRow)
    ]
    assert len(linhas) == 1
    assert isinstance(linhas[0].children[0], discord.ui.Select)
    assert linhas[0].children[0].custom_id == "nemesis:tutoriais:indice:789"
    assert view.timeout == 900


async def _test_seletor_de_tutorial_restringe_consulta_ao_dono_e_navega():
    view = TutorialDetalheLayoutView(123, "inicio")
    container = _container_da_view(view)
    linha_seletor = next(
        item for item in container.children if isinstance(item, discord.ui.ActionRow)
    )
    seletor = linha_seletor.children[0]
    seletor._values = ["missoes"]

    negada = type("Interaction", (), {})()
    negada.user = type("User", (), {"id": 999})()
    negada.response = type("Response", (), {"send_message": AsyncMock()})()
    await seletor.callback(negada)
    negada.response.send_message.assert_awaited_once()
    assert negada.response.send_message.await_args.kwargs["ephemeral"] is True

    aceita = type("Interaction", (), {})()
    aceita.user = type("User", (), {"id": 123})()
    aceita.response = type("Response", (), {"edit_message": AsyncMock()})()
    await seletor.callback(aceita)
    aceita.response.edit_message.assert_awaited_once()
    nova_view = aceita.response.edit_message.await_args.kwargs["view"]
    assert isinstance(nova_view, TutorialDetalheLayoutView)
    assert nova_view.autor_id == 123



def test_seletor_de_tutorial_restringe_consulta_ao_dono_e_navega():
    asyncio.run(_test_seletor_de_tutorial_restringe_consulta_ao_dono_e_navega())
