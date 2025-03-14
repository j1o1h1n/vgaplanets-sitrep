import math

from typing import Any, Dict, List, Tuple, Optional
from collections import defaultdict

MAX_DIST = 83

Point = tuple[int, int]


def distance(p1, p2):
    return math.sqrt((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)


def toroidal_coords(p, map_width: int, map_height: int):
    " project the coordinates into the four mirrors "
    x, y = p['x'], p['y']
    offsets = [(0,0), (map_width, 0), (-map_width, 0), (0, map_height), (0, -map_height)]
    for dx, dy in offsets:
        yield {'x': x + dx, 'y': y + dy}


def toroidal_distance(p, q, bottom_left: Point, top_right: Point) -> float:
    " return the minimum toroidal distance "
    map_width = top_right[0] - bottom_left[0]
    map_height = top_right[1] - bottom_left[1]
    return min(distance(p, s) for s in toroidal_coords(q, map_width, map_height))


def build_dist_matrix(planets: List[Dict[Any, Any]], 
                      max_dist: Optional[float]=None, 
                      bottom_left: Optional[Point]=None, 
                      top_right: Optional[Point]=None) -> Dict[Tuple[int, int], float]:
    """Returns a map of the distances between each pair of planets."""

    distances = {}
    num_planets = len(planets)

    if bottom_left and top_right:
        dist = lambda p, q: toroidal_distance(p, q, bottom_left, top_right)
    else:
        dist = lambda p, q: distance(p, q)
    
    for i in range(num_planets):
        for j in range(i + 1, num_planets):
            d = dist(planets[i], planets[j])
            if max_dist and d > max_dist:
                continue
            distances[(planets[i]['id'], planets[j]['id'])] = d
            distances[(planets[j]['id'], planets[i]['id'])] = d  # Symmetric
    
    return distances


def build_cliques(planets: List[Dict[Any, Any]], 
                  max_dist: Optional[float]=None, 
                  bottom_left: Optional[Point]=None, 
                  top_right: Optional[Point]=None) -> list[set[int]]:
    " return list of planets in max_dist distance of each other "
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
    mapshape = settings['mapshape']
    mapwidth = settings['mapwidth']
    mapheight = settings['mapheight']
    if mapshape != 1:
        return None, None
    true_width = mapwidth + magic_padding
    true_height = mapheight + magic_padding
    bottom_left = true_width + magic_offset, true_height + magic_offset
    top_right = bottom_left[0] + true_width, bottom_left[1] + true_height
    return bottom_left, top_right
    
    