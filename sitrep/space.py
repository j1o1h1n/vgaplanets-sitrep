import math
import heapq

from typing import Optional, NamedTuple, Any
from collections import deque

from . import vgap

SHIP_ID = int
PLANET_ID = int
STARBASE_ID = int
PLANET = dict[str, Any]
SHIP = dict[str, Any]
STARBASE = dict[str, Any]
PLANET_SHIP_MAP = dict[PLANET_ID, list[SHIP]]

# max warp 9 distance
MAX_DIST = 81.5

# maximum hops to a starbase for planet allocation
MAX_SB_DIST = 3

# planets in a single warp hop, typically 81 ly
Neighbours = dict[PLANET_ID, list[tuple[float, PLANET_ID]]]

# connected planet sets
Clique = list[set[PLANET_ID]]

# results of a range search
RangeSearch = list[tuple[float, PLANET]]

# shortest path between nodes in a clique
ShortestPaths = dict[int, dict[int, int]]


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


def k_nearest_neighbors(root: KDNode, target: KDNode, k: float | int) -> RangeSearch:
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

    def search(node: KDNode | None, depth=0):
        if node is None:
            return

        # Compute squared Euclidean distance for efficiency.
        dist_sq = sq_distance(target.point, node.point)

        # If we don't have k points yet, push current one.
        # Otherwise, check if current point is closer than the farthest in our heap.
        if len(best) < k:
            heapq.heappush(best, (-dist_sq, node.point))
        elif dist_sq < -best[0][0]:
            heapq.heapreplace(best, (-dist_sq, node.point))

        # Determine axis (0 for x, 1 for y)
        axis = depth % 2
        diff = (
            target.point["x"] - node.point["x"]
            if axis == 0
            else target.point["y"] - node.point["y"]
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


def range_search(root: KDNode | None, target: KDNode, d: float | int) -> RangeSearch:
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

    def search(node: KDNode | None, depth=0):
        if node is None:
            return

        dist_sq = sq_distance(target.point, node.point)

        if dist_sq <= d_sq:
            result.append((dist_sq, node.point))

        axis = depth % 2
        diff = (
            target.point["x"] - node.point["x"]
            if axis == 0
            else target.point["y"] - node.point["y"]
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
    result = [(math.sqrt(d_sq), p) for d_sq, p in result]
    return result


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


def x_warp_well_coords(p):
    offsets = [
        (0, -3),
        (-3, 0),
        (0, 3),
        (3, 0),
        (-2, -2),
        (-2, 2),
        (2, 2),
        (2, -2),
        (-1, -2),
        (1, -2),
        (-2, -1),
        (2, -1),
        (-2, 1),
        (2, 1),
        (1, 2),
        (-1, 2),
        (0, 2),
        (0, -2),
        (0, 0),
    ]
    x, y = p["x"], p["y"]
    for dx, dy in offsets:
        yield {"x": x + dx, "y": y + dy}


def build_neighbours(turn: "vgap.Turn", max_dist: int | float = 81) -> Neighbours:
    "Returns a dict of neighbours for each planet, with distance"
    spherical_map = SphericalMapSettings(turn)
    kdtree = build_kd_tree(turn.planets())
    planets = {p["id"]: p for p in turn.planets()}

    neighbours: Neighbours = {}
    for root_id in planets:
        root_planet = planets[root_id]
        s_coords = [xy for xy in spherical_map.project_coords(root_planet)]

        # get a shortlist of candidates
        candidates: dict[int, tuple[dict, float]] = {}
        for xy in s_coords:
            node = KDNode(xy)
            for d, p in range_search(kdtree, node, max_dist + 5):
                p_id = p["id"]
                if p_id == root_id:
                    continue
                if p_id not in candidates or candidates[p_id][1] > d:
                    candidates[p_id] = (xy, d)

        # check whether the warpwell is reachable for each
        neighbours[root_id] = []
        for candidate_id in candidates:
            target = planets[candidate_id]
            xy = candidates[candidate_id][0]
            for w_coord in x_warp_well_coords(target):
                d = distance(xy, w_coord)
                if d < max_dist + 0.5:
                    neighbours[root_id].append((d, candidate_id))
                    break
        neighbours[root_id] = sorted(neighbours[root_id])
    return neighbours


def build_cliques(neighbours: Neighbours) -> Clique:
    "Return list of planets connected by hops of max_dist, with the first clique the set of isolated planets"
    cliques: Clique = [set()]
    visited = set()
    for lead_id in neighbours:
        if lead_id in visited:
            continue
        visited.add(lead_id)
        clique = set()
        candidates = {lead_id}
        while candidates:
            p = candidates.pop()
            clique.add(p)
            visited.add(p)
            for _, q in neighbours[p]:
                if q in clique or q in visited:
                    continue
                candidates.add(q)
        if len(clique) == 1:
            cliques[0].add(clique.pop())
        else:
            cliques.append(clique)
    return cliques


def shortest_paths(cliques: Clique, neighbours: Neighbours) -> ShortestPaths:
    """
    Returns a dictionary where keys are nodes and values are the shortest number of steps
    from the given start_node.
    """
    paths = {p: {p: 0} for p in cliques[0]}
    for clique in cliques[1:]:
        for start_node in clique:
            steps = {start_node: 0}  # Distance from start_node to itself is 0
            queue = deque([start_node])
            while queue:
                node = queue.popleft()
                for _, neighbor in neighbours.get(node, []):
                    if neighbor not in steps:  # Only process unvisited nodes
                        steps[neighbor] = steps[node] + 1
                        queue.append(neighbor)
            paths[start_node] = steps
    return paths


class SphericalMapSettings:

    # FIXME verify this
    magic_offset = 149
    magic_padding = 20

    def __init__(self, turn):
        settings = turn.data["settings"]
        mapshape = settings["mapshape"]
        mapwidth = settings["mapwidth"]
        mapheight = settings["mapheight"]
        if mapshape != 1:
            raise Exception("map is not spherical")
        true_width = mapwidth + self.magic_padding
        true_height = mapheight + self.magic_padding
        self.bottom_left = Point(
            true_width + self.magic_offset, true_height + self.magic_offset
        )
        self.top_right = Point(
            self.bottom_left[0] + true_width, self.bottom_left[1] + true_height
        )
        self.map_width = self.top_right[0] - self.bottom_left[0]
        self.map_height = self.top_right[1] - self.bottom_left[1]

    def project_coords(self, p: dict):
        "returns the original coordinate and the projection into the four mirrors"
        x, y = p["x"], p["y"]
        offsets = [
            (0, 0),
            (self.map_width, 0),
            (-self.map_width, 0),
            (0, self.map_height),
            (0, -self.map_height),
        ]
        for dx, dy in offsets:
            yield {"x": x + dx, "y": y + dy}

    def __repr__(self):
        return f"<SphericalMapSettings bl: {self.bottom_left}, tr: {self.top_right}>"


class Cluster:

    def __init__(self, turn: "vgap.Turn"):
        self.turn = turn
        # FIXME handle non-spherical map
        self.spherical_map = SphericalMapSettings(turn)
        self.kdtree = build_kd_tree(turn.planets())
        self.neighbours = build_neighbours(self.turn)
        self.cliques = build_cliques(self.neighbours)
        self.paths = shortest_paths(self.cliques, self.neighbours)

    def ships_by_planets(self, player_id: Optional[int] = None) -> PLANET_SHIP_MAP:
        "Return ships by planet id, with id 0 used for ships not at a planet"
        ships = self.turn.ships(player_id)
        ship_map: PLANET_SHIP_MAP = {}
        for ship in ships:
            res = range_search(self.kdtree, KDNode(ship), 0)
            if not res:
                continue
            planet_id = res[0][1]["id"]
            if planet_id not in ship_map:
                ship_map[planet_id] = []
            ship_map[planet_id].append(ship)

        return ship_map

    def allocate_planets_to_starbases(self) -> dict[PLANET_ID, STARBASE_ID]:
        def levels(sb):
            return sum(
                sb[k]
                for k in [
                    "enginetechlevel",
                    "hulltechlevel",
                    "beamtechlevel",
                    "torptechlevel",
                ]
            )

        turn = self.turn
        paths = self.paths
        allocation: dict[PLANET_ID, STARBASE_ID] = {}

        my_planet_ids = {p["id"] for p in turn.planets(turn.player_id)}

        tech_sorted_starbases = reversed(
            sorted(
                (levels(sb), sb["planetid"]) for sb in turn.starbases(turn.player_id)
            )
        )
        my_starbases = [sb for _, sb in tech_sorted_starbases]

        for start_id in my_starbases:
            path = {
                p: d
                for p, d in paths[start_id].items()
                if d <= MAX_SB_DIST and p in my_planet_ids
            }
            for p in path:
                prev = allocation.get(p)
                if not prev or paths[prev][p] > path[p]:
                    allocation[p] = start_id
        return allocation
