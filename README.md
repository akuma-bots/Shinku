# Bot de Comunidade (Python) — Ticket + Moderação Automática (Multi-servidor)

Bot estilo **Carl-bot / Lorrita** feito em Python com `discord.py`. Funciona em
**quantos servidores você quiser** — cada servidor configura seu próprio cargo
de suporte, canal de logs e categoria de tickets com o comando `/configurar`.

1. Roda um sistema de **tickets** com painel de botão, mensagem de boas-vindas
   ("Olá bem vindo, Como posso ajudar?") e **resolução automática** por
   palavras-chave — só chama a equipe de suporte quando não reconhece o assunto
   ou o cliente pede.
1b. **Fecha o ticket automaticamente**: quando o cliente ou o atendente escreve
   algo como "fechar o ticket" (em qualquer mensagem do canal), ou quando o
   ticket fica **10 minutos sem nenhuma mensagem**.
2. **Lê as regras** de `config/rules.json` (compartilhadas por todos os servidores)
   e escaneia todas as mensagens.
3. Ao detectar quebra de regra, **avisa o membro** (por DM, citando a regra exata),
   registra o aviso *daquele servidor* e, ao atingir o limite configurado, aplica
   automaticamente a punição (**mute → kick → ban**, dependendo da regra).
4. Tem comandos manuais de moderação (`/ban`, `/kick`, `/mute`, `/warn`, `/clear`, `/regras`, `/avisos`).
5. **`/configurar`** — cada servidor define seu próprio cargo de suporte, canal de logs
   e categoria de tickets, sem precisar mexer no código ou no `.env`.

## 1. Criar o bot no Discord

1. https://discord.com/developers/applications → New Application.
2. **Bot** → Reset Token → copie o token (não compartilhe com ninguém).
3. Em **Bot**, ative os intents: `MESSAGE CONTENT INTENT`, `SERVER MEMBERS INTENT`.
4. Em **OAuth2 > URL Generator**, marque `bot` + `applications.commands`. Permissões necessárias:
   `Ban Members`, `Kick Members`, `Moderate Members` (timeout), `Manage Channels`,
   `Manage Messages`, `Send Messages`, `Read Message History`, `View Channels`.
5. Use o link gerado para convidar o bot — **esse mesmo link funciona para convidar
   o bot em quantos servidores você quiser.**

## 2. Instalar

