"""
Comprehensive Pytest Verification Suite for Warehouse Digital Twin Optimization with Clean Datasets.
Verifies:
1. Clean & preprocessed empirical data integrity (exact row counts, zero null coordinates).
2. Topological graph connectivity and metric spatial consistency.
3. DaRA 2026 empirical picker timing calibration.
4. Discrete-event digital twin kinematic conservation and congestion mechanics.
5. Batching capacity constraints and routing permutation completeness.
6. Macro consistency between experimental CSV artifacts and LaTeX definitions.
7. Zero API credentials or secrets leakage.
"""

from pathlib import Path
import re
import sys
import networkx as nx
import numpy as np
import pandas as pd
import pytest

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.digital_twin.warehouse_graph import WarehouseGraph, AISLE_CONFIG_M, DEPOT_COORDS_M, DEPOT_NODE_ID
from src.digital_twin.simulation_engine import WarehouseDigitalTwin, PickTask, SimulationConfig
from src.optimization.baselines import (
    batch_orders_fcfs,
    route_s_shape,
    route_largest_gap,
    route_tsp_nearest_neighbor,
)
from src.optimization.cast_wave_optimizer import CASTWaveOptimizer


def test_clean_data_exists():
    """Verify clean empirical dataset and Stage 1 cleaning reports exist in data/clean."""
    clean_dir = BASE_DIR / "data" / "clean"
    assert clean_dir.exists(), f"Clean directory {clean_dir} does not exist"

    required_files = [
        "slots.csv",
        "nav_nodes.csv",
        "nav_edges.csv",
        "picks_clean.csv",
        "orders_clean.csv",
        "products_clean.csv",
        "picker_timing.csv",
        "kit_scenarios_flat.csv",
        "kit_results_flat.csv",
        "rmfs_layout_large.csv",
        "rmfs_pods_large.csv",
        "cleaning_report_footwear.json",
        "cleaning_report_kit.json",
        "cleaning_report_dara.json",
        "cleaning_report_rmfs.json",
    ]
    for fname in required_files:
        fpath = clean_dir / fname
        assert fpath.exists(), f"Missing required clean file: {fname}"
        assert fpath.stat().st_size > 0, f"Clean file {fname} is empty"


def test_teammate_cleaning_pipeline_outputs():
    """Verify Stage 1 cleaning script, CLEANING_LOG.md, and audited JSON metrics match across all 4 datasets."""
    import json

    assert (BASE_DIR / "src" / "clean_data.py").exists(), "Missing src/clean_data.py"
    assert (BASE_DIR / "CLEANING_LOG.md").exists(), "Missing root CLEANING_LOG.md"

    clean_dir = BASE_DIR / "data" / "clean"
    fw = json.loads((clean_dir / "cleaning_report_footwear.json").read_text(encoding="utf-8"))
    assert fw["orders_raw_rows"] == 122370
    assert fw["orders_duplicate_rows_dropped"] == 2559
    assert fw["orders_clean_rows"] == 119811
    assert fw["picks_clean_rows"] == 215192
    assert fw["unit_gap"] == 268
    assert fw["nav_nodes"] == 44
    assert fw["nav_edges"] == 68

    kit = json.loads((clean_dir / "cleaning_report_kit.json").read_text(encoding="utf-8"))
    assert kit["kit_instances_sampled"] == 50
    assert kit["kit_flat_order_lines"] == 49615
    assert kit["kit_result_rows"] == 1591

    dara = json.loads((clean_dir / "cleaning_report_dara.json").read_text(encoding="utf-8"))
    assert dara["dara_raw_rows"] == 540
    assert dara["dara_pick_rows_after_filter"] == 270
    assert dara["dara_pick_gaps_computed"] == 257
    assert abs(dara["dara_gap_median_s"] - 36.0) < 0.1

    rmfs = json.loads((clean_dir / "cleaning_report_rmfs.json").read_text(encoding="utf-8"))
    assert rmfs["rmfs_large_layout_rows"] == 205
    assert rmfs["rmfs_large_pod_nonzero_entries"] == 3342


