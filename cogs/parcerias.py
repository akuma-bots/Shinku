import asyncio
import logging
import time
import uuid

import discord
from discord import app_commands
from discord.ext import commands

from utils.apresentacao import criar_embed

from utils.storage import carregar, salvar, atualizar_json
from utils.guild_config import get_config, set_config, lideranca_only


ARQUIVO = "parcerias.json"
logger = logging.getLogger(__name__)
_PARCERIAS_LOCK = asyncio.Lock()


async def _todas():
    dados = await carregar(ARQUIVO, {})
    return dados if isinstance(dados, dict) else {}


async def _da_guild(guild_id: int):
    dados = await _todas()

    lista = dados.get(str(guild_id), [])

    if not isinstance(lista, list):
        lista = []

    return [parceria for parceria in lista if isinstance(parceria, dict)]


async def _salvar_da_guild(guild_id: int, lista):
    dados = await _todas()

    dados[str(guild_id)] = lista

    await salvar(
        ARQUIVO,
        dados,
    )


def _normalizar_parceria(parceria: dict, guild_id: int) -> dict:
    """
    Garante que parcerias antigas continuem funcionando e tenham
    os campos necessários para o histórico interno de parcerias.
    """

    resultado = dict(parceria)

    resultado.setdefault(
        "id",
        str(uuid.uuid4()),
    )

    resultado.setdefault(
        "guild_id",
        guild_id,
    )

    resultado.setdefault(
        "nome",
        "Parceria",
    )

    resultado.setdefault(
        "convite",
        "",
    )

    resultado.setdefault(
        "descricao",
        "",
    )

    resultado.setdefault(
        "banner",
        None,
    )

    resultado.setdefault(
        "cargo_id",
        None,
    )

    resultado.setdefault(
        "criado_por_id",
        None,
    )

    resultado.setdefault(
        "criado_em",
        time.time(),
    )

    resultado.setdefault(
        "atualizado_em",
        resultado["criado_em"],
    )

    resultado.setdefault(
        "status",
        "ativa",
    )

    return resultado


async def _normalizar_todas_guild(guild_id: int):
    lista = await _da_guild(guild_id)

    alterou = False
    resultado = []

    for parceria in lista:
        normalizada = _normalizar_parceria(
            parceria,
            guild_id,
        )

        if normalizada != parceria:
            alterou = True

        resultado.append(normalizada)

    if alterou:
        await _salvar_da_guild(
            guild_id,
            resultado,
        )

    return resultado


async def _cargo_categoria_parcerias(
    guild: discord.Guild,
) -> discord.Role | None:

    config = await get_config(
        guild.id
    )

    cargo_id = config.get(
        "cargo_categoria_parcerias_id"
    )

    if cargo_id:
        cargo = guild.get_role(
            cargo_id
        )

        if cargo:
            return cargo

    return discord.utils.get(
        guild.roles,
        name="PARCERIAS",
    )


async def _criar_cargo_da_parceria(
    guild: discord.Guild,
    nome: str,
) -> tuple[discord.Role | None, str | None]:

    cargo_categoria = (
        await _cargo_categoria_parcerias(
            guild
        )
    )

    if not cargo_categoria:
        return None, (
            "não achei o cargo-categoria de parcerias. "
            "Configure com `/configurar-cargo-parcerias` primeiro."
        )

    try:
        novo_cargo = await guild.create_role(
            name=nome,
            reason=f"Cargo automático da parceria: {nome}",
        )

    except discord.Forbidden:
        return None, (
            "não tenho permissão de 'Gerenciar Cargos' "
            "para criar o cargo."
        )

    except discord.HTTPException:
        return None, (
            "o Discord recusou a criação do cargo."
        )

    try:
        posicao = max(
            cargo_categoria.position - 1,
            1,
        )

        await novo_cargo.edit(
            position=posicao
        )

    except (
        discord.Forbidden,
        discord.HTTPException,
    ):
        return novo_cargo, (
            "criei o cargo, mas não consegui posicioná-lo "
            "abaixo da categoria de parcerias."
        )

    return novo_cargo, None


