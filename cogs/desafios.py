import time
import discord
from discord import app_commands
from discord.ext import commands

from utils import desafios
from utils.guild_config import get_config, set_config
from utils.perfis import get_perfil, calcular_patente_atual, definir_patente, _salvar_perfil

XP_VITORIA_PVP = 50  # ajuste esse valor como preferir
COOLDOWN_PADRAO_MINUTOS = 15


def _view_desafio(desafio_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Aceitar", style=discord.ButtonStyle.success,
                                     emoji="⚔️", custom_id=f"desafio:aceitar:{desafio_id}"))
    view.add_item(discord.ui.Button(label="Recusar", style=discord.ButtonStyle.danger,
                                     emoji="🚫", custom_id=f"desafio:recusar:{desafio_id}"))
    return view


async def _atualizar_stats_pvp(guild_id: int, vencedor_id: int, perdedor_id: int):
    pv = await get_perfil(guild_id, vencedor_id)
    patente_antiga = pv["patente"]
    pv["vitorias"] += 1
    pv["kills"] += 1
    pv["xp"] += XP_VITORIA_PVP
    await _salvar_perfil(guild_id, vencedor_id, pv)

    pp = await get_perfil(guild_id, perdedor_id)
    pp["derrotas"] += 1
    pp["deaths"] += 1
    await _salvar_perfil(guild_id, perdedor_id, pp)

    return pv, patente_antiga


