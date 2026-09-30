/* ========================================================================== 
   Atalho English Journey (PWA) - v2
   Mostra a proxima pendencia antes de concluir e grava no Excel do GitHub.
   ========================================================================== */
const CONFIG_KEY = "ejAtalhoConfig";
const QUEUE_KEY = "ejAtalhoQueue";
const DEFAULT_SHORTCUTS = [
  { id: "duolingo", emoji: "🦉", label: "Duolingo", keyword: "duolingo" },
  { id: "english_live", emoji: "🗣️", label: "English Live", keyword: "english live" },
  { id: "mairo", emoji: "🎓", label: "Mairo Vergara", keyword: "mairo" },
];
let CFG = null;

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
function saveConfig(cfg) { localStorage.setItem(CONFIG_KEY, JSON.stringify(cfg)); CFG = cfg; }
function configIsComplete(cfg) { return !!(cfg && cfg.token && cfg.repo && cfg.branch && cfg.path && cfg.usuario); }
function todayISOLocal() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}
function nowBR() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`;
}
function formatBR(iso) {
  if (!iso || iso.length < 10) return iso || "?";
  const [y,m,d] = iso.slice(0,10).split("-");
  return `${d}/${m}/${y}`;
}
function toISODate(v) {
  if (v instanceof Date) return `${v.getUTCFullYear()}-${String(v.getUTCMonth()+1).padStart(2,"0")}-${String(v.getUTCDate()).padStart(2,"0")}`;
  const s=String(v ?? "").trim();
  const m=s.match(/^(\d{4}-\d{2}-\d{2})/); if(m) return m[1];
  const m2=s.match(/^(\d{2})\/(\d{2})\/(\d{4})/); if(m2) return `${m2[3]}-${m2[2]}-${m2[1]}`;
  return s;
}
function isTrue(v) {
  if(typeof v==="boolean") return v;
  if(typeof v==="number") return v===1;
  return ["true","1","sim","yes","verdadeiro"].includes(String(v ?? "").trim().toLowerCase());
}
function matchesKeyword(row, keyword) {
  return `${row["Tarefa"] ?? ""} ${row["Modalidade"] ?? ""}`.toLowerCase().includes(String(keyword ?? "").toLowerCase());
}
function vibrate(){ if(navigator.vibrate) navigator.vibrate([30,40,30]); }
function selecionarAlvo(rows, usuario, keyword, todayISO) {
  const candidatos=rows.map((r,idx)=>({row:r,idx,dataISO:toISODate(r["Data"]),concluido:isTrue(r["Concluido"])}))
    .filter(c=>String(c.row["Usuario"] ?? "").trim()===usuario.trim() && !c.concluido && matchesKeyword(c.row,keyword));
  if(!candidatos.length) return null;
  candidatos.sort((a,b)=>a.dataISO.localeCompare(b.dataISO));
  const vencidas=candidatos.filter(c=>c.dataISO<=todayISO);
  return vencidas.length ? vencidas[0] : {...candidatos[0], futura:true};
}

function ghHeaders(token){ return {Authorization:`token ${token}`,Accept:"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}; }
function encodePath(path){ return path.split("/").filter(Boolean).map(encodeURIComponent).join("/"); }
function base64ToBytes(b64){ const binary=atob(b64.replace(/\n/g,"")); const bytes=new Uint8Array(binary.length); for(let i=0;i<binary.length;i++) bytes[i]=binary.charCodeAt(i); return bytes; }
function bytesToBase64(buffer){ let binary=""; const bytes=new Uint8Array(buffer), chunk=0x8000; for(let i=0;i<bytes.length;i+=chunk) binary+=String.fromCharCode.apply(null,bytes.subarray(i,i+chunk)); return btoa(binary); }
async function ghFetchFile(cfg){
  const url=`https://api.github.com/repos/${cfg.repo}/contents/${encodePath(cfg.path)}?ref=${encodeURIComponent(cfg.branch)}`;
  const resp=await fetch(url,{headers:ghHeaders(cfg.token)});
  if(!resp.ok){ const t=await resp.text().catch(()=>""); throw new Error(`Falha ao ler arquivo no GitHub (HTTP ${resp.status}). ${t.slice(0,200)}`); }
  const json=await resp.json(); return {bytes:base64ToBytes(json.content),sha:json.sha};
}
async function ghPushFile(cfg,arrayBuffer,sha,message){
  const url=`https://api.github.com/repos/${cfg.repo}/contents/${encodePath(cfg.path)}`;
  const body={message,content:bytesToBase64(arrayBuffer),branch:cfg.branch,sha};
  const resp=await fetch(url,{method:"PUT",headers:{...ghHeaders(cfg.token),"Content-Type":"application/json"},body:JSON.stringify(body)});
  if(resp.status===409){ const e=new Error("conflict"); e.conflict=true; throw e; }
  if(!resp.ok){ const t=await resp.text().catch(()=>""); throw new Error(`Falha ao gravar arquivo no GitHub (HTTP ${resp.status}). ${t.slice(0,200)}`); }
  return resp.json();
}