```bash
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Preencha o `.env`:
- `DISCORD_TOKEN`: token do bot (obrigatório).
- `GUILD_ID`: (opcional) ID de um servidor seu para sincronizar comandos
  instantaneamente ali durante testes — os outros servidores recebem os
  comandos via sincronização global (pode levar até 1h na primeira vez).

Os campos `TICKET_CATEGORY_ID`, `SUPPORT_ROLE_ID` e `LOG_CHANNEL_ID` **não são
mais necessários no `.env`** — agora cada servidor configura isso pelo comando
`/configurar` direto no Discord.

## 3. Rodar

```bash
python bot.py
```

## 4. Configurar em cada servidor

Depois de convidar o bot para um servidor, um administrador roda:

```
/configurar cargo_suporte:@Suporte canal_logs:#logs-mod categoria_tickets:Tickets
```

Pode rodar `/configurar` sem nenhum parâmetro para ver a configuração atual daquele
servidor. Cada parâmetro é opcional — só o que for informado é atualizado.

## 5. Comandos disponíveis

| Comando | O que faz |
|---|---|
| `/configurar` | Define cargo de suporte, canal de logs e categoria de tickets **deste servidor** |
| `/ticket-painel` | Publica o painel com o botão "Abrir Ticket" |
| `/ban` `/kick` `/mute` `/unmute` `/warn` | Moderação manual |
| `/clear` | Apaga mensagens em massa |
| `/regras` | Mostra as regras do servidor (lidas de `config/rules.json`) |
| `/avisos` | Mostra quantos avisos automáticos um membro já recebeu neste servidor, por regra |

## 6. Personalizar as regras (moderação automática)

Edite `config/rules.json`. Essas regras são **as mesmas em todos os servidores**
onde o bot está (é um único arquivo compartilhado). Tipos de detecção disponíveis:

- `"palavras"`: lista de palavras/expressões proibidas.
- `"regex"`: padrões de regex (ex: links de convite do Discord).
- `"mencao_massa"`: dispara quando o membro marca muitas pessoas/cargos ou usa @everyone.
- `"spam_flood"`: dispara quando o membro manda muitas mensagens em pouco tempo.

Cada regra define:
- `"limite_avisos_para_punicao"`: quantos avisos até a punição automática.
- `"punicao_final"`: `"mute"`, `"kick"` ou `"ban"`.

Os avisos ficam salvos em `data/avisos.json`, **separados por servidor**, e zeram
depois que a punição é aplicada.

## 7. Personalizar as respostas automáticas de ticket

Edite `config/knowledge_base.json` (também compartilhado por todos os servidores).
Cada entrada tem `palavras_chave`, `resposta` e `escalar_sempre`. Isso é
correspondência de palavras-chave simples — não é IA generativa.

## 8. Hospedagem 24/7

Suba o código para o GitHub (sem o `.env`) e faça o deploy em um serviço como
Railway ou Discloud, configurando `DISCORD_TOKEN` direto na plataforma.

## 9. Novidades: mais detecção, logs e anti-raid

- **Mais tipos de detecção automática** em `config/rules.json`: `caps_spam` (grito em maiúsculas),
  `emoji_spam` (flood de emoji), `zalgo` (texto corrompido com unicode empilhado), além dos já
  existentes (`palavras`, `regex`, `mencao_massa`, `spam_flood`). Cada regra pode ter
  `"canais_liberados": [ids]` para não se aplicar em canais específicos (ex: canal de divulgação livre).
- **`cogs/logs.py`** — registra no canal de logs: entrada/saída de membro, mensagens editadas e apagadas.
- **`cogs/antiraid.py`** — detecta picos de entrada de membros (possível raid), avisa a equipe de
  suporte e expulsa automaticamente contas muito novas enquanto o pico durar.

## 10. Comandos de gerência: onde cada regra vale

Com `/liberar-canal`, um admin (permissão "Gerenciar Servidor") escolhe uma
regra (ex: "Regra 9 — Links externos sem permissão" ou "Regra 3 — Respeito
entre membros") e um canal — a partir daí, o automod ignora aquela regra
**só naquele canal, só neste servidor** (ex: liberar links num canal de
divulgação, ou liberar linguagem mais solta numa sala livre).

- `/liberar-canal regra:<escolha> canal:#canal` — libera
- `/bloquear-canal regra:<escolha> canal:#canal` — volta a aplicar a regra
- `/canais-liberados` — lista tudo que está liberado neste servidor

## 11. Cargo automático por canal

Configure um canal "administrado" pelo bot: quem postar ali — mensagem de
texto, print, comprovante, o que for — recebe automaticamente o cargo
escolhido. Bom pra verificação, aceite de regras, comprovação de compra etc.
O bot reage com ✅ na mensagem quando dá certo.

- `/definir-canal-cargo canal:#canal cargo:@Cargo` — ativa nesse canal
- `/remover-canal-cargo canal:#canal` — desativa
- `/canais-cargo-automatico` — lista tudo que está ativo neste servidor

**Importante:** o cargo do bot precisa estar **acima** do cargo que ele vai
dar, na lista de cargos do servidor (Configurações → Cargos), senão o
Discord não deixa o bot atribuir. Se isso acontecer, o bot avisa no canal
de logs.

## 12. Logs, contadores, eventos, parcerias, embeds e customização

**Logs (expandido)** — além de entrada/saída de membro e mensagens
editadas/apagadas, agora também registra: banimento/desbanimento,
mudança de apelido, cargo adicionado/removido, canal criado/apagado,
e entrada/saída/troca de canal de voz. Tudo no mesmo canal de logs
configurado por `/configurar`.

**Contadores** — canais de voz travados (ninguém entra) que mostram uma
contagem ao vivo no próprio nome, atualizada a cada 10 minutos (limite do
Discord pra renomear canal):
- `/criar-contador tipo:<membros|online|bots|boosts|cargo> [cargo]`
- `/remover-contador canal:#canal`
- `/contadores` — lista os ativos

**Eventos** — anuncia automaticamente eventos agendados do Discord
(criação, início e cancelamento) no canal escolhido:
- `/configurar-canal-eventos canal:#canal`

