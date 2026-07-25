"""
Turn-based 6v6 battle engine.

Keeps Generation I's flavor (type determines physical/special split, no
stat-stage tactics) but with a simplified, transparent damage formula so the
math is easy to reason about and to tune. The Elite computer trainer fields
all six legendary-tier Pokemon at a higher level and plays with real
matchup-aware tactics, so it is a genuine challenge.
"""

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from data import Species, Move, type_effectiveness, build_moveset, LEGENDARY_SPECIES

PLAYER_LEVEL = 60
CPU_LEVEL = 52          # lower level, but legendary base stats still hit far harder & tankier
                        # (tuned via simulation so a thoughtfully-drafted team wins roughly
                        # half the time, while a careless draft still loses most of the time --
                        # see progress.md for the sweep. Was 55, lowered after "too difficult"
                        # feedback once the compulsory-reroll drafting rule made hand-picking
                        # a hard-countering team much harder to engineer on purpose.)
CRIT_CHANCE = 1 / 16
CRIT_MULT = 1.5


def calc_hp(base: int, level: int) -> int:
    return base * level // 50 + level + 10


def calc_stat(base: int, level: int) -> int:
    return base * level // 50 + 5


@dataclass
class BattleMon:
    species: Species
    level: int
    max_hp: int
    atk: int
    dfn: int
    spa: int
    spd: int
    spe: int
    moves: List[Move]
    current_hp: int = 0

    def __post_init__(self):
        if self.current_hp == 0:
            self.current_hp = self.max_hp

    @property
    def fainted(self) -> bool:
        return self.current_hp <= 0

    @property
    def hp_fraction(self) -> float:
        return 0 if self.max_hp <= 0 else max(0.0, self.current_hp / self.max_hp)

    @property
    def name(self) -> str:
        return self.species.name


def make_battle_mon(species: Species, level: int) -> BattleMon:
    return BattleMon(
        species=species,
        level=level,
        max_hp=calc_hp(species.hp, level),
        atk=calc_stat(species.atk, level),
        dfn=calc_stat(species.dfn, level),
        spa=calc_stat(species.spa, level),
        spd=calc_stat(species.spd, level),
        spe=calc_stat(species.spe, level),
        moves=build_moveset(species.type1, species.type2),
    )


def build_player_team(species_list) -> List[BattleMon]:
    return [make_battle_mon(sp, PLAYER_LEVEL) for sp in species_list]


def build_cpu_team(rng: Optional[random.Random] = None) -> List[BattleMon]:
    rng = rng or random.Random()
    order = list(LEGENDARY_SPECIES)
    rng.shuffle(order)
    return [make_battle_mon(sp, CPU_LEVEL) for sp in order]


# ---------------------------------------------------------------------------
# Damage
# ---------------------------------------------------------------------------

@dataclass
class DamageResult:
    damage: int
    effectiveness: float
    crit: bool
    missed: bool


@dataclass
class TurnEvent:
    """One animatable beat of a turn, for the UI to play back in sequence."""
    lines: List[str] = field(default_factory=list)        # revealed when the beat starts
    end_lines: List[str] = field(default_factory=list)    # revealed once its animation finishes
    mon: Optional[BattleMon] = None                       # whose HP bar animates (None = no bar)
    hp_from: int = 0
    hp_to: int = 0
    attacker_side: Optional[str] = None                    # "player"/"cpu" -- who lunges
    defender_side: Optional[str] = None                    # "player"/"cpu" -- who flinches
    has_damage: bool = False                               # long, suspenseful drain vs a quick beat
    switch_side: Optional[str] = None                      # "player"/"cpu" if this beat is a switch-in
    switch_to_mon: Optional[BattleMon] = None               # the mon that's now active, for display sync
    is_faint_pause: bool = False                            # a beat of silence to let a KO collapse play


def _atk_def_stats(attacker: BattleMon, defender: BattleMon, move: Move) -> Tuple[int, int]:
    if move.category == "Special":
        return attacker.spa, defender.spd
    return attacker.atk, defender.dfn


def calc_damage(attacker: BattleMon, defender: BattleMon, move: Move,
                 arena_type: Optional[str], rng: random.Random) -> DamageResult:
    if move.power <= 0:
        return DamageResult(0, 1.0, False, False)

    if rng.uniform(0, 100) > move.accuracy:
        return DamageResult(0, 1.0, False, True)

    eff = type_effectiveness(move.type, defender.species.types)
    if eff == 0:
        return DamageResult(0, 0.0, False, False)

    atk_stat, def_stat = _atk_def_stats(attacker, defender, move)
    base = ((2 * attacker.level / 5 + 2) * move.power * (atk_stat / max(1, def_stat)) / 50) + 2

    stab = 1.5 if move.type in attacker.species.types else 1.0
    arena_bonus = 1.2 if arena_type and move.type == arena_type else 1.0
    crit = rng.random() < CRIT_CHANCE
    crit_mult = CRIT_MULT if crit else 1.0
    variance = rng.uniform(0.85, 1.0)

    dmg = base * stab * eff * arena_bonus * crit_mult * variance
    return DamageResult(max(1, int(dmg)), eff, crit, False)


