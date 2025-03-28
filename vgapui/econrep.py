import math
import logging

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Header, Footer

# from textual.containers import VerticalScroll

from textual.widgets import Collapsible
from textual.widgets import DataTable

from rich.text import Text

from . import space
from . import vgap

query_one = vgap.query_one

logger = logging.getLogger(__name__)

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


def build_econ_report(turn):
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
    ]
    keys = [
        "megacredits",
        "supplies",
        "neutronium",
        "duranium",
        "tritanium",
        "molybdenum",
    ]

    def make_rec(d):
        return [d[k] for k in keys]

    def planet_label(planet, my_starbases):
        t = planet["temp"]
        idx = min(math.trunc(t / 5), len(COLOURS) - 1)
        c = COLOURS[idx]
        has_starbase = planet["id"] in my_starbases
        marker = "⨁" if has_starbase else "◯"
        return Text.assemble((marker, c), (f" P{planet['id']}-{planet['name']}", c))

    player_id = turn.player_id
    my_planets = turn.planets(player_id)
    # my_ships = turn.ships(player_id)
    my_starbases = {sb["planetid"]: sb for sb in turn.starbases(player_id)}

    sector_map = {
        planet_id: s + 1
        for s, sector in enumerate(turn.sectors())
        for planet_id in sector
    }
    sb_allocation = space.allocate_planets_to_starbases(turn)

    rows = [
        (
            (sector_map.get(p["id"], 0), sb_allocation.get(p["id"], 0), p["id"]),
            sector_map.get(p["id"], 0),
            sb_allocation.get(p["id"], 0),
            planet_label(p, my_starbases),
            *make_rec(p),
        )
        for p in my_planets
    ]
    rows.sort()
    rows = [row[1:] for row in rows]

    return cols, rows


class EconReportTableScreen(Screen):

    BINDINGS = [("c", "copy_data", "Copy")]

    def __init__(self, game, *args, racename="", **kwargs):
        super().__init__(*args, **kwargs)
        self.sub_title = racename

        turn = game.turn()
        player_id = turn.player_id
        self.my_planets = {p["id"]: p for p in turn.planets(player_id)}
        self.my_starbases = {sb["planetid"]: sb for sb in turn.starbases(player_id)}

        self.cols, self.rows = build_econ_report(game.turn())

        # for copying
        self.table_text = "\t".join(self.cols) + "\n"
        self.table_text += "\n".join(
            ["\t".join([str(c) for c in row]) for row in self.rows]
        )

    def compose(self) -> ComposeResult:
        sectors: dict[int, list[int]] = {}
        for row in self.rows:
            s, sb = row[:2]
            if s not in sectors:
                sectors[s] = []
            if sb not in sectors[s]:
                sectors[s].append(sb)

        def build_data_table(sector: int, planetid: int) -> DataTable:
            rows = [r[2:] for r in self.rows if r[0] == sector and r[1] == planetid]
            sums = [0] * (len(rows[-1]) - 1)
            for row in rows:
                for col in range(len(sums)):
                    sums[col] += row[col + 1]
            rows.append(["Total"] + sums)

            table: DataTable = DataTable()
            table.add_columns(*self.cols[2:])
            table.add_rows(rows)
            return table

        yield Header()
        for sector in sectors:
            title = f"Sector {sector}" if sector else "Isolated"
            with Collapsible(title=title):
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

                    with Collapsible(title=subtitle):
                        yield build_data_table(sector, planetid)
        yield Footer()

    def action_copy_data(self):
        self.app.copy_to_clipboard(self.table_text)
