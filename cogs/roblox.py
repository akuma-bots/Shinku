from utils.apresentacao import criar_embed
import asyncio
import logging
import random
import string
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks
from utils.storage import carregar, salvar

ARQUIVO_VINCULOS = "roblox_vinculos.json"       # { guild_id: { discord_id: {roblox_id, roblox_username} } }
ARQUIVO_PENDENTES = "roblox_pendentes.json"     # { guild_id: { discord_id: {roblox_id, roblox_username, codigo} } }
ARQUIVO_GRUPO = "roblox_grupo_config.json"      # { guild_id: {"grupo_id": int, "mapeamentos": {rank_nome: cargo_id}} }

_LOG = logging.getLogger(__name__)
_ROBLOX_VINCULO_LOCK = asyncio.Lock()


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
    grupo_id = config.get("grupo_id")
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

    cargos_pra_remover = [
        cargo for cargo in membro.roles
        if cargo.id in ids_gerenciados and cargo.id != cargo_id_correto
    ]
    cargo_pra_adicionar = None
    if cargo_id_correto and not any(c.id == cargo_id_correto for c in membro.roles):
        cargo_pra_adicionar = guild.get_role(cargo_id_correto)

    try:
        if cargos_pra_remover:
            await membro.remove_roles(*cargos_pra_remover, reason="Sincronização de rank do Roblox")
        if cargo_pra_adicionar:
            await membro.add_roles(cargo_pra_adicionar, reason="Sincronização de rank do Roblox")
    except discord.Forbidden:
        return "Sem permissão pra ajustar os cargos (verifique a hierarquia de cargos do bot)."

    if not rank_atual:
        return "A pessoa não está mais no grupo Roblox — cargos de rank removidos."
    if cargo_pra_adicionar:
        return f"Cargo atualizado pra **{rank_atual}**."
    return f"Já estava correto (**{rank_atual}**)."


