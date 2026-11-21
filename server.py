# -*- coding: utf-8 -*-
"""
⚡ Flex SMS Live Web Dashboard (Mobile-First & Instant On-Demand Force Fetch)
- Warm Keep-Alive Worker Sessions (<0.25s instant live search)
- Zero rate-limit & zero background bloat
- Instant 'Force Fetch' API endpoint (<0.3s)
- Fully responsive for mobile devices and desktops
- Render.com Cloud Deployment Ready (binds to $PORT)
"""

import os
import sys
import time
import json
import logging
import asyncio
import collections
from aiohttp import web

from config import load_config, save_config
from client import FlexSMSClient

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("SMSHubServer")

# Load configuration
cfg = load_config()
PORTAL_URL = cfg.get("portal_base_url", "http://168.119.13.175/ints")
ACCOUNTS = cfg.get("accounts", [
    {"username": "Atiar59_FD", "password": "Atiar5942@#"},
    {"username": "Smswork21_FD", "password": "Smswork21_FD"}
])

# Read port from environment variable (Render sets $PORT, default 5000 locally)
WEB_PORT = int(os.environ.get("PORT", cfg.get("web_port", 5000)))

# Default permanent keyword
current_keyword = cfg.get("default_keyword", "Telegram")

recent_records = collections.deque(maxlen=60)
seen_hashes = {}
sse_clients = set()
fetch_lock = asyncio.Lock()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_FILE = os.path.join(CURRENT_DIR, "dashboard.html")
PROXIES_FILE = os.path.join(CURRENT_DIR, "proxies.txt")

def load_proxies():
    proxies = []
    if os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    l = line.strip()
                    if l and not l.startswith("#"):
                        if not l.startswith("http://") and not l.startswith("https://") and not l.startswith("socks5://"):
                            l = f"http://{l}"
                        proxies.append(l)
        except Exception:
            pass
    return proxies

proxies_list = load_proxies()

# Build worker pool
worker_pool = []
if proxies_list:
    for idx, prx in enumerate(proxies_list):
        acc = ACCOUNTS[idx % len(ACCOUNTS)]
        w = FlexSMSClient(
            username=acc["username"],
            password=acc["password"],
            base_url=PORTAL_URL,
            worker_id=f"Proxy-{idx+1}",
            proxy=prx
        )
        worker_pool.append(w)
    logger.info(f"⚡ Loaded {len(worker_pool)} proxy workers.")
else:
    for idx, acc in enumerate(ACCOUNTS):
        w = FlexSMSClient(
            username=acc["username"],
            password=acc["password"],
            base_url=PORTAL_URL,
            worker_id=f"Engine-{idx+1}"
        )
        worker_pool.append(w)
    logger.info("⚡ Initialized dual dedicated engines (Atiar59_FD & Smswork21_FD).")

def broadcast_record(item):
    """Direct SSE push to active browser connections if any."""
    if not item:
        return
    msg = f"data: {json.dumps(item)}\n\n"
    dead = []
    for q in list(sse_clients):
        try:
            q.put_nowait(msg)
        except Exception:
            dead.append(q)
    for dq in dead:
        sse_clients.discard(dq)

def ingest_records(records):
    """Updates recent records and broadcasts."""
    if not records:
        return 0
    new_count = 0
    records_sorted = sorted(records, key=lambda r: str(r.get("time", "")))
    for rec in records_sorted:
        dedup_key = f"{rec.get('time')}|{rec.get('number')}|{rec.get('message')}"
        if dedup_key not in seen_hashes:
            seen_hashes[dedup_key] = time.time()
            recent_records.appendleft(rec)
            broadcast_record(rec)
            new_count += 1
            logger.info(f"📨 [NEW SMS] {rec.get('flag')} {rec.get('country')} | {rec.get('number')} | OTP: {rec.get('otp') or 'None'}")
    return new_count

