# Rules for agents (and humans) working in this repo

This file is read by Claude Code, Codex, Cursor and similar tools. It exists
because coding agents reliably overcomplicate Prefect deployments. Follow it.

## prefect.yaml

1. **No `build:` or `push:` sections. Ever.** CI builds and pushes images
   (`.github/workflows/deploy-release.yml`). The image tag reaches prefect.yaml
   through the `$IMAGE` environment variable. Do not add
   `prefect_docker.deployments.steps.build_docker_image` or anything like it.
2. **No helper scripts to "generate" prefect.yaml.** It is a static file. If you
   think it needs templating, you want a `definitions:` anchor or an
   `{{ $ENV_VAR }}` reference, both of which already exist in the file.
3. **One deployment block per (flow, work pool) pair.** Name it after the pool
   or the variant (`process`, `modal-git`, `modal-image`). Reuse the anchors in
   `definitions:` for pools and pull steps rather than copying blocks.
4. **Entrypoints are repo-relative paths**:
   `packages/<pkg>/src/<module>/flows.py:<flow_function>`. The function name must
   match the `def`. `scripts/check_prefect_yaml.py` enforces this in CI.
5. **Nothing environment-specific in the file.** Workspace and credentials come
   from `PREFECT_API_URL` / `PREFECT_API_KEY` in the environment. The same file
   deploys to dev, staging and production.
6. **Pull steps decide how code arrives.** Three patterns, already defined:
   `pull_git` (clone only), `pull_git_install` (clone + `uv sync`), `pull_image`
   (code is in the image). Pick one; do not invent a fourth.
7. Deploy with plain `prefect deploy --all` or `prefect deploy --name flow/deployment`.
   Do not use `PrefectHQ/actions-prefect-deploy`; it supports a single
   `pyproject.toml` and this repo has several.

## Python packages

- This is a **uv workspace**. Each flow package lives in `packages/<name>/` with
  its own `pyproject.toml`. Shared code goes in `packages/common`.
- Add a new workload by copying `packages/canary`, renaming the module, and
  adding a deployment block. Register it in the root `pyproject.toml`
  `dependencies` and `[tool.uv.sources]`.
- Heavy optional deps (torch) go behind an **extra** (`starter-gpu[gpu]`) so
  tests and the canary never install them. Import them inside the task that
  needs them, not at module top level.
- Flows and tasks are plain functions with type hints and defaults. No classes,
  no decorators beyond `@flow` / `@task`, no custom runners unless asked.
- **Outputs are run-scoped.** Use `starter_common.run_scoped_prefix` so re-runs
  never overwrite earlier results. Expose an `output_override` parameter for
  intentional reuse.

## CI/CD

- `ci.yml` runs on PRs: ruff, pytest, prefect.yaml validation, image build
  without push. It never touches Prefect Cloud.
- `deploy-canary.yml` runs on push to main: deploys the canary and runs it with
  `--watch`. A failing canary means the deploy path is broken.
- `deploy-release.yml` runs on `v*` tags: builds the image once, then
  `prefect deploy --all` into each GitHub Environment's workspace.
- Secrets are **GitHub Environment secrets**, one set per workspace, from a
  Prefect **service account**, never a personal key.

## Monitoring

- There is **no heartbeat flow**. Prefect marks work pools not ready and
  deployments not ready on the server when workers stop polling. Scheduled runs
  queue and go Late; they are not lost.
- Alerts are automations on those built-in signals. They are created by
  `scripts/setup_automations.py`. Change alerting there, not in flow code.

## When in doubt

Make the smallest change that works and stop. Do not add retries, caching,
result persistence, custom logging, or Makefiles unless the task asks for them.
