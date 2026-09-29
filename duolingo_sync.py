"""
Integração (NÃO OFICIAL) com o Duolingo para sincronizar automaticamente a
conclusão da tarefa diária de Duolingo dentro do English Journey.

LEIA ANTES DE USAR — por que isso funciona por "leitura" e não por "aviso":
----------------------------------------------------------------------------
O Duolingo não publica uma API pública oficial nem webhooks para
desenvolvedores externos. Ou seja, tecnicamente NÃO é possível o Duolingo
"avisar" este app quando você conclui uma lição.

O que existe — e é o que este módulo usa — é um endpoint de perfil não
documentado, usado por dezenas de projetos open-source de "streak
tracking", que devolve dados PÚBLICOS do seu perfil (XP total acumulado e
streak/sequência atual), desde que:
  1) o seu perfil no Duolingo esteja configurado como PÚBLICO
     (Configurações > Privacidade, no app/site do Duolingo); e
  2) você informe o seu @usuario (não o nome de exibição).

Riscos e limitações (importantes, avise sempre o usuário):
  - É um endpoint não oficial: o Duolingo pode alterá-lo ou bloqueá-lo a
    qualquer momento, sem aviso prévio.
  - Não use com alta frequência nem para nada além de ler os SEUS
    PRÓPRIOS dados públicos.
  - A detecção de "concluiu hoje" é uma INFERÊNCIA (streak subiu e/ou XP
    subiu), não uma confirmação exata de qual lição foi feita.
"""
from __future__ import annotations

import requests

DUOLINGO_PROFILE_URL = "https://www.duolingo.com/2017-06-30/users"
FIELDS = "username,streak,totalXp,streakData{currentStreak{length}}"
TIMEOUT = 10
XP_MINIMO_PADRAO = 10  # XP mínimo de ganho para considerar "sessão concluída"


def fetch_public_stats(username: str) -> dict | None:
    """Busca XP total e streak atual do perfil PÚBLICO do Duolingo.

    Retorna um dict {"username", "total_xp", "streak"} ou None se:
    - o nome de usuário estiver vazio;
    - o perfil não existir ou estiver privado;
    - o endpoint não responder (timeout, bloqueio, mudança de formato etc.).

    Uma falha aqui NUNCA deve derrubar o app — o chamador deve tratar o
    retorno None como "não foi possível sincronizar agora, tente depois".
    """
    if not username or not username.strip():
        return None
    try:
        resp = requests.get(
            DUOLINGO_PROFILE_URL,
            params={"username": username.strip(), "fields": FIELDS},
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EnglishJourneyPersonalSync/1.0)"},
        )
        resp.raise_for_status()
        data = resp.json()
        users = data.get("users") or []
        if not users:
            return None
        u = users[0]
        streak_data = u.get("streakData") or {}
        current_streak = (streak_data.get("currentStreak") or {})
        return {
            "username": u.get("username", username),
            "total_xp": int(u.get("totalXp", 0) or 0),
            "streak": int(u.get("streak", 0) or current_streak.get("length", 0) or 0),
        }
    except Exception:  # noqa: BLE001
        return None


def completed_recently(stats_novo: dict, xp_base: int, streak_base: int,
                        xp_minimo: int = XP_MINIMO_PADRAO) -> bool:
    """Decide se a pessoa concluiu uma sessão de Duolingo desde o último
    snapshot salvo (xp_base / streak_base), usando dois sinais combinados:

      1) STREAK subiu em relação ao snapshot anterior -> concluiu.
      2) OU o XP TOTAL subiu pelo menos `xp_minimo` -> concluiu (cobre o
         caso de quem já tinha mantido o streak antes da última checagem).
    """
    if stats_novo is None:
        return False
    streak_subiu = stats_novo["streak"] > streak_base
    xp_subiu = (stats_novo["total_xp"] - xp_base) >= xp_minimo
    return bool(streak_subiu or xp_subiu)
