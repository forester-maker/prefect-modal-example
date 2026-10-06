# Image for the "modal-image" deployment (and any other image-based pool).
# Built and pushed by CI. Never built from inside prefect.yaml.
#
#   docker build -t prefect-modal-starter:dev .
#
# torch pulls CUDA wheels on linux, so this image is several GB. That is the
# price of a sub-second cold start on Modal versus installing torch per run.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV UV_PROJECT_ENVIRONMENT=/usr/local \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependency layer first so code changes do not invalidate the torch download.
COPY pyproject.toml uv.lock ./
COPY packages/common/pyproject.toml packages/common/
COPY packages/canary/pyproject.toml packages/canary/
COPY packages/gpu_workload/pyproject.toml packages/gpu_workload/
RUN uv sync --frozen --no-dev --no-install-workspace --extra gpu

# Now the code. Entrypoints in prefect.yaml are paths relative to /app.
COPY packages ./packages
RUN uv sync --frozen --no-dev --no-editable --extra gpu
