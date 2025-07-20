import math
import re
import copy
import typing
import collections

DEBUG_TURNS = {}
DEBUG_PLAYERS = {}

MISSION_MINE_SWEEP = 1

LAY_MINEFIELD = re.compile(
    r"now contains (\d+) mine units and is (\d+) light years in radius"
)
STARCLUSTER_DESTROY_MINES = re.compile(
    r"has come in contact with the .* (Star Cluster|Debris Disk) and has been partly destroyed. It is now (\d+) light years accross"
)
SWEEP_MINES = re.compile(r"(\d+) mines remain.")
SCOOP_MINES = re.compile(
    r"We have scooped up mines from our minefield #(\d+). (\d+) units have been converted into \d+ torpedos."
)
MINEFIELD_DETONATIONS = re.compile(r"Explosions detected: (\d+)")

SCAN_ENEMY = re.compile(r"closer to target mines with beam weapons.  (\d+) mines remain.")
SCAN_OWN = re.compile(r"Mine field contains (\d+) mines.")


def calc_radius(mines):
    return min(150, int(math.trunc(math.sqrt(mines))))


class Point(typing.NamedTuple):
    x: int
    y: int


class Minefield:
    # TODO adjust for robots
    def __init__(self, mfid: int, ownerid: int, x: int, y: int, web: bool, robot: bool, mines: int):
        self.mfid = mfid
        self.ownerid = ownerid
        self.x = x
        self.y = y
        self.web = web
        self.robot = robot
        self.mines = mines
        c = 4 if self.robot else 1
        self.radius = calc_radius(self.mines * c)

    def __repr__(self):
        t = "Robot" if self.robot else "Web" if self.web else ""
        return f"<{t}Minefield #{self.mfid} @ {self.x},{self.y}: owner={self.ownerid}, mines={self.mines}, radius={self.radius}>"

    def __str__(self):
        t = "W" if self.web else "M"
        return f"{t}{self.mfid},{self.x},{self.y},{self.ownerid},{self.mines},{self.radius}"

    def update(self, delta: int):
        self.mines = max(0, self.mines + delta)
        self.radius = calc_radius(self.mines)

    def scoop(self, scooped: int):
        c = 4 if self.robot else 1
        self.mines = max(0, self.mines - (scooped * c))
        self.radius = calc_radius(self.mines)

    def set_mines(self, mines: int):
        self.mines = mines
        self.radius = calc_radius(self.mines)

    def set_radius(self, radius: int):
        c = 4 if self.robot else 1
        self.mines = round((radius * radius) / c)
        self.radius = radius

    def decay(self, in_nebula=False, decay_rate=0.05):
        # TODO handle nebulas
        # TODO handle dense minefields
        change = -round(self.mines * decay_rate) - 1
        self.update(change)


def is_glory(m):
    return m["messagetype"] in (8, 9) and "shockwave" in m["body"]


def is_mine(m):
    return m["messagetype"] == 16 and "struck a mine" in m["body"]


def is_web_mine(m):
    return m["messagetype"] == 16 and "struck a web mine" in m["body"]


def is_lay_mines(m):
    return (
        m["messagetype"] == 3
        and "We have converted our torpedoes into deep space mines" in m["body"]
    )


def is_scoop_mines(m):
    return (
        m["messagetype"] == 4
        and "We have scooped up mines from our minefield" in m["body"]
    )


def is_sweep_mines(m):
    return (
        m["messagetype"] == 4
        and "Firing beam weapons at random, wide setting to clear mines." in m["body"]
    )

def is_scan_enemy_mines(m):
    return m['messagetype'] == 19 and "We are scanning for mines.  Enemy Mine field detected" in m['body']

def is_scan_our_mines(m):
    return m['messagetype'] == 19 and "We are scanning our mines" in m['body']

def is_starcluster_destroy_mines(m):
    return (
        m["messagetype"] == 3
        and "has come in contact with the" in m["body"]
        and "and has been partly destroyed" in m["body"]
    )


def is_minefield_detonations(m):
    return (
        m["messagetype"] == 4 and "We are detecting minefield detonations" in m["body"]
    )


