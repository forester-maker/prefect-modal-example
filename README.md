# prefect-modal-starter

A small, forkable Prefect Cloud setup with the shape of a real one:

- **uv workspace** with several packages, each with its own `pyproject.toml`
- **two work pools**: a process pool you run anywhere, and a **Modal push pool**
  that needs no worker and gives you GPUs on demand
- **Docker image built by CI, not by prefect.yaml**, with the tag passed in at
  deploy time
- **GitHub Actions**: PR checks, a push-to-main canary that deploys *and runs* a
  flow, and tag-based releases fanned out to dev / staging / production
  workspaces through GitHub Environments
- **alerts as code** on Prefect's built-in work pool and flow run signals
- an `AGENTS.md` so your coding agents stop overcomplicating `prefect.yaml`

Nothing here is clever. That is the point: fork it, swap the flows, keep the plumbing.

## Layout

```
.
├── prefect.yaml                  # all deployments; no build/push sections
├── Dockerfile                    # image for the modal-image deployment
├── pyproject.toml                # uv workspace root
├── packages/
│   ├── common/                   # starter_common: run_scoped_prefix()
│   ├── canary/                   # starter_canary: tiny flow CI deploys + runs
│   └── gpu_workload/             # starter_gpu: torch smoke test for Modal
├── scripts/
│   ├── setup_work_pools.sh       # create starter-process + starter-modal
│   ├── setup_automations.py      # Slack alerts on pool/run signals
│   └── check_prefect_yaml.py     # static validation, runs in CI
├── tests/
├── .github/workflows/
│   ├── ci.yml                    # PR: ruff, pytest, yaml check, image build
│   ├── deploy-canary.yml         # main: deploy canary, run it, wait
│   └── deploy-release.yml        # v* tag: build+push image, deploy all envs
└── AGENTS.md                     # rules for coding agents
```

## Quick start (15 minutes, no registry, no Docker)

