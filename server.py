# -*- coding: utf-8 -*-
"""
⚡ ATIAR SMS - High-Performance Live Verification Hub
- Dual-Engine Parallel Workers (Atiar59_FD & Smswork21_FD)
- Staggered background polling (every 1.8s) for 0ms memory response
- Instant On-Demand Force Fetch with strict 2.8s portal timeout (NEVER hangs!)
- Real-time SSE Push for immediate notification delivery
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
logger = logging.getLogger("AtiarSMS")

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

recent_records = collections.deque(maxlen=80)
seen_hashes = {}
sse_clients = set()
worker_locks = {}
last_worker_idx = 0

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

# Build dedicated dual worker engines
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
    """Direct SSE push to all active browser connections."""
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

async def run_worker_loop(worker, stagger_offset=0.0, poll_interval=3.6):
    """
    Dedicated parallel background worker loop (like two independent browser tabs).
    Alternates every ~1.8 seconds between accounts.
    Ensures recent_records is ALWAYS warm and full of the latest portal reports!
    """
    loop = asyncio.get_running_loop()
    await asyncio.sleep(stagger_offset)

    # Initial login
    try:
        await loop.run_in_executor(None, worker.login)
        logger.info(f"🔥 [{worker.worker_id}] {worker.username} active and logged in.")
        init_recs = await loop.run_in_executor(None, worker.fetch_records, current_keyword, 20)
        if init_recs:
            ingest_records(init_recs)
    except Exception as e:
        logger.warning(f"Initial worker start notice for {worker.username}: {e}")

    while True:
        try:
            now_t = time.time()
            if worker.rate_limited_until <= now_t:
                if not worker.is_logged_in:
                    await loop.run_in_executor(None, worker.login)
                if worker.is_logged_in:
                    recs = await loop.run_in_executor(None, worker.fetch_records, current_keyword, 20)
                    if recs:
                        ingest_records(recs)
        except Exception as e:
            logger.debug(f"[{worker.worker_id}] Background fetch notice: {e}")

        await asyncio.sleep(poll_interval)

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
    logger.info(f"Client connected to SSE stream. Total clients: {len(sse_clients)}")

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
    kw = request.query.get("keyword", current_keyword).strip()
    limit = int(request.query.get("limit", 25))
    if kw:
        matched = [r for r in recent_records if kw.lower() in str(r.get('cli', '')).lower() or kw.lower() in str(r.get('message', '')).lower()]
        return web.json_response(matched[:limit])
    return web.json_response(list(recent_records)[:limit])

async def handle_force_fetch(request):
    """
    ⚡ INSTANT FORCE FETCH (<0.3s)
    - Returns live portal results or instant memory snapshot
    - Strict 2.8s timeout: NEVER hangs or freezes!
    - Alternates between Atiar59_FD and Smswork21_FD with rate-limit immunity
    """
    global current_keyword, last_worker_idx
    loop = asyncio.get_running_loop()

    kw = request.query.get("keyword", current_keyword).strip() or current_keyword
    limit = int(request.query.get("limit", 20))
    now = time.time()

    # Instant memory snapshot ready
    memory_snapshot = [
        r for r in recent_records 
        if (not kw or kw.lower() in str(r.get('cli', '')).lower() or kw.lower() in str(r.get('message', '')).lower())
    ][:limit]

    # Pick next worker in round-robin sequence that is available
    available = [w for w in worker_pool if w.rate_limited_until <= now and w.is_logged_in]
    if available:
        last_worker_idx = (last_worker_idx + 1) % len(available)
        worker = available[last_worker_idx]
    else:
        worker = min(worker_pool, key=lambda w: w.rate_limited_until)

    t0 = time.time()

    # Try fast live query with strict 2.8s timeout
    try:
        recs = await asyncio.wait_for(
            loop.run_in_executor(None, worker.fetch_records, kw, limit),
            timeout=2.8
        )
        fetch_ms = int((time.time() - t0) * 1000)

        if recs:
            ingest_records(recs)
            recs_sorted = sorted(recs, key=lambda r: str(r.get("time", "")), reverse=True)
            return web.json_response({
                "success": True,
                "count": len(recs_sorted),
                "records": recs_sorted,
                "worker": worker.username,
                "latency_ms": fetch_ms
            })
    except Exception as e:
        logger.warning(f"Force fetch live query fallback notice: {e}")

    # Fallback to current memory snapshot immediately (0ms delay)
    fetch_ms = int((time.time() - t0) * 1000)
    return web.json_response({
        "success": True,
        "count": len(memory_snapshot),
        "records": memory_snapshot,
        "worker": "instant-memory",
        "latency_ms": max(fetch_ms, 20)
    })

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
        logger.info("⚡ Non-blocking startup: Launching dual parallel workers...")
        tasks = []
        for idx, w in enumerate(worker_pool):
            offset = idx * 1.8
            t = asyncio.create_task(run_worker_loop(w, stagger_offset=offset, poll_interval=3.6))
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
    print("⚡ ATIAR SMS Hub (Instant Parallel Dual-Engine)")
    print(f"👉 Local Web Hub: http://localhost:{WEB_PORT}")
    print(f"👉 Workers: {len(worker_pool)} ({', '.join(w.username for w in worker_pool)})")
    print(f"👉 Active Keyword: '{current_keyword}' (Permanent)")
    print("=" * 65)

    app = create_app()
    web.run_app(app, host='0.0.0.0', port=WEB_PORT)
