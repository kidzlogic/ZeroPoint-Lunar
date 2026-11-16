"""Launch the Zero-Point Lunar web application without rewriting project files."""
import os
import runpy
from pathlib import Path


if __name__ == "__main__":
    project_dir = Path(__file__).resolve().parent
    os.chdir(project_dir)
    runpy.run_path(str(project_dir / "lunar_web_app.py"), run_name="__main__")
