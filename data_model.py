"""
Módulo de dados: estrutura do Excel, template do plano de 6 meses,
catálogo de materiais para o plano personalizado, distribuição inteligente
(empacotamento) dos materiais nos horários livres, usuários (com suporte a
administrador), materiais de estudo compartilhados (links/arquivos) e
helpers de leitura/escrita em memória (BytesIO).

IMPORTANTE: cada pessoa tem seu próprio período de 6 meses, que começa no
dia em que ela cria a conta (não em uma data fixa do projeto).
"""
from __future__ import annotations

import calendar
import hashlib
import io
import json
from datetime import date, timedelta

import pandas as pd

START_DATE = date(2026, 8, 31)
END_DATE = date(2027, 2, 28)

SKILLS = ["Speaking", "Listening", "Writing", "Grammar", "Vocabulary"]
MODALITIES = ["English Live", "Mairo Vergara", "Estudo complementar", "Personalizado"]

SKILL_COLORS = {
    "Speaking": "#2563eb",
    "Listening": "#8b5cf6",
    "Writing": "#14b8a6",
    "Grammar": "#f59e0b",
    "Vocabulary": "#ef4444",
}

USER_PALETTE = ["#2563eb", "#f97316", "#10b981", "#e11d48", "#a855f7", "#0ea5e9"]

WEEKDAY_NAMES = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

ATIVIDADES_COLUMNS = [
    "ID", "Usuario", "Data", "Horario", "Tarefa", "Habilidade", "Modalidade",
    "MinutosPlanejados", "MinutosExecutados", "Concluido", "Anotacoes", "DataConclusao",
]

USUARIOS_COLUMNS = [
    "Usuario", "Equipe", "Cor", "MetaSemanal", "SenhaHash", "IsAdmin",
    "TipoPlano", "DisponibilidadeJSON", "MateriaisJSON", "DuracoesPadraoJSON",
]

# "Tipo" é "Link" ou "Arquivo". Para Link, usa-se a coluna URL. Para
# Arquivo, usam-se NomeArquivo (nome original) e CaminhoArquivo (caminho
# do blob salvo no repositório GitHub, ex: "materiais/12_apostila.pdf").
MATERIAIS_COLUMNS = [
    "ID", "Usuario", "Tipo", "Titulo", "Descricao", "URL",
    "NomeArquivo", "CaminhoArquivo", "TamanhoKB", "DataCriacao",
]

# ============================================================
# TEMPLATE SEMANAL PADRÃO (modelo "📋 Usar modelo padrão")
# 0=Segunda ... 6=Domingo (igual a date.weekday())
# ============================================================
WEEKLY_TEMPLATE = {
    0: [
        {"Tarefa": "Exercícios de gramática", "Habilidade": "Grammar", "Modalidade": "English Live", "MinutosPlanejados": 30, "Horario": "09:00"},
        {"Tarefa": "Lição do dia (Mairo Vergara)", "Habilidade": "Listening", "Modalidade": "Mairo Vergara", "MinutosPlanejados": 40, "Horario": "10:30"},
        {"Tarefa": "História em inglês (30 min)", "Habilidade": "Listening", "Modalidade": "Mairo Vergara", "MinutosPlanejados": 30, "Horario": "14:00"},
        {"Tarefa": "Conversação em grupo", "Habilidade": "Speaking", "Modalidade": "English Live", "MinutosPlanejados": 45, "Horario": "16:00"},
    ],
    1: [
        {"Tarefa": "Anki (memorização)", "Habilidade": "Vocabulary", "Modalidade": "Mairo Vergara", "MinutosPlanejados": 20, "Horario": "06:40"},
        {"Tarefa": "Conversação em grupo", "Habilidade": "Speaking", "Modalidade": "English Live", "MinutosPlanejados": 40, "Horario": "17:30"},
    ],
    2: [
        {"Tarefa": "História em inglês", "Habilidade": "Listening", "Modalidade": "Mairo Vergara", "MinutosPlanejados": 30, "Horario": "06:40"},
        {"Tarefa": "Diário em inglês", "Habilidade": "Writing", "Modalidade": "Estudo complementar", "MinutosPlanejados": 30, "Horario": "22:00"},
    ],
    3: [
        {"Tarefa": "Anki e revisão gramatical", "Habilidade": "Grammar", "Modalidade": "English Live", "MinutosPlanejados": 30, "Horario": "06:40"},
        {"Tarefa": "Conversação com professor", "Habilidade": "Speaking", "Modalidade": "English Live", "MinutosPlanejados": 40, "Horario": "18:00"},
    ],
    4: [
        {"Tarefa": "Lição do dia (Mairo Vergara)", "Habilidade": "Listening", "Modalidade": "Mairo Vergara", "MinutosPlanejados": 30, "Horario": "09:00"},
        {"Tarefa": "Audiobook Mairo Vergara", "Habilidade": "Listening", "Modalidade": "Mairo Vergara", "MinutosPlanejados": 25, "Horario": "11:00"},
        {"Tarefa": "Texto e correção", "Habilidade": "Writing", "Modalidade": "Estudo complementar", "MinutosPlanejados": 45, "Horario": "14:00"},
        {"Tarefa": "Gravação de voz (Speaking)", "Habilidade": "Speaking", "Modalidade": "Estudo complementar", "MinutosPlanejados": 30, "Horario": "16:00"},
    ],
    5: [
        {"Tarefa": "Imersão: filme ou série em inglês", "Habilidade": "Listening", "Modalidade": "Estudo complementar", "MinutosPlanejados": 60, "Horario": "09:00"},
        {"Tarefa": "Lição e Anki", "Habilidade": "Vocabulary", "Modalidade": "Mairo Vergara", "MinutosPlanejados": 40, "Horario": "11:15"},
        {"Tarefa": "Speaking e resumo escrito", "Habilidade": "Speaking", "Modalidade": "Estudo complementar", "MinutosPlanejados": 40, "Horario": "14:00"},
    ],
    6: [
        {"Tarefa": "Revisão semanal e planejamento", "Habilidade": "Vocabulary", "Modalidade": "Estudo complementar", "MinutosPlanejados": 60, "Horario": "15:00"},
    ],
}

