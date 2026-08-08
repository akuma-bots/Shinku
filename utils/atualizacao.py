import datetime
from utils.storage import carregar, salvar
from utils.pesquisa import pesquisar_web, ErroPesquisa

ARQUIVO = "atualizacao_diaria.json"  # { guild_id: {data, tema, resumo} }
FUSO_BRASIL = datetime.timezone(datetime.timedelta(hours=-3))
TEMA_PADRAO = "Gakuran Roblox novidades atualização"


def _hoje() -> str:
    return datetime.datetime.now(FUSO_BRASIL).strftime("%Y-%m-%d")


async def get_atualizacao_de_hoje(guild_id: int) -> dict:
    todos = await carregar(ARQUIVO, {})
    registro = todos.get(str(guild_id))
    if registro and registro["data"] == _hoje():
        return registro
    return None


async def atualizar_agora(guild_id: int, tema: str = None) -> dict:
    """Pesquisa na web sobre o tema e guarda o resumo do dia. Chamado uma vez
    por dia sozinho (tarefa em segundo plano) ou manualmente via comando."""
    tema_usado = tema or TEMA_PADRAO
    try:
        resumo = await pesquisar_web(tema_usado)
    except ErroPesquisa as e:
        resumo = f"(pesquisa falhou hoje: {e})"

    registro = {"data": _hoje(), "tema": tema_usado, "resumo": resumo}
    todos = await carregar(ARQUIVO, {})
    todos[str(guild_id)] = registro
    await salvar(ARQUIVO, todos)
    return registro