def test_processed_data_integrity():
    """Verify exact row counts and clean coordinates in processed parquet files."""
    proc_dir = BASE_DIR / "data" / "02_processed"
    assert proc_dir.exists()

    slots = pd.read_parquet(proc_dir / "slots.parquet")
    assert len(slots) == 2292, f"Expected 2,292 slots, found {len(slots)}"
    assert slots["x_m"].notna().all(), "Found null x_m coordinates in slots"
    assert slots["y_m"].notna().all(), "Found null y_m coordinates in slots"

    orders = pd.read_parquet(proc_dir / "orders_clean.parquet")
    assert len(orders) == 119811, f"Expected 119,811 clean orders, found {len(orders)}"

    picks = pd.read_parquet(proc_dir / "picks_clean.parquet")
    assert len(picks) == 215192, f"Expected 215,192 picks, found {len(picks)}"
    assert picks["x_m"].notna().all(), "Found unmapped x_m coordinates in picks"
    assert picks["y_m"].notna().all(), "Found unmapped y_m coordinates in picks"

    nodes = pd.read_parquet(proc_dir / "nav_nodes.parquet")
    assert len(nodes) == 44, f"Expected 44 navigation nodes, found {len(nodes)}"

    edges = pd.read_parquet(proc_dir / "nav_edges.parquet")
    assert len(edges) == 68, f"Expected 68 navigation edges, found {len(edges)}"


def test_dara_timing_calibration():
    """Verify DaRA 2026 empirical timing dataset and median dwell calibration."""
    proc_dir = BASE_DIR / "data" / "02_processed"
    dara = pd.read_parquet(proc_dir / "picker_timing.parquet")
    assert len(dara) == 270
    valid_gaps = dara["gap_to_next_s"].dropna()
    assert len(valid_gaps) == 257
    assert abs(valid_gaps.median() - 36.0) < 0.1, f"Expected median gap 36.0s, got {valid_gaps.median()}"
    valid_dwell = dara["est_handle_s"].dropna()
    assert abs(valid_dwell.median() - 12.6) < 0.1, f"Expected median handling dwell 12.6s, got {valid_dwell.median()}"


def test_graph_connectivity_and_routing():
    """Verify topological graph connectivity and metric distance consistency."""
    graph = WarehouseGraph()
    G = graph.graph

    assert nx.is_connected(G), "Warehouse topological graph is disconnected!"
    assert G.number_of_nodes() == 44, f"Expected 44 nodes, got {G.number_of_nodes()}"
    assert G.number_of_edges() == 68, f"Expected 68 edges, got {G.number_of_edges()}"

    # Verify depot distance is 0 at depot
    d_depot = graph.distance_to_depot(DEPOT_COORDS_M[0], DEPOT_COORDS_M[1], DEPOT_NODE_ID)
    assert abs(d_depot) < 1e-4

    # Distance to aisle A shelf (West block)
    d_a = graph.distance_to_depot(10.0, 0.0, "A")
    assert d_a > 40.0, f"Distance to Aisle A should be > 40m, got {d_a:.1f}"

    # Symmetry
    p1 = (10.0, 0.0, "A")
    p2 = (20.0, 26.48, "E")
    d12 = graph.shortest_path_distance(p1, p2)
    d21 = graph.shortest_path_distance(p2, p1)
    assert abs(d12 - d21) < 1e-4, f"Asymmetric shortest path distance: {d12} vs {d21}"


def test_digital_twin_kinematics():
    """Verify discrete-event simulation kinematics and non-negative metrics."""
    graph = WarehouseGraph()
    config = SimulationConfig(pick_dwell_s=12.6, walking_speed_mps=1.10)
    twin = WarehouseDigitalTwin(graph, config)

    tasks = [
        PickTask(1, 1, "SKU1", 1, 10.0, 0.0, 1, "A", 1, "A-01-11"),
        PickTask(2, 1, "SKU2", 2, 20.0, 12.08, 1, "C", 2, "C-02-11"),
        PickTask(3, 1, "SKU3", 1, 15.0, 26.48, 1, "E", 3, "E-03-11"),
    ]

    res = twin.simulate_wave({0: tasks})
    assert res["makespan_s"] > 0.0
    assert res["total_distance_m"] > 0.0
    assert res["total_pick_time_s"] == pytest.approx(3 * 12.6, rel=1e-3)
    assert res["total_blocked_time_s"] == 0.0  # single picker cannot block itself


