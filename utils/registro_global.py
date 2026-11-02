"""Centraliza os registros operacionais da NÊMESIS em tópicos permanentes de Fórum."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord

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
    "mensagens": ("📝・Mensagens", "Exclusões, edições e remoções em massa de mensagens."),
    "atendimento": ("🎫・Atendimento", "Abertura, atribuição, encerramento, avaliações e transcrições de tickets."),
    "moderacao": ("🛡️・Moderação", "Advertências, timeouts, expulsões, banimentos e ações da equipe."),
    "membros": ("👥・Membros", "Entradas, saídas, alterações de cargos e dados de membros."),
    "sistemas": ("⚙️・Sistemas", "Missões, contribuições, temporadas, rankings, guerras e eventos operacionais."),
    "administracao": ("🏛️・Administração", "Configurações, permissões, alterações estruturais e decisões administrativas."),
    "seguranca": ("🚨・Segurança", "AutoMod, Anti-Raid, falhas de proteção e incidentes de segurança."),
    "formularios": ("📋・Formulários", "Inscrições, candidaturas, aprovações, recusas e revisões."),
    "progressao": ("📈・Progressão", "XP, níveis, patentes, promoções, rebaixamentos e evolução individual."),
    "missoes": ("🎯・Missões", "Criação, atribuição, conclusão, validação e recompensas de missões."),
    "competicoes": ("⚔️・Competições", "Desafios, lutas, guerras, placares, participantes e resultados competitivos."),
    "eventos": ("🏆・Eventos", "Agenda, inscrições, campeonatos, atividades e resultados de eventos."),
    "parcerias": ("🤝・Parcerias", "Solicitações, aprovações, representantes, cargos e alterações de parcerias."),
    "integracoes": ("🔗・Integrações", "Roblox, dashboard, APIs externas e sincronizações entre sistemas."),
    "infraestrutura": ("🖥️・Infraestrutura", "Conexões, armazenamento, health checks, tarefas e disponibilidade do Shinku."),
    "configuracoes": ("⚙️・Configurações", "Mudanças de configuração, parâmetros e ajustes operacionais do servidor."),
    "entradas": ("📥・Histórico de Entradas", "Entradas, saídas, reentradas, convites associados e integração inicial de membros."),
    "historico_membros": ("🧾・Histórico dos Membros", "Linha do tempo individual: alterações de perfil, apelido, status, participação e ocorrências vinculadas ao membro."),
    "cargos": ("🎖️・Histórico de Cargos", "Concessão, remoção, alteração e sincronização de cargos, com autor identificado quando disponível."),
    "convites": ("🔗・Histórico de Convites", "Criação, remoção e uso de convites, convites atribuídos e estatísticas de recrutamento."),
    "voz": ("🎙️・Chamadas", "Entradas, saídas, movimentações e alterações relevantes nos canais de voz."),
    "anexos": ("📎・Anexos", "Arquivos, imagens, vídeos e outros anexos enviados, editados ou removidos em mensagens."),
    "atividade": ("📊・Atividade dos Membros", "Participação em atividades, presença em eventos e métricas de engajamento que os sistemas realmente coletarem."),
    "conquistas": ("🏅・Conquistas", "Conquistas desbloqueadas, recordes, marcos pessoais e recompensas concedidas."),
    "sorteios": ("🎁・Sorteios", "Criação, participação, encerramento, seleção de vencedores e entrega de prêmios."),
    "sugestoes": ("💡・Sugestões e Votações", "Sugestões recebidas, votos, decisões, mudanças de status e resultados de votações."),
    "relatorios": ("📑・Relatórios", "Relatórios enviados, revisados, aprovados, recusados e encaminhamentos da equipe."),
    "roblox": ("🧩・Integração Roblox", "Vínculos de contas, verificações externas, sincronizações de grupos e falhas da integração Roblox."),
    "automod": ("🤖・AutoMod", "Detecções, bloqueios, filtros, ações automáticas, falsos positivos revisados e falhas do AutoMod."),
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


async def _obter_topico(forum: discord.ForumChannel, categoria: str) -> discord.Thread:
    if categoria not in CATEGORIAS:
        raise ValueError(f"Categoria de registro desconhecida: {categoria}")
    nome, descricao = CATEGORIAS[categoria]
    async with _lock(forum.guild.id, categoria):
        ids = await _ler_ids(forum.guild.id)
        thread_id = ids.get(categoria)
        if thread_id:
            thread = forum.guild.get_thread(int(thread_id))
            if thread is None:
                try:
                    thread = await forum.guild.fetch_channel(int(thread_id))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    thread = None
            if thread is not None and thread.parent_id == forum.id:
                return thread

        # Recupera tópicos já existentes antes de criar, inclusive arquivados.
        for thread in forum.threads:
            if thread.name == nome:
                await _salvar_id(forum.guild.id, categoria, thread.id)
                return thread
        async for thread in forum.archived_threads(limit=100):
            if thread.name == nome:
                await _salvar_id(forum.guild.id, categoria, thread.id)
                return thread

        inicial = discord.Embed(
            title=nome,
            description=(f"**REGISTRO PERMANENTE — NÊMESIS**\n\n{descricao}\n\n"
                         "As ocorrências desta área serão adicionadas aqui em sequência. "
                         "Este tópico é fixo; não será criado um tópico por evento."),
            color=0xB3132B,
            timestamp=datetime.now(timezone.utc),
        )
        inicial.set_footer(text="NÊMESIS • Registro Global")
        criado = await forum.create_thread(
            name=nome,
            embed=inicial,
            auto_archive_duration=10080,
            reason="Provisionamento dos tópicos permanentes do Registro Global NÊMESIS",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        thread = criado.thread
        await _salvar_id(forum.guild.id, categoria, thread.id)
        _LOG.info("Tópico permanente criado: %s (%s)", nome, thread.id)
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
    resultado = {}
    for categoria in CATEGORIAS:
        thread = await _obter_topico(canal, categoria)
        resultado[categoria] = thread.id
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
        registro = embed.copy() if embed is not None else discord.Embed(
            title=str(titulo or "Registro")[:256],
            description=str(descricao or "Sem detalhes.")[:4096],
            color=cor,
        )
        if registro.timestamp is None:
            registro.timestamp = datetime.now(timezone.utc)
        if not registro.footer.text:
            registro.set_footer(text=f"NÊMESIS • Registro Global • {CATEGORIAS[categoria][0]}")
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
