from utils.apresentacao import criar_embed
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands
from utils.guia_servidores import (
    GuiaServidoresView,
    GuiaCanaisSelect,
    CARGO_VISITANTES_ID,
    NOME_CARGO_VISITANTES,
    TAG_ORG_NEMESIS,
    publicar_guia_servidor,
)
from utils.storage import carregar
from utils import monitoramento_membros
from utils.registro_global import CANAL_REGISTRO_GLOBAL_ID, CATEGORIAS, garantir_topicos, registrar as registrar_global
from utils.guild_config import membro_tem_lideranca
from utils.historico_membros import (
    ABAS, construir_dossie, _embed_geral, _embed_missoes,
    _embed_competitivo, _embed_moderacao, _embed_registros,
    _timeout_membro,
)


logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
CANAL_ENTRADAS_ID = 1563995880623841331


def _formatar_linhas_registro(linhas, limite: int = 3800) -> str:
    """Monta texto multilinha previsível e respeita o limite seguro do embed."""
    limite_seguro = max(1, int(limite))
    return "\n".join(str(linha) for linha in linhas if linha is not None)[:limite_seguro]


def _usuario_pode_consultar_historico(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild_id == GUILD_NEMESIS_ID and membro_tem_lideranca(interaction.user))


def _layout_boas_vindas(embed: discord.Embed) -> discord.ui.LayoutView:
    """Mensagem de entrada com a navegação do servidor dentro do cartão."""
    partes = [f"## {embed.title or 'NÊMESIS — BOAS-VINDAS'}"]
    if embed.description:
        partes.append(embed.description)
    for campo in embed.fields:
        partes.append(f"### {campo.name}\n{campo.value}")
    if embed.footer and embed.footer.text:
        partes.append(f"-# {embed.footer.text}")
    layout = discord.ui.LayoutView(timeout=None)
    layout.add_item(discord.ui.Container(
        discord.ui.TextDisplay("\n\n".join(partes)),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("### ◈ PRIMEIROS PASSOS"),
        discord.ui.ActionRow(GuiaCanaisSelect()),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# Nêmesis Systeam • Integração de novos integrantes"),
        accent_colour=0x9F1239,
    ))
    return layout



MARCADOR_ARQUIVO_MEMBROS = "NÊMESIS • ARQUIVO DE MEMBROS • V2"


def _componentes_contem_marcador(componentes, marcador: str) -> bool:
    pendentes = list(componentes or [])
    while pendentes:
        componente = pendentes.pop()
        if marcador.casefold() in str(getattr(componente, "content", "") or "").casefold():
            return True
        pendentes.extend(list(getattr(componente, "children", []) or []))
    return False


def _card_registro(origem: discord.ui.View, embed: discord.Embed | None = None,
                   titulo: str = "CENTRAL DE HISTÓRICO", descricao: str = "Consulta restrita à liderança autorizada."):
    """Mantém seletores e botões de consulta dentro de um cartão Components V2."""
    layout = discord.ui.LayoutView(timeout=origem.timeout)
    partes = [f"## {embed.title if embed and embed.title else titulo}"]
    if embed and embed.description:
        partes.append(embed.description)
    elif descricao:
        partes.append(descricao)
    if embed:
        for campo in embed.fields:
            partes.append(f"**{campo.name}**\n{campo.value}")
        if embed.footer and embed.footer.text:
            partes.append(f"-# {embed.footer.text}")
    componentes = [
        discord.ui.TextDisplay("\n\n".join(partes)[:3900]),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
    ]
    linhas = {}
    for item in origem.children:
        if isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
        elif isinstance(item, discord.ui.UserSelect):
            novo = discord.ui.UserSelect(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, custom_id=item.custom_id,
                disabled=item.disabled, row=item.row,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await original.callback(interaction)
            novo.callback = callback
        elif isinstance(item, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, options=list(item.options),
                custom_id=item.custom_id, disabled=item.disabled, row=item.row,
            )
            async def callback(interaction, original=item, clone=novo):
                original._values = clone._values
                await original.callback(interaction)
            novo.callback = callback
        else:
            continue
        linhas.setdefault(item.row or 0, []).append(novo)
    for _, itens in sorted(linhas.items()):
        for inicio in range(0, len(itens), 5):
            componentes.append(discord.ui.ActionRow(*itens[inicio:inicio + 5]))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# Nêmesis Systeam • Arquivo e auditoria"),
    ])
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