class ParceriaView(discord.ui.View):
    """
    Botão persistente para selecionar/remover o cargo da parceria.
    """

    def __init__(
        self,
        role_id: int,
    ):
        super().__init__(
            timeout=None
        )

        self.role_id = role_id

        button = discord.ui.Button(
            label="Selecionar cargo",
            style=discord.ButtonStyle.secondary,
            custom_id=(
                f"parceria:selecionar:{role_id}"
            ),
        )

        button.callback = (
            self._selecionar_cargo
        )

        self.add_item(button)

    async def _selecionar_cargo(
        self,
        interaction: discord.Interaction,
    ):
        guild = interaction.guild
        member = interaction.user

        if (
            not guild
            or not isinstance(
                member,
                discord.Member,
            )
        ):
            await interaction.response.send_message(
                "Esta ação só pode ser usada dentro do servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        role = guild.get_role(
            self.role_id
        )

        if not role:
            await interaction.response.send_message(
                "O cargo desta parceria não existe mais.",
                ephemeral=True,
            )
            return

        bot_member = guild.me

        if (
            not bot_member
            or bot_member.top_role <= role
        ):
            await interaction.response.send_message(
                "Não consigo gerenciar este cargo porque ele está acima "
                "ou no mesmo nível do meu maior cargo.",
                ephemeral=True,
            )
            return

        try:

            if role in member.roles:

                await member.remove_roles(
                    role,
                    reason=(
                        f"Cargo da parceria removido por "
                        f"{member}"
                    ),
                )

                await interaction.response.send_message(
                    f"✓ O cargo {role.mention} foi removido de você.",
                    ephemeral=True,
                )

            else:

                await member.add_roles(
                    role,
                    reason=(
                        f"Cargo da parceria selecionado por "
                        f"{member}"
                    ),
                )

                await interaction.response.send_message(
                    f"✓ O cargo {role.mention} foi adicionado a você.",
                    ephemeral=True,
                )

        except discord.Forbidden:

            await interaction.response.send_message(
                "Não tenho permissão para gerenciar este cargo.",
                ephemeral=True,
            )

        except discord.HTTPException:

            await interaction.response.send_message(
                "Não foi possível alterar seu cargo agora. "
                "Tente novamente.",
                ephemeral=True,
            )





MARCADOR_CARTAO_PARCERIAS = "NÊMESIS • ALIANÇAS E PARCERIAS • V2"


def _componentes_contem_marcador(componentes, marcador: str) -> bool:
    pendentes = list(componentes or [])
    while pendentes:
        componente = pendentes.pop()
        if marcador.casefold() in str(getattr(componente, "content", "") or "").casefold():
            return True
        pendentes.extend(list(getattr(componente, "children", []) or []))
    return False


class ParceriaLayoutView(discord.ui.LayoutView):
    """Apresentação da parceria e botão de cargo no mesmo cartão."""

    def __init__(self, role_id: int | None, embed: discord.Embed | None = None):
        super().__init__(timeout=None)
        partes = [f"## {embed.title if embed and embed.title else '🤝 ALIANÇA OFICIAL'}"]
        if embed and embed.description:
            partes.append(embed.description)
        if embed:
            for campo in embed.fields:
                partes.append(f"**{campo.name}**\n{campo.value}")
        componentes = []
        if embed and embed.image and embed.image.url:
            componentes.append(discord.ui.MediaGallery(
                discord.MediaGalleryItem(url=embed.image.url, description="NÊMESIS • Parceria")
            ))
        componentes.extend([
            discord.ui.TextDisplay("\n\n".join(partes)[:3900]),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        ])
        if role_id:
            origem = ParceriaView(int(role_id))
            original = origem.children[0]
            botao = discord.ui.Button(
                label=original.label, style=original.style,
                custom_id=original.custom_id, emoji=original.emoji,
            )
            botao.callback = original.callback
            componentes.append(discord.ui.ActionRow(botao))
        componentes.extend([
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(f"-# Nêmesis Systeam • Alianças e parcerias • {MARCADOR_CARTAO_PARCERIAS}"),
        ])
        self.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))


