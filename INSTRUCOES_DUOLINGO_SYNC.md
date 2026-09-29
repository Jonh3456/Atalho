# English Journey + Duolingo + Atalho de 1 clique — guia de instalação

Este pacote traz TUDO que foi construído nas últimas conversas, já
consolidado em cima do seu `app.py`/`data_model.py` mais recentes (os que
você anexou), para evitar os erros de versões desencontradas de antes.

## O que tem neste zip

```
app.py                              <- ATUALIZADO (integração Duolingo + atalhos 1 clique)
data_model.py                       <- ATUALIZADO (colunas Duolingo + função find_nearest_pending_task)
github_sync.py                      <- sem alteração (incluído para o pacote ficar completo)
theme.py                            <- sem alteração (incluído para o pacote ficar completo)
requirements.txt                    <- sem alteração (já tinha "requests")
README.md                           <- sem alteração (readme original do repositório de dados)
duolingo_sync.py                    <- NOVO (lê o perfil público do Duolingo)
duolingo_autosync.py                <- NOVO (roda sozinho via GitHub Actions, sem abrir o app)
.github/workflows/duolingo_autosync.yml   <- NOVO (agenda a execução automática, 2x/dia)
pwa/                                 <- NOVO (atalho de 1 clique instalável no celular — PWA)
  ├── index.html, app.js, sw.js, manifest.json
  ├── icons/icon-192.png, icons/icon-512.png
  └── README.md (passo a passo de instalação do PWA)
```

## O raciocínio que foi mantido em TODO o sistema

Depois de pesquisar, confirmei que:
- **Duolingo**: não tem API/webhook oficial, mas tem um endpoint não
  documentado de perfil público (usado por projetos de "streak
  tracking") — por isso a sincronização é feita por **leitura**
  periódica, não por aviso.
- **EF English Live**: não tem API/webhook acessível, nem em conta
  pessoal nem corporativa.
- **Mairo Vergara (Hotmart)**: a Hotmart até tem webhook de "módulo
  completo", mas só o **produtor** do curso pode configurá-lo — não o
  aluno.

Como só o Duolingo permite alguma automação real, a solução para
English Live e Mairo Vergara é **eliminar o atrito manual** com um atalho
de 1 clique (tela no próprio dashboard + um PWA instalável no celular).

**Uma única regra de negócio, usada em 3 lugares diferentes** (para
nunca haver comportamento divergente):
1. Sincronização automática do Duolingo (dentro do `app.py`, ao logar).
2. Script `duolingo_autosync.py` (roda sozinho via GitHub Actions, mesmo
   que ninguém abra o app).
3. Atalhos manuais de 1 clique (English Live / Mairo Vergara / qualquer
   outro), tanto na tela **Configurações** do dashboard quanto no PWA.

A regra (função `data_model.find_nearest_pending_task`, testada com 11
casos automatizados, e replicada em JavaScript no PWA com paridade
confirmada por 8 testes):
1. Entre as tarefas pendentes do usuário com a palavra-chave certa,
   filtra as que já venceram (data ≤ hoje).
2. Se houver alguma vencida/hoje, marca a **mais antiga**.
3. Se só houver tarefa **futura**, **pede confirmação** antes de marcar
   (nunca marca uma tarefa de dias à frente sozinho, exceto quando você
   mesmo confirma).
4. Se não houver nenhuma pendente, avisa que não há nada a marcar.

## Passo a passo de instalação

### 1. Suba os arquivos atualizados no repositório de dados do GitHub
Substitua no seu repositório (o mesmo do Streamlit, ex.:
`english-dashboard-data`):
- `app.py`
- `data_model.py`

E adicione os arquivos novos na **raiz** do mesmo repositório:
- `duolingo_sync.py`
- `duolingo_autosync.py`
- pasta `.github/workflows/` com `duolingo_autosync.yml` dentro

(`github_sync.py`, `theme.py`, `requirements.txt` e `README.md` estão
inclusos no zip sem alterações, apenas para o pacote ficar completo caso
você prefira reenviar tudo de uma vez.)

### 2. Configure os "Secrets" do GitHub Actions (sincronização 100% automática)
Em **Settings → Secrets and variables → Actions**, crie:
- `DATA_REPO_TOKEN` → Personal Access Token com escopo `repo` (Contents:
  Read and write) — pode ser um token novo ou o mesmo do Streamlit.
- `GITHUB_REPO` → ex.: `SEU_USUARIO/english-dashboard-data`
- `GITHUB_BRANCH` → ex.: `main`
- `GITHUB_FILE_PATH` → ex.: `data/estudo_ingles_dados.xlsx`

### 3. No app (Streamlit), cada pessoa ativa a integração com Duolingo
1. Abra o English Journey → **⚙️ Configurações**.
2. Role até **"🦉 Integração com Duolingo"**.
3. Informe seu `@usuario` do Duolingo (confirme que seu perfil está
   **público**: app do Duolingo → Perfil → ⚙️ → Privacidade).
4. Marque **"Ativar sincronização automática"** → **Salvar**.
5. Garanta que exista, no seu calendário, uma tarefa com a palavra
   **"Duolingo"** no nome ou na modalidade.

A partir daqui: toda vez que você abrir o app, roda 1 checagem
automática (toast 🦉). Duas vezes por dia, o GitHub Action roda sozinho,
mesmo sem abrir o app.

### 4. Use os atalhos de 1 clique para English Live e Mairo Vergara
Na mesma tela de Configurações, logo abaixo, em **"✅ Atalhos de 1
clique"**, há um botão para cada um — clique e ele marca a tarefa
pendente mais próxima daquele tipo, seguindo a mesma regra acima.

### 5. (Opcional, recomendado) Instale o atalho como PWA no celular
Para não precisar nem abrir o dashboard completo — veja o passo a passo
em `pwa/README.md`.

## Testes realizados antes da entrega
- ✅ `py_compile` em todos os arquivos Python (sintaxe válida).
- ✅ 11 testes unitários da função `find_nearest_pending_task` (tarefa
  atrasada, futura, sem pendência, isolamento por usuário, busca por
  Modalidade, tarefa já concluída nunca escolhida, migração de esquema
  antigo, XP/streak).
- ✅ 8 testes da versão JavaScript (PWA) confirmando paridade exata com
  a versão Python.
- ✅ Round-trip completo do Excel (gravar → ler → normalizar) com as
  novas colunas do Duolingo.
- ✅ Verificação cruzada de que todas as funções/variáveis novas
  referenciadas em `app.py` estão definidas antes do uso.
