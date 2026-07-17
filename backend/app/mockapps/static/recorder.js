// Understudy IN-BROWSER recorder — served into the mock apps so a user can
// teach a workflow by doing it in their own browser (no local Playwright).
//
// It captures the same SEMANTIC events as the Playwright recorder (role +
// accessible name + testid + css), but instead of a Playwright binding it:
//   * buffers events in sessionStorage so they survive navigations between
//     /portal and /erp (same tab, same origin),
//   * shows a floating "● Recording" widget with Stop / Cancel,
//   * on Stop, POSTs the assembled trace to /api/traces (bearer token read from
//     localStorage, shared same-origin with the SPA) and returns to the app.
//
// It is inert unless a recording is active (started via /portal?record=1).

(() => {
  if (window.__understudyRec) return;
  window.__understudyRec = true;

  const REC = "understudy_rec";          // {id,name,start_url,started_at}
  const EVENTS = "understudy_rec_events"; // [SemanticEvent]
  const TOKEN = "understudy_token";

  const load = (k, d) => { try { return JSON.parse(sessionStorage.getItem(k)) ?? d; } catch { return d; } };
  const save = (k, v) => sessionStorage.setItem(k, JSON.stringify(v));

  // ---- start a recording if the URL asked for it --------------------------
  const params = new URLSearchParams(location.search);
  if (params.get("record") === "1" && !sessionStorage.getItem(REC)) {
    const clean = location.origin + location.pathname;
    save(REC, {
      id: "rec-" + Math.random().toString(16).slice(2, 14),
      name: params.get("name") || "My demonstration",
      start_url: clean,
      started_at: new Date().toISOString(),
    });
    save(EVENTS, []);
    history.replaceState({}, "", clean);  // drop ?record=1 so reloads don't re-init
  }

  const rec = sessionStorage.getItem(REC) ? load(REC, null) : null;
  if (!rec) return;  // not recording — stay inert

  const events = () => load(EVENTS, []);
  const push = (evt) => { const e = events(); e.push(evt); save(EVENTS, e); updateWidget(e.length); };

  // ================= semantic capture (ported from inject.js) ==============
  function accessibleName(el) {
    if (!el || el.nodeType !== 1) return null;
    const aria = el.getAttribute("aria-label"); if (aria) return aria.trim();
    if (el.labels && el.labels.length) { const t = el.labels[0].innerText.trim(); if (t) return t; }
    if (el.id) { const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (lab && lab.innerText.trim()) return lab.innerText.trim(); }
    const own = (el.innerText || el.value || el.getAttribute("placeholder") || el.getAttribute("title") || "").trim();
    return own ? own.slice(0, 80) : null;
  }
  function role(el) {
    const explicit = el.getAttribute("role"); if (explicit) return explicit;
    const tag = el.tagName.toLowerCase(); const type = (el.getAttribute("type") || "").toLowerCase();
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") { if (["button", "submit", "reset"].includes(type)) return "button"; if (type === "checkbox") return "checkbox"; if (type === "radio") return "radio"; return "textbox"; }
    return tag;
  }
  function cssPath(el) {
    const parts = []; let node = el;
    while (node && node.nodeType === 1 && parts.length < 5) {
      if (node.id) { parts.unshift(`#${CSS.escape(node.id)}`); break; }
      const dt = node.getAttribute("data-testid");
      if (dt) { parts.unshift(`[data-testid="${dt}"]`); break; }
      let part = node.tagName.toLowerCase();
      const sibs = node.parentElement ? [...node.parentElement.children].filter((c) => c.tagName === node.tagName) : [];
      if (sibs.length > 1) part += `:nth-of-type(${sibs.indexOf(node) + 1})`;
      parts.unshift(part); node = node.parentElement;
    }
    return parts.join(" > ");
  }
  const targetInfo = (el) => ({ role: role(el), name: accessibleName(el), testid: el.getAttribute("data-testid") || null, css: cssPath(el), tag: el.tagName.toLowerCase() });

  function readableFields() {
    const out = [], seen = new Set();
    for (const el of document.querySelectorAll("[data-testid]")) {
      const tag = el.tagName.toLowerCase();
      if (["input", "textarea", "select", "button", "a", "form"].includes(tag)) continue;
      const value = (el.innerText || "").trim();
      if (!value || value.length > 200) continue;
      const testid = el.getAttribute("data-testid");
      let label = el.getAttribute("aria-label") || "";
      if (!label && tag === "dd") { const dt = el.previousElementSibling; if (dt && dt.tagName.toLowerCase() === "dt") label = dt.innerText.trim(); }
      if (!label) { const prev = el.previousElementSibling; if (prev && ["th", "label", "dt", "span"].includes(prev.tagName.toLowerCase())) label = prev.innerText.trim(); }
      const key = testid + "|" + value; if (seen.has(key)) continue; seen.add(key);
      out.push({ testid, value, label: label || null, role: role(el), name: label || accessibleName(el) || null });
      if (out.length >= 60) break;
    }
    return out;
  }
  function realTarget(e) {
    const path = e.composedPath ? e.composedPath() : [e.target];
    for (const n of path) { if (n.nodeType !== 1) continue; const t = n.tagName?.toLowerCase(); if (["a", "button", "input", "select", "textarea", "label"].includes(t) || n.getAttribute?.("role")) return n; }
    return path.find((n) => n.nodeType === 1) || e.target;
  }
  const base = () => ({ url: location.href, page_title: document.title, ts_ms: Date.now() });
  const inWidget = (el) => el && el.closest && el.closest("#understudy-rec-widget");

  // ---- listeners ----------------------------------------------------------
  document.addEventListener("click", (e) => {
    const el = realTarget(e); if (!el || el.nodeType !== 1 || inWidget(el)) return;
    const tag = el.tagName.toLowerCase();
    if (["input", "textarea", "select"].includes(tag)) return;
    // a submit button fires click THEN submit; keep only the submit (it carries
    // the commit intent) so we don't double-post.
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (type === "submit" || (tag === "button" && type !== "button" && el.form)) return;
    push({ type: "click", target: targetInfo(el), ...base() });
  }, true);
  document.addEventListener("change", (e) => {
    const el = e.composedPath ? e.composedPath()[0] : e.target;
    if (!el || el.nodeType !== 1 || inWidget(el)) return;
    const tag = el.tagName.toLowerCase();
    if (tag === "select") push({ type: "select", target: targetInfo(el), value: el.value, ...base() });
    else if (tag === "input" || tag === "textarea") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (type === "password") return;
      push({ type: "fill", target: targetInfo(el), value: type === "checkbox" ? String(el.checked) : el.value, ...base() });
    }
  }, true);
  document.addEventListener("submit", (e) => {
    const form = e.composedPath ? e.composedPath()[0] : e.target;
    const submitter = e.submitter || form.querySelector('[type="submit"],button');
    push({ type: "submit", target: submitter ? targetInfo(submitter) : targetInfo(form), ...base() });
  }, true);

  // navigate snapshot on load (provenance source for induction)
  const snapshot = () => push({ type: "navigate", page_text: (document.body?.innerText || "").slice(0, 5000), readable_fields: readableFields(), ...base() });
  if (document.readyState === "complete") snapshot();
  else window.addEventListener("load", snapshot, { once: true });

  // ================= floating widget =======================================
  let widget, countEl;
  function buildWidget() {
    widget = document.createElement("div");
    widget.id = "understudy-rec-widget";
    widget.innerHTML = `
      <style>
        #understudy-rec-widget{position:fixed;bottom:20px;right:20px;z-index:2147483647;
          background:#1b2330;color:#fff;border-radius:12px;padding:12px 14px;font:14px system-ui,sans-serif;
          box-shadow:0 8px 30px rgba(0,0,0,.3);display:flex;align-items:center;gap:12px;min-width:260px}
        #understudy-rec-widget .rdot{width:11px;height:11px;border-radius:50%;background:#e5484d;animation:rblink 1.1s infinite}
        @keyframes rblink{0%,100%{opacity:1}50%{opacity:.25}}
        #understudy-rec-widget .rtxt{flex:1;line-height:1.3}
        #understudy-rec-widget .rtxt b{display:block;font-weight:650}
        #understudy-rec-widget .rtxt small{color:#9aa4b2}
        #understudy-rec-widget button{border:none;border-radius:8px;padding:7px 12px;font:inherit;font-weight:600;cursor:pointer}
        #understudy-rec-widget .rstop{background:#e5484d;color:#fff}
        #understudy-rec-widget .rcancel{background:transparent;color:#9aa4b2}
      </style>
      <span class="rdot"></span>
      <span class="rtxt"><b>Recording your demonstration</b><small><span id="urec-n">0</span> steps captured</small></span>
      <button class="rstop">Stop &amp; save</button>
      <button class="rcancel">Cancel</button>`;
    document.body.appendChild(widget);
    countEl = widget.querySelector("#urec-n");
    widget.querySelector(".rstop").addEventListener("click", stop);
    widget.querySelector(".rcancel").addEventListener("click", cancel);
    updateWidget(events().length);
  }
  function updateWidget(n) { if (countEl) countEl.textContent = String(n); }

  function cleanup() { sessionStorage.removeItem(REC); sessionStorage.removeItem(EVENTS); }
  function cancel() { cleanup(); location.href = "/"; }

  async function stop() {
    const evs = events();
    const trace = { id: rec.id, name: rec.name, started_at: rec.started_at, start_url: rec.start_url, events: evs };
    const btn = widget.querySelector(".rstop"); btn.textContent = "Saving…"; btn.disabled = true;
    try {
      const token = localStorage.getItem(TOKEN);
      const res = await fetch("/api/traces", {
        method: "POST",
        headers: { "content-type": "application/json", ...(token ? { authorization: "Bearer " + token } : {}) },
        body: JSON.stringify(trace),
      });
      if (!res.ok) throw new Error("save failed (" + res.status + ")");
      cleanup();
      location.href = "/workflows?recorded=" + encodeURIComponent(rec.id);
    } catch (err) {
      btn.textContent = "Stop & save"; btn.disabled = false;
      alert("Couldn't save the recording: " + err.message + "\nMake sure you're signed in.");
    }
  }

  if (document.body) buildWidget();
  else window.addEventListener("DOMContentLoaded", buildWidget, { once: true });
})();
