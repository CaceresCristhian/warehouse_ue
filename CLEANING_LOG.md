# IDEA 15.5 – Data Cleaning & Handover Resolution Log

Generated: 2026-11-17T11:57:21 (Stage 1 Raw-to-Clean Audit) | Updated: 2026-11-18 (Stage 2 Digital Twin Reconciliation)

---

## Dataset 1 – Footwear Warehouse (`01_Footwear_Warehouse_2025`)

| Metric | Value |
|--------|-------|
| Raw order lines | 122,370 |
| Duplicate rows dropped | 2,559 |
| Zero-qty rows (flagged) | 29 |
| No-size rows (flagged) | 16 |
| Clean order lines | 119,811 |
| Total units ordered | 215,460 |
| Total units picked | 215,192 |
| Unit gap (orders − picks) | 268 |
| Pick locations missing from slots | 22 |
| Navigation nodes | 44 |
| Navigation edges (auto-built) | 68 |

**Size scale distribution (order lines)**

| Scale | Lines |
|-------|-------|
| us | 80,492 |
| us_x10 | 38,598 |
| unknown | 16 |
| mm | 705 |

**Missing pick locations** (flagged in `picks_clean.csv`): `C-014`, `C-021`, `C-022`, `C-023`, `C-024`, `C-026`, `C-061`, `C-102`, `E-25-20`, `EX-01`, `EX-04`, `EX-11`, `G-25-10`, `I-25-20`, `J-25-20`, `K-25-20`, `K-26-20`, `RC-01`, `RC-03`, `RC-04`, `RC-05`, `ZN-COR`.

**Stage 1 Decisions Applied (`clean_data.py`)**

- Duplicates: dropped (all 9 field exact match: 2,559 rows removed).
- Zero-qty and no-size rows: **flagged** with `quality_flag` column, not dropped — modelling team to decide.
- Size scale: classified per row into `us`, `us_x10`, `mm`, `unknown`; raw value preserved.
- Coordinate unit: `0.08 m/unit` scale factor applied (`x_m`, `y_m` columns), mapping raw range `x ∈ [66, 686], y ∈ [-29, 1471]` to physical industrial footprint `55 m × 120 m`.
- Storage policy slot values (`4.0–16.0`): melted from wide 18-slot format to long format (`location, storage_code, slot_num, sku, slot_value, policy`).
- Missing pick locations: flagged `quality_flag='location_not_in_slots'` in `picks_clean.csv`.
- Pick/order unit gap: narrowed from raw 13,003 units down to **268 units** after deduplication (`97.9%` reconciliation rate).

---

## Dataset 2 – KIT Benchmark (`02_KIT_Benchmark_2026`)

| Metric | Value |
|--------|-------|
| Instances sampled | 50 |
| Flat order-item rows | 49,615 |
| OFAT result rows | 1,591 |

**Stage 1 Decisions Applied (`clean_data.py`)**

- Decimal commas in result CSVs replaced with decimal points.
- Semicolon separators normalised to comma.
- Sample: first 5 LHS paramsets × 10 replications flattened to `kit_scenarios_flat.csv`.
- All OFAT routing/waiting baseline results combined into `kit_results_flat.csv`.

---

## Dataset 3 – DaRA (`03_DaRA_2026`)

| Metric | Value |
|--------|-------|
| Raw WMS rows | 540 |
| Pick rows (qty < 0) | 270 |
| Inter-pick gaps computed | 257 |
| Median gap (s) | 36.0 |
| Mean gap (s) | 54.0 |
| IQR (s) | 26.0–59.0 |
| Max gap (s) | 431.0 |

**Stage 1 Decisions Applied (`clean_data.py`)**

- Filtered to stock-out rows only (`Moved Quantity < 0`).
- Inter-pick gaps capped at 600 s (10 min) to remove session breaks.
- Walk/handle split estimated at 65/35 (Chackelson et al. 2013), yielding median pick handling dwell `est_handle_s = 12.6 s`.

---

## Dataset 4 – RMFS (`04_RMFS_2026`, optional robotic benchmark)

| Scenario | Layout rows | Pod non-zero entries |
|----------|-------------|----------------------|
| Large | 205 | 3,342 |
| Enlarged 0.8 | 409 | 7,016 |
| Enlarged 0.9 | 409 | 7,552 |

**Stage 1 Decisions Applied (`clean_data.py`)**

- Scientific-notation floats cast to integers.
- Pod inventory melted to long format (`pod_id, cargo_type, qty`); zero-qty entries omitted.
- Why RMFS is retained as optional archive only: RMFS models robotic Kiva-style pod-to-station fulfillment without human aisle traversal or narrow-aisle passing conflicts, whereas our study targets manual multi-block order-picking warehouses.

---

## Stage 2 Modelling Team Resolution of Handover Checklist (`src/data_preprocessing.py`)

| Handover Checklist Item | Modelling Team Resolution Implemented |
|-------------------------|---------------------------------------|
| **Coordinate unit (`0.08 m/unit`)** | Adopted as an engineering calibration scale factor mapping raw coordinate range (`x ∈ [66, 686], y ∈ [-29, 1471]`) to a representative `55 m × 120 m` two-block layout across `slots.parquet`, `nav_nodes.parquet`, and `nav_edges.parquet`; exact millimeter verification against `Full layout.dwg` is noted as a limitation for future work. |
| **Aisle width & passing rule** | Modelled as narrow single-file sub-aisles (`K = 1` unimpeded picker per sub-segment `(aisle, west/east)`, with velocity slowdown factor `α = 0.40` under simultaneous occupancy, calibrated to Koreis & Klumpp, 2026). |
| **Number of pickers per shift** | Default operational fleet set to `P = 4` pickers for standard waves (`15–30` picks), with dense-wave scalability ablation (`≈ 46.6` picks/wave) evaluated across `P ∈ {2, 4, 6, 8, 10, 12}`. |
| **Cart capacity (`C`)** | Set to `C = 27` footwear boxes per trolley, matching empirical wave line distributions. |
| **Zero-qty / no-size rows** | Preserved with `quality_flag` in `orders_clean.parquet`; wave replay draws directly from validated physical pick confirmations (`picks_clean.parquet`). |
| **22 missing pick locations** | Explicitly reconciled in `src/data_preprocessing.py`: 16 staging/consolidation codes (`RC-01`..`RC-05`, `EX-01`..`EX-11`, `C-014`..`C-102`, `ZN-COR`) mapped to central I/O staging buffer `CC-08` (`32.24 m, 50.48 m`), and 6 extended rack bays (`E-25-20`, `G-25-10`, `I-25-20`, `J-25-20`, `K-25-20`, `K-26-20`) matched to the nearest existing bay in the corresponding aisle from `slots.csv` (`100%` valid coordinates across all `215,192` picks). |
| **Walk/handle split in DaRA** | Calibrated empirical pick dwell time `τ_pick = 12.6 s` (35% of 36.0 s median inter-pick gap) and unimpeded walk speed `v_0 = 1.10 m/s`. |
