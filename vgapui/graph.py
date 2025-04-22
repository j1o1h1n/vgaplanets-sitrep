"""
Build plots of interesting information.
"""

from . import econ
from . import vgap


GRAPHS = {
    "Mines": "mines",
    "Factories": "factories",
    "Megacredits": "megacredits",
    "Supplies": "supplies",
    "Neutronium": "neutronium",
    "Molybdenum": "molybdenum",
    "Duranium": "duranium",
    "Tritanium": "tritanium",
    "Neutronium Reserves": "groundneutronium",
    "Molybdenum Reserves": "groundmolybdenum",
    "Duranium Reserves": "groundduranium",
    "Tritanium Reserves": "groundtritanium",
    "Population ({race})": "clans",
    "Population (natives)": "nativeclans",
    "Income": None,
}


def h2r(hex_color: str) -> tuple:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        raise ValueError("Hex color must be 6 characters long.")
    rr, gg, bb = hex_color[:2], hex_color[2:4], hex_color[4:]
    return int(rr, 16), int(gg, 16), int(bb, 16)


def get_graph_data(game: vgap.Game, name: str) -> tuple[str, list[int]]:
    if name == "Income":
        vals = []
        for turn in game.turns.values():
            planets = [p for p in turn.planets(turn.player_id)]
            colonies = [econ.build_planet_colony(turn, p["id"]) for p in planets]
            vals.append(sum(econ.calc_income(c) for c in colonies))
    else:
        rsrc = GRAPHS[name]
        vals = [t.stockpile(rsrc) for t in game.turns.values()]
    title = name
    if "{race}" in title:
        race = vgap.get_player_race_name(game.turn())
        title = title.format(race=race)
    return title, vals


def human_readable_ticks(ymin, ymax, n_ticks=5, abbreviate=True):
    import math

    # Calculate a nice step size
    span = ymax - ymin
    raw_step = span / (n_ticks - 1)
    magnitude = 10 ** int(math.floor(math.log10(raw_step)))
    nice_steps = [1, 2, 5, 10]

    # Find closest nice step
    step = min(nice_steps, key=lambda x: abs(raw_step - x * magnitude)) * magnitude

    # Generate ticks, make sure to include ymax if possible
    start = math.floor(ymin / step) * step
    end = math.ceil(ymax / step) * step
    ticks = list(range(int(start), int(end + 1), int(step)))
    if ticks[-1] < ymax:
        ticks.append(int(end + step))

    if abbreviate:

        def fmt_1(n):
            if n >= 1_000_000:
                return f"{n / 1_000_000:0.1f}M"
            elif n >= 1_000:
                return f"{n / 1_000:0.1f}k"
            return str(n)

        def fmt_0(n):
            if n >= 1_000_000:
                return f"{n // 1_000_000}M"
            elif n >= 1_000:
                return f"{n // 1_000}k"
            return str(n)

        labels = [fmt_0(t) for t in ticks[:-1]] + [fmt_1(ticks[-1])]
    else:
        labels = [str(t) for t in ticks]

    return ticks, labels


def update_plot(game, plt, graph_name):
    plt.clear_data()
    title, y_values = get_graph_data(game, graph_name)
    x_values = list(game.turns.keys())
    yticks, ylabels = human_readable_ticks(min(y_values), max(y_values))
    xticks, xlabels = human_readable_ticks(min(x_values), max(x_values))
    plt.plot(
        x_values,
        y_values,
        marker="fhd",
        color=h2r("#97567B"),
    )
    # not working?
    # plt.canvas_color(h2r("#000000"))
    plt.yticks(yticks, ylabels)
    plt.xticks(xticks, xlabels)
    plt.title(title)
