import re

from typing import NamedTuple


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
        data = mo.groupdict()
        if data["side1"].startswith("Planet") and data["action"] == "has been captured":
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


def is_glory(record: dict) -> bool:
    return record["messagetype"] in (8, 9) and "shockwave" in record["body"]


def parse_glory(record: dict) -> dict:
    """
    Extract (x, y, ship_id, damage) from a distress record like:
      {'headline': 'GBB Sporocyst ID#368', 'body': '... AT: ( 2342 , 1965 ) ... Damage is at 24%', ...}
    """
    # ship_id from headline
    m_id = re.search(r"ID#(\d+)", record.get("headline", ""))
    # coordinates
    m_xy = re.search(r"AT:\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)", record.get("body", ""))
    # damage percentage
    m_dmg = re.search(r"Damage is at (\d+)%", record.get("body", ""))

    return {
        "x": int(m_xy.group(1)) if m_xy else None,
        "y": int(m_xy.group(2)) if m_xy else None,
        "ship_id": int(m_id.group(1)) if m_id else None,
        "damage": int(m_dmg.group(1)) if m_dmg else None,
    }
