const state = {
  currentView: "overview",
  customers: [
    { name: "K-Health", email: "procurement@k-health.kr", country: "韩国", source: "阿里国际站", level: "A", contract: "第一年 · 72%", action: "确认首年采购额", owner: "林晓", avatar: "K" },
    { name: "Medline Gulf", email: "buying@medline.ae", country: "阿联酋", source: "老客转介绍", level: "B", contract: "正常履约", action: "回复样品询盘", owner: "周宁", avatar: "M" },
    { name: "HealthPlus", email: "info@healthplus.sa", country: "沙特", source: "阿里国际站", level: "C", contract: "资料待补", action: "等待营业执照", owner: "林晓", avatar: "H" },
    { name: "Al Noor Medical", email: "sales@alnoor.qa", country: "卡塔尔", source: "展会线索", level: "B", contract: "正常履约", action: "安排季度回访", owner: "周宁", avatar: "A" },
    { name: "VitaCare", email: "purchasing@vitacare.sg", country: "新加坡", source: "官网表单", level: "A", contract: "次年需求翻倍", action: "更新采购预测", owner: "林晓", avatar: "V" },
  ],
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function refreshIcons() {
  if (window.lucide) window.lucide.createIcons();
}

function showToast(message) {
  const toast = $("#toast");
  toast.querySelector("span").textContent = message;
  toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2400);
}

function switchView(viewName) {
  state.currentView = viewName;
  $$(".view").forEach((view) => view.classList.toggle("active", view.id === `view-${viewName}`));
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === viewName));
  const activeNav = $(`.nav-item[data-view="${viewName}"]`);
  $("#breadcrumbCurrent").textContent = activeNav?.querySelector("span")?.textContent || "业务总览";
  $("#sidebar").classList.remove("open");
  window.scrollTo({ top: 0, behavior: "smooth" });
  refreshIcons();
}

function renderCustomers(filter = "all", search = "") {
  const normalized = search.trim().toLowerCase();
  const filtered = state.customers.filter((customer) => {
    const matchesSearch = !normalized || [customer.name, customer.country, customer.email, customer.source].some((value) => value.toLowerCase().includes(normalized));
    const matchesFilter = filter === "all" || (filter === "risk" && customer.contract.includes("待")) || (filter === "followup" && customer.action);
    return matchesSearch && matchesFilter;
  });
  $("#customerRows").innerHTML = filtered.map((customer) => `
    <tr>
      <td><span class="customer-avatar">${customer.avatar}</span><span class="customer-name"><strong>${customer.name}</strong><span>${customer.email}</span></span></td>
      <td><strong>${customer.country}</strong><span class="table-sub">${customer.source}</span></td>
      <td><span class="level ${customer.level.toLowerCase()}">${customer.level} 级</span></td>
      <td><span class="contract-state"><i data-lucide="${customer.contract.includes("待") ? "clock-3" : "check-circle-2"}"></i>${customer.contract}</span></td>
      <td><span class="next-action">${customer.action}</span></td>
      <td><span class="owner"><span class="owner-dot">${customer.owner.slice(0, 1)}</span>${customer.owner}</span></td>
      <td><button class="icon-button quiet" title="查看客户" aria-label="查看客户" data-customer="${customer.name}"><i data-lucide="chevron-right"></i></button></td>
    </tr>
  `).join("") || `<tr><td colspan="7" style="text-align:center;padding:34px;color:#8a999c">没有找到匹配的客户</td></tr>`;
  refreshIcons();
}

function openModal() {
  $("#customerModal").hidden = false;
  $("#customerModal input")?.focus();
}

function closeModal() {
  $("#customerModal").hidden = true;
}

function generateContent() {
  const product = $("#productName").value.trim() || "Medical Disposable";
  const market = $("#targetMarket").value;
  const params = $("#productParams").value.trim();
  $("#previewTitle").textContent = `${product} | Reliable Medical Disposable for ${market.split(" / ")[0]} Buyers`;
  $("#previewBullets").innerHTML = [
    "DEHP-free and latex-free materials for safer clinical use",
    "EO sterilized with individually sealed packaging",
    "Consistent performance designed for high-volume procurement",
    "Flexible construction supports comfortable clinical handling",
    `Quality documentation available for ${market} registration review`,
  ].map((item) => `<li>${item}</li>`).join("");
  $("#previewDescription").textContent = `${product} is designed for hospitals, clinics, and distributors seeking dependable medical consumables. Built around ${params || "consistent quality and practical clinical performance"}, it helps overseas buyers simplify procurement while maintaining reliable product standards.`;
  showToast("英文上架包已生成");
  refreshIcons();
}

