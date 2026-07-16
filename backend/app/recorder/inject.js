// Understudy recorder — injected into every page of the demonstration browser.
//
// Captures SEMANTIC events (role + accessible name + testid + css fallback),
// not coordinates. Events are delivered to Python through the
// window.__understudy_emit binding exposed by Playwright.
//
// Design notes:
//  * composedPath()[0] is used so clicks inside open shadow DOM resolve to
//    the real target rather than the shadow host.
//  * Text inputs are NOT emitted per keystroke; the final value is emitted
//    on 'change' (blur/enter), collapsing typing into a single FILL event.
//  * On each page load we also emit a NAVIGATE event carrying a trimmed
//    innerText snapshot — induction uses it to figure out where a typed
//    value was originally READ from (data provenance -> extract steps).

(() => {
  if (window.__understudyInstalled) return;
  window.__understudyInstalled = true;

  const emit = (evt) => {
    try { window.__understudy_emit(JSON.stringify(evt)); } catch (_) {}
  };

  // ---- accessible name (pragmatic subset of the AccName algorithm) --------
  function accessibleName(el) {
    if (!el || el.nodeType !== 1) return null;
    const aria = el.getAttribute("aria-label");
    if (aria) return aria.trim();
    const labelledBy = el.getAttribute("aria-labelledby");
    if (labelledBy) {
      const parts = labelledBy.split(/\s+/)
        .map((id) => document.getElementById(id)?.innerText || "");
      const joined = parts.join(" ").trim();
      if (joined) return joined;
    }
    if (el.labels && el.labels.length) {
      const t = el.labels[0].innerText.trim();
      if (t) return t;
    }
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab && lab.innerText.trim()) return lab.innerText.trim();
    }
    const own = (el.innerText || el.value || el.getAttribute("placeholder") ||
                 el.getAttribute("title") || "").trim();
    return own ? own.slice(0, 80) : null;
  }

  // ---- implicit ARIA role (subset that covers form/nav UI) -----------------
  function role(el) {
    const explicit = el.getAttribute("role");
    if (explicit) return explicit;
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (tag === "a" && el.hasAttribute("href")) return "link";
    if (tag === "button") return "button";
    if (tag === "select") return "combobox";
    if (tag === "textarea") return "textbox";
    if (tag === "input") {
      if (["button", "submit", "reset"].includes(type)) return "button";
      if (type === "checkbox") return "checkbox";
      if (type === "radio") return "radio";
      return "textbox";
    }
    return tag;
  }

  // ---- short, stable-ish css selector (last-resort fallback) --------------
  function cssPath(el) {
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 5) {
      let part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift(`#${CSS.escape(node.id)}`); break; }
      const dt = node.getAttribute("data-testid");
      if (dt) { parts.unshift(`[data-testid="${dt}"]`); break; }
      const siblings = node.parentElement
        ? [...node.parentElement.children].filter(
            (c) => c.tagName === node.tagName)
        : [];
      if (siblings.length > 1)
        part += `:nth-of-type(${siblings.indexOf(node) + 1})`;
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(" > ");
  }

  function targetInfo(el) {
    return {
      role: role(el),
      name: accessibleName(el),
      testid: el.getAttribute("data-testid") || null,
      css: cssPath(el),
      tag: el.tagName.toLowerCase(),
    };
  }

  // ---- readable fields: labelled, testid'd VALUES visible on the page -------
  // These are the provenance source: induction matches a value the user later
  // types against these to emit an `extract` step targeting the real testid,
  // so replays re-read the value live instead of baking in a constant.
  function readableFields() {
    const out = [];
    const seen = new Set();
    for (const el of document.querySelectorAll("[data-testid]")) {
      const tag = el.tagName.toLowerCase();
      // we want displayed values, not the controls the user acts on
      if (["input", "textarea", "select", "button", "a", "form"].includes(tag))
        continue;
      const value = (el.innerText || "").trim();
      if (!value || value.length > 200) continue;
      const testid = el.getAttribute("data-testid");
      // label: aria, or a preceding <dt> (definition lists), or previous sibling
      let label = el.getAttribute("aria-label") || "";
      if (!label && tag === "dd") {
        const dt = el.previousElementSibling;
        if (dt && dt.tagName.toLowerCase() === "dt") label = dt.innerText.trim();
      }
      if (!label) {
        const prev = el.previousElementSibling;
        if (prev && ["th", "label", "dt", "span"].includes(
              prev.tagName.toLowerCase()))
          label = prev.innerText.trim();
      }
      const key = testid + "|" + value;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({
        testid, value, label: label || null,
        role: role(el), name: label || accessibleName(el) || null,
      });
      if (out.length >= 60) break;
    }
    return out;
  }

  function realTarget(e) {
    const path = e.composedPath ? e.composedPath() : [e.target];
    // prefer the nearest interactive ancestor on the composed path
    for (const n of path) {
      if (n.nodeType !== 1) continue;
      const t = n.tagName?.toLowerCase();
      if (["a", "button", "input", "select", "textarea", "label"].includes(t) ||
          n.getAttribute?.("role")) return n;
    }
    return path.find((n) => n.nodeType === 1) || e.target;
  }

  const base = () => ({
    url: location.href,
    page_title: document.title,
    ts_ms: Date.now(),
  });

  // ---- listeners (capture phase so nothing swallows them) ------------------
  document.addEventListener("click", (e) => {
    const el = realTarget(e);
    if (!el || el.nodeType !== 1) return;
    const tag = el.tagName.toLowerCase();
    // typing focus clicks on inputs are noise; the FILL event carries intent
    if (["input", "textarea", "select"].includes(tag)) return;
    emit({ type: "click", target: targetInfo(el), ...base() });
  }, true);

  document.addEventListener("change", (e) => {
    const el = e.composedPath ? e.composedPath()[0] : e.target;
    if (!el || el.nodeType !== 1) return;
    const tag = el.tagName.toLowerCase();
    if (tag === "select") {
      emit({ type: "select", target: targetInfo(el), value: el.value, ...base() });
    } else if (tag === "input" || tag === "textarea") {
      const type = (el.getAttribute("type") || "text").toLowerCase();
      if (type === "password") return; // never record secrets
      const value = type === "checkbox" ? String(el.checked) : el.value;
      emit({ type: "fill", target: targetInfo(el), value, ...base() });
    }
  }, true);

  document.addEventListener("submit", (e) => {
    const form = e.composedPath ? e.composedPath()[0] : e.target;
    const submitter = e.submitter || form.querySelector('[type="submit"],button');
    emit({
      type: "submit",
      target: submitter ? targetInfo(submitter) : targetInfo(form),
      ...base(),
    });
  }, true);

  // ---- page snapshot on load (provenance source for induction) ------------
  const snapshot = () => emit({
    type: "navigate",
    page_text: (document.body?.innerText || "").slice(0, 5000),
    readable_fields: readableFields(),
    ...base(),
  });
  if (document.readyState === "complete") snapshot();
  else window.addEventListener("load", snapshot, { once: true });
})();
