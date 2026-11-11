import time
import uuid
import logging
import re
import unicodedata

import discord
from discord.ext import commands, tasks

from cogs.sorteios import ARQUIVO, _SORTEIOS_LOCK, timestamp_discord
from utils.apresentacao import criar_embed, COR_PRIMARIA, COR_SUCESSO, COR_ERRO
from utils.guild_config import GUILD_NEMESIS_ID, membro_tem_lideranca
from utils.storage import carregar, salvar

logger = logging.getLogger(__name__)
MARCADOR_PAINEL = "NEMESIS-PAINEL-SORTEIOS"


def _componentes_contem_marcador(componentes, marcador: str) -> bool:
    pendentes = list(componentes or [])
    while pendentes:
        componente = pendentes.pop()
        if marcador in str(getattr(componente, "content", "") or ""):
            return True
        pendentes.extend(list(getattr(componente, "children", []) or []))
    return False



def _canal_oficial_sorteios(guild):
    exatos = []
    candidatos = []
    for canal in guild.text_channels:
        nome_normalizado = unicodedata.normalize("NFKC", canal.name).casefold()
        tokens = re.findall(r"[a-z0-9]+", nome_normalizado)
        if tokens in (["sorteios"], ["sorteio"]):
            exatos.append(canal)
        elif any(token.startswith("sorteio") for token in tokens):
            candidatos.append(canal)
    return exatos if exatos else candidatos


async def _carregar_todos():
    dados = await carregar(ARQUIVO, {})
    return dados if isinstance(dados, dict) else {}


async def _salvar_item(sorteio):
    async with _SORTEIOS_LOCK:
        todos = await _carregar_todos()
        todos[str(sorteio["id"])] = sorteio
        sorteio["atualizado_em"] = time.time()
        await salvar(ARQUIVO, todos)


def _eh_lideranca(interaction):
    return bool(
        interaction.guild
        and interaction.guild.id == GUILD_NEMESIS_ID
        and membro_tem_lideranca(interaction.user)
    )


def _embed_sorteio(sorteio, quantidade=0):
    fim = float(sorteio.get("fim") or 0)
    descricao = (
        f"{sorteio.get('descricao') or 'Participe e concorra ao prêmio.'}\n\n"
        f"**Prêmio**\n{sorteio.get('premio', 'Não informado')}\n\n"
        f"**Participação**\n"
        f"Use o botão abaixo para participar. Cada membro pode entrar uma única vez.\n\n"
        f"**Vencedores:** {int(sorteio.get('vencedores', 1))}\n"
        f"**Encerra:** {timestamp_discord(fim, 'F')} ({timestamp_discord(fim, 'R')})\n"
        f"**Participantes:** {quantidade}"
    )
    embed = criar_embed(title="🎉 " + str(sorteio.get("titulo") or "SORTEIO NÊMESIS"), description=descricao, color=COR_PRIMARIA)
    if sorteio.get("banner"):
        embed.set_image(url=sorteio["banner"])
    embed.set_footer(text=f"NÊMESIS • Sorteios • ID:{sorteio['id']}")
    return embed


def _calcular_chances(membro, sorteio):
    """Todos os participantes têm a mesma chance; cargos não alteram elegibilidade."""
    return 1


def _card_com_view(origem: discord.ui.View, titulo: str, descricao: str,
                   rodape: str = "Nêmesis Systeam • Sorteios", imagem: str | None = None):
    """Converte controles tradicionais em componentes contidos no mesmo cartão."""
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    componentes = []
    if imagem:
        componentes.append(discord.ui.MediaGallery(
            discord.MediaGalleryItem(url=imagem, description=titulo[:100])
        ))
    componentes.extend([
        discord.ui.TextDisplay(f"## {titulo}\n{descricao}"),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ])
    linhas = {}
    for item in origem.children:
        if isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
        elif isinstance(item, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=item.placeholder,
                min_values=item.min_values,
                max_values=item.max_values,
                options=list(item.options),
                custom_id=item.custom_id,
                disabled=item.disabled,
                row=item.row,
            )
            async def selecionar(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = selecionar
        else:
            continue
        linhas.setdefault(item.row or 0, []).append(novo)
    for _, itens in sorted(linhas.items()):
        for inicio in range(0, len(itens), 5):
            componentes.append(discord.ui.ActionRow(*itens[inicio:inicio + 5]))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(f"-# {rodape}"),
    ])
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout



