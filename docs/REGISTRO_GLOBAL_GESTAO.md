# Registro Global de Gestão — NÊMESIS

O Fórum `1566579335966498926` mantém 29 tópicos permanentes da geração **V2**. Todos têm o prefixo `🆕 NÊMESIS V2` e numeração `01` a `29`, tornando-os fáceis de distinguir dos antigos. O Shinku cria tópicos V2 novos, salva seus IDs e aposenta os tópicos antigos/duplicados arquivando-os e bloqueando-os, sem apagar mensagens históricas. Cada ocorrência é uma mensagem dentro do tópico correspondente; não se cria um tópico por evento.

## Áreas de registro

| Área | O que deve reunir |
|---|---|
| Mensagens | Edições, exclusões e alterações de anexos |
| Atendimento | Tickets, atribuições, encerramentos, avaliações |
| Moderação | Advertências, timeouts, expulsões, banimentos |
| Membros | Histórico geral e alterações de dados |
| Histórico de Entradas | Entradas, saídas, reentradas e integração inicial |
| Histórico dos Membros | Linha do tempo por membro e ocorrências associadas |
| Histórico de Cargos | Concessão, remoção e sincronização de cargos |
| Convites | Criação, remoção, uso e atribuição de convites |
| Atividade em Voz | Entradas, saídas e mudanças de sala |
| Atividade dos Membros | Participação e métricas efetivamente coletadas |
| Progressão | XP, níveis, patentes, promoções e rebaixamentos |
| Conquistas | Desbloqueios, recordes e recompensas |
| Missões | Criação, atribuição, conclusão, validação e recompensas |
| Competições | Desafios, lutas, guerras, placares e resultados |
| Eventos | Agenda, inscrições, atividades e resultados |
| Sorteios | Criação, participação, vencedores e entrega de prêmios |
| Sugestões e Votações | Sugestões, votos, decisões e resultados |
| Formulários | Inscrições, candidaturas, aprovações e revisões |
| Relatórios | Envio, revisão, aprovação e encaminhamentos |
| Parcerias | Solicitações, aprovações e alterações |
| Roblox | Vínculos, sincronizações e falhas da integração |
| Integrações | APIs externas, dashboard e sincronizações |
| AutoMod | Detecções, bloqueios, filtros e revisões |
| Segurança | Anti-Raid, convites suspeitos e incidentes |
| Infraestrutura | Conexões, Upstash, health checks e tarefas |
| Configurações | Parâmetros e ajustes operacionais |
| Administração | Permissões, estrutura e decisões administrativas |
| Sistemas | Compatibilidade para registros legados ainda não migrados |

## Identificação e organização V2

- O prefixo `🆕 NÊMESIS V2` identifica exclusivamente a estrutura atual.
- O número de dois dígitos indica a ordem fixa do tópico e facilita a localização no celular.
- Tópicos sem o prefixo V2 são legados; após a sincronização ficam arquivados e bloqueados, preservando o histórico.
- Não excluir tópicos antigos automaticamente: mensagens e evidências históricas permanecem consultáveis.

## Regras de integridade

- As categorias antigas permanecem válidas para compatibilidade com os cogs existentes.
- Novas categorias não apagam nem reclassificam dados históricos já armazenados.
- O registro deve incluir, quando disponível, autor da ação, membro afetado, horário, IDs do objeto e detalhes antes/depois.
- Não mencionar usuários em massa nem permitir menções automáticas: `AllowedMentions.none()`.
- Se o Discord não identificar com segurança o autor de um evento, o registro deve dizer isso explicitamente em vez de atribuir culpa por inferência.
- Acesso ao Fórum deve continuar restrito e validado; nenhuma mudança de hierarquia é implícita nesta expansão.
- A criação e publicação de tópicos ocorre apenas quando o bot inicializa ou quando um registro precisa ser gravado. O código não confirma que o Fórum ativo já recebeu as mudanças até o deploy e a validação no Discord.

## Limites de cobertura

Um tópico existir não significa que todos os sistemas já enviam eventos para ele. Cada listener/fluxo precisa ser conectado e testado individualmente. A auditoria deve distinguir eventos disponíveis pela API do Discord, eventos produzidos pelos próprios cogs e eventos que não podem ser observados sem integração adicional.
