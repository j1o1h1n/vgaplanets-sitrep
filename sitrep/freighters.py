"""
A report that shows all the freighters sightings for a player.

The report can be copied as a JS drawing for pasting into the VGA Planets UI.
"""

import re
import copy
import json

from .vgap import query_one, query, Game, Turn

INSTALL_DRAWING_JS = """
install_drawing = function(layer) {
    const overlays = vgap.map.drawingtool.overlays;

    // Check for valid structure
    if (!layer || !layer.name || !Array.isArray(layer.markups)) {
        console.warn("Invalid overlay layer format");
        return;
    }

    // Replace or add the layer
    const existingIndex = overlays.findIndex(l => l.name === layer.name);
    if (existingIndex !== -1) {
        overlays[existingIndex] = layer;
    } else {
        overlays.push(layer);
    }

    // Activate and redraw
    vgap.map.drawingtool.current = {
        overlay: layer,
        markup: null,
        editindex: null,
        addType: "point"
    };
    vgap.map.draw();

    // save as note
    const note = vgap.getNote(0, -133919);
    // FIXME fails on no notes
    let body = [];
    if (note['body']) {
        body = JSON.parse(note['body']);
        layerIndex = body.findIndex(entry => entry.name === layer.name);
        if (layerIndex !== -1) {
            body[layerIndex] = layer;
        } else {
            body.push(layer);
        }
    } else {
        body.push(layer);
    }
    note['body'] = JSON.stringify(body);
    note["changed"] = 1;
};
"""


FREIGHTER_NAMES = [
    "Small Deep Space Freighter",
    "Medium Deep Space Freighter",
    "Large Deep Space Freighter",
    "Super Transport Freighter",
    "Neutronic Fuel Carrier",
    "Small Transport",
    "Medium Transport",
    "Dwarfstar Class Transport",
    "Dwarfstar II Class Transport",
    "Outrider Class Transport",
    "Aries Class Transport",
    "Gemini Class Transport",
    "Sagittarius Class Transport",
    "Skyfire Class Transport",
    "Taurus Class Transport",
    "Dungeon Class Stargate",
]

SHIP = dict[str, int | str]
REC = dict[str, int | str]
RGB = str

POINT = {
    "type": "point",
    "x": None,
    "y": None,
    "text": None,
    "snapto": True,
    "attr": {"stroke": None},
    "color": None,
    "zmin": 0,
    "zmax": 0,
}

CIRCLE = {
    "type": "circle",
    "x": None,
    "y": None,
    "r": None,
    "attr": {"stroke": None},
    "color": None,
    "zmin": 0,
    "zmax": 0,
}

LINE = {
    "type": "line",
    "points": [{"x": None, "y": None}, {"x": None, "y": None}],
    "attr": {"stroke": None},
    "color": None,
    "zmin": 0,
    "zmax": 0,
}

COLS = [
    "id",
    "name",
    "infoturn",
    "player",
    "player_race",
    "x",
    "y",
    "targetx",
    "targety",
    "warp",
    "mass",
    "hullid",
    "hull.name",
]

COL_NAME = {
    "id": "Id",
    "name": "Name",
    "infoturn": "Turn",
    "player": "Player",
    "player_race": "Race",
    "x": "X",
    "y": "Y",
    "targetx": "Target X",
    "targety": "Target Y",
    "warp": "Warp",
    "mass": "Mass",
    "hullid": "Hull Id",
    "hull.name": "Hull",
}