class Roblox(commands.Cog):
    """Verificação e vínculo de conta Roblox, com sincronização automática de
    cargo por rank do grupo Roblox da gangue — quem sobe/desce de patente no
    jogo, sobe/desce de cargo no Discord sozinho."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sincronizacao_automatica.start()

    def cog_unload(self):
        self.sincronizacao_automatica.cancel()

    # ---------------- Verificação de conta ----------------

    @app_commands.command(name="roblox-vincular", description="Passo 1: inicia a verificação da sua conta Roblox.")
    @app_commands.describe(usuario_roblox="Seu nome de usuário no Roblox")
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
            f"Depois de salvar lá, volta aqui e roda `/roblox-confirmar`. Depois de confirmado, pode apagar o código.",
            ephemeral=True,
        )

    @app_commands.command(name="roblox-confirmar", description="Passo 2: confirma a verificação depois de colocar o código no seu perfil Roblox.")
    async def roblox_confirmar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        pendentes = await carregar(ARQUIVO_PENDENTES, {})
        pendente = pendentes.get(str(interaction.guild.id), {}).get(str(interaction.user.id))
        if not pendente:
            await interaction.followup.send("Você não tem nenhuma verificação pendente. Use `/roblox-vincular` primeiro.", ephemeral=True)
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
                    "Esta verificação já foi processada ou substituída. Use /roblox-vincular para iniciar outra.",
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

        await interaction.followup.send(mensagem, ephemeral=True)

    @app_commands.command(name="roblox-desvincular", description="Remove o vínculo da sua conta Roblox.")
    async def roblox_desvincular(self, interaction: discord.Interaction):
        vinculos = await carregar(ARQUIVO_VINCULOS, {})
        guild_dados = vinculos.get(str(interaction.guild.id), {})
        if guild_dados.pop(str(interaction.user.id), None) is None:
            await interaction.response.send_message("Você não tem nenhuma conta Roblox vinculada.", ephemeral=True)
            return
        await salvar(ARQUIVO_VINCULOS, vinculos)
        await interaction.response.send_message("🔓 Vínculo removido.", ephemeral=True)

    @app_commands.command(name="roblox-perfil", description="Mostra a conta Roblox vinculada de um membro.")
    @app_commands.describe(membro="De quem ver (padrão: você mesmo)")
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

    @app_commands.command(
        name="roblox-identificar",
        description="Encontra o membro da NÊMESIS que vinculou um nome de usuário Roblox.",
    )
    @app_commands.describe(usuario_roblox="Nome exato da conta Roblox já verificada")
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

    @app_commands.command(name="roblox-configurar-grupo", description="Define qual grupo Roblox da gangue o bot vai usar pra sincronizar cargos.")
    @app_commands.describe(grupo_id="ID numérico do grupo Roblox (aparece na URL do grupo)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def roblox_configurar_grupo(self, interaction: discord.Interaction, grupo_id: str):
        if not grupo_id.isdigit():
            await interaction.response.send_message("O ID do grupo precisa ser só números.", ephemeral=True)
            return
        todos = await carregar(ARQUIVO_GRUPO, {})
        atual = todos.get(str(interaction.guild.id), {"grupo_id": None, "mapeamentos": {}})
        atual["grupo_id"] = int(grupo_id)
        todos[str(interaction.guild.id)] = atual
        await salvar(ARQUIVO_GRUPO, todos)
        await interaction.response.send_message(
            f"✅ Grupo Roblox configurado (ID `{grupo_id}`). Agora use `/roblox-mapear-cargo` pra ligar cada rank a um cargo do Discord.",
            ephemeral=True,
        )

    @app_commands.command(name="roblox-mapear-cargo", description="Liga um rank do grupo Roblox a um cargo do Discord.")
    @app_commands.describe(rank_roblox="Nome EXATO do rank no grupo Roblox (ex: 'Oficial')", cargo_discord="Cargo do Discord correspondente")
    @app_commands.checks.has_permissions(manage_guild=True)
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
            await interaction.response.send_message("Configure o grupo primeiro com `/roblox-configurar-grupo`.", ephemeral=True)
            return
        atual["mapeamentos"][rank_roblox] = cargo_discord.id
        todos[str(interaction.guild.id)] = atual
        await salvar(ARQUIVO_GRUPO, todos)
        await interaction.response.send_message(f"✅ Rank **{rank_roblox}** agora dá o cargo {cargo_discord.mention} automaticamente.", ephemeral=True)

    @app_commands.command(name="roblox-remover-mapeamento", description="Remove a ligação de um rank do Roblox com cargo do Discord.")
    @app_commands.describe(rank_roblox="Nome exato do rank, como aparece em /roblox-mapeamentos")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def roblox_remover_mapeamento(self, interaction: discord.Interaction, rank_roblox: str):
        todos = await carregar(ARQUIVO_GRUPO, {})
        atual = todos.get(str(interaction.guild.id), {"grupo_id": None, "mapeamentos": {}})
        if atual["mapeamentos"].pop(rank_roblox, None) is None:
            await interaction.response.send_message("Não achei esse rank mapeado.", ephemeral=True)
            return
        todos[str(interaction.guild.id)] = atual
        await salvar(ARQUIVO_GRUPO, todos)
        await interaction.response.send_message(f"🗑️ Mapeamento de **{rank_roblox}** removido.", ephemeral=True)

    @app_commands.command(name="roblox-mapeamentos", description="Lista os ranks do Roblox ligados a cargos do Discord neste servidor.")
    async def roblox_mapeamentos(self, interaction: discord.Interaction):
        config = await _config_grupo(interaction.guild.id)
        if not config["grupo_id"]:
            await interaction.response.send_message("Nenhum grupo Roblox configurado ainda.", ephemeral=True)
            return
        linhas = [f"**{rank}** → <@&{cargo_id}>" for rank, cargo_id in config["mapeamentos"].items()]
        texto = "\n".join(linhas) if linhas else "Nenhum rank mapeado ainda."
        embed = criar_embed(title="🎮 Sincronização de cargos por rank", description=f"Grupo: `{config['grupo_id']}`\n\n{texto}", color=0x00A2FF)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="roblox-sincronizar", description="Força a sincronização de cargo por rank (de um membro ou de todo mundo vinculado).")
    @app_commands.describe(membro="(Opcional) só esse membro — sem isso, sincroniza todo mundo vinculado")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def roblox_sincronizar(self, interaction: discord.Interaction, membro: discord.Member = None):
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
                if not config["grupo_id"] or not config["mapeamentos"]:
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
                        await sincronizar_cargo_membro(guild, membro, vinculo["roblox_id"])
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
