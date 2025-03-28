import math
import heapq

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


def sq_distance(p, q):
    dx = p["x"] - q["x"]
    dy = p["y"] - q["y"]
    dist_sq = dx * dx + dy * dy
    return dist_sq


def distance(p, q):
    return math.sqrt(sq_distance(p, q))


class KDNode:

    def __init__(
        self,
        point: dict,
        left: Optional["KDNode"] = None,
        right: Optional["KDNode"] = None,
    ):
        self.point = point
        self.left = left
        self.right = right


def build_kd_tree(points: list[dict], depth=0) -> Optional[KDNode]:
    if not points:
        return None

    # In 2D, axis is 0 for x and 1 for y, alternating with depth
    axis = depth % 2

    # Sort the list of points by the current axis.

    sorted_points = sorted(points, key=lambda p: p["x"] if axis == 0 else p["y"])

    # Select the median point
    median_index = len(sorted_points) // 2

    # Create a node and recursively build the left and right subtrees.
    return KDNode(
        point=sorted_points[median_index],
        left=build_kd_tree(sorted_points[:median_index], depth + 1),
        right=build_kd_tree(sorted_points[median_index + 1 :], depth + 1),
    )


def k_nearest_neighbors(root: KDNode, target: dict, k: int):
    """
    Find the k nearest points to the target in the kd-tree.

    Parameters:
        root: The root node of the kd-tree (built from dicts with "x" and "y").
        target: A dict with "x" and "y" keys representing the query point.
        k: The number of nearest neighbors to return.

    Returns:
        A list of tuples (distance, point), sorted by distance (closest first).
    """
    # Use a max-heap (store negative squared distance)
    best: list[tuple[float, dict]] = []  # Each entry is (-squared_distance, point)

    def search(node, depth=0):
        if node is None:
            return

        # Compute squared Euclidean distance for efficiency.
        dist_sq = sq_distance(target, node)

        # If we don't have k points yet, push current one.
        # Otherwise, check if current point is closer than the farthest in our heap.
        if len(best) < k:
            heapq.heappush(best, (-dist_sq, node.point))
        elif dist_sq < -best[0][0]:
            heapq.heapreplace(best, (-dist_sq, node.point))

        # Determine axis (0 for x, 1 for y)
        axis = depth % 2
        diff = (
            target["x"] - node.point["x"]
            if axis == 0
            else target["y"] - node.point["y"]
        )

        if diff < 0:
            near_branch = node.left
            far_branch = node.right
        else:
            near_branch = node.right
            far_branch = node.left

        # Recurse into the near branch.
        search(near_branch, depth + 1)

        # If the splitting plane is within the current best distance, search far branch.
        if len(best) < k or diff * diff < -best[0][0]:
            search(far_branch, depth + 1)

    search(root)

    # Convert heap to a sorted list (closest first), and compute actual distance.
    result = [(-d, p) for d, p in best]  # d is negative squared distance.
    result.sort(key=lambda x: x[0])
    result = [(math.sqrt(d_sq), p) for d_sq, p in result]
    return result


def range_search(root, target, d):
    """
    Find all points within distance d from the target in the kd-tree.

    Parameters:
        root: The root node of the kd-tree.
        target: A dict with "x" and "y" keys representing the query point.
        d: The distance threshold.

    Returns:
        A list of points (dicts) that are within distance d of the target.
    """
    result = []
    d_sq = d * d  # work with squared distance for efficiency

    def search(node, depth=0):
        if node is None:
            return

        dist_sq = sq_distance(target, node)

        if dist_sq <= d_sq:
            result.append(node.point)

        axis = depth % 2
        diff = (
            target["x"] - node.point["x"]
            if axis == 0
            else target["y"] - node.point["y"]
        )

        # Always search the branch that is nearer first.
        if diff < 0:
            near_branch = node.left
            far_branch = node.right
        else:
            near_branch = node.right
            far_branch = node.left

        search(near_branch, depth + 1)

        # If the splitting plane is within the distance d, search the far branch as well.
        if diff * diff <= d_sq:
            search(far_branch, depth + 1)

    search(root)
    return result


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
