let DATA = { entries: [], clusters: [] };
let BLOCKED = new Set();
let showCensored = localStorage.getItem("codeslang.showCensored") === "1";
let activeLetter = "All";

const grid = document.getElementById("grid");
const empty = document.getElementById("empty");
const searchEl = document.getElementById("search");
const clusterEl = document.getElementById("cluster");
const azEl = document.getElementById("az");
const resultLine = document.getElementById("result-line");
const countLine = document.getElementById("count-line");
const showCensoredEl = document.getElementById("show-censored");
const censoredCountEl = document.getElementById("censored-count");

function isBlocked(word) {
  return BLOCKED.has((word || "").toLowerCase());
}

function wordLink(word) {
  return "word.html?w=" + encodeURIComponent(word);
}

function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return ""; }
}

function clusterLabel(id) {
  return id === null || id === undefined ? "uncategorized" : "cluster " + id;
}

function visibleEntries() {
  if (showCensored) return DATA.entries;
  return DATA.entries.filter((e) => !isBlocked(e.word));
}

function filtered() {
  const q = searchEl.value.trim().toLowerCase();
  const c = clusterEl.value;
  return visibleEntries().filter((e) => {
    if (activeLetter !== "All") {
      const first = (e.word[0] || "").toUpperCase();
      if (activeLetter === "#") {
        if (/[A-Z]/.test(first)) return false;
      } else if (first !== activeLetter) return false;
    }
    if (c !== "" && String(e.cluster) !== c) return false;
    if (!q) return true;
    return (
      e.word.toLowerCase().includes(q) ||
      (e.definition || "").toLowerCase().includes(q) ||
      (e.forms || []).join(" ").toLowerCase().includes(q)
    );
  });
}

function render() {
  const list = filtered();
  grid.innerHTML = "";
  empty.hidden = list.length > 0;
  const hidden = DATA.entries.length - visibleEntries().length;
  resultLine.textContent = list.length + " of " + DATA.entries.length + " terms" + (hidden ? " (" + hidden + " hidden by censor filter)" : "");
  if (censoredCountEl) censoredCountEl.textContent = String(BLOCKED.size);
  for (const e of list.slice(0, 300)) {
    const card = document.createElement("article");
    card.className = "card";
    const href = wordLink(e.word);
    card.tabIndex = 0;
    card.setAttribute("role", "link");
    card.setAttribute("aria-label", e.word);
    card.addEventListener("click", (ev) => {
      if (ev.target.closest(".card-check")) return;
      if (ev.target.closest(".chip")) return;
      if (ev.target.closest("a")) return;
      location.href = href;
    });
    card.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      if (ev.target.closest && ev.target.closest(".chip")) return;
      if (ev.target !== card) return;
      ev.preventDefault();
      location.href = href;
    });
    const h = document.createElement("h3");
    const a = document.createElement("a");
    a.href = href;
    a.textContent = e.word;
    a.tabIndex = -1;
    h.appendChild(a);
    const p = document.createElement("p");
    p.className = "def";
    p.textContent = e.definition || "—";
    const tags = document.createElement("div");
    tags.className = "tags";
    const c = document.createElement("span");
    c.className = "chip";
    c.textContent = clusterLabel(e.cluster);
    tags.appendChild(c);
    if (isBlocked(e.word)) {
      const b = document.createElement("span");
      b.className = "chip dark";
      b.textContent = "censored";
      tags.appendChild(b);
    }
    if (e.uses && e.uses.length) {
      const u = document.createElement("span");
      u.className = "chip";
      u.textContent = e.uses.length + " usage";
      tags.appendChild(u);
    }
    if (e.similar && e.similar.length) {
      const s = document.createElement("a");
      s.className = "chip";
      s.href = wordLink(e.similar[0].word);
      s.textContent = "∼ " + e.similar[0].word;
      tags.appendChild(s);
    }
    card.append(h, p, tags);
    if (isLocalhost()) {
      const row = document.createElement("div");
      row.className = "card-check";
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.dataset.word = e.word;
      box.checked = isBlocked(e.word);
      box.setAttribute("aria-label", "Blacklist " + e.word);
      box.addEventListener("click", (ev) => ev.stopPropagation());
      box.addEventListener("change", () => {
        if (box.checked) BLOCKED.add(e.word.toLowerCase());
        else BLOCKED.delete(e.word.toLowerCase());
        if (censoredCountEl) censoredCountEl.textContent = String(BLOCKED.size);
        render();
      });
      label.append(box, document.createTextNode(" blacklist"));
      row.appendChild(label);
      card.append(row);
    }
    grid.appendChild(card);
  }
}

function buildAZ() {
  const letters = ["All", ...Array.from({ length: 26 }, (_, i) => String.fromCharCode(65 + i)), "#"];
  azEl.innerHTML = "";
  for (const L of letters) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = L;
    b.setAttribute("aria-pressed", String(L === activeLetter));
    b.addEventListener("click", () => {
      activeLetter = L;
      buildAZ();
      render();
    });
    azEl.appendChild(b);
  }
}

