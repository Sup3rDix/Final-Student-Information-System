"""Launch the old-school Student Information System: python main.py"""
from pathlib import Path

from sis.app import App


if __name__ == "__main__":
    App(Path(__file__).resolve().parent / "data").run()
