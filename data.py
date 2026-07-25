"""
Pokemon Indigo League - data module.

Holds the National Dex #1-151 (Kanto only, as befits an Indigo League game),
their base stats and types, the type effectiveness chart, and the move
tables used to build each Pokemon's battle moveset.

Base stats reproduce well-known, widely published Generation I game data.
"""

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

TYPES = [
    "Normal", "Fire", "Water", "Electric", "Grass", "Ice", "Fighting",
    "Poison", "Ground", "Flying", "Psychic", "Bug", "Rock", "Ghost", "Dragon",
]

# Classic Game Boy-era type colors (kept saturated but readable on the GBC-ish
# palette the rest of the game uses).
TYPE_COLORS = {
    "Normal":   (168, 168, 120),
    "Fire":     (240, 128, 48),
    "Water":    (104, 144, 240),
    "Electric": (248, 208, 48),
    "Grass":    (120, 200, 80),
    "Ice":      (152, 216, 216),
    "Fighting": (192, 48, 40),
    "Poison":   (160, 64, 160),
    "Ground":   (224, 192, 104),
    "Flying":   (168, 144, 240),
    "Psychic":  (248, 88, 136),
    "Bug":      (168, 184, 32),
    "Rock":     (184, 160, 56),
    "Ghost":    (112, 88, 152),
    "Dragon":   (112, 56, 248),
}

# In Generation I, a move's damage category (Physical/Special) was
# determined purely by its type -- there was no per-move split yet.
PHYSICAL_TYPES = {
    "Normal", "Fighting", "Poison", "Ground", "Flying", "Bug", "Rock", "Ghost",
}

# type -> (super effective against, resisted by target when defending 0.5x, no effect 0x)
_SUPER_EFFECTIVE = {
    "Normal":   [],
    "Fire":     ["Grass", "Ice", "Bug"],
    "Water":    ["Fire", "Ground", "Rock"],
    "Electric": ["Water", "Flying"],
    "Grass":    ["Water", "Ground", "Rock"],
    "Ice":      ["Grass", "Ground", "Flying", "Dragon"],
    "Fighting": ["Normal", "Ice", "Rock"],
    "Poison":   ["Grass"],
    "Ground":   ["Fire", "Electric", "Poison", "Rock"],
    "Flying":   ["Grass", "Fighting", "Bug"],
    "Psychic":  ["Fighting", "Poison"],
    "Bug":      ["Grass", "Psychic"],
    "Rock":     ["Fire", "Ice", "Flying", "Bug"],
    "Ghost":    ["Ghost", "Psychic"],
    "Dragon":   ["Dragon"],
}

_RESISTED_BY = {
    "Normal":   [],
    "Fire":     ["Fire", "Water", "Rock", "Dragon"],
    "Water":    ["Water", "Grass", "Dragon"],
    "Electric": ["Electric", "Grass", "Dragon"],
    "Grass":    ["Fire", "Grass", "Poison", "Flying", "Bug", "Dragon"],
    "Ice":      ["Fire", "Water", "Ice"],
    "Fighting": ["Poison", "Flying", "Psychic", "Bug"],
    "Poison":   ["Poison", "Ground", "Rock", "Ghost"],
    "Ground":   ["Grass", "Bug"],
    "Flying":   ["Electric", "Rock"],
    "Psychic":  ["Psychic"],
    "Bug":      ["Fire", "Fighting", "Poison", "Flying", "Ghost"],
    "Rock":     ["Fighting", "Ground"],
    "Ghost":    ["Normal"],
    "Dragon":   [],
}

_NO_EFFECT = {
    "Normal":   ["Ghost"],
    "Electric": ["Ground"],
    "Fighting": ["Ghost"],
    "Ground":   ["Flying"],
}


def type_effectiveness(move_type: str, defender_types) -> float:
    """Multiplier for a move of move_type hitting a Pokemon with defender_types."""
    mult = 1.0
    for dt in defender_types:
        if dt is None:
            continue
        if dt in _NO_EFFECT.get(move_type, []):
            return 0.0
        if dt in _SUPER_EFFECTIVE.get(move_type, []):
            mult *= 2.0
        elif dt in _RESISTED_BY.get(move_type, []):
            mult *= 0.5
    return mult


