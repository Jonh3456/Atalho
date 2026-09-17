"""
English Journey — Dashboard interativo de estudo de inglês (6 meses)
Roda no Streamlit, salva os dados em um arquivo Excel versionado no GitHub,
suporta login por usuário/PIN, competição entre pessoas/equipes, calendário
com foco nos próximos estudos, Modo Admin (gerenciar/remover pessoas) e, na
Visão Geral, separa Pendentes/Concluídas com botão de nova atividade.

Cada pessoa tem seu próprio plano de 6 meses, que começa no dia em que ela
CRIA SUA CONTA, e pode ser PERSONALIZADO a partir da disponibilidade (dias/
horários livres), dos materiais de estudo e da duração de cada tarefa —
tudo escolhido no momento do cadastro, com campos de duração editáveis
(botões -/+) diretamente ao lado de cada tarefa/material. A distribuição
dos materiais nos horários livres é feita por empacotamento inteligente:
cada bloco de disponibilidade é preenchido com quantas tarefas couberem
nele (respeitando a duração de cada uma), em vez de 1 material por bloco.
"""
from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import streamlit as st

import data_model as dm
import github_sync
from theme import CUSTOM_CSS

st.set_page_config(page_title="English Journey — Dashboard", page_icon="🎓", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Colunas técnicas (JSON internos) que não devem aparecer nas tabelas de
# "Pessoas cadastradas" (Configurações) nem no Modo Admin — são detalhes de
# implementação usados só para reabrir o editor de perfil.
COLUNAS_TECNICAS_OCULTAS = ["DisponibilidadeJSON", "MateriaisJSON", "DuracoesPadraoJSON"]

# ============================================================
# INICIALIZAÇÃO DE DADOS
# ============================================================

def get_today() -> date:
    return date.today()


def init_data():
    if "dfs" in st.session_state:
        return
    github_mode = github_sync.is_configured()
    st.session_state.github_mode = github_mode
    st.session_state.save_error = None
    st.session_state.last_saved = None

    if github_mode:
        try:
            content, sha = github_sync.fetch_file()
        except Exception as exc:  # noqa: BLE001
            st.session_state.save_error = str(exc)
            content, sha = None, None
        if content:
            raw = dm.bytes_to_workbook(content)
            atividades = dm.normalize_atividades(raw.get("Atividades", dm.empty_atividades_df()))
            usuarios = dm.normalize_usuarios(raw.get("Usuarios", dm.default_usuarios_df()))
        else:
            usuarios = dm.default_usuarios_df()
            atividades = dm.build_template_activities(usuarios.iloc[0]["Usuario"], 1)
            sha = None
        st.session_state.dfs_sha = sha
    else:
        usuarios = dm.default_usuarios_df()
        atividades = dm.build_template_activities(usuarios.iloc[0]["Usuario"], 1)
        st.session_state.dfs_sha = None

    st.session_state.dfs = {"Atividades": atividades, "Usuarios": usuarios}


def _merge_remote_into_session():
    """Antes de salvar, busca o estado mais recente do GitHub e recupera
    para dentro da sessão atual qualquer PESSOA (e suas atividades) que
    tenha sido criada por outra sessão/dispositivo enquanto esta sessão
    estava aberta.

    Por quê: cada sessão do Streamlit mantém sua própria cópia em memória
    dos dados (carregada uma vez, no login). Sem essa mesclagem, se a
    Pessoa A criar uma conta enquanto a Pessoa B já está com o app aberto,
    a próxima vez que B salvar qualquer coisa (ex: marcar uma tarefa),
    B acabaria sobrescrevendo o arquivo inteiro com sua cópia desatualizada
    — apagando a Pessoa A, mesmo que o commit dela apareça no histórico do
    GitHub. Esta função evita esse apagamento silencioso.
    """
    if not st.session_state.get("github_mode"):
        return
    try:
        content, _ = github_sync.fetch_file()
    except Exception:  # noqa: BLE001
        return
    if not content:
        return
    try:
        raw = dm.bytes_to_workbook(content)
    except Exception:  # noqa: BLE001
        return
    remote_usuarios = dm.normalize_usuarios(raw.get("Usuarios", dm.default_usuarios_df()))
    local_usuarios = st.session_state.dfs["Usuarios"]
    faltantes = remote_usuarios[~remote_usuarios["Usuario"].isin(local_usuarios["Usuario"])]
    if faltantes.empty:
        return
    st.session_state.dfs["Usuarios"] = pd.concat([local_usuarios, faltantes], ignore_index=True)
    remote_atividades = dm.normalize_atividades(raw.get("Atividades", dm.empty_atividades_df()))
    local_atividades = st.session_state.dfs["Atividades"]
    nomes_faltantes = set(faltantes["Usuario"])
    recuperadas = remote_atividades[remote_atividades["Usuario"].isin(nomes_faltantes)].copy()
    if not recuperadas.empty:
        max_id_local = int(local_atividades["ID"].max()) if len(local_atividades) else 0
        recuperadas["ID"] = range(max_id_local + 1, max_id_local + 1 + len(recuperadas))
        st.session_state.dfs["Atividades"] = pd.concat([local_atividades, recuperadas], ignore_index=True)


def persist(message: str = "Atualização do dashboard de inglês"):
    if st.session_state.get("github_mode"):
        try:
            _merge_remote_into_session()
            content = dm.workbook_to_bytes(st.session_state.dfs)
            new_sha = github_sync.push_file(content, st.session_state.dfs_sha, message)
            st.session_state.dfs_sha = new_sha
            st.session_state.save_error = None
            st.session_state.last_saved = datetime.now()
        except Exception as exc:  # noqa: BLE001
            st.session_state.save_error = str(exc)
    else:
        st.session_state.last_saved = datetime.now()


def pull_latest():
    if not st.session_state.get("github_mode"):
        return
    try:
        content, sha = github_sync.fetch_file()
        if content:
            raw = dm.bytes_to_workbook(content)
            st.session_state.dfs = {
                "Atividades": dm.normalize_atividades(raw.get("Atividades", dm.empty_atividades_df())),
                "Usuarios": dm.normalize_usuarios(raw.get("Usuarios", dm.default_usuarios_df())),
            }
            st.session_state.dfs_sha = sha
            st.session_state.save_error = None
    except Exception as exc:  # noqa: BLE001
        st.session_state.save_error = str(exc)


init_data()
TODAY = get_today()

# ============================================================
# LOGIN (usuário + senha/PIN)
# ============================================================

def do_login(nome: str, pin: str) -> tuple[bool, str]:
    usuarios = st.session_state.dfs["Usuarios"]
    row = usuarios[usuarios["Usuario"] == nome]
    if row.empty:
        return False, "Usuário não encontrado."
    senha_hash_salva = row.iloc[0]["SenhaHash"]
    if not senha_hash_salva:
        if not pin:
            return False, "Defina um PIN para continuar (primeiro acesso)."
        idx = usuarios.index[usuarios["Usuario"] == nome][0]
        usuarios.at[idx, "SenhaHash"] = dm.hash_password(pin)
        st.session_state.dfs["Usuarios"] = usuarios
        persist(f"Definir PIN inicial de {nome}")
        return True, ""
    if dm.hash_password(pin) == senha_hash_salva:
        return True, ""
    return False, "PIN incorreto."


def _criar_conta(novo_nome, nova_equipe, novo_pin, tipo_plano, nova_meta,
                  disponibilidade_dict, materiais_selecionados, custom_durations=None,
                  material_durations=None):
    usuarios = st.session_state.dfs["Usuarios"]
    atividades = st.session_state.dfs["Atividades"]

    if not novo_nome.strip() or not novo_pin:
        st.error("Informe nome e PIN.")
        return
    if novo_nome in usuarios["Usuario"].tolist():
        st.error("Já existe alguém com esse nome. Escolha outro ou faça login acima.")
        return

    cor = dm.USER_PALETTE[len(usuarios) % len(dm.USER_PALETTE)]
    eh_personalizado = tipo_plano.startswith("🎯")
    novo = pd.DataFrame([{
        "Usuario": novo_nome, "Equipe": nova_equipe, "Cor": cor,
        "MetaSemanal": nova_meta, "SenhaHash": dm.hash_password(novo_pin), "IsAdmin": False,
        "TipoPlano": "personalizado" if eh_personalizado else "padrao",
        "DisponibilidadeJSON": dm.availability_rows_to_json(
            [{"Dia": dm.WEEKDAY_NAMES[d], "Horario": b["horario"], "Minutos": b["minutos"]}
             for d, blocos in disponibilidade_dict.items() for b in blocos]
        ) if eh_personalizado else "[]",
        "MateriaisJSON": dm.materials_to_json(materiais_selecionados, material_durations) if eh_personalizado else "[]",
        "DuracoesPadraoJSON": dm.durations_dict_to_json(custom_durations) if not eh_personalizado else "{}",
    }])
    st.session_state.dfs["Usuarios"] = pd.concat([usuarios, novo], ignore_index=True)

    max_id = int(atividades["ID"].max()) if len(atividades) else 0
    inicio = date.today()
    fim = dm.add_months(inicio, 6)

    if eh_personalizado:
        plano = dm.build_personalized_activities(
            novo_nome, disponibilidade_dict, materiais_selecionados, max_id + 1,
            start_date=inicio, end_date=fim, material_durations=material_durations,
        )
    else:
        plano = dm.build_template_activities(
            novo_nome, max_id + 1, start_date=inicio, end_date=fim,
            custom_durations=custom_durations,
        )

    st.session_state.dfs["Atividades"] = pd.concat([atividades, plano], ignore_index=True)
    st.session_state.pop("materiais_customizados", None)
    persist(f"Criar novo usuário: {novo_nome} ({'personalizado' if eh_personalizado else 'padrão'})")
    st.session_state.auth_user = novo_nome
    st.session_state.flash_new_user_count = len(plano)
    st.session_state.flash_new_user_period = (inicio, fim)
    try:
        st.query_params["u"] = novo_nome
        st.query_params["h"] = dm.hash_password(novo_pin)
    except Exception:  # noqa: BLE001
        pass
    st.rerun()


def login_screen():
    usuarios = st.session_state.dfs["Usuarios"]
    st.markdown(
        "<div class='login-hero'><h1>🎓 English Journey</h1>"
        "<p>Entre para acompanhar sua evolução no inglês</p></div>",
        unsafe_allow_html=True,
    )
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        with st.form("login_form"):
            nomes = usuarios["Usuario"].tolist()
            nome_sel = st.selectbox("Quem é você?", nomes) if nomes else None
            tem_senha = False
            if nome_sel:
                row = usuarios[usuarios["Usuario"] == nome_sel]
                tem_senha = bool(row.iloc[0]["SenhaHash"]) if not row.empty else False
            label_pin = "PIN (4+ dígitos ou senha)" if tem_senha else "Crie um PIN (primeiro acesso)"
            pin = st.text_input(label_pin, type="password")
            entrar = st.form_submit_button("Entrar", width="stretch")
            if entrar:
                if not nome_sel:
                    st.error("Cadastre um usuário primeiro (veja abaixo).")
                else:
                    ok, msg = do_login(nome_sel, pin)
                    if ok:
                        st.session_state.auth_user = nome_sel
                        try:
                            row_login = st.session_state.dfs["Usuarios"]
                            row_login = row_login[row_login["Usuario"] == nome_sel]
                            if not row_login.empty:
                                st.query_params["u"] = nome_sel
                                st.query_params["h"] = row_login.iloc[0]["SenhaHash"]
                        except Exception:  # noqa: BLE001
                            pass
                        st.rerun()
                    else:
                        st.error(msg)

        with st.expander("➕ Sou novo(a) aqui — criar meu usuário"):
            st.caption(
                "Seu cronograma será gerado automaticamente para os próximos 6 meses, "
                f"começando **hoje ({date.today().strftime('%d/%m/%Y')})**."
            )
            novo_nome = st.text_input("Seu nome", key="signup_nome")
            nova_equipe = st.text_input("Equipe", value="Time Fluência", key="signup_equipe")
            novo_pin = st.text_input("Crie um PIN", type="password", key="signup_pin")

            tipo_plano = st.radio(
                "Como você quer montar seu cronograma?",
                ["📋 Usar modelo padrão (English Live + Mairo Vergara)",
                 "🎯 Personalizar (meus horários livres e meus materiais)"],
                key="signup_tipo_plano",
            )

            disponibilidade_dict: dict = {}
            materiais_selecionados: list = []
            custom_durations: dict = {}
            material_durations: dict = {}
            nova_meta = 14
            minutos_semana = 0

            # -----------------------------------------------------------
            # Ramo 1: modelo padrão — cada tarefa do template aparece com
            # seu próprio campo de duração (+/-), sempre visível.
            # -----------------------------------------------------------
            if tipo_plano.startswith("📋"):
                st.markdown("##### ⏱️ Duração de cada tarefa (ajuste com +/- se quiser)")
                for nome_tarefa in dm.list_template_task_names():
                    default_min = dm.template_task_default_duration(nome_tarefa)
                    valor = st.number_input(
                        nome_tarefa, min_value=5, step=5, value=int(default_min),
                        key=f"signup_duracao_padrao_{nome_tarefa}",
                    )
                    custom_durations[nome_tarefa] = int(valor)
                nova_meta = st.number_input("Meta semanal (h)", min_value=1, max_value=60, value=14, key="signup_meta_padrao")

            # -----------------------------------------------------------
            # Ramo 2: personalizado (disponibilidade + materiais + duração,
            # cada material com seu próprio campo +/- sempre visível)
            # -----------------------------------------------------------
            else:
                st.markdown("##### 🗓️ Seus horários livres por dia da semana")
                st.caption(
                    "Adicione uma linha para cada horário livre que você tem (pode repetir o mesmo "
                    "dia quantas vezes precisar). Use o **+** no final da tabela para adicionar mais linhas."
                )
                disponibilidade_editor = st.data_editor(
                    pd.DataFrame(dm.DEFAULT_AVAILABILITY_ROWS),
                    num_rows="dynamic",
                    width="stretch",
                    key="signup_disponibilidade_editor",
                    column_config={
                        "Dia": st.column_config.SelectboxColumn("Dia da semana", options=dm.WEEKDAY_NAMES),
                        "Horario": st.column_config.TextColumn("Horário (HH:MM)"),
                        "Minutos": st.column_config.NumberColumn("Minutos disponíveis", min_value=0, step=5),
                    },
                )
                disponibilidade_dict = dm.availability_rows_to_dict(disponibilidade_editor.to_dict("records"))
                minutos_semana = dm.weekly_minutes_from_availability(disponibilidade_dict)
                st.caption(f"⏱️ Total informado: **{minutos_semana} min/semana** ≈ **{minutos_semana/60:.1f}h/semana**")
                st.info(
                    "💡 A distribuição é inteligente: cada horário livre é preenchido com quantas "
                    "tarefas couberem nele (respeitando a duração de cada material), em vez de um "
                    "material por horário — assim seu tempo livre é aproveitado ao máximo."
                )

                st.markdown("##### 📚 Seus materiais de estudo")
                materiais_catalogo = st.multiselect(
                    "Selecione os materiais que você vai usar (serão distribuídos em rodízio pelos horários acima):",
                    options=list(dm.MATERIAL_CATALOG.keys()),
                    default=["Anki (memorização)", "Mairo Vergara - Lição do dia", "English Live - Conversação em grupo"],
                    key="signup_materiais_catalogo",
                )
                materiais_selecionados = [{"nome": m, "habilidade": dm.MATERIAL_CATALOG[m]} for m in materiais_catalogo]

                with st.expander("➕ Adicionar material personalizado (não está na lista)"):
                    cm1, cm2, cm3, cm4 = st.columns([2, 1.3, 1, 1])
                    custom_nome = cm1.text_input("Nome do material", key="signup_custom_material_nome")
                    custom_habilidade = cm2.selectbox("Habilidade", dm.SKILLS, key="signup_custom_material_skill")
                    custom_minutos = cm3.number_input("Tempo (min)", min_value=5, step=5, value=30, key="signup_custom_material_minutos")
                    if cm4.button("Adicionar", key="signup_btn_add_custom_material", width="stretch"):
                        if "materiais_customizados" not in st.session_state:
                            st.session_state.materiais_customizados = []
                        if custom_nome.strip():
                            st.session_state.materiais_customizados.append({
                                "nome": custom_nome, "habilidade": custom_habilidade, "minutos": int(custom_minutos),
                            })
                            st.success(f"'{custom_nome}' ({custom_minutos} min) adicionado à sua lista!")
                    if st.session_state.get("materiais_customizados"):
                        st.caption("Materiais personalizados adicionados nesta sessão:")
                        for m in st.session_state.materiais_customizados:
                            st.markdown(f"- **{m['nome']}** ({m['habilidade']}, {m.get('minutos', 30)} min)")
                        materiais_selecionados = materiais_selecionados + [
                            {"nome": m["nome"], "habilidade": m["habilidade"]}
                            for m in st.session_state.materiais_customizados
                        ]

                if materiais_selecionados:
                    st.markdown("##### ⏱️ Duração de cada material (ajuste com +/- se quiser)")
                    custom_defaults = {
                        m["nome"]: m.get("minutos", dm.get_default_duration(m["nome"]))
                        for m in st.session_state.get("materiais_customizados", [])
                    }
                    nomes_unicos = []
                    for m in materiais_selecionados:
                        if m["nome"] not in nomes_unicos:
                            nomes_unicos.append(m["nome"])
                    for nome_material in nomes_unicos:
                        default_min = custom_defaults.get(nome_material, dm.get_default_duration(nome_material))
                        valor = st.number_input(
                            nome_material, min_value=5, step=5, value=int(default_min),
                            key=f"signup_duracao_material_{nome_material}",
                        )
                        material_durations[nome_material] = int(valor)

                nova_meta_sugerida = round(minutos_semana / 60) if minutos_semana else 14
                nova_meta = st.number_input("Meta semanal (h)", min_value=1, max_value=80,
                                             value=int(nova_meta_sugerida), key="signup_meta_personalizada")

            if st.button("Criar usuário e entrar", type="primary", width="stretch", key="signup_btn_criar"):
                _criar_conta(novo_nome, nova_equipe, novo_pin, tipo_plano, nova_meta,
                             disponibilidade_dict, materiais_selecionados,
                             custom_durations=custom_durations, material_durations=material_durations)


def _sync_query_params_login():
    """Tenta restaurar o login a partir dos parâmetros da URL (query params),
    para que um simples F5/atualização de página não desconecte o usuário.

    Não guarda o PIN em texto puro: usa o mesmo hash já salvo em SenhaHash,
    comparando com o valor presente na URL. Isso é equivalente, em termos de
    segurança, a um token de sessão simples — sem precisar criar colunas
    novas nem gravações extras no GitHub a cada login."""
    if st.session_state.get("auth_user"):
        return
    try:
        qp_user = st.query_params.get("u")
        qp_hash = st.query_params.get("h")
    except Exception:  # noqa: BLE001
        return
    if not qp_user or not qp_hash:
        return
    usuarios_qp = st.session_state.dfs["Usuarios"]
    row_qp = usuarios_qp[usuarios_qp["Usuario"] == qp_user]
    if row_qp.empty:
        return
    senha_hash_salva_qp = row_qp.iloc[0]["SenhaHash"]
    if senha_hash_salva_qp and senha_hash_salva_qp == qp_hash:
        st.session_state.auth_user = qp_user


if "auth_user" not in st.session_state:
    st.session_state.auth_user = None

_sync_query_params_login()

if st.session_state.auth_user is None:
    login_screen()
    st.stop()

current_user = st.session_state.auth_user
atividades: pd.DataFrame = st.session_state.dfs["Atividades"]
usuarios: pd.DataFrame = st.session_state.dfs["Usuarios"]

if "IsAdmin" not in usuarios.columns:
    usuarios = dm.normalize_usuarios(usuarios)
    st.session_state.dfs["Usuarios"] = usuarios
    persist("Migrar esquema de usuários (adicionar coluna IsAdmin)")

if current_user not in usuarios["Usuario"].tolist():
    st.session_state.auth_user = None
    st.rerun()

# ============================================================
# HELPERS DE CÁLCULO
# ============================================================

def week_bounds(d: date):
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end


def user_date_range(user: str) -> tuple[date, date]:
    df = atividades[atividades["Usuario"] == user]
    if df.empty:
        return TODAY, dm.add_months(TODAY, 6)
    datas = pd.to_datetime(df["Data"], errors="coerce").dt.date.dropna()
    if datas.empty:
        return TODAY, dm.add_months(TODAY, 6)
    return datas.min(), datas.max()


def is_admin(user: str) -> bool:
    row = usuarios[usuarios["Usuario"] == user]
    if row.empty:
        return False
    return bool(row.iloc[0].get("IsAdmin", False))


def compute_stats(user: str) -> dict:
    df = atividades[atividades["Usuario"] == user].copy()
    if df.empty:
        return dict(
            actual_hours=0.0, planned_hours=0.0, xp=0, level=1, stars=0,
            completion_rate=0.0, streak=0, week_hours=0.0, weekly_goal=14,
            completed=df, week_df=df,
        )
    df["minutos_reais"] = df.apply(
        lambda r: r["MinutosExecutados"] if r["Concluido"] and r["MinutosExecutados"] > 0
        else (r["MinutosPlanejados"] if r["Concluido"] else 0), axis=1
    )
    completed = df[df["Concluido"]]
    actual_hours = completed["minutos_reais"].sum() / 60
    planned_hours = df["MinutosPlanejados"].sum() / 60
    xp = round(completed["minutos_reais"].sum() / 5)
    level = xp // 500 + 1
    stars = min(5, xp // 1000)
    completion_rate = (len(completed) / len(df) * 100) if len(df) else 0.0

    ws, we = week_bounds(TODAY)
    df["data_dt"] = pd.to_datetime(df["Data"], errors="coerce").dt.date
    week_df = df[(df["data_dt"] >= ws) & (df["data_dt"] <= we)]
    week_hours = week_df[week_df["Concluido"]]["minutos_reais"].sum() / 60

    dates_done = sorted(set(completed["Data"]), reverse=True)
    streak = 0
    if dates_done:
        streak = 1
        prev = datetime.strptime(dates_done[0], "%Y-%m-%d").date()
        for ds in dates_done[1:]:
            cur = datetime.strptime(ds, "%Y-%m-%d").date()
            if (prev - cur).days == 1:
                streak += 1
                prev = cur
            else:
                break

    weekly_goal = 14
    urow = usuarios[usuarios["Usuario"] == user]
    if len(urow):
        weekly_goal = int(urow.iloc[0]["MetaSemanal"])

    return dict(
        actual_hours=actual_hours, planned_hours=planned_hours, xp=xp, level=level,
        stars=stars, completion_rate=completion_rate, streak=streak, week_hours=week_hours,
        weekly_goal=weekly_goal, completed=completed, week_df=week_df,
    )


def kpi_card(col, icon, label, value, sub, css_class):
    col.markdown(
        f"""<div class="kpi-card {css_class}">
                <div class="kpi-icon">{icon}</div>
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-sub">{sub}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def toggle_activity(activity_id: int):
    idx = atividades.index[atividades["ID"] == activity_id]
    if len(idx) == 0:
        return
    i = idx[0]
    new_val = not bool(atividades.at[i, "Concluido"])
    atividades.at[i, "Concluido"] = new_val
    if new_val:
        if not atividades.at[i, "MinutosExecutados"]:
            atividades.at[i, "MinutosExecutados"] = atividades.at[i, "MinutosPlanejados"]
        atividades.at[i, "DataConclusao"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    else:
        atividades.at[i, "DataConclusao"] = ""
    st.session_state.dfs["Atividades"] = atividades
    persist(f"Marcar atividade {activity_id} como {'concluída' if new_val else 'pendente'}")
    if new_val:
        st.toast("Tarefa concluída", icon="✅")


def add_activity(user: str, data_str: str, horario: str, tarefa: str, habilidade: str,
                  modalidade: str, minutos: int):
    max_id = int(atividades["ID"].max()) if len(atividades) else 0
    nova = pd.DataFrame([{
        "ID": max_id + 1, "Usuario": user, "Data": data_str, "Horario": horario,
        "Tarefa": tarefa, "Habilidade": habilidade, "Modalidade": modalidade,
        "MinutosPlanejados": minutos, "MinutosExecutados": 0, "Concluido": False,
        "Anotacoes": "", "DataConclusao": "",
    }])
    st.session_state.dfs["Atividades"] = pd.concat([atividades, nova], ignore_index=True)
    persist(f"Adicionar atividade: {tarefa} ({user})")
    st.toast("Nova Atividade atribuída", icon="🆕")


def add_recurring_activities(user: str, data_inicial: date, horario: str, tarefa: str,
                              habilidade: str, modalidade: str, minutos: int,
                              frequencia: str, repetir_ate: date):
    """Cria várias ocorrências da mesma atividade, respeitando a frequência
    escolhida (Diariamente/Semanalmente/Mensalmente), até a data limite."""
    datas = dm.generate_recurring_dates(data_inicial, repetir_ate, frequencia)
    max_id = int(atividades["ID"].max()) if len(atividades) else 0
    novas = []
    for i, d in enumerate(datas):
        novas.append({
            "ID": max_id + i + 1, "Usuario": user, "Data": d.isoformat(), "Horario": horario,
            "Tarefa": tarefa, "Habilidade": habilidade, "Modalidade": modalidade,
            "MinutosPlanejados": minutos, "MinutosExecutados": 0, "Concluido": False,
            "Anotacoes": "", "DataConclusao": "",
        })
    novas_df = pd.DataFrame(novas, columns=dm.ATIVIDADES_COLUMNS)
    st.session_state.dfs["Atividades"] = pd.concat([atividades, novas_df], ignore_index=True)
    persist(f"Adicionar atividade recorrente ({frequencia}): {tarefa} ({user}) — {len(datas)} ocorrência(s)")
    st.toast(f"Nova Atividade atribuída ({len(datas)} ocorrências)", icon="🆕")


def delete_activity(activity_id: int):
    idx = atividades.index[atividades["ID"] == activity_id]
    if len(idx) == 0:
        return
    st.session_state.dfs["Atividades"] = atividades.drop(idx)
    persist(f"Excluir atividade {activity_id}")


stats = compute_stats(current_user)
user_start, user_end = user_date_range(current_user)

# ============================================================
# SIDEBAR (botão "Sair" fica no final, após tudo mais)
# ============================================================
with st.sidebar:
    st.markdown("### 🎓 English Journey")
    admin_tag = " <span class='admin-badge'>ADMIN</span>" if is_admin(current_user) else ""
    st.markdown(f"Logado como **{current_user}**{admin_tag}", unsafe_allow_html=True)
    st.divider()

    nav_options = ["🎯 Visão geral", "📅 Calendário", "📊 Evolução", "🏆 Competição", "🥇 Conquistas", "⚙️ Configurações"]
    if is_admin(current_user):
        nav_options.append("🛡️ Modo Admin")

    page = st.radio("Navegação", nav_options, label_visibility="collapsed")

    st.divider()
    if st.session_state.get("github_mode"):
        st.success("🔗 Conectado ao GitHub")
        if st.session_state.get("last_saved"):
            st.caption(f"Último salvamento: {st.session_state.last_saved.strftime('%d/%m %H:%M')}")
        if st.button("🔄 Buscar atualizações da equipe", width="stretch"):
            pull_latest()
            st.rerun()
    else:
        st.warning("⚠️ GitHub não configurado — dados salvos apenas nesta sessão local.")
    if st.session_state.get("save_error"):
        st.error(f"Erro ao sincronizar: {st.session_state.save_error}")

    st.divider()
    if st.button("🚪 Sair", width="stretch"):
        st.session_state.auth_user = None
        try:
            st.query_params.clear()
        except Exception:  # noqa: BLE001
            pass
        st.rerun()

    st.markdown(
        f"<p style='margin-top:14px;margin-bottom:2px;font-size:12px;font-weight:800;"
        f"color:#94a3b8;text-transform:uppercase;letter-spacing:0.5px;'>Sua jornada:</p>"
        f"<p class='eyebrow-label' style='color:#2563eb;font-weight:800;font-size:13px;margin:0;'>"
        f"{user_start.strftime('%d/%m/%Y')} a {user_end.strftime('%d/%m/%Y')} • {current_user}</p>"
        f"<p style='font-size:11px;color:#94a3b8;margin-top:10px;'>Criado por Darlei D.</p>",
        unsafe_allow_html=True,
    )

# ============================================================
# CABEÇALHO
# ============================================================
st.markdown(
    f"""<div class="mini-stat-bar">
            <div class="mini-stat stat-fire"><span class="icon">🔥</span><span class="value">{stats['streak']}</span></div>
            <div class="mini-stat stat-star"><span class="icon">⭐</span><span class="value">{stats['xp']}XP</span></div>
            <div class="mini-stat stat-clock"><span class="icon">🕐</span><span class="value">{stats['week_hours']:.1f}h</span></div>
            <div class="mini-stat stat-percent"><span class="icon">📊</span><span class="value">{stats['completion_rate']:.0f}%</span></div>
        </div>""",
    unsafe_allow_html=True,
)

if st.session_state.get("flash_new_user_count"):
    ini, fim = st.session_state.get("flash_new_user_period", (user_start, user_end))
    st.success(
        f"✅ Cronograma criado automaticamente para **{current_user}**: "
        f"{st.session_state.flash_new_user_count} atividades geradas para os 6 meses "
        f"({ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')})."
    )
    st.session_state.flash_new_user_count = None

header_left, header_right = st.columns([3, 1])
with header_left:
    st.markdown("## Sua evolução no inglês")
    st.caption("Consistência hoje, fluência amanhã.")
with header_right:
    st.write("")
    st.write("")
    if st.button("➕ Nova atividade", width="stretch", type="primary", key="btn_toggle_nova_atividade"):
        st.session_state.show_new_activity_form = not st.session_state.get("show_new_activity_form", False)

if st.session_state.get("show_new_activity_form"):
    with st.container(border=True):
        st.markdown("##### ➕ Adicionar nova atividade")
        c1, c2 = st.columns(2)
        nova_data = c1.date_input("Data", value=TODAY, key="nova_atividade_data")
        novo_horario = c2.text_input("Horário", value="18:00", key="nova_atividade_horario")
        nova_tarefa = st.text_input("Tarefa", key="nova_atividade_tarefa")
        c3, c4, c5 = st.columns(3)
        nova_habilidade = c3.selectbox("Habilidade", dm.SKILLS, key="nova_atividade_habilidade")
        nova_modalidade = c4.selectbox("Modalidade", dm.MODALITIES, key="nova_atividade_modalidade")
        novos_minutos = c5.number_input("Minutos", min_value=5, step=5, value=30, key="nova_atividade_minutos")
        nova_frequencia = st.selectbox(
            "Recorrência", dm.FREQUENCIAS_RECORRENCIA, key="nova_atividade_frequencia",
            help="Marque se essa atividade deve se repetir automaticamente (diariamente, semanalmente ou mensalmente).",
        )
        nova_repetir_ate = None
        if nova_frequencia != "Não recorrente":
            nova_repetir_ate = st.date_input(
                "Repetir até", value=user_end, min_value=nova_data, key="nova_atividade_repetir_ate",
            )
        col_ok, col_cancel = st.columns(2)
        if col_ok.button("💾 Salvar", width="stretch", type="primary", key="btn_salvar_nova_atividade"):
            if not nova_tarefa.strip():
                st.error("Informe o nome da tarefa.")
            else:
                if nova_frequencia == "Não recorrente":
                    add_activity(current_user, nova_data.isoformat(), novo_horario, nova_tarefa,
                                  nova_habilidade, nova_modalidade, novos_minutos)
                else:
                    add_recurring_activities(
                        current_user, nova_data, novo_horario, nova_tarefa, nova_habilidade,
                        nova_modalidade, novos_minutos, nova_frequencia, nova_repetir_ate,
                    )
                st.session_state.show_new_activity_form = False
                st.success("Atividade adicionada!")
                st.rerun()
        if col_cancel.button("Cancelar", width="stretch", key="btn_cancelar_nova_atividade"):
            st.session_state.show_new_activity_form = False
            st.rerun()

# ============================================================
# PÁGINA: VISÃO GERAL
# ============================================================
if page == "🎯 Visão geral":
    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, "⏱️", "Horas executadas", f"{stats['actual_hours']:.1f}h", f"{stats['week_hours']:.1f}h nesta semana", "bg-blue")
    kpi_card(c2, "⭐", "Pontos e nível", f"{stats['xp']} XP", f"Nível {stats['level']} • {stats['stars']}/5 estrelas", "bg-violet")
    kpi_card(c3, "🔥", "Sequência atual", f"{stats['streak']} dias", "Continue para não perder a sequência", "bg-orange")
    kpi_card(c4, "✅", "Taxa de conclusão", f"{stats['completion_rate']:.0f}%", f"{len(stats['completed'])} tarefas concluídas", "bg-emerald")

    st.write("")
    left, right = st.columns([2, 1])

    with left:
        st.markdown("#### 📋 Minhas tarefas pendentes")
        modo_visao = st.radio(
            "Ver pendências:", ["📆 Dia", "📅 Semana"], horizontal=True,
            key="modo_visao_pendencias",
        )

        df_pessoa = atividades[atividades["Usuario"] == current_user].copy()
        df_pessoa["data_dt"] = pd.to_datetime(df_pessoa["Data"], errors="coerce").dt.date

        if modo_visao == "📅 Semana":
            if "semana_offset" not in st.session_state:
                st.session_state.semana_offset = 0
            nav1, nav2, nav3 = st.columns([1, 3, 1])
            if nav1.button("◀", key="semana_prev"):
                st.session_state.semana_offset -= 1
            if nav3.button("▶", key="semana_next"):
                st.session_state.semana_offset += 1
            base_day = TODAY + timedelta(weeks=st.session_state.semana_offset)
            ws, we = week_bounds(base_day)
            nav2.markdown(f"<p style='text-align:center;font-weight:700;'>{ws.strftime('%d/%m')} a {we.strftime('%d/%m')}</p>", unsafe_allow_html=True)
            periodo_df = df_pessoa[(df_pessoa["data_dt"] >= ws) & (df_pessoa["data_dt"] <= we)]
            periodo_horas_meta = stats["weekly_goal"]
            periodo_label = "semana"
        else:
            if "dia_offset" not in st.session_state:
                st.session_state.dia_offset = 0
            nav1, nav2, nav3 = st.columns([1, 3, 1])
            if nav1.button("◀", key="dia_prev"):
                st.session_state.dia_offset -= 1
            if nav3.button("▶", key="dia_next"):
                st.session_state.dia_offset += 1
            sel_day = TODAY + timedelta(days=st.session_state.dia_offset)
            nav2.markdown(f"<p style='text-align:center;font-weight:700;'>{sel_day.strftime('%A, %d/%m').capitalize()}</p>", unsafe_allow_html=True)
            periodo_df = df_pessoa[df_pessoa["data_dt"] == sel_day]
            periodo_horas_meta = round(stats["weekly_goal"] / 7, 1)
            periodo_label = "dia"

        periodo_df = periodo_df.sort_values(["Data", "Horario"])
        pendentes_df = periodo_df[~periodo_df["Concluido"]]
        concluidas_periodo_df = periodo_df[periodo_df["Concluido"]]

        horas_feitas_periodo = concluidas_periodo_df.apply(
            lambda r: (r["MinutosExecutados"] or r["MinutosPlanejados"]), axis=1
        ).sum() / 60 if len(concluidas_periodo_df) else 0.0
        pct = min(100, (horas_feitas_periodo / periodo_horas_meta * 100) if periodo_horas_meta else 0)
        st.markdown(
            f"<div class='progress-track-light'><div class='progress-fill-blue' style='width:{pct}%;'></div></div>"
            f"<p style='text-align:right;font-size:12px;color:#64748b;'>{horas_feitas_periodo:.1f} / {periodo_horas_meta}h ({periodo_label})</p>",
            unsafe_allow_html=True,
        )

        if pendentes_df.empty:
            st.success(f"🎉 Nenhuma pendência para {'esta semana' if modo_visao == '📅 Semana' else 'este dia'}! Bom trabalho.")
        for _, row in pendentes_df.iterrows():
            data_row = pd.to_datetime(row["Data"], errors="coerce")
            atrasada = data_row.date() < TODAY if pd.notna(data_row) else False
            data_label = data_row.strftime("%d/%m") if pd.notna(data_row) else row["Data"]
            cols = st.columns([0.56, 0.15, 0.15, 0.14])
            titulo_cor = "#dc2626" if atrasada else "inherit"
            data_cor = "#dc2626" if atrasada else "#2563eb"
            alerta_atraso = " <span style='font-size:11px;color:#dc2626;font-weight:800;'>⚠️ ATRASADA</span>" if atrasada else ""
            cols[0].markdown(
                f"<div style='display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;'>"
                f"<span style='font-size:20px;font-weight:900;color:{data_cor};min-width:52px;'>{data_label}</span>"
                f"<span style='font-weight:700;color:{titulo_cor};'>{row['Tarefa']}</span>{alerta_atraso}"
                f"</div>"
                f"<span style='font-size:12px;color:#64748b;margin-left:62px;'>{row['Horario']} • {row['MinutosPlanejados']} min • {row['Habilidade']} • {row['Modalidade']}</span>",
                unsafe_allow_html=True,
            )
            with cols[1].popover("✏️ Editar"):
                novo_nome_tarefa = st.text_input("Nome da tarefa", value=row["Tarefa"], key=f"nome_{row['ID']}")
                novos_planejados = st.number_input("Minutos planejados (duração da tarefa)", min_value=5, step=5, value=int(row["MinutosPlanejados"]), key=f"planejados_{row['ID']}")
                novos_min = st.number_input("Minutos executados", min_value=0, step=5, value=int(row["MinutosExecutados"]), key=f"min_{row['ID']}")
                notas = st.text_area("Anotações", value=row["Anotacoes"], key=f"notas_{row['ID']}")
                if st.button("Salvar", key=f"save_{row['ID']}"):
                    idx = atividades.index[atividades["ID"] == row["ID"]][0]
                    atividades.at[idx, "Tarefa"] = novo_nome_tarefa.strip() or row["Tarefa"]
                    atividades.at[idx, "MinutosPlanejados"] = int(novos_planejados)
                    atividades.at[idx, "MinutosExecutados"] = novos_min
                    atividades.at[idx, "Anotacoes"] = notas
                    st.session_state.dfs["Atividades"] = atividades
                    persist("Editar atividade")
                    st.rerun()
            if cols[2].button("🗑️", key=f"del_{row['ID']}", help="Excluir tarefa"):
                delete_activity(row["ID"])
                st.rerun()
            with cols[3]:
                sub_chk, sub_lbl = st.columns([0.45, 0.55])
                with sub_chk:
                    st.checkbox(
                        "Concluído", value=False, key=f"chk_{row['ID']}",
                        on_change=toggle_activity, args=(row["ID"],), label_visibility="collapsed",
                    )
                with sub_lbl:
                    st.markdown("<p class='feito-label-right'>Feito</p>", unsafe_allow_html=True)

        if not concluidas_periodo_df.empty:
            with st.expander(f"✅ Concluídas neste {periodo_label} ({len(concluidas_periodo_df)}) — arquivadas da tela principal"):
                for _, row in concluidas_periodo_df.iterrows():
                    cols = st.columns([0.68, 0.12, 0.20])
                    cols[0].markdown(
                        f"<span style='text-decoration:line-through;color:#94a3b8;'>{row['Tarefa']}</span> "
                        f"<span style='font-size:12px;color:#64748b;'>— {row['Data']} • {row['Horario']}</span>",
                        unsafe_allow_html=True,
                    )
                    if cols[1].button("🗑️", key=f"del_done_{row['ID']}", help="Excluir tarefa"):
                        delete_activity(row["ID"])
                        st.rerun()
                    with cols[2]:
                        sub_chk2, sub_lbl2 = st.columns([0.45, 0.55])
                        with sub_chk2:
                            st.checkbox(
                                "Concluído", value=True, key=f"chk_done_{row['ID']}",
                                on_change=toggle_activity, args=(row["ID"],), label_visibility="collapsed",
                            )
                        with sub_lbl2:
                            st.markdown("<p class='feito-label-right'>Feito</p>", unsafe_allow_html=True)

        # -------- ⚠️ Atrasados: sanfona com TODAS as pendências vencidas --------
        atrasados_geral_df = df_pessoa[
            (~df_pessoa["Concluido"]) & (df_pessoa["data_dt"] < TODAY)
        ].sort_values(["Data", "Horario"])
        if not atrasados_geral_df.empty:
            with st.expander(f"⚠️ Atrasados ({len(atrasados_geral_df)}) - verifique os dias"):
                for _, row in atrasados_geral_df.iterrows():
                    data_fmt = pd.to_datetime(row["Data"], errors="coerce")
                    data_label_atrasado = data_fmt.strftime("%d/%m") if pd.notna(data_fmt) else row["Data"]
                    st.markdown(
                        f"<span style='font-weight:800;color:#dc2626;'>{data_label_atrasado}</span> — {row['Tarefa']}",
                        unsafe_allow_html=True,
                    )
        else:
            st.success("🎉 Nenhuma pendência para este dia! Bom trabalho.")

    with right:
        pct_week = min(100, (stats["week_hours"] / stats["weekly_goal"] * 100) if stats["weekly_goal"] else 0)
        st.markdown(
            f"""<div class="mission-card">
                    <p>🎯 Missão semanal</p>
                    <h2>Atingir {stats['weekly_goal']} horas</h2>
                    <div class="progress-track">
                        <div class="progress-fill" style="width:{pct_week}%;"></div>
                    </div>
                    <p style="margin-top:10px;">{stats['week_hours']:.1f}h realizadas •
                        {max(0, stats['weekly_goal']-stats['week_hours']):.1f}h restantes</p>
                    <p style="margin-top:14px;font-size:13px;">🎁 Recompensa: 2 estrelas e 250 XP bônus</p>
                </div>""",
            unsafe_allow_html=True,
        )
        st.write("")
        st.markdown("##### Equilíbrio de habilidades")
        if len(stats["completed"]):
            skill_data = stats["completed"].groupby("Habilidade")["minutos_reais"].sum().reset_index()
            skill_data["Horas"] = (skill_data["minutos_reais"] / 60).round(1)
        else:
            skill_data = pd.DataFrame(columns=["Habilidade", "minutos_reais", "Horas"])
        if skill_data.empty or skill_data["Horas"].sum() == 0:
            st.info("Marque atividades como concluídas para ver o gráfico.")
        else:
            chart = alt.Chart(skill_data).mark_arc(innerRadius=60).encode(
                theta="Horas:Q",
                color=alt.Color("Habilidade:N", scale=alt.Scale(domain=list(dm.SKILL_COLORS.keys()), range=list(dm.SKILL_COLORS.values())), legend=alt.Legend(orient="bottom")),
                tooltip=["Habilidade", "Horas"],
            ).properties(height=260)
            st.altair_chart(chart, width="stretch")

# ============================================================
# PÁGINA: CALENDÁRIO
# ============================================================
elif page == "📅 Calendário":
    df_user = atividades[atividades["Usuario"] == current_user].copy()
    df_user["data_dt"] = pd.to_datetime(df_user["Data"], errors="coerce").dt.date

    st.markdown("##### ⏭️ Próximos estudos")
    proximos = df_user[(df_user["data_dt"] >= TODAY) & (~df_user["Concluido"])].sort_values(["Data", "Horario"]).head(5)
    if proximos.empty:
        st.info("Nenhuma atividade futura pendente encontrada.")
    else:
        for _, row in proximos.iterrows():
            st.markdown(
                f"<div style='padding:10px 14px;border:1px solid #e2e8f0;border-radius:14px;margin-bottom:8px;'>"
                f"<b>{row['Tarefa']}</b><br>"
                f"<span style='font-size:12px;color:#64748b;'>{row['Data']} • {row['Horario']} • {row['MinutosPlanejados']} min • {row['Habilidade']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ============================================================
    # 📆 CALENDÁRIO MENSAL ESTILO OUTLOOK (1 mês por vez, clicável).
    # O painel do dia selecionado aparece ACIMA da grade do mês.
    # ============================================================
    st.markdown("##### 📆 Calendário mensal")
    st.caption("Veja toda a sua programação de estudos organizada por dia. Clique em um dia para ver e editar as tarefas daquele dia — navegue entre os meses para ver como está organizado.")

    if "cal_grid_month" not in st.session_state:
        st.session_state.cal_grid_month = date(TODAY.year, TODAY.month, 1)
    if "cal_selected_day" not in st.session_state:
        st.session_state.cal_selected_day = TODAY

    # -------- Painel do dia selecionado (ACIMA do calendário) --------
    dia_sel = st.session_state.cal_selected_day
    st.markdown(f"###### 🗓️ Tarefas de {dia_sel.strftime('%d/%m/%Y')}")
    dia_sel_mask = (atividades["Usuario"] == current_user) & (pd.to_datetime(atividades["Data"], errors="coerce").dt.date == dia_sel)
    dia_sel_df = atividades[dia_sel_mask].sort_values("Horario").copy()

    if dia_sel_df.empty:
        st.info("Nenhuma tarefa cadastrada para este dia.")
    else:
        dia_editado = st.data_editor(
            dia_sel_df.drop(columns=["ID", "Usuario", "DataConclusao", "Data"]),
            num_rows="dynamic",
            width="stretch",
            key=f"cal_day_editor_{dia_sel.isoformat()}",
            column_config={
                "Horario": st.column_config.TextColumn("Horário"),
                "Tarefa": st.column_config.TextColumn("Tarefa"),
                "Habilidade": st.column_config.SelectboxColumn("Habilidade", options=dm.SKILLS),
                "Modalidade": st.column_config.SelectboxColumn("Modalidade", options=dm.MODALITIES),
                "MinutosPlanejados": st.column_config.NumberColumn("Min. planejados", min_value=0, step=5),
                "MinutosExecutados": st.column_config.NumberColumn("Min. executados", min_value=0, step=5),
                "Concluido": st.column_config.CheckboxColumn("Feito?"),
                "Anotacoes": st.column_config.TextColumn("Anotações"),
            },
        )
        if st.button("💾 Salvar tarefas deste dia", type="primary", key=f"cal_day_save_{dia_sel.isoformat()}"):
            others = atividades[~dia_sel_mask].copy()
            max_id = int(atividades["ID"].max()) if len(atividades) else 0
            new_rows = []
            for _, r in dia_editado.iterrows():
                new_rows.append({
                    "ID": max_id + len(new_rows) + 1,
                    "Usuario": current_user,
                    "Data": dia_sel.isoformat(),
                    "Horario": str(r["Horario"]),
                    "Tarefa": r["Tarefa"],
                    "Habilidade": r["Habilidade"],
                    "Modalidade": r["Modalidade"],
                    "MinutosPlanejados": int(r["MinutosPlanejados"] or 0),
                    "MinutosExecutados": int(r["MinutosExecutados"] or 0),
                    "Concluido": bool(r["Concluido"]),
                    "Anotacoes": r.get("Anotacoes", "") or "",
                    "DataConclusao": datetime.now().strftime("%Y-%m-%d %H:%M") if bool(r["Concluido"]) else "",
                })
            new_day_df = pd.DataFrame(new_rows, columns=dm.ATIVIDADES_COLUMNS)
            st.session_state.dfs["Atividades"] = pd.concat([others, new_day_df], ignore_index=True)
            persist(f"Atualizar tarefas de {dia_sel.isoformat()} — {current_user}")
            st.success("Tarefas do dia atualizadas!")
            st.rerun()

    st.write("")
    nav_prev, nav_label, nav_next = st.columns([1, 4, 1])
    if nav_prev.button("◀ Mês anterior", key="cal_grid_prev", width="stretch"):
        base = st.session_state.cal_grid_month
        prev_month_last_day = base - timedelta(days=1)
        st.session_state.cal_grid_month = date(prev_month_last_day.year, prev_month_last_day.month, 1)
    if nav_next.button("Próximo mês ▶", key="cal_grid_next", width="stretch"):
        base = st.session_state.cal_grid_month
        next_month_first_day = dm.add_months(base, 1)
        st.session_state.cal_grid_month = date(next_month_first_day.year, next_month_first_day.month, 1)
    grid_month = st.session_state.cal_grid_month
    nav_label.markdown(
        f"<p style='text-align:center;font-weight:800;font-size:16px;margin-top:6px;'>{grid_month.strftime('%B/%Y').capitalize()}</p>",
        unsafe_allow_html=True,
    )

    primeiro_dia_mes = grid_month.replace(day=1)
    dias_no_mes = (dm.add_months(primeiro_dia_mes, 1) - timedelta(days=1)).day
    offset_inicial = primeiro_dia_mes.weekday()  # 0=Segunda
    total_celulas = offset_inicial + dias_no_mes
    total_celulas = ((total_celulas + 6) // 7) * 7  # completa a última semana
    semanas = total_celulas // 7

    weekday_cols = st.columns(7)
    for wd_col, wd_nome in zip(weekday_cols, ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]):
        wd_col.markdown(f"<div class='cal-weekday'>{wd_nome}</div>", unsafe_allow_html=True)

    dia_atual_num = 1
    for semana_idx in range(semanas):
        semana_cols = st.columns(7)
        for dow in range(7):
            celula_idx = semana_idx * 7 + dow
            with semana_cols[dow]:
                if celula_idx < offset_inicial or dia_atual_num > dias_no_mes:
                    st.write("")
                else:
                    dia_data = date(grid_month.year, grid_month.month, dia_atual_num)
                    atividades_do_dia = df_user[df_user["data_dt"] == dia_data].sort_values("Horario")
                    n_tarefas = len(atividades_do_dia)
                    n_feitas = int(atividades_do_dia["Concluido"].sum()) if n_tarefas else 0
                    label_btn = f"{dia_atual_num}"
                    if n_tarefas:
                        label_btn += f" ({n_feitas}/{n_tarefas})"
                    css_extra = "cal-day-selected" if dia_data == st.session_state.cal_selected_day else ("cal-day-today" if dia_data == TODAY else "")
                    if css_extra:
                        st.markdown(f"<div class='{css_extra}'>", unsafe_allow_html=True)
                    if st.button(label_btn, key=f"cal_day_btn_{dia_data.isoformat()}", width="stretch"):
                        st.session_state.cal_selected_day = dia_data
                        st.rerun()
                    if css_extra:
                        st.markdown("</div>", unsafe_allow_html=True)
                    chips_html = ""
                    MAX_CHIPS = 3
                    for _, arow in atividades_do_dia.head(MAX_CHIPS).iterrows():
                        cor_chip = dm.SKILL_COLORS.get(arow["Habilidade"], "#64748b")
                        done_class = " cal-done" if arow["Concluido"] else ""
                        chips_html += (
                            f"<span class='cal-chip{done_class}' style='background:{cor_chip};' "
                            f"title='{arow['Tarefa']} • {arow['Horario']}'>{arow['Horario']} {arow['Tarefa']}</span>"
                        )
                    if n_tarefas > MAX_CHIPS:
                        chips_html += f"<span class='cal-more'>+{n_tarefas - MAX_CHIPS} mais</span>"
                    if chips_html:
                        st.markdown(chips_html, unsafe_allow_html=True)
                    dia_atual_num += 1

    legenda_html = " &nbsp; ".join(
        f"<span style='display:inline-block;width:10px;height:10px;border-radius:3px;background:{cor};margin-right:4px;'></span>{hab}"
        for hab, cor in dm.SKILL_COLORS.items()
    )
    st.markdown(f"<p style='font-size:11px;color:#64748b;margin-top:8px;'>{legenda_html}</p>", unsafe_allow_html=True)

    st.markdown("##### 🔥 Heatmap de estudo (todo o período)")
    heat = df_user.groupby("data_dt").agg(total=("ID", "count"), feitas=("Concluido", "sum")).reset_index()
    heat["data_dt"] = pd.to_datetime(heat["data_dt"])
    all_days = pd.DataFrame({"data_dt": pd.date_range(user_start, user_end)})
    heat = all_days.merge(heat, on="data_dt", how="left").fillna(0)
    heat["semana"] = ((heat["data_dt"] - pd.Timestamp(user_start)).dt.days // 7)
    heat["dia_semana"] = heat["data_dt"].dt.strftime("%a")
    heat["ratio"] = heat.apply(lambda r: (r["feitas"] / r["total"]) if r["total"] > 0 else 0, axis=1)
    dias_ordem = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    heat_chart = alt.Chart(heat).mark_rect(cornerRadius=3).encode(
        x=alt.X("semana:O", title="Semana", axis=alt.Axis(labels=False, ticks=False)),
        y=alt.Y("dia_semana:N", sort=dias_ordem, title=""),
        color=alt.Color("ratio:Q", scale=alt.Scale(scheme="blues", domain=[0, 1]), legend=None),
        tooltip=[alt.Tooltip("data_dt:T", title="Data"), alt.Tooltip("feitas:Q", title="Concluídas"), alt.Tooltip("total:Q", title="Total")],
    ).properties(height=200)
    st.altair_chart(heat_chart, width="stretch")

    st.markdown("##### 📝 Editar atividades do mês")
    months = pd.date_range(user_start.replace(day=1), user_end, freq="MS").to_list()
    if not months or months[0].date() > user_start:
        months = [pd.Timestamp(user_start.replace(day=1))] + months
    month_labels = [m.strftime("%B/%Y").capitalize() for m in months]
    default_idx = 0
    for i, m in enumerate(months):
        if m.year == TODAY.year and m.month == TODAY.month:
            default_idx = i
            break
    sel_label = st.select_slider("Mês", options=month_labels, value=month_labels[default_idx])
    sel_month = months[month_labels.index(sel_label)]

    month_start = sel_month.date()
    next_month = (sel_month + pd.offsets.MonthBegin(1)).date()
    mask = (atividades["Usuario"] == current_user) & (pd.to_datetime(atividades["Data"]).dt.date >= month_start) & (pd.to_datetime(atividades["Data"]).dt.date < next_month)
    month_df = atividades[mask].sort_values(["Data", "Horario"]).copy()

    edited = st.data_editor(
        month_df.drop(columns=["ID", "Usuario", "DataConclusao"]),
        num_rows="dynamic",
        width="stretch",
        key=f"editor_{current_user}_{sel_label}",
        column_config={
            "Data": st.column_config.TextColumn("Data (AAAA-MM-DD)"),
            "Horario": st.column_config.TextColumn("Horário"),
            "Habilidade": st.column_config.SelectboxColumn("Habilidade", options=dm.SKILLS),
            "Modalidade": st.column_config.SelectboxColumn("Modalidade", options=dm.MODALITIES),
            "MinutosPlanejados": st.column_config.NumberColumn("Min. planejados", min_value=0, step=5),
            "MinutosExecutados": st.column_config.NumberColumn("Min. executados", min_value=0, step=5),
            "Concluido": st.column_config.CheckboxColumn("Feito?"),
            "Anotacoes": st.column_config.TextColumn("Anotações"),
        },
    )

    if st.button("💾 Salvar alterações deste mês", type="primary"):
        others = atividades[~mask].copy()
        max_id = int(atividades["ID"].max()) if len(atividades) else 0
        new_rows = []
        for _, r in edited.iterrows():
            new_rows.append({
                "ID": max_id + len(new_rows) + 1 if pd.isna(r.get("ID")) else r.get("ID"),
                "Usuario": current_user,
                "Data": str(r["Data"]),
                "Horario": str(r["Horario"]),
                "Tarefa": r["Tarefa"],
                "Habilidade": r["Habilidade"],
                "Modalidade": r["Modalidade"],
                "MinutosPlanejados": int(r["MinutosPlanejados"] or 0),
                "MinutosExecutados": int(r["MinutosExecutados"] or 0),
                "Concluido": bool(r["Concluido"]),
                "Anotacoes": r.get("Anotacoes", "") or "",
                "DataConclusao": datetime.now().strftime("%Y-%m-%d %H:%M") if bool(r["Concluido"]) else "",
            })
        seen_ids = set(others["ID"].tolist())
        next_id = max_id + 1
        for row in new_rows:
            if row["ID"] in seen_ids or not row["ID"]:
                row["ID"] = next_id
                next_id += 1
            seen_ids.add(row["ID"])
        new_month_df = pd.DataFrame(new_rows, columns=dm.ATIVIDADES_COLUMNS)
        st.session_state.dfs["Atividades"] = pd.concat([others, new_month_df], ignore_index=True)
        persist(f"Atualizar atividades de {sel_label} — {current_user}")
        st.success("Alterações salvas!")
        st.rerun()

# ============================================================
# PÁGINA: EVOLUÇÃO
# ============================================================
elif page == "📊 Evolução":
    f1, f2, f3 = st.columns(3)
    skill_f = f1.selectbox("Habilidade", ["Todas"] + dm.SKILLS)
    mod_f = f2.selectbox("Modalidade", ["Todas"] + dm.MODALITIES)
    status_f = f3.selectbox("Status", ["Todos", "Concluídos", "Pendentes"])

    df = atividades[atividades["Usuario"] == current_user].copy()
    if skill_f != "Todas":
        df = df[df["Habilidade"] == skill_f]
    if mod_f != "Todas":
        df = df[df["Modalidade"] == mod_f]
    if status_f == "Concluídos":
        df = df[df["Concluido"]]
    elif status_f == "Pendentes":
        df = df[~df["Concluido"]]

    df["data_dt"] = pd.to_datetime(df["Data"], errors="coerce")
    df["minutos_reais"] = df.apply(lambda r: (r["MinutosExecutados"] or r["MinutosPlanejados"]) if r["Concluido"] else 0, axis=1)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### Horas nas últimas 8 semanas")
        weeks = []
        for i in range(8):
            wstart = user_start + timedelta(days=7 * i)
            wend = wstart + timedelta(days=6)
            sub = df[(df["data_dt"].dt.date >= wstart) & (df["data_dt"].dt.date <= wend)]
            weeks.append({"Semana": f"S{i+1}", "Horas": round(sub["minutos_reais"].sum() / 60, 1), "Tipo": "Executado"})
            weeks.append({"Semana": f"S{i+1}", "Horas": stats["weekly_goal"], "Tipo": "Meta"})
        wdf = pd.DataFrame(weeks)
        chart = alt.Chart(wdf).mark_bar().encode(
            x=alt.X("Semana:N"),
            y=alt.Y("Horas:Q"),
            color=alt.Color("Tipo:N", scale=alt.Scale(domain=["Executado", "Meta"], range=["#2563eb", "#cbd5e1"])),
            xOffset="Tipo:N",
            tooltip=["Semana", "Tipo", "Horas"],
        ).properties(height=300)
        st.altair_chart(chart, width="stretch")

    with col2:
        st.markdown("##### Evolução mensal")
        month_rows = []
        cursor = pd.Timestamp(user_start)
        for _ in range(6):
            mend = cursor + pd.offsets.MonthEnd(0)
            sub = df[(df["data_dt"] >= cursor) & (df["data_dt"] <= mend)]
            month_rows.append({"Mes": cursor.strftime("%b/%y"), "Horas": round(sub["minutos_reais"].sum() / 60, 1)})
            cursor = cursor + pd.offsets.MonthBegin(1)
        mdf = pd.DataFrame(month_rows)
        line = alt.Chart(mdf).mark_area(line={"color": "#8b5cf6", "strokeWidth": 3}, color=alt.Gradient(
            gradient="linear",
            stops=[alt.GradientStop(color="#8b5cf6", offset=0), alt.GradientStop(color="#ffffff", offset=1)],
            x1=1, x2=1, y1=1, y2=0,
        )).encode(x=alt.X("Mes:N", sort=None), y="Horas:Q", tooltip=["Mes", "Horas"]).properties(height=300)
        st.altair_chart(line, width="stretch")

    # ============================================================
    # 📊 Horas por material: planejadas vs. realizadas (colunas agrupadas)
    # ============================================================
    st.write("")
    st.markdown("##### Horas por material: planejadas x realizadas")
    st.caption("Quantas horas de cada material estão no calendário (planejadas) versus quanto já foi efetivamente realizado.")
    df_material_base = atividades[atividades["Usuario"] == current_user].copy()
    if skill_f != "Todas":
        df_material_base = df_material_base[df_material_base["Habilidade"] == skill_f]
    if mod_f != "Todas":
        df_material_base = df_material_base[df_material_base["Modalidade"] == mod_f]
    if df_material_base.empty:
        st.info("Nenhuma atividade encontrada para montar o gráfico por material.")
    else:
        planejado_por_material = df_material_base.groupby("Tarefa")["MinutosPlanejados"].sum() / 60
        df_material_base["minutos_realizados"] = df_material_base.apply(
            lambda r: (r["MinutosExecutados"] or r["MinutosPlanejados"]) if r["Concluido"] else 0, axis=1
        )
        realizado_por_material = df_material_base.groupby("Tarefa")["minutos_realizados"].sum() / 60
        materiais_rows = []
        for material_nome in planejado_por_material.index:
            materiais_rows.append({"Material": material_nome, "Horas": round(planejado_por_material[material_nome], 1), "Tipo": "Planejadas"})
            materiais_rows.append({"Material": material_nome, "Horas": round(realizado_por_material.get(material_nome, 0.0), 1), "Tipo": "Realizadas"})
        materiais_df = pd.DataFrame(materiais_rows)
        maior_nome_material = max((len(str(m)) for m in planejado_por_material.index), default=10)
        materiais_chart = alt.Chart(materiais_df).mark_bar().encode(
            y=alt.Y("Material:N", sort="-x", title="", axis=alt.Axis(labelLimit=200, labelPadding=8)),
            x=alt.X("Horas:Q"),
            color=alt.Color("Tipo:N", scale=alt.Scale(domain=["Planejadas", "Realizadas"], range=["#cbd5e1", "#2563eb"])),
            yOffset="Tipo:N",
            tooltip=["Material", "Tipo", "Horas"],
        ).properties(
            height=max(160, 60 * planejado_por_material.shape[0]),
            padding={"left": min(320, max(120, maior_nome_material * 6)), "top": 5, "right": 5, "bottom": 5},
        )
        st.altair_chart(materiais_chart, width="stretch")

# ============================================================
# PÁGINA: COMPETIÇÃO
# ============================================================
elif page == "🏆 Competição":
    st.markdown("#### Ranking geral")
    rows = []
    for _, u in usuarios.iterrows():
        s = compute_stats(u["Usuario"])
        rows.append({
            "Usuario": u["Usuario"], "Equipe": u["Equipe"], "Cor": u["Cor"],
            "XP": s["xp"], "Horas": round(s["actual_hours"], 1), "Sequencia": s["streak"], "Estrelas": s["stars"],
        })
    rank_df = pd.DataFrame(rows).sort_values("XP", ascending=False).reset_index(drop=True)

    medalhas = ["🥇", "🥈", "🥉"]
    cols = st.columns(min(3, max(1, len(rank_df))))
    for i, (_, r) in enumerate(rank_df.head(3).iterrows()):
        with cols[i]:
            st.markdown(
                f"""<div class="podium-card" style="background:{r['Cor']};">
                        <div style="font-size:34px;">{medalhas[i] if i < 3 else '🎖️'}</div>
                        <div style="font-size:20px;font-weight:900;margin-top:6px;">{r['Usuario']}</div>
                        <div style="font-size:13px;opacity:.9;">{r['Equipe']}</div>
                        <div style="font-size:26px;font-weight:900;margin-top:10px;">{r['XP']} XP</div>
                        <div style="font-size:12px;opacity:.9;">{r['Horas']}h • {'⭐'*int(r['Estrelas']) or '—'}</div>
                    </div>""",
                unsafe_allow_html=True,
            )

    st.write("")
    st.markdown("##### Comparativo de XP entre todos")
    bar = alt.Chart(rank_df).mark_bar(cornerRadiusEnd=8).encode(
        x=alt.X("XP:Q"),
        y=alt.Y("Usuario:N", sort="-x"),
        color=alt.Color("Usuario:N", scale=alt.Scale(domain=rank_df["Usuario"].tolist(), range=rank_df["Cor"].tolist()), legend=None),
        tooltip=["Usuario", "Equipe", "XP", "Horas"],
    ).properties(height=max(120, 46 * len(rank_df)))
    st.altair_chart(bar, width="stretch")

    st.write("")
    st.markdown("##### 🏅 Times")
    team_df = rank_df.groupby("Equipe").agg(XP=("XP", "sum"), Horas=("Horas", "sum"), Integrantes=("Usuario", "count")).reset_index().sort_values("XP", ascending=False)
    tcols = st.columns(min(3, max(1, len(team_df))))
    for i, (_, t) in enumerate(team_df.iterrows()):
        with tcols[i % len(tcols)]:
            kpi_card(st, "👥", t["Equipe"], f"{t['XP']} XP", f"{t['Horas']:.1f}h • {t['Integrantes']} pessoa(s)", ["bg-blue", "bg-violet", "bg-teal"][i % 3])

    st.write("")
    st.markdown("##### 📈 Corrida de horas (acumulado)")
    lines = []
    for _, u in usuarios.iterrows():
        udf = atividades[(atividades["Usuario"] == u["Usuario"]) & (atividades["Concluido"])].copy()
        udf["data_dt"] = pd.to_datetime(udf["Data"], errors="coerce")
        udf["minutos_reais"] = udf.apply(lambda r: r["MinutosExecutados"] or r["MinutosPlanejados"], axis=1)
        daily = udf.groupby("data_dt")["minutos_reais"].sum().sort_index().cumsum() / 60
        for d, v in daily.items():
            lines.append({"Data": d, "HorasAcumuladas": v, "Usuario": u["Usuario"], "Cor": u["Cor"]})
    if lines:
        race_df = pd.DataFrame(lines)
        race_chart = alt.Chart(race_df).mark_line(point=True, strokeWidth=3).encode(
            x="Data:T", y="HorasAcumuladas:Q",
            color=alt.Color("Usuario:N", scale=alt.Scale(domain=usuarios["Usuario"].tolist(), range=usuarios["Cor"].tolist())),
            tooltip=["Usuario", "Data", "HorasAcumuladas"],
        ).properties(height=320)
        st.altair_chart(race_chart, width="stretch")
    else:
        st.info("Assim que alguém concluir atividades, a corrida de horas aparece aqui.")

# ============================================================
# PÁGINA: CONQUISTAS
# ============================================================
elif page == "🥇 Conquistas":
    quem = st.selectbox("Ver conquistas de:", usuarios["Usuario"].tolist(), index=usuarios["Usuario"].tolist().index(current_user))
    s = compute_stats(quem)
    completed = s["completed"]
    speaking_done = len(completed[completed["Habilidade"] == "Speaking"]) if len(completed) else 0
    listening_hours = (completed[completed["Habilidade"] == "Listening"]["minutos_reais"].sum() / 60) if len(completed) else 0
    dias_unicos = completed["Data"].nunique() if len(completed) else 0

    st.markdown(
        f"""<div class="mission-card" style="background:linear-gradient(135deg,#f59e0b,#ea580c);">
                <p>🏅 Nível de {quem}</p>
                <h2>Nível {s['level']}: {dm.level_name(s['level'])}</h2>
                <p style="margin-top:8px;">{s['xp']} XP acumulados • {s['stars']}/5 estrelas</p>
            </div>""",
        unsafe_allow_html=True,
    )
    st.write("")

    achievements = [
        ("Primeiros passos", "Concluir a primeira atividade", len(completed) >= 1, "+50 XP"),
        ("Semana consistente", "Estudar em 7 dias diferentes", dias_unicos >= 7, "⭐ 1 estrela"),
        ("Falante corajoso", "Completar 10 sessões de Speaking", speaking_done >= 10, "+200 XP"),
        ("Ouvido treinado", "Completar 20 horas de Listening", listening_hours >= 20, "⭐ 1 estrela"),
        ("Meta semanal", "Executar a meta em uma semana", s["week_hours"] >= s["weekly_goal"], "⭐⭐ 2 estrelas"),
        ("Fluency Champion", "Concluir 80% do plano de 6 meses", s["completion_rate"] >= 80, "👑 Troféu final"),
    ]
    cols = st.columns(3)
    for i, (title, desc, ok, reward) in enumerate(achievements):
        with cols[i % 3]:
            st.markdown(
                f"""<div class="badge-card {'unlocked' if ok else ''}">
                        <div class="badge-icon {'on' if ok else ''}">🏆</div>
                        <div style="font-weight:900;margin-top:10px;color:#0f172a;">{title}</div>
                        <div style="font-size:13px;color:#64748b;margin-top:4px;">{desc}</div>
                        <div style="font-weight:800;color:#f59e0b;margin-top:10px;">{'Desbloqueado ✓' if ok else reward}</div>
                    </div>""",
                unsafe_allow_html=True,
            )
            st.write("")

    # ============================================================
    # 🏆 Níveis a alcançar
    # ============================================================
    st.divider()
    st.markdown("#### 🏆 Níveis")
    st.caption("Sua trilha de progresso — cada nível é alcançado a cada 500 XP acumulados.")
    nivel_atual = s["level"]
    total_niveis_exibidos = max(len(dm.LEVEL_NAMES), nivel_atual + 2)
    lvl_cols = st.columns(2)
    for lvl in range(1, total_niveis_exibidos + 1):
        minimo, _ = dm.level_xp_range(lvl)
        eh_atual = lvl == nivel_atual
        alcancado = lvl <= nivel_atual
        badge_class = "current" if eh_atual else ""
        card_class = "current" if eh_atual else ""
        status_txt = "Nível atual" if eh_atual else ("Alcançado ✓" if alcancado else f"a partir de {minimo} XP")
        with lvl_cols[(lvl - 1) % 2]:
            st.markdown(
                f"""<div class="level-card {card_class}">
                        <div class="level-badge {badge_class}">{lvl}</div>
                        <div>
                            <div style="font-weight:900;color:#0f172a;">Nível {lvl}: {dm.level_name(lvl)}</div>
                            <div style="font-size:12px;color:#64748b;">{status_txt}</div>
                        </div>
                    </div>""",
                unsafe_allow_html=True,
            )
            st.write("")

# ============================================================
# PÁGINA: CONFIGURAÇÕES
# ============================================================
elif page == "⚙️ Configurações":
    st.markdown("#### Metas pessoais")
    urow_idx = usuarios.index[usuarios["Usuario"] == current_user][0]
    novo_goal = st.number_input("Meta semanal de horas", min_value=1, max_value=60, value=int(usuarios.at[urow_idx, "MetaSemanal"]))
    if st.button("Salvar meta"):
        usuarios.at[urow_idx, "MetaSemanal"] = novo_goal
        st.session_state.dfs["Usuarios"] = usuarios
        persist("Atualizar meta semanal")
        st.success("Meta atualizada!")
        st.rerun()

    st.divider()
    st.markdown("#### 👥 Pessoas cadastradas")
    colunas_exibir = [c for c in usuarios.columns if c not in (["SenhaHash"] + COLUNAS_TECNICAS_OCULTAS)]
    st.dataframe(usuarios[colunas_exibir], width="stretch", hide_index=True)
    st.caption("Novas pessoas criam sua própria conta (com PIN) na tela de login, clicando em **'Sou novo(a) aqui'**.")

    st.divider()
    st.markdown("#### ✏️ Editar meu perfil de estudo")
    st.caption(
        "Adicione ou remova materiais, ajuste o tempo de cada um e altere seus horários "
        "livres. Ao clicar em **Reorganizar meus estudos**, o app relê seus novos parâmetros, "
        "**não altera** o que já foi concluído (pontos e aulas realizadas ficam intactos), limpa "
        "o calendário a partir de **hoje** e redistribui tudo com as novas configurações."
    )
    with st.expander("Abrir editor de perfil"):
        urow_perfil = usuarios[usuarios["Usuario"] == current_user].iloc[0]
        tipo_plano_salvo = urow_perfil.get("TipoPlano", "personalizado") or "personalizado"
        idx_tipo_salvo = 1 if tipo_plano_salvo == "personalizado" else 0
        tipo_plano_perfil = st.radio(
            "Como você quer montar seu cronograma?",
            ["📋 Usar modelo padrão (English Live + Mairo Vergara)",
             "🎯 Personalizar (meus horários livres e meus materiais)"],
            index=idx_tipo_salvo, key="perfil_tipo_plano",
        )

        disponibilidade_dict_perfil: dict = {}
        materiais_selecionados_perfil: list = []
        custom_durations_perfil: dict = {}
        material_durations_perfil: dict = {}

        if tipo_plano_perfil.startswith("📋"):
            st.markdown("##### ⏱️ Duração de cada tarefa (ajuste com +/- se quiser)")
            duracoes_salvas = dm.durations_dict_from_json(urow_perfil.get("DuracoesPadraoJSON", "{}"))
            for nome_tarefa in dm.list_template_task_names():
                default_min = duracoes_salvas.get(nome_tarefa, dm.template_task_default_duration(nome_tarefa))
                valor = st.number_input(
                    nome_tarefa, min_value=5, step=5, value=int(default_min),
                    key=f"perfil_duracao_padrao_{nome_tarefa}",
                )
                custom_durations_perfil[nome_tarefa] = int(valor)
        else:
            st.markdown("##### 🗓️ Seus horários livres por dia da semana")
            disponibilidade_salva = dm.availability_rows_from_json(urow_perfil.get("DisponibilidadeJSON", "[]"))
            disponibilidade_editor_perfil = st.data_editor(
                pd.DataFrame(disponibilidade_salva or dm.DEFAULT_AVAILABILITY_ROWS),
                num_rows="dynamic", width="stretch", key="perfil_disponibilidade_editor",
                column_config={
                    "Dia": st.column_config.SelectboxColumn("Dia da semana", options=dm.WEEKDAY_NAMES),
                    "Horario": st.column_config.TextColumn("Horário (HH:MM)"),
                    "Minutos": st.column_config.NumberColumn("Minutos disponíveis", min_value=0, step=5),
                },
            )
            disponibilidade_dict_perfil = dm.availability_rows_to_dict(disponibilidade_editor_perfil.to_dict("records"))
            minutos_semana_perfil = dm.weekly_minutes_from_availability(disponibilidade_dict_perfil)
            st.caption(f"⏱️ Total informado: **{minutos_semana_perfil} min/semana** ≈ **{minutos_semana_perfil/60:.1f}h/semana**")

            st.markdown("##### 📚 Seus materiais de estudo")
            materiais_salvos = dm.materials_from_json(urow_perfil.get("MateriaisJSON", "[]"))
            nomes_salvos = [m["nome"] for m in materiais_salvos]
            durations_salvas_perfil = {m["nome"]: m.get("minutos", dm.get_default_duration(m["nome"])) for m in materiais_salvos}
            materiais_catalogo_perfil = st.multiselect(
                "Selecione os materiais que você vai usar (serão distribuídos em rodízio pelos horários acima):",
                options=list(dm.MATERIAL_CATALOG.keys()),
                default=[m for m in nomes_salvos if m in dm.MATERIAL_CATALOG] or
                        ["Anki (memorização)", "Mairo Vergara - Lição do dia", "English Live - Conversação em grupo"],
                key="perfil_materiais_catalogo",
            )
            materiais_selecionados_perfil = [{"nome": m, "habilidade": dm.MATERIAL_CATALOG[m]} for m in materiais_catalogo_perfil]

            with st.expander("➕ Adicionar material personalizado (não está na lista)"):
                cm1, cm2, cm3, cm4 = st.columns([2, 1.3, 1, 1])
                custom_nome_p = cm1.text_input("Nome do material", key="perfil_custom_material_nome")
                custom_habilidade_p = cm2.selectbox("Habilidade", dm.SKILLS, key="perfil_custom_material_skill")
                custom_minutos_p = cm3.number_input("Tempo (min)", min_value=5, step=5, value=30, key="perfil_custom_material_minutos")
                if cm4.button("Adicionar", key="perfil_btn_add_custom_material", width="stretch"):
                    if "perfil_materiais_customizados" not in st.session_state:
                        st.session_state.perfil_materiais_customizados = []
                    if custom_nome_p.strip():
                        st.session_state.perfil_materiais_customizados.append({
                            "nome": custom_nome_p, "habilidade": custom_habilidade_p, "minutos": int(custom_minutos_p),
                        })
                        st.success(f"'{custom_nome_p}' ({custom_minutos_p} min) adicionado à sua lista!")
                if st.session_state.get("perfil_materiais_customizados"):
                    st.caption("Materiais personalizados adicionados nesta sessão:")
                    for m in st.session_state.perfil_materiais_customizados:
                        st.markdown(f"- **{m['nome']}** ({m['habilidade']}, {m.get('minutos', 30)} min)")
                    materiais_selecionados_perfil = materiais_selecionados_perfil + [
                        {"nome": m["nome"], "habilidade": m["habilidade"]}
                        for m in st.session_state.perfil_materiais_customizados
                    ]

            if materiais_selecionados_perfil:
                st.markdown("##### ⏱️ Duração de cada material (ajuste com +/- se quiser)")
                custom_defaults_p = {
                    m["nome"]: m.get("minutos", dm.get_default_duration(m["nome"]))
                    for m in st.session_state.get("perfil_materiais_customizados", [])
                }
                nomes_unicos_p = []
                for m in materiais_selecionados_perfil:
                    if m["nome"] not in nomes_unicos_p:
                        nomes_unicos_p.append(m["nome"])
                for nome_material in nomes_unicos_p:
                    default_min = custom_defaults_p.get(
                        nome_material, durations_salvas_perfil.get(nome_material, dm.get_default_duration(nome_material))
                    )
                    valor = st.number_input(
                        nome_material, min_value=5, step=5, value=int(default_min),
                        key=f"perfil_duracao_material_{nome_material}",
                    )
                    material_durations_perfil[nome_material] = int(valor)

        st.divider()
        if st.button("🔄 Reorganizar meus estudos", type="primary", width="stretch", key="perfil_btn_reorganizar"):
            eh_personalizado_perfil = tipo_plano_perfil.startswith("🎯")
            if eh_personalizado_perfil and not materiais_selecionados_perfil:
                st.error("Selecione ao menos 1 material de estudo antes de reorganizar.")
            else:
                urow_idx_perfil = usuarios.index[usuarios["Usuario"] == current_user][0]
                usuarios.at[urow_idx_perfil, "TipoPlano"] = "personalizado" if eh_personalizado_perfil else "padrao"
                usuarios.at[urow_idx_perfil, "DisponibilidadeJSON"] = dm.availability_rows_to_json(
                    [{"Dia": dm.WEEKDAY_NAMES[d], "Horario": b["horario"], "Minutos": b["minutos"]}
                     for d, blocos in disponibilidade_dict_perfil.items() for b in blocos]
                ) if eh_personalizado_perfil else "[]"
                usuarios.at[urow_idx_perfil, "MateriaisJSON"] = dm.materials_to_json(
                    materiais_selecionados_perfil, material_durations_perfil
                ) if eh_personalizado_perfil else "[]"
                usuarios.at[urow_idx_perfil, "DuracoesPadraoJSON"] = dm.durations_dict_to_json(
                    custom_durations_perfil
                ) if not eh_personalizado_perfil else "{}"
                st.session_state.dfs["Usuarios"] = usuarios

                # Preserva TUDO que já foi concluído e tudo no passado (antes de hoje).
                # Limpa apenas as pendências de hoje em diante, para redistribuir com
                # os novos parâmetros — sem tocar em pontuação/histórico já feito.
                mask_limpar = (
                    (atividades["Usuario"] == current_user)
                    & (pd.to_datetime(atividades["Data"], errors="coerce").dt.date >= TODAY)
                    & (~atividades["Concluido"])
                )
                atividades_mantidas = atividades[~mask_limpar].copy()
                max_id_perfil = int(atividades["ID"].max()) if len(atividades) else 0
                fim_periodo_perfil = user_end if user_end > TODAY else dm.add_months(TODAY, 6)

                if eh_personalizado_perfil:
                    novo_plano_perfil = dm.build_personalized_activities(
                        current_user, disponibilidade_dict_perfil, materiais_selecionados_perfil,
                        max_id_perfil + 1, start_date=TODAY, end_date=fim_periodo_perfil,
                        material_durations=material_durations_perfil,
                    )
                else:
                    novo_plano_perfil = dm.build_template_activities(
                        current_user, max_id_perfil + 1, start_date=TODAY, end_date=fim_periodo_perfil,
                        custom_durations=custom_durations_perfil,
                    )

                st.session_state.dfs["Atividades"] = pd.concat([atividades_mantidas, novo_plano_perfil], ignore_index=True)
                st.session_state.pop("perfil_materiais_customizados", None)
                persist(f"Reorganizar estudos de {current_user} (perfil atualizado)")
                st.success("Perfil atualizado e estudos reorganizados! Seu histórico e pontuação continuam intactos.")
                st.rerun()

    st.divider()
    st.markdown("#### 🔐 Alterar minha senha (PIN)")
    st.caption("Troque o PIN usado para entrar no seu usuário. Você precisa informar o PIN atual para confirmar a troca.")
    with st.form("form_trocar_senha"):
        pin_atual_form = st.text_input("PIN atual", type="password", key="trocar_senha_atual")
        pin_novo_form = st.text_input("Novo PIN", type="password", key="trocar_senha_novo")
        pin_novo_confirma_form = st.text_input("Confirme o novo PIN", type="password", key="trocar_senha_confirma")
        submit_senha = st.form_submit_button("Salvar nova senha", type="primary")
        if submit_senha:
            urow_senha = usuarios[usuarios["Usuario"] == current_user].iloc[0]
            senha_hash_atual = urow_senha["SenhaHash"]
            if senha_hash_atual and dm.hash_password(pin_atual_form) != senha_hash_atual:
                st.error("PIN atual incorreto.")
            elif not pin_novo_form:
                st.error("Informe o novo PIN.")
            elif pin_novo_form != pin_novo_confirma_form:
                st.error("A confirmação não confere com o novo PIN.")
            elif pin_novo_form == pin_atual_form:
                st.warning("O novo PIN deve ser diferente do atual.")
            else:
                idx_senha = usuarios.index[usuarios["Usuario"] == current_user][0]
                novo_hash_senha = dm.hash_password(pin_novo_form)
                usuarios.at[idx_senha, "SenhaHash"] = novo_hash_senha
                st.session_state.dfs["Usuarios"] = usuarios
                persist(f"Alterar senha de {current_user}")
                try:
                    st.query_params["u"] = current_user
                    st.query_params["h"] = novo_hash_senha
                except Exception:  # noqa: BLE001
                    pass
                st.success("Senha atualizada com sucesso!")
                st.rerun()

    st.divider()
    st.markdown("#### 💾 Backup e restauração")
    col_a, col_b = st.columns(2)
    with col_a:
        backup_bytes = dm.workbook_to_bytes(st.session_state.dfs)
        st.download_button("⬇️ Baixar backup (.xlsx)", data=backup_bytes, file_name="estudo_ingles_backup.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    with col_b:
        if st.button("↺ Restaurar plano padrão de " + current_user + " (a partir de hoje)", width="stretch"):
            others = atividades[atividades["Usuario"] != current_user]
            max_id = int(others["ID"].max()) if len(others) else 0
            novo_plano = dm.build_template_activities(
                current_user, max_id + 1, start_date=TODAY, end_date=dm.add_months(TODAY, 6),
            )
            st.session_state.dfs["Atividades"] = pd.concat([others, novo_plano], ignore_index=True)
            persist(f"Restaurar plano padrão de {current_user}")
            st.success("Plano restaurado!")
            st.rerun()

    st.write("")
    df_atrasadas_config = atividades[
        (atividades["Usuario"] == current_user)
        & (~atividades["Concluido"])
        & (pd.to_datetime(atividades["Data"], errors="coerce").dt.date < TODAY)
    ]
    if not df_atrasadas_config.empty:
        st.warning(f"Você tem {len(df_atrasadas_config)} tarefa(s) pendente(s) atrasada(s).")
    if st.button("🔁 Colocar dias vencidos em dia (reorganizar calendário)", width="stretch"):
        pendentes_mask = (atividades["Usuario"] == current_user) & (~atividades["Concluido"])
        pendentes_datas = pd.to_datetime(atividades.loc[pendentes_mask, "Data"], errors="coerce").dt.date
        atrasadas_datas = pendentes_datas[pendentes_datas < TODAY]
        if atrasadas_datas.empty:
            st.info("Você já está em dia! Nenhuma tarefa pendente está atrasada.")
        else:
            delta_dias = (TODAY - atrasadas_datas.min()).days
            novas_datas = (pendentes_datas + timedelta(days=delta_dias)).apply(lambda d: d.isoformat())
            atividades.loc[pendentes_mask, "Data"] = novas_datas
            st.session_state.dfs["Atividades"] = atividades
            persist(f"Reorganizar dias vencidos de {current_user} (+{delta_dias} dias nas pendências)")
            st.success(f"Calendário reorganizado! Suas tarefas pendentes foram adiantadas em {delta_dias} dia(s). O que já foi concluído não foi alterado.")
            st.rerun()

    st.divider()
    st.markdown("#### 🔗 Conexão com o GitHub")
    if st.session_state.get("github_mode"):
        st.success("Conectado — todas as alterações são salvas automaticamente como commits no repositório configurado.")
    else:
        st.info(
            "Configure `GITHUB_TOKEN`, `GITHUB_REPO`, `GITHUB_BRANCH` e `GITHUB_FILE_PATH` em "
            "`.streamlit/secrets.toml` (local) ou em *Settings → Secrets* no Streamlit Community Cloud "
            "para habilitar o salvamento permanente e o acesso multi-dispositivo."
        )
    with st.expander("🔍 Diagnóstico da conexão"):
        st.json(github_sync.get_diagnostics())

# ============================================================
# PÁGINA: MODO ADMIN
# ============================================================
elif page == "🛡️ Modo Admin":
    if not is_admin(current_user):
        st.error("Você não tem permissão de administrador.")
        st.stop()

    st.markdown("#### 🛡️ Painel do Administrador")
    st.caption("Gerencie as pessoas cadastradas no English Journey.")

    colunas_exibir_admin = [c for c in usuarios.columns if c not in (["SenhaHash"] + COLUNAS_TECNICAS_OCULTAS)]
    tabela_admin = usuarios[colunas_exibir_admin].copy()
    tabela_admin["IsAdmin"] = tabela_admin["IsAdmin"].map({True: "✅ Sim", False: "—"})
    st.dataframe(tabela_admin, width="stretch", hide_index=True)

    st.divider()
    st.markdown("##### 👑 Conceder/revogar administrador")
    outros_usuarios = usuarios[usuarios["Usuario"] != current_user]["Usuario"].tolist()
    if not outros_usuarios:
        st.info("Não há outras pessoas cadastradas ainda.")
    else:
        alvo_admin = st.selectbox("Pessoa", outros_usuarios, key="admin_toggle_alvo")
        alvo_idx = usuarios.index[usuarios["Usuario"] == alvo_admin][0]
        alvo_e_admin = bool(usuarios.at[alvo_idx, "IsAdmin"])
        col_promo, col_rebaixa = st.columns(2)
        if not alvo_e_admin:
            if col_promo.button(f"👑 Tornar {alvo_admin} administrador(a)", width="stretch"):
                usuarios.at[alvo_idx, "IsAdmin"] = True
                st.session_state.dfs["Usuarios"] = usuarios
                persist(f"Promover {alvo_admin} a administrador")
                st.success(f"{alvo_admin} agora é administrador(a)!")
                st.rerun()
        else:
            if col_rebaixa.button(f"👤 Remover admin de {alvo_admin}", width="stretch"):
                usuarios_apos = usuarios.copy()
                usuarios_apos.at[alvo_idx, "IsAdmin"] = False
                usuarios_apos = dm.ensure_admin(usuarios_apos)
                st.session_state.dfs["Usuarios"] = usuarios_apos
                persist(f"Revogar admin de {alvo_admin}")
                st.success(f"Permissão de administrador removida de {alvo_admin}.")
                st.rerun()

    st.divider()
    st.markdown("##### 🗑️ Remover pessoa")
    st.caption(
        "Remove a pessoa e todo o histórico de atividades dela. "
        "Você não pode remover a si mesmo(a), nem remover o último administrador restante."
    )
    if not outros_usuarios:
        st.info("Não há outras pessoas para remover.")
    else:
        alvo_remover = st.selectbox("Pessoa a remover", outros_usuarios, key="admin_remover_alvo")
        alvo_remover_idx = usuarios.index[usuarios["Usuario"] == alvo_remover][0]
        alvo_e_admin_remover = bool(usuarios.at[alvo_remover_idx, "IsAdmin"])
        total_admins = int(usuarios["IsAdmin"].sum())
        bloqueado = alvo_e_admin_remover and total_admins <= 1

        if bloqueado:
            st.warning(f"{alvo_remover} é o único administrador restante e não pode ser removido. Promova outra pessoa antes.")

        confirmar = st.checkbox(f"Confirmo que quero remover **{alvo_remover}** permanentemente", key="admin_confirma_remover")
        if st.button("🗑️ Remover definitivamente", type="secondary", disabled=(bloqueado or not confirmar)):
            st.session_state.dfs["Usuarios"] = usuarios[usuarios["Usuario"] != alvo_remover].reset_index(drop=True)
            st.session_state.dfs["Atividades"] = atividades[atividades["Usuario"] != alvo_remover].reset_index(drop=True)
            persist(f"Remover pessoa: {alvo_remover}")
            st.success(f"{alvo_remover} foi removido(a).")
            st.rerun()
