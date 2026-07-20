const state = {
  atlas: null,
  cases: null,
  capabilityGroup: "all",
  capabilityRoute: "all",
  engineFilter: "all",
  query: "",
  caseFilter: "all",
  views: new Map(),
};

const viewMeta = {
  original: { label: "论文原图", stamp: "ORIGINAL / OA ARTICLE" },
  overlay: { label: "提取覆盖层", stamp: "EXTRACTION EVIDENCE" },
  recreated: { label: "数据复现图", stamp: "RECONSTRUCTED OUTPUT" },
};

const engineLabels = {
  stable: "稳定",
  candidate: "候选",
  benchmark_only: "仅基准",
  coordinate_specific: "专用坐标",
  restricted: "受限恢复",
};

const demoLabels = {
  source_mapped: "源数据映射",
  visible_geometry: "几何已提取",
  partial_visible: "局部已提取",
  oa_reference: "OA 代表图",
  no_case: "待补案例",
};

const capabilityGroups = document.querySelector("#capability-groups");
const capabilitySummary = document.querySelector("#capability-summary");
const groupTabs = document.querySelector("#group-tabs");
const engineFilters = document.querySelector("#engine-filters");
const calibrationRoutes = document.querySelector("#calibration-routes");
const caseList = document.querySelector("#case-list");
const challengeList = document.querySelector("#challenge-list");
const capabilityDialog = document.querySelector("#capability-dialog");
const imageDialog = document.querySelector("#image-dialog");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function externalLink(url, label, className = "") {
  if (!url) return escapeHtml(label);
  return `<a class="${escapeHtml(className)}" href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
}

function referenceCase(caseId) {
  return state.atlas.referenceCases.find((item) => item.id === caseId);
}

function renderCalibrationRoutes() {
  calibrationRoutes.innerHTML = state.atlas.calibrationFamilies
    .map((route, index) => {
      const active = state.capabilityRoute === route.id;
      const count = state.atlas.capabilities.filter((item) => item.calibrationFamily === route.id).length;
      const extension = route.origin !== "WebPlotDigitizer";
      return `
        <button
          class="route-card ${active ? "is-active" : ""} ${extension ? "is-extension" : ""}"
          type="button"
          data-route="${escapeHtml(route.id)}"
          aria-pressed="${active}"
        >
          <span class="route-index">${String(index + 1).padStart(2, "0")}</span>
          <strong>${escapeHtml(route.label)}</strong>
          <small>${extension ? "THU EXTENSION" : "WPD CALIBRATION"} · ${count} 类型</small>
          <p>${escapeHtml(route.description)}</p>
        </button>`;
    })
    .join("");
}

function renderGroupTabs() {
  const all = [{ id: "all", title: "全部类型", label: "All" }, ...state.atlas.groups];
  groupTabs.innerHTML = all
    .map((group) => {
      const count = group.id === "all"
        ? state.atlas.capabilities.length
        : state.atlas.capabilities.filter((item) => item.group === group.id).length;
      const active = state.capabilityGroup === group.id;
      return `
        <button
          class="group-tab ${active ? "is-active" : ""}"
          type="button"
          role="tab"
          data-group="${escapeHtml(group.id)}"
          aria-selected="${active}"
        >
          <span>${escapeHtml(group.title)}</span>
          <small>${escapeHtml(group.label)} / ${String(count).padStart(2, "0")}</small>
        </button>`;
    })
    .join("");
}

function renderEngineFilters() {
  const filters = ["all", "stable", "candidate", "benchmark_only", "coordinate_specific", "restricted"];
  engineFilters.innerHTML = filters
    .map((key) => {
      const count = key === "all"
        ? state.atlas.capabilities.length
        : state.atlas.capabilities.filter((item) => item.engineStatus === key).length;
      const active = state.engineFilter === key;
      return `
        <button
          class="engine-filter ${active ? "is-active" : ""}"
          type="button"
          data-engine="${key}"
          aria-pressed="${active}"
        >${key === "all" ? "全部" : engineLabels[key]} <sup>${count}</sup></button>`;
    })
    .join("");
}

function filteredCapabilities() {
  const query = state.query.trim().toLocaleLowerCase("zh-CN");
  return state.atlas.capabilities.filter((item) => {
    const inGroup = state.capabilityGroup === "all" || item.group === state.capabilityGroup;
    const inRoute = state.capabilityRoute === "all" || item.calibrationFamily === state.capabilityRoute;
    const inEngine = state.engineFilter === "all" || item.engineStatus === state.engineFilter;
    const haystack = [item.label, item.id, ...item.aliases, item.recoverableRepresentation]
      .join(" ")
      .toLocaleLowerCase("zh-CN");
    return inGroup && inRoute && inEngine && (!query || haystack.includes(query));
  });
}

function capabilityCard(item) {
  const caseItem = item.caseId ? referenceCase(item.caseId) : null;
  const visual = item.thumbnail
    ? `<img src="${escapeHtml(item.thumbnail)}" alt="${escapeHtml(item.label)} 的真实论文代表图裁剪" loading="lazy" />`
    : `<div class="capability-placeholder" aria-hidden="true"><span>${escapeHtml(item.label.slice(0, 2).toUpperCase())}</span><i></i><i></i><i></i></div>`;
  const aliases = item.aliases.slice(0, 3).map((alias) => `<span>${escapeHtml(alias)}</span>`).join("");

  return `
    <button
      class="capability-card"
      type="button"
      data-capability="${escapeHtml(item.id)}"
      data-engine-status="${escapeHtml(item.engineStatus)}"
      data-demo-status="${escapeHtml(item.demoStatus)}"
    >
      <span class="capability-visual">${visual}</span>
      <span class="capability-card-body">
        <span class="capability-status-row">
          <span class="engine-badge status-${escapeHtml(item.engineStatus)}">${escapeHtml(engineLabels[item.engineStatus])}</span>
          <span class="demo-badge">${escapeHtml(demoLabels[item.demoStatus])}</span>
        </span>
        <strong>${escapeHtml(item.label)}</strong>
        <span class="alias-row">${aliases}</span>
        <span class="recover-line"><b>可恢复</b>${escapeHtml(item.recoverableRepresentation)}</span>
        <span class="case-line">${caseItem ? `${escapeHtml(caseItem.journal)} · ${escapeHtml(caseItem.figure)}` : "尚无精确匹配的 OA 代表图"}</span>
      </span>
    </button>`;
}

function renderCapabilities() {
  const filtered = filteredCapabilities();
  const grouped = state.atlas.groups
    .map((group) => ({ ...group, items: filtered.filter((item) => item.group === group.id) }))
    .filter((group) => group.items.length);

  const activeFilters = [
    state.capabilityGroup !== "all",
    state.capabilityRoute !== "all",
    state.engineFilter !== "all",
    Boolean(state.query.trim()),
  ].some(Boolean);

  capabilitySummary.innerHTML = `
    <span>显示 <strong>${filtered.length}</strong> / ${state.atlas.capabilities.length} 种提取类型；${filtered.filter((item) => item.caseId).length} 种有真实 OA 代表图。</span>
    ${activeFilters ? '<button type="button" class="clear-capability-filters">清除筛选</button>' : ""}`;

  if (!grouped.length) {
    capabilityGroups.innerHTML = '<div class="error-card">没有匹配的图表类型。请清除筛选或换一个关键词。</div>';
    return;
  }

  capabilityGroups.innerHTML = grouped
    .map(
      (group, index) => `
        <section class="capability-group" aria-labelledby="group-${escapeHtml(group.id)}">
          <header>
            <span>${String(index + 1).padStart(2, "0")}</span>
            <div>
              <h3 id="group-${escapeHtml(group.id)}">${escapeHtml(group.title)}</h3>
              <p>${escapeHtml(group.label)} · ${group.items.length} types · route ${escapeHtml(group.route)}</p>
            </div>
          </header>
          <div class="capability-grid">${group.items.map(capabilityCard).join("")}</div>
        </section>`,
    )
    .join("");
}

function openCapability(item) {
  const caseItem = item.caseId ? referenceCase(item.caseId) : null;
  const engineDefinition = state.atlas.statusDefinitions.engine[item.engineStatus];
  const demoDefinition = state.atlas.statusDefinitions.demo[item.demoStatus];
  const route = state.atlas.calibrationFamilies.find((candidate) => candidate.id === item.calibrationFamily);
  const visual = item.thumbnail
    ? `<button class="dialog-image-button" type="button"><img src="${escapeHtml(item.thumbnail)}" alt="${escapeHtml(item.label)} 真实论文代表图" /></button>`
    : `<div class="dialog-no-case">尚未选定与此子类型精确匹配的 OA 论文代表图。</div>`;
  const source = caseItem
    ? `
      <dl class="dialog-source">
        <div><dt>论文</dt><dd>${externalLink(caseItem.articleUrl, caseItem.articleTitle)}</dd></div>
        <div><dt>作者 / 年</dt><dd>${escapeHtml(caseItem.authors)} · ${escapeHtml(caseItem.year)}</dd></div>
        <div><dt>期刊 / 图号</dt><dd>${externalLink(caseItem.figureUrl, `${caseItem.journal} · ${caseItem.figure}`)}</dd></div>
        <div><dt>DOI</dt><dd>${escapeHtml(caseItem.doi)}</dd></div>
        <div><dt>许可</dt><dd>${externalLink(caseItem.licenseUrl, caseItem.license)}</dd></div>
      </dl>
      <div class="dialog-actions">
        ${externalLink(caseItem.articleUrl, "打开原文 ↗")}
        ${externalLink(caseItem.report, "查看证据报告 ↗")}
      </div>`
    : "";

  document.querySelector("#capability-dialog-content").innerHTML = `
    <div class="capability-dialog-grid">
      <div class="capability-dialog-visual">${visual}</div>
      <div class="capability-dialog-copy">
        <p class="dialog-kicker">${escapeHtml(route.label)} / ${escapeHtml(route.origin)}</p>
        <h2>${escapeHtml(item.label)}</h2>
        <p class="dialog-aliases">${escapeHtml(item.aliases.join(" · "))}</p>
        <div class="dialog-statuses">
          <span class="engine-badge status-${escapeHtml(item.engineStatus)}">引擎：${escapeHtml(engineLabels[item.engineStatus])}</span>
          <span class="demo-badge">案例：${escapeHtml(demoLabels[item.demoStatus])}</span>
        </div>
        <div class="recoverability">
          <div><span>可恢复表示</span><strong>${escapeHtml(item.recoverableRepresentation)}</strong></div>
          <div><span>不能从像素推出</span><strong>${escapeHtml(item.nonRecoverable)}</strong></div>
        </div>
        <details>
          <summary>状态解释</summary>
          <p>${escapeHtml(engineDefinition)}</p>
          <p>${escapeHtml(demoDefinition)}</p>
          <p>${escapeHtml(route.description)}</p>
        </details>
        ${source}
      </div>
    </div>`;
  capabilityDialog.showModal();
}

function caseTemplate(item, index) {
  const activeView = state.views.get(item.id) || "original";
  const activeAsset = item.assets[activeView];
  const activeMeta = viewMeta[activeView];
  const tabs = Object.entries(viewMeta)
    .map(
      ([key, meta]) => `
        <button
          class="view-tab ${key === activeView ? "is-active" : ""}"
          type="button"
          data-case="${escapeHtml(item.id)}"
          data-view="${key}"
          aria-pressed="${key === activeView}"
        >${escapeHtml(meta.label)}</button>`,
    )
    .join("");

  const metrics = item.metrics
    .map((metric) => `<div class="metric"><strong title="${escapeHtml(metric.value)}">${escapeHtml(metric.value)}</strong><span>${escapeHtml(metric.label)}</span></div>`)
    .join("");
  const chartTypes = item.chartTypes.map((type) => `<span class="type-chip">${escapeHtml(type)}</span>`).join("");

  return `
    <article class="case-card" data-verification="${escapeHtml(item.verification)}" data-id="${escapeHtml(item.id)}">
      <div class="case-visual">
        <div class="view-toolbar" role="group" aria-label="${escapeHtml(item.title)} 的图像视图">
          ${tabs}
          <span class="scope-chip">${escapeHtml(item.scope)}</span>
        </div>
        <div class="image-stage" data-stamp="${escapeHtml(activeMeta.stamp)}">
          <img
            class="case-image"
            src="${escapeHtml(activeAsset)}"
            alt="${escapeHtml(item.title)} — ${escapeHtml(activeMeta.label)}"
            data-title="${escapeHtml(item.articleTitle)} · ${escapeHtml(item.figure)} · ${escapeHtml(activeMeta.label)}"
            loading="${index === 0 ? "eager" : "lazy"}"
          />
        </div>
        <p class="image-caption"><span>${escapeHtml(activeMeta.label)}</span><span>${escapeHtml(item.journal)} · ${escapeHtml(item.figure)}</span></p>
      </div>
      <div class="case-copy">
        <div class="case-head">
          <div class="case-eyebrow"><span>${escapeHtml(item.eyebrow)}</span><span class="case-number">${String(index + 1).padStart(2, "0")}</span></div>
          <span class="status-chip">${escapeHtml(item.verificationLabel)}</span>
          <h3>${escapeHtml(item.title)}</h3>
          <p class="case-summary">${escapeHtml(item.summary)}</p>
        </div>
        <div class="metrics">${metrics}</div>
        <dl class="meta-list">
          <div><dt>论文</dt><dd>${externalLink(item.articleUrl, item.articleTitle)}</dd></div>
          <div><dt>作者 / 年</dt><dd>${escapeHtml(item.authors)} · ${escapeHtml(item.year)}</dd></div>
          <div><dt>图号</dt><dd>${externalLink(item.figureUrl, item.figure)}</dd></div>
          <div><dt>DOI</dt><dd>${escapeHtml(item.doi)}</dd></div>
          <div><dt>许可</dt><dd>${externalLink(item.licenseUrl, item.license)}</dd></div>
        </dl>
        <div class="chart-types" aria-label="图表类型">${chartTypes}</div>
        <div class="case-actions">
          <a href="${escapeHtml(item.assets.data)}" download>下载 CSV</a>
          <a href="${escapeHtml(item.assets.report)}" target="_blank">查看报告</a>
          <a href="${escapeHtml(item.assets.sourceData)}" download>官方附件</a>
        </div>
      </div>
    </article>`;
}

function renderCases() {
  const filtered = state.cases.cases.filter(
    (item) => state.caseFilter === "all" || item.verification === state.caseFilter,
  );
  caseList.innerHTML = filtered.length
    ? filtered.map(caseTemplate).join("")
    : '<div class="error-card">当前筛选没有案例。</div>';
}

function renderChallenges() {
  challengeList.innerHTML = state.cases.challengeQueue
    .map(
      (item) => `
        <article class="challenge-card">
          <img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.title)} — 论文原图" loading="lazy" />
          <div class="challenge-copy">
            <div>
              <span class="status-chip">RESEARCH QUEUE</span>
              <h3>${escapeHtml(item.title)}</h3>
              <p>${escapeHtml(item.note)}</p>
            </div>
            ${externalLink(item.articleUrl, `${item.journal} · ${item.year} · ${item.figure} ↗`)}
          </div>
        </article>`,
    )
    .join("");
}

function updateStats() {
  const counts = state.atlas.counts;
  document.querySelector("#hero-stats").innerHTML = `
    <span><strong>${String(counts.types).padStart(2, "0")}</strong> 提取类型</span>
    <span><strong>${String(counts.groups).padStart(2, "0")}</strong> 能力类别</span>
    <span><strong>${String(counts.oaRepresentatives).padStart(2, "0")}</strong> OA 代表入口</span>
    <span><strong>${counts.wpdCalibrationFamilies}+${counts.extensionRoutes}</strong> 校准与扩展路由</span>`;
}

function activateCaseFilter(button) {
  state.caseFilter = button.dataset.filter;
  document.querySelectorAll(".filter").forEach((candidate) => {
    const active = candidate === button;
    candidate.classList.toggle("is-active", active);
    candidate.setAttribute("aria-pressed", String(active));
  });
  renderCases();
}

function activateView(button) {
  state.views.set(button.dataset.case, button.dataset.view);
  renderCases();
  document.querySelector(`[data-id="${CSS.escape(button.dataset.case)}"]`)?.scrollIntoView({ block: "nearest" });
}

function openImage(image) {
  imageDialog.querySelector("img").src = image.src;
  imageDialog.querySelector("img").alt = image.alt;
  imageDialog.querySelector("p").textContent = image.dataset.title || image.alt;
  imageDialog.showModal();
}

function resetCapabilityFilters() {
  state.capabilityGroup = "all";
  state.capabilityRoute = "all";
  state.engineFilter = "all";
  state.query = "";
  document.querySelector("#capability-search").value = "";
  renderCalibrationRoutes();
  renderGroupTabs();
  renderEngineFilters();
  renderCapabilities();
}

document.addEventListener("click", (event) => {
  const group = event.target.closest(".group-tab");
  if (group) {
    state.capabilityGroup = group.dataset.group;
    renderGroupTabs();
    renderCapabilities();
  }

  const route = event.target.closest(".route-card");
  if (route) {
    state.capabilityRoute = state.capabilityRoute === route.dataset.route ? "all" : route.dataset.route;
    renderCalibrationRoutes();
    renderCapabilities();
  }

  const engine = event.target.closest(".engine-filter");
  if (engine) {
    state.engineFilter = engine.dataset.engine;
    renderEngineFilters();
    renderCapabilities();
  }

  const capability = event.target.closest(".capability-card");
  if (capability) {
    const item = state.atlas.capabilities.find((candidate) => candidate.id === capability.dataset.capability);
    if (item) openCapability(item);
  }

  if (event.target.closest(".clear-capability-filters")) resetCapabilityFilters();

  const caseFilter = event.target.closest(".filter");
  if (caseFilter) activateCaseFilter(caseFilter);

  const tab = event.target.closest(".view-tab");
  if (tab) activateView(tab);

  const image = event.target.closest(".case-image");
  if (image) openImage(image);

  const dialogImage = event.target.closest(".dialog-image-button img");
  if (dialogImage) openImage(dialogImage);
});

document.querySelector("#capability-search").addEventListener("input", (event) => {
  state.query = event.target.value;
  renderCapabilities();
});

capabilityDialog.querySelector(".dialog-close").addEventListener("click", () => capabilityDialog.close());
capabilityDialog.addEventListener("click", (event) => {
  if (event.target === capabilityDialog) capabilityDialog.close();
});
imageDialog.querySelector(".dialog-close").addEventListener("click", () => imageDialog.close());
imageDialog.addEventListener("click", (event) => {
  if (event.target === imageDialog) imageDialog.close();
});

Promise.all([
  fetch("data/capabilities.json").then((response) => {
    if (!response.ok) throw new Error(`能力清单加载失败：${response.status}`);
    return response.json();
  }),
  fetch("data/cases.json").then((response) => {
    if (!response.ok) throw new Error(`案例清单加载失败：${response.status}`);
    return response.json();
  }),
])
  .then(([atlas, cases]) => {
    state.atlas = atlas;
    state.cases = cases;
    cases.cases.forEach((item) => state.views.set(item.id, "original"));
    updateStats();
    renderCalibrationRoutes();
    renderGroupTabs();
    renderEngineFilters();
    renderCapabilities();
    renderCases();
    renderChallenges();
  })
  .catch((error) => {
    console.error(error);
    capabilityGroups.innerHTML = `
      <div class="error-card">能力清单未加载。请通过本地 HTTP 服务打开画廊，而不是直接双击 HTML 文件。</div>`;
    caseList.innerHTML = '<div class="error-card">案例清单未加载。</div>';
  });
