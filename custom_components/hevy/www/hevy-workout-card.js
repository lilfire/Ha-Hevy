/**
 * Hevy live workout card for Home Assistant.
 *
 * Talks to the Hevy integration over the websocket API (hevy/*). The active
 * session is stored in Home Assistant, so a refresh or restart resumes it.
 * No external dependencies.
 */

const CARD_VERSION = "0.2.0";
const SET_TYPES = ["normal", "warmup", "failure", "dropset"];
const RPE_VALUES = [6, 7, 7.5, 8, 8.5, 9, 9.5, 10];
const SAVE_DELAY_MS = 800;

// Which inputs to show per Hevy exercise type.
const FIELDS_BY_TYPE = {
  weight_reps: ["weight_kg", "reps"],
  reps_only: ["reps"],
  bodyweight_reps: ["weight_kg", "reps"],
  bodyweight_assisted_reps: ["weight_kg", "reps"],
  duration: ["duration_seconds"],
  weight_duration: ["weight_kg", "duration_seconds"],
  distance_duration: ["distance_meters", "duration_seconds"],
  short_distance_weight: ["distance_meters", "weight_kg"],
};
const MEASUREMENTS = ["weight_kg", "reps", "duration_seconds", "distance_meters"];

const STRINGS = {
  en: {
    workout: "Workout",
    who: "Who is working out?",
    chooseRoutine: "Choose a routine",
    next: "Next",
    emptyWorkout: "Empty workout",
    title: "Title",
    notes: "Notes",
    addSet: "Add set",
    remove: "Remove",
    addExercise: "Add an exercise",
    search: "Search exercises…",
    private: "Private workout",
    finish: "Finish",
    discard: "Discard",
    confirmFinish: "Send {sets} completed sets to {dest}?",
    confirmDiscard: "Discard this workout?",
    yes: "Yes",
    cancel: "Cancel",
    sending: "Sending…",
    saved: "Saved",
    saveFailed: "Could not save: {error}",
    success: "Workout “{title}” saved to {dest}.",
    failed: "Hevy rejected the workout: {error}",
    uncertain:
      "The result is uncertain ({error}). Check Hevy before retrying — retrying a workout that already arrived creates a duplicate.",
    retry: "Retry",
    edit: "Back to edit",
    clear: "Clear session",
    start: "Start",
    noRoutines: "No routines.",
    noSets: "Check off at least one set first.",
    loading: "Loading…",
    noAccount: "No Hevy account is loaded.",
    total: "Total",
    last7: "Last 7 days",
    streak: "Streak",
    set: "Set",
    type: "Type",
    weight_kg: "kg",
    reps: "Reps",
    duration_seconds: "Sec",
    distance_meters: "m",
    rpe: "RPE",
    done: "Done",
    normal: "Normal",
    warmup: "Warm-up",
    failure: "Failure",
    dropset: "Drop set",
    collapsed: "{n} completed sets",
    showDetails: "Show details",
  },
  nb: {
    workout: "Treningsøkt",
    who: "Hvem trener?",
    chooseRoutine: "Velg en rutine",
    next: "Neste",
    emptyWorkout: "Tom økt",
    title: "Tittel",
    notes: "Notater",
    addSet: "Legg til sett",
    remove: "Fjern",
    addExercise: "Legg til øvelse",
    search: "Søk etter øvelser…",
    private: "Privat økt",
    finish: "Fullfør",
    discard: "Forkast",
    confirmFinish: "Sende {sets} fullførte sett til {dest}?",
    confirmDiscard: "Forkaste denne økten?",
    yes: "Ja",
    cancel: "Avbryt",
    sending: "Sender…",
    saved: "Lagret",
    saveFailed: "Kunne ikke lagre: {error}",
    success: "Økten «{title}» er lagret i {dest}.",
    failed: "Hevy avviste økten: {error}",
    uncertain:
      "Resultatet er usikkert ({error}). Sjekk Hevy før du prøver igjen — et nytt forsøk på en økt som allerede kom fram gir duplikat.",
    retry: "Prøv igjen",
    edit: "Tilbake til redigering",
    clear: "Tøm økt",
    start: "Start",
    noRoutines: "Ingen rutiner.",
    noSets: "Huk av minst ett sett først.",
    loading: "Laster…",
    noAccount: "Ingen Hevy-konto er lastet.",
    total: "Totalt",
    last7: "Siste 7 dager",
    streak: "Streak",
    set: "Sett",
    type: "Type",
    weight_kg: "kg",
    reps: "Reps",
    duration_seconds: "Sek",
    distance_meters: "m",
    rpe: "RPE",
    done: "Ferdig",
    normal: "Normal",
    warmup: "Oppvarming",
    failure: "Til failure",
    dropset: "Dropsett",
    collapsed: "{n} fullførte sett",
    showDetails: "Vis detaljer",
  },
};

