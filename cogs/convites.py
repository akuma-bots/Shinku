from __future__ import annotations
import asyncio, logging
from collections import defaultdict
from datetime import datetime, timezone
import discord
from discord.ext import commands
from utils.apresentacao import criar_embed
from utils.guild_config import membro_tem_lideranca
from utils.storage import carregar, salvar

logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
CANAL_CONVITES_ID = 1563995880623841332
ARQUIVO_CONVITES = "convites_nemesis.json"


def _autorizado(interaction):
    return bool(
        interaction.guild_id == GUILD_NEMESIS_ID
        and membro_tem_lideranca(interaction.user)
    )


def _resumo(servidor, inviter_id):
    membros = servidor.get("_membros", {})
    registro = servidor.get(str(inviter_id), {})
    ativos_legados = (
        set(map(str, registro.get("membros", [])))
        if isinstance(registro, dict)
        else set()
    )
    historico = servidor.get("_historico", {})
    itens = []
    for mid, item in membros.items() if isinstance(membros, dict) else []:
        if isinstance(item, dict) and str(item.get("inviter_id")) == str(inviter_id):
            itens.append({"member_id": str(mid), **item})
    ids = {item["member_id"] for item in itens}
    # O histórico antigo preserva convidados que já saíram; o campo membros
    # representa apenas os que continuam presentes no servidor.
    for mid, convidador in historico.items() if isinstance(historico, dict) else []:
        if str(convidador) == str(inviter_id) and str(mid) not in ids:
            itens.append(
                {
                    "member_id": str(mid),
                    "active": str(mid) in ativos_legados,
                    "legacy": True,
                }
            )
    return itens


