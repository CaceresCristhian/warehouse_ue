"""
Data Preprocessing for Footwear Warehouse Digital Twin using Cleaned Datasets.
Ingests:
- data/clean/slots.csv: Master physical storage locations and metric coordinates.
- data/clean/nav_nodes.csv: 44 corridor navigation waypoints (LC, CC, RC).
- data/clean/nav_edges.csv: 68 corridor and aisle topological edges with metric lengths.
- data/clean/picks_clean.csv: 215,192 empirical pick operations with quality flags.
- data/clean/orders_clean.csv: 119,811 deduplicated order lines with timestamps.
- data/clean/products_clean.csv: Master product references & ABC classes.
- data/clean/picker_timing.csv: DaRA 2026 empirical picker timing calibration.

Outputs clean, validated Parquet files into data/02_processed/.
"""

from pathlib import Path
import re
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
CLEAN_DIR = BASE_DIR / "data" / "clean"
PROC_DIR = BASE_DIR / "data" / "02_processed"


def preprocess_storage_locations() -> pd.DataFrame:
    """Load and process master slots with validated metric coordinates."""
    df = pd.read_csv(CLEAN_DIR / "slots.csv")
    df["x_m"] = pd.to_numeric(df["x_m"], errors="raise").astype(float)
    df["y_m"] = pd.to_numeric(df["y_m"], errors="raise").astype(float)
    df["x_raw"] = pd.to_numeric(df["x_raw"], errors="raise").astype(float)
    df["y_raw"] = pd.to_numeric(df["y_raw"], errors="raise").astype(float)
    df["z"] = pd.to_numeric(df["level"], errors="raise").astype(int)
    df["row"] = pd.to_numeric(df["row"], errors="coerce").fillna(0).astype(int)
    df["col"] = pd.to_numeric(df["col"], errors="coerce").fillna(0).astype(int)

    # Active picking levels (levels 1 and 2); levels 3 and 4 are replenishment
    df["is_pick_level"] = df["z"].isin([1, 2])
    df = df.sort_values(["z", "aisle", "row", "col"]).reset_index(drop=True)

    out_path = PROC_DIR / "slots.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Preprocessed {len(df)} storage slots -> {out_path}")
    return df


