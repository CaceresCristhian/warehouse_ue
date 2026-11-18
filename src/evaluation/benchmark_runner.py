"""
Empirical Benchmark and Stress Testing Runner for Footwear Warehouse Digital Twin.
Executes:
1. Multi-Wave Historical Benchmark across 100 authentic picking waves using clean deduplicated data.
2. Congestion Sensitivity & Ablation Analysis across fleet sizes (P = 2, 4, 6, 8, 10, 12).
3. Rigorous statistical significance testing (paired t-test, Wilcoxon, Cohen's d).
Outputs CSV files to experiments/.
"""

from pathlib import Path
import sys
import time

BASE_DIR = Path(__file__).resolve().parents[2]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import numpy as np
import pandas as pd
from scipy import stats

from src.digital_twin.warehouse_graph import WarehouseGraph
from src.digital_twin.simulation_engine import WarehouseDigitalTwin, PickTask, SimulationConfig
from src.optimization.baselines import (
    batch_orders_fcfs,
    route_s_shape,
    route_largest_gap,
    route_tsp_nearest_neighbor,
)
from src.optimization.cast_wave_optimizer import CASTWaveOptimizer


def load_historical_waves(num_waves: int = 100) -> list[tuple[int, list[PickTask]]]:
    """Load real picking wave records from clean processed parquet."""
    pw_path = BASE_DIR / "data" / "02_processed" / "picks_clean.parquet"
    df = pd.read_parquet(pw_path)

    # Filter waves with at least 15 picks to ensure realistic operational density
    wave_counts = df.groupby("wave_id").size()
    valid_wave_ids = wave_counts[wave_counts >= 15].index.values

    # Deterministic selection of 100 diverse waves
    np.random.seed(42)
    selected_ids = np.random.choice(valid_wave_ids, size=min(num_waves, len(valid_wave_ids)), replace=False)
    selected_ids.sort()

    wave_tasks: list[tuple[int, list[PickTask]]] = []
    for wid in selected_ids:
        sub = df[df["wave_id"] == wid].reset_index(drop=True)
        tasks = [
            PickTask(
                task_id=i,
                wave_number=int(row["wave_id"]),
                reference=str(row["sku"]),
                quantity=int(row["qty"]),
                x_m=float(row["x_m"]),
                y_m=float(row["y_m"]),
                z=int(row["z"]),
                aisle=str(row["aisle"]),
                bay=int(row["row"]),
                location=str(row["location"]),
            )
            for i, row in sub.iterrows()
        ]
        wave_tasks.append((int(wid), tasks))

    print(f"Loaded {len(wave_tasks)} historical waves (mean picks/wave: {np.mean([len(t) for _, t in wave_tasks]):.1f})")
    return wave_tasks


