import io
import aiohttp
from PIL import Image, ImageDraw, ImageFont

LARGURA, ALTURA = 900, 300
COR_FUNDO = (30, 30, 35)
COR_BARRA = (88, 101, 242)
COR_TEXTO = (255, 255, 255)
COR_TEXTO_SECUNDARIO = (185, 185, 195)


async def _baixar_avatar(url: str) -> Image.Image:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resposta:
            dados = await resposta.read()
    return Image.open(io.BytesIO(dados)).convert("RGBA")


def _fonte(tamanho: int):
    """Usa a fonte padrão do Pillow — funciona sempre, sem depender de
    nenhum arquivo .ttf no repositório (visual mais simples). Se quiser algo
    mais bonito depois, coloca um .ttf em config/ e troca aqui pra
    ImageFont.truetype('config/fonte.ttf', tamanho)."""
    try:
        return ImageFont.truetype("arial.ttf", tamanho)
    except Exception:
        return ImageFont.load_default()


async def gerar_card(nome: str, avatar_url: str, patente, xp: int, xp_proximo,
                      vitorias: int, derrotas: int, sequencia_atual: int, maior_sequencia: int,
                      kdr_valor: float, medalhas: int) -> io.BytesIO:
    base = Image.new("RGBA", (LARGURA, ALTURA), COR_FUNDO)
    desenho = ImageDraw.Draw(base)

    avatar = await _baixar_avatar(avatar_url)
    avatar = avatar.resize((180, 180))
    mascara = Image.new("L", (180, 180), 0)
    ImageDraw.Draw(mascara).ellipse((0, 0, 180, 180), fill=255)
    base.paste(avatar, (40, 60), mascara)

    fonte_nome = _fonte(36)
    fonte_label = _fonte(20)
    fonte_valor = _fonte(26)

    desenho.text((250, 40), nome, font=fonte_nome, fill=COR_TEXTO)
    desenho.text((250, 90), patente or "Sem patente", font=fonte_label, fill=COR_TEXTO_SECUNDARIO)

    barra_x, barra_y, barra_w, barra_h = 250, 140, 600, 24
    desenho.rounded_rectangle((barra_x, barra_y, barra_x + barra_w, barra_y + barra_h), radius=12, fill=(60, 60, 68))
    if xp_proximo:
        progresso = min(1.0, xp / xp_proximo) if xp_proximo > 0 else 0
        desenho.rounded_rectangle((barra_x, barra_y, barra_x + int(barra_w * progresso), barra_y + barra_h),
                                   radius=12, fill=COR_BARRA)
        texto_xp = f"{xp} / {xp_proximo} XP"
    else:
        desenho.rounded_rectangle((barra_x, barra_y, barra_x + barra_w, barra_y + barra_h), radius=12, fill=COR_BARRA)
        texto_xp = f"{xp} XP (patente máxima)"
    desenho.text((barra_x, barra_y + 30), texto_xp, font=fonte_label, fill=COR_TEXTO_SECUNDARIO)

    stats = [
        ("Vitórias", str(vitorias)),
        ("Derrotas", str(derrotas)),
        ("Sequência", f"{sequencia_atual} (recorde {maior_sequencia})"),
        ("KDR", str(kdr_valor)),
        ("Medalhas", str(medalhas)),
    ]
    x = 250
    for label, valor in stats:
        desenho.text((x, 210), label, font=fonte_label, fill=COR_TEXTO_SECUNDARIO)
        desenho.text((x, 235), valor, font=fonte_valor, fill=COR_TEXTO)
        x += 130

    buffer = io.BytesIO()
    base.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer