import json
from pathlib import Path
from types import SimpleNamespace

from cogs.boas_vindas_dm import carregar_catalogo_codigos, TAG_GANGUE, CONVITE_NEMESIS, BoasVindasDM, BoasVindasLayoutView, CARGO_VISITANTES_ID
from utils.guia_servidores import TAG_ORG_NEMESIS, NOME_CARGO_VISITANTES, GuiaServidoresView, CANAIS_GUIA_SERVIDORES


def test_welcome_codes_catalog_has_all_games_and_requirements():
    catalogo = carregar_catalogo_codigos()
    assert {"shigaku", "gakuran", "fistborn"}.issubset(catalogo["jogos"])
    for jogo in ("shigaku", "gakuran", "fistborn"):
        dados = catalogo["jogos"][jogo]
        assert dados["codigos"]
        assert dados["requisitos"]
        assert dados["fonte"].startswith("https://")


def test_welcome_uses_nemesis_tag_and_invite():
    assert TAG_GANGUE == "NΞM"
    assert TAG_ORG_NEMESIS == "NΞM"
    assert CONVITE_NEMESIS.startswith("https://discord.gg/")


def test_welcome_uses_official_visitor_role():
    assert CARGO_VISITANTES_ID == 1563995879990624371
    assert NOME_CARGO_VISITANTES == "Visitantes"


def test_codes_catalog_is_valid_json():
    root = Path(__file__).resolve().parents[1]
    data = json.loads((root / "config" / "codigos_jogos.json").read_text(encoding="utf-8"))
    assert len(data["atualizado_em"]) == 10
    assert data["atualizado_em"][4] == "-" and data["atualizado_em"][7] == "-"
    if "semana_referente" in data:
        semana = data["semana_referente"]
        assert semana["inicio"] <= semana["fim"]
        assert semana["fuso"]


def test_weekly_catalog_period_is_monday_through_sunday():
    from datetime import date
    from scripts.atualizar_codigos_jogos import calcular_semana

    inicio, fim = calcular_semana(date(2026, 10, 15))
    assert inicio == date(2026, 10, 12)
    assert fim == date(2026, 10, 18)
    assert fim.weekday() == 6
    assert (fim - inicio).days == 6


def test_codes_are_available_in_the_welcome_card_without_slash_commands():
    import discord

    membro = SimpleNamespace(
        display_name="Candidato",
        display_avatar=SimpleNamespace(url="https://cdn.example.org/avatar.png"),
    )
    view = BoasVindasLayoutView(membro, 123)

    assert not hasattr(BoasVindasDM, "consultar_codigos")
    assert isinstance(view, discord.ui.LayoutView)
    assert len(view.children) == 1
    container = view.children[0]
    assert isinstance(container, discord.ui.Container)

    linhas = [item for item in container.children if isinstance(item, discord.ui.ActionRow)]
    assert len(linhas) == 3
    seletores = [linha.children[0] for linha in linhas if isinstance(linha.children[0], discord.ui.Select)]
    valores = {opcao.value for seletor in seletores for opcao in seletor.options}
    assert {"inicio", "shigaku", "gakuran", "fistborn"}.issubset(valores)
    assert all(linha in container.children for linha in linhas)
    assert any(
        isinstance(controle, discord.ui.Button)
        and controle.custom_id == "nemesis:alternar_notas_dm"
        for linha in linhas for controle in linha.children
    )


def test_entry_navigation_uses_select_inside_components_v2_card():
    import discord

    view = GuiaServidoresView()
    assert isinstance(view, discord.ui.LayoutView)
    assert len(view.children) == 1
    container = view.children[0]
    assert isinstance(container, discord.ui.Container)
    linhas = [item for item in container.children if isinstance(item, discord.ui.ActionRow)]
    assert len(linhas) == 1
    seletor = linhas[0].children[0]
    assert isinstance(seletor, discord.ui.Select)
    assert len(seletor.options) == len(CANAIS_GUIA_SERVIDORES) == 12
    assert seletor.placeholder == "◈ Escolha uma área para conhecer"
    assert linhas[0] in container.children
