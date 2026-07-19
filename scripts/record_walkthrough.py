"""Record a narrated, cursor-driven walkthrough of Understudy → a single .mp4.

macOS-only (uses `say` for TTS and `afinfo` for durations). ffmpeg is provided
by the pip package `imageio-ffmpeg` (no Homebrew needed).

    make dev-native        # backend serving the built SPA at :8000 (same-origin)
    python scripts/record_walkthrough.py         # -> docs/media/walkthrough.mp4

How it works: each scene has narration + an on-screen action. We synth the
narration up front (so we know each clip's length), drive the browser with a
glide-to-target cursor overlay while Playwright records video, then lay each
narration clip back onto its scene's timeline and mux with ffmpeg.
"""
from __future__ import annotations

import asyncio
import contextlib
import re
import subprocess
import time
from pathlib import Path

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
BASE = "http://localhost:8000"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "media"
WORK = ROOT / "scratch_record"          # scene audio + raw video (transient)
VIEW = {"width": 1280, "height": 800}
VOICE = "Samantha"                        # a clean built-in en_US voice
RATE = 180                                # words/min — calm narration pace

# A visible cursor + click ripple, injected on every document (survives nav).
CURSOR_JS = r"""
() => {
  if (window.__aicur) return; window.__aicur = true;
  const install = () => {
    if (!document.body || document.getElementById('__ai_cursor')) return;
    const c = document.createElement('div'); c.id = '__ai_cursor';
    c.style.cssText = 'position:fixed;left:0;top:0;z-index:2147483647;'
      + 'pointer-events:none;will-change:transform;filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))';
    c.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24">'
      + '<path d="M3 2 L3 21 L8.5 15.5 L12 23 L15 21.5 L11.5 14 L19 14 Z" '
      + 'fill="#111" stroke="#fff" stroke-width="1.3" stroke-linejoin="round"/></svg>';
    document.body.appendChild(c);
    if (window.__aix != null)
      c.style.transform = `translate(${window.__aix}px,${window.__aiy}px)`;
  };
  if (document.readyState === 'loading')
    document.addEventListener('DOMContentLoaded', install, { once: true });
  else install();
  addEventListener('mousemove', e => {
    window.__aix = e.clientX; window.__aiy = e.clientY;
    install();                                   // self-heal if the SPA remounted
    const c = document.getElementById('__ai_cursor');
    if (c) c.style.transform = `translate(${e.clientX}px,${e.clientY}px)`;
  }, true);
  addEventListener('mousedown', e => {
    if (!document.body) return;
    const r = document.createElement('div');
    r.style.cssText = `position:fixed;left:${e.clientX}px;top:${e.clientY}px;`
      + 'z-index:2147483646;width:10px;height:10px;margin:-5px;border-radius:50%;'
      + 'background:rgba(37,99,235,.55);pointer-events:none;transition:all .45s ease-out';
    document.body.appendChild(r);
    requestAnimationFrame(() => { r.style.width='46px'; r.style.height='46px';
      r.style.margin='-23px'; r.style.opacity='0'; });
    setTimeout(() => r.remove(), 480);
  }, true);
}
"""


def sh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True)


def synth(text: str, dst: Path) -> float:
    """Speak `text` to `dst` (aiff); return its duration in seconds."""
    sh("say", "-v", VOICE, "-r", str(RATE), "-o", str(dst), text)
    info = sh("afinfo", str(dst)).stdout
    m = re.search(r"estimated duration:\s*([\d.]+)", info)
    return float(m.group(1)) if m else 3.0


