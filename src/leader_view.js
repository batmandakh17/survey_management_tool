/* RTM interview tool: the team leader view (Step 3). Prepare a round (household list, history, replacements,
   calendar, team, rule, files), import the enumerators' exports and merge them (proposal F), follow progress,
   export the merged call log and the round's files, and read the attrition and operational analytics.
   Reads only files the leader opens; writes only files the leader saves or exports. */
(function () {
  'use strict';
  const R = window.RTM, L = window.LCORE, S = window.LSTATS, APP = window.APP;
  const sh = () => APP.shell;
  const esc = s => sh().esc(s);
  const $ = s => document.querySelector(s);
  const p2 = n => String(n).padStart(2, '0');
  const pc = (x, d) => (x === null || x === undefined || isNaN(x) ? '–' : (100 * x).toFixed(d === undefined ? 0 : d) + '%');
  const nm = (x, d) => (x === null || x === undefined || isNaN(x) ? '–' : (+x).toFixed(d || 0));
  const ci = w => (w ? `${pc(w.p)} <span class="muted small">(${pc(w.lo)}–${pc(w.hi)}, n ${w.n})</span>` : '<span class="muted">–</span>');
  const TZ_OF = { UZ: 'Asia/Tashkent', TJ: 'Asia/Dushanbe', KG: 'Asia/Bishkek', KZ: 'Asia/Almaty', PH: 'Asia/Manila', ID: 'Asia/Jakarta', UA: 'Europe/Kyiv',
    AM: 'Asia/Yerevan', GE: 'Asia/Tbilisi', SO: 'Africa/Mogadishu', MN: 'Asia/Ulaanbaatar' };
  const COUNTRIES = (window.RTM_HOLIDAYS && window.RTM_HOLIDAYS.meta && window.RTM_HOLIDAYS.meta.countries) || {};
  const RAMADAN = new Set(['UZ', 'TJ', 'KG', 'KZ', 'ID', 'SO']);
  const WDN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const LV = window.LEAD = {};
  let st = null, cache = {};
  const ui = { tab: 'prepare', hhFilter: 'all', hhEnum: '', logEnum: '', logStatus: '', logQ: '', logMore: 0, ready: null, passphrases: null, busy: '' };
  LV.state = () => st;
  LV.ui = ui;
  LV.unsavedCount = () => (st ? st.unsaved : 0);
  LV.refresh = () => { invalidate(); render(); };
  LV.riskData = () => riskData();
  const invalidate = () => { cache = {}; };
  // the assignment and its files follow the settings they were made with: a later change asks for the rule again
  const stale = () => { if (st.plan || ui.ready) ui.stale = true; st.plan = null; ui.ready = null; ui.passphrases = null; };
  const filesStale = () => { if (ui.ready) { ui.ready = null; ui.passphrases = null; ui.stale = true; } };
  const toast = (t, k) => sh().toast(t, k);
  const render = () => sh().render();

  // ---- the leader's own log: every action with who and when, hash-chained like the enumerators' logs ----
  function logEv(what, fields) {
    const prev = st.events.length ? st.events[st.events.length - 1].hash : st.genesis;
    const e = R.clean(Object.assign({ event_id: R.uuid(), type: 'leader', what, program: st.program, round: st.round }, fields || {},
      { logged_by: st.leader, logged_at: R.localISO(R.now()), prev_hash: prev }));
    e.hash = R.sha256(R.canon(e));
    st.events.push(e);
    st.unsaved++;
    return e;
  }
  const randomSeed = () => { const a = new Uint32Array(1); crypto.getRandomValues(a); return 100000 + (a[0] % 900000); };
  function newSession(o) {
    st = {
      schema: L.SCHEMA.leader, leader: o.leader, program: o.program, country: o.country, round: o.round, started_at: R.localISO(R.now()),
      inputs: { households: null, replacements: null, history: [], manual: null }, mapping: {},
      cal: { window_start: '', window_end: '', working_weekdays: [1, 2, 3, 4, 5, 6], call_hours: { start: 9, end: 21 }, time_zone: TZ_OF[o.country] || '', dial_cap: null },
      holidayWorking: [], customHolidays: [], removedHolidays: [], ramadanOn: RAMADAN.has(o.country), breakFast: null,
      team: [], rule: { name: 'keep_same', rotation_share: null, seed: randomSeed(), order_by: 'psu', method: 'random' },
      spread: 0.5, margin: 0.15, policy: { active: true, triggers: ['REFUSAL_HARD', 'ALL_NUMBERS_DEAD'] }, protect: false,
      plan: null, generated: null, manifest: null, imports: [], resolutions: [], events: [], unsaved: 0,
      risk: { dropout: { kind: 'pooled' }, return: { kind: 'pooled' } },
    };
    st.genesis = R.sha256(R.canon({ program: st.program, round: st.round, leader: st.leader, started_at: st.started_at }));
    logEv('started', {});
    invalidate();
  }

  // ---- calendar from the settings: holidays from the bundled table, the leader's changes kept ----
  function calendar() {
    const c = st.cal;
    const out = { window_start: c.window_start, window_end: c.window_end, working_weekdays: c.working_weekdays.slice().sort(), call_hours: c.call_hours, time_zone: c.time_zone, dial_cap: c.dial_cap };
    const hol = [];
    if (R.isDateKey(c.window_start) && R.isDateKey(c.window_end)) {
      R.bundledHolidays(st.country).filter(h => h.date >= c.window_start && h.date <= c.window_end && !st.removedHolidays.includes(h.date))
        .forEach(h => hol.push({ date: h.date, name: h.name, estimated: !!h.estimated, working: st.holidayWorking.includes(h.date) }));
      st.customHolidays.filter(h => h.date >= c.window_start && h.date <= c.window_end && !hol.some(x => x.date === h.date))
        .forEach(h => hol.push({ date: h.date, name: h.name, estimated: false, working: st.holidayWorking.includes(h.date), added_by_leader: true }));
    }
    out.holidays = hol.sort((a, b) => (a.date < b.date ? -1 : 1));
    const ram = ramadanDates();
    if (st.ramadanOn && ram.length && Number.isInteger(st.breakFast)) out.ramadan = { dates: ram, break_fast_hour: st.breakFast };
    return out;
  }
  // Ramadan: the 30 days before Eid al-Fitr, from the same holiday table (Section 3.5.4), inside the window
  function ramadanDates() {
    const c = st.cal;
    if (!R.isDateKey(c.window_start) || !R.isDateKey(c.window_end)) return [];
    const out = new Set();
    R.bundledHolidays(st.country).filter(h => /fitr/i.test(h.name)).forEach(h => {
      for (let i = 1; i <= 30; i++) { const k = R.addDaysKey(h.date, -i); if (k >= c.window_start && k <= c.window_end) out.add(k); }
    });
    return [...out].sort();
  }

  // ---- derived inputs ----
  function derived() {
    if (cache.d) return cache.d;
    const d = {};
    d.hh = st.inputs.households ? L.parseHouseholds(st.inputs.households.text) : null;
    d.repl = st.inputs.replacements ? L.parseReplacements(st.inputs.replacements.text, d.hh ? d.hh.households : null) : null;
    d.histFiles = st.inputs.history.map(f => L.readHistoryFile(f.name, f.text));
    d.unknown = L.unknownCodes(d.histFiles);
    d.hist = L.buildHistory(d.histFiles.concat(exportHistory(d.histFiles)), { tz: st.cal.time_zone || null, mapping: st.mapping });
    d.round = d.hh && !d.hh.errors.length ? L.roundHouseholds(d.hh.households, d.repl && !d.repl.errors.length ? d.repl.lists : new Map(), d.hist, st.round) : null;
    d.avail = d.round && d.repl && !d.repl.errors.length ? L.availableReplacements(d.repl.lists, d.round.reserves, d.hh.households) : new Map();
    d.manualMap = null;
    if (st.inputs.manual) {
      const T = L.readTable(st.inputs.manual.text), hc = T.col('hhid'), ec = T.col('enumerator_id') || T.col('enumerator');
      d.manualMap = new Map(hc && ec ? T.rows.map(r => [String(r[hc]).trim(), String(r[ec]).trim()]) : []);
    }
    cache.d = d;
    return d;
  }
  // an enumerator's own export of an earlier round, opened as history, counts as that round's dials
  function exportHistory(files) {
    const out = [];
    files.filter(f => f.kind === 'export').forEach(f => {
      const rows = f.export.dials || [];
      const text = R.toCSV(rows.map(r => Object.fromEntries(R.CSV_COLS.map(c => [c, r[c] === undefined || r[c] === null ? '' : String(r[c])]))), R.CSV_COLS);
      out.push(L.readHistoryFile(f.name.replace(/\.json$/i, '.csv'), text));
    });
    return out;
  }
  function suggestFromHistory() {
    const d = derived(), H = d.hist;
    if (st.suggested) return;
    const lastR = H.rounds.length ? H.rounds[H.rounds.length - 1] : null;
    const lm = lastR !== null ? H.manifests.get(lastR) : null;
    if (lm && lm.calendar) {
      const c = lm.calendar;
      if (st.cal.dial_cap === null && Number.isInteger(c.dial_cap)) st.cal.dial_cap = c.dial_cap;
      if (c.call_hours) st.cal.call_hours = Object.assign({}, c.call_hours);
      if (Array.isArray(c.working_weekdays)) st.cal.working_weekdays = c.working_weekdays.slice();
      if (c.time_zone && !st.cal.time_zone) st.cal.time_zone = c.time_zone;
    }
    if (!st.team.length && lastR !== null) {
      const ids = new Set();
      if (lm) { (lm.enumerators || []).forEach(e => ids.add(e.enumerator_id)); (lm.away || []).forEach(e => ids.add(e)); }
      (H.dials.get(lastR) || []).forEach(x => { if (x.operator) ids.add(x.operator); });
      st.team = [...ids].sort().map(id => ({ id, available: true, share: 1 }));
    }
    if (lastR !== null) st.suggested = true;
  }

  // ---- applying the rule, the load check, and the files ----
  const ruleObj = () => R.clean({ name: st.rule.name, rotation_share: st.rule.name === 'keep_same' ? st.rule.rotation_share : undefined, seed: st.rule.seed,
    order_by: /split|share/.test(st.rule.name) ? st.rule.order_by : undefined, method: st.rule.name === 'share_of_total' ? st.rule.method : undefined });
  function prepErrors() {
    const d = derived(), c = st.cal, e = [];
    if (!d.hh) e.push('Open the household list (step 1).');
    else if (d.hh.errors.length) e.push('Fix the household list first (step 1).');
    if (d.repl && d.repl.errors.length) e.push('Fix the replacement list, or remove it (step 3).');
    if (!R.isDateKey(c.window_start) || !R.isDateKey(c.window_end) || c.window_end < c.window_start) e.push('Set the round window (step 4).');
    if (!Number.isInteger(c.dial_cap) || c.dial_cap < 1) e.push('Set the dial cap, the program’s stopping rule (step 4).');
    if (!c.working_weekdays.length) e.push('Tick at least one working weekday (step 4).');
    if (!(c.call_hours.start < c.call_hours.end)) e.push('The call hours must start before they end (step 4).');
    if (st.ramadanOn && ramadanDates().length && !Number.isInteger(st.breakFast)) e.push('Enter the hour the fast is broken, or untick Ramadan (step 4).');
    if (!st.team.some(t => t.available)) e.push('Add the team and mark who is available (step 5).');
    if (st.rule.name === 'keep_same' && (!Number.isFinite(st.rule.rotation_share) || st.rule.rotation_share < 0 || st.rule.rotation_share > 1)) e.push('Enter this round’s rotation share (step 6). It has no default.');
    if (st.rule.name === 'manual' && !st.inputs.manual) e.push('Open the manual list of hhid and enumerator_id (step 6).');
    if (st.rule.name === 'share_of_total') {
      const tot = st.team.filter(t => t.available).reduce((s, t) => s + (t.share || 0), 0);
      if (Math.abs(tot - 100) > 0.5) e.push(`The shares of available enumerators add up to ${nm(tot, 1)}%, not 100% (step 5).`);
    }
    if (!Number.isInteger(+st.rule.seed)) e.push('The seed must be a whole number (step 6).');
    return e;
  }
  function inputFor() {
    const d = derived();
    const team = st.team.map(t => ({ id: t.id, available: t.available, share: st.rule.name === 'share_of_total' ? t.share : (t.share > 0 ? t.share : 1) }));
    return { round: st.round, households: d.round.mains, team, hist: d.hist, tz: st.cal.time_zone || null, cap: st.cal.dial_cap, rule: Object.assign(ruleObj(), { seed: +st.rule.seed }),
      manual: d.manualMap, calendar: calendar(), spread: st.spread };
  }
  // households in the high dropout tier get an early first dial (Section 3.4 box; proposal D)
  function highRiskSet() {
    cache.r = undefined;
    const r = riskData();
    return new Set(r ? r.dropout.filter(s => s.tier === 'high').map(s => s.row._.hhid) : []);
  }
  function applyRule() {
    const errs = prepErrors();
    if (errs.length) { ui.errors = errs; return render(); }
    ui.errors = [];
    const inp = inputFor(), A = L.assign(inp);
    if (A.errors.length) { ui.errors = A.errors; return render(); }
    ui.stale = false;
    inp.highRisk = highRiskSet();
    const P = L.plan(inp, A.out, A.summaries, inp.hist);
    st.plan = { out: A.out, sums: A.summaries, notes: A.notes, warnings: A.warnings, plans: P.plans, best: P.best, firstDays: P.firstDays, workingDays: P.workingDays, moves: [], at: R.localISO(R.now()) };
    st.generated = null; ui.ready = null; ui.passphrases = null;
    logEv('rule_applied', { rule: st.rule.name, rotation_share: st.rule.rotation_share, seed: +st.rule.seed, households: A.out.size });
    render();
  }
  function balance() {
    if (!st.plan) return;
    const inp = inputFor();
    const moves = L.balance(inp, st.plan.out, st.plan.sums, st.margin, +st.rule.seed);
    st.plan.moves = st.plan.moves.concat(moves);
    inp.highRisk = highRiskSet();
    const P = L.plan(inp, st.plan.out, st.plan.sums, inp.hist);
    st.plan.plans = P.plans;
    logEv('loads_balanced', { margin: st.margin, moved: moves.length });
    toast(moves.length ? `${R.plural(moves.length, 'household')} moved to balance the loads (reason: capacity).` : 'The loads are already within the margin, or no kept household could be moved.');
    render();
  }
  function reassign(hhid, to) {
    const x = st.plan.out.get(hhid);
    if (!x || x.enumerator_id === to) return;
    st.plan.out.set(hhid, { enumerator_id: to, reason: 'manual', previous_enumerator: x.previous_enumerator || x.enumerator_id });
    const inp = inputFor();
    inp.highRisk = highRiskSet();
    st.plan.plans = L.plan(inp, st.plan.out, st.plan.sums, inp.hist).plans;
    logEv('household_moved', { hhid, to });
    render();
  }
  const PASS_ALPHA = 'abcdefghjkmnpqrstuvwxyz23456789';
  const newPassphrase = () => { const a = new Uint32Array(12); crypto.getRandomValues(a); const s = [...a].map(x => PASS_ALPHA[x % PASS_ALPHA.length]).join(''); return `${s.slice(0, 4)}-${s.slice(4, 8)}-${s.slice(8, 12)}`; };
  async function writeFiles() {
    const d = derived(), p = st.plan;
    const at = R.localISO(R.now());
    const B = L.buildFiles(Object.assign(inputFor(), {
      program: st.program, country: st.country, leader: st.leader, generated_at: at, replacement_policy: st.policy,
      out: p.out, sums: p.sums, plans: p.plans, allHouseholds: d.hh.households, replacements: d.avail,
    }));
    const files = [];
    ui.passphrases = null;
    if (st.protect) {
      if (!R.canSeal()) return toast('This browser cannot protect files here.', 'warn');
      ui.busy = 'Protecting the files…'; render();
      const pass = [];
      for (const f of B.files) {
        const pw = newPassphrase();
        const { env } = await R.seal(f.obj, pw, { contains: R.SCHEMA.assign, program: st.program, round: st.round, enumerator_id: f.enumerator_id });
        files.push({ name: f.name, text: JSON.stringify(env, null, 1), enumerator_id: f.enumerator_id, n: f.obj.households.length, fingerprint: f.obj.fingerprint, protected: true });
        pass.push({ enumerator_id: f.enumerator_id, file: f.name, passphrase: pw });
      }
      ui.passphrases = pass;
      ui.busy = '';
    } else B.files.forEach(f => files.push({ name: f.name, text: JSON.stringify(f.obj, null, 1), enumerator_id: f.enumerator_id, n: f.obj.households.length, fingerprint: f.obj.fingerprint }));
    if (st.protect) B.manifest.enumerators.forEach(e => { e.protected = true; });
    const mName = `${st.program}_R${p2(st.round)}_manifest.json`;
    files.push({ name: mName, text: JSON.stringify(B.manifest, null, 1), manifest: true });
    files.push({ name: 'calendar.csv', text: R.toCSV([B.calendarRow], ['round', 'start', 'end']), calendar: true });
    st.generated = { at, files: files.map(f => R.clean({ name: f.name, enumerator_id: f.enumerator_id, households: f.n, fingerprint: f.fingerprint, protected: f.protected })) };
    st.manifest = B.manifest;
    ui.ready = files;
    logEv('files_written', { files: files.length, manifest_fingerprint: B.manifest.fingerprint, protected: st.protect ? 1 : undefined });
    invalidate();
    render();
  }
  async function saveAllToFolder(files) {
    if (!window.showDirectoryPicker) return downloadAll(files);
    try {
      const dir = await window.showDirectoryPicker({ mode: 'readwrite' });
      for (const f of files) { const h = await dir.getFileHandle(f.name, { create: true }); const w = await h.createWritable(); await w.write(f.text); await w.close(); }
      toast(`${files.length} files saved in the folder ${dir.name}.`);
    } catch (e) { if (!e || e.name !== 'AbortError') downloadAll(files); }
  }
  function downloadAll(files) { files.forEach((f, i) => setTimeout(() => sh().download(f.name, f.text, f.name.endsWith('.csv') ? 'text/csv' : 'application/json'), i * 250)); }

  // ---- the merge (F) ----
  const resolutionMap = () => { const m = new Map(); st.resolutions.forEach(r => m.set(r.key, r)); return m; };
  function merged() {
    if (cache.g) return cache.g;
    if (!st.manifest) return null;
    const recs = st.imports.map(f => Object.assign(L.readImport(f.name, f.text), { opened: f.opened }));
    const G = L.merge(st.manifest, recs, resolutionMap(), R.now());
    const C = L.cases(st.manifest, G), P = L.progress(st.manifest, C, G);
    cache.g = { G, C, P, recs };
    return cache.g;
  }
  async function addImports(files) {
    let n = 0;
    for (const f of files) {
      const text = await sh().readText(f);
      st.imports.push({ name: f.webkitRelativePath || f.name, text });
      n++;
    }
    logEv('logs_imported', { files: n, names: [...files].map(f => f.name).slice(0, 50) });
    invalidate();
    toast(`${R.plural(n, 'file')} added to the merge.`);
    render();
  }
  function resolve(key, decision) {
    const note = ($(`[data-note-for="${CSS.escape(key)}"]`) || {}).value || '';
    const e = logEv('resolution', { key, decision, note: note || undefined });
    st.resolutions.push({ key, decision, note, logged_by: e.logged_by, logged_at: e.logged_at });
    invalidate();
    render();
  }
  function openSealed(i) {
    const f = st.imports[i];
    let env; try { env = JSON.parse(f.text); } catch (e) { return; }
    sh().askPassphrase({ name: f.name }, env, obj => {
      f.text = JSON.stringify(obj); f.opened = 1;
      logEv('contacts_opened', { file: f.name });
      invalidate(); render();
    });
  }

  // ---- the round's output files ----
  const OUTCOMES = [
    ['COMPLETE', 'complete', 'Interviewed: the complete counted for the round'],
    ['REFUSED', 'refusal', 'A refusal that is not to be retried'],
    ['CONTACT_NO_INTERVIEW', 'contact, no interview', 'Reached but not interviewed: appointment, partial, respondent away, soft refusal, language'],
    ['NO_CONTACT', 'non-contact', 'Dialed, never reached'],
    ['NUMBER_NOT_WORKING', 'not eligible on its numbers', 'Every number dialed was not in service or wrong'],
    ['REPLACED', 'replaced', 'Replaced by its next replacement household this round'],
    ['NOT_DIALED', 'not dialed', 'Assigned, not dialed'],
    ['NOT_REPORTED', 'not reported', 'The enumerator’s log for the round is missing'],
    ['CONFLICT', 'unresolved', 'Two completes the leader has not yet resolved'],
  ];
  function interviewsRows(C) {
    const tz = st.manifest.calendar.time_zone;
    const day = iso => R.partsIn(new Date(Date.parse(iso)), tz).key;
    return [...C.values()].sort((a, b) => (a.hhid < b.hhid ? -1 : 1)).map(c => {
      const dials = c.dials, cat = code => (R.STATUS_BY[code] || {}).cat;
      let outcome;
      if (c.state === 'complete') outcome = 'COMPLETE';
      else if (c.state === 'conflict') outcome = 'CONFLICT';
      else if (c.state === 'replaced') outcome = 'REPLACED';
      else if (dials.some(d => d.status === 'REFUSAL_HARD')) outcome = 'REFUSED';
      else if (dials.length && dials.every(d => R.DEAD.has(d.status))) outcome = 'NUMBER_NOT_WORKING';
      else if (dials.some(d => ['contact', 'refusal', 'complete'].includes(cat(d.status)))) outcome = 'CONTACT_NO_INTERVIEW';
      else if (dials.length) outcome = 'NO_CONTACT';
      else outcome = c.state === 'not_reported' ? 'NOT_REPORTED' : 'NOT_DIALED';
      const last = dials.length ? dials[dials.length - 1] : null;
      return { hhid: c.hhid, interview_date: c.complete ? day(c.complete.ts) : last ? day(last.ts) : '', outcome,
        enumerator: c.complete ? (c.complete.operator || c.complete.source) : c.enumerator_id };
    });
  }
  function exportFile(what) {
    const M = st.manifest, base = `${M.program}_R${p2(M.round)}`, g = merged();
    const files = {
      calls: () => [`${base}_calls.csv`, R.toCSV(L.callsRows(g.G), R.CSV_COLS)],
      actions: () => [`${base}_actions.csv`, R.toCSV(L.actionsRows(g.G), L.ACOLS)],
      interviews: () => ['interviews.csv', R.toCSV(interviewsRows(g.C), ['hhid', 'interview_date', 'outcome', 'enumerator'])],
      outcomes: () => ['outcome_codes.csv', R.toCSV(OUTCOMES.map(([code, meaning, note]) => ({ code, meaning, note })), ['code', 'meaning', 'note'])],
      calendar: () => ['calendar.csv', R.toCSV([{ round: M.round, start: M.calendar.window_start, end: M.calendar.window_end }], ['round', 'start', 'end'])],
      report: () => [`${base}_merge_report.csv`, R.toCSV(L.reportRows(g.G), L.REPORT_COLS)],
      contacts: () => [`${base}_contact_updates.csv`, R.toCSV(L.contactRows(g.G), L.CONTACT_COLS)],
      manifest: () => [`${base}_manifest.json`, JSON.stringify(M, null, 1)],
    };
    const [name, text] = files[what]();
    sh().download(name, text, name.endsWith('.csv') ? 'text/csv' : 'application/json');
    logEv('exported', { file: name });
  }

  // ---- saving and reopening the leader's session (A.6) ----
  function projectObject() {
    const o = {
      schema: L.SCHEMA.leader, tool_version: R.VERSION, saved_at: R.localISO(R.now()), saved_by: st.leader,
      program: st.program, country: st.country, round: st.round, started_at: st.started_at, chain_genesis: st.genesis,
      settings: { cal: st.cal, holidayWorking: st.holidayWorking, customHolidays: st.customHolidays, removedHolidays: st.removedHolidays, ramadanOn: st.ramadanOn,
        breakFast: st.breakFast, team: st.team, rule: st.rule, spread: st.spread, margin: st.margin, policy: st.policy, protect: st.protect, mapping: st.mapping, risk: st.risk },
      inputs: st.inputs,
      plan: st.plan ? { out: [...st.plan.out], moves: st.plan.moves, notes: st.plan.notes, warnings: st.plan.warnings, at: st.plan.at } : null,
      generated: st.generated, manifest: st.manifest, imports: st.imports, resolutions: st.resolutions, events: st.events,
      contains_contact_information: true,
    };
    o.checksum = R.sha256(R.canon(o));
    return o;
  }
  // the save dialog: an optional passphrase typed twice; then, if given, what to do once the file is written
  function askSave(after) {
    sh().confirmModal('Save the leader session', 'The file holds the household list with contact information. Keep it in your own folder. To protect it with a passphrase, type one twice; leave both empty to save it unprotected.',
      { okLabel: 'Save', input: 'Passphrase (optional)', input2: 'The same passphrase again', password: true }, async (v, v2) => {
        if ((v || v2) && v !== v2) return toast('The two passphrases differ. Nothing was saved.', 'warn');
        await saveProject(v || null);
        if (after) after();
      });
  }
  async function saveProject(protectPass) {
    const o = projectObject();
    let text = JSON.stringify(o);
    if (protectPass) text = JSON.stringify((await R.seal(o, protectPass, { contains: L.SCHEMA.leader, program: st.program, round: st.round, enumerator_id: st.leader })).env);
    const name = `leader_${st.program}_R${p2(st.round)}.json`;
    let where = null;
    if (window.showSaveFilePicker && !APP.noFSA) {
      try {
        if (!LV.handle) LV.handle = await window.showSaveFilePicker({ suggestedName: name, types: [{ description: 'Leader session', accept: { 'application/json': ['.json'] } }] });
        const w = await LV.handle.createWritable(); await w.write(text); await w.close(); where = LV.handle.name;
      } catch (e) { if (e && e.name === 'AbortError') return; LV.handle = null; }
    }
    if (!where) { const p = R.partsIn(R.now(), null); where = name.replace('.json', `_${p.key}_${p2(p.h)}${p2(p.mi)}.json`); sh().download(where, text, 'application/json'); }
    st.unsaved = 0; st.last_save = { at: o.saved_at, file: where };
    toast(`Leader session saved${protectPass ? ', protected' : ''}: ${where}. It holds contact information: keep it in your own folder.`);
    render();
  }
  function loadProject(o, name) {
    if (!o || o.schema !== L.SCHEMA.leader) return toast(`${name} is not a saved leader session.`, 'warn');
    const copy = Object.assign({}, o); delete copy.checksum;
    if (R.sha256(R.canon(copy)) !== o.checksum) return toast(`${name} was changed or damaged after it was saved (checksum). It was not opened.`, 'warn');
    const chain = R.verifyChain(o.events || [], o.chain_genesis);
    st = { schema: o.schema, leader: o.saved_by, program: o.program, country: o.country, round: o.round, started_at: o.started_at, genesis: o.chain_genesis,
      inputs: o.inputs, plan: null, generated: o.generated, manifest: o.manifest, imports: o.imports || [], resolutions: o.resolutions || [], events: o.events || [], unsaved: 0 };
    Object.assign(st, o.settings);
    st.risk = st.risk || { dropout: { kind: 'pooled' }, return: { kind: 'pooled' } };
    if (o.plan) {
      invalidate();
      const inp = inputFor();
      const sums = new Map(inp.households.map(h => [h.hhid, L.summaryOf(inp.hist, h.hhid, st.round, inp.tz)]));
      const out = new Map(o.plan.out);
      st.plan = { out, sums, notes: o.plan.notes, warnings: o.plan.warnings, moves: o.plan.moves, at: o.plan.at };
      const P = L.plan(inp, out, sums, inp.hist);
      Object.assign(st.plan, { plans: P.plans, best: P.best, firstDays: P.firstDays, workingDays: P.workingDays });
    }
    invalidate();
    ui.tab = st.manifest ? 'progress' : 'prepare';
    toast(`Leader session restored: ${st.program} round ${st.round}, ${R.plural(st.imports.length, 'imported file')}${chain.ok ? '' : ', but its log fails the integrity check'}.`, chain.ok ? 'ok' : 'warn');
    render();
  }

  // ---- risk (Step 4): features from the closed rounds of the loaded history, scored for this round's households ----
  function riskData() {
    if (cache.r !== undefined) return cache.r;
    const model = window.LRISK && LRISK.model();
    const d = derived();
    if (!model || !d.hist.rounds.length) { cache.r = null; return null; }
    const input = [];
    for (const [r, ds] of d.hist.dials) if (r < st.round) ds.forEach(x => input.push({ hhid: x.hhid, round: r, wall: x.wall, status: x.status, cmp_code: x.cmp, dur: x.dur, operator: x.operator }));
    const T = S.build(input), X = LRISK.facts(T, model), c = st.round;
    const holder = new Map();
    if (st.manifest) st.manifest.households.forEach(h => holder.set(h.hhid, { e: h.enumerator_id, stratum: h.stratum }));
    else if (st.plan && d.round) { const hh = new Map(d.round.mains.map(h => [h.hhid, h])); for (const [id, x] of st.plan.out) holder.set(id, { e: x.enumerator_id, stratum: (hh.get(id) || {}).stratum }); }
    else if (d.round) d.round.mains.forEach(h => holder.set(h.hhid, { e: '', stratum: h.stratum }));
    const ids = [...holder.keys()].sort();
    const drows = ids.map(h => LRISK.dropoutRow(model, X, h, c - 1)).filter(Boolean);
    const rrows = ids.map(h => LRISK.returnRow(model, X, h, c - 2)).filter(Boolean);
    const out = { model, X, holder, c, history: X.rounds };
    out.dropout = LRISK.tiers(model, LRISK.score(model.dropout, drows, st.risk.dropout), model.tiers.dropout);
    out.return = LRISK.tiers(model, LRISK.score(model.return, rrows, st.risk.return), model.tiers.return);
    out.own = { dropout: LRISK.ownPairs(model, X, 'dropout'), return: LRISK.ownPairs(model, X, 'return') };
    cache.r = out;
    return out;
  }
  const chanceText = (kind, p) => {
    const f = p >= 0.1 ? `about ${Math.round(p * 10)} in 10` : p >= 0.01 ? `about ${Math.round(p * 100)} in 100` : 'fewer than 1 in 100';
    return kind === 'dropout' ? `${f} similar households were not interviewed the next round` : `${f} similar households were interviewed again within three rounds`;
  };
  const calibrated = kind => st.risk[kind] && st.risk[kind].kind !== 'pooled';

  // ---- analytics: earlier rounds (closed) and this round so far ----
  function analytics() {
    if (cache.a) return cache.a;
    const d = derived(), g = merged();
    const input = [];
    for (const [r, ds] of d.hist.dials) ds.forEach(x => input.push({ hhid: x.hhid, round: r, wall: x.wall, status: x.status, cmp_code: x.cmp, dur: x.dur, operator: x.operator }));
    const cur = st.manifest ? st.manifest.round : st.round;
    if (g) g.G.dials.forEach(x => input.push({ hhid: x.hhid, round: cur, wall: R.wallFromISO(x.ts), status: x.status, cmp_code: x.status === 'COMPLETE', dur: x.dur_min, operator: x.operator || x.logged_by }));
    const T = S.build(input.filter(x => x.round <= cur));
    const closed = T.rounds.filter(r => r < cur), now = T.rounds.includes(cur) ? [cur] : [];
    const I = S.interviewed(T, d.hist.interviews.size ? d.hist.interviews : null);
    const rd = new Map();
    for (const c of T.cases.values()) if (c.completed) { if (!rd.has(c.round)) rd.set(c.round, []); rd.get(c.round).push(c.complete_dial.date); }
    const roundDates = new Map([...rd].map(([r, a]) => [r, a.sort()[Math.floor((a.length - 1) / 2)]]));
    const hol = new Map();
    for (const r of T.rounds) {
      const m = r === cur ? st.manifest : d.hist.manifests.get(r);
      const list = m && m.calendar && m.calendar.holidays ? m.calendar.holidays : R.bundledHolidays(st.country);
      hol.set(r, new Map(list.map(h => [h.date, h.name])));
    }
    const ram = new Set();
    R.bundledHolidays(st.country).filter(h => /fitr/i.test(h.name)).forEach(h => { for (let i = 1; i <= 30; i++) ram.add(R.addDaysKey(h.date, -i)); });
    const closedSets = { sets: new Map([...I.sets].filter(([r]) => r < cur)), source: I.source };
    const a = { T, cur, closed, now, source: I.source,
      s33c: closed.length ? S.s33(T, closed) : null, s33n: now.length ? S.s33(T, now) : null,
      s34: S.s34(closedSets, closed, roundDates),
      s31c: closed.length ? S.s31(T, closed) : null, s31n: now.length ? S.s31(T, now) : null,
      s35c: closed.length ? S.s35(T, closed, { holidays: hol, ramadan: ram }) : null, s35n: now.length ? S.s35(T, now, { holidays: hol, ramadan: ram }) : null };
    // continuation into this round, so far: last round's respondents already interviewed this round
    const prev = I.sets.get(cur - 1), sofar = I.sets.get(cur);
    a.sofar = prev && prev.size && now.length ? { base: prev.size, share: sofar ? [...prev].filter(h => sofar.has(h)).length / prev.size : 0 } : null;
    cache.a = a;
    return a;
  }

  // =================================================================== rendering
  LV.html = () => (st ? sessionView() : startView());
  LV.after = () => {};
  function startView() {
    const opts = Object.entries(COUNTRIES).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join('');
    return `<section class="start"><h1>Team leader view</h1>
      <p class="lead">Prepare a round, write one assignment file per enumerator, then import their exported logs to follow progress, merge the call log and read the round's analytics.</p>
      <div class="startgrid">
        <form class="pickcard" id="lstart" novalidate onsubmit="return false">
          <b>Start a round</b>
          <label>Your leader ID <input name="leader" required placeholder="L01" autocomplete="off"></label>
          <label>Program code <input name="program" required placeholder="L2MN" autocomplete="off"></label>
          <label>Country, for the holiday calendar <select name="country" required><option value="">Choose the country</option>${opts}</select></label>
          <label>Round <input name="round" type="number" min="1" required></label>
          <button class="primary" data-lact="start">Start</button>
        </form>
        <label class="bigpick"><input type="file" id="lf-project" accept=".json,application/json"><b>Continue a saved leader session</b><span>For example <code>leader_L2MN_R05.json</code></span>
          <span>Only importing logs? Start a round, then open its manifest on the Import tab.</span></label>
      </div>
      <div class="how"><h2>How it works</h2><ol>
        <li><b>Prepare the round.</b> Open the household list, earlier rounds' merged logs and the replacement list; set the calendar and the team; choose the rule. The tool writes one assignment file per enumerator, so no file carries another enumerator's contact information.</li>
        <li><b>Give each enumerator their own file</b>, through a folder only they can read.</li>
        <li><b>Import their exports</b> from the common folder, in one batch, whenever you want to see progress. Every merge decision is listed and none is made silently.</li></ol>
        <p class="muted">This page reads only files you open and writes only files you save or export. It has no server, no shared database and no network connection.</p></div></section>`;
  }
  function sessionView() {
    const M = st.manifest;
    const tabs = [['prepare', 'Prepare round'], ['import', 'Import logs'], ['progress', 'Progress'], ['calllog', 'Call log'], ['analytics', 'Analytics'], ['risk', 'Risk lists']];
    const g = M ? merged() : null;
    const openIssues = g && st.imports.length ? g.G.issues.filter(i => i.status === 'open' && i.severity === 'action').length : 0;
    return `<section class="summary">
        <div class="line"><b>${esc(st.leader)}</b> · ${esc(st.program)} round ${st.round} · ${esc(COUNTRIES[st.country] || st.country)}${M ? ` · window ${esc(M.calendar.window_start)} to ${esc(M.calendar.window_end)} · ${M.households.length} households, ${M.enumerators.length} enumerators` : ''}</div>
        <div class="actions"><button class="primary" data-lact="save"${st.unsaved ? ` title="${R.plural(st.unsaved, 'change')} not saved yet"` : ''}>Save leader session${st.unsaved ? ` <span class="pill" aria-label="${R.plural(st.unsaved, 'change')} not saved yet">${st.unsaved}</span>` : ''}</button>
          <button class="subtle" data-lact="close">Close</button></div>
        <div class="savestate">${st.last_save ? `Last saved ${esc(st.last_save.at.slice(0, 16).replace('T', ' '))} (${esc(st.last_save.file)})` : 'Not saved yet'}${st.unsaved ? `${(st.last_save ? ', ' : ': ')}${R.plural(st.unsaved, 'change')}${st.last_save ? ' since' : ''}` : ''} · the session file holds contact information: keep it in your own folder</div>
      </section>
      <nav class="tabs" role="tablist">${tabs.map(([k, l]) => `<button role="tab" data-lact="tab" data-t="${k}" aria-selected="${ui.tab === k}" class="${ui.tab === k ? 'on' : ''}">${l}${k === 'import' && openIssues ? ` <span class="count warn" title="${R.plural(openIssues, 'merge question')} waiting for your decision">${openIssues}</span>` : ''}</button>`).join('')}</nav>
      <div class="body"><main class="panel lead-panel">${({ prepare: prepareTab, import: importTab, progress: progressTab, calllog: callLogTab, analytics: analyticsTab, risk: riskTab })[ui.tab]()}</main></div>`;
  }
  // the replacement list in words: how many, for how many households, how many still in reserve
  function replSummary(d) {
    const n = d.repl.counts.replacements, m = d.repl.counts.mains, free = [...d.avail.values()].reduce((a, l) => a + l.length, 0);
    return `${d.repl.format === 'rtmtools' ? 'rtmtools selection' : 'Program list'}: ${R.plural(n, 'replacement')}${n === m ? `, one for each of ${R.plural(m, 'household')}` : ` for ${R.plural(m, 'household')}`}. ${free} ${free === 1 ? 'is' : 'are'} still in reserve and can be used this round.`;
  }
  // why the return model's medium tier was merged, from the backtests bundled with the model
  const mergedWhy = () => {
    const ov = ((window.RTM_RISK.tiers.overlaps || {}).return) || [], names = { UZB: 'L2CU', TAJ: 'L2T', KGZ: 'L2KGZ', KAZ: 'L2Kaz', PHL: 'L2PHL', IND: 'L2Indo' };
    const where = [...new Set(ov.map(o => { const n = o.table.split('/').map(x => names[x]).find(Boolean); return n ? n + (o.table.includes('recalibrated') ? ', recalibrated on its own rounds' : '') : ''; }).filter(Boolean))];
    return `in ${ov.length === 1 ? 'one held-out test' : R.plural(ov.length, 'held-out test')}${where.length ? ` (${where.join('; ')})` : ''}, its medium and low tiers could not be told apart, so they are merged`;
  };
  const decisionLabel = i => { const c = (i.choices || []).find(x => x.value === i.decision); return c ? c.label : i.decision === 'acknowledged' ? 'Noted' : i.decision; };
  const REASON_WORD = { keep: 'kept', rotation: 'rotation', switch_hard_to_reach: 'hard to reach', enumerator_unavailable: 'enumerator away', new: 'new',
    manual: 'by hand', capacity: 'capacity', rule: 'by the round’s rule', replacement: 'replacement' };
  const list = arr => (arr && arr.length ? `<ul class="msgs">${arr.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '');
  const errList = arr => (arr && arr.length ? `<div class="alert warn">${list(arr)}</div>` : '');

  // ---- Prepare round ----
  function prepareTab() {
    const d = derived();
    const c = st.cal, cal = calendar();
    const hhCard = `<section class="lcard"><h3>1 · Household list</h3>
      <p class="muted">One row per household: <code>hhid, psu, stratum, phone_1 … phone_3</code>, optional <code>phone_k_label, contact_name, respondent_member, language, tz, status</code> (active, removed or reserve). CSV in UTF-8, or an Excel workbook (its first sheet). It holds contact information: it never goes to the common folder.</p>
      <label class="btn subtle">${st.inputs.households ? 'Replace' : 'Open'} the household list<input type="file" id="lf-hh" accept=".csv,.txt,.xlsx"></label>
      ${st.inputs.households ? `<span class="muted"> ${esc(st.inputs.households.name)}</span>${list(st.inputs.households.warnings)}` : ''}
      ${d.hh ? `${errList(d.hh.errors)}${d.hh.errors.length ? '' : `<p>${d.hh.counts.rows} rows: <b>${d.hh.counts.active}</b> active, ${d.hh.counts.removed} removed, ${d.hh.counts.reserve} reserve.${d.round ? ` This round: <b>${d.round.mains.length}</b> households to assign, ${d.round.reserves.size} unused replacements, ${d.round.removed.length} removed (kept in the list, not deleted).` : ''}</p>`}${list(d.hh.warnings)}${d.round ? list(d.round.warnings) : ''}` : ''}</section>`;
    const histRows = d.hist.rounds.map(r => {
      const ds = d.hist.dials.get(r) || [], m = d.hist.manifests.get(r), cm = d.hist.complete.get(r);
      return `<tr><td>${r}</td><td class="num">${(d.hist.present.get(r) || new Set()).size}</td><td class="num">${ds.length}</td><td class="num">${cm ? cm.size : 0}</td><td>${m ? 'yes' : '–'}</td><td>${d.hist.interviews.has(r) ? 'yes' : '–'}</td></tr>`;
    }).join('');
    const unknown = [...d.unknown];
    const histCard = `<section class="lcard"><h3>2 · Earlier rounds</h3>
      <p class="muted">The merged logs the leader view exported for earlier rounds (<code>_calls.csv</code>, <code>_actions.csv</code>, <code>_manifest.json</code>), a program's own dial log in the same columns, or interview records (<code>hhid, round, interview_date, outcome, enumerator</code>). They give each household's last interview, last enumerator and dials, which the rule and the plan use.</p>
      <label class="btn subtle">Add files<input type="file" id="lf-hist" accept=".csv,.json" multiple></label>${st.inputs.history.length ? ` <button class="link" data-lact="clearhist">Remove all ${st.inputs.history.length}</button>` : ''}
      ${d.histFiles.filter(f => f.kind === 'unknown').map(f => `<div class="alert warn">${esc(f.name)}: ${esc(f.error)}</div>`).join('')}
      ${histRows ? `<table class="grid small"><thead><tr><th>Round</th><th class="num">Households</th><th class="num">Dials</th><th class="num">Interviewed</th><th>Manifest</th><th>Interview records</th></tr></thead><tbody>${histRows}</tbody></table>
        <p class="muted small">Interviewed = a case completed by the handbook's rule (Box 3.0: the first complete-coded dial of 3 minutes or more).</p>` : ''}
      ${unknown.length ? `<div class="alert info"><b>Map the program's own result codes once</b> onto the tool's codes, in the lists below. Unmapped codes count as "Other".<table class="grid small"><tbody>${unknown.map(([code, n]) => `<tr><td><code>${esc(code)}</code> <span class="muted">(${n} dials)</span></td><td><select data-lmap="${esc(code)}"><option value="">Other</option>${R.STATUS.map(s => `<option value="${s.code}" ${st.mapping[code] === s.code ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></td></tr>`).join('')}</tbody></table></div>` : ''}
      </section>`;
    const replCard = `<section class="lcard"><h3>3 · Replacement list</h3>
      <p class="muted">The sampling tool's <code>selection.csv</code> (rtmtools: <code>unit_id, stratum, selected, reserve</code>), or a program file <code>hhid, replacement_hhid, rank</code>. Each PSU's reserve is dealt round-robin to its households in selection order, so each replacement belongs to one household. Replacement households need their contacts in the household list.</p>
      <label class="btn subtle">${st.inputs.replacements ? 'Replace' : 'Open'} the replacement list<input type="file" id="lf-repl" accept=".csv,.txt,.xlsx"></label>${st.inputs.replacements ? ` <span class="muted">${esc(st.inputs.replacements.name)}</span> <button class="link" data-lact="clearrepl">Remove</button>` : ''}
      ${d.repl ? `${errList(d.repl.errors)}${d.repl.errors.length ? '' : `<p>${replSummary(d)}</p>`}${list(d.repl.warnings)}` : ''}
      <div class="row2"><label class="inline"><input type="checkbox" data-lset="policy.active" data-type="bool" ${st.policy.active ? 'checked' : ''}> Replacements in use this round</label>
      <span class="checks">Allowed after: ${[['REFUSAL_HARD', 'a hard refusal'], ['ALL_NUMBERS_DEAD', 'no working number'], ['CAP_REACHED', 'the dial cap']].map(([k, l]) => `<label class="inline"><input type="checkbox" data-ltrig="${k}" ${st.policy.triggers.includes(k) ? 'checked' : ''}> ${l}</label>`).join(' ')}</span></div></section>`;
    const wd = [1, 2, 3, 4, 5, 6, 7].map(i => `<label class="inline"><input type="checkbox" data-lwd="${i}" ${c.working_weekdays.includes(i) ? 'checked' : ''}> ${WDN[i - 1]}</label>`).join(' ');
    const ram = ramadanDates();
    const working = cal.holidays.length ? `<table class="grid small"><thead><tr><th>Date</th><th>Holiday</th><th>Call center works</th><th></th></tr></thead><tbody>${cal.holidays.map(h => `<tr><td>${esc(h.date)} ${WDN[R.weekdayOfKey(h.date) - 1]}</td><td>${esc(h.name)}${h.estimated ? ' <span class="tag">estimated</span>' : ''}${h.added_by_leader ? ' <span class="tag">added</span>' : ''}</td><td><input type="checkbox" data-lhwork="${h.date}" ${h.working ? 'checked' : ''}></td><td><button class="link" data-lact="delhol" data-d="${h.date}">remove</button></td></tr>`).join('')}</tbody></table>` : R.isDateKey(c.window_start) && R.isDateKey(c.window_end) ? '<p class="muted">No public holiday inside the window.</p>' : '<p class="muted">Set the first and last day above to see the public holidays inside the window.</p>';
    const days = R.isDateKey(c.window_start) && R.isDateKey(c.window_end) ? L.workingDays(cal) : [];
    const calCard = `<section class="lcard"><h3>4 · Round calendar</h3>
      <p class="muted">A fixed window for the round. Holidays come from the bundled table (Python package <code>holidays</code>, as in Section 3.5.4); they are left out of automatic planning but never block calling.</p>
      <div class="row3"><label>First day <input type="date" data-lset="cal.window_start" value="${esc(c.window_start)}"></label><label>Last day <input type="date" data-lset="cal.window_end" value="${esc(c.window_end)}"></label>
      <label>Dial cap (stopping rule) <input type="number" min="1" data-lset="cal.dial_cap" data-type="int" value="${c.dial_cap === null ? '' : c.dial_cap}"></label></div>
      <div class="checks">Working days: ${wd}</div>
      <div class="row3"><label>Calls from <input type="number" min="0" max="23" data-lset="cal.call_hours.start" data-type="int" value="${c.call_hours.start}"></label><label>until <input type="number" min="1" max="24" data-lset="cal.call_hours.end" data-type="int" value="${c.call_hours.end}"></label>
      <label>Time zone <input data-lset="cal.time_zone" value="${esc(c.time_zone)}" placeholder="Asia/Ulaanbaatar"></label></div>
      ${days.length ? `<p>${days.length} working days in the window; first dials are spread over the first <input class="tiny" type="number" min="10" max="100" step="5" data-lset="spread" data-type="pct" value="${Math.round(st.spread * 100)}">% of them (Section 3.4: front-load the contact effort).</p>` : ''}
      <h4>Holidays inside the window</h4>${working}
      <div class="row3"><label>Add a day off <input type="date" id="lhol-date"></label><label>Name <input id="lhol-name" placeholder="call center closed"></label><button class="subtle" data-lact="addhol">Add</button></div>
      ${ram.length || st.ramadanOn ? `<h4>Ramadan</h4><label class="inline"><input type="checkbox" data-lset="ramadanOn" data-type="bool" ${st.ramadanOn ? 'checked' : ''}> Observed: no first dial is planned in the hour the fast is broken (Section 3.5.4)</label>
        ${ram.length ? `<p>${R.plural(ram.length, 'day')} of the window ${ram.length === 1 ? 'falls' : 'fall'} in Ramadan (${esc(ram[0])} to ${esc(ram[ram.length - 1])}: the 30 days before Eid al-Fitr).</p><label>Hour the fast is broken <input type="number" min="0" max="23" data-lset="breakFast" data-type="int" value="${st.breakFast === null ? '' : st.breakFast}"></label>` : '<p class="muted">No day of the window falls in Ramadan.</p>'}` : ''}
      </section>`;
    const lastR = d.hist.rounds.length ? d.hist.rounds[d.hist.rounds.length - 1] : null;
    const lastCount = id => (lastR !== null ? [...(d.hist.roster.get(lastR) || new Map()).values()].filter(e => e === id).length : 0);
    const teamCard = `<section class="lcard"><h3>5 · Team</h3>
      <table class="grid small"><thead><tr><th>Enumerator</th><th>Available this round</th><th>Share${st.rule.name === 'share_of_total' ? ' (%, adds up to 100)' : ' (relative)'}</th><th class="num">Households last round</th><th></th></tr></thead><tbody>
      ${st.team.map((t, i) => `<tr><td class="id">${esc(t.id)}</td><td><input type="checkbox" data-lteam="${i}" data-f="available" ${t.available ? 'checked' : ''}></td><td><input class="tiny" type="number" min="0" step="any" data-lteam="${i}" data-f="share" value="${t.share}"></td><td class="num">${lastCount(t.id) || '–'}</td><td><button class="link" data-lact="delenum" data-i="${i}">remove</button></td></tr>`).join('')}
      </tbody></table>
      <div class="row3"><label>Add an enumerator ID <input id="lenum-id" placeholder="E08"></label><button class="subtle" data-lact="addenum">Add</button></div>
      <p class="muted small">An enumerator marked away keeps their history; their households are dealt to the others with reason "enumerator unavailable" (Section 3.5.3's forced change).</p></section>`;
    const rules = [
      ['keep_same', 'Keep the same enumerator <span class="tag">default</span>', 'The handbook’s stated default (Section 3.5.3 and its rule-of-thumb box): keep the same enumerator, rotate a planned share of households each round, and switch the enumerator for a household that becomes hard to reach. The rotation lets enumerator effects be measured and diluted (Section 3.2).'],
      ['random', 'Random', 'Households dealt at random, mixing strata, in proportion to the shares. For the first round, or a round where enumerator effects must be estimated.'],
      ['equal_split', 'Equal split', 'Consecutive blocks of the list in a chosen order, sizes differing by at most one. Enumerator and area effects then cannot be told apart.'],
      ['share_of_total', 'Share of total', 'Like equal split or random, with the shares in step 5 adding up to 100%: part-time or new enumerators.'],
      ['manual', 'Manual', 'A list of hhid and enumerator_id. Households without one, and unknown IDs, are flagged.'],
    ];
    const ruleCard = `<section class="lcard"><h3>6 · Assignment rule</h3>
      ${rules.map(([k, l, t]) => `<label class="rule"><input type="radio" name="lrule" data-lrule="${k}" ${st.rule.name === k ? 'checked' : ''}> <b>${l}</b><span class="muted small">${t}</span></label>`).join('')}
      ${st.rule.name === 'keep_same' ? `<div class="row3"><label>Rotation share this round (%) <input type="number" min="0" max="100" step="1" data-lset="rule.rotation_share" data-type="pct" value="${st.rule.rotation_share === null ? '' : Math.round(st.rule.rotation_share * 100)}" placeholder="no default"></label></div>
        <p class="muted small">No default: the handbook says the size of the share "is a judgment, not an estimate from these data". Hard to reach: not interviewed last round although it received the full dial cap, or its enumerator asked for a switch. The switch is a step the handbook has not tested; the reason codes let the program test it. Households new to the panel are dealt at random.</p>` : ''}
      ${/split|share/.test(st.rule.name) ? `<div class="row3"><label>Order of the list <select data-lset="rule.order_by">${['psu', 'stratum', 'language', 'hhid'].map(k => `<option ${st.rule.order_by === k ? 'selected' : ''}>${k}</option>`).join('')}</select></label>${st.rule.name === 'share_of_total' ? `<label>Method <select data-lset="rule.method"><option value="blocks" ${st.rule.method === 'blocks' ? 'selected' : ''}>consecutive blocks</option><option value="random" ${st.rule.method !== 'blocks' ? 'selected' : ''}>random dealing</option></select></label>` : ''}</div>` : ''}
      ${st.rule.name === 'manual' ? `<label class="btn subtle">${st.inputs.manual ? 'Replace' : 'Open'} the manual list<input type="file" id="lf-manual" accept=".csv,.xlsx"></label>${st.inputs.manual ? ` <span class="muted">${esc(st.inputs.manual.name)}</span>` : ''}` : ''}
      <div class="row3"><label>Seed <input type="number" data-lset="rule.seed" data-type="int" value="${esc(st.rule.seed)}"></label><span class="muted small">Written into every file, so the same inputs and seed give the same assignment.</span></div>
      ${ui.stale && !st.plan ? '<p class="alert warn">A setting changed after the rule was applied, so the assignment and any files written from it are set aside. Apply the rule again, then write the files again.</p>' : ''}${errList(ui.errors)}
      <div class="btnrow"><button class="primary" data-lact="apply">Apply the rule</button></div></section>`;
    return hhCard + histCard + replCard + calCard + teamCard + ruleCard + (st.plan ? previewCard() : '');
  }
  function previewCard() {
    const p = st.plan, d = derived(), inp = inputFor();
    const loads = L.loads(inp, p.out, p.sums);
    const reasons = ['keep', 'rotation', 'switch_hard_to_reach', 'enumerator_unavailable', 'new', 'rule', 'manual', 'capacity'];
    const cnt = {};
    for (const x of p.out.values()) { const k = `${x.enumerator_id}|${x.reason}`; cnt[k] = (cnt[k] || 0) + 1; }
    const enums = st.team.filter(t => t.available).map(t => t.id);
    const used = reasons.filter(r => enums.some(e => cnt[`${e}|${r}`]));
    const hh = new Map(d.round.mains.map(h => [h.hhid, h]));
    const strata = [...new Set(d.round.mains.map(h => h.stratum || '–'))].sort();
    const sc = {};
    for (const [id, x] of p.out) { const k = `${x.enumerator_id}|${hh.get(id).stratum || '–'}`; sc[k] = (sc[k] || 0) + 1; }
    const R_ = { keep: 'kept', rotation: 'rotation', switch_hard_to_reach: 'hard to reach', enumerator_unavailable: 'enumerator away', new: 'new', manual: 'by hand', capacity: 'capacity',
      rule: st.rule.name === 'equal_split' || (st.rule.name === 'share_of_total' && st.rule.method === 'blocks') ? 'by block of the list' : 'dealt at random' };
    const outside = loads.filter(l => Math.abs(l.departure) > st.margin);
    const rows = [...p.out.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1));
    const filt = ui.hhEnum ? rows.filter(([, x]) => x.enumerator_id === ui.hhEnum) : rows;
    return `<section class="lcard"><h3>7 · Check the assignment before any file is written</h3>
      ${list(p.notes)}${list(p.warnings)}
      <table class="grid small"><thead><tr><th>Enumerator</th>${used.map(r => `<th class="num">${R_[r]}</th>`).join('')}<th class="num">Households</th>${strata.map(s => `<th class="num">stratum ${esc(s)}</th>`).join('')}<th class="num">Expected dials</th><th class="num">Against target</th></tr></thead><tbody>
      ${loads.map(l => `<tr><td class="id">${esc(l.id)}</td>${used.map(r => `<td class="num">${cnt[`${l.id}|${r}`] || ''}</td>`).join('')}<td class="num"><b>${l.households}</b></td>${strata.map(s => `<td class="num">${sc[`${l.id}|${s}`] || ''}</td>`).join('')}<td class="num">${nm(l.dials)}</td><td class="num ${Math.abs(l.departure) > st.margin ? 'warn' : ''}">${l.departure >= 0 ? '+' : ''}${pc(l.departure)}</td></tr>`).join('')}
      </tbody></table>
      <p class="muted small">Each row counts the households the enumerator receives this round, by reason: ${st.rule.name === 'keep_same' ? 'kept from last round, moved by rotation, switched as hard to reach, moved from an enumerator who is away, new to the panel' : 'kept with the same enumerator, moved by this round’s rule, moved by hand, and new to the panel'}. Expected dials use each household's dials last round (the mean for households without one). Target: the enumerator's share of the expected dials.</p>
      <div class="row3"><label>Margin (%) <input class="tiny" type="number" min="0" max="100" data-lset="margin" data-type="pct" value="${Math.round(st.margin * 100)}"></label>
        ${outside.length ? `<span class="warn">${R.plural(outside.length, 'enumerator')} ${outside.length === 1 ? 'is' : 'are'} outside the margin.</span> <button class="subtle" data-lact="balance">Move kept households at random to balance (reason: capacity)</button>` : '<span class="muted">Every load is within the margin.</span>'}</div>
      ${p.best && p.best.length ? `<p class="muted small">Households without a last interview are planned at the program's best hours from earlier rounds: ${p.best.map(h => p2(h) + ':00').join(', ')} (Section 3.5.1).</p>` : ''}
      <details><summary>Households (${p.out.size}): move one by hand</summary>
        <div class="row3"><label>Enumerator <select data-lset="__hhEnum"><option value="">all</option>${enums.map(e => `<option ${ui.hhEnum === e ? 'selected' : ''}>${esc(e)}</option>`).join('')}</select></label></div>
        <table class="grid small"><thead><tr><th>Household</th><th>Stratum</th><th>Enumerator</th><th>Reason</th><th>Before</th><th>First dial</th><th class="num">Replacements</th></tr></thead><tbody>
        ${filt.slice(0, 400).map(([id, x]) => { const pl = p.plans.get(id) || {}; return `<tr><td class="id">${esc(id)}</td><td>${esc(hh.get(id).stratum || '')}</td><td><select data-lmove="${esc(id)}">${enums.map(e => `<option ${x.enumerator_id === e ? 'selected' : ''}>${esc(e)}</option>`).join('')}</select></td><td>${esc(R_[x.reason] || x.reason)}</td><td>${esc(x.previous_enumerator || '')}</td><td>${esc(pl.first_dial_date || '')} ${Number.isInteger(pl.target_hour) ? p2(pl.target_hour) + ':00' : ''}</td><td class="num">${(d.avail.get(id) || []).length || ''}</td></tr>`; }).join('')}
        </tbody></table>${filt.length > 400 ? `<p class="muted">First 400 of ${filt.length} shown.</p>` : ''}</details>
      </section>
      <section class="lcard"><h3>8 · Write the files</h3>
      <p>One assignment file per enumerator, holding only that enumerator's households and their replacements, a manifest of the round (IDs only, for the merge) and the <code>calendar.csv</code> row for the round template.</p>
      <label class="inline"><input type="checkbox" data-lset="protect" data-type="bool" ${st.protect ? 'checked' : ''}> Protect each assignment file with its own passphrase. The tool makes the passphrases and shows them once; give each enumerator theirs privately.</label>
      ${ui.busy ? `<p class="alert info">${esc(ui.busy)}</p>` : ''}
      ${outside.length ? `<p class="warn small">${outside.map(l => `${esc(l.id)} ${l.departure >= 0 ? '+' : ''}${pc(l.departure)}`).join(', ')}: outside the ${pc(st.margin)} margin (step 7). The files can still be written as they are.</p>` : ''}
      <div class="btnrow"><button class="primary" data-lact="write">Write the files</button></div>
      ${ui.ready ? readyList() : ''}</section>`;
  }
  function readyList() {
    const f = ui.ready;
    return `<div class="alert info"><b>${f.length} files are ready.</b> Put each assignment file in that enumerator's own folder, never in the common folder. The manifest and calendar row stay with you.</div>
      ${ui.passphrases ? `<div class="alert warn"><b>Passphrases, shown once.</b> Copy them now or download the list; they are not saved anywhere.
        <table class="grid small"><tbody>${ui.passphrases.map(p => `<tr><td class="id">${esc(p.enumerator_id)}</td><td>${esc(p.file)}</td><td><code>${esc(p.passphrase)}</code></td></tr>`).join('')}</tbody></table>
        <button class="subtle" data-lact="dlpass">Download the passphrase list</button></div>` : ''}
      <div class="btnrow"><button class="primary" data-lact="saveall">${window.showDirectoryPicker ? 'Save all into a folder' : 'Download all'}</button>${window.showDirectoryPicker ? '<button class="subtle" data-lact="dlall">Download all</button>' : ''}</div>
      <ul class="files">${f.map((x, i) => `<li><button class="link" data-lact="dlone" data-i="${i}">${esc(x.name)}</button>${x.n !== undefined ? ` <span class="muted">${x.n} households${x.protected ? ', protected' : ''}</span>` : ''}</li>`).join('')}</ul>`;
  }

  // ---- Import logs ----
  function importTab() {
    if (!st.manifest) {
      return `<section class="lcard"><h3>The round's manifest</h3><p>The merge checks every export against the round's manifest (who has which households). Write the files on the Prepare tab, or open the manifest you wrote earlier. Then add the enumerators' exports from the common folder here.</p>
        <label class="btn">Open a round manifest<input type="file" id="lf-manifest" accept=".json"></label></section>`;
    }
    const g = merged(), G = g.G;
    if (!st.imports.length) {
      return `<section class="lcard"><h3>Add exports from the common folder</h3>
        <p class="muted">Each enumerator's <code>{enumerator_id}_{date}.json</code> and <code>.csv</code>, in one batch; the newest export of each enumerator is used. Contacts files go here too, but they never belong in the common folder.</p>
        <label class="btn">Add files<input type="file" id="lf-imports" accept=".json,.csv" multiple></label>
        <p class="muted">No export added yet. The merge checks every file against this round's manifest (${R.plural(st.manifest.households.length, 'household')}, ${R.plural(st.manifest.enumerators.length, 'enumerator')}); an enumerator whose export has not arrived is reported once you add the others.</p></section>`;
    }
    const open = G.issues.filter(i => i.status === 'open' && i.severity === 'action');
    const sealed = st.imports.map((f, i) => ({ f, i, rec: g.recs[i] })).filter(x => x.rec.kind === 'sealed' && x.rec.contains === R.SCHEMA.contacts);
    return `<section class="lcard"><h3>Add exports from the common folder</h3>
      <p class="muted">Each enumerator's <code>{enumerator_id}_{date}.json</code> and <code>.csv</code>, in one batch; the newest export of each enumerator is used. Contacts files go here too, but they never belong in the common folder.</p>
      <label class="btn">Add files<input type="file" id="lf-imports" accept=".json,.csv" multiple></label>
      ${st.imports.length ? ` <button class="link" data-lact="clearimports">Remove all ${st.imports.length} files</button>` : ''}
      ${sealed.map(x => `<div class="alert info">${esc(x.f.name)} is a protected contacts file. <button class="subtle" data-lact="opensealed" data-i="${x.i}">Open with its passphrase</button></div>`).join('')}</section>
      ${open.length ? `<section class="lcard"><h3>Needs your decision <span class="count warn">${open.length}</span></h3>${open.map(issueCard).join('')}</section>` : (st.imports.length ? '<p class="alert ok">No merge question is open.</p>' : '')}
      ${G.files.length ? `<section class="lcard"><h3>Files</h3><table class="grid small"><thead><tr><th>File</th><th>Kind</th><th>Enumerator</th><th>Exported</th><th class="num">Events or rows</th><th>Used</th></tr></thead><tbody>
        ${G.files.map(f => `<tr><td>${esc(f.name)}</td><td>${esc(f.kind)}</td><td class="id">${esc(f.enumerator_id)}</td><td>${esc((f.exported_at || '').slice(0, 16).replace('T', ' '))}</td><td class="num">${f.count || ''}</td><td>${esc(f.use)}</td></tr>`).join('')}</tbody></table></section>` : ''}
      ${G.issues.length ? `<section class="lcard"><h3>Merge report</h3><p class="muted">Every situation the merge found, the rule applied and, where you decided, who decided and when.</p>
        <table class="grid small"><thead><tr><th>What</th><th>Enumerator</th><th>Household</th><th>Detail</th><th>Status</th></tr></thead><tbody>
        ${G.issues.map(i => `<tr><td>${esc(i.type.replace(/_/g, ' '))}</td><td class="id">${esc(i.enumerator || '')}</td><td class="id">${esc(i.hhid || '')}</td><td>${esc(i.detail)}</td><td>${i.severity === 'info' ? 'noted' : i.status === 'open' ? '<b class="warn">open</b>' : `${esc(decisionLabel(i))} · ${esc(i.by)} ${esc((i.at || '').slice(0, 16).replace('T', ' '))}`}</td></tr>`).join('')}</tbody></table>
        <button class="subtle" data-lact="export" data-what="report">Download the merge report</button></section>` : ''}
      ${G.updates.length ? `<section class="lcard"><h3>New or corrected phone numbers</h3><p>${R.plural(G.updates.length, 'update')} from the contacts files${G.updates.some(u => !u.digest_ok) ? ', some not matching the call log' : ''}. Move them into the household list for the next round.</p>
        <button class="subtle" data-lact="export" data-what="contacts">Download contact updates</button> <span class="tag warn">has phone numbers</span></section>` : ''}`;
  }
  function issueCard(i) {
    const choices = i.choices || [{ value: 'acknowledged', label: 'Noted' }];
    return `<div class="issue"><div><b>${esc(i.type.replace(/_/g, ' '))}</b>${i.enumerator ? ` · ${esc(i.enumerator)}` : ''}${i.hhid ? ` · <span class="id">${esc(i.hhid)}</span>` : ''}${i.file ? ` · <span class="muted">${esc(i.file)}</span>` : ''}</div>
      <div>${esc(i.detail)}</div>
      <div class="btnrow">${choices.map(c => `<button class="subtle" data-lact="resolve" data-key="${esc(i.key)}" data-v="${esc(c.value)}">${esc(c.label)}</button>`).join('')}
        <input class="note" data-note-for="${esc(i.key)}" placeholder="note (optional)"></div></div>`;
  }

  // ---- Progress ----
  function progressTab() {
    if (!st.manifest) return '<p class="muted">Write the round’s files or open its manifest first (Prepare or Import tab).</p>';
    const g = merged(), P = g.P, M = st.manifest;
    const cols = [['households', 'Households'], ['complete', 'Complete'], ['in_progress', 'In progress'], ['not_started', 'Not started'], ['released', 'Released'], ['replaced', 'Replaced'], ['remove_requested', 'Removal requested'], ['conflict', 'Two completes'], ['not_reported', 'Not reported'], ['dials', 'Dials'], ['enumerator_days', 'Enumerator-days']];
    const always = new Set(['households', 'complete', 'in_progress', 'not_started', 'dials', 'enumerator_days']);
    const shownCols = cols.filter(([k]) => always.has(k) || P.list.some(r => r[k]));
    const row = r => `<tr${r.enumerator_id === 'All' ? ' class="total"' : ''}><td class="id">${esc(r.enumerator_id)}${r.enumerator_id === 'All' ? '' : `<div class="muted small nowrap">${r.last_export ? 'export ' + esc(r.last_export.slice(5, 16).replace('T', ' ')) : 'no export yet'}</div>`}</td>${shownCols.map(([k]) => `<td class="num">${r[k] || (k === 'households' ? 0 : '')}</td>`).join('')}<td class="num">${pc(r.households ? r.complete / r.households : null)}</td><td class="num">${nm(r.completes_per_day, 1)}</td></tr>`;
    const days = P.days, max = Math.max(1, ...days.map(x => x.cumulative)), W = 640, H = 160, bw = W / days.length;
    const today = R.partsIn(R.now(), M.calendar.time_zone).key;
    const chart = `<svg viewBox="0 0 ${W} ${H + 24}" class="chart" role="img" aria-label="Completes by day of the window, cumulative">
      ${days.map((x, i) => `<rect x="${i * bw + 1}" y="${H - x.cumulative / max * H}" width="${Math.max(1, bw - 2)}" height="${x.cumulative / max * H}" class="${x.day > today ? 'future' : 'bar'}"><title>${x.day}: ${x.completes} completes, ${x.cumulative} so far</title></rect>`).join('')}
      <text x="0" y="${H + 16}" class="axis">${esc(days[0].day)}</text><text x="${W}" y="${H + 16}" class="axis" text-anchor="end">${esc(days[days.length - 1].day)}</text>
      <text x="0" y="12" class="axis">${max} completes</text></svg>`;
    const C = [...g.C.values()];
    const states = Object.keys(L.STATES);
    let f = C;
    if (ui.hhFilter !== 'all') f = f.filter(c => c.state === ui.hhFilter);
    if (ui.hhEnum) f = f.filter(c => c.enumerator_id === ui.hhEnum);
    f.sort((a, b) => (a.hhid < b.hhid ? -1 : 1));
    return `<section class="lcard"><h3>Team</h3><p class="muted small">Households: those assigned, plus any replacement brought in this round (the household it replaces stays in the count, as Replaced). Not reported: households of an enumerator whose export has not arrived, counted apart from completes and misses. Completes per enumerator-day as in Box 3.0, from this round's dials. Columns with nothing to count are left out.</p>
      <div class="tablewrap"><table class="grid small"><thead><tr><th>Enumerator</th>${shownCols.map(([, l]) => `<th class="num">${l}</th>`).join('')}<th class="num">Share complete</th><th class="num">Completes per enumerator-day</th></tr></thead>
      <tbody>${P.list.map(row).join('')}${row(P.total)}</tbody></table></div></section>
      <section class="lcard"><h3>Completes over the window</h3>${chart}
      <table class="grid small"><thead><tr><th>Stratum</th><th class="num">Households</th><th class="num">Complete</th><th class="num">Share</th></tr></thead><tbody>${P.strata.map(s => `<tr><td>${esc(s.stratum)}</td><td class="num">${s.households}</td><td class="num">${s.complete}</td><td class="num">${pc(s.households ? s.complete / s.households : null)}</td></tr>`).join('')}</tbody></table></section>
      <section class="lcard"><h3>Households</h3>
      <div class="filters">${['all'].concat(states).map(k => `<button class="chip ${ui.hhFilter === k ? 'on' : ''}" data-lact="hhfilter" data-f="${k}">${k === 'all' ? 'All' : L.STATES[k]} <span class="count">${k === 'all' ? C.length : C.filter(c => c.state === k).length}</span></button>`).join('')}
        <select data-lset="__hhEnum"><option value="">every enumerator</option>${M.enumerators.map(e => `<option ${ui.hhEnum === e.enumerator_id ? 'selected' : ''}>${esc(e.enumerator_id)}</option>`).join('')}</select></div>
      <table class="grid small"><thead><tr><th>Household</th><th>Enumerator</th><th>Reason</th><th>State</th><th class="num">Dials</th><th>Last result</th><th>Complete on</th></tr></thead><tbody>
      ${f.slice(0, 500).map(c => { const last = c.dials[c.dials.length - 1]; return `<tr><td class="id">${esc(c.hhid)}${c.replaces ? ` <span class="tag">replaces ${esc(c.replaces)}</span>` : ''}</td><td class="id">${esc(c.enumerator_id)}</td><td>${esc(REASON_WORD[c.reason] || (c.reason || '').replace(/_/g, ' '))}</td><td><span class="st st-${c.state}">${esc(L.STATES[c.state])}</span>${c.short ? ' <span class="tag warn">complete under 3 min</span>' : ''}</td><td class="num">${c.n}</td><td>${last ? esc(sh().statusLabel(last.status)) : ''}</td><td>${c.complete ? esc(c.complete.ts.slice(0, 16).replace('T', ' ')) : ''}</td></tr>`; }).join('')}
      </tbody></table>${f.length > 500 ? `<p class="muted">First 500 of ${f.length}.</p>` : ''}</section>`;
  }

  // ---- Call log ----
  function callLogTab() {
    if (!st.manifest) return '<p class="muted">Write the round’s files or open its manifest first.</p>';
    const g = merged(), G = g.G;
    let d = G.dials;
    if (ui.logEnum) d = d.filter(x => x.source === ui.logEnum);
    if (ui.logStatus) d = d.filter(x => x.status === ui.logStatus);
    if (ui.logQ) d = d.filter(x => x.hhid.toLowerCase().includes(ui.logQ.toLowerCase()));
    const show = d.slice(0, 300 + ui.logMore);
    const open = G.issues.filter(i => i.status === 'open' && i.severity === 'action').length;
    return `<section class="lcard"><h3>The round's files</h3>
      ${open ? `<p class="alert warn">${R.plural(open, 'merge question')} ${open === 1 ? 'is' : 'are'} still open (Import tab). The files below follow the current state: dials you left out are not in them.</p>` : ''}
      <div class="btnrow"><button class="primary" data-lact="export" data-what="calls">Merged call log (CSV)</button><button class="subtle" data-lact="export" data-what="actions">Actions (CSV)</button>
        <button class="subtle" data-lact="export" data-what="interviews">interviews.csv</button><button class="subtle" data-lact="export" data-what="outcomes">outcome_codes.csv</button>
        <button class="subtle" data-lact="export" data-what="calendar">calendar.csv</button><button class="subtle" data-lact="export" data-what="manifest">Manifest</button></div>
      <p class="muted small">The merged call log has the harmonized dial-table columns of the enumerators' exports, the dial number counted per household across enumerators; the handbook's analysis scripts read it as a program's log, and the leader view reads it back as an earlier round. <code>interviews.csv</code> has one row per household for the Section 4.2 round template; <code>outcome_codes.csv</code> lists the codes and meanings to copy into the template's configuration.</p></section>
      <section class="lcard"><h3>Merged call log <span class="count">${G.dials.length}</span></h3>
      <div class="filters"><select data-lset="__logEnum"><option value="">every enumerator</option>${[...G.perEnum.keys()].sort().map(e => `<option ${ui.logEnum === e ? 'selected' : ''}>${esc(e)}</option>`).join('')}</select>
        <select data-lset="__logStatus"><option value="">every result</option>${R.STATUS.map(s => `<option value="${s.code}" ${ui.logStatus === s.code ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select>
        <input type="search" data-lset="__logQ" value="${esc(ui.logQ)}" placeholder="household ID"></div>
      <table class="grid small"><thead><tr><th>Household</th><th class="num">Dial</th><th>Start</th><th class="num">Minutes</th><th>Result</th><th>Enumerator</th><th>Number</th><th>Action</th><th>Logged</th></tr></thead><tbody>
      ${show.map(x => `<tr><td class="id">${esc(x.hhid)}</td><td class="num">${x.attempt}</td><td>${esc(R.wallFromISO(x.ts).slice(0, 16))}</td><td class="num">${nm(x.dur_min, 1)}</td><td>${esc(sh().statusLabel(x.status))}${x.corrected ? ' <span class="tag">corrected</span>' : ''}</td><td class="id">${esc(x.operator || x.source)}</td><td>${x.phone_slot || ''}</td><td>${esc(x.action || '')}</td><td>${esc(x.logged_by)} ${esc((x.logged_at || '').slice(5, 16).replace('T', ' '))}</td></tr>`).join('')}
      </tbody></table>${d.length > show.length ? `<button class="subtle" data-lact="logmore">Show 300 more (${d.length - show.length} left)</button>` : ''}</section>`;
  }

  // ---- Analytics ----
  const bars = (rows, opts) => {
    const W = 560, H = 140, n = rows.length || 1, bw = W / n, max = opts.max || Math.max(0.01, ...rows.map(r => r.v || 0));
    return `<svg viewBox="0 0 ${W} ${H + 36}" class="chart" role="img" aria-label="${esc(opts.label)}">${rows.map((r, i) => {
      const h = r.v === null || r.v === undefined ? 0 : r.v / max * H;
      const lab = r.v === null || r.v === undefined ? '' : (opts.fmt || (v => pc(v)))(r.v);
      return `<rect x="${i * bw + 2}" y="${H - h + 14}" width="${Math.max(1, bw - 4)}" height="${h}" class="${r.v === null || r.v === undefined ? 'none' : r.cls || 'bar'}"><title>${esc(r.t)}</title></rect>`
        + `<text x="${i * bw + bw / 2}" y="${H - h + 10}" class="axis val" text-anchor="middle">${esc(lab)}</text><text x="${i * bw + bw / 2}" y="${H + 28}" class="axis" text-anchor="middle">${esc(r.x)}</text>`;
    }).join('')}</svg>`;
  };
  function analyticsTab() {
    const d = derived();
    if (!d.hist.rounds.length && !st.manifest) return '<p class="muted">Open earlier rounds (Prepare tab, step 2) or import this round’s exports to see the analytics.</p>';
    const a = analytics(), s34 = a.s34;
    // where each round's figures come from, with runs of rounds grouped: "rounds 1–4 from the call log"
    const runs = [];
    [...a.source].sort((x, y) => x[0] - y[0]).forEach(([r, s_]) => { const l = runs[runs.length - 1]; if (l && l.s === s_ && l.to === r - 1) l.to = r; else runs.push({ from: r, to: r, s: s_ }); });
    const src = runs.map(x => `${x.from === x.to ? `round ${x.from}` : `rounds ${x.from}–${x.to}`} from the ${x.s}`).join('; ');
    const part = (title, defn, body) => `<section class="lcard"><h3>${title}</h3><p class="muted small">${defn}</p>${body}</section>`;
    // attrition
    const cont = s34.continuation || [];
    const att = part('Continuation and retention', `Continuation (Box 2.0): the share of a round's respondents interviewed again in the next round. Interviewed = ${d.hist.interviews.size ? 'interview records where loaded, otherwise ' : ''}a case completed by the handbook's rule. Closed rounds only (${a.closed.join(', ') || 'none yet'}); this round is still open. Data: ${esc(src)}.`,
      !a.closed.length ? '<p class="muted">Not yet: these measures need closed rounds. To see them now, open earlier rounds on the Prepare tab (step 2); this round’s figures follow when it closes.</p>' : `${cont.length ? `<table class="grid small"><thead><tr><th>Round</th><th class="num">Last round's respondents</th><th class="num">Continuation</th><th class="num">Missed, back later</th></tr></thead><tbody>${cont.map(x => `<tr><td>${x.from} → ${x.round}</td><td class="num">${x.base}</td><td class="num">${pc(x.share, 1)}</td><td class="num">${pc(x.back_later, 1)}</td></tr>`).join('')}
        ${a.sofar ? `<tr class="total"><td>${a.cur - 1} → ${a.cur}, so far</td><td class="num">${a.sofar.base}</td><td class="num">${pc(a.sofar.share, 1)}</td><td class="num muted">open</td></tr>` : ''}</tbody></table>
        <p>Median continuation <b>${pc(s34.continuation_median, 1)}</b>; lowest round <b>${pc(s34.continuation_min, 1)}</b>.</p>` : '<p class="muted">Two consecutive closed rounds are needed.</p>'}
        <h4>The first-round sample, round by round (Box 2.0, Section 2.4.4)</h4><p class="muted small">Households interviewed in round ${s34.rounds && s34.rounds[0]}, interviewed again in each later round, without returns.</p>
        ${(s34.retention_first || []).length ? bars(s34.retention_first.map(x => ({ x: 'R' + x.round, v: x.share, t: `round ${x.round}: ${pc(x.share, 1)} of ${x.base}` })), { label: 'Retention of the first-round sample', max: 1 }) : ''}
        <h4>Retention by rounds since joining (Section 3.4.3)</h4><p class="muted small">Pooled over entry cohorts: interviewed k rounds after joining (strict), or then or in one of the next three rounds (with returns). Cohorts count only when round joining + k + 3 is in the data, so the last three closed rounds cannot yet be judged.</p>
        ${s34.retention && s34.retention.length ? `<table class="grid small"><thead><tr><th>k</th><th class="num">Households</th><th class="num">Interviewed in round k</th><th class="num">Then or within three rounds</th></tr></thead><tbody>${s34.retention.map(x => `<tr><td>${x.k}</td><td class="num">${x.n}</td><td class="num">${ci(x.share)}</td><td class="num">${ci(x.still)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">Not yet: fewer than 10 households have k + 3 later rounds in the data.</p>'}
        <h4>By entry cohort</h4><table class="grid small"><thead><tr><th>Joined in round</th><th class="num">Households</th>${(s34.rounds || []).slice(1).map(r => `<th class="num">R${r}</th>`).join('')}</tr></thead><tbody>
        ${(s34.cohorts || []).map(c => `<tr><td>${c.entry}${c.original ? '' : ' <span class="tag">later entrants</span>'}</td><td class="num">${c.n}</td>${(s34.rounds || []).slice(1).map(r => { const x = c.by_round.find(y => y.round === r); return `<td class="num">${x ? (x.share === null ? '<span class="muted">n&lt;10</span>' : pc(x.share)) : ''}</td>`; }).join('')}</tr>`).join('')}</tbody></table>`);
    const lossB = (s34.loss || []).map(gx => `<tr><td>${gx.group}</td>${['k1', 'k2_6', 'k7_12', 'k13_24'].map(b => `<td class="num">${gx.bands[b].loss ? ci(gx.bands[b].loss) : `<span class="muted">n ${gx.bands[b].n}</span>`}</td>`).join('')}</tr>`).join('');
    const loss = part('Loss by rounds since joining, and returns', 'Loss (Section 3.4.3, Figure 3.4.4): among households interviewed in a round, the share not interviewed in the next, by rounds since joining (1 = the round after joining). Returns: of those, the share interviewed again within three rounds. Only rounds with four later rounds in the data count; cells under 10 are not shown.',
      !a.closed.length ? '<p class="muted">Not yet: loss and returns need closed rounds.</p>' : `${s34.returns && s34.returns.pairs ? `<table class="grid small"><thead><tr><th>Group</th><th class="num">k = 1</th><th class="num">2–6</th><th class="num">7–12</th><th class="num">13–24</th></tr></thead><tbody>${lossB}</tbody></table>` : `<p class="muted">Not yet judgeable: a household interviewed in round r is judged only when rounds r + 1 to r + 4 are all closed${s34.rounds && s34.rounds.length ? `; the first judgeable household-rounds come from round ${s34.rounds[0]} once round ${s34.rounds[0] + 4} has closed` : ''}.</p>`}
       <p>Returns: ${s34.returns && s34.returns.lost ? `<b>${pc(s34.returns.back_within, 1)}</b> of ${s34.returns.lost} households missed the round after an interview were interviewed again within three rounds (${s34.returns.pairs} household-rounds judged).` : 'not yet judgeable: four later rounds are needed.'}</p>
       <p>Recruitment: opening rounds ${(s34.waves && s34.waves.opening.join(', ')) || '–'}${s34.waves && s34.waves.later.length ? `; later wave ${s34.waves.later.join(', ')}` : ''}. Newcomers (median share of a round's interviews, after the first round): ${pc(s34.newcomers_median, 1)}.</p>`);
    // effort (3.3)
    const s33 = (x, label) => x ? `<tr><td>${label}</td><td class="num">${x.pooled.cases}</td><td class="num">${x.pooled.dials}</td><td class="num">${x.pooled.completes}</td><td class="num">${nm(x.pooled.dials_per_complete, 2)}</td><td class="num">${pc(x.pooled.completion_rate, 1)}</td><td class="num">${pc(x.pooled.first_dial_share, 1)}</td><td class="num">${x.pooled.k90 || '–'}</td><td class="num">${nm(x.pooled.median_dials_noncomplete, 1)}</td></tr>` : '';
    const hz = (a.s33c || a.s33n).hazard.slice(0, 15);
    const effort = part('Dials per complete and hazard by dial (Section 3.3.1)', 'Case = a household in a round with at least one dial; complete = the first complete-coded dial of 3 minutes or more, or, as the handbook’s scripts do when there is none, its first complete-coded dial. Dials after the complete are not counted. Hazard at dial k = completes on dial k among cases still pending before it (cells under 10 not shown).',
      `<table class="grid small"><thead><tr><th></th><th class="num">Cases</th><th class="num">Dials</th><th class="num">Completes</th><th class="num">Dials per complete</th><th class="num">Completion</th><th class="num">On the first dial</th><th class="num">Dial reaching 90% of completes</th><th class="num">Median dials if not completed</th></tr></thead>
        <tbody>${s33(a.s33c, 'Closed rounds')}${s33(a.s33n, 'This round so far')}</tbody></table>
       ${a.s33c ? `<table class="grid small"><thead><tr><th>Round</th><th class="num">Cases</th><th class="num">Dials per complete</th><th class="num">Completion</th></tr></thead><tbody>${a.s33c.byRound.map(r => `<tr><td>${r.round}</td><td class="num">${r.cases}</td><td class="num">${nm(r.dials_per_complete, 2)}</td><td class="num">${pc(r.completion_rate, 1)}</td></tr>`).join('')}</tbody></table>` : ''}
       <h4>Hazard by dial, ${a.s33c ? 'closed rounds' : 'this round so far'}</h4>${bars(hz.map(h => ({ x: h.k, v: h.hazard, t: `dial ${h.k}: ${h.completes} of ${h.at_risk} pending cases completed` + (h.hazard === null ? ' (too few)' : ` (${pc(h.hazard, 1)})`) })), { label: 'Hazard by dial', max: 1 })}
       ${a.s33c && a.s33c.missed.newly_missed ? `<h4>Missed households (Section 3.3.5)</h4><p>Of ${a.s33c.missed.newly_missed} households interviewed one round, dialed and not completed in the next, ${pc(a.s33c.missed.redialled && a.s33c.missed.redialled.p)} were dialed again the round after, and ${a.s33c.missed.back_given_redial ? pc(a.s33c.missed.back_given_redial.p) : '– (fewer than 10 redialed)'} of those were completed: missed is not lost.</p>` : ''}`);
    // productivity (3.1)
    const p31 = (x, label) => x ? `<tr><td>${label}</td><td class="num">${nm(x.pooled.completes_per_day, 2)}</td><td class="num">${nm(x.pooled.minutes_per_day, 0)}</td><td class="num">${nm(x.pooled.minutes_per_complete, 1)}</td><td class="num">${nm(x.pooled.interview_minutes_mean, 1)}</td><td class="num">${nm(x.pooled.failed_minutes_per_complete, 1)}</td><td class="num">${pc(x.pooled.attendance)}</td><td class="num">${nm(x.pooled.fieldwork_days, 0)}</td><td class="num">${nm(x.pooled.enumerators, 0)}</td></tr>` : '';
    const per = a.s31n ? a.s31n.perEnum : [];
    const prod = part('Completes per enumerator-day, dial minutes and attendance (Section 3.1)', 'Enumerator-day: an enumerator with at least one dial on a date. Dial minutes: durations below 0 or above 120 minutes replaced by the median of the same kind of dial. Attendance: enumerator-days ÷ (enumerators × fieldwork days), median over rounds. The handbook asks for these every round.',
      `<table class="grid small"><thead><tr><th></th><th class="num">Completes per enumerator-day</th><th class="num">Dial minutes per day</th><th class="num">Dial minutes per complete</th><th class="num">Interview minutes</th><th class="num">Failed-dial minutes per complete</th><th class="num">Attendance</th><th class="num">Fieldwork days</th><th class="num">Enumerators</th></tr></thead><tbody>${p31(a.s31c, 'Closed rounds')}${p31(a.s31n, 'This round so far')}</tbody></table>
       ${per.length ? `<h4>This round, by enumerator</h4><table class="grid small"><thead><tr><th>Enumerator</th><th class="num">Enumerator-days</th><th class="num">Completes</th><th class="num">Completes per day</th><th class="num">Dials per day</th><th class="num">Dial minutes per day</th></tr></thead><tbody>${per.map(x => `<tr><td class="id">${esc(x.op)}</td><td class="num">${x.enumerator_days}</td><td class="num">${x.completes}</td><td class="num">${nm(x.completes_per_day, 2)}</td><td class="num">${nm(x.dials_per_day, 1)}</td><td class="num">${nm(x.minutes_per_day, 0)}</td></tr>`).join('')}</tbody></table>` : ''}`);
    // timing (3.5)
    const t35 = a.s35c || a.s35n;
    const timing = part('When calls succeed (Section 3.5)', 'Success: the dial on which the interview took place. Hours with at least 50 dials; best and busiest hours among those with at least 2% of dials, success weighted by dials. Hours are the call system’s local clock.',
      `${bars(t35.hours.map(h => ({ x: h.hour, v: h.success ? h.success.p : null, t: `${p2(h.hour)}:00: ${h.n} dials` + (h.success ? `, ${pc(h.success.p, 1)} success` : ' (fewer than 50)') })), { label: 'Success by hour' })}
       <p>Best hours ${t35.best.hours.map(h => p2(h) + ':00').join(', ') || '–'}: <b>${pc(t35.best.success, 1)}</b>; busiest hours ${t35.busy.hours.map(h => p2(h) + ':00').join(', ') || '–'}: <b>${pc(t35.busy.success, 1)}</b>. Dials at 18:00 or later: ${pc(t35.evening_share, 1)}.</p>
       <table class="grid small"><thead><tr><th></th><th class="num">Share of dials</th><th class="num">Success</th></tr></thead><tbody>${t35.week.map(w => `<tr><td>${({ weekday: 'Monday to Friday', saturday: 'Saturday', sunday: 'Sunday' })[w.group]}</td><td class="num">${pc(w.dial_share, 1)}</td><td class="num">${ci(w.success)}</td></tr>`).join('')}</tbody></table>
       <h4>First dial against the last interview's time (Section 3.5.2)</h4><p class="muted small">Households completed last round: the first dial of the round, by its clock distance from the start of last round's completing dial.</p>
       <table class="grid small"><thead><tr><th></th><th class="num">First dials</th><th class="num">First-dial success</th><th class="num">Completed in the round</th></tr></thead><tbody>${t35.same_time.map(b => `<tr><td>${b.bin}</td><td class="num">${b.n}</td><td class="num">${ci(b.first_dial_success)}</td><td class="num">${ci(b.round_completion)}</td></tr>`).join('')}</tbody></table>
       <h4>Continuity (Section 3.5.3)</h4><p>First dial made by the enumerator who completed last round's interview: <b>${pc(t35.continuity.same_share, 1)}</b> of ${t35.continuity.n} households. Completion: same enumerator ${ci(t35.continuity.same)}; another enumerator ${ci(t35.continuity.different)}.</p>
       <h4>Holidays inside the window (Section 3.5.4)</h4>${t35.holidays.length ? `<table class="grid small"><thead><tr><th>Round</th><th>Date</th><th>Holiday</th><th>Called</th><th class="num">Dials against a typical weekday</th></tr></thead><tbody>${t35.holidays.map(h => `<tr><td>${h.round}</td><td>${esc(h.date)}</td><td>${esc(h.name)}</td><td>${h.called ? 'yes' : 'no'}</td><td class="num">${pc(h.rel_dials)}</td></tr>`).join('')}</tbody></table>
         <p>Success on holidays ${ci(t35.holiday_summary.success_on_holidays)} against other days ${ci(t35.holiday_summary.success_other_days)}. <span class="muted small">Unadjusted: the handbook's figure also adjusts for the round, the tenth of the round, the weekday and the dial number.</span></p>` : '<p class="muted">No public holiday fell inside a fieldwork window (its first and last day excluded).</p>'}
       ${t35.ramadan.contrast !== null ? `<p>Ramadan: evening minus daytime success on Ramadan dates, against other dates: ${pc(t35.ramadan.contrast, 1)} (${t35.ramadan.dates} Ramadan dates).</p>` : ''}
       ${a.s35c && a.s35n ? '<p class="muted small">Pooled over the closed rounds; this round’s figures follow when it closes.</p>' : ''}`);
    const notes = `<p class="muted small">All measures are unweighted, as in the handbook. Interview records can replace call-log completes for the attrition measures when loaded (step 2). ${a.T.fallbacks ? `${R.plural(a.T.fallbacks, 'case')} count as complete only through the scripts' fallback (a complete-coded dial under 3 minutes). ` : ''}${a.T.dropped.clock ? `${R.plural(a.T.dropped.clock, 'dial')} more than 90 days from their round's median date were left out. ` : ''}</p>`;
    return notes + att + loss + effort + prod + timing;
  }

  // ---- Risk lists (leader only) ----
  function riskTab() {
    const r = riskData();
    const intro = `<section class="lcard"><h3>Risk lists, for the leader only</h3>
      <p>Two models, both backtested before use. <b>Dropout risk</b> ranks the households interviewed last round by how likely they are to be missed this round; it was trained on the handbook's six programs with dial logs. <b>Return likelihood</b> ranks the households interviewed two rounds ago and missed last round by how likely they are to come back; it was trained on L2PHL and L2Indo only, the two programs that redial almost every missed household, and it is weak. The model card below gives how well each does.</p>
      <p class="muted small">Tiers are tied to workload: within this round, the top ${pc(r ? r.model.tiers.high : 0.15)} of households by score are high, the next ${pc(r ? r.model.tiers.medium : 0.35)} medium, the rest low.${(window.RTM_RISK && !window.RTM_RISK.tiers.return.includes('medium')) ? ` The return model has two tiers only, high and low: ${mergedWhy()}.` : ''} A tier says how similar households fared; it is never a prediction about one household, and never a reason to drop one (Section 3.3.5). Enumerators never see tiers, and tiers are not written into assignment files; the high dropout tier only moves households earlier in the plan of first dials. Only operational features are used, never demographic ones; the model card below lists them, and those left out on purpose.</p></section>`;
    if (!r) return intro + '<p class="muted">Open earlier rounds on the Prepare tab (step 2): the models need last round’s interviews to score this round’s households.</p>' + `<section class="lcard">${LRISK.cardHTML()}</section>`;
    return intro + riskList('dropout', r) + riskList('return', r) + ownData(r) + `<section class="lcard">${LRISK.cardHTML()}</section>`;
  }
  function riskList(kind, r) {
    const list = r[kind], v = st.risk[kind], cal = calibrated(kind);
    const title = kind === 'dropout' ? `Dropout risk: households interviewed in round ${r.c - 1}` : `Return likelihood: interviewed in round ${r.c - 2}, missed in round ${r.c - 1}`;
    if (!list.length) return `<section class="lcard"><h3>${title}</h3><p class="muted">No household to score: ${kind === 'dropout' ? `round ${r.c - 1} is not in the loaded history` : `rounds ${r.c - 2} and ${r.c - 1} are needed`}.</p></section>`;
    const tiers = r.model.tiers[kind];
    const f = ui['rk_' + kind] || 'high';
    const shown = list.filter(s => f === 'all' || s.tier === f).sort((a, b) => b.lp - a.lp);
    const strata = [...new Set(list.map(s => (r.holder.get(s.row._.hhid) || {}).stratum || '–'))].sort();
    const byStratum = strata.map(st_ => { const g = list.filter(s => ((r.holder.get(s.row._.hhid) || {}).stratum || '–') === st_); return `<tr><td>${esc(st_)}</td>${tiers.map(t => `<td class="num">${g.filter(s => s.tier === t).length}</td>`).join('')}<td class="num">${g.length}</td></tr>`; }).join('');
    const word = kind === 'dropout' ? ['raises the risk', 'lowers the risk'] : ['makes a return more likely', 'makes a return less likely'];
    return `<section class="lcard"><h3>${title}</h3>
      <p>${cal ? `Model in use: <b>${v.kind === 'refit' ? 'refitted' : 'recalibrated'} on this program's own rounds</b>, so each household's chance is shown.` : `Model in use: ${trainedName(r, kind)}. It ranks households, but its chances are not yet calibrated to this program, so each household's score is shown against the round's average score instead. That ratio orders households and is not a chance: the backtests check the ordering, not the ratio. ${ownRounds(r, kind) >= 2 ? 'This program has outcomes from enough rounds to recalibrate it: see “This program’s own data” below.' : 'It can be recalibrated once two rounds have outcomes.'}`}</p>
      <div class="filters">${tiers.concat(['all']).map(t => `<button class="chip ${f === t ? 'on' : ''}" data-lact="rkfilter" data-k="${kind}" data-f="${t}">${t === 'all' ? 'All' : t[0].toUpperCase() + t.slice(1)} <span class="count">${t === 'all' ? list.length : list.filter(s => s.tier === t).length}</span></button>`).join('')}</div>
      <div class="tablewrap"><table class="grid small"><thead><tr><th>Household</th><th>Enumerator</th><th>Tier</th><th>${cal ? 'Chance' : 'Score against the round’s average'}</th><th>What moves the score most</th></tr></thead><tbody>
      ${shown.slice(0, 300).map(s => `<tr><td class="id">${esc(s.row._.hhid)}</td><td class="id">${esc((r.holder.get(s.row._.hhid) || {}).e || '–')}</td><td><span class="tier tier-${s.tier}">${s.tier}</span></td>
        <td>${cal ? esc(chanceText(kind, s.p)) : `${nm(s.relative, 1)} times the average`}</td>
        <td>${LRISK.explain(kind, s).map(x => `${esc(x.text)} <span class="muted">${x.up ? word[0] : word[1]}</span>`).join('<br>')}</td></tr>`).join('')}
      </tbody></table></div>${shown.length > 300 ? `<p class="muted">First 300 of ${shown.length}.</p>` : ''}
      <h4>Tiers by stratum</h4><p class="muted small">So that any concentration in one area is visible.</p>
      <table class="grid small"><thead><tr><th>Stratum</th>${tiers.map(t => `<th class="num">${t}</th>`).join('')}<th class="num">Households</th></tr></thead><tbody>${byStratum}</tbody></table>
      <button class="subtle" data-lact="riskcsv" data-k="${kind}">Download this list (CSV, leader only)</button></section>`;
  }
  // the bundled model, named by what it was trained on: six programs for dropout, two for return
  const NUMW = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];
  const trainedName = (r, kind) => { const k = Object.keys((r.model[kind] || {}).n || {}).length; return `the model as trained on ${NUMW[k] || k} programs`; };
  const ownRounds = (r, kind) => new Set(r.own[kind].map(p => p._.outcome)).size;
  // a 95% interval for an AUC (Hanley and McNeil, 1982), from the number of events and non-events tested
  const aucCI = (a, n1, n0) => {
    const q1 = a / (2 - a), q2 = 2 * a * a / (1 + a);
    const se = Math.sqrt(Math.max(0, (a * (1 - a) + (n1 - 1) * (q1 - a * a) + (n0 - 1) * (q2 - a * a)) / (n1 * n0)));
    return [Math.max(0, a - 1.96 * se), Math.min(1, a + 1.96 * se)];
  };
  // what the own-round backtest says, in words: the ranking first, then the chances
  function verdict(b, kind) {
    const P = b.pooled, C = b.recalibrated, evs = kind === 'dropout' ? 'losses' : 'returns';
    if (!P || !Number.isFinite(P.auc) || !P.events || P.events === P.n) return `No round could be tested yet: each needs at least 10 ${evs} and 10 households without one in the rounds before it.`;
    const [lo, hi] = aucCI(P.auc, P.events, P.n - P.events), iv = `AUC ${nm(P.auc, 2)}, 95% interval ${nm(lo, 2)} to ${nm(hi, 2)}, on ${P.n} household-rounds with ${P.events} ${evs}`;
    if (hi < 0.5) return `<b>The model ranks this program's households worse than chance</b> (${iv}). Do not use its lists for this program; keep the version in use and tell the person who maintains the models.`;
    if (lo <= 0.5) return `<b>Too few outcomes to judge:</b> on this program's own rounds so far, the model's ranking cannot be told from chance (${iv}). Keep the version in use and run the backtest again after the next round.`;
    const recal = !C || C.brier >= P.brier ? `Recalibration does not bring its chances closer to what happened (Brier ${C ? C.brier.toFixed(4) : '–'} against ${P.brier.toFixed(4)}): keep the model as trained.`
      : C.brier >= C.brier_null ? `Recalibrated, its chances are closer to what happened than as trained (Brier ${C.brier.toFixed(4)} against ${P.brier.toFixed(4)}), but no closer than giving every household the average rate (${C.brier_null.toFixed(4)}): use the ranking, not the chances.`
      : `Recalibrated, its chances are closer to what happened than as trained and than giving every household the average rate (Brier ${C.brier.toFixed(4)} against ${P.brier.toFixed(4)} and ${C.brier_null.toFixed(4)}), so the recalibrated version can be used.`;
    return `The model ranks this program's households better than chance (${iv}). ${recal}`;
  }
  function ownData(r) {
    const row = (kind, label) => {
      const pairs = r.own[kind], ev = pairs.reduce((a, p) => a + p._.y, 0), rounds = ownRounds(r, kind);
      const b = ui['bt_' + kind], v = st.risk[kind], evs = kind === 'dropout' ? ['loss', 'losses'] : ['return', 'returns'];
      const line = x => (x ? `<td class="num">${nm(x.auc, 2)}</td><td class="num">${x.brier.toFixed(4)} / ${x.brier_null.toFixed(4)}</td><td class="num">${pc(x.capture_high)}</td><td class="num">${x.n}</td>` : '<td colspan="4" class="muted">not enough own outcomes yet</td>');
      const inUse = `In use: <b>${esc(v.kind === 'pooled' ? trainedName(r, kind) : v.kind === 'recalibrated' ? 'recalibrated on own rounds' : 'refitted on own rounds')}</b>${v.at ? `, since ${esc(v.at.slice(0, 16).replace('T', ' '))} by ${esc(v.by)}` : ''}.`;
      const have = pairs.length ? `${R.plural(pairs.length, 'household-round')} with a known outcome, from ${R.plural(rounds, 'round')}: ${R.plural(ev, evs[0], evs[1])}.` : 'No household-round with a known outcome yet.';
      const can = rounds >= 2 ? ` Enough to recalibrate: run the backtest, and choose the recalibrated version only if it does better. A refit needs about ${LRISK.REFIT_MIN} ${evs[1]}${ev < LRISK.REFIT_MIN ? ` (${ev} so far)` : ''}.`
        : ` Recalibration needs outcomes from two rounds${kind === 'return' ? ' (a return is known three rounds after the miss)' : ''}.`;
      return `<h4>${label}</h4>
        <p>${have}${can} ${inUse}</p>
        ${rounds >= 2 ? `<button class="subtle" data-lact="backtest" data-k="${kind}">Backtest on this program's own rounds</button>` : ''}
        ${b ? `<table class="grid small"><thead><tr><th>Version</th><th class="num">AUC</th><th class="num">Brier / no model</th><th class="num">${kind === 'dropout' ? 'Losses' : 'Returns'} in the high tier</th><th class="num">Household-rounds tested</th><th></th></tr></thead><tbody>
          <tr><td>As trained</td>${line(b.pooled)}<td>${v.kind !== 'pooled' ? `<button class="link" data-lact="usever" data-k="${kind}" data-v="pooled">use</button>` : 'in use'}</td></tr>
          <tr><td>Recalibrated on own rounds</td>${line(b.recalibrated)}<td>${b.recalibrated ? (v.kind !== 'recalibrated' ? `<button class="link" data-lact="usever" data-k="${kind}" data-v="recalibrated">use</button>` : 'in use') : ''}</td></tr>
          <tr><td>Refitted on own rounds</td>${line(b.refit)}<td>${b.refit ? (v.kind !== 'refit' ? `<button class="link" data-lact="usever" data-k="${kind}" data-v="refit">use</button>` : 'in use') : ''}</td></tr>
          </tbody></table><p>${verdict(b, kind)}</p>
          <p class="muted small">Rolling origin: each round is predicted using only the outcomes known before it, ${R.plural(b.steps, 'round')} tested. AUC: the chance that a household with the outcome scores above one without (0.5 is no better than chance). Brier: the mean squared gap between chance and outcome, lower is better; “no model” gives every household the tested rounds' average rate. The version you choose is then fitted on every outcome known now.</p>` : ''}`;
    };
    return `<section class="lcard"><h3>This program's own data</h3><p class="muted small">The models were trained on other programs. As this program's rounds gather outcomes, the tool can recalibrate them (intercept and slope) or refit them on the program alone. Switch only after the backtest shows the change helps.</p>
      ${row('dropout', 'Dropout risk')}${row('return', 'Return likelihood')}</section>`;
  }
  function riskCSV(kind) {
    const r = riskData(), cal = calibrated(kind);
    const rows = r[kind].slice().sort((a, b) => b.lp - a.lp).map(s => {
      const ex = LRISK.explain(kind, s);
      return { model: kind, round: r.c, hhid: s.row._.hhid, enumerator_id: (r.holder.get(s.row._.hhid) || {}).e || '', tier: s.tier,
        relative_to_round_average: s.relative === null ? '' : s.relative.toFixed(2), chance: cal ? s.p.toFixed(3) : '', model_version: st.risk[kind].kind,
        driver_1: ex[0] ? `${ex[0].text} (${ex[0].up ? '+' : '-'})` : '', driver_2: ex[1] ? `${ex[1].text} (${ex[1].up ? '+' : '-'})` : '', driver_3: ex[2] ? `${ex[2].text} (${ex[2].up ? '+' : '-'})` : '' };
    });
    const name = `${st.program}_R${p2(r.c)}_risk_${kind}.csv`;
    sh().download(name, R.toCSV(rows, ['model', 'round', 'hhid', 'enumerator_id', 'tier', 'relative_to_round_average', 'chance', 'model_version', 'driver_1', 'driver_2', 'driver_3']), 'text/csv');
    logEv('exported', { file: name });
  }

  // =================================================================== events
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-lact]');
    if (!el || APP.view !== 'leader') return;
    if (sh().clearWarnings) sh().clearWarnings();
    const a = el.dataset.lact;
    switch (a) {
      case 'start': {
        const f = $('#lstart'), g = n => f.querySelector(`[name="${n}"]`).value.trim();
        if (!g('leader') || !g('program') || !g('country') || !(+g('round') >= 1)) return toast('Fill in your leader ID, the program code, the country and the round.', 'warn');
        newSession({ leader: g('leader'), program: g('program'), country: g('country'), round: +g('round') });
        ui.tab = 'prepare'; render(); break;
      }
      case 'tab': ui.tab = el.dataset.t; render(); break;
      case 'apply': applyRule(); break;
      case 'balance': balance(); break;
      case 'write': writeFiles(); break;
      case 'saveall': saveAllToFolder(ui.ready); break;
      case 'dlall': downloadAll(ui.ready); break;
      case 'dlone': { const f = ui.ready[+el.dataset.i]; sh().download(f.name, f.text, f.name.endsWith('.csv') ? 'text/csv' : 'application/json'); break; }
      case 'dlpass': sh().download(`passphrases_${st.program}_R${p2(st.round)}.csv`, R.toCSV(ui.passphrases, ['enumerator_id', 'file', 'passphrase']), 'text/csv'); break;
      case 'addhol': {
        const dd = ($('#lhol-date') || {}).value, n = ($('#lhol-name') || {}).value || 'day off';
        if (!R.isDateKey(dd)) return toast('Choose the date of the day off.', 'warn');
        st.customHolidays.push({ date: dd, name: n }); st.removedHolidays = st.removedHolidays.filter(x => x !== dd);
        logEv('holiday_added', { date: dd, name: n }); invalidate(); stale(); render(); break;
      }
      case 'delhol': st.removedHolidays.push(el.dataset.d); st.customHolidays = st.customHolidays.filter(h => h.date !== el.dataset.d); logEv('holiday_removed', { date: el.dataset.d }); invalidate(); stale(); render(); break;
      case 'addenum': { const id = ($('#lenum-id') || {}).value.trim(); if (!id || st.team.some(t => t.id === id)) return; st.team.push({ id, available: true, share: st.rule.name === 'share_of_total' ? 0 : 1 }); logEv('enumerator_added', { id }); stale(); render(); break; }
      case 'delenum': { const t = st.team.splice(+el.dataset.i, 1)[0]; logEv('enumerator_removed', { id: t.id }); stale(); render(); break; }
      case 'clearhist': st.inputs.history = []; logEv('history_cleared', {}); invalidate(); stale(); render(); break;
      case 'clearrepl': st.inputs.replacements = null; logEv('replacements_removed', {}); invalidate(); render(); break;
      case 'clearimports': st.imports = []; logEv('imports_cleared', {}); invalidate(); render(); break;
      case 'resolve': resolve(el.dataset.key, el.dataset.v); break;
      case 'opensealed': openSealed(+el.dataset.i); break;
      case 'export': exportFile(el.dataset.what); break;
      case 'hhfilter': ui.hhFilter = el.dataset.f; render(); break;
      case 'logmore': ui.logMore += 300; render(); break;
      case 'rkfilter': ui['rk_' + el.dataset.k] = el.dataset.f; render(); break;
      case 'riskcsv': riskCSV(el.dataset.k); break;
      case 'backtest': { const r = riskData(); ui['bt_' + el.dataset.k] = LRISK.backtest(r.model, r.X, el.dataset.k); logEv('risk_backtest', { model: el.dataset.k }); render(); break; }
      case 'usever': {
        const r = riskData(), k = el.dataset.k, v = LRISK.fitVersion(r.model, r.X, k, el.dataset.v);
        st.risk[k] = Object.assign(v, { at: R.localISO(R.now()), by: st.leader });
        logEv('risk_model_switched', { model: k, version: v.kind, fitted_on: v.fitted_on, events: v.events });
        cache.r = undefined; render(); break;
      }
      case 'save': askSave(); break;
      case 'close': {
        const closeIt = () => { st = null; LV.handle = null; invalidate(); ui.ready = null; ui.passphrases = null; render(); };
        if (!st.unsaved) { sh().confirmModal('Close the leader session', 'Your session is saved.', { okLabel: 'Close' }, closeIt); break; }
        sh().confirmModal('Close the leader session', `${R.plural(st.unsaved, 'change')} ${st.unsaved === 1 ? 'is' : 'are'} not saved. Save the session first, or ${st.unsaved === 1 ? 'it is' : 'they are'} lost.`,
          { okLabel: 'Save, then close', altLabel: 'Close without saving', onAlt: closeIt }, () => askSave(() => { if (!st.unsaved) closeIt(); }));
        break;
      }
    }
  });
  const setPath = (obj, path, v) => { const ks = path.split('.'); let o = obj; ks.slice(0, -1).forEach(k => { o = o[k]; }); o[ks[ks.length - 1]] = v; };
  document.addEventListener('change', async e => {
    const t = e.target;
    if (APP.view !== 'leader') return;
    const file = t.files && t.files[0];
    if (t.id === 'lf-project' && file) {
      let o; try { o = JSON.parse(await sh().readText(file)); } catch (x) { return toast(`${file.name} is not readable JSON.`, 'warn'); }
      if (o && o.schema === R.SCHEMA.sealed) return sh().askPassphrase(file, o, inner => loadProject(inner, file.name));
      return loadProject(o, file.name);
    }
    if (!st) return;
    // a table: CSV as it is, or the first sheet of an Excel workbook (proposal G)
    const table = async f => {
      if (!/\.xlsx$/i.test(f.name)) return { name: f.name, text: await sh().readText(f) };
      try {
        const x = await L.readXlsx(await f.arrayBuffer());
        x.warnings.forEach(w => toast(w, 'warn'));
        return { name: f.name, text: x.text, from_xlsx: 1, warnings: x.warnings };
      } catch (err) { toast(`${f.name}: ${err.message}`, 'warn'); return null; }
    };
    if (t.id === 'lf-hh' && file) { const x = await table(file); if (!x) return; st.inputs.households = x; logEv('household_list_opened', { file: file.name }); invalidate(); stale(); return render(); }
    if (t.id === 'lf-repl' && file) { const x = await table(file); if (!x) return; st.inputs.replacements = x; logEv('replacements_opened', { file: file.name }); invalidate(); stale(); return render(); }
    if (t.id === 'lf-manual' && file) { const x = await table(file); if (!x) return; st.inputs.manual = x; logEv('manual_list_opened', { file: file.name }); invalidate(); stale(); return render(); }
    if (t.id === 'lf-hist' && t.files.length) {
      for (const f of t.files) st.inputs.history.push({ name: f.name, text: await sh().readText(f) });
      logEv('history_opened', { files: t.files.length }); invalidate(); stale(); suggestFromHistory(); invalidate(); return render();
    }
    if (t.id === 'lf-imports' && t.files.length) return addImports([...t.files]);
    if (t.id === 'lf-manifest' && file) {
      let o; try { o = JSON.parse(await sh().readText(file)); } catch (x) { return toast(`${file.name} is not readable JSON.`, 'warn'); }
      if (!L.validManifest(o)) return toast(`${file.name} is not a round manifest.`, 'warn');
      if (o.program !== st.program || +o.round !== +st.round) return toast(`${file.name} is ${o.program} round ${o.round}, not ${st.program} round ${st.round}.`, 'warn');
      if (R.fingerprint(o) !== o.fingerprint) toast('The manifest was changed after it was written (fingerprint). It is used, and the change is logged.', 'warn');
      st.manifest = o; logEv('manifest_opened', { file: file.name, fingerprint_ok: R.fingerprint(o) === o.fingerprint ? 1 : 0 }); invalidate(); return render();
    }
    if (t.dataset.lmap !== undefined) { st.mapping[t.dataset.lmap] = t.value || undefined; logEv('code_mapped', { code: t.dataset.lmap, to: t.value || 'OTHER' }); invalidate(); return render(); }
    if (t.dataset.lwd !== undefined) { const i = +t.dataset.lwd; st.cal.working_weekdays = t.checked ? [...new Set(st.cal.working_weekdays.concat(i))] : st.cal.working_weekdays.filter(x => x !== i); invalidate(); stale(); return render(); }
    if (t.dataset.lhwork !== undefined) { const k = t.dataset.lhwork; st.holidayWorking = t.checked ? st.holidayWorking.concat(k) : st.holidayWorking.filter(x => x !== k); logEv('holiday_working', { date: k, working: t.checked ? 1 : 0 }); stale(); return render(); }
    if (t.dataset.ltrig !== undefined) { const k = t.dataset.ltrig; st.policy.triggers = t.checked ? [...new Set(st.policy.triggers.concat(k))] : st.policy.triggers.filter(x => x !== k); filesStale(); return render(); }
    if (t.dataset.lteam !== undefined) { const x = st.team[+t.dataset.lteam]; if (t.dataset.f === 'available') x.available = t.checked; else x.share = parseFloat(t.value) || 0; logEv('team_changed', { id: x.id, available: x.available ? 1 : 0, share: x.share }); stale(); return render(); }
    if (t.dataset.lrule !== undefined) { st.rule.name = t.dataset.lrule; stale(); return render(); }
    if (t.dataset.lmove !== undefined) return reassign(t.dataset.lmove, t.value);
    if (t.dataset.lset !== undefined) {
      const path = t.dataset.lset, type = t.dataset.type;
      let v = t.type === 'checkbox' ? t.checked : t.value;
      if (type === 'int') v = t.value === '' ? null : parseInt(t.value, 10);
      if (type === 'pct') v = t.value === '' ? null : parseFloat(t.value) / 100;
      if (path.startsWith('__')) { ui[path.slice(2)] = v; return render(); }
      setPath(st, path, v);
      if (/^cal\.|ramadanOn|breakFast|spread/.test(path)) invalidate();
      if (/^(rule\.|cal\.|spread|ramadanOn|breakFast)/.test(path)) stale();
      else if (/^policy\./.test(path)) filesStale();
      return render();
    }
  });
})();