# Map of hull IDs to their short names
_SHORT_HULL_NAMES = {
    14: "NFC",
    15: "SDSF",
    16: "MDSF",
    17: "LDSF",
    18: "STF",
    27: "Swift",
    28: "Fearless",
    69: "SSD",
    102: "Scorpius Light",
    104: "Refinery",
    107: "Ore Condenser",
    109: "Freighter ©",
    120: "D9 USVA",
    203: "Arm. Nest",
    207: "Dur R",
    208: "Trit R",
    209: "Molyb R",
    1001: "Outrider Transport",
    1010: "Arkham Destroyer",
    1021: "Reptile Escort",
    1049: "Madonzilla ©",  # note duplicate 1049; last one wins
    1025: "Saurian Frigate",
    1030: "Valiant Storm",
    1032: "Bright Light",
    1033: "Deth Armoured",
    1038: "D3 Frigate",
    1041: "Shield Gen",
    1040: "Pest Light",
    1047: "Red Storm",
    1048: "Skyfire Transport",
    1059: "Med Trans",
    1050: "Bloodfang Stealth",
    1062: "Sky Garnet F",
    1085: "Iron Tug",
    1089: "Iron Command",
    1090: "Sage Repair",
    1093: "Heavy Transport",
    1095: "Joe Light",
    1098: "Taurus Transport",
    2010: "Arkham Cruiser",
    2011: "Thor Heavy",
    2035: "Saurian Heavy",
    2033: "Deth Stealth",
    2038: "D3 Cruiser",
    2102: "Scorpius Heavy",
    3004: "Vendetta Stealth",
    3033: "Deth Heavy",
}


def short_hull_name(hull: REC) -> str:
    """
    Return the shorthand name for the hull
    """
    # get id and name (works for objects or dicts)
    hid = int(hull["id"])
    hname = str(hull["name"])

    # direct lookup
    if hid in _SHORT_HULL_NAMES:
        return _SHORT_HULL_NAMES[hid]

    # fallback: parse the full hull name
    m = re.match(r"^(([^ ]+).*) Class ", hname)
    if m:
        base, token = m.group(1), m.group(2)
        return token if re.search(r"\d", token) else base

    m = re.match(r"^(([^ ]+) [^ ]+)", hname)
    if m:
        token = m.group(2)
        return token if re.search(r"\d", token) else hname

    # otherwise, return as-is
    return hname


def Point(x, y, text, color):
    data = copy.deepcopy(POINT)
    data["x"] = x
    data["y"] = y
    data["attr"]["stroke"] = color
    data["color"] = color
    data["text"] = text
    return data


def Circle(x, y, r, color):
    data = copy.deepcopy(CIRCLE)
    data["x"] = x
    data["y"] = y
    data["attr"]["stroke"] = color
    data["color"] = color
    data["r"] = r
    return data


def Line(x0, y0, x1, y1, color):
    data = copy.deepcopy(LINE)
    data["points"][0]["x"] = x0
    data["points"][0]["y"] = y0
    data["points"][1]["x"] = x1
    data["points"][1]["y"] = y1
    data["attr"]["stroke"] = color
    data["color"] = color
    return data


def get_hulls(game: Game) -> dict[int, REC]:
    return {h["id"]: h for h in game.turn().rst["hulls"]}


def init(game: Game) -> dict[int, SHIP]:
    """Build a dict freights, by hull id"""
    hulls = get_hulls(game)

    def lookup_hull(name):
        return query_one(hulls.values(), lambda h: h["name"] == name)

    ships = [lookup_hull(name) for name in FREIGHTER_NAMES]
    return {int(s["id"]): s for s in ships if s}


def lookup(game: Game, turn: Turn, ship: SHIP, key: str) -> str | int:
    hulls = init(game)
    if key.startswith("player"):
        player_id = ship["ownerid"]
        player = query_one(turn.rst["players"], lambda x: x["id"] == player_id)
        if key == "player":
            return f"P{player_id}-{player['username']}"
        if key == "player_race":
            race = query_one(turn.rst["races"], lambda x: x["id"] == player["raceid"])
            return race["adjective"]
    elif key.startswith("hull."):
        key = key.split(".")[-1]
        return hulls[int(ship["hullid"])][key]
    return ship[key]