# --------------------------------------------------------------------------
# The script: (narration, async action). Actions get (ctx) with page + helpers.
# --------------------------------------------------------------------------
class Ctx:
    def __init__(self, pg):
        self.pg = pg
        self.pos = (VIEW["width"] / 2, VIEW["height"] / 2)
        self.grabbed: dict[str, str] = {}

    async def glide(self, x, y, steps=26):
        await self.pg.mouse.move(x, y, steps=steps)
        self.pos = (x, y)

    async def _box(self, loc):
        with contextlib.suppress(Exception):
            await loc.scroll_into_view_if_needed(timeout=4000)
        return await loc.bounding_box()

    async def move_to(self, loc):
        b = await self._box(loc)
        if b:
            await self.glide(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2)

    async def click(self, loc):
        await self.move_to(loc)
        await self.pg.wait_for_timeout(160)
        await loc.click(timeout=8000)

    async def type(self, loc, text):
        await self.click(loc)
        with contextlib.suppress(Exception):
            await loc.fill("")
        await loc.type(text, delay=45)

    async def settle(self, ms=700):
        await self.pg.wait_for_timeout(ms)

    async def body_has(self, text, tries=30, ms=1200):
        low = text.lower()
        for _ in range(tries):
            await self.pg.wait_for_timeout(ms)
            if low in (await self.pg.locator("body").inner_text()).lower():
                return True
        return False


async def s_intro(c: Ctx):
    await c.pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
    await c.settle(800)
    await c.click(c.pg.get_by_role("button", name="Try the live demo"))
    await c.pg.wait_for_selector("text=Dashboard", timeout=30000)
    from contextlib import suppress
    with suppress(Exception):
        await c.pg.get_by_role("button", name="Skip").click(timeout=2500)
    await c.settle(900)


async def s_dashboard(c: Ctx):
    await c.pg.goto(BASE + "/", wait_until="domcontentloaded")
    await c.settle(900)
    for sel in [".kpi", ".stat", ".card"]:
        loc = c.pg.locator(sel)
        if await loc.count():
            n = min(3, await loc.count())
            for i in range(n):
                await c.move_to(loc.nth(i))
                await c.settle(500)
            break


async def s_learned(c: Ctx):
    await c.pg.goto(BASE + "/workflows/wf-demo-seed-001",
                    wait_until="domcontentloaded")
    await c.settle(1100)
    await c.pg.mouse.wheel(0, 420)
    await c.settle(900)
    if await c.body_has("approval", tries=1, ms=200):
        pass
    await c.pg.mouse.wheel(0, 420)
    await c.settle(800)


async def s_teach(c: Ctx):
    await c.pg.goto(BASE + "/workflows", wait_until="domcontentloaded")
    await c.settle(700)
    from contextlib import suppress
    with suppress(Exception):
        await c.click(c.pg.get_by_role("button", name=re.compile("Teach a new")))
        await c.settle(700)
        await c.click(c.pg.get_by_role("button", name=re.compile("Start recording")))
    # land in the Vendra recorder
    await c.pg.wait_for_selector("#understudy-rec-widget", timeout=15000)
    await c.settle(700)
    # open an invoice and read its values off the page
    await c.click(c.pg.get_by_test_id("open-INV-1001"))
    await c.settle(900)
    for key, tid in [("vendor", "inv-vendor"), ("number", "inv-number"),
                     ("date", "inv-date"), ("amount", "inv-amount"),
                     ("gl", "inv-gl")]:
        with suppress(Exception):
            txt = await c.pg.get_by_test_id(tid).inner_text(timeout=2500)
            c.grabbed[key] = re.sub(r"[^0-9A-Za-z.\-/ ]", "", txt).strip()
    await c.move_to(c.pg.get_by_test_id("inv-amount"))
    await c.settle(700)
    # switch to LedgerOne via the recorder's app switcher
    await c.click(c.pg.locator('#understudy-rec-widget .rjump[data-path="/erp"]'))
    await c.pg.wait_for_load_state("domcontentloaded")
    await c.settle(700)
    await c.click(c.pg.get_by_test_id("new-bill"))
    await c.settle(700)
    g = c.grabbed
    await c.type(c.pg.get_by_test_id("field-vendor"), g.get("vendor", "Acme Corp"))
    await c.type(c.pg.get_by_test_id("field-invoice-number"),
                 g.get("number", "INV-1001"))
    await c.type(c.pg.get_by_test_id("field-invoice-date"),
                 g.get("date", "2026-02-01"))
    await c.type(c.pg.get_by_test_id("field-amount"),
                 re.sub(r"[^0-9.]", "", g.get("amount", "1200")) or "1200")
    await c.type(c.pg.get_by_test_id("field-gl-code"), g.get("gl", "6000"))
    await c.settle(500)
    await c.click(c.pg.get_by_test_id("post-bill"))
    await c.settle(900)
    # stop & save the demonstration
    with suppress(Exception):
        await c.click(c.pg.locator("#understudy-rec-widget .rstop"))
    await c.pg.wait_for_url(re.compile(r"/workflows"), timeout=15000)
    await c.settle(900)


