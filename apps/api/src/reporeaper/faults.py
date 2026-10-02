"""Trusted gate-only crash probes, enabled by a deployment flag, configured through SQL."""

import os

from sqlalchemy import text

from reporeaper.db import one


async def crash_once(db, run_id, point):
    if os.environ.get("GATE_FAULTS_ENABLED") != "1":
        return
    async with db.transaction() as c:
        row = await one(
            c,
            """UPDATE runs SET configuration=jsonb_set(configuration,'{gate_fired}','true'),
            lease_until=now()+interval '8 seconds' WHERE id=:id
            AND configuration->>'gate_crash'=:point AND NOT configuration ? 'gate_fired'
            RETURNING id""",
            id=run_id,
            point=point,
        )
        if row:
            await c.execute(
                text(
                    "UPDATE command_receipts SET lease_until=now()+interval '8 seconds' WHERE command_id IN (SELECT id FROM outbox WHERE run_id=:id AND completed_at IS NULL)"
                ),
                {"id": run_id},
            )
            await c.execute(
                text("UPDATE service_leases SET lease_until=now() WHERE name='dispatcher'")
            )
    if row:
        print(f"Gate crash at {point}; durable state preserved for {run_id}", flush=True)
        os._exit(86)