# ---------------------------------------------------------------------------
# Moves
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Move:
    name: str
    type: str
    power: int
    accuracy: int  # out of 100

    @property
    def category(self) -> str:
        return "Physical" if self.type in PHYSICAL_TYPES else "Special"


# A short, flavorful movepool per type. Each Pokemon draws its 4 moves from
# its own type(s) plus a Normal-type filler, so every moveset is thematic and
# a dual type always brings real coverage.
MOVES_BY_TYPE = {
    "Normal":   [Move("Tackle", "Normal", 40, 100), Move("Quick Attack", "Normal", 40, 100), Move("Hyper Beam", "Normal", 150, 90)],
    "Fire":     [Move("Ember", "Fire", 40, 100), Move("Flamethrower", "Fire", 90, 100), Move("Fire Blast", "Fire", 110, 85)],
    "Water":    [Move("Water Gun", "Water", 40, 100), Move("Surf", "Water", 90, 100), Move("Hydro Pump", "Water", 110, 80)],
    "Electric": [Move("Thunder Shock", "Electric", 40, 100), Move("Thunderbolt", "Electric", 90, 100), Move("Thunder", "Electric", 110, 70)],
    "Grass":    [Move("Vine Whip", "Grass", 45, 100), Move("Razor Leaf", "Grass", 55, 95), Move("Solar Beam", "Grass", 120, 100)],
    "Ice":      [Move("Ice Punch", "Ice", 75, 100), Move("Aurora Beam", "Ice", 65, 100), Move("Blizzard", "Ice", 110, 70)],
    "Fighting": [Move("Karate Chop", "Fighting", 50, 100), Move("Low Kick", "Fighting", 60, 90), Move("Submission", "Fighting", 80, 80)],
    "Poison":   [Move("Poison Sting", "Poison", 40, 100), Move("Acid", "Poison", 60, 100), Move("Sludge Bomb", "Poison", 90, 100)],
    "Ground":   [Move("Mud-Slap", "Ground", 20, 100), Move("Bonemerang", "Ground", 65, 90), Move("Earthquake", "Ground", 100, 100)],
    "Flying":   [Move("Wing Attack", "Flying", 60, 100), Move("Aerial Ace", "Flying", 70, 100), Move("Sky Attack", "Flying", 140, 90)],
    "Psychic":  [Move("Confusion", "Psychic", 50, 100), Move("Psybeam", "Psychic", 65, 100), Move("Psychic", "Psychic", 90, 100)],
    "Bug":      [Move("Bug Bite", "Bug", 60, 100), Move("Fury Cutter", "Bug", 55, 95), Move("Megahorn", "Bug", 120, 85)],
    "Rock":     [Move("Rock Throw", "Rock", 50, 90), Move("Rock Slide", "Rock", 75, 90), Move("Ancient Power", "Rock", 60, 100)],
    "Ghost":    [Move("Lick", "Ghost", 30, 100), Move("Night Shade", "Ghost", 65, 100), Move("Shadow Ball", "Ghost", 80, 100)],
    "Dragon":   [Move("Dragon Rage", "Dragon", 60, 100), Move("Dragon Claw", "Dragon", 80, 100), Move("Hyper Beam", "Normal", 150, 90)],
}


def build_moveset(type1: str, type2: Optional[str]):
    """Pick a thematic 4-move kit: 2 STAB moves from the primary type, 1 from
    the secondary type (if any) and 1 Normal-type filler, deduplicated and
    padded back up to 4 with more primary-type moves if needed."""
    pool1 = MOVES_BY_TYPE[type1]
    picks = [pool1[0], pool1[2]]  # cheap accurate move + the big STAB nuke
    if type2 and type2 != type1:
        picks.append(MOVES_BY_TYPE[type2][1])
    else:
        picks.append(pool1[1])
    filler = MOVES_BY_TYPE["Normal"][1] if type1 != "Normal" else MOVES_BY_TYPE["Fighting"][0]
    picks.append(filler)
    # de-duplicate by name while preserving order, then pad
    seen = set()
    moves = []
    for m in picks:
        if m.name not in seen:
            moves.append(m)
            seen.add(m.name)
    i = 0
    while len(moves) < 4:
        candidate = pool1[i % len(pool1)]
        if candidate.name not in seen:
            moves.append(candidate)
            seen.add(candidate.name)
        i += 1
    return moves[:4]