# ============================================================
# CATÁLOGO DE MATERIAIS (modelo "🎯 Personalizar")
# ============================================================
MATERIAL_CATALOG: dict[str, str] = {
    "Anki (memorização)": "Vocabulary",
    "Mairo Vergara - Lição do dia": "Grammar",
    "Mairo Vergara - Áudio/História": "Listening",
    "Mairo Vergara - Audiobook": "Listening",
    "English Live - Exercício de gramática": "Grammar",
    "English Live - Conversação em grupo": "Speaking",
    "English Live - Aula com professor": "Speaking",
    "Filme/Série legendado": "Listening",
    "Podcast em inglês": "Listening",
    "Livro/Leitura": "Vocabulary",
    "Diário/Redação": "Writing",
    "Gravação de voz (Speaking)": "Speaking",
}

DEFAULT_MATERIAL_DURATIONS: dict[str, int] = {
    "Anki (memorização)": 20,
    "Mairo Vergara - Lição do dia": 45,
    "Mairo Vergara - Áudio/História": 30,
    "Mairo Vergara - Audiobook": 40,
    "English Live - Exercício de gramática": 30,
    "English Live - Conversação em grupo": 40,
    "English Live - Aula com professor": 40,
    "Filme/Série legendado": 60,
    "Podcast em inglês": 30,
    "Livro/Leitura": 30,
    "Diário/Redação": 30,
    "Gravação de voz (Speaking)": 20,
}
DEFAULT_CUSTOM_MATERIAL_DURATION = 30


def get_default_duration(nome_material: str) -> int:
    return DEFAULT_MATERIAL_DURATIONS.get(nome_material, DEFAULT_CUSTOM_MATERIAL_DURATION)


def list_template_task_names() -> list[str]:
    vistos: list[str] = []
    for _, itens in sorted(WEEKLY_TEMPLATE.items()):
        for item in itens:
            if item["Tarefa"] not in vistos:
                vistos.append(item["Tarefa"])
    return vistos


def template_task_default_duration(nome_tarefa: str) -> int:
    for _, itens in WEEKLY_TEMPLATE.items():
        for item in itens:
            if item["Tarefa"] == nome_tarefa:
                return item["MinutosPlanejados"]
    return DEFAULT_CUSTOM_MATERIAL_DURATION