Prereqs: [uv](https://docs.astral.sh/uv/), a Prefect Cloud workspace, and for
the GPU part a [Modal](https://modal.com) account.

```bash
git clone https://github.com/forester-maker/prefect-modal-starter
cd prefect-modal-starter
uv sync
uv run prefect cloud login            # pick the workspace to deploy into
```

**1. Run a flow locally** (no deployment, no pool):

```bash
uv run python packages/canary/src/starter_canary/flows.py
```

**2. Create the work pools.** The Modal step needs `modal token new` done once
on your machine, or `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` in the environment.

```bash
./scripts/setup_work_pools.sh
```

It also prints the job variables the Modal pool accepts (gpu, cpu, memory,
image, env, and so on).

**3. Deploy.** Two environment variables tell the pull steps where the code is:

```bash
export REPO_URL=https://github.com/<you>/prefect-modal-starter
export REPO_BRANCH=main
uv run prefect --no-prompt deploy --all
```

`--no-prompt` skips the interactive questions `prefect deploy` otherwise asks; CI
uses it too. `IMAGE` is unset, so the `modal-image` deployment is created with an empty image
and will fail if run. That is expected until CI builds one (see Releases).

**4. Run the canary on the process pool.** In one terminal:

```bash
uv run prefect worker start --pool starter-process
```

In another:

```bash
uv run prefect deployment run canary/process --watch
```

**5. Run the GPU smoke test on Modal.** No worker needed. The first run clones
the repo into a Modal container and installs torch with uv, so it takes a few
minutes (the deployment's `timeout` is set to 30 min to allow for it); later runs
reuse Modal's cache.

```bash
uv run prefect deployment run gpu-smoke-test/modal-git --watch
```

You should see the device name (a T4 by default), a matmul timing, and an output
path like `/tmp/outputs/modal-git/2026-10-06/<flow-run-id>/result.json`. Run it
again and the path changes. That is `run_scoped_prefix` doing its job.

## The pieces

### prefect.yaml

Read it top to bottom; it is commented. Things worth noticing:

- `definitions:` holds anchors for the two pools and three pull strategies.
  Deployments compose them with `*anchor` and `<<: *anchor`.
- `{{ $REPO_URL }}`, `{{ $REPO_BRANCH }}` and `{{ $IMAGE }}` are resolved from
  the environment **when you run `prefect deploy`**. CI sets them; locally you do.
- There is no `build:` and no `push:`. See [Why no Docker build in
  prefect.yaml](#why-no-docker-build-in-prefectyaml).

| Deployment                  | Pool            | Code arrives via            | Use it for                              |
|-----------------------------|-----------------|-----------------------------|-----------------------------------------|
| `canary/process`            | starter-process | git clone                   | CI canary when you run workers          |
| `canary/modal`              | starter-modal   | git clone + uv sync         | CI canary with zero infrastructure      |
| `gpu-smoke-test/modal-git`  | starter-modal   | git clone + uv sync (torch) | first GPU run, no registry              |
| `gpu-smoke-test/modal-image`| starter-modal   | baked into `$IMAGE`         | production; fast cold start             |
| `gpu-smoke-test/process-cpu`| starter-process | git clone                   | laptop check of the flow logic          |

### Modal job variables

Set per deployment under `work_pool.job_variables`. From the Modal push pool's
base job template:

| Variable           | Type    | Notes                                                        |
|--------------------|---------|--------------------------------------------------------------|
| `gpu`              | string  | `T4`, `A10G`, `A100`, `H100`, ... Modal's GPU names          |
| `cpu`              | number  | vCPUs                                                        |
| `memory`           | integer | MiB                                                          |
| `image`            | string  | container image; default is a stock Prefect image            |
| `env`              | object  | environment variables                                        |
| `timeout`          | integer | seconds. **Default 300.** Set it for anything longer.        |
| `pip_packages`     | array   | extra packages installed at start (prefer the image)         |
| `secrets`          | array   | Modal secret names                                           |
| `command`          | string  | override the container command                               |
| `proxy`            | string  | Modal proxy name                                             |
| `environment_name` | string  | Modal environment                                            |
| `modal_credentials`| block   | set once on the pool by `--provision-infra`                  |

The 300-second default `timeout` is the one that bites: a 4-hour training run
on the default dies at 5 minutes. Every Modal deployment in this repo sets it
explicitly. Print the live template any time with:

```bash
uv run prefect work-pool get-default-base-job-template --type modal:push
```

### Two ways to get code onto Modal

**Pull from git at run time** (`modal-git`). Modal starts a stock Prefect
image, clones this repo, runs `uv sync --extra gpu`. Zero build infrastructure.
Slow first start because torch is large. Fine for a POC; not what you want
behind a 100-job backlog.

**Pre-built image** (`modal-image`). CI builds the `Dockerfile`, pushes it to
GHCR, and passes the tag as `$IMAGE` to `prefect deploy`. Cold start is just
the container pull. This is the production path. To use ECR instead, set the
`IMAGE_REGISTRY` repository variable and replace the login step in
`deploy-release.yml` with
[`aws-actions/amazon-ecr-login`](https://github.com/aws-actions/amazon-ecr-login).

### Run-scoped outputs

`starter_common.run_scoped_prefix(base)` returns
`{base}/{deployment}/{YYYY-MM-DD}/{flow-run-id}`. Every run writes somewhere
new, so re-running a deployment for a test never clobbers a previous result.
Pass `output_override=` to reuse a specific location on purpose. The smoke test
writes to the local filesystem; swap in an `s3://` base and `s3fs`/`boto3`
and nothing else changes.

## CI/CD

### Pull request → `ci.yml`

Ruff, pytest, `scripts/check_prefect_yaml.py`, and a Docker build with
`push: false`. Nothing contacts Prefect Cloud. You can see the image build but
nothing is deployed, which is the "build but don't deploy on PR" behaviour that
is awkward to get from prefect.yaml build steps.

### Push to main → `deploy-canary.yml`

Deploys `canary/process` and `canary/modal`, then runs one of them with
`--watch` and fails the workflow if it does not complete. This is your
"is this thing on" check: it proves CI can authenticate, `prefect deploy`
works, and the pool can execute. Real flows deploy less often (on tags), so this
keeps the path exercised between releases.

Knobs (repository **Variables**, not secrets):

| Variable             | Default          | Meaning                                                        |
|----------------------|------------------|----------------------------------------------------------------|
| `CANARY_DEPLOYMENT`  | `canary/process` | Set to `canary/modal` if you do not run a process worker       |
| `CANARY_TIMEOUT_MIN` | `10`             | How long to wait for the run                                   |

### Tag `v*` → `deploy-release.yml`

1. Build the image once, push to `ghcr.io/<owner>/prefect-modal-starter:<tag>`.
2. For each GitHub Environment in `DEPLOY_ENVIRONMENTS` (default
   `["dev","staging","production"]`), run `prefect deploy --all` with that
   environment's secrets and `IMAGE` set to the tag from step 1.

Because each environment is a separate Cloud workspace, one `prefect.yaml`
serves all of them. Put **required reviewers** on the `production` environment
(Settings → Environments → production) and the production job pauses for
approval while dev and staging go ahead. That is your release gate without
Terraform.

```bash
git tag v0.1.0 && git push origin v0.1.0
```

### Secrets

Create one GitHub Environment per workspace: `dev`, `staging`, `production`
(add more for per-customer workspaces; list them in `DEPLOY_ENVIRONMENTS`).
Each needs two secrets:

| Secret            | Value                                                                   |
|-------------------|-------------------------------------------------------------------------|
| `PREFECT_API_URL` | `https://api.prefect.cloud/api/accounts/<acct>/workspaces/<ws>`         |
| `PREFECT_API_KEY` | an API key from a **service account** with Developer role on that workspace |

Use a service account, not a personal key: it survives people leaving, and it
shows up in the audit log as "CI", not as a person. For your very first run a
personal key is fine; swap it before anyone depends on this.

The image push uses the built-in `GITHUB_TOKEN`; no extra secret.

## Alerts

Prefect already knows when a work pool has no worker, when a deployment is no
longer being polled, and when a scheduled run is Late. A flow cannot tell you
its own worker is dead. So there is no heartbeat flow here. Instead,
`scripts/setup_automations.py` creates three automations on the built-in
signals and sends them to a Slack webhook:

| Automation                       | Fires when                                                              |
|----------------------------------|-------------------------------------------------------------------------|
| `starter: work pool not ready`   | the process pool has no online worker                                   |
| `starter: flow run crashed`      | any run enters Crashed (infra died, as opposed to a Python exception)   |
| `starter: flow run stuck late`   | a run went Late and still had not started 10 minutes later              |

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
uv run python scripts/setup_automations.py
```

Re-running updates in place. Point it at each workspace you care about.

## Why no Docker build in prefect.yaml

Prefect can build and push an image from `prefect.yaml`. Don't. It couples
"what is deployed" to "how the artifact is built", makes it hard to build
without deploying (PRs), and reruns a multi-GB torch build inside
`prefect deploy`. Build the image in a CI job that is good at building images,
hand the tag to `prefect deploy`, and keep `prefect.yaml` as the declaration of
your deployments. `scripts/check_prefect_yaml.py` fails CI if someone adds a
`build:` section back.

## Adding a workload

1. Copy `packages/canary` to `packages/<name>`, rename the module, write your
   flow in `flows.py`.
2. Add `starter-<name>` to the root `pyproject.toml` `dependencies` and
   `[tool.uv.sources]`. Run `uv lock`.
3. Add a deployment block in `prefect.yaml` using the existing anchors.
4. Open a PR. CI validates the entrypoint and builds the image.
5. Merge, tag, done.

## License

Apache-2.0.
