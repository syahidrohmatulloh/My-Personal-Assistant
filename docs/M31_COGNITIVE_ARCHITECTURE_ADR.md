# M31 — Cognitive Architecture Foundation

## Architecture Decision Record (M31A) + Cognitive Decision Trace Spec (M31B)

**Status:** Accepted — Locked for M31B Implementation
**Author:** Aliyya Engineering
**Date:** 2026-09-01
**Scope:** M31A (ADR) + M31B (Trace Spec) only. M31C–M31G and M32–M33 are out of scope.
**Repository basis:** `syahidrohmatulloh/My-Personal-Assistant`, `main`, reviewed against the current M30 runtime.
**Locked Principles:** See §1.2.

---

## Revision 0.2 Summary

Revision 0.2 resolves the architecture-gate findings from v0.1. The changes are substantive rather than editorial:

- Replaces generic/imaginary module names with actual Aliyya repository modules.
- Replaces the strict linear brain-like pipeline with a logical dependency graph that permits parallel reads and deferred work.
- Grounds `assistant_mode` and `companion_mode` in current runtime values.
- Treats affect as policy/context constraints that may be resolved before generation, not as a mandatory post-LLM stage.
- Removes mandatory M31G-era salience values from M31B trace data.
- Renames **User-Authored Truth** to **User-Authored Assertion** and adds temporal staleness semantics.
- Separates external mutations, explicitly authorized automation, and internal cognitive persistence.
- Introduces fail-open trace sinks and a production-safe preview policy.
- Removes the unused `X-Cognitive-Trace-ID` response-header concept from M31B v1.
- Resolves the test-spec contradiction: trace contract tests inspect trace contents; behavioral tests independently verify behavior.
- Grounds warm-comeback reason codes in the deterministic M30 implementation.
- Validates all example reason codes against the canonical taxonomy.

---

## Table of Contents

