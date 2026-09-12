# F7-REL-01 — Release Acceptance orchestration

This slice adds one exact-candidate technical Release Acceptance decision above the existing proven F7 authorities.

The aggregate gate binds these authorities to the same candidate SHA:

- release package/build (`pr253-v0112109-release-package.yml`);
- Full Regression, including the registered PostgreSQL migration and runtime-startup authorities;
- application-wide PostgreSQL zero-residual gate;
- F7-REL-03 PostgreSQL backup -> restore -> startup -> data-integrity authority.

Every accepted child run must be a `workflow_dispatch` run on the requested branch whose `head_sha` equals the candidate SHA. The aggregate run retains machine-readable evidence with all accepted child run IDs and candidate identity.

F7-REL-02 is deliberately outside this technical gate. PO acceptance remains a Phase 8/9 dependency and is not synthesized or marked green by F7-REL-01.

The existing release-package workflow currently carries its historical PR253/v01.12.109 filename. F7-REL-01 treats that workflow as the current package/build authority; renaming the workflow is not required for the orchestration contract and would unnecessarily mix a compatibility cleanup into this closure slice.
