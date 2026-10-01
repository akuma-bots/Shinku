import discord
from discord import app_commands
from discord.ext import commands
from utils.storage import carregar, salvar
from utils.guild_config import get_config, set_config

ARQUIVO = "parcerias.json"


async def _todas():
    return await carregar(ARQUIVO, {})


async def _da_guild(guild_id: int):
    dados = await _todas()
    return dados.get(str(guild_id), [])


async def _salvar_da_guild(guild_id: int, lista):
    dados = await _todas()
    dados[str(guild_id)] = lista
    await salvar(ARQUIVO, dados)


async def _cargo_categoria_parcerias(guild: discord.Guild) -> discord.Role | None:
    config = await get_config(guild.id)
    cargo_id = config.get("cargo_categoria_parcerias_id")

    if cargo_id:
        cargo = guild.get_role(cargo_id)
        if cargo:
            return cargo

    return discord.utils.get(guild.roles, name="PARCERIAS")


async def _criar_cargo_da_parceria(
    guild: discord.Guild,
    nome: str
) -> tuple[discord.Role | None, str | None]:

    cargo_categoria = await _cargo_categoria_parcerias(guild)

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
            "pra criar o cargo."
        )

    try:
        posicao = max(cargo_categoria.position - 1, 1)
        await novo_cargo.edit(position=posicao)

    except (discord.Forbidden, discord.HTTPException):
        return novo_cargo, (
            "criei o cargo, mas não consegui posicioná-lo abaixo "
            "da categoria (meu cargo provavelmente está abaixo "
            "dela na lista)."
        )

    return novo_cargo, None


