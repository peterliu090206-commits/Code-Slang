let DATA = { entries: [], clusters: [] };
let activeLetter = "All";

const grid = document.getElementById("grid");
const empty = document.getElementById("empty");
const searchEl = document.getElementById("search");
const clusterEl = document.getElementById("cluster");
const azEl = document.getElementById("az");
const resultLine = document.getElementById("result-line");
const countLine = document.getElementById("count-line");

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

function filtered() {
  const q = searchEl.value.trim().toLowerCase();
  const c = clusterEl.value;
  return DATA.entries.filter((e) => {
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
  resultLine.textContent = list.length + " of " + DATA.entries.length + " terms";
  for (const e of list.slice(0, 300)) {
    const card = document.createElement("article");
    card.className = "card";
    const h = document.createElement("h3");
    const a = document.createElement("a");
    a.href = wordLink(e.word);
    a.textContent = e.word;
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
  if (!DATA.entries.length) return;
  const now = new Date();
  const dayIndex = Math.floor(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) / 86400000);
  const pick = DATA.entries[dayIndex % DATA.entries.length];
  document.getElementById("wotd").hidden = false;
  const link = document.getElementById("wotd-link");
  link.href = wordLink(pick.word);
  link.textContent = pick.word;
  document.getElementById("wotd-def").textContent = pick.definition;
}

async function init() {
  const res = await fetch("data/combined.json");
  DATA = await res.json();
  countLine.textContent = DATA.count + " slang terms · " + DATA.clusters.length + " similarity clusters · definitions + real usage + sources";
  document.getElementById("gen-line").textContent = "Generated " + (DATA.generated_at || "") + " from scraper/slang.json.";
  buildAZ();
  buildClusters();
  wordOfDay();
  render();
  searchEl.addEventListener("input", render);
  clusterEl.addEventListener("change", render);
  document.getElementById("random").addEventListener("click", () => {
    const pick = DATA.entries[Math.floor(Math.random() * DATA.entries.length)];
    location.href = wordLink(pick.word);
  });
  setupBackToTop();
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
