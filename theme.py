"""Shared look & feel: palette, fonts, and small drawing/UI helpers."""

import pygame

WIDTH, HEIGHT = 1080, 720
FPS = 60

# -- palette: a muted, slightly-phosphor GBC-screen feel ---------------------
BG = (18, 22, 19)
BG_ALT = (24, 30, 25)
PANEL = (40, 48, 40)
PANEL_EDGE = (14, 18, 14)
PANEL_LIGHT = (66, 78, 64)
TEXT = (224, 236, 214)
TEXT_DIM = (150, 168, 142)
ACCENT = (250, 210, 64)      # gold -- selection / legendary
ACCENT_DIM = (150, 126, 42)
GOOD = (104, 200, 120)
BAD = (222, 76, 76)
INK = (16, 18, 16)

ARENA_THEMES = {
    "Water":  {"bg": (18, 40, 64), "panel": (26, 58, 92), "accent": (104, 176, 240), "type": "Water",
               "blurb": "Rolling tides sap fire and steady footing. Water-type attacks crash down harder."},
    "Fire":   {"bg": (58, 24, 16), "panel": (94, 40, 22), "accent": (240, 128, 56), "type": "Fire",
               "blurb": "Cinder Plateau's heat thins the air. Fire-type attacks blaze even fiercer."},
    "Desert": {"bg": (58, 46, 20), "panel": (94, 76, 34), "accent": (222, 188, 96), "type": "Ground",
               "blurb": "Cracked earth and shifting dunes. Ground-type attacks hit like a landslide."},
    "Grass":  {"bg": (20, 46, 22), "panel": (32, 70, 34), "accent": (128, 208, 88), "type": "Grass",
               "blurb": "Deep, tangled overgrowth. Grass-type attacks take root and strike true."},
}

_FONT_CACHE = {}


def font(size, bold=False, mono="consolas"):
    key = (size, bold, mono)
    if key not in _FONT_CACHE:
        path = pygame.font.match_font(mono, bold=bold) or pygame.font.get_default_font()
        _FONT_CACHE[key] = pygame.font.Font(path, size)
    return _FONT_CACHE[key]


def render(text, size, color, bold=False, aa=True):
    return font(size, bold).render(text, aa, color)


def draw_panel(screen, rect, bg=PANEL, edge=PANEL_EDGE, radius=6, width=3):
    pygame.draw.rect(screen, bg, rect, border_radius=radius)
    pygame.draw.rect(screen, edge, rect, width, border_radius=radius)


def draw_text(screen, text, pos, size=20, color=TEXT, bold=False, aa=True, center=False, shadow=False):
    surf = render(text, size, color, bold=bold, aa=aa)
    r = surf.get_rect()
    if center:
        r.center = pos
    else:
        r.topleft = pos
    if shadow:
        sh = render(text, size, INK, bold=bold, aa=aa)
        screen.blit(sh, (r.x + 2, r.y + 2))
    screen.blit(surf, r)
    return r


def wrap_text(text, size, max_width, bold=False):
    words = text.split(" ")
    lines, cur = [], ""
    f = font(size, bold)
    for w in words:
        test = (cur + " " + w).strip()
        if f.size(test)[0] > max_width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


class Button:
    def __init__(self, rect, label, size=22, enabled=True, sub=None):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.size = size
        self.enabled = enabled
        self.sub = sub

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)

    def draw(self, screen, hovered=False, selected=False):
        bg = PANEL_LIGHT if (hovered and self.enabled) else PANEL
        if selected:
            bg = ACCENT_DIM
        if not self.enabled:
            bg = (30, 34, 30)
        draw_panel(screen, self.rect, bg=bg, edge=ACCENT if selected else PANEL_EDGE,
                   width=3 if selected else 2)
        color = TEXT if self.enabled else TEXT_DIM
        draw_text(screen, self.label, self.rect.center, size=self.size, color=color,
                   bold=True, center=True)
        if self.sub:
            draw_text(screen, self.sub, (self.rect.centerx, self.rect.bottom - 14),
                      size=13, color=TEXT_DIM, center=True)
