from textual import on
from textual.app import App, ComposeResult
from textual.events import Click
from textual.containers import Container, VerticalScroll, Center, Horizontal, Vertical
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Label,
    Header,
    Footer,
    Button,
    Static,
    DataTable,
    Collapsible,
    RadioSet,
    RadioButton,
    MarkdownViewer,
)
from textual_plotext import PlotextPlot

from rich.text import Text

import datetime
import random
import getpass
import logging

from . import vgap
from . import helpdoc
from . import econrep
from . import msglog
from . import freighters

# from . import milint
from . import graph
from . import transmission
from .widgets import rule

from typing import Optional

DBFILE = "planets.db"
ALL_SETTINGS = ["state"]

TURNSTATUS = {
    0: ("unseen", "#e7ffff"),
    1: ("seen", "#d45f10"),
    2: ("ready", "#4bb0ff"),
}

ELITE = "🯰🯱🯲🯳🯴🯵🯶🯷🯸🯹"


def elite(n):
    chars = []
    while n > 0:
        chars.append(ELITE[n % 10])
        n = n // 10
    return "".join(reversed(chars))


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

    BINDINGS = [
        ("c", "copy_data", "Copy"),
        ("x", "copy_json", "Export Diagram"),
        ("z", "copy_json_shim", "Copy Export JS Shim"),
    ]

    def __init__(self, rows, *args, json_data="", race="", help="", **kwargs):
        super().__init__(*args, **kwargs)
        self.sub_title = race
        self.json_data = json_data
        self.table = DataTable(zebra_stripes=True)
        self.table.add_columns(*rows[0])
        self.table.add_rows(rows[1:])
        self.table_text = "\n".join(["\t".join([str(c) for c in row]) for row in rows])
        self.help = help

    def on_mount(self):
        self.refresh_bindings()

    def on_screen_resume(self):
        self.app.update_help(self.help)

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield self.table
        yield Footer()

    def action_copy_data(self):
        self.app.copy_to_clipboard(self.table_text)

    def action_copy_json(self):
        self.app.copy_to_clipboard(f"install_drawing({self.json_data})")

    def action_copy_json_shim(self):
        self.app.copy_to_clipboard(freighters.INSTALL_DRAWING_JS)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        """Check if an action may run."""
        if action == "copy_json" and not self.json_data:
            return False
        if action == "copy_json_shim" and not self.json_data:
            return False
        return True