async def run_worker_keepalive(worker, stagger_offset=0.0, keepalive_interval=85):
    """
    Lightweight keep-alive loop.
    Keeps worker PHP sessions hot and valid so that when user clicks Force Fetch,
    it executes in <0.25s with ZERO login delay and zero rate-limiting.
    """
    loop = asyncio.get_running_loop()
    await asyncio.sleep(stagger_offset)
    try:
        await loop.run_in_executor(None, worker.login)
        logger.info(f"🔥 [{worker.worker_id}] {worker.username} session warmed up & ready.")
    except Exception as e:
        logger.warning(f"Initial warm-up notice for {worker.username}: {e}")

    while True:
        await asyncio.sleep(keepalive_interval)
        try:
            if not worker.is_logged_in:
                await loop.run_in_executor(None, worker.login)
            else:
                # Lightweight keepalive ping to maintain active PHPSESSID cookie
                await loop.run_in_executor(None, worker.fetch_records, current_keyword, 5)
        except Exception as e:
            logger.debug(f"Keepalive ping for {worker.username}: {e}")
            try:
                await loop.run_in_executor(None, worker.login)
            except Exception:
                pass

# --- Web Endpoints ---

async def handle_index(request):
    try:
        if os.path.exists(DASHBOARD_FILE):
            with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            return web.Response(text=content, content_type="text/html", charset="utf-8")
        return web.Response(text="<h2>dashboard.html not found</h2>", status=404)
    except Exception as e:
        return web.Response(text=f"Server error: {e}", status=500)

async def handle_stream(request):
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache, no-transform',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )
    await response.prepare(request)

    q = asyncio.Queue()
    sse_clients.add(q)
    logger.info(f"Client connected. Total clients: {len(sse_clients)}")

    try:
        while True:
            msg = await q.get()
            await response.write(msg.encode('utf-8'))
            q.task_done()
    except asyncio.CancelledError:
        pass
    finally:
        sse_clients.discard(q)

    return response

async def handle_get_records(request):
    limit = int(request.query.get("limit", 25))
    return web.json_response(list(recent_records)[:limit])

async def handle_force_fetch(request):
    """
    ⚡ ULTRA-FAST ON-DEMAND FORCE FETCH (<0.3s)
    Queries the portal live with keyword and returns the exact fresh reports!
    """
    global current_keyword
    loop = asyncio.get_running_loop()

    kw = request.query.get("keyword", current_keyword).strip() or current_keyword
    limit = int(request.query.get("limit", 20))

    # Pick worker with lowest cooldown
    worker = min(worker_pool, key=lambda w: w.rate_limited_until)
    if not worker.is_logged_in:
        try:
            await loop.run_in_executor(None, worker.login)
        except Exception:
            pass

    t0 = time.time()
    logger.info(f"⚡ [Force Fetch] Live querying portal: keyword='{kw}', worker={worker.username}...")

    try:
        recs = await loop.run_in_executor(None, worker.fetch_records, kw, limit)
        fetch_ms = int((time.time() - t0) * 1000)

        if recs:
            recs_sorted = sorted(recs, key=lambda r: str(r.get("time", "")), reverse=True)
            # Update cache
            for r in recs_sorted:
                dedup_key = f"{r.get('time')}|{r.get('number')}|{r.get('message')}"
                if dedup_key not in seen_hashes:
                    seen_hashes[dedup_key] = time.time()
                    recent_records.appendleft(r)
            return web.json_response({
                "success": True,
                "count": len(recs_sorted),
                "records": recs_sorted,
                "worker": worker.username,
                "latency_ms": fetch_ms
            })
        else:
            return web.json_response({
                "success": True,
                "count": 0,
                "records": [],
                "worker": worker.username,
                "latency_ms": fetch_ms
            })
    except Exception as e:
        logger.error(f"Force fetch primary failed ({e}). Retrying secondary worker...")
        try:
            other_worker = [w for w in worker_pool if w != worker][0]
            if not other_worker.is_logged_in:
                await loop.run_in_executor(None, other_worker.login)
            recs = await loop.run_in_executor(None, other_worker.fetch_records, kw, limit)
            fetch_ms = int((time.time() - t0) * 1000)
            recs_sorted = sorted(recs, key=lambda r: str(r.get("time", "")), reverse=True) if recs else []
            for r in recs_sorted:
                dedup_key = f"{r.get('time')}|{r.get('number')}|{r.get('message')}"
                if dedup_key not in seen_hashes:
                    seen_hashes[dedup_key] = time.time()
                    recent_records.appendleft(r)
            return web.json_response({
                "success": True,
                "count": len(recs_sorted),
                "records": recs_sorted,
                "worker": other_worker.username,
                "latency_ms": fetch_ms
            })
        except Exception as e2:
            fetch_ms = int((time.time() - t0) * 1000)
            logger.error(f"Force fetch secondary failed: {e2}")
            return web.json_response({
                "success": False,
                "error": str(e2),
                "records": list(recent_records)[:limit],
                "latency_ms": fetch_ms
            }, status=500)