**Parcerias** — registra parcerias com outros servidores e publica o
anúncio automaticamente:
- `/configurar-canal-parcerias canal:#canal`
- `/adicionar-parceria nome: convite: descricao: [banner]`
- `/remover-parceria nome:`
- `/parcerias` — lista as parcerias registradas

**Embeds customizadas** — abre um formulário (título, descrição, cor em
hex, imagem, rodapé), sem precisar escrever JSON nem código:
- `/criar-embed [canal]`
- `/editar-embed canal: id_mensagem:` — edita uma embed que o próprio bot enviou

**Customização de status** — muda o "jogando"/"assistindo"/"ouvindo" do
bot. Como isso é global (vale em todos os servidores ao mesmo tempo), só
funciona pra quem é dono da aplicação do bot no Developer Portal:
- `/definir-status tipo: texto:`

## ⚠️ Nova intent privilegiada necessária

O contador de "membros online" (`/criar-contador tipo:online`) precisa da
**Presence Intent**, além das já usadas (Message Content e Server Members
Intent). Vá em Discord Developer Portal → sua aplicação → Bot → ative
**Presence Intent** também, senão o bot não vai conseguir ver quem está
online.

## 13. Chat do bot e resolução de tickets — IA de verdade (Groq de graça, sem verificação)

**Isso mudou:** tanto o chat sobre Gakuran quanto a resolução automática de
tickets deixaram de usar busca por palavra-chave. Agora os dois chamam uma
API de IA pra realmente entender o que a pessoa está perguntando/dizendo.

**Por padrão, o bot usa o Groq — que é de graça e o cadastro é só com
email ou conta Google, sem pedir verificação de idade nem cartão**
(~14.400 mensagens por dia, de sobra pra um servidor comum). Gere sua
chave grátis em https://console.groq.com/keys e coloque no `.env`:
```
GROQ_API_KEY=sua_chave_aqui
IA_PROVEDOR=groq
```

Também dá pra usar o Google Gemini (`IA_PROVEDOR=gemini` +
`GEMINI_API_KEY`) — mas ele pede verificação de idade em algumas contas
Google, então deixei o Groq como padrão. Se preferir pagar pelo Claude
(mais qualidade), troque pra `IA_PROVEDOR=anthropic` e preencha
`ANTHROPIC_API_KEY`.

Sem nenhuma chave configurada pro provedor escolhido, tanto o chat quanto a
resolução de ticket avisam o erro e (no caso do ticket) escalam direto pra
um humano, pra não deixar o cliente sem resposta.

**Chat sobre Gakuran** — `/configurar-chat cargo: [canal]` e
`/desativar-chat`, igual antes. A IA recebe todo o conteúdo de
`config/gakuran_knowledge.json` como contexto e responde com entendimento
de linguagem natural, não por bater frase.

**Resolução de tickets** — a IA recebe o conteúdo de
`config/knowledge_base.json` como contexto de suporte. Se a dúvida do
cliente estiver coberta, ela responde ajudando. Se não estiver, ou for um
assunto sensível (marcado como `"escalar_sempre": true` no JSON), ela
escala pra um atendente humano sozinha — sem precisar da pessoa digitar
"falar com atendente".

## 14. Por que os comandos "sumiam" a cada atualização — e a correção

**A causa real:** toda vez que o bot reiniciava, ele reenviava a lista
inteira de comandos pro Discord. Se isso acontece com frequência (a
Discloud reinicia sozinha às vezes), o Discord começa a **limitar** essas
atualizações — e é aí que comandos somem ou param de atualizar. Além
disso, a pasta `data/` (onde ficam salvas as configurações de cada
servidor: `/configurar`, `/liberar-canal`, contadores etc.) estava sendo
enviada vazia dentro do zip a cada atualização, o que também podia
**apagar tudo que já estava configurado** na hospedagem.

**O que mudou:**
1. O bot agora guarda uma "assinatura" do conjunto de comandos em
   `data/comandos_sincronizados.json`. Se reiniciar e os comandos forem
   exatamente os mesmos, ele **pula** a sincronização global — evita bater
   no limite de taxa do Discord.
2. Além da sincronização global (que pode levar até 1h pra propagar), o
   bot agora sincroniza **instantaneamente em todo servidor onde ele já
   está**, automaticamente, sem precisar de nenhum ID fixo no `.env`.
