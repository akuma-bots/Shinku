import time
import uuid
import logging
import re

import discord
from discord.ext import commands

from cogs.sorteios import ARQUIVO, _SORTEIOS_LOCK, timestamp_discord
from utils.apresentacao import criar_embed, COR_PRIMARIA, COR_SUCESSO, COR_ERRO
from utils.guild_config import GUILD_NEMESIS_ID, membro_tem_lideranca
from utils.storage import carregar, salvar

logger = logging.getLogger(__name__)
MARCADOR_PAINEL = "NEMESIS-PAINEL-SORTEIOS"


def _canal_oficial_sorteios(guild):
    exatos = []
    candidatos = []
    for canal in guild.text_channels:
        tokens = re.findall(r"[a-z0-9]+", canal.name.casefold())
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
    minimo = sorteio.get("cargo_minimo_id")
    if minimo:
        descricao += f"\n**Requisito mínimo:** <@&{int(minimo)}>"
    bonus = sorteio.get("bonus_cargos") or {}
    if bonus:
        linhas = [
            f"<@&{int(role_id)}> — +{max(1, int(chances))} chance(s)"
            for role_id, chances in bonus.items()
        ]
        descricao += "\n\n**Chances adicionais**\n" + "\n".join(linhas)
    embed = criar_embed(title="🎉 " + str(sorteio.get("titulo") or "SORTEIO NÊMESIS"), description=descricao, color=COR_PRIMARIA)
    if sorteio.get("banner"):
        embed.set_image(url=sorteio["banner"])
    embed.set_footer(text=f"NÊMESIS • Sorteios • ID:{sorteio['id']}")
    return embed


def _calcular_chances(membro, sorteio):
    cargos = {cargo.id for cargo in membro.roles}
    minimo = sorteio.get("cargo_minimo_id")
    if minimo and int(minimo) not in cargos:
        return None
    total = 1
    bonus = sorteio.get("bonus_cargos") or {}
    if isinstance(bonus, dict):
        for role_id, quantidade in bonus.items():
            try:
                if int(role_id) in cargos:
                    total += max(0, min(100, int(quantidade)))
            except (TypeError, ValueError):
                continue
    return max(1, min(1000, total))


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
            "cargo_minimo_id": None,
            "painel_avancado": True,
            "bonus_cargos": {},
            "vencedores_ids": [],
            "encerrado": False,
            "rascunho": True,
            "criado_por_id": interaction.user.id,
            "criado_em": agora,
            "atualizado_em": agora,
        }
        await _salvar_item(sorteio)
        await interaction.response.send_message(
            f"Rascunho **{sorteio['id']}** criado. Configure o requisito e as chances extras antes de publicar.",
            view=ConfigurarSorteioView(self.cog, sorteio["id"]),
            ephemeral=True,
        )


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

class SeletorCargoMinimo(discord.ui.RoleSelect):
    def __init__(self, cog, sorteio_id):
        super().__init__(placeholder="Selecione o cargo obrigatório", min_values=1, max_values=1)
        self.cog = cog
        self.sorteio_id = sorteio_id

    async def callback(self, interaction: discord.Interaction):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        sorteio = await self.cog.obter(self.sorteio_id)
        if not sorteio or not sorteio.get("rascunho"):
            await interaction.response.send_message("Este rascunho não está mais disponível.", ephemeral=True)
            return
        sorteio["cargo_minimo_id"] = self.values[0].id
        await _salvar_item(sorteio)
        await interaction.response.send_message(f"Requisito mínimo definido: {self.values[0].mention}.", ephemeral=True)


class SeletorCargoBonus(discord.ui.RoleSelect):
    def __init__(self, cog, sorteio_id):
        super().__init__(placeholder="Selecione o cargo que dará chances extras", min_values=1, max_values=1)
        self.cog = cog
        self.sorteio_id = sorteio_id

    async def callback(self, interaction: discord.Interaction):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalDefinirBonus(self.cog, self.sorteio_id, self.values[0].id, self.values[0].name))


class ModalDefinirBonus(discord.ui.Modal, title="Configurar chances extras"):
    quantidade = discord.ui.TextInput(label="Chances adicionais", placeholder="Ex.: 1", default="1", max_length=3)

    def __init__(self, cog, sorteio_id, role_id, role_name):
        super().__init__()
        self.cog = cog
        self.sorteio_id = sorteio_id
        self.role_id = role_id
        self.role_name = role_name

    async def on_submit(self, interaction: discord.Interaction):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        try:
            quantidade = int(self.quantidade.value)
        except (TypeError, ValueError):
            quantidade = 0
        if quantidade < 1 or quantidade > 100:
            await interaction.response.send_message("Informe entre 1 e 100 chances adicionais.", ephemeral=True)
            return
        sorteio = await self.cog.obter(self.sorteio_id)
        if not sorteio or not sorteio.get("rascunho"):
            await interaction.response.send_message("Este rascunho não está mais disponível.", ephemeral=True)
            return
        bonus = sorteio.setdefault("bonus_cargos", {})
        bonus[str(self.role_id)] = quantidade
        await _salvar_item(sorteio)
        await interaction.response.send_message(f"Cargo **{self.role_name}** configurado com **+{quantidade}** chance(s).", ephemeral=True)


