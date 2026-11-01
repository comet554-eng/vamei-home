// 页面只负责展示和收集输入；理解、知识库调用、生成、校验都在后端 /api/round 和 /api/check。
const $ = (id) => document.getElementById(id);
const state = { rounds: [], cur: -1, samples: [], mode: "mock", editing: false, busy: false };

const LV = { red: "不能发，必须改", yellow: "可以发，但要人工确认", green: "通过" };
const ST = { ok: "一致", single: "单一来源", conflict: "矛盾", suspect: "可疑", image: "读图" };
const INTENT = { price: "价格", moq: "MOQ", certificates: "证书", registration: "注册", samples: "样品",
  exclusivity: "独家代理", shipping: "物流", indication: "适应症" };
const BUYER = { distributor: "经销商", clinic: "诊所", individual: "个人", unknown: "未知" };
const LANG = { en: "英语", es: "西班牙语", zh: "中文", pt: "葡萄牙语", ru: "俄语" };
const MODE = { llm: "模型", rules: "规则", kb: "知识库", template: "模板", reuse: "沿用", manual: "手改" };
const KIND = { first: "初稿", revise: "按指令修改", manual: "手动修改" };

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function api(path, body) {
  const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
  if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
  return data;
}

async function init() {
  try {
    const s = await api("/api/status");
    state.mode = s.mode;
    $("status").textContent = s.mode === "llm" ? `模型：${s.provider} · ${s.model}` : "离线模板（未配置模型）";
  } catch (e) {
    $("status").textContent = "后端未连接";
  }
  try {
    state.samples = await api("/api/samples");
    $("sample").innerHTML = state.samples.map((s, i) => `<option value="${i}">${esc(s.label)}</option>`).join("");
  } catch (e) { /* 没有示例也能手动粘贴 */ }
  render();
}

function current() { return state.rounds[state.cur]; }

async function send(path, body) {
  if (state.busy) return;
  state.busy = true;
  render();
  try {
    const r = await api(path, body);
    state.rounds = state.rounds.slice(0, state.cur + 1);
    state.rounds.push(r);
    state.cur = state.rounds.length - 1;
    state.editing = false;
    $("instruction").value = "";
  } catch (e) {
    alert("出错了：" + e.message);
  } finally {
    state.busy = false;
    render();
  }
}

function base() {
  return { inquiry: $("inquiry").value, channel: $("channel").value, lang: $("lang").value };
}

function runFirst() {
  if (!$("inquiry").value.trim()) return alert("先粘贴或载入一条询盘");
  state.rounds = [];
  state.cur = -1;
  send("/api/round", base());
}

function runRevise(instruction) {
  const c = current();
  if (!c) return;
  send("/api/round", { ...base(), instruction, prev: { understanding: c.understanding, reply: c.reply } });
}

function runCheck() {
  const c = current();
  if (!c) return;
  send("/api/check", { inquiry: $("inquiry").value, understanding: c.understanding, reply: $("replyEdit").value });
}

function fixInstruction() {
  const c = current();
  const items = (c?.findings || []).map((f) => `- ${f.rule} ${f.title}：${f.suggestion}`);
  return items.length ? "按校验意见修改：\n" + items.join("\n") : "";
}

function riskyText() {
  const s = state.samples.find((x) => x.inquiry.trim() === $("inquiry").value.trim()) || state.samples[0];
  return s ? s.risky_edit : "";
}

function kv(rows) {
  return `<table class="kv">${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join("")}</table>`;
}

function renderUnderstanding(u) {
  if (!u) return '<span class="muted">还没有运行</span>';
  return kv([
    ["摘要", esc(u.summary_zh)],
    ["语言", esc(LANG[u.language] || u.language) + ` → 回复用 ${esc(LANG[u.reply_lang] || u.reply_lang)}`],
    ["国家", esc(u.country || "未识别")],
    ["买家", esc(BUYER[u.buyer_type] || u.buyer_type)],
    ["意图", esc((u.intents || []).map((i) => INTENT[i] || i).join("、") || "—")],
    ["型号", esc((u.products || []).join("、") || "未指明，按全部填充剂")],
    ["问到的用途", esc((u.asked_uses || []).join("、") || "—")],
  ]);
}

function renderRefs(c) {
  if (!c) return '<span class="muted">还没有运行</span>';
  const m = c.market;
  const head = m ? `<div class="market">目标市场：<b>${esc(m.name_zh || m.code)}</b> · ${esc(m.regulator || "—")} · 注册状态 <span class="st st-${m.status === "registered" ? "ok" : "conflict"}">${esc(m.status)}</span></div>` : "";
  const rows = c.refs.map((r) => [
    `${r.product.replace("HAFILLER ", "")} · ${r.field}`,
    `${esc(r.value)} <span class="st st-${esc(r.st)}">${esc(ST[r.st] || r.st)}${r.d ? " " + esc(r.d) : ""}</span>`,
  ]);
  return head + kv(rows);
}

function highlight(text, findings) {
  const chars = Array.from(text); // 后端下标按 Unicode 码点算
  const mark = new Array(chars.length).fill(null);
  for (const f of findings) {
    for (const [s, e] of f.spans) {
      for (let i = s; i < e && i < chars.length; i++) {
        if (!mark[i] || (mark[i].level === "yellow" && f.level === "red")) mark[i] = f;
      }
    }
  }
  let html = "", i = 0;
  while (i < chars.length) {
    const f = mark[i];
    let j = i;
    while (j < chars.length && mark[j] === f) j++;
    const seg = esc(chars.slice(i, j).join(""));
    html += f ? `<mark class="${f.level}" title="${esc(f.rule + " " + f.title)}">${seg}<sup>${esc(f.rule)}</sup></mark>` : seg;
    i = j;
  }
  return html;
}

