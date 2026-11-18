# Reproducibility & Verification Log — IDEA 15.5 (Warehouse Digital Twin)

## 1. Environment & Dependencies
- **OS**: Windows 11 (`win32`)
- **Python**: 3.12.10
- **Core Libraries**: `numpy`, `pandas`, `pyarrow`, `networkx`, `scipy`, `matplotlib`, `pytest`
- **LaTeX Compiler**: `tectonic` (XeTeX + BibTeX)

## 2. Dataset Provenance & Two-Stage Cleaning Audit
See `CLEANING_LOG.md` and `data/00_Handover/IDEA15.5_Dataset_Handover.md` for full handover and cleaning checklists.

1. **Footwear Warehouse WMS Dataset** (`01_Footwear_Warehouse_2025` — de Assis et al., *Data in Brief*, Vol. 61, 111837, Aug 2025; DOI: `10.1016/j.dib.2025.111837`):
   - Raw order lines: `122,370`
   - Exact 9-field duplicates removed (`clean_data.py`): `2,559`
   - Clean order lines (`data/clean/orders_clean.csv`): `119,811` across `32,634` unique orders (`178` working days, Jan–Oct 2023).
   - Clean pick operations (`data/clean/picks_clean.csv`): `215,192` rows across `9,707` waves.
   - Order-to-pick unit reconciliation: `215,460` units ordered vs. `215,192` units picked (`268` units residual gap).
   - Storage slots (`data/clean/slots.csv`): `2,292` physical locations across 18 aisles (`A`–`R`) and 4 vertical levels (`z = 1..4`).
   - Unlisted staging/overflow pick locations (`22` codes flagged in Stage 1): Reconciled in Stage 2 (`src/data_preprocessing.py`) to central I/O staging buffer `CC-08` (`32.24 m, 50.48 m`) and corresponding aisle bays (`100%` valid metric coordinates across all `215,192` picks).
   - Navigation graph (`data/clean/nav_nodes.csv`, `data/clean/nav_edges.csv`): `44` corridor nodes (`LC`, `CC`, `RC`), `68` metric edges (`0.08 m/unit` scale factor), central I/O depot at `CC-08` (`32.24 m, 50.48 m`).
2. **DaRA Picker Timing Dataset** (`03_DaRA_2026` — Niemann et al., *Sensors*, Vol. 26, No. 2, 739, Jan 2026; DOI: `10.3390/s26020739`):
   - Raw WMS movement rows: `540` (`270` stock-out picks across `18` subjects).
   - Valid inter-pick intervals (`data/clean/picker_timing.csv`): `257` gaps; median `36.0 s`, mean `54.0 s`, IQR `26.0–59.0 s`.
   - Calibrated pick handling dwell duration: `12.6 s` median (IQR: `9.1–20.6 s`).
3. **KIT Order-Picking Benchmark** (`02_KIT_Benchmark_2026` — Barlang et al., RADAR4KIT, Apr 2026; DOI: `10.35097/mwsv59v8sk9sqaan`):
   - Sampled flat scenario items (`data/clean/kit_scenarios_flat.csv`): `49,615` rows across `50` instances.
   - Consolidated OFAT baseline results (`data/clean/kit_results_flat.csv`): `1,591` rows.
4. **RMFS Robotic Pod Dataset** (`04_RMFS_2026` — optional archive, Jul 2026; DOI: `10.17632/tp6jnzwgzm.1`):
   - Cleaned layouts (`rmfs_layout_large.csv`, `rmfs_layout_enlarged_08.csv`, `rmfs_layout_enlarged_09.csv`: `205`, `409`, `409` rows) and melted pod inventories (`3,342`, `7,016`, `7,552` non-zero entries).

## 3. Pipeline Execution Steps
```powershell
# Step 1 (Stage 1): Clean raw datasets and sync 23 clean CSV/JSON artifacts into data/clean/
python -m src.clean_data

# Step 2 (Stage 2): Reconcile coordinates and compile validated Parquet tables in data/02_processed/
python -m src.data_preprocessing

# Step 3: Run 100-wave historical benchmark and dense-wave fleet scalability ablation
python -m src.evaluation.benchmark_runner

# Step 4: Run 6-variant component-by-component ablation
python -m src.evaluation.run_component_ablation

# Step 5: Generate vector figures, dynamic LaTeX tables, and macros.tex
python -m src.evaluation.generate_visualizations

# Step 6: Execute automated pytest suite (15/15 tests passing)
pytest tests/test_pipeline.py -v
```

