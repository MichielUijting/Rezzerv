# Onboarding v2 — acceptance & closure

Status: application acceptance target for I.5  
Canonical product source: `docs/product/INHUIS_PRODUCTONTWERP_ONBOARDING_V2.md`

## 1. Closure statement

Onboarding v2 is **application-complete** when the A→I product chain below is green as one acceptance set and all cross-slice invariants in this document remain true.

Application-complete does **not** mean that production e-mail delivery is already enabled. Real Resend activation is intentionally a deployment concern that remains disabled until the hosting environment, public application URL, secrets and verified mail domain exist.

The product principle remains:

> **Inhuis past zich aan de gebruiker aan. De gebruiker hoeft zich niet aan Inhuis aan te passen.**

Product relevance and authorization remain separate concerns. Product configuration decides which capabilities are relevant; server-side authorization decides what a user may do.

## 2. A→I acceptance matrix

| Slice | Product promise | Primary executable proof | Acceptance state |
| --- | --- | --- | --- |
| A — Nieuwe-account foundation | A normal new consumer gets an account, exactly one own regular household, canonical `household.admin`, onboarding state and a server session. | `backend/tests/consumer_account_registration_selftest.py` | Required green |
| B — Gebruiksdoel foundation | The onboarding use case is captured as product intent without becoming authorization. | `backend/tests/onboarding_use_case_foundation_selftest.py` | Required green |
| C — Inhuis halen | Shopping-oriented onboarding produces the intended product configuration and preserves authorization boundaries. | `backend/tests/inhuis_halen_onboarding_selftest.py` | Required green |
| D — Wat Inhuis | Inventory-oriented onboarding configures tracking depth without making product settings an authority source. | `backend/tests/wat_inhuis_onboarding_selftest.py` | Required green |
| E — Waar Inhuis | Location-oriented onboarding supports the configured location depth, including the locationless/shared foundations used by the product model. | `backend/tests/waar_inhuis_onboarding_selftest.py`, `backend/tests/shared_household_minimum_selftest.py`, `backend/tests/test_locationless_inventory_identity_guard.py` | Required green |
| F — Dynamische navigatie | Home navigation is projected from product relevance; no configuration preserves legacy broad presentation. | `backend/tests/dynamic_navigation_product_projection_selftest.py`, `frontend/tests/dynamic-home-navigation.contract.mjs` | Required green |
| G — Dynamische Instellingen | Settings visibility follows product relevance while disabled/allowed state remains authorization-driven; legacy no-config presentation stays intact. | `frontend/tests/dynamic-settings-navigation.contract.mjs`, existing Dynamic Settings validation | Required green |
| H — Circulair uitbreiden | Capabilities can be expanded monotonically, without removing known configuration or rewriting the original primary use case. | `backend/tests/circular_capability_expansion_selftest.py`, `frontend/tests/circular-capability-expansion.contract.mjs` | Required green |
| I — Echte uitnodigingen | Invitation creation, acceptance, household context, secure delivery semantics, UI lifecycle and closure of direct member creation form one coherent flow. | I.1–I.4 invitation selftests/contracts listed below | Required green |

## 3. I acceptance set

I is accepted only when all four slices remain green together:

### I.1 — invitation foundation

- `backend/tests/household_invitation_foundation_selftest.py`
- `backend/tests/household_invitation_target_policy_selftest.py`

Invariant: creating an invitation creates **no account, membership or authorization**.

### I.2 — acceptance and household context

- `backend/tests/household_invitation_acceptance_selftest.py`
- `frontend/tests/invitation-acceptance.contract.mjs`

Invariants:

- acceptance is bound to the exact normalized invited e-mail;
- invitation-specific registration creates no phantom/empty personal household;
- successful acceptance consumes the invitation atomically and creates exactly one canonical `household.member` membership;
- session context is rotated server-side into the invited household;
- household switching is server-authoritative.

### I.3 — delivery semantics

- `backend/tests/household_invitation_delivery_selftest.py`
- `backend/tests/household_invitation_delivery_redaction_selftest.py`

Invariants:

- no password or temporary password is sent;
- raw invitation secret is not persisted or audited;
- provider errors cannot leak the bearer secret into persisted/user-visible failure text;
- successful resend rotates the invitation secret;
- failed resend keeps the last successfully delivered link valid;
- delivery state and invitation lifecycle state remain separate.

### I.4 — household UI and legacy closure

- `backend/tests/household_member_legacy_closure_selftest.py`
- `frontend/src/features/settings/SettingsHouseholdPage.invitations.contract.test.js`
- existing live Docker/Playwright membership regression

