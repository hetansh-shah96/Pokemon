"""
Pokemon Indigo League Challenge
--------------------------------
A Game Boy-inspired, fully offline 6v6 Pokemon battle game.

Draft a team of 6 from the first 151 Pokemon (no legendaries allowed),
choose your battle arena, then face the computer's Legendary Six in a full
turn-based battle.

Run:  python main.py
"""

import asyncio
import math
import random

import pygame

import theme
from theme import (
    WIDE_W, WIDE_H, NARROW_W, NARROW_H, FPS, BG, BG_ALT, PANEL, PANEL_LIGHT, PANEL_EDGE, TEXT,
    TEXT_DIM, ACCENT, ACCENT_DIM, GOOD, BAD, INK, ARENA_THEMES, Button,
    draw_panel, draw_text, wrap_text, font,
)
import data
from data import PLAYABLE_SPECIES, LEGENDARY_SPECIES, TYPE_COLORS
import sprites
import battle


TEAM_SIZE = 6
SUGGESTION_COUNT = 10

# -- battle animation pacing --------------------------------------------
ATTACK_HIT_SECONDS = 4.5     # a landed, damaging hit: slow suspenseful HP drain
ATTACK_MISS_SECONDS = 1.4    # a miss / no-effect beat: quick, no bar to drain
TEXT_BEAT_SECONDS = 0.9      # switch-in announcements etc.
LUNGE_SECONDS = 0.35
SHAKE_DELAY = 0.15
SHAKE_SECONDS = 0.45
FAINT_SECONDS = 1.1

