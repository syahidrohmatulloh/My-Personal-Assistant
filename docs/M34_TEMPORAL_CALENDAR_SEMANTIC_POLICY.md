# M34 — Temporal / Calendar Semantic Policy

**Status:** Implemented by the M34 major patch
**Baseline:** M33 (`0bacad9`)
**Version:** `M34-v1`

## Canonical invariant

```text
time mention != event != commitment != scheduling request
```

M34 fixes Calendar false positives and false negatives by making those concepts
separate deterministic axes rather than treating activity + date/time as
Calendar authority.

## Semantic axes

`CalendarSemanticAssessment` records temporal reference, subject, eventhood,
commitment, speech act, persistence target, route, independent confidence axes,
and deterministic reason codes.

## Precision-first routing

Without an explicit Calendar/reminder request, M34 keeps these in normal chat:

- tentative plans;
- habits/routines;
- temporal questions;
- public situational information;
- third-party events;
- cancelled/non-events;
- bare date/time information without eventhood.

A committed personal event with temporal information may become a Calendar
candidate. It is not treated as created/saved until the existing authoritative
Calendar confirmation/write path succeeds.

## Pending-state isolation

Pending suggestions are dialogue state, not ambient long-term context.

Same-conversation pending state is preferred. User-level fallback is permitted
only when the current message explicitly refers to an older agenda/jadwal
("yang tadi", "sebelumnya", etc.). A plain "iya" in a new conversation cannot
accidentally confirm an unrelated old pending suggestion.

## Architecture

```text
chat.py
  -> CognitiveRuntime
    -> cognitive_calendar_orchestration
      -> temporal_calendar_policy
      -> existing Calendar services
```

`temporal_calendar_policy.py` is deterministic and read-only: no LLM, database,
embedding, network, Google provider, or persistence dependency.

## User-facing language

The presupposition `Ini kayaknya agenda...` is removed.

A qualified candidate can ask neutrally:

```text
Mau aku masukin ke Calendar?
```

An ambiguous fallback explicitly avoids assuming the user's temporal statement
is already a schedule.

## Non-goals

M34 does not redesign Google Calendar writes, add a database table, promote
routines/tentative plans into schedules, or add a second cognitive trace.