function showBanner(kind,text,autoHideMs=6000){ const el=$("#banner"); el.className=`status-banner show ${kind}`; el.textContent=text; if(autoHideMs){clearTimeout(showBanner._t);showBanner._t=setTimeout(()=>el.classList.remove("show"),autoHideMs);} }
function showSpinner(show){ $("#spinner-overlay").classList.toggle("show",!!show); }
function askConfirm(title,body){ return new Promise(resolve=>{ $("#modal-title").textContent=title; $("#modal-body").textContent=body; $("#modal-overlay").classList.add("show"); const done=result=>{$("#modal-overlay").classList.remove("show");$("#modal-confirm").onclick=null;$("#modal-cancel").onclick=null;resolve(result);}; $("#modal-confirm").onclick=()=>done(true); $("#modal-cancel").onclick=()=>done(false); }); }

function loadQueue(){ try{return JSON.parse(localStorage.getItem(QUEUE_KEY)||"[]");}catch{return [];} }
function saveQueue(q){ localStorage.setItem(QUEUE_KEY,JSON.stringify(q)); }
function renderQueueBanner(){ const q=loadQueue(),box=$("#pending-queue-box"); if(!q.length){box.style.display="none";return;} box.style.display="block"; $("#pending-queue-text").textContent=`⏳ ${q.length} ação(ões) aguardando conexão: `+q.map(i=>i.label).join(", ")+"."; }
async function processQueue(){ const q=loadQueue(); if(!q.length)return; const remaining=[]; for(const item of q){ const shortcut=CFG.shortcuts.find(s=>s.id===item.shortcutId)||item; const result=await performMark(shortcut,{silent:true}).catch(e=>({ok:false,error:e})); if(!result.ok&&!result.cancelled)remaining.push(item); } saveQueue(remaining); renderQueueBanner(); if(!remaining.length){showBanner("ok","✅ Todas as ações pendentes foram sincronizadas."); await carregarPendenciasNosCards();} }
window.addEventListener("online",()=>processQueue());

function obterStatusAlvo(alvo,todayISO){
  if(!alvo) return {classe:"sem-pendencia",status:"✅ Nenhuma atividade pendente"};
  if(alvo.dataISO<todayISO) return {classe:"atrasada",status:`🔴 Atrasada desde ${formatBR(alvo.dataISO)}`};
  if(alvo.dataISO===todayISO) return {classe:"hoje",status:"🟡 Pendente para hoje"};
  return {classe:"futura",status:`🔵 Próxima: ${formatBR(alvo.dataISO)}`};
}
function obterDescricaoTarefa(row,fallback){
  const tarefa=String(row?.["Tarefa"]??"").trim(), modalidade=String(row?.["Modalidade"]??"").trim();
  if(tarefa&&modalidade&&tarefa.toLowerCase()!==modalidade.toLowerCase()) return `${tarefa} • ${modalidade}`;
  return tarefa||modalidade||fallback;
}
async function carregarPendenciasNosCards(){
  if(!CFG||!configIsComplete(CFG))return;
  const btn=$("#btn-refresh-pendencias"); if(btn){btn.classList.add("loading");btn.disabled=true;}
  CFG.shortcuts.forEach(s=>{ const st=$(`#status-${s.id}`),ds=$(`#descricao-${s.id}`),card=$(`#card-${s.id}`); if(st)st.textContent="Consultando pendência..."; if(ds)ds.textContent=""; if(card)card.classList.remove("atrasada","hoje","futura","sem-pendencia","erro-consulta"); });
  try{
    const {bytes}=await ghFetchFile(CFG); const wb=XLSX.read(bytes,{type:"array",cellDates:true});
    if(!wb.SheetNames.includes("Atividades"))throw new Error('A aba "Atividades" não foi encontrada.');
    const rows=XLSX.utils.sheet_to_json(wb.Sheets["Atividades"],{defval:""}), today=todayISOLocal();
    CFG.shortcuts.forEach(s=>{ const alvo=selecionarAlvo(rows,CFG.usuario,s.keyword,today), visual=obterStatusAlvo(alvo,today); const card=$(`#card-${s.id}`),st=$(`#status-${s.id}`),ds=$(`#descricao-${s.id}`); if(card){card.classList.remove("atrasada","hoje","futura","sem-pendencia","erro-consulta");card.classList.add(visual.classe);} if(st)st.textContent=visual.status; if(ds)ds.textContent=alvo?obterDescricaoTarefa(alvo.row,s.label):"Todas as atividades foram concluídas"; });
  }catch(err){
    CFG.shortcuts.forEach(s=>{ const card=$(`#card-${s.id}`),st=$(`#status-${s.id}`),ds=$(`#descricao-${s.id}`); if(card){card.classList.remove("atrasada","hoje","futura","sem-pendencia");card.classList.add("erro-consulta");} if(st)st.textContent="⚠️ Não foi possível consultar"; if(ds)ds.textContent=navigator.onLine?"Toque em atualizar para tentar novamente":"Sem conexão com a internet"; });
    showBanner("warn",`Não foi possível carregar as pendências: ${err.message}`);
  }finally{ if(btn){btn.classList.remove("loading");btn.disabled=false;} }
}