Invariants:

- household UI uses e-mail-only invitations;
- the browser does not create members/accounts directly and asks for no member password;
- pending/accepted/expired/revoked invitation lifecycle is visible;
- resend/revoke operate on pending invitations;
- existing linked-member role management and removal remain available;
- legacy `POST /api/household/members` is fail-closed with HTTP 410 and points clients to `/api/household/invitations`.

## 4. Cross-slice invariants

The following invariants define the closure boundary and must not regress after I.5.

### 4.1 Account and household identity

1. Generic consumer registration creates its own regular household and canonical admin membership.
2. Invitation-specific registration is deliberately different: it creates an account for the invitation flow but **does not** create an extra personal household.
3. Successful invitation acceptance creates membership only in the invited household and exactly as `household.member`.
4. Frontteam platform authority and personal household context remain separate; historical shared Frontteam context is not a personal runtime household.

### 4.2 Product relevance is not authorization

1. Product configuration decides relevance/presentation.
2. Permissions and canonical membership/platform roles remain the authority source.
3. A relevant but unauthorized setting may be visible disabled with explanation where the product contract says so.
4. An irrelevant capability is omitted from the dynamic projection.
5. No product configuration means the pre-v2 broad/legacy presentation remains available.

### 4.3 Session authority

1. The HttpOnly server session is authoritative for account/household context.
2. Browser-supplied household or role data never grants authority.
3. Product configuration is **not** part of the public `/api/session` payload.
4. Multi-household switching uses server-side membership validation and session rotation.

### 4.4 Circular expansion

1. `primary_use_case` remains the original onboarding choice and is not rewritten by later expansion.
2. Active capabilities/use cases are tracked separately.
3. Expansion is additive/monotonic: it may add capability depth but must not silently remove already configured capability, locations or known answers.
4. Structural expansion still requires the canonical household-settings permission.

### 4.5 Invitation security

1. An invitation is a pending capability to join; it is not a user, membership or permission grant.
2. Acceptance is single-use and exact-account/e-mail bound.
3. Tokens are bearer secrets and token hashes are the only persisted token material.
4. Audit records contain no raw token or token hash.
5. Legacy direct member creation remains permanently closed.

## 5. Legacy compatibility boundary

Onboarding v2 is intentionally incremental.

- Existing households with **no product configuration** retain the broad legacy presentation.
- Merely viewing circular-expansion/settings UI must not silently create configuration or narrow an existing user's experience.
- Existing member role management remains supported after I.4; only direct member/account creation was retired.

## 6. Production e-mail activation is deferred

The application implementation for invitation delivery exists, but real e-mail delivery stays disabled until a hosting environment is selected and configured.

Before setting `REZZERV_EMAIL_ENABLED=true`, deployment acceptance must verify at least:

1. a definitive public HTTPS application base URL (`REZZERV_APP_BASE_URL`);
2. secure secret storage for `REZZERV_RESEND_API_KEY`;
3. a verified sender/domain and the required SPF/DKIM/DNS configuration;
4. production/staging separation where applicable;
5. end-to-end delivery to controlled test mailboxes;
6. monitoring for delivery failures without secret leakage;
7. reverse-proxy/application access-log handling for invitation URLs;
8. browser referrer policy and third-party-resource behavior on `/uitnodiging/:token`;
9. a security decision that the existing path-token transport is acceptable in the chosen hosting stack, or migration to a transport model that keeps the raw bearer secret out of infrastructure access logs before real mail is enabled.

This deployment gate is not an I.5 application-code blocker because production mail remains disabled until it is completed. It **is** a blocker for enabling real invitation e-mail.

## 7. I.5 executable closure

The dedicated workflow `.github/workflows/onboarding-v2-acceptance-closure-validation.yml` is the umbrella acceptance gate. It re-runs representative A→I backend selftests, frontend contracts, the I.5 cross-invariant selftest and a production frontend build on one exact commit.

The closure is green only when the workflow emits:

`ONBOARDING_V2_I5_ACCEPTANCE_CLOSURE_GREEN`

## 8. Definition of done

Onboarding v2 may be marked **application-complete** when:

- the I.5 umbrella workflow is green on the exact PR head;
- all automatically triggered current-head regression workflows are green;
- there are no unresolved review threads;
- the PR scope contains no unintended production behavior changes;
- the accepted head is merged with an expected-head guard;
- post-merge `main` is verified;
- production Resend remains disabled until the deployment gate in section 6 is completed.

At that point A→I is closed as one product line, while hosting/e-mail activation remains a separately controlled deployment milestone.
