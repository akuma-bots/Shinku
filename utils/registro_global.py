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

# OCTÓGONO (oito posições + cargo coletivo) e todos os cargos funcionais de staff.
CARGOS_ACESSO_IDS = {
    1563995880015536193, 1563995880015536192, 1563995880015536191,
    1563995880015536190, 1563995880015536189, 1563995880007139428,
    1563995880007139427, 1563995880007139426, 1563995880007139425,
    1563995880007139424, 1563995880007139423, 1563995880007139422,
    1563995880007139421, 1563995880007139420, 1563995880007139419,
    1563995879998754946, 1563995879998754945,
}

CATEGORIAS = {
    "mensagens": ("🆕 NÊMESIS V3・01・Mensagens", "Exclusões, edições e remoções em massa de mensagens."),
    "atendimento": ("🆕 NÊMESIS V3・02・Atendimento", "Abertura, atribuição, encerramento, avaliações e transcrições de tickets."),
    "moderacao": ("🆕 NÊMESIS V3・03・Moderação", "Advertências, timeouts, expulsões, banimentos e ações da equipe."),
    "membros": ("🆕 NÊMESIS V3・04・Membros", "Entradas, saídas, alterações de cargos e dados de membros."),
    "sistemas": ("🆕 NÊMESIS V3・05・Sistemas", "Missões, contribuições, temporadas, rankings, guerras e eventos operacionais."),
    "administracao": ("🆕 NÊMESIS V3・06・Administração", "Configurações, permissões, alterações estruturais e decisões administrativas."),
    "seguranca": ("🆕 NÊMESIS V3・07・Segurança", "AutoMod, Anti-Raid, falhas de proteção e incidentes de segurança."),
    "formularios": ("🆕 NÊMESIS V3・08・Formulários", "Inscrições, candidaturas, aprovações, recusas e revisões."),
    "progressao": ("🆕 NÊMESIS V3・09・Progressão", "XP, níveis, patentes, promoções, rebaixamentos e evolução individual."),
    "missoes": ("🆕 NÊMESIS V3・10・Missões", "Criação, atribuição, conclusão, validação e recompensas de missões."),
    "competicoes": ("🆕 NÊMESIS V3・11・Competições", "Desafios, lutas, guerras, placares, participantes e resultados competitivos."),
    "eventos": ("🆕 NÊMESIS V3・12・Eventos", "Agenda, inscrições, campeonatos, atividades e resultados de eventos."),
    "parcerias": ("🆕 NÊMESIS V3・13・Parcerias", "Solicitações, aprovações, representantes, cargos e alterações de parcerias."),
    "integracoes": ("🆕 NÊMESIS V3・14・Integrações", "Roblox, dashboard, APIs externas e sincronizações entre sistemas."),
    "infraestrutura": ("🆕 NÊMESIS V3・15・Infraestrutura", "Conexões, armazenamento, health checks, tarefas e disponibilidade do Shinku."),
    "configuracoes": ("🆕 NÊMESIS V3・16・Configurações", "Mudanças de configuração, parâmetros e ajustes operacionais do servidor."),
    "entradas": ("🆕 NÊMESIS V3・17・Entradas", "Entradas, saídas, reentradas, convites associados e integração inicial de membros."),
    "historico_membros": ("🆕 NÊMESIS V3・18・Histórico Membros", "Linha do tempo individual: alterações de perfil, apelido, status, participação e ocorrências vinculadas ao membro."),
    "cargos": ("🆕 NÊMESIS V3・19・Histórico Cargos", "Concessão, remoção, alteração e sincronização de cargos, com autor identificado quando disponível."),
    "convites": ("🆕 NÊMESIS V3・20・Convites", "Criação, remoção e uso de convites, convites atribuídos e estatísticas de recrutamento."),
    "voz": ("🆕 NÊMESIS V3・21・Chamadas", "Entradas, saídas, movimentações e alterações relevantes nos canais de voz."),
    "anexos": ("🆕 NÊMESIS V3・22・Anexos", "Arquivos, imagens, vídeos e outros anexos enviados, editados ou removidos em mensagens."),
    "atividade": ("🆕 NÊMESIS V3・23・Atividade", "Participação em atividades, presença em eventos e métricas de engajamento que os sistemas realmente coletarem."),
    "conquistas": ("🆕 NÊMESIS V3・24・Conquistas", "Conquistas desbloqueadas, recordes, marcos pessoais e recompensas concedidas."),
    "sorteios": ("🆕 NÊMESIS V3・25・Sorteios", "Criação, participação, encerramento, seleção de vencedores e entrega de prêmios."),
    "sugestoes": ("🆕 NÊMESIS V3・26・Sugestões", "Sugestões recebidas, votos, decisões, mudanças de status e resultados de votações."),
    "relatorios": ("🆕 NÊMESIS V3・27・Relatórios", "Relatórios enviados, revisados, aprovados, recusados e encaminhamentos da equipe."),
    "roblox": ("🆕 NÊMESIS V3・28・Roblox", "Vínculos de contas, verificações externas, sincronizações de grupos e falhas da integração Roblox."),
    "automod": ("🆕 NÊMESIS V3・29・AutoMod", "Detecções, bloqueios, filtros, ações automáticas, falsos positivos revisados e falhas do AutoMod."),
}
_LOCKS: dict[tuple[int, str], asyncio.Lock] = {}


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


