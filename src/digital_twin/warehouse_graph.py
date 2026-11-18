"""
Warehouse Topological Navigation Graph G = (V, E) for Footwear Manufacturing Facility.
Built from clean empirical navigation data:
- 44 Waypoint Nodes (nav_nodes.parquet): Left Corridor (LC), Center Corridor (CC), Right Corridor (RC).
- 68 Topological Edges (nav_edges.parquet): Metric lengths (length_m) connecting corridors and aisles.
- Central I/O Depot located at CC-08 (x_m = 32.24, y_m = 50.48).
- Metric coordinate system: distances directly in meters.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import networkx as nx
import numpy as np
import pandas as pd

# Central I/O Depot coordinates (meters)
DEPOT_NODE_ID = "CC-08"
DEPOT_COORDS_M = (32.24, 50.48)

# Metric aisle centerline definitions (y_m) and block extents
# West block: x_m in [5.28, 32.24]; East block: x_m in [32.24, 54.88]
AISLE_CONFIG_M = {
    "A": {"y_m": 0.00, "west": True, "east": False, "row": 1},
    "B": {"y_m": 4.88, "west": True, "east": False, "row": 2},
    "C": {"y_m": 12.08, "west": True, "east": False, "row": 3},
    "D": {"y_m": 19.28, "west": True, "east": False, "row": 4},
    "E": {"y_m": 26.48, "west": True, "east": False, "row": 5},
    "F": {"y_m": 33.68, "west": True, "east": False, "row": 6},
    "G": {"y_m": 40.88, "west": True, "east": False, "row": 7},
    "H": {"y_m": 50.48, "west": True, "east": True, "row": 8},
    "I": {"y_m": 50.48, "west": True, "east": True, "row": 8},
    "J": {"y_m": 60.08, "west": True, "east": True, "row": 9},
    "K": {"y_m": 67.28, "west": True, "east": True, "row": 10},
    "L": {"y_m": 74.48, "west": True, "east": True, "row": 11},
    "M": {"y_m": 81.68, "west": True, "east": True, "row": 12},
    "N": {"y_m": 88.88, "west": True, "east": True, "row": 13},
    "O": {"y_m": 96.08, "west": True, "east": True, "row": 14},
    "P": {"y_m": 103.28, "west": True, "east": True, "row": 15},
    "Q": {"y_m": 110.48, "west": True, "east": True, "row": 16},
    "R": {"y_m": 117.68, "west": True, "east": False, "row": 17},
}


class WarehouseGraph:
    """NetworkX topological graph of the footwear warehouse layout."""

    def __init__(
        self,
        nodes_df: Optional[pd.DataFrame] = None,
        edges_df: Optional[pd.DataFrame] = None,
    ):
        self.graph = nx.Graph()
        self.node_coords: Dict[str, Tuple[float, float]] = {}
        self.corridor_nodes: Dict[str, List[str]] = {"LC": [], "CC": [], "RC": []}
        self._load_network(nodes_df, edges_df)
        self._precompute_shortest_paths()

    def _load_network(
        self,
        nodes_df: Optional[pd.DataFrame] = None,
        edges_df: Optional[pd.DataFrame] = None,
    ):
        """Build graph directly from clean navigation nodes and edges."""
        base_dir = Path(__file__).resolve().parents[2]
        proc_dir = base_dir / "data" / "02_processed"

        if nodes_df is None:
            nodes_path = proc_dir / "nav_nodes.parquet"
            if not nodes_path.exists():
                raise FileNotFoundError(f"Navigation nodes not found: {nodes_path}")
            nodes_df = pd.read_parquet(nodes_path)

        if edges_df is None:
            edges_path = proc_dir / "nav_edges.parquet"
            if not edges_path.exists():
                raise FileNotFoundError(f"Navigation edges not found: {edges_path}")
            edges_df = pd.read_parquet(edges_path)

        # Add nodes
        for _, row in nodes_df.iterrows():
            nid = str(row["node_id"])
            xm = float(row["x_m"])
            ym = float(row["y_m"])
            ca = str(row["cross_aisle"])
            is_io = (str(row["is_io_point"]).lower() == "yes")
            self.graph.add_node(
                nid,
                x_m=xm,
                y_m=ym,
                cross_aisle=ca,
                is_io_point=is_io,
            )
            self.node_coords[nid] = (xm, ym)
            if ca in self.corridor_nodes:
                self.corridor_nodes[ca].append(nid)

        # Add edges
        for _, row in edges_df.iterrows():
            u = str(row["from_node"])
            v = str(row["to_node"])
            w = float(row["length_m"])
            aisle_id = str(row["aisle_id"])
            self.graph.add_edge(u, v, weight=w, aisle_id=aisle_id)

    def _precompute_shortest_paths(self):
        """Precompute all-pairs shortest paths across the 44 corridor nodes."""
        self.dist_matrix = dict(nx.all_pairs_dijkstra_path_length(self.graph, weight="weight"))

    def get_aisle_centerline_y(self, aisle: str) -> float:
        """Return metric centerline y_m for a given aisle code."""
        cfg = AISLE_CONFIG_M.get(aisle)
        return cfg["y_m"] if cfg else 50.48

    def _find_nearest_corridor_node(self, corridor: str, y_target: float) -> str:
        """Find the corridor node closest to y_target."""
        nodes = self.corridor_nodes.get(corridor, [])
        if not nodes:
            return f"{corridor}-08"
        best_node = nodes[0]
        best_diff = float("inf")
        for nid in nodes:
            ny = self.node_coords[nid][1]
            diff = abs(ny - y_target)
            if diff < best_diff:
                best_diff = diff
                best_node = nid
        return best_node

    def get_aisle_endpoints(self, aisle: str, x_m: float) -> Tuple[str, str]:
        """Return the (west_node, east_node) corridor endpoints for the aisle segment containing x_m."""
        y_c = self.get_aisle_centerline_y(aisle)
        if x_m <= 32.24:
            # West block: between LC and CC
            lc_node = self._find_nearest_corridor_node("LC", y_c)
            cc_node = self._find_nearest_corridor_node("CC", y_c)
            return lc_node, cc_node
        else:
            # East block: between CC and RC
            cc_node = self._find_nearest_corridor_node("CC", y_c)
            rc_node = self._find_nearest_corridor_node("RC", y_c)
            return cc_node, rc_node

    def shortest_path_distance(
        self,
        p1: Tuple[float, float, str],
        p2: Tuple[float, float, str],
    ) -> float:
        """
        Compute true warehouse metric travel distance (in meters) between two locations.
        Each point is (x_m, y_m, aisle).
        """
        x1, y1, aisle1 = p1
        x2, y2, aisle2 = p2

        # Special case: Depot CC-08
        if aisle1 in ("DEPOT", "CC-08") or (abs(x1 - DEPOT_COORDS_M[0]) < 1e-3 and abs(y1 - DEPOT_COORDS_M[1]) < 1e-3):
            return self.distance_to_depot(x2, y2, aisle2)
        if aisle2 in ("DEPOT", "CC-08") or (abs(x2 - DEPOT_COORDS_M[0]) < 1e-3 and abs(y2 - DEPOT_COORDS_M[1]) < 1e-3):
            return self.distance_to_depot(x1, y1, aisle1)

        # Same aisle and same block (West vs East): direct traversal along aisle
        is_same_block = (x1 <= 32.24 and x2 <= 32.24) or (x1 >= 32.24 and x2 >= 32.24)
        if aisle1 == aisle2 and is_same_block:
            dist_m = abs(x1 - x2) + abs(y1 - self.get_aisle_centerline_y(aisle1)) + abs(y2 - self.get_aisle_centerline_y(aisle2))
            return float(dist_m)

        # Different aisles or blocks: evaluate routing via corridor endpoints
        y_c1 = self.get_aisle_centerline_y(aisle1)
        y_c2 = self.get_aisle_centerline_y(aisle2)

        shelf_dist_1 = abs(y1 - y_c1)
        shelf_dist_2 = abs(y2 - y_c2)

        # Candidate exit corridors for p1
        exits_1 = []
        if x1 <= 32.24:
            lc1 = self._find_nearest_corridor_node("LC", y_c1)
            cc1 = self._find_nearest_corridor_node("CC", y_c1)
            exits_1.append((lc1, abs(x1 - 5.28)))
            exits_1.append((cc1, abs(32.24 - x1)))
        else:
            cc1 = self._find_nearest_corridor_node("CC", y_c1)
            rc1 = self._find_nearest_corridor_node("RC", y_c1)
            exits_1.append((cc1, abs(x1 - 32.24)))
            exits_1.append((rc1, abs(54.88 - x1)))

        # Candidate entry corridors for p2
        entries_2 = []
        if x2 <= 32.24:
            lc2 = self._find_nearest_corridor_node("LC", y_c2)
            cc2 = self._find_nearest_corridor_node("CC", y_c2)
            entries_2.append((lc2, abs(x2 - 5.28)))
            entries_2.append((cc2, abs(32.24 - x2)))
        else:
            cc2 = self._find_nearest_corridor_node("CC", y_c2)
            rc2 = self._find_nearest_corridor_node("RC", y_c2)
            entries_2.append((cc2, abs(x2 - 32.24)))
            entries_2.append((rc2, abs(54.88 - x2)))

        min_total = float("inf")
        for node1, d1 in exits_1:
            for node2, d2 in entries_2:
                corridor_dist = self.dist_matrix.get(node1, {}).get(node2, float("inf"))
                total = shelf_dist_1 + d1 + corridor_dist + d2 + shelf_dist_2
                if total < min_total:
                    min_total = total

        return float(min_total)

    def distance_to_depot(self, x_m: float, y_m: float, aisle: str) -> float:
        """Compute shortest path distance from any position to Central Depot CC-08 (32.24, 50.48)."""
        if aisle in ("DEPOT", "CC-08"):
            return 0.0

        y_c = self.get_aisle_centerline_y(aisle)
        shelf_dist = abs(y_m - y_c)

        candidates = []
        if x_m <= 32.24:
            lc = self._find_nearest_corridor_node("LC", y_c)
            cc = self._find_nearest_corridor_node("CC", y_c)
            candidates.append((lc, abs(x_m - 5.28)))
            candidates.append((cc, abs(32.24 - x_m)))
        else:
            cc = self._find_nearest_corridor_node("CC", y_c)
            rc = self._find_nearest_corridor_node("RC", y_c)
            candidates.append((cc, abs(x_m - 32.24)))
            candidates.append((rc, abs(54.88 - x_m)))

        min_dist = float("inf")
        for node, d in candidates:
            corridor_dist = self.dist_matrix.get(node, {}).get(DEPOT_NODE_ID, float("inf"))
            total = shelf_dist + d + corridor_dist
            if total < min_dist:
                min_dist = total

        return float(min_dist)
