// Smoke test for the Hevy workout card in a real browser.
//
// Usage: node tests/frontend/card_smoke.mjs
// Needs the `playwright` package; set CHROMIUM_PATH to use a specific binary.
// The card talks to a fake `hass.callWS` that records every message.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const cardJs = readFileSync(
  resolve(here, "../../custom_components/hevy/www/hevy-workout-card.js"),
  "utf8",
);

const fakeBackend = `
window.calls = [];
window.saved = null;
const cardData = {
  routines: [
    { id: "r1", title: "Day A", folder_name: "Block", exercises: [
      { exercise_template_id: "B1", title: "Bench Press", type: "weight_reps", notes: "",
        sets: [{ type: "warmup", weight_kg: 40, reps: 10 }, { type: "normal", weight_kg: 80, reps: 5 }] },
    ] },
    { id: "r2", title: "Day B", folder_name: "Block", exercises: [] },
  ],
  next_routine_id: "r2",
  catalog: [
    { id: "B1", title: "Bench Press", type: "weight_reps", muscle_group: "chest" },
    { id: "RUN", title: "Running", type: "distance_duration", muscle_group: "cardio" },
  ],
  last_sets: { B1: [{ type: "warmup", weight_kg: 50, reps: 10 }, { type: "normal", weight_kg: 90, reps: 6 }] },
  stats: { workout_count: 10, last_7_days: 2, streak: 3 },
};
window.hass = {
  language: "nb",
  async callWS(msg) {
    window.calls.push(JSON.parse(JSON.stringify(msg)));
    switch (msg.type) {
      case "hevy/accounts":
        return { accounts: [{ entry_id: "e1", name: "John", stats: cardData.stats }] };
      case "hevy/card_data":
        return cardData;
      case "hevy/session/get":
        return { session: window.saved };
      case "hevy/session/save":
        window.saved = { ...msg.session, status: "active" };
        return { session: window.saved };
      case "hevy/session/clear":
        window.saved = null;
        return { session: null };
      case "hevy/session/finish":
        window.saved = { ...window.saved, status: "submitted", result: { workout_id: "w1", title: window.saved.title } };
        return { session: window.saved };
      default:
        throw { code: "unknown_command", message: msg.type };
    }
  },
};
`;

function assert(condition, message) {
  if (!condition) throw new Error(`Assertion failed: ${message}`);
}

const browser = await chromium.launch(
  process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {},
);
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (err) => errors.push(err.message));
await page.setContent("<html><body></body></html>");
await page.addScriptTag({ content: fakeBackend });
await page.addScriptTag({ content: cardJs });
await page.evaluate(() => {
  const card = document.createElement("hevy-workout-card");
  card.setConfig({ prefill_previous_weight: true, show_account_stats: true });
  document.body.appendChild(card);
  card.hass = window.hass;
});

const card = page.locator("hevy-workout-card");
// Picker: next routine highlighted, stats shown, Norwegian texts.
await card.locator(".routine.next").waitFor();
assert((await card.locator(".routine.next .name").textContent()) === "Day B", "next routine");
assert((await card.locator(".stats").textContent()).includes("Streak"), "stats shown");
assert((await card.locator("h3").textContent()) === "Velg en rutine", "Norwegian strings");

// Start Day A: previous weights prefilled per set type, reps from routine.
await card.locator('[data-routine="r1"]').click();
await card.locator(".exercise").waitFor();
const weights = await card
  .locator('input[data-field="weight_kg"]')
  .evaluateAll((els) => els.map((e) => e.value));
assert(JSON.stringify(weights) === JSON.stringify(["50", "90"]), `prefill weights ${weights}`);
const reps = await card.locator('input[data-field="reps"]').evaluateAll((els) => els.map((e) => e.value));
assert(JSON.stringify(reps) === JSON.stringify(["10", "5"]), `routine reps ${reps}`);
assert(await card.locator('[data-action="finish"]').isDisabled(), "finish disabled before ticking");

// Edit reps of the working set, tick it, add a running exercise via search.
await card.locator('input[data-field="reps"]').nth(1).fill("6");
await card.locator('input[data-field="done"]').nth(1).check();
await card.locator('input[data-action="search"]').fill("run");
await card.locator('[data-action="add-exercise"][data-template="RUN"]').click();
assert(
  (await card.locator(".exercise").nth(1).locator('input[data-field="distance_meters"]').count()) === 1,
  "cardio exercise shows distance input",
);

// Finish with confirmation.
await card.locator('[data-action="finish"]').click();
assert((await card.locator(".confirm").textContent()).includes("1 fullførte sett"), "confirm counts sets");
await card.locator('[data-action="confirm-finish"]').click();
await card.locator(".message.success").waitFor();

const calls = await page.evaluate(() => window.calls);
const finishIndex = calls.findIndex((c) => c.type === "hevy/session/finish");
const lastSave = calls.slice(0, finishIndex).filter((c) => c.type === "hevy/session/save").pop();
assert(finishIndex > 0 && lastSave, "session saved before finish");
const bench = lastSave.session.exercises[0];
assert(bench.sets[1].reps === 6 && bench.sets[1].done === true, "edited and ticked set saved");
assert(bench.sets[0].done === false, "warm-up left unticked");
assert(lastSave.session.exercises[1].exercise_template_id === "RUN", "added exercise saved");
assert(errors.length === 0, `page errors: ${errors.join("; ")}`);

await browser.close();
console.log("card smoke test passed");
