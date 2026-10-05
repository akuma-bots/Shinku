from utils.storage import carregar, salvar


ARQUIVO_RECORDES = "recordes.json"
ARQUIVO_COMPETITIVO = "competitivo.json"


async def _tudo():
    return await carregar(
        ARQUIVO_RECORDES,
        {},
    )


async def obter_todos(
    guild_id: int,
) -> dict:
    dados = await _tudo()

    return dados.get(
        str(guild_id),
        {},
    )


async def verificar_e_atualizar(
    guild_id: int,
    categoria: str,
    user_id: int,
    valor: float,
):
    """
    Verifica e atualiza um recorde.

    O recorde continua sendo armazenado em
    recordes.json e também é refletido no
    competitivo.json para o Dashboard.
    """

    dados = await _tudo()

    recordes_guild = dados.setdefault(
        str(guild_id),
        {},
    )

    atual = recordes_guild.get(
        categoria
    )

    if (
        atual
        and valor <= atual["valor"]
    ):
        return None

    novo = {
        "user_id": user_id,
        "valor": valor,
    }

    recordes_guild[categoria] = novo

    await salvar(
        ARQUIVO_RECORDES,
        dados,
    )

    await _sincronizar_recorde_site(
        guild_id=guild_id,
        categoria=categoria,
        user_id=user_id,
        valor=valor,
    )

    return novo


async def _sincronizar_recorde_site(
    guild_id: int,
    categoria: str,
    user_id: int,
    valor: float,
):
    """
    Publica o recorde no competitivo.json compartilhado
    pelo Dashboard.

    O registro fica dentro do perfil do jogador,
    sem substituir os demais dados existentes.
    """

    dados = await carregar(
        ARQUIVO_COMPETITIVO,
        {
            "catalogo": [],
            "perfis": {},
        },
    )

    dados.setdefault(
        "catalogo",
        [],
    )

    dados.setdefault(
        "perfis",
        {},
    )

    chave = str(user_id)

    perfil = dados["perfis"].get(
        chave
    )

    if perfil is None:
        perfil = {
            "discordId": chave,
            "nome": "",
            "pontos": 0,
            "elo": 1000,
            "vitorias": 0,
            "derrotas": 0,
        }

    perfil["discordId"] = chave

    recordes = perfil.get(
        "recordes",
        {},
    )

    if not isinstance(
        recordes,
        dict,
    ):
        recordes = {}

    recordes[categoria] = {
        "valor": valor,
        "guildId": str(guild_id),
    }

    perfil["recordes"] = recordes

    dados["perfis"][chave] = perfil

    await salvar(
        ARQUIVO_COMPETITIVO,
        dados,
    )


async def sincronizar_todos_site(
    guild_id: int,
) -> int:
    """
    Sincroniza todos os recordes da guild
    com os perfis correspondentes do Dashboard.

    Retorna a quantidade de recordes sincronizados.
    """

    recordes = await obter_todos(
        guild_id
    )

    quantidade = 0

    for categoria, recorde in recordes.items():

        if not isinstance(
            recorde,
            dict,
        ):
            continue

        user_id = recorde.get(
            "user_id"
        )

        valor = recorde.get(
            "valor"
        )

        if user_id is None or valor is None:
            continue

        try:
            await _sincronizar_recorde_site(
                guild_id=guild_id,
                categoria=categoria,
                user_id=int(user_id),
                valor=float(valor),
            )

            quantidade += 1

        except Exception as erro:
            print(
                f"[RECORDES] "
                f"Falha ao sincronizar "
                f"{categoria}: {erro}"
            )

    return quantidade