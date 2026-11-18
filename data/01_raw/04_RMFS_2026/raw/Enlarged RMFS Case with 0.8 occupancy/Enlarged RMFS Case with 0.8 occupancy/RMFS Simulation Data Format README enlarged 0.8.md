# RMFS Simulation Data Format README

This repository contains two core types of data files used for initializing the RMFS (Robotic Mobile Fulfillment System) environment: order demand data (`Total_Info_long_...txt`) and pod inventory data (`Info_Pod_long_...txt`).

## 1. Pod Inventory Data (Pod Information)
* **File Name Example**: `Info_Pod_long_0.8.txt`
* **Physical Meaning**: Records the initial inventory quantity or status of various cargo types on every physical pod in the system.

### Data Structure Analysis
In the system, this file is read and reshaped into a 2D matrix of shape `(N_pod, N_cargo_type)`:
* **Total Rows**: `320` rows. Each row represents a specific pod (Pod ID from 0 to 319).
* **Total Columns**: `100` columns. Each column represents a specific cargo type (Cargo Type ID from 0 to 99).
* **Cell Value**: The value at matrix index `(i, j)` represents **the quantity or status of the j-th cargo type on the i-th pod**.

---

## 2. Order Demand Data (Total Order Information)
* **File Name Example**: `Total_Info_long_0.8_{ii}.txt`
* **Physical Meaning**: Records the long-term sequence of order demands assigned to each picking station.

### Dataset Split (Train / Test)
The index `{ii}` in the order filename `Total_Info_long_0.8_{ii}.txt` is used to distinguish between training and testing environments:
* **Testing Set**: Files with indices from **`1` to `25`**
* **Training Set**: Files with indices from **`26` to `100`**

### Data Structure Analysis
This file is read and reshaped into a 2D matrix of shape `(N_station, N_cargo_type * N_orders)`:
* **Total Rows**: `8` rows. Each row represents a fixed picking station (Station ID from 0 to 7).
* **Total Columns**: Dynamic length. The total number of columns is `100 * number of order batches`.
* **Data Arrangement Logic**: 
    For each row (i.e., each station), the data is arranged sequentially in groups of `100` elements (`N_cargo_type`).
    * Columns `0` to `99`: The demand for the 100 cargo types in the **1st order** for this station.
    * Columns `100` to `199`: The demand for the 100 cargo types in the **2nd order for this station.
    * And so on...

---
### Core Environment Parameters Reference
Based on this dataset, the core parameters are:
* `n_cargo_type` = 100
* `n_station` = 8
* `n_pod` = 320
* `n_robot` = 30