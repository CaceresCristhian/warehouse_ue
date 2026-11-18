"""
CAST-Wave: Congestion-Aware Spatio-Temporal Order Batching and Wave Scheduler.

Novel features:
1. Spatial Sector Clustering (Aisle-Zone Decomposition):
   Clusters orders into spatially cohesive batches to minimize warehouse footprint per tour.
2. Staggered Spatio-Temporal Dispatching:
   Assigns disjoint spatial sectors to concurrent pickers to eliminate narrow-aisle conflicts.
3. Congestion-Penalized Dynamic Routing:
   Sequences picks by balancing travel distance against predicted narrow-aisle occupancy collisions.
4. Dynamic Workload Equalization:
   Balances item count and estimated travel duration across operators to minimize wave makespan.
"""

from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from ..digital_twin.warehouse_graph import WarehouseGraph, DEPOT_COORDS_M, DEPOT_NODE_ID
from ..digital_twin.simulation_engine import PickTask, SimulationConfig


class CASTWaveOptimizer:
    """Proposed Congestion-Aware Spatio-Temporal Batching & Routing Engine."""

    def __init__(self, graph: WarehouseGraph, config: Optional[SimulationConfig] = None):
        self.graph = graph
        self.config = config or SimulationConfig()

    def get_spatial_sector(self, task: PickTask) -> int:
        """
        Partition warehouse layout into 5 distinct topological sectors (in meters):
        0: West South (Aisles A-D, y_m <= 21.6 m)
        1: West Mid (Aisles E-G, 21.6 m < y_m <= 42.4 m)
        2: West North (Aisles H-R, x_m <= 32.24 m, y_m > 42.4 m)
        3: East Mid (Aisles H-L, x_m > 32.24 m, y_m <= 76.0 m)
        4: East North (Aisles M-Q, x_m > 32.24 m, y_m > 76.0 m)
        """
        x_m, y_m = task.x_m, task.y_m
        if x_m <= 32.24:
            if y_m <= 21.6:
                return 0
            elif y_m <= 42.4:
                return 1
            else:
                return 2
        else:
            if y_m <= 76.0:
                return 3
            else:
                return 4

    def batch_orders(
        self,
        tasks: List[PickTask],
        num_pickers: int = 4,
        capacity: int = 27,
    ) -> Dict[int, List[PickTask]]:
        """
        Spatially cluster tasks into capacity-constrained picker batches
        to maximize sector disjointness across operators.
        """
        if not tasks:
            return {p: [] for p in range(num_pickers)}

        # Group tasks by primary spatial sector
        sector_buckets: Dict[int, List[PickTask]] = {s: [] for s in range(5)}
        for t in tasks:
            sec = self.get_spatial_sector(t)
            sector_buckets[sec].append(t)

        # Sort tasks within each sector by proximity to depot
        for sec in sector_buckets:
            sector_buckets[sec].sort(
                key=lambda t: self.graph.distance_to_depot(t.x_m, t.y_m, t.aisle)
            )

        # Assign sectors to pickers in a balanced, spatially separated manner
        batches: Dict[int, List[PickTask]] = {p: [] for p in range(num_pickers)}
        picker_units = {p: 0 for p in range(num_pickers)}
        picker_sectors: Dict[int, Set[int]] = {p: set() for p in range(num_pickers)}

        total_units = sum(t.quantity for t in tasks)
        target_units_per_picker = max(1, int(np.ceil(total_units / num_pickers)))

        # Iterate through sectors and allocate to pickers with lowest current load
        for sec, sec_tasks in sector_buckets.items():
            for task in sec_tasks:
                under_target = [
                    p for p in range(num_pickers)
                    if picker_units[p] < target_units_per_picker and picker_units[p] + task.quantity <= capacity
                ]
                if under_target:
                    best_p = min(
                        under_target,
                        key=lambda p: (
                            0 if sec in picker_sectors[p] else 1,
                            picker_units[p],
                        ),
                    )
                else:
                    candidates = [
                        p for p in range(num_pickers)
                        if picker_units[p] + task.quantity <= capacity
                    ]
                    if candidates:
                        best_p = min(
                            candidates,
                            key=lambda p: (
                                picker_units[p],
                                0 if sec in picker_sectors[p] else 1,
                            ),
                        )
                    else:
                        best_p = min(range(num_pickers), key=lambda p: picker_units[p])

                batches[best_p].append(task)
                picker_units[best_p] += task.quantity
                picker_sectors[best_p].add(sec)

        return batches

    def route_batch_congestion_aware(
        self,
        tasks: List[PickTask],
        picker_id: int,
        occupied_aisles_timeline: Optional[Dict[Tuple[str, str], List[Tuple[float, float]]]] = None,
    ) -> List[PickTask]:
        """
        Sequence picks within a batch using dynamic congestion-penalized Nearest Neighbor.
        If another picker is active in an aisle segment at estimated arrival time, detour/delay penalty is applied.
        """
        if len(tasks) <= 1:
            return list(tasks)

        unvisited = list(tasks)
        route: List[PickTask] = []
        curr_pos = (DEPOT_COORDS_M[0], DEPOT_COORDS_M[1], DEPOT_NODE_ID)
        est_current_time = 0.0

        # Calibrated metric distance penalty: corresponds to ~12-15s yielding delay in 40% slowdown
        congestion_penalty_meters = 15.0

        while unvisited:
            best_idx = 0
            best_cost = float("inf")

            for i, t in enumerate(unvisited):
                dist = self.graph.distance_to_depot(t.x_m, t.y_m, t.aisle) if curr_pos[2] == DEPOT_NODE_ID else self.graph.shortest_path_distance(curr_pos, (t.x_m, t.y_m, t.aisle))
                est_arrival = est_current_time + (dist / self.config.walking_speed_mps)

                # Congestion penalty if aisle segment is occupied during estimated arrival window
                penalty = 0.0
                if occupied_aisles_timeline:
                    seg = (t.aisle, "west" if t.x_m <= 32.24 else "east")
                    occ_windows = occupied_aisles_timeline.get(seg, [])
                    for t_start, t_end in occ_windows:
                        if max(est_arrival, t_start) <= min(est_arrival + self.config.pick_dwell_s, t_end):
                            penalty += congestion_penalty_meters

                total_cost = dist + penalty
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_idx = i

            chosen = unvisited.pop(best_idx)
            route.append(chosen)

            # Update estimated time
            step_dist = self.graph.distance_to_depot(chosen.x_m, chosen.y_m, chosen.aisle) if curr_pos[2] == DEPOT_NODE_ID else self.graph.shortest_path_distance(curr_pos, (chosen.x_m, chosen.y_m, chosen.aisle))
            est_current_time += (step_dist / self.config.walking_speed_mps) + self.config.pick_dwell_s
            curr_pos = (chosen.x_m, chosen.y_m, chosen.aisle)

        # 2-Opt Local Search Refinement with Congestion Cost Awareness
        if len(route) > 3:
            def route_total_cost(r: List[PickTask]) -> float:
                cost = self.graph.distance_to_depot(r[0].x_m, r[0].y_m, r[0].aisle)
                curr_t = (cost / self.config.walking_speed_mps) + self.config.pick_dwell_s

                # Check initial task aisle occupancy
                if occupied_aisles_timeline:
                    seg0 = (r[0].aisle, "west" if r[0].x_m <= 32.24 else "east")
                    for t_start, t_end in occupied_aisles_timeline.get(seg0, []):
                        if max(curr_t - self.config.pick_dwell_s, t_start) <= min(curr_t, t_end):
                            cost += congestion_penalty_meters

                for k in range(len(r) - 1):
                    d_step = self.graph.shortest_path_distance(
                        (r[k].x_m, r[k].y_m, r[k].aisle),
                        (r[k + 1].x_m, r[k + 1].y_m, r[k + 1].aisle),
                    )
                    arr_t = curr_t + (d_step / self.config.walking_speed_mps)
                    cost += d_step
                    if occupied_aisles_timeline:
                        seg_k = (r[k + 1].aisle, "west" if r[k + 1].x_m <= 32.24 else "east")
                        for t_start, t_end in occupied_aisles_timeline.get(seg_k, []):
                            if max(arr_t, t_start) <= min(arr_t + self.config.pick_dwell_s, t_end):
                                cost += congestion_penalty_meters
                    curr_t = arr_t + self.config.pick_dwell_s

                cost += self.graph.distance_to_depot(r[-1].x_m, r[-1].y_m, r[-1].aisle)
                return cost

            best_cost = route_total_cost(route)
            improved = True
            iterations = 0
            max_iter = min(30, len(route) * 2)
            n = len(route)

            while improved and iterations < max_iter:
                improved = False
                iterations += 1
                for i in range(n - 1):
                    for j in range(i + 2, n):
                        new_route = route[:i] + route[i:j][::-1] + route[j:]
                        new_cost = route_total_cost(new_route)
                        if new_cost < best_cost - 1e-4:
                            route = new_route
                            best_cost = new_cost
                            improved = True
                            break
                    if improved:
                        break

        return route

    def optimize_wave(
        self,
        tasks: List[PickTask],
        num_pickers: int = 4,
        trolley_capacity: int = 27,
    ) -> Dict[int, List[PickTask]]:
        """
        Full CAST-Wave optimization pipeline:
        1. Spatial clustering into disjoint picker batches.
        2. Iterative congestion-aware route sequencing.
        """
        batches = self.batch_orders(tasks, num_pickers=num_pickers, capacity=trolley_capacity)
        final_routes: Dict[int, List[PickTask]] = {}
        occupied_timeline: Dict[Tuple[str, str], List[Tuple[float, float]]] = {}

        # Route pickers sequentially to register predicted occupancy windows
        for p_id in sorted(batches.keys()):
            p_tasks = batches[p_id]
            if not p_tasks:
                final_routes[p_id] = []
                continue

            routed = self.route_batch_congestion_aware(
                p_tasks, picker_id=p_id, occupied_aisles_timeline=occupied_timeline
            )
            final_routes[p_id] = routed

            # Record estimated occupancy windows for subsequent pickers
            t_curr = 0.0
            pos = (DEPOT_COORDS_M[0], DEPOT_COORDS_M[1], DEPOT_NODE_ID)
            for t in routed:
                d = self.graph.distance_to_depot(t.x_m, t.y_m, t.aisle) if pos[2] == DEPOT_NODE_ID else self.graph.shortest_path_distance(pos, (t.x_m, t.y_m, t.aisle))
                t_arr = t_curr + (d / self.config.walking_speed_mps)
                t_dep = t_arr + self.config.pick_dwell_s
                seg = (t.aisle, "west" if t.x_m <= 32.24 else "east")
                occupied_timeline.setdefault(seg, []).append((t_arr, t_dep))
                t_curr = t_dep
                pos = (t.x_m, t.y_m, t.aisle)

        return final_routes
