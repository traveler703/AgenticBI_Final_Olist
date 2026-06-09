import "./styles.css";
import { newChart, downloadChart } from "./charts.js";
import { marked } from "marked";

const $ = (s) => document.querySelector(s);
const el = (t, c, h) => { const n = document.createElement(t); if (c) n.className = c; if (h != null) n.innerHTML = h; return n; };

// LLM 偶尔把表格压成一行或写出 ::---: 这类非法分隔行，渲染前修复，否则 marked 不识别为表格
function mdToHtml(content) {
  let s = String(content || "");
  if (/\|\s*:?-{2,}:?\s*\|/.test(s)) {
    s = s.replace(/\| +\|/g, "|\n|");                         // 行内表格的行边界 "| |" 拆成换行
  }
  s = s.replace(/\|\s*:{2,}/g, "|:").replace(/:{2,}\s*\|/g, ":|"); // ::---: 修成 :---:
  return marked.parse(s);
}

const ICON = {
  copy: '<svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M16 1H4a2 2 0 00-2 2v12h2V3h12V1zm3 4H8a2 2 0 00-2 2v14a2 2 0 002 2h11a2 2 0 002-2V7a2 2 0 00-2-2zm0 16H8V7h11v14z"/></svg>',
  view: '<svg viewBox="0 0 24 24" width="15" height="15"><path fill="currentColor" d="M3 5h8v2H5v12h12v-6h2v8H3V5zm10-2h8v8h-2V6.4l-7.3 7.3-1.4-1.4L17.6 5H13V3z"/></svg>',
  download: '<svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M12 16l-5-5 1.4-1.4L11 12.2V3h2v9.2l2.6-2.6L17 11l-5 5zm-7 2h14v2H5v-2z"/></svg>',
  zoom: '<svg viewBox="0 0 24 24" width="14" height="14"><path fill="currentColor" d="M15 3h6v6h-2V6.4l-3.3 3.3-1.4-1.4L17.6 5H15V3zM3 15h2v2.6l3.3-3.3 1.4 1.4L6.4 19H9v2H3v-6z"/></svg>',
};

const SUGGESTIONS = [
  "2017 年 GMV 是多少？按月和各州排名的趋势怎样？",
  "2017 年哪个州的销售额最高？交付准时率是多少？哪种支付方式最受欢迎？",
  "平台整体准时交付率是多少？哪些州延迟最严重？",
  "哪种支付方式最受欢迎？平均分期数是多少？",
  "产品的重量、尺寸与运费之间有什么关系？",
  "在地图上展示各州销售额的地理分布。",
  "根据历史订单趋势，预测未来 6 周的销售额，并给出趋势解读。",
  "为什么某些州的平均配送时长显著高于全国均值？",
  "如何降低巴西东北部地区的高退货率？请给出具体的运营改进方案。",
  "基于全部分析结果，给出平台 3 个月内的三大优先改进策略。",
  "对差评评论做情感分析与高频词，并生成词云。",
  "如果将 Top20 高差评卖家的商品统一下架，平台整体评分预估提升多少？",
  "扫描近期数据，是否有某州订单量骤降或差评率突升的异常？",
];

const state = { convId: null, provider: "cloud", model: null, models: null, busy: false, abort: null };

async function init() {
  bindEvents();
  renderSuggestions();
  await loadModels();
  await loadConversations();
  refreshRouteStat();
}

