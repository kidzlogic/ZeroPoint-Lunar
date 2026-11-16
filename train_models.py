"""Compatibility entrypoint for training the project lunar image model."""
import os
import runpy
from pathlib import Path


if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    runpy.run_path(str(project_dir / "train.py"), run_name="__main__")
