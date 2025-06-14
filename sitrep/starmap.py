import re
import string
import json

from typing import Any

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


BEAM_BV = [3, 1, 10, 25, 
           29, 20, 40, 35, 
           35, 45]

TORP_BV = [30, 36, 40, 4, 
           50, 60, 70, 80, 
           96, 110, 130]

FIGHTER_BV = 100


def get_battle_value(ship, hull):
    if ship['beams'] == 0 and ship['torps'] == 0 and hull['fighterbays'] == 0:
        return 0, 0
    bv = (ship['beams'] * BEAM_BV[ship['beamid'] - 1]) + \
         (ship['torps'] * TORP_BV[ship['torpedoid'] - 1]) + \
         (hull.get("fighterbays", 0) * FIGHTER_BV)
    return bv, hull['mass']


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

    if int(hull.get("fighterbays", 0)) > 0:
        result += " f"

    return result


def build_ship_desc(ship: dict[str,int|str], hulls: dict[int,dict[str,int|str]]) -> str:
    """
    Build a short descriptive name for the ship.

    hulls can be built from turn.data like this:
    >>> hulls = {h['id']:h for h in turn.data["hulls"]}
    """
    desc = ship_desc(hulls[int(ship['hullid'])], int(ship['engineid']), int(ship['beams']), int(ship['beamid']), int(ship['torps']), int(ship['torpedoid']), int(ship['ammo']))
    return desc

# dict of turn_id : { planet_owners, starbases }
type TURNINFO = dict[int,dict[str,dict[int,int]]]

def build_starmap(game: vgap.Game) -> dict:
    players = list(game.players.values())
    planets = {}
    turninfo: TURN_INFO = {}

    # build known planets list
    for player in players:
        turns = game.turns(player.player_id)
        for turn_id in turns:
            turn = turns[turn_id]
            for p in turn.planets():
                if p["id"] in planets:
                    continue
                name = p["name"].replace("'\"", "")
                planets[p["id"]] = {"id": p["id"], "name": name, "x": p["x"], "y": p["y"]}

    maxturn = max(game.turns().keys())
    missing = set()
    for player in players:
        player_id = player.player_id
        turns = game.turns(player_id)
        for turn_id in range(1, maxturn):
            if turn_id not in turninfo:
                turninfo[turn_id] = {"planet_owner": {}, "starbases": set()}
            if not turn_id in turns:
                missing.add(turn_id)
                continue

            turn = turns[turn_id]
            # update planet and starbase ownership
            for planet in turn.planets(player_id):
                turninfo[turn.turn_id]["planet_owner"][planet["id"]] = player_id
            for sb in turn.starbases(player_id):
                turninfo[turn.turn_id]["starbases"].add(sb["planetid"])
    
    for turn_id in missing:
        turninfo[turn_id] = turninfo[turn_id - 1]

    # create planet owner encoding
    planet_ids = list(range(max(planets.keys()) + 1))
    def encode(owners: dict[int,int]) -> str:
        return "".join(ALPHANUM[owners.get(p, 0)] for p in planet_ids)

    planet_owners = [encode(turninfo[t]['planet_owner']) for t in turninfo]
    starbases = [list(turninfo[t]["starbases"]) for t in turninfo]

    return {"planets": planets, "planet_owners": planet_owners, "starbases": starbases, "turns": max(turninfo.keys())}


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
    turns = data['turns']
    players_data = ",\n".join(["    " + json.dumps(val) for val in players])
    planets_data = ",\n".join(["    " + json.dumps(val) for val in data["planets"].values()])
    planet_owners_data = ",\n".join(["    " + json.dumps(val) for val in data["planet_owners"]])
    starbases_data = ",\n".join(["    " + json.dumps(val) for val in data["starbases"]])

    output = f"""{{
  "title": {json.dumps(game.name)},
  "width": {mapwidth},
  "height": {mapheight},
  "mapshape": {mapshape},
  "padding": 20,
  "turns": {turns},
  "players": [
{players_data}
  ],
  "planets": [
{planets_data}
  ],
  "planet_owners": [
{planet_owners_data}
  ],
  "starbases": [
{starbases_data}
  ]
}}
"""

    with open(output_path, 'w') as f:
        f.write(output)


def build_shiplist(game: vgap.Game) -> dict[str,Any]:
    players = list(game.players.values())

    # list of ship manifests by turn, where each manifest entry is a uid,x,y triplet
    shiplist: list[list[int]] = []

    next_uid = 10000

    # map of shipid to uid
    shipid_to_uid: dict[int,int] = {}

    # map of uid to ship info dict {id, shipdesc_id, ownerid} 
    # TODO: and icon
    shipinfo: dict[int,dict[str,int]] = {}

    # map of shipdesc_id to description string
    shipdescs: dict[int,str] = {}

    # map of shipdesc to shipdesc_id
    shipdesc_ids: dict[str,int] = {}

    hulls: dict[int,dict[str,int|str]]|None = None
    turninfo: dict[int,list[int]] = {}
    for player in players:
        player_id = player.player_id
        turns = game.turns(player_id)
        for turn in turns.values():
            if hulls is None:
                hulls = {h['id']:h for h in turn.data["hulls"]}
            if turn.turn_id not in turninfo:
                turninfo[turn.turn_id] = []
            ships = [(ship["id"], build_ship_desc(ship, hulls), ship) for ship in turn.ships(player_id)]
            for shipid, shipdesc, ship in ships:
                bv, dv = get_battle_value(ship, hulls[ship['hullid']])
                if shipdesc not in shipdesc_ids:
                    shipdesc_id = len(shipdesc_ids)
                    shipdesc_ids[shipdesc] = shipdesc_id
                    shipdescs[shipdesc_id] = (shipdesc, bv, dv)
                shipdesc_id = shipdesc_ids[shipdesc]
                rec = {"id": shipid, "name": ship["name"], "shipdesc": shipdesc_id, "ownerid": player_id}
                
                if shipid not in shipid_to_uid or shipinfo[shipid_to_uid[shipid]] != rec:
                    # new uid
                    uid = next_uid
                    next_uid += 1
                    shipid_to_uid[shipid] = uid
                    shipinfo[uid] = rec
            
                uid = shipid_to_uid[shipid]
                x, y = ship["x"], ship["y"]
                ammo = ship["ammo"]
                turninfo[turn.turn_id].extend([uid, x, y, ammo])

    shiplist = []
    for i in range(max(turninfo.keys())):
        shiplist.append(turninfo.get(i + 1, []))

    return {"shipinfo": shipinfo, "shipdescs": shipdescs, "shiplist": shiplist}


def write_shiplist(game: vgap.Game, output_path: str):
    shiplist = build_shiplist(game)

    shipinfo = shiplist['shipinfo']
    shipdescs = shiplist['shipdescs']
    shiplist = shiplist['shiplist']

    shipinfo_data = ",\n".join(f'    "{k}": {json.dumps(v)}' for k,v in shipinfo.items())
    shipdescs_data = ",\n".join(f'    "{k}": {json.dumps(v)}' for k,v in shipdescs.items())
    shiplist_data = ",\n".join(f'    {json.dumps(v)}' for v in shiplist)

    output = f"""
{{
  "shipdescs": {{
{shipdescs_data}    
  }},
  "shipinfo": {{
{shipinfo_data}    
  }},
  "shiplist": [
{shiplist_data}    
  ]
}}
""" 

    with open(output_path, 'w') as f:
        f.write(output)

