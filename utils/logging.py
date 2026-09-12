from __future__ import annotations

import logging
import sys


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
