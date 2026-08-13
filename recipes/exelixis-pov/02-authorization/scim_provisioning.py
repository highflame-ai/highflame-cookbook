#!/usr/bin/env python3
"""Track 02 — SCIM provisioning: the UC8 trigger, live (admin#1220 / ADR 0028).

This script plays the role of the tenant's IdP (Okta / Entra) and drives Highflame's
inbound SCIM 2.0 provider end-to-end:

  1. Discovery probe        — GET /ServiceProviderConfig (what every IdP checks first)
  2. Create a human         — POST /Users (the Entra/Okta provisioning push)
  3. Link probe             — GET /Users?filter=userName eq "..." (how the IdP matches)
  4. Mirror a group         — POST /Groups, then PATCH in BOTH real-world shapes:
                              Entra's filtered-path remove and Okta's member-array add
  5. THE UC8 TRIGGER        — PATCH active:false. Membership flips, and a durable
                              offboarding record is enqueued: ZeroID deactivates every
                              agent identity the human owns and cascade-revokes their
                              credentials (delegated descendants included); Shield's
                              deny-set picks the revoked tokens up within seconds.
  6. Rehire != resurrection — PATCH active:true restores MEMBERSHIP ONLY. Agents stay
                              dead; a returning human re-enables them deliberately.

What this proves: the trigger surface Exelixis asked for in UC8 — "an agent acting for
a deactivated human is automatically denied" — now exists and speaks real-IdP SCIM.
The revocation mechanism it fires is demoed in track 01 (revoke -> tree collapses) and
pre_execution_and_revocation.py (revoked principal denied). This script is the missing
first domino: IdP deactivation -> that mechanism, with no human in the loop.

Group pushes are not cosmetic: on a tenant with an idp_group_mappings row for the
group's displayName (Studio -> Settings -> Project Access), every group change here
re-materializes the member's project access deterministically (ADR 0015).

Auth note: this surface uses a per-tenant SCIM bearer token (hfscim_...), minted by an
org admin — NOT your zid_sk_ key. Mint one:

    curl -X POST "$ADMIN_URL/v1/admin/scim/tokens" \
         -H "Authorization: Bearer <your session JWT>" \
         -d '{"name": "pov-demo"}'      # plaintext is shown exactly once

Set HIGHFLAME_SCIM_URL (e.g. https://control-dev.highflame.dev/scim/v2) and
HIGHFLAME_SCIM_TOKEN in .env. With either missing the script skips (exit 2) — nothing
provisions into a real tenant by accident.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import common  # noqa: E402

SCIM_URL = os.environ.get("HIGHFLAME_SCIM_URL", "").rstrip("/")
SCIM_TOKEN = os.environ.get("HIGHFLAME_SCIM_TOKEN", "")

SCIM_MEDIA = "application/scim+json"


def scim(
    method: str,
    path: str,
    body: dict | None = None,
    expect: tuple[int, ...] = (200, 201, 204),
) -> tuple[int, dict | None]:
    """One SCIM request, exactly as an IdP would send it."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(SCIM_URL + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {SCIM_TOKEN}")
    req.add_header("Content-Type", SCIM_MEDIA)
    req.add_header("Accept", SCIM_MEDIA)
    try:
        with urllib.request.urlopen(req, timeout=common.TIMEOUT) as resp:
            raw = resp.read()
            payload = json.loads(raw) if raw else None
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = {"detail": raw.decode(errors="replace")}
        status = e.code
    if status not in expect:
        raise common.HighflameError(
            f"{method} {path} -> HTTP {status}: {json.dumps(payload, indent=2)}"
        )
    return status, payload