async function performMark(shortcut,opts={}){
  const cardEl=document.getElementById(`card-${shortcut.id}`); if(cardEl)cardEl.classList.add("loading"); if(!opts.silent)showSpinner(true);
  try{
    let attempt=0;
    while(attempt<3){ attempt++; const {bytes,sha}=await ghFetchFile(CFG); const wb=XLSX.read(bytes,{type:"array",cellDates:true});
      if(!wb.SheetNames.includes("Atividades"))throw new Error('A aba "Atividades" não foi encontrada no arquivo Excel.');
      const sheet=wb.Sheets["Atividades"], headerRow=XLSX.utils.sheet_to_json(sheet,{header:1})[0]||[], rows=XLSX.utils.sheet_to_json(sheet,{defval:""}), alvo=selecionarAlvo(rows,CFG.usuario,shortcut.keyword,todayISOLocal());
      if(!alvo){if(!opts.silent)showBanner("warn",`Nenhuma tarefa pendente encontrada para "${shortcut.label}".`);return {ok:false};}
      if(alvo.futura){ if(opts.silent)return {ok:false,cancelled:true}; const ok=await askConfirm("Marcar tarefa futura?",`A próxima tarefa de "${shortcut.label}" está agendada para ${formatBR(alvo.dataISO)}. Deseja marcar como concluída adiantada?`); if(!ok)return {ok:false,cancelled:true}; }
      const target=rows[alvo.idx]; target["Concluido"]=true; if(!target["MinutosExecutados"])target["MinutosExecutados"]=target["MinutosPlanejados"]||""; target["DataConclusao"]=nowBR(); const nota=String(target["Anotacoes"]??""),nova=`Marcado via atalho PWA (${shortcut.label})`; target["Anotacoes"]=nota?`${nota} | ${nova}`:nova;
      wb.Sheets["Atividades"]=XLSX.utils.json_to_sheet(rows,{header:headerRow}); const out=XLSX.write(wb,{type:"array",bookType:"xlsx"});
      try{ await ghPushFile(CFG,out,sha,`Atalho PWA: ${shortcut.label} concluído (${CFG.usuario}, ref. ${alvo.dataISO})`); if(!opts.silent){showBanner("ok",`✅ "${shortcut.label}" marcado como concluído (referente a ${formatBR(alvo.dataISO)}).`);vibrate();await carregarPendenciasNosCards();} return {ok:true,date:alvo.dataISO}; }catch(e){if(e&&e.conflict)continue;throw e;}
    }
    throw new Error("Conflito de versão no GitHub após 3 tentativas.");
  }catch(err){ const network=err instanceof TypeError; if(network&&!opts.silent){const q=loadQueue();q.push({shortcutId:shortcut.id,label:shortcut.label,keyword:shortcut.keyword,emoji:shortcut.emoji,ts:Date.now()});saveQueue(q);renderQueueBanner();showBanner("warn",`Sem conexão. "${shortcut.label}" foi enfileirado.`);return {ok:false,queued:true};} if(!opts.silent)showBanner("err",`Erro ao sincronizar: ${err.message}`);return {ok:false,error:err}; }
  finally{if(cardEl)cardEl.classList.remove("loading");if(!opts.silent)showSpinner(false);}
}

