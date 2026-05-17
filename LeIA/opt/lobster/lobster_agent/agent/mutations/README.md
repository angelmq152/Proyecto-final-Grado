# MutationContext Flow

Mutation tools must not call Kubernetes directly. Each tool passes its actual mutation callback
to `MutationContext.execute()`, which owns policy checks, approval routing, dry-run behavior, and
the action ledger.

```text
tool input
   |
   v
policy.validate()
   | forbidden
   v
ABORTED_POLICY action  <-------------------------------+
   |                                                    |
   +--> return ActionResult                            |
                                                        |
allowed                                                 |
   v                                                    |
create PENDING action                                  |
   |                                                    |
   +-- AUTONOMOUS ----------------------------------+   |
   |                                               |   |
   +-- NORMAL / CRITICAL --> AWAITING_APPROVAL ----+   |
                            request_approval()         |
                            rejected -> REJECTED ------+
                            approved -> APPROVED       |
                                                        |
dry_run?                                                |
   | yes                                                |
   v                                                    |
ABORTED_DRY_RUN with planned manifest ------------------+
   |
   +--> return ActionResult

no dry-run
   |
   v
RUNNING -> executor()
   | success
   v
COMPLETED with result

RUNNING -> executor()
   | exception
   v
FAILED with error
```

Bloque 5.1 only provides this wrapper and the shared ledger. Concrete mutation tools such as
pod restarts or tenant deployments belong in Bloque 5.2.
