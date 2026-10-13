import asyncio
import logging
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from utils import missoes
from utils.catalogo_missoes import (
    carregar_catalogo,
    sincronizar_catalogo,
    salvar_mensagem_discord,
    obter_mensagem_discord,
)
from utils.guild_config import get_config
from utils.perfis import (
    get_perfil,
    _salvar_perfil,
    _sincronizar_site,
    calcular_patente_atual,
    definir_patente,
)


log = logging.getLogger(__name__)


class EnviarProvaMissaoModal(discord.ui.Modal, title="Enviar provas da missão"):
    missao_id = discord.ui.TextInput(
        label="ID da missão",
        placeholder="Ex.: M-001",
        required=True,
        max_length=50,
    )
    imagem_url = discord.ui.TextInput(
        label="Link da imagem da prova (Discord)",
        placeholder="Envie a imagem no Discord e cole o link da imagem",
        required=True,
        max_length=1000,
    )

    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.receber_prova_modal(interaction, str(self.missao_id.value), str(self.imagem_url.value))


class EnviarProvaMissaoView(discord.ui.View):
    """Botão persistente para abrir o formulário de envio de provas."""

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="ENVIAR PROVAS",
        style=discord.ButtonStyle.primary,
        emoji="📨",
        custom_id="nemesis:missao:enviar_provas",
    )
    async def enviar_provas(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EnviarProvaMissaoModal(self.cog))


TIPOS = {
    "missao": {"nome": "Missão", "emoji": "🎯"},
    # O valor interno antigo é mantido para compatibilidade com os dados existentes.
    "contribuicao": {"nome": "Contribuição", "emoji": "✦"},
    "especial": {"nome": "Missão especial", "emoji": "⭐"},
}

CANAIS_PADRAO = {
    "canal_missoes_missao_id": 1556543214885019668,
    "canal_missoes_contribuicao_id": 1556543539213639760,
    "canal_missoes_especial_id": 1556543708478972015,
    "canal_provas_missao_id": 1556543417843056641,
    "canal_provas_contribuicao_id": 1556543628296593448,
    "canal_provas_especial_id": 1556543872534839336,
}

NOMES_CANAIS = {}