async def s_induce(c: Ctx):
    await c.pg.goto(BASE + "/workflows", wait_until="domcontentloaded")
    await c.settle(700)
    btn = c.pg.get_by_role("button", name="Learn this workflow").first
    from contextlib import suppress
    with suppress(Exception):
        await c.click(btn)
        await c.body_has("learned", tries=10, ms=1000)
    await c.settle(1200)


async def s_run(c: Ctx):
    await c.pg.goto(BASE + "/workflows/wf-demo-seed-001",
                    wait_until="domcontentloaded")
    await c.settle(900)
    await c.type(c.pg.locator("input.input.mono").first, "INV-1005")
    await c.settle(400)
    await c.click(c.pg.get_by_role("button", name="Run once"))
    await c.body_has("waiting for your approval", tries=30, ms=1500)
    await c.settle(1200)
    from contextlib import suppress
    with suppress(Exception):
        await c.click(c.pg.get_by_role("button", name="Approve").first)
    await c.body_has("completed", tries=20, ms=1500)
    await c.settle(1000)


async def s_preview(c: Ctx):
    await c.pg.goto(BASE + "/workflows/wf-demo-seed-001",
                    wait_until="domcontentloaded")
    await c.settle(800)
    await c.type(c.pg.locator("input.input.mono").first, "INV-1002")
    from contextlib import suppress
    with suppress(Exception):
        await c.click(c.pg.get_by_role("button", name="Dry run"))
        await c.body_has("completed", tries=18, ms=1300)
    with suppress(Exception):
        await c.click(c.pg.get_by_role("button", name="Check target health"))
        await c.body_has("resolve", tries=15, ms=1200)
    await c.settle(900)


async def s_assistant(c: Ctx):
    await c.pg.goto(BASE + "/assistant", wait_until="domcontentloaded")
    await c.settle(800)
    box = c.pg.get_by_placeholder("Message the assistant…")
    await c.type(box, "Which of my workflows need approval?")
    await c.settle(300)
    await box.press("Enter")
    await c.body_has("approval", tries=30, ms=1500)
    await c.settle(1200)


async def s_polish(c: Ctx):
    await c.pg.goto(BASE + "/", wait_until="domcontentloaded")
    await c.settle(700)
    await c.pg.keyboard.press("Meta+k")
    await c.settle(700)
    from contextlib import suppress
    with suppress(Exception):
        await c.pg.locator(".cmdk-input input").fill("dark")
        await c.settle(600)
        await c.pg.keyboard.press("Enter")
    await c.settle(1100)


SCENES = [
    ("Understudy is an A I teammate that learns a browser workflow by watching "
     "you do it once, then runs it for you — with a human approval gate before "
     "anything irreversible. Let me sign in with the one-click demo.", s_intro),
    ("The dashboard tracks what matters: success rate, invoices pending "
     "approval, time saved, and the cost of every language-model call.",
     s_dashboard),
    ("Here is a workflow it already learned. The spec is legible — each step "
     "has a plain-English intent, values are parameters or values read live off "
     "the page, and the step that posts the bill is marked requires-approval.",
     s_learned),
    ("Now the core idea: teaching it a brand-new workflow by demonstration. I "
     "open an invoice in the Vendra portal, switch to the LedgerOne E-R-P, enter "
     "the bill using the values I just read, and post it. Understudy records the "
     "semantic actions — roles and labels, never pixels — then I stop and save.",
     s_teach),
    ("From that single demonstration it induces a runnable workflow, and "
     "automatically gates the post step. Record the same task twice and it can "
     "tell which values are parameters because they varied.", s_induce),
    ("Running it on a brand-new invoice: I give it only an invoice id. It reads "
     "the vendor, amount and G-L code live, fills the E-R-P, and hard-pauses at "
     "the commit. Only after I approve does it post the bill.", s_run),
    ("Before trusting a run I can dry-run it. Watch — it reads the invoice and "
     "fills the entire E-R-P form exactly as a real run would, but it stops at "
     "the gate and commits absolutely nothing. And a drift pre-flight checks "
     "that every element the workflow depends on still resolves on the live "
     "pages, so I catch a redesigned portal before it silently breaks a run.",
     s_preview),
    ("There is also a conversational agent, driving the same governed tools as "
     "the UI. It can start work, but it has no approve tool — releasing a gate "
     "stays human-only, by construction.", s_assistant),
    ("A command palette reaches anything, including dark mode. That is "
     "Understudy: learn by watching, run under policy, with a human in the loop. "
     "Thanks for watching.", s_polish),
]