3. A pasta `data/` **não vem mais dentro do zip** (ela se cria sozinha na
   primeira vez que o bot roda) e agora está no `.discloudignore`, pra um
   novo upload nunca apagar o que já está salvo na hospedagem.

**Resumindo pra você:** a partir de agora, suba o zip novo normalmente —
os comandos aparecem na hora em todos os servidores onde o bot já está, e
as configurações de cada servidor não se perdem mais.

## 15. Chat com pesquisa na web — qualquer assunto, respostas mais completas

O chat (`@bot sua pergunta`) deixou de ser só sobre Gakuran — agora
responde **qualquer pergunta**, sobre qualquer assunto, e continua
pesquisando na web antes de responder (via Tavily) pra trazer informação
atual. O conhecimento curado sobre Gakuran continua ali como um extra —
o bot usa quando a pergunta é sobre esse jogo especificamente, mas não
fica mais travado nisso.

Também aumentei o limite de tamanho da resposta da IA (de 600 pra 2.000
tokens) — respostas mais longas e completas quando o assunto exige,
divididas automaticamente em várias mensagens do Discord se passar de
2000 caracteres.

Gere sua chave grátis do Tavily em https://tavily.com e coloque no `.env`:
```
TAVILY_API_KEY=sua_chave_aqui
```

## 16. Painel web — gerencia tudo pelo site (login com Discord)

Agora existe um site separado (entregue como `web-dashboard.zip`) onde dá
pra logar com Discord e configurar tudo pelo navegador, sem precisar de
comando nenhum: cargo de suporte, canal de logs, categoria de tickets,
chat com IA, exceções de automod, cargo automático, contadores, parcerias
e envio de embeds.

**Isso muda o armazenamento do bot:** pra bot e site conseguirem enxergar
a mesma configuração, o bot agora guarda tudo no **Upstash Redis** (banco
gratuito, sem cartão) em vez de só arquivo local. Sem configurar isso, o
bot continua funcionando 100% normal por comando — só o painel web que
fica indisponível, porque ele não teria como ver o que está salvo.

Pra ativar os dois juntos, veja o `README.md` **dentro do zip do
`web-dashboard`** — tem o passo a passo completo (Upstash, credenciais
OAuth2 do Discord, deploy na Netlify). Resumo do que entra no `.env` do
bot:
```
UPSTASH_REDIS_REST_URL=...
UPSTASH_REDIS_REST_TOKEN=...
```

## 17. Guerras, Perfil, Patentes e Rankings

**Sobre o pedido de "guardar mensagens de todo servidor pro dono ver":**
decidi não implementar isso. Seria um sistema de espionagem — mensagens de
pessoas em servidores (que podem nem ser seus) guardadas num banco pra uma
única pessoa ler sem quem escreveu saber, o que fere a expectativa de
privacidade das pessoas nesses servidores e as políticas de dados do
Discord pra bots. O que já existe (`cogs/logs.py`) é a alternativa correta:
um log **visível pra equipe do próprio servidor**, não escondido.

**O que foi implementado:**

**Guerras** (`cogs/guerras.py`):
- `/guerra-agendar gangue_a: gangue_b: quando:` — anuncia no canal de eventos
- `/guerra-registrar gangue_a: gangue_b: placar_a: placar_b: [mvp] [participantes_a] [participantes_b]`
  — registra o resultado. Os participantes são mencionados (@) no próprio
  comando; o bot atualiza o perfil de cada um automaticamente (XP,
  vitórias/derrotas, sequência, medalhas, promoção de patente)
- `/guerra-historico [gangue]` — últimas guerras
- `/temporada-nova` — encerra a temporada atual e começa outra (nada é
  apagado, só passa a contar separado)
- `/ranking-temporada [temporada]` — ranking de vitórias daquela temporada

**Perfil e Patentes** (`cogs/perfil.py`):
- `/perfil [membro]` — patente, XP, vitórias, derrotas, MVPs, sequência,
  KDR (se tiver PvP registrado) e medalhas
- `/patente-configurar nome: xp_minimo: [cargo_recompensa]` — cria uma
  patente; ao bater o XP mínimo numa guerra, o jogador é promovido
  **automaticamente** e recebe o cargo (se configurado)
