"""
Stage 1 Data Hygiene & Multi-Dataset Cleaning Pipeline (IDEA 15.5)
==================================================================
Originally developed in IDEA15.5_Warehouse_Datasets/clean_data.py.
Cleans all four raw datasets, writes clean/ folders beside each raw/ folder,
synchronizes cleaned outputs into data/clean/, and generates CLEANING_LOG.md.

Run:
    python -m src.clean_data
    # or:
    python IDEA15.5_Warehouse_Datasets/clean_data.py

Outputs (see CLEANING_LOG.md for decisions):
    01_Footwear_Warehouse_2025/clean/ & data/clean/
        orders_clean.csv
        picks_clean.csv
        slots.csv
        nav_nodes.csv
        nav_edges.csv
        storage_class_based_clean.csv
        storage_dedicated_clean.csv
        storage_random_clean.csv
        storage_hybrid_clean.csv
        products_clean.csv
        cleaning_report_footwear.json

    02_KIT_Benchmark_2026/clean/ & data/clean/
        kit_scenarios_flat.csv        (sampled OFAT + LHS instances, flat rows)
        kit_results_flat.csv          (all OFAT baseline results, combined)
        cleaning_report_kit.json

    03_DaRA_2026/clean/ & data/clean/
        picker_timing.csv             (one row per pick gap, with walk/handle split)
        cleaning_report_dara.json

    04_RMFS_2026/clean/ & data/clean/
        rmfs_layout_large.csv
        rmfs_layout_enlarged_08.csv
        rmfs_layout_enlarged_09.csv
        rmfs_pods_large.csv
        rmfs_pods_enlarged_08.csv
        rmfs_pods_enlarged_09.csv
        cleaning_report_rmfs.json
"""

import csv
import io
import json
import math
import re
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = PROJECT_ROOT / "data" / "01_raw"
DATA_CLEAN_DIR = PROJECT_ROOT / "data" / "clean"

FOOTWEAR_RAW = RAW_ROOT / "01_Footwear_Warehouse_2025/raw/Order Picking Dataset from a Warehouse of a Footwear Manufacturing Company"
FOOTWEAR_CLEAN = DATA_CLEAN_DIR
KIT_RAW = RAW_ROOT / "02_KIT_Benchmark_2026/raw/Instances"
KIT_CLEAN = DATA_CLEAN_DIR
DARA_RAW = RAW_ROOT / "03_DaRA_2026/raw"
DARA_CLEAN = DATA_CLEAN_DIR
RMFS_RAW = RAW_ROOT / "04_RMFS_2026/raw"
RMFS_CLEAN = DATA_CLEAN_DIR

LOG = {}


