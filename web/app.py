"""ContextOS website: a small local app on http://localhost:8000."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from contextos.config import Config, load_config, save_settings
from contextos.services import tasks
from contextos.services.jobs import Jobs
from contextos.services.scheduler import Scheduler
from contextos.sources import all_sources
from contextos.storage import Store
from web import views

HERE = Path(__file__).parent


def create_app(
    config_loader: Callable[[], Config] = load_config,
    llm_factory: tasks.LLMFactory = tasks.default_llm,
    start_scheduler: bool = True,
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1"),
) -> FastAPI:
    jobs = Jobs()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = None
        if start_scheduler:
            scheduler = Scheduler(llm_factory, config_loader)
            scheduler.start()
        yield
        if scheduler:
            scheduler.stop.set()

    app = FastAPI(title="ContextOS", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    # Version static files by content, so browsers fetch new CSS/JS after an update instead of a stale cache.
    templates.env.globals["asset_v"] = hashlib.sha1(
        b"".join(f.read_bytes() for f in sorted((HERE / "static").iterdir()) if f.is_file())
    ).hexdigest()[:10]
    templates.env.filters["ago"] = views.ago
    templates.env.filters["local"] = lambda dt, fmt="%H:%M": dt.astimezone(tasks.local_tz()).strftime(fmt) if dt else ""

    # Your messages are on this server, so only answer to this machine. Checking Host blocks DNS-rebinding
    # attacks; checking Origin on writes stops other websites from posting to it (CSRF).
    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        if host not in allowed_hosts:
            return PlainTextResponse("ContextOS only answers on localhost.", status_code=403)
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            if origin and urlparse(origin).hostname not in allowed_hosts:
                return PlainTextResponse("Cross-site request blocked.", status_code=403)
        return await call_next(request)

    def cfg_dep() -> Config:
        return config_loader()

    def store_dep(cfg: Config = Depends(cfg_dep)) -> Iterator[Store]:
        store = Store(cfg.db_path)
        try:
            yield store
        finally:
            store.close()

    def page(request: Request, name: str, cfg: Config, store: Store, /, **ctx) -> HTMLResponse:
        sources = all_sources(cfg)
        syncs = [store.last_synced(s.name) for s in sources if s.is_configured()]
        return templates.TemplateResponse(
            request,
            name,
            {
                "nav": name.split(".")[0],
                "last_sync": max((s for s in syncs if s), default=None),
                "any_source": any(s.is_configured() for s in sources),
                "has_key": cfg.has_api_key,
                # Work still running in the background; the page reconnects to it on load.
                "running": {k: jobs.running(k) for k in ("refresh", "ask", "sync", "gmail")},
                **ctx,
            },
        )

    # ---- pages --------------------------------------------------------------

    @app.get("/")
    def home():
        return RedirectResponse("/today")

    @app.get("/today", response_class=HTMLResponse)
    def today(
        request: Request, window: str | None = None, cfg: Config = Depends(cfg_dep), store: Store = Depends(store_dep)
    ):
        # Remember "Since midnight" vs "Last 24h" across tab switches.
        if window not in ("today", "24h"):
            window = request.cookies.get("window") if request.cookies.get("window") in ("today", "24h") else "today"
        tz = tasks.local_tz()
        start, _ = tasks.window_for(window, tz)
        rec = store.latest_digest(created_since=start)
        ctx = views.digest_view(store, rec, tz) if rec else {}
        response = page(request, "today.html", cfg, store, window=window, view=ctx, history=False)
        response.set_cookie("window", window, max_age=60 * 60 * 24 * 365, samesite="lax")
        return response

    @app.get("/digest/{digest_id}", response_class=HTMLResponse)
    def digest_page(request: Request, digest_id: int, cfg: Config = Depends(cfg_dep), store: Store = Depends(store_dep)):
        rec = store.get_digest(digest_id)
        if not rec:
            raise HTTPException(404)
        ctx = views.digest_view(store, rec, tasks.local_tz())
        return page(request, "today.html", cfg, store, window="", view=ctx, history=True)

    @app.get("/history", response_class=HTMLResponse)
    def history(request: Request, cfg: Config = Depends(cfg_dep), store: Store = Depends(store_dep)):
        tz = tasks.local_tz()
        days: dict[str, list] = {}
        for rec in store.list_digests(limit=90):
            days.setdefault(rec.created_at.astimezone(tz).strftime("%A %d %B"), []).append(rec)
        return page(request, "history.html", cfg, store, days=days)

    @app.get("/ask", response_class=HTMLResponse)
    def ask_page(request: Request, cfg: Config = Depends(cfg_dep), store: Store = Depends(store_dep)):
        tz = tasks.local_tz()
        asks = [_ask_view(store, a, tz) for a in store.list_asks(limit=15)]
        return page(request, "ask.html", cfg, store, asks=asks, has_messages=bool(store.counts()))

    @app.get("/ask/{ask_id}/card", response_class=HTMLResponse)
    def ask_card(request: Request, ask_id: int, store: Store = Depends(store_dep)):
        a = next((x for x in store.list_asks(limit=200) if x["id"] == ask_id), None)
        if not a:
            raise HTTPException(404)
        return templates.TemplateResponse(request, "_answer.html", {"a": _ask_view(store, a, tasks.local_tz())})

    @app.get("/sources", response_class=HTMLResponse)
    def sources_page(request: Request, cfg: Config = Depends(cfg_dep), store: Store = Depends(store_dep)):
        logs = store.last_sync_logs()
        counts = store.counts()
        rows = [
            {
                "name": s.name,
                "configured": s.is_configured(),
                "hint": s.setup_hint(),
                "count": counts.get(s.name, 0),
                "log": logs.get(s.name),
                "last": store.last_synced(s.name),
            }
            for s in all_sources(cfg)
        ]
        return page(
            request,
            "sources.html",
            cfg,
            store,
            rows=rows,
            gmail_creds=cfg.gmail_credentials.exists(),
            gmail_token=cfg.gmail_token.exists(),
        )

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, saved: int = 0, cfg: Config = Depends(cfg_dep), store: Store = Depends(store_dep)):
        return page(
            request,
            "settings.html",
            cfg,
            store,
            cfg=cfg,
            saved=saved,
            secrets={k: bool(getattr(cfg, k)) for k in ("slack_token", "discord_token")},
        )

    # ---- actions on briefing items -----------------------------------------

    @app.post("/items/action", response_class=HTMLResponse)
    def item_action(
        request: Request,
        digest_id: int = Form(...),
        section: str = Form(...),
        key: str = Form(...),
        action: str = Form(...),
        cfg: Config = Depends(cfg_dep),
        store: Store = Depends(store_dep),
    ):
        if action not in ("done", "snooze", "reopen"):
            raise HTTPException(400, "unknown action")
        item = views.find_item(store, digest_id, section, key)
        if item is None:
            raise HTTPException(404, "item not found")
        tz = tasks.local_tz()
        until = views.snooze_until(tz, cfg.morning_hour) if action == "snooze" else None
        store.add_action(digest_id, key, item.get("refs", []), item, action, until)
        return _render_item(request, store, item, section, digest_id, tz)

    @app.post("/items/vote", response_class=HTMLResponse)
    def item_vote(
        request: Request,
        digest_id: int = Form(...),
        section: str = Form(...),
        key: str = Form(...),
        vote: int = Form(...),
        store: Store = Depends(store_dep),
    ):
        item = views.find_item(store, digest_id, section, key)
        if item is None:
            raise HTTPException(404, "item not found")
        store.add_feedback(digest_id, key, item, vote=1 if vote > 0 else -1)
        return _render_item(request, store, item, section, digest_id, tasks.local_tz())

    @app.post("/feedback/missed", response_class=HTMLResponse)
    def missed(digest_id: int = Form(...), note: str = Form(...), store: Store = Depends(store_dep)):
        if note.strip():
            store.add_feedback(digest_id, note=note.strip()[:2000])
        return HTMLResponse('<p class="muted">Thanks, noted. This goes into your eval set.</p>')

    def _render_item(request, store, item, section, digest_id, tz):
        view = views.make_item(
            item,
            section,
            digest_id,
            store.by_refs(item.get("refs", [])),
            tz,
            store.actions(),
            store.votes(digest_id),
            datetime.now(UTC),
        )
        return templates.TemplateResponse(request, "_item.html", {"it": view})

    # ---- settings -----------------------------------------------------------

    @app.post("/settings")
    def settings(
        request: Request,
        user_name: str = Form(""),
        about_me: str = Form(""),
        mute: str = Form(""),
        slack_token: str = Form(""),
        discord_token: str = Form(""),
        discord_user_id: str = Form(""),
        morning_hour: int = Form(8),
        auto_sync_minutes: int = Form(15),
        cfg: Config = Depends(cfg_dep),
    ):
        save_settings(
            cfg,
            {
                "user_name": user_name.strip(),
                "about_me": about_me.strip(),
                "mute": mute,
                "slack_token": slack_token.strip(),
                "discord_token": discord_token.strip(),
                "discord_user_id": discord_user_id.strip(),
                "morning_hour": max(0, min(23, morning_hour)),
                "auto_sync_minutes": max(5, auto_sync_minutes),
            },
        )
        return RedirectResponse("/settings?saved=1", status_code=303)

    @app.post("/settings/gmail-credentials")
    async def gmail_credentials(file: UploadFile, cfg: Config = Depends(cfg_dep)):
        raw = await file.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(400, "That file isn't JSON. Download the OAuth client JSON from Google Cloud.") from None
        if "installed" not in data:
            raise HTTPException(400, "Expected a 'Desktop app' OAuth client file (it has an \"installed\" key).")
        cfg.gmail_credentials.write_bytes(raw)
        cfg.gmail_credentials.chmod(0o600)
        return RedirectResponse("/sources", status_code=303)

    @app.post("/settings/gmail-disconnect")
    def gmail_disconnect(cfg: Config = Depends(cfg_dep)):
        cfg.gmail_token.unlink(missing_ok=True)
        return RedirectResponse("/sources", status_code=303)

    # ---- background jobs ----------------------------------------------------

    @app.post("/api/refresh")
    def api_refresh(window: str = Form("today"), cfg: Config = Depends(cfg_dep)):
        job = jobs.start(
            "refresh",
            lambda j: tasks.run_refresh(cfg, llm_factory, window, lambda m: j.emit("progress", text=m)),
            meta={"window": window},
        )
        return JSONResponse({"job": job.id})

    @app.post("/api/ask")
    def api_ask(question: str = Form(...), cfg: Config = Depends(cfg_dep)):
        question = question.strip()
        if not question:
            raise HTTPException(400, "Ask something.")
        job = jobs.start("ask", lambda j: tasks.run_ask(cfg, llm_factory, question[:2000], j), meta={"question": question[:2000]})
        return JSONResponse({"job": job.id})

    @app.post("/api/sync")
    def api_sync(cfg: Config = Depends(cfg_dep)):
        def work(j):
            with tasks.RUN_LOCK:
                reports = tasks.run_sync(cfg, lambda m: j.emit("progress", text=m), llm_factory=llm_factory)
            return {"new": sum(r.new for r in reports)}

        job = jobs.start("sync", work)
        return JSONResponse({"job": job.id})

    @app.post("/api/gmail/connect")
    def api_gmail_connect(cfg: Config = Depends(cfg_dep)):
        job = jobs.start("gmail", lambda j: tasks.connect_gmail(cfg, lambda m: j.emit("progress", text=m)))
        return JSONResponse({"job": job.id})

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(404)

        async def stream():
            sent = 0
            while True:
                pending = job.events[sent:]
                for event in pending:
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                sent += len(pending)
                if job.finished and sent >= len(job.events):
                    return
                await asyncio.sleep(0.25)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return app


def _ask_view(store: Store, a: dict, tz) -> dict:
    messages = store.by_refs(a["refs"])
    return {**a, "html": views.answer_html(a["answer"], messages, tz), "cost": (a["meta"].get("llm") or {}).get("cost_usd")}
