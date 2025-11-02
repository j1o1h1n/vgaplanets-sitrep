import math
import copy
import re

import sitrep.starmap
import sitrep.space
import sitrep.freighters

from sitrep.vgap import query

from collections import defaultdict
from typing import Any, Iterable, NamedTuple

# Types for clarity
Loc = dict[str, int]
Record = dict[str, Any]

FLEET_COMBAT = re.compile(
    r"""
    (?P<side1>.*?)\s+ID\#(?P<id1>\d+)\s+   # first name + its ID
    (?P<action>has.*ed)\s+                 # the verb (captured/destroyed/etc)
    (?:by\s+)?                             # optional "by"
    (?:the\s+)?                            # optional "the"
    (?P<side2>.*?)\s+ID\#(?P<id2>\d+)      # second name + its ID
    .*?                                    # skip any junk
    \(\s*(?P<x>\d+)\s*,\s*(?P<y>\d+)\s*\)  # the (x, y) coords
""",
    re.VERBOSE | re.DOTALL,
)

CAPTURE_PLANET = re.compile(
    "has captured the .* planet .* formerly under the command of"
)


class CombatResult(NamedTuple):
    result: str  # captured or destroyed
    id: int  # ship id


def combat_results(turn):
    results = []
    msgs = turn.data["messages"]
    fleet_msgs = [m for m in msgs if m["messagetype"] == 6]
    for msg in fleet_msgs:
        if msg["body"].startswith("The colonists"):
            continue
        if CAPTURE_PLANET.search(msg["body"]):
            continue

        mo = FLEET_COMBAT.search(msg["body"])
        if mo:
            data = mo.groupdict()
            if (
                data["side1"].startswith("Planet")
                and data["action"] == "has been captured"
            ):
                continue

        if not mo:
            print(f"no match: {msg['body']}")
            continue

        match data["action"]:
            case "has destroyed":
                results.append(CombatResult("destroyed", int(data["id2"])))
            case "has captured":
                results.append(CombatResult("captured", int(data["id2"])))
            case "has been destroyed":
                results.append(CombatResult("destroyed", int(data["id1"])))
            case "has been captured":
                results.append(CombatResult("captured", int(data["id1"])))
            case _:
                print(f"case fallthrough: {data['action']}")
    return results


def fuel_cost(mass, warp, dist, engineid, engines):
    if warp == 0:
        return 0
    xv = engines[engineid][f"warp{warp}"]
    max_dist = warp * warp
    return math.floor(
        xv * math.floor(mass / 10) * ((math.floor(dist) / max_dist) / 10000)
    )


def build_ships_from_vcrs(turn):
    vcrs = turn.data["vcrs"]
    ships = {}
    for vcr in vcrs:
        sides = ["left"] if vcr["battletype"] else ["left", "right"]
        for side in sides:
            ship = copy.copy(vcr[side])
            ship["id"] = ship["objectid"]
            ship["ownerid"] = vcr[f"{side}ownerid"]
            ship["warp"] = 0
            ship["engineid"] = 0
            ship["beams"] = ship["beamcount"]
            ship["torps"] = ship["launchercount"]
            ship["bays"] = ship["baycount"]
            ship["ammo"] = max(ship["fighters"], ship["torpedos"])
            ship["mass"] = sitrep.starmap.calc_mass(ship, turn, {}) + ship["ammo"]
            for key in ["x", "y", "turn"]:
                ship[key] = vcr[key]
            ships[ship["id"]] = ship
    return list(ships.values())


def _hivemap(turn) -> tuple[dict, dict, dict, dict]:
    hulls = {h["id"]: h for h in turn.data["hulls"]}
    beams = {h["id"]: h for h in turn.data["beams"]}
    engines = {h["id"]: h for h in turn.data["engines"]}
    torps = {h["id"]: h for h in turn.data["torpedos"]}
    return hulls, beams, engines, torps


def _shipdesc(ship: dict, hulls: dict) -> str:
    """Builds your 'S{id} <desc>[/ammo]' style label."""
    desc = sitrep.starmap.build_ship_desc(ship, hulls)  # existing helper
    ammo = ship.get("ammo", 0)
    if ship.get("bays", 0):
        desc = f"{desc}/f{ammo}"
    elif ship.get("torps", 0):
        desc = f"{desc}/{ammo}"
    return desc


def _deadweight(lightweight: int, hull: dict) -> int:
    return lightweight + hull["cargo"] + hull["fueltank"]