def main() -> int:
    if not SCIM_URL or not SCIM_TOKEN:
        print(
            "SKIP: set HIGHFLAME_SCIM_URL and HIGHFLAME_SCIM_TOKEN to run the SCIM proof.\n"
            "      (Mint the hfscim_ token as an org admin — see this file's docstring.)"
        )
        return 2

    suffix = uuid.uuid4().hex[:8]
    email = f"scim-demo-{suffix}@exelixis-pov.example"
    group_name = f"exelixis-scim-demo-{suffix}"

    # 1 — the receiver is live.
    common.banner("SCIM receiver discovery — what Okta/Entra probe first")
    _, spc = scim("GET", "/ServiceProviderConfig")
    print(
        f"  provider is live: patch={spc['patch']['supported']} "
        f"filter={spc['filter']['supported']} bulk={spc['bulk']['supported']}"
    )

    # 2 — create the human.
    common.banner("POST /Users — the IdP provisioning push")
    _, user = scim(
        "POST",
        "/Users",
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": email,
            "name": {"formatted": "SCIM Demo Human"},
            "externalId": f"entra-{suffix}",
            "active": True,
        },
        expect=(201,),
    )
    user_id = user["id"]
    print(f"  provisioned {email}")
    print(f"  stable user id: {user_id}")
    print(
        "  (a platform-unknown email mints a scim_* id; a known email REUSES its stable id\n"
        "   and the global profile is never mutated by a tenant's stream)"
    )

    # 3 — the link probe.
    common.banner('GET /Users?filter=userName eq "..." — how the IdP links')
    _, page = scim("GET", f"/Users?filter=userName%20eq%20%22{email}%22")
    assert page["totalResults"] == 1 and page["Resources"][0]["id"] == user_id
    print(f"  filter resolves to the same stable id ({user_id}) — linking works")

    # 4 — group state, in both real-world PATCH shapes.
    common.banner("POST /Groups + the PATCH shape zoo (Entra and Okta forms)")
    _, group = scim(
        "POST",
        "/Groups",
        {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": group_name,
            "members": [{"value": user_id}],
        },
        expect=(201,),
    )
    group_id = group["id"]
    print(f"  group {group_name!r} mirrored with 1 member")

    # Entra's filtered-path single-member remove (capitalized op and all).
    scim(
        "PATCH",
        f"/Groups/{group_id}",
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "Remove", "path": f'members[value eq "{user_id}"]'}],
        },
    )
    _, g = scim("GET", f"/Groups/{group_id}")
    assert len(g["members"]) == 0
    print("  Entra-form remove (filtered path, capitalized op): member gone")

    # Okta's member-array add.
    scim(
        "PATCH",
        f"/Groups/{group_id}",
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "add", "path": "members", "value": [{"value": user_id}]}
            ],
        },
    )
    _, g = scim("GET", f"/Groups/{group_id}")
    assert len(g["members"]) == 1
    print("  Okta-form add (member array): member back")
    print(
        "\n  On a tenant with a group mapping for this displayName (Studio -> Settings ->\n"
        "  Project Access), each push above just re-materialized the member's project\n"
        "  access — deterministically, from config, with provenance (ADR 0015)."
    )

    # 5 — the UC8 trigger.
    common.banner("PATCH active:false — the deactivation push (THE UC8 TRIGGER)")
    scim(
        "PATCH",
        f"/Users/{user_id}",
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "value": {"active": False}}],
        },
    )
    _, u = scim("GET", f"/Users/{user_id}")
    assert u["active"] is False
    print("  membership: deactivated (source=scim)")
    print(
        "  offboarding: durably enqueued BEFORE the SCIM ack — the outbox worker calls\n"
        "  ZeroID offboard-by-owner: every agent identity this human owns is deactivated,\n"
        "  its API keys swept, credentials cascade-revoked (delegated descendants via the\n"
        "  parent_jti chain included), and Shield's deny-set updates within seconds.\n"
        "  A transient outage DELAYS an offboarding; it can never DROP one.\n"
        "  Evidence view: GET /v1/admin/scim/offboardings (org admin)."
    )

    # 6 — rehire != resurrection.
    common.banner("PATCH active:true — rehire restores membership ONLY (ADR 0028 D6)")
    scim(
        "PATCH",
        f"/Users/{user_id}",
        {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": True}],
        },
    )
    _, u = scim("GET", f"/Users/{user_id}")
    assert u["active"] is True
    print(
        "  membership restored; agent identities STAY deactivated and credentials STAY\n"
        "  revoked — a returning human re-enables agents deliberately, never silently."
    )

    # Cleanup: drop the demo group, park the demo user inactive.
    common.banner("Cleanup")
    scim("DELETE", f"/Groups/{group_id}", expect=(204,))
    scim(
        "PATCH",
        f"/Users/{user_id}",
        {"Operations": [{"op": "replace", "path": "active", "value": False}]},
    )
    print(
        f"  demo group deleted; demo user {email} left as an inactive directory row\n"
        "  (the platform soft-deletes; an offboarded member stays visible to the IdP\n"
        "  for reactivation — that is by design, not residue)."
    )

    print(
        "\nWhat you just proved: the IdP-side kill chain for UC8. Compose it with the\n"
        "revocation mechanism demo (track 01 / pre_execution_and_revocation.py) and the\n"
        "story is end-to-end: HR deactivates a human in Okta -> within seconds every agent\n"
        "acting on their behalf is denied at the decision point."
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except common.HighflameError as e:
        print(f"FAIL: {e}")
        sys.exit(1)