def run_benchmark(num_waves: int = 100, num_pickers: int = 4) -> pd.DataFrame:
    """Run full empirical benchmark on 100 historical waves across 4 methods."""
    print("=" * 60)
    print(f"Executing 100-Wave Benchmark (P = {num_pickers} pickers, DaRA 12.6s dwell)...")
    print("=" * 60)

    graph = WarehouseGraph()
    config = SimulationConfig(pick_dwell_s=12.6, walking_speed_mps=1.10)
    twin = WarehouseDigitalTwin(graph, config)
    optimizer = CASTWaveOptimizer(graph, config)

    wave_data = load_historical_waves(num_waves)
    results = []
    t0 = time.time()

    for idx, (wid, tasks) in enumerate(wave_data, 1):
        if idx % 20 == 0 or idx == len(wave_data):
            print(f"  Processing wave {idx}/{len(wave_data)} (Wave ID: {wid})...")

        # 1. Fair Multi-Picker FCFS + S-Shape
        ts_start = time.perf_counter()
        b_fair = batch_orders_fcfs(tasks, capacity=config.trolley_capacity_units, num_pickers=num_pickers, fair_round_robin=True)
        routes_ss = {p: route_s_shape(b_tasks, graph) for p, b_tasks in b_fair.items()}
        rt_ss_ms = (time.perf_counter() - ts_start) * 1000.0
        res_ss = twin.simulate_wave(routes_ss)
        results.append({
            "wave_id": wid,
            "method": "FCFS_SShape",
            "num_picks": len(tasks),
            "num_pickers": num_pickers,
            "makespan_s": res_ss["makespan_s"],
            "makespan_min": res_ss["makespan_min"],
            "total_distance_m": res_ss["total_distance_m"],
            "total_blocked_time_s": res_ss["total_blocked_time_s"],
            "total_travel_time_s": res_ss["total_travel_time_s"],
            "total_pick_time_s": res_ss["total_pick_time_s"],
            "congestion_events_count": res_ss["congestion_events_count"],
            "workload_cv": res_ss["workload_cv"],
            "runtime_ms": rt_ss_ms,
        })

        # 2. Fair Multi-Picker FCFS + Largest-Gap
        ts_start = time.perf_counter()
        b_fair_lg = batch_orders_fcfs(tasks, capacity=config.trolley_capacity_units, num_pickers=num_pickers, fair_round_robin=True)
        routes_lg = {p: route_largest_gap(b_tasks, graph) for p, b_tasks in b_fair_lg.items()}
        rt_lg_ms = (time.perf_counter() - ts_start) * 1000.0
        res_lg = twin.simulate_wave(routes_lg)
        results.append({
            "wave_id": wid,
            "method": "FCFS_LargestGap",
            "num_picks": len(tasks),
            "num_pickers": num_pickers,
            "makespan_s": res_lg["makespan_s"],
            "makespan_min": res_lg["makespan_min"],
            "total_distance_m": res_lg["total_distance_m"],
            "total_blocked_time_s": res_lg["total_blocked_time_s"],
            "total_travel_time_s": res_lg["total_travel_time_s"],
            "total_pick_time_s": res_lg["total_pick_time_s"],
            "congestion_events_count": res_lg["congestion_events_count"],
            "workload_cv": res_lg["workload_cv"],
            "runtime_ms": rt_lg_ms,
        })

        # 3. Fair Multi-Picker FCFS + Static TSP (2-Opt)
        ts_start = time.perf_counter()
        b_fair_tsp = batch_orders_fcfs(tasks, capacity=config.trolley_capacity_units, num_pickers=num_pickers, fair_round_robin=True)
        routes_tsp = {p: route_tsp_nearest_neighbor(b_tasks, graph) for p, b_tasks in b_fair_tsp.items()}
        rt_tsp_ms = (time.perf_counter() - ts_start) * 1000.0
        res_tsp = twin.simulate_wave(routes_tsp)
        results.append({
            "wave_id": wid,
            "method": "FCFS_StaticTSP",
            "num_picks": len(tasks),
            "num_pickers": num_pickers,
            "makespan_s": res_tsp["makespan_s"],
            "makespan_min": res_tsp["makespan_min"],
            "total_distance_m": res_tsp["total_distance_m"],
            "total_blocked_time_s": res_tsp["total_blocked_time_s"],
            "total_travel_time_s": res_tsp["total_travel_time_s"],
            "total_pick_time_s": res_tsp["total_pick_time_s"],
            "congestion_events_count": res_tsp["congestion_events_count"],
            "workload_cv": res_tsp["workload_cv"],
            "runtime_ms": rt_tsp_ms,
        })

        # 4. Proposed CAST-Wave (5-Zone Sector + LPT + Congestion-Aware 2-Opt)
        ts_start = time.perf_counter()
        routes_cast = optimizer.optimize_wave(tasks, num_pickers=num_pickers, trolley_capacity=config.trolley_capacity_units)
        rt_cast_ms = (time.perf_counter() - ts_start) * 1000.0
        res_cast = twin.simulate_wave(routes_cast)
        results.append({
            "wave_id": wid,
            "method": "CAST_Wave",
            "num_picks": len(tasks),
            "num_pickers": num_pickers,
            "makespan_s": res_cast["makespan_s"],
            "makespan_min": res_cast["makespan_min"],
            "total_distance_m": res_cast["total_distance_m"],
            "total_blocked_time_s": res_cast["total_blocked_time_s"],
            "total_travel_time_s": res_cast["total_travel_time_s"],
            "total_pick_time_s": res_cast["total_pick_time_s"],
            "congestion_events_count": res_cast["congestion_events_count"],
            "workload_cv": res_cast["workload_cv"],
            "runtime_ms": rt_cast_ms,
        })

        # 5. Audited Legacy Single-Picker FCFS Baseline (for reference)
        ts_start = time.perf_counter()
        b_leg = batch_orders_fcfs(tasks, capacity=config.trolley_capacity_units, num_pickers=num_pickers, fair_round_robin=False)
        routes_leg = {p: route_s_shape(b_tasks, graph) for p, b_tasks in b_leg.items()}
        rt_leg_ms = (time.perf_counter() - ts_start) * 1000.0
        res_leg = twin.simulate_wave(routes_leg)
        results.append({
            "wave_id": wid,
            "method": "Legacy_Single_Picker_FCFS",
            "num_picks": len(tasks),
            "num_pickers": num_pickers,
            "makespan_s": res_leg["makespan_s"],
            "makespan_min": res_leg["makespan_min"],
            "total_distance_m": res_leg["total_distance_m"],
            "total_blocked_time_s": res_leg["total_blocked_time_s"],
            "total_travel_time_s": res_leg["total_travel_time_s"],
            "total_pick_time_s": res_leg["total_pick_time_s"],
            "congestion_events_count": res_leg["congestion_events_count"],
            "workload_cv": res_leg["workload_cv"],
            "runtime_ms": rt_leg_ms,
        })

    elapsed = time.time() - t0
    df_res = pd.DataFrame(results)
    out_path = BASE_DIR / "experiments" / "benchmark_results.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df_res.to_csv(out_path, index=False)
    print(f"Benchmark completed in {elapsed:.1f}s -> {out_path} ({len(df_res)} rows)")
    return df_res