def _mensagem_tem_cartao_sorteio(mensagem: discord.Message, sorteio_id: str) -> bool:
    marcador = f"ID:{sorteio_id}".casefold()
    pendentes = list(getattr(mensagem, "components", []) or [])
    while pendentes:
        item = pendentes.pop()
        if marcador in str(getattr(item, "content", "") or "").casefold():
            return True
        pendentes.extend(list(getattr(item, "children", []) or []))
    return False


def _card_sorteio(sorteio: dict, quantidade: int, view: discord.ui.View):
    return _card_com_view(
        view,
        "🎉 " + str(sorteio.get("titulo") or "SORTEIO NÊMESIS"),
        (
            f"{sorteio.get('descricao') or 'Participe e concorra ao prêmio.'}\n\n"
            f"**Prêmio:** {sorteio.get('premio', 'Não informado')}\n"
            + (f"**Requisitos (opcionais):** {sorteio.get('requisitos')}\n" if sorteio.get("requisitos") else "")
            + f"**Vencedores:** {int(sorteio.get('vencedores', 1))}\n"
            f"**Encerra:** {timestamp_discord(float(sorteio.get('fim') or 0), 'F')} "
            f"({timestamp_discord(float(sorteio.get('fim') or 0), 'R')})\n"
            f"**Participantes:** {quantidade}\n\n"
            "Cada membro pode participar uma única vez."
        ),
        rodape=f"NÊMESIS • Sorteios • ID:{sorteio['id']}",
        imagem=sorteio.get("banner"),
    )


class ModalCriarSorteio(discord.ui.Modal, title="Criar sorteio"):
    titulo = discord.ui.TextInput(label="Nome do sorteio", placeholder="Ex.: Sorteio Diário", default="Sorteio NÊMESIS", max_length=100)
    premio = discord.ui.TextInput(label="Prêmio", placeholder="Ex.: recompensa, item ou benefício", max_length=300)
    descricao = discord.ui.TextInput(label="Descrição", placeholder="Informações e instruções para participar", style=discord.TextStyle.paragraph, required=False, max_length=900)
    duracao = discord.ui.TextInput(label="Duração em minutos", placeholder="Ex.: 1440 para 24 horas", max_length=6)
    vencedores = discord.ui.TextInput(label="Quantidade de vencedores", default="1", max_length=2)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança da NÊMESIS.", ephemeral=True)
            return
        premio = str(self.premio.value).strip()
        try:
            minutos = int(self.duracao.value)
            vencedores = int(self.vencedores.value)
        except (TypeError, ValueError):
            await interaction.response.send_message("Informe duração e quantidade de vencedores usando números inteiros.", ephemeral=True)
            return
        if not premio or minutos < 1 or minutos > 43200 or vencedores < 1 or vencedores > 100:
            await interaction.response.send_message("Prêmio obrigatório; duração de 1 a 43.200 minutos; vencedores de 1 a 100.", ephemeral=True)
            return
        agora = time.time()
        sorteio = {
            "id": uuid.uuid4().hex[:8],
            "guild_id": interaction.guild.id,
            "canal_id": None,
            "mensagem_id": None,
            "titulo": str(self.titulo.value or "Sorteio NÊMESIS").strip(),
            "premio": premio,
            "descricao": str(self.descricao.value or "").strip(),
            "banner": None,
            "fim": agora + minutos * 60,
            "vencedores": vencedores,
            "participantes": [],
            "chances_por_usuario": {},
            "painel_avancado": True,
            "vencedores_ids": [],
            "encerrado": False,
            "rascunho": True,
            "criado_por_id": interaction.user.id,
            "criado_em": agora,
            "atualizado_em": agora,
        }
        await _salvar_item(sorteio)
        await interaction.response.send_message(
            view=_card_com_view(
                ConfigurarSorteioView(self.cog, sorteio["id"]),
                "𓂀 RASCUNHO CRIADO",
                (
                    f"O sorteio **{sorteio['id']}** foi criado e está salvo como rascunho.\n\n"
                    "Ajuste a apresentação, defina uma imagem se desejar e publique quando estiver pronto."
                ),
                rodape="NÊMESIS • Central de Sorteios",
            ),
            ephemeral=True,
        )