# -- team-builder reroll pacing ------------------------------------------
REROLL_SPIN_BASE_MS = 450    # every slot spins at least this long
REROLL_STAGGER_MS = 90       # then settles left-to-right, one slot at a time


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Pokemon Indigo League Challenge")
        try:
            desktop_w, desktop_h = pygame.display.get_desktop_sizes()[0]
        except Exception:
            desktop_w, desktop_h = WIDE_W, WIDE_H
        # A real (non-exclusive) window sized to fill the screen -- keeps the
        # normal title bar with minimize/maximize/close, unlike SDL fullscreen.
        self.window = pygame.display.set_mode((desktop_w, desktop_h), pygame.RESIZABLE)
        # Everything draws onto this fixed-size logical canvas, which then
        # gets scaled + letterboxed into whatever the real window size is.
        # The canvas itself switches between a landscape (wide) and portrait
        # (narrow) shape depending on the real window's aspect ratio -- see
        # the `W`/`H` properties and present().
        self.narrow = desktop_h > desktop_w
        self.screen = pygame.Surface((self.W, self.H))
        self._present_scale = 1.0
        self._present_offset = (0, 0)
        self.clock = pygame.time.Clock()
        self.rng = random.Random()
        self.state = "title"
        self.mouse_pos = (0, 0)
        self.hp_anim = {}   # id(BattleMon) -> displayed hp float, driven by the anim system
        self.running = True
        self.now_ms = 0
        self.idle_t = 0.0
        self.blink_next = {"player": 0, "cpu": 0}   # next scheduled blink, ms
        self.blink_until = {"player": 0, "cpu": 0}  # blinking (eyes shut) until this ms
        self._bbox_cache = {}  # id(sprite Surface) -> its visible (non-transparent) bounding rect
        self.start_new_run()

    # ------------------------------------------------------------------
    # Run / state reset
    # ------------------------------------------------------------------
    def start_new_run(self):
        self.team_species = []
        self.suggestions = []
        self.detail_species = None
        self.detail_index = None
        self.arena_choice = None
        self.battle = None
        self.battle_menu = "root"      # root / fight / switch / stats
        self.forced_switch_notice = False
        self.pending_end = False
        self.must_reroll = False       # True once a pick has been made from the current batch
        self.reroll_anim = None        # cascading slot-machine reroll animation state, or None
        self.visible_log = []          # log lines actually revealed so far
        self.anim_queue = []           # battle.TurnEvent objects awaiting playback
        self.anim_current = None
        self.anim_start = 0
        self.anim_duration = 0.0
        self.anim_lunge_side = None
        self.anim_shake_side = None
        self.faint_start = {}          # id(BattleMon) -> ms timestamp collapse animation began
        self.display_player_mon = None  # which mon's sprite/HUD to show right now (lags the
        self.display_cpu_mon = None     # real active index until its "sends out" beat plays)
        self.roll_suggestions()

    @property
    def battle_animating(self):
        return self.anim_current is not None or bool(self.anim_queue)

    @property
    def W(self):
        return NARROW_W if self.narrow else WIDE_W

    @property
    def H(self):
        return NARROW_H if self.narrow else WIDE_H

    def roll_suggestions(self):
        """Instant roll -- only used for the very first batch on screen entry."""
        pool = [s for s in PLAYABLE_SPECIES if s not in self.team_species]
        n = min(SUGGESTION_COUNT, len(pool))
        self.suggestions = self.rng.sample(pool, n)
        if self.suggestions:
            self.detail_species = self.suggestions[0]
            self.detail_index = ("suggestion", 0)

    def start_reroll(self):
        """Player-triggered reroll: cascading slot-machine shuffle before the
        new batch of 10 settles, one slot at a time, left to right."""
        if self.reroll_anim is not None:
            return
        pool = [s for s in PLAYABLE_SPECIES if s not in self.team_species]
        n = min(SUGGESTION_COUNT, len(pool))
        final = self.rng.sample(pool, n)
        spin_pool = pool if len(pool) >= 10 else PLAYABLE_SPECIES
        now = pygame.time.get_ticks()
        stops = [now + REROLL_SPIN_BASE_MS + i * REROLL_STAGGER_MS for i in range(n)]
        self.reroll_anim = {"final": final, "stops": stops, "pool": spin_pool}
        self.must_reroll = False

    def skip_reroll_anim(self):
        if self.reroll_anim is None:
            return
        self.reroll_anim["stops"] = [0] * len(self.reroll_anim["stops"])
        self._update_reroll_anim()

    def _update_reroll_anim(self):
        ra = self.reroll_anim
        now = self.now_ms
        if now >= max(ra["stops"], default=0):
            self.suggestions = ra["final"]
            self.reroll_anim = None
            if self.suggestions:
                self.detail_species = self.suggestions[0]
                self.detail_index = ("suggestion", 0)
            return
        tick = now // 70
        display = []
        for i in range(len(ra["final"])):
            if now >= ra["stops"][i]:
                display.append(ra["final"][i])
            else:
                flicker_rng = random.Random(tick * 97 + i)
                display.append(flicker_rng.choice(ra["pool"]))
        self.suggestions = display

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def to_logical(self, pos):
        """Map a real-window mouse position back into the fixed logical canvas."""
        ox, oy = self._present_offset
        s = self._present_scale or 1.0
        return ((pos[0] - ox) / s, (pos[1] - oy) / s)

    async def run(self):
        # An async loop (yielding once a frame via asyncio.sleep(0)) runs
        # identically under plain CPython and under pygbag/pyodide in the
        # browser, which requires cooperative yielding -- a blocking
        # `while True` loop would freeze the browser tab.
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    break
                elif event.type == pygame.VIDEORESIZE:
                    self.window = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                    continue
                if hasattr(event, "pos"):
                    event.pos = self.to_logical(event.pos)
                if event.type == pygame.MOUSEMOTION:
                    self.mouse_pos = event.pos
                else:
                    self.handle_event(event)
            if not self.running:
                break
            self.update()
            self.draw()
            pygame.display.flip()
            self.clock.tick(FPS)
            await asyncio.sleep(0)
        pygame.quit()

    def handle_event(self, event):
        handler = getattr(self, f"handle_{self.state}", None)
        if handler:
            handler(event)

    def update(self):
        self.now_ms = pygame.time.get_ticks()
        self.idle_t = self.now_ms / 1000.0
        if self.reroll_anim is not None:
            self._update_reroll_anim()
        if self.battle:
            self._update_battle_anim()

    # ------------------------------------------------------------------
    # Battle animation playback: turns battle.turn_events into a slow,
    # readable sequence -- lunge, hit flash, then a gradual HP drain -- so
    # the player can actually watch (and sweat) each blow land.
    # ------------------------------------------------------------------
    def _start_next_anim_event(self):
        ev = self.anim_queue.pop(0)
        self.anim_current = ev
        self.anim_start = self.now_ms
        self.anim_lunge_side = ev.attacker_side
        self.anim_shake_side = ev.defender_side if ev.has_damage else None
        if ev.is_faint_pause:
            self.anim_duration = FAINT_SECONDS
        elif ev.has_damage:
            self.anim_duration = ATTACK_HIT_SECONDS
        elif any(("missed" in l.lower() or "no effect" in l.lower()) for l in ev.lines):
            self.anim_duration = ATTACK_MISS_SECONDS
        else:
            self.anim_duration = TEXT_BEAT_SECONDS
        self.visible_log.extend(ev.lines)
        if ev.mon is not None:
            self.hp_anim[id(ev.mon)] = ev.hp_from
        if ev.switch_side == "player":
            self.display_player_mon = ev.switch_to_mon
        elif ev.switch_side == "cpu":
            self.display_cpu_mon = ev.switch_to_mon

    def _finish_anim_event(self):
        ev = self.anim_current
        if ev.mon is not None:
            self.hp_anim[id(ev.mon)] = ev.hp_to
            if ev.hp_to <= 0:
                self.faint_start[id(ev.mon)] = self.now_ms
        self.visible_log.extend(ev.end_lines)
        self.anim_current = None
        self.anim_lunge_side = None
        self.anim_shake_side = None

    def skip_battle_anim(self):
        """Fast-forward: resolve every queued beat instantly."""
        if self.anim_current is not None:
            self._finish_anim_event()
        while self.anim_queue:
            self._start_next_anim_event()
            self._finish_anim_event()

    def _update_blink(self):
        for side in ("player", "cpu"):
            if self.now_ms >= self.blink_next[side]:
                self.blink_until[side] = self.now_ms + 130
                self.blink_next[side] = self.now_ms + self.rng.randint(2500, 5500)

    def _update_battle_anim(self):
        self._update_blink()
        b = self.battle
        if self.anim_current is None and self.anim_queue:
            self._start_next_anim_event()
        if self.anim_current is None:
            for mon in b.player_team + b.cpu_team:
                if not mon.fainted:
                    self.hp_anim[id(mon)] = mon.current_hp
            self.display_player_mon = b.player_active
            self.display_cpu_mon = b.cpu_active
            return
        ev = self.anim_current
        elapsed = (self.now_ms - self.anim_start) / 1000.0
        t = min(1.0, elapsed / self.anim_duration) if self.anim_duration > 0 else 1.0
        if ev.mon is not None:
            eased = 1 - (1 - t) ** 2   # ease-out: fast start, settles at the end
            self.hp_anim[id(ev.mon)] = ev.hp_from + (ev.hp_to - ev.hp_from) * eased
        if t >= 1.0:
            self._finish_anim_event()

    def sprite_offset(self, side):
        """(dx, dy) pixel offset for the given side's sprite this frame --
        lunge toward the opponent, plus a gentle idle bob when at rest."""
        dx = dy = 0.0
        ev = self.anim_current
        if ev is not None:
            elapsed = (self.now_ms - self.anim_start) / 1000.0
            if self.anim_lunge_side == side and elapsed <= LUNGE_SECONDS:
                lunge_t = elapsed / LUNGE_SECONDS
                punch = math.sin(math.pi * lunge_t) * 20
                dx += punch if side == "player" else -punch
            if self.anim_shake_side == side:
                shake_t = elapsed - SHAKE_DELAY
                if 0 <= shake_t <= SHAKE_SECONDS:
                    decay = 1 - shake_t / SHAKE_SECONDS
                    dx += math.sin(shake_t * 45) * 9 * decay
        else:
            phase = 0.0 if side == "player" else 2.4
            dy += math.sin(self.idle_t * 2.2 + phase) * 3
        return dx, dy

    def flash_alpha(self, side):
        """Hit-flash intensity (0-160) for the given side's sprite this frame."""
        ev = self.anim_current
        if ev is None or self.anim_shake_side != side:
            return 0
        elapsed = (self.now_ms - self.anim_start) / 1000.0
        shake_t = elapsed - SHAKE_DELAY
        if 0 <= shake_t <= SHAKE_SECONDS:
            return int(160 * (1 - shake_t / SHAKE_SECONDS))
        return 0

    def faint_progress(self, mon):
        """0 = fully visible, 1 = fully collapsed/faded, for a fainted mon."""
        start = self.faint_start.get(id(mon))
        if start is None:
            return 0.0
        elapsed = (self.now_ms - start) / 1000.0
        return max(0.0, min(1.0, elapsed / FAINT_SECONDS))

    def draw(self):
        self._sync_canvas_mode()
        self.screen.fill(BG)
        drawer = getattr(self, f"draw_{self.state}", None)
        if drawer:
            drawer()
        self.present()

    def _sync_canvas_mode(self):
        """Switch between the landscape (wide) and portrait (narrow) logical
        canvas based on the real window's current aspect ratio -- this is
        what makes resizing the window (or rotating a phone) live-switch
        between the desktop and mobile layouts."""
        win_w, win_h = self.window.get_size()
        narrow = win_h > win_w
        if narrow != self.narrow:
            self.narrow = narrow
            self.screen = pygame.Surface((self.W, self.H))

    def present(self):
        """Scale the logical canvas into the real (possibly resized) window,
        letterboxing to preserve aspect ratio, and remember the transform so
        mouse coordinates can be mapped back correctly."""
        win_w, win_h = self.window.get_size()
        scale = max(0.01, min(win_w / self.W, win_h / self.H))
        out_w, out_h = max(1, int(self.W * scale)), max(1, int(self.H * scale))
        self._present_scale = scale
        self._present_offset = ((win_w - out_w) // 2, (win_h - out_h) // 2)
        if (out_w, out_h) != (win_w, win_h):
            self.window.fill((0, 0, 0))
        if (out_w, out_h) == (self.W, self.H):
            scaled = self.screen
        else:
            scaled = pygame.transform.smoothscale(self.screen, (out_w, out_h))
        self.window.blit(scaled, self._present_offset)

    # ==================================================================
    # TITLE SCREEN
    # ==================================================================
    def handle_title(self, event):
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            self.state = "builder"

    def draw_title(self):
        self.screen.fill((14, 18, 14))
        for i in range(6):
            pygame.draw.rect(self.screen, (20 + i * 2, 26 + i * 2, 20 + i * 2),
                              (0, i * (self.H // 6), self.W, self.H // 6))
        draw_text(self.screen, "POKEMON", (self.W // 2, self.H // 2 - 110), size=70,
                  color=ACCENT, bold=True, center=True, shadow=True)
        draw_text(self.screen, "INDIGO LEAGUE CHALLENGE", (self.W // 2, self.H // 2 - 40),
                  size=34, color=TEXT, bold=True, center=True, shadow=True)
        draw_text(self.screen, "Draft a team of 6. Choose your arena.", (self.W // 2, self.H // 2 + 30),
                  size=20, color=TEXT_DIM, center=True)
        draw_text(self.screen, "Face the Legendary Six -- and try to survive.", (self.W // 2, self.H // 2 + 58),
                  size=20, color=TEXT_DIM, center=True)
        if (pygame.time.get_ticks() // 500) % 2 == 0:
            draw_text(self.screen, "PRESS ENTER OR CLICK TO START", (self.W // 2, self.H - 90),
                      size=22, color=ACCENT, bold=True, center=True)

    # ==================================================================
    # TEAM BUILDER SCREEN
    # ==================================================================
    SIDEBAR_W = 260

    def builder_layout(self):
        return self.builder_layout_narrow() if self.narrow else self.builder_layout_wide()

    def team_slot_rects(self):
        return self.team_slot_rects_narrow() if self.narrow else self.team_slot_rects_wide()

    def builder_buttons(self):
        return self.builder_buttons_narrow() if self.narrow else self.builder_buttons_wide()

    def builder_layout_wide(self):
        cards = []
        cols, rows = 5, 2
        margin = 14
        card_w = (self.W - self.SIDEBAR_W - margin * (cols + 1)) // cols
        card_h = 150
        top = 70
        for i, sp in enumerate(self.suggestions):
            c, r = i % cols, i // cols
            x = margin + c * (card_w + margin)
            y = top + r * (card_h + margin)
            cards.append((sp, pygame.Rect(x, y, card_w, card_h)))
        return cards

    def team_slot_rects_wide(self):
        rects = []
        x = self.W - self.SIDEBAR_W + 8
        top = 70
        for i in range(TEAM_SIZE):
            rects.append(pygame.Rect(x, top + i * 66, self.SIDEBAR_W - 26, 58))
        return rects

    def builder_buttons_wide(self):
        reroll = Button((18, self.H - 66, 220, 46), "REROLL (R)")
        ready = len(self.team_species) == TEAM_SIZE
        confirm = Button((self.W - self.SIDEBAR_W + 8, self.H - 66, self.SIDEBAR_W - 26, 46),
                          "CONFIRM TEAM (ENTER)", enabled=ready)
        return reroll, confirm

    # -- portrait layout: cards (2x5) -> team strip -> detail -> buttons ----
    def builder_layout_narrow(self):
        cards = []
        cols = 2
        margin = 12
        card_w = (self.W - margin * (cols + 1)) // cols
        card_h = 140
        top = 70
        for i, sp in enumerate(self.suggestions):
            c, r = i % cols, i // cols
            x = margin + c * (card_w + margin)
            y = top + r * (card_h + margin)
            cards.append((sp, pygame.Rect(x, y, card_w, card_h)))
        return cards

    def _builder_grid_bottom_narrow(self):
        rows = 5
        return 70 + rows * 140 + (rows - 1) * 12

    def team_slot_rects_narrow(self):
        rects = []
        top = self._builder_grid_bottom_narrow() + 44
        margin = 14
        gap = 8
        slot_w = (self.W - margin * 2 - gap * (TEAM_SIZE - 1)) // TEAM_SIZE
        for i in range(TEAM_SIZE):
            x = margin + i * (slot_w + gap)
            rects.append(pygame.Rect(x, top, slot_w, 90))
        return rects

    def builder_buttons_narrow(self):
        y = self.H - 70
        reroll = Button((14, y, 340, 50), "REROLL (R)")
        ready = len(self.team_species) == TEAM_SIZE
        confirm = Button((self.W - 14 - 340, y, 340, 50), "CONFIRM (ENTER)", enabled=ready)
        return reroll, confirm

    def handle_builder(self, event):
        # Mid-spin: any input just fast-forwards the reroll animation.
        if self.reroll_anim is not None:
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.skip_reroll_anim()
            return

        cards = self.builder_layout()
        slots = self.team_slot_rects()
        reroll, confirm = self.builder_buttons()

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                self.start_reroll()
            elif event.key == pygame.K_RETURN and confirm.enabled:
                self.go_to_arena()
            elif not self.must_reroll and pygame.K_1 <= event.key <= pygame.K_9:
                idx = event.key - pygame.K_1
                self.try_add_suggestion(idx)
            elif not self.must_reroll and event.key == pygame.K_0:
                self.try_add_suggestion(9)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if reroll.hit(pos):
                self.start_reroll()
                return
            if confirm.hit(pos):
                self.go_to_arena()
                return
            if not self.must_reroll:
                for i, (sp, rect) in enumerate(cards):
                    if rect.collidepoint(pos):
                        self.detail_species = sp
                        self.detail_index = ("suggestion", i)
                        self.try_add_suggestion(i)
                        return
            for i, rect in enumerate(slots):
                if rect.collidepoint(pos) and i < len(self.team_species):
                    self.detail_species = self.team_species[i]
                    self.detail_index = ("team", i)
                    self.remove_from_team(i)
                    return

    def try_add_suggestion(self, idx):
        if self.must_reroll or self.reroll_anim is not None:
            return
        if idx >= len(self.suggestions):
            return
        if len(self.team_species) >= TEAM_SIZE:
            return
        sp = self.suggestions.pop(idx)
        self.team_species.append(sp)
        self.must_reroll = len(self.team_species) < TEAM_SIZE
        if self.suggestions:
            self.detail_species = self.suggestions[min(idx, len(self.suggestions) - 1)]
            self.detail_index = ("suggestion", min(idx, len(self.suggestions) - 1))

    def remove_from_team(self, idx):
        self.team_species.pop(idx)

    def go_to_arena(self):
        if len(self.team_species) == TEAM_SIZE:
            self.state = "arena"

    def draw_builder(self):
        (self.draw_builder_narrow if self.narrow else self.draw_builder_wide)()

    def _builder_header_text(self, spinning):
        if spinning:
            return "Rerolling...", TEXT_DIM, False
        if self.must_reroll:
            return "Pick locked in! Reroll to see your next choice.", ACCENT, True
        return f"{len(self.team_species)}/{TEAM_SIZE} chosen -- tap a card to draft it", TEXT_DIM, False

    def _draw_builder_card(self, sp, rect, i, spinning):
        still_spinning = spinning and self.now_ms < self.reroll_anim["stops"][i]
        hovered = (not spinning and not self.must_reroll) and rect.collidepoint(self.mouse_pos)
        focused = (not spinning) and self.detail_species is sp
        if still_spinning:
            pulse = 128 + int(100 * math.sin(self.now_ms / 60))
            edge = (pulse, pulse, 40)
        elif self.must_reroll and not spinning:
            edge = PANEL_EDGE
        else:
            edge = ACCENT if focused else PANEL_EDGE
        bg = PANEL_LIGHT if hovered else PANEL
        if self.must_reroll and not spinning:
            bg = (30, 33, 30)
        draw_panel(self.screen, rect, bg=bg, edge=edge, width=3 if (focused or still_spinning) else 2)
        icon = sprites.get_battle_sprite(sp, size_px=48)
        if self.must_reroll and not spinning:
            icon = icon.copy()
            icon.set_alpha(110)
        self.screen.blit(icon, (rect.x + 6, rect.y + 6))
        name_color = TEXT_DIM if (self.must_reroll and not spinning) else TEXT
        draw_text(self.screen, sp.name, (rect.x + 60, rect.y + 8), size=13, color=name_color, bold=True)
        tx = rect.x + 6
        ty = rect.y + 58
        for t in sp.types:
            b = sprites.type_badge(self.screen, (tx, ty), t, font(9, bold=True))
            tx = b.right + 3
        draw_text(self.screen, f"HP{sp.hp}  ATK{sp.atk}", (rect.x + 6, rect.y + 86), size=11, color=TEXT_DIM)
        draw_text(self.screen, f"DEF{sp.dfn}  SPA{sp.spa}", (rect.x + 6, rect.y + 101), size=11, color=TEXT_DIM)
        draw_text(self.screen, f"SPD{sp.spd}  SPE{sp.spe}", (rect.x + 6, rect.y + 116), size=11, color=TEXT_DIM)
        draw_text(self.screen, f"BST {sp.bst}", (rect.x + 6, rect.y + 132), size=12, color=ACCENT, bold=True)

    def draw_builder_wide(self):
        spinning = self.reroll_anim is not None
        draw_text(self.screen, "BUILD YOUR TEAM", (18, 18), size=28, color=ACCENT, bold=True)
        header, header_color, header_bold = self._builder_header_text(spinning)
        draw_text(self.screen, header, (18, 48), size=16, color=header_color, bold=header_bold)

        cards = self.builder_layout()
        for i, (sp, rect) in enumerate(cards):
            self._draw_builder_card(sp, rect, i, spinning)

        # team panel
        panel_rect = pygame.Rect(self.W - self.SIDEBAR_W, 40, self.SIDEBAR_W - 18, TEAM_SIZE * 66 + 20)
        draw_panel(self.screen, panel_rect, bg=BG_ALT)
        draw_text(self.screen, "YOUR TEAM", (panel_rect.x + 12, 46), size=18, color=ACCENT, bold=True)
        slots = self.team_slot_rects()
        for i, rect in enumerate(slots):
            draw_panel(self.screen, rect, bg=PANEL, edge=PANEL_EDGE, width=1)
            if i < len(self.team_species):
                sp = self.team_species[i]
                icon = sprites.get_battle_sprite(sp, size_px=48)
                self.screen.blit(icon, (rect.x + 4, rect.y + 4))
                draw_text(self.screen, sp.name, (rect.x + 58, rect.y + 8), size=15, color=TEXT, bold=True)
                draw_text(self.screen, sp.type_label, (rect.x + 58, rect.y + 30), size=12, color=TEXT_DIM)
                draw_text(self.screen, "click to drop", (rect.right - 10, rect.y + 8), size=10, color=TEXT_DIM)
            else:
                draw_text(self.screen, f"Slot {i + 1} -- empty", rect.center, size=14, color=TEXT_DIM, center=True)

        detail_rect = pygame.Rect(18, 406, self.W - self.SIDEBAR_W - 36, self.H - 406 - 82)
        self.draw_detail_panel(detail_rect)

        reroll, confirm = self.builder_buttons()
        reroll.draw(self.screen, hovered=reroll.rect.collidepoint(self.mouse_pos),
                    selected=self.must_reroll and not spinning)
        confirm.draw(self.screen, hovered=confirm.rect.collidepoint(self.mouse_pos))
        if not confirm.enabled:
            draw_text(self.screen, "Pick 6 Pokemon to continue", (confirm.rect.centerx, confirm.rect.bottom + 16),
                      size=13, color=TEXT_DIM, center=True)

    def draw_builder_narrow(self):
        spinning = self.reroll_anim is not None
        draw_text(self.screen, "BUILD YOUR TEAM", (14, 16), size=26, color=ACCENT, bold=True)
        header, header_color, header_bold = self._builder_header_text(spinning)
        draw_text(self.screen, header, (14, 46), size=14, color=header_color, bold=header_bold)

        cards = self.builder_layout()
        for i, (sp, rect) in enumerate(cards):
            self._draw_builder_card(sp, rect, i, spinning)

        grid_bottom = self._builder_grid_bottom_narrow()
        draw_text(self.screen, "YOUR TEAM", (14, grid_bottom + 14), size=16, color=ACCENT, bold=True)
        slots = self.team_slot_rects()
        for i, rect in enumerate(slots):
            draw_panel(self.screen, rect, bg=PANEL, edge=PANEL_EDGE, width=1)
            if i < len(self.team_species):
                sp = self.team_species[i]
                icon = sprites.get_battle_sprite(sp, size_px=44)
                self.screen.blit(icon, (rect.centerx - 22, rect.y + 4))
                draw_text(self.screen, sp.name[:9], (rect.centerx, rect.y + 52), size=10,
                          color=TEXT, bold=True, center=True)
            else:
                draw_text(self.screen, f"#{i + 1}", rect.center, size=13, color=TEXT_DIM, center=True)

        reroll, confirm = self.builder_buttons()
        detail_rect = pygame.Rect(14, slots[0].bottom + 14, self.W - 28, reroll.rect.y - slots[0].bottom - 28)
        self.draw_detail_panel(detail_rect)

        reroll.draw(self.screen, hovered=reroll.rect.collidepoint(self.mouse_pos),
                    selected=self.must_reroll and not spinning)
        confirm.draw(self.screen, hovered=confirm.rect.collidepoint(self.mouse_pos))

    def draw_detail_panel(self, rect):
        draw_panel(self.screen, rect, bg=BG_ALT)
        sp = self.detail_species
        if not sp:
            draw_text(self.screen, "Select a Pokemon to inspect it.", rect.center, size=14,
                      color=TEXT_DIM, center=True)
            return
        pad = 14
        x, y = rect.x + pad, rect.y + pad
        icon = sprites.get_battle_sprite(sp, size_px=96)
        self.screen.blit(icon, (x, y))
        head_x = x + 108
        draw_text(self.screen, sp.name, (head_x, y), size=22, color=TEXT, bold=True)
        tx = head_x
        ty = y + 30
        for t in sp.types:
            b = sprites.type_badge(self.screen, (tx, ty), t, font(12, bold=True))
            tx = b.right + 4
        draw_text(self.screen, f"Lv.{battle.PLAYER_LEVEL}   BST {sp.bst}", (head_x, y + 56), size=14, color=ACCENT)

        body_y = y + 108
        col_w = (rect.width - pad * 3) // 2
        stats_x = x
        moves_x = x + col_w + pad
        maxstat = 180

        stats = [("HP", sp.hp), ("Atk", sp.atk), ("Def", sp.dfn),
                  ("SpA", sp.spa), ("SpD", sp.spd), ("Spe", sp.spe)]
        yy = body_y
        for label, val in stats:
            draw_text(self.screen, f"{label}", (stats_x, yy), size=13, color=TEXT_DIM)
            draw_text(self.screen, str(val), (stats_x + 40, yy), size=13, color=TEXT, bold=True)
            bar_rect = pygame.Rect(stats_x + 74, yy + 3, col_w - 74, 8)
            pygame.draw.rect(self.screen, PANEL, bar_rect)
            frac = min(1.0, val / maxstat)
            color = GOOD if frac > 0.55 else (ACCENT if frac > 0.3 else BAD)
            pygame.draw.rect(self.screen, color, (bar_rect.x, bar_rect.y, int(bar_rect.w * frac), bar_rect.h))
            yy += 21

        draw_text(self.screen, "MOVES", (moves_x, body_y - 18), size=13, color=ACCENT, bold=True)
        moves = data.build_moveset(sp.type1, sp.type2)
        yy = body_y
        for m in moves:
            sprites.type_badge(self.screen, (moves_x, yy), m.type, font(9, bold=True))
            draw_text(self.screen, m.name, (moves_x + 58, yy), size=12, color=TEXT)
            draw_text(self.screen, f"P{m.power}/A{m.accuracy}", (moves_x + col_w - 66, yy),
                      size=11, color=TEXT_DIM)
            yy += 25

    # ==================================================================
    # ARENA SELECT SCREEN
    # ==================================================================
    def arena_tiles(self):
        return self.arena_tiles_narrow() if self.narrow else self.arena_tiles_wide()

    def arena_tiles_wide(self):
        names = ["Water", "Fire", "Desert", "Grass"]
        tiles = []
        margin = 24
        w = (self.W - 340 - margin * 5) // 4
        h = 300
        top = 130
        for i, name in enumerate(names):
            x = margin + i * (w + margin)
            tiles.append((name, pygame.Rect(x, top, w, h)))
        return tiles

    def arena_tiles_narrow(self):
        names = ["Water", "Fire", "Desert", "Grass"]
        tiles = []
        margin = 24
        top = 70
        h = 170
        gap = 12
        w = self.W - margin * 2
        for i, name in enumerate(names):
            y = top + i * (h + gap)
            tiles.append((name, pygame.Rect(margin, y, w, h)))
        return tiles

    def handle_arena(self, event):
        tiles = self.arena_tiles()
        back = Button((18, self.H - 66, 200, 46), "BACK")
        go = Button((self.W - 270, self.H - 66, 250, 46), "ENTER BATTLE!", enabled=self.arena_choice is not None)
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN and go.enabled:
                self.start_battle()
            elif event.key == pygame.K_ESCAPE:
                self.state = "builder"
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if back.hit(pos):
                self.state = "builder"
                return
            if go.hit(pos):
                self.start_battle()
                return
            for name, rect in tiles:
                if rect.collidepoint(pos):
                    self.arena_choice = name

    def start_battle(self):
        if not self.arena_choice:
            return
        theme_type = ARENA_THEMES[self.arena_choice]["type"]
        player_team = battle.build_player_team(self.team_species)
        cpu_team = battle.build_cpu_team(self.rng)
        self.battle = battle.Battle(player_team, cpu_team, arena_type=theme_type, rng=self.rng)
        intro = [
            f"The {self.arena_choice} Arena battle begins!",
            f"Go, {self.battle.player_active.name}!",
            f"The opposing trainer sends out {self.battle.cpu_active.name}!",
        ]
        self.battle.log.extend(intro)
        self.visible_log = list(intro)
        self.anim_queue = []
        self.anim_current = None
        self.faint_start = {}
        self.display_player_mon = self.battle.player_active
        self.display_cpu_mon = self.battle.cpu_active
        now = pygame.time.get_ticks()
        self.blink_next = {"player": now + self.rng.randint(1500, 4000),
                            "cpu": now + self.rng.randint(1500, 4000)}
        self.blink_until = {"player": 0, "cpu": 0}
        self.hp_anim = {}
        for m in player_team + cpu_team:
            self.hp_anim[id(m)] = m.current_hp
        self.battle_menu = "root"
        self.state = "battle"

    def draw_arena(self):
        (self.draw_arena_narrow if self.narrow else self.draw_arena_wide)()

    def _draw_arena_roster_and_buttons(self, panel_rect, icon_size=64):
        draw_panel(self.screen, panel_rect, bg=BG_ALT)
        draw_text(self.screen, "YOUR OPPONENTS -- THE LEGENDARY SIX",
                  (panel_rect.x + 14, panel_rect.y + 10), size=16, color=ACCENT, bold=True)
        x = panel_rect.x + 14
        y = panel_rect.y + 40
        step = icon_size + 32
        per_row = max(1, (panel_rect.width - 28) // step)
        for i, sp in enumerate(LEGENDARY_SPECIES):
            icon = sprites.get_battle_sprite(sp, size_px=icon_size)
            col = i % per_row
            row = i // per_row
            ix = x + col * step
            iy = y + row * (icon_size + 24)
            self.screen.blit(icon, (ix, iy))
            draw_text(self.screen, sp.name, (ix, iy + icon_size + 2), size=11, color=TEXT, center=False)

        back = Button((18, self.H - 66, 200, 46), "BACK")
        go = Button((self.W - 270, self.H - 66, 250, 46), "ENTER BATTLE!", enabled=self.arena_choice is not None)
        back.draw(self.screen, hovered=back.rect.collidepoint(self.mouse_pos))
        go.draw(self.screen, hovered=go.rect.collidepoint(self.mouse_pos))

    def draw_arena_wide(self):
        draw_text(self.screen, "CHOOSE YOUR ARENA", (18, 18), size=28, color=ACCENT, bold=True)
        draw_text(self.screen, "The arena's type gets a +20% power boost -- for both sides.",
                  (18, 50), size=15, color=TEXT_DIM)

        for name, rect in self.arena_tiles():
            th = ARENA_THEMES[name]
            selected = self.arena_choice == name
            hovered = rect.collidepoint(self.mouse_pos)
            draw_panel(self.screen, rect, bg=th["panel"], edge=ACCENT if selected else (th["accent"] if hovered else PANEL_EDGE),
                       width=4 if selected else 2)
            draw_text(self.screen, name.upper(), (rect.centerx, rect.y + 30), size=24, color=th["accent"], bold=True, center=True)
            sprites.type_badge(self.screen, (rect.centerx - 30, rect.y + 60), th["type"], font(13, bold=True))
            lines = wrap_text(th["blurb"], 14, rect.width - 30)
            ly = rect.y + 100
            for line in lines:
                draw_text(self.screen, line, (rect.centerx, ly), size=14, color=TEXT, center=True)
                ly += 20
            count = sum(1 for sp in self.team_species if th["type"] in sp.types)
            draw_text(self.screen, f"{count}/6 share this type",
                      (rect.centerx, rect.bottom - 24), size=12, color=ACCENT if count else TEXT_DIM, center=True)

        # Legendary Six roster reveal
        panel = pygame.Rect(24, 450, self.W - 48, 150)
        self._draw_arena_roster_and_buttons(panel)

    def draw_arena_narrow(self):
        draw_text(self.screen, "CHOOSE YOUR ARENA", (14, 14), size=22, color=ACCENT, bold=True)
        draw_text(self.screen, "+20% power boost to that type, for both sides.",
                  (14, 44), size=13, color=TEXT_DIM)

        for name, rect in self.arena_tiles():
            th = ARENA_THEMES[name]
            selected = self.arena_choice == name
            hovered = rect.collidepoint(self.mouse_pos)
            draw_panel(self.screen, rect, bg=th["panel"], edge=ACCENT if selected else (th["accent"] if hovered else PANEL_EDGE),
                       width=4 if selected else 2)
            draw_text(self.screen, name.upper(), (rect.x + 16, rect.y + 14), size=20, color=th["accent"], bold=True)
            sprites.type_badge(self.screen, (rect.x + 16, rect.y + 44), th["type"], font(12, bold=True))
            count = sum(1 for sp in self.team_species if th["type"] in sp.types)
            draw_text(self.screen, f"{count}/6 share type",
                      (rect.x + 16, rect.bottom - 24), size=12, color=ACCENT if count else TEXT_DIM)
            lines = wrap_text(th["blurb"], 13, rect.width - 170)
            ly = rect.y + 16
            for line in lines[:5]:
                draw_text(self.screen, line, (rect.x + 150, ly), size=13, color=TEXT)
                ly += 19

        panel_y = self.arena_tiles()[3][1].bottom + 16
        panel = pygame.Rect(14, panel_y, self.W - 28, 160)
        self._draw_arena_roster_and_buttons(panel, icon_size=56)

    # ==================================================================
    # BATTLE SCREEN
    # ==================================================================
    def battle_menu_buttons(self):
        return self.battle_menu_buttons_narrow() if self.narrow else self.battle_menu_buttons_wide()

    def move_buttons(self):
        return self.move_buttons_narrow() if self.narrow else self.move_buttons_wide()

    def party_buttons(self):
        return self.party_buttons_narrow() if self.narrow else self.party_buttons_wide()

    def _battle_back_rect(self):
        if self.narrow:
            return pygame.Rect(14, self.H - 44, self.W - 28, 34)
        return pygame.Rect(self.W - 300, self.H - 44, 270, 34)

    def battle_menu_buttons_wide(self):
        x = self.W - 300
        y = self.H - 190
        return [
            Button((x, y, 270, 44), "FIGHT"),
            Button((x, y + 50, 270, 44), "SWITCH"),
            Button((x, y + 100, 270, 44), "STATS"),
        ]

    def move_buttons_wide(self):
        mon = self.battle.player_active
        rects = []
        x = self.W - 300
        y = self.H - 190
        for i, m in enumerate(mon.moves):
            rects.append((i, m, pygame.Rect(x, y + i * 46, 270, 40)))
        return rects

    def party_buttons_wide(self):
        rects = []
        x = self.W - 300
        y = self.H - 190
        for i, mon in enumerate(self.battle.player_team):
            rects.append((i, mon, pygame.Rect(x, y + i * 30, 270, 26)))
        return rects

    # -- portrait layout: a full-width action panel pinned to the bottom ----
    def _battle_menu_top_narrow(self):
        return self.H - 300

    def battle_menu_buttons_narrow(self):
        x, y, w = 14, self._battle_menu_top_narrow(), self.W - 28
        return [
            Button((x, y, w, 54), "FIGHT"),
            Button((x, y + 62, w, 54), "SWITCH"),
            Button((x, y + 124, w, 54), "STATS"),
        ]

    def move_buttons_narrow(self):
        mon = self.battle.player_active
        rects = []
        x, y, w = 14, self._battle_menu_top_narrow(), self.W - 28
        for i, m in enumerate(mon.moves):
            rects.append((i, m, pygame.Rect(x, y + i * 58, w, 52)))
        return rects

    def party_buttons_narrow(self):
        rects = []
        x, y, w = 14, self._battle_menu_top_narrow(), self.W - 28
        for i, mon in enumerate(self.battle.player_team):
            rects.append((i, mon, pygame.Rect(x, y + i * 40, w, 34)))
        return rects

    def handle_battle(self, event):
        b = self.battle

        # While a blow is playing out, any click/key just fast-forwards it --
        # the menu is locked out until the animation queue is drained.
        if self.battle_animating:
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.skip_battle_anim()
            return

        if b.winner:
            if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
                self.state = "result"
            return

        if b.awaiting_player_switch:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, mon, rect in self.party_buttons():
                    if rect.collidepoint(event.pos) and not mon.fainted and i != b.player_active_idx:
                        b.switch_player(i)
                        self.visible_log.append(f"Go, {b.player_active.name}!")
                        self.battle_menu = "root"
            return

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.battle_menu = "root"
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        pos = event.pos

        if self.battle_menu == "root":
            for i, btn in enumerate(self.battle_menu_buttons()):
                if btn.hit(pos):
                    self.battle_menu = ["fight", "switch", "stats"][i]
        elif self.battle_menu == "fight":
            for i, m, rect in self.move_buttons():
                if rect.collidepoint(pos):
                    b.take_turn(("move", i))
                    self.anim_queue = list(b.turn_events)
                    self.battle_menu = "root"
        elif self.battle_menu == "switch":
            for i, mon, rect in self.party_buttons():
                if rect.collidepoint(pos) and not mon.fainted and i != b.player_active_idx:
                    b.take_turn(("switch", i))
                    self.anim_queue = list(b.turn_events)
                    self.battle_menu = "root"
            back = self._battle_back_rect()
            if back.collidepoint(pos):
                self.battle_menu = "root"
        elif self.battle_menu == "stats":
            back = self._battle_back_rect()
            if back.collidepoint(pos):
                self.battle_menu = "root"

    def draw_hud(self, mon, rect, is_player):
        draw_panel(self.screen, rect, bg=BG_ALT)
        draw_text(self.screen, mon.name, (rect.x + 12, rect.y + 8), size=18, color=TEXT, bold=True)
        draw_text(self.screen, f"Lv.{mon.level}", (rect.right - 60, rect.y + 8), size=14, color=TEXT_DIM)
        bar_rect = (rect.x + 12, rect.y + 34, rect.width - 24, 14)
        shown = int(round(self.hp_anim.get(id(mon), mon.current_hp)))
        sprites.draw_hp_bar(self.screen, bar_rect, shown, mon.max_hp, font(12) if is_player else None)
        if not is_player:
            draw_text(self.screen, f"{max(0, shown)}/{mon.max_hp}", (rect.x + 12, rect.y + 52),
                      size=12, color=TEXT_DIM)
        tx = rect.x + 12
        ty = rect.y + (70 if not is_player else 52)
        for t in mon.species.types:
            b = sprites.type_badge(self.screen, (tx, ty), t, font(10, bold=True))
            tx = b.right + 4

    def get_bbox(self, icon):
        """Cached visible (non-transparent) bounding rect of a sprite Surface
        -- real images have wildly varying padding, so anything we overlay
        (like a blink band) needs to be positioned relative to the actual
        art, not the padded canvas."""
        key = id(icon)
        bbox = self._bbox_cache.get(key)
        if bbox is None:
            bbox = icon.get_bounding_rect()
            if bbox.width == 0 or bbox.height == 0:
                bbox = icon.get_rect()
            self._bbox_cache[key] = bbox
        return bbox

    def apply_blink(self, surf, bbox):
        """Overlay a brief dark band across the estimated eye-line -- a cheap
        approximation of blinking that works on any sprite (real photo/art
        or procedural), since we can't know exact eye pixels on real art."""
        out = surf.copy()
        band_h = max(2, int(bbox.height * 0.09))
        band_y = bbox.y + int(bbox.height * 0.16)
        band = pygame.Surface((bbox.width, band_h), pygame.SRCALPHA)
        band.fill((12, 12, 16, 235))
        out.blit(band, (bbox.x, band_y))
        return out

    def draw_battler_sprite(self, mon, base_pos, size_px, side):
        """Draws one battler with idle bob / attack lunge / hit flash / faint
        collapse / blink layered on top of its sprite."""
        fp = self.faint_progress(mon) if mon.fainted else 0.0
        if fp >= 1.0:
            return
        icon = sprites.get_battle_sprite(mon.species, size_px=size_px)
        if fp == 0 and self.now_ms < self.blink_until.get(side, 0):
            icon = self.apply_blink(icon, self.get_bbox(icon))
        dx, dy = self.sprite_offset(side)
        if fp > 0:
            scale_y = max(0.04, 1 - fp)
            new_h = max(1, int(icon.get_height() * scale_y))
            icon = pygame.transform.smoothscale(icon, (icon.get_width(), new_h)).convert_alpha()
            icon.set_alpha(max(0, int(255 * (1 - fp))))
            dy += size_px * (1 - scale_y)
        pos = (base_pos[0] + dx, base_pos[1] + dy)
        self.screen.blit(icon, pos)
        flash = self.flash_alpha(side)
        if flash > 0 and fp == 0:
            overlay = pygame.Surface(icon.get_size(), pygame.SRCALPHA)
            overlay.fill((255, 50, 50, flash))
            self.screen.blit(overlay, pos)

    def draw_battle(self):
        (self.draw_battle_narrow if self.narrow else self.draw_battle_wide)()

    def _draw_battle_action_panel(self, menu_rect):
        """Everything that goes inside the action-menu box -- FIGHT/SWITCH/
        STATS, the move list, the party list, forced-switch prompt, and the
        animating/winner overlays. Fully shared between layouts: it only
        ever reads button rects via battle_menu_buttons()/move_buttons()/
        party_buttons(), which already resolve to the right mode."""
        b = self.battle
        draw_panel(self.screen, menu_rect, bg=BG_ALT)

        if self.battle_animating:
            draw_text(self.screen, "...", (menu_rect.centerx, menu_rect.y + 20), size=22, color=TEXT_DIM, center=True)
            draw_text(self.screen, "(click to skip)", (menu_rect.centerx, menu_rect.bottom - 20),
                      size=12, color=TEXT_DIM, center=True)
            return

        if b.winner:
            draw_text(self.screen, "Click to continue...", menu_rect.center, size=16, color=ACCENT, center=True)
            return

        if b.awaiting_player_switch:
            draw_text(self.screen, "Choose your next Pokemon!", (menu_rect.x + 15, menu_rect.y + 8),
                      size=15, color=BAD, bold=True)
            for i, mon, rect in self.party_buttons():
                fainted = mon.fainted
                active = i == b.player_active_idx
                bg = (30, 34, 30) if fainted else PANEL_LIGHT
                draw_panel(self.screen, rect, bg=bg, width=1)
                label = f"{mon.name}  {max(0, mon.current_hp)}/{mon.max_hp}"
                color = TEXT_DIM if fainted else TEXT
                draw_text(self.screen, label, (rect.x + 8, rect.y + 5), size=13, color=color)
            return

        if self.battle_menu == "root":
            for btn in self.battle_menu_buttons():
                btn.draw(self.screen, hovered=btn.rect.collidepoint(self.mouse_pos))
        elif self.battle_menu == "fight":
            for i, m, rect in self.move_buttons():
                hovered = rect.collidepoint(self.mouse_pos)
                draw_panel(self.screen, rect, bg=PANEL_LIGHT if hovered else PANEL, width=2)
                sprites.type_badge(self.screen, (rect.x + 6, rect.y + 6), m.type, font(10, bold=True))
                draw_text(self.screen, m.name, (rect.x + 70, rect.y + 6), size=14, color=TEXT, bold=True)
                draw_text(self.screen, f"PWR {m.power}  ACC {m.accuracy}", (rect.x + 70, rect.y + 22),
                          size=11, color=TEXT_DIM)
        elif self.battle_menu == "switch":
            for i, mon, rect in self.party_buttons():
                fainted = mon.fainted
                active = i == b.player_active_idx
                bg = (30, 34, 30) if fainted else (ACCENT_DIM if active else PANEL)
                draw_panel(self.screen, rect, bg=bg, width=1)
                label = f"{mon.name}  {max(0, mon.current_hp)}/{mon.max_hp}"
                draw_text(self.screen, label, (rect.x + 8, rect.y + 4), size=13,
                          color=TEXT_DIM if fainted else TEXT)
            back = self._battle_back_rect()
            draw_panel(self.screen, back, bg=PANEL_LIGHT if back.collidepoint(self.mouse_pos) else PANEL)
            draw_text(self.screen, "BACK", back.center, size=14, color=TEXT, center=True)
        elif self.battle_menu == "stats":
            self.draw_battle_stats(menu_rect)

    def draw_battle_wide(self):
        b = self.battle
        arena_name = self.arena_choice or "Water"
        th = ARENA_THEMES[arena_name]
        self.screen.fill(th["bg"])
        pygame.draw.rect(self.screen, th["panel"], (0, self.H - 260, self.W, 260))

        cpu_mon = self.display_cpu_mon or b.cpu_active
        player_mon = self.display_player_mon or b.player_active
        self.draw_battler_sprite(cpu_mon, (self.W - 220, 60), 140, "cpu")
        self.draw_battler_sprite(player_mon, (70, self.H - 470), 170, "player")

        self.draw_hud(cpu_mon, pygame.Rect(30, 40, 320, 90), is_player=False)
        self.draw_hud(player_mon, pygame.Rect(self.W - 400, self.H - 360, 340, 100), is_player=True)

        # log panel
        log_rect = pygame.Rect(20, self.H - 240, self.W - 340, 220)
        draw_panel(self.screen, log_rect, bg=(10, 12, 10))
        lines = self.visible_log[-9:]
        ly = log_rect.y + 12
        for line in lines:
            draw_text(self.screen, line, (log_rect.x + 14, ly), size=16, color=TEXT)
            ly += 23

        menu_rect = pygame.Rect(self.W - 320, self.H - 240, 300, 220)
        self._draw_battle_action_panel(menu_rect)

    def draw_battle_narrow(self):
        b = self.battle
        arena_name = self.arena_choice or "Water"
        th = ARENA_THEMES[arena_name]
        self.screen.fill(th["bg"])

        cpu_mon = self.display_cpu_mon or b.cpu_active
        player_mon = self.display_player_mon or b.player_active

        self.draw_hud(cpu_mon, pygame.Rect(14, 14, self.W - 28, 88), is_player=False)
        self.draw_battler_sprite(cpu_mon, (self.W // 2 - 70, 108), 140, "cpu")

        self.draw_hud(player_mon, pygame.Rect(14, 258, self.W - 28, 98), is_player=True)
        self.draw_battler_sprite(player_mon, (self.W // 2 - 85, 362), 170, "player")

        menu_top = self._battle_menu_top_narrow() - 34
        log_rect = pygame.Rect(14, 548, self.W - 28, menu_top - 548 - 10)
        draw_panel(self.screen, log_rect, bg=(10, 12, 10))
        lines = self.visible_log[-12:]
        ly = log_rect.y + 10
        for line in lines:
            draw_text(self.screen, line, (log_rect.x + 12, ly), size=15, color=TEXT)
            ly += 21

        menu_rect = pygame.Rect(10, menu_top, self.W - 20, self.H - menu_top - 10)
        self._draw_battle_action_panel(menu_rect)

    def draw_battle_stats(self, menu_rect):
        mon = self.battle.player_active
        sp = mon.species
        x, y = menu_rect.x + 12, menu_rect.y + 8
        draw_text(self.screen, sp.name, (x, y), size=16, color=TEXT, bold=True)
        stats = [("HP", mon.current_hp, mon.max_hp), ("Atk", mon.atk, None), ("Def", mon.dfn, None),
                  ("SpA", mon.spa, None), ("SpD", mon.spd, None), ("Spe", mon.spe, None)]
        yy = y + 24
        for label, val, out_of in stats:
            text = f"{label}: {val}/{out_of}" if out_of else f"{label}: {val}"
            draw_text(self.screen, text, (x, yy), size=13, color=TEXT_DIM)
            yy += 18
        back = self._battle_back_rect()
        draw_panel(self.screen, back, bg=PANEL_LIGHT if back.collidepoint(self.mouse_pos) else PANEL)
        draw_text(self.screen, "BACK", back.center, size=14, color=TEXT, center=True)

    # ==================================================================
    # RESULT SCREEN
    # ==================================================================
    def handle_result(self, event):
        again = Button((self.W // 2 - 260, self.H - 130, 240, 56), "PLAY AGAIN")
        quit_btn = Button((self.W // 2 + 20, self.H - 130, 240, 56), "QUIT")
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if again.hit(event.pos):
                self.start_new_run()
                self.state = "title"
            elif quit_btn.hit(event.pos):
                self.running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                self.start_new_run()
                self.state = "title"
            elif event.key == pygame.K_ESCAPE:
                self.running = False

    def draw_result(self):
        b = self.battle
        won = b.winner == "player"
        self.screen.fill((16, 30, 18) if won else (32, 14, 14))
        title = "YOU ARE THE CHAMPION!" if won else "THE LEGENDARY SIX PREVAIL..."
        draw_text(self.screen, title, (self.W // 2, 160), size=42, color=ACCENT if won else BAD,
                  bold=True, center=True, shadow=True)
        sub = ("Your team out-battled every legendary in Kanto." if won
               else "Train harder and challenge the Legendary Six again.")
        draw_text(self.screen, sub, (self.W // 2, 220), size=18, color=TEXT, center=True)

        p_ko = sum(1 for m in b.player_team if m.fainted)
        c_ko = sum(1 for m in b.cpu_team if m.fainted)
        draw_text(self.screen, f"Your Pokemon fainted: {p_ko}/6", (self.W // 2, 280), size=16, color=TEXT_DIM, center=True)
        draw_text(self.screen, f"Legendary Six fainted: {c_ko}/6", (self.W // 2, 306), size=16, color=TEXT_DIM, center=True)

        again = Button((self.W // 2 - 260, self.H - 130, 240, 56), "PLAY AGAIN")
        quit_btn = Button((self.W // 2 + 20, self.H - 130, 240, 56), "QUIT")
        again.draw(self.screen, hovered=again.rect.collidepoint(self.mouse_pos))
        quit_btn.draw(self.screen, hovered=quit_btn.rect.collidepoint(self.mouse_pos))


if __name__ == "__main__":
    asyncio.run(Game().run())