async def record() -> Path:
    from playwright.async_api import async_playwright
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "vid").mkdir(exist_ok=True)

    print("• synthesizing narration …")
    durs = []
    for i, (text, _) in enumerate(SCENES):
        d = synth(text, WORK / f"s{i}.aiff")
        durs.append(d)
        print(f"    scene {i}: {d:.1f}s")

    print("• recording browser …")
    lengths = []
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True)
        ctx = await b.new_context(viewport=VIEW, record_video_dir=str(WORK / "vid"),
                                  record_video_size=VIEW)
        await ctx.add_init_script("(" + CURSOR_JS + ")()")  # IIFE: run on every doc
        pg = await ctx.new_page()
        c = Ctx(pg)
        t0 = time.monotonic()
        for i, (_, action) in enumerate(SCENES):
            start = time.monotonic()
            await c.glide(VIEW["width"] / 2, VIEW["height"] / 2, steps=8)
            try:
                await action(c)
            except Exception as exc:  # keep rolling; a flaky scene ≠ dead take
                print(f"    ! scene {i} action error: {exc}")
            elapsed = time.monotonic() - start
            target = max(durs[i] + 0.6, elapsed + 0.3)
            remaining = target - (time.monotonic() - start)
            if remaining > 0:
                await pg.wait_for_timeout(int(remaining * 1000))
            lengths.append(time.monotonic() - start)
            print(f"    scene {i}: {lengths[i]:.1f}s (audio {durs[i]:.1f}s)")
        print(f"    total: {time.monotonic() - t0:.1f}s")
        await ctx.close()          # finalizes the video file
        await b.close()
        video = max((WORK / "vid").glob("*.webm"), key=lambda p: p.stat().st_mtime)

    print("• assembling narration track …")
    segs = []
    for i, L in enumerate(lengths):
        seg = WORK / f"seg{i}.wav"
        sh(FFMPEG, "-y", "-i", str(WORK / f"s{i}.aiff"), "-af", "apad",
           "-t", f"{L:.3f}", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le",
           str(seg))
        segs.append(seg)
    listf = WORK / "list.txt"
    listf.write_text("".join(f"file '{s}'\n" for s in segs))
    narration = WORK / "narration.wav"
    sh(FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
       "-c:a", "pcm_s16le", str(narration))

    print("• muxing → mp4 …")
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "walkthrough.mp4"
    r = sh(FFMPEG, "-y", "-i", str(video), "-i", str(narration),
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264",
           "-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "23",
           "-c:a", "aac", "-b:a", "160k", "-shortest", str(out))
    if r.returncode != 0:      # fall back to webm (copy video + opus audio)
        print("    (libx264 unavailable, falling back to .webm)")
        out = OUT / "walkthrough.webm"
        r = sh(FFMPEG, "-y", "-i", str(video), "-i", str(narration),
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "libopus", "-shortest", str(out))
        if r.returncode != 0:
            print(r.stderr[-1500:])
            raise SystemExit("mux failed")
    return out


if __name__ == "__main__":
    path = asyncio.run(record())
    mb = path.stat().st_size / 1e6
    print(f"\n✓ {path}  ({mb:.1f} MB)")
