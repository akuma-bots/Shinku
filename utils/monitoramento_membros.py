"""Armazenamento privado e limitado de atividade individual da NÊMESIS.

Registra mensagens e eventos a partir da ativação do monitoramento. Os dados
são mantidos por 30 dias e limitados por membro para controlar retenção/custo.
"""
from __future__ import annotations

import time
import logging
from utils.storage import atualizar_json, carregar, definir_expiracao, salvar_com_expiracao

RETENCAO_SEGUNDOS = 30 * 24 * 60 * 60
LIMITE_MENSAGENS = 500
LIMITE_EVENTOS = 300
LIMITE_REVISOES = 2
log = logging.getLogger(__name__)


def _arquivo(guild_id: int, user_id: int) -> str:
    return f"atividade_membro_{int(guild_id)}_{int(user_id)}.json"


def _numero(valor) -> float:
    try:
        return float(valor or 0)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def _limpar(dados: dict, agora: float) -> dict:
    limite = agora - RETENCAO_SEGUNDOS
    bruto_mensagens = dados.get("mensagens", [])
    bruto_eventos = dados.get("eventos", [])
    bruto_mensagens = bruto_mensagens if isinstance(bruto_mensagens, list) else []
    bruto_eventos = bruto_eventos if isinstance(bruto_eventos, list) else []
    mensagens = [x for x in bruto_mensagens if isinstance(x, dict) and _numero(x.get("timestamp")) >= limite]
    eventos = [x for x in bruto_eventos if isinstance(x, dict) and _numero(x.get("timestamp")) >= limite]
    dados["mensagens"] = mensagens[-LIMITE_MENSAGENS:]
    dados["eventos"] = eventos[-LIMITE_EVENTOS:]
    dados["atualizado_em"] = agora
    return dados


def _arquivo_indice(guild_id: int, message_id: int | str) -> str:
    return f"atividade_mensagem_{int(guild_id)}_{int(message_id)}.json"


async def buscar_mensagem(guild_id: int, message_id: int | str) -> dict | None:
    arquivo = _arquivo_indice(guild_id, message_id)
    try:
        registro = await carregar(arquivo, {})
        await definir_expiracao(arquivo, RETENCAO_SEGUNDOS)
        return registro if isinstance(registro, dict) and registro.get("user_id") else None
    except Exception:
        log.exception("Falha ao consultar índice de mensagem (guild=%s, message=%s).", guild_id, message_id)
        return None


async def registrar_mensagem(guild_id: int, user_id: int, registro: dict) -> None:
    agora = time.time()
    message_id = str(registro.get("message_id") or "")
    if not message_id:
        return

    def transformar(atual):
        dados = atual if isinstance(atual, dict) else {"mensagens": [], "eventos": []}
        _limpar(dados, agora)
        mensagens = dados["mensagens"]
        existente = next((x for x in mensagens if str(x.get("message_id")) == message_id), None)
        if existente is None:
            mensagens.append({**registro, "message_id": message_id, "revisoes": []})
        else:
            # Eventos duplicados/reentregues não apagam conteúdo já armazenado.
            if registro.get("status") == "excluida":
                existente["status"] = "excluida"
                existente["excluida_em"] = registro.get("excluida_em", agora)
            elif registro.get("status") == "editada" and existente.get("status") != "excluida":
                anterior = existente.get("conteudo", "")
                novo = registro.get("conteudo", "")
                if anterior != novo:
                    revisoes = existente.setdefault("revisoes", [])
                    revisoes.append({"conteudo": anterior, "timestamp": agora})
                    existente["revisoes"] = revisoes[-LIMITE_REVISOES:]
                existente["conteudo"] = novo
                existente["status"] = "editada"
                existente["editada_em"] = agora
                if "anexos" in registro:
                    existente["anexos"] = registro["anexos"]
        mensagens.sort(key=lambda x: float(x.get("timestamp", 0) or 0))
        dados["mensagens"] = mensagens[-LIMITE_MENSAGENS:]
        return _limpar(dados, agora)

    arquivo = _arquivo(guild_id, user_id)
    try:
        dados_atualizados = await atualizar_json(
            arquivo, {"mensagens": [], "eventos": []}, transformar
        )
        await definir_expiracao(arquivo, RETENCAO_SEGUNDOS)

        # O índice mantém o status efetivamente salvo no dossiê. Assim, os
        # listeners cacheado e raw reconhecem uma exclusão já processada.
        mensagens = dados_atualizados.get("mensagens", []) if isinstance(dados_atualizados, dict) else []
        mensagem_atualizada = next(
            (item for item in mensagens if str(item.get("message_id")) == message_id),
            None,
        )
        status_final = (mensagem_atualizada or {}).get("status") or registro.get("status", "enviada")

        indice_arquivo = _arquivo_indice(guild_id, message_id)
        entrada = {
            "user_id": int(user_id),
            "channel_id": int(registro.get("canal_id") or 0),
            "timestamp": _numero(registro.get("timestamp")) or agora,
            "status": str(status_final),
        }
        await salvar_com_expiracao(indice_arquivo, entrada, RETENCAO_SEGUNDOS)
    except Exception:
        log.exception("Falha ao persistir mensagem do membro (guild=%s, user=%s, message=%s).", guild_id, user_id, message_id)


async def registrar_evento(guild_id: int, user_id: int, tipo: str, descricao: str, *, timestamp: float | None = None, detalhes: dict | None = None) -> None:
    agora = float(timestamp or time.time())
    evento = {"tipo": str(tipo)[:60], "descricao": str(descricao)[:1200], "timestamp": agora, "detalhes": detalhes or {}}

    def transformar(atual):
        dados = atual if isinstance(atual, dict) else {"mensagens": [], "eventos": []}
        _limpar(dados, agora)
        eventos = dados["eventos"]
        # Deduplicação simples para eventos repetidos do mesmo instante.
        chave = (evento["tipo"], evento["timestamp"], evento["descricao"])
        if not any((x.get("tipo"), x.get("timestamp"), x.get("descricao")) == chave for x in eventos):
            eventos.append(evento)
        dados["eventos"] = eventos[-LIMITE_EVENTOS:]
        return _limpar(dados, agora)

    arquivo = _arquivo(guild_id, user_id)
    try:
        await atualizar_json(arquivo, {"mensagens": [], "eventos": []}, transformar)
        await definir_expiracao(arquivo, RETENCAO_SEGUNDOS)
    except Exception:
        log.exception("Falha ao persistir evento de atividade (guild=%s, user=%s, tipo=%s).", guild_id, user_id, tipo)


async def consultar(guild_id: int, user_id: int) -> dict:
    arquivo = _arquivo(guild_id, user_id)
    agora = time.time()
    dados = await atualizar_json(arquivo, {"mensagens": [], "eventos": []}, lambda atual: _limpar(atual if isinstance(atual, dict) else {"mensagens": [], "eventos": []}, agora))
    await definir_expiracao(arquivo, RETENCAO_SEGUNDOS)
    return dados if isinstance(dados, dict) else {"mensagens": [], "eventos": []}