class EscolherCargoMinimoView(discord.ui.View):
    def __init__(self, cog, sorteio_id):
        super().__init__(timeout=180)
        self.add_item(SeletorCargoMinimo(cog, sorteio_id))


class EscolherCargoBonusView(discord.ui.View):
    def __init__(self, cog, sorteio_id):
        super().__init__(timeout=180)
        self.add_item(SeletorCargoBonus(cog, sorteio_id))


class ConfigurarSorteioView(discord.ui.View):
    def __init__(self, cog, sorteio_id):
        super().__init__(timeout=900)
        self.cog = cog
        self.sorteio_id = sorteio_id

    @discord.ui.button(label="Definir requisito mínimo", style=discord.ButtonStyle.secondary, emoji="🔒")
    async def requisito(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        await interaction.response.send_message("Escolha o cargo obrigatório:", view=EscolherCargoMinimoView(self.cog, self.sorteio_id), ephemeral=True)

    @discord.ui.button(label="Adicionar cargo com bônus", style=discord.ButtonStyle.secondary, emoji="✨")
    async def bonus(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        await interaction.response.send_message("Escolha o cargo que receberá chances extras:", view=EscolherCargoBonusView(self.cog, self.sorteio_id), ephemeral=True)

    @discord.ui.button(label="Definir imagem", style=discord.ButtonStyle.secondary, emoji="🖼️")
    async def imagem(self, interaction, button):
        if not _eh_lideranca(interaction):
            await interaction.response.send_message("Acesso restrito à liderança.", ephemeral=True)
            return
        await interaction.response.send_modal(ModalBannerSorteio(self.cog, self.sorteio_id))
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
            mensagem = await canal.send(embed=_embed_sorteio(sorteio), view=ViewSorteioPublico())
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("Não consegui publicar no canal #Sorteios. Verifique minhas permissões.", ephemeral=True)
            return
        sorteio["canal_id"] = canal.id
        sorteio["mensagem_id"] = mensagem.id
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
            "Confirma o encerramento antecipado deste sorteio?",
            view=ConfirmarEncerramentoSorteioView(self.cog, self.values[0]),
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
        bot.add_view(PainelAdministrativoView())
        bot.add_view(ViewSorteioPublico())

    async def obter(self, sorteio_id):
        todos = await _carregar_todos()
        item = todos.get(str(sorteio_id))
        return item if isinstance(item, dict) else None

    async def registrar_view_publica(self, sorteio):
        try:
            self.bot.add_view(ViewSorteioPublico(), message_id=int(sorteio["mensagem_id"]))
        except (KeyError, TypeError, ValueError, discord.HTTPException):
            logger.exception("Não foi possível registrar a view persistente do sorteio %s.", sorteio.get("id"))

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
        chances = _calcular_chances(membro, sorteio)
        if chances is None:
            role_id = sorteio.get("cargo_minimo_id")
            cargo = interaction.guild.get_role(int(role_id)) if role_id else None
            await interaction.followup.send(f"Você ainda não pode participar. É necessário possuir {cargo.mention if cargo else 'o cargo mínimo configurado'}.", ephemeral=True)
            return
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
            await interaction.message.edit(embed=_embed_sorteio(atual, len(atual.get("participantes", []))), view=ViewSorteioPublico())
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
            atuais = _calcular_chances(interaction.user, sorteio)
            if atuais is None:
                await interaction.followup.send("Você ainda não atende ao requisito mínimo deste sorteio.", ephemeral=True)
                return
            await interaction.followup.send(f"Você ainda não entrou. Se participar agora, terá **{atuais}** chance(s).", ephemeral=True)
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
        await interaction.response.send_message(embed=embed, view=SeletorSorteioAtivoView(self, ativos), ephemeral=True)

    async def _por_mensagem(self, mensagem_id):
        todos = await _carregar_todos()
        for item in todos.values():
            if isinstance(item, dict) and str(item.get("mensagem_id")) == str(mensagem_id):
                return item
        return None

    @commands.Cog.listener()
    async def on_ready(self):
        if self._painel_lock:
            return
        self._painel_lock = True
        try:
            guild = self.bot.get_guild(GUILD_NEMESIS_ID)
            if guild is None:
                return
            canais = _canal_oficial_sorteios(guild)
            if len(canais) != 1:
                logger.warning("Painel administrativo de sorteios não sincronizado: canal oficial ausente ou ambíguo (candidatos=%s).", [c.name for c in guild.text_channels if "sorteio" in c.name.casefold()])
                return
            canal = canais[0]
            painel = None
            async for mensagem in canal.history(limit=100):
                if mensagem.author == self.bot.user and any(MARCADOR_PAINEL in (e.footer.text or "") for e in mensagem.embeds if e.footer):
                    painel = mensagem
                    break
            embed = criar_embed(title="🎁 CENTRAL DE SORTEIOS", description="Área administrativa para criar e configurar sorteios oficiais da NÊMESIS. A criação e as configurações são restritas à liderança.", color=COR_PRIMARIA)
            embed.set_footer(text=MARCADOR_PAINEL)
            if painel:
                await painel.edit(embed=embed, view=PainelAdministrativoView())
            else:
                await canal.send(embed=embed, view=PainelAdministrativoView())
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
