/* ==========================================================================
   Atalho English Journey (PWA)
   --------------------------------------------------------------------------
   Lê e grava DIRETAMENTE no mesmo arquivo Excel (aba "Atividades") que o
   English Journey usa no GitHub, via GitHub Contents API. Não depende do
   Streamlit estar aberto — funciona a qualquer hora, do celular.

   Regra de seleção da tarefa a marcar (MESMA lógica usada no app.py e no
   duolingo_autosync.py, para o comportamento ser idêntico em todo o
   sistema):
     1. Procura, para o seu usuário, tarefas NÃO concluídas cujo texto
        (Tarefa + Modalidade) contenha a palavra-chave do atalho.
     2. Se existir alguma pendente com data até hoje (atrasada ou de
        hoje), marca a MAIS ANTIGA delas.
     3. Se só existir tarefa futura, PEDE CONFIRMAÇÃO antes de marcar.
     4. Se não achar nenhuma pendente, avisa que não há nada a marcar.
   ========================================================================== */

const CONFIG_KEY = "ejAtalhoConfig";
const QUEUE_KEY = "ejAtalhoQueue";

const DEFAULT_SHORTCUTS = [
  { id: "duolingo", emoji: "🦉", label: "Duolingo", keyword: "duolingo" },
  { id: "english_live", emoji: "🗣️", label: "English Live", keyword: "english live" },
  { id: "mairo", emoji: "🎓", label: "Mairo Vergara", keyword: "mairo" },
];

let CFG = null;

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------
function $(sel) { return document.querySelector(sel); }
function $all(sel) { return Array.from(document.querySelectorAll(sel)); }

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function loadConfig() {
  try {
    const raw = localStorage.getItem(CONFIG_KEY);
    if (!raw) return null;
    const cfg = JSON.parse(raw);
    if (!cfg.shortcuts || !cfg.shortcuts.length) cfg.shortcuts = DEFAULT_SHORTCUTS.slice();
    return cfg;
  } catch { return null; }
}

function saveConfig(cfg) {
  localStorage.setItem(CONFIG_KEY, JSON.stringify(cfg));
  CFG = cfg;
}

function configIsComplete(cfg) {
  return !!(cfg && cfg.token && cfg.repo && cfg.branch && cfg.path && cfg.usuario);
}

function todayISOLocal() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function nowBR() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${y}-${m}-${day} ${hh}:${mm}`;
}

function formatBR(iso) {
  if (!iso || iso.length < 10) return iso || "?";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
}

function toISODate(v) {
  if (v instanceof Date) {
    const y = v.getUTCFullYear();
    const m = String(v.getUTCMonth() + 1).padStart(2, "0");
    const d = String(v.getUTCDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }
  const s = String(v ?? "").trim();
  const m = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (m) return m[1];
  const m2 = s.match(/^(\d{2})\/(\d{2})\/(\d{4})/); // dd/mm/aaaa fallback
  if (m2) return `${m2[3]}-${m2[2]}-${m2[1]}`;
  return s;
}

function isTrue(v) {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v === 1;
  const s = String(v ?? "").trim().toLowerCase();
  return ["true", "1", "sim", "yes", "verdadeiro"].includes(s);
}

function matchesKeyword(row, keyword) {
  const hay = `${row["Tarefa"] ?? ""} ${row["Modalidade"] ?? ""}`.toLowerCase();
  return hay.includes(String(keyword ?? "").toLowerCase());
}

function vibrate() {
  if (navigator.vibrate) navigator.vibrate([30, 40, 30]);
}

// Mesma regra usada em data_model.find_nearest_pending_task (Python):
// prioriza a pendência vencida/hoje mais antiga; se só houver futura,
// sinaliza `futura: true` para o chamador pedir confirmação.
function selecionarAlvo(rows, usuario, keyword, todayISO) {
  const candidatos = rows
    .map((r, idx) => ({ row: r, idx, dataISO: toISODate(r["Data"]), concluido: isTrue(r["Concluido"]) }))
    .filter((c) =>
      String(c.row["Usuario"] ?? "").trim() === usuario.trim() &&
      !c.concluido &&
      matchesKeyword(c.row, keyword)
    );
  if (candidatos.length === 0) return null;
  candidatos.sort((a, b) => (a.dataISO < b.dataISO ? -1 : a.dataISO > b.dataISO ? 1 : 0));
  const overdueOuHoje = candidatos.filter((c) => c.dataISO <= todayISO);
  if (overdueOuHoje.length > 0) return overdueOuHoje[0];
  return { ...candidatos[0], futura: true };
}

// ---------------------------------------------------------------------------
// GitHub Contents API
// ---------------------------------------------------------------------------
function ghHeaders(token) {
  return {
    Authorization: `token ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

