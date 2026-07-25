# Pokemon Indigo League Challenge — build progress

A Pygame Game Boy-style Pokemon battle game (Gen 1 / Kanto only). Player
drafts a team of 6 from randomized suggestions (no legendaries), picks a
battle arena, then fights the computer's fixed "Legendary Six" (Articuno,
Zapdos, Moltres, Mewtwo, Mew, Dragonite) in a full 6v6 battle with HP bars,
type effectiveness, crits, switching, and a matchup-aware AI.

Run with: `pip install -r requirements.txt` then `python main.py` from this
folder. Note: plain `pygame` has no prebuilt wheel yet for very new Python
versions (this machine runs 3.14) — `pygame-ce` was installed instead; it's
a drop-in replacement (same `import pygame`).

**Web build command (IMPORTANT, do not forget the flags):**
```
python -m pygbag --build --template web_template/pygbag.tmpl --width 1080 --height 720 .
```
Then commit the resulting `build/web/*`. **Gotcha discovered the hard way:**
running `python -m pygbag .` (dev server, no `--build`) auto-rebuilds the
site using *whatever flags you pass that invocation* -- run it without
`--template`/`--width`/`--height` even once and it silently regenerates
`build/web/` with pygbag's stock template and 1280x720 canvas, undoing the
custom template. Always pass the same three flags, every time, build or
serve.

