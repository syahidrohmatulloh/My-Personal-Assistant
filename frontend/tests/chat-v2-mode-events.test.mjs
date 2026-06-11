/**
 * Focused tests for Chat V2 assistant-mode event plumbing.
 *
 * Run from the frontend/ directory:
 *
 *     node --test tests/chat-v2-mode-events.test.mjs
 *
 * No test framework dependency: this compiles app/chat-v2/mode-events.ts
 * with the project's own TypeScript into a temp dir, then tests it with
 * Node's built-in test runner (Node 20+).
 */

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const frontendDir = dirname(dirname(fileURLToPath(import.meta.url)));
const sourceFile = join(frontendDir, "app", "chat-v2", "mode-events.ts");
const outDir = mkdtempSync(join(tmpdir(), "chat-v2-mode-events-"));
process.on("exit", () => {
  try {
    rmSync(outDir, { recursive: true, force: true });
  } catch {}
});

const compile = spawnSync(
  "pnpm",
  [
    "exec",
    "tsc",
    sourceFile,
    "--outDir",
    outDir,
    "--module",
    "commonjs",
    "--target",
    "es2020",
    "--lib",
    "es2020,dom",
    "--skipLibCheck",
    "--strict",
  ],
  { cwd: frontendDir, encoding: "utf8" },
);

if (compile.status !== 0) {
  throw new Error(
    `Failed to compile mode-events.ts:\n${compile.stdout || ""}${compile.stderr || ""}`,
  );
}

const require = createRequire(import.meta.url);
const {
  ASSISTANT_MODE_EVENT,
  changeAssistantMode,
  createAssistantModeDetail,
  extractAssistantMode,
  extractAssistantName,
} = require(join(outDir, "mode-events.js"));

/** Minimal detail-carrying event for Node's standard EventTarget. */
class DetailEvent extends Event {
  constructor(type, detail) {
    super(type);
    this.detail = detail;
  }
}

test("event name matches the app-wide channel", () => {
  assert.equal(ASSISTANT_MODE_EVENT, "assistant-companion-settings");
});

test("extracts the flat shape used by chat surfaces", () => {
  assert.equal(
    extractAssistantMode({ assistant_mode: "chief_of_staff" }),
    "chief_of_staff",
  );
  assert.equal(
    extractAssistantMode({ assistant_mode: "life_companion" }),
    "life_companion",
  );
});

test("extracts from full companion-settings objects (lib/api.ts dispatch)", () => {
  assert.equal(
    extractAssistantMode({
      assistant_mode: "chief_of_staff",
      companion_mode: "friendly",
      mood_realism: "stable",
    }),
    "chief_of_staff",
  );
});

test("extracts the legacy nested preferences shape", () => {
  assert.equal(
    extractAssistantMode({ preferences: { assistant_mode: "life_companion" } }),
    "life_companion",
  );
});

test("rejects everything else", () => {
  assert.equal(extractAssistantMode(undefined), null);
  assert.equal(extractAssistantMode(null), null);
  assert.equal(extractAssistantMode("chief_of_staff"), null);
  assert.equal(extractAssistantMode({}), null);
  assert.equal(extractAssistantMode({ assistant_mode: "serious" }), null);
  assert.equal(extractAssistantMode({ assistant_mode: 42 }), null);
  assert.equal(extractAssistantMode({ preferences: null }), null);
  assert.equal(extractAssistantMode({ preferences: { assistant_mode: 1 } }), null);
});

test("created details round-trip through extraction", () => {
  for (const mode of ["life_companion", "chief_of_staff"]) {
    assert.equal(extractAssistantMode(createAssistantModeDetail(mode)), mode);
  }
});

test("extracts the assistant name from full settings broadcasts", () => {
  assert.equal(extractAssistantName({ assistant_name: "Aliyya" }), "Aliyya");
  assert.equal(extractAssistantName({ assistant_name: "  Nara  " }), "Nara");
  assert.equal(
    extractAssistantName({
      assistant_name: "Aliyya",
      assistant_mode: "chief_of_staff",
      companion_mode: "friendly",
    }),
    "Aliyya",
  );
});

test("rejects missing or blank assistant names", () => {
  assert.equal(extractAssistantName(undefined), null);
  assert.equal(extractAssistantName(null), null);
  assert.equal(extractAssistantName({}), null);
  assert.equal(extractAssistantName({ assistant_name: "" }), null);
  assert.equal(extractAssistantName({ assistant_name: "   " }), null);
  assert.equal(extractAssistantName({ assistant_name: 42 }), null);
  assert.equal(extractAssistantName({ assistant_mode: "life_companion" }), null);
});

test("changeAssistantMode: success applies once and persists once", async () => {
  const applied = [];
  const persisted = [];
  let fetched = 0;

  await changeAssistantMode("chief_of_staff", {
    applyLocally: (mode) => applied.push(mode),
    persist: async (mode) => persisted.push(mode),
    fetchServerMode: async () => {
      fetched += 1;
      return "life_companion";
    },
  });

  assert.deepEqual(applied, ["chief_of_staff"], "local state changes immediately, exactly once");
  assert.deepEqual(persisted, ["chief_of_staff"], "backend settings persist");
  assert.equal(fetched, 0, "no resync fetch on success");
});