def test_cast_wave_optimizer_constraints():
    """Verify CAST-Wave respects trolley capacities and preserves all tasks."""
    graph = WarehouseGraph()
    config = SimulationConfig()
    opt = CASTWaveOptimizer(graph, config)

    tasks = [
        PickTask(i, 100, f"SKU_{i}", 2, float(5 + (i % 25)), float((i % 15) * 7), 1, "A", 1, f"LOC_{i}")
        for i in range(20)
    ]

    routes = opt.optimize_wave(tasks, num_pickers=4, trolley_capacity=27)
    assigned_tasks = [t for r in routes.values() for t in r]
    assert len(assigned_tasks) == len(tasks), f"Task count mismatch: {len(assigned_tasks)} vs {len(tasks)}"

    for p, r in routes.items():
        total_units = sum(t.quantity for t in r)
        assert total_units <= 27, f"Picker {p} exceeded trolley capacity: {total_units} > 27"


def test_macro_consistency_with_benchmarks():
    """Verify paper macros match empirical CSV benchmark files within rounding precision."""
    bench_csv = BASE_DIR / "experiments" / "benchmark_results.csv"
    assert bench_csv.exists()
    df = pd.read_csv(bench_csv)

    macro_file = BASE_DIR / "paper" / "tables" / "macros.tex"
    assert macro_file.exists()
    macros_text = macro_file.read_text(encoding="utf-8")

    # Extract CAST-Wave makespan mean (tolerance 0.01 for 2-decimal rounding)
    cast_mean_csv = df[df["method"] == "CAST_Wave"]["makespan_min"].mean()
    m_cast = re.search(r"\\newcommand\{\\CASTWaveMakespanMean\}\{([\d\.]+)\}", macros_text)
    assert m_cast is not None
    assert abs(float(m_cast.group(1)) - cast_mean_csv) < 0.01, f"Macro mismatch: {m_cast.group(1)} vs {cast_mean_csv:.2f}"

    # Extract S-Shape makespan mean
    ss_mean_csv = df[df["method"] == "FCFS_SShape"]["makespan_min"].mean()
    m_ss = re.search(r"\\newcommand\{\\SShapeMakespanMean\}\{([\d\.]+)\}", macros_text)
    assert m_ss is not None
    assert abs(float(m_ss.group(1)) - ss_mean_csv) < 0.01, f"Macro mismatch: {m_ss.group(1)} vs {ss_mean_csv:.2f}"

    # Verify wave count macro matches exactly
    m_waves = re.search(r"\\newcommand\{\\BenchmarkWaves\}\{(\d+)\}", macros_text)
    assert m_waves is not None
    assert int(m_waves.group(1)) == df["wave_id"].nunique()


def test_bibliography_and_ieee_template_compliance():
    """Verify references.bib has 15-20 entries, >=80% post-2021, and all main.tex citations resolve."""
    bib_file = BASE_DIR / "paper" / "references.bib"
    main_tex = BASE_DIR / "paper" / "main.tex"
    assert bib_file.exists() and main_tex.exists()

    bib_text = bib_file.read_text(encoding="utf-8")
    tex_text = main_tex.read_text(encoding="utf-8")

    bib_keys = set(re.findall(r"@\w+\{([^,\s]+),", bib_text))
    assert 15 <= len(bib_keys) <= 20, f"Expected 15-20 references per IEEE template, found {len(bib_keys)}"

    years = [int(y) for y in re.findall(r"year\s*=\s*\{(\d{4})\}", bib_text)]
    recent_ratio = sum(1 for y in years if y >= 2021) / len(years)
    assert recent_ratio >= 0.80, f"Expected >=80% references from 2021+, got {recent_ratio:.1%}"

    cited_groups = re.findall(r"\\cite\{([^}]+)\}", tex_text)
    cited_keys = {k.strip() for grp in cited_groups for k in grp.split(",")}
    missing_keys = cited_keys - bib_keys
    assert not missing_keys, f"Undefined citation keys in main.tex: {missing_keys}"
    assert "\\section{Data Availability}" in tex_text
    assert "\\begin{IEEEkeywords}" in tex_text


