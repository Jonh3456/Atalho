"""CSS customizado do dashboard."""

CUSTOM_CSS = """
<style>
.block-container { padding-top: 2rem; }

.kpi-card {
    border-radius: 22px; padding: 20px; color: white;
    box-shadow: 0 6px 18px rgba(0,0,0,0.08); min-height: 120px;
}
.kpi-card.bg-blue    { background: linear-gradient(135deg, #2563eb, #1d4ed8); }
.kpi-card.bg-violet  { background: linear-gradient(135deg, #8b5cf6, #7c3aed); }
.kpi-card.bg-orange  { background: linear-gradient(135deg, #f97316, #ea580c); }
.kpi-card.bg-emerald { background: linear-gradient(135deg, #10b981, #059669); }
.kpi-card.bg-teal    { background: linear-gradient(135deg, #14b8a6, #0d9488); }
.kpi-icon  { font-size: 26px; margin-bottom: 6px; }
.kpi-label { font-size: 13px; opacity: 0.9; }
.kpi-value { font-size: 28px; font-weight: 900; margin: 2px 0; }
.kpi-sub   { font-size: 12px; opacity: 0.85; }

.progress-track-light { width: 100%; height: 10px; border-radius: 999px; background: #e2e8f0; overflow: hidden; }
.progress-fill-blue { height: 100%; background: #2563eb; border-radius: 999px; }
.progress-track { width: 100%; height: 12px; border-radius: 999px; background: rgba(255,255,255,0.25); overflow: hidden; }
.progress-fill { height: 100%; background: white; border-radius: 999px; }

.mission-card {
    border-radius: 24px; padding: 26px; color: white;
    background: linear-gradient(135deg, #1d4ed8, #7c3aed);
    box-shadow: 0 10px 24px rgba(29,78,216,0.25);
}
.mission-card h2 { margin: 6px 0 14px 0; font-size: 24px; color: #ffffff !important; }
.mission-card p  { margin: 0; color: #ffffff !important; }

.podium-card {
    border-radius: 22px; padding: 22px; color: white; text-align: center;
    box-shadow: 0 8px 20px rgba(0,0,0,0.12);
}

.badge-card {
    border: 1px solid #e2e8f0; border-radius: 20px; padding: 18px;
    background: #f8fafc !important; text-align: left;
}
.badge-card.unlocked { background: #fff7ed !important; border-color: #fdba74 !important; }
.badge-icon {
    width: 46px; height: 46px; border-radius: 16px;
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; background: #e2e8f0 !important; color: #94a3b8 !important;
}
.badge-icon.on { background: #f59e0b !important; color: #ffffff !important; }

.login-hero { text-align: center; padding: 30px 10px 10px 10px; }
.login-hero h1 { font-size: 32px; font-weight: 900; margin-bottom: 4px; }
.login-hero p  { color: #64748b; }

.admin-badge {
    display: inline-block; background: #1e293b; color: white; font-size: 11px;
    font-weight: 800; padding: 3px 10px; border-radius: 999px; margin-left: 8px;
}

.level-card {
    border-radius: 20px; padding: 18px; background: #f8fafc !important; border: 1px solid #e2e8f0;
    display: flex; align-items: center; gap: 14px; overflow: visible;
}
.level-card.current { background: #fff7ed !important; border-color: #fdba74 !important; }
.level-badge {
    width: 44px; height: 44px; min-width: 44px; flex-shrink: 0; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; font-weight: 900; color: #ffffff !important; background: #94a3b8 !important;
}
.level-badge.current { background: #f59e0b !important; }
.level-card > div:last-child {
    min-width: 0; flex: 1 1 auto; overflow-wrap: break-word; word-break: break-word;
}

div[data-testid="stButton"] button { border-radius: 12px; font-weight: 700; }

/* ---------- Barra compacta de estatísticas (topo do app) ---------- */
.mini-stat-bar {
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 20px;
    width: 100%;
    margin-top: 25px;
    padding-right: 8px;
}
.mini-stat {
    display: flex;
    align-items: center;
    gap: 5px;
    background: transparent;
    border: none;
    padding: 0;
    font-weight: 900;
    font-size: 15px;
    box-shadow: none;
}
.mini-stat .icon { font-size: 25px; line-height: 1; }
.mini-stat.stat-fire .value { color: #ff9600; }
.mini-stat.stat-star .value { color: #9b5de5; }
.mini-stat.stat-clock .value { color: #2196f3; }
.mini-stat.stat-percent .value { color: #00a878; }

/* ---------- Calendário estilo Outlook (grade mensal clicável) ---------- */
.cal-weekday { text-align: center; font-size: 11px; font-weight: 800; color: #64748b; padding: 4px 0; }
.cal-chip {
    display: block; font-size: 10px; font-weight: 700; color: white; border-radius: 6px;
    padding: 2px 5px; margin-bottom: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cal-chip.cal-done { opacity: 0.55; text-decoration: line-through; }
.cal-more { font-size: 10px; color: #94a3b8; font-weight: 700; }
.cal-day-btn button { width: 100%; min-height: 34px; border-radius: 8px !important; }
.cal-day-selected button { border: 2px solid #2563eb !important; background: #eff6ff !important; }
.cal-day-today button { border: 2px solid #f59e0b !important; }

/* ---------- Cabeçalho: garante que o texto de datas não seja cortado ---------- */
.eyebrow-label {
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: unset !important;
    line-height: 1.4 !important;
    word-break: normal !important;
    overflow-wrap: break-word !important;
    max-width: 100% !important;
}

/* ---------- Checkbox de "Feito": maior, evidente e com borda azul ---------- */
label:has(> input[aria-label="Concluído"]) {
    display: flex !important; align-items: center !important;
    cursor: pointer;
}
label:has(> input[aria-label="Concluído"]) > span:first-of-type {
    width: 36px !important;
    height: 36px !important;
    min-width: 36px !important;
    border-radius: 9px !important;
    border-width: 3.5px !important;
    border-color: #2563eb !important;
    box-shadow: 0 0 0 1px rgba(37,99,235,0.15);
}
label:has(> input[aria-label="Concluído"]:checked) > span:first-of-type {
    background-color: #2563eb !important;
    border-color: #2563eb !important;
}
.feito-label-right {
    font-size: 14px; font-weight: 800; color: #334155;
    white-space: nowrap; user-select: none; margin: 0;
    display: flex; align-items: center; height: 36px;
}

/* ---------- Materiais de estudo: card do item + botão-link estilizado ---------- */
.material-card {
    border: 1px solid #e2e8f0 !important;
    border-radius: 16px;
    padding: 14px 16px;
    background: #f8fafc !important;
    margin-bottom: 10px;
    color: #0f172a !important;
}

/* Título dos materiais — funciona também no Dark Mode */
.material-card h1,
.material-card h2,
.material-card h3,
.material-card h4,
.material-card h5,
.material-card h6 {
    color: #0f172a !important;
}

/* Texto normal dentro do card */
.material-card p,
.material-card span,
.material-card div {
    color: #334155;
}

/* Metadados */
.material-card .material-meta {
    color: #64748b !important;
}
.material-icon {
    font-size: 20px; margin-right: 6px;
}
.material-meta {
    font-size: 12px; color: #64748b; margin-top: 2px;
}
.material-link-btn {
    display: inline-flex; align-items: center; gap: 6px;
    background: #2563eb; color: #ffffff !important; font-weight: 700;
    font-size: 13px; padding: 8px 14px; border-radius: 10px;
    text-decoration: none !important; border: none;
}
.material-link-btn:hover { background: #1d4ed8; }

/* ---------- RESPONSIVIDADE MOBILE ---------- */
@media (max-width: 640px) {
    .block-container {
        padding: 1rem 0.75rem 2rem 0.75rem !important;
        max-width: 100% !important;
    }
    [data-testid="stAppViewContainer"] > .main {
        width: 100% !important;
    }
    .eyebrow-label {
        font-size: 9px !important;
        letter-spacing: 0.2px !important;
    }
    [data-testid="stMarkdownContainer"] h1 {
        font-size: 22px !important;
        line-height: 1.15 !important;
        margin-bottom: 8px !important;
    }
    [data-testid="stMarkdownContainer"] h2 {
        font-size: 18px !important;
        line-height: 1.2 !important;
    }
    [data-testid="stMarkdownContainer"] h3 {
        font-size: 16px !important;
        line-height: 1.25 !important;
    }
    [data-testid="stMarkdownContainer"] h4,
    [data-testid="stMarkdownContainer"] h5 {
        font-size: 14px !important;
    }
    p {
        font-size: 13px !important;
        line-height: 1.4 !important;
    }
               [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0.6rem !important;
    }
    [data-testid="column"] {
        width: 100% !important;
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }
    .kpi-value { font-size: 20px !important; }
    .kpi-label { font-size: 10px !important; }
    .kpi-icon { font-size: 18px !important; }
    .mission-card {
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
        padding: 14px !important;
        margin-bottom: 10px !important;
    }
    .mission-card h2 {
        font-size: 17px !important;
        line-height: 1.2 !important;
    }
    .podium-card {
        width: 100% !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
    .podium-card div[style*="font-size:34px"] { font-size: 26px !important; }
    .podium-card div[style*="font-size:26px"] { font-size: 20px !important; }
    .login-hero {
        width: 100% !important;
        max-width: 100% !important;
        padding: 20px 15px !important;
        box-sizing: border-box !important;
    }
    .login-hero h1 {
        font-size: 24px !important;
        line-height: 1.15 !important;
    }
    input, textarea, select {
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
    [data-testid="stTextInput"],
    [data-testid="stTextArea"],
    [data-testid="stSelectbox"],
    [data-testid="stNumberInput"] {
        width: 100% !important;
    }
    .stButton { width: 100% !important; }
    .stButton > button {
        width: 100% !important;
        min-height: 42px !important;
        font-size: 13px !important;
        padding: 8px 12px !important;
    }
    .cal-chip {
        font-size: 8px !important;
        padding: 1px 3px !important;
        max-width: 100% !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        white-space: nowrap !important;
    }
    .mini-stat {
        font-size: 18px !important;
        padding: 15px 8px !important;
        gap: 4px !important;
        max-width: 100% !important;
        box-sizing: border-box !important;
    }
    .mini-stat .icon { font-size: 25px !important; }
    img { max-width: 100% !important; height: auto !important; }
    [data-testid="stDataFrame"] {
        width: 100% !important;
        overflow-x: auto !important;
    }
    [data-testid="stExpander"] {
        width: 100% !important;
        box-sizing: border-box !important;
    }
    hr { margin: 12px 0 !important; }
    [data-testid="stVerticalBlock"] { gap: 0.5rem !important; }
    html, body, [data-testid="stAppViewContainer"] {
        max-width: 100% !important;
        overflow-x: hidden !important;
    }
}
</style>
"""