async def _limpeza_v3_concluida(guild_id: int) -> bool:
    ids = await _ler_ids(guild_id)
    return ids.get("_limpeza_total_v3_concluida") is True


async def _marcar_limpeza_v3_concluida(guild_id: int) -> None:
    chave = str(guild_id)
    def atualizar(dados):
        if not isinstance(dados, dict):
            dados = {}
        servidor = dados.get(chave)
        if not isinstance(servidor, dict):
            servidor = {}
        servidor["_limpeza_total_v3_concluida"] = True
        dados[chave] = servidor
        return dados
    await atualizar_json(ARQUIVO, {}, atualizar)


async def _excluir_todos_topicos(forum: discord.ForumChannel) -> int:
    """Exclusão única e intencional de todos os tópicos do fórum dedicado."""
    encontrados: dict[int, discord.Thread] = {t.id: t for t in forum.threads}
    async for thread in forum.archived_threads(limit=None):
        encontrados[thread.id] = thread

    excluidos = 0
    for thread in encontrados.values():
        try:
            await thread.delete(
                reason="Reconstrução total autorizada do Registro Global NÊMESIS: remoção de todos os tópicos antigos"
            )
            excluidos += 1
            _LOG.info("Tópico antigo excluído na reconstrução V3: %s (%s)", thread.name, thread.id)
        except discord.NotFound:
            continue
        except (discord.Forbidden, discord.HTTPException):
            _LOG.exception("Não foi possível excluir o tópico %s; a reconstrução foi interrompida.", thread.id)
            raise
    _LOG.warning("Limpeza total do Registro Global concluída: %s tópicos excluídos.", excluidos)
    return excluidos


def _embed_cabecalho_topico(nome: str, descricao: str) -> discord.Embed:
    embed = discord.Embed(
        title=nome,
        description=(
            "**CENTRAL OFICIAL DE AUDITORIA**\n"
            "Área permanente de registros operacionais da NÊMESIS. "
            "As ocorrências são organizadas por assunto neste mesmo tópico."
        ),
        color=0xB3132B,
    )
    embed.add_field(name="ESCOPO DESTE TÓPICO", value=descricao[:1024], inline=False)
    embed.add_field(
        name="PADRÃO DE AUDITORIA",
        value=(
            "Quando disponível, cada registro identifica responsável, membro relacionado, "
            "ação, canal/protocolo, data e resultado. Dados não observáveis pelo Discord "
            "não são presumidos."
        ),
        inline=False,
    )
    embed.add_field(
        name="ORGANIZAÇÃO",
        value=(
            "Os eventos desta categoria são adicionados em sequência aqui. "
            "Não é criado um tópico por ocorrência e os registros não devem ser misturados "
            "com assuntos de outras categorias."
        ),
        inline=False,
    )
    embed.add_field(
        name="ACESSO E INTEGRIDADE",
        value=(
            "Fórum restrito aos cargos autorizados da NÊMESIS. "
            "O cabeçalho é mantido pelo Shinku; as ocorrências são acrescentadas abaixo."
        ),
        inline=False,
    )
    embed.set_footer(text="NÊMESIS • REGISTRO GLOBAL V3 • TÓPICO PERMANENTE")
    return embed


