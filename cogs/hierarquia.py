"""Configuração da hierarquia de XP e permissões delimitadas da NÊMESIS."""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from utils.perfis import salvar_patentes, get_patentes, get_perfil
from utils.hierarquia import sincronizar_cargo_patente

log = logging.getLogger(__name__)

# Progressão deliberadamente longa. Os valores são editáveis pelo comando
# /patente-configurar após a inicialização.
PATENTES_PADRAO = [
    ("Lutador", 0),
    ("Subtenente", 750),
    ("Tenente", 2000),
    ("Executor", 4000),
    ("Especialista", 7000),
    ("Elite", 11000),
    ("Veterano", 16000),
    ("Treinador", 22000),
    ("Comandante", 30000),
    ("Vice Capitão", 40000),
    ("Capitão", 52000),
    ("Capitão Geral", 68000),
]

CARGOS_PATENTE_ID = {
    "Lutador": 1561705759992057877,
    "Subtenente": 1559561987296469024,
    "Tenente": 1558909073758625973,
    "Executor": 1561715055077097603,
    "Especialista": 1561715502508933150,
    "Elite": 1561703280227262474,
    "Veterano": 1561703510406602872,
    "Treinador": 1561706517819039845,
    "Comandante": 1561715380672798730,
    "Vice Capitão": 1560370097577791569,
    "Capitão": 1558909311315607723,
    "Capitão Geral": 1561706215195541605,
}

# Permissões cumulativas apenas para funções operacionais delimitadas.
# Não concedemos Administrator, Manage Guild, Manage Roles, Manage Channels,
# Kick Members ou Ban Members por esta configuração.
PERMISSOES_POR_PATENTE = {
    "Lutador": set(),
    "Subtenente": set(),
    "Tenente": set(),
    "Executor": set(),
    "Especialista": set(),
    "Elite": set(),
    "Veterano": set(),
    # A progressão oferece recursos de participação, não moderação/administração.
    "Treinador": {"create_public_threads"},
    "Comandante": {"create_public_threads", "create_private_threads"},
    "Vice Capitão": {"create_public_threads", "create_private_threads", "use_external_emojis"},
    "Capitão": {"create_public_threads", "create_private_threads", "use_external_emojis", "use_external_stickers"},
    "Capitão Geral": {
        "create_public_threads", "create_private_threads",
        "use_external_emojis", "use_external_stickers",
        "send_messages_in_threads",
    },
}

# Estas permissões não são concedidas pela hierarquia competitiva. As permissões
# administrativas/moderativas permanecem reservadas ao OCTÓGONO/liderança.
PERMISSOES_RESTRITAS = {
    "administrator", "manage_guild", "manage_roles", "manage_channels",
    "kick_members", "ban_members", "moderate_members", "manage_messages",
    "manage_nicknames", "manage_events", "manage_threads", "manage_webhooks",
    "manage_permissions", "mention_everyone", "manage_expressions",
    "manage_guild_expressions", "manage_emojis", "manage_emojis_and_stickers",
}