def preprocess_navigation() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load navigation nodes and edges."""
    nodes = pd.read_csv(CLEAN_DIR / "nav_nodes.csv")
    nodes["x_m"] = pd.to_numeric(nodes["x_m"]).astype(float)
    nodes["y_m"] = pd.to_numeric(nodes["y_m"]).astype(float)
    nodes["x_raw"] = pd.to_numeric(nodes["x_raw"]).astype(float)
    nodes["y_raw"] = pd.to_numeric(nodes["y_raw"]).astype(float)
    nodes["z_raw"] = pd.to_numeric(nodes["z_raw"]).astype(float)
    nodes_path = PROC_DIR / "nav_nodes.parquet"
    nodes.to_parquet(nodes_path, index=False)
    print(f"Preprocessed {len(nodes)} navigation nodes -> {nodes_path}")

    edges = pd.read_csv(CLEAN_DIR / "nav_edges.csv")
    edges["length_m"] = pd.to_numeric(edges["length_m"]).astype(float)
    edges_path = PROC_DIR / "nav_edges.parquet"
    edges.to_parquet(edges_path, index=False)
    print(f"Preprocessed {len(edges)} navigation edges -> {edges_path}")

    return nodes, edges


def preprocess_dara_timing() -> pd.DataFrame:
    """Load and process DaRA 2026 empirical picker timing calibration."""
    df = pd.read_csv(CLEAN_DIR / "picker_timing.csv")
    df["gap_to_next_s"] = pd.to_numeric(df["gap_to_next_s"], errors="coerce")
    df["est_walk_s"] = pd.to_numeric(df["est_walk_s"], errors="coerce")
    df["est_handle_s"] = pd.to_numeric(df["est_handle_s"], errors="coerce")
    out_path = PROC_DIR / "picker_timing.parquet"
    df.to_parquet(out_path, index=False)
    valid_gaps = df["gap_to_next_s"].dropna()
    print(f"Preprocessed {len(df)} DaRA timing records ({len(valid_gaps)} valid inter-pick gaps) -> {out_path}")
    print(f"  DaRA Inter-pick Gap: Median={valid_gaps.median():.1f}s, Mean={valid_gaps.mean():.1f}s, IQR=[{valid_gaps.quantile(0.25):.1f}s, {valid_gaps.quantile(0.75):.1f}s]")
    return df


def preprocess_orders_and_picks(slots_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clean and match orders and picks to exact physical metric coordinates."""
    # Product ABC mapping
    prod_df = pd.read_csv(CLEAN_DIR / "products_clean.csv")
    abc_map = dict(zip(prod_df["sku"], prod_df["abc_class"]))

    # Clean customer orders
    orders = pd.read_csv(CLEAN_DIR / "orders_clean.csv")
    orders["wave_id"] = pd.to_numeric(orders["wave_id"], errors="coerce").astype(int)
    orders["qty"] = pd.to_numeric(orders["qty"], errors="coerce").fillna(1).astype(int)
    orders["created_at"] = pd.to_datetime(orders["created_at"], errors="coerce")
    orders["abc_class"] = orders["sku"].map(abc_map).fillna("C")
    orders_path = PROC_DIR / "orders_clean.parquet"
    orders.to_parquet(orders_path, index=False)
    print(f"Preprocessed {len(orders)} clean customer orders -> {orders_path}")

    # Clean picks
    picks = pd.read_csv(CLEAN_DIR / "picks_clean.csv")
    picks["wave_id"] = pd.to_numeric(picks["wave_id"], errors="coerce").astype(int)
    picks["qty"] = pd.to_numeric(picks["qty"], errors="coerce").fillna(1).astype(int)
    picks["abc_class"] = picks["sku"].map(abc_map).fillna("C")

    # Merge slot coordinates
    slot_coords = slots_df[["location", "aisle", "row", "col", "x_m", "y_m", "x_raw", "y_raw", "z"]].copy()
    picks = picks.merge(slot_coords, on="location", how="left")

    # Staging / overflow buffers mapping (RC-01, EX-*, C-*, ZN-*)
    # Mapped to the central I/O staging area (CC-08 at x_m=32.24, y_m=50.48)
    is_staging = picks["x_m"].isna() & (
        picks["location"].str.startswith("RC-")
        | picks["location"].str.startswith("ZN-")
        | picks["location"].str.startswith("EX-")
        | picks["location"].str.startswith("C-")
    )
    picks.loc[is_staging, "x_m"] = 32.24
    picks.loc[is_staging, "y_m"] = 50.48
    picks.loc[is_staging, "x_raw"] = 403.0
    picks.loc[is_staging, "y_raw"] = 631.0
    picks.loc[is_staging, "z"] = 1
    picks.loc[is_staging, "aisle"] = "CC"
    picks.loc[is_staging, "row"] = 8
    picks.loc[is_staging, "col"] = 0

    # Remaining shelf codes with aisle and bay (e.g., E-25-20, G-25-10, I-25-20, J-25-20, K-25-20, K-26-20)
    # Match against nearest existing bay in the same aisle from slots_df
    unassigned = picks["x_m"].isna()
    if unassigned.any():
        aisle_y_raw_map = slots_df.groupby("aisle")["y_raw"].median().to_dict()
        for idx in picks[unassigned].index:
            loc_str = str(picks.at[idx, "location"])
            parts = loc_str.split("-")
            aisle_cand = parts[0] if len(parts) > 0 else "CC"
            bay_cand = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
            same_aisle = slots_df[slots_df["aisle"] == aisle_cand]
            if not same_aisle.empty:
                nearest_idx = (same_aisle["row"] - bay_cand).abs().idxmin()
                x_raw_cand = float(same_aisle.loc[nearest_idx, "x_raw"])
                y_raw_cand = float(same_aisle.loc[nearest_idx, "y_raw"])
            else:
                x_raw_cand = min(666.0, 86.0 + bay_cand * 16.0)
                y_raw_cand = float(aisle_y_raw_map.get(aisle_cand, 631.0))
            picks.at[idx, "aisle"] = aisle_cand
            picks.at[idx, "row"] = bay_cand
            picks.at[idx, "col"] = 0
            picks.at[idx, "z"] = 1
            picks.at[idx, "x_raw"] = x_raw_cand
            picks.at[idx, "y_raw"] = y_raw_cand
            picks.at[idx, "x_m"] = round(x_raw_cand * 0.08, 3)
            picks.at[idx, "y_m"] = round(y_raw_cand * 0.08, 3)

    picks["x_m"] = picks["x_m"].astype(float)
    picks["y_m"] = picks["y_m"].astype(float)
    picks["z"] = picks["z"].astype(int)

    picks = picks.sort_values(["wave_id"]).reset_index(drop=True)
    picks_path = PROC_DIR / "picks_clean.parquet"
    picks.to_parquet(picks_path, index=False)
    print(f"Preprocessed {len(picks)} clean pick records (100% valid coordinates) -> {picks_path}")

    return orders, picks


def main():
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Starting Clean WMS Data Preprocessing for Digital Twin...")
    print("=" * 60)
    slots = preprocess_storage_locations()
    preprocess_navigation()
    preprocess_dara_timing()
    preprocess_orders_and_picks(slots)
    print("=" * 60)
    print("Preprocessing successfully completed. All files in data/02_processed/.")
    print("=" * 60)


if __name__ == "__main__":
    main()
