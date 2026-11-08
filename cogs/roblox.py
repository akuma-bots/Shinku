from utils.apresentacao import criar_embed, aplicar_identidade_servidor
import asyncio
import logging
import random
import string
from datetime import datetime, timezone
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.guild_config import (
    lideranca_only, membro_tem_lideranca,
    CARGOS_AUTORIZADOS_HIERARQUIA_IDS, CARGOS_LIDERANCA_IDS,
)
from utils.storage import carregar, salvar

ARQUIVO_VINCULOS = "roblox_vinculos.json"       # { guild_id: { discord_id: {roblox_id, roblox_username} } }
ARQUIVO_PENDENTES = "roblox_pendentes.json"     # { guild_id: { discord_id: {roblox_id, roblox_username, codigo} } }
ARQUIVO_GRUPO = "roblox_grupo_config.json"      # { guild_id: {"grupo_id": int, "mapeamentos": {rank_nome: cargo_id}} }

_LOG = logging.getLogger(__name__)
_ROBLOX_VINCULO_LOCK = asyncio.Lock()



ROBLOX_GRUPO_ID = 621286796
ROBLOX_GRUPO_URL = "https://www.roblox.com/pt/communities/621286796/Comunidade-Nik"
ROBLOX_CANAL_CENTRAL_ID = 1565825670066737202
ARQUIVO_PAINEL_ROBLOX = "roblox_painel_central.json"
ARQUIVO_HISTORICO_ROBLOX = "roblox_historico.json"

async def _buscar_dados_grupo(grupo_id: int = ROBLOX_GRUPO_ID) -> dict:
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"https://groups.roblox.com/v1/groups/{int(grupo_id)}") as resposta:
            resposta.raise_for_status()
            dados = await resposta.json()
    if not isinstance(dados, dict):
        raise ValueError("A API do grupo Roblox retornou dados inválidos.")
    return dados

class ModalVincularRoblox(discord.ui.Modal, title="Vincular conta Roblox"):
    usuario = discord.ui.TextInput(
        label="Nome de usuário Roblox",
        placeholder="Digite seu usuário Roblox",
        min_length=3,
        max_length=20,
    )

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.roblox_vincular(interaction, str(self.usuario.value).strip())


class ModalConfigurarGrupoRoblox(discord.ui.Modal, title="Configurar grupo Roblox"):
    grupo_id = discord.ui.TextInput(
        label="ID da comunidade Roblox",
        placeholder="Ex.: 621286796",
        min_length=1,
        max_length=20,
    )

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.roblox_configurar_grupo(interaction, str(self.grupo_id.value).strip())


class ModalMapearPatenteRoblox(discord.ui.Modal, title="Mapear patente Roblox"):
    patente = discord.ui.TextInput(
        label="Nome exato da patente no Roblox",
        placeholder="Digite como aparece no grupo Roblox",
        min_length=1,
        max_length=100,
    )

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        patente = str(self.patente.value).strip()
        if not patente:
            await interaction.response.send_message("Informe o nome da patente.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Selecione o cargo do Discord que corresponde à patente **{discord.utils.escape_markdown(patente)}**.",
            view=SeletorCargoRoblox(self.cog, patente),
            ephemeral=True,
        )