async def handle_get_status(request):
    return web.json_response({
        "status": "online",
        "is_logged_in": any(w.is_logged_in for w in worker_pool),
        "workers_count": len(worker_pool),
        "keyword": current_keyword,
        "buffered_count": len(recent_records),
        "connected_clients": len(sse_clients)
    })

async def handle_set_keyword(request):
    global current_keyword
    try:
        data = await request.json()
        new_kw = str(data.get("keyword", "")).strip()
        is_perm = bool(data.get("permanent", False))
        if new_kw:
            current_keyword = new_kw
            if is_perm:
                cfg["default_keyword"] = new_kw
                save_config(cfg)
            logger.info(f"Keyword updated to: '{new_kw}' (Permanent: {is_perm})")
            return web.json_response({"success": True, "keyword": current_keyword})
        return web.json_response({"success": False, "error": "Empty keyword"}, status=400)
    except Exception as e:
        return web.json_response({"success": False, "error": str(e)}, status=500)

async def handle_clear_records(request):
    global recent_records, seen_hashes
    recent_records.clear()
    seen_hashes.clear()
    logger.info("Feed records and cache cleared.")
    return web.json_response({"success": True})

def create_app():
    app = web.Application()
    app.router.add_get('/', handle_index)
    app.router.add_get('/api/stream', handle_stream)
    app.router.add_get('/api/records', handle_get_records)
    app.router.add_get('/api/force_fetch', handle_force_fetch)
    app.router.add_get('/api/status', handle_get_status)
    app.router.add_post('/api/keyword', handle_set_keyword)
    app.router.add_post('/api/clear', handle_clear_records)

    async def on_startup(app_instance):
        logger.info("Initializing warm worker sessions for instant on-demand queries...")
        loop = asyncio.get_running_loop()
        tasks = []

        # Perform initial seed fetch on first worker so dashboard has immediate data
        try:
            w0 = worker_pool[0]
            await loop.run_in_executor(None, w0.login)
            init_recs = await loop.run_in_executor(None, w0.fetch_records, current_keyword, 15)
            if init_recs:
                ingest_records(init_recs)
        except Exception as e:
            logger.warning(f"Startup seed notice: {e}")

        # Start warm keepalive tasks (one per worker)
        for idx, w in enumerate(worker_pool):
            offset = idx * 35.0
            t = asyncio.create_task(run_worker_keepalive(w, stagger_offset=offset, keepalive_interval=85))
            tasks.append(t)
        app_instance['worker_tasks'] = tasks

    async def on_cleanup(app_instance):
        for t in app_instance.get('worker_tasks', []):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app

if __name__ == "__main__":
    print("=" * 65)
    print("⚡ Flex SMS Hub (Mobile-Ready & Instant On-Demand Force Fetch)")
    print(f"👉 Local Web Hub: http://localhost:{WEB_PORT}")
    print(f"👉 Workers: {len(worker_pool)} ({', '.join(w.username for w in worker_pool)})")
    print(f"👉 Active Keyword: '{current_keyword}' (Permanent)")
    print("=" * 65)

    app = create_app()
    web.run_app(app, host='0.0.0.0', port=WEB_PORT)
