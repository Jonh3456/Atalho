# Atalho English Journey (PWA)

App instalável no celular (ícone na tela inicial, tela cheia, sem barra do
navegador) com botões de 1 toque para marcar tarefas de **outros apps**
(English Live, Curso do Mairo Vergara, Duolingo, ou qualquer outro que você
adicionar) como concluídas — gravando direto na mesma planilha Excel do
GitHub que o English Journey usa.

## Por que um PWA, e não uma integração automática?

**English Live** e o curso do **Mairo Vergara (Hotmart)** não oferecem
nenhuma forma de automação disponível para você como usuário/aluno (sem
API pública nem webhook acessível — no caso da Hotmart, o webhook existe,
mas só quem configura é o produtor do curso, não o aluno). Por isso, a
solução realista é **eliminar o atrito**: você só abre este atalho (ou
nem isso — pode deixar na tela inicial do celular) e toca 1 vez.

## Regra de qual tarefa é marcada (idêntica ao restante do sistema)

Esta é a MESMA regra usada pela sincronização automática do Duolingo no
`app.py` e no `duolingo_autosync.py` — implementada de forma independente
em JavaScript aqui, mas testada para produzir exatamente o mesmo
resultado (8 testes automatizados comparando as duas implementações):

1. Procura, para o **seu usuário**, tarefas **não concluídas** cujo texto
   (`Tarefa` + `Modalidade`) contenha a palavra-chave do atalho.
2. Se existir alguma pendente com data **até hoje** (atrasada ou de
   hoje), marca a **mais antiga** delas — limpa o atraso em ordem.
3. Se só existir tarefa **futura**, o app **pergunta antes** de marcar.
4. Se não achar nenhuma pendente, avisa que não há nada a marcar.

## Passo a passo de instalação

### 1. Suba os arquivos para o GitHub (via GitHub Pages)
Pode ser o mesmo repositório de dados do English Journey ou um separado
(recomendado). O PWA só precisa **acessar** o arquivo de dados via API.

1. Crie (ou use) um repositório, ex.: `english-journey-atalho`.
2. Envie estes arquivos para a raiz: `index.html`, `app.js`, `sw.js`,
   `manifest.json` e a pasta `icons/` (com `icon-192.png` e `icon-512.png`).
3. Vá em **Settings → Pages** → em "Source" escolha a branch `main` e a
   pasta `/ (root)` → Salvar.
4. Em alguns minutos, o GitHub te dá uma URL tipo:
   `https://SEU_USUARIO.github.io/english-journey-atalho/`

> ⚠️ PWAs só funcionam (instalar, funcionar offline) em **HTTPS** — o
> GitHub Pages já entrega isso de graça.

### 2. Crie um token do GitHub só para isso (escopo mínimo)
1. GitHub → **Settings → Developer settings → Fine-grained tokens →
   Generate new token**.
2. Em "Repository access", escolha **apenas** o repositório onde está o
   Excel de dados (ex.: `english-dashboard-data`).
3. Em "Permissions", dê **Contents: Read and write**.
4. Copie o token gerado (começa com `github_pat_...`).

⚠️ **Segurança**: o token fica salvo **apenas no armazenamento local do
seu navegador/celular**. Ainda assim, limite o escopo a esse único
repositório e evite instalar em aparelhos compartilhados. Se desconfiar
de vazamento, revogue-o a qualquer momento.

### 3. Instale o PWA no celular
- **Android (Chrome)**: abra a URL → menu (⋮) → "Adicionar à tela
  inicial" / "Instalar app".
- **iPhone (Safari)**: abra a URL → botão de compartilhar (□↑) →
  "Adicionar à Tela de Início".

### 4. Configure na primeira abertura
- **Token do GitHub**, **Repositório**, **Branch**, **Caminho do
  arquivo** (ex. `data/estudo_ingles_dados.xlsx`), **Seu usuário**
  (idêntico ao cadastrado na aba `Usuarios`).
- **Atalhos**: já vêm 3 pré-configurados (Duolingo 🦉, English Live 🗣️,
  Mairo Vergara 🎓) — edite emoji/nome/palavra-chave, remova, ou adicione
  quantos quiser, direto no app.

## Sobre a palavra-chave de cada atalho
Comparada (sem diferenciar maiúsculas/minúsculas) contra `Tarefa` **e**
`Modalidade`. Ex.: se sua Modalidade é "Mairo Vergara", a palavra-chave
`mairo` já encontra certinho.

## Funciona offline?
A interface abre normalmente sem internet. A **gravação** sempre precisa
de internet — se tocar num botão sem conexão, o app **enfileira** a ação
e sincroniza automaticamente quando a internet voltar (ou ao tocar em
"🔄 Tentar sincronizar agora"). Ações de tarefa **futura** nunca são
confirmadas sozinhas pela fila offline — por segurança, sempre esperam
você confirmar manualmente.

## Limitações importantes (leia)
- Sem autenticação própria: quem tiver o aparelho instalado/configurado
  marca tarefas daquele usuário. Não instale em aparelhos compartilhados.
- Conflitos de gravação simultânea são resolvidos com nova tentativa
  automática (até 3x) — em uso pessoal isso praticamente não ocorre.
