import { useLayoutEffect, useState } from "react";

interface Step { selector: string; title: string; body: string; }

const STEPS: Step[] = [
  { selector: 'a[href="/"]', title: "Dashboard",
    body: "Your workspace at a glance — runs, success rate, pending approvals, cost." },
  { selector: 'a[href="/assistant"]', title: "Assistant",
    body: "Ask in plain language. It discovers, learns, and runs workflows — but never approves an irreversible step itself." },
  { selector: 'a[href="/workflows"]', title: "Workflows",
    body: "Procedures Understudy learned by watching. Click “Teach a new workflow” to record one in your browser." },
  { selector: 'a[href="/approvals"]', title: "Approvals",
    body: "Runs pause here before anything irreversible. Approve or reject — every decision is attributed to you." },
  { selector: 'a[href="/audit"]', title: "Audit log",
    body: "Every action across the workspace, with actor and timestamp. The proof trail." },
];

export function Tour({ onClose }: { onClose: () => void }) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  useLayoutEffect(() => {
    const el = document.querySelector(STEPS[i].selector);
    if (el) {
      el.scrollIntoView({ block: "nearest" });
      setRect(el.getBoundingClientRect());
    } else {
      setRect(null);
    }
  }, [i]);

  const step = STEPS[i];
  const top = rect ? rect.top : 120;
  const left = rect ? rect.right + 14 : 260;

  return (
    <div className="tour-overlay" onClick={onClose}>
      {rect && (
        <div className="tour-ring" style={{
          top: rect.top - 4, left: rect.left - 4,
          width: rect.width + 8, height: rect.height + 8,
        }} />
      )}
      <div className="tour-pop" style={{ top, left }} onClick={(e) => e.stopPropagation()}>
        <div className="tour-title">{step.title}</div>
        <div className="tour-body">{step.body}</div>
        <div className="tour-foot">
          <span className="tour-count">{i + 1} of {STEPS.length}</span>
          <div className="tour-btns">
            <button className="btn sm" onClick={onClose}>Skip</button>
            {i > 0 && <button className="btn sm" onClick={() => setI(i - 1)}>Back</button>}
            {i < STEPS.length - 1
              ? <button className="btn sm primary" onClick={() => setI(i + 1)}>Next</button>
              : <button className="btn sm primary" onClick={onClose}>Done</button>}
          </div>
        </div>
      </div>
    </div>
  );
}