function buildClusters() {
  const ids = [...new Set(DATA.entries.map((e) => e.cluster))].filter((x) => x !== null && x !== undefined).sort((a, b) => a - b);
  for (const id of ids) {
    const opt = document.createElement("option");
    opt.value = String(id);
    const members = (DATA.clusters.find((k) => k.id === id) || {}).members || [];
    opt.textContent = "Cluster " + id + (members.length ? " — " + members.slice(0, 3).join(", ") + (members.length > 3 ? "…" : "") : "");
    clusterEl.appendChild(opt);
  }
}

function wordOfDay() {
  const pool = visibleEntries();
  if (!pool.length) return;
  const now = new Date();
  const dayIndex = Math.floor(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) / 86400000);
  const pick = pool[dayIndex % pool.length];
  document.getElementById("wotd").hidden = false;
  const link = document.getElementById("wotd-link");
  link.href = wordLink(pick.word);
  link.textContent = pick.word;
  document.getElementById("wotd-def").textContent = pick.definition;
}

async function init() {
  const [res, blockRes] = await Promise.all([
    fetch("data/combined.json"),
    fetch("data/blocklist.json").catch(() => null),
  ]);
  DATA = await res.json();
  try {
    if (blockRes && blockRes.ok) {
      const blockData = await blockRes.json();
      BLOCKED = new Set((blockData.words || []).map((w) => String(w).toLowerCase()));
    }
  } catch { /* no blocklist -> show everything */ }
  if (showCensoredEl) showCensoredEl.checked = showCensored;
  countLine.textContent = DATA.count + " slang terms · " + DATA.clusters.length + " similarity clusters · definitions + real usage + sources";
  document.getElementById("gen-line").textContent = "Generated " + (DATA.generated_at || "") + " from scraper/slang.json.";
  buildAZ();
  buildClusters();
  wordOfDay();
  render();
  searchEl.addEventListener("input", render);
  clusterEl.addEventListener("change", render);
  document.getElementById("random").addEventListener("click", () => {
    const pool = visibleEntries();
    if (!pool.length) return;
    const pick = pool[Math.floor(Math.random() * pool.length)];
    location.href = wordLink(pick.word);
  });
  setupBackToTop();
  setupFab();
}

function isLocalhost() {
  if (location.protocol === "file:") return true;
  const host = (location.hostname || "").toLowerCase().replace(/^\[|\]$/g, "");
  return ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""].includes(host);
}

function blocklistJson(words) {
  return JSON.stringify({ words: [...words].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())) }, null, 2);
}

function downloadFile(filename, text) {
  const blob = new Blob([text], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 100);
}

function setupFab() {
  const fab = document.getElementById("blacklist-fab");
  if (!fab || !isLocalhost()) return;
  fab.hidden = false;
  if (fab.dataset.ready) return;
  fab.dataset.ready = "1";
  fab.addEventListener("click", () => {
    // Query all rendered card checkboxes; keep already-blocked words that
    // are currently filtered out of view so they aren't lost on export.
    const rendered = [...grid.querySelectorAll('input[type="checkbox"][data-word]')];
    const renderedLower = new Set(rendered.map((b) => b.dataset.word.toLowerCase()));
    const kept = [...BLOCKED].filter((w) => !renderedLower.has(w));
    const checked = rendered.filter((b) => b.checked).map((b) => b.dataset.word.toLowerCase());
    const byLower = new Map(DATA.entries.map((e) => [e.word.toLowerCase(), e.word]));
    const finalLower = new Set([...kept, ...checked]);
    const finalWords = [...finalLower].map((l) => byLower.get(l) || l);
    BLOCKED = finalLower;
    if (censoredCountEl) censoredCountEl.textContent = String(BLOCKED.size);
    downloadFile("blocklist_manual.json", blocklistJson(finalWords) + "\n");
    const orig = fab.textContent;
    fab.textContent = "Saved " + finalWords.length + " words";
    setTimeout(() => { fab.textContent = orig; }, 1500);
    render();
  });
}

function setupBackToTop() {
  const btn = document.getElementById("toTop");
  if (!btn) return;
  const toggle = () => {
    const show = window.scrollY > 0;
    btn.hidden = !show;
    btn.classList.toggle("show", show);
  };
  window.addEventListener("scroll", toggle, { passive: true });
  toggle();
  btn.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
}

init().catch((err) => {
  countLine.textContent = "Could not load data/combined.json — run scripts/build_data.py first.";
  console.error(err);
});

// Wire censor UI immediately (not after data fetch) so controls show even on slow/failed loads.
if (showCensoredEl) {
  showCensoredEl.checked = showCensored;
  if (!showCensoredEl.dataset.wired) {
    showCensoredEl.dataset.wired = "1";
    showCensoredEl.addEventListener("change", () => {
      showCensored = showCensoredEl.checked;
      localStorage.setItem("codeslang.showCensored", showCensored ? "1" : "0");
      buildAZ();
      wordOfDay();
      render();
    });
  }
}
// Unhide localhost blacklist button immediately; it works off the card checkboxes.
setupFab();