def _embed_parceria_publica(parceria: dict, guild: discord.Guild, indice: int | None = None) -> discord.Embed:
    """Cartão público padronizado das alianças oficiais."""
    nome = str(parceria.get("nome") or "Comunidade parceira")[:180]
    descricao = str(parceria.get("descricao") or "Aliança oficial da NÊMESIS.")[:3500]
    embed = discord.Embed(
        title=f"◈ NÊMESIS  |  ALIANÇA OFICIAL",
        description=f"**{nome}**\n{descricao}",
        color=0x8F1D2C,
        timestamp=discord.utils.utcnow(),
    )
    status = str(parceria.get("status") or "ativa").lower()
    status_label = {"ativa": "🟢 ATIVA", "suspensa": "🔴 SUSPENSA", "revisao_pendente": "🟡 REVISÃO PENDENTE", "removida": "⚫ ENCERRADA"}.get(status, status.upper())
    embed.add_field(name="STATUS DA ALIANÇA", value="**" + status_label + "**", inline=True)
    embed.add_field(name="CATEGORIA", value=str(parceria.get("categoria") or "Reconhecida"), inline=True)
    if parceria.get("segmento"):
        embed.add_field(name="SEGMENTO", value=str(parceria.get("segmento"))[:180], inline=True)
    if parceria.get("membros"):
        embed.add_field(name="COMUNIDADE", value=(format(int(parceria["membros"]), ",").replace(",", ".") + " membros"), inline=True)
    convite = str(parceria.get("convite") or "")
    embed.add_field(name="ACESSO À COMUNIDADE", value=f"[Entrar no servidor]({convite})" if convite else "Convite indisponível", inline=False)
    cargo = guild.get_role(int(parceria["cargo_id"])) if parceria.get("cargo_id") else None
    embed.add_field(name="CARGO DE PARCEIRO", value=cargo.mention if cargo else "Não vinculado", inline=True)
    embed.add_field(name="REGISTRO", value=str(parceria.get("id", "—"))[:18], inline=True)
    if parceria.get("proxima_revisao"):
        embed.add_field(name="PRÓXIMA REVISÃO", value=f'<t:{int(parceria.get("proxima_revisao"))}:D>', inline=True)
    banner = parceria.get("banner")
    if banner:
        try:
            embed.set_image(url=str(banner))
        except (TypeError, discord.HTTPException):
            pass
    embed.set_author(name="NÊMESIS • RELAÇÕES INSTITUCIONAIS")
    sufixo = f" • Registro {indice}" if indice else ""
    embed.set_footer(text="Aliança verificada pela administração NÊMESIS" + sufixo)
    return embed


async def registrar_parceria_aprovada(
    guild: discord.Guild,
    candidatura: dict,
    aprovador: discord.Member,
) -> tuple[dict | None, str | None]:
    """Converte uma candidatura aprovada em parceria ativa no cadastro oficial."""
    candidatura_id = str(candidatura.get("id") or "")
    async with _PARCERIAS_LOCK:
        lista = await _normalizar_todas_guild(guild.id)
        existente = next((p for p in lista if p.get("candidatura_id") == candidatura_id), None)
        if existente:
            return existente, None

        nome = str(candidatura.get("nome") or "Comunidade parceira").strip()[:80]
        cargo, aviso_cargo = await _criar_cargo_da_parceria(guild, nome)
        agora = time.time()
        parceria = {
            "id": str(uuid.uuid4()),
            "guild_id": guild.id,
            "nome": nome,
            "convite": str(candidatura.get("convite") or ""),
            "descricao": str(candidatura.get("proposta") or candidatura.get("segmento") or "Aliança oficial da NÊMESIS.")[:3500],
            "segmento": str(candidatura.get("segmento") or "")[:180],
            "membros": candidatura.get("membros"),
            "banner": candidatura.get("banner"),
            "cargo_id": cargo.id if cargo else None,
            "criado_por_id": aprovador.id,
            "criado_em": agora,
            "atualizado_em": agora,
            "status": "ativa",
            "categoria": str(candidatura.get("categoria") or "Reconhecida"),
            "candidatura_id": candidatura_id,
            "proxima_revisao": agora + (15 * 24 * 60 * 60),
        }
        config = await get_config(guild.id)
        canal_id = config.get("canal_parcerias_id")
        canal = guild.get_channel(canal_id) if canal_id else None
        if isinstance(canal, discord.TextChannel):
            try:
                mensagem = await canal.send(
                    view=ParceriaLayoutView(cargo.id if cargo else None, _embed_parceria_publica(parceria, guild)),
                    allowed_mentions=discord.AllowedMentions.none(),
                )
                parceria["mensagem_id"] = mensagem.id
                parceria["canal_id"] = canal.id
            except (discord.Forbidden, discord.HTTPException):
                logger.exception("Falha ao publicar parceria aprovada: %s", nome)
                parceria["mensagem_id"] = None
                parceria["canal_id"] = canal.id
        else:
            parceria["mensagem_id"] = None
            parceria["canal_id"] = canal_id

        def persistir(dados):
            if not isinstance(dados, dict):
                dados = {}
            atual = dados.get(str(guild.id), [])
            if not isinstance(atual, list):
                atual = []
            existente_atual = next((p for p in atual if isinstance(p, dict) and p.get("candidatura_id") == candidatura_id), None)
            if existente_atual:
                return dados
            atual.append(parceria)
            dados[str(guild.id)] = atual
            return dados
        await atualizar_json(ARQUIVO, {}, persistir)

    try:
        from utils.registro_global import registrar as registrar_global
        await registrar_global(
            guild, "parcerias", "Aliança oficial aprovada e ativada",
            f"**Comunidade:** {nome}\n**Candidatura:** {candidatura_id}\n"
            f"**Aprovador:** {aprovador.mention}\n**Categoria:** {parceria['categoria']}\n"
            f"**Próxima revisão:** <t:{int(parceria['proxima_revisao'])}:F>\n"
            f"**Cargo:** {cargo.mention if cargo else 'Não criado'}",
            cor=0xB58A45,
        )
    except Exception:
        logger.exception("Falha ao auditar ativação de parceria %s", nome)
    return parceria, aviso_cargo