class ModalRequisitosSorteio(discord.ui.Modal, title="Requisitos opcionais"):
    requisitos = discord.ui.TextInput(
        label="Requisitos para participar (opcional)",
        placeholder="Ex.: estar no servidor e ler as regras do sorteio",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=900,
    )

    def __init__(self, cog, sorteio_id):
        super().__init__()
        self.cog = cog
        self.sorteio_id = sorteio_id

    async def on_submit(self, interaction):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        sorteio = await self.cog.obter(self.sorteio_id)
        if not sorteio or not sorteio.get("rascunho"):
            await interaction.response.send_message("Este rascunho não está mais disponível.", ephemeral=True)
            return
        sorteio["requisitos"] = str(self.requisitos.value or "").strip()
        await _salvar_item(sorteio)
        resposta = "Requisitos opcionais salvos." if sorteio["requisitos"] else "Requisitos removidos. A participação permanece livre."
        await interaction.response.send_message(resposta, ephemeral=True)


class ModalBannerSorteio(discord.ui.Modal, title="Imagem do sorteio"):
    url = discord.ui.TextInput(label="URL da imagem", placeholder="https://...", max_length=400)

    def __init__(self, cog, sorteio_id):
        super().__init__()
        self.cog = cog
        self.sorteio_id = sorteio_id

    async def on_submit(self, interaction):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        endereco = str(self.url.value or "").strip()
        if not endereco.startswith(("https://", "http://")):
            await interaction.response.send_message("Informe uma URL http:// ou https:// válida.", ephemeral=True)
            return
        sorteio = await self.cog.obter(self.sorteio_id)
        if not sorteio or not sorteio.get("rascunho"):
            await interaction.response.send_message("Este rascunho não está mais disponível.", ephemeral=True)
            return
        sorteio["banner"] = endereco
        await _salvar_item(sorteio)
        await interaction.response.send_message("Imagem do sorteio configurada.", ephemeral=True)

