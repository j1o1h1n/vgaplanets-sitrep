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
