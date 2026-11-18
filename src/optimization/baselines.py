"""
Baseline Order Batching and Picker Routing Heuristics:
1. FCFS Batching + S-Shape Routing (Hall, 1993; Roodbergen & de Koster, 2001)
2. FCFS Batching + Largest-Gap Routing (Hall, 1993)
3. Capacity-Constrained Greedy Batching + Static TSP Routing (2-Opt / Nearest-Neighbor)
"""

from typing import Dict, List, Tuple
import numpy as np

from ..digital_twin.warehouse_graph import WarehouseGraph, AISLE_CONFIG_M, DEPOT_COORDS_M
from ..digital_twin.simulation_engine import PickTask


def batch_orders_fcfs(
    tasks: List[PickTask],
    capacity: int = 27,
    num_pickers: int = 4,
    fair_round_robin: bool = False,
) -> Dict[int, List[PickTask]]:
    """
    Batch tasks in First-Come-First-Served order into picker routes.
    If fair_round_robin=True, distributes incoming tasks round-robin across all pickers.
    If fair_round_robin=False, uses legacy sequential trolley filling.
    """
    if fair_round_robin:
        return batch_orders_fcfs_round_robin(tasks, capacity=capacity, num_pickers=num_pickers)

    batches: Dict[int, List[PickTask]] = {p: [] for p in range(num_pickers)}
    picker_units = {p: 0 for p in range(num_pickers)}

    curr_p = 0
    for task in tasks:
        if picker_units[curr_p] + task.quantity <= capacity:
            batches[curr_p].append(task)
            picker_units[curr_p] += task.quantity
        else:
            allocated = False
            for p in range(num_pickers):
                if picker_units[p] + task.quantity <= capacity:
                    batches[p].append(task)
                    picker_units[p] += task.quantity
                    curr_p = p
                    allocated = True
                    break
            if not allocated:
                batches[curr_p].append(task)
                picker_units[curr_p] += task.quantity
                curr_p = (curr_p + 1) % num_pickers

    return batches


def batch_orders_fcfs_round_robin(
    tasks: List[PickTask],
    capacity: int = 27,
    num_pickers: int = 4,
) -> Dict[int, List[PickTask]]:
    """
    Fair Multi-Picker FCFS Batching:
    Distributes tasks in First-Come-First-Served order round-robin across all active pickers,
    respecting individual trolley capacity constraints.
    """
    batches: Dict[int, List[PickTask]] = {p: [] for p in range(num_pickers)}
    picker_units = {p: 0 for p in range(num_pickers)}

    curr_p = 0
    for task in tasks:
        allocated = False
        for offset in range(num_pickers):
            p = (curr_p + offset) % num_pickers
            if picker_units[p] + task.quantity <= capacity:
                batches[p].append(task)
                picker_units[p] += task.quantity
                curr_p = (p + 1) % num_pickers
                allocated = True
                break
        if not allocated:
            least_p = min(range(num_pickers), key=lambda p: picker_units[p])
            batches[least_p].append(task)
            picker_units[least_p] += task.quantity
            curr_p = (least_p + 1) % num_pickers

    return batches


def batch_orders_balanced_lpt(
    tasks: List[PickTask],
    capacity: int = 27,
    num_pickers: int = 4,
) -> Dict[int, List[PickTask]]:
    """
    Longest-Processing-Time (LPT) Unit-Balancing Batching:
    Greedily assigns tasks sorted by units descending to the least-loaded picker,
    achieving balanced cart volume across operators.
    """
    batches: Dict[int, List[PickTask]] = {p: [] for p in range(num_pickers)}
    picker_units = {p: 0 for p in range(num_pickers)}

    sorted_tasks = sorted(tasks, key=lambda t: t.quantity, reverse=True)
    for task in sorted_tasks:
        candidates = [p for p in range(num_pickers) if picker_units[p] + task.quantity <= capacity]
        best_p = min(candidates, key=lambda p: picker_units[p]) if candidates else min(range(num_pickers), key=lambda p: picker_units[p])
        batches[best_p].append(task)
        picker_units[best_p] += task.quantity

    return batches


def route_s_shape(tasks: List[PickTask], graph: WarehouseGraph) -> List[PickTask]:
    """
    S-Shape (Traversal) heuristic:
    Traverse visited aisles completely from one cross-aisle to the other,
    alternating direction between consecutive aisles.
    """
    if not tasks:
        return []

    # Group tasks by (aisle, block)
    aisle_groups: Dict[Tuple[str, str], List[PickTask]] = {}
    for task in tasks:
        block = "west" if task.x_m <= 32.24 else "east"
        aisle_groups.setdefault((task.aisle, block), []).append(task)

    # Sort aisle groups by physical row y_m
    sorted_keys = sorted(
        aisle_groups.keys(),
        key=lambda k: (AISLE_CONFIG_M.get(k[0], {}).get("row", 99), 0 if k[1] == "west" else 1),
    )

    ordered_route: List[PickTask] = []
    forward = True  # West to East vs East to West
    for key in sorted_keys:
        group = aisle_groups[key]
        group_sorted = sorted(group, key=lambda t: t.x_m, reverse=not forward)
        ordered_route.extend(group_sorted)
        forward = not forward

    return ordered_route


