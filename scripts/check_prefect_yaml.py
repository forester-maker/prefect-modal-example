"""Static checks for prefect.yaml. Runs in CI on every PR; no API access needed.

Checks:
  * the file parses, including YAML anchors and merge keys
  * there are no build/push sections (CI owns images; see AGENTS.md)
  * every entrypoint points at a file that exists and defines the named flow
  * deployment names are unique per flow
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    data = yaml.safe_load((ROOT / "prefect.yaml").read_text())
    problems: list[str] = []

    for banned in ("build", "push"):
        if data.get(banned):
            problems.append(
                f"top-level `{banned}:` is set; images are built by CI, not prefect.yaml"
            )

    deployments = data.get("deployments") or []
    if not deployments:
        problems.append("no deployments defined")

    seen: Counter[str] = Counter()
    for d in deployments:
        name = d.get("name", "<unnamed>")
        entrypoint = d.get("entrypoint", "")
        if ":" not in entrypoint:
            problems.append(f"{name}: entrypoint `{entrypoint}` is not path:function")
            continue
        path, func = entrypoint.rsplit(":", 1)
        file = ROOT / path
        if not file.exists():
            problems.append(f"{name}: entrypoint file {path} does not exist")
            continue
        if not re.search(rf"^def {re.escape(func)}\(", file.read_text(), re.M):
            problems.append(f"{name}: {path} has no `def {func}(`")
        seen[f"{func}/{name}"] += 1
        if not (d.get("work_pool") or {}).get("name"):
            problems.append(f"{name}: no work_pool.name")

    for key, n in seen.items():
        if n > 1:
            problems.append(f"deployment {key} defined {n} times")

    if problems:
        print("prefect.yaml problems:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print(f"prefect.yaml OK: {len(deployments)} deployments")
    for d in deployments:
        print(f"  {d['entrypoint'].rsplit(':', 1)[1]}/{d['name']}  ->  {d['work_pool']['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
