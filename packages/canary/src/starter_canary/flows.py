"""Canary flow.

Deployed on every push to ``main`` and immediately run by CI. If this flow cannot be
deployed, scheduled, picked up, and completed, the deploy pipeline is broken. That is
the whole point: a cheap end-to-end check that CI can still reach Prefect Cloud and
that the work pool can still execute work.

Ongoing health of the pool itself is handled by Prefect's built-in work pool status and
the automations in ``scripts/setup_automations.py``, not by this flow.
"""

from __future__ import annotations

import platform
import sys

from prefect import flow, get_run_logger, runtime


@flow(name="canary", log_prints=True)
def canary(greeting: str = "hello") -> dict[str, str]:
    """Log where and how this run executed, then exit cleanly."""
    logger = get_run_logger()
    info = {
        "greeting": greeting,
        "python": sys.version.split()[0],
        "host": platform.node(),
        "flow_run_id": str(runtime.flow_run.id),
        "deployment": runtime.deployment.name or "(none, ran locally)",
        "ui_url": runtime.flow_run.ui_url or "(not connected to an API)",
    }
    for key, value in info.items():
        logger.info("%s=%s", key, value)
    return info


if __name__ == "__main__":
    canary()