function diffHtml(a, b) {
  const A = a.split(/(\s+)/), B = b.split(/(\s+)/);
  if (A.length * B.length > 4e6) return esc(b);
  const dp = Array.from({ length: A.length + 1 }, () => new Uint16Array(B.length + 1));
  for (let i = A.length - 1; i >= 0; i--)
    for (let j = B.length - 1; j >= 0; j--)
      dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  let i = 0, j = 0, out = "";
  while (i < A.length || j < B.length) {
    if (i < A.length && j < B.length && A[i] === B[j]) { out += esc(A[i]); i++; j++; }
    else if (j < B.length && (i >= A.length || dp[i][j + 1] >= dp[i + 1][j])) { out += `<ins>${esc(B[j])}</ins>`; j++; }
    else { out += `<del>${esc(A[i])}</del>`; i++; }
  }
  return out;
}

function renderFindings(c) {
  if (!c) return "";
  if (!c.findings.length) return '<p class="muted">没有发现问题。</p>';
  return c.findings.map((f) => `<div class="finding ${f.level}"><b><span class="rule">${esc(f.rule)}</span>${esc(f.title)}</b>
    <div>${esc(f.message)}</div><div class="sugg">建议：${esc(f.suggestion)}</div></div>`).join("");
}

function renderTrace(c) {
  if (!c) return "";
  return c.trace.map((t) => `<li><b>${esc(t.step)}</b><span class="mode">${esc(MODE[t.mode] || t.mode)}</span>${t.ms} ms
    <div>${esc(t.note)}</div>${t.error ? `<span class="err">错误：${esc(t.error)}</span>` : ""}</li>`).join("")
    + (c.wall_ms != null ? `<li><b>本轮总用时</b>${c.wall_ms} ms<div>第一轮的理解和生成同时跑，所以各步加起来会比总用时长</div></li>` : "");
}

function render() {
  const c = current();
  const has = !!c;
  $("rounds").innerHTML = state.rounds.map((r, i) =>
    `<span class="tab ${i === state.cur ? "active" : ""}" data-i="${i}"><span class="dot dot-${r.level}"></span>第 ${i + 1} 轮 · ${KIND[r.kind]}</span>`).join("");

  $("understanding").innerHTML = renderUnderstanding(c?.understanding);
  $("kbrefs").innerHTML = renderRefs(c);

  $("replyView").classList.toggle("hidden", state.editing);
  $("replyEdit").classList.toggle("hidden", !state.editing);
  if (has) {
    $("replyView").classList.remove("muted");
    $("replyView").innerHTML = highlight(c.reply, c.findings);
  } else {
    $("replyView").classList.add("muted");
    $("replyView").textContent = "还没有回复";
  }
  $("replyZh").textContent = c?.reply_zh || "（手动修改的回复没有中文对照）";
  $("zhBox").classList.toggle("hidden", !has);
  const prev = state.rounds[state.cur - 1];
  $("diffBox").classList.toggle("hidden", !prev);
  if (prev) $("diff").innerHTML = diffHtml(prev.reply, c.reply);

  $("level").className = "level " + (c?.level || "");
  $("level").textContent = has ? `${{ red: "红", yellow: "黄", green: "绿" }[c.level]} · ${LV[c.level]}` : "—";
  $("findings").innerHTML = renderFindings(c);
  $("trace").innerHTML = renderTrace(c);

  $("mockHint").classList.toggle("hidden", !(has && state.mode !== "llm"));
  const idle = !state.busy;
  $("run").disabled = !idle;
  $("run").textContent = state.busy ? "处理中…" : "理解并生成回复";
  $("revise").disabled = !(idle && has && !state.editing);
  $("fix").disabled = !(idle && has && !state.editing && c.findings.length);
  $("edit").disabled = !(idle && has);
  $("edit").textContent = state.editing ? "取消编辑" : "编辑回复";
  $("recheck").classList.toggle("hidden", !state.editing);
  $("risky").classList.toggle("hidden", !state.editing);
  $("recheck").disabled = !idle;
}

$("load").onclick = () => {
  const s = state.samples[$("sample").value];
  if (!s) return;
  $("inquiry").value = s.inquiry;
  $("channel").value = s.channel;
  state.rounds = [];
  state.cur = -1;
  state.editing = false;
  render();
};
$("run").onclick = runFirst;
$("revise").onclick = () => {
  const t = $("instruction").value.trim();
  if (!t) return alert("先写修改要求");
  runRevise(t);
};
$("fix").onclick = () => {
  const t = fixInstruction();
  $("instruction").value = t;
  runRevise(t);
};
$("edit").onclick = () => {
  state.editing = !state.editing;
  if (state.editing) $("replyEdit").value = current().reply;
  render();
};
$("recheck").onclick = () => {
  if (!$("replyEdit").value.trim()) return alert("回复是空的");
  runCheck();
};
$("risky").onclick = () => {
  const box = $("replyEdit");
  const t = riskyText();
  const at = box.value.indexOf("\n\n") >= 0 ? box.value.indexOf("\n\n") + 2 : 0;
  box.value = box.value.slice(0, at) + t + "\n\n" + box.value.slice(at);
};
$("rounds").onclick = (e) => {
  const tab = e.target.closest(".tab");
  if (!tab || state.busy) return;
  state.cur = Number(tab.dataset.i);
  state.editing = false;
  render();
};

init();