def sq_distance(p, q):
    dx = p.x - q.x
    dy = p.y - q.y
    dist_sq = dx * dx + dy * dy
    return dist_sq


def distance(p, q):
    return math.sqrt(sq_distance(p, q))


def handle_countermining(minefields, turn_id=None):
    arr = list(sorted(minefields.values(), key=lambda mf: (mf.ownerid, mf.mfid)))
    for i in range(len(arr)):
        lhs = arr[i]
        for rhs in arr[i + 1 :]:
            if rhs.web != lhs.web or rhs.ownerid == lhs.ownerid:
                continue
            dist = distance(lhs, rhs)
            destroyed = 0
            while lhs.mines and rhs.mines and (dist < lhs.radius + rhs.radius):
                lhs.update(-1)
                rhs.update(-1)
                destroyed += 1
            if destroyed and turn_id in DEBUG_TURNS and (lhs.ownerid in DEBUG_PLAYERS or rhs.ownerid in DEBUG_PLAYERS):
                print(f"countermine: {lhs} vs {rhs}: {destroyed} explosions")

def handle_countermining_simple(minefields):
    arr = list(sorted(minefields.values(), key=lambda mf: mf.mfid))
    for i in range(len(arr)):
        lhs = arr[i]
        for rhs in arr[i + 1:]:
            if not lhs.mines:
                break
            if not rhs.mines:
                continue
            if rhs.web != lhs.web:
                continue
            if rhs.ownerid == lhs.ownerid:
                continue
            dist = distance(lhs, rhs)
            if dist < lhs.radius + rhs.radius:
                if lhs.mines < rhs.mines:
                    lhs.update(-lhs.mines)
                    rhs.update(-lhs.mines)
                else:
                    lhs.update(-rhs.mines)
                    rhs.update(-rhs.mines)


def build_minefield(msg: dict, is_robot: bool) -> Minefield:
    assert msg["messagetype"] == 3
    mfid = msg["target"]
    ownerid = msg["ownerid"]
    x, y = msg["x"], msg["y"]
    web = "They are web style mines" in msg["body"]
    mo = LAY_MINEFIELD.search(msg["body"])
    if not mo:
        raise ValueError(msg)
    mines, radius = mo.groups()
    return Minefield(mfid, ownerid, x, y, web, is_robot, int(mines))


def build_msgs(game):
    msgs = {}
    for player_id in game.players:
        for turn in game.turns(player_id).values():
            for msg in turn.data["messages"]:
                msgs[msg["id"]] = msg
    sorted_keys = list(sorted(msgs.keys()))
    msgs = {k: msgs[k] for k in sorted_keys}
    return msgs


def sanity_check_destroy(game, turn_id, minefields, scanned):
    if turn_id < 4:
        return
    prev_turn = turn_id - 1
    sweeps = {}
    for player_id in game.players:
        turn = game.turns(player_id)[prev_turn]
        sweeps.update({ship['id']: Point(ship['x'], ship['y']) for ship 
                      in turn.ships(player_id) 
                      if ship["mission"] == MISSION_MINE_SWEEP and ship["neutronium"] > 0})

    known = set(minefields.keys())
    not_scanned = known - scanned
    should_have_scanned = collections.defaultdict(int)
    for mfid in not_scanned:
        mf = minefields[mfid]
        for s, p1 in sweeps.items():
            d = distance(mf, p1)
            if d < 200 + mf.radius:
                should_have_scanned[mf.mfid] += 1
                # print(f"{turn_id}: ship {s} should have scanned {mf.mfid}")
                break

    # if it was missed by two or more ships, remove
    should_have_scanned = {mfid for mfid in should_have_scanned if should_have_scanned[mfid] > 1}
    if should_have_scanned:
        print(f"sanity_check_destroy: turn={turn_id}: {list(should_have_scanned.keys())}")
    for mfid in should_have_scanned:
        del minefields[mfid]