class Desafios(commands.Cog):
    """Duelo PvP casual: /desafiar posta em Desafios com botões Aceitar/
    Recusar; se aceito, anuncia em Lutas; o resultado é enviado por print e
    passa pelo mesmo motor de revisão manual (Provas-PVP) antes de atualizar
    XP, vitórias/derrotas e patente automaticamente. Tem um cooldown entre a
    mesma dupla de jogadores, configurável, pra evitar farm de XP."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}
        bot.processadores_revisao["pvp"] = self.processar_aprovacao_pvp

    async def processar_aprovacao_pvp(self, guild: discord.Guild, revisao: dict) -> str:
        desafio = await desafios.get(guild.id, revisao["referencia_id"])
        if not desafio:
            return "⚠️ Desafio original não foi encontrado."

        pv, patente_antiga = await _atualizar_stats_pvp(guild.id, desafio["vencedor_id"], desafio["perdedor_id"])
        await desafios.definir_status(guild.id, desafio["id"], "concluido")

        texto = f"🏆 <@{desafio['vencedor_id']}> venceu! +{XP_VITORIA_PVP} XP, +1 vitória. <@{desafio['perdedor_id']}> +1 derrota."

        nova_patente = await calcular_patente_atual(guild.id, pv["xp"])
        if nova_patente and nova_patente["nome"] != patente_antiga:
            await definir_patente(guild.id, desafio["vencedor_id"], nova_patente["nome"])
            membro = guild.get_member(desafio["vencedor_id"])
            cargo_id = nova_patente.get("cargo_id")
            if membro and cargo_id:
                cargo = guild.get_role(cargo_id)
                if cargo:
                    try:
                        await membro.add_roles(cargo, reason="Promoção automática por PvP")
                    except discord.Forbidden:
                        pass
            texto += f"\n⬆️ <@{desafio['vencedor_id']}> promovido(a) para **{nova_patente['nome']}**"

        recordes_cog = self.bot.get_cog("Recordes")
        if recordes_cog:
            await recordes_cog.anunciar_se_recorde(guild, "vitorias_pvp", desafio["vencedor_id"], pv["vitorias"])
            await recordes_cog.anunciar_se_recorde(guild, "xp_total", desafio["vencedor_id"], pv["xp"])

        return texto

    # ---------------- Configuração ----------------
    @app_commands.command(name="desafio-canais", description="Define os canais de desafios e lutas.")
    @app_commands.describe(canal_desafios="Onde os desafios são anunciados", canal_lutas="Onde as lutas aceitas são anunciadas")
    @app_commands.checks.has_permissions(administrator=True)
    async def desafio_canais(self, interaction: discord.Interaction,
                              canal_desafios: discord.TextChannel, canal_lutas: discord.TextChannel):
        await set_config(interaction.guild.id, canal_desafios_id=canal_desafios.id, canal_lutas_id=canal_lutas.id)
        await interaction.response.send_message(
            f"✅ Desafios em {canal_desafios.mention}, lutas em {canal_lutas.mention}.", ephemeral=True
        )

    @app_commands.command(name="desafio-cooldown", description="Define o tempo mínimo entre desafios da mesma dupla de jogadores.")
    @app_commands.describe(minutos="Minutos de espera entre desafios da mesma dupla")
    @app_commands.checks.has_permissions(administrator=True)
    async def desafio_cooldown(self, interaction: discord.Interaction, minutos: int):
        await set_config(interaction.guild.id, desafio_cooldown_minutos=minutos)
        await interaction.response.send_message(f"✅ Cooldown definido em {minutos} minuto(s).", ephemeral=True)

    # ---------------- Desafio ----------------
    @app_commands.command(name="desafiar", description="Desafia um membro para uma luta PvP.")
    @app_commands.describe(membro="Quem você quer desafiar")
    async def desafiar(self, interaction: discord.Interaction, membro: discord.Member):
        if membro.id == interaction.user.id:
            await interaction.response.send_message("Você não pode se desafiar.", ephemeral=True)
            return
        if membro.bot:
            await interaction.response.send_message("Você não pode desafiar um bot.", ephemeral=True)
            return

        config = await get_config(interaction.guild.id)
        cooldown_min = config.get("desafio_cooldown_minutos", COOLDOWN_PADRAO_MINUTOS)
        ultimo = await desafios.get_ultimo_entre(interaction.guild.id, interaction.user.id, membro.id)
        if ultimo and cooldown_min > 0:
            segundos_passados = time.time() - ultimo["timestamp"]
            segundos_necessarios = cooldown_min * 60
            if segundos_passados < segundos_necessarios:
                restante_min = int((segundos_necessarios - segundos_passados) // 60) + 1
                await interaction.response.send_message(
                    f"Vocês já se desafiaram recentemente — espera mais **{restante_min} min** pra desafiar de novo.",
                    ephemeral=True,
                )
                return

        desafio = await desafios.criar(interaction.guild.id, interaction.user.id, membro.id)

        canal_id = config.get("canal_desafios_id")
        canal = interaction.guild.get_channel(canal_id) if canal_id else interaction.channel

        embed = discord.Embed(
            title="⚔️ Desafio proposto!",
            description=f"{interaction.user.mention} desafiou {membro.mention} para uma luta!",
            color=0xED4245,
        )
        embed.set_footer(text=f"ID: {desafio['id']}")
        msg = await canal.send(content=membro.mention, embed=embed, view=_view_desafio(desafio["id"]))
        await desafios.definir_mensagem(interaction.guild.id, desafio["id"], canal.id, msg.id)

        await interaction.response.send_message(f"✅ Desafio enviado em {canal.mention}.", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if not custom_id.startswith("desafio:"):
            return

        _, acao, desafio_id = custom_id.split(":", 2)
        desafio = await desafios.get(interaction.guild.id, desafio_id)
        if not desafio or desafio["status"] != "pendente":
            await interaction.response.send_message("Esse desafio não está mais disponível.", ephemeral=True)
            return
        if interaction.user.id != desafio["desafiado_id"]:
            await interaction.response.send_message("Esse desafio não é seu.", ephemeral=True)
            return

        await interaction.response.defer()

        if acao == "aceitar":
            await desafios.definir_status(interaction.guild.id, desafio_id, "aceito")
            embed = interaction.message.embeds[0]
            embed.color = 0x57F287
            embed.add_field(name="✅ Aceito!", value="A luta pode acontecer agora.", inline=False)
            await interaction.message.edit(embed=embed, view=None)

            config = await get_config(interaction.guild.id)
            canal_id = config.get("canal_lutas_id")
            canal = interaction.guild.get_channel(canal_id) if canal_id else interaction.channel
            aviso = discord.Embed(
                title="🥊 Luta em andamento",
                description=f"<@{desafio['desafiante_id']}> vs <@{desafio['desafiado_id']}>",
                color=0xED4245,
            )
            aviso.set_footer(text=f"Ao terminar, use /luta-completar desafio_id:{desafio_id}")
            await canal.send(embed=aviso)
        else:
            await desafios.definir_status(interaction.guild.id, desafio_id, "recusado")
            embed = interaction.message.embeds[0]
            embed.color = 0x99AAB5
            embed.add_field(name="🚫 Recusado", value="O desafio foi recusado.", inline=False)
            await interaction.message.edit(embed=embed, view=None)

    @app_commands.command(name="luta-completar", description="Envia o resultado de uma luta aceita para revisão.")
    @app_commands.describe(desafio_id="ID do desafio (aparece na mensagem de aceite)",
                            vencedor="Quem venceu a luta", print="Print comprovando o resultado")
    async def luta_completar(self, interaction: discord.Interaction, desafio_id: str,
                              vencedor: discord.Member, print: discord.Attachment):
        desafio = await desafios.get(interaction.guild.id, desafio_id)
        if not desafio or desafio["status"] != "aceito":
            await interaction.response.send_message("Não achei essa luta em andamento.", ephemeral=True)
            return
        if interaction.user.id not in (desafio["desafiante_id"], desafio["desafiado_id"]):
            await interaction.response.send_message("Só quem participou da luta pode enviar o resultado.", ephemeral=True)
            return
        if vencedor.id not in (desafio["desafiante_id"], desafio["desafiado_id"]):
            await interaction.response.send_message("O vencedor precisa ser um dos participantes da luta.", ephemeral=True)
            return

        perdedor_id = desafio["desafiado_id"] if vencedor.id == desafio["desafiante_id"] else desafio["desafiante_id"]
        await desafios.definir_resultado(interaction.guild.id, desafio_id, vencedor.id, perdedor_id)

        config = await get_config(interaction.guild.id)
        canal_id = config.get("canal_provas_pvp_id")
        canal = interaction.guild.get_channel(canal_id) if canal_id else interaction.channel

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.response.send_message("⚠️ O sistema de revisão não está carregado. Avise um admin.", ephemeral=True)
            return

        await revisoes_cog.abrir_revisao(
            interaction.guild, canal,
            tipo="pvp", autor_id=interaction.user.id, referencia_id=desafio_id,
            print_url=print.url, titulo=f"Luta: <@{desafio['desafiante_id']}> vs <@{desafio['desafiado_id']}>",
            descricao=f"Vencedor indicado: {vencedor.mention}",
        )
        await interaction.response.send_message(f"✅ Resultado enviado para revisão em {canal.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Desafios(bot))