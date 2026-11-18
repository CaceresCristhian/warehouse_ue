"""
Root entrypoint for the IDEA 15.5 Stage 1 Multi-Dataset Cleaning Pipeline.
Runs the 4-dataset raw-to-clean pipeline (Footwear, KIT, DaRA, RMFS) and
synchronizes all 23 cleaned CSV and JSON report artifacts into data/clean/.
"""

from src.clean_data import main

if __name__ == "__main__":
    main()
