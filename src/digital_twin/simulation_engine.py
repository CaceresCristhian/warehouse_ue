"""
Discrete-Event Digital Twin Simulator for Footwear Warehouse Order Fulfillment.
Empirically calibrated using:
- Footwear Warehouse WMS empirical layout & operations (Assis et al., 2025).
- DaRA 2026 empirical picker timing: pick handling dwell time median = 12.6 s (Sensors, 2026).
- Multi-picker kinematics, narrow-aisle capacity limits, and speed degradation penalties.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
import heapq
from typing import Dict, List, Optional, Set, Tuple
import numpy as np

from .warehouse_graph import WarehouseGraph, DEPOT_COORDS_M, DEPOT_NODE_ID


class EventType(Enum):
    START_BATCH = auto()
    ARRIVE_AISLE = auto()
    START_PICK = auto()
    FINISH_PICK = auto()
    EXIT_AISLE = auto()
    RETURN_DEPOT = auto()


@dataclass(order=True)
class SimEvent:
    time: float
    event_type: EventType = field(compare=False)
    picker_id: int = field(compare=False)
    data: dict = field(default_factory=dict, compare=False)


@dataclass
class PickTask:
    task_id: int
    wave_number: int
    reference: str
    quantity: int
    x_m: float
    y_m: float
    z: int
    aisle: str
    bay: int
    location: str


@dataclass
class PickerMetrics:
    picker_id: int
    total_travel_distance_m: float = 0.0
    total_travel_time_s: float = 0.0
    total_pick_time_s: float = 0.0
    total_blocked_time_s: float = 0.0
    congestion_events_count: int = 0
    start_time_s: float = 0.0
    completion_time_s: float = 0.0
    num_picks: int = 0


@dataclass
class SimulationConfig:
    walking_speed_mps: float = 1.10  # 1.10 m/s baseline human walking speed with trolley
    pick_dwell_s: float = 12.6  # Empirically calibrated from DaRA 2026 median handling time (IQR: 9.1s - 20.6s)
    aisle_congestion_factor: float = 0.40  # Speed drops to 40% when aisle is shared
    aisle_max_free_capacity: int = 1  # 1 picker moving freely per aisle segment
    trolley_capacity_units: int = 27  # Footwear warehouse empirical limit


class WarehouseDigitalTwin:
    """Discrete-Event Simulator modeling physical warehouse operations and congestion dynamics."""

    def __init__(self, graph: WarehouseGraph, config: Optional[SimulationConfig] = None):
        self.graph = graph
        self.config = config or SimulationConfig()
        self.reset()

    def reset(self):
        """Reset internal simulator state for a new run."""
        self.current_time: float = 0.0
        self.event_queue: List[SimEvent] = []
        # Track active pickers in aisle segments: segment key -> Set[picker_id]
        # segment key: (aisle, "west" | "east")
        self.aisle_occupancy: Dict[Tuple[str, str], Set[int]] = {}
        self.picker_metrics: Dict[int, PickerMetrics] = {}
        self.picker_positions: Dict[int, Tuple[float, float, str]] = {}
        self.event_history: List[dict] = []

    def _get_aisle_segment(self, aisle: str, x_m: float) -> Tuple[str, str]:
        """Classify which aisle block the metric coordinates fall into."""
        block = "west" if x_m <= 32.24 else "east"
        return (aisle, block)

    def simulate_wave(
        self,
        picker_routes: Dict[int, List[PickTask]],
        picker_speeds: Optional[Dict[int, float]] = None,
    ) -> Dict[str, any]:
        """
        Execute discrete-event simulation of an entire picking wave.
        `picker_routes` maps picker_id -> ordered list of PickTasks.
        """
        self.reset()
        num_pickers = len(picker_routes)
        if num_pickers == 0:
            return {"makespan_s": 0.0, "makespan_min": 0.0, "total_distance_m": 0.0}

        speeds = picker_speeds or {p: self.config.walking_speed_mps for p in picker_routes}

        # Initialize pickers and queue first events
        for p_id, route in picker_routes.items():
            self.picker_metrics[p_id] = PickerMetrics(picker_id=p_id, num_picks=len(route))
            self.picker_positions[p_id] = (DEPOT_COORDS_M[0], DEPOT_COORDS_M[1], DEPOT_NODE_ID)
            if route:
                heapq.heappush(
                    self.event_queue,
                    SimEvent(
                        time=0.0,
                        event_type=EventType.START_BATCH,
                        picker_id=p_id,
                        data={"route": route, "route_idx": 0},
                    ),
                )

        # Event processing loop
        while self.event_queue:
            evt = heapq.heappop(self.event_queue)
            self.current_time = evt.time
            p_id = evt.picker_id
            m = self.picker_metrics[p_id]
            speed = speeds.get(p_id, self.config.walking_speed_mps)

            if evt.event_type == EventType.START_BATCH:
                m.start_time_s = self.current_time
                route = evt.data["route"]
                idx = evt.data["route_idx"]
                first_pick = route[idx]

                # Depart depot towards first pick
                dist_m = self.graph.distance_to_depot(first_pick.x_m, first_pick.y_m, first_pick.aisle)
                seg = self._get_aisle_segment(first_pick.aisle, first_pick.x_m)

                # Check congestion in target aisle
                occupants = self.aisle_occupancy.get(seg, set())
                eff_speed = speed
                if len(occupants) >= self.config.aisle_max_free_capacity:
                    eff_speed *= self.config.aisle_congestion_factor
                    blocked_penalty = (dist_m / eff_speed) - (dist_m / speed)
                    m.total_blocked_time_s += max(0.0, blocked_penalty)
                    m.congestion_events_count += 1

                travel_time = dist_m / eff_speed
                m.total_travel_distance_m += dist_m
                m.total_travel_time_s += travel_time

                # Enter aisle
                self.aisle_occupancy.setdefault(seg, set()).add(p_id)
                self.picker_positions[p_id] = (first_pick.x_m, first_pick.y_m, first_pick.aisle)

                # Schedule reaching pick
                heapq.heappush(
                    self.event_queue,
                    SimEvent(
                        time=self.current_time + travel_time,
                        event_type=EventType.START_PICK,
                        picker_id=p_id,
                        data={"route": route, "route_idx": idx, "segment": seg},
                    ),
                )

            elif evt.event_type == EventType.START_PICK:
                route = evt.data["route"]
                idx = evt.data["route_idx"]
                seg = evt.data["segment"]

                # Physical pick dwell time (calibrated to DaRA 12.6s)
                dwell = self.config.pick_dwell_s
                m.total_pick_time_s += dwell

                # Schedule finish pick
                heapq.heappush(
                    self.event_queue,
                    SimEvent(
                        time=self.current_time + dwell,
                        event_type=EventType.FINISH_PICK,
                        picker_id=p_id,
                        data={"route": route, "route_idx": idx, "segment": seg},
                    ),
                )

            elif evt.event_type == EventType.FINISH_PICK:
                route = evt.data["route"]
                idx = evt.data["route_idx"]
                prev_seg = evt.data["segment"]
                curr_pick = route[idx]

                next_idx = idx + 1
                if next_idx < len(route):
                    next_pick = route[next_idx]
                    next_seg = self._get_aisle_segment(next_pick.aisle, next_pick.x_m)

                    # Compute travel distance between picks
                    dist_m = self.graph.shortest_path_distance(
                        (curr_pick.x_m, curr_pick.y_m, curr_pick.aisle),
                        (next_pick.x_m, next_pick.y_m, next_pick.aisle),
                    )

                    # If leaving current aisle segment, release occupancy
                    if next_seg != prev_seg:
                        self.aisle_occupancy.get(prev_seg, set()).discard(p_id)
                        self.aisle_occupancy.setdefault(next_seg, set()).add(p_id)

                    # Check congestion in next aisle segment
                    occupants = self.aisle_occupancy.get(next_seg, set())
                    other_occupants = len(occupants - {p_id})
                    eff_speed = speed
                    if other_occupants >= self.config.aisle_max_free_capacity:
                        eff_speed *= self.config.aisle_congestion_factor
                        penalty = (dist_m / eff_speed) - (dist_m / speed)
                        m.total_blocked_time_s += max(0.0, penalty)
                        m.congestion_events_count += 1

                    travel_time = dist_m / eff_speed
                    m.total_travel_distance_m += dist_m
                    m.total_travel_time_s += travel_time
                    self.picker_positions[p_id] = (next_pick.x_m, next_pick.y_m, next_pick.aisle)

                    heapq.heappush(
                        self.event_queue,
                        SimEvent(
                            time=self.current_time + travel_time,
                            event_type=EventType.START_PICK,
                            picker_id=p_id,
                            data={"route": route, "route_idx": next_idx, "segment": next_seg},
                        ),
                    )
                else:
                    # Route completed; release aisle and return to depot
                    self.aisle_occupancy.get(prev_seg, set()).discard(p_id)
                    dist_m = self.graph.distance_to_depot(curr_pick.x_m, curr_pick.y_m, curr_pick.aisle)
                    travel_time = dist_m / speed
                    m.total_travel_distance_m += dist_m
                    m.total_travel_time_s += travel_time
                    self.picker_positions[p_id] = (DEPOT_COORDS_M[0], DEPOT_COORDS_M[1], DEPOT_NODE_ID)

                    heapq.heappush(
                        self.event_queue,
                        SimEvent(
                            time=self.current_time + travel_time,
                            event_type=EventType.RETURN_DEPOT,
                            picker_id=p_id,
                            data={},
                        ),
                    )

            elif evt.event_type == EventType.RETURN_DEPOT:
                m.completion_time_s = self.current_time

        # Compile comprehensive wave metrics
        makespan_s = max(m.completion_time_s for m in self.picker_metrics.values())
        tot_dist_m = sum(m.total_travel_distance_m for m in self.picker_metrics.values())
        tot_block_s = sum(m.total_blocked_time_s for m in self.picker_metrics.values())
        tot_picks = sum(m.num_picks for m in self.picker_metrics.values())
        tot_travel_s = sum(m.total_travel_time_s for m in self.picker_metrics.values())
        tot_pick_s = sum(m.total_pick_time_s for m in self.picker_metrics.values())
        num_congestions = sum(m.congestion_events_count for m in self.picker_metrics.values())

        # Workload balance: coefficient of variation of completion times
        durations = [m.completion_time_s - m.start_time_s for m in self.picker_metrics.values()]
        workload_cv = float(np.std(durations) / (np.mean(durations) + 1e-6)) if durations else 0.0

        return {
            "makespan_s": float(makespan_s),
            "makespan_min": float(makespan_s / 60.0),
            "total_distance_m": float(tot_dist_m),
            "total_distance_km": float(tot_dist_m / 1000.0),
            "total_blocked_time_s": float(tot_block_s),
            "total_travel_time_s": float(tot_travel_s),
            "total_pick_time_s": float(tot_pick_s),
            "congestion_events_count": int(num_congestions),
            "workload_cv": float(workload_cv),
            "num_picks": int(tot_picks),
            "num_pickers": int(num_pickers),
            "picker_metrics": self.picker_metrics,
        }
