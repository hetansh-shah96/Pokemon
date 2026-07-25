"""
Optional real sprite art, loaded from PokeAPI's public sprite repository
(the classic, small Generation I pixel sprites -- a perfect fit for this
game's Game Boy theme) for personal / non-commercial fan-project use.

Everything here is best-effort and fully non-blocking: fetches happen on
background threads and get cached to disk, the game keeps rendering the
procedural pixel-art sprite (see sprites.py) until (and unless) a real one
becomes available, and if there's no internet connection at all, the whole
session just quietly stays on the procedural art -- nothing ever blocks or
crashes waiting on the network.
"""

import io
import os
import sys
import threading
import urllib.error
import urllib.request

import pygame

# Browsers (pygbag/pyodide) have no raw sockets and no real OS threads --
# fetching there goes through the Fetch API via an asyncio task instead.
# See _web_fetch()/request() below for the platform split.
_IS_WEB = sys.platform == "emscripten"

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sprite_cache")

_SPRITE_URL_TEMPLATES = [
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/versions/generation-i/red-blue/{}.png",
    "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{}.png",
]

_bytes_cache = {}       # dex -> raw png bytes, or False if unavailable
_raw_surface_cache = {}  # dex -> pygame.Surface (natural size), or False
_scaled_cache = {}      # (dex, size_px) -> pygame.Surface
_pending = set()
_lock = threading.Lock()
_offline = False


def _download(dex):
    global _offline
    for template in _SPRITE_URL_TEMPLATES:
        url = template.format(dex)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pokemon-indigo-league-fangame/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = resp.read()
            if data:
                return data
        except urllib.error.HTTPError:
            continue  # this particular sprite variant doesn't exist there -- try the next URL
        except Exception:
            # DNS failure, timeout, connection refused, etc. -- assume no internet this session
            with _lock:
                _offline = True
            return None
    return None


def _worker(dex):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        path = os.path.join(CACHE_DIR, f"{dex}.png")
        data = None
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                data = None
        if not data:
            data = _download(dex)
            if data:
                try:
                    with open(path, "wb") as f:
                        f.write(data)
                except OSError:
                    pass
        with _lock:
            _bytes_cache[dex] = data if data else False
    finally:
        with _lock:
            _pending.discard(dex)


async def _web_fetch(dex):
    """Browser build: fetch via the Fetch API (pyodide.http.pyfetch) since
    there are no raw sockets or real OS threads inside the WASM sandbox.
    In-memory only -- no persistent disk cache is attempted here, since a
    plain pygbag build's virtual filesystem doesn't survive a page reload
    anyway; the browser's own HTTP cache covers repeat plays well enough."""
    try:
        try:
            from pyodide.http import pyfetch
        except Exception:
            return
        for template in _SPRITE_URL_TEMPLATES:
            try:
                resp = await pyfetch(template.format(dex))
                if resp.ok:
                    data = await resp.bytes()
                    with _lock:
                        _bytes_cache[dex] = bytes(data) if data else False
                    return
            except Exception:
                continue
        with _lock:
            _bytes_cache[dex] = False
    finally:
        with _lock:
            _pending.discard(dex)


def request(dex):
    """Kick off a background fetch for this dex number, if not already underway."""
    with _lock:
        if dex in _bytes_cache or dex in _pending or (_offline and not _IS_WEB):
            return
        _pending.add(dex)
    if _IS_WEB:
        import asyncio
        asyncio.ensure_future(_web_fetch(dex))
    else:
        threading.Thread(target=_worker, args=(dex,), daemon=True).start()


def _get_raw_surface(dex):
    if dex in _raw_surface_cache:
        surf = _raw_surface_cache[dex]
        return surf or None
    with _lock:
        data = _bytes_cache.get(dex)
    if data is None:
        request(dex)
        return None
    if data is False:
        _raw_surface_cache[dex] = False
        return None
    try:
        surf = pygame.image.load(io.BytesIO(data))
        # Several of these sprite dumps (esp. the classic Gen I rips) have no
        # alpha channel at all -- just a flat white matte. Treat pure white as
        # transparent so they don't render as little white boxes in battle.
        surf.set_colorkey((255, 255, 255))
        surf = surf.convert_alpha()
    except Exception:
        surf = False
    _raw_surface_cache[dex] = surf
    return surf or None


def get_scaled_sprite(dex, size_px):
    """A real sprite scaled (pixelated, nearest-neighbour) and centered onto a
    size_px square, or None if it isn't available yet (still loading, or
    permanently unavailable -- caller should fall back to the procedural
    sprite in either case)."""
    key = (dex, size_px)
    if key in _scaled_cache:
        return _scaled_cache[key]
    raw = _get_raw_surface(dex)
    if raw is None:
        return None
    w, h = raw.get_size()
    if w == 0 or h == 0:
        return None
    scale = size_px / max(w, h)
    new_w, new_h = max(1, round(w * scale)), max(1, round(h * scale))
    scaled = pygame.transform.scale(raw, (new_w, new_h))
    canvas = pygame.Surface((size_px, size_px), pygame.SRCALPHA)
    canvas.blit(scaled, ((size_px - new_w) // 2, (size_px - new_h) // 2))
    _scaled_cache[key] = canvas
    return canvas