def _total_paginas(servidor, inviter_id):
    codigos = {item.get("code") or "legado" for item in _resumo(servidor, inviter_id)}
    return max(1, (len(codigos) + 7) // 8)


def _embed(membro, servidor, pagina=0):
    itens = _resumo(servidor, membro.id)
    ativos = sum(1 for x in itens if x.get("active", True))
    embed = criar_embed(
        title="🔗・CONSULTA INDIVIDUAL DE CONVITES",
        description=(
            f"**Integrante:** {membro.mention}\n**Convites atribuídos:** {len(itens)}"
            f"\n**Convidados presentes:** {ativos}\n**Saídas:** {len(itens)-ativos}"
        ),
        cor=0x991B33,
    )
    embed.set_thumbnail(url=membro.display_avatar.url)
    agrupados = {}
    for item in itens:
        agrupados.setdefault(item.get("code") or "legado", []).append(item)
    if not agrupados:
        embed.add_field(
            name="Links utilizados",
            value="Nenhum convite atribuído foi registrado.",
            inline=False,
        )
    grupos = list(agrupados.items())
    total_paginas = max(1, (len(grupos) + 7) // 8)
    pagina = max(0, min(pagina, total_paginas - 1))
    inicio = pagina * 8
    for code, grupo in grupos[inicio : inicio + 8]:
        url = next((x.get("url") for x in grupo if x.get("url")), None)
        presentes = sum(1 for x in grupo if x.get("active", True))
        linhas = [
            f"**Convidados:** {len(grupo)} • **Presentes:** {presentes}",
            f"**Link:** {url or 'Não registrado (dado legado)'}",
        ]
        nomes = [
            f"• {x.get('member_name') or x['member_id']} — {'presente' if x.get('active', True) else 'saiu'}"
            for x in grupo[:3]
        ]
        if nomes:
            linhas.append("**Membros:**\n" + "\n".join(nomes))
        if len(grupo) > 3:
            linhas.append(f"… e mais {len(grupo)-3}.")
        embed.add_field(
            name=f"Convite {code}" if code != "legado" else "Registros antigos",
            value="\n".join(linhas)[:1024],
            inline=False,
        )
    embed.set_footer(
        text=f"Consulta privada • Página {pagina + 1}/{total_paginas} • Links exibidos somente quando registrados."
    )
    return embed



def _card_convites(origem: discord.ui.View, embed: discord.Embed | None = None,
                   titulo: str = "CENTRAL DE CONVITES", descricao: str = "Consulta individual e privada."):
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
    for item in origem.children:
        if isinstance(item, discord.ui.UserSelect):
            novo = discord.ui.UserSelect(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, custom_id=item.custom_id,
                disabled=item.disabled,
            )
            async def selecionar(interaction, original=item, clone=novo, view=origem):
                original._values = clone._values
                if hasattr(clone, "_resolved"):
                    original._resolved = clone._resolved
                await view.selecionar(interaction)
            novo.callback = selecionar
            componentes.append(discord.ui.ActionRow(novo))
        elif isinstance(item, discord.ui.Select):
            novo = discord.ui.Select(
                placeholder=item.placeholder, min_values=item.min_values,
                max_values=item.max_values, options=list(item.options),
                custom_id=item.custom_id, disabled=item.disabled,
            )
            async def selecionar(interaction, original=item, clone=novo):
                original._values = clone._values
                await original.callback(interaction)
            novo.callback = selecionar
            componentes.append(discord.ui.ActionRow(novo))
        elif isinstance(item, discord.ui.Button):
            novo = discord.ui.Button(
                label=item.label, style=item.style, disabled=item.disabled,
                custom_id=item.custom_id, url=item.url, emoji=item.emoji,
            )
            novo.callback = item.callback
            componentes.append(discord.ui.ActionRow(novo))
    componentes.extend([
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay("-# Nêmesis Systeam • Consulta privada"),
    ])
    layout.add_item(discord.ui.Container(*componentes, accent_colour=0x9F1239))
    verificacao = getattr(origem, "interaction_check", None)
    if callable(verificacao):
        layout.interaction_check = verificacao
    return layout


class SeletorConvitesView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.seletor = discord.ui.UserSelect(
            placeholder="Pesquise e selecione um integrante",
            min_values=1,
            max_values=1,
            custom_id="nemesis:convites:membro:selecionar",
        )
        self.seletor.callback = self.selecionar
        self.add_item(self.seletor)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id or not _autorizado(interaction):
            await interaction.response.send_message(
                "Acesso restrito à liderança autorizada.", ephemeral=True
            )
            return False
        return True

    async def selecionar(self, interaction):
        membro = self.seletor.values[0]
        if not isinstance(membro, discord.Member):
            try:
                membro = await interaction.guild.fetch_member(membro.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message(
                    "Integrante não encontrado.", ephemeral=True
                )
                return
        if membro.bot:
            await interaction.response.send_message(
                "Bots não possuem consulta de convites.", ephemeral=True
            )
            return
        await interaction.response.defer()
        try:
            dados = await carregar(ARQUIVO_CONVITES, {})
            servidor = (
                dados.get(str(GUILD_NEMESIS_ID), {}) if isinstance(dados, dict) else {}
            )
            await interaction.edit_original_response(content=None, embed=None)
            await interaction.edit_original_response(
                view=_card_convites(
                    VoltarConvitesView(
                        self.owner_id,
                        membro.id,
                        0,
                        _total_paginas(servidor, membro.id),
                    ),
                    _embed(membro, servidor),
                )
            )
        except Exception:
            logger.exception("Falha na consulta de convites do membro %s.", membro.id)
            await interaction.edit_original_response(
                content="Não foi possível carregar os convites.", embed=None, view=None
            )


class VoltarConvitesView(discord.ui.View):
    def __init__(self, owner_id, membro_id, pagina, total_paginas):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.membro_id = membro_id
        self.pagina = pagina
        self.total_paginas = total_paginas
        self.anterior.disabled = pagina <= 0
        self.proxima.disabled = pagina >= total_paginas - 1

    async def _mudar_pagina(self, interaction, delta):
        if interaction.user.id != self.owner_id or not _autorizado(interaction):
            await interaction.response.send_message(
                "Acesso restrito à liderança autorizada.", ephemeral=True
            )
            return
        try:
            membro = await interaction.guild.fetch_member(self.membro_id)
            dados = await carregar(ARQUIVO_CONVITES, {})
            servidor = (
                dados.get(str(GUILD_NEMESIS_ID), {}) if isinstance(dados, dict) else {}
            )
            self.pagina = max(0, min(self.total_paginas - 1, self.pagina + delta))
            self.anterior.disabled = self.pagina <= 0
            self.proxima.disabled = self.pagina >= self.total_paginas - 1
            await interaction.response.edit_message(content=None, embed=None, view=None)
            await interaction.edit_original_response(
                view=_card_convites(self, _embed(membro, servidor, self.pagina))
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message(
                "Não foi possível atualizar esta consulta.", ephemeral=True
            )

    @discord.ui.button(
        label="Anterior", emoji="◀️", style=discord.ButtonStyle.secondary, row=0
    )
    async def anterior(self, interaction, button):
        await self._mudar_pagina(interaction, -1)

    @discord.ui.button(
        label="Próxima", emoji="▶️", style=discord.ButtonStyle.secondary, row=0
    )
    async def proxima(self, interaction, button):
        await self._mudar_pagina(interaction, 1)

    @discord.ui.button(
        label="Consultar outro integrante",
        emoji="🔎",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def voltar(self, interaction, button):
        if interaction.user.id != self.owner_id or not _autorizado(interaction):
            await interaction.response.send_message(
                "Acesso restrito à liderança autorizada.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            view=_card_convites(
                SeletorConvitesView(self.owner_id),
                criar_embed(
                    title="🔗 CENTRAL DE CONVITES",
                    description="Selecione um integrante para consultar convites atribuídos e convidados presentes.",
                    cor=0x991B33,
                ),
            )
        )


class PainelConsultaConvitesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Consultar convites de membro",
        emoji="🔗",
        style=discord.ButtonStyle.primary,
        custom_id="nemesis:convites:abrir",
    )
    async def abrir(self, interaction, button):
        if not _autorizado(interaction):
            await interaction.response.send_message(
                "Acesso restrito à liderança autorizada da NÊMESIS.", ephemeral=True
            )
            return
        origem = SeletorConvitesView(interaction.user.id)
        await interaction.response.send_message(
            view=_card_convites(
                origem,
                criar_embed(
                    title="🔗 CENTRAL DE CONVITES",
                    description="Selecione um integrante para consultar quantos convites trouxe, quais links foram utilizados e quem continua no servidor. Consulta individual, não é um ranking.",
                    cor=0x991B33,
                    rodape="NÊMESIS • REGISTRO GLOBAL • CONSULTA PRIVADA",
                ),
            ),
            ephemeral=True,
        )


class PainelConsultaConvitesLayoutView(discord.ui.LayoutView):
    """Painel de consulta com o botão dentro do cartão Components V2."""

    def __init__(self):
        super().__init__(timeout=None)
        legado = PainelConsultaConvitesView()
        original = next(
            item for item in legado.children
            if getattr(item, "custom_id", None) == "nemesis:convites:abrir"
        )
        botao = discord.ui.Button(
            label=original.label,
            emoji=original.emoji,
            style=original.style,
            custom_id=original.custom_id,
        )
        botao.callback = original.callback
        self.add_item(discord.ui.Container(
            discord.ui.TextDisplay(
                "## 🔗 CENTRAL DE CONVITES\n"
                "**Consulta individual da NÊMESIS.**\n"
                "Selecione um integrante para conferir os convites atribuídos, "
                "os links utilizados e quem permanece no servidor.\n\n"
                "A consulta é privada e não funciona como ranking."
            ),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.ActionRow(botao),
            discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay("-# Nêmesis Systeam"),
            accent_colour=0x9F1239,
        ))



def _componentes_contem_marcador(componentes, marcador: str) -> bool:
    pendentes = list(componentes or [])
    while pendentes:
        componente = pendentes.pop()
        if marcador.casefold() in str(getattr(componente, "content", "") or "").casefold():
            return True
        if str(getattr(componente, "custom_id", "") or "") == "nemesis:convites:abrir":
            return True
        pendentes.extend(list(getattr(componente, "children", []) or []))
    return False


def _mensagem_eh_painel_convites(mensagem: discord.Message) -> bool:
    # Reconhece a versão atual, os painéis legados (embed) e o botão antigo,
    # mesmo que o texto/título tenha sido alterado em uma publicação anterior.
    for embed in mensagem.embeds:
        titulo = str(embed.title or "").casefold()
        descricao = str(embed.description or "").casefold()
        rodape = str(embed.footer.text or "").casefold() if embed.footer else ""
        if "central de convites" in titulo or (
            "convites" in titulo and ("nemesis" in descricao or "consulta" in descricao)
        ) or "painel de convites" in rodape:
            return True
    pendentes = list(getattr(mensagem, "components", []) or [])
    while pendentes:
        componente = pendentes.pop()
        conteudo = str(getattr(componente, "content", "") or "").casefold()
        custom_id = str(getattr(componente, "custom_id", "") or "")
        if "central de convites" in conteudo or custom_id == "nemesis:convites:abrir":
            return True
        pendentes.extend(list(getattr(componente, "children", []) or []))
    return False


class ConvitesNemesis(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._convites = {}
        self._locks = defaultdict(asyncio.Lock)
        self._inicializados = set()
        self._painel_lock = asyncio.Lock()
        self.bot.add_view(PainelConsultaConvitesLayoutView())

    async def _buscar_convites(self, guild):
        try:
            convites = await guild.invites()
        except (discord.Forbidden, discord.HTTPException):
            logger.exception(
                "Não foi possível ler convites; verifique Gerenciar servidor."
            )
            return None
        return {
            i.code: (i.uses or 0, i.inviter.id if i.inviter else None) for i in convites
        }

    async def _carregar(self):
        dados = await carregar(ARQUIVO_CONVITES, {})
        if not isinstance(dados, dict):
            dados = {}
        servidor = dados.setdefault(str(GUILD_NEMESIS_ID), {})
        servidor.setdefault("_historico", {})
        servidor.setdefault("_membros", {})
        for uid, reg in servidor.items():
            if uid.startswith("_") or not isinstance(reg, dict):
                continue
            for mid in reg.get("membros", []):
                servidor["_historico"].setdefault(str(mid), uid)
        return dados, servidor

    async def _atualizar_painel(self, guild):
        # on_ready pode disparar novamente após reconexões. Serializar a
        # sincronização e persistir a mensagem evita criar um painel por evento.
        async with self._painel_lock:
            try:
                canal = guild.get_channel(CANAL_CONVITES_ID)
                if canal is None:
                    canal = await guild.fetch_channel(CANAL_CONVITES_ID)
                if not isinstance(canal, discord.TextChannel):
                    raise TypeError(
                        f"O canal {CANAL_CONVITES_ID} precisa ser um canal de texto."
                    )

                dados, servidor = await self._carregar()
                painel = None
                painel_id = servidor.get("_painel_message_id")
                if painel_id:
                    try:
                        painel = await canal.fetch_message(int(painel_id))
                        if painel.author.id != self.bot.user.id or not _mensagem_eh_painel_convites(painel):
                            painel = None
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                        painel = None

                encontrados = []
                # A varredura curta também remove duplicatas criadas antes da
                # persistência do ID, sem depender apenas do título do painel.
                async for mensagem in canal.history(limit=200, oldest_first=True):
                    if mensagem.author.id == self.bot.user.id and _mensagem_eh_painel_convites(mensagem):
                        encontrados.append(mensagem)
                if painel is None:
                    painel = next(
                        (item for item in encontrados if str(item.id) == str(painel_id)),
                        encontrados[0] if encontrados else None,
                    )
                elif all(item.id != painel.id for item in encontrados):
                    encontrados.append(painel)

                if painel is None:
                    painel = await canal.send(
                        view=PainelConsultaConvitesLayoutView(),
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    logger.info("Painel da Central de Convites publicado no canal %s (message=%s).", CANAL_CONVITES_ID, painel.id)
                else:
                    if not _componentes_contem_marcador(painel.components, "CENTRAL DE CONVITES"):
                        await painel.edit(content=None, embeds=[], attachments=[])
                        await painel.edit(
                            view=PainelConsultaConvitesLayoutView(),
                            allowed_mentions=discord.AllowedMentions.none(),
                        )
                    logger.info("Painel da Central de Convites sincronizado (message=%s).", painel.id)

                servidor["_painel_message_id"] = str(painel.id)
                await salvar(ARQUIVO_CONVITES, dados)

                # Remove cópias antigas, mantendo o painel canônico.
                for duplicada in encontrados:
                    if duplicada.id == painel.id:
                        continue
                    try:
                        await duplicada.delete()
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        logger.warning("Não foi possível remover painel duplicado de convites: %s", duplicada.id)
            except Exception:
                logger.exception(
                    "Falha ao publicar a Central de Convites no canal %s.",
                    CANAL_CONVITES_ID,
                )

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(GUILD_NEMESIS_ID)
        if guild is None:
            return
        if guild.id not in self._inicializados:
            cache = await self._buscar_convites(guild)
            if cache is not None:
                self._convites[guild.id] = cache
                self._inicializados.add(guild.id)
                await self._reconciliar(guild)
        await self._atualizar_painel(guild)

    async def _reconciliar(self, guild):
        try:
            presentes = {
                str(m.id) async for m in guild.fetch_members(limit=None) if not m.bot
            }
            async with self._locks[guild.id]:
                dados, servidor = await self._carregar()
                membros = servidor["_membros"]
                for mid, item in membros.items():
                    if isinstance(item, dict):
                        item["active"] = mid in presentes
                for uid, reg in servidor.items():
                    if uid.startswith("_") or not isinstance(reg, dict):
                        continue
                    ativos = {
                        mid
                        for mid, item in membros.items()
                        if isinstance(item, dict)
                        and str(item.get("inviter_id")) == uid
                        and item.get("active")
                    }
                    antigos = {
                        str(mid)
                        for mid in reg.get("membros", [])
                        if str(mid) in presentes and str(mid) not in membros
                    }
                    reg["membros"] = sorted(ativos | antigos)
                    reg["total"] = len(reg["membros"])
                await salvar(ARQUIVO_CONVITES, dados)
        except (discord.Forbidden, discord.HTTPException):
            logger.exception("Falha ao reconciliar convites ativos.")

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild and invite.guild.id == GUILD_NEMESIS_ID:
            async with self._locks[invite.guild.id]:
                self._convites.setdefault(invite.guild.id, {})[invite.code] = (
                    invite.uses or 0,
                    invite.inviter.id if invite.inviter else None,
                )

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild and invite.guild.id == GUILD_NEMESIS_ID:
            async with self._locks[invite.guild.id]:
                self._convites.setdefault(invite.guild.id, {}).pop(invite.code, None)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        if guild.id != GUILD_NEMESIS_ID or member.bot:
            return
        async with self._locks[guild.id]:
            dados, servidor = await self._carregar()
            hist, membros = servidor["_historico"], servidor["_membros"]
            mid = str(member.id)
            anterior = self._convites.get(guild.id)
            atual = await self._buscar_convites(guild)
            if atual is None:
                return
            self._convites[guild.id] = atual
            if hist.get(mid):
                item = membros.setdefault(
                    mid, {"inviter_id": str(hist[mid]), "legacy": True}
                )
                item.update(
                    active=True,
                    returned_at=datetime.now(timezone.utc).timestamp(),
                    member_name=member.display_name,
                )
                reg = servidor.setdefault(str(hist[mid]), {"total": 0, "membros": []})
                ativos = set(map(str, reg.get("membros", [])))
                ativos.add(mid)
                reg["membros"] = sorted(ativos)
                reg["total"] = len(ativos)
                await salvar(ARQUIVO_CONVITES, dados)
                return
            if anterior is None:
                return
            usados = [
                (code, info)
                for code, info in atual.items()
                if code in anterior and info[0] > anterior[code][0]
            ]
            if len(usados) != 1:
                logger.info(
                    "Convite não identificado com segurança: member=%s candidates=%s",
                    member.id,
                    len(usados),
                )
                return
            code, (_, inviter) = usados[0]
            if not inviter or inviter == member.id:
                return
            hist[mid] = str(inviter)
            membros[mid] = {
                "inviter_id": str(inviter),
                "code": code,
                "url": f"https://discord.gg/{code}",
                "joined_at": datetime.now(timezone.utc).timestamp(),
                "member_name": member.display_name,
                "active": True,
            }
            reg = servidor.setdefault(str(inviter), {"total": 0, "membros": []})
            ativos = set(map(str, reg.get("membros", [])))
            ativos.add(mid)
            reg["membros"] = sorted(ativos)
            reg["total"] = len(ativos)
            reg["ultimo_membro"] = member.id
            reg["ultimo_codigo"] = code
            await salvar(ARQUIVO_CONVITES, dados)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.guild.id != GUILD_NEMESIS_ID or member.bot:
            return
        async with self._locks[member.guild.id]:
            dados, servidor = await self._carregar()
            mid = str(member.id)
            item = servidor["_membros"].get(mid)
            if isinstance(item, dict):
                item.update(
                    active=False,
                    left_at=datetime.now(timezone.utc).timestamp(),
                    member_name=member.display_name,
                )
            inviter = servidor["_historico"].get(mid)
            if inviter:
                reg = servidor.setdefault(str(inviter), {"total": 0, "membros": []})
                ativos = set(map(str, reg.get("membros", [])))
                ativos.discard(mid)
                reg["membros"] = sorted(ativos)
                reg["total"] = len(ativos)
                await salvar(ARQUIVO_CONVITES, dados)


async def setup(bot):
    await bot.add_cog(ConvitesNemesis(bot))