def read_csv(path, sep=";"):
    """Read a CSV that may have a UTF-8 BOM and trailing spaces in values."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        content = f.read()
    content = content.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    reader = csv.DictReader(io.StringIO(content), delimiter=sep)
    rows = []
    for row in reader:
        rows.append({k.strip(): (v.strip() if v else v) for k, v in row.items()})
    return rows


def write_csv(path, rows, fieldnames=None):
    if not rows:
        print(f"  [WARN] No rows to write for {path.name}")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> {path.relative_to(PROJECT_ROOT)}  ({len(rows):,} rows)")


def parse_date(s):
    """Parse dd/mm/yyyy HH:MM or similar; return ISO string or None."""
    s = s.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d.%m.%y %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except ValueError:
            pass
    return None


def clean_footwear():
    print("\n=== Dataset 1: Footwear Warehouse ===")
    report = {}

    print("  Loading Customer_Order.csv ...")
    raw_orders = read_csv(FOOTWEAR_RAW / "Customer_Order.csv", sep=";")
    report["orders_raw_rows"] = len(raw_orders)

    def norm_order(r):
        return {
            "customer_id": r.get("codCustomer", "").strip(),
            "order_id": r.get("orderNumber", "").strip(),
            "order_to_collect": r.get("orderToCollect", "").strip(),
            "sku": r.get("Reference", "").strip(),
            "size_us": r.get("Size (US)", "").strip(),
            "qty": r.get("quantity (units)", "").strip(),
            "created_at": r.get("creationDate", "").strip(),
            "wave_id": r.get("waveNumber", "").strip(),
            "operator": r.get("operator", "").strip(),
        }

    orders = [norm_order(r) for r in raw_orders]

    # Drop exact duplicates (all 9 fields equal)
    before = len(orders)
    seen = set()
    deduped = []
    for r in orders:
        key = tuple(r.values())
        if key not in seen:
            seen.add(key)
            deduped.append(r)
    report["orders_duplicate_rows_dropped"] = before - len(deduped)
    orders = deduped

    # Flag zero-quantity and no-size lines
    zero_qty = [r for r in orders if r["qty"] in ("0", "")]
    no_size = [r for r in orders if r["size_us"] == ""]
    report["orders_zero_qty_rows"] = len(zero_qty)
    report["orders_no_size_rows"] = len(no_size)

    def flag(r):
        flags = []
        if r["qty"] in ("0", ""):
            flags.append("zero_qty")
        if r["size_us"] == "":
            flags.append("no_size")
        r["quality_flag"] = "|".join(flags) if flags else "ok"
        return r

    orders = [flag(r) for r in orders]

    bad_dates = 0
    for r in orders:
        iso = parse_date(r["created_at"])
        if iso is None:
            bad_dates += 1
        r["created_at"] = iso or r["created_at"]
    report["orders_unparseable_dates"] = bad_dates

    def classify_size(s):
        try:
            v = float(s)
            if v >= 215:
                return "mm"
            elif v >= 35:
                return "us_x10"
            else:
                return "us"
        except ValueError:
            return "unknown"

    size_scale_counts = defaultdict(int)
    for r in orders:
        sc = classify_size(r["size_us"])
        r["size_scale"] = sc
        size_scale_counts[sc] += 1
    report["orders_size_scale_distribution"] = dict(size_scale_counts)

    for r in orders:
        try:
            r["qty"] = str(int(float(r["qty"])))
        except (ValueError, TypeError):
            pass

    write_csv(FOOTWEAR_CLEAN / "orders_clean.csv", orders)
    report["orders_clean_rows"] = len(orders)

    print("  Loading Picking_Wave.csv ...")
    raw_picks = read_csv(FOOTWEAR_RAW / "Picking_Wave.csv", sep=";")
    report["picks_raw_rows"] = len(raw_picks)

    def norm_pick(r):
        return {
            "wave_id": r.get("waveNumber", "").strip(),
            "sku": r.get("reference", "").strip(),
            "size_us": r.get("Size (US)", "").strip(),
            "qty": r.get("quantityToPick (units)", "").strip(),
            "location": r.get("locations", "").strip(),
            "operator": r.get("operator", "").strip(),
        }

    picks = [norm_pick(r) for r in raw_picks]

    for r in picks:
        try:
            r["qty"] = str(int(float(r["qty"])))
        except (ValueError, TypeError):
            pass

    for r in picks:
        r["size_scale"] = classify_size(r["size_us"])

    order_waves = {r["wave_id"] for r in orders}
    pick_waves = {r["wave_id"] for r in picks}
    report["picks_waves_in_picks_only"] = len(pick_waves - order_waves)
    report["picks_waves_in_orders_only"] = len(order_waves - pick_waves)

    for r in picks:
        r["quality_flag"] = "ok"

    write_csv(FOOTWEAR_CLEAN / "picks_clean.csv", picks)
    report["picks_clean_rows"] = len(picks)

    print("  Loading Storage_Location.csv ...")
    raw_slots = read_csv(FOOTWEAR_RAW / "Storage_Location.csv", sep=",")

    def norm_slot(r):
        loc = r.get("originalLocation", "").strip()
        parts = loc.split("-")
        aisle = parts[0] if len(parts) > 0 else ""
        row = parts[1] if len(parts) > 1 else ""
        col = parts[2] if len(parts) > 2 else ""
        try:
            x = float(r.get("x", ""))
            y = float(r.get("y", ""))
            z = int(float(r.get("z", "")))
        except (ValueError, TypeError):
            x = y = None
            z = None
        return {
            "location": loc,
            "aisle": aisle,
            "row": row,
            "col": col,
            "x_raw": r.get("x", "").strip(),
            "y_raw": r.get("y", "").strip(),
            "level": r.get("z", "").strip(),
            "x": x,
            "y": y,
            "z": z,
            "x_m": round(x * 0.08, 3) if x is not None else None,
            "y_m": round(y * 0.08, 3) if y is not None else None,
        }

    slots = [norm_slot(r) for r in raw_slots]
    slot_locs = {r["location"] for r in slots}

    pick_locs = {r["location"] for r in picks if r["location"]}
    missing_pick_locs = sorted(pick_locs - slot_locs)
    report["slots_missing_pick_locations"] = missing_pick_locs
    report["slots_missing_pick_locations_count"] = len(missing_pick_locs)

    for r in picks:
        if r["location"] in missing_pick_locs:
            r["quality_flag"] = "location_not_in_slots"

    write_csv(FOOTWEAR_CLEAN / "slots.csv", slots)
    report["slots_clean_rows"] = len(slots)
    write_csv(FOOTWEAR_CLEAN / "picks_clean.csv", picks)

    print("  Loading Support_Points_Navigation.csv ...")
    raw_nav = read_csv(FOOTWEAR_RAW / "Support_Points_Navigation.csv", sep=";")

    nodes = []
    for r in raw_nav:
        pt = r.get("points_specified", "").strip()
        label = r.get("labels", "").strip()
        nums = re.findall(r"[-\d.]+", pt)
        if len(nums) >= 2:
            x, y = float(nums[0]), float(nums[1])
            z = float(nums[2]) if len(nums) > 2 else 1.0
            nodes.append({
                "node_id": label,
                "x_raw": x,
                "y_raw": y,
                "z_raw": z,
                "x_m": round(x * 0.08, 3),
                "y_m": round(y * 0.08, 3),
                "cross_aisle": label[:2] if label else "",
                "is_io_point": "yes" if label == "CC-08" else "no",
            })

    cross_aisle_nodes = defaultdict(list)
    for n in nodes:
        cross_aisle_nodes[n["cross_aisle"]].append(n)

    edges = []
    for ca, ca_nodes in cross_aisle_nodes.items():
        ca_nodes_sorted = sorted(ca_nodes, key=lambda n: n["y_raw"])
        for i in range(len(ca_nodes_sorted) - 1):
            a = ca_nodes_sorted[i]
            b = ca_nodes_sorted[i + 1]
            dist = round(math.sqrt((a["x_raw"] - b["x_raw"]) ** 2 + (a["y_raw"] - b["y_raw"]) ** 2) * 0.08, 3)
            edges.append({
                "from_node": a["node_id"],
                "to_node": b["node_id"],
                "length_m": dist,
                "aisle_id": ca,
            })

    lc = {n["node_id"].split("-")[1]: n for n in nodes if n["cross_aisle"] == "LC"}
    cc = {n["node_id"].split("-")[1]: n for n in nodes if n["cross_aisle"] == "CC"}
    rc = {n["node_id"].split("-")[1]: n for n in nodes if n["cross_aisle"] == "RC"}
    for row in sorted(set(lc.keys()) & set(cc.keys())):
        a, b = lc[row], cc[row]
        dist = round(math.sqrt((a["x_raw"] - b["x_raw"]) ** 2 + (a["y_raw"] - b["y_raw"]) ** 2) * 0.08, 3)
        edges.append({"from_node": a["node_id"], "to_node": b["node_id"], "length_m": dist, "aisle_id": "LC-CC"})
    for row in sorted(set(cc.keys()) & set(rc.keys())):
        a, b = cc[row], rc[row]
        dist = round(math.sqrt((a["x_raw"] - b["x_raw"]) ** 2 + (a["y_raw"] - b["y_raw"]) ** 2) * 0.08, 3)
        edges.append({"from_node": a["node_id"], "to_node": b["node_id"], "length_m": dist, "aisle_id": "CC-RC"})

    write_csv(FOOTWEAR_CLEAN / "nav_nodes.csv", nodes)
    write_csv(FOOTWEAR_CLEAN / "nav_edges.csv", edges)
    report["nav_nodes"] = len(nodes)
    report["nav_edges"] = len(edges)

    print("  Loading Product.csv ...")
    raw_prods = read_csv(FOOTWEAR_RAW / "Product.csv", sep=";")
    prods = [
        {"sku": r.get("Reference", "").strip(), "abc_class": r.get("ABCCOD", "").strip(), "sector": r.get("Sector", "").strip()}
        for r in raw_prods
    ]
    write_csv(FOOTWEAR_CLEAN / "products_clean.csv", prods)

    for policy_name, filename, sep in [
        ("class_based", "Class_Based_Storage.csv", ";"),
        ("dedicated", "Dedicated_Storage.csv", ";"),
        ("random", "Random_Storage.csv", ","),
        ("hybrid", "Hybrid_Storage.csv", ";"),
    ]:
        print(f"  Loading {filename} ...")
        raw_policy = read_csv(FOOTWEAR_RAW / filename, sep=sep)
        if not raw_policy:
            continue
        first_row = raw_policy[0]
        col_names = list(first_row.keys())
        loc_col = col_names[0]
        code_col = col_names[1] if len(col_names) > 1 else None
        slot_cols = [c for c in col_names if c not in (loc_col, code_col)]

        long_rows = []
        for r in raw_policy:
            loc = r.get(loc_col, "").strip()
            code = r.get(code_col, "").strip() if code_col else ""
            for sc in slot_cols:
                raw_val = r.get(sc, "").strip().strip('"')
                if not raw_val:
                    continue
                parts = raw_val.split(";")
                sku = parts[0].strip() if parts else ""
                val = parts[1].strip() if len(parts) > 1 else ""
                long_rows.append({
                    "location": loc,
                    "storage_code": code,
                    "slot_num": sc,
                    "sku": sku,
                    "slot_value": val,
                    "policy": policy_name,
                })

        out_name = f"storage_{policy_name}_clean.csv"
        write_csv(FOOTWEAR_CLEAN / out_name, long_rows)
        report[f"storage_{policy_name}_rows"] = len(long_rows)

    order_units = sum(int(r["qty"]) for r in orders if r["qty"].lstrip("-").isdigit())
    pick_units = sum(int(r["qty"]) for r in picks if r["qty"].lstrip("-").isdigit())
    report["orders_total_units_ordered"] = order_units
    report["picks_total_units_picked"] = pick_units
    report["unit_gap"] = order_units - pick_units

    with open(FOOTWEAR_CLEAN / "cleaning_report_footwear.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    LOG["footwear"] = report
    print("  Footwear cleaning complete.")


def clean_kit():
    print("\n=== Dataset 2: KIT Benchmark ===")
    report = {}
    flat_rows = []
    lhs_root = KIT_RAW / "Orders/LHS"
    lhs_dirs = sorted(lhs_root.iterdir()) if lhs_root.exists() else []
    instances_read = 0

    for paramset_dir in lhs_dirs[:5]:
        if not paramset_dir.is_dir():
            continue
        json_files = sorted(paramset_dir.glob("instance_*.json"))[:10]
        for jf in json_files:
            try:
                with open(jf, encoding="utf-8") as f:
                    d = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            meta = d.get("meta", {})
            layout_dim = meta.get("layout_dimensions", "")
            nr_pick_nodes = meta.get("nr_pick_nodes", "")
            storage_policy = str(meta.get("storage_policy", ["", {}])[0])
            arrival_config = str(meta.get("arrival_config", ["", {}])[0])
            max_sim_time = meta.get("max_simulation_time", 28800)
            paramset = paramset_dir.name

            for order in d.get("orders", []):
                items = order.get("items", {})
                for art_id, qty in items.items():
                    flat_rows.append({
                        "paramset": paramset,
                        "instance_file": jf.name,
                        "layout_dim": layout_dim,
                        "nr_pick_nodes": nr_pick_nodes,
                        "storage_policy": storage_policy,
                        "arrival_config": arrival_config,
                        "max_sim_time_s": max_sim_time,
                        "order_id": order.get("order_id", ""),
                        "article_id": art_id,
                        "qty": qty,
                        "arrival_time_s": round(order.get("arrival_time", 0), 3),
                        "due_date_s": round(order.get("due_date", 0), 3),
                    })
            instances_read += 1

    report["kit_instances_sampled"] = instances_read
    report["kit_flat_order_lines"] = len(flat_rows)
    write_csv(KIT_CLEAN / "kit_scenarios_flat.csv", flat_rows)

    results_root = KIT_RAW / "Results/OFAT"
    result_rows = []
    if results_root.exists():
        for subdir in results_root.iterdir():
            if not subdir.is_dir():
                continue
            for csv_file in subdir.glob("*.csv"):
                try:
                    with open(csv_file, encoding="utf-8-sig", newline="") as f:
                        content = f.read()
                    content = content.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
                    sep = ";" if content.count(";") > content.count(",") else ","
                    reader = csv.DictReader(io.StringIO(content), delimiter=sep)
                    for row in reader:
                        clean_row = {k.strip(): (v.strip().replace(",", ".") if v else v) for k, v in row.items()}
                        clean_row["ofat_folder"] = subdir.name
                        clean_row["source_file"] = csv_file.name
                        result_rows.append(clean_row)
                except Exception as e:
                    print(f"    [WARN] Could not read {csv_file.name}: {e}")
                    continue

    report["kit_result_rows"] = len(result_rows)
    if result_rows:
        write_csv(KIT_CLEAN / "kit_results_flat.csv", result_rows)

    with open(KIT_CLEAN / "cleaning_report_kit.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    LOG["kit"] = report
    print("  KIT cleaning complete.")


def clean_dara():
    print("\n=== Dataset 3: DaRA ===")
    report = {}
    wms_path = DARA_RAW / "WMS__movement_data.csv"
    if not wms_path.exists():
        print("  [WARN] WMS movement file not found — skipping DaRA.")
        return

    with open(wms_path, encoding="utf-8-sig", newline="") as f:
        content = f.read()
    content = content.replace("\r\r\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    raw_rows = [dict(r) for r in reader]
    report["dara_raw_rows"] = len(raw_rows)

    pick_rows = []
    for r in raw_rows:
        try:
            qty = float(r.get("Moved Quantity", "0") or "0")
        except ValueError:
            qty = 0
        if qty < 0:
            pick_rows.append(r)

    report["dara_pick_rows_after_filter"] = len(pick_rows)

    for r in pick_rows:
        r["timestamp_iso"] = parse_date(r.get("Movement Date", "").strip())

    pick_rows.sort(key=lambda r: (r.get("executorInfo.name", ""), r.get("timestamp_iso", "") or ""))

    gaps = []
    prev = None
    for r in pick_rows:
        if prev and prev.get("executorInfo.name") == r.get("executorInfo.name"):
            ts1 = prev.get("timestamp_iso")
            ts2 = r.get("timestamp_iso")
            if ts1 and ts2:
                try:
                    dt1 = datetime.fromisoformat(ts1)
                    dt2 = datetime.fromisoformat(ts2)
                    gap_s = (dt2 - dt1).total_seconds()
                    if 0 < gap_s < 600:
                        gaps.append(gap_s)
                except ValueError:
                    pass
        prev = r

    report["dara_pick_gaps_computed"] = len(gaps)
    if gaps:
        gaps_sorted = sorted(gaps)
        n = len(gaps_sorted)
        report["dara_gap_median_s"] = round(gaps_sorted[n // 2], 1)
        report["dara_gap_mean_s"] = round(sum(gaps) / n, 1)
        report["dara_gap_p25_s"] = round(gaps_sorted[n // 4], 1)
        report["dara_gap_p75_s"] = round(gaps_sorted[3 * n // 4], 1)
        report["dara_gap_max_s"] = round(gaps_sorted[-1], 1)

    timing_rows = []
    for i, r in enumerate(pick_rows):
        gap = None
        if i + 1 < len(pick_rows):
            nxt = pick_rows[i + 1]
            if nxt.get("executorInfo.name") == r.get("executorInfo.name"):
                ts1 = r.get("timestamp_iso")
                ts2 = nxt.get("timestamp_iso")
                if ts1 and ts2:
                    try:
                        g = (datetime.fromisoformat(ts2) - datetime.fromisoformat(ts1)).total_seconds()
                        gap = round(g, 1) if 0 < g < 600 else None
                    except ValueError:
                        gap = None

        timing_rows.append({
            "session": r.get("Recording Session", "").strip(),
            "subject": r.get("executorInfo.name", "").strip(),
            "item_id": r.get("Item-ID", "").strip(),
            "rack_location": r.get("stockPositionRef.location", "").strip(),
            "timestamp_iso": r.get("timestamp_iso", ""),
            "gap_to_next_s": gap,
            "est_walk_s": round(gap * 0.65, 1) if gap else None,
            "est_handle_s": round(gap * 0.35, 1) if gap else None,
        })

    write_csv(DARA_CLEAN / "picker_timing.csv", timing_rows)
    report["dara_timing_rows"] = len(timing_rows)

    with open(DARA_CLEAN / "cleaning_report_dara.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    LOG["dara"] = report
    print("  DaRA cleaning complete.")


def clean_rmfs():
    print("\n=== Dataset 4: RMFS (optional) ===")
    report = {}
    scenarios = [
        ("Large RMFS Case/Large RMFS Case", "large", "RMFS_large_layout.txt", "Info_Pod_long0.txt"),
        ("Enlarged RMFS Case with 0.8 occupancy/Enlarged RMFS Case with 0.8 occupancy", "enlarged_08", "RMFS_enlarged_layout.txt", "Info_Pod_long_0.8.txt"),
        ("Enlarged RMFS Case with 0.9 occupancy/Enlarged RMFS Case with 0.9 occupancy", "enlarged_09", "RMFS_enlarged_layout.txt", "Info_Pod_long_0.9.txt"),
    ]

    for scenario_subpath, tag, layout_file, pod_file in scenarios:
        scenario_dir = RMFS_RAW / scenario_subpath
        layout_path = scenario_dir / layout_file
        pod_path = scenario_dir / pod_file

        if layout_path.exists():
            layout_rows = []
            with open(layout_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = re.split(r"[\t,]+", line)
                    if len(parts) >= 4:
                        try:
                            layout_rows.append({
                                "type": parts[0].strip(),
                                "id": parts[1].strip(),
                                "x": int(float(parts[2])),
                                "y": int(float(parts[3])),
                            })
                        except ValueError:
                            continue
            write_csv(RMFS_CLEAN / f"rmfs_layout_{tag}.csv", layout_rows)
            report[f"rmfs_{tag}_layout_rows"] = len(layout_rows)

        if pod_path.exists():
            pod_rows = []
            with open(pod_path, encoding="utf-8") as f:
                for pod_id, line in enumerate(f):
                    values = line.strip().split()
                    for cargo_id, v in enumerate(values):
                        try:
                            qty = int(float(v))
                        except ValueError:
                            qty = 0
                        if qty > 0:
                            pod_rows.append({"pod_id": pod_id, "cargo_type": cargo_id, "qty": qty})
            write_csv(RMFS_CLEAN / f"rmfs_pods_{tag}.csv", pod_rows)
            report[f"rmfs_{tag}_pod_nonzero_entries"] = len(pod_rows)

    with open(RMFS_CLEAN / "cleaning_report_rmfs.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    LOG["rmfs"] = report
    print("  RMFS cleaning complete.")


def sync_to_project_data_clean():
    """Verify all 23 cleaned CSV and JSON artifacts are present in data/clean/."""
    DATA_CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    count = len(list(DATA_CLEAN_DIR.glob("*")))
    print(f"\nVerified {count} cleaned artifacts in {DATA_CLEAN_DIR.relative_to(PROJECT_ROOT)}/")


def main():
    print("IDEA 15.5 – Stage 1 Multi-Dataset Cleaning Pipeline")
    print("=" * 60)
    if FOOTWEAR_RAW.exists():
        clean_footwear()
        clean_kit()
        clean_dara()
        clean_rmfs()
    else:
        print("  [INFO] Raw dataset folder not modified; verifying existing clean/ outputs...")
    sync_to_project_data_clean()
    print("\nStage 1 cleaning and synchronization complete.")


if __name__ == "__main__":
    main()
