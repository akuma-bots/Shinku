import random

TEMPLATES_PADRAO = [
    {"tipo": "pvp", "titulo": "Duelo Relâmpago", "descricao": "Vença 1 duelo PvP hoje.", "recompensa_xp": 15},
    {"tipo": "pvp", "titulo": "Sequência de Vitórias", "descricao": "Vença 2 duelos PvP hoje.", "recompensa_xp": 30},
    {"tipo": "pve", "titulo": "Caçador Iniciante", "descricao": "Derrote 1 inimigo no PvE.", "recompensa_xp": 15},
    {"tipo": "pve", "titulo": "Exterminador", "descricao": "Derrote 2 inimigos no PvE.", "recompensa_xp": 30},
    {"tipo": "pve", "titulo": "Caça ao Chefe", "descricao": "Derrote um inimigo difícil no PvE.", "recompensa_xp": 50},
]


def sortear(quantidade: int) -> list:
    """Sorteia `quantidade` templates sem repetir, a menos que peçam mais
    missões do que existem templates disponíveis."""
    pool = list(TEMPLATES_PADRAO)
    random.shuffle(pool)
    if quantidade <= len(pool):
        return pool[:quantidade]
    return [random.choice(TEMPLATES_PADRAO) for _ in range(quantidade)]