function runCompliance() {
  const button = $("#runMatch");
  button.disabled = true;
  button.innerHTML = '<i data-lucide="loader-circle"></i>正在比对...';
  refreshIcons();
  window.setTimeout(() => {
    $("#matchScore").textContent = "82%";
    $("#resultTime").textContent = "刚刚更新";
    button.disabled = false;
    button.innerHTML = '<i data-lucide="scan-search"></i>开始智能比对';
    showToast("比对完成，已标记 1 项人工准备资料");
    refreshIcons();
  }, 750);
}

function copyText() {
  const content = [$("#previewTitle").textContent, ...Array.from($("#previewBullets li")).map((item) => `• ${item.textContent}`), $("#previewDescription").textContent].join("\n");
  navigator.clipboard?.writeText(content);
  showToast("上架文案已复制");
}

function exportBrief() {
  const text = "MedBridge 海外销售中心简报\n\n活跃客户：128\n待回访任务：16\n合规资料可用率：86%\n库存缺口预警：2\n\n本简报由工作台演示原型生成。";
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "medbridge-sales-brief.txt";
  link.click();
  URL.revokeObjectURL(url);
  showToast("简报已导出");
}

document.addEventListener("click", (event) => {
  const nav = event.target.closest("[data-view]");
  if (nav) switchView(nav.dataset.view);
  const viewLink = event.target.closest("[data-view-link]");
  if (viewLink) switchView(viewLink.dataset.viewLink);
  if (event.target.closest(".notification-button")) {
    const button = $(".notification-button");
    const panel = $("#notificationPanel");
    const willOpen = panel.hidden;
    panel.hidden = !willOpen;
    button.setAttribute("aria-expanded", String(willOpen));
  }
  const action = event.target.closest("[data-action]");
  if (action?.dataset.action === "new-customer") openModal();
  if (action?.dataset.action === "export") exportBrief();
  if (action?.dataset.action === "run-compliance") switchView("compliance");
  if (event.target.closest("[data-close-modal]")) closeModal();
  const filter = event.target.closest("[data-customer-filter]");
  if (filter) {
    $$(".segmented-control button").forEach((button) => button.classList.remove("active"));
    filter.classList.add("active");
    renderCustomers(filter.dataset.customerFilter, $("#customerSearch").value);
  }
  if (event.target.closest(".complete-task")) {
    const row = event.target.closest(".task-row");
    row.style.opacity = ".45";
    row.querySelector("strong").style.textDecoration = "line-through";
    showToast("任务已标记完成");
  }
});

$("#clearNotifications").addEventListener("click", () => {
  $$("#notificationPanel .notification-item").forEach((item) => { item.hidden = true; });
  $("#notificationPanel .notification-empty").hidden = false;
  $(".notification-dot").hidden = true;
  showToast("通知已全部标为已读");
});

function closeNotifications() {
  $("#notificationPanel").hidden = true;
  $(".notification-button").setAttribute("aria-expanded", "false");
}
document.addEventListener("click", (event) => {
  if (!event.target.closest(".notification-button, #notificationPanel") || event.target.closest(".notification-item")) closeNotifications();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !$("#notificationPanel").hidden) {
    closeNotifications();
    $(".notification-button").focus();
  }
});

$("#mobileMenu").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
$("#customerSearch").addEventListener("input", (event) => {
  const activeFilter = $(".segmented-control button.active")?.dataset.customerFilter || "all";
  renderCustomers(activeFilter, event.target.value);
});
$("#customerForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const name = form.get("name");
  state.customers.unshift({
    name,
    email: form.get("email"),
    country: form.get("country"),
    source: "手动录入",
    level: form.get("level"),
    contract: "待建立",
    action: "创建首次回访",
    owner: "林晓",
    avatar: name.slice(0, 1).toUpperCase(),
  });
  event.target.reset();
  closeModal();
  renderCustomers();
  switchView("customers");
  showToast(`${name} 已加入客户资产`);
});
$("#generateContent").addEventListener("click", generateContent);
$("#copyText").addEventListener("click", copyText);
$("#copyContent").addEventListener("click", copyText);
$("#runMatch").addEventListener("click", runCompliance);
$("#globalSearch").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.target.value.trim()) {
    $("#customerSearch").value = event.target.value;
    renderCustomers("all", event.target.value);
    switchView("customers");
  }
});
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    $("#globalSearch").focus();
  }
  if (event.key === "Escape") closeModal();
});

renderCustomers();
refreshIcons();
