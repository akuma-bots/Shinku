import asyncio
import logging

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
        texto = str(descricao or "Consulte a descrição com a liderança.").strip()
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

            parte = texto[:corte].rstrip()
            if parte:
                partes.append(parte)
            texto = texto[corte:].lstrip()

        return partes or ["Consulte a descrição com a liderança."]

    @classmethod
    def _montar_embeds(cls, atividade: dict) -> list[discord.Embed]:
        """Monta uma ou mais mensagens para descrições de até 20.000 caracteres."""
        tipo = TIPOS.get(str(atividade.get("tipo", "missao")).lower(), TIPOS["missao"])
        ativa = atividade.get("ativa", True)
        try:
            recompensa = max(0, int(atividade.get("recompensa_xp", atividade.get("pontos", 0)) or 0))
        except (TypeError, ValueError):
            recompensa = 0

        titulo_base = f"NÊMESIS — {atividade.get('titulo', 'Missão')}"[:256]
        partes = cls._dividir_descricao(atividade.get("descricao"))
        embeds = []

        for indice, parte in enumerate(partes, start=1):
            if indice == 1:
                titulo = titulo_base
            else:
                sufixo = f" — continuação {indice}/{len(partes)}"
                titulo = f"{titulo_base[:256 - len(sufixo)]}{sufixo}"

            embed = discord.Embed(
                title=titulo,
                description=parte,
                color=0x5865F2 if ativa else 0x747F8D,
            )

            if indice == 1:
                embed.add_field(name="Categoria", value=tipo["nome"], inline=True)
                embed.add_field(name="ID da missão", value=f"`{atividade.get('id', '—')}`", inline=True)
                embed.add_field(name="Recompensa", value=f"+{recompensa} de pontuação e +{recompensa} XP", inline=False)
                if ativa:
                    embed.add_field(
                        name="Como concluir",
                        value=(
                            "Conclua a atividade e envie uma captura de tela como prova usando "
                            f"`/missao-completar missao_id:{atividade.get('id', '')}`."
                        ),
                        inline=False,
                    )
                    embed.set_footer(text="Missão padrão gerenciada pelo GitHub • A publicação é atualizada pelo bot")
                else:
                    embed.add_field(name="Status", value="Esta missão está encerrada.", inline=False)
                    embed.set_footer(text="Missão encerrada • A publicação permanece no canal como histórico")
            else:
                embed.set_footer(text=f"NÊMESIS • Continuação da descrição da missão • {indice}/{len(partes)}")

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
                            await mensagem_parte.edit(embed=embed)
                            resultado["atualizadas"] += 1
                        else:
                            mensagem_parte = await canal.send(embed=embed)
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

    @app_commands.command(name="missao-completar", description="Envia uma prova de conclusão de missão.")
    @app_commands.describe(
        missao_id="ID da missão, pontuação ou missão especial",
        print="Imagem comprovando a conclusão",
    )
    async def missao_completar(
        self,
        interaction: discord.Interaction,
        missao_id: str,
        print: discord.Attachment,
    ):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ Use este comando dentro do servidor.", ephemeral=True)
            return

        atividade = await missoes.get(guild.id, missao_id)
        if not atividade or not atividade.get("ativa", True):
            await interaction.followup.send("❌ Não encontrei uma atividade ativa com esse ID.", ephemeral=True)
            return

        tipo = str(atividade.get("tipo", "missao")).lower()
        if tipo not in TIPOS:
            await interaction.followup.send("❌ Tipo de atividade inválido. Peça à staff para corrigir a configuração.", ephemeral=True)
            return

        config = await get_config(guild.id)
        chave_prova = {
            "missao": "canal_provas_missao_id",
            "contribuicao": "canal_provas_contribuicao_id",
            "especial": "canal_provas_especial_id",
        }[tipo]
        canal_id = config.get(chave_prova) or CANAIS_PADRAO.get(chave_prova)
        canal = await self._resolver_canal(guild, canal_id) if canal_id else None
        if canal is None:
            await interaction.followup.send("❌ O canal de provas desse tipo ainda não foi configurado.", ephemeral=True)
            return

        revisoes_cog = self.bot.get_cog("Revisoes")
        if not revisoes_cog:
            await interaction.followup.send("❌ O sistema de revisão não está carregado. Avise a staff.", ephemeral=True)
            return

        info = TIPOS[tipo]
        await revisoes_cog.abrir_revisao(
            guild,
            canal,
            tipo="missao",
            autor_id=interaction.user.id,
            referencia_id=str(atividade["id"]),
            print_url=print.url,
            titulo=f"{info['emoji']} {info['nome']} — {atividade.get('titulo', 'Atividade')}",
            descricao=(
                f"Prova enviada por {interaction.user.mention}. "
                f"Recompensa: +{int(atividade.get('recompensa_xp', atividade.get('pontos', 0)) or 0)} "
                "de pontuação e XP."
            ),
        )
        await interaction.followup.send(
            f"✅ Sua prova foi enviada para {canal.mention} e aguarda revisão da staff.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(Missoes(bot))