class Missoes(commands.Cog):
    """Missões permanentes definidas no GitHub e revisão de provas."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._sync_lock = asyncio.Lock()
        # O custom_id fixo mantém o botão funcional mesmo após reinícios do bot.
        self.bot.add_view(EnviarProvaMissaoView(self))
        if not hasattr(bot, "processadores_revisao"):
            bot.processadores_revisao = {}
        for tipo in ("missao", "contribuicao", "especial"):
            bot.processadores_revisao[tipo] = self.processar_aprovacao

    @commands.Cog.listener()
    async def on_ready(self):
        guild = self.bot.get_guild(1543381737961160910)
        if guild is None:
            log.warning("Missões padrão: servidor NÊMESIS não encontrado no cache.")
            return
        await self.sincronizar_missoes_discord(guild)

    async def _resolver_canal(self, guild: discord.Guild, canal_id: int):
        canal = guild.get_channel(int(canal_id))
        if canal is None:
            try:
                canal = await guild.fetch_channel(int(canal_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as erro:
                log.warning("Não foi possível resolver o canal %s: %s", canal_id, erro)
                return None
        return canal if isinstance(canal, discord.TextChannel) else None

    async def _renomear_canais_pontuacao(self, guild: discord.Guild, config: dict):
        bot_member = guild.me
        if bot_member is None:
            return
        for chave, nome_novo in NOMES_CANAIS.items():
            canal_id = config.get(chave) or CANAIS_PADRAO.get(chave)
            if not canal_id:
                continue
            canal = await self._resolver_canal(guild, canal_id)
            if canal is None or canal.name == nome_novo:
                continue
            if not canal.permissions_for(bot_member).manage_channels:
                log.warning("Sem permissão para renomear o canal %s para %s.", canal.id, nome_novo)
                continue
            try:
                await canal.edit(name=nome_novo, reason="Padronização do sistema de missões da NÊMESIS")
            except discord.HTTPException:
                log.exception("Falha ao renomear o canal %s.", canal.id)

    @staticmethod
    def _dividir_descricao(descricao: str, limite: int = 3800) -> list[str]:
        """Divide descrições longas em blocos compatíveis com o limite do Discord."""
        texto = str(descricao if descricao is not None else "")
        if not texto:
            texto = "Consulte a descrição com a liderança."
        if len(texto) > 20000:
            texto = texto[:20000]

        partes = []
        while texto:
            if len(texto) <= limite:
                partes.append(texto)
                break

            corte = texto.rfind(chr(10), 0, limite)
            if corte < limite // 2:
                corte = texto.rfind(" ", 0, limite)
            if corte < limite // 2:
                corte = limite
            elif corte < limite:
                # Mantém a quebra de linha/espaço para não perder caracteres.
                corte += 1

            partes.append(texto[:corte])
            texto = texto[corte:]

        return partes or ["Consulte a descrição com a liderança."]

    @classmethod
    def _montar_embeds(cls, atividade: dict) -> list[discord.Embed]:
        """Cria o cartão oficial de missão, preservando descrições longas integralmente."""
        tipo = TIPOS.get(str(atividade.get("tipo", "missao")).lower(), TIPOS["missao"])
        ativa = atividade.get("ativa", True)
        try:
            recompensa = max(0, int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0))
        except (TypeError, ValueError):
            recompensa = 0

        titulo_base = f"𝐍̷Ê𝐌𝐄𝐒𝐈𝐒  ━  {atividade.get('titulo', 'Missão')}"[:256]
        descricao_original = str(atividade.get("descricao") or "").strip()
        if not descricao_original:
            descricao_original = "Esta missão ainda não possui uma descrição detalhada."

        partes = cls._dividir_descricao(descricao_original)
        embeds = []
        cor = 0xB51F32 if ativa else 0x454545

        for indice, parte in enumerate(partes, start=1):
            sufixo = f"  ━  PARTE {indice}/{len(partes)}" if len(partes) > 1 else ""
            titulo = f"{titulo_base[:256 - len(sufixo)]}{sufixo}"
            embed = discord.Embed(
                title=titulo,
                description=(
                    "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
                    f"   {'MISSÃO DISPONÍVEL' if ativa else 'MISSÃO ENCERRADA'}\n"
                    "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
                    f"{parte}"
                ),
                color=cor,
            )

            if indice == 1:
                embed.add_field(
                    name="◈ CLASSIFICAÇÃO",
                    value=f"**{tipo['nome']}**\nID: {atividade.get('id', '—')}",
                    inline=True,
                )
                embed.add_field(
                    name="◈ RECOMPENSA",
                    value=f"**{recompensa:,} P.C.**\n**{recompensa:,} XP**".replace(",", "."),
                    inline=True,
                )
                if ativa:
                    embed.add_field(
                        name="◈ PROCEDIMENTO",
                        value=(
                            "1. Leia todos os requisitos da missão.\n"
                            "2. Conclua a atividade no jogo.\n"
                            "3. Clique em **ENVIAR PROVAS** e informe o ID da missão e o link da evidência.\n"
                            "4. Aguarde a análise da staff; a recompensa é liberada após aprovação."
                        ),
                        inline=False,
                    )
                    embed.set_footer(text="NÊMESIS  •  OPERAÇÕES OFICIAIS  •  Envio sujeito à validação da staff")
                else:
                    embed.add_field(
                        name="◈ SITUAÇÃO",
                        value="Esta operação foi encerrada. A publicação permanece disponível apenas para consulta.",
                        inline=False,
                    )
                    embed.set_footer(text="NÊMESIS  •  ARQUIVO DE OPERAÇÕES")
            else:
                embed.set_footer(text=f"NÊMESIS  •  CONTINUAÇÃO DA MISSÃO  •  {indice}/{len(partes)}")

            embeds.append(embed)

        return embeds

    async def sincronizar_missoes_discord(self, guild: discord.Guild) -> dict:
        """Publica cada missão padrão uma vez e edita a mesma mensagem nos próximos reinícios."""
        if self._sync_lock.locked():
            return {"atualizadas": 0, "publicadas": 0, "falhas": 0, "ignorada": True}

        async with self._sync_lock:
            catalogo = carregar_catalogo()
            atividades = await sincronizar_catalogo(guild.id, catalogo)
            config = await get_config(guild.id)
            await self._renomear_canais_pontuacao(guild, config)

            resultado = {"atualizadas": 0, "publicadas": 0, "falhas": 0}
            for atividade in atividades:
                chave_canal = atividade.get("canal_config", "")
                canal_id = config.get(chave_canal) or CANAIS_PADRAO.get(chave_canal)
                if not canal_id:
                    log.error("Missão %s sem canal configurado (%s).", atividade.get("id"), chave_canal)
                    resultado["falhas"] += 1
                    continue

                canal = await self._resolver_canal(guild, canal_id)
                if canal is None:
                    log.error("Canal da missão %s não encontrado: %s", atividade.get("id"), canal_id)
                    resultado["falhas"] += 1
                    continue

                mensagem = None
                registro_mensagem = await obter_mensagem_discord(guild.id, str(atividade["id"]))
                mensagem_id = registro_mensagem.get("discord_message_id") or atividade.get("discord_message_id")
                canal_salvo_id = registro_mensagem.get("discord_channel_id") or atividade.get("discord_channel_id")
                if mensagem_id and str(canal_salvo_id) == str(canal.id):
                    try:
                        mensagem = await canal.fetch_message(int(mensagem_id))
                    except discord.NotFound:
                        mensagem = None
                    except (discord.Forbidden, discord.HTTPException) as erro:
                        log.warning("Falha ao buscar mensagem da missão %s: %s", atividade.get("id"), erro)
                        resultado["falhas"] += 1
                        continue

                embeds = self._montar_embeds(atividade)
                ids_mensagens = registro_mensagem.get("discord_message_ids") or []
                if not ids_mensagens and mensagem_id:
                    ids_mensagens = [mensagem_id]

                mensagens_atualizadas = []
                falhou = False
                for indice, embed in enumerate(embeds):
                    mensagem_parte = None
                    if indice < len(ids_mensagens):
                        try:
                            mensagem_parte = await canal.fetch_message(int(ids_mensagens[indice]))
                        except discord.NotFound:
                            mensagem_parte = None
                        except (discord.Forbidden, discord.HTTPException) as erro_busca:
                            log.warning("Falha ao buscar parte %s da missão %s: %s", indice + 1, atividade.get("id"), erro_busca)
                            falhou = True
                            break

                    try:
                        if mensagem_parte is not None:
                            await mensagem_parte.edit(
                                embed=embed,
                                view=EnviarProvaMissaoView(self)
                                if indice == 0 and atividade.get("ativa", True)
                                else None,
                            )
                            resultado["atualizadas"] += 1
                        else:
                            mensagem_parte = await canal.send(
                                embed=embed,
                                view=EnviarProvaMissaoView(self)
                                if indice == 0 and atividade.get("ativa", True)
                                else None,
                            )
                            resultado["publicadas"] += 1

                        if indice == 0:
                            try:
                                if not mensagem_parte.pinned:
                                    await mensagem_parte.pin(reason="Missão padrão permanente da NÊMESIS")
                            except discord.HTTPException as erro_fixar:
                                log.warning("Não foi possível fixar a missão %s; a mensagem continuará no canal: %s", atividade.get("id"), erro_fixar)

                        mensagens_atualizadas.append(int(mensagem_parte.id))
                    except (discord.Forbidden, discord.HTTPException) as erro:
                        log.exception("Não foi possível publicar/atualizar a parte %s da missão %s: %s", indice + 1, atividade.get("id"), erro)
                        falhou = True
                        break

                if falhou or not mensagens_atualizadas:
                    resultado["falhas"] += 1
                    continue

                for id_antigo in ids_mensagens[len(embeds):]:
                    try:
                        antiga = await canal.fetch_message(int(id_antigo))
                        await antiga.delete()
                    except (TypeError, ValueError, discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass

                await salvar_mensagem_discord(
                    guild.id,
                    str(atividade["id"]),
                    canal.id,
                    mensagens_atualizadas,
                )

            log.info(
                "Catálogo de missões sincronizado: %s publicadas, %s atualizadas, %s falhas.",
                resultado["publicadas"], resultado["atualizadas"], resultado["falhas"],
            )
            return resultado

    @app_commands.command(
        name="missoes-sincronizar",
        description="Publica ou atualiza as missões padrão nos canais oficiais.",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def missoes_sincronizar(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        if interaction.guild is None:
            await interaction.followup.send("Use este comando dentro do servidor.", ephemeral=True)
            return
        try:
            resultado = await self.sincronizar_missoes_discord(interaction.guild)
        except Exception as erro:
            log.exception("Erro na sincronização manual das missões.")
            await interaction.followup.send(f"Falha ao sincronizar as missões: `{type(erro).__name__}`.", ephemeral=True)
            return
        await interaction.followup.send(
            "Sincronização concluída. "
            f"Publicadas: **{resultado.get('publicadas', 0)}** · "
            f"Atualizadas: **{resultado.get('atualizadas', 0)}** · "
            f"Falhas: **{resultado.get('falhas', 0)}**.",
            ephemeral=True,
        )

    async def processar_aprovacao(self, guild: discord.Guild, revisao: dict) -> str:
        atividade = await missoes.get(guild.id, revisao.get("referencia_id", ""))
        if not atividade:
            return "⚠️ A atividade original não foi encontrada; nenhuma recompensa foi aplicada."

        revisao_id = str(revisao.get("id", ""))
        if revisao_id in atividade.get("recompensas_aplicadas", []):
            return "Esta revisão já foi contabilizada; nenhuma recompensa duplicada foi aplicada."

        autor_id = int(revisao.get("autor_id", 0))
        if not autor_id:
            return "⚠️ Não foi possível identificar o participante."

        try:
            recompensa = max(0, int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0))
        except (TypeError, ValueError):
            recompensa = 0

        perfil = await get_perfil(guild.id, autor_id)
        perfil["xp"] = int(perfil.get("xp", 0) or 0) + recompensa
        await _salvar_perfil(guild.id, autor_id, perfil)

        # Recompensa aprovada também avança a progressão independente da gangue.
        progressao = self.bot.get_cog("ProgressaoGangue")
        if progressao is not None and recompensa > 0:
            try:
                tipo_progressao = str(atividade.get("tipo", "missao")).lower()
                if tipo_progressao not in {"missao", "contribuicao", "especial"}:
                    tipo_progressao = "missao"
                await progressao.registrar_recompensa(
                    guild=guild,
                    user_id=autor_id,
                    quantidade=recompensa,
                    tipo=tipo_progressao,
                    evento_id=revisao_id,
                )
            except Exception as erro:
                log.exception("Falha ao registrar recompensa na progressão da gangue para %s: %s", autor_id, erro)

        dados_guild = await missoes._guild(guild.id)
        alvo = next(
            (item for item in dados_guild.get("missoes", [])
             if str(item.get("id")) == str(atividade.get("id"))),
            None,
        )
        if alvo is not None:
            aplicadas = alvo.setdefault("recompensas_aplicadas", [])
            if revisao_id not in aplicadas:
                aplicadas.append(revisao_id)
            await missoes._salvar_guild(guild.id, dados_guild)

        membro = guild.get_member(autor_id)
        try:
            await _sincronizar_site(
                user_id=autor_id,
                perfil=perfil,
                nome=membro.display_name if membro else "",
                delta_pontos=recompensa,
            )
        except Exception as erro:
            log.exception("Falha ao sincronizar pontuação de %s: %s", autor_id, erro)

        texto = f"✅ <@{autor_id}> recebeu **+{recompensa} XP** e **+{recompensa} de pontuação**."
        nova_patente = await calcular_patente_atual(guild.id, perfil["xp"])
        if nova_patente and nova_patente.get("nome") != perfil.get("patente"):
            await definir_patente(guild.id, autor_id, nova_patente["nome"])
            cargo_id = nova_patente.get("cargo_id")
            cargo = guild.get_role(int(cargo_id)) if cargo_id else None
            if membro and cargo:
                try:
                    await membro.add_roles(cargo, reason="Promoção automática por conclusão de missão")
                except discord.Forbidden:
                    pass
            texto += f" Nova patente: **{nova_patente['nome']}**."
        return texto

    async def receber_prova_modal(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        imagem_url: str,
    ):
        """Valida a missão e encaminha a prova para revisão da staff."""
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Use este botão dentro do servidor da NÊMESIS.", ephemeral=True)
            return

        atividade = await missoes.get(guild.id, missao_id.strip())
        if not atividade or not atividade.get("ativa", True):
            await interaction.followup.send(
                "❌ Não encontrei uma missão ativa com esse ID. Confira o ID na publicação da missão.",
                ephemeral=True,
            )
            return

        tipo = str(atividade.get("tipo", "missao")).lower()
        if tipo not in TIPOS:
            await interaction.followup.send(
                "❌ O tipo desta atividade está inválido. Avise a staff.",
                ephemeral=True,
            )
            return

        url = imagem_url.strip()
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if (
            parsed.scheme != "https"
            or host not in {"cdn.discordapp.com", "media.discordapp.net"}
            or not parsed.path
        ):
            await interaction.followup.send(
                "❌ O link precisa ser de uma imagem hospedada no Discord. Envie a imagem em um canal permitido, abra a imagem, copie o link e cole aqui.",
                ephemeral=True,
            )
            return

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.followup.send(
                "❌ O sistema de revisão não está carregado. Avise a staff.",
                ephemeral=True,
            )
            return

        from utils import revisoes

        pendentes = await revisoes.listar(guild.id, status="pendente")
        ja_enviada = any(
            int(item.get("autor_id", 0) or 0) == interaction.user.id
            and str(item.get("referencia_id", "")) == str(atividade["id"])
            and item.get("tipo") == "missao"
            for item in pendentes
        )
        if ja_enviada:
            await interaction.followup.send(
                "⏳ Você já tem uma prova pendente para esta missão. Aguarde a análise da staff antes de enviar outra.",
                ephemeral=True,
            )
            return

        info = TIPOS[tipo]
        recompensa = max(
            0,
            int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0),
        )
        canal_config = await get_config(guild.id)
        chave_prova = {
            "missao": "canal_provas_missao_id",
            "contribuicao": "canal_provas_contribuicao_id",
            "especial": "canal_provas_especial_id",
        }[tipo]
        canal_id = canal_config.get(chave_prova) or CANAIS_PADRAO.get(chave_prova)
        canal = await self._resolver_canal(guild, canal_id) if canal_id else None
        if canal is None:
            await interaction.followup.send(
                "❌ O canal de provas deste tipo não foi encontrado. Avise a staff.",
                ephemeral=True,
            )
            return

        try:
            await revisoes_cog.abrir_revisao(
                guild,
                canal,
                tipo="missao",
                autor_id=interaction.user.id,
                referencia_id=str(atividade["id"]),
                print_url=url,
                titulo=f"{info['emoji']} {info['nome']} — {atividade.get('titulo', 'Atividade')}",
                descricao=(
                    f"Prova enviada por {interaction.user.mention}. "
                    f"ID da missão: `{atividade['id']}`. "
                    f"Recompensa após aprovação: +{recompensa} de pontuação e +{recompensa} XP."
                ),
            )
        except (discord.Forbidden, discord.HTTPException):
            log.exception("Falha ao criar revisão da missão %s.", atividade.get("id"))
            await interaction.followup.send(
                "❌ Não consegui publicar a prova para revisão. Verifique se o bot tem permissão para enviar mensagens e Embeds no canal de provas.",
                ephemeral=True,
            )
            return
        except Exception:
            log.exception("Erro inesperado ao receber prova da missão %s.", atividade.get("id"))
            await interaction.followup.send(
                "❌ Ocorreu um erro ao enviar sua prova. Tente novamente mais tarde.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            f"✅ Prova enviada para {canal.mention}. A recompensa será aplicada somente após a aprovação da staff.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Missoes(bot))