def run_fleet_scalability_ablation(num_waves: int = 40) -> pd.DataFrame:
    """
    Evaluate makespan, distance, and congestion across fleet sizes P in [2, 4, 6, 8, 10, 12]
    on dense operational waves (~47 picks per wave formed from merged consecutive waves).
    Directly addresses Reviewer High Concern #1 & #3.
    """
    print("=" * 60)
    print("Executing Fleet Scalability & Congestion Ablation on Dense Waves...")
    print("=" * 60)

    graph = WarehouseGraph()
    config = SimulationConfig(pick_dwell_s=12.6, walking_speed_mps=1.10)
    twin = WarehouseDigitalTwin(graph, config)
    optimizer = CASTWaveOptimizer(graph, config)

    wave_data = load_historical_waves(num_waves)
    # Form 20 dense operational waves by merging consecutive wave records
    dense_waves = []
    for i in range(0, len(wave_data) - 1, 2):
        w1, t1 = wave_data[i]
        w2, t2 = wave_data[i + 1]
        dense_waves.append((w1, list(t1) + list(t2)))

    fleet_sizes = [2, 4, 6, 8, 10, 12]
    ablation_results = []

    for wid, tasks in dense_waves:
        for P in fleet_sizes:
            # Fair Multi-Picker FCFS + Static TSP (2-Opt)
            b_fair = batch_orders_fcfs(tasks, capacity=config.trolley_capacity_units, num_pickers=P, fair_round_robin=True)
            routes_tsp = {p: route_tsp_nearest_neighbor(b_tasks, graph) for p, b_tasks in b_fair.items()}
            res_tsp = twin.simulate_wave(routes_tsp)
            ablation_results.append({
                "wave_id": wid,
                "num_picks": len(tasks),
                "fleet_size": P,
                "method": "FCFS_StaticTSP",
                "makespan_min": res_tsp["makespan_min"],
                "total_distance_m": res_tsp["total_distance_m"],
                "total_blocked_time_s": res_tsp["total_blocked_time_s"],
                "congestion_events_count": res_tsp["congestion_events_count"],
            })

            # Sector Clustering + Balanced LPT + Static 2-Opt TSP (decouples sectoring from congestion avoidance)
            b_sec = optimizer.batch_orders(tasks, num_pickers=P, capacity=config.trolley_capacity_units)
            routes_sec = {p: route_tsp_nearest_neighbor(b_tasks, graph) for p, b_tasks in b_sec.items()}
            res_sec = twin.simulate_wave(routes_sec)
            ablation_results.append({
                "wave_id": wid,
                "num_picks": len(tasks),
                "fleet_size": P,
                "method": "Sector_StaticTSP",
                "makespan_min": res_sec["makespan_min"],
                "total_distance_m": res_sec["total_distance_m"],
                "total_blocked_time_s": res_sec["total_blocked_time_s"],
                "congestion_events_count": res_sec["congestion_events_count"],
            })

            # Proposed CAST-Wave (5-Zone Sector + LPT + Congestion-Aware 2-Opt)
            routes_cast = optimizer.optimize_wave(tasks, num_pickers=P, trolley_capacity=config.trolley_capacity_units)
            res_cast = twin.simulate_wave(routes_cast)
            ablation_results.append({
                "wave_id": wid,
                "num_picks": len(tasks),
                "fleet_size": P,
                "method": "CAST_Wave",
                "makespan_min": res_cast["makespan_min"],
                "total_distance_m": res_cast["total_distance_m"],
                "total_blocked_time_s": res_cast["total_blocked_time_s"],
                "congestion_events_count": res_cast["congestion_events_count"],
            })

    df_abl = pd.DataFrame(ablation_results)
    out_path = BASE_DIR / "experiments" / "congestion_ablation_results.csv"
    df_abl.to_csv(out_path, index=False)
    print(f"Fleet ablation completed -> {out_path} ({len(df_abl)} rows)")
    return df_abl


