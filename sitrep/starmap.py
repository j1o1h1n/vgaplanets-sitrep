import re
import string
import json

from . import vgap


ALPHANUM = string.digits + string.ascii_uppercase

HULL_SPECIAL_NAMES = {
    14: "NFC", 15: "SDSF", 16: "MDSF", 17: "LDSF", 18: "STF",
    27: "Swift", 28: "Fearless", 69: "SSD", 102: "Scorpius Light", 104: "Refinery",
    107: "Ore Condenser", 109: "Freighter ©", 120: "D9 USVA", 203: "Arm. Nest",
    207: "Dur R", 208: "Trit R", 209: "Molyb R", 1001: "Outrider Transport",
    1010: "Arkham Destroyer", 1021: "Reptile Escort", 1049: "Madonzilla ©",
    1025: "Saurian Frigate", 1030: "Valiant Storm", 1032: "Bright Light",
    1033: "Deth Armoured", 1038: "D3 Frigate", 1041: "Shield Gen",
    1040: "Pest Light", 1047: "Red Storm", 1048: "Skyfire Transport",
    1059: "Med Trans", 1050: "Bloodfang Stealth", 1062: "Sky Garnet F",
    1085: "Iron Tug", 1089: "Iron Command", 1090: "Sage Repair",
    1093: "Heavy Transport", 1095: "Joe Light", 1098: "Taurus Transport",
    2010: "Arkham Cruiser", 2011: "Thor Heavy", 2035: "Saurian Heavy",
    2033: "Deth Stealth", 2038: "D3 Cruiser", 2102: "Scorpius Heavy",
    3004: "Vendetta Stealth", 3033: "Deth Heavy"
}


SHORT_BEAM_NAMES = [
    None, "Las", "X", "Pl", "Bl", "Pos", "Dis", "HBl", "Ph", "HDis", "HPh"
]

SHORT_TORP_NAMES = [
    None, "Mk1", "Pr", "Mk2", "γ", "Mk3", "Mk4", "Mk5", "Mk6", "Mk7", "Mk8", "QT"
]


def short_hull_name(hull: dict[str,str|int]) -> str:
    if hull['id'] in HULL_SPECIAL_NAMES:
        return HULL_SPECIAL_NAMES[int(hull['id'])]

    hull_name = str(hull['name'])
    m = re.match(r"^(([^ ]+).*) Class ", hull_name)
    if m:
        return m[2] if re.search(r"\d", m[2]) else m[1]

    m = re.match(r"^(([^ ]+) [^ ]+)", hull_name)
    if m:
        return m[2] if re.search(r"\d", m[2]) else hull_name

    return hull_name


def ship_desc(hull: dict[str,str|int], engine_id: int, beams: int, beam_id: int, launchers: int, launcher_id: int, ammo: int) -> str:
    result = short_hull_name(hull)

    if engine_id > 0:
        result += f" E{engine_id}"

    if beams > 0 and beam_id > 0:
        result += f" {beams}{SHORT_BEAM_NAMES[beam_id]}"

    if launchers > 0 and launcher_id > 0:
        result += f" {launchers}{SHORT_TORP_NAMES[launcher_id]}"

    if ammo > 0:
        if int(hull.get("fighterbays", 0)) > 0:
            result += " f"
        result += f"/{ammo}"

    return result


def build_ship_desc(ship: dict[str,int|str], hulls: dict[int,dict[str,int|str]]) -> str:
    """
    Build a short descriptive name for the ship.

    hulls can be built from turn.data like this:
    >>> hulls = {h['id']:h for h in turn.data["hulls"]}
    """
    desc = ship_desc(hulls[int(ship['hullid'])], int(ship['engineid']), int(ship['beams']), int(ship['beamid']), int(ship['torps']), int(ship['torpedoid']), int(ship['ammo']))
    return f"S{ship['id']} {desc}"


def build_starmap(game: vgap.Game, skip_last_turn=True) -> dict:
    players = list(game.players.values())
    planets = {}
    turninfo = {}
    skip_turn = -1 if not skip_last_turn else max(game.turns().keys())
    for player in players:
        player_id = player.player_id
        turns = game.turns(player_id)
        for turn in turns.values():
            if turn.turn_id == skip_turn:
                continue
            # update with any new planets
            for p in turn.planets():
                if p["id"] in planets:
                    continue
                name = p["name"].replace("'\"", "")
                planets[p["id"]] = {"id": p["id"], "name": name, "x": p["x"], "y": p["y"]}
            # update planet and starbase ownership
            if turn.turn_id not in turninfo:
                turninfo[turn.turn_id] = {"planet_owner": {}, "starbase_owner": {}}
            for planet in turn.planets(player_id):
                turninfo[turn.turn_id]["planet_owner"][planet["id"]] = player_id
            for sb in turn.starbases(player_id):
                turninfo[turn.turn_id]["starbase_owner"][sb["planetid"]] = player_id
    
    # create planet owner encoding
    planet_ids = list(range(max(planets.keys())))
    def encode(owners: dict[int,int]) -> str:
        return "".join(ALPHANUM[owners.get(p, 0)] for p in planet_ids)

    planet_owners = [encode(turninfo[t]['planet_owner']) for t in turninfo]
    starbases = [list(turninfo[turn.turn_id]["starbase_owner"].keys()) for t in turninfo]

    return {"planets": planets, "planet_owners": planet_owners, "starbases": starbases}


def write_starmap(game: vgap.Game, output_path: str):
    turn = game.turns()[1]
    settings = turn.data["settings"]
    mapshape = settings["mapshape"]
    mapwidth = settings["mapwidth"]
    mapheight = settings["mapheight"]
    players = [
        { "id": p.player_id, "name": p.name, "race": p.short_name, "color": p.color }
        for p in game.players.values()
    ]

    data = build_starmap(game)

    starmap = {
      "title": game.name,
      "width": mapwidth,
      "height": mapheight,
      "mapshape": mapshape,
      "padding": 50,
      "players": players,
      "planets": list(data["planets"].values()),
      "planet_owners": data["planet_owners"],
      "starbases": data["starbases"],
    };

    with open(output_path, 'w') as f:
        f.write(json.dumps(starmap, indent=2))


def build_shiplist(game):
    players = list(game.players.values())
    shiplist = {}
    ship_descs = {}
    for player in players:
        player_id = player.player_id
        turns = game.turns(player_id)
        for turn in turns.values():
            if turn.turn_id not in shiplist:
                shiplist[turn.turn_id] = []
            for ship in turn.ships(player_id):
                ship_id = ship["id"]
                shiplist[turn.turn_id].append({"id": ship_id, "x": ship["x"], "y": ship["y"], "ownerid": player_id})
    return {"shiplist": shiplist}


def write_shiplist(game: vgap.Game, output_path: str):
    shiplist = build_shiplist(game)
    with open(output_path, 'w') as f:
        f.write(json.dumps(shiplist, indent=2))

