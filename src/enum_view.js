/* RTM interview tool: the enumerator view (Step 2). Plain DOM, event delegation, no libraries. */
'use strict';
(function () {
  const R = window.RTM;
  const APP = window.APP = {
    view: 'enum', S: null, C: null, tab: 'today', sel: null, call: null, manual: false, correct: null, contact: false,
    unsaved: 0, saveEvery: 10, fileHandle: null, filter: 'open', q: '', day: null, modal: null, toasts: [],
    loadErrors: [], loadWarnings: [], noFSA: false, downloads: [], perfTable: false, showTable: {},
  };
  const $ = (s, r) => (r || document).querySelector(s);
  const esc = s => String(s === undefined || s === null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const WD = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const MONTH = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  const pct = x => (x === null || x === undefined || isNaN(x) ? '–' : (100 * x).toFixed(0) + '%');
  const num = (x, d) => (x === null || x === undefined || isNaN(x) ? '–' : (+x).toFixed(d || 0));

  // ---- time formatting, in the calendar's time zone ----
  const calTZ = () => (APP.S ? R.calendarOf(APP.S.assignment).tz : null);
  const hm = d => { const p = R.partsIn(d, calTZ()); return `${R.p2(p.h)}:${R.p2(p.mi)}`; };
  const dayLabel = k => { const [, m, d] = k.split('-').map(Number); return `${WD[R.weekdayOfKey(k) - 1]} ${d} ${MON[m - 1]}`; };
  const todayKey = () => R.partsIn(R.now(), calTZ()).key;
  const when = d => { const p = R.partsIn(d, calTZ()); return (p.key === todayKey() ? 'today' : dayLabel(p.key)) + ' ' + R.p2(p.h) + ':' + R.p2(p.mi); };
  const isoWhen = iso => (iso ? when(R.parseTS(iso)) : '');
  const toLocalInput = d => { const p = R.partsIn(d, null); return `${p.key}T${R.p2(p.h)}:${R.p2(p.mi)}`; };
  const fromLocalInput = v => (v ? new Date(v) : null);
  const statusLabel = code => (R.STATUS_BY[code] ? R.STATUS_BY[code].label : code || '');

  // ---- files ----
  const readText = file => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(r.result); r.onerror = () => no(r.error); r.readAsText(file, 'utf-8'); });
  function download(name, text, type) {
    const blob = new Blob([text], { type: type || 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name; a.style.display = 'none';
    document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 2000);
    APP.downloads.push(name);
  }
  // messages of one action stay together; the next action's message replaces them, so no stale warning lingers
  let lastToast = 0;
  function toast(text, kind) {
    const id = Math.random().toString(36).slice(2), t = Date.now();
    if (t - lastToast > 400) APP.toasts = [];
    lastToast = t;
    APP.toasts.push({ id, text, kind: kind || 'ok' });
    if (APP.toasts.length > 3) APP.toasts = APP.toasts.slice(-3);
    renderToasts();
    setTimeout(() => { APP.toasts = APP.toasts.filter(t => t.id !== id); renderToasts(); }, kind === 'warn' ? 9000 : 4500);
  }
  function renderToasts() {
    const el = $('#toasts'); if (!el) return;
    el.innerHTML = APP.toasts.map(t => `<div class="toast ${t.kind}" role="status">${esc(t.text)}</div>`).join('');
  }

  // ---- loading files ----
  // a protected file (D11) is opened with the passphrase the leader gave; nothing about the passphrase is kept
  function askPassphrase(file, env, then) {
    if (!R.canSeal()) { APP.loadErrors = [`${file.name} is protected, and this browser cannot open protected files here. Use a current Chrome, Edge, Firefox or Safari.`]; return render(); }
    APP.modal = { kind: 'passphrase', file: file.name, env, then, error: '', busy: false };
    render();
    const i = $('#modal-input'); if (i) i.focus();
  }
  function tryPassphrase() {
    const m = APP.modal; if (!m || m.kind !== 'passphrase' || m.busy) return;
    const i = $('#modal-input'), v = i ? i.value : '';
    if (!v) { m.error = 'Enter the passphrase.'; return render(); }
    m.busy = true; m.error = ''; render();
    R.unseal(m.env, v).then(({ obj, k }) => { APP.modal = null; m.then(obj, k); })
      .catch(e => { m.busy = false; m.error = e.message; render(); const j = $('#modal-input'); if (j) j.focus(); });
  }
  async function openAssignment(file) {
    APP.loadErrors = []; APP.loadWarnings = [];
    let A;
    try { A = JSON.parse(await readText(file)); } catch (e) { APP.loadErrors = [`${file.name} is not a readable JSON file.`]; return render(); }
    if (A && A.schema === R.SCHEMA.sealed) {
      if (A.contains !== R.SCHEMA.assign) { APP.loadErrors = [`${file.name} is a protected ${A.contains === R.SCHEMA.project ? 'saved session' : 'file'}, not an assignment.${A.contains === R.SCHEMA.project ? ' Use "Continue a saved session".' : ''}`]; return render(); }
      return askPassphrase(file, A, (inner, k) => useAssignment(file, inner, k));
    }
    useAssignment(file, A, null);
  }
  function useAssignment(file, A, k) {
    if (A && A.schema === R.SCHEMA.project) { APP.loadErrors = [`${file.name} is a saved session, not an assignment. Use "Continue a saved session".`]; return render(); }
    const v = R.validateAssignment(A);
    if (v.errors.length) { APP.loadErrors = v.errors.map(e => `${file.name}: ${e}`); return render(); }
    if (APP.S) {           // an updated assignment for the session in progress
      if (R.fingerprint(A) === APP.S.fingerprint) { toast('This is the assignment already in your session: nothing to update.'); return render(); }
      const u = R.updateAssignment(APP.S, A, file.name);
      if (u.problems.length) { toast(u.problems.join(' '), 'warn'); return render(); }
      if (k) APP.S.seal = k;
      APP.unsaved++; APP.loadWarnings = v.warnings;
      toast(`Assignment updated: ${R.plural(u.added.length, 'household')} added, ${u.removed.length} no longer assigned. Your logged calls are kept.`);
      return render();
    }
    const S = R.newSession(A);
    if (k) S.seal = k;
    R.append(S, 'session', { what: 'started', fingerprint: S.fingerprint, fingerprint_ok: A.fingerprint ? (A.fingerprint === S.fingerprint ? 1 : 0) : undefined, file: file.name, protected: k ? 1 : undefined });
    APP.S = S; APP.unsaved = 1; APP.loadWarnings = v.warnings; APP.tab = 'today'; APP.sel = null; APP.day = null;
    render();
    toast(`Assignment loaded: ${A.households.length} households for ${A.enumerator_id}, round ${A.round}.`);
  }
  async function openProject(file) {
    APP.loadErrors = []; APP.loadWarnings = [];
    let o;
    try { o = JSON.parse(await readText(file)); } catch (e) { APP.loadErrors = [`${file.name} is not a readable JSON file.`]; return render(); }
    if (o && o.schema === R.SCHEMA.sealed) {
      if (o.contains !== R.SCHEMA.project) { APP.loadErrors = [`${file.name} is a protected ${o.contains === R.SCHEMA.assign ? 'assignment' : 'file'}, not a saved session.${o.contains === R.SCHEMA.assign ? ' Use "Open my assignment file".' : ''}`]; return render(); }
      return askPassphrase(file, o, (inner, k) => useProject(file, inner, k));
    }
    useProject(file, o, null);
  }
  function useProject(file, o, k) {
    if (o && o.schema === R.SCHEMA.assign) { APP.loadErrors = [`${file.name} is an assignment file, not a saved session. Use "Open my assignment file".`]; return render(); }
    const r = R.loadProject(o);
    if (r.errors.length) { APP.loadErrors = r.errors.map(e => `${file.name}: ${e}`); return render(); }
    APP.S = r.session; if (k) APP.S.seal = k; APP.unsaved = 0; APP.loadWarnings = r.warnings; APP.tab = 'today'; APP.sel = null; APP.day = null; APP.fileHandle = null;
    render();
    toast(`Session restored: ${r.session.events.length} logged events, saved ${isoWhen(o.saved_at)}.`);
  }
  async function openPast(files) {
    const S = APP.S; let added = 0; const msgs = [];
    const seen = new Set(S.past.dials.map(r => r.event_id));
    const mine = new Set(R.effective(S).dials.map(d => d.event_id));
    for (const f of files) {
      try {
        const { meta, rows } = R.readExport(await readText(f), f.name);
        if (meta.enumerator_id && meta.enumerator_id !== S.assignment.enumerator_id) { msgs.push(`${f.name} is ${meta.enumerator_id}'s log, not yours: skipped.`); continue; }
        let n = 0;
        for (const r of rows) { if (!r.event_id || seen.has(r.event_id) || mine.has(r.event_id)) continue; seen.add(r.event_id); S.past.dials.push(r); n++; }
        if (n) S.past.files.push({ name: f.name, round: meta.round || null, rows: rows.length, added: n });
        else if (rows.length) msgs.push(`${f.name}: no new dials, it repeats a log already loaded.`);
        added += n;
      } catch (e) { msgs.push(e.message); }
    }
    if (added) APP.unsaved++;
    msgs.forEach(m => toast(m, 'warn'));
    if (added) toast(`${added} earlier dials added to your performance view.`);
    render();
  }

  // ---- saving and exporting ----
  async function saveSession() {
    const S = APP.S, A = S.assignment, now = R.now();
    const o = R.buildProject(S, now);
    const text = JSON.stringify(S.seal ? await R.sealWith(o, S.seal, { contains: R.SCHEMA.project, program: A.program, round: A.round, enumerator_id: A.enumerator_id }) : o);
    const fixedName = `${A.enumerator_id}_project_R${R.p2(A.round)}.json`;
    let where = null;
    if (window.showSaveFilePicker && !APP.noFSA) {
      try {
        if (!APP.fileHandle) APP.fileHandle = await window.showSaveFilePicker({ suggestedName: fixedName, types: [{ description: 'Saved session', accept: { 'application/json': ['.json'] } }] });
        const w = await APP.fileHandle.createWritable(); await w.write(text); await w.close();
        where = APP.fileHandle.name;
      } catch (e) {
        if (e && e.name === 'AbortError') return;
        APP.fileHandle = null;
      }
    }
    if (!where) {
      const p = R.partsIn(now, null);
      where = `${A.enumerator_id}_project_R${R.p2(A.round)}_${p.key}_${R.p2(p.h)}${R.p2(p.mi)}.json`;
      download(where, text, 'application/json');
    }
    S.last_save = { at: o.saved_at, event_count: S.events.length, file: where };
    APP.unsaved = 0;
    render();
    toast(`Session saved${S.seal ? ', protected with your passphrase' : ''}: ${where}. Keep it in your own folder, not the common one.`);
  }
  async function exportLog() {
    const S = APP.S, now = R.now();
    const X = R.buildExport(S, now);
    if (X.contacts && S.seal) X.contactsOut = await R.sealWith(X.contacts, S.seal, { contains: R.SCHEMA.contacts, program: X.contacts.program, round: X.contacts.round, enumerator_id: X.contacts.enumerator_id });
    const ev = R.append(S, 'export', { file_base: X.base, event_count: X.json.event_count, last_hash: X.json.last_hash, contacts_file: X.contacts ? 1 : undefined });
    S.last_export = { at: ev.logged_at, base: X.base, event_count: X.json.event_count };
    APP.unsaved++;
    APP.exportPack = X;
    APP.modal = { kind: 'export' };
    render();
  }

  // ---- logging ----
  function log(type, fields, priv, msg) {
    R.append(APP.S, type, fields, priv);
    APP.unsaved++;
    render();
    if (msg) toast(msg);
    if (APP.unsaved >= APP.saveEvery && APP.unsaved % APP.saveEvery === 0) toast(`${APP.unsaved} changes not saved yet. Save your session.`, 'warn');
  }
  // bring the call box into view inside the household panel (it sits below the phone numbers)
  function showCallBox() { const el = $('.callbox'); if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' }); }
  function startCall(hhid, slot) {
    APP.call = { hhid, slot: +slot, start: R.now(), end: null };
    APP.manual = false;
    render();
    showCallBox();
    clearInterval(APP.timer);
    APP.timer = setInterval(() => {
      const el = $('#call-timer'); if (!el || !APP.call || APP.call.end) return;
      const s = Math.floor((R.now() - APP.call.start) / 1000); el.textContent = `${R.p2(Math.floor(s / 60))}:${R.p2(s % 60)}`;
    }, 1000);
  }
  function endCall() { if (!APP.call) return; APP.call.end = R.now(); clearInterval(APP.timer); render(); showCallBox(); }
  function readCallForm(manual) {
    const f = $('#callform'); if (!f) return null;
    const g = n => { const el = f.querySelector(`[name="${n}"]`); return el ? el.value.trim() : ''; };
    const status = (f.querySelector('input[name="status"]:checked') || {}).value || '';
    const v = { status, note: g('note'), action: g('action'), appt: g('appointment') };
    if (manual) {
      v.slot = +g('slot'); v.start = fromLocalInput(g('start'));
      const mins = parseFloat(g('minutes'));
      v.end = v.start && !isNaN(mins) ? new Date(v.start.getTime() + mins * 60000) : null;
    } else { v.slot = APP.call.slot; v.start = APP.call.start; v.end = APP.call.end; }
    return v;
  }
  // a missing entry is marked on the field itself and focused; the mark goes when the field is changed
  function fieldError(formSel, name, text) {
    const f = $(formSel), el = f && (name === 'status' ? f.querySelector('fieldset.statuses') : f.querySelector(`[name="${name}"]`));
    if (el) {
      el.classList.add('invalid'); el.setAttribute('aria-invalid', 'true');
      const clear = () => { el.classList.remove('invalid'); el.removeAttribute('aria-invalid'); };
      el.addEventListener('input', clear, { once: true }); el.addEventListener('change', clear, { once: true });
      (name === 'status' ? el.querySelector('input') : el).focus();
      if (el.scrollIntoView) el.scrollIntoView({ block: 'center' });
    }
    toast(text, 'warn');
  }
  function saveCall(manual) {
    const c = APP.C.map.get(APP.sel); if (!c) return;
    const v = readCallForm(manual); if (!v) return;
    if (!v.status) return fieldError('#callform', 'status', 'Choose the result of the call.');
    if (manual && !v.start) return fieldError('#callform', 'start', 'Enter when the call started.');
    if (v.status === 'OTHER' && !v.note) return fieldError('#callform', 'note', 'Write a note for "Other".');
    const appt = v.appt ? fromLocalInput(v.appt) : null;
    if (v.status === 'APPOINTMENT' && !appt) return fieldError('#callform', 'appointment', 'Enter the agreed callback time.');
    const fields = {
      hhid: c.hhid, phone_slot: v.slot, ts: R.localISO(v.start), end_ts: v.end ? R.localISO(v.end) : undefined,
      status: v.status, operator: APP.S.assignment.enumerator_id, appointment_ts: appt ? R.localISO(appt) : undefined,
      action: v.action || undefined, note: v.note || undefined, replaces: c.h.replaces || undefined, entered: manual ? 'after the call' : undefined,
    };
    const mins = v.end ? (v.end - v.start) / 60000 : null;
    APP.call = null; APP.manual = false;
    log('dial', fields, null, `Call saved: ${statusLabel(v.status)} (dial ${c.n + 1} for ${c.hhid}).`);
    if (v.status === 'COMPLETE' && mins !== null && mins < R.MIN_COMPLETE_MIN) toast(`This complete lasted under ${R.MIN_COMPLETE_MIN} minutes. Box 3.0 counts it as an appointment contact, not a complete, so the household stays open. Correct the time if it is wrong.`, 'warn');
  }
  function saveCorrection(eventId, isAction) {
    const f = $('#corrform'); if (!f) return;
    const g = n => { const el = f.querySelector(`[name="${n}"]`); return el ? el.value.trim() : ''; };
    const reason = g('reason');
    if (!reason) return fieldError('#corrform', 'reason', 'Write why you are correcting this entry.');
    const voidIt = isAction || (f.querySelector('input[type="checkbox"][name="void"]') || {}).checked;
    if (voidIt) { APP.correct = null; return log('correction', { target: eventId, void: 1, reason }, null, isAction ? 'Action undone. It stays in the log, marked as undone.' : 'Entry voided. It stays in the log, marked as voided.'); }
    const d = R.effective(APP.S).dials.find(x => x.event_id === eventId) || {};
    const ch = {};
    const st = g('status'); if (st && st !== d.status) ch.status = st;
    const sl = +g('slot'); if (sl && sl !== d.phone_slot) ch.phone_slot = sl;
    // the form shows times to the minute and durations to a tenth: only what the enumerator actually changed is corrected
    const start = fromLocalInput(g('start'));
    const startChanged = !!(start && R.localISO(start).slice(0, 16) !== (d.ts || '').slice(0, 16));
    if (startChanged) ch.ts = R.localISO(start);
    const mins = parseFloat(g('minutes')), had = d.dur_min === null || d.dur_min === undefined ? null : d.dur_min;
    const minsChanged = !isNaN(mins) && (had === null || Math.abs(mins - parseFloat(num(had, 1))) > 1e-9);
    const from = startChanged ? start : R.parseTS(d.ts), dur = minsChanged ? mins : had;
    if (from && dur !== null && (minsChanged || startChanged)) { const e = R.localISO(new Date(from.getTime() + dur * 60000)); if (e !== d.end_ts) ch.end_ts = e; }
    const ap = fromLocalInput(g('appointment')); if (ap && R.localISO(ap).slice(0, 16) !== (d.appointment_ts || '').slice(0, 16)) ch.appointment_ts = R.localISO(ap);
    const note = g('note'); if (note !== (d.note || '')) ch.note = note || undefined;
    if (!Object.keys(R.clean(ch)).length) return toast('Nothing changed.', 'warn');
    APP.correct = null;
    log('correction', { target: eventId, changes: R.clean(ch), reason }, null, 'Correction saved. The original entry stays in the log.');
  }
  function confirmModal(title, text, opts, onOk) {
    APP.modal = Object.assign({ kind: 'confirm', title, text, onOk }, opts || {});
    render();
    const i = $('#modal-input'); if (i) i.focus();
  }
  function doAction(c, action) {
    const needReason = action !== 'RELEASE';
    const texts = {
      RELEASE: `Stop calling ${c.hhid} for this round. It stays in the panel and is called again next round (handbook 3.3.5: release, never delete).`,
      SWITCH_REQUEST: `Ask the leader to give ${c.hhid} to another enumerator next round. You can keep calling it this round.`,
      REMOVE_REQUEST: c.flags.no_phone ? `Ask the leader to remove ${c.hhid}: it has no phone number. The leader decides.` : `Ask the leader to remove ${c.hhid}: none of its numbers works. The leader decides.`,
    };
    confirmModal(R.ACTIONS[action], texts[action], { input: needReason ? 'Why? (required)' : 'Reason (optional)', required: needReason, okLabel: R.ACTIONS[action] }, reason => {
      log('action', { hhid: c.hhid, action, reason: reason || undefined }, null, `${R.ACTIONS[action]}: ${c.hhid}.`);
    });
  }
  function activateReplacement(c) {
    const r = c.replacements.find(x => !x.active);
    if (!r) return toast('No replacement left for this household.', 'warn');
    confirmModal('Activate a replacement', `${r.hhid} (replacement ${r.rank} for ${c.hhid}) becomes a household to call. ${c.hhid} is closed for this round. Replacements are used in their order, as the sample was drawn.`,
      { input: 'Why? (required)', required: true, okLabel: 'Activate ' + r.hhid }, reason => {
        log('action', { hhid: c.hhid, action: 'ACTIVATE_REPLACEMENT', target_hhid: r.hhid, reason }, null, `${r.hhid} activated as a replacement for ${c.hhid}.`);
        APP.sel = r.hhid; render();
      });
  }
  function replacementAllowed(c) {
    const pol = APP.S.assignment.replacement_policy || {};
    if (!pol.active) return { ok: false, why: 'Replacements are not in use this round.' };
    if (!c.replacements.some(x => !x.active)) return { ok: false, why: 'No replacement left for this household.' };
    const trig = pol.triggers || ['REFUSAL_HARD', 'ALL_NUMBERS_DEAD'];
    if ((trig.includes('REFUSAL_HARD') && c.flags.hard_refusal) || (trig.includes('ALL_NUMBERS_DEAD') && c.flags.all_dead) || (trig.includes('CAP_REACHED') && c.flags.cap_reached)) return { ok: true };
    const say = { REFUSAL_HARD: 'a hard refusal', ALL_NUMBERS_DEAD: 'no working number', CAP_REACHED: 'the dial cap reached' };
    return { ok: false, why: 'Allowed after ' + trig.map(t => say[t] || t).join(' or ') + '.' };
  }
  function saveContact() {
    const f = $('#contactform'); if (!f) return;
    const g = n => { const el = f.querySelector(`[name="${n}"]`); return el ? el.value.trim() : ''; };
    const c = APP.C.map.get(APP.sel);
    const isNew = g('slot') === 'new';
    const slot = isNew ? Math.max(0, ...c.slots.map(s => s.slot)) + 1 : +g('slot');
    const change = isNew ? 'add' : g('change'), number = g('number'), label = g('label');
    if (change !== 'mark_dead' && !/[0-9]{5,}/.test(number.replace(/\D/g, ''))) return toast('Enter the phone number.', 'warn');
    APP.contact = false;
    log('contact_update', { hhid: c.hhid, slot, change, label: label || undefined }, change === 'mark_dead' ? null : { number },
      change === 'mark_dead' ? `Number ${slot} marked as not working.` : `Number ${slot} saved. It goes to your leader in a separate contacts file when you export.`);
  }

  // ---- rendering ----
  function topbar() {
    return `<header class="topbar">
      <div class="brand"><span class="logo" aria-hidden="true"></span>RTM interview tool <span class="ver">v${R.VERSION}</span></div>
      <nav class="views" aria-label="View"><button data-act="view" data-v="enum" class="${APP.view === 'enum' ? 'on' : ''}">Enumerator</button><button data-act="view" data-v="leader" class="${APP.view === 'leader' ? 'on' : ''}">Team leader</button></nav>
      <div class="offline" title="This page has no server, no shared database and no network connection: the browser is told to refuse any. It reads only files you open, and writes only files you save or export.">Offline · no server · no shared database · no network</div>
    </header>`;
  }
  function startScreen() {
    return `<section class="start">
      <h1>Enumerator view</h1>
      <p class="lead">Open the assignment file your team leader gave you, or continue a session you saved earlier.</p>
      <div class="startgrid">
        <label class="bigpick"><input type="file" id="f-assign" accept=".json,application/json"><b>Open my assignment file</b><span>For example <code>E07_assignment_R05.json</code></span></label>
        <label class="bigpick"><input type="file" id="f-project" accept=".json,application/json"><b>Continue a saved session</b><span>For example <code>E07_project_R05.json</code></span></label>
      </div>
      ${APP.loadErrors.length ? `<div class="alert bad" role="alert"><b>The file could not be opened.</b><ul>${APP.loadErrors.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div>` : ''}
      <div class="how">
        <h2>How it works</h2>
        <ol>
          <li><b>Call and log.</b> Open a household, start the call, end it, choose the result. The time is recorded for you.</li>
          <li><b>Save your session</b> to your own folder whenever you stop. Saving keeps everything, so you can close the browser and continue later.</li>
          <li><b>Export your log</b> at the end of each day and at the end of the round, and put it in the common folder for your leader.</li>
        </ol>
        <p class="muted">This page reads only files you open and writes only files you save or export. It has no server, no shared database and no network connection.</p>
      </div>
    </section>`;
  }
  function summary(C, now) {
    const S = APP.S, A = S.assignment, cal = C.cal, p = R.progress(C);
    const left = R.workingDaysLeft(cal, todayKey());
    const w = k => { const [y, m, d] = k.split('-').map(Number); return `${d} ${MON[m - 1]} ${y}`; };
    const seg = (n, cls) => (n ? `<span class="seg ${cls}" style="flex:${n}"></span>` : '');
    const chain = R.verifyChain(S.events, S.genesis);
    const banners = [];
    if (APP.loadWarnings.length) banners.push(`<div class="alert warn"><b>Note.</b> ${APP.loadWarnings.map(esc).join(' ')}</div>`);
    if (!chain.ok) banners.push(`<div class="alert bad"><b>Integrity check failed</b> at event ${chain.index + 1}: ${esc(chain.reason)}.</div>`);
    if (APP.unsaved >= APP.saveEvery) banners.push(`<div class="alert warn"><b>${APP.unsaved} changes are not saved yet.</b> <button class="link" data-act="save">Save your session now</button>.</div>`);
    const outside = todayKey() < cal.start ? 'The round has not started yet.' : todayKey() > cal.end ? 'The round window has ended: release any household still open and export your log.' : '';
    if (outside) banners.push(`<div class="alert info">${outside}</div>`);
    return `<section class="summary">
      <div class="who"><b>${esc(A.enumerator_id)}</b> · ${esc(A.program)} round ${A.round} · window ${dayLabel(cal.start)} – ${w(cal.end)} · ${left} working day${left === 1 ? '' : 's'} left</div>
      <div class="prog" aria-label="Progress">
        <div class="bar">${seg(p.complete, 'ok')}${seg(p.released + p.replaced + p.remove_requested, 'rel')}${seg(p.in_progress, 'prog')}${seg(p.not_started, 'none')}</div>
        <div class="legend"><b>${p.complete}</b> complete · <b>${p.in_progress}</b> in progress · <b>${p.not_started}</b> not started · <b>${p.released + p.replaced + p.remove_requested}</b> released or closed · ${p.total} households${p.reassigned ? ` · ${p.reassigned} no longer assigned to you` : ''}</div>
      </div>
      <div class="actions">
        <button class="primary" data-act="save"${APP.unsaved ? ` title="${R.plural(APP.unsaved, 'change')} not saved yet"` : ''}>Save session${APP.unsaved ? ` <span class="pill" aria-label="${R.plural(APP.unsaved, 'change')} not saved yet">${APP.unsaved}</span>` : ''}</button>
        <button data-act="export">Export log</button>
        <label class="btn">Load earlier logs<input type="file" id="f-past" accept=".json,.csv" multiple></label>
        <label class="btn subtle">Load updated assignment<input type="file" id="f-update" accept=".json"></label>
        <button class="subtle" data-act="close">Close session</button>
      </div>
      <div class="savestate">${S.last_save ? `Last saved ${isoWhen(S.last_save.at)}${S.last_save.file ? ' (' + esc(S.last_save.file) + ')' : ''}` : 'Not saved yet'}${APP.unsaved ? `${(S.last_save ? ', ' : ': ')}${R.plural(APP.unsaved, 'change')}${S.last_save ? ' since' : ''}` : ''} · ${S.last_export ? `last exported ${isoWhen(S.last_export.at)}` : 'not exported yet'}${S.seal ? ' · <span class="tag">protected: saved sessions and contacts files use your passphrase</span>' : ''}</div>
      ${banners.join('')}
    </section>`;
  }
  function tabs(C, now) {
    const q = R.queue(C, now, todayKey());
    const t = [['today', 'Today', q.due.length], ['households', 'Households', C.list.length], ['calendar', 'Calendar'], ['performance', 'My performance'], ['log', 'Log']];
    return `<nav class="tabs" role="tablist">${t.map(([k, l, n]) => `<button role="tab" aria-selected="${APP.tab === k}" data-act="tab" data-t="${k}" class="${APP.tab === k ? 'on' : ''}">${l}${n !== undefined ? ` <span class="count">${n}</span>` : ''}</button>`).join('')}</nav>`;
  }
  const kindLabel = { callback: 'Callback', first: 'First dial', overdue: 'Overdue', redial: 'Redial', next_day: 'Redial', cap: 'Cap reached', refusal: 'Refusal', dead: 'No number', window_end: 'Window ends' };
  function card(c, showDate) {
    const s = c.next;
    const t = s.at ? (showDate ? when(s.at) : hm(s.at)) : '';
    return `<button class="card" data-act="open" data-hh="${esc(c.hhid)}">
      <span class="when">${t}</span><span class="kind k-${s.kind}">${kindLabel[s.kind] || ''}</span>
      <span class="id">${esc(c.hhid)}</span><span class="name">${esc((c.h.contact || {}).name || '')}</span>
      <span class="meta">${c.n ? `${c.n} dial${c.n > 1 ? 's' : ''} · last: ${esc(statusLabel(c.last.status))}` : esc(reasonText(c.h))}${c.kind === 'replacement' ? ' · replacement' : ''}</span>
    </button>`;
  }
  function todayPanel(C, now) {
    const cal = C.cal, day = APP.day || todayKey(), q = R.queue(C, now, day);
    const hol = cal.holiday(day), work = cal.isWorking(day);
    const dayNote = !cal.inWindow(day) ? 'outside the round window' : hol ? `holiday: ${esc(hol.name)}${hol.estimated ? ' (date estimated)' : ''}${work ? ', marked as a working day' : ''}` : work ? 'working day' : 'not a working day';
    const col = (title, list, empty, showDate) => `<section class="col"><h3>${title} <span class="count">${list.length}</span></h3>${list.length ? list.map(c => card(c, showDate)).join('') : `<p class="muted">${empty}</p>`}</section>`;
    return `<div class="daybar">
        <button data-act="day" data-d="-1" aria-label="Previous day">‹</button>
        <b>${dayLabel(day)}</b>${q.isToday ? ' <span class="pill">today</span>' : ''} <span class="muted">${dayNote}</span>
        <button data-act="day" data-d="1" aria-label="Next day">›</button>
        ${q.isToday ? '' : '<button class="subtle" data-act="day" data-d="0">Back to today</button>'}
      </div>
      ${hol && cal.inWindow(day) ? `<div class="alert info">Public holiday${hol.estimated ? ' (estimated date)' : ''}. Calls are not planned automatically on holidays, but you can still call and log.</div>` : ''}
      <div class="today">
        ${q.isToday ? col('Due now', q.due, 'Nothing is due right now.', true) : ''}
        ${col(q.isToday ? 'Later today' : 'Planned for this day', q.later, 'No calls planned.', false)}
        ${q.isToday ? col('Needs your decision', q.decide, 'No decisions waiting.', false) : ''}
      </div>`;
  }
  const RULE_NOTE = 'How households are assigned: the handbook\'s stated default is to keep the same enumerator, rotate a planned share of households each round, and switch the enumerator for a household that becomes hard to reach (Section 3.5.3).';
  const RULE_REASONS = new Set(['keep', 'rotation', 'switch_hard_to_reach']);
  // the round's rule, from the assignment file; under the other rules a moved household was dealt by that rule
  const RULE_LABEL = { random: 'random', equal_split: 'equal split', share_of_total: 'share of total', manual: 'a list made by hand' };
  const RULE_WHY = {
    random: 'This round your leader dealt households at random, mixing strata, in proportion to each enumerator’s share. The handbook’s stated default is otherwise to keep the same enumerator (Section 3.5.3).',
    equal_split: 'This round your leader split the household list into consecutive blocks, one per enumerator. The handbook’s stated default is otherwise to keep the same enumerator (Section 3.5.3).',
    share_of_total: 'This round your leader gave each enumerator a set share of the households. The handbook’s stated default is otherwise to keep the same enumerator (Section 3.5.3).',
    manual: 'This round your leader assigned households from a list made by hand. The handbook’s stated default is otherwise to keep the same enumerator (Section 3.5.3).',
  };
  const ruleName = () => ((APP.S && APP.S.assignment.rule) || {}).name || 'keep_same';
  // equal split, and share of total in blocks, place households by blocks of the list; the others deal them at random
  const byBlocks = () => { const r = (APP.S && APP.S.assignment.rule) || {}; return r.name === 'equal_split' || (r.name === 'share_of_total' && r.method === 'blocks'); };
  const ruleReason = () => (byBlocks() ? `Placed with you by a block of the list (${RULE_LABEL[ruleName()] || ruleName()})` : `Dealt to you at random by this round’s rule (${RULE_LABEL[ruleName()] || ruleName()})`);
  // the keep reason is told from the household's own history: interviewed last round, earlier, or not yet
  function reasonText(h) {
    const a = h.assignment || {}, hist = h.history || {}, li = hist.last_interview, rule = ruleName();
    // 'rule' since the review loop; files written before it gave such households 'rotation'
    if (a.reason === 'rule' || (rule !== 'keep_same' && a.reason === 'rotation')) return ruleReason();
    if (a.reason !== 'keep') return R.REASONS[a.reason] || '';
    const t = APP.S ? APP.S.assignment.round : null;
    if (li && t !== null && li.round === t - 1) return 'Kept with you: you interviewed it last round';
    if (li) return `Kept with you: you interviewed it in round ${li.round}`;
    return 'Kept with you: you had it last round';
  }
  const reasonShort = { keep: 'Kept with you', rotation: 'Rotation', switch_hard_to_reach: 'Switched: hard to reach', enumerator_unavailable: 'Previous enumerator away',
    new: 'New to the panel', manual: 'Assigned by hand', capacity: 'Workload balance', replacement: 'Replacement' };
  const shortReason = h => { const r = (h.assignment || {}).reason || '';
    return r === 'rule' || (ruleName() !== 'keep_same' && r === 'rotation') ? (byBlocks() ? 'By a block of the list' : 'Dealt at random') : reasonShort[r] || r.replace(/_/g, ' '); };
  const stateLabel = { reassigned: 'No longer yours', complete: 'Complete', in_progress: 'In progress', not_started: 'Not started', released: 'Released', replaced: 'Replaced', remove_requested: 'Removal requested' };
  function householdsPanel(C) {
    const f = APP.filter, q = APP.q.toLowerCase();
    const keep = c => (f === 'all' || (f === 'open' && c.open) || (f === 'closed' && !c.open && c.state !== 'complete') || f === c.state || (f === 'leader' && (c.flags.switch_requested || c.state === 'remove_requested' || c.flags.all_dead)))
      && (!q || c.hhid.toLowerCase().includes(q) || ((c.h.contact || {}).name || '').toLowerCase().includes(q));
    const chips = [['open', 'Open'], ['not_started', 'Not started'], ['in_progress', 'In progress'], ['complete', 'Complete'], ['closed', 'Released or closed'], ['leader', 'Needs the leader'], ['all', 'All']];
    return `<div class="filters">${chips.map(([k, l]) => `<button class="chip ${f === k ? 'on' : ''}" data-act="filter" data-f="${k}">${l}</button>`).join('')}
      <input type="search" id="hh-search" placeholder="Search ID or name" value="${esc(APP.q)}" aria-label="Search households"></div>
      <div id="hh-table">${hhTable(C.list.filter(keep))}</div>
      <p class="muted small">${ruleName() !== 'keep_same' && RULE_WHY[ruleName()] ? RULE_WHY[ruleName()] : RULE_NOTE}</p>`;
  }
  function hhTable(list) {
    if (!list.length) return '<p class="muted">No household matches.</p>';
    return `<table class="grid"><thead><tr><th>Household</th><th>Contact</th><th>Why you have it</th><th>First dial planned</th><th class="num">Dials</th><th>Last result</th><th>Next</th><th>State</th></tr></thead><tbody>
      ${list.map(c => { const pl = c.h.plan || {}; return `<tr data-act="open" data-hh="${esc(c.hhid)}" tabindex="0">
        <td class="id">${esc(c.hhid)}${c.kind === 'replacement' ? ' <span class="tag">replacement</span>' : ''}</td><td>${esc((c.h.contact || {}).name || '')}</td>
        <td>${esc(shortReason(c.h))}</td>
        <td>${pl.first_dial_date ? dayLabel(pl.first_dial_date) : ''}${Number.isInteger(pl.target_hour) ? ' ' + R.p2(pl.target_hour) + ':00' : ''}</td>
        <td class="num">${c.n}</td><td>${c.last ? esc(statusLabel(c.last.status)) : ''}</td>
        <td>${c.next.at ? when(c.next.at) + (c.open && c.next.at < R.now() ? ' <span class="tag warn">overdue</span>' : '') : esc(kindLabel[c.next.kind] || '')}</td>
        <td><span class="st st-${c.state}">${stateLabel[c.state]}</span>${c.flags.switch_requested ? ' <span class="tag">switch asked</span>' : ''}${c.flags.complete_short ? ' <span class="tag warn">under 3 min</span>' : ''}</td></tr>`; }).join('')}
    </tbody></table>`;
  }
  function calendarPanel(C) {
    const cal = C.cal, A = APP.S.assignment;
    const bundled = new Map(R.bundledHolidays(A.country).map(h => [h.date, h]));
    const stats = {};
    const add = (k, f) => { stats[k] = stats[k] || { plan: 0, cb: 0, dials: 0, ok: 0 }; stats[k][f]++; };
    C.list.forEach(c => { const pl = c.h.plan || {}; if (pl.first_dial_date) add(pl.first_dial_date, 'plan'); if (c.open && c.next.kind === 'callback') add(R.partsIn(c.next.at, cal.tz).key, 'cb'); });
    C.eff.dials.forEach(d => add(R.partsIn(R.parseTS(d.ts), cal.tz).key, 'dials'));
    // completes by Box 3.0's rule: a household's complete of 3 minutes or more, on the day it was made
    C.list.forEach(c => { if (c.complete) add(R.partsIn(R.parseTS(c.complete.ts), cal.tz).key, 'ok'); });
    const [sy, sm] = cal.start.split('-').map(Number), [ey, em] = cal.end.split('-').map(Number);
    const months = []; for (let y = sy, m = sm; y < ey || (y === ey && m <= em); m === 12 ? (y++, m = 1) : m++) months.push([y, m]);
    const today = todayKey();
    const grid = ([y, m]) => {
      const first = `${y}-${R.p2(m)}-01`, lead = R.weekdayOfKey(first) - 1;
      const days = new Date(Date.UTC(y, m, 0)).getUTCDate();
      let cells = '';
      for (let i = 0; i < lead; i++) cells += '<div class="cell blank"></div>';
      for (let d = 1; d <= days; d++) {
        const k = `${y}-${R.p2(m)}-${R.p2(d)}`, inW = cal.inWindow(k);
        const hol = (inW ? cal.holiday(k) : null) || bundled.get(k);
        const st = stats[k] || {};
        const cls = ['cell', inW ? 'inw' : 'outw', inW && !cal.isWorking(k) ? 'off' : '', hol ? 'hol' : '', k === today ? 'today' : ''].join(' ');
        cells += `<button class="${cls}" data-act="gotoday" data-k="${k}" ${inW ? '' : 'tabindex="-1"'}>
          <span class="dn">${d}</span>${hol ? `<span class="hname">${esc(hol.name)}${hol.estimated ? ' (est.)' : ''}</span>` : ''}
          ${inW ? `<span class="marks">${st.plan ? `<span class="m plan" title="first dials planned">${st.plan} planned</span>` : ''}${st.cb ? `<span class="m cb" title="callbacks booked">${st.cb} callback${st.cb > 1 ? 's' : ''}</span>` : ''}${st.dials ? `<span class="m done" title="dials made; completes">${R.plural(st.dials, 'dial')} · ${st.ok} complete</span>` : ''}</span>` : ''}
        </button>`;
      }
      return `<section class="month"><h3>${MONTH[m - 1]} ${y}</h3><div class="wk">${WD.map(w => `<span>${w}</span>`).join('')}</div><div class="days">${cells}</div></section>`;
    };
    const holsIn = (cal.raw.holidays || []).filter(h => cal.inWindow(h.date));
    return `<p class="muted">Days in the round window are white; days outside it are grey. Hatched days get no calls planned automatically: days the call center does not work and public holidays. Holidays come from the assignment file (the leader's list for this round) and, outside the window, from the tool's bundled table (Python package <code>holidays</code>, as in handbook Section 3.5.4). Click a day to see its calls.</p>
      <div class="months">${months.map(grid).join('')}</div>
      <p class="muted">${holsIn.length ? `Holidays in the window: ${holsIn.map(h => `${dayLabel(h.date)} ${esc(h.name)}${h.estimated ? ' (estimated)' : ''}${h.working ? ' — working day' : ''}`).join('; ')}.` : 'No public holiday falls inside the window.'} Working weekdays: ${cal.raw.working_weekdays.map(x => WD[x - 1]).join(', ')}; call hours ${R.p2(cal.hours.start)}:00–${R.p2(cal.hours.end)}:00${cal.tz ? ' (' + esc(cal.tz) + ')' : ''}.</p>`;
  }
  function perfPanel(C, now) {
    const S = APP.S, tz = C.cal.tz;
    const cur = C.eff.dials.map(R.dialRow);
    const all = cur.concat(S.past.dials);
    const thisM = (() => { const p = R.partsIn(now, tz); return `${p.y}-${R.p2(p.m)}`; })();
    const lastM = (() => { const p = R.partsIn(now, tz); return p.m === 1 ? `${p.y - 1}-12` : `${p.y}-${R.p2(p.m - 1)}`; })();
    const sets = [['This round so far', cur], ['This month', all.filter(r => R.monthKey(r, tz) === thisM)], ['Last month', all.filter(r => R.monthKey(r, tz) === lastM)], ['All loaded logs', all]];
    const P = sets.map(([l, rows]) => [l, R.perf(rows, tz)]);
    const row = (label, f, def) => `<tr><th title="${esc(def || '')}">${label}</th>${P.map(([, p]) => `<td class="num">${f(p)}</td>`).join('')}</tr>`;
    const kpi = `<table class="grid kpi"><thead><tr><th></th>${P.map(([l]) => `<th class="num">${l}</th>`).join('')}</tr></thead><tbody>
      ${row('Dials', p => p.dials, 'Box 3.0: one call to a household')}
      ${row('Completes', p => p.completes, 'Box 3.0: the dial on which the interview took place, 3 minutes or more')}
      ${row('Success rate', p => pct(p.success), 'Completes per dial')}
      ${row('Dials per complete', p => num(p.dpc, 1))}
      ${row('First-dial success', p => pct(p.first_rate), 'Completes on the first dial of a case, per first dial')}
      ${row('Enumerator-days', p => p.edays, 'Box 3.0: days with at least one dial')}
      ${row('Completes per enumerator-day', p => num(p.cpd, 1), 'Box 3.0')}
    </tbody></table>`;
    const hp = R.perf(all, tz);
    const lo = Math.min(C.cal.hours.start, ...hp.hours.map((h, i) => (h.dials ? i : 24))), hi = Math.max(C.cal.hours.end - 1, ...hp.hours.map((h, i) => (h.dials ? i : 0)));
    const hrs = []; for (let h = lo; h <= hi; h++) hrs.push(h);
    const chart = hourChart(hrs.map(h => ({ h, n: hp.hours[h].dials, ok: hp.hours[h].ok })));
    const tableH = `<table class="grid small"><thead><tr><th>Hour</th><th class="num">Dials</th><th class="num">Completes</th><th class="num">Success</th></tr></thead><tbody>${hrs.map(h => { const x = hp.hours[h]; return `<tr><td>${R.p2(h)}:00</td><td class="num">${x.dials}</td><td class="num">${x.ok}</td><td class="num">${x.dials >= 10 ? pct(x.ok / x.dials) : x.dials ? 'too few' : ''}</td></tr>`; }).join('')}</tbody></table>`;
    // the plan ahead
    const cal = C.cal, tk = todayKey(), open = C.list.filter(c => c.open);
    const ahead = {}; const addA = (k, f) => { ahead[k] = ahead[k] || { first: 0, cb: 0, redial: 0 }; ahead[k][f]++; };
    open.forEach(c => { if (!c.next.at) return; const k = R.partsIn(c.next.at, cal.tz).key; if (k < tk) return; addA(k, c.next.kind === 'callback' ? 'cb' : c.n ? 'redial' : 'first'); });
    const due = open.filter(c => c.next.due).length;
    const aheadRows = Object.keys(ahead).sort().slice(0, 12).map(k => `<tr><td>${dayLabel(k)}${cal.isWorking(k) ? '' : ' <span class="tag">non-working</span>'}</td><td class="num">${ahead[k].first}</td><td class="num">${ahead[k].redial}</td><td class="num">${ahead[k].cb}</td></tr>`).join('');
    const files = S.past.files;
    return `<div class="perf">
      <section><h3>My results</h3>${kpi}
        <p class="muted">Definitions from handbook Box 3.0. "This round so far" counts the calls logged in this session; the other columns add any earlier logs you load. ${files.length ? `Loaded: ${files.map(f => esc(f.name)).join(', ')}.` : 'No earlier logs loaded yet: use "Load earlier logs" above to compare with last month.'}</p></section>
      <section><h3>When my calls succeed</h3>
        <p class="muted">Share of dials started in each hour on which the interview took place, over all loaded logs. Hours with fewer than 10 dials are shown hatched: too few to judge. This is your own pattern. Across the programs, the handbook finds that dials later in the day succeed more often than those at midday (Section 3.5.1).</p>
        ${chart}<details><summary>Show as a table</summary>${tableH}</details></section>
      <section><h3>The plan ahead</h3>
        <p><b>${open.length}</b> household${open.length === 1 ? '' : 's'} still open · <b>${due}</b> due now · <b>${R.workingDaysLeft(cal, tk)}</b> working days left in the window.</p>
        ${aheadRows ? `<table class="grid small"><thead><tr><th>Day</th><th class="num">First dials</th><th class="num">Redials</th><th class="num">Callbacks</th></tr></thead><tbody>${aheadRows}</tbody></table>` : '<p class="muted">Nothing planned ahead.</p>'}
      </section></div>`;
  }
  function hourChart(rows) {
    const W = 640, H = 200, pl = 34, pb = 26, pt = 10, bw = (W - pl - 8) / Math.max(rows.length, 1);
    const y = v => pt + (H - pt - pb) * (1 - v);
    let bars = '';
    rows.forEach((r, i) => {
      const x = pl + i * bw + 3, rate = r.n ? r.ok / r.n : 0, few = r.n < 10;
      const top = y(rate), h = H - pb - top;
      if (r.n) bars += `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${(bw - 6).toFixed(1)}" height="${Math.max(h, 1).toFixed(1)}" rx="3" class="${few ? 'few' : 'bar'}"><title>${R.p2(r.h)}:00 — ${r.ok} completes of ${r.n} dials${few ? ' (too few to judge)' : ''}</title></rect>`;
      bars += `<text x="${(x + (bw - 6) / 2).toFixed(1)}" y="${H - 9}" class="ax" text-anchor="middle">${r.h}</text>`;
      if (r.n) bars += `<text x="${(x + (bw - 6) / 2).toFixed(1)}" y="${(top - 3).toFixed(1)}" class="lab" text-anchor="middle">${r.n}</text>`;
    });
    const grid = [0, 0.25, 0.5, 0.75, 1].map(v => `<line x1="${pl}" x2="${W - 4}" y1="${y(v)}" y2="${y(v)}" class="gl"/><text x="${pl - 4}" y="${y(v) + 4}" class="ax" text-anchor="end">${v * 100}%</text>`).join('');
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Success rate by hour of the day">
      <defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" class="hatch"/></pattern></defs>
      ${grid}${bars}<text x="${W - 4}" y="${pt + 2}" class="ax" text-anchor="end">bar label: dials</text></svg>`;
  }
  function logPanel(C) {
    const S = APP.S, chain = R.verifyChain(S.events, S.genesis);
    const ev = S.events.slice().reverse();
    const kindTxt = e => ({ dial: 'Call', correction: e.void ? 'Voided an entry' : 'Correction', action: R.ACTIONS[e.action] || e.action, contact_update: 'Phone number', export: 'Exported the log', session: e.what === 'started' ? 'Session started' : 'Assignment updated' }[e.type] || e.type);
    const detail = e => {
      if (e.type === 'dial') return `${statusLabel(e.status)} · number ${e.phone_slot} · ${isoWhen(e.ts)}${e.end_ts ? ' – ' + hm(R.parseTS(e.end_ts)) : ''}${e.appointment_ts ? ' · callback ' + isoWhen(e.appointment_ts) : ''}${e.action ? ' · ' + (R.ACTIONS[e.action] || e.action) : ''}${e.note ? ' · “' + esc(e.note) + '”' : ''}`;
      if (e.type === 'correction') return `${esc(e.reason || '')}${e.changes ? ' · changed: ' + Object.keys(e.changes).join(', ') : ''}`;
      if (e.type === 'action') return `${e.target_hhid ? 'replacement ' + esc(e.target_hhid) + ' · ' : ''}${esc(e.reason || '')}`;
      if (e.type === 'contact_update') return `number ${e.slot}: ${esc(e.change)}${e.label ? ' (' + esc(e.label) + ')' : ''}`;
      if (e.type === 'export') return esc(e.file_base) + ' · ' + e.event_count + ' events';
      if (e.type === 'session') return e.what === 'started' ? `from ${esc(e.file || 'the assignment file')}${e.fingerprint_ok === 0 ? ' · the file was changed after it was generated' : ''}` : `${e.households_added || 0} added, ${e.households_removed || 0} removed`;
      return '';
    };
    return `<p class="${chain.ok ? 'okline' : 'badline'}">${chain.ok ? `Integrity check passed: all ${chain.n} events are unchanged and in order.` : `Integrity check failed at event ${chain.index + 1}: ${esc(chain.reason)}.`} Every entry records who logged it and when; corrections are added as new entries, never written over the old ones.</p>
      <table class="grid small"><thead><tr><th>Logged</th><th>By</th><th>What</th><th>Household</th><th>Details</th></tr></thead><tbody>
      ${ev.map(e => `<tr${e.type === 'dial' ? ` data-act="open" data-hh="${esc(e.hhid)}"` : ''}><td>${isoWhen(e.logged_at)}</td><td>${esc(e.logged_by)}</td><td>${kindTxt(e)}</td><td class="id">${esc(e.hhid || '')}</td><td>${detail(e)}</td></tr>`).join('')}
      </tbody></table>`;
  }

  // ---- the household panel ----
  function drawer(C, now) {
    if (!APP.sel) return '';
    const c = C.map.get(APP.sel);
    if (!c) return '';
    const h = c.h, hist = h.history || {}, pl = h.plan || {}, A = APP.S.assignment;
    const inCall = APP.call && APP.call.hhid === c.hhid;
    const last3 = Array.isArray(hist.last3) ? hist.last3 : [];
    const usual = Number.isInteger(pl.target_hour) ? `${R.p2(pl.target_hour)}:00` : '';
    const tzNote = h.tz && h.tz !== C.cal.tz ? ` <span class="tag">their time zone: ${esc(h.tz)}</span>` : '';
    const phones = c.slots.map(s => `<div class="phone ${s.dead ? 'dead' : ''}">
        <div class="pslot">Number ${s.slot}${s.label ? ` · ${esc(s.label)}` : ''}${s.updated ? ' <span class="tag">updated</span>' : ''}</div>
        <div class="pnum"><span class="num-big">${esc(s.number || '(number not given)')}</span>
          <button class="subtle" data-act="copy" data-txt="${esc(s.number)}" aria-label="Copy number">Copy</button></div>
        <div class="pstate">${s.dials ? `${s.dials} dial${s.dials > 1 ? 's' : ''} this round, last: ${esc(statusLabel(s.last))}` : s.prior ? `last round: ${esc(statusLabel(s.prior))}` : 'not dialed this round'}${s.dead ? ' · <b>not working</b>' : ''}</div>
        ${c.open && !inCall && !APP.call ? `<button class="primary" data-act="call" data-slot="${s.slot}">Start call</button>` : ''}
      </div>`).join('') || '<p class="muted">No phone number for this household.</p>';
    const callBox = inCall ? callPanel(c) : '';
    const manual = APP.manual && !APP.call ? manualForm(c) : '';
    const dialRows = c.dials.map(d => {
      const isCorr = APP.correct === d.event_id;
      return `<li class="dial"><div><b>${d.attempt}.</b> ${hm(R.parseTS(d.ts))}${d.end_ts ? '–' + hm(R.parseTS(d.end_ts)) : ''} ${dayLabel(R.partsIn(R.parseTS(d.ts), C.cal.tz).key)} · number ${d.phone_slot} · <b>${esc(statusLabel(d.status))}</b>${d.dur_min !== null ? ` · ${num(d.dur_min, 1)} min` : ''}${d.appointment_ts ? ` · callback ${isoWhen(d.appointment_ts)}` : ''}${d.action ? ` · ${esc(R.ACTIONS[d.action])}` : ''}${d.corrected ? ' <span class="tag">corrected</span>' : ''}</div>
        ${d.note ? `<div class="muted">“${esc(d.note)}”</div>` : ''}
        ${isCorr ? correctionForm(d) : `<button class="link" data-act="correct" data-ev="${d.event_id}">Correct or void</button>`}</li>`;
    }).join('');
    const acts = c.actions.filter(a => a.via !== 'dial').map(a => `<li>${esc(R.ACTIONS[a.action] || a.action)}${a.target_hhid ? ' ' + esc(a.target_hhid) : ''} · ${isoWhen(a.logged_at)}${a.reason ? ' · ' + esc(a.reason) : ''}
        ${APP.correct === a.event_id ? correctionForm(null, a) : `<button class="link" data-act="correct" data-ev="${a.event_id}">Undo</button>`}</li>`).join('');
    const ra = replacementAllowed(c);
    const repl = c.replacements.length ? `<section class="sec"><h4>Replacements, in order</h4><ol class="repl">${c.replacements.map(r => `<li class="${r.active ? 'active' : ''}"><span class="id">${esc(r.hhid)}</span> ${esc((r.contact || {}).name || '')} ${r.active ? '<span class="tag ok">activated</span>' : ''}</li>`).join('')}</ol>
        ${c.open ? `<button ${ra.ok ? '' : 'disabled'} data-act="replace">Activate the next replacement</button> <span class="muted">${ra.ok ? '' : esc(ra.why)}</span>` : ''}</section>` : '';
    const next = c.next;
    return `<aside class="drawer" aria-label="Household ${esc(c.hhid)}">
      <div class="dhead"><div><div class="id big">${esc(c.hhid)}</div><div>${esc((h.contact || {}).name || '')}</div></div>
        <button class="subtle" data-act="closehh" aria-label="Close">✕</button></div>
      <div class="badges"><span class="st st-${c.state}">${stateLabel[c.state]}</span> <span class="tag">${esc(reasonText(h))}</span>${c.kind === 'replacement' ? ` <span class="tag">replaces ${esc(h.replaces)}</span>` : ''}${c.flags.switch_requested ? ' <span class="tag">switch asked</span>' : ''}</div>
      ${ruleName() !== 'keep_same' && RULE_WHY[ruleName()] ? `<details class="why"><summary>Why is this household with me?</summary><p class="muted small">${RULE_WHY[ruleName()]}</p></details>`
        : RULE_REASONS.has((h.assignment || {}).reason) ? `<details class="why"><summary>Why is this household with me?</summary><p class="muted small">${RULE_NOTE}</p></details>` : ''}
      ${c.flags.complete_short && c.open ? `<div class="alert warn">The complete you logged lasted under ${R.MIN_COMPLETE_MIN} minutes. Box 3.0 counts it as an appointment contact, not a complete, so the household stays open: call again, or correct the time if it is wrong.</div>` : ''}
      ${c.kind === 'removed' ? `<div class="alert info">This household is no longer in your assignment${h.removed_at ? ` (your leader's update, opened ${isoWhen(h.removed_at)})` : ''}. The calls you logged stay in your log and in your exports; you cannot log new calls for it.</div>` : ''}
      ${c.open ? `<div class="next k-${next.kind}"><b>Next:</b> ${next.at ? (next.at < R.now() ? 'overdue since ' : '') + when(next.at) + ' · ' : ''}${esc(next.text)}${next.holiday ? ` <span class="tag">${esc(next.holiday.name)}</span>` : ''}</div>` : ''}
      <dl class="facts">
        <dt>Usual time</dt><dd>${usual ? (hist.last_interview ? `${usual}, from the last interview` : `${usual}, planned by your leader (no interview yet)`) : 'not known'}${tzNote}</dd>
        <dt>Last interview</dt><dd>${hist.last_interview ? `round ${hist.last_interview.round}, ${dayLabel(hist.last_interview.date)}${Number.isInteger(hist.last_interview.hour) ? ' at ' + R.p2(hist.last_interview.hour) + ':00' : ''}` : 'none yet'}</dd>
        <dt>Last three rounds</dt><dd>${last3.length ? last3.map((x, i) => { const r = APP.S.assignment.round - 3 + i;
          return x === null || x === undefined ? `<span class="r3" title="round ${r}: not yet in the panel">${r} –</span>` : x ? `<span class="r3" title="round ${r}: interviewed">${r} <span class="dot yes">●</span></span>` : `<span class="r3" title="round ${r}: not interviewed">${r} <span class="dot no">○</span></span>`; }).join(' ') + ' <span class="muted small">● interviewed · ○ not</span>' : '–'}</dd>
        <dt>In the panel since</dt><dd>${hist.joined_round ? 'round ' + hist.joined_round : '–'}</dd>
        <dt>First dial planned</dt><dd>${pl.first_dial_date ? dayLabel(pl.first_dial_date) + (usual ? ' at ' + usual : '') : '–'}</dd>
        <dt>Sampling unit</dt><dd>${esc(h.psu || '')}${h.stratum ? ' · stratum ' + esc(h.stratum) : ''}</dd>
        ${h.note ? `<dt>Leader's note</dt><dd>${esc(h.note)}</dd>` : ''}
      </dl>
      <section class="sec"><h4>Phone numbers</h4>${phones}
        ${c.open && !APP.call ? `<button class="link" data-act="manual">Log a call made earlier</button> · ` : ''}${c.kind === 'removed' ? '' : '<button class="link" data-act="contact">Add or correct a number</button>'}
        ${APP.contact ? contactForm(c) : ''}</section>
      ${callBox}${manual}
      <section class="sec"><h4>Calls this round</h4>${dialRows ? `<ol class="dials">${dialRows}</ol>` : '<p class="muted">No call yet.</p>'}</section>
      ${c.open || acts ? `<section class="sec"><h4>Actions</h4>${acts ? `<ul class="acts">${acts}</ul>` : ''}
        ${c.open ? `<div class="btnrow"><button data-act="release">${R.ACTIONS.RELEASE}</button><button data-act="switch">Ask for another enumerator</button><button ${c.flags.all_dead || c.flags.no_phone ? '' : 'disabled title="Only when no number works"'} data-act="remove">Ask the leader to remove</button></div>` : ''}</section>` : ''}
      ${repl}
    </aside>`;
  }
  const statusButtons = (sel) => `<fieldset class="statuses"><legend>Result of the call</legend>${R.STATUS.map(s => `<label class="sopt s-${s.cat}"><input type="radio" name="status" value="${s.code}" ${sel === s.code ? 'checked' : ''}>${esc(s.label)}</label>`).join('')}</fieldset>`;
  const afterFields = (defAppt) => `<div class="row2"><label>Callback time, if one was agreed <input type="datetime-local" name="appointment" value="${defAppt || ''}"></label>
      <label>After this call <select name="action"><option value="">Keep calling</option><option value="RELEASE">${R.ACTIONS.RELEASE}</option><option value="SWITCH_REQUEST">Ask for another enumerator next round</option></select></label></div>
      <label>Note <input type="text" name="note" maxlength="300" placeholder="Operational only: no personal details"></label>`;
  function callPanel(c) {
    const k = APP.call;
    if (!k.end) {
      return `<section class="sec callbox live"><h4>On the phone · ${esc(c.hhid)} · number ${k.slot}</h4>
        <div class="timer"><span id="call-timer">00:00</span> since ${hm(k.start)}</div>
        <div class="btnrow"><button class="primary" data-act="endcall">End call</button><button class="subtle" data-act="cancelcall">Cancel (no call made)</button></div></section>`;
    }
    const mins = (k.end - k.start) / 60000;
    return `<section class="sec callbox"><h4>Call ended · ${esc(c.hhid)} · ${hm(k.start)}–${hm(k.end)} · ${num(mins, 1)} min · number ${k.slot}</h4>
      <form id="callform" novalidate onsubmit="return false">${statusButtons('')}${afterFields('')}
      <div class="btnrow"><button class="primary" data-act="savecall">Save call</button><button class="subtle" data-act="cancelcall">Discard</button></div></form></section>`;
  }
  function manualForm(c) {
    const now = R.now();
    return `<section class="sec callbox"><h4>Log a call made earlier</h4><p class="muted">The time you enter is the call's time; the log also records when you entered it.</p>
      <form id="callform" novalidate onsubmit="return false">
      <div class="row2"><label>Number <select name="slot">${c.slots.map(s => `<option value="${s.slot}">${s.slot}${s.label ? ' · ' + esc(s.label) : ''}</option>`).join('')}</select></label>
      <label>Started <input type="datetime-local" name="start" value="${toLocalInput(new Date(now.getTime() - 15 * 60000))}"></label>
      <label>Minutes <input type="number" name="minutes" min="0" step="0.1" value="1"></label></div>
      ${statusButtons('')}${afterFields('')}
      <div class="btnrow"><button class="primary" data-act="savemanual">Save call</button><button class="subtle" data-act="cancelmanual">Cancel</button></div></form></section>`;
  }
  function correctionForm(d, a) {
    if (a) {
      return `<form id="corrform" novalidate class="corr" onsubmit="return false"><p class="muted">Undoing keeps the action in the log, marked as undone.</p>
        <label>Why? <input type="text" name="reason" required></label>
        <div class="btnrow"><button class="primary" data-act="savecorr" data-ev="${a.event_id}" data-isaction="1">Undo</button><button class="subtle" data-act="cancelcorr">Cancel</button></div></form>`;
    }
    const st = R.parseTS(d.ts), mins = d.dur_min !== null ? d.dur_min : '';
    return `<form id="corrform" novalidate class="corr" onsubmit="return false">
      <div class="row2"><label>Result <select name="status">${R.STATUS.map(s => `<option value="${s.code}" ${s.code === d.status ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></label>
      <label>Number <input type="number" name="slot" min="1" value="${d.phone_slot}"></label>
      <label>Started <input type="datetime-local" name="start" value="${toLocalInput(st)}"></label>
      <label>Minutes <input type="number" name="minutes" min="0" step="0.1" value="${mins === '' ? '' : num(mins, 1)}"></label></div>
      <label>Callback time <input type="datetime-local" name="appointment" value="${d.appointment_ts ? toLocalInput(R.parseTS(d.appointment_ts)) : ''}"></label>
      <label>Note <input type="text" name="note" value="${esc(d.note || '')}"></label>
      <label class="inline"><input type="checkbox" name="void"> Void this entry (it was logged by mistake)</label>
      <label>Why are you correcting it? <input type="text" name="reason" required></label>
      <div class="btnrow"><button class="primary" data-act="savecorr" data-ev="${d.event_id}">Save correction</button><button class="subtle" data-act="cancelcorr">Cancel</button></div></form>`;
  }
  function contactForm(c) {
    return `<form id="contactform" novalidate class="corr" onsubmit="return false"><p class="muted">A new or corrected number goes to your leader in a separate contacts file when you export, never in the log for the common folder.</p>
      <div class="row2"><label>Which number <select name="slot">${c.slots.map(s => `<option value="${s.slot}">${s.slot}${s.label ? ' · ' + esc(s.label) : ''}</option>`).join('')}<option value="new">A new number</option></select></label>
      <label>Change <select name="change"><option value="correct">Correct this number</option><option value="mark_dead">Mark it as not working</option></select></label></div>
      <div class="row2"><label>Phone number <input type="tel" name="number" autocomplete="off"></label><label>Whose number <input type="text" name="label" placeholder="respondent, spouse, neighbor…"></label></div>
      <div class="btnrow"><button class="primary" data-act="savecontact">Save number</button><button class="subtle" data-act="cancelcontact">Cancel</button></div></form>`;
  }
  function modal() {
    const m = APP.modal; if (!m) return '';
    if (m.kind === 'export') {
      const X = APP.exportPack;
      return `<div class="scrim"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="mt"><h3 id="mt">Your log is ready</h3>
        <p>${R.plural(X.rows.length, 'call')}, ${R.plural(X.json.event_count, 'logged event')} in all${X.chain.ok ? ', integrity check passed' : ', <b>integrity check failed</b>'}.</p>
        <ol class="files"><li><button class="primary" data-act="dl" data-what="csv">Download ${esc(X.base)}.csv</button></li>
          <li><button class="primary" data-act="dl" data-what="json">Download ${esc(X.base)}.json</button></li>
          ${X.contacts ? `<li><button data-act="dl" data-what="contacts">Download ${esc(X.base)}_contacts.json</button> <span class="tag warn">has phone numbers</span>${X.contactsOut ? ' <span class="tag">protected</span>' : ''}</li>` : ''}</ol>
        <p>Put the <b>.csv</b> and <b>.json</b> files in the common folder. They hold household IDs, times and results, but no names or phone numbers.${X.contacts ? ' Give the <b>contacts</b> file to your leader directly, not through the common folder.' : ''} Each export holds the whole round so far, so a newer export replaces an older one.</p>
        <div class="btnrow"><button data-act="closemodal">Done</button></div></div></div>`;
    }
    if (m.kind === 'passphrase') {
      return `<div class="scrim"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="mt"><h3 id="mt">Protected file</h3>
        <p>${esc(m.file)} is protected with a passphrase. Enter the passphrase your leader gave you. It is used only on this computer and is not stored.</p>
        <label>Passphrase <input type="password" id="modal-input" autocomplete="off" ${m.busy ? 'disabled' : ''}></label>
        ${m.error ? `<p class="alert warn" role="alert">${esc(m.error)}</p>` : ''}
        <div class="btnrow"><button class="primary" data-act="unseal" ${m.busy ? 'disabled' : ''}>${m.busy ? 'Opening…' : 'Open'}</button><button class="subtle" data-act="closemodal">Cancel</button></div></div></div>`;
    }
    return `<div class="scrim"><div class="modal" role="dialog" aria-modal="true" aria-labelledby="mt"><h3 id="mt">${esc(m.title)}</h3><p>${esc(m.text)}</p>
      ${m.input ? `<label>${esc(m.input)} <input type="${m.password ? 'password' : 'text'}" id="modal-input" autocomplete="off"></label>` : ''}
      ${m.input2 ? `<label>${esc(m.input2)} <input type="${m.password ? 'password' : 'text'}" id="modal-input2" autocomplete="off"></label>` : ''}
      <div class="btnrow"><button class="primary" data-act="modalok">${esc(m.okLabel || 'OK')}</button>${m.altLabel ? `<button data-act="modalalt">${esc(m.altLabel)}</button>` : ''}<button class="subtle" data-act="closemodal">Cancel</button></div></div></div>`;
  }
  function leaderPlaceholder() {
    return `<section class="start"><h1>Team leader view</h1>
      <p class="lead">The leader view (assignment files for each enumerator, importing their logs, the merged log, progress, attrition and risk lists) is built in Step 3.</p>
      <p class="muted">Like the enumerator view, it will read only files you open and write only files you save or export, with no server, no shared database and no network connection.</p></section>`;
  }

  function render() {
    const root = $('#app');
    if (APP.view === 'leader') {
      root.innerHTML = topbar() + (window.LEAD ? window.LEAD.html() : leaderPlaceholder()) + modal();
      renderToasts();
      if (window.LEAD && window.LEAD.after) window.LEAD.after();
      return;
    }
    if (!APP.S) { root.innerHTML = topbar() + startScreen() + modal(); renderToasts(); return; }
    const now = R.now();
    const C = R.cases(APP.S, now); APP.C = C;
    if (APP.sel && !C.map.has(APP.sel)) APP.sel = null;
    const panels = { today: todayPanel, households: householdsPanel, calendar: calendarPanel, performance: perfPanel, log: logPanel };
    root.innerHTML = topbar() + summary(C, now) + tabs(C, now) + `<div class="body ${APP.sel ? 'with-drawer' : ''}"><main class="panel">${panels[APP.tab](C, now)}</main>${drawer(C, now)}</div>` + modal();
    renderToasts();
    if (APP.call && !APP.call.end) { const el = $('#call-timer'); if (el) { const s = Math.floor((now - APP.call.start) / 1000); el.textContent = `${R.p2(Math.floor(s / 60))}:${R.p2(s % 60)}`; } }
  }
  APP.render = render;
  // shared with the leader view (leader_view.js)
  APP.shell = { esc, pct, num, dayLabel, statusLabel, readText, toast: (t, k) => toast(t, k), download: (n, t, ty) => download(n, t, ty),
    askPassphrase: (f, env, then) => askPassphrase(f, env, then), confirmModal: (a, b, c, d) => confirmModal(a, b, c, d), render: () => render() };

  // ---- events ----
  const clearWarnings = () => { if (APP.toasts.some(t => t.kind === 'warn')) { APP.toasts = APP.toasts.filter(t => t.kind !== 'warn'); renderToasts(); } };
  APP.shell.clearWarnings = clearWarnings;
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-act]'); if (!el) return;
    clearWarnings();
    const act = el.dataset.act, c = APP.C && APP.sel ? APP.C.map.get(APP.sel) : null;
    switch (act) {
      case 'view': APP.view = el.dataset.v; render(); break;
      case 'tab': APP.tab = el.dataset.t; render(); break;
      case 'open': APP.sel = el.dataset.hh; APP.correct = null; APP.contact = false; APP.manual = false; render(); break;
      case 'closehh': if (APP.call && !APP.call.end) return toast('End the call first.', 'warn'); APP.sel = null; APP.call = null; render(); break;
      case 'filter': APP.filter = el.dataset.f; render(); break;
      case 'day': { const d = +el.dataset.d; APP.day = d === 0 ? null : R.addDaysKey(APP.day || todayKey(), d); if (APP.day === todayKey()) APP.day = null; render(); break; }
      case 'gotoday': APP.day = el.dataset.k === todayKey() ? null : el.dataset.k; APP.tab = 'today'; render(); break;
      case 'call': startCall(APP.sel, el.dataset.slot); break;
      case 'endcall': endCall(); break;
      case 'cancelcall': clearInterval(APP.timer); APP.call = null; render(); break;
      case 'savecall': saveCall(false); break;
      case 'manual': APP.manual = true; render(); break;
      case 'cancelmanual': APP.manual = false; render(); break;
      case 'savemanual': saveCall(true); break;
      case 'correct': APP.correct = el.dataset.ev; render(); break;
      case 'cancelcorr': APP.correct = null; render(); break;
      case 'savecorr': saveCorrection(el.dataset.ev, !!el.dataset.isaction); break;
      case 'release': if (c) doAction(c, 'RELEASE'); break;
      case 'switch': if (c) doAction(c, 'SWITCH_REQUEST'); break;
      case 'remove': if (c) doAction(c, 'REMOVE_REQUEST'); break;
      case 'replace': if (c) activateReplacement(c); break;
      case 'contact': APP.contact = !APP.contact; render(); break;
      case 'cancelcontact': APP.contact = false; render(); break;
      case 'savecontact': saveContact(); break;
      case 'copy': { const t = el.dataset.txt; if (navigator.clipboard && t) navigator.clipboard.writeText(t).then(() => toast('Number copied.'), () => toast('Copy it by hand: ' + t, 'warn')); break; }
      case 'save': saveSession(); break;
      case 'export': exportLog(); break;
      case 'dl': { const X = APP.exportPack, w = el.dataset.what;
        if (w === 'csv') download(X.base + '.csv', X.csv, 'text/csv');
        if (w === 'json') download(X.base + '.json', JSON.stringify(X.json, null, 1), 'application/json');
        if (w === 'contacts') download(X.base + '_contacts.json', JSON.stringify(X.contactsOut || X.contacts, null, 1), 'application/json');
        el.textContent = 'Downloaded ✓'; break; }
      case 'closemodal': APP.modal = null; render(); break;
      case 'unseal': tryPassphrase(); break;
      case 'modalalt': { const m = APP.modal; APP.modal = null; render(); if (m && m.onAlt) m.onAlt(); break; }
      case 'modalok': { const m = APP.modal, i = $('#modal-input'), i2 = $('#modal-input2');
        const v = i ? (m.password ? i.value : i.value.trim()) : '', v2 = i2 ? (m.password ? i2.value : i2.value.trim()) : '';
        if (m.required && !v) return toast('Please write the reason.', 'warn');
        APP.modal = null; m.onOk(v, v2); render(); break; }
      case 'close': {
        const closeIt = () => { APP.S = null; APP.sel = null; APP.call = null; APP.unsaved = 0; APP.fileHandle = null; APP.loadWarnings = []; render(); };
        if (!APP.unsaved) { confirmModal('Close this session', 'Your session is saved. You can continue later by opening the saved session file.', { okLabel: 'Close session' }, closeIt); break; }
        confirmModal('Close this session', `${R.plural(APP.unsaved, 'change')} ${APP.unsaved === 1 ? 'is' : 'are'} not saved. Save your session first, or ${APP.unsaved === 1 ? 'it' : 'they'} will be lost.`,
          { okLabel: 'Save, then close', altLabel: 'Close without saving', onAlt: closeIt }, async () => { await saveSession(); if (!APP.unsaved) closeIt(); });
        break;
      }
    }
  });
  document.addEventListener('change', e => {
    const t = e.target;
    if (t.id === 'f-assign' && t.files[0]) openAssignment(t.files[0]);
    else if (t.id === 'f-project' && t.files[0]) openProject(t.files[0]);
    else if (t.id === 'f-past' && t.files.length) openPast([...t.files]);
    else if (t.id === 'f-update' && t.files[0]) openAssignment(t.files[0]);
  });
  document.addEventListener('input', e => {
    if (e.target.id === 'hh-search') { APP.q = e.target.value; const C = APP.C; const tbl = $('#hh-table'); if (tbl) { APP.tab = 'households'; render(); const s = $('#hh-search'); if (s) { s.focus(); s.setSelectionRange(s.value.length, s.value.length); } } }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.matches && e.target.matches('tr[data-act="open"]')) e.target.click();
    if (e.key === 'Escape' && APP.modal) { APP.modal = null; render(); }
    if (e.key === 'Enter' && e.target.id === 'modal-input' && APP.modal && APP.modal.kind === 'passphrase') { e.preventDefault(); tryPassphrase(); }
  });
  window.addEventListener('beforeunload', e => { if (APP.unsaved > 0 || (window.LEAD && window.LEAD.unsavedCount() > 0)) { e.preventDefault(); e.returnValue = ''; } });
  // refresh what is due every minute, without disturbing a form in progress
  setInterval(() => { if (APP.S && !APP.call && !APP.manual && !APP.correct && !APP.contact && !APP.modal && !document.activeElement.matches('input,select,textarea')) render(); }, 60000);
  document.addEventListener('DOMContentLoaded', render);
  if (document.readyState !== 'loading') render();
})();
