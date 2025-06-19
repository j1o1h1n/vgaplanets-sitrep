import copy
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

PLAYER_COLORS = [
  '#a6cee3',
  '#1e77b4',
  '#b2df8a',
  '#32a02b',
  '#fb9a99',
  '#e3191b',
  '#fdbf6e',
  '#ff7e00',
  '#cab2d6',
  '#693c9a',
  '#ffff99',
  '#b15827'
];

def get_battle_value(ship, hull):
    if ship['beams'] == 0 and ship['torps'] == 0 and hull['fighterbays'] == 0:
        return 0, 0
    ev = ship['engineid']
    bv = (ship['beams'] * BEAM_BV[ship['beamid'] - 1]) + \
         (ship['torps'] * TORP_BV[ship['torpedoid'] - 1]) + \
         (hull.get("fighterbays", 0) * FIGHTER_BV) + \
         (ev * 10)

    return bv, hull['mass'] + (ev * 10)


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

    # starclusters
    starclusters = game.turns()[1].data["stars"]

    # nebulas
    nebulas = game.turns()[1].data["nebulas"]

    return {"planets": planets, "starclusters": starclusters, "nebulas": nebulas,
            "planet_owners": planet_owners, "starbases": starbases, "turns": max(turninfo.keys())}


def write_starmap(game: vgap.Game, output_path: str):
    turn = game.turns()[1]
    settings = turn.data["settings"]
    mapshape = settings["mapshape"]
    mapwidth = settings["mapwidth"]
    mapheight = settings["mapheight"]
    players = [
        { "id": p.player_id, "name": p.name, "race": p.short_name, "color": PLAYER_COLORS[p.player_id % len(PLAYER_COLORS)] }
        for p in game.players.values()
    ]

    data = build_starmap(game)
    turns = data['turns']
    players_data = ",\n".join(["    " + json.dumps(val) for val in players])
    planets_data = ",\n".join(["    " + json.dumps(val) for val in data["planets"].values()])
    starclusters_data = ",\n".join(["    " + json.dumps(val) for val in data["starclusters"]])
    nebula_data = ",\n".join(["    " + json.dumps(val) for val in data["nebulas"]])
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
  "starclusters": [
{starclusters_data}
  ],
  "nebulas": [
{nebula_data}
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


def match_ship(lhs, rhs):
    return lhs['id'] == rhs['id'] and lhs['shipdesc'] == rhs['shipdesc'] and lhs['ownerid'] == rhs['ownerid']


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
        prev_alive = set()
        for turn in turns.values():
            if hulls is None:
                hulls = {h['id']:h for h in turn.data["hulls"]}
            if turn.turn_id not in turninfo:
                turninfo[turn.turn_id] = {}
            ships = turn.ships(player_id)
            alive = set()
            for ship in ships:
                shipid = ship['id']
                shipdesc = build_ship_desc(ship, hulls)
                bv, dv = get_battle_value(ship, hulls[ship['hullid']])
                if shipdesc not in shipdesc_ids:
                    shipdesc_id = len(shipdesc_ids)
                    shipdesc_ids[shipdesc] = shipdesc_id
                    shipdescs[shipdesc_id] = (shipdesc, bv, dv)
                shipdesc_id = shipdesc_ids[shipdesc]
                rec = {"id": shipid, "name": ship["name"], "shipdesc": shipdesc_id, "ownerid": player_id}
                
                prev_id_uid = shipid_to_uid.get(shipid, None)
                if prev_id_uid is None \
                   or prev_id_uid not in prev_alive \
                   or not match_ship(shipinfo[prev_id_uid], rec):
                    # new uid
                    uid = next_uid
                    next_uid += 1
                    shipid_to_uid[shipid] = uid
                    shipinfo[uid] = rec
                uid = shipid_to_uid[shipid]
                alive.add(uid)

                # update name so last name is used
                shipinfo[uid]["name"] = ship["name"]
                loc = f'{ship["x"]},{ship["y"]}'
                ammo = ship["ammo"]
                if loc not in turninfo[turn.turn_id]:
                    turninfo[turn.turn_id][loc] = []
                turninfo[turn.turn_id][loc].extend([uid, ammo])
            prev_alive = alive

    shiplist = []
    for i in range(max(turninfo.keys())):
        shiplist.append(turninfo.get(i + 1, {}))

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


# message types
BATTLE, EXPLOSION = 100, 101


def build_messages_for_turn(game, turn_id):
    turns = {player.player_id:game.turns(player.player_id).get(turn_id, None) for player in game.players.values()}

    pat = re.compile(r'Distress call and explosion detected at \( \d+, \d+ \) the name of the ship was: (.*)')

    exp_msgs = {}
    for turn in turns.values():
        if turn is None:
            continue
        msgs = (m for m in turn.data['messages'] if m['messagetype'] in {10})
        locs = {}
        for m in msgs:
            loc = m['x'], m['y']
            mo = pat.match(m['body'])
            if not mo:
                continue
            name = f"{mo.group(1)}"
            if loc not in locs:
                locs[loc] = []
            locs[loc].append(name)
        exp_msgs.update(locs)

    vcr_map = {}
    for turn in turns.values():
        if turn is None:
            continue
        for vcr in turn.data['vcrs']:
            vcr_map[vcr['id']] = vcr

    vcrs = list(vcr_map.values())
    vcrs.sort(key = lambda vcr: (vcr['x'], vcr['y'], vcr['id']))
    vcrs_by_loc = {}
    for vcr in vcrs:
        loc = vcr['x'], vcr['y']
        if loc not in vcrs_by_loc:
            vcrs_by_loc[loc] = []
        vcrs_by_loc[loc].append(vcr)

    def match_ship(ship_id, owner_id, vcr):
        " True if the ship matches the details of a combattent in the vcr "
        def sided_match(side):
            " True if the ship matches the details of a side-combattent in the vcr "
            if side == 'right' and vcr['battletype']:
                # ship can't be a planet
                return False
            # match owner and ship_id
            return (vcr[f'{side}ownerid'] == owner_id) and (vcr[side]['objectid'] == ship_id)

        return sided_match('left') or sided_match('right')

    messages = {}
    for loc in vcrs_by_loc:
        key = f"{loc[0]},{loc[1]}"
        messages[key] = []
        loc_vcrs = vcrs_by_loc[loc]
        for idx in range(len(loc_vcrs)):
            vcr = loc_vcrs[idx]
            next_vcr = loc_vcrs[idx+1] if idx + 1 < len(loc_vcrs) else None
            left_owner_id, right_owner_id = vcr['leftownerid'], vcr['rightownerid']
            left_id, right_id = vcr['left']['objectid'], vcr['right']['objectid']
            left_name, right_name = vcr['left']['name'], vcr['right']['name']
            battle_type = vcr['battletype'] # 1 => rhs is planet
            
            if next_vcr:
                left_survives = match_ship(left_id, left_owner_id, next_vcr)
            else:
                left_survives = vgap.query_one(turns[left_owner_id].ships(left_owner_id), lambda ship: ship["id"] == left_id) is not None
            if battle_type:
                right_survives = vgap.query_one(turns[right_owner_id].planets(right_owner_id), lambda planet: planet["id"] == right_id) is not None
            elif next_vcr:
                right_survives = match_ship(right_id, right_owner_id, next_vcr)
            else:
                right_survives = vgap.query_one(turns[right_owner_id].ships(right_owner_id), lambda ship: ship["id"] == right_id) is not None

            btype = 2 if vcr["right"]["hasstarbase"] else 1 if battle_type else 0
            planet_lost = btype and vgap.query_one(turns[right_owner_id].planets(right_owner_id), lambda planet: planet["id"] == right_id) is None
            battle_rec = [BATTLE, btype, left_id, right_id, left_name, right_name, left_owner_id, right_owner_id, left_survives, right_survives]
            messages[key].append(battle_rec)

        for name in exp_msgs.get(loc, []):
            exp_rec = [EXPLOSION, name]
            messages[key].append(exp_rec)

    return messages


def build_messages(game):
    maxturn = max(game.turns().keys())
    messages = []
    for turn_id in range(1, maxturn):
        messages.append(build_messages_for_turn(game, turn_id))
    return messages

def write_messagelist(game: vgap.Game, output_path: str):
    messages = build_messages(game)
    messages_data = ",\n".join(f'    {json.dumps(m)}' for m in messages)

    output = f"""{{
  "messagelist": [
{messages_data}
  ]
}}
"""

    with open(output_path, 'w') as f:
        f.write(output)
