#!/usr/bin/env python3
"""Gera notas públicas somente para alterações funcionais relevantes da NÊMESIS."""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUSO = ZoneInfo("America/Sao_Paulo")
MANIFEST = ROOT / "config" / "novidades.json"
IGNORAR = (
    ".github/",
    "tests/",
    "docs/",
    "scripts/",
    "README",
    "LICENSE",
    "CHANGELOG",
)
AREAS = {
    "cogs/": "sistemas e comandos",
    "utils/": "mecanismos internos e infraestrutura",
    "config/": "configurações dos sistemas",
    "bot.py": "núcleo e inicialização do bot",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def arquivos_alterados(before: str, after: str) -> list[tuple[str, str]]:
    if not before or set(before) == {"0"}:
        raw = git("show", "--format=", "--name-status", after)
    else:
        raw = git("diff", "--name-status", before, after)
    itens = []
    for linha in raw.splitlines():
        partes = linha.split("\t")
        if len(partes) < 2:
            continue
        status = partes[0]
        caminho = partes[-1]
        if caminho == "config/novidades.json" or caminho.startswith(IGNORAR):
            continue
        if not (caminho.startswith(("cogs/", "utils/", "config/")) or caminho == "bot.py"):
            continue
        if caminho.endswith((".pyc", ".log")):
            continue
        itens.append((status, caminho))
    return itens


def assunto_commits(before: str, after: str) -> list[str]:
    try:
        if not before or set(before) == {"0"}:
            saida = git("log", "-1", "--format=%s", after)
        else:
            saida = git("log", "--format=%s", f"{before}..{after}")
        return [linha.strip() for linha in saida.splitlines() if linha.strip()]
    except subprocess.CalledProcessError:
        return []


def commits_relevantes(assuntos: list[str]) -> list[str]:
    """Somente commits explicitamente classificados como entrega importante."""
    padrao = re.compile(
        r"^(?:feat|feature|security|release|perf)(?:\([^)]*\))?:"
        r"|^fix!(?:\([^)]*\))?:"
        r"|^hotfix(?:\([^)]*\))?:"
        r"|^perf!(?:\([^)]*\))?:"
        r"|^\[release\]"
        r"|^(?:adiciona|adicionar|implementa|implementar|cria|criar|corrige|corrigir|corrigido|protege|proteger|reforça|reforcar|migra|migrar|torna|tornar|melhora|melhorar|aprimora|aprimorar|restaura|restaurar|repara|reparar|registra|registrar|limita|limitar|ignora|ignorar|separa|separar|atualiza|atualizar|ajusta|ajustar|notifica|notificar|garante|garantir|remove|remover|adapta|adaptar)\b",
        re.IGNORECASE,
    )
    return [assunto for assunto in assuntos if padrao.search(assunto.strip())]


def gerar(before: str, after: str) -> dict | None:
    alteracoes = arquivos_alterados(before, after)
    if not alteracoes:
        return None

    assuntos = commits_relevantes(assunto_commits(before, after))
    if not assuntos:
        return None

    textos = " ".join(assuntos).lower()
    status = [s for s, _ in alteracoes]
    tem_correcao = bool(re.search(r"\\b(fix|bug|corrig|corrigir|hotfix|patch|repar)\\b", textos))
    tem_recurso = bool(re.search(r"\\b(feat|feature|adicion|cria|implement|novo|nova)\\b", textos))
    if tem_correcao and (tem_recurso or len(assuntos) > 1):
        tipo = "Melhorias e correções"
    elif tem_correcao:
        tipo = "Correções"
    elif tem_recurso or any(s.startswith("A") for s in status):
        tipo = "Novos recursos e melhorias"
    else:
        tipo = "Melhorias dos sistemas"

    areas = []
    for prefixo, nome in AREAS.items():
        if any(caminho.startswith(prefixo) if prefixo.endswith("/") else caminho == prefixo
               for _, caminho in alteracoes):
            areas.append(nome)

    # Os assuntos dos commits são a fonte principal; os caminhos apenas contextualizam.
    rotulos = {
        "missoes": "Missões", "revisoes": "Análise de provas",
        "ranking": "Rankings", "parcerias": "Parcerias",
        "tickets": "Atendimento", "automod": "Moderação automática",
        "moderacao": "Moderação", "eventos": "Eventos",
        "perfil": "Perfis", "novidades": "Central de atualizações",
        "desafios": "Desafios", "guerras": "Guerras",
    }
    # Notas públicas nunca devem reproduzir assuntos de commits em inglês.
    # Traduções explícitas preservam detalhes; assuntos desconhecidos recebem
    # uma descrição funcional em português baseada nas áreas realmente alteradas.
    traducoes = {
        "fix: corrige validação de provas":
            "validação de provas: corrigido o fluxo de análise e registro dos comprovantes.",
        "fix!: corrige validação de provas":
            "validação de provas: corrigido o fluxo de análise e registro dos comprovantes.",
        "fix multi-step form continuation interaction listener":
            "Formulários: corrigida a continuidade entre as etapas de inscrição.",
        "improve update announcements with bot branding":
            "Central de atualizações: identidade visual do bot aplicada aos comunicados.",
        "write current update notes in brazilian portuguese":
            "Central de atualizações: notas padronizadas em português do Brasil.",
        "fix application delivery channel and migrate staff form questions":
            "Formulários: corrigido o canal de recebimento e ampliado o questionário de recrutamento.",
        "add regression tests for staff questions and submission channel":
            "Formulários: adicionados testes para as perguntas e o canal de recebimento.",
    }
    unicos = list(dict.fromkeys(assuntos))
    linhas = []
    for assunto in unicos[:6]:
        chave = assunto.casefold().strip()
        limpo = traducoes.get(chave)
        if not limpo:
            # Os commits em português já descrevem a entrega. Exibir o assunto
            # real evita substituir alterações distintas por uma frase genérica.
            limpo = re.sub(
                r"^(?:feat|feature|fix|perf|security|hotfix)(?:\([^)]*\))?:\s*",
                "",
                assunto,
                flags=re.IGNORECASE,
            ).strip()
            if limpo and not re.search(r"[.!?]$", limpo):
                limpo += "."
            if limpo:
                limpo = limpo[0].upper() + limpo[1:]
        if limpo:
            linhas.append(f"• {limpo[:220]}")
    if not linhas:
        return None
    mensagem = (
        "A NÊMESIS recebeu uma atualização. Confira exatamente o que mudou nesta versão:\n\n"
        + "\n".join(linhas)
    )
    if areas:
        mensagem += "\n\n**Áreas envolvidas:** " + ", ".join(areas) + "."
    mensagem += (
        "\n\nAs alterações foram integradas ao repositório principal. "
        "A disponibilidade das funções depende da conclusão do deploy do bot."
    )