def build_rows(game: Game, player_id: int) -> list[REC]:
    hulls = init(game)
    return [
        {k: lookup(game, turn, ship, k) for k in COLS}
        for turn in game.turns.values()
        for ship in query(
            turn.rst["ships"],
            lambda s: s["ownerid"] == player_id and s["hullid"] in hulls,
        )
    ]


def build_report(game: Game, player_id: int) -> list[list[str | int]]:
    """Return list of rows suitable for display"""
    hulls = get_hulls(game)
    rows: list[list[str | int]] = []
    cols: list[str | int] = ["T", "Ship", "Loc", "Tgt", "Warp", "Mass", "Hull"]
    rows.append(cols)
    for rec in build_rows(game, player_id):
        loc = f"{rec['x']},{rec['y']}"
        tgt = f"{rec['targetx']},{rec['targety']}"
        if loc == tgt:
            tgt = ""
        hull_id = int(rec["hullid"])
        hull_name = short_hull_name(hulls[hull_id])
        row: list[str | int] = [
            rec["infoturn"],
            f"S{rec['id']}-{rec['name']}",
            loc,
            tgt,
            rec["warp"],
            rec["mass"],
            hull_name,
        ]
        rows.append(row)
    return rows


# Following functions are for drawing the freighter sightings on the map


def get_diplomacy_color(turn: Turn, player_id: int) -> RGB:
    """Get the colour set in the Planets Nu diplomacy tab"""
    return (
        "#"
        + query_one(turn.rst["relations"], lambda rel: rel["playertoid"] == player_id)[
            "color"
        ]
    )


def shade(hex_color: RGB, percent: float = -0.1) -> RGB:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError(f"Hex color must be in the format #RRGGBB, was {hex_color}")

    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    r = min(255, max(0, int(r * (1 + percent))))
    g = min(255, max(0, int(g * (1 + percent))))
    b = min(255, max(0, int(b * (1 + percent))))

    return f"#{r:02x}{g:02x}{b:02x}"


def build_drawing_data(game, player_id):
    turn = game.turn()

    base_col = get_diplomacy_color(turn, player_id)
    col1 = shade(base_col, 0.1)
    col2 = shade(base_col, -0.1)
    col3 = shade(base_col, -0.25)

    latest_turn = turn.turn_id
    fresh = latest_turn - 4
    older = latest_turn - 10

    def pick_colour(t):
        if t > fresh:
            return col1
        elif t > older:
            return col2
        else:
            return col3

    rows = build_rows(game, player_id)
    points = {}
    circles = {}
    lines = {}

    for row in reversed(rows):
        s_id = row["id"]
        infoturn = row["infoturn"]
        col = pick_colour(infoturn)

        # add a point
        point = row["x"], row["y"]
        label = f"S{s_id}-T{infoturn}"
        if point not in points:
            points[point] = []
        points[point].append((label, col))

        # add a circle
        warp = row["warp"]
        if point not in circles:
            circles[point] = []
        circles[point].append((warp * warp, col))

        target = row["targetx"], row["targety"]
        if point != target:
            # add a segment
            if point not in lines:
                lines[point] = []
            lines[point].append((target, col))

    markups = []
    race = rows[0]["player_race"] if rows else "unknown"
    note = {"name": f"{race} Freighters", "active": True, "markups": markups}
    for coords in points:
        x, y = coords
        items = points[coords]
        color = items[0][1]
        text = " ".join(info for info, _ in items[:3])
        if len(items) > 3:
            text += "..."
        markups.append(Point(x=x, y=y, color=color, text=text))
    for coords in circles:
        x, y = coords
        items = circles[coords]
        color = items[0][1]
        r = items[0][0]
        markups.append(Circle(x=x, y=y, color=color, r=r))
    for coords in lines:
        x, y = coords
        items = lines[coords]
        color = items[0][1]
        for item in items:
            x1, y1 = item[0]
            markups.append(Line(x0=x, y0=y, x1=x1, y1=y1, color=color))

    return json.dumps(note)
