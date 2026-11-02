# Registro Global — Fórum de Gestão da NÊMESIS

O Shinku publica registros operacionais no fórum **GESTÃO → Registros** (`1566579335966498926`) do servidor NÊMESIS (`1563995879981981817`). O fórum deve permanecer restrito aos cargos autorizados e ao próprio bot.

## Organização dos tópicos permanentes

Cada categoria possui um tópico fixo. O bot recupera o tópico salvo no Upstash e procura tópicos existentes (inclusive arquivados) antes de criar um novo. Assim, não abre um tópico por evento e evita duplicações.

| Chave | Tópico | Registros |
|---|---|---|
| mensagens | 📝 Mensagens | Edições e exclusões |
| atendimento | 🎫 Atendimento | Tickets e atendimentos |
| moderacao | 🛡️ Moderação | Advertências, timeouts, expulsões e banimentos |
| membros | 👥 Membros | Entradas, saídas e alterações de cargos |
| sistemas | ⚙️ Sistemas | Compatibilidade com registros antigos |
| administracao | 🏛️ Administração | Mudanças estruturais e decisões |
| seguranca | 🚨 Segurança | AutoMod, Anti-Raid, convites e incidentes |
| formularios | 📋 Formulários | Candidaturas, análises e decisões |
| progressao | 📈 Progressão | XP, níveis e patentes |
| missoes | 🎯 Missões | Criação, conclusão e recompensas |
| competicoes | ⚔️ Competições | Desafios, lutas, guerras e resultados |
| eventos | 🏆 Eventos | Agenda, inscrições e campeonatos |
| parcerias | 🤝 Parcerias | Solicitações e alterações |
| integracoes | 🔗 Integrações | Roblox, dashboard e APIs |
| infraestrutura | 🖥️ Infraestrutura | Storage, health checks e tarefas |
| configuracoes | ⚙️ Configurações | Parâmetros e ajustes operacionais |

## Regras de publicação

- O Shinku é exclusivo da NÊMESIS; o utilitário recusa outras guilds.
- Menções não são disparadas por registros automáticos.
- Falhas de publicação são registradas nos logs do processo e não devem derrubar o comando ou evento principal.
- Tópicos arquivados são reabertos quando necessário.
- As categorias antigas são mantidas para compatibilidade com registros existentes.
- O fórum deve negar visualização a @everyone e conceder acesso apenas aos cargos definidos pela política administrativa.

## Limites da validação

A alteração do código não publica mensagens retroativas nem modifica o fórum ativo imediatamente. O provisionamento dos novos tópicos ocorre quando o Shinku reinicia e consegue validar permissões e acesso ao fórum. A confirmação final exige deploy e teste no Discord.
