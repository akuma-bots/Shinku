# Sistema de Sugestões — NÊMESIS

## Canal e publicação
- Canal oficial: `1563995881508831336`.
- O Cog sincroniza um único painel oficial; se a publicação já existir, ela é editada em vez de duplicada.
- O canal configurado é um Fórum: o painel fica em uma publicação própria (fixada quando as permissões permitem) e cada sugestão vira uma publicação/tópico independente. O sistema também mantém compatibilidade com canal de texto.
- Qualquer membro da NÊMESIS pode enviar uma sugestão pelo botão persistente **Enviar sugestão**.
- O formulário recebe título, descrição, resultado esperado e categoria. Categorias desconhecidas são classificadas como **Outros**.
- Antes de publicar, o sistema procura títulos muito semelhantes para reduzir sugestões duplicadas e encaminha o membro à publicação existente.
- Há um intervalo de 10 minutos por membro entre envios; a verificação de duplicidade acontece antes de consumir esse intervalo.

## Votação e discussão
- Cada publicação tem botões persistentes de apoio, não apoio e comentário.
- Cada pessoa mantém somente um voto; pode trocar a opção ou clicar novamente para retirar o voto.
- O autor não pode votar na própria sugestão, e as ações são validadas contra a publicação original do Fórum.
- O autor pode editar título, descrição e resultado esperado enquanto a sugestão estiver pendente ou em análise.
- O botão **Acompanhar** permite receber atualizações por DM quando a liderança mudar o status.
- No Fórum, a própria publicação da sugestão é o espaço de comentários; em canal de texto, o botão cria uma thread vinculada.
- Sugestões rejeitadas ou implementadas encerram a votação.

## Gestão
- O botão **Painel da liderança** abre uma consulta privada, protegida por `membro_tem_lideranca()`.
- A liderança pode filtrar atividade recente, mais apoiadas, pendentes, em análise, aprovadas, em desenvolvimento, rejeitadas e implementadas.
- O painel calcula total de votos e taxa de aprovação das decisões.
- O botão **Gerenciar** em cada publicação permite alterar o status e registrar uma justificativa.
- Cada alteração de status mantém uma trilha de auditoria com situação anterior, nova situação, responsável, justificativa e data.
- O autor recebe uma mensagem privada quando a liderança registra uma decisão (se aceitar DMs).

## Persistência e auditoria
- Sugestões, votos, decisões, histórico de status, seguidores, cooldowns e IDs do painel são salvos por `utils.storage`, usando Upstash Redis quando configurado.
- Envios e decisões são enviados ao tópico **📋・Sugestões e Ideias** do Registro Global.
- Não são criados slash commands nem canais adicionais.
- A Central Administrativa contém um atalho para o canal oficial.

