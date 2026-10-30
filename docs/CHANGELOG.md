# Notas de atualização — NÊMESIS / Shinku

Este arquivo registra mudanças por estado de entrega. Merge no GitHub não significa, por si só, que o recurso já esteja ativo no Discord; a ativação depende do deploy e da inicialização correta do bot.

## 2026-10-30 — Central de tickets

### Entregue no código (PRs #49 e #50)
- Reformulação da central de atendimento com identidade visual Carmesim.
- Painel com catálogo de categorias, descrições, fluxo de atendimento, etapas e informações de privacidade.
- Suporte a banner e miniatura por URL HTTPS.
- Novos comandos administrativos:
  - `/ticket-painel-configurar`
  - `/ticket-categoria-visual`
- Novas ações no ticket: adicionar participante e solicitar equipe.
- Preservação das ações de assumir e fechar atendimento, registros, histórico e avaliação.
- Renovação dos nomes e descrições das oito categorias, preservando as chaves internas para compatibilidade.

### Emblemas personalizados (PRs #53 e #54)
- Integração dos oito emojis personalizados ao menu de categorias e ao catálogo visual.
- O bot localiza os emblemas pelo nome cadastrado no servidor, sem exigir IDs informados manualmente.
- Nomes atuais reconhecidos: `emoji_1` a `emoji_8`.
- Compatibilidade mantida com os nomes anteriores `TicketEmoji1` a `TicketEmoji8`.
- Emoji Unicode alternativo utilizado quando um emblema personalizado não está disponível.

### Categorias atuais planejadas
1. Recrutamento e Admissão
2. Estrutura e Hierarquia
3. Integridade e Conduta
4. Operações Competitivas
5. Assistência Técnica
6. Relações Institucionais
7. Gestão de Eventos
8. Premiações e Reconhecimentos

## Sistema de missões e provas

### Em desenvolvimento — PR #55
- Reforma visual dos cartões de catálogo e da central de validação.
- Recompensas de missões apresentadas exclusivamente em XP; P.C. não deve ser exibido como recompensa de missão.
- Cartões de validação com protocolo, participante, categoria, referência, horário e diretrizes de análise.
- Preservação do fluxo de aprovação manual, auditoria, prevenção de duplicidade e divisão de XP entre responsável e auxiliar.

**Estado:** a PR #55 ainda deve ser confirmada como mesclada e implantada antes de anunciar essas mudanças como disponíveis no servidor.

## Observações de implantação
- Alterações mescladas precisam de deploy bem-sucedido no Render.
- Após o deploy, validar os logs de inicialização e os painéis no Discord.
- Não publicar como ativo nenhum recurso marcado como em desenvolvimento ou sem confirmação de deploy.
