from textual.app import ComposeResult
from textual.events import Click
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Header, Footer
from textual.containers import Container

from rich.text import Text

import logging

from . import vgap
from . import freighters

# from . import milint
logger = logging.getLogger(__name__)
query_one = vgap.query_one


class StarmapWidget(Widget):

    can_focus = True

    BINDINGS = [
        ("c", "center", "Center on HW"),
        ("+", "zoom_in", "Zoom In"),
        ("=", "zoom_in", "Zoom In"),
        ("-", "zoom_out", "Zoom Out"),
        ("w", "pan_up", "Up"),
        ("a", "pan_left", "Left"),
        ("s", "pan_down", "Down"),
        ("d", "pan_right", "Right"),
        ("escape", "pop_screen", "Back"),
    ]

    def __init__(self, game: vgap.Game, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game
        self.scale = 4.0  # ly per logical cell
        # the map starts centered on the homeworld
        planets = self.game.turn().data["planets"]
        center = query_one(planets, lambda p: p["flag"] == 1) or planets[0]
        self.set_center(center)
        self._cell_index: dict[tuple[int, int], int] = {}

    def set_center(self, center: dict) -> None:
        self.center = center
        self.center_xy = (int(self.center["x"]), int(self.center["y"]))

    def render(self) -> Text:
        cx, cy = self.center_xy
        turn = self.game.turn()
        planets = turn.data["planets"]
        starbases = turn.data["starbases"]
        planets_with_starbase = {s["planetid"] for s in starbases}
        # Determine viewport size from the widget so we truly fill it.
        cols = max(10, self.size.width)
        rows = max(5, self.size.height)
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

    def _pan(self, dx_cells: int, dy_cells: int) -> None:
        step = 8  # how many logical cells per keypress
        cx, cy = self.center_xy
        self.center_xy = (
            int(cx + dx_cells * step * self.scale),
            int(cy + dy_cells * step * self.scale),
        )
        self.refresh()

    def on_click(self, event: Click) -> None:
        x, y = event.x, event.y
        planet_id = self._cell_index.get((x, y), -1)
        planets = self.game.turn().data["planets"]
        planet = query_one(planets, lambda p: p["id"] == planet_id)
        if planet:
            self.app.log(f"click {planet['x']},{planet['y']}: {planet['name']}")
        else:
            self.app.log(f"nothing found at {x}, {y}")

    def action_center(self) -> None:
        self.set_center(self.center)
        self.scale = 4.0
        self.refresh()

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
        self.refresh()

    def action_zoom_out(self) -> None:
        self.scale = min(50.0, self.scale * 1.25)
        self.refresh()


class StarmapContainer(Container):

    def __init__(self, game: vgap.Game, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game
        self.scale = 4.0  # ly per logical cell
        self.center_xy: tuple = ()  # (cx, cy) in world coords
        self._cell_index: dict[tuple[int, int], int] = {}

    def compose(self) -> ComposeResult:
        yield StarmapWidget(self.game, id="starmap")


class StarmapScreen(Screen):
    """Full-screen wrapper around the ASCII starmap widget."""

    def __init__(self, game: vgap.Game, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game

    def compose(self) -> ComposeResult:
        yield Header()
        yield StarmapWidget(self.game, id="starmap")
        yield Footer()

    def action_pop_screen(self) -> None:
        self.app.pop_screen()