def _in_radius(p: Loc, q: Loc, r: int) -> bool:
    return sitrep.space.distance(p, q) < r


def _gather_turn_ships(turn, enemy_only=True) -> list[dict]:
    ships = query(
        turn.data["ships"],
        lambda s: (s["ownerid"] != turn.player_id) if enemy_only else True,
    )
    seen_ids = {s["id"] for s in ships}
    # Add VCR-only ships not in visible list
    vcr_ships = [
        s
        for s in build_ships_from_vcrs(turn)
        if (not enemy_only or s["ownerid"] != turn.player_id)
        and s["id"] not in seen_ids
    ]
    ships.extend(vcr_ships)
    return ships


def _update_with_glory(
    turn, ship_recs: dict[int, list[Record]], all_recs: list[Record]
) -> None:
    """If no observation of a ship for this turn, clone last known and apply Glory message intel."""
    glory_recs = [
        sitrep.messages.parse_glory(m)
        for m in turn.data["messages"]
        if sitrep.messages.is_glory(m)
    ]
    for g in glory_recs:
        ship_id = g["ship_id"]
        if ship_id not in ship_recs:
            continue
        last = ship_recs[ship_id][-1]
        if last["turn"] == turn.turn:  # already have an obs this turn
            continue
        x, y, damage = g["x"], g["y"], g["damage"]
        rec = last.copy()
        rec["turn"] = turn.turn
        rec["_loc"] = {"x": x, "y": y}
        rec["loc"] = f"{x},{y}"
        rec["note"] = f"{damage}% damaged"
        ship_recs[ship_id].append(rec)
        all_recs.append(rec)


def _fuel_used_for_move(
    prev_mass: int, warp: int, dist: int, engineid: int, engines: dict
) -> int:
    if not (dist and warp and prev_mass):
        return 0
    return fuel_cost(prev_mass, warp, dist, engineid, engines)


def _collect_detailed_records(
    game,
    target_player_id: int,
    from_turn: int,
    point: Loc,
    radius: int,
) -> tuple[list[Record], dict[int, list[Record]]]:
    """Build per-observation records across turns for target player within radius."""
    turns = game.turns()
    last_turn = turns[game.last_turn]
    hulls, _beams, engines, _torps = _hivemap(last_turn)

    # lightweight calc template (your defaults)
    ship_template = {"beamid": 7, "torpedoid": 9}

    all_recs: list[Record] = []
    ship_recs: dict[int, list[Record]] = {}
    combat_by_id: dict[int, Any]

    for turn_id in sorted(turns):
        if turn_id < from_turn:
            continue

        turn = turns[turn_id]
        combat_by_id = {r.id: r for r in combat_results(turn)}
        ships = _gather_turn_ships(turn, enemy_only=True)

        for ship in ships:
            if ship["ownerid"] != target_player_id:
                continue

            loc = {"x": ship["x"], "y": ship["y"]}
            if not _in_radius(point, loc, radius):
                continue

            shipid = ship["id"]
            hull = hulls[ship["hullid"]]
            shipdesc = _shipdesc(ship, hulls)
            bv, dv = sitrep.starmap.get_battle_value(ship, hull)
            warp = ship.get("warp", 0)
            ammo = ship.get("ammo", 0)
            mass = ship.get("mass", 0)
            lwt = sitrep.starmap.calc_mass(
                ship, turn, ship_template
            )  # lightweight tonnage
            cargo = hull["cargo"]
            fueltank = hull["fueltank"]
            deadwt = _deadweight(lwt, hull)

            # Movement delta and fuel (vs last obs for this ship)
            hist = ship_recs.setdefault(shipid, [])
            d = 0 if not hist else round(sitrep.space.distance(loc, hist[-1]["_loc"]))
            prev_mass = hist[-1]["mass"] if hist else 0
            # Min observed warp as proxy for engine id (your prior heuristic)
            vals = [s["warp"] for s in hist if s.get("warp")]
            min_warp = min(vals) if vals else 0
            engineid = max(1, min_warp)
            fuel_used = _fuel_used_for_move(prev_mass, warp, d, engineid, engines)

            # Note: combat result takes precedence, else damage note
            note = ""
            if shipid in combat_by_id:
                note = combat_by_id[shipid].result
            elif ship.get("damage", 0) > 0:
                note = f"{ship['damage']}% damaged"

            rec: Record = {
                "id": shipid,
                "turn": turn_id,
                "name": ship["name"],
                "hullid": ship["hullid"],
                "shipdesc": shipdesc,
                "ownerid": ship["ownerid"],
                "_loc": loc,
                "loc": f"{loc['x']},{loc['y']}",
                "distance": d,
                "fuel_used": fuel_used,
                "warp": warp,
                "lightweight": lwt,
                "cargo": cargo,
                "fueltank": fueltank,
                "mass": mass,
                "ammo": ammo,
                "deadweight": deadwt,
                "load": mass - lwt,
                "bv": bv,
                "note": note,
            }

            hist.append(rec)
            all_recs.append(rec)

        # Glory intel clones for ships already seen (keeps within radius if the glory loc is inside)
        _update_with_glory(turn, ship_recs, all_recs)

    return all_recs, ship_recs


