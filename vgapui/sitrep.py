from textual.app import App, ComposeResult
from textual.containers import HorizontalScroll, VerticalScroll
from textual.screen import Screen
from textual.widgets import Placeholder
from textual import on, work
from textual.widgets import Header, Input, Footer, Markdown, OptionList
from textual.containers import VerticalScroll
from textual.widgets import Footer, Label, ListItem, ListView
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Static
from textual.widgets import DataTable

import getpass
import logging
import vgapui.vgap

DBFILE = "planets.db"
ALL_SETTINGS = ["state"]


logger = logging.getLogger(__name__)


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
        yield VerticalScroll(
            self.table
        )
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
        self.player_options = ["Choose Player"] + [f"P{p.id}-{p.username} {p.racename}" 
                                                   for p in self.game.players.values()]
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
    """ Choose a game """

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
    """

    def __init__(self, games, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.games = games

    def compose(self) -> ComposeResult:
        items = [ListItem(Label(game.name)) for game in self.games]
        self.log(f"Created list items {items}")
        yield Header()
        yield ListView(*items, classes="game_chooser")
        yield Footer()


class SituationReport(App):
    TITLE = "Situation Report"
    SUB_TITLE = ""

    BINDINGS = [("g", "choose_game", "Games"),
                ("escape", "pop_screen", "Pop the current screen")]

    def __init__(self, planets_db, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.planets_db = planets_db
        self.settings = self.planets_db.settings()
        for k in ALL_SETTINGS:
            if not k in self.settings:
                self.settings[k] = {}
        self.games = list(self.planets_db.games())
        self.game = None
        self.choose_game(self.settings["state"].get("game_id", None))

    def on_mount(self):
        self.planets_db.update()
        if self.game:
            self.push_screen(ReportScreen(self.game))            

    def on_unmount(self):
        self.planets_db.save_settings(self.settings)
        self.planets_db.close()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def action_pop_screen(self) -> None:
        self.pop_screen()

    def action_choose_game(self) -> None:
        self.push_screen(ChooseGameScreen(self.games))

    def choose_game(self, game_id):
        for game in self.games:
            if game.game_id == game_id:
                self.game = game
                self.sub_title = self.game.name
                self.settings['state']['game_id'] = game_id
                return

    @on(ListView.Selected, ".game_chooser")
    def game_chosen(self, selected: ListView.Selected):
        idx = selected.list_view.index
        game = self.games[idx]
        self.choose_game(game.game_id)
        self.push_screen(ReportScreen(game))

    @on(Button.Pressed, ".report")
    def report_pressed(self, event: Button.Pressed) -> None:
        """ Pressed a report button """
        assert event.button.id is not None
        rows = []
        player_id = None
        match event.button.id:
            case "military":
                player_id = self.query_one(ReportScreen).selected_player
                if not player_id:
                    return
                scores = self.game.scores()[player_id]
                cols = ['Turn', 'Military Score', 'Military Score +/-', 'Warships', 'Warships +/-', 'Freighters', 'Freighters +/-', 'Starbases', 'Starbases +/-']
                data = [(s.turn_id, s.military_score, s.military_score_delta, 
                         s.capital_ships, s.capital_ships_delta,
                         s.civilian_ships, s.civilian_ships_delta,
                         s.starbases, s.starbases_delta)
                        for s in scores.values()]
                rows.append(cols)
                rows.extend(data)
            case "economic":
                pass
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
        format="%(asctime)s - %(levelname)s - %(message)s"
    )
    main()