- `/patente-promover membro: patente:` — promoção manual, ignora o XP
- `/patente-listar` / `/patente-remover`
- `/ranking-jogadores metrica:<vitorias|mvps|maior_sequencia|xp>`

**Medalhas automáticas:** Primeira Vitória, Veterano (10 vitórias), Lenda
(50 vitórias), MVP Frequente (5 MVPs), Sequência de 5 e de 10.

**XP por guerra:** vitória = 30, derrota = 10, bônus de MVP = +20.

**KDR/PvP:** não faz parte do fluxo de guerra em si (que é por gangue).
Se quiser registrar duelos 1x1, isso está pronto na camada de dados
(`utils/perfis.py: registrar_pvp`), mas ainda não tem comando de barra —
me avisa se quiser que eu adicione `/pvp-registrar`.

## Lista original — status final

Guerras ✅, Perfil ✅, Patentes ✅, Rankings ✅, Eventos ✅ (campeonatos +
sorteios), Denúncias + Painel de punições ✅, Integração com Roblox ✅.
Único item que não foi implementado, por decisão minha: o sistema de
guardar mensagens de todo servidor pra você ler depois (motivo explicado
acima, no início desta seção).

## 18. Denúncias, Painel de Punições, Eventos/Sorteios e Roblox

**Denúncias** (`cogs/denuncias.py`):
- `/configurar-canal-denuncias canal:` — onde as denúncias chegam
- `/denunciar membro: motivo:` — qualquer pessoa pode usar, é privado (só
  quem denuncia vê a confirmação)
- `/denuncias-listar [status]` — fila pra equipe revisar
- `/denuncia-resolver id: acao:` — marca como resolvida e já entra no
  histórico de punições daquele membro

**Painel de Punições** (`/punicoes-historico` em `cogs/moderacao.py`):
todo ban/kick/mute/warn manual **e** toda punição automática do automod
agora ficam registradas num histórico único, por membro. `/punicoes-historico
[membro]` mostra tudo — quem aplicou (ou "automod" se foi automático),
tipo e motivo.

**Campeonatos e Sorteios**:
- `/campeonato-agendar nome: data_hora:"DD/MM/AAAA HH:MM" descricao: [canal_voz]`
  — cria um Evento Agendado **de verdade** do Discord (RSVP e lembrete
  nativo do próprio Discord). Horário sempre em Brasília.
- `/sorteio-criar premio: duracao_minutos: [vencedores] [canal]` — posta
  com botão "🎉 Participar"; quando o tempo acaba, o bot sorteia sozinho
  (checa a cada 1 minuto)
- `/sorteio-encerrar id:` — encerra na hora
- `/sorteio-listar` — sorteios em andamento

**Integração com Roblox** (`cogs/roblox.py`) — verificação por código no
perfil, igual bots como o RoVer:
1. `/roblox-vincular usuario_roblox:` — o bot gera um código
2. Cola o código na descrição ("Sobre mim") do perfil Roblox
3. `/roblox-confirmar` — o bot confere e vincula
- `/roblox-perfil [membro]` — mostra usuário e grupos do Roblox vinculados
- `/roblox-desvincular`

Isso usa as APIs públicas do Roblox (não precisa de chave/token).

## 19. IA mais esperta: sabe a hora certa e segue princípios de comportamento

**O problema técnico que corrigi:** o modelo de IA (Groq/Gemini/Claude) não
tem relógio — ele só sabe o que aprendeu no treinamento, então sem ajuda
ele **não sabe que dia é hoje**. Agora, toda vez que alguém conversa com o
bot (chat ou ticket), o bot informa a data e hora reais (horário de
Brasília) pra IA, então perguntas sobre tempo, prazo ou data ficam
corretas em vez de chutadas.

**Novo arquivo `config/principios_ia.txt`** — baseado no texto que você
escreveu sobre o que uma IA nova precisa aprender. É carregado direto pela
IA do chat a cada conversa. Cobre:
- Nunca inventar informação; admitir quando não tem certeza
- Diferenciar fato de opinião; avisar quando algo pode estar desatualizado
- Entender que segundos/minutos/horas/dias e fusos horários importam
- Respeitar diferentes formas de escrever (gíria, erro de digitação,
  formal ou informal) sem julgar
- Adaptar o tamanho e o nível da resposta ao que foi perguntado

