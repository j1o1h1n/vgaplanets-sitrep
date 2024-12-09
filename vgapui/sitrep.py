from textual.app import App, ComposeResult
from textual.containers import HorizontalScroll, VerticalScroll
from textual.screen import Screen
from textual.widgets import Placeholder
from textual import on, work
from textual.widgets import Header, Input, Footer, Markdown
from textual.containers import VerticalScroll
from textual.widgets import Footer, Label, ListItem, ListView
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Button, Static
from textual.widgets import DataTable

import vgapui.vgap

DBFILE = "planets.db"

ALL_SETTINGS = ["state"]


class ReportTableScreen(Screen):

    def __init__(self, rows, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.table = DataTable()
        self.table.add_columns(*rows[0])
        self.table.add_rows(rows[1:])

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(
            self.table
        )
        yield Footer()


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
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Horizontal(
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
        items = [ListItem(Label(game['name'])) for game in self.games]
        self.log(f"Created list items {items}")
        yield Header()
        yield ListView(*items, classes="game_chooser")
        yield Footer()


class SituationReport(App):
    TITLE = "Situation Report"
    SUB_TITLE = ""

    BINDINGS = [("g", "choose_game", "Games"),
                ("escape", "pop_screen", "Pop the current screen")]

    def __init__(self, planets, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.planets = planets
        self.settings = self.planets.settings()
        for k in ALL_SETTINGS:
            if not k in self.settings:
                self.settings[k] = {}
        self.games = list(self.planets.games())
        self.game_id = None
        self.game = None
        self.choose_game(self.settings["state"].get("game_id", None))

    def on_mount(self):
        self.planets.update()
        if self.game:
            self.push_screen(ReportScreen())            

    def on_unmount(self):
        self.planets.save_settings(self.settings)
        self.planets.close()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Footer()

    def action_pop_screen(self) -> None:
        self.pop_screen()

    def action_choose_game(self) -> None:
        self.push_screen(ChooseGameScreen(self.games))

    def choose_game(self, game_id):
        for game in self.games:
            if game["game_id"] == game_id:
                self.game = game
                self.game_id = game_id
                self.sub_title = self.game["name"]
                self.settings['state']['game_id'] = game_id
                return

    @on(ListView.Selected, ".game_chooser")
    def game_chosen(self, selected: ListView.Selected):
        idx = selected.list_view.index
        self.choose_game(self.games[idx]["game_id"])
        self.push_screen(ReportScreen())

    @on(Button.Pressed, ".report")
    def report_pressed(self, event: Button.Pressed) -> None:
        """ Pressed a report button """
        assert event.button.id is not None
        rows = []
        match event.button.id:
            case "military":
                username = "maqusan"
                cols = ['Turn', 'Military Score', 'Military Score +/-', 'Warships', 'Warships +/-']
                data = self.planets.milscore(self.game_id, username)
                rows.append(cols)
                rows.extend(data)
            case "economic":
                pass
        if rows:
            self.push_screen(ReportTableScreen(rows))


planets = vgapui.vgap.Planets(DBFILE)
if not planets.account:
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    planets.login(username, password)

# `textual run --dev src.textual_paint.paint` will search for a
# global variable named `app`, and fallback to
# anything that is an instance of `App`, or
# a subclass of `App`.
app = SituationReport(planets)


def main():
    app.run()

if __name__ == "__main__":
    main()