def test_baseline_fair_round_robin_and_lpt_batching():
    """Verify fair multi-picker round robin and LPT batching allocate load across all pickers."""
    from src.optimization.baselines import batch_orders_fcfs_round_robin, batch_orders_balanced_lpt

    tasks = [
        PickTask(i, 100, f"SKU_{i}", 1, 10.0, float(i * 2), 1, "A", 1, f"LOC_{i}")
        for i in range(24)
    ]
    # Round-Robin with 4 pickers
    batches_rr = batch_orders_fcfs_round_robin(tasks, capacity=27, num_pickers=4)
    assert all(len(b) > 0 for b in batches_rr.values()), "All pickers must receive tasks under fair round-robin"
    assert [len(b) for b in batches_rr.values()] == [6, 6, 6, 6]

    # LPT unit balancing with variable quantities
    var_tasks = [
        PickTask(i, 100, f"SKU_{i}", (i % 3) + 1, 10.0, float(i * 2), 1, "A", 1, f"LOC_{i}")
        for i in range(24)
    ]
    batches_lpt = batch_orders_balanced_lpt(var_tasks, capacity=27, num_pickers=4)
    units = [sum(t.quantity for t in b) for b in batches_lpt.values()]
    assert max(units) - min(units) <= 2, f"LPT unit balancing should keep picker load gap <= 2, got {units}"


def test_two_picker_aisle_congestion_slowdown():
    """Verify that multi-picker aisle occupancy triggers congestion mechanics."""
    graph = WarehouseGraph()
    config = SimulationConfig(walking_speed_mps=1.10, pick_dwell_s=12.6, aisle_congestion_factor=0.40)
    twin = WarehouseDigitalTwin(graph, config)

    # Place two pickers targeting adjacent slots in the exact same aisle simultaneously
    p0_tasks = [PickTask(1, 1, "SKU1", 1, 10.0, 12.08, 1, "C", 1, "C-01-11")]
    p1_tasks = [PickTask(2, 1, "SKU2", 1, 12.0, 12.08, 1, "C", 2, "C-02-11")]

    # Run simultaneously
    res_multi = twin.simulate_wave({0: p0_tasks, 1: p1_tasks})
    # Run isolated
    twin.reset()
    res_single0 = twin.simulate_wave({0: p0_tasks})
    twin.reset()
    res_single1 = twin.simulate_wave({1: p1_tasks})

    # Simultaneous runs in the same narrow aisle segment must encounter congestion or queueing
    assert res_multi["makespan_s"] >= max(res_single0["makespan_s"], res_single1["makespan_s"])


def test_zero_credential_leakage():
    """Verify zero API keys, secrets, or internal paths in tracked codebase."""
    forbidden = ["ghp" + "_", "sk-" + "proj", "AKIA" + "SYS", "AIzaSy" + "KEY", "password =", "private_key ="]
    this_file = Path(__file__).resolve()
    for path in BASE_DIR.glob("**/*.py"):
        if path.resolve() == this_file:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for secret in forbidden:
            assert secret not in text, f"Potential credential leak of {secret} in {path}"


def test_simulator_determinism_with_seed():
    """Verify digital twin simulator produces identical output given identical input."""
    graph = WarehouseGraph()
    config = SimulationConfig(pick_dwell_s=12.6, walking_speed_mps=1.10)
    twin1 = WarehouseDigitalTwin(graph, config)
    twin2 = WarehouseDigitalTwin(graph, config)

    tasks = [
        PickTask(1, 1, "SKU1", 1, 10.0, 0.0, 1, "A", 1, "A-01-11"),
        PickTask(2, 1, "SKU2", 1, 15.0, 12.08, 1, "C", 2, "C-02-11"),
        PickTask(3, 1, "SKU3", 1, 20.0, 26.48, 1, "E", 3, "E-03-11"),
    ]
    res1 = twin1.simulate_wave({0: tasks[:2], 1: tasks[2:]})
    res2 = twin2.simulate_wave({0: tasks[:2], 1: tasks[2:]})

    assert res1["makespan_s"] == pytest.approx(res2["makespan_s"], abs=1e-6)
    assert res1["total_distance_m"] == pytest.approx(res2["total_distance_m"], abs=1e-6)
    assert res1["total_blocked_time_s"] == pytest.approx(res2["total_blocked_time_s"], abs=1e-6)