class SeletorCargoRoblox(discord.ui.View):
    def __init__(self, cog, patente: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.patente = patente
        seletor = discord.ui.RoleSelect(
            placeholder="Escolha o cargo correspondente",
            min_values=1,
            max_values=1,
            custom_id="nemesis:roblox:mapear_cargo",
        )
        seletor.callback = self.selecionar_cargo
        self.add_item(seletor)

    async def selecionar_cargo(self, interaction: discord.Interaction):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        cargo = interaction.data
        selecionados = next(
            (item for item in self.children if isinstance(item, discord.ui.RoleSelect)),
            None,
        )
        if selecionados is None or not selecionados.values:
            await interaction.response.send_message("Selecione um cargo válido.", ephemeral=True)
            return
        cargo = selecionados.values[0]
        bot_member = interaction.guild.me
        if cargo.is_default() or cargo.managed:
            await interaction.response.send_message("Esse cargo não pode ser usado no mapeamento.", ephemeral=True)
            return
        if bot_member is None or cargo >= bot_member.top_role:
            await interaction.response.send_message(
                "Não consigo atribuir esse cargo. Coloque o cargo do bot acima dele na hierarquia.",
                ephemeral=True,
            )
            return
        if cargo.id in (CARGOS_AUTORIZADOS_HIERARQUIA_IDS | CARGOS_LIDERANCA_IDS):
            await interaction.response.send_message(
                "Cargos administrativos da NÊMESIS não podem ser concedidos por patente Roblox.",
                ephemeral=True,
            )
            return
        await self.cog.salvar_mapeamento_roblox(interaction, self.patente, cargo)


class SeletorRemoverPatenteRoblox(discord.ui.View):
    def __init__(self, cog, mapeamentos: dict):
        super().__init__(timeout=180)
        self.cog = cog
        opcoes = [
            discord.SelectOption(label=str(patente)[:100], value=str(patente)[:100], description="Remover a associação desta patente")
            for patente in list(mapeamentos.keys())[:25]
        ]
        seletor = discord.ui.Select(
            placeholder="Selecione a patente que deseja remover",
            min_values=1,
            max_values=1,
            options=opcoes,
        )
        seletor.callback = self.remover
        self.add_item(seletor)

    async def remover(self, interaction: discord.Interaction):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        seletor = next((item for item in self.children if isinstance(item, discord.ui.Select)), None)
        if seletor is None or not seletor.values:
            await interaction.response.send_message("Selecione uma patente válida.", ephemeral=True)
            return
        await self.cog.roblox_remover_mapeamento(interaction, seletor.values[0])


class CentralAdministrativaRobloxView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.button(label="Configurar grupo", style=discord.ButtonStyle.primary, emoji="🌐", row=0)
    async def configurar_grupo(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        await interaction.response.send_modal(ModalConfigurarGrupoRoblox(self.cog))

    @discord.ui.button(label="Mapear patente", style=discord.ButtonStyle.success, emoji="🎖️", row=0)
    async def mapear_patente(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        await interaction.response.send_modal(ModalMapearPatenteRoblox(self.cog))

    @discord.ui.button(label="Remover mapeamento", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def remover_patente(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        config = await _config_grupo(interaction.guild.id)
        if not config["mapeamentos"]:
            await interaction.response.send_message("Ainda não existem patentes mapeadas.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Escolha qual associação deseja remover.",
            view=SeletorRemoverPatenteRoblox(self.cog, config["mapeamentos"]),
            ephemeral=True,
        )

    @discord.ui.button(label="Ver mapeamentos", style=discord.ButtonStyle.secondary, emoji="📋", row=1)
    async def ver_mapeamentos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        await self.cog.roblox_mapeamentos(interaction)

    @discord.ui.button(label="Sincronizar membros", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def sincronizar_membros(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        await self.cog.roblox_sincronizar(interaction)

    @discord.ui.button(label="Histórico", style=discord.ButtonStyle.secondary, emoji="🕘", row=1)
    async def historico(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        await self.cog.roblox_historico(interaction)


class CentralRobloxView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(discord.ui.Button(label="Acessar comunidade", style=discord.ButtonStyle.link, url=ROBLOX_GRUPO_URL, emoji="🌐"))

    @discord.ui.button(label="Vincular minha conta", style=discord.ButtonStyle.primary, custom_id="nemesis:roblox:vincular", emoji="🔗")
    async def vincular_conta(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalVincularRoblox(self.cog))

    @discord.ui.button(label="Confirmar vínculo", style=discord.ButtonStyle.success, custom_id="nemesis:roblox:confirmar", emoji="✅")
    async def confirmar_conta(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.roblox_confirmar(interaction)

    @discord.ui.button(label="Verificar participação", style=discord.ButtonStyle.secondary, custom_id="nemesis:roblox:participacao", emoji="🛡️")
    async def verificar_participacao(self, interaction: discord.Interaction, button: discord.ui.Button):
        vinculos = await carregar(ARQUIVO_VINCULOS, {})
        vinculo = (vinculos.get(str(interaction.guild_id), {}) or {}).get(str(interaction.user.id))
        if not isinstance(vinculo, dict) or not vinculo.get("roblox_id"):
            await interaction.response.send_message(
                "Sua conta ainda não está vinculada. Use **Vincular minha conta** primeiro.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        try:
            config_grupo = await _config_grupo(interaction.guild_id)
            grupo_id = config_grupo["grupo_id"] or ROBLOX_GRUPO_ID
            rank = await _buscar_rank_no_grupo(int(vinculo["roblox_id"]), grupo_id)
            if rank:
                embed = criar_embed(
                    title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ VERIFICAÇÃO ROBLOX",
                    description=(
                        "Sua conta vinculada foi encontrada na comunidade oficial.\n\n"
                        f"**Conta:** [{vinculo.get('roblox_username', 'Roblox')}]"
                        f"(https://www.roblox.com/users/{int(vinculo['roblox_id'])}/profile)\n"
                        f"**Participação:** Confirmada\n**Rank no grupo:** {rank}\n"
                        f"**Comunidade:** [Acessar grupo]({ROBLOX_GRUPO_URL})"
                    ),
                    color=0x2E8B57,
                )
            else:
                embed = criar_embed(
                    title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ VERIFICAÇÃO ROBLOX",
                    description=(
                        "A conta está vinculada, mas não foi encontrada como membro da comunidade oficial.\n\n"
                        f"**Conta:** {vinculo.get('roblox_username', 'Roblox')}\n"
                        "**Participação:** Não confirmada\n"
                        f"**Próximo passo:** [Entrar na comunidade]({ROBLOX_GRUPO_URL})"
                    ),
                    color=0xB8860B,
                )
            await interaction.followup.send(embed=embed, ephemeral=True)
        except (aiohttp.ClientError, ValueError, TypeError):
            _LOG.exception("Falha ao verificar participação no grupo Roblox.")
            await interaction.followup.send(
                "Não foi possível consultar o grupo Roblox agora. Tente novamente em alguns instantes.",
                ephemeral=True,
            )

    @discord.ui.button(label="Administração", style=discord.ButtonStyle.secondary, custom_id="nemesis:roblox:admin", emoji="⚙️", row=1)
    async def administrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.exigir_administracao_roblox(interaction):
            return
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ ADMINISTRAÇÃO ROBLOX",
            description=(
                "**Configuração da comunidade**\nDefina o grupo Roblox oficial.\n\n"
                "**Patentes e cargos**\nAssocie cada patente Roblox ao cargo equivalente do Discord.\n\n"
                "**Manutenção**\nConsulte associações, remova mapeamentos e sincronize os membros vinculados."
            ),
            color=0xB3132B,
        )
        await interaction.response.send_message(
            embed=embed,
            view=CentralAdministrativaRobloxView(self.cog),
            ephemeral=True,
        )

    @discord.ui.button(label="Meu perfil Roblox", style=discord.ButtonStyle.secondary, custom_id="nemesis:roblox:perfil", emoji="👤")
    async def meu_perfil(self, interaction: discord.Interaction, button: discord.ui.Button):
        vinculos = await carregar(ARQUIVO_VINCULOS, {})
        vinculo = (vinculos.get(str(interaction.guild_id), {}) or {}).get(str(interaction.user.id))
        if not isinstance(vinculo, dict):
            await interaction.response.send_message("Sua conta ainda não está vinculada. Use o botão de vinculação para começar.", ephemeral=True)
            return
        rid = int(vinculo["roblox_id"])
        embed = criar_embed(title="NÊMESIS • PERFIL ROBLOX", description=f"**Usuário:** {vinculo.get('roblox_username', 'Não informado')}\n**Perfil:** https://www.roblox.com/users/{rid}/profile\n**Comunidade:** [Abrir grupo oficial]({ROBLOX_GRUPO_URL})", color=0xB3132B)
        try:
            config_grupo = await _config_grupo(interaction.guild_id)
            grupo_id = config_grupo["grupo_id"] or ROBLOX_GRUPO_ID
            rank = await _buscar_rank_no_grupo(rid, grupo_id)
            embed.add_field(
                name="COMUNIDADE NÊMESIS",
                value=f"Participação confirmada — **{rank}**" if rank else "Não encontrado como membro do grupo",
                inline=False,
            )
        except (aiohttp.ClientError, ValueError, TypeError):
            embed.add_field(name="COMUNIDADE NÊMESIS", value="Não foi possível consultar agora", inline=False)
        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={rid}&width=150&height=150&format=png")
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def _buscar_usuario_roblox(nome_usuario: str):
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [nome_usuario], "excludeBannedUsers": False},
        ) as resposta:
            resposta.raise_for_status()
            dados = await resposta.json()
    if not isinstance(dados, dict):
        raise ValueError("A API do Roblox retornou uma resposta inválida.")
    resultados = dados.get("data", [])
    return resultados[0] if isinstance(resultados, list) and resultados else None


async def _buscar_descricao_roblox(roblox_id: int) -> str:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"https://users.roblox.com/v1/users/{int(roblox_id)}") as resposta:
            resposta.raise_for_status()
            dados = await resposta.json()
    if not isinstance(dados, dict):
        raise ValueError("A API do Roblox retornou uma resposta inválida.")
    return dados.get("description", "") or ""


async def _buscar_grupos_roblox(roblox_id: int) -> list:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"https://groups.roblox.com/v2/users/{int(roblox_id)}/groups/roles") as resposta:
            resposta.raise_for_status()
            dados = await resposta.json()
    if not isinstance(dados, dict):
        raise ValueError("A API de grupos do Roblox retornou uma resposta inválida.")
    grupos = dados.get("data", [])
    return grupos if isinstance(grupos, list) else []


async def _buscar_rank_no_grupo(roblox_id: int, grupo_id: int):
    """Devolve o nome do cargo (rank) da pessoa dentro do grupo configurado,
    ou None se ela não estiver no grupo."""
    grupos = await _buscar_grupos_roblox(roblox_id)
    for entrada in grupos:
        if not isinstance(entrada, dict):
            continue
        grupo = entrada.get("group")
        cargo = entrada.get("role")
        if not isinstance(grupo, dict) or not isinstance(cargo, dict):
            continue
        try:
            corresponde = int(grupo.get("id")) == int(grupo_id)
        except (TypeError, ValueError, OverflowError):
            continue
        nome = cargo.get("name")
        if corresponde and isinstance(nome, str) and nome.strip():
            return nome.strip()
    return None


async def _config_grupo(guild_id: int) -> dict:
    todos = await carregar(ARQUIVO_GRUPO, {})
    if not isinstance(todos, dict):
        todos = {}
    config = todos.get(str(guild_id), {})
    if not isinstance(config, dict):
        config = {}
    grupo_id = config.get("grupo_id") or ROBLOX_GRUPO_ID
    try:
        grupo_id = int(grupo_id) if grupo_id not in (None, "") else None
    except (TypeError, ValueError, OverflowError):
        grupo_id = None
    mapeamentos = config.get("mapeamentos", {})
    if not isinstance(mapeamentos, dict):
        mapeamentos = {}
    normalizados = {}
    for rank, cargo_id in mapeamentos.items():
        try:
            cargo_id = int(cargo_id)
        except (TypeError, ValueError, OverflowError):
            continue
        nome_rank = str(rank or "").strip()
        if nome_rank:
            normalizados[nome_rank] = cargo_id
    return {"grupo_id": grupo_id, "mapeamentos": normalizados}


async def sincronizar_cargo_membro(guild: discord.Guild, membro: discord.Member, roblox_id: int) -> str:
    """Ajusta os cargos de rank do membro pra bater com o rank atual dele no
    grupo Roblox configurado. Devolve um texto curto dizendo o que aconteceu."""
    config = await _config_grupo(guild.id)
    grupo_id = config["grupo_id"]
    mapeamentos = config["mapeamentos"]
    if not grupo_id or not mapeamentos:
        return "Nenhum grupo/mapeamento de cargo configurado neste servidor."

    try:
        rank_atual = await _buscar_rank_no_grupo(roblox_id, grupo_id)
    except (aiohttp.ClientError, ValueError) as e:
        return f"Erro ao consultar a API do Roblox: {e}"

    cargo_id_correto = mapeamentos.get(rank_atual) if rank_atual else None
    ids_gerenciados = set(mapeamentos.values())

    # Uma patente ainda não mapeada não deve retirar cargos válidos do membro.
    if rank_atual and cargo_id_correto is None:
        return f"Patente **{rank_atual}** identificada, mas ainda sem cargo correspondente configurado."

    cargos_pra_remover = [
        cargo for cargo in membro.roles
        if cargo.id in ids_gerenciados and cargo.id != cargo_id_correto
    ]
    cargo_pra_adicionar = None
    if cargo_id_correto and not any(c.id == cargo_id_correto for c in membro.roles):
        cargo_pra_adicionar = guild.get_role(cargo_id_correto)
        if cargo_pra_adicionar is None:
            return f"O cargo configurado para **{rank_atual}** não existe mais no Discord. Revise o mapeamento."

    try:
        # Primeiro concede o cargo correto; só depois remove as patentes antigas.
        # Assim, uma falha ao adicionar não deixa o membro sem patente no Discord.
        if cargo_pra_adicionar:
            await membro.add_roles(cargo_pra_adicionar, reason="Sincronização de rank do Roblox")
        if cargos_pra_remover:
            await membro.remove_roles(*cargos_pra_remover, reason="Sincronização de rank do Roblox")
    except discord.Forbidden:
        return "Sem permissão pra ajustar os cargos (verifique a hierarquia de cargos do bot)."

    if not rank_atual:
        return "A pessoa não está mais no grupo Roblox — cargos de rank removidos."
    if cargo_pra_adicionar:
        return f"Cargo atualizado pra **{rank_atual}**."
    return f"Já estava correto (**{rank_atual}**)."


async def _registrar_evento_roblox(
    guild: discord.Guild,
    titulo: str,
    descricao: str,
    user_id: int | None = None,
) -> None:
    from utils.registro_global import registrar as registrar_global
    await registrar_global(guild, "roblox", titulo, descricao, cor=0xB3132B)
    if user_id is not None:
        await registrar_global(
            guild,
            "historico_membros",
            titulo,
            f"**Membro:** <@{user_id}> (ID: {user_id})\n{descricao}",
            cor=0xB3132B,
        )


class Roblox(commands.Cog):
    """Verificação e vínculo de conta Roblox, com sincronização automática de
    cargo por rank do grupo Roblox da gangue — quem sobe/desce de patente no
    jogo, sobe/desce de cargo no Discord sozinho."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sincronizacao_automatica.start()

    def cog_unload(self):
        self.sincronizacao_automatica.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Cria ou atualiza um único painel público da comunidade Roblox."""
        if getattr(self, "_painel_roblox_sync", False):
            return
        self._painel_roblox_sync = True
        try:
            canal = self.bot.get_channel(ROBLOX_CANAL_CENTRAL_ID)
            if canal is None:
                canal = await self.bot.fetch_channel(ROBLOX_CANAL_CENTRAL_ID)
            if not isinstance(canal, discord.TextChannel):
                _LOG.error("Canal configurado para a central Roblox não é um canal de texto.")
                return
            embed = criar_embed(title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ CENTRAL ROBLOX", description="Acesse a comunidade oficial da NÊMESIS no Roblox e conecte sua conta ao Discord.\n\n**Comunidade:** [Comunidade Nik](" + ROBLOX_GRUPO_URL + ")\n**ID do grupo:** `" + str(ROBLOX_GRUPO_ID) + "`\n\n**Vinculação segura**\nA confirmação utiliza um código temporário na descrição do perfil Roblox. O bot nunca solicita senha ou cookie.", color=0xB3132B)
            aplicar_identidade_servidor(embed, canal.guild, self.bot)
            try:
                config_grupo = await _config_grupo(canal.guild.id)
                grupo_id_painel = config_grupo["grupo_id"] or ROBLOX_GRUPO_ID
                dados = await _buscar_dados_grupo(grupo_id_painel)
                nome = str(dados.get("name") or "Comunidade Roblox")[:100]
                membros = dados.get("memberCount")
                valor = "**" + nome + "**"
                if isinstance(membros, int):
                    valor += "\n**" + format(membros, ",") + "** membros\n"
                embed.add_field(name="GRUPO OFICIAL", value=valor + f"\nID: `{grupo_id_painel}`", inline=True)
                owner = dados.get("owner") or {}
                owner_name = owner.get("username") if isinstance(owner, dict) else None
                if owner_name:
                    embed.add_field(name="PROPRIETÁRIO", value=str(owner_name)[:100], inline=True)
                if dados.get("hasVerifiedBadge") is True:
                    embed.add_field(name="STATUS", value="Comunidade verificada pelo Roblox", inline=True)
                descricao = str(dados.get("description") or "").strip()
                if descricao:
                    embed.add_field(name="SOBRE A COMUNIDADE", value=descricao[:900], inline=False)
            except (aiohttp.ClientError, ValueError, TypeError):
                _LOG.exception("Falha ao consultar dados públicos do grupo Roblox.")
                embed.add_field(name="GRUPO OFICIAL", value="[Abrir Comunidade Nik](" + ROBLOX_GRUPO_URL + ")", inline=True)
            estado = await carregar(ARQUIVO_PAINEL_ROBLOX, {})
            if not isinstance(estado, dict):
                estado = {}
            registro = estado.get(str(canal.guild.id), {})
            mensagem = None
            if isinstance(registro, dict) and registro.get("message_id"):
                try:
                    mensagem = await canal.fetch_message(int(registro["message_id"]))
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    mensagem = None
            view = CentralRobloxView(self)
            if mensagem:
                await mensagem.edit(embed=embed, view=view)
            else:
                mensagem = await canal.send(embed=embed, view=view)
            estado[str(canal.guild.id)] = {"channel_id": canal.id, "message_id": mensagem.id}
            await salvar(ARQUIVO_PAINEL_ROBLOX, estado)
            self.bot.add_view(CentralRobloxView(self))
            _LOG.info("Central Roblox atualizada no canal %s (mensagem %s).", canal.id, mensagem.id)
        except Exception:
            _LOG.exception("Falha ao publicar/atualizar a Central Roblox.")
        finally:
            self._painel_roblox_sync = False

    async def exigir_administracao_roblox(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not membro_tem_lideranca(interaction.user):
            mensagem = "Esta área é restrita à administração da NÊMESIS."
            if interaction.response.is_done():
                await interaction.followup.send(mensagem, ephemeral=True)
            else:
                await interaction.response.send_message(mensagem, ephemeral=True)
            return False
        return True

    async def salvar_mapeamento_roblox(self, interaction: discord.Interaction, patente: str, cargo: discord.Role):
        todos = await carregar(ARQUIVO_GRUPO, {})
        if not isinstance(todos, dict):
            todos = {}
        atual = todos.get(str(interaction.guild.id), {})
        if not isinstance(atual, dict):
            atual = {}
        grupo_id = atual.get("grupo_id") or ROBLOX_GRUPO_ID
        mapeamentos = atual.get("mapeamentos", {})
        if not isinstance(mapeamentos, dict):
            mapeamentos = {}
        mapeamentos[patente] = cargo.id
        atual["grupo_id"] = int(grupo_id)
        atual["mapeamentos"] = mapeamentos
        todos[str(interaction.guild.id)] = atual
        await salvar(ARQUIVO_GRUPO, todos)
        await _registrar_evento_roblox(
            interaction.guild,
            "Mapeamento de patente Roblox atualizado",
            f"**Patente:** {patente}\n**Cargo Discord:** {cargo.mention}\n**Responsável:** {interaction.user.mention}",
            interaction.user.id,
        )
        await interaction.response.edit_message(
            content=f"✅ A patente **{discord.utils.escape_markdown(patente)}** agora corresponde ao cargo {cargo.mention}.",
            view=None,
        )

    # ---------------- Verificação de conta ----------------

    async def roblox_vincular(self, interaction: discord.Interaction, usuario_roblox: str):
        await interaction.response.defer(ephemeral=True)

        try:
            usuario = await _buscar_usuario_roblox(usuario_roblox)
        except (aiohttp.ClientError, ValueError) as e:
            await interaction.followup.send("A API do Roblox está indisponível ou retornou dados inválidos. Tente novamente mais tarde.", ephemeral=True)
            return

        if not usuario:
            await interaction.followup.send("Não achei esse usuário no Roblox. Confere se digitou certo.", ephemeral=True)
            return

        codigo = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))

        pendentes = await carregar(ARQUIVO_PENDENTES, {})
        guild_dados = pendentes.setdefault(str(interaction.guild.id), {})
        guild_dados[str(interaction.user.id)] = {
            "roblox_id": usuario["id"],
            "roblox_username": usuario["name"],
            "codigo": codigo,
        }
        await salvar(ARQUIVO_PENDENTES, pendentes)

        await interaction.followup.send(
            f"Quase lá! Vai em **roblox.com → seu perfil → Editar → About/Sobre mim** e cola este código "
            f"em qualquer lugar da descrição:\n\n**`{codigo}`**\n\n"
            "Depois de salvar, volte à Central Roblox e pressione **Confirmar vínculo**. Depois de confirmado, pode apagar o código.",
            ephemeral=True,
        )

    async def roblox_confirmar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        pendentes = await carregar(ARQUIVO_PENDENTES, {})
        pendente = pendentes.get(str(interaction.guild.id), {}).get(str(interaction.user.id))
        if not pendente:
            await interaction.followup.send("Você não tem nenhuma verificação pendente. Pressione **Vincular minha conta** na Central Roblox primeiro.", ephemeral=True)
            return

        try:
            descricao = await _buscar_descricao_roblox(pendente["roblox_id"])
        except (aiohttp.ClientError, ValueError) as e:
            await interaction.followup.send("A API do Roblox está indisponível ou retornou dados inválidos. Tente novamente mais tarde.", ephemeral=True)
            return

        if pendente["codigo"] not in descricao:
            await interaction.followup.send(
                "Não encontrei o código na descrição do seu perfil ainda. Confere se salvou certinho e tenta de novo "
                "(pode levar um minutinho pra atualizar no Roblox).",
                ephemeral=True,
            )
            return

        async with _ROBLOX_VINCULO_LOCK:
            # Recarrega os dois arquivos dentro do lock para impedir que duas
            # confirmações simultâneas vinculem a mesma conta Roblox.
            vinculos = await carregar(ARQUIVO_VINCULOS, {})
            pendentes = await carregar(ARQUIVO_PENDENTES, {})
            if not isinstance(vinculos, dict):
                vinculos = {}
            if not isinstance(pendentes, dict):
                pendentes = {}
            guild_pendentes = pendentes.get(str(interaction.guild.id), {})
            if not isinstance(guild_pendentes, dict):
                guild_pendentes = {}
            pendente_atual = guild_pendentes.get(str(interaction.user.id))
            if not isinstance(pendente_atual, dict) or str(pendente_atual.get("codigo")) != str(pendente.get("codigo")):
                await interaction.followup.send(
                    "Esta verificação já foi processada ou substituída. Inicie uma nova vinculação pela Central Roblox.",
                    ephemeral=True,
                )
                return

            guild_dados = vinculos.get(str(interaction.guild.id), {})
            if not isinstance(guild_dados, dict):
                guild_dados = {}
            roblox_id = int(pendente_atual["roblox_id"])
            vinculo_existente = next(
                (
                    discord_id
                    for discord_id, dados in guild_dados.items()
                    if str(discord_id) != str(interaction.user.id)
                    and isinstance(dados, dict)
                    and str(dados.get("roblox_id")) == str(roblox_id)
                ),
                None,
            )
            if vinculo_existente is not None:
                await interaction.followup.send(
                    "Esta conta Roblox já está vinculada a outro perfil Discord da NÊMESIS. "
                    "Se você acredita que houve um erro, abra um ticket para a staff verificar.",
                    ephemeral=True,
                )
                return

            guild_dados[str(interaction.user.id)] = {
                "roblox_id": roblox_id,
                "roblox_username": str(pendente_atual.get("roblox_username") or pendente.get("roblox_username") or ""),
            }
            vinculos[str(interaction.guild.id)] = guild_dados
            await salvar(ARQUIVO_VINCULOS, vinculos)

            guild_pendentes.pop(str(interaction.user.id), None)
            pendentes[str(interaction.guild.id)] = guild_pendentes
            await salvar(ARQUIVO_PENDENTES, pendentes)
            pendente = pendente_atual

        mensagem = f"✅ Verificado! Sua conta Discord agora está vinculada a **{pendente['roblox_username']}** no Roblox."

        # já aproveita e sincroniza o cargo de rank na hora, se estiver configurado
        resultado_sync = await sincronizar_cargo_membro(interaction.guild, interaction.user, pendente["roblox_id"])
        if "Nenhum grupo" not in resultado_sync:
            mensagem += f"\n🎖️ {resultado_sync}"

        await _registrar_evento_roblox(
            interaction.guild,
            "Conta Roblox vinculada",
            (
                f"**Conta Roblox:** {pendente['roblox_username']} (ID: {pendente['roblox_id']})\n"
                f"**Membro Discord:** <@{interaction.user.id}>\n"
                f"**Sincronização de cargo:** {resultado_sync}"
            ),
            interaction.user.id,
        )
        await interaction.followup.send(mensagem, ephemeral=True)

    async def roblox_desvincular(self, interaction: discord.Interaction):
        vinculos = await carregar(ARQUIVO_VINCULOS, {})
        guild_dados = vinculos.get(str(interaction.guild.id), {})
        vinculo_removido = guild_dados.pop(str(interaction.user.id), None)
        if vinculo_removido is None:
            await interaction.response.send_message("Você não tem nenhuma conta Roblox vinculada.", ephemeral=True)
            return
        await salvar(ARQUIVO_VINCULOS, vinculos)
        await _registrar_evento_roblox(
            interaction.guild,
            "Conta Roblox desvinculada",
            f"**Conta Roblox:** {vinculo_removido.get('roblox_username', 'Não informado')} (ID: {vinculo_removido.get('roblox_id', '—')})",
            interaction.user.id,
        )
        await interaction.response.send_message("🔓 Vínculo removido.", ephemeral=True)

    async def roblox_perfil(self, interaction: discord.Interaction, membro: discord.Member = None):
        alvo = membro or interaction.user
        vinculos = await carregar(ARQUIVO_VINCULOS, {})
        vinculo = vinculos.get(str(interaction.guild.id), {}).get(str(alvo.id))

        if not vinculo:
            await interaction.response.send_message(f"{alvo.mention} não tem conta Roblox vinculada.", ephemeral=True)
            return

        await interaction.response.defer()
        embed = criar_embed(title=f"🎮 Roblox de {alvo.display_name}", color=0x00A2FF)
        embed.add_field(name="Usuário", value=vinculo["roblox_username"], inline=True)
        embed.add_field(name="Perfil", value=f"https://www.roblox.com/users/{vinculo['roblox_id']}/profile", inline=False)

        try:
            grupos = await _buscar_grupos_roblox(vinculo["roblox_id"])
            if grupos:
                principais = ", ".join(g["group"]["name"] for g in grupos[:5])
                embed.add_field(name="Grupos", value=principais, inline=False)
        except aiohttp.ClientError:
            pass

        embed.set_thumbnail(url=f"https://www.roblox.com/headshot-thumbnail/image?userId={vinculo['roblox_id']}&width=150&height=150&format=png")
        await interaction.followup.send(embed=embed)

    async def roblox_identificar(self, interaction: discord.Interaction, usuario_roblox: str):
        if interaction.guild is None:
            await interaction.response.send_message(
                "Use este comando dentro do servidor da NÊMESIS.", ephemeral=True
            )
            return

        vinculos = await carregar(ARQUIVO_VINCULOS, {})
        guild_dados = vinculos.get(str(interaction.guild.id), {})
        procurado = usuario_roblox.strip().casefold()
        encontrado = next(
            (
                (discord_id, dados)
                for discord_id, dados in guild_dados.items()
                if isinstance(dados, dict)
                and str(dados.get("roblox_username", "")).casefold() == procurado
            ),
            None,
        )
        if encontrado is None:
            await interaction.response.send_message(
                "Não encontrei esse nome entre as contas Roblox verificadas da NÊMESIS.",
                ephemeral=True,
            )
            return

        discord_id, dados = encontrado
        membro = interaction.guild.get_member(int(discord_id))
        nome_membro = membro.mention if membro else f"ID Discord: {discord_id}"
        roblox_id = int(dados["roblox_id"])
        embed = criar_embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ IDENTIFICAÇÃO ROBLOX",
            description=f"Conta Roblox: {dados['roblox_username']} (https://www.roblox.com/users/{roblox_id}/profile)\nMembro Discord: {nome_membro}",
            color=0xB3132B,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------------- Cargo automático por rank do grupo ----------------

    async def roblox_configurar_grupo(self, interaction: discord.Interaction, grupo_id: str):
        if not await self.exigir_administracao_roblox(interaction):
            return
        if not grupo_id.isdigit():
            await interaction.response.send_message("O ID do grupo precisa ser só números.", ephemeral=True)
            return
        todos = await carregar(ARQUIVO_GRUPO, {})
        atual = todos.get(str(interaction.guild.id), {"grupo_id": None, "mapeamentos": {}})
        atual["grupo_id"] = int(grupo_id)
        todos[str(interaction.guild.id)] = atual
        await salvar(ARQUIVO_GRUPO, todos)
        await interaction.response.send_message(
            f"✅ Grupo Roblox configurado (ID `{grupo_id}`).",
            ephemeral=True,
        )

    async def roblox_mapear_cargo(self, interaction: discord.Interaction, rank_roblox: str, cargo_discord: discord.Role):
        if cargo_discord >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "⚠️ Esse cargo está acima (ou igual) ao meu cargo mais alto — eu não vou conseguir atribuir ele. "
                "Suba meu cargo na lista de cargos do servidor e tente de novo.",
                ephemeral=True,
            )
            return

        todos = await carregar(ARQUIVO_GRUPO, {})
        atual = todos.get(str(interaction.guild.id), {"grupo_id": None, "mapeamentos": {}})
        if not atual["grupo_id"]:
            await interaction.response.send_message("Configure o grupo primeiro pela área administrativa Roblox.", ephemeral=True)
            return
        atual["mapeamentos"][rank_roblox] = cargo_discord.id
        todos[str(interaction.guild.id)] = atual
        await salvar(ARQUIVO_GRUPO, todos)
        await interaction.response.send_message(f"✅ Rank **{rank_roblox}** agora dá o cargo {cargo_discord.mention} automaticamente.", ephemeral=True)

    async def roblox_remover_mapeamento(self, interaction: discord.Interaction, rank_roblox: str):
        todos = await carregar(ARQUIVO_GRUPO, {})
        atual = todos.get(str(interaction.guild.id), {"grupo_id": None, "mapeamentos": {}})
        if atual["mapeamentos"].pop(rank_roblox, None) is None:
            await interaction.response.send_message("Não achei esse rank mapeado.", ephemeral=True)
            return
        todos[str(interaction.guild.id)] = atual
        await salvar(ARQUIVO_GRUPO, todos)
        await interaction.response.send_message(f"🗑️ Mapeamento de **{rank_roblox}** removido.", ephemeral=True)

    async def roblox_mapeamentos(self, interaction: discord.Interaction):
        config = await _config_grupo(interaction.guild.id)
        if not config["grupo_id"]:
            await interaction.response.send_message("Nenhum grupo Roblox configurado ainda.", ephemeral=True)
            return
        linhas = [f"**{rank}** → <@&{cargo_id}>" for rank, cargo_id in config["mapeamentos"].items()]
        texto = "\n".join(linhas) if linhas else "Nenhum rank mapeado ainda."
        embed = criar_embed(title="🎮 Sincronização de cargos por rank", description=f"Grupo: `{config['grupo_id']}`\n\n{texto}", color=0x00A2FF)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def roblox_sincronizar(self, interaction: discord.Interaction, membro: discord.Member = None):
        if not await self.exigir_administracao_roblox(interaction):
            return
        await interaction.response.defer(ephemeral=True)
        vinculos = await carregar(ARQUIVO_VINCULOS, {})
        guild_vinculos = vinculos.get(str(interaction.guild.id), {})

        if membro:
            vinculo = guild_vinculos.get(str(membro.id))
            if not vinculo:
                await interaction.followup.send(f"{membro.mention} não tem conta Roblox vinculada.", ephemeral=True)
                return
            resultado = await sincronizar_cargo_membro(interaction.guild, membro, vinculo["roblox_id"])
            await interaction.followup.send(f"{membro.mention}: {resultado}", ephemeral=True)
            return

        atualizados = 0
        for discord_id, vinculo in guild_vinculos.items():
            membro_obj = interaction.guild.get_member(int(discord_id))
            if membro_obj:
                await sincronizar_cargo_membro(interaction.guild, membro_obj, vinculo["roblox_id"])
                atualizados += 1
        await interaction.followup.send(f"✅ Sincronização concluída pra {atualizados} membro(s) vinculado(s).", ephemeral=True)

    async def roblox_historico(self, interaction: discord.Interaction):
        if not await self.exigir_administracao_roblox(interaction):
            return
        historico = await carregar(ARQUIVO_HISTORICO_ROBLOX, {})
        eventos = historico.get(str(interaction.guild.id), []) if isinstance(historico, dict) else []
        if not isinstance(eventos, list) or not eventos:
            await interaction.response.send_message("Ainda não há alterações registradas. O histórico começa a ser preenchido nas verificações automáticas.", ephemeral=True)
            return
        linhas = []
        for evento in reversed(eventos[-12:]):
            if not isinstance(evento, dict):
                continue
            tipo = str(evento.get("tipo", "atualização")).replace("_", " ").title()
            nome = discord.utils.escape_markdown(str(evento.get("roblox_username") or "Conta Roblox"))
            discord_id = evento.get("discord_id")
            membro = f"<@{discord_id}>" if str(discord_id or "").isdigit() else "Membro não identificado"
            anterior = evento.get("rank_anterior") or "—"
            atual = evento.get("rank_atual") or "—"
            quando = str(evento.get("quando") or "")
            try:
                data = datetime.fromisoformat(quando)
                timestamp = int(data.timestamp())
                data_texto = f"<t:{timestamp}:R>"
            except (TypeError, ValueError, OverflowError):
                data_texto = "data indisponível"
            linhas.append(f"**{tipo}** · {nome}\n{membro} · `{anterior}` → `{atual}`\n{data_texto}")
        embed = criar_embed(title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒 ━ HISTÓRICO ROBLOX", description="\n\n".join(linhas)[:3900] or "Nenhum evento válido encontrado.", color=0xB3132B)
        embed.set_footer(text="Últimas 12 alterações • Verificação automática a cada 30 minutos")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    @tasks.loop(minutes=30)
    async def sincronizacao_automatica(self):
        import logging
        logger = logging.getLogger(__name__)
        try:
            vinculos = await carregar(ARQUIVO_VINCULOS, {})
        except Exception:
            logger.exception("Falha ao carregar vínculos Roblox; sincronização será repetida no próximo ciclo.")
            return

        if not isinstance(vinculos, dict):
            logger.error("Arquivo de vínculos Roblox possui formato inválido.")
            return

        for guild in self.bot.guilds:
            try:
                config = await _config_grupo(guild.id)
                if not config["grupo_id"]:
                    continue
                guild_vinculos = vinculos.get(str(guild.id), {})
                if not isinstance(guild_vinculos, dict):
                    logger.error("Vínculos Roblox inválidos (guild=%s).", guild.id)
                    continue

                for discord_id, vinculo in guild_vinculos.items():
                    try:
                        membro = guild.get_member(int(discord_id))
                        if not membro or not isinstance(vinculo, dict) or not vinculo.get("roblox_id"):
                            continue
                        roblox_id = int(vinculo["roblox_id"])
                        rank_atual = await _buscar_rank_no_grupo(roblox_id, config["grupo_id"])
                        historico = await carregar(ARQUIVO_HISTORICO_ROBLOX, {})
                        if not isinstance(historico, dict):
                            historico = {}
                        eventos = historico.get(str(guild.id), [])
                        if not isinstance(eventos, list):
                            eventos = []
                        estado_anterior = next((
                            item for item in reversed(eventos)
                            if isinstance(item, dict)
                            and str(item.get("discord_id")) == str(discord_id)
                            and item.get("tipo") in {"entrada", "saida", "alteracao_rank", "verificacao_inicial"}
                        ), None)
                        rank_anterior = estado_anterior.get("rank_atual") if estado_anterior else None
                        tipo_evento = None
                        if estado_anterior is None:
                            tipo_evento = "verificacao_inicial"
                        elif rank_anterior is None and rank_atual is not None:
                            tipo_evento = "entrada"
                        elif rank_anterior is not None and rank_atual is None:
                            tipo_evento = "saida"
                        elif rank_anterior != rank_atual:
                            tipo_evento = "alteracao_rank"
                        if tipo_evento:
                            eventos.append({
                                "tipo": tipo_evento,
                                "discord_id": int(discord_id),
                                "roblox_id": roblox_id,
                                "roblox_username": str(vinculo.get("roblox_username") or ""),
                                "rank_anterior": rank_anterior,
                                "rank_atual": rank_atual,
                                "quando": datetime.now(timezone.utc).isoformat(),
                            })
                            historico[str(guild.id)] = eventos[-200:]
                            await salvar(ARQUIVO_HISTORICO_ROBLOX, historico)
                            rotulos = {
                                "verificacao_inicial": "Vínculo Roblox verificado",
                                "entrada": "Membro entrou no grupo Roblox",
                                "saida": "Membro saiu do grupo Roblox",
                                "alteracao_rank": "Rank Roblox alterado",
                            }
                            detalhe = (
                                f"**Membro Discord:** <@{discord_id}> (ID: {discord_id})\n"
                                f"**Conta Roblox:** {vinculo.get('roblox_username', 'Não informado')} (ID: {roblox_id})\n"
                                f"**Rank anterior:** {rank_anterior or 'Sem rank'}\n"
                                f"**Rank atual:** {rank_atual or 'Sem rank'}"
                            )
                            await _registrar_evento_roblox(
                                guild,
                                rotulos.get(tipo_evento, "Atualização Roblox"),
                                detalhe,
                                int(discord_id),
                            )
                        resultado = await sincronizar_cargo_membro(guild, membro, roblox_id)
                        if resultado.startswith("Erro ao consultar"):
                            logger.warning("Consulta de rank falhou (guild=%s, user=%s): %s", guild.id, discord_id, resultado)
                    except Exception:
                        logger.exception(
                            "Falha ao sincronizar cargo Roblox (guild=%s, user=%s).",
                            guild.id, discord_id,
                        )
            except Exception:
                logger.exception(
                    "Falha na sincronização automática Roblox (guild=%s); continuará no próximo ciclo.",
                    guild.id,
                )

    @sincronizacao_automatica.before_loop
    async def antes(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Roblox(bot))
