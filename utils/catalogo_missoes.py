import json
from pathlib import Path

from utils import missoes as armazenamento
from utils.storage import carregar, salvar


ARQUIVO_MENSAGENS_DISCORD = "missoes_discord.json"


CAMINHO_CATALOGO = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "missoes_padrao.json"
)


def carregar_catalogo() -> list:
    """Lê o catálogo versionado no GitHub, fonte das missões padrão."""
    try:
        dados = json.loads(CAMINHO_CATALOGO.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise RuntimeError(
            f"Não foi possível carregar {CAMINHO_CATALOGO}: {erro}"
        ) from erro

    lista = dados.get("missoes") if isinstance(dados, dict) else None
    if not isinstance(lista, list):
        raise RuntimeError("O catálogo padrão de missões não contém uma lista válida.")

    resultado = []
    ids = set()
    for item in lista:
        if not isinstance(item, dict):
            continue
        missao_id = str(item.get("id") or "").strip()
        if not missao_id or missao_id in ids:
            raise RuntimeError(f"ID ausente ou duplicado no catálogo: {missao_id!r}")
        ids.add(missao_id)
        if item.get("tipo") not in armazenamento.TIPOS_VALIDOS:
            raise RuntimeError(
                f"Tipo inválido na missão padrão {missao_id}: {item.get('tipo')!r}"
            )
        resultado.append(item)

    return resultado


async def sincronizar_catalogo(guild_id: int, catalogo: list = None) -> list:
    """Mescla as missões do GitHub sem apagar histórico nem provas já aplicadas."""
    catalogo = catalogo if catalogo is not None else carregar_catalogo()
    guild_data = await armazenamento._guild(guild_id)
    existentes = {
        str(item.get("id")): item
        for item in guild_data.get("missoes", [])
        if isinstance(item, dict)
    }

    ids_padrao = {str(item["id"]) for item in catalogo}
    atualizadas = []

    for definicao in catalogo:
        missao_id = str(definicao["id"])
        antiga = existentes.get(missao_id, {})
        atual = armazenamento._normalizar_missao({
            **antiga,
            **definicao,
            "id": missao_id,
            "origem": "github",
            "recompensas_aplicadas": antiga.get("recompensas_aplicadas", []),
            "discord_message_id": antiga.get("discord_message_id"),
            "discord_channel_id": antiga.get("discord_channel_id"),
        })
        atual["canal_config"] = definicao.get("canal_config", "")
        atualizadas.append(atual)

    personalizadas = [
        item for item in guild_data.get("missoes", [])
        if str(item.get("id")) not in ids_padrao
    ]
    guild_data["missoes"] = personalizadas + atualizadas
    await armazenamento._salvar_guild(guild_id, guild_data)
    return atualizadas


async def obter_mensagem_discord(guild_id: int, missao_id: str) -> dict:
    """Busca os IDs em storage separado para que o painel do site não os apague."""
    dados = await carregar(ARQUIVO_MENSAGENS_DISCORD, {})
    guild = dados.get(str(guild_id), {})
    registro = guild.get(str(missao_id), {})
    return registro if isinstance(registro, dict) else {}


async def salvar_mensagem_discord(
    guild_id: int,
    missao_id: str,
    canal_id: int,
    mensagem_ids,
) -> None:
    """Persiste todas as mensagens de uma missão, mantendo compatibilidade com IDs antigos."""
    if isinstance(mensagem_ids, (str, int)):
        ids = [int(mensagem_ids)]
    else:
        ids = [int(valor) for valor in (mensagem_ids or [])]

    if not ids:
        raise ValueError("É necessário salvar pelo menos um ID de mensagem.")

    dados = await carregar(ARQUIVO_MENSAGENS_DISCORD, {})
    if not isinstance(dados, dict):
        dados = {}
    guild = dados.setdefault(str(guild_id), {})
    guild[str(missao_id)] = {
        "discord_channel_id": int(canal_id),
        "discord_message_id": ids[0],
        "discord_message_ids": ids,
    }
    await salvar(ARQUIVO_MENSAGENS_DISCORD, dados)
