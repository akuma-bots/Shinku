import datetime
import secrets
import time

import discord
from discord import app_commands
from discord.ext import commands

from utils.apresentacao import criar_embed
from utils.guild_config import lideranca_only
from utils.storage import atualizar_json, carregar


ARQUIVO_ACADEMIA = "academia_nemesis.json"
FUSO_BRASIL = datetime.timezone(datetime.timedelta(hours=-3))
_LIMITE_SESSOES = 300


def _chave_servidor(guild_id: int) -> str:
    return str(int(guild_id))


def _sessoes_do_servidor(dados: dict, guild_id: int) -> dict:
    if not isinstance(dados, dict):
        return {}
    servidor = dados.get(_chave_servidor(guild_id), {})
    if not isinstance(servidor, dict):
        return {}
    sessoes = servidor.get("sessoes", {})
    return sessoes if isinstance(sessoes, dict) else {}


def _criar_registro_sessao(*, sessao_id: str, nome: str, descricao: str, inicio: float, vagas: int, criador_id: int, agora: float | None = None) -> dict:
    agora = float(agora or time.time())
    return {
        "id": str(sessao_id),
        "nome": str(nome).strip()[:100],
        "descricao": str(descricao).strip()[:1500],
        "inicio": float(inicio),
        "vagas": max(0, min(int(vagas or 0), 500)),
        "status": "aberta",
        "criado_por": int(criador_id),
        "criado_em": agora,
        "atualizado_em": agora,
        "inscritos": {},
    }


def _inscrever(registro: dict, user_id: int, *, agora: float | None = None) -> tuple[dict, str]:
    registro = dict(registro or {})
    inscritos = registro.get("inscritos", {})
    inscritos = dict(inscritos) if isinstance(inscritos, dict) else {}
    user_key = str(int(user_id))
    if registro.get("status") != "aberta":
        return registro, "encerrada"
    if user_key in inscritos:
        return registro, "ja_inscrito"
    vagas = max(0, int(registro.get("vagas", 0) or 0))
    if vagas and len(inscritos) >= vagas:
        return registro, "lotada"
    agora = float(agora or time.time())
    inscritos[user_key] = {
        "status": "inscrito",
        "inscrito_em": agora,
        "avaliado_em": None,
        "avaliado_por": None,
        "observacao": "",
    }
    registro["inscritos"] = inscritos
    registro["atualizado_em"] = agora
    return registro, "inscrito"


def _avaliar_inscrito(registro: dict, user_id: int, resultado: str, avaliador_id: int, observacao: str = "", *, agora: float | None = None) -> tuple[dict, str]:
    registro = dict(registro or {})
    inscritos = registro.get("inscritos", {})
    inscritos = dict(inscritos) if isinstance(inscritos, dict) else {}
    user_key = str(int(user_id))
    resultado = str(resultado or "").strip().lower()
    if resultado not in {"aprovado", "reprovado", "ausente"}:
        return registro, "resultado_invalido"
    if user_key not in inscritos:
        return registro, "nao_inscrito"
    agora = float(agora or time.time())
    participante = dict(inscritos[user_key])
    avaliacao = {
        "status": resultado,
        "avaliado_em": agora,
        "avaliado_por": int(avaliador_id),
        "observacao": str(observacao or "").strip()[:500],
    }
    historico_avaliacoes = participante.get("historico_avaliacoes", [])
    if not isinstance(historico_avaliacoes, list):
        historico_avaliacoes = []
    historico_avaliacoes.append(dict(avaliacao))
    participante["historico_avaliacoes"] = historico_avaliacoes[-10:]
    participante.update(avaliacao)
    inscritos[user_key] = participante
    registro["inscritos"] = inscritos
    registro["atualizado_em"] = agora
    return registro, "avaliado"


def _encerrar_sessao(registro: dict, *, agora: float | None = None) -> tuple[dict, bool]:
    registro = dict(registro or {})
    if registro.get("status") != "aberta":
        return registro, False
    agora = float(agora or time.time())
    registro["status"] = "encerrada"
    registro["encerrada_em"] = agora
    registro["atualizado_em"] = agora
    return registro, True


