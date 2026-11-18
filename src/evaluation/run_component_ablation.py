"""
Component-by-Component Ablation Runner for Footwear Warehouse Digital Twin.
Directly addresses Reviewer Concern #1 and #2:
- Audited Fair Multi-Picker FCFS Baseline (Round-Robin batching)
- Balanced LPT Unit Batching + Static 2-Opt TSP
- Sector Clustering + Balanced LPT Batching + Static 2-Opt TSP
- Full CAST-Wave (Sector Clustering + Balanced LPT + Dynamic Congestion-Penalized TSP)
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

from src.evaluation.benchmark_runner import load_historical_waves
from src.digital_twin.warehouse_graph import WarehouseGraph
from src.digital_twin.simulation_engine import WarehouseDigitalTwin, PickTask, SimulationConfig
from src.optimization.baselines import (
    batch_orders_fcfs,
    batch_orders_fcfs_round_robin,
    batch_orders_balanced_lpt,
    route_s_shape,
    route_largest_gap,
    route_tsp_nearest_neighbor,
)
from src.optimization.cast_wave_optimizer import CASTWaveOptimizer


def run_component_ablation(num_waves: int = 100, num_pickers: int = 4):
    print("=" * 70)
    print(f"Running Component Ablation on {num_waves} Waves (Fleet P = {num_pickers} Pickers)...")
    print("=" * 70)

    graph = WarehouseGraph()
    config = SimulationConfig(pick_dwell_s=12.6, walking_speed_mps=1.10)
    twin = WarehouseDigitalTwin(graph, config)
    optimizer = CASTWaveOptimizer(graph, config)
    waves = load_historical_waves(num_waves)

    results = []
    t0 = time.time()

    for idx, (wid, tasks) in enumerate(waves, 1):
        if idx % 25 == 0 or idx == len(waves):
            print(f"  Processed {idx}/{len(waves)} waves...")

        # 0. Legacy Degenerate FCFS (1 picker carries all, as audited by reviewer)
        b_leg = batch_orders_fcfs(tasks, capacity=config.trolley_capacity_units, num_pickers=num_pickers, fair_round_robin=False)
        r0 = {p: route_s_shape(b_leg[p], graph) for p in b_leg}
        res0 = twin.simulate_wave(r0)

        # 1. Fair Multi-Picker FCFS (Round-Robin) + S-Shape
        b_rr = batch_orders_fcfs_round_robin(tasks, capacity=config.trolley_capacity_units, num_pickers=num_pickers)
        r1 = {p: route_s_shape(b_rr[p], graph) for p in b_rr}
        res1 = twin.simulate_wave(r1)

        # 2. Fair Multi-Picker FCFS (Round-Robin) + Static 2-Opt TSP
        r2 = {p: route_tsp_nearest_neighbor(b_rr[p], graph) for p in b_rr}
        res2 = twin.simulate_wave(r2)

        # 3. Balanced Unit Batching (LPT) + Static 2-Opt TSP (isolates workload balancing)
        b_lpt = batch_orders_balanced_lpt(tasks, capacity=config.trolley_capacity_units, num_pickers=num_pickers)
        r3 = {p: route_tsp_nearest_neighbor(b_lpt[p], graph) for p in b_lpt}
        res3 = twin.simulate_wave(r3)

        # 4. Sector Clustering + Balanced Batching + Static 2-Opt TSP (isolates spatial sectoring)
        b_sec = optimizer.batch_orders(tasks, num_pickers=num_pickers, capacity=config.trolley_capacity_units)
        r4 = {p: route_tsp_nearest_neighbor(b_sec[p], graph) for p in b_sec}
        res4 = twin.simulate_wave(r4)

        # 5. Full CAST-Wave: Sector + Balanced Batching + Dynamic Congestion-Penalized TSP
        r5 = optimizer.optimize_wave(tasks, num_pickers=num_pickers, trolley_capacity=config.trolley_capacity_units)
        res5 = twin.simulate_wave(r5)

        results.append({
            "wave_id": wid,
            "num_picks": len(tasks),
            "Legacy_Single_Picker_SShape": res0["makespan_min"],
            "Fair_RR_SShape": res1["makespan_min"],
            "Fair_RR_StaticTSP": res2["makespan_min"],
            "Balanced_LPT_StaticTSP": res3["makespan_min"],
            "Sector_LPT_StaticTSP": res4["makespan_min"],
            "CAST_Wave_Full": res5["makespan_min"],
            # Every metric is measured per stage (no cross-stage reuse)
            "cv_legacy": res0["workload_cv"],
            "cv_rr": res1["workload_cv"],
            "cv_rr_tsp": res2["workload_cv"],
            "cv_lpt": res3["workload_cv"],
            "cv_sector": res4["workload_cv"],
            "cv_cast": res5["workload_cv"],
            "dist_legacy": res0["total_distance_m"],
            "dist_rr_ss": res1["total_distance_m"],
            "dist_rr_tsp": res2["total_distance_m"],
            "dist_lpt_tsp": res3["total_distance_m"],
            "dist_sector_tsp": res4["total_distance_m"],
            "dist_cast_wave": res5["total_distance_m"],
            "blocked_legacy": res0["total_blocked_time_s"],
            "blocked_rr_ss": res1["total_blocked_time_s"],
            "blocked_rr_tsp": res2["total_blocked_time_s"],
            "blocked_lpt_tsp": res3["total_blocked_time_s"],
            "blocked_sector_tsp": res4["total_blocked_time_s"],
            "blocked_cast_wave": res5["total_blocked_time_s"],
        })

    df = pd.DataFrame(results)
    out_csv = BASE_DIR / "experiments" / "component_ablation_results.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nAblation completed in {time.time()-t0:.2f}s -> Saved {out_csv}")

    print("\n" + "=" * 70)
    print("COMPONENT ABLATION SUMMARY (Means over 100 historical waves):")
    print("=" * 70)
    print(f"0. Legacy Single-Picker FCFS  : {df['Legacy_Single_Picker_SShape'].mean():.2f} +/- {df['Legacy_Single_Picker_SShape'].std():.2f} min (CV = {df['cv_legacy'].mean():.3f})")
    print(f"1. Fair FCFS (RR) + S-Shape   : {df['Fair_RR_SShape'].mean():.2f} +/- {df['Fair_RR_SShape'].std():.2f} min (CV = {df['cv_rr'].mean():.3f})")
    print(f"2. Fair FCFS (RR) + Static TSP: {df['Fair_RR_StaticTSP'].mean():.2f} +/- {df['Fair_RR_StaticTSP'].std():.2f} min (CV = {df['cv_rr_tsp'].mean():.3f})")
    print(f"3. Balanced LPT + Static TSP  : {df['Balanced_LPT_StaticTSP'].mean():.2f} +/- {df['Balanced_LPT_StaticTSP'].std():.2f} min (CV = {df['cv_lpt'].mean():.3f})")
    print(f"4. Sector + LPT + Static TSP  : {df['Sector_LPT_StaticTSP'].mean():.2f} +/- {df['Sector_LPT_StaticTSP'].std():.2f} min (CV = {df['cv_sector'].mean():.3f})")
    print(f"5. Full CAST-Wave (Proposed)  : {df['CAST_Wave_Full'].mean():.2f} +/- {df['CAST_Wave_Full'].std():.2f} min (CV = {df['cv_cast'].mean():.3f})")

    # Percentage reductions vs Fair RR + S-Shape
    base_m = df["Fair_RR_SShape"].mean()
    cast_m = df["CAST_Wave_Full"].mean()
    imp_vs_fair = (base_m - cast_m) / base_m * 100.0
    print(f"\nMakespan Reduction vs Fair Multi-Picker Baseline : -{imp_vs_fair:.1f}%")

    # Statistical significance
    t_stat, p_val = stats.ttest_rel(df["Fair_RR_SShape"], df["CAST_Wave_Full"])
    w_stat, w_pval = stats.wilcoxon(df["Fair_RR_SShape"], df["CAST_Wave_Full"])
    diff = df["CAST_Wave_Full"] - df["Fair_RR_SShape"]
    dz = float(np.mean(diff) / np.std(diff, ddof=1))
    print(f"Paired t-test vs Fair Baseline: t = {t_stat:.2f}, p = {p_val:.2e}")
    print(f"Wilcoxon signed-rank test     : W = {w_stat:.1f}, p = {w_pval:.2e}")
    print(f"Paired Effect Size (Cohen dz) : {dz:.2f}")

    return df


if __name__ == "__main__":
    run_component_ablation(100, 4)
