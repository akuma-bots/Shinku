import time
import discord
from discord import app_commands
from discord.ext import commands

from utils import desafios
from utils.guild_config import get_config, set_config
from utils.perfis import get_perfil, calcular_patente_atual, definir_patente, _salvar_perfil, sincronizar_perfil_site

XP_VITORIA_PVP = 50
COOLDOWN_PADRAO_MINUTOS = 15


async def _resolver_canal(
    guild: discord.Guild,
    canal_id,
    fallback=None,
    fallback_id=None,
):
    """Resolve o canal configurado, tenta o padrão e usa o canal atual como último recurso."""
    vistos = set()
    for valor in (canal_id, fallback_id):
        if valor in (None, ""):
            continue
        try:
            identificador = int(valor)
        except (TypeError, ValueError):
            continue
        if identificador in vistos:
            continue
        vistos.add(identificador)
        canal = guild.get_channel(identificador)
        if canal is None:
            try:
                canal = await guild.fetch_channel(identificador)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as erro:
                print("[Desafios] Falha ao resolver canal " + str(identificador) + ": " + str(erro))
                continue
        if canal is not None and callable(getattr(canal, "send", None)):
            return canal
    if fallback is not None and callable(getattr(fallback, "send", None)):
        return fallback
    return None

def _view_desafio(desafio_id: str) -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="Aceitar", style=discord.ButtonStyle.success,
                                     emoji="⚔️", custom_id=f"desafio:aceitar:{desafio_id}"))
    view.add_item(discord.ui.Button(label="Recusar", style=discord.ButtonStyle.danger,
                                     emoji="🚫", custom_id=f"desafio:recusar:{desafio_id}"))
    return view


async def _atualizar_stats_pvp(
    guild_id: int,
    vencedor_id: int,
    perdedor_id: int,
    xp_extra_vencedor: int = 0,
    desafio_id: str = "",
):
    """
    Aplica as estatísticas uma vez por desafio e por perfil.
    O marcador é salvo junto com as estatísticas para que uma falha parcial
    possa ser retomada sem duplicar a recompensa já persistida.
    """
    evento_id = f"pvp:{desafio_id}" if desafio_id else ""

    pv = await get_perfil(guild_id, vencedor_id)
    patente_antiga = pv.get("patente")
    eventos_vitoria = pv.get("resultados_pvp_aplicados", [])
    if not isinstance(eventos_vitoria, list):
        eventos_vitoria = []
    if not evento_id or evento_id not in eventos_vitoria:
        pv["vitorias"] = int(pv.get("vitorias", 0) or 0) + 1
        pv["kills"] = int(pv.get("kills", 0) or 0) + 1
        pv["xp"] = int(pv.get("xp", 0) or 0) + XP_VITORIA_PVP + xp_extra_vencedor
        if evento_id:
            eventos_vitoria.append(evento_id)
            pv["resultados_pvp_aplicados"] = eventos_vitoria[-1000:]
        await _salvar_perfil(guild_id, vencedor_id, pv)
    try:
        await sincronizar_perfil_site(guild_id, vencedor_id)
    except Exception as erro:
        print(f"[PvP] Falha ao sincronizar vencedor {vencedor_id}: {erro}")

    pp = await get_perfil(guild_id, perdedor_id)
    eventos_derrota = pp.get("resultados_pvp_aplicados", [])
    if not isinstance(eventos_derrota, list):
        eventos_derrota = []
    if not evento_id or evento_id not in eventos_derrota:
        pp["derrotas"] = int(pp.get("derrotas", 0) or 0) + 1
        pp["deaths"] = int(pp.get("deaths", 0) or 0) + 1
        if evento_id:
            eventos_derrota.append(evento_id)
            pp["resultados_pvp_aplicados"] = eventos_derrota[-1000:]
        await _salvar_perfil(guild_id, perdedor_id, pp)
    try:
        await sincronizar_perfil_site(guild_id, perdedor_id)
    except Exception as erro:
        print(f"[PvP] Falha ao sincronizar perdedor {perdedor_id}: {erro}")

    return pv, patente_antiga


async def _remover_xp(guild_id: int, user_id: int, quantidade: int) -> bool:
    perfil = await get_perfil(guild_id, user_id)
    if perfil["xp"] < quantidade:
        return False
    perfil["xp"] -= quantidade
    await _salvar_perfil(guild_id, user_id, perfil)
    return True