async def _atualizar_cabecalho_topico(
    thread: discord.Thread,
    nome: str,
    descricao: str,
) -> None:
    if thread.archived or thread.locked:
        return
    embed = _embed_cabecalho_topico(nome, descricao)
    try:
        mensagem = await thread.fetch_message(thread.id)
        atual = mensagem.embeds[0].to_dict() if mensagem.embeds else None
        if atual != embed.to_dict():
            await mensagem.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            _LOG.info("Cabeçalho do tópico atualizado: %s (%s)", nome, thread.id)
            await asyncio.sleep(0.2)
    except discord.NotFound:
        _LOG.warning("Tópico sem mensagem inicial recuperável: %s (%s).", nome, thread.id)
    except (discord.Forbidden, discord.HTTPException):
        _LOG.exception("Não foi possível atualizar o cabeçalho do tópico %s (%s).", nome, thread.id)


async def _obter_topico(
    forum: discord.ForumChannel,
    categoria: str,
    topicos_existentes: list[discord.Thread] | None = None,
) -> discord.Thread:
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoria de registro desconhecida: {categoria}")
    nome, descricao = CATEGORIAS[categoria]
    async with _lock(forum.guild.id, categoria):
        ids = await _ler_ids(forum.guild.id)
        # O ID salvo pode apontar para um tópico legado com nome antigo.
        # Primeiro procuramos um tópico que já tenha o nome canônico; só depois
        # reaproveitamos/renomeamos o ID salvo. Isso evita perpetuar a estrutura velha.
        thread_salva = None
        thread_id = ids.get(categoria)
        if thread_id:
            thread_salva = forum.guild.get_thread(int(thread_id))
            if thread_salva is None:
                try:
                    thread_salva = await forum.guild.fetch_channel(int(thread_id))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    thread_salva = None
            if thread_salva is not None and thread_salva.parent_id != forum.id:
                thread_salva = None
            if (
                thread_salva is not None
                and topicos_existentes is not None
                and all(item.id != thread_salva.id for item in topicos_existentes)
            ):
                topicos_existentes.append(thread_salva)

        existentes = topicos_existentes
        if existentes is None:
            existentes = list(forum.threads)
            async for thread in forum.archived_threads(limit=None):
                if all(item.id != thread.id for item in existentes):
                    existentes.append(thread)

        # Se o tópico canônico já existe, ele prevalece sobre qualquer ID legado.
        for thread in existentes:
            if thread.name == nome:
                if thread_salva is not None and thread_salva.id != thread.id:
                    _LOG.info(
                        "Tópico legado %s (%s) substituído pelo canônico %s (%s); será aposentado na limpeza.",
                        thread_salva.name,
                        thread_salva.id,
                        nome,
                        thread.id,
                    )
                if ids.get(categoria) != thread.id:
                    await _salvar_id(forum.guild.id, categoria, thread.id)
                await _atualizar_cabecalho_topico(thread, nome, descricao)
                return thread

        # A geração V3 é uma reconstrução intencional: nunca reaproveita nem
        # renomeia os tópicos legados. Cria um destino novo e deixa o antigo
        # fora do mapa canônico para ser arquivado/bloqueado na limpeza.
        thread_salva = None

        inicial = _embed_cabecalho_topico(nome, descricao)
        criado = await forum.create_thread(
            name=nome,
            embed=inicial,
            auto_archive_duration=10080,
            reason="Provisionamento dos tópicos permanentes do Registro Global NÊMESIS",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        thread = criado.thread
        if topicos_existentes is not None:
            topicos_existentes.append(thread)
        await _salvar_id(forum.guild.id, categoria, thread.id)
        _LOG.info("Tópico permanente criado: %s (%s)", nome, thread.id)
        # A criação de threads usa a mesma rota do Fórum; espaçar as operações
        # evita rajadas de 429 durante a primeira sincronização de 29 destinos.
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



async def garantir_topicos(guild: discord.Guild) -> dict[str, int]:
    """Cria ou recupera os tópicos fixos configurados; não cria duplicatas por evento."""
    if guild.id != GUILD_NEMESIS_ID:
        return {}
    canal = guild.get_channel(CANAL_REGISTRO_GLOBAL_ID)
    if canal is None:
        canal = await guild.fetch_channel(CANAL_REGISTRO_GLOBAL_ID)
    if not isinstance(canal, discord.ForumChannel) or canal.guild.id != guild.id:
        raise TypeError("O destino configurado não é o Fórum de Registro Global da NÊMESIS.")
    await configurar_permissoes(canal)
    validar_privacidade(canal)
    # Reconstrução V3: executa a exclusão total uma única vez. O marcador só
    # é gravado depois que os 29 destinos novos foram criados; se houver falha
    # no meio, a próxima inicialização repete a limpeza dos tópicos parciais.
    reconstruindo = not await _limpeza_v3_concluida(guild.id)
    if reconstruindo:
        await _excluir_todos_topicos(canal)
        await atualizar_json(ARQUIVO, {}, lambda dados: {
            **(dados if isinstance(dados, dict) else {}),
            str(guild.id): {"_limpeza_total_v3_concluida": False},
        })

    # Faz uma única leitura dos tópicos ativos e arquivados.
    topicos_existentes: list[discord.Thread] = list(canal.threads)
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

    # Após a reconstrução V3, o Fórum deve conter apenas os destinos canônicos.
    # Em sincronizações normais, tópicos extras são arquivados/bloqueados sem
    # interferir nos 29 destinos oficiais.
    canonicos = set(resultado.values())
    aposentados = 0
    legados: dict[int, discord.Thread] = {
        thread.id: thread for thread in topicos_existentes
    }

    for thread in legados.values():
        if thread.id in canonicos or (thread.archived and thread.locked):
            continue
        try:
            await thread.edit(
                archived=True,
                locked=True,
                reason="Aposentação de tópico legado/duplicado após sincronização do Registro Global NÊMESIS",
            )
            aposentados += 1
        except discord.NotFound:
            continue
        except (discord.Forbidden, discord.HTTPException):
            _LOG.exception("Falha ao aposentar tópico legado (%s).", thread.id)
    if reconstruindo:
        await _marcar_limpeza_v3_concluida(guild.id)
        _LOG.warning(
            "RECONSTRUÇÃO TOTAL V3 CONCLUÍDA: %s tópicos novos criados após exclusão de todos os tópicos anteriores.",
            len(resultado),
        )
    _LOG.info(
        "Sincronização do Registro Global concluída: %s destinos canônicos; %s tópicos legados arquivados e bloqueados.",
        len(resultado), aposentados,
    )
    return resultado


async def registrar(
    guild: discord.Guild,
    categoria: str,
    titulo: str,
    descricao: str | None = None,
    *,
    embed: discord.Embed | None = None,
    cor: int = 0x99AAB5,
    arquivo: discord.File | None = None,
    view: discord.ui.View | None = None,
    content: str | None = None,
    allowed_mentions: discord.AllowedMentions | None = None,
) -> bool:
    """Publica um registro no tópico permanente apropriado sem interromper o fluxo principal."""
    if guild.id != GUILD_NEMESIS_ID:
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
        if categoria not in CATEGORIAS:
            raise ValueError(f"Categoria de registro desconhecida: {categoria}")

        registro = embed.copy() if embed is not None else criar_embed(
            title=str(titulo or "Registro")[:256],
            description=str(descricao or "Sem detalhes.")[:4096],
            cor=cor,
        )
        if not registro.title:
            registro.title = str(titulo or "Registro")[:256]
        if registro.timestamp is None:
            registro.timestamp = datetime.now(timezone.utc)
        if not registro.author.name:
            registro.set_author(name="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  |  CENTRAL DE REGISTROS")
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
