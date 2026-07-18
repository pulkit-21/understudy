import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, WorkflowSpec } from "./api";
import { Icon } from "./Icon";

export interface Command {
  id: string;
  title: string;
  hint?: string;
  group: string;
  icon: string;
  keywords?: string;
  run: () => void;
}

/**
 * ⌘K command palette — keyboard-first navigation and actions across the whole
 * app. Opens on ⌘K / Ctrl+K (and via the sidebar search affordance). Navigation,
 * quick actions, and every learned workflow are searchable in one place.
 */
export function CommandPalette({
  open, onClose, onToggleTheme, onStartTour, onLogout,
}: {
  open: boolean;
  onClose: () => void;
  onToggleTheme: () => void;
  onStartTour: () => void;
  onLogout: () => void;
}) {
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const [workflows, setWorkflows] = useState<WorkflowSpec[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // load workflows lazily the first time the palette opens
  useEffect(() => {
    if (open && workflows.length === 0) {
      api.listWorkflows().then(setWorkflows).catch(() => {});
    }
    if (open) {
      setQ("");
      setSel(0);
      setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = (path: string) => () => { nav(path); onClose(); };

  const commands: Command[] = useMemo(() => {
    const base: Command[] = [
      { id: "nav-dash", title: "Go to Dashboard", group: "Navigate", icon: "dashboard", run: go("/") },
      { id: "nav-assistant", title: "Open Assistant", group: "Navigate", icon: "chat", keywords: "chat agent", run: go("/assistant") },
      { id: "nav-workflows", title: "Go to Workflows", group: "Navigate", icon: "workflows", run: go("/workflows") },
      { id: "nav-runs", title: "Go to Runs", group: "Navigate", icon: "runs", keywords: "history", run: go("/runs") },
      { id: "nav-approvals", title: "Go to Approvals", group: "Navigate", icon: "approvals", keywords: "gate review", run: go("/approvals") },
      { id: "nav-audit", title: "Go to Audit log", group: "Navigate", icon: "book", run: go("/audit") },
      { id: "nav-team", title: "Go to Team", group: "Navigate", icon: "team", run: go("/team") },
      { id: "nav-settings", title: "Go to Settings", group: "Navigate", icon: "settings", run: go("/settings") },
      { id: "act-newchat", title: "New chat with the Assistant", group: "Actions", icon: "chat", keywords: "ask agent", run: go("/assistant") },
      { id: "act-theme", title: "Toggle light / dark theme", group: "Actions", icon: "moon", keywords: "dark mode appearance", run: () => { onToggleTheme(); onClose(); } },
      { id: "act-tour", title: "Take the product tour", group: "Actions", icon: "book", keywords: "help guide onboarding", run: () => { onStartTour(); onClose(); } },
      { id: "act-portal", title: "Open Vendra portal", group: "Mock apps", icon: "external", keywords: "invoice", run: () => { window.open("/portal", "_blank"); onClose(); } },
      { id: "act-erp", title: "Open LedgerOne ERP", group: "Mock apps", icon: "external", keywords: "bill payment", run: () => { window.open("/erp", "_blank"); onClose(); } },
      { id: "act-logout", title: "Sign out", group: "Actions", icon: "logout", run: () => { onClose(); onLogout(); } },
    ];
    const wf: Command[] = workflows.map((w) => ({
      id: `wf-${w.id}`,
      title: w.name,
      hint: `${w.parameters.length} param${w.parameters.length === 1 ? "" : "s"} · ${w.status}`,
      group: "Workflows",
      icon: "workflows",
      keywords: "run " + w.parameters.map((p) => p.key).join(" "),
      run: go(`/workflows/${w.id}`),
    }));
    return [...base, ...wf];
  }, [workflows]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return commands;
    return commands.filter((c) =>
      `${c.title} ${c.group} ${c.keywords || ""}`.toLowerCase().includes(t));
  }, [q, commands]);

  useEffect(() => { setSel(0); }, [q]);

  // keep the selected row scrolled into view
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${sel}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  if (!open) return null;

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, filtered.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); filtered[sel]?.run(); }
    else if (e.key === "Escape") { e.preventDefault(); onClose(); }
  };

  // group the filtered commands, preserving first-seen order
  const groups: { name: string; items: { c: Command; idx: number }[] }[] = [];
  filtered.forEach((c, idx) => {
    let g = groups.find((x) => x.name === c.group);
    if (!g) { g = { name: c.group, items: [] }; groups.push(g); }
    g.items.push({ c, idx });
  });

  return (
    <div className="cmdk-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="cmdk" onClick={(e) => e.stopPropagation()}>
        <div className="cmdk-input">
          <Icon name="search" size={18} />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKey}
            placeholder="Search commands, workflows, pages…"
            aria-label="Search commands"
          />
          <kbd className="cmdk-esc">esc</kbd>
        </div>
        <div className="cmdk-list" ref={listRef}>
          {filtered.length === 0 && <div className="cmdk-empty">No matches for “{q}”.</div>}
          {groups.map((g) => (
            <div key={g.name}>
              <div className="cmdk-group">{g.name}</div>
              {g.items.map(({ c, idx }) => (
                <button
                  key={c.id}
                  data-idx={idx}
                  className={"cmdk-item" + (idx === sel ? " sel" : "")}
                  onMouseEnter={() => setSel(idx)}
                  onClick={() => c.run()}
                >
                  <Icon name={c.icon} size={16} />
                  <span className="cmdk-title">{c.title}</span>
                  {c.hint && <span className="cmdk-hint">{c.hint}</span>}
                </button>
              ))}
            </div>
          ))}
        </div>
        <div className="cmdk-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> select</span>
          <span><kbd>esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}
