# Hierarquia e permissões da NÊMESIS

Este documento registra a matriz aplicada pelo Shinku. Os IDs são os cargos do servidor configurado e devem ser mantidos sincronizados com a estrutura oficial.

## Administração

Somente cargos acima de Supervisor Staff recebem acesso administrativo geral:

- OCTÓGONO — `1563995880007139425`
- Diretor Staff — `1563995880007139424`
- Vice-Diretor Staff — `1563995880007139423`

Supervisor Staff (`1563995880007139422`) não recebe, por esse cargo isolado, acesso administrativo geral.

## Gestão de missões

A gestão de missões é exclusiva do OCTÓGONO. A regra vale para a central administrativa, sincronização, temporadas, relatórios operacionais, inteligência e registro manual de atividades de missão. Nas revisões, decisões de missões, contribuições, operações especiais e PvE também exigem OCTÓGONO; revisões competitivas não relacionadas a missões continuam sob a liderança administrativa.

Não há permissões atribuídas a responsáveis de divisões enquanto esses responsáveis não forem designados.

## Cargos de progressão e IDs oficiais

| Rank | Cargo | ID |
|---:|---|---:|
| 12 | Lutador | `1563995879990624373` |
| 11 | Subtenente | `1563995879990624374` |
| 10 | Tenente | `1563995879990624375` |
| 9 | Executor | `1563995879990624376` |
| 8 | Especialista | `1563995879990624377` |
| 7 | Elite | `1563995879995874937` |
| 6 | Veterano | `1563995879998754938` |
| 5 | Treinador | `1563995879998754939` |
| 4 | Comandante | `1563995879998754940` |
| 3 | Vice Capitão | `1563995879998754941` |
| 2 | Capitão | `1563995879998754942` |
| 1 | Capitão Geral | `1563995879998754943` |

O Shinku preenche automaticamente os vínculos padrão sem sobrescrever configurações personalizadas. O OCTÓGONO pode alterar um vínculo pelo comando `/gangue-configurar-cargo`; cargos administrativos e o cargo-base NÊMESIS não podem ser usados como cargos de progressão.

## Ações hierárquicas

Os cargos acima de Elite podem promover, rebaixar e banir:

- Veterano — `1563995879998754938`
- Treinador — `1563995879998754939`
- Comandante — `1563995879998754940`
- Vice Capitão — `1563995879998754941`
- Capitão — `1563995879998754942`
- Capitão Geral — `1563995879998754943`

Elite (`1563995879998754937`) e cargos inferiores não recebem essas ações por progressão. A ação sobre outro membro exige que o cargo de autoridade do responsável esteja acima do maior cargo do alvo. O dono do servidor não pode ser banido; o bot continua sujeito às permissões e à hierarquia nativas do Discord.

## Auditoria e preservação

- Promoções e rebaixamentos de patentes são registrados no Registro Global.
- `/gangue-promover` e `/gangue-rebaixar` ajustam o XP até o limiar do rank escolhido e aplicam o cargo configurado; exigem justificativa e ficam no histórico.
- `/gangue-configurar-cargo` vincula cada rank a um cargo do Discord e é exclusivo do OCTÓGONO.
- `/patente-promover` e `/patente-rebaixar` alteram as patentes do perfil competitivo, sem substituir a hierarquia principal.
- O comando `/banir` registra responsável, alvo e motivo; não apaga mensagens anteriores.
- Promoção, rebaixamento e banimento não podem atingir membro com cargo igual ou superior ao responsável.
- A hierarquia não é alterada automaticamente por esta configuração.
- Alterações de cargos no Discord continuam sujeitas à hierarquia e às permissões do próprio bot.
- XP é a métrica competitiva vigente; os campos antigos de pontos são mantidos apenas para compatibilidade com dados históricos e não alimentam mais o ranking.