Project lives at `C:\Users\Parag Shah\OneDrive\Desktop\Pokemon` (moved here
from a scratch folder partway through the build, at the user's request).
Also pushed to `https://github.com/hetansh-shah96/Pokemon` (separate,
independent git repo scoped to just this folder -- the parent Desktop
folder is itself a *different*, unrelated git repo for a family-tree
project; do not run git commands here expecting them to touch that one).

## Update 2026-07-25 (fourth pass): web build for Vercel via pygbag

The user wanted this playable as a link (Vercel/Railway). Pygame can't run
on either as a native desktop app -- there's no display attached to a
serverless/container host. Chosen fix: **pygbag**, which compiles a Pygame
project to WebAssembly so it runs in a browser `<canvas>`. The desktop
build (`python main.py`) is fully preserved and behaves identically; the
web path is additive, gated behind `sys.platform == "emscripten"` checks,
never changing desktop code paths.

- **`main.py`**: `Game.run()` is now `async def run()`, looping on
  `self.running` (a flag, not `sys.exit()`) and calling
  `await asyncio.sleep(0)` once per frame -- required so the browser's
  single-threaded event loop gets a chance to breathe; harmless/invisible
  on desktop. Entry point is now `asyncio.run(Game().run())`. The
  `QUIT`-button and Escape-key handlers in the result screen now set
  `self.running = False` instead of calling `pygame.quit(); sys.exit()`
  (sys.exit() inside a coroutine is the wrong tool on any platform, not
  just web).
- **`theme.py`** `font()`: on desktop, unchanged (Consolas/Courier via
  `pygame.font.match_font`). Under `sys.platform == "emscripten"`, loads a
  bundled font file instead, since Windows system fonts don't exist in a
  browser sandbox. Picked **VT323** (`fonts/VT323-Regular.ttf`, SIL OFL --
  `fonts/OFL.txt` included) specifically because it measured *narrower*
  than Consolas at every size tested (see this conversation's font-width
  comparison against Space Mono, which measured wider and was rejected for
  overflow risk against the game's many tightly-fit text areas). Sized up
  ~15% (`_WEB_SIZE_BOOST`) since VT323 reads smaller per point than
  Consolas even though it's narrower.
- **`real_sprites.py`**: added `_web_fetch()`, an async function using
  `pyodide.http.pyfetch` (there are no raw sockets in a browser -- `urllib`
  cannot work there at all), scheduled via `asyncio.ensure_future()`
  instead of `threading.Thread` (no real OS threads without
  cross-origin-isolation, which this deploy doesn't assume). Gated by
  `_IS_WEB = sys.platform == "emscripten"` in `request()`; the desktop
  threading+urllib+disk-cache path is 100% unchanged and still primary/
  best-tested. **No persistent disk cache on web** (pyodide's default
  virtual filesystem doesn't survive a page reload) -- just an in-memory
  cache for the session; the browser's own HTTP cache covers repeat plays.
  Confirmed `raw.githubusercontent.com` sends `Access-Control-Allow-Origin: *`
  so this fetch won't hit CORS problems from any hosting domain.
- **`pygbag.ini`** (note: `.ini` extension despite TOML-ish syntax --
  `.toml` is silently ignored, this cost real debugging time, don't rename
  it): excludes `sprite_cache/`, `build/`, `.git/`, `__pycache__/` from
  what pygbag bundles into the app package.
- **`build/web/`** -- the actual built static site (`index.html`,
  `pokemon.apk`, `pokemon.tar.gz`, `favicon.png`) is committed directly to
  the repo on purpose, and IS tracked by git (only `build/web-cache/`,
  pygbag's own local template-download cache, is ignored). This means
  Vercel needs **no build step at all** -- see `vercel.json`
  (`"buildCommand": false`, `outputDirectory: "build/web"`). Rebuild after
  any code change with: `pip install pygbag` then
  `python -m pygbag --build .` from this folder, then commit the new
  `build/web/*`.

## Update 2026-07-26 (sixth pass): full responsive (mobile/portrait) redesign

User chose a genuine portrait-native redesign over a "rotate your phone"
stopgap. Implemented as a **dual logical canvas + per-screen dispatch**,
approved via plan mode first (see the plan file this session referenced,
or just read this section -- it captures the same design).

- `theme.py`: `WIDE_W, WIDE_H = 1080, 720` (landscape, unchanged values)
  and new `NARROW_W, NARROW_H = 720, 1280` (portrait, 9:16-ish).
- `main.py` `Game`: `self.narrow` (bool), plus `W`/`H` properties
  resolving to the narrow or wide constants. `_sync_canvas_mode()` (called
  at the top of every `draw()`) recomputes `narrow` from
  `self.window.get_size()` (`win_h > win_w`) and recreates `self.screen`
  on any *change* -- this is what makes resizing the desktop window, or a
  phone rotating, live-switch layouts, verified directly (resized a real
  window from landscape to portrait and back, mid-run).
  `present()`/`to_logical()` use `self.W`/`self.H` instead of the old bare
  module constants.
- **Key pattern that made this tractable**: `handle_builder`,
  `handle_arena`, and `handle_battle` never needed to change at all --
  they were already written to call layout-getter methods
  (`builder_layout()`, `arena_tiles()`, `battle_menu_buttons()`,
  `move_buttons()`, `party_buttons()`) rather than hardcoding coordinates
  inline. So only those getters (plus the `draw_*` methods) needed
  wide/narrow variants; every event handler stayed a single shared
  implementation. If you extend this later, keep new screens following
  that same discipline -- it's the whole reason this didn't turn into 2x
  the event-handling code too.
- Per screen:
  - **Title, Result**: adapt via the `W`/`H` swap alone (already-
    proportional math) -- no dispatcher needed.
  - **Builder**: `builder_layout`/`team_slot_rects`/`builder_buttons`/
    `draw_builder` each became a 1-line dispatcher to `_wide`/`_narrow`
    siblings. Narrow: 2x5 card grid, team as a 6-icon horizontal strip,
    Pokedex detail panel below (reuses `draw_detail_panel` completely
    unchanged -- it was already parameterized by an arbitrary `rect`),
    Reroll/Confirm stacked as two half-width buttons at the bottom.
  - **Arena**: same dispatcher pattern. Narrow: 4 tiles stacked in one
    column (landscape-shaped tiles: name/badge/share-count on the left,
    blurb text to the right, rather than the wide version's centered
    vertical stack) via a new shared `_draw_arena_roster_and_buttons()`
    helper (auto-wraps the 6-icon roster into rows based on available
    width, so it's correct in both modes without a size-specific fork).
  - **Battle**: the biggest one. Extracted the action-menu *rendering*
    (FIGHT/SWITCH/STATS, move list, party list, forced-switch prompt,
    animating/winner overlays) into a shared `_draw_battle_action_panel
    (menu_rect)` -- it only ever reads button rects through the
    already-dispatching getters, so it needed zero mode-awareness itself.
    Only the outer "scene" composition differs:
    `draw_battle_wide`/`draw_battle_narrow` position the HUDs/sprites/log
    panel differently (narrow: everything stacked vertically, CPU then
    player then log, with the action panel pinned to the bottom ~300px
    for thumb reach) and then both call the same
    `_draw_battle_action_panel`. `draw_hud`, `draw_battler_sprite`, and
    `draw_battle_stats` needed *no changes* -- already parameterized by
    the caller-supplied rect/position, exactly like `draw_detail_panel`.

### Verified

- Full narrow-mode regression: draft (with compulsory reroll + slot-
  machine animation) -> arena -> battle (forced switches, fainting,
  animation skip) -> result, via direct handler calls, across multiple
  seeded trials -- no crashes, no mis-registered clicks.
- Full **wide**-mode regression re-run after the refactor (same style),
  confirming zero behavior change to the desktop experience the user had
  already approved.
- Live resize test in a real (non-headless) window: started landscape,
  resized to a portrait aspect mid-run, resized back -- `self.narrow`
  and `self.screen`'s size flipped correctly both directions, no crash.
- Headless screenshots of every narrow screen/sub-state (builder empty
  and mid-pick, arena unselected and selected, battle root/fight/switch/
  stats) -- checked visually for overlap and clipping, none found.
- Rebuilt the pygbag web bundle (same command as before, see above) and
  confirmed the packaged `.apk` contains the updated `main.py`/`theme.py`.
- **Not verified**: an actual phone browser. Touch-to-mouse translation
  under pygbag/emscripten should map taps to the same `MOUSEBUTTONDOWN`
  handling already tested, but that's inference, not a live check --
  ask the user to confirm on their own device after this deploys.

## Update 2026-07-25 (fifth pass): fixed the live Vercel deploy's look

User deployed to Vercel (pokemon-dexp.vercel.app) and reported it looked
"squeezed in" with grey margins on all sides, plus an ugly stock green/blue
"Ready to start" gate on load. Root-caused by reading pygbag's actual
cached template (`build/web-cache/*.tmpl`) rather than guessing:

- pygbag's default template centers the canvas in a box sized to a
  **hardcoded `fb_ar: 1.77`** (16:9) aspect ratio, regardless of what your
  actual game canvas looks like -- our game is 1080x720 = **1.5** aspect,
  not 1.77. That mismatch was causing a *second*, redundant letterbox
  layer on top of the first (pygbag's own box, sized wrong, nested inside
  which our own `Game.present()` was correctly but pointlessly letterboxing
  again) -- hence the "double margin, too squeezed" look.
- The green/blue "Ready to start" box and greyish backdrop are pygbag's
  literal placeholder defaults (`background: green; color: blue` in the
  stock template) -- not a bug, just unstyled scaffolding nobody's meant to
  ship as-is.

Fix: `web_template/pygbag.tmpl` is now a **customized copy** of pygbag's
default template (`--template web_template/pygbag.tmpl` flag, see build
command above), with targeted changes only:
- `fb_ar` corrected from `1.77` to `1.5` to match the real canvas.
- Build now explicitly passed `--width 1080 --height 720` (was defaulting
  to pygbag's own 1280x720) so the declared screen size matches too.
- Body/html/canvas backgrounds recolored to the game's dark palette
  (`#12160f`) instead of grey/powderblue, so any residual margin blends in
  rather than clashing.
- `#infobox` (the click-to-start gate) restyled dark-green/gold/monospace
  to match the game instead of stock green/blue, and its message changed
  to "POKEMON INDIGO LEAGUE -- Click or tap to start".
- Deliberately did **not** force the canvas to `100vw/100vh` via
  `!important` (considered it, backed off) -- that would have overridden
  pygbag's own resize mechanism blindly, and without a real browser to
  test in, risked *stretching/distorting* the image instead of fixing it.
  The `fb_ar` correction is the well-understood, low-risk fix; if the
  remaining margin still bothers you after this deploy, that forced-fill
  approach is the next thing to try, but test it live, don't assume it.
- `web_template/` is excluded from the actual app bundle via
  `pygbag.ini`'s `ignoreDirs` (it's a build input for the HTML wrapper,
  not Python app source).

### What was actually verified vs. not

Verified, with real (not assumed) evidence:
- Full desktop regression after the async refactor: headless multi-trial
  playthroughs (draft->reroll->arena->battle->result) via direct handler
  calls, **plus** a from-scratch integration test that drives the actual
  `asyncio`-based `run()` loop through the real `pygame.event` queue with
  correctly-transformed screen coordinates (a first attempt at this test
  posted un-transformed logical coordinates and got a false-positive hang
  on the forced-switch screen's narrow party-button rects -- the game
  itself was fine, the test was buggy; fixed by converting logical->real
  coordinates via `_present_scale`/`_present_offset` before posting, same
  math as `Game.to_logical` in reverse).
- `pygbag --build .` completes without error and produces a well-formed
  `build/web/` (inspected `pokemon.apk`'s contents directly -- exactly the
  9 expected project files/fonts, nothing extra).
- The pygbag local dev server (`python -m pygbag .`, no `--build`) starts
  and correctly serves `index.html` and `pokemon.apk` over HTTP (checked
  via `curl`, matching content-lengths, correct CORS/COOP headers).

**NOT verified** (no real browser available in this environment):
- That the game actually boots and plays correctly once pyodide loads it
  in a real browser tab. The async loop structure and `pyodide.http.pyfetch`
  usage follow documented pygbag/pyodide conventions as closely as I could
  confirm from pygbag's own installed source, but the WASM/JS runtime
  interaction itself is untested live. **Before deploying to Vercel,
  it's worth running `python -m pygbag .` locally and opening
  `http://localhost:8000` in an actual browser first** to catch anything
  that only shows up at runtime (font rendering, sprite fetch over
  `pyfetch`, canvas sizing) -- that 5-minute check is cheap insurance
  against debugging it for the first time on a live Vercel deploy.

## Status (last updated: 2026-07-25) — FEATURE-COMPLETE, PLAYTESTED

All six planned pieces are built and have been exercised end-to-end
(headless simulation + a real, non-headless pygame window smoke test on
this machine). Nothing is known-broken as of this update.

- [x] `data.py` — all 151 Kanto species w/ real base stats & types, type
      chart, per-type move pools, `build_moveset()`. Legendary tier =
      Articuno/Zapdos/Moltres/Mewtwo/Mew/**Dragonite** (Dragonite added as
      the 6th slot since Gen 1 only has 5 true legendaries but the brief
      asked for a computer team of 6 — flagged to the user, they didn't
      object).
- [x] `sprites.py` — deterministic procedural pixel-art silhouettes per
      species (seeded by dex #, varied proportions/jitter so they don't all
      look the same), colored by type, type badges, HP bar drawer. No
      external images/fonts (works fully offline).
- [x] `battle.py` — BattleMon stats-at-level, Gen1-style physical/special
      split by move type, damage formula (STAB/effectiveness/crit/arena
      bonus/variance), AI (`ai_choose_action`, matchup-aware switching),
      `Battle` class (turn resolution, forced switches, win condition).
      **Balance tuning done via simulation** (see below) —
      `PLAYER_LEVEL = 60`, `CPU_LEVEL = 55`. At this gap: a random/careless
      player team wins ~0-1% of the time; a deliberately type-countered
      team wins ~33-36%. This is intentional — team-building skill should
      matter a lot. If it ever feels off, these two constants + the
      `expected_score`/`ai_choose_action` heuristics in `battle.py` are the
      knobs to turn.
- [x] `theme.py` — palette (muted GBC-phosphor greens + gold accent),
      Consolas-based retro font helpers, `Button` widget, `draw_panel`,
      arena theme table (`ARENA_THEMES`: Water/Fire/Desert/Grass, each maps
      to a real battle type for the +20%/arena power bonus — Desert maps to
      Ground since Gen 1 has no dedicated Ground arena look, Grass matches
      Grass, etc).
- [x] `main.py` — full game loop + all 5 screens (Title, Team Builder,
      Arena Select, Battle, Result), state machine, mouse + keyboard input.
      Layout was iterated on after visual QA screenshots caught real bugs
      (card text/badges overflowing at the original 5-col width, the
      detail/Pokedex panel overflowing into the Confirm button, the arena
      "N/6 share this type" caption overlapping between tiles, the player
      HUD box sitting in a confusing spot) — all fixed; see "Known-good
      layout notes" below before changing dimensions again.

## Known-good layout notes (read before resizing anything)

- Team Builder: `Game.SIDEBAR_W = 260` is the single source of truth for
  the right-hand "Your Team" column width; card grid width derives from it
  in `builder_layout()`. The big horizontal "Pokedex" detail panel lives
  *below* the card grid (full width minus sidebar), not squeezed into the
  sidebar — there wasn't enough vertical room there for 6 stat bars + 4
  moves. If you add more suggestion rows/cols, re-check this detail panel's
  y-position (`draw_builder`, `detail_rect = ...`) still fits above the
  bottom button row.
- Arena Select: the per-tile "N/6 share this type" caption must stay short
  — a longer string centered on a ~190px-wide tile overflows into the
  neighboring tile's text. Keep it under ~20 chars or shrink the font.
- Battle screen: player HUD box is at `(WIDTH-400, HEIGHT-360, 340, 100)`,
  deliberately anchored just above the log panel (`HEIGHT-240`) rather than
  up near the CPU sprite — that earlier position read as confusing/floating
  in playtesting.
- All of the above was verified visually, not just by "it imports fine" —
  screenshots were rendered via `SDL_VIDEODRIVER=dummy` +
  `pygame.image.save()` and inspected directly. If you change layout code,
  do the same rather than trusting it blind.

## Update 2026-07-25 (later same day): windowing + battle animation pass

Follow-up request: proper full-screen sizing with a minimize button, a
slow/suspenseful HP-drain animation per hit (4-5s), and more lifelike
battler animation. All implemented:

- **Windowing** (`main.py` `Game.__init__`/`present()`/`run()`): the real OS
  window (`self.window`) now opens at the desktop resolution via
  `pygame.display.get_desktop_sizes()` with the `RESIZABLE` flag -- fills
  the screen but keeps a normal title bar (minimize/maximize/close all
  work), unlike exclusive `pygame.FULLSCREEN` which has no chrome at all.
  Everything still draws onto a fixed 1080x720 logical canvas
  (`self.screen`, unchanged from before), which `present()` scales +
  letterboxes into the real window every frame. Mouse coordinates are
  mapped back from real-window space to logical space via
  `Game.to_logical()`, applied to every event with a `.pos` in `run()`.
  `VIDEORESIZE` re-creates the window surface. If you ever touch this,
  don't rename `self.screen` back to meaning "the display" -- the
  canvas/window split is now load-bearing.
- **Battle animation** (`battle.py` `TurnEvent` + `main.py`
  `_update_battle_anim`/`_start_next_anim_event`/`_finish_anim_event`):
  `Battle.take_turn()` now also records a `self.turn_events` list -- one
  `TurnEvent` per beat (move announcement, miss, damage, faint, switch-in)
  instead of just dumping strings into `self.log`. `main.py` plays these
  back one at a time: a landed hit drains the HP bar over
  `ATTACK_HIT_SECONDS = 4.5s` (eased, not linear) while the attacker lunges
  and the defender flashes red and shakes; a KO gets its own
  `is_faint_pause` beat (`FAINT_SECONDS = 1.1s`) so the collapse
  (squash + fade, see `draw_battler_sprite`) is actually visible before the
  next Pokemon appears. The menu is locked out during playback
  (`Game.battle_animating`); clicking or pressing any key fast-forwards the
  whole queue instantly (`skip_battle_anim`) as an escape hatch -- default
  pacing is still the full slow drain.
  - Important subtlety: `Battle.cpu_active`/`player_active` (by index) can
    already point at a *replacement* Pokemon internally before its
    "sends out" beat has actually played (since `take_turn` resolves the
    whole turn's logic synchronously up front). Rendering must NOT read
    `b.cpu_active`/`b.player_active` directly during playback -- use
    `Game.display_cpu_mon`/`display_player_mon`, which only advance when a
    `TurnEvent` tagged `switch_side`/`switch_to_mon` actually plays. They
    resync to the real active mon automatically whenever nothing is
    animating. If you add new event types, keep this pattern.
- **Character animation** (`main.py` `sprite_offset`/`flash_alpha`/
  `faint_progress`, `sprites.py`): idle mons get a continuous small
  vertical bob (sine wave, desynced per side) so they read as alive even
  between turns; sprites also got a small mouth added under the eyes
  purely for readability/character. No new assets, still fully procedural
  and offline.

Playtested via both headless (`SDL_VIDEODRIVER=dummy`, screenshotting
mid-animation frames by manipulating `anim_start`/`faint_start` to check
lunge/drain/collapse render correctly) and a real, non-headless window
running live for several seconds. Nothing known-broken.

## Update 2026-07-25 (third pass): drafting lock, real sprites, blink, easier difficulty

Follow-up request: force a reroll between picks instead of letting the
player cherry-pick several Pokemon from one batch of 10, animate that
reroll, use real Pokemon sprite images instead of only procedural art,
make battlers blink, hide the CPU's level on the arena screen, and lower
the difficulty because random/careless teams basically never won.

- **Compulsory reroll** (`main.py`): `Game.must_reroll` is set the instant
  a card is drafted and blocks every other pick (`try_add_suggestion`,
  the number-key shortcuts, and card clicks in `handle_builder`) until
  `start_reroll()` runs. Locked cards render dimmed/greyed with a faded
  icon; the Reroll button highlights gold via `Button(..., selected=True)`.
- **Reroll animation**: `start_reroll()` precomputes the real next batch
  (`reroll_anim['final']`) plus a per-slot stop time cascading left to
  right (`REROLL_SPIN_BASE_MS` + `REROLL_STAGGER_MS * i`). Until each
  slot's stop time, `main.py` `_update_reroll_anim()` fills that slot with
  a fast, deterministically-seeded (`tick = now//70`) random flicker
  Pokemon instead of the real pick -- a cheap "slot machine" effect with no
  extra assets. `Game.suggestions` *is* the display list during the spin
  (overwritten every frame), so `draw_builder`'s existing card-rendering
  code needed no changes beyond a gold pulsing border on still-spinning
  slots. Any click/key mid-spin calls `skip_reroll_anim()` to fast-forward,
  same escape-hatch pattern as the battle animation skip.
- **Real sprite images** (`real_sprites.py`, new file + `sprites.py`
  `get_battle_sprite()`): fetches the classic small Gen I pixel sprites
  from PokeAPI's public sprite repo (`raw.githubusercontent.com/PokeAPI/
  sprites`, falling back to the modern default sprite if the Gen I path
  404s for a given dex) on background daemon threads, caches the raw bytes
  to `sprite_cache/{dex}.png` on disk and the decoded/scaled Surface in
  memory. **Fully non-blocking and offline-safe**: the main thread never
  waits on the network -- `get_battle_sprite()` returns the procedural
  sprite immediately if the real one isn't loaded yet (or never will be),
  and a single genuine network-level failure (not a 404) sets a
  session-wide `_offline` flag so every subsequent call skips straight to
  the procedural fallback with zero delay. **Important gotcha already hit
  and fixed**: these sprite dumps have no alpha channel, just a flat white
  matte -- `_get_raw_surface` calls `surf.set_colorkey((255,255,255))`
  before `convert_alpha()` or every sprite renders as a white box. The
  legendary gold border is applied in `get_battle_sprite` (not inside
  `real_sprites.py`) so it's consistent whether the art is real or
  procedural. `sprites.generate_sprite()` (the old procedural path) is
  unchanged and is still exactly what renders until/unless the real image
  arrives. This is personal fan-project use of a well-known public
  developer sprite resource, not a commercial redistribution -- worth
  knowing if this project's scope or audience ever changes.
- **Blinking** (`main.py` `apply_blink`/`get_bbox`/`_update_blink`): every
  few seconds (`random 2.5-5.5s`), each active battler blinks for ~130ms --
  a dark band overlaid across the sprite's estimated eye-line. Real sprite
  art has wildly inconsistent padding per species/pose, so the band is
  positioned relative to `Surface.get_bounding_rect()` (the actual visible,
  non-transparent pixels, cached per-Surface by `id()` in
  `Game.get_bbox`), *not* the padded square canvas -- positioning it
  relative to the canvas was tried first and looked broken (see git
  history / this conversation if you need the before/after). This is a
  deliberate approximation (no real eyelid animation is possible from a
  single static image) and is good enough in motion; don't over-invest in
  pixel-perfect eye detection here.
- **Difficulty rebalance**: `battle.CPU_LEVEL` lowered from 55 to **52**
  after simulating a realistic drafting process under the new
  one-pick-per-batch-of-10 constraint (see the sweep methodology earlier
  in this file). At 52, a player who simply reroll-picks the
  highest-BST option each round wins roughly 50-60% of the time (verified
  both via a standalone `battle.py` simulation and by driving the actual
  `Game`/UI objects end-to-end); a genuinely careless/unlucky draft still
  usually loses. If this ever needs retuning again, `CPU_LEVEL` is the
  primary lever -- the sweep showed the win rate is *very* sensitive to it
  (roughly 12%->64% between level 55 and 50 for the same drafting
  heuristic), so change it in small steps (1-2 levels) and re-simulate
  rather than guessing.
- **Hide CPU power**: the Arena Select screen's "YOUR OPPONENTS" panel no
  longer prints the Legendary Six's level -- still reveals names/sprites
  for hype, just not the exact stat/level intimidation factor. The
  in-battle HUD still shows level once you're actually fighting (that's
  normal/expected, matches every mainline game).

Playtested: headless full-stack runs (draft -> reroll lock/animation ->
arena -> battle -> result) across multiple trials with both a naive bot
and a "thoughtful" (highest-BST draft + expected-value move choice)
heuristic bot to confirm the new win rate, plus a real (non-headless,
on-screen) window run letting the reroll spin and a battle hit actually
play out in real time. Nothing known-broken.

## If you want to keep improving this

Everything asked for is in place, but possible follow-ups if the user wants
more later:
- Status effects (paralyze/burn/poison/sleep) are not implemented — battles
  are pure damage races right now. Would add real depth and more AI
  counterplay options.
- No sound/music (not requested; pygame.mixer is available if wanted).
- Arena/keyboard: the Arena Select screen's tiles are mouse-only (Enter and
  Escape work, but there's no arrow-key tile picker). Everything else
  supports both mouse and keyboard.
- `pygame-ce` vs `pygame`: if the user's Python version ever gets a real
  `pygame` wheel, either package works interchangeably — no code changes
  needed either way.

## Design decisions worth knowing if you pick this back up

- No internet/image/font assets are used anywhere (fully offline-capable) —
  sprites are procedurally generated, fonts are local Windows system fonts
  (Consolas/Courier), by deliberate choice given the sandboxed environment.
- Arena bonus is +20% power to moves of the arena's matching type, for
  *both* sides (fair, but mostly benefits the player since the CPU's fixed
  legendary roster is 4/6 Flying-type and none of the 4 arenas is
  Flying-themed).
- User explicitly approved: Pygame graphical window (not terminal), "low
  animation ok", Game Boy style sprites are fine, but full stats/HP must be
  shown clearly for every Pokemon — that's why the Team Builder has a full
  stat/move readout panel and the battle screen has a dedicated STATS menu.
