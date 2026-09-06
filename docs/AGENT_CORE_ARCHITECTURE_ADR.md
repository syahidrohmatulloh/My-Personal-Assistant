# Agent Core Architecture ADR

Status: **ACCEPTED / LOCKED**
Date: 6 September 2026
Baseline: `43b3798643a2f93bd20d682b6d33a7baaf905c23`
Predecessor: M35C3 — COMPLETE / FROZEN

## 1. Decision

Aliyya Agent Core introduces a durable operational-state domain for work
that Aliyya is actively helping bring to completion.

Canonical loop:

    OBJECTIVE
    → PLAN
    → STEP
    → OBSERVE
    → VERIFY
    → UPDATE STATE
    → CONTINUE / WAIT / COMPLETE

Agent Core is not Memory, not Goals, not Calendar pending state, and not
a generic external tool-execution engine.

## 2. Canonical domain boundaries

### Memory

Memory answers what Aliyya knows or believes about the user and their world.

Memory remains governed by M35 provenance, confirmation, trust, retrieval,
and lifecycle contracts.

Memory MUST NOT become Agent Core work-state storage.

### Goal

Goal answers what outcome or direction the user cares about.

Existing `goals`, `goal_check_ins`, `goal_suggestions`, and
`goal_action_proposals` remain Goal-domain state.

A Goal is not automatically an executable Agent Objective.

### Agent Objective

Agent Objective answers what operational outcome Aliyya is currently helping
bring to completion.

An objective MAY reference an existing `goal_id`, but Goal and Agent Objective
remain separate domains.

Inference alone MUST NOT create an active objective.

Initial activation authority:

    explicit_user_request
    user_confirmed_proposal

### External Action

Broad external-system mutation is outside Agent Core v1.

External actions may appear as planned steps, but execution authority belongs
to the future Action & Authority milestone.

## 3. Existing systems remain separate

`calendar_pending_actions` remains Calendar-specific continuation state.

`proactive_nudges` remains scheduled in-chat message delivery.

`WorkingMemoryState` remains request/turn scoped and ephemeral.

None of these tables is repurposed as generic Agent Core state.

## 4. Canonical persistence model

Agent Core v1 introduces four generic durable tables:

    agent_objectives
    agent_plans
    agent_plan_steps
    agent_events

### agent_objectives

Represents one durable operational outcome.

Canonical status:

    proposed
    active
    waiting
    paused
    completed
    cancelled

Minimum conceptual state:

    id
    user_id
    title
    desired_outcome
    status
    priority
    goal_id nullable
    source_conversation_id nullable
    source_message_id nullable
    creation_authority
    active_plan_id nullable
    waiting_reason nullable
    resume_after nullable
    last_progress_at nullable
    completed_at nullable
    cancelled_at nullable
    created_at
    updated_at

### agent_plans

A versioned decomposition of one objective.

Canonical status:

    active
    completed
    superseded
    cancelled

Only one plan may be active per objective.

Replanning creates a new plan version and supersedes the old plan rather than
rewriting historical execution state.

### agent_plan_steps

A durable unit of work or continuation.

Canonical step kinds:

    internal
    user_input
    wait_time
    observe
    verify
    external_action

Canonical step status:

    pending
    ready
    in_progress
    waiting
    blocked
    completed
    failed
    cancelled

Canonical verification status:

    not_required
    pending
    verified
    failed

Execution and verification are separate concepts.

### agent_events

Append-only audit and evidence stream for meaningful Agent Core transitions.

Initial event vocabulary:

    objective_created
    objective_activated
    plan_created
    plan_superseded
    step_ready
    step_started
    observation
    verification
    step_completed
    step_failed
    objective_waiting
    objective_resumed
    objective_completed
    objective_cancelled
    note

Materialized status columns remain the efficient current-state representation.
Events explain how that state was reached.

## 5. State-machine contract

### Objective

Allowed transitions:

    proposed → active
    active → waiting
    waiting → active
    active → paused
    paused → active
    active → cancelled
    waiting → cancelled
    paused → cancelled
    active → completed
    waiting → completed