function renderMainScreen(){
  $("#header-sub").textContent=`usuário: ${CFG.usuario}`; const container=$("#cards-container");
  container.innerHTML=CFG.shortcuts.map(s=>`<div class="task-card" id="card-${s.id}" data-id="${s.id}"><div class="emoji">${escapeHtml(s.emoji)}</div><div class="info"><div class="label">${escapeHtml(s.label)}</div><div class="pending-status" id="status-${s.id}">Consultando pendência...</div><div class="pending-description" id="descricao-${s.id}"></div></div><div class="chev">›</div></div>`).join("");
  $all(".task-card").forEach(card=>card.addEventListener("click",()=>{const s=CFG.shortcuts.find(x=>x.id===card.dataset.id);if(s)performMark(s);})); renderQueueBanner(); carregarPendenciasNosCards();
}

let workingShortcuts=[];
function renderShortcutRows(){ $("#shortcut-list").innerHTML=workingShortcuts.map((s,idx)=>`<div class="shortcut-row" data-idx="${idx}"><input type="text" class="emoji-input sc-emoji" maxlength="4" value="${escapeHtml(s.emoji)}"><input type="text" class="sc-label" placeholder="Nome do botão" value="${escapeHtml(s.label)}"><input type="text" class="sc-keyword" placeholder="palavra-chave" value="${escapeHtml(s.keyword)}"><button class="remove-btn" data-remove="${idx}" type="button">✕</button></div>`).join(""); $all(".remove-btn").forEach(btn=>btn.addEventListener("click",()=>{workingShortcuts.splice(Number(btn.dataset.remove),1);renderShortcutRows();})); }
function readShortcutRowsFromDOM(){ return $all(".shortcut-row").map(el=>({id:el.querySelector(".sc-label").value.trim().toLowerCase().replace(/[^a-z0-9]+/g,"_")||`atalho_${Date.now()}`,emoji:el.querySelector(".sc-emoji").value.trim()||"✅",label:el.querySelector(".sc-label").value.trim(),keyword:el.querySelector(".sc-keyword").value.trim()})).filter(s=>s.label&&s.keyword); }
function showConfigScreen(canCancel){$("#screen-main").style.display="none";$("#screen-config").style.display="block";$("#btn-cancel-config").style.display=canCancel?"block":"none";const c=CFG||{};$("#cfg-token").value=c.token||"";$("#cfg-repo").value=c.repo||"";$("#cfg-branch").value=c.branch||"main";$("#cfg-path").value=c.path||"";$("#cfg-usuario").value=c.usuario||"";workingShortcuts=(c.shortcuts?.length?c.shortcuts:DEFAULT_SHORTCUTS).map(s=>({...s}));renderShortcutRows();}
function showMainScreen(){$("#screen-config").style.display="none";$("#screen-main").style.display="block";renderMainScreen();}
function bindConfigEvents(){
  $("#btn-add-shortcut").addEventListener("click",()=>{workingShortcuts.push({id:`atalho_${Date.now()}`,emoji:"✅",label:"",keyword:""});renderShortcutRows();});
  $("#btn-save-config").addEventListener("click",()=>{const token=$("#cfg-token").value.trim(),repo=$("#cfg-repo").value.trim(),branch=$("#cfg-branch").value.trim()||"main",path=$("#cfg-path").value.trim().replace(/^\/+/,""),usuario=$("#cfg-usuario").value.trim(),shortcuts=readShortcutRowsFromDOM();if(!token||!repo||!path||!usuario){showBanner("err","Preencha token, repositório, caminho e usuário.");return;}if(!shortcuts.length){showBanner("err","Adicione ao menos um atalho.");return;}saveConfig({token,repo,branch,path,usuario,shortcuts});showBanner("ok","Configuração salva neste aparelho.");showMainScreen();});
  $("#btn-cancel-config").addEventListener("click",showMainScreen); $("#btn-retry-queue").addEventListener("click",processQueue); $("#btn-refresh-pendencias").addEventListener("click",carregarPendenciasNosCards);
  $("#btn-reset-config").addEventListener("click",async()=>{if(!await askConfirm("Apagar configuração?","Isso remove o token e as preferências deste aparelho."))return;localStorage.removeItem(CONFIG_KEY);localStorage.removeItem(QUEUE_KEY);CFG=null;location.reload();});
  $("#btn-open-config").addEventListener("click",()=>showConfigScreen(!!CFG&&configIsComplete(CFG)));
}
function init(){bindConfigEvents();CFG=loadConfig();if(configIsComplete(CFG)){showMainScreen();if(navigator.onLine)processQueue();}else showConfigScreen(false);if("serviceWorker" in navigator)navigator.serviceWorker.register("./sw.js").catch(()=>{});}
document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible"&&CFG&&configIsComplete(CFG))carregarPendenciasNosCards();});
document.addEventListener("DOMContentLoaded",init);