DEFAULT_AVAILABILITY_ROWS = [
    {"Dia": "Segunda", "Horario": "09:00", "Minutos": 60},
    {"Dia": "Terça", "Horario": "06:40", "Minutos": 40},
    {"Dia": "Terça", "Horario": "17:30", "Minutos": 60},
    {"Dia": "Quarta", "Horario": "06:40", "Minutos": 40},
    {"Dia": "Quarta", "Horario": "22:00", "Minutos": 30},
    {"Dia": "Quinta", "Horario": "06:40", "Minutos": 40},
    {"Dia": "Quinta", "Horario": "18:00", "Minutos": 60},
    {"Dia": "Sexta", "Horario": "09:00", "Minutos": 90},
    {"Dia": "Sábado", "Horario": "11:00", "Minutos": 120},
    {"Dia": "Domingo", "Horario": "15:00", "Minutos": 60},
]


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def hash_password(raw: str) -> str:
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def build_template_activities(
    usuario: str,
    start_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    custom_durations: dict[str, int] | None = None,
) -> pd.DataFrame:
    start_date = start_date or START_DATE
    end_date = end_date or END_DATE
    custom_durations = custom_durations or {}

    rows = []
    cursor = start_date
    next_id = start_id
    while cursor <= end_date:
        for item in WEEKLY_TEMPLATE.get(cursor.weekday(), []):
            duracao = custom_durations.get(item["Tarefa"], item["MinutosPlanejados"])
            rows.append({
                "ID": next_id, "Usuario": usuario, "Data": cursor.isoformat(),
                "Horario": item["Horario"], "Tarefa": item["Tarefa"],
                "Habilidade": item["Habilidade"], "Modalidade": item["Modalidade"],
                "MinutosPlanejados": int(duracao), "MinutosExecutados": 0,
                "Concluido": False, "Anotacoes": "", "DataConclusao": "",
            })
            next_id += 1
        cursor += timedelta(days=1)
    return pd.DataFrame(rows, columns=ATIVIDADES_COLUMNS)


def _minutes_to_hhmm(total_minutes: int) -> str:
    total_minutes = total_minutes % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _hhmm_to_minutes(hhmm: str) -> int:
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001
        return 18 * 60


def build_personalized_activities(
    usuario: str,
    disponibilidade: dict[int, list[dict]],
    materiais: list[dict],
    start_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    material_durations: dict[str, int] | None = None,
) -> pd.DataFrame:
    start_date = start_date or START_DATE
    end_date = end_date or END_DATE
    material_durations = material_durations or {}

    if not materiais:
        materiais = [{"nome": "Estudo livre", "habilidade": s} for s in SKILLS]

    n = len(materiais)
    durations = [
        max(5, int(material_durations.get(m["nome"], get_default_duration(m["nome"])) or get_default_duration(m["nome"])))
        for m in materiais
    ]

    rows = []
    cursor = start_date
    next_id = start_id
    mat_idx = 0

    while cursor <= end_date:
        blocos = sorted(
            disponibilidade.get(cursor.weekday(), []),
            key=lambda b: str(b.get("horario", "")),
        )
        for bloco in blocos:
            block_minutes = int(bloco.get("minutos", 0) or 0)
            if block_minutes <= 0:
                continue
            current_minute = _hhmm_to_minutes(bloco.get("horario", "18:00"))
            remaining = block_minutes

            while remaining > 0:
                placed = False
                for step in range(n):
                    idx = (mat_idx + step) % n
                    duracao = durations[idx]
                    if duracao <= remaining:
                        material = materiais[idx]
                        rows.append({
                            "ID": next_id, "Usuario": usuario, "Data": cursor.isoformat(),
                            "Horario": _minutes_to_hhmm(current_minute), "Tarefa": material["nome"],
                            "Habilidade": material["habilidade"], "Modalidade": "Personalizado",
                            "MinutosPlanejados": int(duracao), "MinutosExecutados": 0,
                            "Concluido": False, "Anotacoes": "", "DataConclusao": "",
                        })
                        next_id += 1
                        current_minute += duracao
                        remaining -= duracao
                        mat_idx = (idx + 1) % n
                        placed = True
                        break
                if not placed:
                    break
        cursor += timedelta(days=1)
    return pd.DataFrame(rows, columns=ATIVIDADES_COLUMNS)


def weekly_minutes_from_availability(disponibilidade: dict[int, list[dict]]) -> int:
    total = 0
    for blocos in disponibilidade.values():
        for b in blocos:
            total += int(b.get("minutos", 0) or 0)
    return total