class ParceriaView(discord.ui.View):
    """Botão persistente para selecionar/retirar o cargo da parceria."""

    def __init__(self, role_id: int):
        super().__init__(timeout=None)

        self.role_id = role_id

        button = discord.ui.Button(
            label="Selecionar cargo",
            style=discord.ButtonStyle.secondary,
            custom_id=f"parceria:selecionar:{role_id}",
        )

        button.callback = self._selecionar_cargo
        self.add_item(button)

    async def _selecionar_cargo(
        self,
        interaction: discord.Interaction
    ):
        guild = interaction.guild
        member = interaction.user

        if not guild or not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Esta ação só pode ser usada dentro do servidor da NÊMESIS.",
                ephemeral=True,
            )
            return

        role = guild.get_role(self.role_id)

        if not role:
            await interaction.response.send_message(
                "O cargo desta parceria não existe mais.",
                ephemeral=True,
            )
            return

        bot_member = guild.me

        if not bot_member or bot_member.top_role <= role:
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
                    reason=f"Cargo da parceria removido por {member}",
                )

                await interaction.response.send_message(
                    f"✓ O cargo {role.mention} foi removido de você.",
                    ephemeral=True,
                )

            else:

                await member.add_roles(
                    role,
                    reason=f"Cargo da parceria selecionado por {member}",
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


class Parcerias(commands.Cog):
    """Sistema de parcerias da NÊMESIS.

    Registra nome, convite e descrição, publica o anúncio,
    cria automaticamente o cargo da parceria abaixo da categoria
    PARCERIAS e disponibiliza esse cargo para seleção no comando
    /parcerias.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="configurar-canal-parcerias",
        description="Define onde as parcerias são anunciadas.",
    )
    @app_commands.describe(
        canal="Canal de texto para os anúncios de parceria"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
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
        cargo="O cargo-categoria usado como separador de PARCERIAS"
    )
    @app_commands.checks.has_permissions(manage_guild=True)
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
            f"✓ Novos cargos de parceria serão criados logo abaixo "
            f"de {cargo.mention}.",
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
    @app_commands.checks.has_permissions(manage_guild=True)
    async def adicionar_parceria(
        self,
        interaction: discord.Interaction,
        nome: str,
        convite: str,
        descricao: str,
        banner: str = None,
    ):
        config = await get_config(interaction.guild.id)

        canal_id = config.get("canal_parcerias_id")
        canal = (
            interaction.guild.get_channel(canal_id)
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

        await interaction.response.defer(ephemeral=True)

        cargo, aviso_cargo = await _criar_cargo_da_parceria(
            interaction.guild,
            nome,
        )

        # O cargo NÃO é atribuído automaticamente ao criador.
        embed = discord.Embed(
            title=f"🤝 Nova parceria: {nome}",
            description=descricao,
            color=0x57F287,
        )

        embed.add_field(
            name="Convite",
            value=convite,
            inline=False,
        )

        if cargo:
            embed.add_field(
                name="Cargo da parceria",
                value=cargo.mention,
                inline=False,
            )

        if banner:
            embed.set_image(url=banner)

        embed.set_footer(
            text=f"Parceria registrada por {interaction.user}"
        )

        await canal.send(
            embed=embed,
            view=ParceriaView(cargo.id) if cargo else None,
        )

        lista = await _da_guild(interaction.guild.id)

        lista.append({
            "nome": nome,
            "convite": convite,
            "descricao": descricao,
            "banner": banner,
            "cargo_id": cargo.id if cargo else None,
        })

        await _salvar_da_guild(
            interaction.guild.id,
            lista,
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
                f" — não criei o cargo: {aviso_cargo}"
            )

        await interaction.followup.send(
            f"✓ Parceria com **{nome}** registrada e anunciada "
            f"em {canal.mention}{resultado_cargo}",
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
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remover_parceria(
        self,
        interaction: discord.Interaction,
        nome: str,
    ):
        lista = await _da_guild(interaction.guild.id)

        alvo = next(
            (
                p
                for p in lista
                if p["nome"].lower() == nome.lower()
            ),
            None,
        )

        if not alvo:
            await interaction.response.send_message(
                "Não achei nenhuma parceria com esse nome.",
                ephemeral=True,
            )
            return

        cargo_id = alvo.get("cargo_id")

        if cargo_id:
            cargo = interaction.guild.get_role(cargo_id)

            if cargo:
                try:
                    await cargo.delete(
                        reason=f"Parceria com {nome} removida"
                    )
                except discord.Forbidden:
                    pass

        nova_lista = [
            p
            for p in lista
            if p["nome"].lower() != nome.lower()
        ]

        await _salvar_da_guild(
            interaction.guild.id,
            nova_lista,
        )

        await interaction.response.send_message(
            f"✓ Parceria com **{nome}** removida "
            "(cargo incluso, se existia).",
            ephemeral=True,
        )

    @app_commands.command(
        name="parcerias",
        description=(
            "Mostra as parcerias com o cargo de cada uma "
            "para seleção."
        ),
    )
    async def parcerias(
        self,
        interaction: discord.Interaction,
    ):
        lista = await _da_guild(interaction.guild.id)

        if not lista:
            await interaction.response.send_message(
                "Nenhuma parceria registrada ainda.",
                ephemeral=True,
            )
            return

        # IMPORTANTE:
        # A lista inteira do comando fica invisível para os demais
        # membros do canal.
        await interaction.response.defer(ephemeral=True)

        # Cada parceria recebe seu próprio embed e seu próprio
        # botão, deixando o cargo de seleção imediatamente abaixo.
        for indice, p in enumerate(lista[:25], start=1):

            embed = discord.Embed(
                title=f"🤝 {p['nome']}",
                description=p["descricao"],
                color=0x5865F2,
            )

            embed.add_field(
                name="Convite",
                value=p["convite"],
                inline=False,
            )

            cargo_id = p.get("cargo_id")

            cargo = (
                interaction.guild.get_role(cargo_id)
                if cargo_id
                else None
            )

            if cargo:

                embed.add_field(
                    name="Cargo da parceria",
                    value=cargo.mention,
                    inline=False,
                )

                view = ParceriaView(cargo.id)

            else:

                embed.add_field(
                    name="Cargo da parceria",
                    value="Cargo não disponível.",
                    inline=False,
                )

                view = None

            if p.get("banner"):
                embed.set_image(url=p["banner"])

            embed.set_footer(
                text=f"Parceria {indice} • NÊMESIS"
            )

            # A resposta também permanece efêmera.
            await interaction.followup.send(
                embed=embed,
                view=view,
                ephemeral=True,
            )

        if len(lista) > 25:
            await interaction.followup.send(
                "⚠️ Apenas as primeiras 25 parcerias foram exibidas.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Parcerias(bot))

    # Reativa os botões das mensagens antigas após reiniciar o bot.
    dados = await _todas()
    cargos_registrados = set()

    for lista in dados.values():

        for parceria in lista:

            cargo_id = parceria.get("cargo_id")

            if cargo_id and cargo_id not in cargos_registrados:

                bot.add_view(
                    ParceriaView(cargo_id)
                )

                cargos_registrados.add(cargo_id)