class Hierarquia(commands.Cog):
    """Ferramentas administrativas para progressão e permissões da hierarquia."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="hierarquia-inicializar",
        description="Vincula os 12 cargos existentes à progressão longa de XP da NÊMESIS.",
    )
    @app_commands.checks.has_permissions(manage_roles=True, manage_guild=True)
    async def hierarquia_inicializar(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        por_id = {cargo.id: cargo for cargo in guild.roles}
        ausentes = [
            nome for nome, _ in PATENTES_PADRAO
            if CARGOS_PATENTE_ID[nome] not in por_id
        ]
        if ausentes:
            await interaction.followup.send(
                "Não alterei a configuração porque estes IDs de cargos não foram encontrados no servidor:\n"
                + "\n".join(
                    f"• {nome}: {CARGOS_PATENTE_ID[nome]}" for nome in ausentes
                ),
                ephemeral=True,
            )
            return

        patentes = []
        for nome, xp_minimo in PATENTES_PADRAO:
            patentes.append({
                "nome": nome,
                "xp_minimo": xp_minimo,
                "cargo_id": CARGOS_PATENTE_ID[nome],
            })
        await salvar_patentes(guild.id, patentes)
        await interaction.followup.send(
            "✦ **Hierarquia de XP registrada.**\n"
            + "\n".join(f"• **{nome}** — {xp:,} XP".replace(",", ".") for nome, xp in PATENTES_PADRAO)
            + "\n\nOs cargos foram vinculados por ID. Nenhuma permissão administrativa foi concedida.",
            ephemeral=True,
        )

    @app_commands.command(
        name="hierarquia-permissoes",
        description="Aplica permissões graduais e seguras aos 12 cargos da NÊMESIS.",
    )
    @app_commands.checks.has_permissions(manage_roles=True, manage_guild=True)
    async def hierarquia_permissoes(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        por_nome = {cargo.name.casefold(): cargo for cargo in guild.roles}
        ausentes = [nome for nome, _ in PATENTES_PADRAO if nome.casefold() not in por_nome]
        if ausentes:
            await interaction.followup.send(
                "Não apliquei permissões: faltam cargos com nome exato: " + ", ".join(ausentes),
                ephemeral=True,
            )
            return

        bot_member = guild.me
        if bot_member is None:
            await interaction.followup.send("Não consegui validar a hierarquia do bot.", ephemeral=True)
            return

        # Evita editar um cargo que o bot não pode gerenciar e evita aplicar
        # política sobre cargo que já possui Administrator.
        cargos = [por_nome[nome.casefold()] for nome, _ in PATENTES_PADRAO]
        nao_gerenciaveis = [cargo.name for cargo in cargos if cargo >= bot_member.top_role]
        if nao_gerenciaveis:
            await interaction.followup.send(
                "Mova o cargo do bot acima destes cargos e tente novamente: "
                + ", ".join(nao_gerenciaveis),
                ephemeral=True,
            )
            return
        administradores = [cargo.name for cargo in cargos if cargo.permissions.administrator]
        if administradores:
            await interaction.followup.send(
                "Não alterei permissões porque estes cargos já possuem Administrator: "
                + ", ".join(administradores)
                + ". Remova essa permissão manualmente e execute novamente.",
                ephemeral=True,
            )
            return

        aplicados = []
        try:
            for nome, _ in PATENTES_PADRAO:
                cargo = por_nome[nome.casefold()]
                atuais = cargo.permissions
                valores = {campo: getattr(atuais, campo) for campo in discord.Permissions.VALID_FLAGS}

                # Remove apenas permissões elevadas gerenciadas por esta política.
                for flag in PERMISSOES_RESTRITAS:
                    if flag in valores:
                        valores[flag] = False
                for flag in PERMISSOES_POR_PATENTE[nome]:
                    valores[flag] = True

                novas = discord.Permissions(**valores)
                if novas.administrator:
                    await interaction.followup.send(
                        f"Operação cancelada: a política não pode conceder Administrator a {nome}.",
                        ephemeral=True,
                    )
                    return
                await cargo.edit(
                    permissions=novas,
                    reason=f"Política gradual de permissões da NÊMESIS aplicada por {interaction.user}",
                )
                aplicados.append(nome)
        except (discord.Forbidden, discord.HTTPException) as erro:
            log.exception("Falha ao aplicar permissões da hierarquia.")
            await interaction.followup.send(
                f"Aplicação parcial ({len(aplicados)}/12). O Discord recusou uma alteração: {type(erro).__name__}. "
                "Confira a hierarquia e as permissões do bot antes de tentar novamente.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            "✦ **Política de permissões aplicada aos 12 cargos.**\n"
            "• Lutador até Veterano: sem privilégios administrativos adicionais.\n"
            "• Treinador: gerenciar mensagens.\n"
            "• Comandante: gerenciar mensagens e moderar membros.\n"
            "• Vice Capitão: permissões anteriores + gerenciar apelidos.\n"
            "• Capitão: permissões anteriores + gerenciar eventos.\n"
            "• Capitão Geral: permissões anteriores + gerenciar threads.\n\n"
            "**Proteções:** nenhum cargo recebeu Administrator, Gerenciar servidor, Gerenciar cargos, Gerenciar canais, Expulsar ou Banir membros. "
            "Permissões específicas por canal devem ser ajustadas nas sobrescritas dos canais.",
            ephemeral=True,
        )

    @app_commands.command(
        name="hierarquia-sincronizar",
        description="Recalcula e aplica a patente por XP dos membros com perfil registrado.",
    )
    @app_commands.checks.has_permissions(manage_roles=True, manage_guild=True)
    async def hierarquia_sincronizar(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use este comando dentro do servidor.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        patentes = await get_patentes(guild.id)
        if not patentes:
            await interaction.followup.send("Execute primeiro /hierarquia-inicializar.", ephemeral=True)
            return

        from utils.perfis import ARQUIVO_PERFIS
        from utils.storage import carregar
        dados = await carregar(ARQUIVO_PERFIS, {})
        perfis = dados.get(str(guild.id), {}) if isinstance(dados, dict) else {}
        ok = 0
        falhas = 0
        sem_membro = 0
        for user_id, perfil in perfis.items():
            if not isinstance(perfil, dict):
                continue
            membro = guild.get_member(int(user_id))
            if membro is None:
                sem_membro += 1
                continue
            try:
                patente = await sincronizar_cargo_patente(
                    guild, membro, int(perfil.get("xp", 0) or 0)
                )
                if patente:
                    ok += 1
            except Exception:
                falhas += 1
                log.exception("Falha ao sincronizar hierarquia para membro %s", user_id)

        await interaction.followup.send(
            f"Sincronização concluída. Perfis processados: **{ok}** · Falhas: **{falhas}** · "
            f"Membros fora do servidor: **{sem_membro}**.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Hierarquia(bot))
