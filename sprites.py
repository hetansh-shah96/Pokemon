"""
Battle sprites: real art when available, procedural Game Boy-style pixel
art otherwise.

generate_sprite() draws a small, deterministic pixel grid (seeded by dex
number) so every Pokemon has a distinct silhouette without hand-authoring
151 sprites, and needs no network access at all.

get_battle_sprite() is what the rest of the game should call: it prefers a
real sprite (see real_sprites.py) fetched in the background from a public
sprite repository, and transparently falls back to the procedural art
while that's loading (or forever, if there's no internet this session).
"""

import random
import pygame

from data import TYPE_COLORS
import real_sprites

GRID = 14
_CACHE = {}
_BATTLE_CACHE = {}


def _shade(color, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in color)


def _envelope(y, rows, types, proportions):
    """Half-width (0..1 fraction of half-grid) of the silhouette at row y."""
    head_end, torso_end, head_w, torso_w, leg_w = proportions
    t = y / (rows - 1)
    if t < head_end:
        w = head_w
    elif t < torso_end:
        w = torso_w
    else:
        w = leg_w
    if "Water" in types or "Ice" in types:
        w *= 1.08  # rounder, blobbier
    if "Rock" in types or "Ground" in types or "Fighting" in types:
        w = min(1.0, w * 1.05 + 0.05)  # blockier / bulkier
    if "Bug" in types:
        w *= 0.92
    return min(1.0, w)


def _build_grid(species):
    rng = random.Random(species.dex * 9973 + 17)
    half = GRID // 2
    grid = [[0] * GRID for _ in range(GRID)]
    types = species.types

    # per-species body proportions so silhouettes vary even within a type
    proportions = (
        rng.uniform(0.16, 0.30),           # head_end
        rng.uniform(0.55, 0.78),           # torso_end
        rng.uniform(0.35, 0.60),           # head_w
        rng.uniform(0.70, 1.0),            # torso_w
        rng.uniform(0.40, 0.65),           # leg_w
    )

    for y in range(GRID):
        w = _envelope(y, GRID, types, proportions)
        noise = rng.choice([-1, 0, 0, 0, 1])
        limit = max(1, min(half - 1, round(w * (half - 1)) + noise))
        leg_row = y / GRID > proportions[1]
        inner = 0
        if leg_row and "Ghost" not in types:
            # two legs/feet: hollow out the innermost column(s)
            inner = 1 if half > 4 else 0
        for x in range(half):
            if inner <= x <= limit:
                grid[y][half - 1 - x] = 1
                grid[y][half + x] = 1
        # jagged edge jitter for a hand-pixeled feel
        if rng.random() < 0.35 and limit + 1 < half:
            side = half + limit + 1
            if side < GRID:
                grid[y][side] = 1
                grid[y][GRID - 1 - side + 1] = 1

    if "Ghost" in types:
        # fade out the very bottom rows -> floating wisp look
        for y in range(GRID - 2, GRID):
            for x in range(GRID):
                if rng.random() < 0.6:
                    grid[y][x] = 0

    if "Flying" in types:
        # wing flare a few rows below the head, poking out past the torso
        wing_row = int(GRID * 0.38)
        for dy in (0, 1):
            y = min(GRID - 1, wing_row + dy)
            for x in range(GRID):
                w = _envelope(y, GRID, types, proportions)
                limit = max(1, round(w * (half - 1)))
                edge = half + limit + 1
                if 0 <= edge < GRID:
                    grid[y][edge] = 1
                    grid[y][GRID - 1 - edge] = 1

    if "Bug" in types:
        # antennae poking up above the head
        top_fill = [x for x in range(GRID) if grid[0][x]]
        if top_fill:
            cx = GRID // 2
            grid[0][cx - 2] = grid[0][cx - 2] or 0
        # represented via extra pixel above row 0 handled in render (skip)

    if "Fire" in types and "Flying" not in types:
        # small flame lick at the base, center bottom
        cx = GRID // 2
        for dx in (-1, 0, 1):
            x = cx + dx
            if 0 <= x < GRID:
                grid[GRID - 1][x] = 1

    if "Dragon" in types or "Ice" in types:
        # spiky crest on the head
        for x in range(GRID):
            if grid[1][x] and rng.random() < 0.5:
                grid[0][x] = 1

    return grid