class ConfigurarSorteioView(discord.ui.View):
    def __init__(self, cog, sorteio_id):
        super().__init__(timeout=900)
        self.cog = cog
        self.sorteio_id = sorteio_id

    @discord.ui.button(label="Definir imagem", style=discord.ButtonStyle.secondary, emoji="🖼️")
    async def imagem(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalBannerSorteio(self.cog, self.sorteio_id))
    @discord.ui.button(label="Requisitos opcionais", style=discord.ButtonStyle.primary, emoji="📌")
    async def definir_requisitos(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        sorteio = await self.cog.obter(self.sorteio_id)
        if not sorteio or not sorteio.get("rascunho"):
            await interaction.response.send_message("Este rascunho não está mais disponível.", ephemeral=True)
            return
        modal = ModalRequisitosSorteio(self.cog, self.sorteio_id)
        modal.requisitos.default = str(sorteio.get("requisitos") or "")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Publicar sorteio", style=discord.ButtonStyle.success, emoji="🎉")
    async def publicar(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        sorteio = await self.cog.obter(self.sorteio_id)
        if not sorteio or not sorteio.get("rascunho"):
            await interaction.response.send_message("Este rascunho não está mais disponível.", ephemeral=True)
            return
        canais = _canal_oficial_sorteios(interaction.guild)
        if len(canais) != 1:
            await interaction.response.send_message("Não encontrei um único canal oficial chamado #Sorteios.", ephemeral=True)
            return
        canal = canais[0]
        try:
            mensagem = await canal.send(view=_card_sorteio(sorteio, len(sorteio.get("participantes", [])), ViewSorteioPublico()))
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("Não consegui publicar no canal #Sorteios. Verifique minhas permissões.", ephemeral=True)
            return
        sorteio["canal_id"] = canal.id
        sorteio["mensagem_id"] = mensagem.id
        sorteio["lembrete_proximo_em"] = time.time() + 7200
        sorteio["rascunho"] = False
        await _salvar_item(sorteio)
        await self.cog.registrar_view_publica(sorteio)
        await interaction.response.send_message(f"Sorteio publicado em {canal.mention}: {mensagem.jump_url}", ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancelar rascunho", style=discord.ButtonStyle.danger, emoji="✖️")
    async def cancelar(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        async with _SORTEIOS_LOCK:
            todos = await _carregar_todos()
            todos.pop(self.sorteio_id, None)
            await salvar(ARQUIVO, todos)
        await interaction.response.send_message("Rascunho cancelado.", ephemeral=True)
        self.stop()


class ViewSorteioPublico(discord.ui.View):
    def __init__(self, encerrado=False):
        super().__init__(timeout=None)
        if encerrado:
            for item in self.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.success, custom_id="nemesis_sorteio:participar")
    async def participar(self, interaction: discord.Interaction, button):
        cog = interaction.client.get_cog("SorteiosPainel")
        if cog is None:
            await interaction.response.send_message("O sistema de sorteios está temporariamente indisponível.", ephemeral=True)
            return
        await cog.participar(interaction)

    @discord.ui.button(label="🎟️ Minhas chances", style=discord.ButtonStyle.secondary, custom_id="nemesis_sorteio:minhas_chances")
    async def minhas_chances(self, interaction: discord.Interaction, button):
        cog = interaction.client.get_cog("SorteiosPainel")
        if cog is None:
            await interaction.response.send_message("O sistema de sorteios está temporariamente indisponível.", ephemeral=True)
            return
        await cog.mostrar_chances(interaction)


class PainelAdministrativoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Criar sorteio", style=discord.ButtonStyle.success, emoji="🎉", custom_id="nemesis_sorteios:criar")
    async def criar(self, interaction: discord.Interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("A criação de sorteios é restrita à liderança da NÊMESIS.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalCriarSorteio(interaction.client.get_cog("SorteiosPainel")))

    @discord.ui.button(label="Sorteios ativos", style=discord.ButtonStyle.secondary, emoji="📋", custom_id="nemesis_sorteios:ativos")
    async def ativos(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        cog = interaction.client.get_cog("SorteiosPainel")
        await cog.mostrar_ativos(interaction)


class SeletorSorteioAtivo(discord.ui.Select):
    def __init__(self, cog, sorteios):
        opcoes = [
            discord.SelectOption(
                label=str(item.get("titulo") or item.get("premio") or "Sorteio")[:100],
                value=str(item["id"]),
                description=(str(len(item.get("participantes", []))) + " participantes · " + timestamp_discord(float(item.get("fim") or 0), "R"))[:100],
            )
            for item in sorteios[:25]
        ]
        super().__init__(placeholder="Selecione um sorteio", min_values=1, max_values=1, options=opcoes)
        self.cog = cog

    async def callback(self, interaction):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        await interaction.response.send_message(
            view=_card_com_view(
                ConfirmarEncerramentoSorteioView(self.cog, self.values[0]),
                "CONFIRMAR ENCERRAMENTO",
                "Confirma o encerramento antecipado deste sorteio? A ação selecionará os vencedores.",
            ),
            ephemeral=True,
        )


class SeletorSorteioAtivoView(discord.ui.View):
    def __init__(self, cog, sorteios):
        super().__init__(timeout=180)
        self.add_item(SeletorSorteioAtivo(cog, sorteios))


class ConfirmarEncerramentoSorteioView(discord.ui.View):
    def __init__(self, cog, sorteio_id):
        super().__init__(timeout=90)
        self.cog = cog
        self.sorteio_id = sorteio_id

    @discord.ui.button(label="Confirmar encerramento", style=discord.ButtonStyle.danger, emoji="⏹️")
    async def confirmar(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        sorteio = await self.cog.obter(self.sorteio_id)
        if not sorteio or sorteio.get("encerrado") or sorteio.get("rascunho"):
            await interaction.response.send_message("Este sorteio não está mais ativo.", ephemeral=True)
            return
        if str(sorteio.get("guild_id")) != str(interaction.guild.id):
            await interaction.response.send_message("Este sorteio pertence a outro servidor.", ephemeral=True)
            return
        cog_sorteios = interaction.client.get_cog("Sorteios")
        if cog_sorteios is None:
            await interaction.response.send_message("O mecanismo de encerramento está indisponível.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await cog_sorteios.sortear_vencedores(sorteio)
        await interaction.followup.send("Encerramento solicitado. Confira o canal oficial para confirmar a publicação do resultado.", ephemeral=True)
        self.stop()


class SorteiosPainel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._painel_lock = False
        bot.add_view(_card_com_view(
            PainelAdministrativoView(), "🎁 CENTRAL DE SORTEIOS",
            "Área administrativa para criar e configurar sorteios oficiais da NÊMESIS. A criação e as configurações são restritas à liderança.",
            rodape=MARCADOR_PAINEL,
        ))
        bot.add_view(_card_com_view(
            ViewSorteioPublico(), "SORTEIO NÊMESIS",
            "Participe do sorteio e consulte suas chances usando os controles abaixo.",
        ))

    @tasks.loop(seconds=60)
    async def republicar_sorteios_ativos(self):
        """Envia lembretes privados em lotes para todos os membros dos sorteios ativos."""
        agora = time.time()
        try:
            todos = await _carregar_todos()
        except Exception:
            logger.exception("Falha ao carregar sorteios para lembretes periódicos.")
            return

        for sorteio in list(todos.values()):
            if not isinstance(sorteio, dict) or sorteio.get("rascunho") or sorteio.get("encerrado"):
                continue
            try:
                fim = float(sorteio.get("fim") or 0)
                proximo = float(sorteio.get("lembrete_proximo_em") or 0)
                canal_id = int(sorteio.get("canal_id") or 0)
                mensagem_id = int(sorteio.get("mensagem_id") or 0)
            except (TypeError, ValueError):
                continue
            if agora >= fim or not canal_id or not mensagem_id:
                continue

            guild = self.bot.get_guild(int(sorteio.get("guild_id") or GUILD_NEMESIS_ID))
            if guild is None:
                continue

            # Inicia uma nova rodada privada a cada 2 horas.
            if agora >= proximo and not sorteio.get("lembrete_fila_ids"):
                canal = guild.get_channel(canal_id)
                if canal is None:
                    try:
                        canal = await self.bot.fetch_channel(canal_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        logger.warning("Canal indisponível para lembrete do sorteio %s.", sorteio.get("id"))
                        continue
                try:
                    original = await canal.fetch_message(mensagem_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    logger.warning("Mensagem original indisponível para o sorteio %s.", sorteio.get("id"))
                    continue
                membros = [m.id for m in guild.members if not m.bot]
                sorteio["lembrete_fila_ids"] = membros
                sorteio["lembrete_fila_indice"] = 0
                sorteio["lembrete_jump_url"] = original.jump_url
                await _salvar_item(sorteio)

            fila = sorteio.get("lembrete_fila_ids") or []
            indice = int(sorteio.get("lembrete_fila_indice") or 0)
            if not fila:
                # Sem membros disponíveis: tenta novamente em 2 horas.
                if agora >= proximo:
                    sorteio["lembrete_proximo_em"] = agora + 7200
                    await _salvar_item(sorteio)
                continue

            fim_lote = min(indice + 10, len(fila))
            link = str(sorteio.get("lembrete_jump_url") or f"https://discord.com/channels/{guild.id}/{canal_id}/{mensagem_id}")
            mensagem = (
                f"🔔 **NÊMESIS • Lembrete de sorteio**\n\n"
                f"**{str(sorteio.get('titulo') or 'Sorteio NÊMESIS')[:100]}** ainda está recebendo participantes.\n"
                f"Confira o prêmio e as informações no canal oficial: {link}"
            )
            for user_id in fila[indice:fim_lote]:
                try:
                    membro = guild.get_member(int(user_id))
                    if membro is None:
                        membro = await guild.fetch_member(int(user_id))
                    if not membro.bot:
                        await membro.send(mensagem, allowed_mentions=discord.AllowedMentions.none())
                except (discord.NotFound, discord.Forbidden):
                    # DMs fechadas ou usuário indisponível: segue para o próximo.
                    pass
                except discord.HTTPException:
                    logger.warning("Falha temporária ao enviar DM do sorteio %s para %s.", sorteio.get("id"), user_id)
                await __import__("asyncio").sleep(1.0)

            sorteio["lembrete_fila_indice"] = fim_lote
            if fim_lote >= len(fila):
                sorteio["lembrete_fila_ids"] = []
                sorteio["lembrete_fila_indice"] = 0
                sorteio["lembrete_jump_url"] = None
                sorteio["lembrete_proximo_em"] = time.time() + 7200
                logger.info("Rodada de DMs do sorteio %s concluída para %s membros.", sorteio.get("id"), len(fila))
            await _salvar_item(sorteio)

    @republicar_sorteios_ativos.before_loop
    async def antes_republicar_sorteios(self):
        await self.bot.wait_until_ready()

    async def obter(self, sorteio_id):
        todos = await _carregar_todos()
        item = todos.get(str(sorteio_id))
        return item if isinstance(item, dict) else None

    async def registrar_view_publica(self, sorteio):
        try:
            mensagem_id = int(sorteio["mensagem_id"])
            view = _card_sorteio(
                sorteio, len(sorteio.get("participantes", [])), ViewSorteioPublico()
            )
            self.bot.add_view(view, message_id=mensagem_id)
            guild = self.bot.get_guild(int(sorteio.get("guild_id") or GUILD_NEMESIS_ID))
            canal = guild.get_channel(int(sorteio.get("canal_id") or 0)) if guild else None
            if canal is not None:
                mensagem = await canal.fetch_message(mensagem_id)
                if not _mensagem_tem_cartao_sorteio(mensagem, sorteio.get("id", "")):
                    await mensagem.edit(content=None, embeds=[], attachments=[])
                await mensagem.edit(view=view)
        except (KeyError, TypeError, ValueError, discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.exception("Não foi possível sincronizar o cartão persistente do sorteio %s.", sorteio.get("id"))

    async def participar(self, interaction):
        if not interaction.guild or interaction.guild.id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este sorteio pertence à NÊMESIS.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        sorteio = await self._por_mensagem(interaction.message.id)
        if not sorteio or sorteio.get("rascunho"):
            await interaction.followup.send("Não encontrei este sorteio.", ephemeral=True)
            return
        if sorteio.get("encerrado") or time.time() >= float(sorteio.get("fim") or 0):
            await interaction.followup.send("O período de participação deste sorteio terminou.", ephemeral=True)
            return
        membro = interaction.user
        chances = 1
        async with _SORTEIOS_LOCK:
            todos = await _carregar_todos()
            atual = todos.get(str(sorteio["id"]))
            if not isinstance(atual, dict) or atual.get("encerrado") or time.time() >= float(atual.get("fim") or 0):
                await interaction.followup.send("Este sorteio não está mais recebendo inscrições.", ephemeral=True)
                return
            participantes = atual.setdefault("participantes", [])
            if str(membro.id) in {str(uid) for uid in participantes}:
                existentes = atual.get("chances_por_usuario") or {}
                total = int(existentes.get(str(membro.id), chances) or chances)
                await interaction.followup.send(f"Você já está participando. Suas chances registradas: **{total}**.", ephemeral=True)
                return
            participantes.append(membro.id)
            chances_map = atual.setdefault("chances_por_usuario", {})
            chances_map[str(membro.id)] = chances
            atual["atualizado_em"] = time.time()
            todos[str(atual["id"])] = atual
            await salvar(ARQUIVO, todos)
        await interaction.followup.send(f"Você está participando! Suas chances neste sorteio: **{chances}**.", ephemeral=True)
        try:
            await interaction.message.edit(
                view=_card_sorteio(
                    atual, len(atual.get("participantes", [])), ViewSorteioPublico()
                ),
            )
        except discord.HTTPException:
            logger.warning("Inscrição registrada, mas não foi possível atualizar a mensagem do sorteio %s.", sorteio.get("id"))

    async def mostrar_chances(self, interaction):
        if not interaction.guild or interaction.guild.id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Este sorteio pertence à NÊMESIS.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        sorteio = await self._por_mensagem(interaction.message.id)
        if not sorteio:
            await interaction.followup.send("Não encontrei este sorteio.", ephemeral=True)
            return
        registradas = sorteio.get("chances_por_usuario") or {}
        total = registradas.get(str(interaction.user.id))
        if total is None:
            # A participação é aberta: cargos e requisitos não alteram as chances.
            atuais = 1
            await interaction.followup.send(
                f"Você ainda não entrou. Se participar agora, terá **{atuais}** chance.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(f"Você está inscrito neste sorteio com **{int(total)}** chance(s).", ephemeral=True)

    async def mostrar_ativos(self, interaction):
        todos = await _carregar_todos()
        ativos = [
            item for item in todos.values()
            if isinstance(item, dict)
            and str(item.get("guild_id")) == str(interaction.guild.id)
            and not item.get("encerrado")
            and not item.get("rascunho")
        ]
        ativos.sort(key=lambda item: float(item.get("fim") or 0))
        if not ativos:
            await interaction.response.send_message("Não há sorteios ativos no momento.", ephemeral=True)
            return
        embed = criar_embed(title="📋 SORTEIOS EM ANDAMENTO", description="Selecione um sorteio para encerrar antecipadamente. A ação exige confirmação.", color=COR_PRIMARIA)
        await interaction.response.send_message(
            view=_card_com_view(
                SeletorSorteioAtivoView(self, ativos),
                "📋 SORTEIOS EM ANDAMENTO",
                "Selecione um sorteio para encerrar antecipadamente. A ação exige confirmação.",
            ),
            ephemeral=True,
        )

    async def _por_mensagem(self, mensagem_id):
        todos = await _carregar_todos()
        for item in todos.values():
            if isinstance(item, dict) and str(item.get("mensagem_id")) == str(mensagem_id):
                return item
        return None

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.republicar_sorteios_ativos.is_running():
            self.republicar_sorteios_ativos.start()
        if self._painel_lock:
            return
        self._painel_lock = True
        try:
            guild = self.bot.get_guild(GUILD_NEMESIS_ID)
            if guild is None:
                return
            canais = _canal_oficial_sorteios(guild)
            if len(canais) != 1:
                logger.warning("Painel administrativo de sorteios não sincronizado: canal oficial ausente ou ambíguo (candidatos=%s).", [c.name for c in guild.text_channels if "sorteio" in unicodedata.normalize("NFKC", c.name).casefold()])
                return
            canal = canais[0]
            painel = None
            async for mensagem in canal.history(limit=100):
                if mensagem.author == self.bot.user and (
                    any(MARCADOR_PAINEL in (e.footer.text or "") for e in mensagem.embeds if e.footer)
                    or _componentes_contem_marcador(mensagem.components, MARCADOR_PAINEL)
                ):
                    painel = mensagem
                    break
            embed = criar_embed(title="🎁 CENTRAL DE SORTEIOS", description="Área administrativa para criar e configurar sorteios oficiais da NÊMESIS. A criação e as configurações são restritas à liderança.", color=COR_PRIMARIA)
            embed.set_footer(text=MARCADOR_PAINEL)
            view = _card_com_view(
                PainelAdministrativoView(), "🎁 CENTRAL DE SORTEIOS",
                "Área administrativa para criar e configurar sorteios oficiais da NÊMESIS. A criação e as configurações são restritas à liderança.",
                rodape=MARCADOR_PAINEL,
            )
            if painel:
                if not _componentes_contem_marcador(painel.components, MARCADOR_PAINEL):
                    await painel.edit(content=None, embeds=[], attachments=[])
                    await painel.edit(view=view)
            else:
                await canal.send(view=view)
            todos = await _carregar_todos()
            for sorteio in todos.values():
                if isinstance(sorteio, dict) and sorteio.get("mensagem_id") and not sorteio.get("encerrado") and not sorteio.get("rascunho"):
                    await self.registrar_view_publica(sorteio)
            logger.info("Central administrativa de sorteios sincronizada no canal %s.", canal.id)
        except Exception:
            logger.exception("Falha ao sincronizar a central administrativa de sorteios.")
        finally:
            self._painel_lock = False


async def setup(bot):
    await bot.add_cog(SorteiosPainel(bot))
