from __future__ import annotations
import asyncio, logging
from collections import defaultdict
from datetime import datetime, timezone
import discord
from discord.ext import commands
from utils.apresentacao import criar_embed
from utils.guild_config import membro_tem_lideranca
from utils.registro_global import obter_topico
from utils.storage import carregar, salvar

logger = logging.getLogger(__name__)
GUILD_NEMESIS_ID = 1563995879981981817
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
            await interaction.edit_original_response(
                content=None,
                embed=_embed(membro, servidor),
                view=VoltarConvitesView(
                    self.owner_id,
                    membro.id,
                    0,
                    _total_paginas(servidor, membro.id),
                ),
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
            await interaction.response.edit_message(
                embed=_embed(membro, servidor, self.pagina), view=self
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
            content="Selecione um integrante.",
            embed=None,
            view=SeletorConvitesView(self.owner_id),
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
        await interaction.response.send_message(
            embed=criar_embed(
                title="🔗 CENTRAL DE CONVITES",
                description="Selecione um integrante para consultar quantos convites trouxe, quais links foram utilizados e quem continua no servidor. Consulta individual, não é um ranking.",
                cor=0x991B33,
                rodape="NÊMESIS • REGISTRO GLOBAL • CONSULTA PRIVADA",
            ),
            view=SeletorConvitesView(interaction.user.id),
            ephemeral=True,
        )


class ConvitesNemesis(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._convites = {}
        self._locks = defaultdict(asyncio.Lock)
        self._inicializados = set()
        self.bot.add_view(PainelConsultaConvitesView())

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
        try:
            thread = await obter_topico(guild, "convites")
            if thread.archived or thread.locked:
                await thread.edit(archived=False, locked=False)
            msg = await thread.fetch_message(thread.id)
            await msg.edit(
                view=PainelConsultaConvitesView(),
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except Exception:
            logger.exception("Falha ao publicar painel de convites.")

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
