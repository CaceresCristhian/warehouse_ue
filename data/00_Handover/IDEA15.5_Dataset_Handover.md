---
title: "IDEA 15.5 – Dataset Handover for Data Cleaning and Modelling"
date: "16 November 2026"
---

Live, editable version of this note: <https://claude.ai/artifact/GPkWLCWWfgj9GvTPbYaXJz>

## Summary

Four datasets (2025–2026) are downloaded, unpacked, checked and packed into this zip, about 7 GB once unzipped. The footwear warehouse data is the core of the digital twin; the other three feed demand scenarios, picker timing and an optional alternative topic.

| # | Dataset | Published | Role in the digital twin | Licence |
| --- | --- | --- | --- | --- |
| 1 | [Footwear warehouse order picking](https://data.mendeley.com/datasets/pf2w725pw3/1) (Data in Brief 61, 111837) | Aug 2025 | Layout, storage slots, real orders, waves and operators | CC BY 4.0 |
| 2 | [KIT benchmark instances for manual order picking](https://doi.org/10.35097/mwsv59v8sk9sqaan) | Apr 2026 | Synthetic order streams for peak bursts, wave release and due dates; baseline results | CC BY 4.0 |
| 3 | [DaRA dataset](https://zenodo.org/records/10468175) (Sensors 26(2), 739) | Jan 2026 | Real pick-to-pick times and walking behaviour to calibrate picker speed | CC BY-NC 4.0 (non-commercial) |
| 4 | [RMFS dataset](https://data.mendeley.com/datasets/tp6jnzwgzm/1) (optional) | Jul 2026 | Only if the group switches to a robot-based fulfillment topic | CC BY 4.0 |

The biggest finding: the footwear data contains a `Customer_Order.csv` the paper never describes — 122,370 order lines with creation timestamps from Jan–Oct 2023. That gives you real demand peaks, not just synthetic ones.

**Team workflow:** collection (done) → cleaning → modelling the digital twin. Cleaning follows the checklist below; modelling follows the last section.

## Folder structure and file inventory

The package is one zip, `IDEA15.5_Warehouse_Datasets.zip`. Unzip it and keep the folder names: every path in this note refers to them. Originals sit untouched in each `raw/` folder; create a sibling `clean/` folder per dataset for your outputs.

| Folder | Key files | Size (unzipped) | Source |
| --- | --- | --- | --- |
| `00_Handover/` | This note as Word, PDF and Markdown; `README.txt` with the folder map | <1 MB | — |
| `01_Footwear_Warehouse_2025/raw/` | `Customer_Order.csv`, `Picking_Wave.csv`, `Storage_Location.csv`, `Support_Points_Navigation.csv`, `Product.csv`, 4 storage-policy CSVs, `Full layout.dwg`, layout PDF/SVG per floor (Z1–Z4), `README.txt`, author notebook | 35 MB | [Mendeley](https://data.mendeley.com/datasets/pf2w725pw3/1) |
| `02_KIT_Benchmark_2026/raw/Instances/` | `Data_input/` (layouts as NetworkX `.pkl`, storage assignments `.json`), `Orders/` (13,200 instance `.json`), `Results/` (baseline CSV/XLSX), `Readme.txt`, layout legend image | 1.9 GB | [RADAR4KIT](https://doi.org/10.35097/mwsv59v8sk9sqaan) |
| `02_KIT_Benchmark_2026/raw/10.35097-mwsv59v8sk9sqaan/` | Repository readme, metadata XML and MD5 checksums | <1 MB | RADAR4KIT |
| `03_DaRA_2026/raw/` | `WMS__movement_data.csv`, `Documentation.pdf` (floor plan, item master), `Overview.pdf`, `BLE_Data_and_Revised_Annotations/` (35 BLE CSVs + labels), `Video_Revised_Annotations/` (234 label CSVs) | 5.0 GB | [Zenodo](https://zenodo.org/records/10468175) |
| `04_RMFS_2026/raw/` | 3 scenario folders, each with a layout file, a pod inventory file and 100 order files, plus a README | 150 MB | [Mendeley](https://data.mendeley.com/datasets/tp6jnzwgzm/1) |

Left out of the zip because they duplicate what is already unpacked: the two KIT `.tar` archives and the three RMFS source zips. Never downloaded: DaRA's video recordings (about 170 GB) and IMU data (867 MB); the twin does not need them, and they stay available on Zenodo.

## Dataset 1 – Footwear warehouse (core)

This is real WMS data from one footwear manufacturer's warehouse: 32,634 orders over 178 working days in 2023, picked in 9,784 waves by 24 operators. It is usable for the twin, but it needs about a dozen fixes first.

**Measured profile** (computed from the files, 16 Nov 2026)

| Item | Value |
| --- | --- |
| Order lines (`Customer_Order.csv`) | 122,370 lines, 32,634 orders, 588 customers, 208 SKUs |
| Time span | 5 Jan 2023 – 19 Oct 2023, minute resolution, one creation timestamp per order |
| Lines per order | median 1, mean 3.75, max 408 |
| Peak release | 38% of orders (12,471) are created in the 07:00 hour; busiest hour: 2 Oct 2023 07:00 with 683 orders |
| Waves | 9,784; mean 4.1 orders and 12.5 lines per wave, max 30 lines; one operator per wave |
| Pick records (`Picking_Wave.csv`) | 215,192 rows, one row per unit picked, 9,707 waves, 22 operators |
| Storage slots (`Storage_Location.csv`) | 2,292 slots, aisles A–R, 4 levels (846 / 846 / 301 / 299 slots) |
| Navigation graph (`Support_Points_Navigation.csv`) | 44 nodes on 3 cross aisles (LC 17, CC 17, RC 10 — the right block covers only the upper aisles); I/O point marked at CC-08 on the Z1 layout |

**Known issues**

- 2,559 exact duplicate order lines, 16 lines with no size, 33 lines with quantity 0.
- Units do not reconcile: orders ask for 228,195 units, pick records hold 215,192 (13,003 short). 77 waves in the orders have no pick rows.
- 4,024 orders are split across more than one wave.
- 22 of the 1,221 pick locations are missing from `Storage_Location.csv` (for example `EX-01`, `EX-04`, `C-014`, `C-102`, `J-25-20`); probably staging or overflow spots.
- Coordinate units are wrong in the README. It says metres, but x runs 86–666 and y 0–1,440, which would make the building 1.4 km long. Calibrate the unit against `Full layout.dwg` before computing travel distances.
- `Size (US)` mixes three scales: 1–16 (80,805 lines), 35–125 (38,846) and 215 and above (2,703). Likely US, US×10 for half sizes, and mm; confirm before using size as a feature.
- The storage-policy files encode each slot as `reference;value`. The README calls the value a quantity, but the values (4.0–16.0 in halves) look like sizes.
- No pick start/end times and no wave-duration column, despite the paper mentioning them. Travel and pick times must come from DaRA or the literature.
- Formatting: semicolon separators with a UTF-8 byte-order mark, except `Random_Storage.csv` and `Storage_Location.csv`, which use commas. Dates are `dd/mm/yyyy HH:MM`. Customer codes and location codes carry trailing spaces.

## Dataset 2 – KIT benchmark instances (demand scenarios)

The KIT set gives 13,200 synthetic shifts of order arrivals on rectangular layouts, each with due dates. Use it to stress-test the twin under peak bursts and wave release; it has no real data and no congestion.

- **Layouts:** `Data_input/OFAT/Layout/` (4 layouts, 128–512 pick nodes) and `Data_input/LHS/Layout/` (100 layouts), stored as NetworkX graphs in `.pkl` files. Loading them needs `networkx` installed.
- **Storage assignments:** JSON maps of article ID to a two-number pick-node position such as `[3, 1]` (confirm the axis order in `Readme.txt`), one per layout and storage policy (random, A-closest-to-depot, A-to-X, A-to-Y).
- **Orders:** one JSON per shift (8 h = 28,800 s). Each has a `meta` block (layout, arrival pattern, wave count, stochasticity, order-size weights, due-date rule, storage policy) and an `orders` list of `order_id`, `items` {article: qty}, `arrival_time` and `due_date` in seconds.
- **Designs:** `Orders/OFAT/` changes one factor at a time (order volume 500–2,000 per shift, due dates, layout, order size, stochasticity, storage policy, article distribution); `Orders/LHS/` holds 100 parameter sets × 100 replications.
- **Results:** baseline CSV/XLSX for routing (S-shape, largest gap, nearest neighbour, return) × waiting rules, including a 1–4 picker comparison in `Results/OFAT/Pickers/`.

**Known issues**

- Result CSVs use semicolons and decimal commas (`187,91`); parse with `sep=";", decimal=","`.
- Distances are in abstract length units with the depot at (0, 0); they must be scaled to metres to combine with footwear or DaRA timings.
- Most orders hold 1–3 items (weights 0.8 / 0.15 / 0.05 in the sample checked), so batching gains will look smaller than in the footwear data.
- One instance file was truncated during unpacking and has been restored and validated; all 13,438 extracted files match the archive sizes.

## Dataset 3 – DaRA (picker timing calibration)

DaRA records 18 people picking in a lab replica of an order-picking warehouse (Fraunhofer IML team) in May 2024. Its value for the twin is real pick-to-pick times: median 35 s between confirmed picks.

- **`WMS__movement_data.csv`:** 540 rows = 270 picks, each logged as a pair (stock out of a rack location, into a tote at `PIK`). 18 subjects × 15 picks, 6 sessions, 15 items, 15 rack locations (`R1.1.6.A` = rack.section.level.slot), second-resolution timestamps from 22–24 May 2024.
- **Pick-to-pick time:** median 35 s, mean 49 s, interquartile range 25–56 s, max 342 s (252 gaps).
- **`Documentation.pdf`:** floor plan of the replica (8 rack blocks, 5 aisles) and item master data (storage location, dimensions, weight). Use it to turn the gaps into walking speed plus per-pick handling time.
- **BLE and video label folders:** frame-level labels per subject for walking, standing, handling, location (aisle, cross aisle) and order. Useful if you want to split the 35 s into walking and picking.

**Known issues**

- A small lab warehouse with planned errors and learning effects; treat it as a calibration source, not as operational data.
- Only quantities move per row; filter `Moved Quantity < 0` to get one row per pick.
- Dates are `dd.mm.yy HH:MM:SS`. The `stockPositionRef.containerCode` column is empty on the rack-side row of each pair by design.
- The annotation CSVs are one-hot columns per label (for example `CL017|Step`); they are large (5 GB unpacked) — load only the subjects and label groups you need.

## Dataset 4 – RMFS (optional, only if the topic changes)

Keep this aside unless the group switches to robots carrying shelves to stationary pickers. It has no human picker routing, no timestamps and no real orders.

- Three scenarios: 4 stations / 160 pods / 20 robots on a 20×10 grid, and two 8-station / 320-pod / 30-robot cases at 80% and 90% occupancy.
- `RMFS_*_layout.txt`: tab-separated `Type, ID, X, Y` for stations, robot bases and storage spots.
- `Info_Pod_*.txt`: one number per line, reshaped to pods × 100 cargo types.
- `Total_Info_long*.txt`: space-separated, 100 values (one per cargo type) per line, 124 lines in the file checked; the README reshapes it to stations × (100 × orders); files 1–25 are test, 26–100 train.
- Values are written as floats in scientific notation (`2.0e+01`); cast to integers when cleaning.

## Congestion: validation targets, not a dataset

No public dataset records picker blocking, so the twin has to simulate it. Check the simulated delays against the one large real-warehouse study, [Koreis & Klumpp, Int. J. Production Economics, 2026](https://re.public.polimi.it/retrieve/2a5f5969-6072-4ad1-93b5-c8e1db8a9c4d/IJPE%202026.pdf), whose raw data is confidential.

| Measure (German grocery retailer, 490,398 pick events, 205 pickers, 2023) | Reported value |
| --- | --- |
| Extra task time from pick-column blocking (pickers at the same or adjacent slot) | +9.4% |
| Extra task time from within-aisle blocking (picker ahead on the same side) | +6.0% |
| Aisle studied | 3.85 m wide, 120 pick locations 0.8 m apart, U-shaped routing |
| Suggested hotspot flag | blocking on more than 20–30% of picks, or more than 5–7 s delay per blocked pick |

Also missing from every dataset: aisle widths for the footwear warehouse, picker walking speed (derive it from DaRA) and continuous picker trajectories.

## Cleaning checklist (in priority order)

- [ ] Footwear: load every CSV with the right separator, strip the byte-order mark and trailing spaces, parse `creationDate` as `dd/mm/yyyy HH:MM`.
- [ ] Footwear: drop the 2,559 duplicate order lines; decide on the 33 zero-quantity and 16 no-size lines (drop or flag).
- [ ] Footwear: fix the coordinate unit using `Full layout.dwg`, then build the aisle graph from `Storage_Location.csv` + `Support_Points_Navigation.csv` with the I/O point at CC-08.
- [ ] Footwear: map or flag the 22 pick locations missing from `Storage_Location.csv`.
- [ ] Footwear: reconcile orders against picks (13,003-unit gap, 77 waves with no picks) and document the rule you chose.
- [ ] Footwear: confirm the three `Size (US)` scales and the meaning of the value in the storage-policy files.
- [ ] Footwear: export a tidy order-line table (order, SKU, size, qty, timestamp, wave, operator, x, y, z) as the twin's main input.
- [ ] DaRA: keep one row per pick, compute per-subject gaps, and split walking from handling time using the floor plan.
- [ ] KIT: install `networkx`, load one layout and one shift per OFAT folder, and scale abstract units to metres.
- [ ] KIT: parse result CSVs with `sep=";", decimal=","` so baselines can be compared later.
- [ ] RMFS: only if the topic changes — reshape the matrices as in its README and cast to integers.

**Package notes**

- Cite every dataset you use with the DOIs in the summary table. Footwear, KIT and RMFS are CC BY 4.0; DaRA is CC BY-NC 4.0, which is fine for coursework and academic papers but not for commercial use.
- Hand the modelling team the `clean/` folders plus a short note of every rule you applied (what you dropped, how you fixed units). The section below lists what they expect to receive.

## Next steps for the modelling team (digital twin build)

The twin is a discrete-event simulation of the footwear warehouse that tests batching, routing and wave-release policies with several pickers sharing aisles. Build it from the clean tables below, in the order listed.

**What cleaning hands over**

| Clean table | Built from | Columns | Used for |
| --- | --- | --- | --- |
| `orders_clean.csv` | Footwear `Customer_Order.csv` | order_id, sku, size, qty, created_at, wave_id, operator | Demand stream and peak scenarios |
| `picks_clean.csv` | Footwear `Picking_Wave.csv` | wave_id, sku, size, qty, location, operator | Replaying the real waves as the baseline |
| `slots.csv` | `Storage_Location.csv` + storage-policy files | location, aisle, x_m, y_m, level, sku per policy | Layout and storage policies |
| `nav_nodes.csv`, `nav_edges.csv` | Support points + slot coordinates | node, x_m, y_m; from, to, length_m, aisle_id | Travel distances and aisle conflicts |
| `picker_timing.csv` | DaRA | walking speed (m/s), handling time per pick (s), as distributions | The twin's time model |
| `kit_scenarios/` | KIT orders + layouts | order_id, items, arrival_s, due_s, layout scaled to metres | Stress tests and a second test set |

**Build order** (step numbers refer to the methodology in the idea brief)

1. Layout graph and shortest-path distance matrix from the slot and navigation tables, e.g. with NetworkX (step 1).
2. Order encoding: slot location, size, ABC class, and a due time set as creation time plus a service window the group chooses (step 2).
3. Baselines: first-come-first-served batching by creation time with S-shape and largest-gap routing. First replay the real waves from `picks_clean.csv` to check the twin reproduces them. KIT's open-source `ware_ops_algos` repository already implements these heuristics (step 3).
4. Simulation core, e.g. in SimPy: pickers with a cart limit (real waves hold at most 30 lines), a no-passing rule inside aisles, and a delay whenever two pickers share a sub-aisle. The real data shows a median of 7 operators and 48 waves per day.
5. Optimiser: congestion-aware batching and routing (a metaheuristic or reinforcement learning), scored inside the twin (step 4).
6. KPIs: total travel distance, order completion time, wave makespan, blocking count and delay, workload balance across pickers (step 5).
7. Experiments: static versus adaptive wave release (step 6), then peak bursts replaying the real 07:00 surges, such as 2 Oct 2023 with 683 orders in one hour, and KIT's high-volume, high-variability sets (step 7).

**Validation**

- Timing: after scaling, simulated time between picks should fall in DaRA's range (median 35 s, middle half 25–56 s).
- Congestion: simulated blocking delay should land near the real-warehouse figures above (+9.4% pick-column, +6.0% within-aisle).
- Generalisation: rerun the best policy on KIT layouts and compare it with KIT's published baseline results.

**Decisions the group must make before modelling**

- [ ] Aisle width: narrow (no passing) or wide, based on `Full layout.dwg`.
- [ ] Number of pickers per shift in the experiments (real data: 5–8 on most days, at most 11).
- [ ] Due-date rule for orders (the data has creation times only).
- [ ] Cart capacity in lines or units per wave.