# ---------------------------------------------------------------------------
# Species
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Species:
    dex: int
    name: str
    type1: str
    type2: Optional[str]
    hp: int
    atk: int
    dfn: int
    spa: int
    spd: int
    spe: int
    legendary: bool = False

    @property
    def types(self):
        return [t for t in (self.type1, self.type2) if t]

    @property
    def type_label(self):
        return "/".join(self.types)

    @property
    def bst(self):
        return self.hp + self.atk + self.dfn + self.spa + self.spd + self.spe


# dex, name, type1, type2, HP, Atk, Def, SpA, SpD, Spe
_RAW = [
    (1, "Bulbasaur", "Grass", "Poison", 45, 49, 49, 65, 65, 45),
    (2, "Ivysaur", "Grass", "Poison", 60, 62, 63, 80, 80, 60),
    (3, "Venusaur", "Grass", "Poison", 80, 82, 83, 100, 100, 80),
    (4, "Charmander", "Fire", None, 39, 52, 43, 60, 50, 65),
    (5, "Charmeleon", "Fire", None, 58, 64, 58, 80, 65, 80),
    (6, "Charizard", "Fire", "Flying", 78, 84, 78, 109, 85, 100),
    (7, "Squirtle", "Water", None, 44, 48, 65, 50, 64, 43),
    (8, "Wartortle", "Water", None, 59, 63, 80, 65, 80, 58),
    (9, "Blastoise", "Water", None, 79, 83, 100, 85, 105, 78),
    (10, "Caterpie", "Bug", None, 45, 30, 35, 20, 20, 45),
    (11, "Metapod", "Bug", None, 50, 20, 55, 25, 25, 30),
    (12, "Butterfree", "Bug", "Flying", 60, 45, 50, 90, 80, 70),
    (13, "Weedle", "Bug", "Poison", 40, 35, 30, 20, 20, 50),
    (14, "Kakuna", "Bug", "Poison", 45, 25, 50, 25, 25, 35),
    (15, "Beedrill", "Bug", "Poison", 65, 90, 40, 45, 80, 75),
    (16, "Pidgey", "Normal", "Flying", 40, 45, 40, 35, 35, 56),
    (17, "Pidgeotto", "Normal", "Flying", 63, 60, 55, 50, 50, 71),
    (18, "Pidgeot", "Normal", "Flying", 83, 80, 75, 70, 70, 91),
    (19, "Rattata", "Normal", None, 30, 56, 35, 25, 35, 72),
    (20, "Raticate", "Normal", None, 55, 81, 60, 50, 70, 97),
    (21, "Spearow", "Normal", "Flying", 40, 60, 30, 31, 31, 70),
    (22, "Fearow", "Normal", "Flying", 65, 90, 65, 61, 61, 100),
    (23, "Ekans", "Poison", None, 35, 60, 44, 40, 54, 55),
    (24, "Arbok", "Poison", None, 60, 85, 69, 65, 79, 80),
    (25, "Pikachu", "Electric", None, 35, 55, 40, 50, 50, 90),
    (26, "Raichu", "Electric", None, 60, 90, 55, 90, 80, 100),
    (27, "Sandshrew", "Ground", None, 50, 75, 85, 20, 30, 40),
    (28, "Sandslash", "Ground", None, 75, 100, 110, 45, 55, 65),
    (29, "Nidoran-F", "Poison", None, 55, 47, 52, 40, 40, 41),
    (30, "Nidorina", "Poison", None, 70, 62, 67, 55, 55, 56),
    (31, "Nidoqueen", "Poison", "Ground", 90, 82, 87, 75, 85, 76),
    (32, "Nidoran-M", "Poison", None, 46, 57, 40, 40, 40, 50),
    (33, "Nidorino", "Poison", None, 61, 72, 57, 55, 55, 65),
    (34, "Nidoking", "Poison", "Ground", 81, 92, 77, 85, 75, 85),
    (35, "Clefairy", "Normal", None, 70, 45, 48, 60, 65, 35),
    (36, "Clefable", "Normal", None, 95, 70, 73, 85, 90, 60),
    (37, "Vulpix", "Fire", None, 38, 41, 40, 50, 65, 65),
    (38, "Ninetales", "Fire", None, 73, 76, 75, 81, 100, 100),
    (39, "Jigglypuff", "Normal", None, 115, 45, 20, 45, 25, 20),
    (40, "Wigglytuff", "Normal", None, 140, 70, 45, 75, 50, 45),
    (41, "Zubat", "Poison", "Flying", 40, 45, 35, 30, 40, 55),
    (42, "Golbat", "Poison", "Flying", 75, 80, 70, 65, 75, 90),
    (43, "Oddish", "Grass", "Poison", 45, 50, 55, 75, 65, 30),
    (44, "Gloom", "Grass", "Poison", 60, 65, 70, 85, 75, 40),
    (45, "Vileplume", "Grass", "Poison", 75, 80, 85, 110, 90, 50),
    (46, "Paras", "Bug", "Grass", 35, 70, 55, 45, 55, 25),
    (47, "Parasect", "Bug", "Grass", 60, 95, 80, 60, 80, 30),
    (48, "Venonat", "Bug", "Poison", 60, 55, 50, 40, 55, 45),
    (49, "Venomoth", "Bug", "Poison", 70, 65, 60, 90, 75, 90),
    (50, "Diglett", "Ground", None, 10, 55, 25, 35, 45, 95),
    (51, "Dugtrio", "Ground", None, 35, 80, 50, 50, 70, 120),
    (52, "Meowth", "Normal", None, 40, 45, 35, 40, 40, 90),
    (53, "Persian", "Normal", None, 65, 70, 60, 65, 65, 115),
    (54, "Psyduck", "Water", None, 50, 52, 48, 65, 50, 55),
    (55, "Golduck", "Water", None, 80, 82, 78, 95, 80, 85),
    (56, "Mankey", "Fighting", None, 40, 80, 35, 35, 45, 70),
    (57, "Primeape", "Fighting", None, 65, 105, 60, 60, 70, 95),
    (58, "Growlithe", "Fire", None, 55, 70, 45, 70, 50, 60),
    (59, "Arcanine", "Fire", None, 90, 110, 80, 100, 80, 95),
    (60, "Poliwag", "Water", None, 40, 50, 40, 40, 40, 90),
    (61, "Poliwhirl", "Water", None, 65, 65, 65, 50, 50, 90),
    (62, "Poliwrath", "Water", "Fighting", 90, 95, 95, 70, 90, 70),
    (63, "Abra", "Psychic", None, 25, 20, 15, 105, 55, 90),
    (64, "Kadabra", "Psychic", None, 40, 35, 30, 120, 70, 105),
    (65, "Alakazam", "Psychic", None, 55, 50, 45, 135, 95, 120),
    (66, "Machop", "Fighting", None, 70, 80, 50, 35, 35, 35),
    (67, "Machoke", "Fighting", None, 80, 100, 70, 50, 60, 45),
    (68, "Machamp", "Fighting", None, 90, 130, 80, 65, 85, 55),
    (69, "Bellsprout", "Grass", "Poison", 50, 75, 35, 70, 30, 40),
    (70, "Weepinbell", "Grass", "Poison", 65, 90, 50, 85, 45, 55),
    (71, "Victreebel", "Grass", "Poison", 80, 105, 65, 100, 60, 70),
    (72, "Tentacool", "Water", "Poison", 40, 40, 35, 50, 100, 70),
    (73, "Tentacruel", "Water", "Poison", 80, 70, 65, 80, 120, 100),
    (74, "Geodude", "Rock", "Ground", 40, 80, 100, 30, 30, 20),
    (75, "Graveler", "Rock", "Ground", 55, 95, 115, 45, 45, 35),
    (76, "Golem", "Rock", "Ground", 80, 110, 130, 55, 65, 45),
    (77, "Ponyta", "Fire", None, 50, 85, 55, 65, 65, 90),
    (78, "Rapidash", "Fire", None, 65, 100, 70, 80, 80, 105),
    (79, "Slowpoke", "Water", "Psychic", 90, 65, 65, 40, 40, 15),
    (80, "Slowbro", "Water", "Psychic", 95, 75, 110, 100, 80, 30),
    (81, "Magnemite", "Electric", None, 25, 35, 70, 95, 55, 45),
    (82, "Magneton", "Electric", None, 50, 60, 95, 120, 70, 70),
    (83, "Farfetchd", "Normal", "Flying", 52, 65, 55, 58, 62, 60),
    (84, "Doduo", "Normal", "Flying", 35, 85, 45, 35, 35, 75),
    (85, "Dodrio", "Normal", "Flying", 60, 110, 70, 60, 60, 110),
    (86, "Seel", "Water", None, 65, 45, 55, 45, 70, 45),
    (87, "Dewgong", "Water", "Ice", 90, 70, 80, 70, 95, 70),
    (88, "Grimer", "Poison", None, 80, 80, 50, 40, 50, 25),
    (89, "Muk", "Poison", None, 105, 105, 75, 65, 100, 50),
    (90, "Shellder", "Water", None, 30, 65, 100, 45, 25, 40),
    (91, "Cloyster", "Water", "Ice", 50, 95, 180, 85, 45, 70),
    (92, "Gastly", "Ghost", "Poison", 30, 35, 30, 100, 35, 80),
    (93, "Haunter", "Ghost", "Poison", 45, 50, 45, 115, 55, 95),
    (94, "Gengar", "Ghost", "Poison", 60, 65, 60, 130, 75, 110),
    (95, "Onix", "Rock", "Ground", 35, 45, 160, 30, 45, 70),
    (96, "Drowzee", "Psychic", None, 60, 48, 45, 43, 90, 42),
    (97, "Hypno", "Psychic", None, 85, 73, 70, 73, 115, 67),
    (98, "Krabby", "Water", None, 30, 105, 90, 25, 25, 50),
    (99, "Kingler", "Water", None, 55, 130, 115, 50, 50, 75),
    (100, "Voltorb", "Electric", None, 40, 30, 50, 55, 55, 100),
    (101, "Electrode", "Electric", None, 60, 50, 70, 80, 80, 150),
    (102, "Exeggcute", "Grass", "Psychic", 60, 40, 80, 60, 45, 40),
    (103, "Exeggutor", "Grass", "Psychic", 95, 95, 85, 125, 65, 55),
    (104, "Cubone", "Ground", None, 50, 50, 95, 40, 50, 35),
    (105, "Marowak", "Ground", None, 60, 80, 110, 50, 80, 45),
    (106, "Hitmonlee", "Fighting", None, 50, 120, 53, 35, 110, 87),
    (107, "Hitmonchan", "Fighting", None, 50, 105, 79, 35, 110, 76),
    (108, "Lickitung", "Normal", None, 90, 55, 75, 60, 75, 30),
    (109, "Koffing", "Poison", None, 40, 65, 95, 60, 45, 35),
    (110, "Weezing", "Poison", None, 65, 90, 120, 85, 70, 60),
    (111, "Rhyhorn", "Ground", "Rock", 80, 85, 95, 30, 30, 25),
    (112, "Rhydon", "Ground", "Rock", 105, 130, 120, 45, 45, 40),
    (113, "Chansey", "Normal", None, 250, 5, 5, 35, 105, 50),
    (114, "Tangela", "Grass", None, 65, 55, 115, 100, 40, 60),
    (115, "Kangaskhan", "Normal", None, 105, 95, 80, 40, 80, 90),
    (116, "Horsea", "Water", None, 30, 40, 70, 70, 25, 60),
    (117, "Seadra", "Water", None, 55, 65, 95, 95, 45, 85),
    (118, "Goldeen", "Water", None, 45, 67, 60, 35, 50, 63),
    (119, "Seaking", "Water", None, 80, 92, 65, 65, 80, 68),
    (120, "Staryu", "Water", None, 30, 45, 55, 70, 55, 85),
    (121, "Starmie", "Water", "Psychic", 60, 75, 85, 100, 85, 115),
    (122, "Mr-Mime", "Psychic", None, 40, 45, 65, 100, 120, 90),
    (123, "Scyther", "Bug", "Flying", 70, 110, 80, 55, 80, 105),
    (124, "Jynx", "Ice", "Psychic", 65, 50, 35, 115, 95, 95),
    (125, "Electabuzz", "Electric", None, 65, 83, 57, 95, 85, 105),
    (126, "Magmar", "Fire", None, 65, 95, 57, 100, 85, 93),
    (127, "Pinsir", "Bug", None, 65, 125, 100, 55, 70, 85),
    (128, "Tauros", "Normal", None, 75, 100, 95, 40, 70, 110),
    (129, "Magikarp", "Water", None, 20, 10, 55, 15, 20, 80),
    (130, "Gyarados", "Water", "Flying", 95, 125, 79, 60, 100, 81),
    (131, "Lapras", "Water", "Ice", 130, 85, 80, 85, 95, 60),
    (132, "Ditto", "Normal", None, 48, 48, 48, 48, 48, 48),
    (133, "Eevee", "Normal", None, 55, 55, 50, 45, 65, 55),
    (134, "Vaporeon", "Water", None, 130, 65, 60, 110, 95, 65),
    (135, "Jolteon", "Electric", None, 65, 65, 60, 110, 95, 130),
    (136, "Flareon", "Fire", None, 65, 130, 60, 95, 110, 65),
    (137, "Porygon", "Normal", None, 65, 60, 70, 85, 75, 40),
    (138, "Omanyte", "Rock", "Water", 35, 40, 100, 90, 55, 35),
    (139, "Omastar", "Rock", "Water", 70, 60, 125, 115, 70, 55),
    (140, "Kabuto", "Rock", "Water", 30, 80, 90, 55, 45, 55),
    (141, "Kabutops", "Rock", "Water", 60, 115, 105, 65, 70, 80),
    (142, "Aerodactyl", "Rock", "Flying", 80, 105, 65, 60, 75, 130),
    (143, "Snorlax", "Normal", None, 160, 110, 65, 65, 110, 30),
    (144, "Articuno", "Ice", "Flying", 90, 85, 100, 95, 125, 85),
    (145, "Zapdos", "Electric", "Flying", 90, 90, 85, 125, 90, 100),
    (146, "Moltres", "Fire", "Flying", 90, 100, 90, 125, 85, 90),
    (147, "Dratini", "Dragon", None, 41, 64, 45, 50, 50, 50),
    (148, "Dragonair", "Dragon", None, 61, 84, 65, 70, 70, 70),
    (149, "Dragonite", "Dragon", "Flying", 91, 134, 95, 100, 100, 80),
    (150, "Mewtwo", "Psychic", None, 106, 110, 90, 154, 90, 130),
    (151, "Mew", "Psychic", None, 100, 100, 100, 100, 100, 100),
]

# The player's Indigo League challenge bars the true Gen I legendary birds
# and Mewtwo/Mew, as requested. To field a full team of *six* fearsome
# "legendary tier" opponents for the Elite computer trainer, Dragonite (the
# strongest non-legendary in Kanto, and a rare pseudo-legendary in every
# later game) fills the sixth slot alongside the five true legendaries.
LEGENDARY_TIER = {144, 145, 146, 149, 150, 151}

POKEDEX = {row[0]: Species(*row, legendary=(row[0] in LEGENDARY_TIER)) for row in _RAW}

ALL_SPECIES = list(POKEDEX.values())
PLAYABLE_SPECIES = [s for s in ALL_SPECIES if not s.legendary]
LEGENDARY_SPECIES = [s for s in ALL_SPECIES if s.legendary]

assert len(POKEDEX) == 151
