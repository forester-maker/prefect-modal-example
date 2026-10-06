"""Create the alerting automations for a workspace. Idempotent; safe to re-run.

Prefect already tracks work pool and deployment status server-side, so there is
no heartbeat flow here. These automations just turn the built-in signals into
Slack messages:

  1. starter: work pool not ready      the process pool lost its last worker
  2. starter: flow run crashed         infrastructure died under a run
  3. starter: flow run stuck late      a run was Late and still had not started
                                       LATE_GRACE_SECONDS later (default 10 min).
                                       This is the "job silently never ran" case.

Usage:
    export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
    uv run python scripts/setup_automations.py [--pool starter-process] [--block starter-alerts]

Needs PREFECT_API_URL / PREFECT_API_KEY for the target workspace.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from prefect.blocks.notifications import SlackWebhook
from prefect.client.orchestration import get_client
from prefect.events.actions import SendNotification
from prefect.events.schemas.automations import AutomationCore, EventTrigger, Posture

LATE_GRACE_SECONDS = int(os.environ.get("LATE_GRACE_SECONDS", "600"))


def build(pool: str, block_id) -> list[AutomationCore]:
    notify = lambda subject, body: SendNotification(  # noqa: E731
        block_document_id=block_id, subject=subject, body=body
    )
    return [
        AutomationCore(
            name="starter: work pool not ready",
            description=f"No online worker is polling the `{pool}` work pool.",
            trigger=EventTrigger(
                match={"prefect.resource.id": f"prefect.work-pool.{pool}"},
                expect={"prefect.work-pool.not-ready"},
                posture=Posture.Reactive,
                threshold=1,
                within=0,
            ),
            actions=[
                notify(
                    "Work pool {{ work_pool.name }} is NOT READY",
                    "No worker has polled `{{ work_pool.name }}` recently. "
                    "Scheduled runs will queue (and go Late) until one comes back.",
                )
            ],
        ),
        AutomationCore(
            name="starter: flow run crashed",
            description="A flow run entered Crashed (infrastructure failure, not a code bug).",
            trigger=EventTrigger(
                match={"prefect.resource.id": "prefect.flow-run.*"},
                expect={"prefect.flow-run.Crashed"},
                posture=Posture.Reactive,
                threshold=1,
                within=0,
            ),
            actions=[
                notify(
                    "Flow run {{ flow_run.name }} CRASHED",
                    "{{ flow.name }}/{{ deployment.name }} on {{ work_pool.name }}\n"
                    "{{ flow_run|ui_url }}",
                )
            ],
        ),
        AutomationCore(
            name="starter: flow run stuck late",
            description=(f"A flow run went Late and had not started {LATE_GRACE_SECONDS}s later."),
            trigger=EventTrigger(
                match={"prefect.resource.id": "prefect.flow-run.*"},
                after={"prefect.flow-run.Late"},
                expect={"prefect.flow-run.Pending", "prefect.flow-run.Running"},
                for_each={"prefect.resource.id"},
                posture=Posture.Proactive,
                threshold=1,
                within=LATE_GRACE_SECONDS,
            ),
            actions=[
                notify(
                    "Flow run {{ flow_run.name }} is stuck LATE",
                    "{{ flow.name }}/{{ deployment.name }} was scheduled for "
                    "{{ flow_run.expected_start_time }} and nothing has picked it up.\n"
                    "Pool: {{ work_pool.name }}\n{{ flow_run|ui_url }}",
                )
            ],
        ),
    ]


async def main(pool: str, block_name: str) -> int:
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        print("SLACK_WEBHOOK_URL is not set", file=sys.stderr)
        return 2

    block = SlackWebhook(url=url)
    block_id = await block.save(block_name, overwrite=True)
    print(f"slack-webhook block `{block_name}` -> {block_id}")

    async with get_client() as client:
        for automation in build(pool, block_id):
            existing = await client.read_automations_by_name(automation.name)
            if existing:
                await client.update_automation(existing[0].id, automation)
                print(f"updated  {automation.name}")
            else:
                created = await client.create_automation(automation)
                print(f"created  {automation.name} -> {created}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default=os.environ.get("PROCESS_POOL", "starter-process"))
    ap.add_argument("--block", default="starter-alerts")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.pool, args.block)))
