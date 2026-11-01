// 询盘助手页（#view-inquiry）。理解、知识库调用、生成、校验都在后端 /api/round 和 /api/check，这里只负责展示。
// 包在函数里，不和队友 app.js 的全局变量（$、state）冲突。
(() => {
  const root = document.getElementById("view-inquiry");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const S = { base: "", mode: "mock", samples: [], rounds: [], cur: -1, editing: false, busy: false };
  const en = () => document.documentElement.lang.startsWith("en");
  const localized = (zh, english) => en() ? (english || zh) : zh;
  const EN_FIELDS = { title: "title_en", message: "message_en", suggestion: "suggestion_en", step: "step_en", note: "note_en", summary: "summary_en", field: "field_en" };
  const field = (item, name) => localized(item?.[name], item?.[EN_FIELDS[name]]);
  const sampleOptions = () => {
    $("iqSample").innerHTML = '<option value="">— 选择示例询盘 —</option>' +
      S.samples.map((s, i) => `<option value="${i}">${esc(localized(s.label, s.label_en))}</option>`).join("");
  };

  const LV = { red: "红灯 · 不能发，必须改", yellow: "黄灯 · 可以发，但要人工确认", green: "绿灯 · 通过" };
  const CHIP = { red: ["blocked", "红灯"], yellow: ["review", "黄灯"], green: ["ready", "绿灯"] };
  const ST = { ok: "一致", single: "单一来源", conflict: "矛盾", suspect: "可疑", image: "读图" };
  const INTENT = { price: "价格", moq: "MOQ", certificates: "证书", registration: "注册", samples: "样品",
    exclusivity: "独家代理", shipping: "物流", indication: "适应症" };
  const BUYER = { distributor: "经销商", clinic: "诊所", individual: "个人", unknown: "未知" };
  const LANG = { en: "英语", es: "西班牙语", zh: "中文", pt: "葡萄牙语", ru: "俄语" };
  const MODE = { llm: "模型", rules: "规则", kb: "知识库", template: "模板", reuse: "沿用", manual: "手改" };
  const KIND = { first: "初稿", revise: "按指令修改", manual: "手动修改" };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const toast = (m) => (window.showToast ? window.showToast(m) : null);

  async function api(path, body) {
    const opt = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    const r = await fetch(S.base + path, opt);
    const data = await r.json().catch(() => ({ error: `HTTP ${r.status}` }));
    if (!r.ok) throw new Error(data.error || `HTTP ${r.status}`);
    return data;
  }

  // 先试同源（python app/server.py 托管网站时）；不行再试本机 8766（队友用 http.server 单独起网站时）。
  async function findBackend() {
    const fromQuery = new URLSearchParams(location.search).get("api");
    const bases = [fromQuery, "", "http://127.0.0.1:8766"].filter((b) => b !== null);
    for (const b of bases) {
      try {
        const r = await fetch(b + "/api/status");
        const s = await r.json();
        if (s && s.mode) return { base: b, status: s };
      } catch (e) { /* 试下一个 */ }
    }
    return null;
  }

  async function init() {
    const found = await findBackend();
    if (!found) {
      $("iqStatus").textContent = "后端未连接";
      $("iqStatus").className = "status-chip blocked";
      $("iqOffline").hidden = false;
      return render();
    }
    S.base = found.base;
    S.mode = found.status.mode;
    $("iqStatus").textContent = S.mode === "llm" ? `模型：${found.status.model}` : "离线模板（未配置模型）";
    $("iqStatus").className = "status-chip " + (S.mode === "llm" ? "ready" : "review");
    try {
      S.samples = await api("/api/samples");
      sampleOptions();
    } catch (e) { /* 没有示例也能手动粘贴 */ }
    render();
  }

  const current = () => S.rounds[S.cur];

  async function send(path, body) {
    if (S.busy) return;
    S.busy = true;
    render();
    try {
      const r = await api(path, body);
      S.rounds = S.rounds.slice(0, S.cur + 1);
      S.rounds.push(r);
      S.cur = S.rounds.length - 1;
      S.editing = false;
      $("iqInstruction").value = "";
      toast(`第 ${S.cur + 1} 轮完成：${LV[r.level]}`);
    } catch (e) {
      alert("出错了：" + e.message);
    } finally {
      S.busy = false;
      render();
    }
  }

  const base = () => ({ inquiry: $("iqInquiry").value, channel: $("iqChannel").value, lang: $("iqLang").value });

  function runFirst() {
    if (!$("iqInquiry").value.trim()) return alert("先粘贴或选择一条询盘");
    S.rounds = [];
    S.cur = -1;
    send("/api/round", base());
  }

  function runRevise(instruction) {
    const c = current();
    if (c) send("/api/round", { ...base(), instruction, prev: { understanding: c.understanding, reply: c.reply } });
  }

  function fixInstruction() {
    const items = (current()?.findings || []).map((f) => `- ${f.rule} ${f.title}：${f.suggestion}`);
    return items.length ? "按校验意见修改：\n" + items.join("\n") : "";
  }

  const kv = (rows) => `<table class="iq-kv">${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join("")}</table>`;

  function renderUnderstanding(c) {
    if (!c) return '<p class="iq-muted">还没有运行</p>';
    const u = c.understanding;
    let html = kv([
      ["摘要", esc(localized(u.summary_zh, u.summary_en))],
      ["语言", esc(LANG[u.language] || u.language) + ` → 回复用 ${esc(LANG[u.reply_lang] || u.reply_lang)}`],
      ["国家", esc(u.country || "未识别")],
      ["买家", esc(BUYER[u.buyer_type] || u.buyer_type)],
      ["意图", esc((u.intents || []).map((i) => INTENT[i] || i).join("、") || "—")],
      ["型号", esc((u.products || []).join("、") || "未指明，按全部填充剂")],
      ["问到的用途", esc((u.asked_uses || []).join("、") || "—")],
    ]);
    const m = c.market;
    html += '<p class="iq-sub">KNOWLEDGE BASE</p>';
    if (m) html += `<div class="iq-market">目标市场：<b>${esc(localized(m.name_zh, m.name_en) || m.code)}</b> · ${esc(m.regulator || "—")} · 注册状态 <span class="status-chip ${m.status === "registered" ? "ok" : "conflict"}">${esc(m.status)}</span>${window.MB_REGISTRY?.has(m.code) ? ` <button type="button" class="text-button" data-iq-registry="${esc(m.code)}">${localized("查看注册清单", "View registration checklist")}</button>` : ""}</div>`;
    html += kv(c.refs.map((r) => [
      `${r.product.replace("HAFILLER ", "")} · ${localized(r.field, r.field_en)}`,
      `${esc(r.value)}<span class="status-chip ${esc(r.st)}">${esc(ST[r.st] || r.st)}${r.d ? " " + esc(r.d) : ""}</span>`,
    ]));
    return html;
  }

  function highlight(text, findings) {
    const chars = Array.from(text); // 后端下标按 Unicode 码点算
    const mark = new Array(chars.length).fill(null);
    for (const f of findings) for (const [s, e] of f.spans)
      for (let i = s; i < e && i < chars.length; i++)
        if (!mark[i] || (mark[i].level === "yellow" && f.level === "red")) mark[i] = f;
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
    if (!c) return '<p class="iq-muted">生成回复后，这里列出触发的规则和修改建议。</p>';
    if (!c.findings.length) return '<p class="iq-muted">没有发现问题。</p>';
    return c.findings.map((f) => `<div class="iq-finding ${f.level}"><strong><span class="iq-rule">${esc(f.rule)}</span>${esc(field(f,"title"))}</strong>
      <div>${esc(field(f,"message"))}</div><div class="iq-sugg">建议：${esc(field(f,"suggestion"))}</div></div>`).join("");
  }

  function renderTrace(c) {
    if (!c) return '<li class="iq-muted">还没有运行</li>';
    const steps = c.trace.map((t) => `<li><strong>${esc(field(t,"step"))}</strong><span class="iq-mode">${esc(MODE[t.mode] || t.mode)}</span><span class="iq-ms">${t.ms} ms</span>
      <div>${esc(field(t,"note"))}</div>${t.error ? `<span class="iq-err">错误：${esc(t.error)}</span>` : ""}</li>`).join("");
    const wall = c.wall_ms != null ? `<li><strong>本轮总用时</strong><span class="iq-ms">${c.wall_ms} ms</span><div>第一轮的理解和生成同时跑，各步加起来会比总用时长</div></li>` : "";
    return steps + wall;
  }

  function render() {
    const c = current(), has = !!c, idle = !S.busy;
    $("iqRounds").innerHTML = S.rounds.map((r, i) =>
      `<button type="button" class="iq-tab ${i === S.cur ? "active" : ""}" data-iq-round="${i}"><span class="iq-dot ${r.level}"></span>第 ${i + 1} 轮 · ${KIND[r.kind]}</button>`).join("");

    $("iqReplyView").hidden = S.editing;
    $("iqReplyEdit").hidden = !S.editing;
    $("iqReplyView").innerHTML = has ? highlight(c.reply, c.findings) : '<span class="iq-muted">选择或粘贴询盘后，点「理解并生成回复」。</span>';
    $("iqZhBox").hidden = !has;
    $("iqZh").textContent = c?.reply_zh || "（手动修改的回复没有中文对照）";
    const prev = S.rounds[S.cur - 1];
    $("iqDiffBox").hidden = !prev;
    if (prev) $("iqDiff").innerHTML = diffHtml(prev.reply, c.reply);

    const [chip, label] = has ? CHIP[c.level] : ["review", "未运行"];
    $("iqLevelChip").className = "status-chip " + chip;
    $("iqLevelChip").textContent = label;
    $("iqLevel").className = "iq-level " + (c?.level || "");
    $("iqLevel").textContent = has ? LV[c.level] : "—";
    $("iqFindings").innerHTML = renderFindings(c);
    $("iqUnderstanding").innerHTML = renderUnderstanding(c);
    $("iqTrace").innerHTML = renderTrace(c);

    $("iqMockHint").hidden = !(has && S.mode !== "llm");
    $("iqRun").disabled = !idle;
    $("iqRunText").textContent = S.busy ? "处理中…" : "理解并生成回复";
    $("iqRevise").disabled = !(idle && has && !S.editing);
    $("iqFix").disabled = !(idle && has && !S.editing && c.findings.length);
    $("iqEdit").disabled = !(idle && has);
    $("iqEdit").textContent = S.editing ? "取消编辑" : "编辑回复";
    $("iqRecheck").hidden = !S.editing;
    $("iqRisky").hidden = !S.editing;
    $("iqRecheck").disabled = !idle;
  }

  $("iqSample").addEventListener("change", (e) => {
    const s = S.samples[e.target.value];
    if (!s) return;
    $("iqInquiry").value = s.inquiry;
    $("iqChannel").value = s.channel;
    S.rounds = [];
    S.cur = -1;
    S.editing = false;
    render();
  });
  $("iqRun").addEventListener("click", runFirst);
  $("iqRevise").addEventListener("click", () => {
    const t = $("iqInstruction").value.trim();
    if (!t) return alert("先写修改要求");
    runRevise(t);
  });
  $("iqFix").addEventListener("click", () => {
    const t = fixInstruction();
    $("iqInstruction").value = t;
    runRevise(t);
  });
  $("iqEdit").addEventListener("click", () => {
    S.editing = !S.editing;
    if (S.editing) $("iqReplyEdit").value = current().reply;
    render();
  });
  $("iqRecheck").addEventListener("click", () => {
    const c = current();
    const reply = $("iqReplyEdit").value;
    if (!reply.trim()) return alert("回复是空的");
    send("/api/check", { inquiry: $("iqInquiry").value, understanding: c.understanding, reply });
  });
  $("iqRisky").addEventListener("click", () => {
    const s = S.samples.find((x) => x.inquiry.trim() === $("iqInquiry").value.trim()) || S.samples[0];
    if (!s) return;
    const box = $("iqReplyEdit");
    const at = box.value.indexOf("\n\n") >= 0 ? box.value.indexOf("\n\n") + 2 : 0;
    box.value = box.value.slice(0, at) + s.risky_edit + "\n\n" + box.value.slice(at);
  });
  $("iqRounds").addEventListener("click", (e) => {
    const tab = e.target.closest("[data-iq-round]");
    if (!tab || S.busy) return;
    S.cur = Number(tab.dataset.iqRound);
    S.editing = false;
    render();
  });
  root.addEventListener("click", (e) => {
    const link = e.target.closest("[data-iq-registry]");
    if (link) window.MB_REGISTRY?.open(link.dataset.iqRegistry);
  });

  if (location.hash === "#inquiry" && typeof window.switchView === "function") window.switchView("inquiry");
  document.addEventListener("mb:langchange", () => {
    const chosen = $("iqSample").value;
    sampleOptions();
    $("iqSample").value = chosen;
    render();
  });
  init();
})();
