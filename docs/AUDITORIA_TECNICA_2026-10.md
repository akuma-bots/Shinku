# Auditoria técnica do Shinku — NÊMESIS

**Atualização:** 03/11/2026
**Base:** branch `main` do repositório `akuma-bots/Shinku`
**Escopo:** autorização, hierarquia, estabilidade, armazenamento, notificações, observabilidade, documentação e testes.

> Esta é uma revisão estática complementada por execução local automatizada dos testes. Ela não comprova permissões efetivas no Discord, conteúdo real do Upstash, funcionamento do Render nem publicação dos painéis no servidor.

## Resultado executivo

O Shinku já possui módulos dedicados para moderação, AutoMod/anti-raid, tickets, parcerias, formulários, missões, temporadas, perfil, ranking, conquistas, sorteios, logs e revisões. A prioridade desta rodada foi corrigir divergências de autorização, tornar o envio de comunicados mais resistente a concorrência e melhorar a visibilidade operacional, sem duplicar sistemas existentes.

## Alterações realizadas nesta rodada

### P0 — Autorização e hierarquia

- Supervisor Staff foi incluído na autorização administrativa geral, junto de OCTÓGONO, Diretor Staff e Vice-Diretor Staff.
- A permissão geral foi separada dos poderes hierárquicos de promoção, rebaixamento e banimento. Supervisor Staff não herda essas ações apenas por possuir acesso administrativo.
- Os comandos gerais de limpeza de mensagens e consulta de avisos/histórico de punições passaram a usar a autorização administrativa central; o banimento permanece sujeito à autorização hierárquica específica e à posição do alvo.
- A gestão de missões permanece exclusiva do OCTÓGONO.
- A autorização central continua restrita ao servidor oficial e não usa permissões genéricas do Discord como substituto da hierarquia organizacional.
- O teste de hierarquia foi atualizado para validar o acesso geral do Supervisor Staff e negar poderes de promoção/banimento e gestão de missões.
- A documentação oficial de hierarquia foi atualizada.

### P1 — Persistência e notificações

- O armazenamento já oferece `atualizar_json` com compare-and-set via Lua no Upstash e atualização protegida por lock no modo local. O histórico e a remoção de punições também foram migrados para essa operação atômica, evitando que processos diferentes sobrescrevam registros concorrentes.
- O fluxo de notas automáticas passou a usar `atualizar_json` para reservar destinatários e registrar resultados, evitando sobrescrever o documento inteiro com snapshots antigos.
- A reserva ocorre antes da chamada ao Discord; duas instâncias não devem enviar a mesma release ao mesmo destinatário.
- Resultados de transporte incertos permanecem marcados e não são reenviados automaticamente, evitando duplicações quando o Discord pode ter aceitado a DM.
- Foi removida uma constante de concorrência antiga que não era usada. O envio permanece sequencial e com intervalo configurado.
- Foram adicionados testes de reserva única, classificação do resultado e bloqueio de reenvio em resultado incerto.

### P2 — Observabilidade e painel operacional

- O comando existente `/sistema status` foi aprimorado para informar loops e tarefas assíncronas encontrados nos cogs, separando tarefas em execução de tarefas paradas/com falha.
- `/sistema diagnostico` continua verificando a conectividade com o armazenamento sem expor URL ou token.
- Não foi criado um segundo painel administrativo concorrente: os comandos de sistema, formulários, missões, tickets, revisões e parcerias existentes continuam sendo os pontos oficiais de operação.

### P2 — Documentação e avisos

- README e tutorial foram corrigidos para não anunciar `/avisos-enviar`, que não existe no código atual.
- `/notas-atualizacao` foi documentado como prévia somente leitura; a entrega de releases é automática e respeita as preferências individuais.
- A versão Python configurada no runtime, `.python-version` e workflows é 3.11.9; a divergência descrita em auditorias anteriores não se aplica à configuração atual.

## Sistemas existentes revisados

| Área | Situação observada |
|---|---|
| Segurança e hierarquia | Política central; testes de cargos e limites hierárquicos |
| Painel administrativo | `/sistema status` e `/sistema diagnostico`; painel de missões e central de formulários já existem |
| Atividade e desempenho | Perfil, progressão, ranking, conquistas, missões e relatórios já existem |
| Auditoria e registros | Registro Global, logs, revisões e históricos específicos já existem |
| Estabilidade e implantação | Health check HTTP, carregamento de cogs, workflows de validação e auditoria de dependências já existem |

## Riscos ainda pendentes

1. **IDs de canais e cargos:** há IDs padrão/legados distribuídos em módulos. Não foram substituídos porque a configuração efetiva do Discord e do Upstash precisa ser consultada no ambiente real antes de qualquer migração.
2. **Concorrência fora dos fluxos modernizados:** alguns módulos ainda podem usar leitura seguida de `salvar`; é necessário migrar cada documento de forma específica, com testes e compatibilidade dos dados.
3. **Sessão HTTP do Upstash:** `utils/storage.py` ainda cria uma `aiohttp.ClientSession` por comando. A reutilização exige ciclo de vida de inicialização e encerramento bem definido e deve ser tratada separadamente.
4. **Verificação operacional:** permissões reais, envio de DMs, tarefas no Discord, health check do Render e dados do Upstash não podem ser confirmados apenas pelo código.
5. **Segurança estática:** o workflow de segurança audita dependências; análise estática de código e varredura adicional de segredos ainda podem ser incorporadas em uma rodada própria.

## Validação executada

- `python -m compileall -q bot.py cogs utils tests` — aprovado.
- `PYTHONPATH=. python -m pytest -q` — **318 testes aprovados e 67 subtestes aprovados**.
- Os testes foram executados em ambiente isolado com o código clonado do GitHub; não equivalem a teste funcional no Discord ou a deploy no Render.

## Critérios para encerrar a implantação

1. Confirmar o workflow de CI no commit final.
2. Confirmar deploy do Render e resposta saudável em `/health`.
3. Reiniciar o bot e verificar carregamento de todos os cogs e sincronização dos comandos.
4. Testar com contas de Supervisor Staff, direção, OCTÓGONO, membro comum e cargos competitivos.
5. Verificar os painéis e permissões no Discord e confirmar conexão persistente com Upstash.
6. Preservar backup e plano de rollback antes de qualquer migração de dados.