## 4. Key Experimental Results (N = 100 Historical Waves, P = 4 Pickers, DaRA 12.6s Dwell)
- **Fair FCFS + S-Shape (Honest Baseline)**: Makespan = `7.26 ± 1.79 min`, Distance = `830.3 m`, Blocked Time = `404.2 s`, Workload CV = `0.163`, Runtime = `0.04 ms/wave`
- **Fair FCFS + Largest-Gap**: Makespan = `7.29 ± 1.79 min`, Distance = `831.1 m`, Blocked Time = `406.7 s`, Workload CV = `0.163`
- **Fair FCFS + Static 2-Opt TSP**: Makespan = `6.93 ± 1.70 min`, Distance = `807.7 m`, Blocked Time = `380.0 s`, Workload CV = `0.147`, Runtime = `2.65 ms/wave`
- **Balanced LPT + Static 2-Opt TSP**: Makespan = `6.93 ± 1.70 min`, Distance = `807.7 m`, Blocked Time = `380.0 s`, Workload CV = `0.147` (100/100 waves identical to Round-Robin due to `q = 1` single-pair footwear lines)
- **Sector Clustering + Static 2-Opt TSP**: Makespan = `5.37 ± 1.21 min`, Distance = `621.4 m`, Blocked Time = `168.7 s`, Workload CV = `0.211` (-26.1% makespan reduction vs. fair baseline; accounts for 98% of the total makespan reduction)
- **Full CAST-Wave (Proposed, λ = 15.0 m)**: Makespan = `5.32 ± 1.18 min`, Distance = `624.8 m`, Blocked Time = `158.6 s`, Workload CV = `0.212`, Runtime = `2.56 ms/wave` (max `6.34 ms`)
- **Relative Gains vs Fair FCFS S-Shape**:
  - `-26.7%` makespan reduction (`t = 14.26, p = 9.73e-26, Wilcoxon W = 36.0, p = 1.78e-16, Cohen dz = -1.43`)
  - `-24.8%` fleet travel distance reduction (`830.3 m -> 624.8 m`)
  - `-60.8%` narrow-aisle blocked queuing delay reduction (`404.2 s -> 158.6 s`)
  - `90` wins, `3` losses, `7` ties across 100 operational waves
- **Audited Legacy Single-Picker FCFS Baseline (P_eff = 1)**:
  - Makespan = `11.74 ± 2.39 min`, Distance = `449.9 m`, Workload CV = `1.732` (explaining why early drafts reported an inflated -36.8% gain)
- **Dense Operational Waves (20 Waves, Mean 46.6 picks, P ∈ {2, 4, 6, 8, 10, 12})**:
  - `P = 2`: FCFS `15.25 min` (`274.7 s` blk) | Sector `13.38 min` (`64.9 s` blk) | CAST-Wave `13.32 min` (`49.8 s` blk)
  - `P = 4`: FCFS `11.26 min` (`589.6 s` blk) | Sector `8.47 min` (`162.3 s` blk) | CAST-Wave `8.48 min` (`157.0 s` blk)
  - `P = 6`: FCFS `9.71 min` (`835.3 s` blk) | Sector `6.90 min` (`298.0 s` blk) | CAST-Wave `7.09 min` (`279.9 s` blk)
  - `P = 8`: FCFS `8.50 min` (`1,000.3 s` blk) | Sector `6.26 min` (`416.3 s` blk) | CAST-Wave `6.37 min` (`402.5 s` blk)
  - `P = 10`: FCFS `7.85 min` (`1,165.2 s` blk) | Sector `5.42 min` (`463.6 s` blk) | CAST-Wave `5.67 min` (`476.2 s` blk)
  - `P = 12`: FCFS `7.01 min` (`1,273.3 s` blk) | Sector `5.13 min` (`548.7 s` blk) | CAST-Wave `5.43 min` (`593.7 s` blk)