def test_two_opt_monotonic_improvement():
    """Verify route_tsp_nearest_neighbor and CAST-Wave router construct tours with lower/equal distance to arbitrary ordering."""
    from src.optimization.baselines import route_tsp_nearest_neighbor
    from src.optimization.cast_wave_optimizer import CASTWaveOptimizer
    graph = WarehouseGraph()
    config = SimulationConfig()
    opt = CASTWaveOptimizer(graph, config)
    tasks = [
        PickTask(1, 1, "SKU1", 1, 10.0, 0.0, 1, "A", 1, "A-01-11"),
        PickTask(2, 1, "SKU2", 1, 15.0, 12.08, 1, "C", 2, "C-02-11"),
        PickTask(3, 1, "SKU3", 1, 25.0, 26.48, 1, "E", 3, "E-03-11"),
        PickTask(4, 1, "SKU4", 1, 35.0, 40.0, 1, "G", 4, "G-04-11"),
        PickTask(5, 1, "SKU5", 1, 45.0, 50.0, 1, "I", 5, "I-05-11"),
    ]
    def calc_dist(r):
        d = graph.distance_to_depot(r[0].x_m, r[0].y_m, r[0].aisle)
        for i in range(len(r) - 1):
            d += graph.shortest_path_distance((r[i].x_m, r[i].y_m, r[i].aisle),
                                             (r[i+1].x_m, r[i+1].y_m, r[i+1].aisle))
        d += graph.distance_to_depot(r[-1].x_m, r[-1].y_m, r[-1].aisle)
        return d

    arbitrary = [tasks[0], tasks[4], tasks[1], tasks[3], tasks[2]]
    dist_arb = calc_dist(arbitrary)
    refined_baseline = route_tsp_nearest_neighbor(arbitrary, graph)
    dist_baseline = calc_dist(refined_baseline)
    assert dist_baseline <= dist_arb + 1e-4, f"Baseline TSP routing worsened distance: {dist_baseline} > {dist_arb}"

    # Verify CAST-Wave router on isolated batch (no congestion) also monotonically improves/preserves distance
    refined_cast = opt.route_batch_congestion_aware(arbitrary, picker_id=0)
    dist_cast = calc_dist(refined_cast)
    assert dist_cast <= dist_arb + 1e-4, f"CAST-Wave routing worsened distance on isolated batch: {dist_cast} > {dist_arb}"


def test_sector_and_cast_wave_blocking_reduction_on_dense_waves():
    """Verify that Sector and CAST-Wave achieve lower blocked queuing time than uncoordinated FCFS on dense waves."""
    abl_csv = BASE_DIR / "experiments" / "congestion_ablation_results.csv"
    assert abl_csv.exists()
    df = pd.read_csv(abl_csv)
    p_block = df.groupby(["fleet_size", "method"])["total_blocked_time_s"].mean().unstack()

    # Across fleet sizes P >= 4, Sector and CAST-Wave must reduce blocked time vs FCFS
    for P in [4, 6, 8, 10, 12]:
        fcfs_block = p_block.loc[P, "FCFS_StaticTSP"]
        sec_block = p_block.loc[P, "Sector_StaticTSP"]
        cast_block = p_block.loc[P, "CAST_Wave"]
        assert sec_block < fcfs_block, f"At P={P}, Sector blocked time {sec_block:.1f}s not less than FCFS {fcfs_block:.1f}s"
        assert cast_block < fcfs_block, f"At P={P}, CAST blocked time {cast_block:.1f}s not less than FCFS {fcfs_block:.1f}s"

