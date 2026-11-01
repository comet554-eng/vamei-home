// 注册清单页（#view-registry）：四国注册对照、材料任务、官方核查入口。数据来自 /api/registry（kb/registry.json）。
// 自己往导航和 .page-content 里插按钮和页面；整块带 data-i18n-skip，中英文由本脚本按 documentElement.lang 切换。
// 任务的适用性、责任人、日期、状态、证据位置只存在本机 localStorage，不上传。
(() => {
  const content = document.querySelector(".page-content");
  if (!content) return;
  const STORE = "mb-registry-v1";
  const FIELDS = ["applicability", "owner", "due", "status", "evidence"];
  const MAX_LEN = { owner: 60, evidence: 300 };
  const GROUPS = ["ALL", "SA", "BR", "DE", "TR"];

  const T = {
    zh: {
      nav: "注册清单", sub: "沙特、巴西、德国、土耳其的医疗器械注册对照和材料任务。任务进度只保存在本机浏览器。",
      draft: "工作初稿", noticeTitle: "工作初稿，不是最终申报清单",
      noticeExtra: "执行前须按各国官方现行要求复核。本页内容不构成法规意见。",
      compareTitle: "四国对照", markets: (n) => `${n} 个市场`, viewTasks: (n) => `查看 ${n} 项任务`,
      scopeTitle: "适用范围与待补充", progressTitle: "任务进度", total: "合计",
      market: "市场", stage: "阶段", status: "状态", all: "全部",
      shown: (n, total) => `显示 ${n} / ${total} 项`, saved: "修改自动保存在本机浏览器，不会上传。",
      export: "导出 CSV", clear: (n) => (n ? `清除本地修改（${n}）` : "清除本地修改"),
      confirmClear: "清除本机保存的全部修改？适用性、责任人、计划日期、状态和证据位置会恢复为表格原值。",
      cleared: "已清除本地修改", exported: (n) => `已导出 ${n} 项任务`, empty: "没有符合条件的任务",
      cols: ["编号", "市场", "阶段", "材料/任务", "适用说明", "依据", "适用性", "责任人", "计划日期", "状态", "证据位置"],
      ownerPh: "姓名", evidencePh: "文件夹或链接", refTitle: (id) => `跳到来源 ${id}`,
      srcCols: ["编号", "市场", "机构/法规", "官方链接", "复核主题"],
      loading: "正在读取注册清单…",
      error: (e) => `注册清单读取失败：${e.message}。请在项目根目录运行 python app/server.py，再打开 http://127.0.0.1:8766/ 。`,
      file: "四国注册清单.csv",
    },
    en: {
      nav: "Registration Checklist",
      sub: "Medical device registration requirements and document tasks for Saudi Arabia, Brazil, Germany and Türkiye. Task progress is saved only in this browser.",
      draft: "Working draft", noticeTitle: "Working draft, not a final submission checklist",
      noticeExtra: "Re-verify against each authority's current requirements before acting. This page is not regulatory advice.",
      compareTitle: "Market comparison", markets: (n) => `${n} markets`, viewTasks: (n) => `View ${n} tasks`,
      scopeTitle: "Scope and open items", progressTitle: "Task progress", total: "Total",
      market: "Market", stage: "Stage", status: "Status", all: "All",
      shown: (n, total) => `Showing ${n} of ${total}`, saved: "Edits are saved automatically in this browser and are not uploaded.",
      export: "Export CSV", clear: (n) => (n ? `Clear local edits (${n})` : "Clear local edits"),
      confirmClear: "Clear all edits saved in this browser? Applicability, owner, due date, status and evidence will revert to the spreadsheet values.",
      cleared: "Local edits cleared", exported: (n) => `Exported ${n} tasks`, empty: "No tasks match these filters",
      cols: ["No.", "Market", "Stage", "Document / task", "Notes", "Sources", "Applicability", "Owner", "Due date", "Status", "Evidence location"],
      ownerPh: "Name", evidencePh: "Folder or link", refTitle: (id) => `Go to source ${id}`,
      srcCols: ["ID", "Market", "Authority / regulation", "Official link", "What to verify"],
      loading: "Loading the registration checklist…",
      error: (e) => `Could not load the registration checklist (${e.status || "network error"}). Run python app/server.py in the project root, then open http://127.0.0.1:8766/ .`,
      file: "registration-checklist.csv",
    },
  };

  const isEn = () => document.documentElement.lang.startsWith("en");
  const t = () => T[isEn() ? "en" : "zh"];
  const L = (p) => (p ? (isEn() ? p.en : p.zh) : "");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const S = { data: null, error: null, filters: { market: "", stage: "", status: "" }, edits: loadEdits() };

  // ---- 挂到页面上 ----
  const nav = document.createElement("button");
  nav.className = "nav-item";
  nav.dataset.view = "registry";
  nav.setAttribute("data-i18n-skip", "");
  nav.innerHTML = '<i data-lucide="clipboard-list"></i><span></span>';
  const before = document.querySelector('.nav-item[data-view="content"]');
  if (before) before.before(nav);
  else document.querySelector('.nav-item[data-view="inquiry"]')?.after(nav);

  const root = document.createElement("section");
  root.className = "view";
  root.id = "view-registry";
  root.setAttribute("data-i18n-skip", "");
  const contentView = document.getElementById("view-content");
  if (contentView) contentView.before(root);
  else content.append(root);

  // ---- 本地修改 ----
  function loadEdits() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORE) || "{}");
      const out = {};
      for (const [id, e] of Object.entries(raw && typeof raw === "object" ? raw : {})) {
        const clean = {};
        for (const f of FIELDS) if (typeof e?.[f] === "string") clean[f] = e[f].slice(0, MAX_LEN[f] || 20);
        if (Object.keys(clean).length) out[id] = clean;
      }
      return out;
    } catch {
      return {};
    }
  }
  function saveEdits() {
    try {
      if (Object.keys(S.edits).length) localStorage.setItem(STORE, JSON.stringify(S.edits));
      else localStorage.removeItem(STORE);
    } catch { /* 隐私模式等写不进去时只在本页生效 */ }
  }
  const val = (task, f) => (S.edits[task.id]?.[f] !== undefined ? S.edits[task.id][f] : task[f]);
  function setEdit(id, f, v) {
    const task = S.data.tasks.find((x) => x.id === id);
    if (!task) return;
    const e = { ...S.edits[id] };
    if (v === task[f]) delete e[f];
    else e[f] = v;
    if (Object.keys(e).length) S.edits[id] = e;
    else delete S.edits[id];
    saveEdits();
  }
  const validCode = (table, v) => Object.prototype.hasOwnProperty.call(S.data.codes[table], v);

  // ---- 取数据：先同源，再本机 8766（队友单独起网站时），和询盘助手一致 ----
  async function load() {
    const fromQuery = new URLSearchParams(location.search).get("api");
    const bases = [fromQuery, "", "http://127.0.0.1:8766"].filter((b) => b !== null);
    let last = new Error("network error");
    for (const b of bases) {
      try {
        const r = await fetch(b + "/api/registry", { cache: "no-store" });
        const data = await r.json().catch(() => ({}));
        if (r.ok && Array.isArray(data.tasks)) return data;
        last = Object.assign(new Error(data.error || `HTTP ${r.status}`), { status: `HTTP ${r.status}` });
      } catch { /* 换下一个地址 */ }
    }
    throw last;
  }

  // ---- 渲染 ----
  const marketName = (code) => L(S.data.codes.market[code]) || code;
  const counts = (code) => {
    const c = { todo: 0, doing: 0, done: 0, blocked: 0 };
    for (const x of S.data.tasks) if (!code || x.market === code) c[val(x, "status")] = (c[val(x, "status")] || 0) + 1;
    return c;
  };
  const options = (pairs, cur) => pairs.map(([v, label]) => `<option value="${esc(v)}"${v === cur ? " selected" : ""}>${esc(label)}</option>`).join("");
  const codeOptions = (table, cur) => options(Object.entries(S.data.codes[table]).map(([k, p]) => [k, L(p)]), cur);
  const linkify = (s) => esc(s).replace(/https:\/\/[^\s<]+/g, (u) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`);

  function visible() {
    const f = S.filters;
    return S.data.tasks.filter((x) => (!f.market || x.market === f.market) && (!f.stage || x.stage.zh === f.stage)
      && (!f.status || val(x, "status") === f.status));
  }
  function stageOptions() {
    const seen = new Map();
    for (const x of S.data.tasks) if (!S.filters.market || x.market === S.filters.market) seen.set(x.stage.zh, L(x.stage));
    if (!seen.has(S.filters.stage)) S.filters.stage = "";
    return options([["", t().all], ...seen], S.filters.stage);
  }

  function render() {
    const tx = t();
    nav.querySelector("span").textContent = tx.nav;
    syncBreadcrumb();
    if (!S.data) {
      root.innerHTML = `<div class="page-heading compact"><div><p class="eyebrow">REGISTRATION CHECKLIST</p><h1>${esc(tx.nav)}</h1></div></div>
        <div class="rg-notice${S.error ? " rg-error" : ""}" role="status">${esc(S.error ? tx.error(S.error) : tx.loading)}</div>`;
      return;
    }
    const d = S.data, m = d.meta;
    const cards = d.markets.map((mk) => {
      const n = d.tasks.filter((x) => x.market === mk.code).length;
      return `<article class="rg-card${S.filters.market === mk.code ? " active" : ""}" data-rg-card="${esc(mk.code)}">
        <div class="rg-card-head"><strong>${esc(isEn() ? mk.name_en : mk.name_zh)}</strong><span class="panel-badge">${esc(mk.code)}</span></div>
        <dl class="rg-dims">${d.dimensions.map((dim) => `<dt>${esc(L(dim))}</dt><dd>${esc(L(mk[dim.key]))}</dd>`).join("")}</dl>
        <button type="button" class="text-button rg-card-link" data-rg-market="${esc(mk.code)}">${esc(tx.viewTasks(n))} <i data-lucide="arrow-down"></i></button>
      </article>`;
    }).join("");
    root.innerHTML = `
      <div class="page-heading compact">
        <div><p class="eyebrow">REGISTRATION CHECKLIST</p><h1>${esc(L(m.title))}</h1><p class="subheading">${esc(tx.sub)}</p></div>
        <div class="heading-actions"><span class="status-chip review">${esc(tx.draft)}</span></div>
      </div>
      <div class="rg-notice" role="note"><i data-lucide="triangle-alert"></i><div><strong>${esc(tx.noticeTitle)}</strong>
        <p>${esc(L(m.disclaimer))}</p><p>${esc(tx.noticeExtra)}</p></div></div>
      <section class="panel rg-panel" id="rgCompare">
        <div class="panel-heading"><div><p class="section-kicker">MARKET COMPARISON</p><h2>${esc(tx.compareTitle)}</h2></div>
          <span class="panel-badge">${esc(tx.markets(d.markets.length))}</span></div>
        <div class="rg-cards">${cards}</div>
      </section>
      <div class="rg-row">
        <section class="panel rg-panel">
          <div class="panel-heading"><div><p class="section-kicker">SCOPE</p><h2>${esc(tx.scopeTitle)}</h2></div></div>
          <ul class="rg-scope">${[m.assumption, m.pending, m.no_fees].map((p) => `<li>${esc(L(p))}</li>`).join("")}</ul>
        </section>
        <section class="panel rg-panel">
          <div class="panel-heading"><div><p class="section-kicker">PROGRESS</p><h2>${esc(tx.progressTitle)}</h2></div></div>
          <div class="table-scroll rg-stats"><table><thead><tr><th>${esc(tx.market)}</th>${Object.values(d.codes.status).map((p) => `<th>${esc(L(p))}</th>`).join("")}<th>${esc(tx.total)}</th></tr></thead>
            <tbody id="rgStats"></tbody></table></div>
        </section>
      </div>
      <section class="panel rg-panel rg-tasks" id="rgTasks">
        <div class="panel-heading"><div><p class="section-kicker">DOCUMENTS &amp; TASKS</p><h2>${esc(L(m.tasks_title))}</h2></div>
          <span class="panel-badge" id="rgShown"></span></div>
        <div class="rg-progress-note"><i data-lucide="info"></i><span>${esc(L(m.progress_note))}</span></div>
        <div class="rg-toolbar">
          <label class="field-label">${esc(tx.market)}<select data-rg-filter="market">${options([["", tx.all], ...GROUPS.map((c) => [c, marketName(c)])], S.filters.market)}</select></label>
          <label class="field-label">${esc(tx.stage)}<select data-rg-filter="stage" id="rgStage">${stageOptions()}</select></label>
          <label class="field-label">${esc(tx.status)}<select data-rg-filter="status">${options([["", tx.all], ...Object.entries(d.codes.status).map(([k, p]) => [k, L(p)])], S.filters.status)}</select></label>
          <div class="rg-actions"><button type="button" class="button secondary" id="rgExport"><i data-lucide="download"></i>${esc(tx.export)}</button>
            <button type="button" class="button secondary" id="rgClear"></button></div>
        </div>
        <p class="rg-saved">${esc(tx.saved)}</p>
        <div class="table-scroll"><table>
          <colgroup><col style="width:56px"><col style="width:96px"><col style="width:110px"><col style="width:250px"><col style="width:230px"><col style="width:120px"><col style="width:130px"><col style="width:120px"><col style="width:150px"><col style="width:120px"><col style="width:170px"></colgroup>
          <thead><tr>${tx.cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody id="rgRows"></tbody></table></div>
      </section>
      <section class="panel rg-panel rg-sources" id="rgSources">
        <div class="panel-heading"><div><p class="section-kicker">OFFICIAL SOURCES</p><h2>${esc(L(m.sources_title))}</h2></div>
          <span class="panel-badge">${d.sources.length}</span></div>
        <div class="rg-progress-note"><i data-lucide="info"></i><span>${esc(L(m.sources_note))}</span></div>
        <div class="table-scroll"><table><thead><tr>${tx.srcCols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>
          ${d.sources.map((s) => `<tr id="rg-src-${esc(s.id)}"><td><strong>${esc(s.id)}</strong></td><td>${esc(L(s.market_label))}</td><td>${esc(L(s.org))}</td>
            <td class="rg-wrap">${/^https?:\/\//.test(s.url) ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url)}</a>` : esc(s.url)}</td>
            <td class="rg-wrap">${linkify(L(s.topic))}</td></tr>`).join("")}
        </tbody></table></div>
      </section>`;
    renderStats();
    renderRows();
    window.lucide?.createIcons();
  }

  function renderStats() {
    const cell = (n, code) => `<td>${n ? `<span class="status-chip rg-${code}">${n}</span>` : '<span class="rg-zero">0</span>'}</td>`;
    const row = (label, c, cls = "") => `<tr${cls}><td><strong>${esc(label)}</strong></td>${Object.keys(S.data.codes.status).map((k) => cell(c[k] || 0, k)).join("")}
      <td>${Object.values(c).reduce((a, b) => a + b, 0)}</td></tr>`;
    root.querySelector("#rgStats").innerHTML = GROUPS.map((g) => row(marketName(g), counts(g))).join("") + row(t().total, counts(""), ' class="rg-total"');
    const n = Object.keys(S.edits).length, clear = root.querySelector("#rgClear");
    clear.textContent = t().clear(n);
    clear.disabled = !n;
  }

  function renderRows() {
    const tx = t(), rows = visible();
    root.querySelector("#rgShown").textContent = tx.shown(rows.length, S.data.tasks.length);
    root.querySelector("#rgRows").innerHTML = rows.map((x) => {
      const id = esc(x.id), st = val(x, "status"), aria = (i) => esc(`${tx.cols[i]} ${x.id}`);
      return `<tr id="rg-task-${id}">
        <td><strong>${id}</strong></td><td>${esc(marketName(x.market))}</td><td>${esc(L(x.stage))}</td>
        <td class="rg-wrap rg-task">${esc(L(x.task))}</td><td class="rg-wrap rg-note">${esc(L(x.note))}</td>
        <td><div class="rg-refs">${x.refs.map((r) => `<button type="button" class="rg-ref" data-rg-ref="${esc(r)}" title="${esc(tx.refTitle(r))}">${esc(r)}</button>`).join("")}</div></td>
        <td><select class="rg-input" data-id="${id}" data-rg-field="applicability" aria-label="${aria(6)}">${codeOptions("applicability", val(x, "applicability"))}</select></td>
        <td><input class="rg-input" data-id="${id}" data-rg-field="owner" maxlength="${MAX_LEN.owner}" placeholder="${esc(tx.ownerPh)}" value="${esc(val(x, "owner"))}" aria-label="${aria(7)}" /></td>
        <td><input class="rg-input" type="date" data-id="${id}" data-rg-field="due" value="${esc(val(x, "due"))}" aria-label="${aria(8)}" /></td>
        <td><select class="rg-input rg-st-${esc(st)}" data-id="${id}" data-rg-field="status" aria-label="${aria(9)}">${codeOptions("status", st)}</select></td>
        <td><input class="rg-input" data-id="${id}" data-rg-field="evidence" maxlength="${MAX_LEN.evidence}" placeholder="${esc(tx.evidencePh)}" value="${esc(val(x, "evidence"))}" aria-label="${aria(10)}" /></td>
      </tr>`;
    }).join("") || `<tr><td colspan="11" class="rg-empty">${esc(tx.empty)}</td></tr>`;
  }

  function markCards() {
    root.querySelectorAll("[data-rg-card]").forEach((c) => c.classList.toggle("active", c.dataset.rgCard === S.filters.market));
  }
  function applyFilters() {
    root.querySelectorAll("[data-rg-filter]").forEach((sel) => { sel.value = S.filters[sel.dataset.rgFilter]; });
    const stage = root.querySelector("#rgStage");
    if (stage) stage.innerHTML = stageOptions();
    if (root.querySelector("#rgRows")) renderRows();
    markCards();
  }
  function syncBreadcrumb() {
    const bc = document.getElementById("breadcrumbCurrent");
    if (bc && root.classList.contains("active")) bc.textContent = t().nav;
  }

  // ---- 交互 ----
  root.addEventListener("change", (ev) => {
    const f = ev.target.dataset.rgFilter;
    if (!f) return;
    S.filters[f] = ev.target.value;
    applyFilters();
  });
  root.addEventListener("input", (ev) => {
    const el = ev.target, f = el.dataset.rgField;
    if (!f || !S.data) return;
    let v = el.value;
    if ((f === "applicability" || f === "status") && !validCode(f, v)) return;
    if (MAX_LEN[f]) v = v.slice(0, MAX_LEN[f]);
    setEdit(el.dataset.id, f, v);
    if (f === "status") {
      el.className = `rg-input rg-st-${v}`;
    }
    renderStats();
  });
  root.addEventListener("click", (ev) => {
    const ref = ev.target.closest("[data-rg-ref]");
    if (ref) {
      const row = document.getElementById(`rg-src-${ref.dataset.rgRef}`);
      if (row) {
        row.scrollIntoView({ behavior: "smooth", block: "center" });
        row.classList.remove("rg-flash");
        void row.offsetWidth;  // 连点同一个来源也能重新闪
        row.classList.add("rg-flash");
      }
      return;
    }
    const mk = ev.target.closest("[data-rg-market]");
    if (mk) {
      S.filters = { market: mk.dataset.rgMarket, stage: "", status: "" };
      applyFilters();
      root.querySelector("#rgTasks")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (ev.target.closest("#rgExport")) return exportCsv();
    if (ev.target.closest("#rgClear") && Object.keys(S.edits).length && window.confirm(t().confirmClear)) {
      S.edits = {};
      saveEdits();
      renderRows();
      renderStats();
      window.showToast?.(t().cleared);
    }
  });

  function exportCsv() {
    const tx = t(), rows = visible();
    const cell = (v) => {
      let s = String(v ?? "");
      if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;  // 防止 Excel 把输入当公式执行
      return `"${s.replace(/"/g, '""')}"`;
    };
    const lines = [tx.cols, ...rows.map((x) => [x.id, marketName(x.market), L(x.stage), L(x.task), L(x.note), x.refs.join(" / "),
      L(S.data.codes.applicability[val(x, "applicability")]), val(x, "owner"), val(x, "due"),
      L(S.data.codes.status[val(x, "status")]), val(x, "evidence")])];
    const blob = new Blob(["﻿" + lines.map((r) => r.map(cell).join(",")).join("\r\n") + "\r\n"], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob), a = document.createElement("a");
    a.href = url;
    a.download = tx.file;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    window.showToast?.(tx.exported(rows.length));
  }

  // ---- 给询盘助手联动 ----
  const codes = () => (S.data ? S.data.markets.map((x) => x.code) : ["SA", "BR", "DE", "TR"]);
  window.MB_REGISTRY = {
    has: (code) => codes().includes(String(code || "").toUpperCase()),
    open(code) {
      code = String(code || "").toUpperCase();
      if (!this.has(code)) return false;
      S.filters = { market: code, stage: "", status: "" };
      if (typeof window.switchView === "function") window.switchView("registry");
      applyFilters();
      // switchView 会平滑滚回顶部，稍后再滚到对照部分
      setTimeout(() => document.getElementById("rgCompare")?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
      return true;
    },
  };

  // 切语言：整页重画，筛选条件在 S.filters，输入已实时存进 S.edits，都不会丢；面包屑等 i18n.js 处理完再改
  document.addEventListener("mb:langchange", () => {
    render();
    setTimeout(syncBreadcrumb, 0);
  });

  render();
  window.lucide?.createIcons();
  if (location.hash === "#registry" && typeof window.switchView === "function") window.switchView("registry");
  load().then((data) => {
    S.data = data;
    S.error = null;
    // 本机存的修改：任务已删或代码值不认识的丢掉，日期只认 YYYY-MM-DD
    for (const [id, e] of Object.entries(S.edits)) {
      if (!data.tasks.some((x) => x.id === id)) delete S.edits[id];
      else for (const f of Object.keys(e)) {
        if (((f === "applicability" || f === "status") && !validCode(f, e[f])) || (f === "due" && e[f] && !/^\d{4}-\d{2}-\d{2}$/.test(e[f]))) delete e[f];
      }
      if (S.edits[id] && !Object.keys(S.edits[id]).length) delete S.edits[id];
    }
  }, (e) => { S.error = e; }).finally(render);
})();
