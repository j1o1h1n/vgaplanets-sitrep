import math
import logging

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer
from textual.containers import Horizontal

from typing import Any

from textual.widgets import Collapsible
from textual.widgets import DataTable

from textual import on
from rich.text import Text

from . import vgap
from .widgets import rule

from collections import defaultdict


from .vgap import (
    # SHIP_ID,
    PLANET_ID,
    # STARBASE_ID,
    PLANET,
    SHIP,
    STARBASE,
    # PLANET_SHIP_MAP,
    Turn,
)

query_one = vgap.query_one

logger = logging.getLogger(__name__)

# red blue color range for planet temperature
COLOURS = [
    "#4961d2",
    "#5875e1",
    "#6788ee",
    "#779af7",
    "#88abfd",
    "#9abbff",
    "#aac7fd",
    "#bad0f8",
    "#c9d7f0",
    "#d6dce4",
    "#e3d9d3",
    "#edd1c2",
    "#f4c6af",
    "#f7b89c",
    "#f7a889",
    "#f39475",
    "#ec7f63",
    "#e26952",
    "#d55042",
    "#c53334",
]


def build_econ_report(turn: Turn) -> tuple[list[str], list[Any]]:
    cols = [
        "Sector",
        "Starbase",
        "Planet",
        "MCr",
        "Supplies",
        "Neutronium",
        "Duranium",
        "Tritanium",
        "Molybendeum",
        "Ships",
    ]
    keys = [
        "megacredits",
        "supplies",
        "neutronium",
        "duranium",
        "tritanium",
        "molybdenum",
    ]

    def make_rec(planet: PLANET, ships: list[SHIP]) -> list[str]:
        def lookup(k):
            if k == "neutronium":
                return planet[k]
            return sum([planet[k]] + [s[k] for s in ships])

        return [lookup(k) for k in keys]

    def planet_label(planet: PLANET, my_starbases: dict[PLANET_ID, STARBASE]) -> Text:
        t = planet["temp"]
        idx = min(math.trunc(t / 5), len(COLOURS) - 1)
        c = COLOURS[idx]
        has_starbase = planet["id"] in my_starbases
        marker = "⨁" if has_starbase else "◯"
        return Text.assemble((marker, c), (f" P{planet['id']}-{planet['name']}", c))

    def ships_label(planet: PLANET, ships: list) -> str:
        return " ".join([f"S{s['id']}" for s in ships])

    player_id = turn.player_id
    my_planets: list[PLANET] = turn.planets(player_id)
    my_starbases = {sb["planetid"]: sb for sb in turn.starbases(player_id)}
    ships_by_planets = turn.cluster().ships_by_planets(player_id)

    sector_map = {
        planet_id: s for s, sector in enumerate(turn.sectors()) for planet_id in sector
    }
    sb_allocation = turn.cluster().allocate_planets_to_starbases()

    rows = [
        (
            (-sector_map.get(p["id"], 0), -sb_allocation.get(p["id"], 0), p["id"]),
            sector_map.get(p["id"], 0),
            sb_allocation.get(p["id"], 0),
            planet_label(p, my_starbases),
            *make_rec(p, ships_by_planets.get(p["id"], [])),
            ships_label(p, ships_by_planets.get(p["id"], [])),
        )
        for p in my_planets
    ]
    rows.sort()
    # remove the sort key
    rows = [row[1:] for row in rows]

    return cols, rows


class EconReportTableScreen(Screen):

    BINDINGS = [
        ("c", "copy_data", "Copy"),
        ("<", "prev_turn", "Prev Turn"),
        (".", "current_turn", "Current Turn"),
        (">", "next_turn", "Next Turn"),
    ]

    def __init__(self, game, *args, racename="", **kwargs):
        super().__init__(*args, **kwargs)
        self.sub_title = f"{game.data['name']} - {racename}"
        self.game = game
        self.turn = self.game.turn()
        self.expanded = defaultdict(bool)

    def action_prev_turn(self):
        self.update_turn(-1)

    def action_next_turn(self):
        self.update_turn(1)

    def action_current_turn(self):
        self.update_turn(0)

    def update_turn(self, delta: int):
        if delta == 0:
            new_turn_id = max(self.game.turns)
        else:
            turn_id = self.turn.turn_id
            new_turn_id = min(max(1, turn_id + delta), max(self.game.turns))
        if new_turn_id != self.turn.turn_id and new_turn_id in self.game.turns:
            self.turn = self.game.turn(new_turn_id)
            self.refresh(recompose=True)

    def update_data(self):
        player_id = self.turn.player_id
        self.my_planets = {p["id"]: p for p in self.turn.planets(player_id)}
        self.my_starbases = {
            sb["planetid"]: sb for sb in self.turn.starbases(player_id)
        }
        self.cols, self.rows = build_econ_report(self.turn)
        # for copying
        self.table_text = "\t".join(self.cols) + "\n"
        self.table_text += "\n".join(
            ["\t".join([str(c) for c in row]) for row in self.rows]
        )

    def compose(self) -> ComposeResult:
        self.update_data()
        sectors: dict[int, list[int]] = {}
        for row in self.rows:
            s, sb = row[:2]
            if s not in sectors:
                sectors[s] = []
            if sb not in sectors[s]:
                sectors[s].append(sb)

        def build_data_table(sector: int, planetid: int) -> DataTable:
            rows = [r[2:] for r in self.rows if r[0] == sector and r[1] == planetid]

            sums = [0] * (len(rows[-1]) - 2)
            for row in rows:
                for col in range(len(sums)):
                    sums[col] += row[col + 1]
            rows.append(["Total"] + sums + [""])

            table: DataTable = DataTable(zebra_stripes=True)
            table.add_columns(*self.cols[2:])
            table.add_rows(rows)
            return table

        yield Header()
        with Horizontal(classes="rightrow"):
            turn_title = f"▥▥ Turn {self.turn.turn_id} ▥▥"
            yield rule.Rule.horizontal(
                title=turn_title,
                line_style="medium",
                cap_style="round",
                id="turn_ruler",
                classes="infoline",
            )

        for sector in sectors:
            if not sectors[sector]:
                continue
            title = f"Sector {sector}" if sector else "Isolated"
            c_id = f"er-collapsible-s{sector}"
            collapsed = not self.expanded[c_id]
            with Collapsible(id=c_id, title=title, collapsed=collapsed):
                for planetid in sectors[sector]:
                    if planetid:
                        planet = self.my_planets[planetid]
                        starbase = self.my_starbases[planetid]
                        subtitle = f"Starbase P{planetid}-{planet["name"]}"
                        if planet["defense"]:
                            subtitle += f" 🌐 {planet['defense']}"
                        if starbase["defense"]:
                            subtitle += f" 🛡️ {starbase['defense']}"
                        if starbase["fighters"]:
                            subtitle += f" ➢➢ {starbase['fighters']}"
                    else:
                        subtitle = "No Starbase"

                    p_id = f"er-collapsible-s{sector}-p{planetid}"
                    collapsed = not self.expanded[p_id]
                    with Collapsible(id=p_id, title=subtitle, collapsed=collapsed):
                        yield build_data_table(sector, planetid)

        yield Footer()

    def action_copy_data(self):
        self.app.copy_to_clipboard(self.table_text)

    @on(Collapsible.Toggled)
    def on_toggled(self, target: Collapsible.Toggled):
        target_id, target_state = target.collapsible.id, target.collapsible.collapsed
        self.expanded[target_id] = not target_state
