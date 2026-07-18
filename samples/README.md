# Samples

The two artifacts at the heart of Understudy, exported from the seed demonstration
so you can read the data model without running anything.

| File | What it is |
|------|------------|
| [`example-trace.json`](example-trace.json) | A **recorded demonstration** — the semantic events `inject.js` captures when a user does the task once (roles, accessible names, test-ids, page snapshots — never pixel coordinates). This is the *input* to induction. |
| [`example-workflow.json`](example-workflow.json) | The **learned workflow spec** induced from that trace — the editable JSON IR the product runs. Note: one `invoice_id` parameter, `extract` steps that read the other fields live off the page, per-step `intent`, and the final `post-bill` step carrying `risk: "commit"` + `requires_approval: true`. |

Regenerate them anytime:

```bash
make seed          # seeds these into the database, or
python -c "import json; from app.seed import build_demo_trace; from app.induction.heuristic import induce_heuristic; \
t=build_demo_trace(); print(json.dumps(induce_heuristic(t).model_dump(mode='json'), indent=2))"
```
