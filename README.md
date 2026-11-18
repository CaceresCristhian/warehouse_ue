# Warehouse Digital Twin & Congestion-Aware Optimization (CAST-Wave)

This repository implements an end-to-end multi-dataset cleaning pipeline, a discrete-event digital twin simulator, and the **CAST-Wave** (Congestion-Aware Spatio-Temporal Batching and Wave Scheduler) optimization framework for manual order-picking fulfillment in narrow-aisle multi-block distribution facilities.

## Authors
- **Cristhian David Caceres Mateus** (`cristhian.caceres@ue-germany.de`)
- **Sharique Haroon** (`sharique.haroon@ue-germany.de`)
- **Usaid Aamer** (`usaid.aamer@ue-germany.de`)
- **Grejs Ibrahimi** (`grejs.ibrahimi@ue-germany.de`)
- **Shan Faiz** (*Supervisor*, `shan.faiz@ue-germany.de`)

*Department of Business, University of Europe for Applied Sciences, Potsdam 14469, Germany.*

## Multi-Dataset Provenance & Two-Stage Cleaning Pipeline
1. **Footwear Warehouse WMS Dataset** (`data/01_raw/01_Footwear_Warehouse_2025` — de Assis et al., 2025, DOI: `10.1016/j.dib.2025.111837`):
   - **Stage 1 (`src/clean_data.py` / `clean_data.py`)**: Audits 122,370 raw order lines, drops 2,559 exact 9-field duplicates, yields 119,811 clean order lines across 32,634 orders and 215,192 picks across 2,292 storage positions (narrowing the order-to-pick gap from 13,003 units to 268 units), classifies shoe size scales (`us`, `us_x10`, `mm`), melts the 4 storage-policy tables, and constructs the 44-node, 68-edge topological navigation network (`CC-08` depot).
   - **Stage 2 (`src/data_preprocessing.py`)**: Resolves the 22 unlisted staging/overflow and extended-bay locations (`RC-*`, `EX-*`, `C-*`, `ZN-COR`, `E-25-20`..`K-26-20`), maps SKU ABC velocity classes, and compiles validated Parquet tables into `data/02_processed/`.
2. **KIT Manual Order-Picking Benchmark** (`data/01_raw/02_KIT_Benchmark_2026` — Barlang et al., 2026, DOI: `10.35097/mwsv59v8sk9sqaan`):
   - Flattens 50 representative LHS/OFAT instances (49,615 order-item rows in `kit_scenarios_flat.csv`) and normalizes 1,591 baseline OFAT result rows (`kit_results_flat.csv`).
3. **DaRA Picker Timing & Activity Dataset** (`data/01_raw/03_DaRA_2026` — Niemann et al., 2026, DOI: `10.3390/s26020739`):
   - Extracts 270 rack stock-out picks from 540 WMS movement rows across 18 human subjects, yielding 257 valid inter-pick intervals (`36.0 s` median gap, IQR `26.0–59.0 s`) and calibrating the digital twin's empirical pick handling dwell time (`12.6 s` median).
4. **RMFS Robotic Pod Dataset** (`data/01_raw/04_RMFS_2026` — optional archive, DOI: `10.17632/tp6jnzwgzm.1`):
   - Cleans and reshapes 3 robotic pod layouts (`205–409` nodes) and long-format pod inventory tables (`3,342–7,552` entries).

## Project Structure
- `CLEANING_LOG.md`: Master audit log detailing Stage 1 data cleaning metrics and Stage 2 modelling checklist resolutions.
- `clean_data.py`: Root entrypoint for the Stage 1 multi-dataset raw-to-clean pipeline.
- `data/00_Handover/`: Dataset handover documentation (`IDEA15.5_Dataset_Handover.pdf`, `.md`, `.docx`, `README.txt`).
- `data/01_raw/`: Raw datasets across all 4 sources (`01_Footwear_Warehouse_2025`, `02_KIT_Benchmark_2026`, `03_DaRA_2026`, `04_RMFS_2026`).
- `data/clean/`: All 23 cleaned CSV tables and JSON audit reports across all 4 datasets.
- `data/02_processed/`: Validated Parquet tables with verified metric coordinates for the Digital Twin.
- `src/clean_data.py`: Stage 1 raw-to-clean auditing script across all 4 datasets.
- `src/data_preprocessing.py`: Stage 2 coordinate reconciliation and Parquet indexing pipeline.
- `src/digital_twin/`: Topological graph (`warehouse_graph.py`) and continuous-time discrete-event simulator (`simulation_engine.py`).
- `src/optimization/`: Baseline heuristics (`baselines.py`) and the proposed **CAST-Wave** optimizer (`cast_wave_optimizer.py`).
- `src/evaluation/`: Benchmark execution (`benchmark_runner.py`), 5-stage component ablation (`run_component_ablation.py`), and dynamic LaTeX macro/figure generator (`generate_visualizations.py`).
- `experiments/`: Synchronized benchmark and ablation output CSV tables.
- `paper/`: IEEE conference manuscript (`main.tex`), dynamic macros (`tables/macros.tex`), auto-generated LaTeX tables (`tables/table1`–`table3`), and vector figures (`figures/`).
- `docs/`: Block-by-block technical code walkthrough and model rationale (`Code_Explanation_and_Model_Rationale.tex` & `.pdf`).
- `tests/`: Automated unit and regression test suite (`test_pipeline.py`).

## Quick Start & End-to-End Execution
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run Stage 1 raw-to-clean data audit & synchronization
python -m src.clean_data

# 3. Run Stage 2 coordinate reconciliation & Parquet preprocessing
python -m src.data_preprocessing

# 4. Re-run 100-wave empirical benchmark & dense-wave fleet scalability ablation
python -m src.evaluation.benchmark_runner

# 5. Re-run 5-stage component-by-component ablation
python -m src.evaluation.run_component_ablation

# 6. Regenerate publication figures, tables, and dynamic LaTeX macros
python -m src.evaluation.generate_visualizations

# 7. Run automated verification test suite
pytest tests/test_pipeline.py -v
```