class Parcerias(commands.Cog):
    """
    Sistema de parcerias da NÊMESIS.

    O arquivo parcerias.json é armazenamento interno do bot,
    persistido pelo adaptador de armazenamento configurado.
    """

    def __init__(
        self,
        bot: commands.Bot,
    ):
        self.bot = bot

    @app_commands.command(
        name="configurar-canal-parcerias",
        description=(
            "Define onde as parcerias são anunciadas."
        ),
    )
    @app_commands.describe(
        canal=(
            "Canal de texto para os anúncios de parceria"
        ),
    )
    @lideranca_only()
    async def configurar_canal_parcerias(
        self,
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ):

        await set_config(
            interaction.guild.id,
            canal_parcerias_id=canal.id,
        )

        await interaction.response.send_message(
            f"✓ Parcerias agora são anunciadas em {canal.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="configurar-cargo-parcerias",
        description=(
            "Define o cargo-categoria abaixo do qual "
            "os cargos de parceria são criados."
        ),
    )
    @app_commands.describe(
        cargo=(
            "Cargo usado como separador de PARCERIAS"
        ),
    )
    @lideranca_only()
    async def configurar_cargo_parcerias(
        self,
        interaction: discord.Interaction,
        cargo: discord.Role,
    ):

        await set_config(
            interaction.guild.id,
            cargo_categoria_parcerias_id=cargo.id,
        )

        await interaction.response.send_message(
            f"✓ Novos cargos de parceria serão criados "
            f"logo abaixo de {cargo.mention}.",
            ephemeral=True,
        )

    @app_commands.command(
        name="adicionar-parceria",
        description=(
            "Registra uma parceria, anuncia no canal "
            "e cria o cargo dela."
        ),
    )
    @app_commands.describe(
        nome="Nome do servidor parceiro",
        convite="Link de convite do servidor parceiro",
        descricao="Descrição curta da parceria",
        banner="URL de uma imagem/banner (opcional)",
    )
    @lideranca_only()
    async def adicionar_parceria(
        self,
        interaction: discord.Interaction,
        nome: str,
        convite: str,
        descricao: str,
        banner: str = None,
    ):

        config = await get_config(
            interaction.guild.id
        )

        canal_id = config.get(
            "canal_parcerias_id"
        )

        canal = (
            interaction.guild.get_channel(
                canal_id
            )
            if canal_id
            else None
        )

        if not canal:
            await interaction.response.send_message(
                "Configure o canal de parcerias primeiro com "
                "`/configurar-canal-parcerias`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        cargo, aviso_cargo = (
            await _criar_cargo_da_parceria(
                interaction.guild,
                nome,
            )
        )

        agora = time.time()

        parceria = {
            "id": str(uuid.uuid4()),
            "guild_id": interaction.guild.id,
            "nome": nome,
            "convite": convite,
            "descricao": descricao,
            "banner": banner,
            "cargo_id": (
                cargo.id
                if cargo
                else None
            ),
            "criado_por_id": interaction.user.id,
            "criado_em": agora,
            "atualizado_em": agora,
            "status": "ativa",
            "categoria": "Reconhecida",
            "proxima_revisao": agora + (15 * 24 * 60 * 60),
        }

        embed = _embed_parceria_publica(parceria, interaction.guild)

        try:

            mensagem = await canal.send(
                view=ParceriaLayoutView(cargo.id if cargo else None, embed),
            )

            parceria["mensagem_id"] = (
                mensagem.id
            )

            parceria["canal_id"] = (
                canal.id
            )

        except discord.Forbidden:

            # Se o anúncio falhar, mantemos o registro para correção posterior.
            parceria["mensagem_id"] = None
            parceria["canal_id"] = canal.id

        except discord.HTTPException:

            parceria["mensagem_id"] = None
            parceria["canal_id"] = canal.id

        async with _PARCERIAS_LOCK:
            lista = await _normalizar_todas_guild(interaction.guild.id)
            lista.append(parceria)
            await _salvar_da_guild(interaction.guild.id, lista)

        from utils.registro_global import registrar as registrar_global
        detalhe_parceria = (
            f"**Parceria:** {nome}\n"
            f"**Responsável:** {interaction.user.mention} (ID: {interaction.user.id})\n"
            f"**Convite:** {convite}\n"
            f"**Canal:** {canal.mention}\n"
            f"**Anúncio:** {'Publicado' if parceria.get('mensagem_id') else 'Pendente de publicação'}"
        )
        await registrar_global(
            interaction.guild,
            "parcerias",
            "Nova parceria registrada",
            detalhe_parceria,
            cor=0xB3132B,
        )
        await registrar_global(
            interaction.guild,
            "historico_membros",
            "Membro registrou parceria",
            detalhe_parceria,
            cor=0xB3132B,
        )

        if cargo and not aviso_cargo:

            resultado_cargo = (
                f" e o cargo {cargo.mention} foi criado. "
                "Ele não foi atribuído automaticamente a você."
            )

        elif cargo and aviso_cargo:

            resultado_cargo = (
                f" — cargo {cargo.mention} criado, "
                f"mas {aviso_cargo}"
            )

        else:

            resultado_cargo = (
                f" — não criei o cargo: "
                f"{aviso_cargo}"
            )

        await interaction.followup.send(
            f"✓ Parceria com **{nome}** registrada "
            f"e anunciada em {canal.mention}"
            f"{resultado_cargo}",
            ephemeral=True,
        )

    @app_commands.command(
        name="remover-parceria",
        description=(
            "Remove uma parceria registrada pelo nome "
            "e o cargo dela."
        ),
    )
    @app_commands.describe(
        nome="Nome exato da parceria a remover"
    )
    @lideranca_only()
    async def remover_parceria(
        self,
        interaction: discord.Interaction,
        nome: str,
    ):

        async with _PARCERIAS_LOCK:
            lista = await _normalizar_todas_guild(
                interaction.guild.id
            )
    
            indice = next(
                (
                    i
                    for i, parceria in enumerate(lista)
                    if parceria["nome"].lower()
                    == nome.lower()
                ),
                None,
            )
    
            if indice is None:
                await interaction.response.send_message(
                    "Não achei nenhuma parceria com esse nome.",
                    ephemeral=True,
                )
                return
    
            alvo = lista[indice]
    
            cargo_id = alvo.get(
                "cargo_id"
            )
            erro_cargo = None
    
            if cargo_id:
    
                cargo = interaction.guild.get_role(
                    cargo_id
                )
    
                if cargo:
    
                    try:
                        await cargo.delete(
                            reason=(
                                f"Parceria com {nome} removida"
                            )
                        )
    
                    except (
                        discord.Forbidden,
                        discord.HTTPException,
                    ) as erro:
                        erro_cargo = str(erro)
                        logger.exception(
                            "Não foi possível remover o cargo da parceria %s (guild=%s, cargo=%s).",
                            nome,
                            interaction.guild.id,
                            cargo.id,
                        )
    
            alvo["status"] = "removida"
            alvo["atualizado_em"] = time.time()
            alvo["removido_por_id"] = (
                interaction.user.id
            )
            alvo["removido_em"] = time.time()
    
            # Mantém o registro histórico e marca a parceria como inativa.
            lista[indice] = alvo
    
            await _salvar_da_guild(
                interaction.guild.id,
                lista,
            )

        canal_anuncio_id = alvo.get("canal_id")
        mensagem_anuncio_id = alvo.get("mensagem_id")
        canal_anuncio = interaction.guild.get_channel(canal_anuncio_id) if canal_anuncio_id else None
        if isinstance(canal_anuncio, discord.TextChannel) and mensagem_anuncio_id:
            try:
                mensagem_anuncio = await canal_anuncio.fetch_message(int(mensagem_anuncio_id))
                await mensagem_anuncio.edit(
                    embed=_embed_parceria_publica(alvo, interaction.guild),
                    view=None,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, TypeError, ValueError):
                logger.exception("Não foi possível atualizar o anúncio da parceria encerrada: %s", nome)

        from utils.registro_global import registrar as registrar_global
        detalhe_remocao = (
            f"**Parceria:** {alvo.get('nome', nome)}\n"
            f"**Responsável pela remoção:** {interaction.user.mention} (ID: {interaction.user.id})\n"
            f"**Criada por:** <@{alvo.get('criado_por_id')}>\n"
            f"**Status:** Inativa\n"
            f"**Cargo:** {'Removido' if cargo_id and not erro_cargo else 'Falha ao remover' if erro_cargo else 'Não havia cargo vinculado'}"
        )
        await registrar_global(
            interaction.guild,
            "parcerias",
            "Parceria removida",
            detalhe_remocao,
            cor=0xED4245,
        )
        await registrar_global(
            interaction.guild,
            "historico_membros",
            "Membro removeu parceria",
            detalhe_remocao,
            cor=0xED4245,
        )

        aviso = (
            f" Atenção: não consegui excluir o cargo vinculado ({erro_cargo}). "
            "A parceria foi marcada como inativa; remova o cargo manualmente."
            if erro_cargo else ""
        )
        await interaction.response.send_message(
            f"✓ Parceria com **{nome}** removida e marcada como inativa.{aviso}",
            ephemeral=True,
        )

    @app_commands.command(
        name="parcerias",
        description=(
            "Mostra as parcerias ativas com o cargo "
            "de cada uma para seleção."
        ),
    )
    async def parcerias(
        self,
        interaction: discord.Interaction,
    ):

        lista = await _normalizar_todas_guild(
            interaction.guild.id
        )

        lista = [
            parceria
            for parceria in lista
            if parceria.get(
                "status",
                "ativa",
            )
            == "ativa"
        ]

        if not lista:

            await interaction.response.send_message(
                "Nenhuma parceria ativa registrada ainda.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(
            ephemeral=True
        )

        for indice, parceria in enumerate(
            lista[:25],
            start=1,
        ):

            embed = _embed_parceria_publica(parceria, interaction.guild, indice)

            cargo_id = parceria.get(
                "cargo_id"
            )

            cargo = (
                interaction.guild.get_role(
                    cargo_id
                )
                if cargo_id
                else None
            )

            await interaction.followup.send(
                view=ParceriaLayoutView(cargo.id if cargo else None, embed),
                ephemeral=True,
            )

        if len(lista) > 25:

            await interaction.followup.send(
                "⚠️ Apenas as primeiras 25 parcerias foram exibidas.",
                ephemeral=True,
            )


