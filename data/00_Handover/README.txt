IDEA 15.5 - Digital-Twin Warehouse Optimization: dataset package
Collected 16 November 2026. Unzipped size about 7 GB.

START HERE: read IDEA15.5_Dataset_Handover (PDF, Word or Markdown) in this folder.
Live, editable version: https://claude.ai/artifact/GPkWLCWWfgj9GvTPbYaXJz

Team workflow: 1) data collection (done)  2) data cleaning  3) modelling / digital twin build

FOLDER MAP
00_Handover/                     This README and the handover note (cleaning checklist + modelling steps)
01_Footwear_Warehouse_2025/raw/  CORE DATA. Real warehouse: layout, storage slots, 122,370 order lines
                                 with timestamps (Jan-Oct 2023), picking waves, operators. CC BY 4.0
                                 DOI 10.17632/pf2w725pw3.1 / Data in Brief 61 (2025) 111837
02_KIT_Benchmark_2026/raw/       13,200 synthetic order-stream instances (8-hour shifts) on
                                 rectangular layouts + baseline results. CC BY 4.0
                                 DOI 10.35097/mwsv59v8sk9sqaan
03_DaRA_2026/raw/                Lab warehouse picking with 18 people: WMS pick log (timing),
                                 floor plan/item data, BLE location data and activity labels.
                                 CC BY-NC 4.0. Zenodo record 10468175 / Sensors 26(2) 739
04_RMFS_2026/raw/                OPTIONAL. Robotic mobile fulfillment layouts, pods and order
                                 sequences; only if the topic switches to robots. CC BY 4.0
                                 DOI 10.17632/tp6jnzwgzm.1

RULES
- Never edit files in raw/. Write cleaned outputs to a new clean/ folder next to each raw/.
- Keep folder names unchanged; the handover note refers to these paths.
- Cite every dataset you use (DOIs above).
