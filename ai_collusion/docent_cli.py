"""Docent client helpers used by the color game uploader (experiments.color_game.docent_sync).

Needs DOCENT_API_KEY in the environment (or in a .env next to pyproject.toml).
"""
from __future__ import annotations

import os


def make_client():
    from .runner import load_repo_env

    load_repo_env()
    key = os.getenv("DOCENT_API_KEY")
    from docent import Docent
    return Docent(api_key=key) if key else Docent()


def resolve_collection_id(client, name: str) -> str:
    matching = [c for c in client.list_collections() if c["name"] == name]
    if not matching:
        return client.create_collection(name=name, description="")
    if len(matching) == 1:
        return matching[0]["id"]
    raise SystemExit(f"multiple collections named {name!r}; pass --collection-id")