class ChoosePlayer(ModalScreen):

    def __init__(self, turn_id, players: dict[int, vgap.Player], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.turn_id = turn_id
        self.players = players

    def compose(self) -> ComposeResult:
        with Container():
            yield rule.Rule.horizontal(
                title="▥▥ SELECT PLAYER ▥▥",
                line_style="medium",
                cap_style="round",
            )
            with RadioSet():
                for player in self.players.values():
                    title = f"{player.race} - {player.name}"
                    yield RadioButton(f"{title}", id=f"P{player.player_id}")
            yield rule.Rule.horizontal(
                title=f"▥▥ †{elite(self.turn_id)} ▥▥",
                line_style="medium",
                cap_style="round",
                classes="subtitle",
            )

    @on(RadioSet.Changed)
    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.pressed.id:
            player_id = int(event.pressed.id[1:])
            self.dismiss(player_id)


class HelpModal(ModalScreen):

    BINDINGS = [
        ("escape", "pop_screen", "Back"),
    ]

    def __init__(self, doc, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.doc = doc

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield MarkdownViewer(self.doc)

    def action_pop_screen(self):
        self.app.pop_screen()


class StarMapScreen(Screen):
    """ASCII starmap viewer centered on the flagged planet."""

    BINDINGS = [
        ("escape", "pop_screen", "Back"),
        ("c", "center", "Center on HW"),
        ("+", "zoom_in", "Zoom In"),
        ("=", "zoom_in", "Zoom In"),
        ("-", "zoom_out", "Zoom Out"),
        ("w", "pan_up", "Up"),
        ("a", "pan_left", "Left"),
        ("s", "pan_down", "Down"),
        ("d", "pan_right", "Right"),
    ]

    def __init__(self, game: vgap.Game, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game
        self.scale = 4.0  # start more zoomed-in (smaller ly-per-cell)
        self.center_xy: tuple = ()  # (cx, cy) in world coords
        self._cell_index: dict[tuple[int, int], int] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        starmap = Static(id="starmap")
        yield starmap
        yield Footer()

    def on_mount(self) -> None:
        starmap = self.query_one("#starmap", Static)
        # Fill all available space and hide overflow.
        starmap.styles.width = "100%"
        starmap.styles.height = "1fr"
        # starmap.styles.overflow = "hidden"
        # Near-black background for the starfield
        starmap.styles.background = "#050505"

    def on_ready(self) -> None:
        # First real render happens after initial layout
        self.redraw()

    def redraw(self) -> None:
        self.query_one("#starmap", Static).update(self.render_map())

    def on_resize(self) -> None:
        # Recompute viewport-dimension-based grid on any resize.
        self.redraw()
        starmap = self.query_one("#starmap", Static)
        cols = starmap.size.width or self.size.width or 80
        rows = starmap.size.height or (self.size.height - 2) or 24  # header+footer
        cols = max(10, cols)
        rows = max(5, rows)

    def _ensure_center(self, turn) -> None:
        if self.center_xy:
            return
        planets = turn.data["planets"]
        center = query_one(planets, lambda p: p["flag"] == 1) or planets[0]
        self.center_xy = (int(center["x"]), int(center["y"]))

    def render_map(self) -> Text:
        turn = self.game.turn()
        self._ensure_center(turn)
        cx, cy = self.center_xy
        planets = turn.data["planets"]
        starbases = turn.data["starbases"]
        planets_with_starbase = {s["planetid"] for s in starbases}
        # Determine viewport size from the widget so we truly fill it.
        starmap = self.query_one("#starmap", Static)
        cols = max(10, starmap.size.width)
        rows = max(5, starmap.size.height)
        # Two columns per logical cell horizontally
        width_cells = max(5, cols // 2)
        height_cells = max(3, rows)
        radius_x = width_cells // 2
        radius_y = height_cells // 2
        scale = self.scale  # ly per logical cell
        width = width_cells * 2
        height = height_cells

        # build double-width grid
        grid: list[list[tuple[str, str | None]]]
        grid = [[(" ", None) for _ in range(width)] for _ in range(height)]
        self._cell_index.clear()

        def plot(
            planet_id: int, dx: int, dy: int, left: str, right: str, style: str | None
        ):
            x = int(radius_x * 2 + dx * 2)
            y = int(radius_y - dy)
            if 0 <= y < height and 0 <= x + 1 < width:
                grid[y][x] = (left, style)
                grid[y][x + 1] = (right, style)
                self._cell_index[(x, y)] = planet_id
                self._cell_index[(x + 1, y)] = planet_id

        for p in planets:
            dx = int((p["x"] - cx) / scale)
            dy = int((p["y"] - cy) / scale)
            if abs(dx) <= radius_x and abs(dy) <= radius_y:
                planet_id = int(p["id"])
                ownerid = int(p.get("ownerid", 0))
                color = freighters.get_diplomacy_color(turn, ownerid)
                sb = "𜹐" if p["id"] in planets_with_starbase else " "
                plot(planet_id, dx, dy, "🮮", sb, color)

        out = Text()
        for y in range(height):
            if y:
                out.append("\n")
            for ch, style in grid[y]:
                out.append(ch, style=style) if style else out.append(ch)
        return out

    def on_click(self, event: Click) -> None:
        # Only act on clicks inside the starmap widget
        if getattr(event.widget, "id", None) != "starmap":
            return
        x, y = event.x, event.y
        planet_id = self._cell_index.get((x, y), -1)
        planets = self.game.turn().data["planets"]
        planet = query_one(planets, lambda p: p["id"] == planet_id)
        if planet:
            self.app.log(f"click {planet['x']},{planet['y']}: {planet['name']}")
        else:
            self.app.log(f"nothing found at {x}, {y}")

    # --- Panning with WASD / Arrow keys (world units = ly) ---
    def _pan(self, dx_cells: int, dy_cells: int) -> None:
        if self.center_xy is None:
            return
        step = 8  # how many logical cells per keypress
        cx, cy = self.center_xy
        self.center_xy = (
            int(cx + dx_cells * step * self.scale),
            int(cy + dy_cells * step * self.scale),
        )
        self.redraw()

    def action_center(self) -> None:
        self.center_xy = ()
        self.scale = 4.0
        self._ensure_center(self.game.turn())
        self.redraw()

    def action_pan_left(self) -> None:
        self._pan(-1, 0)

    def action_pan_right(self) -> None:
        self._pan(1, 0)

    def action_pan_up(self) -> None:
        self._pan(0, 1)

    def action_pan_down(self) -> None:
        self._pan(0, -1)

    def action_zoom_in(self) -> None:
        # smaller ly-per-cell => closer
        self.scale = max(1.0, self.scale * 0.8)
        self.redraw()

    def action_zoom_out(self) -> None:
        self.scale = min(50.0, self.scale * 1.25)
        self.redraw()

    def action_pop_screen(self):
        self.app.pop_screen()


class ReportScreen(Screen):

    BINDINGS = [
        ("escape", "pop_screen", "Pop the current screen"),
        ("[", "previous_graph", "Previous graph"),
        ("]", "next_graph", "Next graph"),
        ("t", "next_theme", "Next theme"),
        ("m", "starmap", "StarMap"),
    ]

    THEMES = [
        "textual-clear",
        "textual-dark",
        "textual-default",
        "textual-dreamland",
        "textual-elegant",
        "textual-girly",
        "textual-grandpa",
        "textual-matrix",
        "textual-mature",
        "textual-pro",
        "textual-retro",
        "textual-sahara",
        "textual-salad",
        "textual-scream",
        "textual-serious",
        "textual-windows",
    ]

    def __init__(self, game, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game
        self.graphs = list(graph.GRAPHS.keys())
        self.graph_type_id = random.randint(0, len(self.graphs) - 1)
        self.plot = PlotextPlot()
        self.plot_theme = 10
        self.plot.theme = self.THEMES[self.plot_theme]
        self.plot_container = Container(self.plot)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(classes="row standard_reports"):
            yield self.plot_container
            yield Static("Standard Reports", classes="header")
            with Horizontal():
                yield Button("Intel", id="intel")
                yield Button("Econ", id="economic")
                yield Button("FreightTrac", id="freighter")
                yield Button("MsgLog", id="msgs")
        yield Footer()

    def on_mount(self):
        plt = self.query_one(PlotextPlot).plt
        graph.update_plot(self.game, plt, self.graphs[self.graph_type_id])

    def on_screen_resume(self):
        self.app.update_help(helpdoc.MAIN)

    def action_starmap(self):
        self.app.push_screen(StarMapScreen(self.game))

    @on(Button.Pressed)
    def report_pressed(self, event: Button.Pressed) -> None:
        """Pressed a report button"""
        match event.button.id:
            case "intel":
                self.app.push_screen(
                    ChoosePlayer(max(self.game.turns().keys()), self.game.players),
                    self.handle_intel_report,
                )
            case "economic":
                race = self.game.players[self.game.turn().player_id].race
                self.app.push_screen(
                    econrep.EconReportTableScreen(self.game, race=race)
                )
            case "freighter":
                self.app.push_screen(
                    ChoosePlayer(self.game.turn().turn_id, self.game.players),
                    self.handle_freighter_report,
                )
            case "msgs":
                self.app.push_screen(msglog.MessagesScreen(self.game))

    def handle_intel_report(self, player_id):
        player = self.game.players[player_id]
        scores = self.game.scores()[player_id]
        cols, data = build_milscore_report(scores)
        rows = []
        rows.append(cols)
        rows.extend(data)
        self.app.push_screen(
            ReportTableScreen(rows, race=player.race, help=helpdoc.INTEL)
        )

    def handle_freighter_report(self, player_id):
        player = self.game.players[player_id]
        rows = freighters.build_report(self.game, player_id)
        json = freighters.build_drawing_data(self.game, player_id)
        self.app.push_screen(
            ReportTableScreen(
                rows, json_data=json, race=player.race, help=helpdoc.FREIGHTERS
            )
        )

    def replot(self) -> None:
        """Set up the plot."""
        plt = self.query_one(PlotextPlot).plt
        name = self.graphs[self.graph_type_id]
        self.plot_container.styles.animate("opacity", value=0.0, duration=0.6)

        def fade_back():
            graph.update_plot(self.game, plt, name)
            self.plot_container.styles.animate(
                "opacity", value=1.0, duration=0.5, easing="in_cubic"
            )

        self.set_timer(0.6, fade_back)

    def action_next_graph(self) -> None:
        self.graph_type_id = (self.graph_type_id + 1) % len(self.graphs)
        self.replot()

    def action_previous_graph(self) -> None:
        self.graph_type_id -= 1
        if self.graph_type_id < 0:
            self.graph_type_id = len(self.graphs) - 1
        self.replot()

    def action_next_theme(self) -> None:
        self.plot_theme = (self.plot_theme + 1) % len(self.THEMES)
        self.plot.theme = self.THEMES[self.plot_theme]
        self.notify(
            title="Theme updated",
            message=f"Theme is {self.THEMES[self.plot_theme]}.",
        )


class ChooseGameScreen(Screen):
    """Choose a game"""

    def __init__(self, games, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.games = games

    def build_turn_info(self, game):
        races = {r["id"]: r["adjective"] for r in game.turn().data["races"]}
        players = [p for p in game.info["players"] if p["accountid"]]
        data = [
            (p["username"], races[p["raceid"]], TURNSTATUS[p["turnstatus"]][1])
            for p in players
        ]
        res = []
        for name, race, status in data:
            res.extend([("•", status), f" {name} ({race})\n"])
        return Text.assemble(*res)

    def gen_game_info(self, game):
        label = Label(self.build_turn_info(game))
        title = f"{game.name} - {game.data['statusname']} T#{game.info['game']['turn']}"
        player_id = game.turn().player_id
        player = query_one(game.info["players"], lambda p: p["id"] == player_id)
        player_turn_status = TURNSTATUS[player["turnstatus"]][0]
        with Collapsible(collapsed=True, title=title, classes=player_turn_status):
            yield label
            yield Button("Select 🚀", id=f"g{game.game_id}", classes="game_chooser")
            yield Button("Refresh ♻️", id=f"r{game.game_id}", classes="refresh_game")

    def compose(self) -> ComposeResult:
        yield Header()
        for game in self.games:
            yield from self.gen_game_info(game)
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
        ("?", "help", "Help"),
    ]

    def __init__(self, planets_db, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.planets_db = planets_db
        self.settings = self.planets_db.settings()
        self.game = None
        self.help_text = ""
        for k in ALL_SETTINGS:
            if k not in self.settings:
                self.settings[k] = {}

    def update_help(self, help_text):
        self.help_text = help_text

    async def on_mount(self):
        if self.planets_db.requires_update():
            self.run_worker(self.handle_update_games(), exclusive=True)
            self.push_screen(LoadingScreen())
        else:
            self.games = list(self.planets_db.games())
            # sort by status and last update date
            self.games.sort(
                key=lambda g: (
                    -int(g.data["status"]),
                    datetime.datetime.strptime(
                        g.data["lasthostdate"], "%m/%d/%Y %I:%M:%S %p"
                    ),
                ),
                reverse=True,
            )
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
        yield Static(helpdoc.SITREP, classes="display")
        yield Footer()

    def action_pop_screen(self):
        if len(self._screen_stack) > 1:
            self.pop_screen()

    def action_help(self):
        self.push_screen(HelpModal(self.help_text))

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
        # sort by status and last update date
        self.games.sort(
            key=lambda g: (
                -int(g.data["status"]),
                datetime.datetime.strptime(
                    g.data["lasthostdate"], "%m/%d/%Y %I:%M:%S %p"
                ),
            ),
            reverse=True,
        )
        self.push_screen(ChooseGameScreen(self.games))

    async def handle_refresh_game(self, game_id):
        "refresh game data, call from worker"
        await self.planets_db.update(force_update=True)
        game = query_one(self.games, lambda g: g.game_id == game_id)
        turn_id = game.turn().turn_id
        await planets_db.update_turn(game_id, turn_id)

        self.games = list(self.planets_db.games())
        self.game = query_one(self.games, lambda g: g.game_id == game_id)
        self.switch_screen(ReportScreen(self.game))


planets_db = vgap.PlanetsDBAsync(DBFILE)
if not planets_db.account:
    username = input("Username: ")
    password = getpass.getpass("Password: ")
    planets_db.login(username, password)

# used by textual run
app = SituationReport(planets_db)


def main():
    app.run()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,  # Set the logging level to DEBUG
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    main()