def _simplify_latest_per_ship(
    all_recs: list[Record], ship_recs: dict[int, list[Record]]
) -> list[Record]:
    """Collapse to one row per ship (latest obs), carrying a few summary fields."""
    simple: list[Record] = []
    for shipid, hist in ship_recs.items():
        hist_sorted = sorted(hist, key=lambda r: r["turn"])
        latest = hist_sorted[-1].copy()

        vals = [s["warp"] for s in hist_sorted if s.get("warp")]
        min_warp = min(vals) if vals else 0
        engineid = max(1, min_warp)

        min_mass = min((s.get("mass", 0) for s in hist_sorted), default=0)
        max_mass = max((s.get("mass", 0) for s in hist_sorted), default=0)
        mass_range = (
            f"{min_mass} - {max_mass}" if min_mass != max_mass else str(min_mass)
        )

        # Fuel for the latest leg
        fuel_used = 0
        if len(hist_sorted) >= 2:
            prev = hist_sorted[-2]
            fuel_used = _fuel_used_for_move(
                prev.get("mass", 0),
                latest.get("warp", 0),
                latest.get("distance", 0),
                engineid,
                {},
            )  # engines not needed by your fuel_cost signature if cached; pass real 'engines' if required

        simple.append(
            {
                "id": shipid,
                "hull": latest["hullid"],
                "ship": f"S{shipid} {latest['shipdesc']}",
                "name": latest["name"],
                "turn": latest["turn"],
                "loc": latest["loc"],
                "engine": f"W{engineid}",
                "lightweight": latest["lightweight"],
                "mass": latest["mass"],
                "cargo": latest["cargo"],
                "mass range": mass_range,
                "fuel used": fuel_used,
                "load": latest["load"],
                "note": latest["note"],
            }
        )

    simple.sort(key=lambda s: -s["turn"])
    return simple


def gather_ships_by_loc_turn(recs: Iterable[Record]) -> dict[str, dict[int, list[str]]]:
    data: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for s in recs:
        data[s["loc"]][s["turn"]].append(s["ship"])
    return data


def build_milint_layer(data: dict[str, dict[int, list[str]]]) -> dict[str, Any]:
    markups = []
    for loc, turns in data.items():
        x, y = map(int, loc.split(","))
        # Sort turns descending for readability (latest first)
        for_turn = sorted(turns.items(), key=lambda kv: -kv[0])
        text_lines: list[str] = []
        for turn, ships in for_turn:
            if not ships:
                continue
            text_lines.append(f"T{turn} {ships[0]}")
            for s in ships[1:]:
                text_lines.append(f"  {s}")
        if not text_lines:
            continue
        text = "\n".join(text_lines)
        markups.append(sitrep.freighters.Point(x, y, text, "#ff0"))
    return {"name": "MilInt", "active": True, "markups": markups}


def build_milint_report(
    game,
    target_player_id: int,
    from_turn: int,
    point: dict[str, int],
    radius: int,
) -> dict[str, Any]:
    """
    Build a JSON-ish dict for your drawing layer:

    {
      "name": "MilInt",
      "active": true,
      "markups": [ sitrep.freighters.Point(x, y, text, "#ff0"), ... ]
    }

    - Includes enemy (non-self) ships owned by `target_player_id`
    - Considers turns >= `from_turn`
    - Filters observations to within `radius` of `point` (x,y)
    - Merges VCR-only sightings and Glory device intel
    """
    all_recs, ship_recs = _collect_detailed_records(
        game=game,
        target_player_id=target_player_id,
        from_turn=from_turn,
        point=point,
        radius=radius,
    )
    simple = _simplify_latest_per_ship(all_recs, ship_recs)

    # Remove destroyed ships
    simple = [r for r in simple if "destroyed" in r.get("note", "")]

    grouped = gather_ships_by_loc_turn(simple)
    return build_milint_layer(grouped)
