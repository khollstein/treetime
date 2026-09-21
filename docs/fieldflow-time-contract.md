# Treetime → FieldFlow: the time push

What Treetime sends, so the receiving endpoint can be built against it.
Nothing here needs FieldFlow to change how projects are fed back the other
way — the projects feed (`docs/fieldflow-edge-function.ts`) is unchanged, and
both directions use the same API key.

## The request

```
POST https://fieldflow.canopyconsulting.com.au/functions/v1/treetime-time
x-api-key: <the existing Treetime API key>
Content-Type: application/json
```

```json
{ "entries": [
  { "external_id": "tt-3f9a2b71-88412",
    "project_number": "P-2842",
    "person_email": "matthew@canopyconsulting.com.au",
    "started_at": "2026-09-21T08:05:00+10:00",
    "minutes": 210,
    "description": "Tree inspection — Lane Cove",
    "billable": true,
    "project_name": "P-2842 — Lane Cove",
    "client": "North Sydney Council" }
] }
```

The endpoint URL is configurable in **FF Settings → Push time to FieldFlow**,
so it can be pointed somewhere else while the real one is being built.

## The fields

| Field | Always sent | Notes |
| --- | --- | --- |
| `external_id` | yes | Treetime's id for the entry. Stable for the life of the entry — this is the idempotency key. |
| `project_number` | yes | The match key. Same value the projects feed sends as `project_number` / `keyword`. |
| `person_email` | yes | Set once per install in FF Settings. Entries are not sent without it. |
| `started_at` | yes | ISO 8601 with the machine's UTC offset, e.g. `+10:00`. Never naive. |
| `minutes` | yes | Whole minutes, always ≥ 1. `ended_at` is never sent, so there is no "both" case to resolve. |
| `description` | yes | The note on the entry. May be an empty string. |
| `billable` | yes | From the project's billable flag. |
| `project_name`, `client` | yes | Context for the review screen. Safe to ignore. |
| `deleted` | only on withdrawals | See below. |

Treetime never sends an entry without a `project_number` and a
`person_email`; those are reported to the user locally instead, so the review
screen's unmatched list should only ever hold genuine mismatches ("no project
P-2842", "email not on the team").

## Idempotency

`external_id` is `tt-<install id>-<entry id>`. The install id is an eight
character hex string generated once per Treetime install, so ids never
collide between people or machines.

An entry keeps its `external_id` when it is edited, so:

- **Same id, same content** — Treetime won't resend it at all. It tracks a
  hash of what it last sent and skips anything unchanged.
- **Same id, different content** — the entry was edited here; the endpoint
  should update the pending record in place.
- **New id** — a new entry.

So an upsert on `external_id` is all that's needed, and re-sending a batch is
always safe. A record already accepted into time should not be silently
overwritten by a later push; putting the update back in the review list is
the safer reading.

## Deletions (optional to honour)

If an entry that was already pushed is deleted in Treetime, the next push
includes:

```json
{ "external_id": "tt-3f9a2b71-88412", "deleted": true }
```

Treetime stops sending it once the request succeeds. If the endpoint ignores
the flag, nothing breaks — the stale entry just sits in the review list and
can be dismissed by hand.

## Responses

Any `2xx` means the batch was accepted, and Treetime marks those entries as
sent. Anything else and nothing in that batch is marked sent, so it all goes
again on the next push. An empty body is fine.

To reject individual entries while accepting the batch, answer with:

```json
{ "results": [
  { "external_id": "tt-3f9a2b71-88412",
    "status": "rejected",
    "reason": "no project P-2842" }
] }
```

`status` of `rejected`, `error`, `failed`, `unmatched` or `invalid` counts as
a rejection; Treetime shows the reason to the user and retries that entry on
the next push. Any entry not mentioned in `results` counts as accepted.

## When entries are sent

Whichever the user turns on in FF Settings:

- **Manual** — the **Push Time** button in the status bar, or **Push Time
  Now** in FF Settings. Sends the last N days (default 7).
- **Nightly** — from a configured hour (default 19:00), once per day, same
  window. Checked every 15 minutes rather than fired on the hour, so a laptop
  asleep at 19:00 still sends when it wakes.

Both re-send the same recent window each time, which is why the idempotency
key matters: late edits to yesterday's time reach FieldFlow without creating
duplicates.

Batches are capped at 200 entries per request; a longer catch-up is split
across several POSTs.

## The file fallback

If pushing isn't available, **Reports → Export for FieldFlow** writes a CSV
with one row per entry and exactly these columns:

```
external_id,project_number,person_email,started_at,minutes,description,billable
```

Same values, same meanings as above; `billable` is `true`/`false`. Entries
that can't be matched are left out of the file and listed on screen instead.
