TEMPLATES_PADRAO = [
    {"tipo": "pvp", "titulo": "Missão Fácil", "descricao": "Derrote 1 membro de uma gangue rival.", "recompensa_xp": 20},
    {"tipo": "pvp", "titulo": "Missão Média", "descricao": "Derrote um veterano de uma gangue rival.", "recompensa_xp": 40},
    {"tipo": "pvp", "titulo": "Missão Difícil", "descricao": "Derrote um líder de uma gangue rival.", "recompensa_xp": 70},
]


def sortear(quantidade: int) -> list:
    """Retorna as missões diárias fixas (fácil, média, difícil). Se um dia
    você adicionar mais opções em TEMPLATES_PADRAO, passa a sortear entre
    elas normalmente; por enquanto, com só 3 templates, sempre devolve as 3."""
    import random
    pool = list(TEMPLATES_PADRAO)
    random.shuffle(pool)
    if quantidade <= len(pool):
        return pool[:quantidade]
    return [random.choice(TEMPLATES_PADRAO) for _ in range(quantidade)]