def expected_score(attacker: BattleMon, defender: BattleMon, move: Move, arena_type: Optional[str]) -> float:
    """Rough planning heuristic (no RNG) used by the AI to rank moves/switches."""
    if move.power <= 0:
        return 0.0
    eff = type_effectiveness(move.type, defender.species.types)
    if eff == 0:
        return 0.0
    atk_stat, def_stat = _atk_def_stats(attacker, defender, move)
    base = ((2 * attacker.level / 5 + 2) * move.power * (atk_stat / max(1, def_stat)) / 50) + 2
    stab = 1.5 if move.type in attacker.species.types else 1.0
    arena_bonus = 1.2 if arena_type and move.type == arena_type else 1.0
    return base * stab * eff * arena_bonus * (move.accuracy / 100)


# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

def ai_choose_action(cpu_team: List[BattleMon], cpu_active_idx: int,
                      player_active: BattleMon, arena_type: Optional[str],
                      rng: random.Random) -> Tuple[str, int]:
    active = cpu_team[cpu_active_idx]
    move_scores = [(i, expected_score(active, player_active, m, arena_type), m)
                   for i, m in enumerate(active.moves)]
    move_scores.sort(key=lambda t: t[1], reverse=True)
    best_idx, best_score, best_move = move_scores[0]
    best_eff = type_effectiveness(best_move.type, player_active.species.types)

    # Consider switching if our best move is resisted/useless and a benched
    # legend hits much harder into the current opponent.
    if best_eff < 1.0:
        candidates = []
        for i, mon in enumerate(cpu_team):
            if i == cpu_active_idx or mon.fainted:
                continue
            for m in mon.moves:
                eff = type_effectiveness(m.type, player_active.species.types)
                if eff >= 2.0:
                    candidates.append((i, expected_score(mon, player_active, m, arena_type)))
        if candidates:
            candidates.sort(key=lambda t: t[1], reverse=True)
            switch_idx = candidates[0][0]
            if rng.random() < 0.8:
                return ("switch", switch_idx)

    # Occasionally mix in the 2nd-best move so the AI isn't fully predictable,
    # but only when it's not much worse -- this is a tough trainer, not a
    # random one.
    if len(move_scores) > 1 and move_scores[1][1] >= best_score * 0.85 and rng.random() < 0.25:
        return ("move", move_scores[1][0])
    return ("move", best_idx)


def ai_forced_switch(cpu_team: List[BattleMon], player_active: BattleMon, arena_type: Optional[str]) -> int:
    """Pick the best replacement after a faint: best worst-case matchup."""
    best_i, best_score = None, -1
    for i, mon in enumerate(cpu_team):
        if mon.fainted:
            continue
        score = max((expected_score(mon, player_active, m, arena_type) for m in mon.moves), default=0)
        if score > best_score:
            best_i, best_score = i, score
    return best_i


# ---------------------------------------------------------------------------
# Battle orchestration
# ---------------------------------------------------------------------------