function bindEvents() {
  const input = $("#input");
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
  $("#sendBtn").addEventListener("click", send);
  $("#newChat").addEventListener("click", startNewChat);
  $("#toggleArtifacts").addEventListener("click", () => $("#artifacts").classList.toggle("open"));
  $("#closeArtifacts").addEventListener("click", () => $("#artifacts").classList.remove("open"));
  $("#refreshLogBtn").addEventListener("click", showRefreshLog);
  $("#modalClose").addEventListener("click", closeModal);
  $("#modalMask").addEventListener("click", (e) => { if (e.target === $("#modalMask")) closeModal(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  $("#providerSelect").addEventListener("change", onProviderChange);
  $("#modelSelect").addEventListener("change", () => { state.model = $("#modelSelect").value; });
  $("#convTitle").addEventListener("click", editTitle);
}

// ---------- models ----------
async function loadModels() {
  try {
    const d = await (await fetch("/api/models")).json();
    state.provider = d.default_provider || "cloud"; state.models = d.providers;
    const ps = $("#providerSelect"); ps.innerHTML = "";
    for (const [name, info] of Object.entries(d.providers)) {
      const o = el("option", null, name === "cloud" ? "云 API" : "本地 Ollama");
      o.value = name; if (!info.available) o.textContent += "·未连接"; ps.appendChild(o);
    }
    ps.value = state.provider; onProviderChange();
  } catch (e) { console.error(e); }
}
function onProviderChange() {
  state.provider = $("#providerSelect").value;
  const info = state.models?.[state.provider] || { models: [], default: null };
  const ms = $("#modelSelect"); ms.innerHTML = "";
  (info.models || []).forEach((m) => { const o = el("option", null, m); o.value = m; ms.appendChild(o); });
  ms.value = info.default || (info.models || [])[0] || ""; state.model = ms.value;
}

// ---------- conversations ----------
async function loadConversations() {
  const d = await (await fetch("/api/conversations")).json();
  const list = $("#convList"); list.innerHTML = "";
  (d.conversations || []).forEach((c) => {
    const item = el("div", "conv-item" + (c.id === state.convId ? " active" : ""));
    item.dataset.id = c.id;
    item.appendChild(el("span", "conv-name", c.title || "新对话"));
    const del = el("span", "del", "✕"); del.title = "删除";
    del.addEventListener("click", (e) => { e.stopPropagation(); deleteConversation(c.id); });
    item.appendChild(del);
    item.addEventListener("click", () => selectConversation(c.id));
    list.appendChild(item);
  });
}

async function selectConversation(id) {
  cancelInflight();
  state.convId = id;
  const d = await (await fetch(`/api/conversations/${id}/messages`)).json();
  $("#convTitle").textContent = d.conversation?.title || "对话";
  const box = $("#messages"); box.innerHTML = "";
  (d.messages || []).forEach((m) => {
    if (m.role === "user") addUserMessage(m.content);
    else renderAssistant(m.content, m.meta || {});
  });
  await loadConversations();
  scrollBottom();
  const last = [...box.querySelectorAll(".msg.assistant")].pop();
  if (last && _hasArt(last._art)) showArtifacts(last._art, true);
  else clearPanel();
}

function clearPanel() {
  $("#artBody").innerHTML = `<div class="art-empty">对话生成图表后在此展示，点击图表可放大、下载。</div>`;
  $("#artifacts").classList.remove("open");
}

function startNewChat() {
  cancelInflight();
  state.convId = null;
  $("#convTitle").textContent = "新对话";
  $("#messages").innerHTML = `<div class="welcome"><div class="welcome-logo">◆</div><h1>Olist 电商运营分析</h1><p>多智能体 · 自主推理 · 预聚合加速。问我销售、配送、评分、预测、What-if…</p></div>`;
  clearPanel();
  loadConversations();
}

async function deleteConversation(id) {
  await fetch(`/api/conversations/${id}`, { method: "DELETE" });
  if (id === state.convId) startNewChat();
  loadConversations();
}

function editTitle() {
  if (!state.convId) return;
  const span = $("#convTitle");
  const input = el("input", "title-input"); input.value = span.textContent;
  span.replaceWith(input); input.focus(); input.select();
  const save = async () => {
    const title = input.value.trim() || span.textContent;
    await fetch(`/api/conversations/${state.convId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title }) });
    span.textContent = title; input.replaceWith(span); loadConversations();
  };
  input.addEventListener("blur", save);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.blur(); });
}

// ---------- send / SSE ----------
function renderSuggestions() {
  const box = $("#suggestions");
  SUGGESTIONS.forEach((s) => {
    const chip = el("div", "chip", s); chip.title = s;
    chip.addEventListener("click", () => { $("#input").value = s; send(); });
    box.appendChild(chip);
  });
}

async function send() {
  if (state.busy) return;
  const input = $("#input"); const text = input.value.trim(); if (!text) return;
  input.value = ""; input.style.height = "auto";
  $("#messages .welcome")?.remove();
  state.busy = true; $("#sendBtn").disabled = true;
  addUserMessage(text);
  const asst = addAssistantShell();
  const statusEl = asst.querySelector(".status-line span:last-child");
  const trailEl = asst._trail;
  const ac = new AbortController(); state.abort = ac;

  try {
    const resp = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: ac.signal,
      body: JSON.stringify({ message: text, conversation_id: state.convId, provider: state.provider, model: state.model }),
    });
    const reader = resp.body.getReader(); const dec = new TextDecoder(); let buf = "";
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      const parts = buf.split("\n\n"); buf = parts.pop();
      for (const p of parts) {
        const line = p.split("\n").find((l) => l.startsWith("data:")); if (!line) continue;
        let o; try { o = JSON.parse(line.slice(5).trim()); } catch { continue; }
        handleEvent(o, { asst, statusEl, trailEl });
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") asst.querySelector(".body").innerHTML = `<div class="bubble" style="color:var(--red)">请求失败：${e.message}</div>`;
  } finally {
    if (state.abort === ac) { state.abort = null; state.busy = false; $("#sendBtn").disabled = false; }
    refreshRouteStat();
  }
}

// 中止进行中的请求并解锁发送（新建会话 / 切换会话时调用）
function cancelInflight() {
  if (state.abort) { state.abort.abort(); state.abort = null; }
  state.busy = false; $("#sendBtn").disabled = false;
}

function handleEvent(o, ctx) {
  const { event, data } = o;
  if (event === "conversation") {
    if (data.is_new) { state.convId = data.id; loadConversations(); }
  } else if (event === "status") {
    if (ctx.trailEl && ctx.statusEl.textContent && ctx.statusEl.textContent !== "正在分析…")
      ctx.trailEl.textContent = "✓ " + ctx.statusEl.textContent;
    ctx.statusEl.textContent = data.text || "";
    scrollBottom();
  } else if (event === "done") {
    finishAssistant(ctx.asst, data);
    if (data.title) { $("#convTitle").textContent = data.title; loadConversations(); }
  } else if (event === "error") {
    ctx.asst.querySelector(".body").innerHTML = `<div class="bubble" style="color:var(--red)">出错：${data.message}</div>`;
  }
}

// ---------- message DOM ----------
function addUserMessage(text) {
  const m = el("div", "msg user");
  m.innerHTML = `<div class="avatar">你</div><div class="body"><div class="bubble"></div></div>`;
  m.querySelector(".bubble").textContent = text;
  $("#messages").appendChild(m); scrollBottom(); return m;
}
function addAssistantShell() {
  const m = el("div", "msg assistant");
  m.innerHTML = `<div class="avatar">AI</div><div class="body">
    <div class="status-line"><span class="spinner"></span><span>正在分析…</span></div>
    <div class="status-trail"></div></div>`;
  m._trail = m.querySelector(".status-trail");
  $("#messages").appendChild(m); scrollBottom(); return m;
}
function renderAssistant(content, meta) {
  const m = el("div", "msg assistant");
  m.innerHTML = `<div class="avatar">AI</div><div class="body"><div class="bubble">${mdToHtml(content)}</div></div>`;
  m._art = { charts: meta.charts || [], queries: meta.queries || [], anomalies: meta.anomalies || [] };
  attachActions(m, content);
  $("#messages").appendChild(m); return m;
}
function finishAssistant(m, data) {
  const body = m.querySelector(".body"); body.innerHTML = `<div class="bubble">${mdToHtml(data.answer)}</div>`;
  m._art = { charts: data.charts || [], queries: data.queries || [], anomalies: data.anomalies || [] };
  attachActions(m, data.answer || "");
  scrollBottom();
  if (_hasArt(m._art)) showArtifacts(m._art, true);
}
function _hasArt(a) { return a && (a.charts?.length || a.queries?.length || a.anomalies?.length); }
function attachActions(m, text) {
  const acts = el("div", "msg-actions");
  const copy = el("button", null, ICON.copy); copy.title = "复制";
  copy.addEventListener("click", () => { navigator.clipboard.writeText(text); copy.classList.add("on"); setTimeout(() => copy.classList.remove("on"), 800); });
  const view = el("button", null, ICON.view); view.title = "查看本轮图表与 SQL";
  view.addEventListener("click", () => {
    showArtifacts(m._art, true);
    view.classList.add("on"); setTimeout(() => view.classList.remove("on"), 700);
  });
  acts.appendChild(copy);
  if (_hasArt(m._art)) acts.appendChild(view);
  m.querySelector(".body").appendChild(acts);
}

// ---------- artifacts panel ----------
function showArtifacts(art, open) {
  const body = $("#artBody"); body.innerHTML = "";
  if (!art || (!art.charts?.length && !art.queries?.length && !art.anomalies?.length)) {
    body.innerHTML = `<div class="art-empty">本轮没有图表与查询。</div>`;
  } else {
    if (art.anomalies?.length) {
      body.appendChild(el("div", "art-section-label", "异常预警"));
      art.anomalies.slice(0, 8).forEach((a) => {
        const c = el("div", `anomaly-card ${a.severity}`);
        c.innerHTML = `<span class="sev ${a.severity}">${a.severity === "high" ? "高" : "中"}</span><b>${a.type}</b> · ${a.scope} — ${a.detail}`;
        body.appendChild(c);
      });
    }
    if (art.charts?.length) {
      body.appendChild(el("div", "art-section-label", "图表"));
      art.charts.forEach((ch) => mountChart(body, ch));
    }
    if (art.queries?.length) {
      body.appendChild(el("div", "art-section-label", "本次查询 · SQL / 命中表 / 耗时"));
      art.queries.forEach((q) => {
        const card = el("div", "query-card");
        const meta = el("div", "query-meta");
        if (q.route === "MV") meta.appendChild(el("span", "badge mv", `⚡ ${q.matched_view}`));
        else meta.appendChild(el("span", "badge base", "↩ 基础表"));
        meta.appendChild(el("span", "badge ms", `${q.elapsed_ms ?? "-"} ms`));
        const copy = el("button", "sql-copy", ICON.copy); copy.title = "复制 SQL";
        copy.addEventListener("click", () => {
          navigator.clipboard.writeText(q.sql || "");
          copy.classList.add("on"); setTimeout(() => copy.classList.remove("on"), 800);
        });
        meta.appendChild(copy);
        card.appendChild(meta);
        card.appendChild(el("pre", null, escapeHtml(q.sql || "")));
        body.appendChild(card);
      });
    }
  }
  if (open) $("#artifacts").classList.add("open");
}

function mountChart(parent, ch) {
  const card = el("div", "chart-card");
  const acts = el("div", "acts");
  const dl = el("button", null, ICON.download); dl.title = "下载 PNG";
  const zm = el("button", null, ICON.zoom); zm.title = "放大";
  acts.appendChild(dl); acts.appendChild(zm); card.appendChild(acts);
  const box = el("div", "chart-box"); card.appendChild(box);
  parent.appendChild(card);
  const inst = newChart(box, ch.option);
  new ResizeObserver(() => inst.resize()).observe(box);
  dl.addEventListener("click", (e) => { e.stopPropagation(); downloadChart(inst, ch.title); });
  zm.addEventListener("click", (e) => { e.stopPropagation(); openChartModal(ch); });
  card.addEventListener("click", () => openChartModal(ch));
}

// ---------- modal ----------
function openChartModal(ch) {
  $("#modalTitle").style.display = "none"; // 图表自带居中标题，放大视图不再重复左上角标题
  const body = $("#modalBody"); body.innerHTML = "";
  const box = el("div", "chart-box"); body.appendChild(box);
  $("#modalMask").classList.add("open");
  setTimeout(() => { const inst = newChart(box, ch.option); new ResizeObserver(() => inst.resize()).observe(box); }, 50);
}
async function showRefreshLog() {
  $("#modalTitle").style.display = "";
  $("#modalTitle").textContent = "预聚合刷新历史（mv_refresh_log）";
  const body = $("#modalBody"); body.innerHTML = "加载中…";
  try {
    const d = await (await fetch("/api/refresh_log")).json();
    const rows = d.rows || [];
    body.innerHTML = `<table class="loglist"><thead><tr><th>预聚合表</th><th>刷新时间</th><th>源行数</th><th>结果行数</th><th>耗时(ms)</th></tr></thead><tbody>${rows.map((x) => `<tr><td>${x.mv_name}</td><td>${x.refreshed_at}</td><td>${(x.source_rows || 0).toLocaleString()}</td><td>${(x.result_rows || 0).toLocaleString()}</td><td>${x.elapsed_ms}</td></tr>`).join("")}</tbody></table>`;
  } catch (e) { body.innerHTML = "加载失败：" + e.message; }
  $("#modalMask").classList.add("open");
}
function closeModal() { $("#modalMask").classList.remove("open"); $("#modalBody").innerHTML = ""; }

// ---------- misc ----------
async function refreshRouteStat() {
  try {
    const d = await (await fetch("/api/route_stats")).json();
    $("#routeStat").textContent = `⚡ 视图命中 ${(d.mv_hit_rate * 100 || 0).toFixed(0)}%（${d.total || 0}）`;
  } catch { }
}
function scrollBottom() { const b = $("#messages"); b.scrollTop = b.scrollHeight; }
function escapeHtml(s) { return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }

init();