async def _devolver_xp(guild_id: int, user_id: int, quantidade: int):
    perfil = await get_perfil(guild_id, user_id)
    perfil["xp"] += quantidade
    await _salvar_perfil(guild_id, user_id, perfil)


class Desafios(commands.Cog):
    """Duelo PvP casual: /desafiar posta em Desafios com botões Aceitar/
    Recusar; se aceito, anuncia em Lutas; o resultado passa pela revisão
    manual (Provas-PVP) antes de atualizar XP, vitórias/derrotas e patente.
    Tem cooldown entre a mesma dupla (evita farm de XP) e aposta de XP
    opcional: quem vence leva o XP dos dois lados."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}
        bot.processadores_revisao["pvp"] = self.processar_aprovacao_pvp

    async def processar_aprovacao_pvp(self, guild: discord.Guild, revisao: dict) -> str:
        desafio = await desafios.get(guild.id, revisao["referencia_id"])
        if not desafio:
            return "⚠️ Desafio original não foi encontrado."
        # Mesmo que o status já esteja concluído, uma tentativa anterior pode
        # ter falhado ao aplicar patente/recordes após salvar as estatísticas.
        # O ledger por desafio impede duplicar XP, vitórias e derrotas.
        if desafio.get("status") not in {"aguardando_revisao", "aceito", "concluido"}:
            return f"⚠️ O desafio está no estado `{desafio.get('status', 'desconhecido')}` e não pode ser processado."

        xp_extra = int(desafio.get("aposta_xp", 0) or 0) * 2
        pv, patente_antiga = await _atualizar_stats_pvp(
            guild.id,
            int(desafio["vencedor_id"]),
            int(desafio["perdedor_id"]),
            xp_extra,
            desafio_id=str(desafio["id"]),
        )
        await desafios.definir_status(guild.id, desafio["id"], "concluido")

        texto = f"🏆 <@{desafio['vencedor_id']}> venceu! +{XP_VITORIA_PVP} XP, +1 vitória. <@{desafio['perdedor_id']}> +1 derrota."
        if desafio["aposta_xp"] > 0:
            texto += f"\n💰 <@{desafio['vencedor_id']}> ganhou a aposta: +{xp_extra} XP (os {desafio['aposta_xp']} XP de cada lado)."

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
    @app_commands.command(name="desafiar", description="Desafia um membro para uma luta PvP, com aposta de XP opcional.")
    @app_commands.describe(membro="Quem você quer desafiar", aposta_xp="XP que cada um aposta (opcional, ambos apostam o mesmo valor)")
    async def desafiar(self, interaction: discord.Interaction, membro: discord.Member, aposta_xp: int = 0):
        if membro.id == interaction.user.id:
            await interaction.response.send_message("Você não pode se desafiar.", ephemeral=True)
            return
        if membro.bot:
            await interaction.response.send_message("Você não pode desafiar um bot.", ephemeral=True)
            return
        if aposta_xp < 0:
            await interaction.response.send_message("A aposta não pode ser negativa.", ephemeral=True)
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

        canal_id = config.get("canal_desafios_id")
        canal = await _resolver_canal(interaction.guild, canal_id, interaction.channel, fallback_id=1545834386128375909)
        if canal is None or not hasattr(canal, "send"):
            await interaction.response.send_message("❌ Canal de desafios não encontrado. Configure novamente com /desafio-canais.", ephemeral=True)
            return

        if aposta_xp > 0:
            ok = await _remover_xp(interaction.guild.id, interaction.user.id, aposta_xp)
            if not ok:
                await interaction.response.send_message(f"Você não tem {aposta_xp} XP pra apostar.", ephemeral=True)
                return

        try:
            desafio = await desafios.criar(
                interaction.guild.id,
                interaction.user.id,
                membro.id,
                aposta_xp,
            )
        except Exception as erro:
            if aposta_xp > 0:
                try:
                    await _devolver_xp(
                        interaction.guild.id,
                        interaction.user.id,
                        aposta_xp,
                    )
                except Exception:
                    print("[Desafios] Não consegui devolver a aposta após falha ao criar o desafio.")
            print(f"[Desafios] Falha ao criar desafio: {erro}")
            await interaction.response.send_message(
                "❌ Não consegui registrar o desafio no armazenamento. Se havia uma aposta, tente conferir seu XP antes de repetir.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  DESAFIO PvP",
            description=f"{interaction.user.mention} desafiou {membro.mention} para uma luta!",
            color=0xED4245,
        )
        if aposta_xp > 0:
            embed.add_field(name="◈ APOSTA", value=f"{aposta_xp} XP de cada lado (quem vencer leva os {aposta_xp * 2} XP)")
        embed.set_footer(text=f"ID: {desafio['id']}")
        try:
            msg = await canal.send(
                content=membro.mention,
                embed=embed,
                view=_view_desafio(desafio["id"]),
            )
        except (discord.Forbidden, discord.HTTPException) as erro:
            if aposta_xp > 0:
                try:
                    await _devolver_xp(
                        interaction.guild.id,
                        interaction.user.id,
                        aposta_xp,
                    )
                except Exception as erro_reembolso:
                    print(f"[Desafios] Falha ao devolver aposta: {erro_reembolso}")
            await desafios.definir_status(
                interaction.guild.id,
                desafio["id"],
                "cancelado",
            )
            print(f"[Desafios] Falha ao publicar desafio: {erro}")
            await interaction.response.send_message(
                "❌ Não consegui publicar o desafio. Sua aposta foi devolvida; confira as permissões do bot no canal.",
                ephemeral=True,
            )
            return

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
            if desafio["aposta_xp"] > 0:
                ok = await _remover_xp(interaction.guild.id, interaction.user.id, desafio["aposta_xp"])
                if not ok:
                    await desafios.definir_status(interaction.guild.id, desafio_id, "recusado")
                    await _devolver_xp(interaction.guild.id, desafio["desafiante_id"], desafio["aposta_xp"])
                    embed = interaction.message.embeds[0]
                    embed.color = 0x99AAB5
                    embed.add_field(name="🚫 Cancelado", value=f"{interaction.user.mention} não tem XP suficiente pra cobrir a aposta.", inline=False)
                    await interaction.message.edit(embed=embed, view=None)
                    return

            await desafios.definir_status(interaction.guild.id, desafio_id, "aceito")
            embed = interaction.message.embeds[0]
            embed.color = 0x57F287
            embed.add_field(name="✅ Aceito!", value="A luta pode acontecer agora.", inline=False)
            await interaction.message.edit(embed=embed, view=None)

            config = await get_config(interaction.guild.id)
            canal_id = config.get("canal_lutas_id")
            canal = await _resolver_canal(interaction.guild, canal_id, interaction.channel, fallback_id=1545834447944028170)
            if canal is None or not hasattr(canal, "send"):
                await interaction.followup.send("⚠️ Canal de lutas não encontrado. Configure novamente com /desafio-canais.", ephemeral=True)
                return
            aviso = discord.Embed(
                title="𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  CONFRONTO EM ANDAMENTO",
                description=f"<@{desafio['desafiante_id']}> vs <@{desafio['desafiado_id']}>",
                color=0xED4245,
            )
            aviso.set_footer(text=f"Ao terminar, use /luta-completar desafio_id:{desafio_id}")
            await canal.send(embed=aviso)
        else:
            await desafios.definir_status(interaction.guild.id, desafio_id, "recusado")
            if desafio["aposta_xp"] > 0:
                await _devolver_xp(interaction.guild.id, desafio["desafiante_id"], desafio["aposta_xp"])
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

        config = await get_config(interaction.guild.id)
        canal_id = config.get("canal_provas_pvp_id")
        canal = await _resolver_canal(interaction.guild, canal_id, interaction.channel, fallback_id=1545853928736952420)
        if canal is None or not hasattr(canal, "send"):
            await interaction.response.send_message(
                "❌ Canal de provas PvP não encontrado. Confira o ID padrão em utils/guild_config.py.",
                ephemeral=True,
            )
            return

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.response.send_message("⚠️ O sistema de revisão não está carregado. Avise um admin.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            resultado_registrado = await desafios.definir_resultado(
                interaction.guild.id,
                desafio_id,
                vencedor.id,
                perdedor_id,
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Falha ao registrar resultado do desafio PvP %s.",
                desafio_id,
            )
            await interaction.followup.send(
                "Não consegui registrar o resultado no armazenamento. Confira o estado da luta antes de tentar novamente.",
                ephemeral=True,
            )
            return

        if not resultado_registrado:
            await interaction.followup.send(
                "Esta luta já foi enviada para revisão ou deixou de estar ativa. Não criei outra prova.",
                ephemeral=True,
            )
            return

        try:
            await revisoes_cog.abrir_revisao(
                interaction.guild, canal,
                tipo="pvp", autor_id=interaction.user.id, referencia_id=desafio_id,
                print_url=print.url, titulo=f"Luta: <@{desafio['desafiante_id']}> vs <@{desafio['desafiado_id']}>",
                descricao=f"Vencedor indicado: {vencedor.mention}",
            )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Falha ao publicar revisão do desafio PvP %s.",
                desafio_id,
            )
            try:
                await desafios.definir_status(
                    interaction.guild.id,
                    desafio_id,
                    "aceito",
                )
            except Exception:
                logging.getLogger(__name__).exception(
                    "Não consegui devolver o desafio %s ao estado aceito.",
                    desafio_id,
                )
            await interaction.followup.send(
                "Não consegui publicar a prova. Se ela não aparecer no canal de provas, tente enviar o resultado novamente e avise a staff se o problema continuar.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(f"✅ Resultado enviado para revisão em {canal.mention}.", ephemeral=True)


    @app_commands.command(
        name="diagnostico-canais",
        description="Verifica canais padrão, IDs configurados e permissões do bot.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def diagnostico_canais(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        config = await get_config(guild.id)
        canais = [
            ("Desafios", "canal_desafios_id", 1545834386128375909),
            ("Lutas", "canal_lutas_id", 1545834447944028170),
            ("Provas PvP", "canal_provas_pvp_id", 1545853928736952420),
            ("Ranking", "canal_ranking_id", 1545834182406574241),
            ("Provas de missões", "canal_provas_missao_id", 1556543417843056641),
            ("Provas de contribuições", "canal_provas_contribuicao_id", 1556543628296593448),
            ("Provas especiais", "canal_provas_especial_id", 1556543872534839336),
            ("Auditoria", "canal_auditoria_id", 1545837705609617428),
        ]
        linhas = []
        bot_member = guild.me

        for nome, chave, padrao in canais:
            configurado = config.get(chave)
            candidatos = []
            if configurado:
                candidatos.append(("configurado", configurado))
            candidatos.append(("padrão", padrao))
            vistos = set()
            resolvido = None
            origem = None

            for fonte, valor in candidatos:
                try:
                    canal_id = int(valor)
                except (TypeError, ValueError):
                    continue
                if canal_id in vistos:
                    continue
                vistos.add(canal_id)
                canal = guild.get_channel(canal_id)
                if canal is None:
                    try:
                        canal = await guild.fetch_channel(canal_id)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        continue
                if callable(getattr(canal, "send", None)):
                    resolvido = canal
                    origem = fonte
                    break

            if resolvido is None:
                linhas.append(f"❌ **{nome}** — canal configurado/padrão não encontrado.")
                continue

            permissoes = resolvido.permissions_for(bot_member) if bot_member else None
            if permissoes is None:
                linhas.append(f"⚠️ **{nome}** — {resolvido.mention}: não consegui verificar permissões.")
                continue

            faltas = []
            if not permissoes.view_channel:
                faltas.append("Ver canal")
            if not permissoes.send_messages:
                faltas.append("Enviar mensagens")
            if not permissoes.embed_links:
                faltas.append("Inserir links/embeds")

            if faltas:
                linhas.append(
                    f"⚠️ **{nome}** — {resolvido.mention} ({origem}); faltam: {', '.join(faltas)}."
                )
            else:
                nota = "configurado" if origem == "configurado" else "usando padrão"
                linhas.append(f"✅ **{nome}** — {resolvido.mention} ({nota}).")

        embed = discord.Embed(
            title="Diagnóstico de canais — NÊMESIS",
            description="\n".join(linhas),
            color=0x57F287 if all("❌" not in linha and "⚠️" not in linha for linha in linhas) else 0xFEE75C,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Desafios(bot))