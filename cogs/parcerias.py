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


async def _criar_cargo_da_parceria(guild: discord.Guild, nome: str) -> tuple[discord.Role | None, str | None]:
    cargo_categoria = await _cargo_categoria_parcerias(guild)
    if not cargo_categoria:
        return None, "não achei o cargo-categoria de parcerias. Configure com `/configurar-cargo-parcerias` primeiro."

    try:
        novo_cargo = await guild.create_role(name=nome, reason=f"Cargo automático da parceria: {nome}")
    except discord.Forbidden:
        return None, "não tenho permissão de 'Gerenciar Cargos' pra criar o cargo."

    try:
        posicao = max(cargo_categoria.position - 1, 1)
        await novo_cargo.edit(position=posicao)
    except (discord.Forbidden, discord.HTTPException):
        return novo_cargo, "criei o cargo, mas não consegui posicioná-lo abaixo da categoria (meu cargo provavelmente está abaixo dela na lista)."

    return novo_cargo, None


class Parcerias(commands.Cog):
    """Registro de parcerias com outros servidores: guarda nome, convite e
    descrição, publica um anúncio no canal de parcerias, cria um cargo com
    o nome da parceria logo abaixo do cargo-categoria configurado (e já dá
    esse cargo pra quem registrou a parceria), e mantém uma lista
    consultável."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="configurar-canal-parcerias", description="Define onde as parcerias são anunciadas.")
    @app_commands.describe(canal="Canal de texto para os anúncios de parceria")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_canal_parcerias(self, interaction: discord.Interaction, canal: discord.TextChannel):
        await set_config(interaction.guild.id, canal_parcerias_id=canal.id)
        await interaction.response.send_message(f"✅ Parcerias agora são anunciadas em {canal.mention}.", ephemeral=True)

    @app_commands.command(name="configurar-cargo-parcerias", description="Define o cargo-categoria abaixo do qual os cargos de parceria são criados.")
    @app_commands.describe(cargo="O cargo-categoria (ex: aquele separador '⟨ PARCERIAS ⟩' do servidor)")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def configurar_cargo_parcerias(self, interaction: discord.Interaction, cargo: discord.Role):
        await set_config(interaction.guild.id, cargo_categoria_parcerias_id=cargo.id)
        await interaction.response.send_message(
            f"✅ Novos cargos de parceria vão ser criados logo abaixo de {cargo.mention}.", ephemeral=True
        )

    @app_commands.command(name="adicionar-parceria", description="Registra uma parceria, anuncia no canal, cria o cargo dela e já te dá esse cargo.")
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
        canal_id = config["canal_parcerias_id"]
        canal = interaction.guild.get_channel(canal_id) if canal_id else None
        if not canal:
            await interaction.response.send_message(
                "Configure o canal de parcerias primeiro com `/configurar-canal-parcerias`.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        cargo, aviso_cargo = await _criar_cargo_da_parceria(interaction.guild, nome)

        atribuido_ao_autor = False
        if cargo:
            try:
                await interaction.user.add_roles(cargo, reason=f"Registrou a parceria com {nome}")
                atribuido_ao_autor = True
            except discord.Forbidden:
                pass

        embed = discord.Embed(title=f"🤝 Nova parceria: {nome}", description=descricao, color=0x57F287)
        embed.add_field(name="Convite", value=convite, inline=False)
        if banner:
            embed.set_image(url=banner)
        embed.set_footer(text=f"Parceria registrada por {interaction.user}")

        await canal.send(embed=embed)

        lista = await _da_guild(interaction.guild.id)
        lista.append({
            "nome": nome, "convite": convite, "descricao": descricao,
            "banner": banner, "cargo_id": cargo.id if cargo else None,
        })
        await _salvar_da_guild(interaction.guild.id, lista)

        if cargo and not aviso_cargo:
            resultado_cargo = f" e o cargo {cargo.mention} foi criado"
            if atribuido_ao_autor:
                resultado_cargo += " (e já foi atribuído a você)"
        elif cargo and aviso_cargo:
            resultado_cargo = f" — cargo {cargo.mention} criado, mas {aviso_cargo}"
        else:
            resultado_cargo = f" — não criei o cargo: {aviso_cargo}"

        await interaction.followup.send(f"✅ Parceria com **{nome}** registrada, anunciada em {canal.mention}{resultado_cargo}.", ephemeral=True)

    @app_commands.command(name="remover-parceria", description="Remove uma parceria registrada pelo nome (e o cargo dela, se existir).")
    @app_commands.describe(nome="Nome exato da parceria a remover")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def remover_parceria(self, interaction: discord.Interaction, nome: str):
        lista = await _da_guild(interaction.guild.id)
        alvo = next((p for p in lista if p["nome"].lower() == nome.lower()), None)
        if not alvo:
            await interaction.response.send_message("Não achei nenhuma parceria com esse nome.", ephemeral=True)
            return

        cargo_id = alvo.get("cargo_id")
        if cargo_id:
            cargo = interaction.guild.get_role(cargo_id)
            if cargo:
                try:
                    await cargo.delete(reason=f"Parceria com {nome} removida")
                except discord.Forbidden:
                    pass

        nova_lista = [p for p in lista if p["nome"].lower() != nome.lower()]
        await _salvar_da_guild(interaction.guild.id, nova_lista)
        await interaction.response.send_message(f"🗑️ Parceria com **{nome}** removida (cargo incluso, se existia).", ephemeral=True)

    @app_commands.command(name="parcerias", description="Lista as parcerias registradas deste servidor.")
    async def parcerias(self, interaction: discord.Interaction):
        lista = await _da_guild(interaction.guild.id)
        if not lista:
            await interaction.response.send_message("Nenhuma parceria registrada ainda.", ephemeral=True)
            return
        embed = discord.Embed(title="🤝 Parcerias do servidor", color=0x5865F2)
        for p in lista[:25]:
            valor = f"{p['descricao']}\n{p['convite']}"
            if p.get("cargo_id"):
                valor += f"\nCargo: <@&{p['cargo_id']}>"
            embed.add_field(name=p["nome"], value=valor, inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Parcerias(bot))