def route_largest_gap(tasks: List[PickTask], graph: WarehouseGraph) -> List[PickTask]:
    """
    Largest-Gap heuristic:
    In each visited aisle, enter from both ends and return,
    leaving the largest gap between picks unvisited.
    """
    if not tasks:
        return []

    aisle_groups: Dict[Tuple[str, str], List[PickTask]] = {}
    for task in tasks:
        block = "west" if task.x_m <= 32.24 else "east"
        aisle_groups.setdefault((task.aisle, block), []).append(task)

    sorted_keys = sorted(
        aisle_groups.keys(),
        key=lambda k: (AISLE_CONFIG_M.get(k[0], {}).get("row", 99), 0 if k[1] == "west" else 1),
    )

    ordered_route: List[PickTask] = []
    for key in sorted_keys:
        group = aisle_groups[key]
        if len(group) <= 2:
            ordered_route.extend(sorted(group, key=lambda t: t.x_m))
            continue

        # Sort positions along aisle
        pos_sorted = sorted(group, key=lambda t: t.x_m)
        aisle_min_x = 5.28 if key[1] == "west" else 32.24
        aisle_max_x = 32.24 if key[1] == "west" else 54.88

        # Calculate gaps
        gaps = []
        gaps.append((pos_sorted[0].x_m - aisle_min_x, 0))
        for i in range(len(pos_sorted) - 1):
            gaps.append((pos_sorted[i + 1].x_m - pos_sorted[i].x_m, i + 1))
        gaps.append((aisle_max_x - pos_sorted[-1].x_m, len(pos_sorted)))

        max_gap_idx = max(range(len(gaps)), key=lambda i: gaps[i][0])
        left_picks = pos_sorted[:max_gap_idx]
        right_picks = pos_sorted[max_gap_idx:]

        ordered_route.extend(left_picks)
        ordered_route.extend(reversed(right_picks))

    return ordered_route


def route_tsp_nearest_neighbor(tasks: List[PickTask], graph: WarehouseGraph) -> List[PickTask]:
    """
    Traveling Salesperson Problem (TSP) solver using Nearest-Neighbor heuristic
    followed by 2-Opt local search improvement on metric graph distances.
    """
    if len(tasks) <= 2:
        return list(tasks)

    # Nearest Neighbor from Depot
    unvisited = list(tasks)
    route: List[PickTask] = []

    # Start nearest to depot
    curr_idx = min(
        range(len(unvisited)),
        key=lambda i: graph.distance_to_depot(unvisited[i].x_m, unvisited[i].y_m, unvisited[i].aisle),
    )
    route.append(unvisited.pop(curr_idx))

    while unvisited:
        last = route[-1]
        next_idx = min(
            range(len(unvisited)),
            key=lambda i: graph.shortest_path_distance(
                (last.x_m, last.y_m, last.aisle),
                (unvisited[i].x_m, unvisited[i].y_m, unvisited[i].aisle),
            ),
        )
        route.append(unvisited.pop(next_idx))

    # 2-Opt local search refinement (max 30 iterations for speed)
    improved = True
    iterations = 0
    max_iter = min(30, len(route) * 2)

    def route_distance(r: List[PickTask]) -> float:
        if not r:
            return 0.0
        d = graph.distance_to_depot(r[0].x_m, r[0].y_m, r[0].aisle)
        for i in range(len(r) - 1):
            d += graph.shortest_path_distance(
                (r[i].x_m, r[i].y_m, r[i].aisle),
                (r[i + 1].x_m, r[i + 1].y_m, r[i + 1].aisle),
            )
        d += graph.distance_to_depot(r[-1].x_m, r[-1].y_m, r[-1].aisle)
        return d

    best_dist = route_distance(route)
    n = len(route)
    while improved and iterations < max_iter:
        improved = False
        iterations += 1
        for i in range(n - 1):
            for j in range(i + 2, n):
                new_route = route[:i] + route[i:j][::-1] + route[j:]
                new_dist = route_distance(new_route)
                if new_dist < best_dist - 1e-4:
                    route = new_route
                    best_dist = new_dist
                    improved = True
                    break
            if improved:
                break

    return route
