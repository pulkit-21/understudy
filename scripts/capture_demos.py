"""Generate the per-feature demo GIFs embedded in the README.

Drives the running app with Playwright, snapping frames at the key moments of
each feature, and assembles each sequence into an optimized animated GIF under
docs/media/. Reproducible docs media, not test code.

    make dev            # (or docker compose up) so the app is live
    python scripts/capture_demos.py            # -> docs/media/*.gif
    python scripts/capture_demos.py run learn  # -> only the named features
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import sys
from pathlib import Path

from PIL import Image

BASE = "http://localhost:5173"
OUT = Path(__file__).resolve().parents[1] / "docs" / "media"
WIDTH = 960  # downscale for a sane repo footprint


def _save_gif(frames: list[bytes], name: str, ms: int = 1400) -> None:
    if not frames:
        print(f"  (no frames for {name})")
        return
    imgs = []
    for png in frames:
        im = Image.open(io.BytesIO(png)).convert("RGB")
        if im.width > WIDTH:
            im = im.resize((WIDTH, round(im.height * WIDTH / im.width)))
        imgs.append(im.convert("P", palette=Image.ADAPTIVE, colors=128))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.gif"
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=ms,
                 loop=0, optimize=True, disposal=2)
    kb = path.stat().st_size / 1024
    print(f"  ✓ {name}.gif  ({len(imgs)} frames, {kb:.0f} KB)")


async def main():
    only = set(sys.argv[1:])
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        pg = await b.new_page(viewport={"width": 1280, "height": 860})

        async def snap(frames):
            frames.append(await pg.screenshot())

        async def beat(frames, ms=1000):
            """Settle for `ms`, then capture a frame — the core capture rhythm."""
            await pg.wait_for_timeout(ms)
            await snap(frames)

        async def body_has(text):
            return text in (await pg.locator("body").inner_text()).lower()

        async def until(frames, text, tries=30, ms=1500):
            """Snap every `ms` until `text` appears on the page (or we give up)."""
            for _ in range(tries):
                await beat(frames, ms)
                if await body_has(text):
                    return
            await snap(frames)

        # --- login via the one-click demo -------------------------------------
        await pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
        await pg.get_by_role("button", name="Try the live demo").click(timeout=30000)
        await pg.wait_for_selector("text=Dashboard", timeout=30000)
        with contextlib.suppress(Exception):
            await pg.get_by_role("button", name="Skip").click(timeout=2000)
        tok = await pg.evaluate("localStorage.getItem('understudy_token')")

        async def api(method, path, payload=None):
            return await pg.evaluate(
                """async ([m,p,b,t]) => { const r = await fetch(p, {method:m,
                   headers:{'content-type':'application/json','authorization':'Bearer '+t},
                   body: b?JSON.stringify(b):undefined}); return r.status; }""",
                [method, path, payload, tok])

        def want(name):
            return not only or name in only

        # clean slate for tidy captures
        await api("POST", "/api/erp/_reset")

        # 1) learn — the legible, parameterized spec
        if want("learn"):
            f: list[bytes] = []
            await pg.goto(BASE + "/workflows", wait_until="domcontentloaded")
            await beat(f, 1200)
            await pg.locator(".row .title a").first.click()
            await beat(f, 1400)
            await pg.mouse.wheel(0, 600)
            await beat(f, 900)
            await pg.mouse.wheel(0, 600)
            await beat(f, 900)
            _save_gif(f, "learn")

        # 2) run -> gate -> approve -> posted  (the core loop)
        if want("run"):
            f = []
            await pg.goto(BASE + "/workflows/wf-demo-seed-001",
                          wait_until="domcontentloaded")
            await pg.wait_for_timeout(1000)
            await pg.locator("input.input.mono").first.fill("INV-1005")
            await beat(f, 400)
            await pg.get_by_role("button", name="Run once").click()
            await until(f, "waiting for your approval")
            await snap(f)
            await pg.get_by_role("button", name="Approve").first.click()
            await until(f, "completed", tries=20)
            await snap(f)
            _save_gif(f, "run-approve", ms=1200)

        # 3) dry-run preview
        if want("dryrun"):
            f = []
            await pg.goto(BASE + "/workflows/wf-demo-seed-001",
                          wait_until="domcontentloaded")
            await pg.wait_for_timeout(1000)
            await pg.locator("input.input.mono").first.fill("INV-1002")
            await beat(f, 300)
            await pg.get_by_role("button", name="Dry run").click()
            await until(f, "completed", tries=24, ms=1400)
            await snap(f)
            _save_gif(f, "dry-run", ms=1200)

        # 4) drift pre-flight
        if want("drift"):
            f = []
            await pg.goto(BASE + "/workflows/wf-demo-seed-001",
                          wait_until="domcontentloaded")
            await beat(f, 1000)
            await pg.get_by_role("button", name="Check target health").click()
            await until(f, "resolve", tries=20, ms=1200)
            await snap(f)
            _save_gif(f, "drift-preflight", ms=1200)

        # 5) multi-trace parameter discovery
        if want("multitrace"):
            f = []
            await pg.goto(BASE + "/workflows", wait_until="domcontentloaded")
            await beat(f, 1000)
            boxes = pg.locator("input[type=checkbox]")
            if await boxes.count() >= 2:
                await boxes.nth(0).check()
                await boxes.nth(1).check()
                await beat(f, 600)
                await pg.get_by_role("button", name="Learn from").click()
                await beat(f, 2500)
                await beat(f, 1200)
            _save_gif(f, "multi-trace")

        # 6) scheduling
        if want("schedule"):
            f = []
            await pg.goto(BASE + "/schedules", wait_until="domcontentloaded")
            await beat(f, 1000)
            await pg.select_option("select.input", index=1)
            await beat(f, 500)
            await pg.get_by_role("button", name="Create schedule").click()
            await beat(f, 1400)
            _save_gif(f, "schedule")

        # 7) conversational agent
        if want("agent"):
            f = []
            await pg.goto(BASE + "/assistant", wait_until="domcontentloaded")
            await beat(f, 1000)
            box = pg.get_by_placeholder("Message the assistant…")
            await box.fill("Which of my workflows need approval?")
            await beat(f, 400)
            await box.press("Enter")
            await until(f, "approval")
            await snap(f)
            _save_gif(f, "assistant", ms=1300)

        # 8) in-browser recorder + app switcher
        if want("recorder"):
            f = []
            await pg.goto("http://localhost:8000/portal?record=1",
                          wait_until="domcontentloaded")
            await pg.wait_for_selector("#understudy-rec-widget", timeout=8000)
            await beat(f, 800)
            await pg.locator(
                '#understudy-rec-widget .rjump[data-path="/erp"]').click()
            await pg.wait_for_load_state("domcontentloaded")
            await beat(f, 1000)
            await pg.locator('[data-testid="new-bill"]').click()
            await beat(f, 1000)
            _save_gif(f, "recorder")

        # 9) command palette + dark mode
        if want("palette"):
            f = []
            await pg.goto(BASE + "/", wait_until="domcontentloaded")
            await beat(f, 900)
            await pg.keyboard.press("Meta+k")
            await beat(f, 700)
            await pg.locator(".cmdk-input input").fill("dark")
            await beat(f, 600)
            await pg.keyboard.press("Enter")
            await beat(f, 900)
            _save_gif(f, "palette-dark")

        await b.close()
    print("done ->", OUT)


if __name__ == "__main__":
    asyncio.run(main())
