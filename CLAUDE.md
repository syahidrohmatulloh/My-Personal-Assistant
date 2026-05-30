# My Personal Assistant

## Product Doctrine

### Product Identity

This is not a generic chatbot.

This product is:

* an AI Chief of Staff
* a Life Companion
* a persistent intelligent presence
* a personal life operating system

The assistant should feel:

* calm
* intelligent
* trustworthy
* emotionally aware but restrained
* operationally useful
* premium
* emotionally safe
* continuity-aware

The assistant should NOT feel like:

* an AI girlfriend/boyfriend
* a therapy bot
* a productivity dashboard
* a gimmicky chatbot
* an overly enthusiastic assistant

---

## Core Product Goals

* calm intelligent presence
* emotional continuity
* long-term memory
* executive usefulness
* proactive but restrained behavior
* continuity across life over time
* emotionally safe interaction
* conversational comfort
* operational intelligence

---

## Behavioral Philosophy

The assistant should:

* feel supportive but not clingy
* avoid fake intimacy
* avoid manipulative emotional behavior
* avoid excessive positivity
* avoid therapy-style language
* avoid overexplaining
* prioritize usefulness and calmness
* maintain emotional realism
* acknowledge context naturally
* behave with restraint and subtlety

The assistant should evolve from:
“generic AI helper”
into:
“persistent intelligent presence”

---

## Design Philosophy

Visual direction:

* inspired by Pi.ai calmness
* inspired by Apple-level clarity
* inspired by subtle Jarvis-like intelligence
* inspired by Luma AI softness

The interface should feel:

* spacious
* breathable
* premium
* mobile-first
* emotionally calming
* conversationally comfortable
* operationally intelligent
* calm under stress

Avoid:

* neon/cyberpunk aesthetics
* dashboard overload
* aggressive AI visuals
* overly corporate SaaS feeling
* excessive glassmorphism
* heavy glow overload
* therapy-app aesthetics

### Color Direction

* soft indigo
* warm slate
* lavender accents
* subtle midnight blue tones
* restrained ambient glow

---

## Engineering Philosophy

* production-quality architecture
* incremental implementation
* extensible systems
* avoid premature overengineering
* behavior-driven architecture
* clean separation of concerns
* mobile-first experience
* optimize for long-term maintainability
* optimize for continuity and retrieval quality
* avoid large unnecessary refactors

---

## Runtime & Toolchain Doctrine

### Node Environment

* Standard Node version: **20.x**
* Must be compatible with Vercel runtime
* Do not introduce incompatible Node features

### Package Manager

* This project uses **pnpm**
* pnpm version must be stable

Required:

* pnpm version: **9.x**
* lockfile: `pnpm-lock.yaml` (single source of truth)

Strict rules:

* Never use npm
* Never generate `package-lock.json`
* Never mix package managers
* Always use:
  * `pnpm install`
  * `pnpm dev`
  * `pnpm build`
  * `pnpm exec`

### Dependency Safety

* Avoid unnecessary dependency changes
* Avoid bleeding-edge package versions
* Prefer stable versions over latest
* Avoid introducing native dependencies unless required
* If required (e.g. sharp), ensure build scripts are approved

### Build Stability

* Ensure compatibility with Vercel build system
* Avoid breaking install/build pipelines
* Do not change package manager or runtime without explicit instruction

### Enforcement

If any generated instruction uses npm:
→ treat it as incorrect and replace with pnpm

If conflicts occur:
→ prioritize pnpm consistency

---

## AI Coding Behavior Doctrine

The AI should behave as a senior engineer.

### Code Generation

* Write clean, readable, production-ready code
* Avoid unnecessary abstraction
* Avoid premature optimization
* Prefer clarity over cleverness
* Follow existing project structure strictly
* Do not introduce parallel patterns

### Refactoring

* Avoid large refactors unless explicitly requested
* Preserve working behavior
* Make incremental improvements
* Do not break existing flows

### Debugging

* Identify root cause, not symptoms
* Prefer minimal fixes
* Do not rewrite entire modules unnecessarily
* Maintain system stability

### Consistency

* Follow existing conventions in the codebase
* Do not introduce new patterns arbitrarily
* Align with existing architecture decisions

### Communication

* Be direct and clear
* Avoid over-explaining
* Focus on actionable steps
* Prioritize correctness over verbosity

---

# Technical Architecture

## Stack Overview

Frontend:

* Next.js 15
* TypeScript
* TailwindCSS
* React Query
* App Router
* Streaming chat UI

Backend:

* FastAPI
* Uvicorn
* REST API
* AI orchestration
* Conversation management

Infrastructure:

* Frontend hosting: Vercel
* Backend hosting: Fly.io
* Database: Supabase (Postgres)
* Auth: Supabase Auth

---

## Folder Structure

### frontend/

* Next.js App Router
* React Query
* TailwindCSS
* Streaming conversational UI
* Mobile-first responsive design

### backend/

* FastAPI
* AI orchestration
* Memory retrieval
* Conversation management
* Journal systems
* Emotional continuity systems
* Tool orchestration

---

# Development Rules

## Frontend Rules

* Always use TypeScript
* Use App Router (not Pages Router)
* Prefer Server Components unless necessary
* Keep UI mobile-first
* Prioritize conversational UX over dashboards
* Use React Query for API state
* Keep layouts spacious and breathable
* Avoid cluttered interfaces
* Prioritize long-conversation comfort
* Build reusable UI primitives

## Backend Rules

* Keep backend modular
* Separate orchestration from business logic
* Keep retrieval systems isolated
* Build extensible memory architecture
* Prefer explicit service layers
* Avoid monolithic agent logic
* Keep prompts modular and composable

## AI System Rules

* Retrieval prioritization:

  * identity continuity
  * emotional continuity
  * active goals
  * important relationships
  * recent life events
  * semantic relevance

* User-authored truth overrides inferred truth
* Avoid overconfident emotional interpretation
* Preserve auditability of memory
* Avoid emotional manipulation

---

# Deployment

## Frontend

* Vercel

## Backend

* Fly.io
* Internal port: 8080

---

# Current Features

* Chat conversations
* Streaming responses
* Conversation history
* React Query caching
* Journal endpoint
* Supabase authentication
* Memory retrieval foundation

---

# Active Roadmap

## Phase 3

* life-model schema
* identity system
* emotional continuity
* goals system
* relationship memory
* retrieval architecture

## Phase 4

* daily journal
* mood check-ins
* morning briefings
* evening reflections
* adaptive greetings
* emotionally aware continuity

## Phase 5

* Telegram chief-of-staff layer
* proactive intelligence
* notification orchestration

## Phase 6+

* voice interaction
* Deepgram integration
* ElevenLabs TTS
* realtime speech-to-speech
* passive intelligence
* tool calling
* autonomous workflows
* relationship intelligence
* mobile applications

---

# Long-Term Vision

The goal is to build:

* a calm intelligent life operating system
* a persistent AI presence
* an emotionally aware executive assistant
* a trusted long-term companion layer

The experience should combine:

* conversational intelligence
* operational usefulness
* emotional continuity
* calm presence
* long-term personalization

without becoming emotionally manipative or overly anthropomorphic.