`completed` and `cancelled` are terminal in Agent Core v1.

### Plan

Allowed transitions:

    active → completed
    active → superseded
    active → cancelled

### Step

Allowed transitions:

    pending → ready

    ready → in_progress
    ready → waiting
    ready → blocked
    ready → cancelled

    in_progress → completed
    in_progress → waiting
    in_progress → blocked
    in_progress → failed

    waiting → ready
    blocked → ready

    failed → ready
    failed → cancelled

Invalid transitions MUST fail closed.

## 6. Verification contract

A step that executed is not automatically a verified success.

An objective MUST NOT become completed solely because:

- an LLM says it is done;
- a step was attempted;
- an external call returned;
- a reminder was delivered;
- time passed.

Deterministic completion policy evaluates:

1. required plan steps;
2. step completion state;
3. verification requirements;
4. unresolved waiting or blockers;
5. objective completion evidence.

If success cannot be verified automatically, Agent Core may wait for explicit
user confirmation rather than manufacture success.

## 7. Authority contract

LLM reasoning may propose:

- an objective;
- a plan;
- a replanning decision;
- a next step;
- an observation;
- verification evidence.

Deterministic Agent Core policy decides durable state transitions.

Agent Core MUST NOT bypass existing Memory, Calendar, or future
Action & Authority protections.

## 8. CognitiveRuntime ownership

Dependency direction remains:

    chat.py
      → CognitiveRuntime
          → Agent Core services
              → persistence

Existing services MUST NOT depend on CognitiveRuntime.

CognitiveRuntime may:

- retrieve a compact Agent Core snapshot during turn-source fan-in;
- delegate deterministic Agent Core evaluation;
- expose relevant continuation state to the current turn;
- sequence Agent Core decisions with existing cognitive policies.

CognitiveRuntime MUST NOT:

- own SQL;
- become durable storage;
- own an autonomous scheduler;
- directly execute arbitrary external tools;
- bypass Agent Core transition policy.

`COGNITIVE_RUNTIME_VERSION = "M31D-v1"` remains frozen.

## 9. Cross-turn continuation

Agent Core v1 supports passive durable continuation.

A later conversation may retrieve relevant active or waiting objectives
without requiring the user to restate the entire objective.

Compact turn context may include:

    objective_ref
    objective_status
    desired_outcome
    active_plan_ref
    current_or_next_step_ref
    waiting_reason
    resume_after
    verification_status
    last_progress_at

Raw event history MUST NOT be dumped wholesale into model prompts.

## 10. Scheduler boundary

Agent Core v1 does not introduce an autonomous objective runner.

It may persist `resume_after` and waiting state for future compatibility.

Autonomous wake-up, persistent monitoring, cross-objective prioritization,
and unsolicited continuation remain later Persistent Objectives and
Proactive Agent capabilities.

## 11. Initial acceptance behavior

Agent Core is not complete until:

1. User explicitly creates or confirms a multi-step operational objective.
2. Objective and plan persist durably.
3. Aliyya can identify the next step.
4. Another conversation can continue the same objective.
5. Waiting and blocked state are explicit.
6. Observations are separate from assertions of success.
7. Verification prevents false completion.
8. User can pause, resume, or cancel.
9. Planned external actions do not silently execute.
10. Backend restart does not erase operational state.

## 12. Explicit non-goals

Agent Core v1 does not include:

- autonomous browser operation;
- general email sending;
- autonomous Calendar mutation;
- purchases or financial transactions;
- multi-agent delegation;
- push notification infrastructure;
- full personal/executive world graph;
- autonomous prioritization across the user's life;
- background autonomous objective execution;
- replacement of existing Memory or Goals.

## 13. Implementation gate

Before runtime or schema mutation:

1. inspect exact source anchors;
2. inspect live adjacent schema and RLS;
3. design transaction-safe schema and indexes;
4. implement pure deterministic transition policy;
5. define service, API, and runtime integration;
6. define targeted and cross-regression tests;
7. perform database preflight;
8. only then approve production migration.

This ADR locks architecture. It does not itself approve a production migration.
