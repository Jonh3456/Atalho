"""
Sincronização 100% automática do English Journey com o Duolingo, para
rodar como um GitHub Action agendado (cron) — funciona MESMO QUE NINGUÉM
ABRA O APP naquele dia.

Usa a MESMA função compartilhada `data_model.find_nearest_pending_task`
que o app.py (botão manual/checagem automática no login) e o PWA de
atalho seguem como referência conceitual — garantindo que a regra de
"qual tarefa marcar" seja sempre a mesma: prioriza pendências atrasadas
ou de hoje (a mais antiga primeiro); só marca tarefa futura se não houver
nenhuma vencida (e mesmo assim, aqui no modo automático, tarefa futura é
IGNORADA por segurança — quem confirma marcação antecipada é sempre uma
pessoa, pela tela de Configurações ou pelo PWA).

Variáveis de ambiente esperadas (defina como "Secrets" do repositório em
GitHub → Settings → Secrets and variables → Actions):
    GITHUB_TOKEN      = Personal Access Token com escopo 'repo' (Contents: Read/Write)
    GITHUB_REPO       = "usuario/repo" (ex.: darlei/english-dashboard-data)
    GITHUB_BRANCH     = "main"  (opcional, default "main")
    GITHUB_FILE_PATH  = "data/estudo_ingles_dados.xlsx"  (opcional)

Uso local (teste manual):
    export GITHUB_TOKEN=ghp_xxx
    export GITHUB_REPO=usuario/english-dashboard-data
    python duolingo_autosync.py
"""
from __future__ import annotations

import base64
import os
import time
from datetime import date, datetime

import requests

import data_model as dm
import duolingo_sync

API_ROOT = "https://api.github.com"


def _config():
    repo = os.environ.get("GITHUB_REPO", "").strip().strip("/")
    branch = os.environ.get("GITHUB_BRANCH", "main").strip() or "main"
    path = os.environ.get("GITHUB_FILE_PATH", "data/estudo_ingles_dados.xlsx").strip().strip("/")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repo or not token:
        raise RuntimeError("Defina GITHUB_REPO e GITHUB_TOKEN nas variáveis de ambiente/secrets.")
    return repo, branch, path, token


def _headers(token: str):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_file(repo, branch, path, token):
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=_headers(token), params={"ref": branch}, timeout=30)
    if resp.status_code == 200:
        payload = resp.json()
        return base64.b64decode(payload["content"]), payload["sha"]
    if resp.status_code == 404:
        return None, None
    raise RuntimeError(f"Erro ao ler arquivo no GitHub ({resp.status_code}): {resp.text[:300]}")


def push_file(repo, branch, path, token, content: bytes, sha, message: str) -> str:
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    body = {"message": message, "content": base64.b64encode(content).decode("utf-8"), "branch": branch}
    if sha:
        body["sha"] = sha
    for attempt in range(3):
        resp = requests.put(url, headers=_headers(token), json=body, timeout=30)
        if resp.status_code in (200, 201):
            return resp.json()["content"]["sha"]
        if resp.status_code == 409 and attempt < 2:
            _, latest_sha = fetch_file(repo, branch, path, token)
            body["sha"] = latest_sha
            time.sleep(0.6)
            continue
        raise RuntimeError(f"Erro ao salvar arquivo no GitHub ({resp.status_code}): {resp.text[:300]}")
    raise RuntimeError("Não foi possível salvar no GitHub após múltiplas tentativas (conflito de versão).")


def run() -> None:
    repo, branch, path, token = _config()
    print(f"[duolingo_autosync] Lendo {path} em {repo}@{branch} ...")
    content, sha = fetch_file(repo, branch, path, token)
    if not content:
        print("[duolingo_autosync] Arquivo de dados não encontrado — nada a fazer.")
        return

    raw = dm.bytes_to_workbook(content)
    usuarios = dm.normalize_usuarios(raw.get("Usuarios", dm.default_usuarios_df()))
    atividades = dm.normalize_atividades(raw.get("Atividades", dm.empty_atividades_df()))

    hoje = date.today()
    houve_alteracao = False
    total_marcadas = 0

    for idx, urow in usuarios.iterrows():
        user = urow["Usuario"]
        if not bool(urow.get("DuolingoAutoSync", False)):
            continue
        duo_username = str(urow.get("DuolingoUsername", "") or "").strip()
        if not duo_username:
            continue

        print(f"[duolingo_autosync] Checando {user} (@{duo_username}) ...")
        stats = duolingo_sync.fetch_public_stats(duo_username)
        if stats is None:
            print("  -> Não foi possível consultar o perfil (privado, inexistente ou endpoint indisponível).")
            continue

        xp_base = int(urow.get("DuolingoXPBase", 0) or 0)
        streak_base = int(urow.get("DuolingoStreakBase", 0) or 0)
        concluiu = duolingo_sync.completed_recently(stats, xp_base, streak_base)

        usuarios.at[idx, "DuolingoXPBase"] = stats["total_xp"]
        usuarios.at[idx, "DuolingoStreakBase"] = stats["streak"]
        usuarios.at[idx, "DuolingoUltimaSync"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        houve_alteracao = True

        if not concluiu:
            print("  -> Sem novidade desde a última checagem.")
            continue

        alvo = dm.find_nearest_pending_task(atividades, user, dm.DUOLINGO_TASK_KEYWORD, hoje)
        if alvo is None:
            print("  -> Progresso detectado no Duolingo, mas não há tarefa 'Duolingo' pendente no calendário.")
            continue
        if alvo.is_futura:
            # Modo 100% automático: por segurança, NÃO marca tarefa futura
            # sozinho (isso fica para confirmação humana no app/PWA).
            print(f"  -> Progresso detectado, mas a única tarefa pendente é futura ({alvo.data_iso}). Ignorando (requer confirmação manual).")
            continue

        i = atividades.index[atividades["ID"] == alvo.id][0]
        atividades.at[i, "Concluido"] = True
        if not atividades.at[i, "MinutosExecutados"]:
            atividades.at[i, "MinutosExecutados"] = atividades.at[i, "MinutosPlanejados"]
        atividades.at[i, "DataConclusao"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        nota_atual = atividades.at[i, "Anotacoes"] or ""
        nota_sync = (
            f"Sincronizado automaticamente via Duolingo (XP: {xp_base} -> {stats['total_xp']}, "
            f"streak: {stats['streak']})"
        )
        atividades.at[i, "Anotacoes"] = (nota_atual + " | " + nota_sync).strip(" |") if nota_atual else nota_sync
        total_marcadas += 1
        print(f"  -> Progresso detectado! Tarefa de {alvo.data_iso} marcada como concluída.")

    if not houve_alteracao:
        print("[duolingo_autosync] Nenhuma pessoa com sincronização automática configurada. Nada a fazer.")
        return

    novo_conteudo = dm.workbook_to_bytes({"Atividades": atividades, "Usuarios": usuarios})
    mensagem = f"Sincronização automática Duolingo ({hoje.isoformat()}) — {total_marcadas} tarefa(s) marcada(s)"
    push_file(repo, branch, path, token, novo_conteudo, sha, mensagem)
    print(f"[duolingo_autosync] Concluído. {mensagem}.")


if __name__ == "__main__":
    run()