async def setup(
    bot: commands.Bot
):
    await bot.add_cog(
        Parcerias(bot)
    )

    # Reativa os botões das parcerias existentes
    # depois de um reinício do bot.
    dados = await _todas()

    cargos_registrados = set()

    for lista in dados.values():

        if not isinstance(lista, list):
            continue

        for parceria in lista:

            if parceria.get(
                "status",
                "ativa",
            ) != "ativa":
                continue

            cargo_id = parceria.get(
                "cargo_id"
            )

            if cargo_id and cargo_id not in cargos_registrados:
                bot.add_view(ParceriaLayoutView(cargo_id))
                cargos_registrados.add(cargo_id)

            guild_id = int(parceria.get("guild_id") or 0)
            canal_id = int(parceria.get("canal_id") or 0)
            mensagem_id = int(parceria.get("mensagem_id") or 0)
            guild = bot.get_guild(guild_id)
            canal = guild.get_channel(canal_id) if guild and canal_id else None
            if canal is not None and mensagem_id:
                try:
                    mensagem = await canal.fetch_message(mensagem_id)
                    embed = _embed_parceria_publica(parceria, guild)
                    if not _componentes_contem_marcador(mensagem.components, MARCADOR_CARTAO_PARCERIAS):
                        await mensagem.edit(content=None, embeds=[], attachments=[])
                        await mensagem.edit(
                            view=ParceriaLayoutView(cargo_id, embed),
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    logger.exception("Falha ao migrar cartão da parceria %s.", parceria.get("id"))