function encodePath(path) {
  return path.split("/").filter(Boolean).map(encodeURIComponent).join("/");
}

function base64ToBytes(b64) {
  const binary = atob(b64.replace(/\n/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

function bytesToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function ghFetchFile(cfg) {
  const url = `https://api.github.com/repos/${cfg.repo}/contents/${encodePath(cfg.path)}?ref=${encodeURIComponent(cfg.branch)}`;
  const resp = await fetch(url, { headers: ghHeaders(cfg.token) });
  if (!resp.ok) {
    const t = await resp.text().catch(() => "");
    throw new Error(`Falha ao ler arquivo no GitHub (HTTP ${resp.status}). ${t.slice(0, 200)}`);
  }
  const json = await resp.json();
  return { bytes: base64ToBytes(json.content), sha: json.sha };
}

async function ghPushFile(cfg, arrayBuffer, sha, message) {
  const url = `https://api.github.com/repos/${cfg.repo}/contents/${encodePath(cfg.path)}`;
  const body = { message, content: bytesToBase64(arrayBuffer), branch: cfg.branch, sha };
  const resp = await fetch(url, {
    method: "PUT",
    headers: { ...ghHeaders(cfg.token), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (resp.status === 409) { const e = new Error("conflict"); e.conflict = true; throw e; }
  if (!resp.ok) {
    const t = await resp.text().catch(() => "");
    throw new Error(`Falha ao gravar arquivo no GitHub (HTTP ${resp.status}). ${t.slice(0, 200)}`);
  }
  return resp.json();
}

// ---------------------------------------------------------------------------
// UI: banners, spinner, modal de confirmação
// ---------------------------------------------------------------------------
function showBanner(kind, text, autoHideMs = 6000) {
  const el = $("#banner");
  el.className = `status-banner show ${kind}`;
  el.textContent = text;
  if (autoHideMs) {
    clearTimeout(showBanner._t);
    showBanner._t = setTimeout(() => el.classList.remove("show"), autoHideMs);
  }
}

function showSpinner(show) {
  $("#spinner-overlay").classList.toggle("show", !!show);
}

function askConfirm(title, body) {
  return new Promise((resolve) => {
    $("#modal-title").textContent = title;
    $("#modal-body").textContent = body;
    $("#modal-overlay").classList.add("show");
    const cleanup = (result) => {
      $("#modal-overlay").classList.remove("show");
      $("#modal-confirm").onclick = null;
      $("#modal-cancel").onclick = null;
      resolve(result);
    };
    $("#modal-confirm").onclick = () => cleanup(true);
    $("#modal-cancel").onclick = () => cleanup(false);
  });
}

// ---------------------------------------------------------------------------
// Fila offline (best-effort)
// ---------------------------------------------------------------------------
function loadQueue() {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]"); } catch { return []; }
}
function saveQueue(q) { localStorage.setItem(QUEUE_KEY, JSON.stringify(q)); }

function renderQueueBanner() {
  const q = loadQueue();
  const box = $("#pending-queue-box");
  if (q.length === 0) { box.style.display = "none"; return; }
  box.style.display = "block";
  $("#pending-queue-text").textContent =
    `⏳ ${q.length} ação(ões) aguardando conexão para sincronizar: ` +
    q.map((i) => i.label).join(", ") + ".";
}

async function processQueue() {
  const q = loadQueue();
  if (q.length === 0) return;
  const remaining = [];
  for (const item of q) {
    const shortcut = CFG.shortcuts.find((s) => s.id === item.shortcutId) ||
      { id: item.shortcutId, label: item.label, keyword: item.keyword, emoji: item.emoji };
    const result = await performMark(shortcut, { silent: true }).catch((e) => ({ ok: false, error: e }));
    if (!result.ok && !result.cancelled) remaining.push(item); // recoloca na fila se falhou de novo
  }
  saveQueue(remaining);
  renderQueueBanner();
  if (remaining.length === 0) showBanner("ok", "✅ Todas as ações pendentes foram sincronizadas.");
}

window.addEventListener("online", () => { processQueue(); });

// ---------------------------------------------------------------------------
// Lógica principal: marcar tarefa mais próxima como concluída
// ---------------------------------------------------------------------------
async function performMark(shortcut, opts = {}) {
  const cardEl = document.getElementById(`card-${shortcut.id}`);
  if (cardEl) cardEl.classList.add("loading");
  if (!opts.silent) showSpinner(true);
  try {
    let attempt = 0;
    while (attempt < 3) {
      attempt++;
      const { bytes, sha } = await ghFetchFile(CFG);
      const wb = XLSX.read(bytes, { type: "array", cellDates: true });
      if (!wb.SheetNames.includes("Atividades")) {
        throw new Error('A aba "Atividades" não foi encontrada no arquivo Excel.');
      }
      const sheet = wb.Sheets["Atividades"];
      const headerRow = (XLSX.utils.sheet_to_json(sheet, { header: 1 })[0]) || [];
      const rows = XLSX.utils.sheet_to_json(sheet, { defval: "" });

      const todayISO = todayISOLocal();
      const alvo = selecionarAlvo(rows, CFG.usuario, shortcut.keyword, todayISO);

      if (alvo === null) {
        if (!opts.silent) showBanner("warn", `Nenhuma tarefa pendente encontrada para "${shortcut.label}" no seu calendário.`);
        return { ok: false };
      }

      if (alvo.futura) {
        if (!opts.silent) {
          const ok = await askConfirm(
            "Marcar tarefa futura?",
            `A próxima tarefa de "${shortcut.label}" está agendada para ${formatBR(alvo.dataISO)}. ` +
            `Deseja marcar como concluída adiantada mesmo assim?`
          );
          if (!ok) return { ok: false, cancelled: true };
        } else {
          // Em execução silenciosa (fila offline), nunca marca tarefa
          // futura sem confirmação explícita da pessoa.
          return { ok: false, cancelled: true };
        }
      }

      const target = rows[alvo.idx];
      target["Concluido"] = true;
      if (!target["MinutosExecutados"]) target["MinutosExecutados"] = target["MinutosPlanejados"] || "";
      target["DataConclusao"] = nowBR();
      const notaAtual = String(target["Anotacoes"] ?? "");
      const notaNova = `Marcado via atalho PWA (${shortcut.label})`;
      target["Anotacoes"] = notaAtual ? `${notaAtual} | ${notaNova}` : notaNova;

      const newSheet = XLSX.utils.json_to_sheet(rows, { header: headerRow });
      wb.Sheets["Atividades"] = newSheet;
      const out = XLSX.write(wb, { type: "array", bookType: "xlsx" });

      try {
        await ghPushFile(CFG, out, sha, `Atalho PWA: ${shortcut.label} concluído (${CFG.usuario}, ref. ${alvo.dataISO})`);
        if (!opts.silent) {
          showBanner("ok", `✅ "${shortcut.label}" marcado como concluído (referente a ${formatBR(alvo.dataISO)}).`);
          vibrate();
        }
        await carregarPainel();
        return { ok: true, date: alvo.dataISO };
      } catch (e) {
        if (e && e.conflict) continue; // outra gravação aconteceu ao mesmo tempo — tenta de novo
        throw e;
      }
    }
    throw new Error("Conflito de versão no GitHub após 3 tentativas. Tente novamente em instantes.");
  } catch (err) {
    const isNetworkError = err instanceof TypeError; // fetch falhou (offline/DNS/CORS)
    if (isNetworkError && !opts.silent) {
      const q = loadQueue();
      q.push({ shortcutId: shortcut.id, label: shortcut.label, keyword: shortcut.keyword, emoji: shortcut.emoji, ts: Date.now() });
      saveQueue(q);
      renderQueueBanner();
      showBanner("warn", `Sem conexão agora. "${shortcut.label}" foi enfileirado e será sincronizado automaticamente quando a internet voltar.`);
      return { ok: false, queued: true };
    }
    if (!opts.silent) showBanner("err", `Erro ao sincronizar: ${err.message}`);
    return { ok: false, error: err };
  } finally {
    if (cardEl) cardEl.classList.remove("loading");
    if (!opts.silent) showSpinner(false);
  }
}

// ---------------------------------------------------------------------------
// Painel: indicadores e prévia das tarefas pendentes
// ---------------------------------------------------------------------------
function dateFromISO(iso) {
  const parts = String(iso || "").slice(0, 10).split("-").map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return null;
  return new Date(parts[0], parts[1] - 1, parts[2], 12, 0, 0);
}

function localISOFromDate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function calcularIndicadores(rows, usuario) {
  const doUsuario = rows.filter((r) => String(r["Usuario"] ?? "").trim() === usuario.trim());
  const concluidas = doUsuario.filter((r) => isTrue(r["Concluido"]));

  const minutosReais = (r) => {
    const executados = Number(r["MinutosExecutados"] || 0);
    const planejados = Number(r["MinutosPlanejados"] || 0);
    return executados > 0 ? executados : planejados;
  };

  const totalMinutos = concluidas.reduce((acc, r) => acc + minutosReais(r), 0);
  const xp = Math.round(totalMinutos / 5);
  const taxa = doUsuario.length ? (concluidas.length / doUsuario.length) * 100 : 0;

  const hoje = dateFromISO(todayISOLocal());
  const diaSemana = hoje.getDay();
  const segunda = new Date(hoje);
  segunda.setDate(hoje.getDate() + (diaSemana === 0 ? -6 : 1 - diaSemana));
  const domingo = new Date(segunda);
  domingo.setDate(segunda.getDate() + 6);
  const inicioSemana = localISOFromDate(segunda);
  const fimSemana = localISOFromDate(domingo);
  const minutosSemana = concluidas
    .filter((r) => {
      const data = toISODate(r["Data"]);
      return data >= inicioSemana && data <= fimSemana;
    })
    .reduce((acc, r) => acc + minutosReais(r), 0);

  const datas = [...new Set(concluidas.map((r) => toISODate(r["Data"])).filter(Boolean))].sort().reverse();
  let sequencia = 0;
  if (datas.length) {
    sequencia = 1;
    let anterior = dateFromISO(datas[0]);
    for (let i = 1; i < datas.length; i++) {
      const atual = dateFromISO(datas[i]);
      if (anterior && atual && Math.round((anterior - atual) / 86400000) === 1) {
        sequencia += 1;
        anterior = atual;
      } else break;
    }
  }
  return { sequencia, xp, horasSemana: minutosSemana / 60, taxa };
}

function renderIndicadores(rows) {
  const s = calcularIndicadores(rows, CFG.usuario);
  $("#stat-streak").textContent = String(s.sequencia);
  $("#stat-xp").textContent = `${s.xp}XP`;
  $("#stat-week-hours").textContent = `${s.horasSemana.toFixed(1)}h`;
  $("#stat-completion").textContent = `${s.taxa.toFixed(0)}%`;
}

function statusDaPendencia(alvo, hoje) {
  if (!alvo) return { classe: "sem-pendencia", texto: "✅ Nenhuma atividade pendente" };
  if (alvo.dataISO < hoje) return { classe: "atrasada", texto: `🔴 Atrasada desde ${formatBR(alvo.dataISO)}` };
  if (alvo.dataISO === hoje) return { classe: "hoje", texto: "🟡 Pendente para hoje" };
  return { classe: "futura", texto: `🔵 Próxima: ${formatBR(alvo.dataISO)}` };
}

function descricaoDaPendencia(row, fallback) {
  const tarefa = String(row?.["Tarefa"] ?? "").trim();
  const modalidade = String(row?.["Modalidade"] ?? "").trim();
  const horario = String(row?.["Horario"] ?? "").trim();
  const minutos = Number(row?.["MinutosPlanejados"] || 0);
  const partes = [];
  if (tarefa) partes.push(tarefa);
  if (modalidade && modalidade.toLowerCase() !== tarefa.toLowerCase()) partes.push(modalidade);
  if (horario) partes.push(horario);
  if (minutos) partes.push(`${minutos} min`);
  return partes.join(" • ") || fallback;
}

async function carregarPainel() {
  if (!CFG || !configIsComplete(CFG)) return;
  const btn = $("#btn-refresh-pendencias");
  if (btn) { btn.disabled = true; btn.classList.add("loading"); }
  try {
    const { bytes } = await ghFetchFile(CFG);
    const wb = XLSX.read(bytes, { type: "array", cellDates: true });
    if (!wb.SheetNames.includes("Atividades")) throw new Error('A aba "Atividades" não foi encontrada.');
    const rows = XLSX.utils.sheet_to_json(wb.Sheets["Atividades"], { defval: "" });
    const hoje = todayISOLocal();
    renderIndicadores(rows);

    CFG.shortcuts.forEach((shortcut) => {
      const alvo = selecionarAlvo(rows, CFG.usuario, shortcut.keyword, hoje);
      const status = statusDaPendencia(alvo, hoje);
      const card = document.getElementById(`card-${shortcut.id}`);
      const statusEl = document.getElementById(`status-${shortcut.id}`);
      const descEl = document.getElementById(`descricao-${shortcut.id}`);
      card?.classList.remove("atrasada", "hoje", "futura", "sem-pendencia", "erro-consulta");
      card?.classList.add(status.classe);
      if (statusEl) statusEl.textContent = status.texto;
      if (descEl) descEl.textContent = alvo ? descricaoDaPendencia(alvo.row, shortcut.label) : "Todas as atividades foram concluídas";
    });
  } catch (err) {
    CFG.shortcuts.forEach((shortcut) => {
      const card = document.getElementById(`card-${shortcut.id}`);
      const statusEl = document.getElementById(`status-${shortcut.id}`);
      const descEl = document.getElementById(`descricao-${shortcut.id}`);
      card?.classList.remove("atrasada", "hoje", "futura", "sem-pendencia");
      card?.classList.add("erro-consulta");
      if (statusEl) statusEl.textContent = "⚠️ Não foi possível consultar";
      if (descEl) descEl.textContent = navigator.onLine ? "Confira a configuração e toque em Atualizar" : "Sem conexão com a internet";
    });
    showBanner("err", `Erro ao carregar o painel: ${err.message}`, 0);
  } finally {
    if (btn) { btn.disabled = false; btn.classList.remove("loading"); }
  }
}

// ---------------------------------------------------------------------------
// Renderização da tela principal
// ---------------------------------------------------------------------------
function renderMainScreen() {
  $("#header-sub").textContent = `usuário: ${CFG.usuario}`;
  const container = $("#cards-container");
  container.innerHTML = CFG.shortcuts.map((s) => `
    <div class="task-card" id="card-${s.id}" data-id="${s.id}">
      <div class="emoji">${escapeHtml(s.emoji)}</div>
      <div class="info">
        <div class="label">${escapeHtml(s.label)}</div>
        <div class="pending-status" id="status-${s.id}">Consultando pendência...</div>
        <div class="pending-description" id="descricao-${s.id}"></div>
      </div>
      <div class="chev">›</div>
    </div>
  `).join("");
  $all(".task-card").forEach((card) => {
    card.addEventListener("click", () => {
      const shortcut = CFG.shortcuts.find((s) => s.id === card.dataset.id);
      if (shortcut) performMark(shortcut);
    });
  });
  renderQueueBanner();
  carregarPainel();
}

// ---------------------------------------------------------------------------
// Tela de configuração
// ---------------------------------------------------------------------------
let workingShortcuts = [];

function renderShortcutRows() {
  $("#shortcut-list").innerHTML = workingShortcuts.map((s, idx) => `
    <div class="shortcut-row" data-idx="${idx}">
      <input type="text" class="emoji-input sc-emoji" maxlength="4" value="${escapeHtml(s.emoji)}" />
      <input type="text" class="sc-label" placeholder="Nome do botão" value="${escapeHtml(s.label)}" />
      <input type="text" class="sc-keyword" placeholder="palavra-chave" value="${escapeHtml(s.keyword)}" />
      <button class="remove-btn" data-remove="${idx}" type="button">✕</button>
    </div>
  `).join("");
  $all(".remove-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      workingShortcuts.splice(Number(btn.dataset.remove), 1);
      renderShortcutRows();
    });
  });
}

function readShortcutRowsFromDOM() {
  return $all(".shortcut-row").map((rowEl) => ({
    id: rowEl.querySelector(".sc-label").value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_") || `atalho_${Date.now()}`,
    emoji: rowEl.querySelector(".sc-emoji").value.trim() || "✅",
    label: rowEl.querySelector(".sc-label").value.trim(),
    keyword: rowEl.querySelector(".sc-keyword").value.trim(),
  })).filter((s) => s.label && s.keyword);
}

function showConfigScreen(canCancel) {
  $("#screen-main").style.display = "none";
  $("#screen-config").style.display = "block";
  $("#btn-cancel-config").style.display = canCancel ? "block" : "none";
  const cfg = CFG || {};
  $("#cfg-token").value = cfg.token || "";
  $("#cfg-repo").value = cfg.repo || "";
  $("#cfg-branch").value = cfg.branch || "main";
  $("#cfg-path").value = cfg.path || "";
  $("#cfg-usuario").value = cfg.usuario || "";
  workingShortcuts = (cfg.shortcuts && cfg.shortcuts.length ? cfg.shortcuts : DEFAULT_SHORTCUTS).map((s) => ({ ...s }));
  renderShortcutRows();
}

function showMainScreen() {
  $("#screen-config").style.display = "none";
  $("#screen-main").style.display = "block";
  renderMainScreen();
}

function bindConfigEvents() {
  $("#btn-add-shortcut").addEventListener("click", () => {
    workingShortcuts.push({ id: `atalho_${Date.now()}`, emoji: "✅", label: "", keyword: "" });
    renderShortcutRows();
  });

  $("#btn-save-config").addEventListener("click", () => {
    const token = $("#cfg-token").value.trim();
    const repo = $("#cfg-repo").value.trim();
    const branch = $("#cfg-branch").value.trim() || "main";
    const path = $("#cfg-path").value.trim().replace(/^\/+/, "");
    const usuario = $("#cfg-usuario").value.trim();
    const shortcuts = readShortcutRowsFromDOM();

    if (!token || !repo || !path || !usuario) {
      showBanner("err", "Preencha token, repositório, caminho do arquivo e usuário antes de salvar.");
      return;
    }
    if (shortcuts.length === 0) {
      showBanner("err", "Adicione ao menos um atalho (nome + palavra-chave).");
      return;
    }
    saveConfig({ token, repo, branch, path, usuario, shortcuts });
    showBanner("ok", "Configuração salva neste aparelho.");
    showMainScreen();
  });

  $("#btn-cancel-config").addEventListener("click", () => showMainScreen());

  $("#btn-retry-queue").addEventListener("click", () => processQueue());
  $("#btn-refresh-pendencias").addEventListener("click", () => carregarPainel());

  $("#btn-reset-config").addEventListener("click", async () => {
    const ok = await askConfirm("Apagar configuração?", "Isso remove o token e as preferências salvas neste aparelho. Você precisará configurar novamente.");
    if (!ok) return;
    localStorage.removeItem(CONFIG_KEY);
    localStorage.removeItem(QUEUE_KEY);
    CFG = null;
    location.reload();
  });

  $("#btn-open-config").addEventListener("click", () => showConfigScreen(!!CFG && configIsComplete(CFG)));
}

// ---------------------------------------------------------------------------
// Inicialização
// ---------------------------------------------------------------------------
function init() {
  bindConfigEvents();
  CFG = loadConfig();
  if (configIsComplete(CFG)) {
    showMainScreen();
    if (navigator.onLine) processQueue();
  } else {
    showConfigScreen(false);
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && CFG && configIsComplete(CFG)) carregarPainel();
});
document.addEventListener("DOMContentLoaded", init);