class Academia(commands.GroupCog, group_name="academia", group_description="Treinamentos, inscrições e avaliações da NÊMESIS"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _atualizar_sessao(self, guild_id: int, sessao_id: str, transformador):
        resultado = {"status": "nao_encontrada"}

        def aplicar(documento):
            if not isinstance(documento, dict):
                documento = {}
            chave = _chave_servidor(guild_id)
            servidor = documento.get(chave, {})
            if not isinstance(servidor, dict):
                servidor = {}
            sessoes = servidor.get("sessoes", {})
            if not isinstance(sessoes, dict):
                sessoes = {}
            registro = sessoes.get(str(sessao_id))
            if not isinstance(registro, dict):
                documento[chave] = {**servidor, "sessoes": sessoes}
                return documento
            atualizado, status = transformador(registro)
            resultado["status"] = status
            if status in {"inscrito", "avaliado", "encerrada"}:
                sessoes[str(sessao_id)] = atualizado
            servidor["sessoes"] = sessoes
            documento[chave] = servidor
            return documento

        await atualizar_json(ARQUIVO_ACADEMIA, {}, aplicar)
        return resultado["status"]

    @app_commands.command(name="criar", description="Registra um novo treinamento na Academia Nêmesis.")
    @app_commands.describe(nome="Nome do treinamento", descricao="Objetivo, conteúdo e orientações", data_hora="DD/MM/AAAA HH:MM, horário de Brasília", vagas="Limite de participantes; 0 significa sem limite")
    @lideranca_only()
    async def criar(self, interaction: discord.Interaction, nome: app_commands.Range[str, 3, 100], descricao: app_commands.Range[str, 10, 1500], data_hora: str, vagas: app_commands.Range[int, 0, 500] = 0):
        try:
            inicio_dt = datetime.datetime.strptime(data_hora, "%d/%m/%Y %H:%M").replace(tzinfo=FUSO_BRASIL)
        except ValueError:
            await interaction.response.send_message("Data inválida. Utilize DD/MM/AAAA HH:MM no horário de Brasília.", ephemeral=True)
            return
        inicio = inicio_dt.timestamp()
        if inicio <= time.time():
            await interaction.response.send_message("A data do treinamento precisa estar no futuro.", ephemeral=True)
            return
        sessao_id = f"ACD-{secrets.token_hex(3).upper()}"
        registro = _criar_registro_sessao(sessao_id=sessao_id, nome=nome, descricao=descricao, inicio=inicio, vagas=vagas, criador_id=interaction.user.id)

        resultado_criacao = {"criado": False}

        def aplicar(documento):
            if not isinstance(documento, dict):
                documento = {}
            chave = _chave_servidor(interaction.guild.id)
            servidor = documento.get(chave, {})
            if not isinstance(servidor, dict):
                servidor = {}
            sessoes = servidor.get("sessoes", {})
            if not isinstance(sessoes, dict):
                sessoes = {}
            encerradas = sorted(
                (
                    (chave_sessao, item)
                    for chave_sessao, item in sessoes.items()
                    if isinstance(item, dict) and item.get("status") == "encerrada"
                ),
                key=lambda item: float(item[1].get("criado_em", 0) or 0),
            )
            while len(sessoes) >= _LIMITE_SESSOES and encerradas:
                chave_antiga, _ = encerradas.pop(0)
                sessoes.pop(chave_antiga, None)
            if len(sessoes) >= _LIMITE_SESSOES:
                documento[chave] = {**servidor, "sessoes": sessoes}
                return documento
            sessoes[sessao_id] = registro
            resultado_criacao["criado"] = True
            servidor["sessoes"] = sessoes
            documento[chave] = servidor
            return documento

        await atualizar_json(ARQUIVO_ACADEMIA, {}, aplicar)
        if not resultado_criacao["criado"]:
            await interaction.response.send_message(
                "A Academia atingiu o limite de sessões abertas e históricas. "
                "Encerre treinamentos concluídos antes de criar outro.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Treinamento {nome} registrado na Academia.\nCódigo: {sessao_id}\n"
            f"Início: {discord.utils.format_dt(inicio_dt, style='F')}\n"
            f"Vagas: {'Ilimitadas' if not vagas else vagas}",
            ephemeral=True,
        )

    @app_commands.command(name="listar", description="Consulta os treinamentos disponíveis.")
    async def listar(self, interaction: discord.Interaction):
        documento = await carregar(ARQUIVO_ACADEMIA, {})
        sessoes = _sessoes_do_servidor(documento, interaction.guild.id)
        abertas = [item for item in sessoes.values() if isinstance(item, dict) and item.get("status") == "aberta"]
        abertas.sort(key=lambda item: float(item.get("inicio", 0) or 0))
        embed = criar_embed(title="𓂀 ACADEMIA NÊMESIS · TREINAMENTOS", description="Treinamentos cadastrados e disponíveis para inscrição.", color=0x9F1239, rodape=None)
        if not abertas:
            embed.add_field(name="AGENDA", value="Não há treinamentos abertos no momento.", inline=False)
        else:
            for item in abertas[:10]:
                inscritos = item.get("inscritos", {})
                inscritos = inscritos if isinstance(inscritos, dict) else {}
                vagas = int(item.get("vagas", 0) or 0)
                ocupacao = f"{len(inscritos)}/{vagas}" if vagas else f"{len(inscritos)}/Ilimitadas"
                inicio = datetime.datetime.fromtimestamp(float(item.get("inicio", 0)), tz=FUSO_BRASIL)
                embed.add_field(
                    name=f"{item.get('nome', 'Treinamento')[:150]} · {item.get('id', '—')}",
                    value=f"{str(item.get('descricao') or 'Sem descrição.')[:350]}\n"
                    f"Início: {discord.utils.format_dt(inicio, style='F')}\nInscrições: {ocupacao}",
                    inline=False,
                )
        embed.set_footer(text="Use /academia inscrever com o código do treinamento")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="inscrever", description="Inscreve você em um treinamento aberto.")
    @app_commands.describe(sessao_id="Código exibido em /academia listar")
    async def inscrever(self, interaction: discord.Interaction, sessao_id: str):
        status = await self._atualizar_sessao(interaction.guild.id, sessao_id.strip().upper(), lambda registro: _inscrever(registro, interaction.user.id))
        respostas = {
            "inscrito": "Sua inscrição foi registrada.",
            "ja_inscrito": "Você já está inscrito neste treinamento.",
            "lotada": "Este treinamento atingiu o limite de vagas.",
            "encerrada": "As inscrições deste treinamento estão encerradas.",
            "nao_encontrada": "Não encontrei esse treinamento. Confira o código.",
        }
        await interaction.response.send_message(respostas.get(status, "Não foi possível concluir a inscrição."), ephemeral=True)

    @app_commands.command(name="avaliar", description="Registra o resultado de um participante.")
    @app_commands.describe(sessao_id="Código do treinamento", membro="Participante inscrito", resultado="Resultado da avaliação", observacao="Comentário breve sobre a avaliação")
    @app_commands.choices(resultado=[
        app_commands.Choice(name="Aprovado", value="aprovado"),
        app_commands.Choice(name="Reprovado", value="reprovado"),
        app_commands.Choice(name="Ausente", value="ausente"),
    ])
    @lideranca_only()
    async def avaliar(self, interaction: discord.Interaction, sessao_id: str, membro: discord.Member, resultado: app_commands.Choice[str], observacao: app_commands.Range[str, 0, 500] = ""):
        status = await self._atualizar_sessao(
            interaction.guild.id,
            sessao_id.strip().upper(),
            lambda registro: _avaliar_inscrito(registro, membro.id, resultado.value, interaction.user.id, observacao),
        )
        respostas = {
            "avaliado": f"Avaliação de {membro.mention} registrada como {resultado.name}.",
            "nao_inscrito": "Esse membro não possui inscrição neste treinamento.",
            "resultado_invalido": "Resultado de avaliação inválido.",
            "nao_encontrada": "Não encontrei esse treinamento. Confira o código.",
        }
        await interaction.response.send_message(respostas.get(status, "Não foi possível registrar a avaliação."), ephemeral=True)

    @app_commands.command(name="encerrar", description="Encerra as inscrições de um treinamento.")
    @app_commands.describe(sessao_id="Código do treinamento")
    @lideranca_only()
    async def encerrar(self, interaction: discord.Interaction, sessao_id: str):
        status = await self._atualizar_sessao(
            interaction.guild.id,
            sessao_id.strip().upper(),
            lambda registro: (lambda resultado: (resultado[0], "encerrada" if resultado[1] else "ja_encerrada"))(_encerrar_sessao(registro)),
        )
        respostas = {
            "encerrada": "Treinamento encerrado. O histórico e as avaliações foram preservados.",
            "ja_encerrada": "Este treinamento já estava encerrado.",
            "nao_encontrada": "Não encontrei esse treinamento. Confira o código.",
        }
        await interaction.response.send_message(respostas.get(status, "Não foi possível encerrar o treinamento."), ephemeral=True)

    async def _montar_historico(self, interaction: discord.Interaction, membro: discord.Member):
        documento = await carregar(ARQUIVO_ACADEMIA, {})
        sessoes = _sessoes_do_servidor(documento, interaction.guild.id)
        resultados = []
        for sessao in sessoes.values():
            if not isinstance(sessao, dict):
                continue
            inscritos = sessao.get("inscritos", {})
            participante = inscritos.get(str(membro.id)) if isinstance(inscritos, dict) else None
            if isinstance(participante, dict):
                resultados.append((sessao, participante))
        resultados.sort(key=lambda item: float(item[0].get("inicio", 0) or 0), reverse=True)
        embed = criar_embed(title="𓂀 ACADEMIA NÊMESIS · HISTÓRICO", description=f"Treinamentos registrados para {membro.mention}.", color=0x9F1239, rodape=None)
        if not resultados:
            embed.add_field(name="HISTÓRICO", value="Nenhum treinamento registrado.", inline=False)
        else:
            for sessao, participante in resultados[:15]:
                estado = str(participante.get("status", "inscrito")).replace("_", " ").title()
                inicio = datetime.datetime.fromtimestamp(float(sessao.get("inicio", 0)), tz=FUSO_BRASIL)
                embed.add_field(
                    name=f"{str(sessao.get('nome', 'Treinamento'))[:150]} · {estado}",
                    value=f"Código: {sessao.get('id', '—')}\nData: {discord.utils.format_dt(inicio, style='D')}\n"
                    f"Observação: {str(participante.get('observacao') or '—')[:250]}",
                    inline=False,
                )
        return embed

    @app_commands.command(name="meu-historico", description="Consulta seu histórico pessoal de treinamentos.")
    async def meu_historico(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=await self._montar_historico(interaction, interaction.user), ephemeral=True)

    @app_commands.command(name="historico", description="Consulta o histórico de treinamentos de um membro.")
    @app_commands.describe(membro="Membro cujo histórico será consultado")
    @lideranca_only()
    async def historico(self, interaction: discord.Interaction, membro: discord.Member):
        await interaction.response.send_message(embed=await self._montar_historico(interaction, membro), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Academia(bot))
