"""The dated Taiwan reference sheet, distributed as package data."""

from importlib.resources import files


def load_taiwan_facts() -> str:
    return files(__package__).joinpath("taiwan.md").read_text(encoding="utf-8")