**Pra ampliar isso, não precisa mexer em código Python** — é só abrir
`config/principios_ia.txt` e editar/adicionar linhas de texto livre. O bot
recarrega esse arquivo toda vez que reinicia.

## 20. IA Adaptativa — aprende com interações, atualiza sozinha todo dia

**Design importante:** deixei a IA "aprender" de forma **supervisionada**,
não 100% automática. Motivo: se o bot aprendesse qualquer coisa que
qualquer pessoa dissesse no chat, sem filtro, alguém mal-intencionado
poderia ensinar informação falsa ou ofensiva de propósito, e o bot
repetiria isso depois pra todo mundo — inclusive pra quem nunca pediu
aquilo. Por isso separei em duas partes:

**Memória automática (não precisa fazer nada):** o bot guarda sozinho as
últimas ~30 perguntas/respostas de cada servidor e usa isso como contexto
nas próximas conversas — ele "lembra" do que já foi falado recentemente
ali, sem você precisar configurar nada.

**Fatos ensinados de propósito (`cogs/aprendizado.py`)** — só quem tem
permissão de Gerenciar Servidor pode ensinar algo permanente:
- `/ensinar fato:` — ensina algo que o bot vai lembrar sempre (ex: "o
  servidor tem uma parceria com tal grupo", "o dono se chama Fulano")
- `/fatos-ensinados` — lista tudo que já foi ensinado
- `/esquecer-fato numero:` — remove um fato específico

**Atualização diária de verdade (não é só um lembrete, é pesquisa real):**
o bot pesquisa na web sozinho, uma vez por dia (checa a cada 6h se já
atualizou hoje, pra não gastar pesquisa à toa), sobre um tema configurável
— padrão é "novidades do Gakuran". O resultado vira contexto extra em toda
conversa do dia.
- `/configurar-tema-diario tema:` — muda o assunto (ex: "notícias de
  tecnologia", "atualizações do jogo X")
- `/atualizar-agora` — força a pesquisa na hora, sem esperar

Tudo isso é injetado automaticamente no prompt do chat (`cogs/chat.py`),
junto com os princípios de comportamento e a hora certa que já existiam.

## 21. Cargo automático por rank do grupo Roblox da gangue

Agora o vínculo Roblox não é só decorativo — dá pra ligar cada **rank do
grupo Roblox da gangue** a um **cargo do Discord**, e o bot mantém isso
sincronizado sozinho (a cada 30 minutos, e também na hora em que alguém
vincula a conta pela primeira vez).

**Configuração (uma vez só):**
1. `/roblox-configurar-grupo grupo_id:` — o ID numérico do grupo Roblox da
   gangue (aparece na URL do grupo, ex: `roblox.com/groups/**123456**/nome`)
2. `/roblox-mapear-cargo rank_roblox:"Nome exato do rank" cargo_discord:@Cargo`
   — repete pra cada rank que você quiser sincronizar (ex: Membro, Oficial,
   Líder)
3. `/roblox-mapeamentos` — confere o que ficou configurado

**No dia a dia, é tudo automático:**
- Quem vincula a conta (`/roblox-confirmar`) já recebe o cargo certo na hora
- A cada 30 min, o bot rechecka todo mundo vinculado — quem foi promovido
  ou rebaixado **dentro do jogo** tem o cargo do Discord ajustado sozinho
- Quem sai do grupo Roblox perde o cargo de rank automaticamente
- `/roblox-sincronizar [membro]` força isso na hora, sem esperar o ciclo

Testei essa lógica isoladamente (promoção, rebaixamento, saída do grupo,
rank sem mapeamento configurado) — os 5 cenários passaram.

**Mesmo aviso de sempre sobre hierarquia:** o cargo do bot precisa estar
**acima**, na lista de cargos do servidor, de todos os cargos de rank que
ele vai atribuir — senão o Discord bloqueia por segurança (o comando
`/roblox-mapear-cargo` já avisa na hora se detectar isso).

## ⚠️ Atenção com punições automáticas

Esse bot bane/expulsa/silencia **sem intervenção humana** quando os limites são
atingidos, em **todos os servidores onde ele está**. Revise bem as palavras-chave
e os limites em `rules.json` antes de convidar o bot para outros servidores —
falsos positivos podem punir membros injustamente. Teste antes num servidor
de testes.