def generate_sprite(species, size_px=112):
    key = (species.dex, size_px)
    if key in _CACHE:
        return _CACHE[key]

    grid = _build_grid(species)
    primary = TYPE_COLORS[species.type1]
    secondary = TYPE_COLORS[species.type2] if species.type2 else _shade(primary, 0.75)
    outline = _shade(primary, 0.35)
    eye_white = (248, 248, 248)
    eye_black = (24, 24, 24)

    cell = size_px // GRID
    surf = pygame.Surface((cell * GRID, cell * GRID), pygame.SRCALPHA)

    half = GRID // 2
    for y in range(GRID):
        for x in range(GRID):
            if not grid[y][x]:
                continue
            # alternate primary/secondary in a simple vertical banding for
            # a bit of shading interest without needing real shading logic
            band = secondary if (y > GRID * 0.68) else primary
            rect = pygame.Rect(x * cell, y * cell, cell, cell)
            surf.fill(band, rect)
            if y == 0 or y == GRID - 1 or x == 0 or x == GRID - 1:
                pygame.draw.rect(surf, outline, rect, max(1, cell // 8))

    # simple eyes, placed symmetrically in the head band
    eye_y = int(GRID * 0.16)
    for side in (-1, 1):
        ex = half + side * max(2, half // 3)
        if 0 <= ex < GRID:
            r = pygame.Rect(ex * cell, eye_y * cell, cell, cell)
            pygame.draw.rect(surf, eye_white, r)
            pupil = pygame.Rect(ex * cell + cell // 3, eye_y * cell + cell // 3, max(2, cell // 2), max(2, cell // 2))
            pygame.draw.rect(surf, eye_black, pupil)

    # a small mouth beneath the eyes -- just enough to read as a face
    mouth_y = eye_y + 2
    if mouth_y < GRID and grid[mouth_y][half - 1] and grid[mouth_y][half]:
        mw = max(2, half // 2)
        mouth = pygame.Rect((half - mw // 2) * cell, mouth_y * cell + cell // 2, mw * cell, max(2, cell // 4))
        pygame.draw.rect(surf, outline, mouth, border_radius=cell // 4)

    if species.legendary:
        # thin gold outline to mark the Elite computer's legendary tier
        gold = (255, 215, 64)
        pygame.draw.rect(surf, gold, surf.get_rect(), 2)

    _CACHE[key] = surf
    return surf


def get_battle_sprite(species, size_px=112):
    """Real sprite art if it's loaded (or becomes available), else the
    procedural placeholder -- always returns something drawable immediately."""
    key = (species.dex, size_px)
    real = real_sprites.get_scaled_sprite(species.dex, size_px)
    if real is not None:
        if not species.legendary:
            return real
        if key in _BATTLE_CACHE:
            return _BATTLE_CACHE[key]
        bordered = real.copy()
        pygame.draw.rect(bordered, (255, 215, 64), bordered.get_rect(), 2)
        _BATTLE_CACHE[key] = bordered
        return bordered
    return generate_sprite(species, size_px)


def draw_hp_bar(screen, rect, current, maximum, font=None):
    """Classic 3-color Game Boy HP bar with a dark bezel."""
    x, y, w, h = rect
    pygame.draw.rect(screen, (40, 40, 48), (x - 2, y - 2, w + 4, h + 4), border_radius=3)
    pygame.draw.rect(screen, (16, 16, 20), (x - 2, y - 2, w + 4, h + 4), 2, border_radius=3)
    pygame.draw.rect(screen, (60, 60, 68), (x, y, w, h))
    frac = 0 if maximum <= 0 else max(0.0, min(1.0, current / maximum))
    if frac > 0.5:
        color = (96, 200, 96)
    elif frac > 0.2:
        color = (240, 200, 64)
    else:
        color = (224, 72, 72)
    fill_w = int(w * frac)
    if fill_w > 0:
        pygame.draw.rect(screen, color, (x, y, fill_w, h))
    if font:
        label = f"{max(0, current)}/{maximum}"
        txt = font.render(label, False, (255, 255, 255))
        screen.blit(txt, (x + w - txt.get_width(), y + h + 2))


def type_badge(screen, pos, type_name, font):
    """Small colored, rounded type tag; returns the rect used (for layout)."""
    color = TYPE_COLORS[type_name]
    label = font.render(type_name.upper(), False, (18, 18, 18))
    pad_x, pad_y = 6, 2
    w, h = label.get_width() + pad_x * 2, label.get_height() + pad_y * 2
    rect = pygame.Rect(pos[0], pos[1], w, h)
    pygame.draw.rect(screen, color, rect, border_radius=4)
    pygame.draw.rect(screen, _shade(color, 0.6), rect, 1, border_radius=4)
    screen.blit(label, (rect.x + pad_x, rect.y + pad_y))
    return rect
