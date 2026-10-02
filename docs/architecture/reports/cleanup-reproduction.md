# Cleanup proof regression, 2026-10-02

The strengthened M0 crash/replay test stalled at waiting_execution. SQL showed one expired
capacity reservation for a completed execution. Actual Docker listing showed no sandbox.
Docker inspect inside the deployed controller returned exit 1:

```text
error: no such object: reaper-<execution-id>-<owner-id>
[]
```

The cleanup check matched only capitalized `No such object`, retained the reservation,
and blocked subsequent admissions. The failing test run was stopped and was not accepted.
The fix normalizes casing and still requires an explicit missing-object error; daemon
connection/permission failure is not proof of cleanup. The definitive gate report must
record actual child/container removal, reservation reclamation and crash recovery afterward.

The strengthened child probe also initially failed because `docker top -eo args` returned
`Couldn't find PID field in ps output`. Reproduction with `-eo pid,args` showed both
the bootstrap parent and `/usr/local/bin/python -c import time; time.sleep(120)` child.
The trusted test was corrected to retain the PID field and cancel even on probe failure.
