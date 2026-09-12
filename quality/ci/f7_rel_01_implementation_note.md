# F7-REL-01 — Release Acceptance orchestration

This slice adds one exact-candidate technical Release Acceptance decision above the existing proven F7 authorities.

The aggregate gate binds these authorities to the same candidate SHA:

- canonical version-agnostic release package/build (`f7-release-package-authority.yml`);
- Full Regression, including the registered PostgreSQL migration and runtime-startup authorities;
- application-wide PostgreSQL zero-residual gate;
- F7-REL-03 PostgreSQL backup -> restore -> startup -> data-integrity authority.

Every accepted child run must be a `workflow_dispatch` run on the requested branch whose `head_sha` equals the candidate SHA. The aggregate run retains machine-readable evidence with all accepted child run IDs and candidate identity.

The package authority reads the release identity from the exact candidate itself, verifies all backend/frontend version files, builds frontend and Docker runtime from that SHA, starts and restarts the PostgreSQL-only production stack, checks runtime identity, creates a runtime-data-free standalone zip, and retains that zip as an artifact. It contains no hardcoded product version and therefore remains valid across version bumps.

F7-REL-02 is deliberately outside this technical gate. PO acceptance remains a Phase 8/9 dependency and is not synthesized or marked green by F7-REL-01.
