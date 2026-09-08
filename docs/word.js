function getParam(name) {
  return new URLSearchParams(location.search).get(name) || "";
}

function wordLink(word) {
  return "word.html?w=" + encodeURIComponent(word);
}

function domainOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return url || ""; }
}

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

async function init() {
  const res = await fetch("data/combined.json");
  const data = await res.json();
  const entries = data.entries;
  const byLower = new Map(entries.map((e) => [e.word.toLowerCase(), e]));
  const q = getParam("w").toLowerCase();
  const entry = byLower.get(q) || entries.find((e) => e.word.toLowerCase().includes(q));
  const box = document.getElementById("detail");
  box.innerHTML = "";
  if (!entry) {
    box.append(el("p", "Word not found. "), el("a", "Back to all slang"));
    box.querySelector("a").href = "index.html";
    return;
  }
  document.title = entry.word + " — Code Slang";

  box.append(el("p", "Slang · " + (entry.cluster === null || entry.cluster === undefined ? "uncategorized" : "cluster " + entry.cluster), "eyebrow"));
  box.append(el("h1", entry.word));

  const forms = el("div", undefined, "forms");
  for (const f of entry.forms || []) forms.append(el("span", f, "chip"));
  if (forms.children.length) box.append(forms);

  box.append(el("p", entry.definition));

  // Real usage (Wiktionary-style quotations, Urban-Dictionary-style highlight)
  const usage = el("section", undefined, "block");
  usage.append(el("h2", "In the wild — real usage"));
  if (entry.uses && entry.uses.length) {
    for (const u of entry.uses) {
      const d = el("div", undefined, "use");
      d.append(el("p", "“" + u.sentence + "”"));
      const s = el("p", "Source: " + domainOf(u.url), "src");
      const a = el("a", "Open source ↗");
      a.href = u.url; a.rel = "noopener"; a.target = "_blank";
      s.append(" · "); s.append(a);
      d.append(s);
      usage.append(d);
    }
  } else {
    usage.append(el("p", "No extracted usage sentences yet — see sources below."));
  }
  box.append(usage);

  // Similar terms (related-words sidebar idea)
  const sim = el("section", undefined, "block");
  sim.append(el("h2", "Similar terms"));
  const chips = el("div", undefined, "tags");
  const similars = entry.similar || [];
  if (similars.length) {
    for (const s of similars) {
      const a = el("a", s.word + " (" + s.score.toFixed(2) + ")", "chip");
      a.href = wordLink(s.word);
      chips.append(a);
    }
  } else {
    chips.append(el("span", "No close matches in this dataset.", "chip"));
  }
  sim.append(chips);
  if (entry.similar_english && entry.similar_english.length) {
    sim.append(el("p", "Plain-English neighbours: " + entry.similar_english.map((x) => x.word).join(", ")));
  }
  box.append(sim);

  // Cluster mates
  const cluster = (data.clusters || []).find((k) => k.id === entry.cluster);
  if (cluster && cluster.members.length > 1) {
    const cm = el("section", undefined, "block");
    cm.append(el("h2", "Same cluster (" + cluster.members.length + ")"));
    const cchips = el("div", undefined, "tags");
    for (const m of cluster.members) {
      if (m.toLowerCase() === entry.word.toLowerCase()) continue;
      const a = el("a", m, "chip");
      a.href = wordLink(m);
      cchips.append(a);
    }
    cm.append(cchips);
    box.append(cm);
  }

  // Sources
  const src = el("section", undefined, "block");
  src.append(el("h2", "Sources"));
  const ul = el("ul", undefined, "src-list");
  for (const ex of entry.examples || []) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = ex.url; a.target = "_blank"; a.rel = "noopener";
    a.textContent = ex.title || ex.url;
    li.append(a);
    li.append(el("div", domainOf(ex.url) + (ex.description ? " — " + ex.description.slice(0, 160) : ""), "domain"));
    ul.append(li);
  }
  src.append(ul);
  box.append(src);

  // Prev / next alphabetical
  const idx = entries.findIndex((e) => e.word.toLowerCase() === entry.word.toLowerCase());
  const pager = document.getElementById("pager");
  const prev = entries[(idx - 1 + entries.length) % entries.length];
  const next = entries[(idx + 1) % entries.length];
  const pa = el("a", "← " + prev.word, "btn");
  pa.href = wordLink(prev.word);
  const na = el("a", next.word + " →", "btn");
  na.href = wordLink(next.word);
  pager.append(pa, na);
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
  document.getElementById("detail").textContent = "Could not load data/combined.json.";
  console.error(err);
});
