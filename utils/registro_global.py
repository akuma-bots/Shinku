"""Centraliza os registros operacionais da NÊMESIS em tópicos permanentes de Fórum."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord

from utils.apresentacao import criar_embed
from utils.storage import atualizar_json

_LOG = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
CANAL_REGISTRO_GLOBAL_ID = 1566579335966498926
ARQUIVO = "registro_global_topicos.json"
ARQUIVO_MIGRACAO_DESTRUTIVA = "registro_global_migracao_20261103.json"
VERSAO_MIGRACAO_DESTRUTIVA = 1

# OCTÓGONO (oito posições + cargo coletivo) e todos os cargos funcionais de staff.
CARGOS_ACESSO_IDS = {
    1563995880015536193, 1563995880015536192, 1563995880015536191,
    1563995880015536190, 1563995880015536189, 1563995880007139428,
    1563995880007139427, 1563995880007139426, 1563995880007139425,
    1563995880007139424, 1563995880007139423, 1563995880007139422,
    1563995880007139421, 1563995880007139420, 1563995880007139419,
    1563995879998754946, 1563995879998754945,
}

# Estrutura enxuta: cada assunto tem um único destino canônico.
# Os nomes antigos continuam aceitos pelos cogs durante a migração.
CATEGORIAS = {
    "administracao": ("👑・Central de Administração", "Decisões administrativas, permissões, configurações e diretrizes oficiais da NÊMESIS."),
    "historico_membros": ("👥・Arquivo de Membros", "Linha do tempo individual: entradas, saídas, cargos, convites, XP, voz, conquistas e ocorrências relacionadas."),
    "moderacao": ("⚖️・Tribunal de Moderação", "Advertências, timeouts, expulsões, banimentos e decisões da equipe."),
    "seguranca": ("🛡️・Muralha de Segurança", "AutoMod, Anti-Raid, filtros, incidentes, bloqueios e falhas de proteção."),
    "missoes": ("🎯・Operações e Missões", "Missões, operações, formulários, relatórios, atribuições, provas, validações, conclusões e recompensas."),
    "competitivo": ("🏆・Arena Competitiva", "Desafios, PvP, guerras, placares, participantes e resultados."),
    "eventos": ("🎉・Eventos e Celebrações", "Agenda, inscrições, atividades coletivas, sorteios, vencedores e entrega de prêmios."),
    "atendimento": ("🎫・Central de Atendimento", "Tickets, responsáveis, encerramentos, avaliações e transcrições."),
    "mensagens": ("💬・Comunicação Geral", "Edições, exclusões e anexos de mensagens, com autor, canal e contexto disponíveis."),
    "parcerias": ("🤝・Alianças e Parcerias", "Solicitações, aprovações, representantes e alterações de parcerias."),
    "integracoes": ("⚙️・Sistemas e Integrações", "Roblox, APIs externas, Upstash, conexões, health checks, tarefas e disponibilidade do Shinku."),
    "sugestoes": ("📋・Sugestões e Ideias", "Sugestões recebidas, votos, decisões e resultados."),
}

# Paleta NÊMESIS: carmesim escuro, vermelho profundo e preto.
# Tons próximos diferenciam as áreas sem descaracterizar a identidade visual.
CORES_CATEGORIAS = {
    "administracao": 0xB3263E,
    "historico_membros": 0x991B33,
    "moderacao": 0x741629,
    "seguranca": 0x681323,
    "missoes": 0x8F172C,
    "competitivo": 0xA01D35,
    "eventos": 0xAD233A,
    "atendimento": 0xA62139,
    "mensagens": 0x8B1E2D,
    "parcerias": 0x7A1425,
    "integracoes": 0x381018,
    "sugestoes": 0x5C101F,
}

EMOJIS_CATEGORIAS = {
    "administracao": "👑", "historico_membros": "👥", "moderacao": "⚖️",
    "seguranca": "🛡️", "missoes": "🎯", "competitivo": "🏆",
    "eventos": "🎉", "atendimento": "🎫", "mensagens": "💬",
    "parcerias": "🤝", "integracoes": "⚙️", "sugestoes": "📋",
}

ALIASES_CATEGORIAS = {
    "anexos": "mensagens",
    "operacoes": "missoes",
    "infraestrutura": "integracoes",
    "sorteios": "eventos",
    "automod": "seguranca",
    "cargos": "historico_membros",
    "competicoes": "competitivo",
    "configuracoes": "administracao",
    "conquistas": "historico_membros",
    "convites": "historico_membros",
    "entradas": "historico_membros",
    "formularios": "operacoes",
    "membros": "historico_membros",
    "progressao": "historico_membros",
    "relatorios": "operacoes",
    "roblox": "integracoes",
    "sistemas": "operacoes",
    "atividade": "historico_membros",
    "voz": "historico_membros",
}


def normalizar_categoria(categoria: str) -> str:
    """Converte nomes legados para a categoria canônica sem perder registros."""
    chave = str(categoria or "").strip().lower()
    return ALIASES_CATEGORIAS.get(chave, chave)

_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}
_CABECALHOS_VERIFICADOS: set[tuple[int, int]] = set()
_MIGRACAO_DESTRUTIVA_LOCK = asyncio.Lock()


def _lock(guild_id: int, categoria: str) -> asyncio.Lock:
    return _LOCKS.setdefault((guild_id, categoria), asyncio.Lock())


async def _salvar_id(guild_id: int, categoria: str, thread_id: int) -> None:
    chave = str(guild_id)
    def atualizar(dados):
        if not isinstance(dados, dict):
            dados = {}
        servidor = dados.get(chave)
        if not isinstance(servidor, dict):
            servidor = {}
        servidor[categoria] = int(thread_id)
        dados[chave] = servidor
        return dados
    await atualizar_json(ARQUIVO, {}, atualizar)


async def _ler_ids(guild_id: int) -> dict:
    # A leitura é feita pelo mesmo storage usado pelo restante do bot.
    from utils.storage import carregar
    dados = await carregar(ARQUIVO, {})
    servidor = dados.get(str(guild_id), {}) if isinstance(dados, dict) else {}
    return servidor if isinstance(servidor, dict) else {}


def _embed_cabecalho_topico(nome: str, descricao: str) -> discord.Embed:
    categoria = next((chave for chave, (rotulo, _desc) in CATEGORIAS.items() if rotulo == nome), None)
    emoji = EMOJIS_CATEGORIAS.get(categoria, "📌")
    embed = discord.Embed(
        title=f"{emoji}  {nome}",
        description=(
            "**REGISTRO OFICIAL DA NÊMESIS**\n"
            "Área de consulta dos registros operacionais da NÊMESIS. "
            "As ocorrências são organizadas por assunto neste mesmo tópico."
        ),
        color=next((cor for chave, cor in CORES_CATEGORIAS.items() if CATEGORIAS[chave][0] == nome), 0x8B1E2D),
    )
    embed.add_field(name="O que é registrado", value=descricao[:1024], inline=False)
    embed.add_field(
        name="Padrão de registro",
        value=(
            "Quando disponível, cada registro identifica responsável, membro relacionado, "
            "ação, canal/protocolo, data e resultado. Dados não observáveis pelo Discord "
            "não são presumidos."
        ),
        inline=False,
    )
    embed.add_field(
        name="Como funciona",
        value=(
            "Os eventos desta categoria são adicionados em sequência aqui. "
            "Não é criado um tópico por ocorrência e os registros não devem ser misturados "
            "com assuntos de outras categorias."
        ),
        inline=False,
    )
    embed.add_field(
        name="Acesso e integridade",
        value=(
            "Fórum restrito aos cargos autorizados da NÊMESIS. "
            "O cabeçalho é mantido pelo Shinku; as ocorrências são acrescentadas abaixo."
        ),
        inline=False,
    )
    embed.set_footer(text="NÊMESIS • Registro Global")
    return embed


async def _atualizar_cabecalho_topico(
    thread: discord.Thread,
    nome: str,
    descricao: str,
) -> None:
    chave = (thread.guild.id, thread.id)
    if chave in _CABECALHOS_VERIFICADOS or thread.archived or thread.locked:
        return
    embed = _embed_cabecalho_topico(nome, descricao)
    try:
        mensagem = await thread.fetch_message(thread.id)
        atual = mensagem.embeds[0].to_dict() if mensagem.embeds else None
        if atual != embed.to_dict():
            await mensagem.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            _LOG.info("Cabeçalho do tópico atualizado: %s (%s)", nome, thread.id)
            await asyncio.sleep(0.2)
        _CABECALHOS_VERIFICADOS.add(chave)
    except discord.NotFound:
        _LOG.warning("Tópico sem mensagem inicial recuperável: %s (%s).", nome, thread.id)
    except (discord.Forbidden, discord.HTTPException):
        _LOG.exception("Não foi possível atualizar o cabeçalho do tópico %s (%s).", nome, thread.id)


async def _obter_topico(
    forum: discord.ForumChannel,
    categoria: str,
    topicos_existentes: list[discord.Thread] | None = None,
) -> discord.Thread:
    categoria = normalizar_categoria(categoria)
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoria de registro desconhecida: {categoria}")
    nome, descricao = CATEGORIAS[categoria]
    async with _lock(forum.guild.id, categoria):
        ids = await _ler_ids(forum.guild.id)
        existentes = topicos_existentes
        if existentes is None:
            existentes = list(forum.threads)
            async for thread in forum.archived_threads(limit=None):
                if all(item.id != thread.id for item in existentes):
                    existentes.append(thread)

        # Um tópico canônico existente sempre prevalece.
        for thread in existentes:
            if thread.name == nome:
                if ids.get(categoria) != thread.id:
                    await _salvar_id(forum.guild.id, categoria, thread.id)
                await _atualizar_cabecalho_topico(thread, nome, descricao)
                return thread

        # Reaproveita e renomeia um tópico antigo da mesma área. Assim, a
        # reorganização preserva as mensagens e links existentes em vez de
        # criar uma cópia vazia ou apagar o histórico.
        chaves_legadas = [
            chave for chave, destino in ALIASES_CATEGORIAS.items()
            if destino == categoria
        ]
        candidatos = [categoria, *chaves_legadas]
        thread_salva = None
        for chave in candidatos:
            thread_id = ids.get(chave)
            if not thread_id:
                continue
            try:
                candidata = forum.guild.get_thread(int(thread_id))
                if candidata is None:
                    candidata = await forum.guild.fetch_channel(int(thread_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                continue
            if isinstance(candidata, discord.Thread) and candidata.parent_id == forum.id:
                thread_salva = candidata
                break

        if thread_salva is not None:
            try:
                await thread_salva.edit(
                    name=nome,
                    archived=False,
                    locked=False,
                    reason="Reorganização dos registros da NÊMESIS; preservação do histórico existente",
                )
                await _salvar_id(forum.guild.id, categoria, thread_salva.id)
                await _atualizar_cabecalho_topico(thread_salva, nome, descricao)
                _LOG.info(
                    "Tópico reaproveitado e renomeado sem apagar mensagens: %s (%s).",
                    nome, thread_salva.id,
                )
                return thread_salva
            except (discord.Forbidden, discord.HTTPException):
                _LOG.exception("Não foi possível reaproveitar o tópico legado %s (%s).", thread_salva.name, thread_salva.id)
                raise

        inicial = _embed_cabecalho_topico(nome, descricao)
        criado = await forum.create_thread(
            name=nome,
            embed=inicial,
            auto_archive_duration=10080,
            reason="Provisionamento de categoria canônica do Registro Global NÊMESIS",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        thread = criado.thread
        _CABECALHOS_VERIFICADOS.add((forum.guild.id, thread.id))
        if topicos_existentes is not None:
            topicos_existentes.append(thread)
        await _salvar_id(forum.guild.id, categoria, thread.id)
        _LOG.info("Tópico permanente criado: %s (%s)", nome, thread.id)
        await asyncio.sleep(1.1)
        return thread


async def obter_topico(guild: discord.Guild, categoria: str) -> discord.Thread:
    if guild.id != GUILD_NEMESIS_ID:
        raise ValueError("O Registro Global só está configurado para a NÊMESIS.")
    canal = guild.get_channel(CANAL_REGISTRO_GLOBAL_ID)
    if canal is None:
        canal = await guild.fetch_channel(CANAL_REGISTRO_GLOBAL_ID)
    if not isinstance(canal, discord.ForumChannel):
        raise TypeError("O destino do Registro Global não é um Fórum.")
    validar_privacidade(canal)
    return await _obter_topico(canal, categoria)


def validar_privacidade(forum: discord.ForumChannel) -> None:
    """Falha fechado: nenhum registro é publicado se o Fórum não estiver privado."""
    guild = forum.guild
    everyone = forum.overwrites_for(guild.default_role)
    if everyone.view_channel is not False:
        raise PermissionError("O Fórum precisa negar view_channel ao @everyone.")
    for alvo, overwrite in forum.overwrites.items():
        if isinstance(alvo, discord.Role) and alvo.id not in CARGOS_ACESSO_IDS and alvo != guild.default_role:
            if overwrite.view_channel is True:
                raise PermissionError(f"Cargo não autorizado ainda possui acesso: {alvo.name}")
        elif isinstance(alvo, discord.Member) and alvo != guild.me:
            if overwrite.view_channel is True:
                raise PermissionError(f"Membro não autorizado ainda possui acesso individual: {alvo.id}")
    # Também verifica permissões herdadas da categoria, mesmo quando o cargo
    # não possui overwrite próprio no Fórum.
    cargos_servidor = getattr(guild, "roles", [])
    if isinstance(cargos_servidor, (list, tuple, set)):
        for role in cargos_servidor:
            if (
                isinstance(role, discord.Role)
                and role != guild.default_role
                and role.id not in CARGOS_ACESSO_IDS
                and forum.permissions_for(role).view_channel
            ):
                raise PermissionError(f"Cargo não autorizado herda acesso ao Fórum: {role.name}")
    ausentes = []
    for role_id in CARGOS_ACESSO_IDS:
        role = guild.get_role(role_id)
        if role is None:
            ausentes.append(str(role_id))
            continue
        if not forum.permissions_for(role).view_channel:
            ausentes.append(role.name)
    if ausentes:
        raise PermissionError(
            "O Fórum não concede leitura a todos os cargos autorizados: " + ", ".join(ausentes)
        )
    bot_member = guild.me
    if bot_member is None:
        raise PermissionError("Não foi possível validar as permissões do bot no Fórum.")
    permissoes = forum.permissions_for(bot_member)
    necessarias = ("view_channel", "read_message_history", "send_messages", "send_messages_in_threads", "manage_threads", "create_public_threads")
    faltantes = [nome for nome in necessarias if not getattr(permissoes, nome, False)]
    if faltantes:
        raise PermissionError("Permissões do bot ausentes no Fórum: " + ", ".join(faltantes))


async def configurar_permissoes(forum: discord.ForumChannel) -> None:
    """Restringe o Fórum ao OCTÓGONO, staff funcional e ao próprio bot."""
    guild = forum.guild
    if guild.id != GUILD_NEMESIS_ID:
        return
    bot_member = guild.me
    overwrites = dict(forum.overwrites)

    # Nenhuma permissão individual antiga pode manter acesso a um não autorizado.
    for alvo, overwrite in list(overwrites.items()):
        if alvo == guild.default_role:
            overwrite.view_channel = False
        elif alvo == bot_member:
            continue
        elif isinstance(alvo, discord.Role):
            overwrite.view_channel = alvo.id in CARGOS_ACESSO_IDS
        else:
            overwrite.view_channel = False
        overwrites[alvo] = overwrite

    overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
    for role in getattr(guild, "roles", []):
        if (
            isinstance(role, discord.Role)
            and role != guild.default_role
            and role.id not in CARGOS_ACESSO_IDS
        ):
            overwrites[role] = discord.PermissionOverwrite(view_channel=False)

    for role_id in CARGOS_ACESSO_IDS:
        role = guild.get_role(role_id)
        if role is None:
            _LOG.warning("Cargo autorizado não encontrado no servidor: %s", role_id)
            continue
        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages_in_threads=True,
        )
    if bot_member is not None:
        overwrites[bot_member] = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=True,
            send_messages_in_threads=True,
            embed_links=True,
            attach_files=True,
            create_public_threads=True,
            manage_threads=True,
            manage_messages=True,
        )
    try:
        await forum.edit(
            overwrites=overwrites,
            reason="Restringir o Registro Global ao OCTÓGONO e à equipe Staff autorizada",
        )
    except discord.Forbidden:
        validar_privacidade(forum)



async def _executar_migracao_descritiva(forum: discord.ForumChannel) -> int | None:
    """Apaga uma única vez todos os tópicos antigos deste Fórum, inclusive mensagens.

    O marcador persistente só é concluído depois que a exclusão terminou. Se a
    criação dos novos tópicos falhar depois disso, a próxima inicialização
    apenas completa os que faltarem, sem apagar novamente os tópicos novos.
    Retorna a quantidade apagada, ou None quando a migração já foi concluída.
    """
    async with _MIGRACAO_DESTRUTIVA_LOCK:
        from utils.storage import carregar, salvar

        estado = await carregar(ARQUIVO_MIGRACAO_DESTRUTIVA, {})
        if (
            isinstance(estado, dict)
            and estado.get("versao") == VERSAO_MIGRACAO_DESTRUTIVA
            and estado.get("concluida") is True
            and int(estado.get("forum_id", 0)) == forum.id
        ):
            return None

        topicos: dict[int, discord.Thread] = {
            thread.id: thread
            for thread in forum.threads
            if getattr(thread, "parent_id", None) == forum.id
        }
        async for thread in forum.archived_threads(limit=None):
            if getattr(thread, "parent_id", None) == forum.id:
                topicos[thread.id] = thread

        apagados = 0
        for thread in topicos.values():
            try:
                await thread.delete(
                    reason="Migração única e autorizada do Registro Global NÊMESIS para a nova estrutura oficial",
                )
                apagados += 1
                await asyncio.sleep(0.25)
            except discord.NotFound:
                continue
            except (discord.Forbidden, discord.HTTPException):
                _LOG.exception(
                    "Migração do Registro Global interrompida; não foi possível excluir o tópico %s (%s).",
                    thread.name, thread.id,
                )
                raise

        await salvar(
            ARQUIVO_MIGRACAO_DESTRUTIVA,
            {
                "versao": VERSAO_MIGRACAO_DESTRUTIVA,
                "concluida": True,
                "forum_id": forum.id,
                "topicos_excluidos": apagados,
                "estrutura": "registro-global-nemesis-12-areas",
            },
        )
        _LOG.warning(
            "Migração destrutiva do Registro Global concluída: %s tópicos e suas mensagens excluídos permanentemente.",
            apagados,
        )
        return apagados


async def garantir_topicos(guild: discord.Guild) -> dict[str, int]:
    """Executa a migração destrutiva única e provisiona as 12 áreas oficiais."""
    if guild.id != GUILD_NEMESIS_ID:
        return {}
    canal = guild.get_channel(CANAL_REGISTRO_GLOBAL_ID)
    if canal is None:
        canal = await guild.fetch_channel(CANAL_REGISTRO_GLOBAL_ID)
    if not isinstance(canal, discord.ForumChannel) or canal.guild.id != guild.id:
        raise TypeError("O destino configurado não é o Fórum de Registro Global da NÊMESIS.")
    await configurar_permissoes(canal)
    validar_privacidade(canal)

    migracao_executada = await _executar_migracao_descritiva(canal)
    topicos_existentes: list[discord.Thread] = [] if migracao_executada is not None else list(canal.threads)
    try:
        async for thread in canal.archived_threads(limit=None):
            if all(item.id != thread.id for item in topicos_existentes):
                topicos_existentes.append(thread)
    except (discord.Forbidden, discord.HTTPException):
        _LOG.exception("Não foi possível listar todos os tópicos arquivados do Registro Global.")

    resultado = {}
    for categoria in CATEGORIAS:
        thread = await _obter_topico(canal, categoria, topicos_existentes)
        resultado[categoria] = thread.id

    canonicos = set(resultado.values())
    aposentados = 0
    excluidos_vazios = 0
    for thread in topicos_existentes:
        if thread.id in canonicos or (thread.archived and thread.locked):
            continue
        try:
            # Apaga somente tópico redundante comprovadamente vazio (apenas a
            # mensagem inicial). Registros antigos nunca são apagados em lote.
            quantidade = getattr(thread, "message_count", None)
            if quantidade is not None and quantidade <= 1:
                await thread.delete(reason="Remoção de tópico duplicado vazio após consolidação do Registro Global")
                excluidos_vazios += 1
                continue
            await thread.edit(
                archived=True,
                locked=True,
                reason="Tópico antigo com histórico preservado após consolidação do Registro Global",
            )
            aposentados += 1
        except discord.NotFound:
            continue
        except (discord.Forbidden, discord.HTTPException):
            _LOG.exception("Falha ao limpar tópico redundante (%s).", thread.id)

    _LOG.info(
        "Registro Global organizado: %s áreas oficiais; %s tópicos duplicados vazios excluídos; "
        "%s tópicos antigos com histórico arquivados e preservados; migração destrutiva executada=%s.",
        len(resultado), excluidos_vazios, aposentados, migracao_executada is not None,
    )
    return resultado


async def registrar(
    guild: discord.Guild,
    categoria: str,
    titulo: str,
    descricao: str | None = None,
    *,
    embed: discord.Embed | None = None,
    cor: int | None = None,
    arquivo: discord.File | None = None,
    view: discord.ui.View | None = None,
    content: str | None = None,
    allowed_mentions: discord.AllowedMentions | None = None,
) -> bool:
    """Publica um registro no tópico permanente apropriado sem interromper o fluxo principal."""
    if guild.id != GUILD_NEMESIS_ID:
        return False
    categoria = normalizar_categoria(categoria)
    if categoria not in CATEGORIAS:
        _LOG.error("Categoria de registro desconhecida: %s", categoria)
        return False
    try:
        canal = guild.get_channel(CANAL_REGISTRO_GLOBAL_ID)
        if canal is None:
            canal = await guild.fetch_channel(CANAL_REGISTRO_GLOBAL_ID)
        if not isinstance(canal, discord.ForumChannel):
            raise TypeError(f"Canal {CANAL_REGISTRO_GLOBAL_ID} não é um Fórum.")
        validar_privacidade(canal)
        thread = await _obter_topico(canal, categoria)
        if thread.archived or thread.locked:
            await thread.edit(archived=False, locked=False, reason="Reabrir tópico permanente para novos registros")
            nome, descricao_topico = CATEGORIAS[categoria]
            await _atualizar_cabecalho_topico(thread, nome, descricao_topico)

        cor_final = cor if cor is not None else CORES_CATEGORIAS[categoria]
        emoji = EMOJIS_CATEGORIAS[categoria]
        registro = embed.copy() if embed is not None else criar_embed(
            title=f"{emoji}  {str(titulo or 'Registro')[:240]}",
            description=str(descricao or "Sem detalhes.")[:4096],
            cor=cor_final,
        )
        if embed is not None and cor is None:
            registro.color = discord.Colour(cor_final)
            if registro.title and not registro.title.startswith(emoji):
                registro.title = f"{emoji}  {registro.title}"[:256]
        if not registro.title:
            registro.title = str(titulo or "Registro")[:256]
        if registro.timestamp is None:
            registro.timestamp = datetime.now(timezone.utc)
        if not registro.author.name:
            registro.set_author(name="NÊMESIS | Registro Global")
        if not registro.footer.text:
            registro.set_footer(text=f"◈ NÊMESIS • REGISTRO GLOBAL • {CATEGORIAS[categoria][0]}")
        await thread.send(
            content=content,
            embed=registro,
            file=arquivo,
            view=view,
            allowed_mentions=allowed_mentions or discord.AllowedMentions.none(),
        )
        return True
    except (discord.Forbidden, discord.NotFound, discord.HTTPException, TypeError, ValueError):
        _LOG.exception("Não foi possível publicar no Registro Global (guild=%s, categoria=%s).", guild.id, categoria)
    except Exception:
        _LOG.exception("Falha inesperada no Registro Global (guild=%s, categoria=%s).", guild.id, categoria)
    return False