class DossieMembroRegistroView(discord.ui.View):
    """Navegação privada pelas seções do histórico de um membro."""
    def __init__(self, dossie: dict, owner_id: int):
        super().__init__(timeout=300)
        self.dossie = dossie
        self.owner_id = owner_id
        self.pagina_mensagens = 0
        self.aba_atual = "geral"
        opcoes = [discord.SelectOption(label=label, value=chave, description=descricao[:100], default=(chave == "geral")) for chave, label, descricao in ABAS]
        self.seletor = discord.ui.Select(placeholder="Escolha o que deseja consultar", min_values=1, max_values=1, options=opcoes, custom_id="nemesis:registro:membro:aba")
        self.seletor.callback = self._selecionar_aba
        self.add_item(self.seletor)

    @discord.ui.button(label="Atualizar dados", emoji="🔄", style=discord.ButtonStyle.primary, row=1)
    async def atualizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        try:
            self.dossie = await construir_dossie(self.dossie["guild"], self.dossie["membro"])
            chave = self.aba_atual
            from utils.historico_membros import _embed_mensagens, _embed_atividade
            if chave == "mensagens":
                embed = _embed_mensagens(self.dossie, self.pagina_mensagens)
            elif chave == "atividade":
                embed = _embed_atividade(self.dossie)
            else:
                renderizadores = {
                    "geral": _embed_geral, "missoes": _embed_missoes,
                    "competitivo": _embed_competitivo, "moderacao": _embed_moderacao,
                    "registros": _embed_registros,
                }
                embed = renderizadores.get(chave, _embed_geral)(self.dossie)
            mensagens = self.dossie.get("atividade", {}).get("mensagens", [])
            paginas = max(1, (len(mensagens) + 5) // 6)
            self.pagina_mensagens = min(self.pagina_mensagens, paginas - 1)
            self.anterior.disabled = chave != "mensagens" or self.pagina_mensagens <= 0
            self.proxima.disabled = chave != "mensagens" or self.pagina_mensagens >= paginas - 1
            await interaction.edit_original_response(content=None, embeds=[])
            await interaction.edit_original_response(view=_card_registro(self, embed))
        except Exception:
            logger.exception("Falha ao atualizar dossiê individual.")
            await interaction.edit_original_response(content=None, embed=None, view=_card_registro(self, None, "DADOS INDISPONÍVEIS", "Não foi possível atualizar os dados agora."))

    @discord.ui.button(label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary, row=1, disabled=True)
    async def anterior(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.pagina_mensagens = max(0, self.pagina_mensagens - 1)
        await self._atualizar_mensagens(interaction)

    @discord.ui.button(label="Próxima", emoji="▶️", style=discord.ButtonStyle.secondary, row=1, disabled=True)
    async def proxima(self, interaction: discord.Interaction, button: discord.ui.Button):
        mensagens = self.dossie.get("atividade", {}).get("mensagens", [])
        paginas = max(1, (len(mensagens) + 5) // 6)
        self.pagina_mensagens = min(paginas - 1, self.pagina_mensagens + 1)
        await self._atualizar_mensagens(interaction)

    async def _atualizar_mensagens(self, interaction: discord.Interaction):
        from utils.historico_membros import _embed_mensagens
        mensagens = self.dossie.get("atividade", {}).get("mensagens", [])
        paginas = max(1, (len(mensagens) + 5) // 6)
        self.anterior.disabled = self.pagina_mensagens <= 0
        self.proxima.disabled = self.pagina_mensagens >= paginas - 1
        await interaction.response.edit_message(content=None, embed=None, view=None)
        await interaction.edit_original_response(
            view=_card_registro(self, _embed_mensagens(self.dossie, self.pagina_mensagens))
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id or not _usuario_pode_consultar_historico(interaction):
            await interaction.response.send_message("Acesso restrito à liderança autorizada.", ephemeral=True)
            return False
        return True

    async def _selecionar_aba(self, interaction: discord.Interaction):
        renderizadores = {
            "geral": _embed_geral, "missoes": _embed_missoes,
            "competitivo": _embed_competitivo,
            "moderacao": _embed_moderacao, "mensagens": None,
            "atividade": None, "registros": _embed_registros,
        }
        from utils.historico_membros import _embed_mensagens, _embed_atividade
        chave = (interaction.data or {}).get("values", [self.aba_atual])[0]
        self.aba_atual = chave
        self.pagina_mensagens = 0
        if chave == "mensagens":
            embed = _embed_mensagens(self.dossie, self.pagina_mensagens)
        elif chave == "atividade":
            embed = _embed_atividade(self.dossie)
        else:
            embed = renderizadores.get(chave, _embed_geral)(self.dossie)
        for opcao in self.seletor.options:
            opcao.default = opcao.value == chave
        self.anterior.disabled = chave != "mensagens" or not self.dossie.get("atividade", {}).get("mensagens")
        self.proxima.disabled = chave != "mensagens" or len(self.dossie.get("atividade", {}).get("mensagens", [])) <= 6
        await interaction.response.edit_message(content=None, embed=None, view=None)
        await interaction.edit_original_response(view=_card_registro(self, embed))


class SeletorMembroRegistroView(discord.ui.View):
    """Seletor nativo do Discord: pesquisa membro pelo nome ou escolhe na lista."""
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.seletor = discord.ui.UserSelect(
            placeholder="Pesquise pelo nome ou selecione um membro",
            min_values=1, max_values=1,
            custom_id="nemesis:registro:membro:selecionar",
        )
        self.seletor.callback = self._selecionar_membro
        self.add_item(self.seletor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id or not _usuario_pode_consultar_historico(interaction):
            await interaction.response.send_message("Acesso restrito à liderança autorizada.", ephemeral=True)
            return False
        return True

    async def _selecionar_membro(self, interaction: discord.Interaction):
        if interaction.guild is None or interaction.guild.id != GUILD_NEMESIS_ID:
            await interaction.response.send_message("Esta consulta só está disponível na NÊMESIS.", ephemeral=True)
            return
        selecionado_id = int((interaction.data or {}).get("values", [0])[0])
        membro = interaction.guild.get_member(selecionado_id)
        if not isinstance(membro, discord.Member):
            try:
                membro = await interaction.guild.fetch_member(selecionado_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message("Não consegui localizar esse integrante na NÊMESIS.", ephemeral=True)
                return
        await interaction.response.defer()
        try:
            dossie = await construir_dossie(interaction.guild, membro)
            await interaction.edit_original_response(content=None, embeds=[])
            await interaction.edit_original_response(
                view=_card_registro(
                    DossieMembroRegistroView(dossie, self.owner_id), _embed_geral(dossie)
                )
            )
        except Exception:
            logger.exception("Falha ao montar histórico individual (guild=%s, membro=%s).", interaction.guild.id, membro.id)
            await interaction.edit_original_response(content="Não foi possível carregar o histórico agora. Tente novamente.", embed=None, view=None)


class PainelHistoricoMembrosView(discord.ui.View):
    """Botão persistente anexado ao cabeçalho do tópico Histórico de membros."""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Consultar histórico de membro", emoji="🔎", style=discord.ButtonStyle.primary, custom_id="nemesis:registro:membro:abrir")
    async def abrir_historico(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not _usuario_pode_consultar_historico(interaction):
            await interaction.response.send_message("Acesso restrito à liderança autorizada da NÊMESIS.", ephemeral=True)
            return
        await interaction.response.send_message(
            view=_card_registro(
                SeletorMembroRegistroView(interaction.user.id),
                criar_embed(
                    "📚 CENTRAL DE HISTÓRICO INDIVIDUAL",
                    "Pesquise e selecione um integrante. O dossiê mostra mensagens enviadas/editadas/excluídas e eventos de atividade dos últimos 30 dias. O monitoramento é informado e começa após a implantação.",
                    cor=0x9F2035, rodape="NÊMESIS • REGISTRO GLOBAL • CONSULTA PRIVADA",
                ),
            ),
            ephemeral=True,
        )


class PainelHistoricoMembrosLayoutView(discord.ui.LayoutView):
    """Botão de consulta individual contido no cartão do Arquivo de Membros."""

    def __init__(self):
        super().__init__(timeout=None)
        origem = PainelHistoricoMembrosView()
        original = origem.children[0]
        botao = discord.ui.Button(
            label=original.label, style=original.style,
            custom_id=original.custom_id, emoji=original.emoji,
        )
        botao.callback = original.callback
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                "## 📚 ARQUIVO DE MEMBROS\n"
                "Consulta individual de histórico e atividade, disponível somente à liderança autorizada.\n-# " + MARCADOR_ARQUIVO_MEMBROS
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(botao),
            discord.ui.TextDisplay("-# Nêmesis Systeam • Consulta privada"),
            accent_colour=0x9F1239,
        ))


class Logs(commands.Cog):
    """Registra eventos do servidor (entradas, saídas, edições e exclusões de mensagem)
    no Fórum central de Registro Global da NÊMESIS."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._topicos_prontos = False
        self._guia_publicado = False
        self.bot.add_view(PainelHistoricoMembrosLayoutView())
        self.bot.add_view(GuiaServidoresView())

    async def _atualizar_painel_historico_membros(self, guild: discord.Guild, topicos: dict) -> None:
        thread_id = topicos.get("historico_membros")
        if not thread_id:
            logger.error("Tópico Histórico de membros não foi retornado pelo Registro Global.")
            return
        try:
            thread = guild.get_thread(int(thread_id))
            if thread is None:
                thread = await self.bot.fetch_channel(int(thread_id))
            if not isinstance(thread, discord.Thread) or thread.guild.id != GUILD_NEMESIS_ID:
                logger.error("Destino inválido para o painel de histórico individual: %s.", thread_id)
                return
            if thread.archived or thread.locked:
                await thread.edit(archived=False, locked=False, reason="Atualizar painel de consulta do histórico individual")

            painel = None
            async for mensagem in thread.history(limit=50, oldest_first=True):
                if mensagem.author.id == self.bot.user.id and _componentes_contem_marcador(
                    mensagem.components, MARCADOR_ARQUIVO_MEMBROS
                ):
                    painel = mensagem
                    break
            if painel is not None:
                logger.info("Painel do Arquivo de Membros já está em Components V2 (%s).", painel.id)
                return

            # Não se edita um embed e ativa Components V2 na mesma requisição.
            # Limpa o tópico inicial separadamente e publica um cartão próprio.
            try:
                inicial = await thread.fetch_message(thread.id)
                if inicial.embeds or inicial.content:
                    await inicial.edit(content=None, embeds=[], attachments=[])
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.debug("Mensagem inicial do tópico não precisou ser limpa.", exc_info=True)

            painel = await thread.send(
                view=PainelHistoricoMembrosLayoutView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            logger.info("Painel do Arquivo de Membros publicado em Components V2 (%s).", painel.id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.exception("Não foi possível atualizar o painel de histórico individual.")

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            logger.error("Guild NÊMESIS não está em cache; guia e Registro Global aguardam conexão.")
            return

        if not self._topicos_prontos:
            try:
                topicos = await garantir_topicos(guild)
                self._topicos_prontos = len(topicos) == len(CATEGORIAS)
                await self._atualizar_painel_historico_membros(guild, topicos)
                logger.info("Registro Global pronto: %s/%s tópicos permanentes verificados.", len(topicos), len(CATEGORIAS))
            except Exception:
                logger.exception("Não foi possível provisionar os tópicos do Registro Global.")

        if not self._guia_publicado:
            try:
                self._guia_publicado = await publicar_guia_servidor(self.bot)
            except Exception:
                logger.exception("Não foi possível publicar/atualizar o guia oficial da NÊMESIS.")

    async def _canal_logs(self, guild: discord.Guild):
        """Resolve exclusivamente o Fórum central de registros da NÊMESIS."""
        if guild.id != GUILD_NEMESIS_ID:
            return None
        try:
            canal = guild.get_channel(CANAL_REGISTRO_GLOBAL_ID)
            if canal is None:
                canal = await self.bot.fetch_channel(CANAL_REGISTRO_GLOBAL_ID)
            if not isinstance(canal, discord.ForumChannel):
                logger.error("O Registro Global configurado não é um Fórum (%s).", CANAL_REGISTRO_GLOBAL_ID)
                return None
            return canal
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            logger.exception("Fórum de Registro Global indisponível (guild=%s).", guild.id)
            return None

    async def _enviar_log(self, canal, embed: discord.Embed, view: discord.ui.View | None = None, categoria: str = "membros"):
        """Envia eventos ao tópico fixo; mantém o canal de boas-vindas separado."""
        try:
            if embed.timestamp is None:
                embed.timestamp = datetime.now(timezone.utc)
            if not embed.footer.text:
                embed.set_footer(text="NÊMESIS • Registro Global")
            if isinstance(canal, discord.ForumChannel):
                titulo = embed.title or f"Registro • {categoria.replace('_', ' ').title()}"
                return await registrar_global(
                    canal.guild, categoria, titulo, embed=embed,
                )
            if isinstance(view, discord.ui.LayoutView):
                await canal.send(view=view, allowed_mentions=discord.AllowedMentions.none())
            else:
                await canal.send(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
            return True
        except Exception:
            logger.exception("Falha ao publicar registro (channel=%s).", getattr(canal, "id", "desconhecido"))
            return False

    async def _convidador_do_membro(self, guild_id: int, member_id: int):
        try:
            dados = await carregar("convites_nemesis.json", {})
            servidor = dados.get(str(guild_id), {}) if isinstance(dados, dict) else {}
            historico = servidor.get("_historico", {}) if isinstance(servidor, dict) else {}
            convidador_id = historico.get(str(member_id))
            return int(convidador_id) if convidador_id else None
        except Exception:
            logger.exception("Falha ao consultar convidador (guild=%s, member=%s).", guild_id, member_id)
            return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild.id != 1563995879981981817:
            return
        canal = member.guild.get_channel(CANAL_ENTRADAS_ID)
        if canal is None:
            try:
                canal = await self.bot.fetch_channel(CANAL_ENTRADAS_ID)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                logger.exception(
                    "Canal de boas-vindas indisponível (guild=%s, channel=%s, member=%s).",
                    member.guild.id, CANAL_ENTRADAS_ID, member.id,
                )
                canal = None
        if canal is not None and (
            not isinstance(canal, discord.TextChannel) or canal.guild.id != GUILD_NEMESIS_ID
        ):
            logger.error("Destino de boas-vindas inválido (channel=%s).", CANAL_ENTRADAS_ID)
            canal = None

        # Dá tempo ao rastreador para persistir a atribuição deste evento.
        import asyncio
        await asyncio.sleep(0.8)
        convidador_id = await self._convidador_do_membro(member.guild.id, member.id)
        conta_criada = discord.utils.format_dt(member.created_at, style="R")
        total_membros = member.guild.member_count or 0
        agora = datetime.now(timezone.utc)
        embed = criar_embed(
            title="✦・ 𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 — NOVA PRESENÇA ・✦",
            description=(
                "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                "     **UMA NOVA JORNADA COMEÇA**\n"
                "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                f"⟡・Seja bem-vindo(a), {member.mention}.\n"
                "Você acaba de entrar na **NÊMESIS** — uma organização de competição, evolução "
                "e comunidade. Explore os canais oficiais, conheça as divisões e participe das atividades."
            ),
            color=0xB3132B,
            timestamp=agora,
        )
        if member.guild.icon:
            embed.set_author(name="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  |  CENTRAL DE INTEGRAÇÃO", icon_url=member.guild.icon.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(
            name="◈  IDENTIFICAÇÃO",
            value=f"**Integrante:** {member.mention}\n**Registro:** `{member.id}`\n**Efetivo atual:** `{total_membros:,}`",
            inline=False,
        )
        embed.add_field(
            name="◈  IDENTIDADE DA ORGANIZAÇÃO",
            value=f"**TAG DA ORG:** `{TAG_ORG_NEMESIS}`\n**Cargo inicial:** <@&{CARGO_VISITANTES_ID}> — {NOME_CARGO_VISITANTES}",
            inline=True,
        )
        embed.add_field(
            name="◈  RECRUTAMENTO",
            value=f"**Convidador:** <@{convidador_id}>" if convidador_id else
                  "**Convidador:** Não identificado com segurança.",
            inline=True,
        )
        embed.add_field(
            name="◈  REGISTRO",
            value=f"**Conta criada:** {conta_criada}\n**Entrada:** {discord.utils.format_dt(agora, style='F')}",
            inline=True,
        )
        embed.add_field(
            name="╭・SEU PRIMEIRO PASSO",
            value=(
                "01. **Leia as regras:** conheça as normas antes de participar.\n"
                "02. **Entenda a estrutura:** visite Como funciona e Divisões.\n"
                "03. **Conheça a organização:** consulte o Guia Oficial no canal Como funciona.\n"
                "04. **Entre em atividade:** acompanhe missões, eventos e progressão.\n"
                "05. **Precisa de ajuda?** localize Atendimento no menu do guia."
            ),
            inline=False,
        )
        embed.add_field(
            name="✦  SEU PRÓXIMO CAPÍTULO COMEÇA AGORA",
            value="A TAG oficial da organização é **NΞM**. A NÊMESIS reconhece atitude, consistência e espírito competitivo. **Mostre do que você é capaz.**",
            inline=False,
        )
        embed.set_footer(text="NÊMESIS • TAG DA ORG: NΞM • Sistema oficial de integração")
        if canal is not None:
            enviado = await self._enviar_log(canal, embed, view=_layout_boas_vindas(embed))
            if enviado:
                logger.info("Mensagem de entrada publicada (guild=%s, member=%s, channel=%s, inviter=%s).",
                            member.guild.id, member.id, canal.id, convidador_id or "desconhecido")
            else:
                logger.error("Falha ao publicar mensagem de entrada (guild=%s, member=%s, channel=%s).",
                             member.guild.id, member.id, canal.id)


    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Saídas não geram mais notificações no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Arquiva a exclusão somente no histórico privado do autor.

        O tópico do Registro Global não recebe conteúdo de mensagens pessoais.
        O listener raw continua como segunda via para exclusões sem cache.
        """
        if (
            message.author.bot
            or not message.guild
            or message.guild.id != GUILD_NEMESIS_ID
        ):
            return

        indice_existente = await monitoramento_membros.buscar_mensagem(message.guild.id, message.id)
        if indice_existente and indice_existente.get("status") == "excluida":
            return

        agora = datetime.now(timezone.utc).timestamp()
        await monitoramento_membros.registrar_mensagem(
            message.guild.id,
            message.author.id,
            {
                "message_id": str(message.id),
                "canal_id": message.channel.id,
                "timestamp": message.created_at.timestamp(),
                "conteudo": message.content or "",
                "url": message.jump_url,
                "status": "excluida",
                "excluida_em": agora,
                "anexos": [
                    {"nome": anexo.filename, "tamanho": anexo.size}
                    for anexo in message.attachments[:10]
                ],
            },
        )

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.guild_id != GUILD_NEMESIS_ID:
            return
        registro = await monitoramento_membros.buscar_mensagem(payload.guild_id, payload.message_id)
        if registro and registro.get("status") == "excluida":
            return
        agora = datetime.now(timezone.utc).timestamp()
        mensagem_cache = getattr(payload, "cached_message", None)
        if registro:
            user_id = int(registro["user_id"])
            timestamp = registro.get("timestamp")
            conteudo = None
            anexos = None
        elif mensagem_cache and not mensagem_cache.author.bot:
            user_id = mensagem_cache.author.id
            timestamp = mensagem_cache.created_at.timestamp()
            conteudo = mensagem_cache.content or ""
            anexos = [{"nome": a.filename, "tamanho": a.size} for a in mensagem_cache.attachments[:10]]
        else:
            return
        dados = {
            "message_id": str(payload.message_id),
            "canal_id": payload.channel_id,
            "timestamp": timestamp,
            "status": "excluida",
            "excluida_em": agora,
        }
        if conteudo is not None:
            dados["conteudo"] = conteudo
            dados["anexos"] = anexos or []
        await monitoramento_membros.registrar_mensagem(payload.guild_id, user_id, dados)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if payload.guild_id != GUILD_NEMESIS_ID:
            return
        agora = datetime.now(timezone.utc).timestamp()
        cache = {
            mensagem.id: mensagem
            for mensagem in (getattr(payload, "cached_messages", None) or [])
            if mensagem.guild and not mensagem.author.bot
        }
        for message_id in payload.message_ids:
            registro = await monitoramento_membros.buscar_mensagem(payload.guild_id, message_id)
            if registro and registro.get("status") == "excluida":
                continue
            mensagem_cache = cache.get(message_id)
            if registro:
                user_id = int(registro["user_id"])
                timestamp = registro.get("timestamp")
                dados = {
                    "message_id": str(message_id), "canal_id": payload.channel_id,
                    "timestamp": timestamp, "status": "excluida", "excluida_em": agora,
                }
            elif mensagem_cache:
                user_id = mensagem_cache.author.id
                dados = {
                    "message_id": str(message_id), "canal_id": payload.channel_id,
                    "timestamp": mensagem_cache.created_at.timestamp(),
                    "conteudo": mensagem_cache.content or "", "status": "excluida",
                    "excluida_em": agora,
                    "anexos": [{"nome": a.filename, "tamanho": a.size} for a in mensagem_cache.attachments[:10]],
                }
            else:
                continue
            await monitoramento_membros.registrar_mensagem(payload.guild_id, user_id, dados)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.guild_id != GUILD_NEMESIS_ID:
            return
        dados = payload.data if isinstance(payload.data, dict) else {}
        autor = dados.get("author") if isinstance(dados.get("author"), dict) else {}
        if autor.get("bot") is True:
            return
        indice = await monitoramento_membros.buscar_mensagem(payload.guild_id, payload.message_id)
        user_id = int(autor.get("id") or (indice or {}).get("user_id") or 0)
        if not user_id:
            return
        try:
            canal = self.bot.get_channel(payload.channel_id) or await self.bot.fetch_channel(payload.channel_id)
            mensagem = await canal.fetch_message(payload.message_id)
            if mensagem.author.bot:
                return
            registro = {
                "message_id": str(mensagem.id),
                "canal_id": mensagem.channel.id,
                "timestamp": mensagem.created_at.timestamp(),
                "conteudo": mensagem.content or "",
                "url": mensagem.jump_url,
                "status": "editada",
                "anexos": [{"nome": a.filename, "tamanho": a.size} for a in mensagem.attachments[:10]],
            }
            user_id = mensagem.author.id
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            # O payload bruto ainda pode conter o conteúdo atualizado mesmo sem cache/histórico acessível.
            if "content" not in dados:
                return
            timestamp = (indice or {}).get("timestamp") or datetime.now(timezone.utc).timestamp()
            registro = {
                "message_id": str(payload.message_id),
                "canal_id": payload.channel_id,
                "timestamp": timestamp,
                "conteudo": str(dados.get("content") or ""),
                "url": f"https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id}",
                "status": "editada",
                "anexos": [
                    {"nome": str(a.get("filename", "arquivo")), "tamanho": int(a.get("size", 0) or 0)}
                    for a in dados.get("attachments", []) if isinstance(a, dict)
                ][:10],
            }
        await monitoramento_membros.registrar_mensagem(payload.guild_id, user_id, registro)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Captura mensagens da NÊMESIS para consulta privada, com retenção limitada."""
        if not message.guild or message.guild.id != GUILD_NEMESIS_ID or message.author.bot:
            return
        await monitoramento_membros.registrar_mensagem(message.guild.id, message.author.id, {
            "message_id": str(message.id), "canal_id": message.channel.id,
            "timestamp": message.created_at.timestamp(), "conteudo": message.content or "",
            "url": message.jump_url, "status": "enviada",
            "anexos": [{"nome": a.filename, "tamanho": a.size} for a in message.attachments[:10]],
        })
        if not message.attachments:
            return
        linhas = [
            f"**Autor:** {message.author.mention} (ID: {message.author.id})",
            f"**Canal:** {message.channel.mention} (ID: {message.channel.id})",
            f"**Mensagem:** {message.id}",
            f"**Enviado em:** {discord.utils.format_dt(message.created_at, style='F')}",
        ]
        for anexo in message.attachments[:10]:
            linhas.append(f"• **{anexo.filename[:180]}** — {anexo.size:,} bytes")
        await registrar_global(message.guild, "anexos", "Anexos enviados", "\n".join(linhas)[:3800], cor=0x57F287)

    @commands.Cog.listener()
    async def on_message_edit(self, antes: discord.Message, depois: discord.Message):
        """Registra a nova versão no arquivo privado, sem publicar conteúdo no fórum."""
        if (
            antes.author.bot
            or not antes.guild
            or antes.guild.id != GUILD_NEMESIS_ID
        ):
            return

        anexos_antes = [anexo.url for anexo in antes.attachments]
        anexos_depois = [anexo.url for anexo in depois.attachments]
        if antes.content == depois.content and anexos_antes == anexos_depois:
            return

        await monitoramento_membros.registrar_mensagem(
            depois.guild.id,
            depois.author.id,
            {
                "message_id": str(depois.id),
                "canal_id": depois.channel.id,
                "timestamp": depois.created_at.timestamp(),
                "conteudo": depois.content or "",
                "url": depois.jump_url,
                "status": "editada",
                "anexos": [
                    {"nome": anexo.filename, "tamanho": anexo.size}
                    for anexo in depois.attachments[:10]
                ],
            },
        )

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if guild.id == GUILD_NEMESIS_ID:
            await monitoramento_membros.registrar_evento(guild.id, user.id, "banimento", "Membro banido do servidor.")
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = criar_embed(description=f"🔨 {user.mention} (`{user}`) foi banido do servidor.", color=0xED4245)
        embed.set_thumbnail(url=user.display_avatar.url)
        await self._enviar_log(canal, embed, categoria="moderacao")
        await registrar_global(
            guild, "historico_membros", "Banimento de membro",
            f"Membro: {user} (ID: {user.id})\nAção: banimento\nOrigem: evento do Discord; executor não identificado pelo gateway.",
            cor=0xED4245,
        )

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        if guild.id == GUILD_NEMESIS_ID:
            await monitoramento_membros.registrar_evento(guild.id, user.id, "desbanimento", "Banimento removido do membro.")
        canal = await self._canal_logs(guild)
        if not canal:
            return
        embed = criar_embed(description=f"⚖️ {user.mention} (`{user}`) foi desbanido do servidor.", color=0x57F287)
        await self._enviar_log(canal, embed, categoria="moderacao")
        await registrar_global(
            guild, "historico_membros", "Desbanimento de membro",
            f"Membro: {user} (ID: {user.id})\nAção: desbanimento\nOrigem: evento do Discord; executor não identificado pelo gateway.",
            cor=0x57F287,
        )

    @commands.Cog.listener()
    async def on_member_update(self, antes: discord.Member, depois: discord.Member):
        if depois.guild.id == GUILD_NEMESIS_ID:
            if antes.nick != depois.nick:
                await monitoramento_membros.registrar_evento(depois.guild.id, depois.id, "apelido", f"Apelido alterado: {antes.nick or antes.name} → {depois.nick or depois.name}.")
            if antes.name != depois.name or antes.global_name != depois.global_name:
                await monitoramento_membros.registrar_evento(depois.guild.id, depois.id, "identidade", f"Nome de usuário alterado: {antes.name} → {depois.name}.")
            if antes.premium_since != depois.premium_since:
                await monitoramento_membros.registrar_evento(
                    depois.guild.id, depois.id, "impulsionamento",
                    "Começou a impulsionar o servidor." if depois.premium_since else "Deixou de impulsionar o servidor.",
                    detalhes={"premium_since": depois.premium_since.timestamp() if depois.premium_since else None},
                )
            timeout_antes = _timeout_membro(antes)
            timeout_depois = _timeout_membro(depois)
            if timeout_antes != timeout_depois:
                await monitoramento_membros.registrar_evento(
                    depois.guild.id, depois.id, "timeout",
                    "Timeout aplicado, alterado ou removido.",
                    detalhes={
                        "antes": timeout_antes.timestamp() if timeout_antes else None,
                        "depois": timeout_depois.timestamp() if timeout_depois else None,
                    },
                )

        canal = await self._canal_logs(depois.guild)
        if not canal:
            return

        if antes.nick != depois.nick:
            embed = criar_embed(
                title="Apelido alterado",
                description=(
                    f"**Membro:** {depois.mention} ({depois.id})\n"
                    f"**Antes:** {antes.nick or antes.name}\n"
                    f"**Depois:** {depois.nick or depois.name}"
                ),
                color=0xFEE75C,
            )
            await self._enviar_log(canal, embed, categoria="historico_membros")

        if antes.name != depois.name or antes.global_name != depois.global_name:
            identidade = criar_embed(
                title="Identidade do Discord alterada",
                description=(
                    f"**Membro:** {depois.mention} ({depois.id})\n"
                    f"**Nome de usuário:** {antes.name} → {depois.name}\n"
                    f"**Nome global:** {antes.global_name or 'Não definido'} → {depois.global_name or 'Não definido'}"
                ),
                color=0xFEE75C,
            )
            await self._enviar_log(canal, identidade, categoria="membros")

        if antes.premium_since != depois.premium_since:
            iniciou_boost = depois.premium_since is not None
            detalhe_boost = (
                f"**Membro:** {depois.mention} ({depois.id})\n"
                f"**Ação:** {'Começou a impulsionar' if iniciou_boost else 'Deixou de impulsionar'} o servidor.\n"
                f"**Data:** {discord.utils.format_dt(depois.premium_since, style='F') if depois.premium_since else 'Boost encerrado'}"
            )
            await self._enviar_log(
                canal,
                criar_embed(
                    title="Status de impulsionamento alterado",
                    description=detalhe_boost,
                    color=0x57F287 if iniciou_boost else 0xED4245,
                ),
                categoria="membros",
            )


        # Usa o atributo oficial de discord.py e mantém fallback para forks antigos.
        timeout_antes = _timeout_membro(antes)
        timeout_depois = _timeout_membro(depois)
        if timeout_antes != timeout_depois:
            embed = criar_embed(
                title="Timeout alterado",
                description=f"**Membro:** {depois.mention} ({depois.id})",
                color=0xFEE75C,
            )
            embed.add_field(
                name="Antes",
                value=discord.utils.format_dt(timeout_antes, style="F")
                if timeout_antes else "Sem timeout",
                inline=True,
            )
            embed.add_field(
                name="Depois",
                value=discord.utils.format_dt(timeout_depois, style="F")
                if timeout_depois else "Sem timeout",
                inline=True,
            )
            await self._enviar_log(canal, embed, categoria="moderacao")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_presence_update(self, antes: discord.Member, depois: discord.Member):
        """Registra mudanças de presença e jogos, sem armazenar status personalizado ou mídia pessoal."""
        if depois.guild.id != GUILD_NEMESIS_ID or depois.bot:
            return
        status_antes = str(getattr(antes, "status", "offline"))
        status_depois = str(getattr(depois, "status", "offline"))
        jogos_antes = sorted(
            str(getattr(atividade, "name", ""))[:100]
            for atividade in getattr(antes, "activities", [])
            if getattr(atividade, "type", None) == discord.ActivityType.playing and getattr(atividade, "name", None)
        )
        jogos_depois = sorted(
            str(getattr(atividade, "name", ""))[:100]
            for atividade in getattr(depois, "activities", [])
            if getattr(atividade, "type", None) == discord.ActivityType.playing and getattr(atividade, "name", None)
        )
        if status_antes == status_depois and jogos_antes == jogos_depois:
            return
        partes = []
        if status_antes != status_depois:
            partes.append(f"Presença: {status_antes} → {status_depois}")
        if jogos_antes != jogos_depois:
            partes.append(f"Jogos: {', '.join(jogos_antes) or 'nenhum'} → {', '.join(jogos_depois) or 'nenhum'}")
        await monitoramento_membros.registrar_evento(
            depois.guild.id, depois.id, "presenca", " | ".join(partes),
            detalhes={"status_antes": status_antes, "status_depois": status_depois,
                      "jogos_antes": jogos_antes, "jogos_depois": jogos_depois},
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, antes: discord.VoiceState, depois: discord.VoiceState):
        if member.guild.id == GUILD_NEMESIS_ID:
            if antes.channel is None and depois.channel is not None:
                await monitoramento_membros.registrar_evento(member.guild.id, member.id, "voz_entrada", f"Entrou no canal de voz {depois.channel.name}.")
            elif antes.channel != depois.channel and antes.channel and depois.channel:
                await monitoramento_membros.registrar_evento(member.guild.id, member.id, "voz_movimentacao", f"Mudou de {antes.channel.name} para {depois.channel.name}.")
            alteracoes_privadas = []
            for atributo, rotulo in (("mute", "mute do servidor"), ("deaf", "surdez do servidor"), ("self_mute", "autossilenciamento"), ("self_deaf", "autossurdez"), ("self_stream", "transmissão"), ("self_video", "câmera")):
                valor_antes = bool(getattr(antes, atributo, False))
                valor_depois = bool(getattr(depois, atributo, False))
                if valor_antes != valor_depois:
                    alteracoes_privadas.append(f"{rotulo}: {'ativado' if valor_depois else 'desativado'}")
            if alteracoes_privadas:
                await monitoramento_membros.registrar_evento(
                    member.guild.id, member.id, "voz_estado", "; ".join(alteracoes_privadas),
                    detalhes={"canal_id": depois.channel.id if depois.channel else (antes.channel.id if antes.channel else None)},
                )
        canal = await self._canal_logs(member.guild)
        if not canal:
            return
        if antes.channel is None and depois.channel is not None:
            detalhe = f"Entrou no canal de voz {depois.channel.name}."
            await self._enviar_log(canal, criar_embed(description=f"🔊 {detalhe}", color=0x57F287), categoria="voz")
            await registrar_global(member.guild, "historico_membros", "Entrada em chamada", detalhe, cor=0x57F287)
        elif antes.channel != depois.channel:
            detalhe = f"Mudou de {antes.channel.name} para {depois.channel.name}."
            await self._enviar_log(canal, criar_embed(description=f"🔀 {detalhe}", color=0xFEE75C), categoria="voz")
            await registrar_global(member.guild, "historico_membros", "Movimentação em chamada", detalhe, cor=0xFEE75C)

        alteracoes_estado = []
        for atributo, rotulo in (
            ("mute", "Silenciado pelo servidor"),
            ("deaf", "Ensurdecido pelo servidor"),
            ("self_mute", "Silenciado pelo próprio membro"),
            ("self_deaf", "Ensurdecido pelo próprio membro"),
            ("self_stream", "Transmissão ao vivo"),
            ("self_video", "Câmera"),
        ):
            valor_antes = bool(getattr(antes, atributo, False))
            valor_depois = bool(getattr(depois, atributo, False))
            if valor_antes != valor_depois:
                estado = "Ativado" if valor_depois else "Desativado"
                alteracoes_estado.append(f"**{rotulo}:** {estado}")

        if alteracoes_estado:
            canal_atual = depois.channel or antes.channel
            detalhe = (
                f"**Membro:** {member.mention} ({member.id})\n"
                f"**Canal:** {canal_atual.mention if canal_atual else 'Desconectado'}\n"
                + "\n".join(alteracoes_estado)
            )
            await self._enviar_log(
                canal,
                criar_embed(
                    title="Estado de chamada alterado",
                    description=detalhe,
                    color=0xFEE75C,
                ),
                categoria="voz",
            )
            await registrar_global(
                member.guild,
                "historico_membros",
                "Estado de chamada alterado",
                detalhe,
                cor=0xFEE75C,
            )


    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        """Arquiva exclusões em massa apenas nos dossiês privados dos autores."""
        mensagens = [
            mensagem for mensagem in messages
            if mensagem.guild and mensagem.guild.id == GUILD_NEMESIS_ID and not mensagem.author.bot
        ]
        for mensagem in mensagens:
            await monitoramento_membros.registrar_mensagem(
                mensagem.guild.id, mensagem.author.id,
                {
                    "message_id": str(mensagem.id),
                    "canal_id": mensagem.channel.id,
                    "timestamp": mensagem.created_at.timestamp(),
                    "conteudo": mensagem.content or "",
                    "url": mensagem.jump_url,
                    "status": "excluida",
                    "excluida_em": datetime.now(timezone.utc).timestamp(),
                    "anexos": [{"nome": anexo.filename, "tamanho": anexo.size} for anexo in mensagem.attachments[:10]],
                },
            )
        if mensagens:
            logger.info(
                "Exclusão em massa arquivada em dossiês privados: guild=%s mensagens=%s autores=%s",
                GUILD_NEMESIS_ID, len(mensagens), len({mensagem.author.id for mensagem in mensagens}),
            )

    @commands.Cog.listener()
    async def on_guild_channel_update(self, antes: discord.abc.GuildChannel, depois: discord.abc.GuildChannel):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_guild_role_update(self, antes: discord.Role, depois: discord.Role):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_thread_update(self, antes: discord.Thread, depois: discord.Thread):
        """Auditoria estrutural automática desativada para evitar ruído no Registro Global."""
        return
    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        if invite.guild is None or invite.guild.id != GUILD_NEMESIS_ID:
            return
        await registrar_global(
            invite.guild, "convites", "Convite criado",
            f"Código: `{invite.code}`\nCanal: {invite.channel.mention if invite.channel else 'Não identificado'}\n"
            f"Criado por: {invite.inviter.mention if invite.inviter else 'Não identificado'}\n"
            f"Usos máximos: {invite.max_uses or 'Ilimitado'}",
            cor=0x57F287,
        )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        if invite.guild is None or invite.guild.id != GUILD_NEMESIS_ID:
            return
        await registrar_global(
            invite.guild, "convites", "Convite removido",
            f"Código: `{invite.code}`\nCanal: {invite.channel.mention if invite.channel else 'Não identificado'}",
            cor=0xED4245,
        )

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        if channel.guild.id != GUILD_NEMESIS_ID:
            return
        await registrar_global(
            channel.guild, "seguranca", "Webhooks atualizados",
            f"Canal afetado: {channel.mention if hasattr(channel, 'mention') else channel.name} (`{channel.id}`)\n"
            "O Discord notificou uma alteração na configuração de webhooks deste canal.",
            cor=0xFEE75C,
        )

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        if event.guild.id != GUILD_NEMESIS_ID:
            return
        descricao = (
            f"Evento: **{event.name}** (`{event.id}`)\n"
            f"Início: {discord.utils.format_dt(event.start_time, style='F')}\n"
            f"Término: {discord.utils.format_dt(event.end_time, style='F') if event.end_time else 'Não definido'}\n"
            f"Criado por: <@{event.creator_id}>" if event.creator_id else
            f"Evento: **{event.name}** (`{event.id}`)\n"
            f"Início: {discord.utils.format_dt(event.start_time, style='F')}\n"
            f"Término: {discord.utils.format_dt(event.end_time, style='F') if event.end_time else 'Não definido'}"
        )
        await registrar_global(
            event.guild, "eventos", "Evento agendado criado", descricao,
            cor=0x57F287,
        )

    @commands.Cog.listener()
    async def on_scheduled_event_delete(self, event: discord.ScheduledEvent):
        if event.guild.id != GUILD_NEMESIS_ID:
            return
        await registrar_global(
            event.guild, "eventos", "Evento agendado removido",
            f"Evento: **{event.name}** (`{event.id}`)\nStatus final: {event.status}",
            cor=0xED4245,
        )

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, antes: discord.ScheduledEvent, depois: discord.ScheduledEvent):
        if depois.guild.id != GUILD_NEMESIS_ID:
            return
        mudancas = []
        for atributo, rotulo in (("name", "Nome"), ("description", "Descrição"), ("start_time", "Início"), ("end_time", "Término"), ("status", "Status"), ("location", "Local")):
            valor_antes = getattr(antes, atributo, None)
            valor_depois = getattr(depois, atributo, None)
            if valor_antes != valor_depois:
                mudancas.append(f"{rotulo}: {valor_antes} → {valor_depois}")
        if mudancas:
            await registrar_global(
                depois.guild, "eventos", "Evento agendado atualizado",
                f"Evento: **{depois.name}** (`{depois.id}`)\n" + "\n".join(mudancas),
                cor=0xFEE75C,
            )

    @commands.Cog.listener()
    async def on_guild_update(self, antes: discord.Guild, depois: discord.Guild):
        if depois.id != GUILD_NEMESIS_ID:
            return
        mudancas = []
        for atributo, rotulo in (("name", "Nome"), ("description", "Descrição"), ("verification_level", "Verificação"), ("explicit_content_filter", "Filtro de conteúdo"), ("default_notifications", "Notificações padrão"), ("afk_timeout", "Timeout AFK")):
            if getattr(antes, atributo, None) != getattr(depois, atributo, None):
                mudancas.append(f"{rotulo}: {getattr(antes, atributo, None)} → {getattr(depois, atributo, None)}")
        if mudancas:
            await registrar_global(
                depois, "administracao", "Configurações do servidor alteradas",
                "\n".join(mudancas), cor=0xFEE75C,
            )

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, antes, depois):
        if guild.id != GUILD_NEMESIS_ID:
            return
        ids_antes = {item.id: item for item in antes}
        ids_depois = {item.id: item for item in depois}
        criados = [item.name for key, item in ids_depois.items() if key not in ids_antes]
        removidos = [item.name for key, item in ids_antes.items() if key not in ids_depois]
        if criados or removidos:
            await registrar_global(
                guild, "administracao", "Emojis do servidor alterados",
                f"Criados: {', '.join(criados) or 'Nenhum'}\nRemovidos: {', '.join(removidos) or 'Nenhum'}",
                cor=0xFEE75C,
            )

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, antes, depois):
        if guild.id != GUILD_NEMESIS_ID:
            return
        ids_antes = {item.id: item for item in antes}
        ids_depois = {item.id: item for item in depois}
        criados = [item.name for key, item in ids_depois.items() if key not in ids_antes]
        removidos = [item.name for key, item in ids_antes.items() if key not in ids_depois]
        if criados or removidos:
            await registrar_global(
                guild, "administracao", "Figurinhas do servidor alteradas",
                f"Criadas: {', '.join(criados) or 'Nenhuma'}\nRemovidas: {', '.join(removidos) or 'Nenhuma'}",
                cor=0xFEE75C,
            )



async def setup(bot: commands.Bot):
    await bot.add_cog(Logs(bot))