const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );

const uid = () =>
  (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`).replace(/-/g, "");

const toNumber = (value) => {
  if (value === "" || value === null || value === undefined) return null;
  const n = Number(String(value).replace(",", "."));
  return Number.isFinite(n) && n >= 0 ? n : null;
};

class HevyWorkoutCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._started = false;
    this._accounts = [];
    this._entryId = null;
    this._data = null;
    this._session = null;
    this._view = "loading";
    this._message = null;
    this._confirm = null;
    this._search = "";
    this._expanded = new Set();
    this._saveTimer = null;
    this._savePromise = null;
    this._busy = false;
    this.shadowRoot.addEventListener("click", (ev) => this._onClick(ev));
    this.shadowRoot.addEventListener("change", (ev) => this._onChange(ev));
    this.shadowRoot.addEventListener("input", (ev) => this._onInput(ev));
  }

  static getStubConfig() {
    return {};
  }

  setConfig(config) {
    this._config = {
      title: null,
      routine_ids: null,
      exercise_ids: null,
      prefill_previous_weight: false,
      prefill_previous_reps: false,
      default_private_workout: false,
      collapse_completed_sets: false,
      show_account_stats: false,
      show_rpe: true,
      show_set_type: true,
      ...config,
    };
    if (this._started) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      this._load();
    }
  }

  getCardSize() {
    return 8;
  }

  // ------------------------------------------------------------- helpers

  _t(key, vars = {}) {
    const lang = (this._hass?.language || "en").toLowerCase();
    const table = ["nb", "no", "nn"].some((l) => lang.startsWith(l)) ? STRINGS.nb : STRINGS.en;
    let text = table[key] ?? STRINGS.en[key] ?? key;
    for (const [k, v] of Object.entries(vars)) text = text.replace(`{${k}}`, v);
    return text;
  }

  _ws(type, payload = {}) {
    return this._hass.callWS({ type, ...payload });
  }

  _account() {
    return this._accounts.find((a) => a.entry_id === this._entryId);
  }

  _destination() {
    return this._accounts.length > 1 ? `Hevy (${this._account()?.name ?? ""})` : "Hevy";
  }

  _catalogEntry(templateId) {
    return (this._data?.catalog || []).find((c) => c.id === templateId);
  }

  _fieldsFor(exercise) {
    return FIELDS_BY_TYPE[exercise.type] || ["weight_kg", "reps"];
  }

  _completedSets() {
    let n = 0;
    for (const ex of this._session?.exercises || []) {
      for (const s of ex.sets) {
        if (s.done && MEASUREMENTS.some((k) => s[k] !== null && s[k] !== undefined)) n += 1;
      }
    }
    return n;
  }

  // ------------------------------------------------------------- loading

  async _load() {
    this._view = "loading";
    this._render();
    try {
      const { accounts } = await this._ws("hevy/accounts");
      this._accounts = accounts;
      if (!accounts.length) {
        this._view = "empty";
        this._render();
        return;
      }
      let remembered = null;
      try {
        remembered = localStorage.getItem("hevy-workout-card-entry");
      } catch (_err) {
        remembered = null;
      }
      const wanted = this._config.config_entry_id || remembered;
      this._entryId = accounts.some((a) => a.entry_id === wanted) ? wanted : accounts[0].entry_id;
      await this._loadAccount();
    } catch (err) {
      this._message = { kind: "error", text: esc(err.message || err.code || String(err)) };
      this._view = "empty";
      this._render();
    }
  }

  async _loadAccount() {
    this._view = "loading";
    this._render();
    const [data, { session }] = await Promise.all([
      this._ws("hevy/card_data", { entry_id: this._entryId }),
      this._ws("hevy/session/get", { entry_id: this._entryId }),
    ]);
    this._data = data;
    this._session = session;
    this._confirm = null;
    if (!session || session.status === "submitted") {
      this._view = "picker";
    } else if (session.status === "uncertain" || session.status === "submitting") {
      this._view = "result";
    } else {
      this._view = "workout";
    }
    this._render();
  }

  // ------------------------------------------------------------- session

  _prefill(templateId, sets) {
    const last = this._data?.last_sets?.[templateId];
    if (!last || !(this._config.prefill_previous_weight || this._config.prefill_previous_reps)) {
      return sets;
    }
    const byType = {};
    for (const s of last) (byType[s.type || "normal"] ||= []).push(s);
    const seen = {};
    return sets.map((s) => {
      const type = s.type || "normal";
      const index = (seen[type] = (seen[type] ?? -1) + 1);
      const previous = byType[type]?.[index];
      if (!previous) return s;
      const out = { ...s };
      if (this._config.prefill_previous_weight && toNumber(previous.weight_kg) !== null) {
        out.weight_kg = previous.weight_kg;
      }
      if (this._config.prefill_previous_reps && toNumber(previous.reps) !== null) {
        out.reps = previous.reps;
      }
      return out;
    });
  }

  _newSet(base = {}) {
    return {
      type: base.type || "normal",
      weight_kg: base.weight_kg ?? null,
      reps: base.reps ?? null,
      duration_seconds: base.duration_seconds ?? null,
      distance_meters: base.distance_meters ?? null,
      rpe: null,
      done: false,
    };
  }

  _startSession(routine) {
    const exercises = (routine?.exercises || []).map((ex) => ({
      key: uid(),
      exercise_template_id: ex.exercise_template_id,
      title: ex.title,
      type: ex.type || this._catalogEntry(ex.exercise_template_id)?.type || null,
      notes: ex.notes || "",
      superset_id: ex.superset_id ?? null,
      sets: this._prefill(
        ex.exercise_template_id,
        (ex.sets?.length ? ex.sets : [{}]).map((s) => this._newSet(s)),
      ),
    }));
    this._session = {
      id: uid(),
      title: routine?.title || this._t("workout"),
      description: "",
      routine_id: routine?.id || null,
      is_private: !!this._config.default_private_workout,
      started_at: new Date().toISOString(),
      exercises,
      status: "active",
    };
    this._message = null;
    this._view = "workout";
    this._render();
    this._save(true);
  }

  _save(immediate = false) {
    clearTimeout(this._saveTimer);
    const run = async () => {
      if (!this._session) return;
      try {
        await this._ws("hevy/session/save", {
          entry_id: this._entryId,
          session: this._session,
        });
        this._setStatus(this._t("saved"));
      } catch (err) {
        this._setStatus(this._t("saveFailed", { error: err.message || err.code }), true);
      }
    };
    if (immediate) {
      this._savePromise = run();
      return this._savePromise;
    }
    this._saveTimer = setTimeout(() => {
      this._savePromise = run();
    }, SAVE_DELAY_MS);
    return null;
  }

  async _flushSave() {
    if (this._saveTimer) {
      clearTimeout(this._saveTimer);
      this._saveTimer = null;
      await this._save(true);
    } else if (this._savePromise) {
      await this._savePromise;
    }
  }

  _setStatus(text, isError = false) {
    const el = this.shadowRoot.querySelector(".save-status");
    if (el) {
      el.textContent = text;
      el.classList.toggle("error", isError);
    }
  }

  async _finish() {
    this._busy = true;
    this._confirm = null;
    this._render();
    try {
      await this._flushSave();
      const { session } = await this._ws("hevy/session/finish", { entry_id: this._entryId });
      this._session = session;
      if (session.status === "submitted") {
        this._message = {
          kind: "success",
          text: this._t("success", {
            title: esc(session.result?.title || session.title),
            dest: esc(this._destination()),
          }),
        };
        this._view = "picker";
        this._refreshStats();
      } else if (session.status === "failed") {
        this._message = {
          kind: "error",
          text: this._t("failed", { error: esc(session.result?.error) }),
        };
        this._view = "workout";
      } else {
        this._view = "result";
      }
    } catch (err) {
      this._message = {
        kind: "error",
        text: err.code === "no_completed_sets" ? this._t("noSets") : esc(err.message || err.code),
      };
    } finally {
      this._busy = false;
      this._render();
    }
  }

  async _refreshStats() {
    try {
      const { accounts } = await this._ws("hevy/accounts");
      this._accounts = accounts;
      this._render();
    } catch (_err) {
      // Stats are optional.
    }
  }

  async _clear() {
    clearTimeout(this._saveTimer);
    this._saveTimer = null;
    await this._ws("hevy/session/clear", { entry_id: this._entryId });
    this._session = null;
    this._confirm = null;
    this._message = null;
    this._view = "picker";
    this._render();
  }

  // -------------------------------------------------------------- events

  _onClick(ev) {
    const target = ev.target.closest("[data-action]");
    if (!target || this._busy) return;
    const { action } = target.dataset;
    const ex = target.dataset.ex !== undefined ? Number(target.dataset.ex) : null;
    const set = target.dataset.set !== undefined ? Number(target.dataset.set) : null;
    const exercises = this._session?.exercises;
    switch (action) {
      case "start-routine": {
        const routine = this._data.routines.find((r) => r.id === target.dataset.routine);
        this._startSession(routine);
        return;
      }
      case "start-empty":
        this._startSession(null);
        return;
      case "add-set": {
        const sets = exercises[ex].sets;
        sets.push(this._newSet(sets[sets.length - 1] ? { ...sets[sets.length - 1] } : {}));
        break;
      }
      case "remove-set":
        exercises[ex].sets.splice(set, 1);
        break;
      case "remove-exercise":
        exercises.splice(ex, 1);
        break;
      case "add-exercise": {
        const entry = this._catalogEntry(target.dataset.template);
        if (!entry) return;
        exercises.push({
          key: uid(),
          exercise_template_id: entry.id,
          title: entry.title,
          type: entry.type,
          notes: "",
          superset_id: null,
          sets: this._prefill(entry.id, [this._newSet()]),
        });
        this._search = "";
        break;
      }
      case "expand":
        this._expanded.add(exercises[ex].key);
        this._render();
        return;
      case "finish":
        this._confirm = "finish";
        this._render();
        return;
      case "discard":
        this._confirm = "discard";
        this._render();
        return;
      case "cancel-confirm":
        this._confirm = null;
        this._render();
        return;
      case "confirm-finish":
      case "retry":
        this._finish();
        return;
      case "confirm-discard":
      case "clear":
        this._clear();
        return;
      case "edit":
        this._view = "workout";
        this._message = null;
        this._render();
        return;
      default:
        return;
    }
    this._render();
    this._save();
  }

  _onChange(ev) {
    const el = ev.target;
    if (el.dataset.action === "account") {
      this._entryId = el.value;
      try {
        localStorage.setItem("hevy-workout-card-entry", el.value);
      } catch (_err) {
        // Remembering the account is optional.
      }
      this._message = null;
      this._loadAccount();
      return;
    }
    this._updateField(el, true);
  }

  _onInput(ev) {
    const el = ev.target;
    if (el.dataset.action === "search") {
      this._search = el.value;
      this._renderSearchResults();
      return;
    }
    this._updateField(el, false);
  }

  _updateField(el, committed) {
    const { scope, field } = el.dataset;
    if (!scope || !this._session) return;
    const ex = Number(el.dataset.ex);
    const set = Number(el.dataset.set);
    const value = el.type === "checkbox" ? el.checked : el.value;
    let rerender = false;
    if (scope === "session") {
      this._session[field] = value;
    } else if (scope === "exercise") {
      this._session.exercises[ex][field] = value;
    } else if (scope === "set") {
      const target = this._session.exercises[ex].sets[set];
      if (field === "done" || field === "type") {
        target[field] = value;
        // Ticking a set changes the Finish button and possibly collapses sets.
        rerender = field === "done";
      } else {
        target[field] = toNumber(value);
      }
    }
    if (rerender && committed) this._render();
    this._save();
  }

  // ------------------------------------------------------------- rendering

  _renderStats() {
    const stats = this._account()?.stats || this._data?.stats;
    if (!this._config.show_account_stats || !stats) return "";
    const value = (v) => (v === null || v === undefined ? "–" : esc(v));
    return `<div class="stats">
      <div><span>${this._t("total")}</span><b>${value(stats.workout_count)}</b></div>
      <div><span>${this._t("last7")}</span><b>${value(stats.last_7_days)}</b></div>
      <div><span>${this._t("streak")}</span><b>${value(stats.streak)}</b></div>
    </div>`;
  }

  _renderAccountPicker() {
    if (this._accounts.length < 2) return "";
    const options = this._accounts
      .map(
        (a) =>
          `<option value="${esc(a.entry_id)}" ${a.entry_id === this._entryId ? "selected" : ""}>${esc(a.name)}</option>`,
      )
      .join("");
    return `<label class="account">${this._t("who")}
      <select data-action="account" ${this._view === "workout" ? "disabled" : ""}>${options}</select>
    </label>`;
  }

  _renderMessage() {
    if (!this._message) return "";
    return `<div class="message ${esc(this._message.kind)}">${this._message.text}</div>`;
  }

  _renderPicker() {
    let routines = this._data?.routines || [];
    if (Array.isArray(this._config.routine_ids) && this._config.routine_ids.length) {
      const wanted = this._config.routine_ids;
      routines = wanted.map((id) => routines.find((r) => r.id === id)).filter(Boolean);
    }
    const nextId = this._data?.next_routine_id;
    const items = routines
      .map(
        (r) => `<button class="routine ${r.id === nextId ? "next" : ""}" data-action="start-routine" data-routine="${esc(r.id)}">
          <span class="name">${esc(r.title)}</span>
          ${r.folder_name ? `<span class="folder">${esc(r.folder_name)}</span>` : ""}
          ${r.id === nextId ? `<span class="badge">${this._t("next")}</span>` : ""}
        </button>`,
      )
      .join("");
    return `<h3>${this._t("chooseRoutine")}</h3>
      <div class="routines">${items || `<p class="muted">${this._t("noRoutines")}</p>`}</div>
      <button class="secondary" data-action="start-empty">${this._t("emptyWorkout")}</button>`;
  }

  _renderSet(exIndex, setIndex, s, fields) {
    const typeSelect = this._config.show_set_type
      ? `<select data-scope="set" data-field="type" data-ex="${exIndex}" data-set="${setIndex}">
          ${SET_TYPES.map((t) => `<option value="${t}" ${s.type === t ? "selected" : ""}>${this._t(t)}</option>`).join("")}
        </select>`
      : "";
    const inputs = fields
      .map(
        (f) => `<input type="number" inputmode="decimal" min="0" step="any" placeholder="${this._t(f)}"
          aria-label="${this._t(f)}" value="${s[f] ?? ""}"
          data-scope="set" data-field="${f}" data-ex="${exIndex}" data-set="${setIndex}">`,
      )
      .join("");
    const rpe = this._config.show_rpe
      ? `<select aria-label="RPE" data-scope="set" data-field="rpe" data-ex="${exIndex}" data-set="${setIndex}">
          <option value="">RPE</option>
          ${RPE_VALUES.map((v) => `<option value="${v}" ${Number(s.rpe) === v ? "selected" : ""}>${v}</option>`).join("")}
        </select>`
      : "";
    return `<div class="set ${s.done ? "done" : ""}">
      <span class="index">${setIndex + 1}</span>
      ${typeSelect}${inputs}${rpe}
      <input type="checkbox" class="check" aria-label="${this._t("done")}" ${s.done ? "checked" : ""}
        data-scope="set" data-field="done" data-ex="${exIndex}" data-set="${setIndex}">
      <button class="icon" title="${this._t("remove")}" data-action="remove-set" data-ex="${exIndex}" data-set="${setIndex}">✕</button>
    </div>`;
  }

  _renderExercise(ex, i) {
    const fields = this._fieldsFor(ex);
    const collapse =
      this._config.collapse_completed_sets && !this._expanded.has(ex.key) && ex.sets.some((s) => s.done);
    let sets;
    if (collapse) {
      const done = ex.sets.filter((s) => s.done);
      const summary = done
        .map((s) => fields.map((f) => (s[f] ?? "–") + (f === "reps" ? "" : ` ${this._t(f)}`)).join(" × "))
        .join(", ");
      sets =
        `<div class="collapsed">${this._t("collapsed", { n: done.length })}: ${esc(summary)}
          <button class="link" data-action="expand" data-ex="${i}">${this._t("showDetails")}</button></div>` +
        ex.sets.map((s, j) => (s.done ? "" : this._renderSet(i, j, s, fields))).join("");
    } else {
      sets = ex.sets.map((s, j) => this._renderSet(i, j, s, fields)).join("");
    }
    return `<div class="exercise">
      <div class="ex-head">
        <b>${esc(ex.title || this._catalogEntry(ex.exercise_template_id)?.title || ex.exercise_template_id)}</b>
        <button class="link" data-action="remove-exercise" data-ex="${i}">${this._t("remove")}</button>
      </div>
      <input class="notes" placeholder="${this._t("notes")}" value="${esc(ex.notes)}"
        data-scope="exercise" data-field="notes" data-ex="${i}">
      ${sets}
      <button class="secondary small" data-action="add-set" data-ex="${i}">+ ${this._t("addSet")}</button>
    </div>`;
  }

  _searchResults() {
    const query = this._search.trim().toLowerCase();
    let catalog = this._data?.catalog || [];
    const favorites = Array.isArray(this._config.exercise_ids) ? this._config.exercise_ids : [];
    if (!query) {
      catalog = favorites.map((id) => catalog.find((c) => c.id === id)).filter(Boolean);
    } else {
      catalog = catalog.filter((c) => (c.title || "").toLowerCase().includes(query)).slice(0, 20);
    }
    return catalog
      .map(
        (c) => `<button class="result" data-action="add-exercise" data-template="${esc(c.id)}">
          ${esc(c.title)}${c.muscle_group ? ` <span class="muted">${esc(c.muscle_group.replace(/_/g, " "))}</span>` : ""}
        </button>`,
      )
      .join("");
  }

  _renderSearchResults() {
    const el = this.shadowRoot.querySelector(".results");
    if (el) el.innerHTML = this._searchResults();
  }

  _renderConfirm() {
    if (this._confirm === "finish") {
      return `<div class="confirm">${this._t("confirmFinish", {
        sets: this._completedSets(),
        dest: esc(this._destination()),
      })}
        <button data-action="confirm-finish">${this._t("yes")}</button>
        <button class="secondary" data-action="cancel-confirm">${this._t("cancel")}</button></div>`;
    }
    if (this._confirm === "discard") {
      return `<div class="confirm">${this._t("confirmDiscard")}
        <button class="danger" data-action="confirm-discard">${this._t("yes")}</button>
        <button class="secondary" data-action="cancel-confirm">${this._t("cancel")}</button></div>`;
    }
    return `<div class="actions">
      <button data-action="finish" ${this._completedSets() ? "" : "disabled"}>${this._t("finish")}</button>
      <button class="secondary" data-action="discard">${this._t("discard")}</button>
    </div>`;
  }

  _renderWorkout() {
    const s = this._session;
    return `<input class="title" aria-label="${this._t("title")}" value="${esc(s.title)}"
        data-scope="session" data-field="title">
      ${s.exercises.map((ex, i) => this._renderExercise(ex, i)).join("")}
      <div class="add">
        <input data-action="search" placeholder="${this._t("search")}" value="${esc(this._search)}">
        <div class="results">${this._searchResults()}</div>
      </div>
      <label class="private"><input type="checkbox" ${s.is_private ? "checked" : ""}
        data-scope="session" data-field="is_private"> ${this._t("private")}</label>
      ${this._busy ? `<p>${this._t("sending")}</p>` : this._renderConfirm()}
      <div class="save-status muted"></div>`;
  }

  _renderResult() {
    const error = esc(this._session?.result?.error || "");
    return `<div class="message warning">${this._t("uncertain", { error })}</div>
      <div class="actions">
        <button data-action="retry">${this._t("retry")}</button>
        <button class="secondary" data-action="clear">${this._t("clear")}</button>
      </div>`;
  }

  _render() {
    let body;
    switch (this._view) {
      case "loading":
        body = `<p class="muted">${this._t("loading")}</p>`;
        break;
      case "empty":
        body = this._renderMessage() || `<p class="muted">${this._t("noAccount")}</p>`;
        break;
      case "picker":
        body = this._renderStats() + this._renderMessage() + this._renderPicker();
        break;
      case "workout":
        body = this._renderMessage() + this._renderWorkout();
        break;
      default:
        body = this._renderResult();
    }
    this.shadowRoot.innerHTML = `<style>${HevyWorkoutCard.styles}</style>
      <ha-card>
        <div class="header">
          <h2>${esc(this._config.title || this._t("workout"))}</h2>
          ${this._renderAccountPicker()}
        </div>
        <div class="content">${body}</div>
      </ha-card>`;
  }

  static get styles() {
    return `
      :host { display: block; }
      ha-card { display: block; padding: 16px; box-sizing: border-box; }
      .header { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }
      h2 { margin: 0; font-size: 1.3em; }
      h3 { margin: 12px 0 8px; font-size: 1em; }
      .muted { color: var(--secondary-text-color); font-size: 0.85em; }
      .account select, select, input { font: inherit; color: var(--primary-text-color);
        background: var(--card-background-color, #fff); border: 1px solid var(--divider-color, #ccc);
        border-radius: 6px; padding: 6px; box-sizing: border-box; min-width: 0; }
      button { font: inherit; cursor: pointer; border: none; border-radius: 6px; padding: 8px 14px;
        background: var(--primary-color); color: var(--text-primary-color, #fff); }
      button:disabled { opacity: 0.5; cursor: default; }
      button.secondary { background: transparent; color: var(--primary-color); border: 1px solid var(--primary-color); }
      button.danger { background: var(--error-color, #db4437); }
      button.small { padding: 4px 10px; font-size: 0.9em; }
      button.link { background: none; color: var(--primary-color); padding: 0 4px; }
      button.icon { background: none; color: var(--secondary-text-color); padding: 4px 6px; }
      .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0; }
      .stats div { background: var(--secondary-background-color); border-radius: 8px; padding: 8px; text-align: center; }
      .stats span { display: block; font-size: 0.75em; color: var(--secondary-text-color); }
      .routines { display: grid; gap: 8px; margin-bottom: 12px; }
      .routine { display: flex; align-items: center; gap: 8px; text-align: left; background: var(--secondary-background-color);
        color: var(--primary-text-color); }
      .routine.next { outline: 2px solid var(--primary-color); }
      .routine .name { flex: 1; font-weight: 600; }
      .routine .folder { font-size: 0.8em; color: var(--secondary-text-color); }
      .badge { background: var(--primary-color); color: var(--text-primary-color, #fff); border-radius: 10px;
        padding: 2px 8px; font-size: 0.75em; }
      .title { width: 100%; font-size: 1.1em; font-weight: 600; margin: 12px 0; }
      .exercise { border-top: 1px solid var(--divider-color); padding: 10px 0; }
      .ex-head { display: flex; justify-content: space-between; align-items: center; }
      .notes { width: 100%; margin: 6px 0; }
      .set { display: flex; align-items: center; gap: 6px; margin: 4px 0; flex-wrap: wrap; }
      .set input[type=number] { width: 72px; }
      .set.done { opacity: 0.7; }
      .set .index { width: 18px; text-align: right; color: var(--secondary-text-color); }
      .check { width: 22px; height: 22px; }
      .collapsed { font-size: 0.9em; margin: 4px 0; }
      .add { margin: 12px 0; }
      .add input { width: 100%; }
      .results { display: grid; gap: 4px; margin-top: 6px; }
      .result { text-align: left; background: var(--secondary-background-color); color: var(--primary-text-color); }
      .private { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
      .actions, .confirm { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
      .message { border-radius: 8px; padding: 10px; margin: 10px 0; }
      .message.success { background: rgba(67, 160, 71, 0.15); }
      .message.error { background: rgba(219, 68, 55, 0.15); }
      .message.warning { background: rgba(255, 166, 0, 0.18); }
      .save-status.error { color: var(--error-color, #db4437); }
    `;
  }
}

if (!customElements.get("hevy-workout-card")) {
  customElements.define("hevy-workout-card", HevyWorkoutCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "hevy-workout-card",
    name: "Hevy workout",
    description: "Log a live workout and send it to Hevy.",
  });
  console.info(`%c HEVY-WORKOUT-CARD %c ${CARD_VERSION} `, "background:#4ecdc4;color:#000", "");
}
