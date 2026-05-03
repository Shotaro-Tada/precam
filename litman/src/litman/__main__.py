import sys
import subprocess
from pathlib import Path


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "gui":
        project_root = Path(__file__).resolve().parent.parent.parent
        gui_path = Path(__file__).parent / "gui.py"
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(gui_path)] + sys.argv[2:],
            cwd=str(project_root),
        )
    else:
        from .cli import cli
        cli()


if __name__ == "__main__":
    main()