test("changeAssistantMode: failed persist resyncs to the server mode", async () => {
  const applied = [];

  await changeAssistantMode("chief_of_staff", {
    applyLocally: (mode) => applied.push(mode),
    persist: async () => {
      throw new Error("network down");
    },
    fetchServerMode: async () => "life_companion",
  });

  assert.deepEqual(
    applied,
    ["chief_of_staff", "life_companion"],
    "optimistic apply, then resync to the server's mode",
  );
});

test("changeAssistantMode: failed persist + failed resync keeps optimistic state, never throws", async () => {
  const applied = [];

  await changeAssistantMode("life_companion", {
    applyLocally: (mode) => applied.push(mode),
    persist: async () => {
      throw new Error("network down");
    },
    fetchServerMode: async () => {
      throw new Error("still down");
    },
  });

  assert.deepEqual(applied, ["life_companion"]);
});

test("CONTRACT: one initiated toggle produces exactly one global event, listeners stay apply-only", async () => {
  const target = new EventTarget();
  let dispatched = 0;
  let applied = 0;
  let listenerApplied = 0;

  // The app-wide listener shape (ambient background, main chat, Chat V2):
  // apply the incoming mode, never re-dispatch.
  target.addEventListener(ASSISTANT_MODE_EVENT, (event) => {
    const mode = extractAssistantMode(event.detail);
    if (mode) listenerApplied += 1;
  });

  // persist behaves like lib/api.ts patchCompanionSettings: it broadcasts the
  // full settings object on success — the single broadcaster.
  const persist = async (mode) => {
    dispatched += 1;
    target.dispatchEvent(
      new DetailEvent(ASSISTANT_MODE_EVENT, {
        assistant_mode: mode,
        assistant_name: "Aliyya",
        companion_mode: "friendly",
      }),
    );
  };

  await changeAssistantMode("chief_of_staff", {
    applyLocally: () => {
      applied += 1;
    },
    persist,
    fetchServerMode: async () => "life_companion",
  });

  assert.equal(applied, 1, "local apply happens exactly once");
  assert.equal(dispatched, 1, "exactly one global broadcast per initiated change");
  assert.equal(listenerApplied, 1, "listeners apply it exactly once — no amplification");
});

test("CONTRACT: a failed persist broadcasts nothing during resync", async () => {
  const target = new EventTarget();
  let dispatched = 0;
  const applied = [];

  target.addEventListener(ASSISTANT_MODE_EVENT, () => {
    dispatched += 1;
  });

  await changeAssistantMode("chief_of_staff", {
    applyLocally: (mode) => applied.push(mode),
    persist: async () => {
      throw new Error("network down");
    },
    fetchServerMode: async () => "life_companion",
  });

  assert.equal(dispatched, 0, "failed changes never reach other surfaces");
  assert.deepEqual(applied, ["chief_of_staff", "life_companion"]);
});

test("apply-only listeners do not amplify dispatches (fixed wiring)", () => {
  const target = new EventTarget();
  let applied = 0;
  let dispatches = 0;

  // Chat V2's fixed listener contract: read the mode, apply it, never
  // re-dispatch from inside the handler.
  target.addEventListener(ASSISTANT_MODE_EVENT, (event) => {
    const mode = extractAssistantMode(event.detail);
    if (mode) applied += 1;
  });

  const broadcast = (mode) => {
    dispatches += 1;
    target.dispatchEvent(new DetailEvent(ASSISTANT_MODE_EVENT, createAssistantModeDetail(mode)));
  };

  broadcast("chief_of_staff");
  broadcast("life_companion");

  assert.equal(dispatches, 2, "each initiated change dispatches exactly once");
  assert.equal(applied, 2, "each dispatch is applied exactly once");
});

test("REGRESSION: re-broadcasting from the listener fans out unboundedly (old wiring)", () => {
  const target = new EventTarget();
  const SAFETY_CAP = 25;
  let depth = 0;

  const broadcast = (mode) =>
    target.dispatchEvent(new DetailEvent(ASSISTANT_MODE_EVENT, createAssistantModeDetail(mode)));

  // The pre-fix Chat V2 pattern: applyModeLocally() dispatched the same event
  // it was listening to. dispatchEvent is synchronous, so in a browser this
  // recursed until "Maximum call stack size exceeded". The cap below exists
  // only so the test terminates.
  target.addEventListener(ASSISTANT_MODE_EVENT, (event) => {
    const mode = extractAssistantMode(event.detail);
    if (!mode) return;
    depth += 1;
    if (depth >= SAFETY_CAP) return;
    broadcast(mode);
  });

  broadcast("chief_of_staff");

  assert.equal(
    depth,
    SAFETY_CAP,
    "one user action recursed into the handler until the safety cap — the loop the fix removes",
  );
});