def build_minefields(game):
    msgs = build_msgs(game)
    max_turn = max(m["turn"] for m in msgs.values())
    minefields_by_turn = {}
    robot_players = {p: game.players[p].short_name == "The Robots" for p in game.players}
    for t in range(1, max_turn + 1):
        minefields = copy.deepcopy(minefields_by_turn.get(t - 1, {}))

        turn_msgs = sorted(
            [m for m in msgs.values() if m["turn"] == t], key=lambda m: m["id"]
        )
        # lay, sweep/scoop, decay, destroy
        lay = [msg for msg in turn_msgs if is_lay_mines(msg)]
        sweep = [msg for msg in turn_msgs if is_sweep_mines(msg) or is_scoop_mines(msg) or is_scan_enemy_mines(msg) or is_scan_our_mines(msg)]
        sc_destroy = [msg for msg in turn_msgs if is_starcluster_destroy_mines(msg)]

        for msg in lay:
            is_robot = robot_players[msg['ownerid']]
            minefield = build_minefield(msg, is_robot)
            minefields[minefield.mfid] = minefield
            if t in DEBUG_TURNS and msg['ownerid'] in DEBUG_PLAYERS:
                print(f"lay {msg} -> {minefield}")

        # starcluster destroy
        for msg in sc_destroy:
            mo = STARCLUSTER_DESTROY_MINES.search(msg["body"])
            mfid = msg["target"]
            radius = int(mo.group(2))
            minefields[mfid].set_radius(radius)
            if t in DEBUG_TURNS:
                print(f"sc_destroy: {msg} -> {minefields[mfid]}")
        scanned = set()
        for msg in sweep:
            player_id = msg["ownerid"]
            try:
                if is_sweep_mines(msg):
                    mo = SWEEP_MINES.search(msg["body"])
                    newmines = int(mo.group(1))
                    mfid = msg["target"]
                    minefields[mfid].set_mines(newmines)
                    scanned.add(mfid)
                    if t in DEBUG_TURNS and player_id in DEBUG_PLAYERS:
                        print("sweep", msg)
                elif is_scoop_mines(msg):
                    mo = SCOOP_MINES.search(msg["body"])
                    mfid = int(mo.group(1))
                    scooped = int(mo.group(2))
                    minefields[mfid].scoop(scooped)
                    scanned.add(mfid)
                    if t in DEBUG_TURNS and player_id in DEBUG_PLAYERS:
                        print("scoops", msg)
                elif is_scan_enemy_mines(msg):
                    mo = SCAN_ENEMY.search(msg['body'])
                    mines = int(mo.group(1))
                    mfid = msg['target']
                    minefields[mfid].set_mines(mines)
                    scanned.add(mfid)
                elif is_scan_our_mines(msg):
                    mo = SCAN_OWN.search(msg['body'])
                    mines = int(mo.group(1))
                    mfid = msg['target']
                    minefields[mfid].set_mines(mines)
                    scanned.add(mfid)
            except KeyError:
                if t in DEBUG_TURNS and player_id in DEBUG_PLAYERS:
                    if is_scan_enemy_mines(msg):
                        mo = SCAN_ENEMY.search(msg['body'])
                        mines = int(mo.group(1))
                        mfid = msg['target']
                        print(f"Unexpected minefield (enemy): {msg['headline']} scans {mfid}/{mines} at {msg['x']},{msg['y']}")
                    elif is_scan_our_mines(msg):
                        mo = SCAN_OWN.search(msg['body'])
                        mines = int(mo.group(1))
                        mfid = msg['target']
                        print(f"Unexpected minefield (own): {msg['headline']} scans {mfid}/{mines} at {msg['x']},{msg['y']}")
                    else:
                        print(f"KeyError: turn {t}: {msg}")
                pass

        # decay
        for minefield in minefields.values():
            in_nebula = False
            minefield.decay(in_nebula)

        handle_countermining(minefields, turn_id=t)

        # remove destroyed minefields
        destroyed = set()
        for mfid in minefields:
            if minefields[mfid].mines == 0:
                destroyed.add(mfid)
        for mfid in destroyed:
            if t in DEBUG_TURNS and minefields[mfid].ownerid in DEBUG_PLAYERS:
                print(f"remove destroyed: {minefields[mfid]}")
            del minefields[mfid]

        # sanity check: any minefield that should have shown up in a scan but
        # didn't is removed
        sanity_check_destroy(game, t, minefields, scanned)

        minefields_by_turn[t] = {k: mf for k, mf in minefields.items() if mf.mines > 0}

    return minefields_by_turn
