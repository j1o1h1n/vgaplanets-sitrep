from textual.app import App, ComposeResult
from textual.screen import Screen
from textual import on
from textual.widgets import Header, Footer, OptionList
from textual.containers import VerticalScroll, Center
from textual.widgets import Label
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static
from textual.widgets import DataTable
from textual.widgets import Collapsible
from rich.text import Text

import getpass
import logging

from . import vgap
from . import econrep
from . import transmission

from typing import Optional

DBFILE = "planets.db"
ALL_SETTINGS = ["state"]

TURNSTATUS = {
    0: ("unseen", "#e7ffff"),
    1: ("seen", "#d45f10"),
    2: ("ready", "#4bb0ff"),
}

logger = logging.getLogger(__name__)
query_one = vgap.query_one


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
        with Vertical(classes="row standard_reports"):
            yield Static("Standard Reports", classes="header")
            with Horizontal(classes="row"):
                yield Button("Military", id="military", classes="report")
                yield OptionList(
                    *self.player_options, id="selected_player", classes="squash"
                )
            yield Button("Economic", id="economic", classes="report")
        yield Footer()


class ChooseGameScreen(Screen):
    """Choose a game"""

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
            title = f"{game.name} - T#{game.info['game']['turn']}"
            player_id = game.turn().player_id
            player = query_one(game.info["players"], lambda p: p["id"] == player_id)
            player_turn_status = TURNSTATUS[player["turnstatus"]][0]
            with Vertical(classes=f"row {player_turn_status}"):
                yield Collapsible(label, collapsed=True, title=title)
                with Horizontal(classes="row buttons"):
                    yield Button(
                        "Select", id=f"g{game.game_id}", classes="game_chooser"
                    )
                    yield Button(
                        "Refresh", id=f"r{game.game_id}", classes="refresh_game"
                    )
        yield Footer()


class LoadingScreen(Screen):

    def compose(self) -> ComposeResult:
        with Center():
            yield transmission.TransmissionPanel()


class SituationReport(App):

    CSS_PATH = "situation_report.tcss"

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

    async def on_mount(self):
        if self.planets_db.requires_update():
            self.run_worker(self.handle_update_games(), exclusive=True)
            self.push_screen(LoadingScreen())
        else:
            self.games = list(self.planets_db.games())
            self.choose_game(self.settings["state"].get("game_id", None))
            if self.game:
                self.push_screen(ReportScreen(self.game))
            else:
                self.push_screen(ChooseGameScreen(self.games))

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

    def choose_game(self, game_id) -> Optional[vgap.Game]:
        game = query_one(self.games, lambda g: g.game_id == game_id)
        if not game:
            return None
        self.game = game
        self.sub_title = self.game.name
        self.settings["state"]["game_id"] = game_id
        return self.game

    @on(Button.Pressed, ".game_chooser")
    def game_chosen(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if not button_id:
            return
        game_id = int(button_id[1:])
        self.push_screen(ReportScreen(self.choose_game(game_id)))

    @on(Button.Pressed, ".refresh_game")
    async def refresh_game(self, event: Button.Pressed) -> None:
        "update global game info and reload latest turn of selected game"
        button_id = event.button.id
        if not button_id:
            return
        game_id = int(button_id[1:])
        self.run_worker(self.handle_refresh_game(game_id), exclusive=True)
        self.push_screen(LoadingScreen())

    async def handle_update_games(self):
        "update game data, call from worker"
        await self.planets_db.update()
        self.games = list(self.planets_db.games())
        self.push_screen(ChooseGameScreen(self.games))

    async def handle_refresh_game(self, game_id):
        "refresh game data, call from worker"
        await self.planets_db.update(force_update=True)

        self.game = query_one(self.games, lambda g: g.game_id == game_id)
        turn_id = self.game.turn().turn_id
        await planets_db.update_turn(game_id, turn_id)

        self.games = list(self.planets_db.games())
        self.push_screen(ReportScreen(self.game))

    @on(Button.Pressed, ".report")
    def report_pressed(self, event: Button.Pressed) -> None:
        """Pressed a report button"""
        assert event.button.id is not None
        rows = []
        player_id = None
        cols = data = []
        match event.button.id:
            case "military":
                player_id = self.query_one(ReportScreen).selected_player
                racename = self.game.players[player_id].racename if player_id else ""
                if not player_id:
                    return
                scores = self.game.scores()[player_id]
                cols, data = build_milscore_report(scores)
                rows.append(cols)
                rows.extend(data)
                self.push_screen(ReportTableScreen(rows, racename=racename))
            case "economic":
                racename = self.game.players[self.game.turn().player_id].racename
                self.push_screen(
                    econrep.EconReportTableScreen(self.game, racename=racename)
                )


planets_db = vgap.PlanetsDBAsync(DBFILE)
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