def compute_statistical_summary(df: pd.DataFrame):
    """Print detailed statistical comparisons between methods."""
    print("\n" + "=" * 70)
    print("EMPIRICAL BENCHMARK STATISTICAL SUMMARY (N = 100 Historical Waves)")
    print("=" * 70)

    summary = df.groupby("method").agg(
        makespan_mean=("makespan_min", "mean"),
        makespan_std=("makespan_min", "std"),
        dist_mean=("total_distance_m", "mean"),
        dist_std=("total_distance_m", "std"),
        blocked_mean=("total_blocked_time_s", "mean"),
        blocked_std=("total_blocked_time_s", "std"),
        congestions_mean=("congestion_events_count", "mean"),
        workload_cv_mean=("workload_cv", "mean"),
    )
    print(summary.to_string())

    # Paired comparisons against CAST-Wave
    cast_make = df[df["method"] == "CAST_Wave"].sort_values("wave_id")["makespan_min"].values
    for b_name in ["FCFS_SShape", "FCFS_LargestGap", "FCFS_StaticTSP"]:
        b_make = df[df["method"] == b_name].sort_values("wave_id")["makespan_min"].values
        diff = b_make - cast_make
        pct_imp = (np.mean(b_make) - np.mean(cast_make)) / np.mean(b_make) * 100.0
        t_stat, p_val = stats.ttest_rel(b_make, cast_make)
        w_stat, w_pval = stats.wilcoxon(b_make, cast_make)
        d = (np.mean(cast_make) - np.mean(b_make)) / np.std(diff, ddof=1)
        print(f"\nCAST-Wave vs {b_name}:")
        print(f"  Makespan Improvement: {pct_imp:.2f}% (Reduction of {np.mean(diff):.2f} min)")
        print(f"  Paired t-test: t = {t_stat:.3f}, p = {p_val:.2e}")
        print(f"  Wilcoxon signed-rank: W = {w_stat:.1f}, p = {w_pval:.2e}")
        print(f"  Cohen's d effect size: d = {d:.2f}")


def main():
    bench_df = run_benchmark(num_waves=100, num_pickers=4)
    compute_statistical_summary(bench_df)
    run_fleet_scalability_ablation(num_waves=40)


if __name__ == "__main__":
    main()