class Battle:
    def __init__(self, player_team: List[BattleMon], cpu_team: List[BattleMon],
                 arena_type: Optional[str], rng: Optional[random.Random] = None):
        self.player_team = player_team
        self.cpu_team = cpu_team
        self.arena_type = arena_type
        self.rng = rng or random.Random()
        self.player_active_idx = 0
        self.cpu_active_idx = 0
        self.log: List[str] = []
        self.turn_events: List[TurnEvent] = []   # this turn's animation beats, in order
        self.turn_count = 0
        self.winner: Optional[str] = None       # "player" / "cpu" / None
        self.awaiting_player_switch = False      # forced switch after faint

    @property
    def player_active(self) -> BattleMon:
        return self.player_team[self.player_active_idx]

    @property
    def cpu_active(self) -> BattleMon:
        return self.cpu_team[self.cpu_active_idx]

    def alive_indices(self, team: List[BattleMon]) -> List[int]:
        return [i for i, m in enumerate(team) if not m.fainted]

    def _check_winner(self):
        if not self.alive_indices(self.cpu_team):
            self.winner = "player"
        elif not self.alive_indices(self.player_team):
            self.winner = "cpu"

    def switch_player(self, idx: int):
        if idx == self.player_active_idx or self.player_team[idx].fainted:
            return
        self.player_active_idx = idx
        self.awaiting_player_switch = False
        self.log.append(f"Go, {self.player_team[idx].name}!")

    def _apply_move(self, attacker: BattleMon, defender: BattleMon, move: Move,
                     atk_label: str, attacker_side: str, defender_side: str):
        lines = [f"{atk_label} used {move.name}!"]
        result = calc_damage(attacker, defender, move, self.arena_type, self.rng)

        if result.missed:
            lines.append("But it missed!")
            self.log.extend(lines)
            self.turn_events.append(TurnEvent(lines=lines, attacker_side=attacker_side))
            return
        if result.effectiveness == 0:
            lines.append("It had no effect...")
            self.log.extend(lines)
            self.turn_events.append(TurnEvent(lines=lines, attacker_side=attacker_side))
            return

        hp_from = defender.current_hp
        defender.current_hp = max(0, defender.current_hp - result.damage)
        hp_to = defender.current_hp

        if result.crit:
            lines.append("A critical hit!")
        if result.effectiveness > 1.0:
            lines.append("It's super effective!")
        elif result.effectiveness < 1.0:
            lines.append("It's not very effective...")

        end_lines = []
        if defender.fainted:
            end_lines.append(f"{defender.name} fainted!")

        self.log.extend(lines)
        self.log.extend(end_lines)
        self.turn_events.append(TurnEvent(
            lines=lines, end_lines=end_lines, mon=defender, hp_from=hp_from, hp_to=hp_to,
            attacker_side=attacker_side, defender_side=defender_side, has_damage=True,
        ))
        if defender.fainted:
            # a beat of silence so the KO collapse animation is actually seen
            # before the next beat (switch-in, etc.) takes over the display
            self.turn_events.append(TurnEvent(is_faint_pause=True))

    def take_turn(self, player_action: Tuple[str, int]):
        """player_action: ('move', move_idx) or ('switch', team_idx)"""
        if self.winner or self.awaiting_player_switch:
            return
        self.turn_count += 1
        self.turn_events = []

        cpu_action = ai_choose_action(self.cpu_team, self.cpu_active_idx,
                                       self.player_active, self.arena_type, self.rng)

        # Switches resolve first (classic Pokemon behaviour).
        if player_action[0] == "switch":
            self.switch_player(player_action[1])
            self.turn_events.append(TurnEvent(lines=[f"Go, {self.player_active.name}!"],
                                               switch_side="player", switch_to_mon=self.player_active))
            player_action = ("did_switch", -1)
        if cpu_action[0] == "switch":
            self.cpu_active_idx = cpu_action[1]
            line = f"The opposing trainer sends out {self.cpu_active.name}!"
            self.log.append(line)
            self.turn_events.append(TurnEvent(lines=[line], switch_side="cpu", switch_to_mon=self.cpu_active))
            cpu_action = ("did_switch", -1)

        actors = []
        if player_action[0] == "move":
            actors.append(("player", self.player_active, self.player_active.moves[player_action[1]]))
        if cpu_action[0] == "move":
            actors.append(("cpu", self.cpu_active, self.cpu_active.moves[cpu_action[1]]))

        actors.sort(key=lambda a: a[1].spe, reverse=True)
        if len(actors) == 2 and actors[0][1].spe == actors[1][1].spe:
            if self.rng.random() < 0.5:
                actors.reverse()

        for side, mon, move in actors:
            if mon.fainted:
                continue
            if side == "player":
                defender = self.cpu_active
                if defender.fainted:
                    continue
                self._apply_move(mon, defender, move, mon.name, "player", "cpu")
            else:
                defender = self.player_active
                if defender.fainted:
                    continue
                self._apply_move(mon, defender, move, f"Foe {mon.name}", "cpu", "player")
            self._check_winner()
            if self.winner:
                break

        if not self.winner:
            if self.cpu_active.fainted:
                nxt = ai_forced_switch(self.cpu_team, self.player_active, self.arena_type)
                if nxt is not None:
                    self.cpu_active_idx = nxt
                    line = f"The opposing trainer sends out {self.cpu_active.name}!"
                    self.log.append(line)
                    self.turn_events.append(TurnEvent(lines=[line], switch_side="cpu", switch_to_mon=self.cpu_active))
            if self.player_active.fainted:
                if self.alive_indices(self.player_team):
                    self.awaiting_player_switch = True
                else:
                    self.winner = "cpu"
