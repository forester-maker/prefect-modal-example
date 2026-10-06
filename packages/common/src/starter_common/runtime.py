"""Helpers that read the Prefect runtime context.

The main one, ``run_scoped_prefix``, solves a concrete problem: when you re-run a
deployment, the new run should not overwrite the previous run's outputs. Deriving
the output location from the flow run makes every run write somewhere new.
"""

from __future__ import annotations

from datetime import UTC, datetime

from prefect import runtime


def run_scoped_prefix(base: str, override: str | None = None) -> str:
    """Return an output prefix that is unique to the current flow run.

    Args:
        base: Root location, for example ``s3://my-bucket/outputs`` or ``/tmp/outputs``.
        override: If given, returned unchanged. Lets a caller point a run at a fixed
            location (a dry-run folder, a reproduction of a past run, and so on).

    Returns:
        ``{base}/{deployment-or-flow name}/{YYYY-MM-DD}/{flow-run-id}`` when running
        under a Prefect flow run. Falls back to a timestamp outside a run so the
        function is still usable from a plain ``python`` call or a unit test.
    """
    if override:
        return override.rstrip("/")

    base = base.rstrip("/")
    name = runtime.deployment.name or runtime.flow_run.flow_name or "adhoc"
    run_id = runtime.flow_run.id
    start = runtime.flow_run.scheduled_start_time or datetime.now(UTC)
    day = start.strftime("%Y-%m-%d")

    if run_id:
        return f"{base}/{name}/{day}/{run_id}"
    return f"{base}/{name}/{day}/{datetime.now(UTC).strftime('%H%M%S')}"
