import math

from typing import Any, Dict, List, Tuple, Optional, NamedTuple
from collections import defaultdict, deque

PLANET_ID = int
STARBASE_ID = int

# max warp 9 distance
MAX_DIST = 81.5

# maximum hops to a starbase for planet allocation
MAX_SB_DIST = 3


class Point(NamedTuple):
    x: int
    y: int


def P(obj: dict) -> Point:
    return Point(obj["x"], obj["y"])


def distance(p, q):
    return math.sqrt((p["x"] - q["x"]) ** 2 + (p["y"] - q["y"]) ** 2)


def toroidal_coords(p, map_width: int, map_height: int):
    "project the coordinates into the four mirrors"
    x, y = p["x"], p["y"]
    offsets = [
        (0, 0),
        (map_width, 0),
        (-map_width, 0),
        (0, map_height),
        (0, -map_height),
    ]
    for dx, dy in offsets:
        yield {"x": x + dx, "y": y + dy}


def warp_well_coords(coords):
    offsets = [
        (0, -3),
        (-2, -2),
        (-1, -2),
        (0, -2),
        (1, -2),
        (2, -2),
        (-2, -1),
        (2, -1),
        (-3, 0),
        (3, 0),
        (-2, 1),
        (2, 1),
        (-2, 2),
        (-1, 2),
        (0, 2),
        (1, 2),
        (2, 2),
        (0, 3),
    ]
    for p in coords:
        x, y = p["x"], p["y"]
        for dx, dy in offsets:
            yield {"x": x + dx, "y": y + dy}


def toroidal_distance(p, q, bottom_left: Point, top_right: Point) -> float:
    "return the minimum toroidal distance"
    map_width = top_right[0] - bottom_left[0]
    map_height = top_right[1] - bottom_left[1]
    return min(
        distance(p, s)
        for s in warp_well_coords(toroidal_coords(q, map_width, map_height))
    )


def build_dist_matrix(
    planets: List[Dict[Any, Any]],
    max_dist: Optional[float] = None,
    bottom_left: Optional[Point] = None,
    top_right: Optional[Point] = None,
) -> Dict[Tuple[int, int], float]:
    """Returns a map of the distances between each pair of planets."""

    distances = {}
    num_planets = len(planets)

    if bottom_left and top_right:

        def dist(p, q):
            return toroidal_distance(p, q, bottom_left, top_right)

    else:

        def dist(p, q):
            return distance(p, q)

    for i in range(num_planets):
        for j in range(i + 1, num_planets):
            d = dist(planets[i], planets[j])
            if max_dist and d >= max_dist:
                continue
            distances[(planets[i]["id"], planets[j]["id"])] = d
            distances[(planets[j]["id"], planets[i]["id"])] = d  # Symmetric

    return distances


def build_cliques(
    planets: List[Dict[Any, Any]],
    max_dist: Optional[float] = None,
    bottom_left: Optional[Point] = None,
    top_right: Optional[Point] = None,
) -> list[set[int]]:
    "return list of planets connected by hops of max_dist"
    dm = build_dist_matrix(planets, max_dist, bottom_left, top_right)
    neighbours = defaultdict(set)
    for p, q in dm:
        neighbours[p].add(q)
    cliques = []
    visited = set()
    for lead in neighbours:
        if lead in visited:
            continue
        visited.add(lead)
        clique = set()
        candidates = {lead}
        while candidates:
            p = candidates.pop()
            clique.add(p)
            visited.add(p)
            for q in neighbours[p]:
                if q in clique or q in visited:
                    continue
                candidates.add(q)
        cliques.append(clique)
    return cliques


def infer_toroidal_map_settings(settings) -> tuple[Optional[Point], Optional[Point]]:
    # FIXME verify this
    magic_offset = 149
    magic_padding = 20
    mapshape = settings["mapshape"]
    mapwidth = settings["mapwidth"]
    mapheight = settings["mapheight"]
    if mapshape != 1:
        return None, None
    true_width = mapwidth + magic_padding
    true_height = mapheight + magic_padding
    bottom_left = Point(true_width + magic_offset, true_height + magic_offset)
    top_right = Point(bottom_left[0] + true_width, bottom_left[1] + true_height)
    return bottom_left, top_right


def shortest_paths(
    neighbours: dict[PLANET_ID, set[PLANET_ID]], start_node: PLANET_ID
) -> dict[PLANET_ID, int]:
    """
    Returns a dictionary where keys are nodes and values are the shortest number of steps
    from the given start_node.
    """
    steps = {start_node: 0}  # Distance from start_node to itself is 0
    queue = deque([start_node])

    while queue:
        node = queue.popleft()
        for neighbor in neighbours.get(node, []):
            if neighbor not in steps:  # Only process unvisited nodes
                steps[neighbor] = steps[node] + 1
                queue.append(neighbor)

    return steps


def build_graph(
    distances, my_planet_ids: set[PLANET_ID], max_dist=MAX_DIST
) -> dict[PLANET_ID, set[PLANET_ID]]:
    "build a graph of connected planets"
    graph: dict[PLANET_ID, set[PLANET_ID]] = {}
    for a, b in distances:
        if a not in my_planet_ids or b not in my_planet_ids:
            continue
        d = distances[(a, b)]
        if d > max_dist:
            continue
        if a not in graph:
            graph[a] = set()
        if b not in graph:
            graph[b] = set()
        graph[a].add(b)
        graph[b].add(a)
    return graph


def allocate_planets_to_starbases(turn) -> dict[PLANET_ID, STARBASE_ID]:
    allocation: dict[PLANET_ID, STARBASE_ID] = {}
    alloc_dist: dict[PLANET_ID, float] = {}

    my_planet_ids = {p["id"] for p in turn.planets(turn.player_id)}
    my_starbases = turn.starbases(turn.player_id)

    g = build_graph(turn.distances(), my_planet_ids)

    for sb in my_starbases:
        sb_planet = sb["planetid"]
        paths = shortest_paths(g, sb_planet)
        for p in paths:
            d = paths[p]
            if d > MAX_SB_DIST:
                continue
            if p not in allocation or alloc_dist[p] > d:
                allocation[p] = sb_planet
                alloc_dist[p] = d
    return allocation
