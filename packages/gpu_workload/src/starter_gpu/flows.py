"""GPU smoke test.

Runs on the Modal push work pool. It proves three things:

1. The container Modal started actually has a GPU and torch can see it.
2. Dependencies made it into the run (via the image or via ``uv sync`` at pull time).
3. Outputs land in a run-scoped location, so re-running never overwrites a prior run.

It deliberately does not load a model. Transfyr's real pipelines are the right load
test; this flow is for "does the plumbing work" on a cheap GPU in under a minute.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from prefect import flow, get_run_logger, task
from starter_common import run_scoped_prefix


@task
def check_gpu(require_gpu: bool) -> dict:
    """Report the visible accelerator. Fails if a GPU was required and none is present."""
    import torch  # imported here so the canary and tests never need torch installed

    available = torch.cuda.is_available()
    if require_gpu and not available:
        raise RuntimeError("require_gpu=True but torch.cuda.is_available() is False")

    device = torch.device("cuda" if available else "cpu")
    name = torch.cuda.get_device_name(0) if available else "cpu"
    return {"device": str(device), "name": name, "torch": torch.__version__}


@task
def matmul_benchmark(device: str, size: int) -> dict:
    """Multiply two square matrices on the device and time it."""
    import torch

    dev = torch.device(device)
    a = torch.randn(size, size, device=dev)
    b = torch.randn(size, size, device=dev)
    if dev.type == "cuda":
        torch.cuda.synchronize()
    start = time.perf_counter()
    c = a @ b
    if dev.type == "cuda":
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    return {"size": size, "seconds": round(elapsed, 4), "checksum": float(c.sum().item())}


@task
def write_result(prefix: str, payload: dict) -> str:
    """Write the result under the run-scoped prefix.

    Local filesystem here so the example has no cloud dependency. Swap ``Path`` for
    ``s3fs`` / ``boto3`` and the prefix for an ``s3://`` URI and nothing else changes.
    """
    out_dir = Path(prefix)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "result.json"
    out_file.write_text(json.dumps(payload, indent=2))
    return str(out_file)


@flow(name="gpu-smoke-test", log_prints=True)
def gpu_smoke_test(
    size: int = 4096,
    require_gpu: bool = True,
    output_base: str = "/tmp/outputs",
    output_override: str | None = None,
) -> dict:
    """Check the GPU, run one matmul, write the result to a run-scoped location.

    Args:
        size: Matrix dimension. 4096 is a few hundred ms on a T4; raise it to load-test.
        require_gpu: Fail fast if no CUDA device is visible. Set False to run on CPU
            locally or on the process pool.
        output_base: Root for outputs. Each run writes under
            ``{output_base}/{deployment}/{date}/{flow-run-id}``.
        output_override: Exact output location, bypassing the run-scoped prefix.
            Use for dry runs or to intentionally reproduce an earlier run's path.
    """
    logger = get_run_logger()
    gpu = check_gpu(require_gpu)
    logger.info("accelerator: %s", gpu)

    bench = matmul_benchmark(gpu["device"], size)
    logger.info("matmul %sx%s took %ss", size, size, bench["seconds"])

    prefix = run_scoped_prefix(output_base, output_override)
    path = write_result(prefix, {"gpu": gpu, "benchmark": bench})
    logger.info("wrote %s", path)
    return {"gpu": gpu, "benchmark": bench, "output": path}


if __name__ == "__main__":
    gpu_smoke_test(size=512, require_gpu=False)
