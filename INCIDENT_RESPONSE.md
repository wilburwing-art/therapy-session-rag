# Incident Response Plan

This plan governs how TherapyRAG responds to security incidents, privacy events, and service outages. It is intentionally short. When something is on fire, nobody will read past page three.

## Roles

Three roles are assigned at incident declaration. One person can hold two roles in a small event; SEV1 must have three distinct people.

- **Incident Commander (IC).** Owns the response. Decides severity, declares start and end, runs the bridge, calls in additional responders. The IC does not fix the bug — they keep the response coordinated.
- **Scribe.** Maintains the incident timeline in the shared incident doc. Every decision, hypothesis, and mitigation attempt goes in with a wall-clock timestamp. Writes the post-mortem.
- **Comms Lead.** Drafts and sends customer and regulator communications, coordinates with legal and counsel on breach-notification timing, handles press inquiries if any.

## Severity matrix

| Severity | Definition | Initial response |
| --- | --- | --- |
| **SEV1** | Confirmed or high-probability PHI breach, confirmed unauthorized access to production data stores, total outage of the patient chatbot or therapist dashboard, or any event requiring HIPAA breach notification. | Page on-call immediately. IC declares within 15 minutes. Executive notified within 30 minutes. |
| **SEV2** | Degraded service: elevated error rate > 5% on a core surface, partial data unavailability, suspected but unconfirmed PHI exposure, security finding that materially increases risk until fixed. | Page on-call. IC declares within 30 minutes. Customer-visible status update within 1 hour. |
| **SEV3** | Minor service impairment, internal tool outage, low-risk security finding. | Handled on next business day. Tracked in incident log. |

Start high, downgrade later. Under-severity is far more expensive than over-severity.

## HIPAA breach notification timing

Reference: 45 CFR § 164.404 (notification to individuals), § 164.406 (media notice for breaches of 500+ in a state), § 164.408 (HHS OCR notification).

- **Individuals:** notify each affected patient and therapist-covered-entity **without unreasonable delay and no later than 60 calendar days from discovery.** Deadline is measured from when TherapyRAG knows, or should reasonably have known, about the breach.
- **HHS OCR:** breaches affecting **500 or more individuals** must be reported to OCR within the same 60-day window. Breaches affecting fewer than 500 are logged and submitted annually.
- **Media:** if a breach affects 500+ individuals in a single state or jurisdiction, notify prominent media outlets serving that area — same 60-day deadline.
- **Covered entities (therapists):** as the Business Associate, TherapyRAG notifies the Covered Entity in writing as soon as the breach is confirmed so they can meet their own notification obligations.

Err on the side of earlier notice. The 60-day ceiling is a regulatory maximum, not a target.

## Patient notification letter template

```
Subject: Notice of data incident — TherapyRAG

Dear {{ patient_first_name }},

We are writing to inform you of an incident involving your information
stored with TherapyRAG, the platform your therapist uses to record and
review session notes.

What happened
On {{ discovery_date }}, we identified {{ short_plain_description }}.
Our investigation, which began immediately, determined that
{{ scope_sentence: categories of data potentially exposed, time window,
approximate number of affected patients }}.

Information involved
{{ bulleted list: e.g. name, email address, session audio recordings,
session transcripts, chatbot messages, assessment responses }}.

What we have done
{{ bulleted list of contained actions: credential rotation, access
revocation, patched vulnerability, engaged forensics, etc. }}

What you can do
Review any notifications you receive from your therapist. If you suspect
misuse of your information, contact your therapist and, if appropriate,
your state's attorney general.

For questions, reply to this email or contact us at
security@therapyrag.local.

Sincerely,
The TherapyRAG team
```

Counsel reviews every customer-facing notice before it goes out.

## Forensics checklist

Run these before any remediation that could destroy evidence.

1. **Preserve logs.** Snapshot application logs, database audit logs, S3/MinIO access logs, Cloudflare or load-balancer logs, and any SIEM exports. Store outside the affected environment.
2. **Freeze affected instances.** Stop but do not terminate. Take disk and memory snapshots where the host supports it.
3. **Rotate credentials.** Application JWT secrets, database passwords, API keys for every third-party vendor, admin user sessions. Record what was rotated and when.
4. **Engage the IR firm.** Retainer contact and playbook are in the ops runbook. Do this in parallel with internal response, not after.
5. **Tag everything.** Every artifact (screenshot, log export, snapshot) gets an incident id and a timestamp at capture time.
6. **Preserve chain of custody.** One Scribe, one document, signed entries.

## Post-mortem template

Post-mortems are blameless and mandatory for every SEV1 and SEV2. Published internally within 7 business days of incident resolution.

```markdown
# Incident {{YYYY-MM-DD}}-{{short-name}}

**Severity:** SEV{1|2|3}
**Duration:** {{ISO start}} → {{ISO end}} ({{duration}})
**Customer impact:** {{one-sentence summary}}
**Incident Commander:** {{name}}
**Scribe:** {{name}}
**Comms Lead:** {{name}}

## Timeline
{{chronological entries — wall-clock timestamps, action, actor}}

## Root cause
{{What was the actual technical cause? Not "human error" — what did the
system permit that it should not have? Five-whys style.}}

## Contributing factors
{{Everything that made this worse or slower to detect: alerting gaps,
process gaps, knowledge gaps.}}

## What went well
{{Specific actions that shortened the incident.}}

## What went poorly
{{Specific actions or absences that lengthened the incident.}}

## Corrective actions
| # | Action | Owner | Due | Status |
| - | ------ | ----- | --- | ------ |
| 1 | ...    | ...   | ... | open   |

Each action has a ticket. Actions are tracked to completion in the
incident log; the post-mortem is not closed until every high-severity
action is either done or formally deprioritized with rationale.

## Customer communication
{{Links to every external communication: status-page posts, patient
letters, therapist notices, OCR submissions.}}
```

## Declaring an incident over

The IC declares incident resolved only when:

1. Customer impact is reversed.
2. Root cause is either patched or has a documented workaround in effect.
3. Detection gaps identified in the incident have a monitoring action ticket open.
4. Breach-notification obligations, if any, are tracked to completion — the incident is not resolved just because the technical outage is fixed.