def availability_rows_to_dict(rows: list[dict]) -> dict[int, list[dict]]:
    nome_para_idx = {nome: i for i, nome in enumerate(WEEKDAY_NAMES)}
    disponibilidade: dict[int, list[dict]] = {i: [] for i in range(7)}
    for row in rows:
        dia = row.get("Dia")
        idx = nome_para_idx.get(dia)
        minutos = row.get("Minutos", 0) or 0
        horario = row.get("Horario", "18:00") or "18:00"
        if idx is None or int(minutos) <= 0:
            continue
        disponibilidade[idx].append({"horario": str(horario), "minutos": int(minutos)})
    return disponibilidade


def default_usuarios_df() -> pd.DataFrame:
    return pd.DataFrame(
        [{"Usuario": "Admin", "Equipe": "Time Fluência", "Cor": USER_PALETTE[0],
          "MetaSemanal": 14, "SenhaHash": "", "IsAdmin": True,
          "TipoPlano": "padrao", "DisponibilidadeJSON": "[]", "MateriaisJSON": "[]",
          "DuracoesPadraoJSON": "{}"}],
        columns=USUARIOS_COLUMNS,
    )


def ensure_admin(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "IsAdmin" not in df.columns:
        df = df.copy()
        df["IsAdmin"] = False
    if not bool(df["IsAdmin"].any()):
        df = df.copy()
        df.iloc[0, df.columns.get_loc("IsAdmin")] = True
    return df


def availability_rows_to_json(rows: list[dict]) -> str:
    limpo = [
        {"Dia": r.get("Dia", ""), "Horario": str(r.get("Horario", "18:00")), "Minutos": int(r.get("Minutos", 0) or 0)}
        for r in rows if r.get("Dia") and int(r.get("Minutos", 0) or 0) > 0
    ]
    return json.dumps(limpo, ensure_ascii=False)


def availability_rows_from_json(json_str: str) -> list[dict]:
    try:
        rows = json.loads(json_str) if json_str else []
        return rows if isinstance(rows, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def materials_to_json(materiais: list[dict], durations: dict[str, int] | None = None) -> str:
    durations = durations or {}
    limpo = [
        {
            "nome": m["nome"], "habilidade": m["habilidade"],
            "minutos": int(durations.get(m["nome"], m.get("minutos", get_default_duration(m["nome"])))),
        }
        for m in materiais
    ]
    return json.dumps(limpo, ensure_ascii=False)


def materials_from_json(json_str: str) -> list[dict]:
    try:
        materiais = json.loads(json_str) if json_str else []
        return materiais if isinstance(materiais, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def durations_dict_to_json(durations: dict[str, int]) -> str:
    return json.dumps(durations or {}, ensure_ascii=False)


def durations_dict_from_json(json_str: str) -> dict[str, int]:
    try:
        d = json.loads(json_str) if json_str else {}
        return {k: int(v) for k, v in d.items()} if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


FREQUENCIAS_RECORRENCIA = ["Não recorrente", "Diariamente", "Semanalmente", "Mensalmente"]


def generate_recurring_dates(start_date: date, end_date: date, frequencia: str) -> list[date]:
    if end_date < start_date:
        return [start_date]
    datas = []
    cursor = start_date
    if frequencia == "Diariamente":
        while cursor <= end_date:
            datas.append(cursor)
            cursor += timedelta(days=1)
    elif frequencia == "Semanalmente":
        while cursor <= end_date:
            datas.append(cursor)
            cursor += timedelta(days=7)
    elif frequencia == "Mensalmente":
        while cursor <= end_date:
            datas.append(cursor)
            cursor = add_months(cursor, 1)
    else:
        datas.append(start_date)
    return datas


LEVEL_XP_STEP = 500

LEVEL_NAMES = [
    "Explorador do Inglês",
    "Aprendiz Dedicado",
    "Comunicador Iniciante",
    "Falante Confiante",
    "Fluência em Construção",
    "Quase Fluente",
    "Fluente",
    "Mestre da Conversação",
    "Poliglota em Ascensão",
    "Lenda do Inglês",
]


def level_name(level: int) -> str:
    idx = level - 1
    if 0 <= idx < len(LEVEL_NAMES):
        return LEVEL_NAMES[idx]
    extra = level - len(LEVEL_NAMES)
    return f"{LEVEL_NAMES[-1]} {extra + 1}"


def level_xp_range(level: int) -> tuple[int, int | None]:
    minimo = (level - 1) * LEVEL_XP_STEP
    maximo = level * LEVEL_XP_STEP - 1
    return minimo, maximo


def empty_atividades_df() -> pd.DataFrame:
    return pd.DataFrame(columns=ATIVIDADES_COLUMNS)


# ============================================================
# MATERIAIS DE ESTUDO (compartilhados entre todos os participantes)
# ============================================================
def empty_materiais_df() -> pd.DataFrame:
    return pd.DataFrame(columns=MATERIAIS_COLUMNS)


def normalize_materiais(df: pd.DataFrame) -> pd.DataFrame:
    """Garante que a tabela de materiais tenha todas as colunas esperadas,
    mesmo que venha de um arquivo Excel salvo por uma versão mais antiga
    do app (sem essa aba ainda)."""
    if df.empty:
        return empty_materiais_df()
    for col in MATERIAIS_COLUMNS:
        if col not in df.columns:
            df[col] = 0 if col in ("ID", "TamanhoKB") else ""
    df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)
    df["TamanhoKB"] = pd.to_numeric(df["TamanhoKB"], errors="coerce").fillna(0).astype(int)
    for col in ["Usuario", "Tipo", "Titulo", "Descricao", "URL", "NomeArquivo", "CaminhoArquivo", "DataCriacao"]:
        df[col] = df[col].fillna("").astype(str)
    return df[MATERIAIS_COLUMNS]


def safe_filename(nome: str) -> str:
    """Remove caracteres problemáticos de um nome de arquivo, para usar
    como parte do caminho do blob salvo no repositório GitHub."""
    limpo = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in nome).strip()
    limpo = limpo.replace(" ", "_")
    return limpo or "arquivo"


def workbook_to_bytes(dfs: dict) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, df in dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    buffer.seek(0)
    return buffer.read()


def bytes_to_workbook(content: bytes) -> dict:
    buffer = io.BytesIO(content)
    xls = pd.ExcelFile(buffer, engine="openpyxl")
    return {sheet: xls.parse(sheet) for sheet in xls.sheet_names}


def normalize_atividades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return empty_atividades_df()
    for col in ATIVIDADES_COLUMNS:
        if col not in df.columns:
            df[col] = "" if col not in ("ID", "MinutosPlanejados", "MinutosExecutados", "Concluido") else 0
    df["ID"] = pd.to_numeric(df["ID"], errors="coerce").fillna(0).astype(int)
    df["MinutosPlanejados"] = pd.to_numeric(df["MinutosPlanejados"], errors="coerce").fillna(0).astype(int)
    df["MinutosExecutados"] = pd.to_numeric(df["MinutosExecutados"], errors="coerce").fillna(0).astype(int)
    df["Concluido"] = df["Concluido"].apply(lambda v: str(v).strip().lower() in ("true", "1", "sim", "yes"))
    df["Data"] = df["Data"].astype(str)
    df["Horario"] = df["Horario"].astype(str)
    df["Anotacoes"] = df["Anotacoes"].fillna("").astype(str)
    df["DataConclusao"] = df["DataConclusao"].fillna("").astype(str)
    return df[ATIVIDADES_COLUMNS]


def normalize_usuarios(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return default_usuarios_df()
    for col in USUARIOS_COLUMNS:
        if col not in df.columns:
            if col == "MetaSemanal":
                df[col] = 14
            elif col == "IsAdmin":
                df[col] = False
            elif col == "TipoPlano":
                df[col] = "personalizado"
            elif col in ("DisponibilidadeJSON", "MateriaisJSON"):
                df[col] = "[]"
            elif col == "DuracoesPadraoJSON":
                df[col] = "{}"
            else:
                df[col] = ""
    df["MetaSemanal"] = pd.to_numeric(df["MetaSemanal"], errors="coerce").fillna(14).astype(int)
    df["SenhaHash"] = df["SenhaHash"].fillna("").astype(str)
    df["IsAdmin"] = df["IsAdmin"].apply(
        lambda v: v if isinstance(v, bool) else str(v).strip().lower() in ("true", "1", "sim", "yes")
    )
    df["TipoPlano"] = df["TipoPlano"].fillna("personalizado").astype(str)
    df["TipoPlano"] = df["TipoPlano"].replace("", "personalizado")
    df["DisponibilidadeJSON"] = df["DisponibilidadeJSON"].fillna("[]").astype(str).replace("", "[]")
    df["MateriaisJSON"] = df["MateriaisJSON"].fillna("[]").astype(str).replace("", "[]")
    df["DuracoesPadraoJSON"] = df["DuracoesPadraoJSON"].fillna("{}").astype(str).replace("", "{}")
    df = df[USUARIOS_COLUMNS]
    return ensure_admin(df)