1. [M31A — Cognitive Architecture ADR](#1-m31a--cognitive-architecture-adr)
   1. [Purpose](#11-purpose)
   2. [Locked Architecture Principles](#12-locked-architecture-principles)
   3. [Non-Goals](#13-non-goals)
   4. [Canonical Terminology](#14-canonical-terminology)
   5. [Logical Cognitive Runtime Model](#15-logical-cognitive-runtime-model)
   6. [State & Provenance Taxonomy](#16-state--provenance-taxonomy)
   7. [Score Taxonomy](#17-score-taxonomy)
   8. [Actual Aliyya Module Mapping](#18-actual-aliyya-module-mapping)
   9. [Dependency-Direction Rules](#19-dependency-direction-rules)
   10. [`chat.py` Contract](#110-chatpy-contract)
   11. [`CognitiveRuntime` Future Ownership](#111-cognitiveruntime-future-ownership)
   12. [Failure Isolation](#112-failure-isolation)
   13. [Observability Requirements](#113-observability-requirements)
   14. [Migration Strategy](#114-migration-strategy)
   15. [Rejected Alternatives](#115-rejected-alternatives)
2. [M31B — CognitiveDecisionTrace Spec](#2-m31b--cognitivedecisiontrace-spec)
   1. [Purpose & Constraints](#21-purpose--constraints)
   2. [Design Philosophy](#22-design-philosophy)
   3. [Trace Boundaries](#23-trace-boundaries)
   4. [Type Specifications](#24-type-specifications)
   5. [Trace Sink & Privacy Model](#25-trace-sink--privacy-model)
   6. [Reason-Code Taxonomy](#26-reason-code-taxonomy)
   7. [Example Traces](#27-example-traces)
   8. [Test Matrices](#28-test-matrices)
   9. [Rollout Plan](#29-rollout-plan)
   10. [Definition of Done](#210-definition-of-done)
   11. [Explicit Exclusions](#211-explicit-exclusions)
3. [Resolved Review Findings](#3-resolved-review-findings)
4. [Appendices](#4-appendices)

---

# 1. M31A — Cognitive Architecture ADR

## 1.1. Purpose

This ADR locks the architectural foundation for Aliyya's M31 cognitive runtime work. It defines contracts and boundaries for evolving the existing system without a rewrite.

The ADR deliberately uses brain-inspired terminology only where it creates engineering value. Aliyya is **not** intended to simulate neuroanatomy. The target is a persistent cognitive software architecture with inspectable state, deterministic policy boundaries, strong memory provenance, and graceful degradation.

M31A defines:

- the canonical vocabulary used by M31B–M31G;
- the logical dependency model of a chat turn;
- the distinction between ephemeral state, durable state, inference, and explicit user assertions;
- the separation of confidence, salience, relevance, and policy certainty;
- the ownership boundaries between `chat.py`, existing services, and the future `CognitiveRuntime` facade;
- the rule that observability is installed before orchestration is moved.

M31A does **not** prescribe implementation patches.

## 1.2. Locked Architecture Principles

These principles remain unchanged from v0.1 and are non-negotiable for M31.

| # | Principle | Rationale |
|---|---|---|
| P1 | **LLM reasons; deterministic policy decides.** | The LLM may infer, propose, and generate. Hard mode, safety, confirmation, privacy, and other policy constraints remain deterministic. |
| P2 | **Confidence, salience, and relevance are separate concepts.** | They represent different questions and must not collapse into one scalar. |
| P3 | **Working memory is ephemeral by default.** | Only information that passes an explicit encoding gate may become durable. |
| P4 | **Inferred affect is not psychological truth and must preserve source/confidence.** | Explicit self-report outranks inference. Inference remains qualified and time-sensitive. |
| P5 | **Every meaningful cognitive decision must be inspectable.** | If a decision cannot be explained from structured evidence, the architecture is incomplete. |
| P6 | **No new infrastructure unless it solves a demonstrated problem.** | No Redis, Neo4j, LangChain, CrewAI, or new trace persistence in M31A/M31B. |
| P7 | **`CognitiveRuntime` begins as a facade, not a rewrite.** | Existing services remain authoritative while orchestration is migrated incrementally. |
| P8 | **Existing Aliyya behavior remains backward-compatible during M31 foundation work.** | No user-facing regression and no API contract breakage. |
| P9 | **Supabase/Postgres remains the durable source of truth.** | Embeddings, indexes, and graph projections support access; they do not replace truth storage. |
| P10 | **Observability precedes refactor.** | M31B instruments the current runtime before M31C–M31E move responsibilities. |

## 1.3. Non-Goals

M31A/M31B do not:

- replace `chat.py` in a big-bang rewrite;
- introduce a multi-agent conversation framework;
- introduce Redis, Neo4j, or a separate vector database;
- create a new emotion ontology or valence/arousal/dominance model;
- implement M31C `WorkingMemoryState`;
- implement M31F metacognitive behavior;
- compute M31G memory salience;
- implement M32 Habit & Routine Learning;
- implement M33 Consolidation / Dream Cycle;
- change public API response contracts;
- add a trace database table;
- expose cognitive traces to end users;
- treat brain metaphors as mandatory execution topology.

## 1.4. Canonical Terminology

| Term | Definition | Current Aliyya interpretation |
|---|---|---|
| **Turn** | One user request and the assistant processing associated with it. Streaming completion and deferred background work may extend beyond the HTTP request lifecycle. | A send through the chat route plus the resulting assistant message and safe background tasks. |
| **Episode** | A bounded set of turns with coherent topic/goal continuity. | Existing conversation episode/summaries provide an episodic substrate; M31 does not redefine segmentation yet. |
| **Input Surface** | Raw incoming signal plus transport metadata. | User text, attachments, UI context, calendar context, timestamps, future voice/vision inputs. |
| **Perception Signal** | A bounded structured interpretation of input. | Calendar intent/candidates, temporal grounding, personal cues, mood cues, mode commands, attachment context. |
| **Working Memory (WM)** | Ephemeral per-turn cognitive state. | Implicit local variables/results in `chat.py` until M31C formalizes `WorkingMemoryState`. |
| **Retrieval Candidate** | A memory, summary, life-model fact, or other context item available for attention. | Results from memory retrieval, related summaries, life model, calendar/briefing context, etc. |
| **Attention / Context Selection** | Selection/packing of candidates into the bounded LLM context. | `memory_context_packer.py`, `chat_memory_assembly.py`, prompt assembly and history trimming. |
| **Executive Policy** | Deterministic constraints and gates applied to a turn. | Assistant mode commands/settings, calendar confirmation logic, memory gates, M30 comeback suppression, safety/repair gates. |
| **Affect Policy** | Deterministic permission/suppression constraints for expressive companion behavior. | Companion settings, companion mood rules, M30 comeback decision, response texture. It may be resolved before generation. |
| **LLM Reasoning / Generation** | Model inference within the assembled context and constraints. | `claude.py` / Anthropic client path used by chat. |
| **Action** | A side effect or deferred operation. | Calendar draft/confirmation writes, proactive nudge persistence, message persistence, memory background extraction. |
| **Long-Term Memory (LTM)** | Durable personal context and structured life substrate. | `memories`, life model tables, people, goals, events, relationship notes, conversation summaries. |
| **Encoding Gate** | Rule determining whether ephemeral interaction content is eligible for durable memory processing. | `background_extraction_gate.py` and downstream memory extraction/supersession logic. |
| **Feedback / Consolidation** | Deferred processing that updates durable context after the immediate response. | Current memory extraction, relationship memory, goal/mood feedback, summaries; M33 will formalize consolidation. |
| **CognitiveDecisionTrace** | Read-only structured explanation of observable decisions made during one turn. | M31B. Never an input to behavior in M31B. |
| **CognitiveRuntime** | Future facade owning orchestration sequencing and working-memory lifecycle. | M31D onward; not implemented in M31A/M31B. |

### Current mode vocabulary is normative

M31 must preserve the current runtime axes:

- `assistant_mode`: `life_companion | chief_of_staff`
- `companion_mode`: `professional | friendly | affectionate | partner`
- `mood_realism`: `stable | dynamic`

Future modes may be proposed in later ADRs, but M31A/M31B must not fabricate current values such as `assistant`, `coach`, or `focus_mode`.

## 1.5. Logical Cognitive Runtime Model

### 1.5.1. Logical dependencies, not a strict serial pipeline

Aliyya's current runtime performs parallel reads and deferred work. Therefore the cognitive model is a **logical dependency graph**, not a promise that every stage executes serially or exactly once.

```text
                         ┌────────────────────┐
                         │    INPUT SURFACE   │
                         └─────────┬──────────┘
                                   │
                 ┌─────────────────┴─────────────────┐
                 ▼                                   ▼
        ┌──────────────────┐                ┌──────────────────┐
        │ PERCEPTION       │                │ CONTEXT SOURCES  │
        │ signals/gates    │                │ LTM / UI / time  │
        └────────┬─────────┘                └────────┬─────────┘
                 │                                   │
                 └─────────────────┬─────────────────┘
                                   ▼
                         ┌────────────────────┐
                         │ CANDIDATE CONTEXT  │
                         └─────────┬──────────┘
                                   ▼
                         ┌────────────────────┐
                         │ ATTENTION / PACKING│
                         └─────────┬──────────┘
                                   │
                 ┌─────────────────┴──────────────────┐
                 ▼                                    ▼
        ┌──────────────────┐                 ┌──────────────────┐
        │ EXECUTIVE POLICY │                 │ AFFECT POLICY    │
        │ safety/actions   │                 │ allow/suppress   │
        └────────┬─────────┘                 └────────┬─────────┘
                 └─────────────────┬──────────────────┘
                                   ▼
                         ┌────────────────────┐
                         │ CONTEXT ASSEMBLY   │
                         └─────────┬──────────┘
                                   ▼
                         ┌────────────────────┐
                         │ LLM GENERATION     │
                         └─────────┬──────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
          ┌──────────────────┐          ┌────────────────────┐
          │ ACTION COMPLETION│          │ RESPONSE STREAMING │
          │ / DEFERRED WORK  │          └────────────────────┘
          └────────┬─────────┘
                   ▼
          ┌──────────────────┐
          │ FEEDBACK /       │
          │ ENCODING (ASYNC) │
          └──────────────────┘
```

Long-term memory is a **side substrate** read by retrieval/context services and written by approved encoding/persistence paths. It is not a mandatory sequential stage.

### 1.5.2. Input Surface

**Responsibility**
- Validate transport/auth/session input.
- Capture user message, conversation identifier, attachments, and UI/client context.
- Preserve user message even if a non-critical downstream subsystem fails.

**Current owners**
- `backend/app/routers/chat.py`
- attachment handling via `attachments.py`

**Invariant**
- Input handling must not silently invent semantic facts.

### 1.5.3. Perception

**Responsibility**
- Produce bounded signals that downstream logic can use.
- Resolve temporal, calendar, mode, personal, and affect cues where existing services support them.

**Current examples**
- `calendar_candidate_extractor.py`
- `calendar_intent.py`
- `assistant_mode_commands.py`
- `temporal_grounding.py`
- `chat_time_helpers.py`
- `background_extraction_gate.py`
- user/companion mood-related services invoked by `chat.py`

**Invariant**
- LLM-assisted extraction, when used, must be bounded/validated and must not become policy authority.

### 1.5.4. Working Memory

**Responsibility**
- Hold ephemeral outputs/results for the current turn.
- Provide one eventual typed state object in M31C.

**Current state**
- Implicit in `chat.py` local variables and gathered async results.

**Invariant**
- Working memory is not durable memory.
- M31B only observes currently available values; it does not create M31C state.

### 1.5.5. Candidate Context & Attention

**Responsibility**
- Retrieve relevant memory/context candidates.
- Remove inactive/superseded items as existing logic requires.
- Rank and pack within prompt budgets.
- Record which candidate IDs were selected/dropped where that information is currently observable.

**Current owners**
- `memory.py`
- `memory_context_packer.py`
- `chat_memory_assembly.py`
- conversation summaries/episode services
- `life_model.py`
- prompt/history trimming helpers

**Invariant**
- M31B does not invent a new salience model.
- Existing retrieval/packing scores remain observable implementation facts; future canonical salience remains M31G.

### 1.5.6. Executive Policy

**Responsibility**
- Apply deterministic mode/safety/confirmation/authorization constraints.
- Decide whether a proposed side effect may execute, defer, or require confirmation according to existing policy.

**Current examples**
- `assistant_mode_commands.py`
- calendar decision/draft/confirmation services
- `background_extraction_gate.py`
- memory safety/supersession gates
- companion repair/safety logic in `chat.py`

**Invariant**
- Policy constraints may influence prompt/context and action execution.
- The trace mirrors policy; the trace does not decide policy.

### 1.5.7. Affect Policy

**Responsibility**
- Determine whether expressive companion behavior is allowed, suppressed, or not applicable.
- Produce bounded prompt/context directives where existing behavior already does so.

**Current owners/examples**
- `companion.py`
- `companion_comeback_affect.py`
- `response_texture.py`
- user mood and companion mood logic invoked by `chat.py`

**Important runtime fact**
M30 warm comeback is decided **before generation** and may produce a prompt block. Therefore affect is not defined as a mandatory post-LLM transformation.

**Invariant**
- `allowed` means policy permission, not proof that the LLM expressed the affect in final text.

### 1.5.8. Context Assembly

**Responsibility**
- Assemble stable prompt, volatile context, memories, summaries, current app/time context, policy constraints, and bounded history.

**Current owners**
- `prompt_builder.py`
- `chat_memory_assembly.py`
- `chat.py`

**Invariant**
- Context assembly remains behavior-preserving in M31B.

### 1.5.9. LLM Reasoning / Generation

**Responsibility**
- Generate response text within provided context and constraints.

**Current owner**
- `claude.py` and existing Anthropic client invocation path.

**Invariant**
- The LLM is not the source of hard policy truth.

### 1.5.10. Actions and Deferred Feedback

Actions fall into three policy classes:

1. **External or user-visible side effects**
   Examples: calendar mutations or future external API writes. These follow existing confirmation/authorization policy.

2. **Explicitly authorized automations**
   Examples: a reminder/nudge explicitly requested by the user. The user's request may itself be authorization where existing behavior defines it that way.

3. **Internal cognitive persistence**
   Examples: conservative memory extraction, relationship-memory confirmation, summaries, supersession/confidence updates. These are controlled by encoding, provenance, memory-safety, and background-task rules—not by calendar-style confirmation for every row.

**Current owners/examples**
- `calendar_draft_actions.py`
- `calendar_confirmation_actions.py`
- `calendar_pending_actions.py`
- `proactive_nudges.py`
- `memory.py`
- `memory_intelligence.py`
- `relationship_memory.py`
- `safe_background.py`

## 1.6. State & Provenance Taxonomy

State classification and provenance are related but distinct.

### 1.6.1. Lifetime classes

| Class | Meaning | Default storage |
|---|---|---|
| **Ephemeral State** | Exists for the current turn/request or short runtime window. | In process; not durable by default. |
| **Durable State** | Intended to survive sessions and participate in future retrieval. | Supabase/Postgres. |

### 1.6.2. Provenance classes

| Provenance | Meaning | Trust semantics |
|---|---|---|
| **User-Authored Assertion** | Explicit user statement, confirmation, preference, correction, or instruction. | Highest provenance authority over conflicting inference, but may become stale or later change. |
| **User Correction** | Explicit statement that contradicts/replaces prior knowledge. | Highest conflict-resolution priority; should supersede incompatible inferred/older claims according to memory rules. |
| **Inferred State** | Heuristic/LLM-derived signal not explicitly confirmed by the user. | Must retain source/confidence and must not be presented as certain personal truth. |
| **System/Observed State** | State produced by system facts such as calendar result, UI context, timestamps, or tool response. | Authority depends on source freshness and tool reliability. |

### 1.6.3. Rules

- A user-authored assertion is **not eternal truth**. Employment, location, preferences, goals, and relationships can change over time.
- Provenance authority and freshness are separate.
- Explicit user correction outranks incompatible inference.
- Inferred affect remains qualified and time-sensitive.
- Ephemeral state cannot become durable merely because it appeared in the prompt; it must pass an encoding path.
- Durable inferred content must retain inference/provenance metadata supported by the existing storage model.

## 1.7. Score Taxonomy

The architecture reserves four distinct concepts. M31B may only emit values that actually exist at runtime.

| Score | Definition | M31B status |
|---|---|---|
| **Fact Confidence** | Epistemic confidence that a stored assertion/fact is reliable. | Observable where existing memory rows expose `confidence`. |
| **Memory Salience** | Intrinsic importance of a memory to the user's life independent of current query. | **Reserved for M31G. Not computed by M31B.** |
| **Query Relevance** | Relevance to the current turn. May be represented by existing similarity/retrieval scores or route-aware packing signals. | Observable using existing scores; do not relabel every current score as canonical relevance. |
| **Policy Confidence** | Certainty/applicability of a policy decision. | Usually boolean/deterministic today; optional numeric confidence only when an existing heuristic genuinely exposes one. |

### Existing implementation scores are not automatically canonical cognitive scores

For example, `memory_context_packer.py` may use an existing `retrieval_score`, `similarity`, confidence fallback, category bonus, intent bonus, and structured-field bonus to rank packed context. M31B may trace those observable components as implementation metadata. It must not fabricate `salience_score` values before M31G.

## 1.8. Actual Aliyya Module Mapping

This section is grounded in the current repository. Names below are real files/modules, not target abstractions.

| Current module / file | Current cognitive responsibility | M31 note |
|---|---|---|
| `backend/app/routers/chat.py` | Entry point plus broad orchestration across context, memory, calendar, mood, policy, actions, streaming, deferred work. | Instrument first; gradually shrink after M31D. |
| `memory.py` | Durable memory extraction/retrieval, embedding-based matching, ranking support. | LTM retrieval/encoding substrate. |
| `memory_intelligence.py` | Higher-order extraction/evidence/conflict/supersession-related memory processing. | Encoding/consolidation precursor; not rewritten in M31B. |
| `memory_context_packer.py` | Route-aware bounded packing of retrieved memories/summaries. | Current attention implementation surface. |
| `chat_memory_assembly.py` | Chat-facing memory/context assembly helpers. | Current attention/context assembly surface. |
| `memory_retrieval_gate.py` | Determines whether memory retrieval should be attempted. | Retrieval policy signal. |
| `memory_hygiene.py`, `memory_supersession.py` | Memory sanitation/lifecycle/conflict support. | LTM integrity. |
| `conversation_episode.py` and conversation summary services | Episodic continuity and summaries. | Current episodic substrate. |
| `life_model.py` | Identity, mood, people, goals, events and semantic life model access. | Structured LTM substrate. |
| `relationship_memory.py` | Deterministic durable relationship/interaction preference extraction. | Relational memory encoding. |
| `interaction_preferences.py` | Interaction preference context. | Personalization context/policy input. |
| `temporal_grounding.py` | Temporal grounding. | Perception/context signal. |
| `chat_time_helpers.py` | Current-time/timezone chat helpers. | Temporal context. |
| `assistant_mode_commands.py` | Explicit assistant-mode command detection/confirmation. | Executive policy input. |
| `companion.py` | Companion settings/state access. | Policy/affect configuration. |
| `companion_comeback_affect.py` | M30 deterministic warm-return gating and prompt directive. | Affect policy surface; reason codes should mirror its real decisions. |
| `response_texture.py` | Response tone/texture directives. | Affect/presentation context. |
| `user_mood.py` and related mood prompt/feedback services | User mood signals and prompt context. | Affect/perception context with provenance constraints. |
| `calendar_candidate_extractor.py` | Extracts calendar candidates. | Perception. |
| `calendar_intent.py` | Calendar intent interpretation. | Perception/action intent. |
| `calendar_decision_router.py` | Routes calendar decision paths. | Executive/action policy. |
| `calendar_draft_actions.py` | Calendar draft action flow. | Action planning/defer. |
| `calendar_confirmation_actions.py` | Confirmation-based calendar action execution. | External mutation authorization. |
| `calendar_pending_actions.py` | Pending calendar action state. | Deferred action substrate. |
| `calendar_conflicts.py` | Calendar conflict support. | Action safety/context. |
| `proactive_nudges.py` | Deterministic reminder parsing, persistence, scheduler behavior. | Explicitly authorized automation / future habit substrate. |
| `background_extraction_gate.py` | Determines whether background memory extraction should run. | Encoding gate. |
| `safe_background.py` | Safe deferred-task execution boundary. | Failure isolation for feedback/actions. |
| `prompt_builder.py` | Base/volatile prompt rendering and history trimming. | Context assembly. |
| `claude.py` | Anthropic/Claude model access. | LLM generation. |
| `supabase_client.py` | Durable data access helper. | Persistence substrate, not a cognitive layer itself. |

This map is not exhaustive. M31B should instrument only observable surfaces needed for the v1 trace rather than attempting to trace every service import.

## 1.9. Dependency-Direction Rules

1. `chat.py` may orchestrate existing services during M31A–M31C, but services must not depend on `chat.py`.
2. Future `CognitiveRuntime` may depend on existing services; existing services must not depend on `CognitiveRuntime`.
3. `CognitiveDecisionTrace` instrumentation is observational. Cognitive behavior must not depend on it in M31B.
4. LTM reads may occur while other context reads occur in parallel.
5. Perception may perform bounded read-only reference resolution where needed.
6. Affect policy and executive policy may both contribute constraints before the LLM call.
7. Action execution may be immediate, deferred, or background according to existing semantics; action ordering is not inferred from the brain metaphor.
8. Feedback/encoding may run after the response and must remain safe-background/fail-open where current behavior permits.
9. No new circular dependency is introduced to make trace collection convenient.
10. Trace sinks may depend on trace DTOs; cognitive modules must not depend on a concrete sink implementation.

## 1.10. `chat.py` Contract

### During M31 transition

`chat.py` remains the runtime entry point and may continue to orchestrate existing services while M31B observes it.

### Target post-M31E responsibilities

`chat.py` should retain:

- FastAPI request/auth/validation boundaries;
- API serialization and streaming response handling;
- top-level graceful HTTP error handling;
- delegation to the `CognitiveRuntime` facade;
- backward-compatible request/response contracts.

Responsibilities gradually migrated away from `chat.py`:

- direct context-source orchestration;
- memory/context packing decisions;
- inline deterministic policy rules;
- prompt concatenation across many subsystems;
- direct side-effect routing that belongs in action services.

### Migration marker

M31B may emit stable legacy markers such as:

- `legacy.chatpy.orchestrates_memory`
- `legacy.chatpy.assembles_context`
- `legacy.chatpy.applies_affect_policy`
- `legacy.chatpy.routes_actions`

Markers are observability only; they do not create technical debt enforcement logic in M31B.

## 1.11. `CognitiveRuntime` Future Ownership

Beginning in M31D, `CognitiveRuntime` becomes a facade around existing services. It eventually owns:

- turn-level orchestration sequencing;
- `WorkingMemoryState` lifecycle after M31C;
- calling retrieval/context sources;
- invoking attention/context assembly;
- applying executive and affect policy outputs;
- preparing model-call inputs;
- routing actions to existing action services;
- finalizing the cognitive trace.

It does **not** own:

- Postgres schema/RPC implementation;
- model-client internals;
- provider-specific calendar APIs;
- durable memory algorithms that already belong to memory services;
- M33 consolidation internals;
- trace persistence infrastructure in M31B.

## 1.12. Failure Isolation

| Failure surface | Safe degradation | Must never |
|---|---|---|
| Optional perception helper | Omit unavailable signal or use existing fallback. | Invent a high-confidence fact. |
| Memory retrieval | Continue with no retrieved memories if existing chat behavior permits. | Crash the whole turn solely because optional memory failed. |
| Life model/context source | Omit that context and record degradation. | Fabricate substitute personal context. |
| Affect helper | Use neutral/safe existing fallback. | Leak disallowed companion affect. |
| Calendar/tool side effect | Report or preserve existing failure path. | Pretend a mutation succeeded. |
| LLM call | Preserve existing graceful model-error behavior. | Lose already-saved user input. |
| Background encoding | Warn and fail safely. | Break an already completed response. |
| Trace recorder/sink | Drop trace or sink emission. | Affect user-facing chat behavior. |

**Golden rule:** trace collection is non-critical and fail-open.

## 1.13. Observability Requirements

M31B must make currently observable decisions explainable without pretending later M31 capabilities already exist.

Minimum decision surfaces:

- detected/available perception signals used by current routing;
- memory retrieval gate outcome and retrieval result counts;
- selected memory/summary IDs where current packing exposes them;
- context packing counts/budgets;
- current assistant/companion/mood-realism settings relevant to policy;
- M30 warm-comeback decision and underlying suppression reason;
- known action intent / confirmation / deferred-action decisions;
- context section sizes where cheaply measurable;
- subsystem health/degradation and bounded latency metrics;
- legacy `chat.py` orchestration markers.

M31B must not claim complete traceability for M31C Working Memory, M31F metacognition, or M31G salience before those components exist.

## 1.14. Migration Strategy

```text
M31A  →  M31B  →  M31C  →  M31D  →  M31E  →  M31F  →  M31G
 ADR     Trace    WM State  Runtime   Extract   Meta-     Attention/
          v1       v1        Facade    modules   cognition  Salience v1
```

### Phase rules

- **M31A:** documentation only.
- **M31B:** read-only trace instrumentation against existing behavior.
- **M31C:** formalize `WorkingMemoryState`; do not change user behavior by default.
- **M31D:** add `CognitiveRuntime` facade delegating to existing services.
- **M31E:** move orchestration responsibilities incrementally with full regression gates.
- **M31F:** add deterministic metacognitive policy after evidence/trace substrate exists.
- **M31G:** formalize attention/salience model; only then introduce canonical salience values.

Every phase must pass targeted tests plus full backend regression before moving on. Public API contracts stay backward-compatible unless a separate ADR explicitly changes them.

## 1.15. Rejected Alternatives

| Alternative | Decision |
|---|---|
| Generic Cortex stack: Pinecone + Neo4j + Redis + LangChain | Rejected for M31. Existing Supabase/pgvector and structured life model already solve the current substrate needs. |
| Multi-agent chatter via CrewAI/AutoGen | Rejected. Higher latency/cost/failure surface without demonstrated need. |
| Neuromorphic/SNN implementation | Rejected. No current product problem solved. |
| Redis immediately | Deferred. Keep store boundaries adapter-ready; introduce only after multi-process/shared-state pain appears. |
| Persistent event-driven graph immediately | Deferred. Current graph projection is read-only; no demonstrated stale-materialization problem. |
| AffectVector VAD model | Deferred. Current source/confidence mood semantics are safer and grounded. |
| Retrieval-frequency reinforcement | Rejected as a default salience update because it creates self-reinforcing retrieval loops. |
| Auto-learn habits after three occurrences | Rejected. Future habit candidates require temporal spread and user consent. |
| User-facing “dreaming” narrative | Rejected. Future consolidation remains transparent rather than implying consciousness. |
| Big-bang `chat.py` rewrite | Rejected. Facade-first migration is mandatory. |

---

# 2. M31B — CognitiveDecisionTrace Spec

## 2.1. Purpose & Constraints

**Purpose:** create a cheap, read-only, structured mirror of decisions that the current Aliyya runtime already makes, so developers can answer “why did this turn behave this way?” before orchestration is refactored.

Constraints:

- no behavior changes;
- trace failure never breaks chat;
- no new database table;
- no new external infrastructure;
- no user-facing trace endpoint/UI;
- no trace-derived policy decisions;
- no mandatory raw-content logging;
- tests must run without Anthropic/Supabase credentials wherever the tested code is pure;
- instrumentation overhead must be bounded and measured;
- schema must represent missing/not-yet-implemented values honestly as `None`/absent rather than fabricating them.

## 2.2. Design Philosophy

1. **Mirror, not controller.** Trace records decisions after/while they occur; it never supplies the decision input.
2. **Actual runtime over ideal architecture.** M31B traces what Aliyya does today.
3. **Structured reason codes over prose.** Human notes are optional diagnostics.
4. **Metadata over content.** Production-safe trace serialization prefers counts, IDs/hashed refs, booleans, scores, categories, reason codes, and latency.
5. **Absence is honest.** If M31G salience does not exist, M31B says `salience_score=None` rather than inventing one.
6. **Partial trace is valid.** A turn may have no calendar intent, no memory retrieval, or a degraded subsystem.
7. **Extensible sections.** M31C/M31F/M31G may add new trace sections later without pretending they exist in M31B.
8. **Sink-independent.** Trace DTOs do not know whether the trace is dropped, logged, or captured by tests.

## 2.3. Trace Boundaries

M31B v1 covers the following currently observable surfaces:

- turn identity/metadata;
- perception/routing signals that are already produced;
- memory retrieval gate/result metadata;
- memory-context packing metadata;
- current policy settings and selected deterministic decisions;
- M30 warm-comeback decision;
- current action intent/defer/confirmation metadata when observable;
- context-size metadata;
- subsystem health/latency;
- legacy orchestration markers.

M31B does **not** promise a separate section for every future cognitive layer.

## 2.4. Type Specifications

Pseudocode below defines the contract. Exact implementation may use frozen dataclasses, Pydantic models, or typed dictionaries if tests prove a simpler representation is safer.

Required fields are marked **REQUIRED**. Optional fields must have safe defaults.

```python
@dataclass
class CognitiveDecisionTrace:
    trace_id: str                       # REQUIRED, random internal ID
    version: str                        # REQUIRED, "M31B-v1"
    timestamp_utc: datetime             # REQUIRED

    turn_ref: str | None = None         # internal turn/message ref if available
    conversation_ref: str | None = None # internal ref; logging sink may hash/redact
    user_ref: str | None = None         # internal only; production log sink hashes/removes

    perception: PerceptionTrace | None = None
    memory: MemoryTrace | None = None
    attention: AttentionTrace | None = None
    policy: PolicyTrace | None = None
    action: ActionTrace | None = None
    context: ContextAssemblyTrace | None = None

    subsystem_health: list[SubsystemHealth] = field(default_factory=list)
    legacy_markers: list[str] = field(default_factory=list)


@dataclass
class PerceptionTrace:
    route_signals: list[str] = field(default_factory=list)
    personal_cue: bool | None = None
    temporal: list[TemporalTrace] = field(default_factory=list)
    calendar_candidate_detected: bool | None = None
    mode_command_detected: bool | None = None
    latency_ms: float | None = None


@dataclass
class TemporalTrace:
    resolution_type: str                # absolute | relative | ambiguous | none
    resolved_iso: str | None = None
    confidence: float | None = None      # only if source actually exposes confidence
    raw_preview: str | None = None       # dev/redacted preview policy only


@dataclass
class MemoryTrace:
    retrieval_attempted: bool
    retrieval_gate_reason: str | None = None
    retrieval_strategy: str | None = None
    total_candidates: int = 0
    candidates: list[MemoryCandidateTrace] = field(default_factory=list)
    latency_ms: float | None = None
    subsystem_status: str = "healthy"   # healthy | degraded | failed | not_applicable


@dataclass
class MemoryCandidateTrace:
    memory_ref: str
    category: str | None = None
    structured_field: str | None = None

    similarity_score: float | None = None
    retrieval_score: float | None = None
    confidence_score: float | None = None
    packing_score: float | None = None
    salience_score: float | None = None  # MUST remain None until M31G provides it

    selected_for_prompt: bool | None = None
    reason_codes: list[str] = field(default_factory=list)
    preview: str | None = None           # controlled by preview policy


@dataclass
class AttentionTrace:
    packing_intent: str | None = None    # current packer intent, e.g. general/identity/self_regulation
    selected_memory_refs: list[str] = field(default_factory=list)
    selected_summary_refs: list[str] = field(default_factory=list)
    dropped_memory_count: int = 0
    dropped_summary_count: int = 0
    packed_context_chars: int | None = None
    packed_context_budget_chars: int | None = None
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class PolicyTrace:
    assistant_mode: str | None = None        # current: life_companion | chief_of_staff
    companion_mode: str | None = None        # professional | friendly | affectionate | partner
    mood_realism: str | None = None          # stable | dynamic

    affect_rules: list[AffectRuleTrace] = field(default_factory=list)
    confirmation_requirements: list[ConfirmationTrace] = field(default_factory=list)
    policy_markers: list[str] = field(default_factory=list)


@dataclass
class AffectRuleTrace:
    rule_id: str
    decision: str                       # allowed | suppressed | not_applicable
    reason_codes: list[str] = field(default_factory=list)
    runtime_reason: str | None = None   # bounded existing subsystem reason, e.g. serious_work_task


@dataclass
class ConfirmationTrace:
    action_type: str
    required: bool
    reason_codes: list[str] = field(default_factory=list)
    authorization_source: str | None = None


@dataclass
class ActionTrace:
    detected_intents: list[str] = field(default_factory=list)
    executed: list[ActionRecordTrace] = field(default_factory=list)
    deferred: list[ActionRecordTrace] = field(default_factory=list)
    latency_ms: float | None = None


@dataclass
class ActionRecordTrace:
    action_type: str
    status: str                         # success | failed | deferred | skipped
    reason_codes: list[str] = field(default_factory=list)
    target_ref: str | None = None


@dataclass
class ContextAssemblyTrace:
    total_context_chars: int | None = None
    sections: list[ContextSectionTrace] = field(default_factory=list)
    history_message_count: int | None = None
    truncation_occurred: bool | None = None
    reason_codes: list[str] = field(default_factory=list)


@dataclass
class ContextSectionTrace:
    section_type: str
    char_count: int
    item_count: int | None = None
    preview: str | None = None           # controlled by preview policy


@dataclass
class SubsystemHealth:
    subsystem: str
    status: str                         # healthy | degraded | failed | not_applicable
    reason_codes: list[str] = field(default_factory=list)
    latency_ms: float | None = None
```

### Why no mandatory `detected_intent` enum?

The existing chat path has multiple specialized detectors rather than one canonical global intent classifier. M31B therefore records actual route/perception signals instead of inventing a single authoritative classifier. A canonical intent model may be introduced later if M31C/M31D need it.

### Why is `salience_score` present but optional?

The field is reserved for forward-compatible serialization, but M31B must emit `null`/omit it. M31G defines the canonical salience model.

## 2.5. Trace Sink & Privacy Model

### 2.5.1. TraceRecorder boundary

M31B specifies a tiny fail-open recorder/sink abstraction:

```python
class TraceSink(Protocol):
    def emit(self, trace: CognitiveDecisionTrace) -> None: ...

class NullTraceSink:
    """Default production behavior when diagnostic logging is disabled."""

class LoggingTraceSink:
    """Optional compact structured diagnostic logging."""

class TestTraceSink:
    """Captures traces in memory for unit/integration tests."""
```

The exact implementation may use async methods if integration requires it. Sink failure must be caught outside cognitive behavior.

### 2.5.2. Preview policy

```text
none      → no user/message/memory/entity/prompt previews
redacted  → bounded redacted previews after secret/PII scrubbing
          → intended only for controlled developer diagnostics

dev       → bounded developer previews; never production default
```

**Production default: `none`.**

`COGNITIVE_TRACE_LOG=false` is the default production setting. If structured logging is temporarily enabled, the production serializer still defaults to `preview_policy=none` unless an operator intentionally changes it in a controlled diagnostic environment.

### 2.5.3. Identifier policy

- In-memory trace may use internal IDs needed for same-process inspection/tests.
- Logging serialization should omit or pseudonymize `user_ref` and other sensitive identifiers.
- Secrets are never trace fields.
- Do not serialize full request bodies, full memories, full prompt sections, access tokens, API keys, attachment bytes, or provider credentials.

### 2.5.4. Persistence options

| Option | M31B decision |
|---|---|
| In-memory object | **Required baseline.** |
| `NullTraceSink` | **Default production sink.** |
| Optional structured application log | Allowed for controlled diagnostics; default off. |
| Supabase trace table | **Out of scope.** Revisit only if historical inspector use justifies storage. |
| Response header / public trace ID | **Out of scope.** An ID without a retrieval store is not useful and changes the HTTP surface unnecessarily. |

## 2.6. Reason-Code Taxonomy

Reason codes are stable machine-readable explanations. Free-form notes are secondary.

### 2.6.1. Trace lifecycle

```text
trace.created
trace.finalized
trace.sink.skipped_disabled
trace.sink.failed
trace.preview.none
trace.preview.redacted
trace.preview.dev
```

### 2.6.2. Memory retrieval and attention

```text
memory.retrieval.skipped.gate
memory.retrieval.completed
memory.retrieval.degraded
memory.retrieved.semantic_match
memory.retrieved.structured_field
memory.retrieved.personal_cue_threshold
memory.selected.packed
memory.dropped.context_budget
memory.dropped.inactive
memory.dropped.category_limit
memory.dropped.item_limit
memory.dropped.low_similarity
memory.dropped.low_relevance
memory.dropped.conflict_unresolved
memory.dropped.privacy_filter
attention.intent.general
attention.intent.identity
attention.intent.self_regulation
attention.truncated.memory_budget
attention.truncated.total_budget
```

M31B does **not** define `memory.selected.high_salience` or `memory.dropped.low_salience`, because canonical salience does not yet exist.

### 2.6.3. Warm comeback / affect

These codes map directly from M30 deterministic runtime reasons:

```text
affect.warm_comeback.allowed.safe_return
affect.warm_comeback.suppressed.mode_not_partner_dynamic
affect.warm_comeback.suppressed.assistant_mode_not_life_companion
affect.warm_comeback.suppressed.user_distressed
affect.warm_comeback.suppressed.urgent_or_crisis
affect.warm_comeback.suppressed.serious_work_task
affect.warm_comeback.suppressed.cooldown_active
affect.warm_comeback.suppressed.insufficient_history
affect.warm_comeback.suppressed.gap_below_minimum
affect.warm_comeback.suppressed.gap_not_meaningful_vs_cadence
```

Other affect rules may introduce their own codes only when grounded in actual existing deterministic outputs.

### 2.6.4. Assistant/companion policy

```text
policy.assistant_mode.life_companion
policy.assistant_mode.chief_of_staff
policy.companion_mode.professional
policy.companion_mode.friendly
policy.companion_mode.affectionate
policy.companion_mode.partner
policy.mood_realism.stable
policy.mood_realism.dynamic
policy.command.explicit_assistant_mode
policy.fallback.safe_default
```

### 2.6.5. Action and authorization

```text
action.detected.calendar
action.detected.reminder
action.detected.memory_encoding
action.requires_confirmation.calendar_write
action.authorized.explicit_user_request
action.deferred.requires_confirmation
action.executed.success
action.executed.failed
action.skipped.policy_gate
action.background.encoding_scheduled
action.background.encoding_skipped
```

### 2.6.6. Temporal/perception

```text
temporal.resolved.absolute
temporal.resolved.relative
temporal.ambiguous
temporal.none
perception.personal_cue.detected
perception.mode_command.detected
perception.calendar_candidate.detected
```

### 2.6.7. Subsystem health

```text
subsystem.healthy
subsystem.degraded.memory_retrieval
subsystem.failed.memory_retrieval
subsystem.degraded.life_model
subsystem.failed.life_model
subsystem.degraded.calendar
subsystem.failed.calendar
subsystem.degraded.temporal
subsystem.failed.temporal
subsystem.degraded.trace_sink
subsystem.failed.llm
```

### 2.6.8. Legacy orchestration markers

```text
legacy.chatpy.orchestrates_memory
legacy.chatpy.assembles_context
legacy.chatpy.applies_affect_policy
legacy.chatpy.routes_actions
```

### Taxonomy rule

Every reason-code string appearing in M31B example JSON or test fixtures must be declared in §2.6. A unit test should enforce this when implementation begins.

## 2.7. Example Traces

Examples intentionally omit raw personal content. They show the **production-safe conceptual shape**, not a promise that every optional field is populated in every turn.

### 2.7.1. Casual life-companion conversation

```json
{
  "trace_id": "tr_demo_001",
  "version": "M31B-v1",
  "timestamp_utc": "2026-09-01T01:00:00Z",
  "perception": {
    "route_signals": [],
    "personal_cue": false,
    "temporal": [],
    "calendar_candidate_detected": false,
    "mode_command_detected": false
  },
  "memory": {
    "retrieval_attempted": true,
    "retrieval_gate_reason": null,
    "retrieval_strategy": "semantic",
    "total_candidates": 3,
    "candidates": [
      {
        "memory_ref": "mem_hash_a1",
        "category": "relationships",
        "similarity_score": 0.81,
        "retrieval_score": 0.88,
        "confidence_score": 0.86,
        "packing_score": 1.31,
        "salience_score": null,
        "selected_for_prompt": true,
        "reason_codes": [
          "memory.retrieved.semantic_match",
          "memory.selected.packed"
        ],
        "preview": null
      }
    ],
    "latency_ms": 42.0,
    "subsystem_status": "healthy"
  },
  "attention": {
    "packing_intent": "general",
    "selected_memory_refs": ["mem_hash_a1"],
    "selected_summary_refs": [],
    "dropped_memory_count": 2,
    "dropped_summary_count": 0,
    "packed_context_chars": 260,
    "packed_context_budget_chars": 2200,
    "reason_codes": ["attention.intent.general"]
  },
  "policy": {
    "assistant_mode": "life_companion",
    "companion_mode": "partner",
    "mood_realism": "dynamic",
    "affect_rules": [
      {
        "rule_id": "warm_comeback",
        "decision": "not_applicable",
        "reason_codes": [],
        "runtime_reason": null
      }
    ],
    "confirmation_requirements": [],
    "policy_markers": [
      "policy.assistant_mode.life_companion",
      "policy.companion_mode.partner",
      "policy.mood_realism.dynamic"
    ]
  },
  "action": {
    "detected_intents": [],
    "executed": [],
    "deferred": []
  },
  "context": {
    "total_context_chars": 2840,
    "sections": [
      {"section_type": "stable_prompt", "char_count": 900, "item_count": null, "preview": null},
      {"section_type": "memory_context", "char_count": 260, "item_count": 1, "preview": null},
      {"section_type": "history", "char_count": 1680, "item_count": 8, "preview": null}
    ],
    "history_message_count": 8,
    "truncation_occurred": false,
    "reason_codes": []
  },
  "subsystem_health": [
    {"subsystem": "memory", "status": "healthy", "reason_codes": ["subsystem.healthy"], "latency_ms": 42.0}
  ],
  "legacy_markers": [
    "legacy.chatpy.orchestrates_memory",
    "legacy.chatpy.assembles_context"
  ]
}
```

### 2.7.2. Serious work suppresses M30 warm comeback without changing assistant mode

```json
{
  "trace_id": "tr_demo_002",
  "version": "M31B-v1",
  "timestamp_utc": "2026-09-01T02:00:00Z",
  "perception": {
    "route_signals": ["calendar_candidate"],
    "personal_cue": false,
    "temporal": [
      {
        "resolution_type": "relative",
        "resolved_iso": "2026-09-02T09:00:00+07:00",
        "confidence": null,
        "raw_preview": null
      }
    ],
    "calendar_candidate_detected": true,
    "mode_command_detected": false
  },
  "memory": {
    "retrieval_attempted": true,
    "retrieval_strategy": "semantic",
    "total_candidates": 2,
    "candidates": [],
    "subsystem_status": "healthy"
  },
  "attention": {
    "packing_intent": "general",
    "selected_memory_refs": [],
    "selected_summary_refs": [],
    "dropped_memory_count": 2,
    "dropped_summary_count": 0,
    "packed_context_chars": 0,
    "packed_context_budget_chars": 2200,
    "reason_codes": ["attention.intent.general"]
  },
  "policy": {
    "assistant_mode": "life_companion",
    "companion_mode": "partner",
    "mood_realism": "dynamic",
    "affect_rules": [
      {
        "rule_id": "warm_comeback",
        "decision": "suppressed",
        "reason_codes": ["affect.warm_comeback.suppressed.serious_work_task"],
        "runtime_reason": "serious_work_task"
      }
    ],
    "confirmation_requirements": [
      {
        "action_type": "calendar_write",
        "required": true,
        "reason_codes": ["action.requires_confirmation.calendar_write"],
        "authorization_source": null
      }
    ],
    "policy_markers": [
      "policy.assistant_mode.life_companion",
      "policy.companion_mode.partner",
      "policy.mood_realism.dynamic"
    ]
  },
  "action": {
    "detected_intents": ["calendar"],
    "executed": [],
    "deferred": [
      {
        "action_type": "calendar_write",
        "status": "deferred",
        "reason_codes": ["action.deferred.requires_confirmation"],
        "target_ref": null
      }
    ]
  },
  "context": {
    "total_context_chars": 3050,
    "sections": [],
    "history_message_count": 10,
    "truncation_occurred": false,
    "reason_codes": []
  },
  "subsystem_health": [
    {"subsystem": "calendar", "status": "healthy", "reason_codes": ["subsystem.healthy"], "latency_ms": 18.0}
  ],
  "legacy_markers": [
    "legacy.chatpy.applies_affect_policy",
    "legacy.chatpy.routes_actions"
  ]
}
```

### 2.7.3. Eight memory candidates, two packed; no fabricated salience

```json
{
  "trace_id": "tr_demo_003",
  "version": "M31B-v1",
  "timestamp_utc": "2026-09-01T03:00:00Z",
  "memory": {
    "retrieval_attempted": true,
    "retrieval_gate_reason": null,
    "retrieval_strategy": "semantic",
    "total_candidates": 8,
    "candidates": [
      {
        "memory_ref": "mem_hash_001",
        "category": "goals",
        "similarity_score": 0.91,
        "retrieval_score": 1.08,
        "confidence_score": 0.85,
        "packing_score": 1.29,
        "salience_score": null,
        "selected_for_prompt": true,
        "reason_codes": ["memory.retrieved.semantic_match", "memory.selected.packed"],
        "preview": null
      },
      {
        "memory_ref": "mem_hash_002",
        "category": "projects",
        "similarity_score": 0.88,
        "retrieval_score": 0.96,
        "confidence_score": 0.80,
        "packing_score": 1.07,
        "salience_score": null,
        "selected_for_prompt": false,
        "reason_codes": ["memory.retrieved.semantic_match", "memory.dropped.context_budget"],
        "preview": null
      },
      {
        "memory_ref": "mem_hash_003",
        "category": "goals",
        "similarity_score": 0.86,
        "retrieval_score": 1.04,
        "confidence_score": 0.92,
        "packing_score": 1.26,
        "salience_score": null,
        "selected_for_prompt": true,
        "reason_codes": ["memory.retrieved.structured_field", "memory.selected.packed"],
        "preview": null
      }
    ],
    "latency_ms": 55.0,
    "subsystem_status": "healthy"
  },
  "attention": {
    "packing_intent": "general",
    "selected_memory_refs": ["mem_hash_001", "mem_hash_003"],
    "selected_summary_refs": [],
    "dropped_memory_count": 6,
    "dropped_summary_count": 0,
    "packed_context_chars": 570,
    "packed_context_budget_chars": 2200,
    "reason_codes": ["attention.intent.general", "attention.truncated.memory_budget"]
  },
  "policy": {
    "assistant_mode": "chief_of_staff",
    "companion_mode": "partner",
    "mood_realism": "dynamic",
    "affect_rules": [
      {
        "rule_id": "warm_comeback",
        "decision": "suppressed",
        "reason_codes": ["affect.warm_comeback.suppressed.assistant_mode_not_life_companion"],
        "runtime_reason": "assistant_mode_not_life_companion"
      }
    ],
    "confirmation_requirements": [],
    "policy_markers": [
      "policy.assistant_mode.chief_of_staff",
      "policy.companion_mode.partner",
      "policy.mood_realism.dynamic"
    ]
  },
  "subsystem_health": [
    {"subsystem": "memory", "status": "healthy", "reason_codes": ["subsystem.healthy"], "latency_ms": 55.0}
  ],
  "legacy_markers": ["legacy.chatpy.orchestrates_memory"]
}
```

### 2.7.4. Degraded memory retrieval while chat continues

```json
{
  "trace_id": "tr_demo_004",
  "version": "M31B-v1",
  "timestamp_utc": "2026-09-01T04:00:00Z",
  "memory": {
    "retrieval_attempted": true,
    "retrieval_gate_reason": null,
    "retrieval_strategy": "semantic",
    "total_candidates": 0,
    "candidates": [],
    "latency_ms": 3200.0,
    "subsystem_status": "degraded"
  },
  "attention": {
    "packing_intent": "general",
    "selected_memory_refs": [],
    "selected_summary_refs": [],
    "dropped_memory_count": 0,
    "dropped_summary_count": 0,
    "packed_context_chars": 0,
    "packed_context_budget_chars": 2200,
    "reason_codes": ["attention.intent.general"]
  },
  "policy": {
    "assistant_mode": "life_companion",
    "companion_mode": "friendly",
    "mood_realism": "stable",
    "affect_rules": [
      {
        "rule_id": "warm_comeback",
        "decision": "suppressed",
        "reason_codes": ["affect.warm_comeback.suppressed.mode_not_partner_dynamic"],
        "runtime_reason": "mode_not_partner_dynamic"
      }
    ],
    "confirmation_requirements": [],
    "policy_markers": [
      "policy.assistant_mode.life_companion",
      "policy.companion_mode.friendly",
      "policy.mood_realism.stable"
    ]
  },
  "context": {
    "total_context_chars": 1700,
    "sections": [
      {"section_type": "stable_prompt", "char_count": 900, "item_count": null, "preview": null},
      {"section_type": "history", "char_count": 800, "item_count": 4, "preview": null}
    ],
    "history_message_count": 4,
    "truncation_occurred": false,
    "reason_codes": []
  },
  "subsystem_health": [
    {
      "subsystem": "memory",
      "status": "degraded",
      "reason_codes": ["subsystem.degraded.memory_retrieval"],
      "latency_ms": 3200.0
    }
  ],
  "legacy_markers": ["legacy.chatpy.orchestrates_memory"]
}
```

## 2.8. Test Matrices

### 2.8.1. Pure unit tests

These tests must not require Anthropic/Supabase credentials.

| Test | Assertion |
|---|---|
| `test_trace_minimal_serialization` | Required fields serialize; optional sections may be absent. |
| `test_trace_reason_codes_are_known` | Unknown reason code is rejected or explicitly classified as an implementation error. |
| `test_example_reason_codes_match_taxonomy` | All reason codes in checked-in example fixtures are declared. |
| `test_preview_policy_none_removes_content` | Production-safe serializer emits no previews. |
| `test_preview_policy_redacted_bounds_content` | Redacted preview is bounded and scrubbed. |
| `test_logging_sink_disabled` | Disabled logging does not emit. |
| `test_sink_failure_is_fail_open` | Sink exception is contained and does not propagate into cognitive flow. |
| `test_memory_candidate_salience_is_none_in_m31b` | M31B never fabricates canonical salience. |
| `test_affect_decision_enum` | Only `allowed`, `suppressed`, `not_applicable`. |
| `test_current_mode_enums` | Trace accepts current runtime modes and examples use no fabricated modes. |
| `test_semantic_trace_determinism` | For deterministic fixtures, semantic decision fields match; trace ID/timestamp/latency are excluded. |

### 2.8.2. Integration tests

Trace contract assertions are allowed. Behavioral correctness must still be asserted independently.

| Test | Behavior assertion | Trace assertion |
|---|---|---|
| `test_chat_trace_is_non_breaking` | Existing chat response succeeds. | `TestTraceSink` receives a trace. |
| `test_memory_degraded_chat_still_uses_existing_fallback` | Chat follows existing graceful fallback. | Memory health is degraded/failed with canonical reason code. |
| `test_m30_serious_work_behavior_and_trace` | Warm-comeback directive is not injected for serious work. | Trace mirrors `serious_work_task`; assistant mode is unchanged. |
| `test_m30_chief_of_staff_behavior_and_trace` | Warm comeback remains suppressed. | Trace maps `assistant_mode_not_life_companion`. |
| `test_memory_packing_trace_matches_packer` | Prompt receives the same packed memory result as before instrumentation. | Selected IDs/counts mirror `PackedMemoryContext`. |
| `test_calendar_confirmation_behavior_and_trace` | Existing confirmation/defer behavior is unchanged. | Trace mirrors confirmation requirement/defer outcome. |
| `test_trace_sink_exception_does_not_change_response` | Response body/status matches control case. | Sink failure is contained. |
| `test_trace_overhead_budget` | No material regression to existing turn path under controlled benchmark. | Record instrumentation overhead separately. |

### Testing rule

A test may assert trace contents to validate the **trace contract**. It must not use the trace as the sole evidence that chat behavior is correct. Where behavior matters, assert both behavior and trace reflection.

## 2.9. Rollout Plan

M31B is diagnostic infrastructure, not a user cohort feature. No 10% beta-user rollout is needed.

1. Merge M31A ADR after final architecture gate.
2. Implement pure DTOs, reason-code registry, serializer, and `NullTraceSink`/`TestTraceSink`.
3. Add unit tests with no runtime credentials.
4. Wire read-only trace collection into existing `chat.py` at a small number of observable decision surfaces.
5. Run targeted M31B tests.
6. Run full backend regression.
7. Measure local instrumentation overhead.
8. Deploy with `COGNITIVE_TRACE_LOG=false` and production preview policy `none`.
9. If needed, enable structured diagnostic logging temporarily under operator control, inspect output, then disable again.
10. Only after M31B is stable begin M31C Working Memory formalization.

## 2.10. Definition of Done

M31A:

- [ ] Revision 0.2 passes final architecture gate.
- [ ] ADR uses actual Aliyya module names and current mode enums.
- [ ] Logical runtime model does not falsely require serial execution.
- [ ] State/provenance and score taxonomies are locked.
- [ ] ADR merged into `docs/M31_COGNITIVE_ARCHITECTURE_ADR.md`.

M31B:

- [ ] Trace DTOs/type contracts implemented with explicit required/optional fields.
- [ ] Canonical reason-code registry implemented.
- [ ] `NullTraceSink`, `LoggingTraceSink`, and `TestTraceSink` boundaries implemented or equivalent names documented in code.
- [ ] Production logging default is off.
- [ ] Production preview policy defaults to `none`.
- [ ] No new DB table or infrastructure.
- [ ] No public trace header/API/UI.
- [ ] Trace failure is fail-open.
- [ ] M31B does not compute canonical salience.
- [ ] M30 warm-comeback trace maps actual runtime suppression reasons.
- [ ] Trace contract tests and behavioral tests are separated appropriately.
- [ ] All example reason codes validate against taxonomy.
- [ ] Targeted tests pass.
- [ ] Full backend regression passes.
- [ ] No material latency regression attributable to trace instrumentation.
- [ ] Existing chat/API behavior remains unchanged.

## 2.11. Explicit Exclusions

M31B must not implement:

- trace-driven policy or feedback loops;
- metacognitive policy;
- canonical memory salience computation;
- WorkingMemoryState mutation/ownership;
- CognitiveRuntime facade;
- persistent trace table;
- public/user-facing trace endpoint;
- trace ID response headers;
- product analytics dashboards;
- cross-turn cognitive trace graph;
- automatic habit learning;
- consolidation/dream cycle;
- new global intent classifier solely to make the trace look cleaner;
- output-text inspection that claims whether an allowed affect was actually expressed;
- new Redis/Neo4j/vector infrastructure.

---

# 3. Resolved Review Findings

| Review finding from v0.1 | v0.2 resolution |
|---|---|
| Generic module names did not match repo | Replaced with actual `chat.py` imports/services and current repository files. |
| Strict linear pipeline contradicted parallel/deferred runtime | Replaced with logical dependency graph and side-substrate LTM model. |
| Affect incorrectly modeled only after LLM | Affect policy now explicitly may constrain prompt before generation. |
| Fabricated `assistant` / `coach` / `focus_mode` | Current runtime enums are normative: `life_companion | chief_of_staff`; companion mode remains separate. |
| Serious-work example changed mode | Corrected: serious work suppresses M30 affect without switching `assistant_mode`. |
| `salience_score` required before M31G | Made optional/reserved and `null` in M31B examples. |
| M31B claimed every future layer had a trace section | Scope changed to currently observable decision surfaces. |
| All mutations required confirmation | Split external mutations, explicit automation, and internal cognitive persistence. |
| `User-Authored Truth` too absolute | Renamed `User-Authored Assertion`; provenance and freshness separated. |
| Trace tests contradicted explicit exclusions | Trace contract assertions allowed; behavioral tests independently assert behavior. |
| Full trace idempotency unrealistic | Determinism applies to semantic decision fields, excluding IDs/timestamps/latency. |
| Trace response header had no retrieval store | Removed from M31B. |
| Bounded previews still leaked content | Added `none | redacted | dev`; production default `none`. |
| Reason-code examples/taxonomy diverged | Rebuilt taxonomy and examples; automated validation required. |
| M30 reason codes were generic inventions | Codes now map from actual M30 runtime reasons. |
| `allowed` conflated permission with actual expression | Affect trace now uses `decision=allowed|suppressed|not_applicable`; no output-expression claim. |
| 10% beta rollout unnecessary | Replaced with operator-controlled diagnostic enablement. |
| Required/optional fields ambiguous | Type spec explicitly marks required top-level fields and defaults optional sections/fields. |

---

# 4. Appendices

## Appendix A — M30 warm-comeback mapping

| Existing runtime `must_suppress_reason` | M31B stable reason code |
|---|---|
| `mode_not_partner_dynamic` | `affect.warm_comeback.suppressed.mode_not_partner_dynamic` |
| `assistant_mode_not_life_companion` | `affect.warm_comeback.suppressed.assistant_mode_not_life_companion` |
| `user_distressed` | `affect.warm_comeback.suppressed.user_distressed` |
| `urgent_or_crisis` | `affect.warm_comeback.suppressed.urgent_or_crisis` |
| `serious_work_task` | `affect.warm_comeback.suppressed.serious_work_task` |
| `cooldown_active` | `affect.warm_comeback.suppressed.cooldown_active` |
| `insufficient_history` | `affect.warm_comeback.suppressed.insufficient_history` |
| `gap_below_minimum` | `affect.warm_comeback.suppressed.gap_below_minimum` |
| `gap_not_meaningful_vs_cadence` | `affect.warm_comeback.suppressed.gap_not_meaningful_vs_cadence` |
| `None` with `one_short_warm_line` policy | `affect.warm_comeback.allowed.safe_return` |

## Appendix B — Privacy defaults

| Environment | Trace sink | Logging | Preview policy |
|---|---|---|---|
| Production normal | `NullTraceSink` | Off | `none` |
| Production diagnostic window | `LoggingTraceSink` | Explicitly enabled | `none` by default; `redacted` only by deliberate operator choice |
| Local development | `LoggingTraceSink` or `TestTraceSink` | Optional | `redacted` or `dev` |
| Unit/integration tests | `TestTraceSink` | No external log required | fixture-controlled |

## Appendix C — Changelog

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-09-01 | Initial M31A/M31B draft prepared with Kimi sparring. |
| 0.2 | 2026-09-01 | Grounded to actual Aliyya codebase; corrected pipeline, modes, affect semantics, trace schema, privacy, tests, reason codes, and rollout. |

## Appendix D — Final architecture-gate questions

Final architecture gate passed on 2026-09-01 against the following criteria:

1. Do the module names still match `main` at merge time?
2. Does M31B instrument only existing decision surfaces?
3. Are all added trace paths fail-open?
4. Is production trace logging disabled by default?
5. Do examples contain only canonical reason codes?
6. Does M31B leave chat output and action behavior unchanged?
7. Is canonical salience still deferred to M31G?
8. Does M30 tracing mirror its actual deterministic reasons without changing them?

---

*End of Revision 0.2*
