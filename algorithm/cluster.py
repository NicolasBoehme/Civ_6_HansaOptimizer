"""Phase 2 — cluster formation.

Two cities interact iff their centers are within hex distance 6 (the maximum
distance at which a district of one and a district of the other can be
adjacent: 3 + 3 = 6). Connected components of that graph are clusters.
"""
from typing import List

from .hex import distance
from .model import City, Cluster

INTERACTION_RADIUS = 6


def build_clusters(cities: List[City]) -> List[Cluster]:
    n = len(cities)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if distance(cities[i].coords, cities[j].coords) <= INTERACTION_RADIUS:
                union(i, j)

    groups: dict[int, List[City]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(cities[i])
    return [Cluster(cities=g) for g in groups.values()]
