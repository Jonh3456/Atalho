"""
Sincronização do arquivo Excel com um repositório GitHub, usando a
Contents API (https://docs.github.com/en/rest/repos/contents).

Requer, em st.secrets (arquivo .streamlit/secrets.toml ou nas
"Secrets" do Streamlit Community Cloud):

    GITHUB_TOKEN      = "ghp_xxx..."      # Personal Access Token com escopo 'repo'
    GITHUB_REPO       = "usuario/repo"    # ex: "darlei/english-dashboard-data"
    GITHUB_BRANCH     = "main"            # opcional, default "main"
    GITHUB_FILE_PATH  = "data/estudo_ingles_dados.xlsx"  # opcional
"""
import base64
import time

import requests
import streamlit as st

API_ROOT = "https://api.github.com"


def _get_secret(key: str, default: str = "") -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:  # noqa: BLE001
        return default


def _normalize_repo(repo: str) -> str:
    repo = (repo or "").strip().strip('"').strip("'").strip("/")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if repo.lower().startswith(prefix):
            repo = repo[len(prefix):]
            break
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return repo.strip("/")


def _normalize_path(path: str, repo: str) -> str:
    path = (path or "").strip().strip('"').strip("'")
    for marker in ("/blob/main/", "/blob/master/"):
        if marker in path:
            path = path.split(marker, 1)[1]
            break
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if path.lower().startswith(prefix):
            remainder = path[len(prefix):]
            parts = remainder.split("/")
            if len(parts) > 4 and parts[2] in ("blob", "tree"):
                path = "/".join(parts[4:])
            else:
                path = remainder
            break
    path = path.replace("\\", "/").strip("/")
    while "//" in path:
        path = path.replace("//", "/")
    if repo and path.lower().startswith(repo.lower() + "/"):
        path = path[len(repo) + 1:]
    return path.strip("/")


def _normalize_branch(branch: str) -> str:
    branch = (branch or "main").strip().strip('"').strip("'").strip("/")
    return branch or "main"


def _config():
    repo = _normalize_repo(_get_secret("GITHUB_REPO", ""))
    branch = _normalize_branch(_get_secret("GITHUB_BRANCH", "main"))
    raw_path = _get_secret("GITHUB_FILE_PATH", "data/estudo_ingles_dados.xlsx")
    path = _normalize_path(raw_path, repo) or "data/estudo_ingles_dados.xlsx"
    return repo, branch, path


def get_diagnostics() -> dict:
    repo, branch, path = _config()
    token = _get_secret("GITHUB_TOKEN", "")
    return {
        "repo": repo, "branch": branch, "path": path,
        "token_presente": bool(token),
        "token_prefixo": (token[:7] + "...") if token else "",
        "url_api": f"{API_ROOT}/repos/{repo}/contents/{path}" if repo and path else "",
    }


def _headers():
    token = _get_secret("GITHUB_TOKEN", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def is_configured() -> bool:
    repo, _, path = _config()
    token = _get_secret("GITHUB_TOKEN", "")
    return bool(repo) and bool(token) and bool(path)


def fetch_file():
    repo, branch, path = _config()
    if not repo or not path:
        raise RuntimeError("GITHUB_REPO ou GITHUB_FILE_PATH vazios após normalização.")
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=_headers(), params={"ref": branch}, timeout=20)
    if resp.status_code == 200:
        payload = resp.json()
        content = base64.b64decode(payload["content"])
        return content, payload["sha"]
    if resp.status_code == 404:
        return None, None
    raise RuntimeError(f"Erro ao ler arquivo no GitHub ({resp.status_code}): {resp.text[:300]}")


def push_file(content: bytes, sha, message: str) -> str:
    repo, branch, path = _config()
    if not repo or not path:
        raise RuntimeError("GITHUB_REPO ou GITHUB_FILE_PATH vazios após normalização.")
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    body = {"message": message, "content": base64.b64encode(content).decode("utf-8"), "branch": branch}
    if sha:
        body["sha"] = sha
    for attempt in range(3):
        resp = requests.put(url, headers=_headers(), json=body, timeout=30)
        if resp.status_code in (200, 201):
            return resp.json()["content"]["sha"]
        if resp.status_code == 409 and attempt < 2:
            _, latest_sha = fetch_file()
            body["sha"] = latest_sha
            time.sleep(0.6)
            continue
        raise RuntimeError(f"Erro ao salvar arquivo no GitHub ({resp.status_code}): {resp.text[:300]}")
    raise RuntimeError("Não foi possível salvar no GitHub após múltiplas tentativas (conflito de versão).")


# ============================================================
# Variantes genéricas (path arbitrário) — usadas pela tela de Materiais
# de Estudo para salvar/ler/excluir arquivos anexados, guardados em um
# caminho próprio (ex: "materiais/12_apostila.pdf") dentro do MESMO
# repositório/branch já configurados para o arquivo de dados principal.
# ============================================================
def fetch_file_at(path: str):
    """Igual a fetch_file(), mas para um caminho arbitrário dentro do
    repositório configurado (em vez do caminho fixo do Excel principal)."""
    repo, branch, _ = _config()
    if not repo or not path:
        raise RuntimeError("GITHUB_REPO vazio ou caminho do arquivo vazio.")
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=_headers(), params={"ref": branch}, timeout=30)
    if resp.status_code == 200:
        payload = resp.json()
        content = base64.b64decode(payload["content"])
        return content, payload["sha"]
    if resp.status_code == 404:
        return None, None
    raise RuntimeError(f"Erro ao ler arquivo no GitHub ({resp.status_code}): {resp.text[:300]}")


def push_file_at(content: bytes, sha, message: str, path: str) -> str:
    """Igual a push_file(), mas para um caminho arbitrário."""
    repo, branch, _ = _config()
    if not repo or not path:
        raise RuntimeError("GITHUB_REPO vazio ou caminho do arquivo vazio.")
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    body = {"message": message, "content": base64.b64encode(content).decode("utf-8"), "branch": branch}
    if sha:
        body["sha"] = sha
    for attempt in range(3):
        resp = requests.put(url, headers=_headers(), json=body, timeout=60)
        if resp.status_code in (200, 201):
            return resp.json()["content"]["sha"]
        if resp.status_code == 409 and attempt < 2:
            _, latest_sha = fetch_file_at(path)
            body["sha"] = latest_sha
            time.sleep(0.6)
            continue
        raise RuntimeError(f"Erro ao salvar arquivo no GitHub ({resp.status_code}): {resp.text[:300]}")
    raise RuntimeError("Não foi possível salvar no GitHub após múltiplas tentativas (conflito de versão).")


def delete_file_at(path: str, sha: str, message: str) -> None:
    """Exclui um arquivo do repositório (usado ao excluir um material do
    tipo Arquivo). Se o sha não for informado ou o arquivo não existir
    mais, não faz nada (evita erro ao tentar excluir algo já removido)."""
    if not sha:
        return
    repo, branch, _ = _config()
    if not repo or not path:
        return
    url = f"{API_ROOT}/repos/{repo}/contents/{path}"
    body = {"message": message, "sha": sha, "branch": branch}
    resp = requests.delete(url, headers=_headers(), json=body, timeout=30)
    if resp.status_code not in (200, 201, 404):
        raise RuntimeError(f"Erro ao excluir arquivo no GitHub ({resp.status_code}): {resp.text[:300]}")
