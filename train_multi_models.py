"""Compatibility entrypoint for training the data-backed lunar image classifier.

The current dataset has no coordinate, thermal-risk, or dust-plume labels, so this
script intentionally does not generate geolocation or risk models from synthetic data.
"""
import os
import runpy
from pathlib import Path


if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    runpy.run_path(str(project_dir / "train.py"), run_name="__main__")
