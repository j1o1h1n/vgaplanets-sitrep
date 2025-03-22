from textual.app import App, ComposeResult
from textual.screen import Screen
from textual import on
from textual.widgets import Header, Footer, OptionList
from textual.containers import VerticalScroll
from textual.widgets import Label
from textual.containers import Horizontal
from textual.widgets import Button, Static
from textual.widgets import DataTable
from textual.widgets import Collapsible
from rich.text import Text

import getpass
import logging
import vgapui.vgap

from typing import Optional

from .vgap import query_one

DBFILE = "planets.db"
ALL_SETTINGS = ["state"]
TURNSTATUS = {
    0: ("unseen", "grey93", "#eeeeee"),
    1: ("seen", "dark_orange", "#ff8700"),
    2: ("ready", "chartreuse3", "#5fd700"),
}

logger = logging.getLogger(__name__)


def build_milscore_report(scores):
    def unpack(s):
        return (
            s.turn_id,
            s.military_score,
            s.military_score_delta,
            s.capital_ships,
            s.capital_ships_delta,
            s.civilian_ships,
            s.civilian_ships_delta,
            s.starbases,
            s.starbases_delta,
        )

    cols = [
        "Turn",
        "Military Score",
        "Military Score +/-",
        "Warships",
        "Warships +/-",
        "Freighters",
        "Freighters +/-",
        "Starbases",
        "Starbases +/-",
    ]

    data = [unpack(s) for s in scores.values()]
    return cols, data


def build_econ_report(game):
    cols = [
        "Sector",
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

    turn = game.turn()
    sec_map = {
        p_id: i + 1 for i, sector in enumerate(turn.sectors()) for p_id in sector
    }
    planets = turn.planets(turn.player_id)
    data = sorted(
        [
            (
                f"S{sec_map.get(p['id'], 0)}",
                f"P{p['id']}-{p['name']} ⨁",
                *make_rec(p),
            )
            for p in planets
        ]
    )
    return cols, data


class ReportTableScreen(Screen):

    BINDINGS = [("c", "copy_data", "Copy")]

    def __init__(self, rows, *args, racename="", **kwargs):
        super().__init__(*args, **kwargs)
        self.sub_title = racename
        self.table = DataTable()
        self.table.add_columns(*rows[0])
        self.table.add_rows(rows[1:])
        self.table_text = "\n".join(["\t".join([str(c) for c in row]) for row in rows])

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(self.table)
        yield Footer()

    def action_copy_data(self):
        self.app.copy_to_clipboard(self.table_text)


class ReportScreen(Screen):
    DEFAULT_CSS = """
    Button {
        margin: 1 2;
    }

    Horizontal > VerticalScroll {
        width: 24;
    }

    .header {
        margin: 1 0 0 2;
        text-style: bold;
    }

   OptionList {
        width: 80;
        border: blue;
    }

   OptionList:focus-within {
        height: 8;
    }

    .squash {
        height: 3;
    }
    """

    def __init__(self, game, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game
        self.player_options = ["Choose Player"] + [
            f"P{p.id}-{p.username} {p.racename}" for p in self.game.players.values()
        ]
        self.selected_player = None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        vals = list(self.game.players.values())
        if idx > 0:
            self.selected_player = vals[idx - 1].id

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
            OptionList(*self.player_options, id="selected_player", classes="squash"),
            VerticalScroll(
                Static("Standard Reports", classes="header"),
                Button("Military", id="military", classes="report"),
                Button("Economic", id="economic", classes="report"),
            ),
        )
        yield Footer()


class ChooseGameScreen(Screen):
    """Choose a game"""

    DEFAULT_CSS = """
    Screen {
        align: center middle;
    }

    ListView {
        width: 30;
        height: auto;
        margin: 2 2;
    }

    Label {
        padding: 1 2;
    }

    .row {
        height: auto;
    }

    .unseen {
        border: solid #eeeeee;
    }

    .seen {
        border: solid #ff8700;
    }

    .ready {
        border: solid #5fd700;
    }

    """

    def __init__(self, games, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.games = games

    def build_turn_info(self, game):
        races = {r["id"]: r["adjective"] for r in game.turn().rst["races"]}
        players = [p for p in game.info["players"] if p["accountid"]]
        data = [
            (p["username"], races[p["raceid"]], TURNSTATUS[p["turnstatus"]][1])
            for p in players
        ]
        res = []
        for name, race, status in data:
            res.extend([("•", status), f" {name} ({race})\n"])
        return Text.assemble(*res)

    def compose(self) -> ComposeResult:
        yield Header()
        for game in self.games:
            label = Label(self.build_turn_info(game))
            title = f"{game.name} - #{game.info['game']['turn']}"
            player_id = game.turn().player_id
            player = query_one(game.info["players"], lambda p: p["id"] == player_id)
            player_turn_status = TURNSTATUS[player["turnstatus"]][0]
            with Horizontal(classes=f"row {player_turn_status}"):
                yield Collapsible(label, collapsed=True, title=title)
                yield Button("Select", id=f"g{game.game_id}", classes="game_chooser")
        yield Footer()


class SituationReport(App):
    TITLE = "Situation Report"
    SUB_TITLE = ""

    BINDINGS = [
        ("g", "choose_game", "Games"),
        ("escape", "pop_screen", "Pop the current screen"),
    ]

    def __init__(self, planets_db, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.planets_db = planets_db
        self.settings = self.planets_db.settings()
        self.game = None
        for k in ALL_SETTINGS:
            if k not in self.settings:
                self.settings[k] = {}

    def on_mount(self):
        self.planets_db.update()
        self.games = list(self.planets_db.games())
        self.choose_game(self.settings["state"].get("game_id", None))
        if self.game:
            self.push_screen(ReportScreen(self.game))

    def on_unmount(self):
        self.planets_db.save_settings(self.settings)
        self.planets_db.close()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def action_pop_screen(self):
        self.pop_screen()

    def action_choose_game(self):
        self.push_screen(ChooseGameScreen(self.games))

    def choose_game(self, game_id) -> Optional[vgapui.vgap.Game]:
        for game in self.games:
            if game.game_id == game_id:
                self.game = game
                self.sub_title = self.game.name
                self.settings["state"]["game_id"] = game_id
                return game
        return None

    @on(Button.Pressed, ".game_chooser")
    def game_chosen(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id:
            game_id = int(button_id[1:])
            self.push_screen(ReportScreen(self.choose_game(game_id)))

    @on(Button.Pressed, ".report")
    def report_pressed(self, event: Button.Pressed) -> None:
        """Pressed a report button"""
        assert event.button.id is not None
        rows = []
        player_id = None
        match event.button.id:
            case "military":
                player_id = self.query_one(ReportScreen).selected_player
                if not player_id:
                    return
                scores = self.game.scores()[player_id]
                cols, data = build_milscore_report(scores)
            case "economic":
                cols, data = build_econ_report(self.game)
        rows.append(cols)
        rows.extend(data)
        if rows:
            racename = self.game.players[player_id].racename if player_id else ""
            self.push_screen(ReportTableScreen(rows, racename=racename))


planets_db = vgapui.vgap.PlanetsDB(DBFILE)
if not planets_db.account:
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    planets_db.login(username, password)

# `textual run --dev vgapui.sitrep` will search for a
# global variable named `app`, and fallback to
# anything that is an instance of `App`, or
# a subclass of `App`.
app = SituationReport(planets_db)


def main():
    app.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,  # Set the logging level to DEBUG
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    main()
