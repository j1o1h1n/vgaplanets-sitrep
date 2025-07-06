import math
import re
import copy

LAY_MINEFIELD = re.compile(
    r"now contains (\d+) mine units and is (\d+) light years in radius"
)
STARCLUSTER_DESTROY_MINES = re.compile(
    r"has come in contact with the .* Star Cluster and has been partly destroyed. It is now (\d+) light years accross"
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


class Minefield:
    # adjust for robots
    def __init__(self, mfid: int, ownerid: int, x: int, y: int, web: bool, mines: int):
        self.mfid = mfid
        self.ownerid = ownerid
        self.x = x
        self.y = y
        self.web = web
        self.mines = mines
        self.radius = calc_radius(self.mines)

    def __repr__(self):
        web = "" if not self.web else "Web"
        return f"<{web}Minefield #{self.mfid} @ {self.x},{self.y}: owner={self.ownerid}, mines={self.mines}, radius={self.radius}>"

    def __str__(self):
        t = "M" if not self.web else "W"
        return f"{t}{self.mfid},{self.x},{self.y},{self.ownerid},{self.mines},{self.radius}"

    def update(self, delta: int):
        self.mines = max(0, self.mines + delta)
        self.radius = calc_radius(self.mines)

    def set_mines(self, mines: int):
        self.mines = mines
        self.radius = calc_radius(self.mines)

    def set_radius(self, radius: int):
        self.mines = radius * radius
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


def handle_countermining(minefields):
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


def build_minefield(msg):
    assert msg["messagetype"] == 3
    mfid = msg["target"]
    ownerid = msg["ownerid"]
    x, y = msg["x"], msg["y"]
    web = "They are web style mines" in msg["body"]
    mo = LAY_MINEFIELD.search(msg["body"])
    if not mo:
        raise ValueError(msg)
    mines, radius = mo.groups()
    return Minefield(mfid, ownerid, x, y, web, int(mines))


def build_msgs(game):
    msgs = {}
    for player_id in game.players:
        for turn in game.turns(player_id).values():
            for msg in turn.data["messages"]:
                msgs[msg["id"]] = msg
    sorted_keys = list(sorted(msgs.keys()))
    msgs = {k: msgs[k] for k in sorted_keys}
    return msgs


def build_minefields(game):
    msgs = build_msgs(game)
    max_turn = max(m["turn"] for m in msgs.values())
    minefields_by_turn = {}
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
            minefield = build_minefield(msg)
            minefields[minefield.mfid] = minefield

        for msg in sweep:
            if is_sweep_mines(msg):
                mo = SWEEP_MINES.search(msg["body"])
                newmines = int(mo.group(1))
                mfid = msg["target"]
                minefields[mfid].set_mines(newmines)
            elif is_scoop_mines(msg):
                mo = SCOOP_MINES.search(msg["body"])
                mfid = int(mo.group(1))
                scooped = int(mo.group(2))
                minefields[mfid].update(-scooped)
            elif is_scan_enemy_mines(msg):
                mo = SCAN_ENEMY.search(msg['body'])
                mines = int(mo.group(1))
                mfid = msg['target']
                minefields[mfid].set_mines(mines)
            elif is_scan_our_mines(msg):
                mo = SCAN_OWN.search(msg['body'])
                mines = int(mo.group(1))
                mfid = msg['target']
                minefields[mfid].set_mines(mines)

        # decay
        for minefield in minefields.values():
            in_nebula = False
            minefield.decay(in_nebula)

        # destroy
        for msg in sc_destroy:
            mo = STARCLUSTER_DESTROY_MINES.search(msg["body"])
            mfid = msg["target"]
            radius = int(mo.group(1))
            minefield = minefields[mfid].set_radius(radius)

        minefields_by_turn[t] = {k: mf for k, mf in minefields.items() if mf.mines > 0}

    return minefields_by_turn
