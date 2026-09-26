// Review queue UI (T05). Localhost only: renders docs/data/review_queue.json
// with per-card checkboxes, censorship-style. Checked = destructive action
// (pending: reject + blocklist; conflict: remove image). Unchecked pending
// images are treated as APPROVED. The floating button exports a decisions
// JSON file; `py -3 scripts/review_move.py apply-batch <file>` executes it.
// Nothing here writes files. Mirrors the isLocalhost() gate, checkbox row,
// and floating export button from app.js.

function isLocalhost() {
  if (location.protocol === "file:") return true;
  const host = (location.hostname || "").toLowerCase().replace(/^\[|\]$/g, "");
  return ["localhost", "127.0.0.1", "::1", "0.0.0.0", ""].includes(host);
}

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function checkRow(slug, action, label) {
  const row = el("div", undefined, "card-check");
  const lab = document.createElement("label");
  const box = document.createElement("input");
  box.type = "checkbox";
  box.dataset.slug = slug;
  box.dataset.action = action; // "reject" (pending) or "remove" (conflict)
  box.checked = false; // unchecked = approve (pending) / keep (conflict)
  box.setAttribute("aria-label", label + " " + slug);
  box.addEventListener("change", updateFab);
  lab.append(box, document.createTextNode(" " + label));
  row.appendChild(lab);
  return row;
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

function decisions() {
  const boxes = [...document.querySelectorAll('#content input[type="checkbox"][data-slug]')];
  const rejected = boxes.filter((b) => b.checked && b.dataset.action === "reject").map((b) => b.dataset.slug);
  const removed = boxes.filter((b) => b.checked && b.dataset.action === "remove").map((b) => b.dataset.slug);
  const pendingSlugs = [...document.querySelectorAll('#pending input[type="checkbox"][data-action="reject"]')].map((b) => b.dataset.slug);
  const approved = pendingSlugs.filter((s) => !rejected.includes(s));
  return { approved, rejected, removed };
}

function updateFab() {
  const fab = document.getElementById("review-fab");
  if (!fab || fab.hidden) return;
  const d = decisions();
  let label = "Export: " + d.approved.length + " approve · " + d.rejected.length + " reject";
  if (d.removed.length) label += " · " + d.removed.length + " remove";
  fab.textContent = label;
}

function setupFab() {
  const fab = document.getElementById("review-fab");
  if (!fab) return;
  fab.hidden = false;
  if (fab.dataset.ready) return;
  fab.dataset.ready = "1";
  fab.addEventListener("click", () => {
    const d = decisions();
    const payload = {
      exported_at: new Date().toISOString(),
      approved: [...d.approved].sort(),
      rejected: [...d.rejected].sort(),
      remove_image: [...d.removed].sort(),
    };
    downloadFile("review_decisions.json", JSON.stringify(payload, null, 2) + "\n");
    const orig = fab.textContent;
    fab.textContent = "Saved — run apply-batch";
    setTimeout(updateFab, 1500);
  });
  updateFab();
}

function card(e, opts) {
  const card = el("article", undefined, "qcard" + (e.conflict ? " conflict" : ""));
  const img = document.createElement("img");
  const V = window.__V || "1";
  img.src = opts.imgBase + e.slug + ".png?v=" + V;
  img.alt = e.word + (opts.imgAlt || " staged image");
  img.loading = "lazy";
  img.width = 132;
  img.height = 132;
  const body = el("div", undefined, "body");
  const h = el("h3", e.word);
  const tags = el("div", undefined, "tags");
  tags.append(el("span", e.strategy, "chip"));
  tags.append(el("span", "safety: " + e.safety, "chip"));
  if (e.status) tags.append(el("span", e.status, "chip"));
  body.append(h, tags);
  if (e.subject) body.append(el("p", e.subject, "subj"));
  if (e.palette) body.append(el("p", e.palette, "subj"));
  if (opts.stateLine) body.append(opts.stateLine);
  if (opts.check) body.append(checkRow(e.slug, opts.check[0], opts.check[1]));
  card.append(img, body);
  return card;
}

async function init() {
  if (!isLocalhost()) {
    document.getElementById("local-only").hidden = false;
    document.getElementById("stats").textContent = "Not on localhost — review is disabled here.";
    return;
  }
  const V = window.__V || "1";
  const res = await fetch("data/review_queue.json?v=" + V);
  if (!res.ok) throw new Error("HTTP " + res.status);
  const data = await res.json();
  const c = data.counts;
  document.getElementById("stats").textContent =
    data.entries.length + " spec rows · " + c.pending + " pending · " +
    c.approved + " approved · " + c.skipped + " skipped · " + c.conflicts +
    " conflicts · generated " + (data.generated_at || "");
  document.getElementById("content").hidden = false;

  const pendEl = document.getElementById("pending");
  const pend = data.entries.filter((e) => e.pending);
  if (!pend.length) pendEl.append(el("p", "Queue empty — run generate_from_specs.py to stage images.", "sub"));
  for (const e of pend) {
    const state = e.approved
      ? el("p", "Approved image EXISTS — approving overwrites it.", "state-warn")
      : el("p", "No approved image yet.", "state-ok");
    pendEl.append(card(e, {
      imgBase: "data/images_pending/",
      stateLine: state,
      check: ["reject", "reject"],
    }));
  }

  const confEl = document.getElementById("conflicts");
  const conf = data.entries.filter((e) => e.conflict);  document.getElementById("conflicts-wrap").hidden = !conf.length;
  for (const e of conf) {
    confEl.append(card(e, {
      imgBase: "data/images/",
      imgAlt: " approved image (conflict)",
      stateLine: el("p", "Blocked word with an approved image — remove it.", "state-warn"),
      check: ["remove", "remove image"],
    }));
  }

  const revEl = document.getElementById("revise");
  const rev = data.entries.filter((e) => e.needs_revision);
  document.getElementById("revise-wrap").hidden = !rev.length;
  for (const e of rev) {
    const state = el("p", e.rejected_count + " rejected prompt(s) saved as negative examples.", "state-warn");
    const c = card(e, { imgBase: "data/images_pending/", imgAlt: " (rejected, deleted)", stateLine: state });
    const code = el("code", "py -3 scripts/review_move.py export-revision " + e.slug);
    code.style.cssText = "display:block;font-size:12px;background:var(--chip);border:1px solid var(--line);border-radius:8px;padding:4px 8px;margin-top:6px;overflow-x:auto;white-space:nowrap;";
    c.querySelector(".body").append(code);
    // No staged pixels left to show; hide the frame, subject text carries it.
    c.querySelector("img").style.display = "none";
    revEl.append(c);
  }

  const apprEl = document.getElementById("approved");
  const appr = data.entries.filter((e) => e.approved && !e.pending);
  if (!appr.length) apprEl.append(el("span", "none yet", "chip"));
  for (const e of appr) {
    const a = el("a", e.word, "chip");
    a.href = "word.html?w=" + encodeURIComponent(e.word);
    apprEl.append(a);
  }

  const skip = data.entries.filter((e) => e.skip_image && !e.needs_revision);
  document.getElementById("skipped-line").textContent =
    skip.length + " words use the HTML letter-tile fallback (typographic strategy or blocked).";
  const skipEl = document.getElementById("skipped");
  for (const e of skip) skipEl.append(el("span", e.word, "chip"));
  setupFab();
}

init().catch((err) => {
  document.getElementById("stats").textContent =
    "Could not load data/review_queue.json — run py -3 scripts/build_review.py first.";
  console.error(err);
});
