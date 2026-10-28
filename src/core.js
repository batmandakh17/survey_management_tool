/* RTM interview tool: core logic, no DOM.
   Formats: PROPOSAL.md section A and formats/README.md. Vocabulary: handbook Box 3.0 and Box 2.0.
   Everything here is deterministic given the session and the clock (RTM.now), so it can be tested. */
'use strict';
(function (G) {
  const RTM = {};
  RTM.VERSION = '0.2.0';
  RTM.SCHEMA = { assign: 'rtm-assign-1.0', calllog: 'rtm-calllog-1.0', project: 'rtm-project-1.0', contacts: 'rtm-contacts-1.0' };
  RTM.MIN_COMPLETE_MIN = 3;            // Box 3.0: a complete is the first dial coded complete that lasted 3 minutes or more

  // ---- dial dispositions (A.4); the program maps its own codes onto these once, in the leader view ----
  RTM.STATUS = [
    { code: 'COMPLETE', label: 'Complete', cat: 'complete', contact: true },
    { code: 'APPOINTMENT', label: 'Appointment booked', cat: 'contact', contact: true },
    { code: 'PARTIAL', label: 'Partial interview', cat: 'contact', contact: true },
    { code: 'NOT_AVAILABLE', label: 'Respondent not available', cat: 'contact', contact: true },
    { code: 'NO_ANSWER', label: 'No answer', cat: 'noncontact' },
    { code: 'BUSY', label: 'Busy', cat: 'noncontact' },
    { code: 'SWITCHED_OFF', label: 'Switched off / unreachable', cat: 'noncontact' },
    { code: 'DEAD_NUMBER', label: 'Number not in service', cat: 'number' },
    { code: 'WRONG_NUMBER', label: 'Wrong number', cat: 'number' },
    { code: 'REFUSAL_SOFT', label: 'Refusal (may retry)', cat: 'refusal', contact: true },
    { code: 'REFUSAL_HARD', label: 'Refusal (do not retry)', cat: 'refusal', contact: true },
    { code: 'LANGUAGE', label: 'Language barrier', cat: 'contact', contact: true },
    { code: 'OTHER', label: 'Other (write a note)', cat: 'contact' },
  ];
  RTM.STATUS_BY = Object.fromEntries(RTM.STATUS.map(s => [s.code, s]));
  RTM.DEAD = new Set(['DEAD_NUMBER', 'WRONG_NUMBER']);
  // case actions: actions, not dispositions (handbook 3.3 box)
  RTM.ACTIONS = {
    RELEASE: 'Release for this round',
    SWITCH_REQUEST: 'Ask the leader to switch enumerator next round',
    REMOVE_REQUEST: 'Ask the leader to remove (no number works)',
    ACTIVATE_REPLACEMENT: 'Activate a replacement household',
  };
  RTM.REASONS = {
    keep: 'Kept with you: the same enumerator as before',
    rotation: 'Rotation: part of the planned share moved between enumerators',
    switch_hard_to_reach: 'Switched to you: hard to reach with the previous enumerator',
    enumerator_unavailable: 'Moved to you: the previous enumerator is away',
    new: 'New to the panel',
    manual: 'Assigned by hand',
    rule: 'Dealt to you by this round’s rule',
    capacity: 'Moved to balance workloads',
    replacement: 'Replacement household',
  };

  // ---- clock: tests can fix "now"; it then advances with real time ----
  let fixedClock = null;
  RTM.setNow = iso => { fixedClock = iso ? { t: Date.parse(iso), at: Date.now() } : null; };
  RTM.now = () => (fixedClock ? new Date(fixedClock.t + (Date.now() - fixedClock.at)) : new Date());

  // ---- SHA-256 (FIPS 180-4), synchronous and identical in every browser and in Python's hashlib ----
  const K = new Uint32Array([
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
  function sha256Bytes(msg) {
    const l = msg.length, bitLenHi = Math.floor(l / 0x20000000), bitLenLo = (l * 8) >>> 0;
    const nBlocks = ((l + 9 + 63) >> 6);
    const buf = new Uint8Array(nBlocks * 64);
    buf.set(msg); buf[l] = 0x80;
    const dv = new DataView(buf.buffer);
    dv.setUint32(buf.length - 8, bitLenHi); dv.setUint32(buf.length - 4, bitLenLo);
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const W = new Uint32Array(64);
    for (let b = 0; b < nBlocks; b++) {
      for (let t = 0; t < 16; t++) W[t] = dv.getUint32(b * 64 + t * 4);
      for (let t = 16; t < 64; t++) {
        const x = W[t - 15], y = W[t - 2];
        const s0 = ((x >>> 7) | (x << 25)) ^ ((x >>> 18) | (x << 14)) ^ (x >>> 3);
        const s1 = ((y >>> 17) | (y << 15)) ^ ((y >>> 19) | (y << 13)) ^ (y >>> 10);
        W[t] = (W[t - 16] + s0 + W[t - 7] + s1) >>> 0;
      }
      let a = H[0], bb = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (let t = 0; t < 64; t++) {
        const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        const ch = (e & f) ^ (~e & g);
        const t1 = (h + S1 + ch + K[t] + W[t]) >>> 0;
        const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        const maj = (a & bb) ^ (a & c) ^ (bb & c);
        const t2 = (S0 + maj) >>> 0;
        h = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = bb; bb = a; a = (t1 + t2) >>> 0;
      }
      H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + bb) >>> 0; H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
      H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0; H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
    }
    return Array.from(H, x => x.toString(16).padStart(8, '0')).join('');
  }
  RTM.sha256 = str => sha256Bytes(new TextEncoder().encode(str));

  // ---- canonical JSON: sorted keys, no spaces, empty values dropped; the same as Python's
  //      json.dumps(o, sort_keys=True, separators=(',', ':'), ensure_ascii=False) on cleaned objects ----
  RTM.canon = function canon(v) {
    if (v === null || typeof v !== 'object') return JSON.stringify(v);
    if (Array.isArray(v)) return '[' + v.map(canon).join(',') + ']';
    const ks = Object.keys(v).filter(k => v[k] !== undefined).sort();
    return '{' + ks.map(k => JSON.stringify(k) + ':' + canon(v[k])).join(',') + '}';
  };
  // drop undefined, null and empty strings, so that an absent field and an empty one hash the same everywhere
  RTM.clean = o => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== ''));

  RTM.uuid = () => {
    const b = new Uint8Array(16);
    if (G.crypto && G.crypto.getRandomValues) G.crypto.getRandomValues(b);
    else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
    b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
    const h = Array.from(b, x => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  };

  // ---- time ----
  const p2 = n => String(n).padStart(2, '0');
  RTM.p2 = p2;
  RTM.localISO = d => {
    const off = -d.getTimezoneOffset(), s = off >= 0 ? '+' : '-', a = Math.abs(off);
    return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}T${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}${s}${p2(Math.floor(a / 60))}:${p2(a % 60)}`;
  };
  RTM.parseTS = s => (s ? new Date(Date.parse(s)) : null);
  // '1 dial', '2 dials'; irregular plurals are given
  RTM.plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + 's')}`;
  RTM.wallFromISO = iso => (iso ? iso.slice(0, 19).replace('T', ' ') : '');
  RTM.offsetFromISO = iso => { const m = /([+-]\d\d:\d\d|Z)$/.exec(iso || ''); return m ? (m[1] === 'Z' ? '+00:00' : m[1]) : ''; };
  const dtfCache = {};
  function dtf(tz) {
    if (!dtfCache[tz]) dtfCache[tz] = new Intl.DateTimeFormat('en-US', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
    return dtfCache[tz];
  }
  RTM.validTZ = tz => { if (!tz) return false; try { dtf(tz); return true; } catch (e) { return false; } };
  // date parts of an instant in a time zone (device local when tz is empty or unknown)
  RTM.partsIn = (date, tz) => {
    let y, m, d, h, mi, s;
    if (tz && RTM.validTZ(tz)) {
      const p = {}; dtf(tz).formatToParts(date).forEach(x => { if (x.type !== 'literal') p[x.type] = +x.value; });
      y = p.year; m = p.month; d = p.day; h = p.hour % 24; mi = p.minute; s = p.second;
    } else { y = date.getFullYear(); m = date.getMonth() + 1; d = date.getDate(); h = date.getHours(); mi = date.getMinutes(); s = date.getSeconds(); }
    const key = `${y}-${p2(m)}-${p2(d)}`;
    return { y, m, d, h, mi, s, key, wd: RTM.weekdayOfKey(key) };
  };
  RTM.weekdayOfKey = key => { const [Y, M, D] = key.split('-').map(Number); const w = new Date(Date.UTC(Y, M - 1, D)).getUTCDay(); return w === 0 ? 7 : w; };
  RTM.addDaysKey = (key, n) => { const [Y, M, D] = key.split('-').map(Number); const t = new Date(Date.UTC(Y, M - 1, D + n)); return `${t.getUTCFullYear()}-${p2(t.getUTCMonth() + 1)}-${p2(t.getUTCDate())}`; };
  RTM.daysBetweenKeys = (a, b) => { const f = k => { const [Y, M, D] = k.split('-').map(Number); return Date.UTC(Y, M - 1, D); }; return Math.round((f(b) - f(a)) / 864e5); };
  function tzOffsetMin(date, tz) {
    const p = RTM.partsIn(date, tz);
    return Math.round((Date.UTC(p.y, p.m - 1, p.d, p.h, p.mi, p.s) - Math.floor(date.getTime() / 1000) * 1000) / 60000);
  }
  // the instant of a wall-clock time in a time zone (device local when tz is empty or unknown)
  RTM.zoned = (key, h, mi, tz) => {
    const [Y, M, D] = key.split('-').map(Number);
    if (!(tz && RTM.validTZ(tz))) return new Date(Y, M - 1, D, h, mi || 0, 0);
    const guess = Date.UTC(Y, M - 1, D, h, mi || 0, 0);
    let t = guess - tzOffsetMin(new Date(guess), tz) * 60000;
    const off2 = tzOffsetMin(new Date(t), tz);
    t = guess - off2 * 60000;
    return new Date(t);
  };
  RTM.isDateKey = s => typeof s === 'string' && /^\d{4}-\d\d-\d\d$/.test(s) && !isNaN(Date.parse(s + 'T00:00:00Z'));

  // ---- CSV (RFC 4180), no byte-order mark so that pandas and Stata read the first column name as written ----
  RTM.parseCSV = text => {
    text = String(text).replace(/^\uFEFF/, '');
    const rows = []; let row = [], f = '', q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += c;
      } else if (c === '"') q = true;
      else if (c === ',') { row.push(f); f = ''; }
      else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(f); rows.push(row); row = []; f = ''; }
      else f += c;
    }
    if (f !== '' || row.length) { row.push(f); rows.push(row); }
    const nonEmpty = rows.filter(r => r.some(x => x !== ''));
    if (!nonEmpty.length) return [];
    const head = nonEmpty[0].map(h => h.trim());
    return nonEmpty.slice(1).map(r => Object.fromEntries(head.map((h, i) => [h, r[i] === undefined ? '' : r[i]])));
  };
  const csvField = v => { const s = v === undefined || v === null ? '' : String(v); return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  RTM.toCSV = (rows, cols) => [cols.join(','), ...rows.map(r => cols.map(c => csvField(r[c])).join(','))].join('\n') + '\n';

  // ---- assignment file: fingerprint and validation (A.3) ----
  RTM.fingerprint = A => { const o = Object.assign({}, A); delete o.fingerprint; return RTM.sha256(RTM.canon(o)); };
  RTM.validateAssignment = A => {
    const errors = [], warnings = [];
    const err = m => errors.push(m), warn = m => warnings.push(m);
    if (!A || typeof A !== 'object') return { errors: ['This is not an assignment file (not a JSON object).'], warnings };
    if (A.schema !== RTM.SCHEMA.assign) err(`This is not an assignment file: its schema is "${A.schema || 'missing'}", expected "${RTM.SCHEMA.assign}".`);
    ['program', 'enumerator_id', 'generated_by', 'generated_at'].forEach(k => { if (!A[k] || typeof A[k] !== 'string') err(`The header lacks "${k}".`); });
    if (!Number.isInteger(A.round) || A.round < 1) err('The header lacks a valid round number.');
    const c = A.calendar;
    if (!c || typeof c !== 'object') err('The file has no calendar.');
    else {
      if (!RTM.isDateKey(c.window_start) || !RTM.isDateKey(c.window_end)) err('The calendar needs window_start and window_end as dates (YYYY-MM-DD).');
      else if (c.window_end < c.window_start) err('The window ends before it starts.');
      if (!Array.isArray(c.working_weekdays) || !c.working_weekdays.length || c.working_weekdays.some(x => !Number.isInteger(x) || x < 1 || x > 7)) err('working_weekdays must list weekdays 1 (Monday) to 7 (Sunday).');
      const ch = c.call_hours || {};
      if (!Number.isInteger(ch.start) || !Number.isInteger(ch.end) || ch.start < 0 || ch.end > 24 || ch.start >= ch.end) err('call_hours needs whole-hour start and end, start before end.');
      if (!Number.isInteger(c.dial_cap) || c.dial_cap < 1) err('dial_cap (the stopping rule in dials) must be a positive whole number.');
      if (c.time_zone && !RTM.validTZ(c.time_zone)) warn(`The time zone "${c.time_zone}" is not known to this browser; the device's time zone is used.`);
      (c.holidays || []).forEach(h => { if (!RTM.isDateKey(h.date)) err(`A holiday has an invalid date: ${h.date}`); });
      if (c.ramadan && c.ramadan.dates && !Number.isInteger(c.ramadan.break_fast_hour)) warn('Ramadan dates are given without the hour the fast is broken.');
    }
    if (!Array.isArray(A.households) || !A.households.length) err('The file lists no households.');
    else {
      const seen = new Set(), rseen = new Set();
      A.households.forEach((h, i) => {
        const where = `Household ${i + 1}${h && h.hhid ? ' (' + h.hhid + ')' : ''}`;
        if (!h || typeof h.hhid !== 'string' || !h.hhid) { err(`${where} has no household ID (hhid, as text).`); return; }
        if (seen.has(h.hhid)) err(`Household ${h.hhid} appears twice.`);
        seen.add(h.hhid);
        const ph = (h.contact && h.contact.phones) || [];
        if (!ph.length) warn(`Household ${h.hhid} has no phone number.`);
        ph.forEach(p => { if (!Number.isInteger(p.slot) || p.slot < 1) err(`Household ${h.hhid} has a phone without a slot number.`); });
        const reason = h.assignment && h.assignment.reason;
        if (reason && !RTM.REASONS[reason]) warn(`Household ${h.hhid} has an unknown assignment reason "${reason}".`);
        const plan = h.plan || {};
        if (plan.first_dial_date && !RTM.isDateKey(plan.first_dial_date)) err(`Household ${h.hhid} has an invalid first-dial date.`);
        if (c && plan.first_dial_date && RTM.isDateKey(c.window_start) && (plan.first_dial_date < c.window_start || plan.first_dial_date > c.window_end)) warn(`Household ${h.hhid}'s first dial is planned outside the window.`);
        if (plan.target_hour !== undefined && (!Number.isInteger(plan.target_hour) || plan.target_hour < 0 || plan.target_hour > 23)) err(`Household ${h.hhid} has an invalid target hour.`);
        (h.replacements || []).forEach(r => {
          if (!r || !r.hhid) err(`Household ${h.hhid} has a replacement without an ID.`);
          else if (rseen.has(r.hhid)) err(`Replacement ${r.hhid} is listed for two households.`);
          else rseen.add(r.hhid);
        });
      });
      rseen.forEach(r => { if (seen.has(r)) err(`Replacement ${r} is also a main household.`); });
    }
    if (A.fingerprint && errors.length === 0 && RTM.fingerprint(A) !== A.fingerprint) warn('The file was changed after the leader generated it: its fingerprint does not match. The log will record this.');
    if (!A.fingerprint) warn('The file has no fingerprint, so changes made after it was generated cannot be detected.');
    return { errors, warnings };
  };

  // ---- the session and its append-only event log (A.4, A.6 integrity) ----
  RTM.newSession = A => {
    const fp = RTM.fingerprint(A);
    return { assignment: A, fingerprint: fp, genesis: fp, events: [], past: { files: [], dials: [] }, last_export: null, last_save: null, ui: {} };
  };
  RTM.publicPart = e => { const o = Object.assign({}, e); delete o.hash; delete o.private; return o; };
  // what leaves the device: the event with its hash, without the private part (phone numbers stay in the contacts file)
  RTM.exportEvent = e => { const o = Object.assign({}, e); delete o.private; return o; };
  RTM.append = (S, type, fields, privatePart) => {
    const A = S.assignment;
    const prev = S.events.length ? S.events[S.events.length - 1].hash : S.genesis;
    const e = RTM.clean(Object.assign({ event_id: RTM.uuid(), type, program: A.program, round: A.round }, fields,
      { logged_by: A.enumerator_id, logged_at: RTM.localISO(RTM.now()), prev_hash: prev }));
    if (privatePart) e.private_digest = RTM.sha256(RTM.canon(RTM.clean(privatePart)));
    e.hash = RTM.sha256(RTM.canon(RTM.publicPart(e)));
    if (privatePart) e.private = RTM.clean(privatePart);
    S.events.push(e);
    return e;
  };
  RTM.verifyChain = (events, genesis) => {
    let prev = genesis;
    for (let i = 0; i < events.length; i++) {
      const e = events[i];
      if (e.prev_hash !== prev) return { ok: false, index: i, reason: 'an event is missing or out of order before this one' };
      if (RTM.sha256(RTM.canon(RTM.publicPart(e))) !== e.hash) return { ok: false, index: i, reason: 'this event was changed after it was logged' };
      if (e.private && RTM.sha256(RTM.canon(e.private)) !== e.private_digest) return { ok: false, index: i, reason: 'the contact details of this event were changed' };
      prev = e.hash;
    }
    return { ok: true, n: events.length, last: prev };
  };

  // ---- effective log: corrections applied, voided rows removed, dial numbers per case (Box 3.0) ----
  RTM.effective = S => {
    const byId = new Map(), dials = [], actions = [], contacts = [];
    for (const e of S.events) {
      if (e.type === 'dial') { const d = Object.assign({}, e, { corrected: 0 }); byId.set(e.event_id, d); dials.push(d); }
      else if (e.type === 'action') { const a = Object.assign({}, e, { corrected: 0 }); byId.set(e.event_id, a); actions.push(a); }
      else if (e.type === 'contact_update') contacts.push(e);
    }
    for (const e of S.events) {
      if (e.type !== 'correction') continue;
      const t = byId.get(e.target);
      if (!t) continue;
      if (e.void) t.void = true; else Object.assign(t, e.changes || {});
      t.corrected = 1;
      (t.corrections = t.corrections || []).push(e.event_id);
    }
    const live = dials.filter(d => !d.void);
    live.sort((a, b) => (a.hhid < b.hhid ? -1 : a.hhid > b.hhid ? 1 : (Date.parse(a.ts) - Date.parse(b.ts)) || (a.logged_at < b.logged_at ? -1 : 1)));
    const n = {};
    for (const d of live) {
      n[d.hhid] = (n[d.hhid] || 0) + 1;
      d.attempt = n[d.hhid];
      d.dur_min = d.end_ts ? Math.max(0, (Date.parse(d.end_ts) - Date.parse(d.ts)) / 60000) : null;
    }
    const viaDial = live.filter(d => d.action).map(d => ({ event_id: d.event_id, type: 'action', hhid: d.hhid, action: d.action,
      logged_by: d.logged_by, logged_at: d.logged_at, via: 'dial', corrected: d.corrected }));
    const standalone = actions.filter(a => !a.void);
    return { dials: live, actions: standalone.concat(viaDial), standaloneActions: standalone, allActions: actions, contacts };
  };

  // ---- calendar (D): working days, holidays, Ramadan, call hours ----
  RTM.calendarOf = A => {
    const c = A.calendar;
    const hol = new Map((c.holidays || []).map(h => [h.date, h]));
    const tz = c.time_zone && RTM.validTZ(c.time_zone) ? c.time_zone : null;
    const ram = new Set((c.ramadan && c.ramadan.dates) || []);
    return {
      raw: c, tz, start: c.window_start, end: c.window_end, cap: c.dial_cap, hours: c.call_hours,
      holiday: k => hol.get(k) || null,
      isWorking: k => c.working_weekdays.includes(RTM.weekdayOfKey(k)) && !(hol.has(k) && !hol.get(k).working),
      inWindow: k => k >= c.window_start && k <= c.window_end,
      isRamadan: k => ram.has(k),
      breakFastHour: c.ramadan && Number.isInteger(c.ramadan.break_fast_hour) ? c.ramadan.break_fast_hour : null,
    };
  };
  RTM.bundledHolidays = country => (((G.RTM_HOLIDAYS || {}).table || {})[country] || []).map(([date, name, est]) => ({ date, name, estimated: !!est, bundled: true }));
  RTM.workingDaysLeft = (cal, fromKey) => { let k = fromKey < cal.start ? cal.start : fromKey, n = 0; while (k <= cal.end) { if (cal.isWorking(k)) n++; k = RTM.addDaysKey(k, 1); } return n; };

  // ---- phone slots, with this round's contact updates and dial results ----
  function slotsFor(h, contacts, dials) {
    const slots = ((h.contact && h.contact.phones) || []).map(p => ({ slot: p.slot, number: p.number || '', label: p.label || '', prior: p.last_status || '', updated: false }));
    for (const c of contacts) {
      if (c.hhid !== h.hhid) continue;
      let s = slots.find(x => x.slot === c.slot);
      const num = c.private && c.private.number;
      if (!s) { s = { slot: c.slot, number: num || '', label: c.label || '', prior: '', updated: true }; slots.push(s); continue; }
      if (c.change === 'mark_dead') { s.marked_dead = true; continue; }
      if (num) s.number = num;
      if (c.label) s.label = c.label;
      s.updated = true; s.prior = ''; s.marked_dead = false;
    }
    for (const s of slots) {
      const ds = dials.filter(d => d.phone_slot === s.slot);
      s.dials = ds.length;
      s.last = ds.length ? ds[ds.length - 1].status : '';
      s.dead = !!s.marked_dead || (ds.length ? RTM.DEAD.has(s.last) : RTM.DEAD.has(s.prior));
    }
    return slots.sort((a, b) => a.slot - b.slot);
  }

  // ---- the case universe: assigned households plus activated replacements ----
  RTM.householdsOf = (S, eff) => {
    const A = S.assignment, cal = RTM.calendarOf(A);
    const list = A.households.map(h => Object.assign({}, h, { kind: 'main' }));
    const repl = new Map();
    A.households.forEach(h => (h.replacements || []).forEach((r, i) => repl.set(r.hhid, { r, main: h, rank: r.rank || i + 1 })));
    for (const a of eff.actions) {
      if (a.action !== 'ACTIVATE_REPLACEMENT' || !a.target_hhid || !repl.has(a.target_hhid)) continue;
      const { r, main } = repl.get(a.target_hhid);
      if (list.some(x => x.hhid === r.hhid)) continue;
      list.push({ hhid: r.hhid, psu: main.psu, stratum: main.stratum, contact: r.contact || { phones: [] }, tz: main.tz,
        history: { joined_round: A.round }, assignment: { reason: 'replacement' },
        plan: { first_dial_date: RTM.partsIn(RTM.parseTS(a.logged_at), cal.tz).key, target_hour: (main.plan || {}).target_hour },
        replaces: main.hhid, kind: 'replacement', activated_at: a.logged_at });
    }
    // households taken out by an updated assignment stay visible, read-only, with the calls already logged (section B)
    const listed = new Set(list.map(x => x.hhid)), gone = new Map();
    for (const e of S.events) {
      if (e.type !== 'session' || e.what !== 'assignment_updated') continue;
      (e.removed_hhids || []).forEach(id => gone.set(id, e.logged_at));
      (e.added_hhids || []).forEach(id => gone.delete(id));
    }
    eff.dials.forEach(d => { if (!listed.has(d.hhid) && !gone.has(d.hhid)) gone.set(d.hhid, null); });
    for (const [id, at] of gone) {
      if (!listed.has(id)) list.push({ hhid: id, contact: { phones: [] }, history: {}, assignment: {}, plan: {}, kind: 'removed', removed_at: at });
    }
    return list;
  };
  RTM.replacementPool = A => { const m = new Map(); A.households.forEach(h => (h.replacements || []).forEach((r, i) => m.set(r.hhid, { r, main: h.hhid, rank: r.rank || i + 1 }))); return m; };

  // ---- case states and the next suggested dial (D) ----
  RTM.cases = (S, now) => {
    const A = S.assignment, cal = RTM.calendarOf(A), eff = RTM.effective(S);
    const byHH = new Map();
    for (const d of eff.dials) { if (!byHH.has(d.hhid)) byHH.set(d.hhid, []); byHH.get(d.hhid).push(d); }
    const acts = new Map();
    for (const a of eff.actions) { if (!acts.has(a.hhid)) acts.set(a.hhid, []); acts.get(a.hhid).push(a); }
    const pool = RTM.replacementPool(A);
    const out = RTM.householdsOf(S, eff).map(h => {
      const ds = byHH.get(h.hhid) || [], as = acts.get(h.hhid) || [];
      const slots = slotsFor(h, eff.contacts, ds);
      // Box 3.0: a complete needs 3 minutes; a shorter complete-coded dial is an appointment contact, so the household stays open
      const cmpAny = ds.find(d => d.status === 'COMPLETE');
      const cmp = ds.find(d => d.status === 'COMPLETE' && (d.dur_min === null || d.dur_min === undefined || d.dur_min >= RTM.MIN_COMPLETE_MIN));
      const has = code => as.some(a => a.action === code);
      const last = ds.length ? ds[ds.length - 1] : null;
      let state;
      if (cmp) state = 'complete';
      else if (h.kind === 'removed') state = 'reassigned';
      else if (has('ACTIVATE_REPLACEMENT')) state = 'replaced';
      else if (has('RELEASE')) state = 'released';
      else if (has('REMOVE_REQUEST')) state = 'remove_requested';
      else state = ds.length ? 'in_progress' : 'not_started';
      const open = h.kind !== 'removed' && (state === 'in_progress' || state === 'not_started');
      const flags = {
        hard_refusal: ds.some(d => d.status === 'REFUSAL_HARD'),
        all_dead: slots.length > 0 && slots.every(s => s.dead),
        no_phone: slots.length === 0,
        switch_requested: has('SWITCH_REQUEST'),
        complete_short: !!(cmpAny && !cmp),
        cap_reached: ds.length >= cal.cap,
      };
      const appointment = last && last.appointment_ts && ['APPOINTMENT', 'PARTIAL', 'NOT_AVAILABLE', 'REFUSAL_SOFT', 'OTHER', 'LANGUAGE'].includes(last.status) ? RTM.parseTS(last.appointment_ts) : null;
      const myRepl = (h.replacements || []).map((r, i) => Object.assign({ rank: r.rank || i + 1 }, r, { active: false }));
      const c = { h, hhid: h.hhid, kind: h.kind, dials: ds, n: ds.length, last, actions: as, slots, state, open, flags, appointment, replacements: myRepl, complete: cmp || null };
      c.next = RTM.suggest(c, cal, now);
      return c;
    });
    // mark which replacements are active, and which household each activated replacement replaced
    const active = new Set(out.filter(c => c.kind === 'replacement').map(c => c.hhid));
    out.forEach(c => c.replacements.forEach(r => { r.active = active.has(r.hhid); }));
    return { list: out, map: new Map(out.map(c => [c.hhid, c])), cal, eff, pool };
  };

  RTM.suggest = (c, cal, now) => {
    if (!c.open) return { kind: 'none', text: '' };
    if (c.flags.hard_refusal) return { kind: 'refusal', text: 'Hard refusal: release it for this round' };
    if (c.flags.no_phone) return { kind: 'dead', text: 'No phone number: add one if you have it, or ask the leader to remove it' };
    if (c.flags.all_dead) return { kind: 'dead', text: 'No working number left: ask the leader to remove it, or activate a replacement' };
    if (c.n >= cal.cap) return { kind: 'cap', text: `Dial cap of ${cal.cap} reached: release it for this round` };
    const tz = (c.h.tz && RTM.validTZ(c.h.tz)) ? c.h.tz : cal.tz;
    const hour = c.h.plan && Number.isInteger(c.h.plan.target_hour) ? c.h.plan.target_hour : null;
    const startHour = cal.hours.start, endHour = cal.hours.end;
    let at, kind, text;
    if (c.appointment) { at = c.appointment; kind = 'callback'; text = 'Booked callback: call at the agreed time'; }
    else if (c.n === 0) {
      const key = c.h.plan && c.h.plan.first_dial_date ? c.h.plan.first_dial_date : RTM.partsIn(now, cal.tz).key;
      at = RTM.zoned(key, hour !== null ? hour : startHour, 0, tz);
      const hadInterview = !!(c.h.history && c.h.history.last_interview);
      kind = 'first'; text = hour === null ? 'First dial' : hadInterview ? 'First dial, at the time of the last interview' : 'First dial, at the hour your leader planned';
    } else {
      const end = RTM.parseTS(c.last.end_ts || c.last.ts);
      const cand = new Date(end.getTime() + 2 * 3600e3);
      const pc = RTM.partsIn(cand, cal.tz), pe = RTM.partsIn(end, cal.tz);
      if (pc.key === pe.key && cal.isWorking(pc.key) && pc.h >= startHour && pc.h < endHour) {
        at = cand; kind = 'redial'; text = 'Same day, at least two hours after the last dial';
      } else {
        let k = RTM.addDaysKey(pe.key, 1), guard = 0;
        while (!cal.isWorking(k) && guard++ < 60) k = RTM.addDaysKey(k, 1);
        at = RTM.zoned(k, hour !== null ? hour : startHour, 0, tz);
        kind = 'next_day'; text = hour !== null ? 'Next working day, near the usual hour' : 'Next working day';
      }
    }
    // keep the suggestion inside the call hours, and off the hour the fast is broken during Ramadan (3.5.4)
    let pa = RTM.partsIn(at, cal.tz);
    if (pa.h < startHour) { at = RTM.zoned(pa.key, startHour, 0, cal.tz); pa = RTM.partsIn(at, cal.tz); }
    if (pa.h >= endHour && kind !== 'callback') {
      let k = RTM.addDaysKey(pa.key, 1), guard = 0;
      while (!cal.isWorking(k) && guard++ < 60) k = RTM.addDaysKey(k, 1);
      at = RTM.zoned(k, startHour, 0, cal.tz); pa = RTM.partsIn(at, cal.tz);
    }
    if (cal.breakFastHour !== null && cal.isRamadan(pa.key) && pa.h === cal.breakFastHour && kind !== 'callback') {
      at = new Date(at.getTime() + 3600e3); text += '; moved off the hour the fast is broken';
    }
    pa = RTM.partsIn(at, cal.tz);
    if (pa.key > cal.end) return { kind: 'window_end', text: 'The next dial would fall after the window: release it for this round' };
    const due = at.getTime() <= now.getTime();
    if (kind === 'first' && due && pa.key < RTM.partsIn(now, cal.tz).key) kind = 'overdue';
    return { kind, at, due, text, holiday: cal.holiday(pa.key) };
  };

  // ---- the day's call list ----
  RTM.queue = (C, now, dayKey) => {
    const cal = C.cal, todayKey = RTM.partsIn(now, cal.tz).key, isToday = dayKey === todayKey;
    const decide = [], due = [], later = [];
    for (const c of C.list) {
      if (!c.open) continue;
      const s = c.next;
      if (['refusal', 'dead', 'cap', 'window_end'].includes(s.kind)) { if (isToday) decide.push(c); continue; }
      if (!s.at) continue;
      const k = RTM.partsIn(s.at, cal.tz).key;
      if (isToday && s.at.getTime() <= now.getTime()) due.push(c);
      else if (k === dayKey) later.push(c);
    }
    const rank = c => (c.next.kind === 'callback' ? 0 : c.next.kind === 'overdue' ? 1 : 2);
    due.sort((a, b) => rank(a) - rank(b) || a.next.at - b.next.at);
    later.sort((a, b) => a.next.at - b.next.at);
    return { decide, due, later, isToday };
  };

  // ---- progress counts ----
  RTM.progress = C => {
    const p = { total: 0, complete: 0, released: 0, replaced: 0, remove_requested: 0, in_progress: 0, not_started: 0, short: 0, reassigned: 0 };
    for (const c of C.list) { if (c.kind === 'removed') { p.reassigned++; continue; } p.total++; p[c.state]++; if (c.flags.complete_short) p.short++; }
    p.open = p.in_progress + p.not_started;
    return p;
  };

  // ---- export rows (A.4) ----
  RTM.CSV_COLS = ['program', 'round', 'hhid', 'attempt', 'ts', 'end_ts', 'utc_offset', 'dur_min', 'status', 'is_cmp_code',
    'operator', 'phone_slot', 'appointment_ts', 'action', 'replaces', 'note', 'corrected', 'logged_by', 'logged_at', 'event_id', 'prev_hash'];
  RTM.dialRow = d => ({
    program: d.program, round: d.round, hhid: d.hhid, attempt: d.attempt,
    ts: RTM.wallFromISO(d.ts), end_ts: RTM.wallFromISO(d.end_ts), utc_offset: RTM.offsetFromISO(d.ts),
    dur_min: d.dur_min === null || d.dur_min === undefined ? '' : d.dur_min.toFixed(2),
    status: d.status, is_cmp_code: d.status === 'COMPLETE' ? 1 : 0, operator: d.operator || d.logged_by,
    phone_slot: d.phone_slot, appointment_ts: RTM.wallFromISO(d.appointment_ts), action: d.action || '', replaces: d.replaces || '',
    note: d.note || '', corrected: d.corrected ? 1 : 0, logged_by: d.logged_by, logged_at: d.logged_at, event_id: d.event_id, prev_hash: d.prev_hash,
  });
  RTM.exportBase = (S, now) => `${S.assignment.enumerator_id}_${RTM.partsIn(now, null).key}`;
  RTM.buildExport = (S, now) => {
    const A = S.assignment, eff = RTM.effective(S), chain = RTM.verifyChain(S.events, S.genesis);
    const base = RTM.exportBase(S, now);
    const rows = eff.dials.map(RTM.dialRow);
    const contacts = eff.contacts.map(e => RTM.clean({ event_id: e.event_id, hhid: e.hhid, slot: e.slot, change: e.change, label: e.label,
      number: e.private && e.private.number, private_digest: e.private_digest, logged_by: e.logged_by, logged_at: e.logged_at }));
    const json = {
      schema: RTM.SCHEMA.calllog, tool_version: RTM.VERSION, program: A.program, country: A.country || '', round: A.round,
      enumerator_id: A.enumerator_id, assignment_fingerprint: S.fingerprint, chain_genesis: S.genesis,
      exported_at: RTM.localISO(now), exported_by: A.enumerator_id, event_count: S.events.length,
      last_hash: S.events.length ? S.events[S.events.length - 1].hash : S.genesis, chain_verified: chain.ok,
      contains_contact_information: false,
      contacts_file: contacts.length ? base + '_contacts.json' : null,
      events: S.events.map(RTM.exportEvent),
      dials: rows,
      actions: eff.standaloneActions.map(a => RTM.clean({
        event_id: a.event_id, hhid: a.hhid, action: a.action, target_hhid: a.target_hhid, reason: a.reason, note: a.note, logged_by: a.logged_by, logged_at: a.logged_at })),
      // later edits, as events that point to the event they correct (the log stays append-only)
      corrections: S.events.filter(e => e.type === 'correction').map(RTM.exportEvent),
      // which numbers changed, without the numbers: those are only in the separate contacts file
      contact_updates: eff.contacts.map(e => RTM.clean({ event_id: e.event_id, hhid: e.hhid, slot: e.slot, change: e.change, label: e.label,
        private_digest: e.private_digest, logged_by: e.logged_by, logged_at: e.logged_at })),
    };
    const contactFile = contacts.length ? {
      schema: RTM.SCHEMA.contacts, tool_version: RTM.VERSION, program: A.program, round: A.round, enumerator_id: A.enumerator_id,
      exported_at: RTM.localISO(now), contains_contact_information: true,
      note: 'Contains phone numbers. Give this file to your team leader directly; do not put it in the common folder.',
      updates: contacts,
    } : null;
    return { base, csv: RTM.toCSV(rows, RTM.CSV_COLS), json, contacts: contactFile, rows, chain };
  };

  // ---- project file (B) ----
  RTM.buildProject = (S, now) => {
    const o = {
      schema: RTM.SCHEMA.project, tool_version: RTM.VERSION, saved_at: RTM.localISO(now), saved_by: S.assignment.enumerator_id,
      assignment: S.assignment, assignment_fingerprint: S.fingerprint, chain_genesis: S.genesis,
      events: S.events, past: S.past, ui: S.ui || {}, last_export: S.last_export || null,
    };
    o.checksum = RTM.sha256(RTM.canon(o));
    return o;
  };
  RTM.loadProject = o => {
    const errors = [], warnings = [];
    if (!o || o.schema !== RTM.SCHEMA.project) return { errors: [`This is not a saved session: its schema is "${(o && o.schema) || 'missing'}", expected "${RTM.SCHEMA.project}". (An assignment file is opened with the other button.)`], warnings };
    const chk = o.checksum; const copy = Object.assign({}, o); delete copy.checksum;
    if (RTM.sha256(RTM.canon(copy)) !== chk) errors.push('The saved session was changed or damaged after it was saved (its checksum does not match).');
    const A = o.assignment;
    const v = RTM.validateAssignment(A);
    v.errors.forEach(e => errors.push('Embedded assignment: ' + e));
    if (A && RTM.fingerprint(A) !== o.assignment_fingerprint) errors.push('The embedded assignment does not match its fingerprint.');
    if (A && o.saved_by !== A.enumerator_id) warnings.push(`The session was saved by ${o.saved_by}, but the assignment is ${A.enumerator_id}'s.`);
    const chain = RTM.verifyChain(o.events || [], o.chain_genesis);
    if (!chain.ok) errors.push(`The call log fails its integrity check at event ${chain.index + 1}: ${chain.reason}.`);
    if (errors.length) return { errors, warnings };
    const S = { assignment: A, fingerprint: o.assignment_fingerprint, genesis: o.chain_genesis, events: o.events || [],
      past: o.past || { files: [], dials: [] }, last_export: o.last_export || null, last_save: { at: o.saved_at, event_count: (o.events || []).length }, ui: o.ui || {} };
    return { errors, warnings, session: S };
  };
  // a newer assignment for the same enumerator and round: keep the log, take the new households and calendar
  RTM.updateAssignment = (S, A2, fileName) => {
    const A = S.assignment, problems = [];
    if (A2.enumerator_id !== A.enumerator_id) problems.push(`This assignment is for ${A2.enumerator_id}, not ${A.enumerator_id}.`);
    if (A2.round !== A.round || A2.program !== A.program) problems.push(`This assignment is for ${A2.program} round ${A2.round}, not ${A.program} round ${A.round}.`);
    if (problems.length) return { problems };
    const before = new Set(A.households.map(h => h.hhid)), after = new Set(A2.households.map(h => h.hhid));
    const removed = [...before].filter(x => !after.has(x)), added = [...after].filter(x => !before.has(x));
    S.assignment = A2; S.fingerprint = RTM.fingerprint(A2);
    RTM.append(S, 'session', { what: 'assignment_updated', fingerprint: S.fingerprint, fingerprint_ok: A2.fingerprint ? (A2.fingerprint === S.fingerprint ? 1 : 0) : undefined,
      file: fileName, households_added: added.length, households_removed: removed.length, added_hhids: added.length ? added : undefined, removed_hhids: removed.length ? removed : undefined });
    return { problems, added, removed };
  };

  // ---- optional passphrase protection (D11): PBKDF2-SHA-256 then AES-256-GCM, done in the browser, offline ----
  // The envelope's header (what it contains, program, round, enumerator) is bound to the ciphertext as
  // additional authenticated data, so it cannot be swapped onto another file. The passphrase is never stored;
  // the derived key stays in memory for the session only and cannot be extracted.
  RTM.SCHEMA.sealed = 'rtm-sealed-1.0';
  RTM.SEAL_ITER = 600000;
  const B64 = {
    enc: u8 => { let t = ''; for (let i = 0; i < u8.length; i += 0x8000) t += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(t); },
    dec: t => Uint8Array.from(atob(t), ch => ch.charCodeAt(0)),
  };
  RTM.b64 = B64;
  RTM.canSeal = () => !!(typeof crypto !== 'undefined' && crypto.subtle);
  RTM.sealHeader = env => RTM.clean({ schema: env.schema, contains: env.contains, program: env.program, round: env.round, enumerator_id: env.enumerator_id });
  RTM.deriveKey = async (passphrase, salt, iterations) => {
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(String(passphrase).normalize('NFC')), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations }, base, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
  };
  RTM.sealWith = async (obj, k, head) => {
    const env = RTM.clean(Object.assign({ schema: RTM.SCHEMA.sealed }, head));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const aad = new TextEncoder().encode(RTM.canon(RTM.sealHeader(env)));
    const ct = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: aad, tagLength: 128 }, k.key, new TextEncoder().encode(JSON.stringify(obj))));
    return Object.assign(env, {
      note: 'Protected file. Open it in the RTM interview tool with the passphrase your leader gave you.',
      kdf: { name: 'PBKDF2', hash: 'SHA-256', iterations: k.iterations, salt: B64.enc(k.salt) },
      cipher: { name: 'AES-GCM', iv: B64.enc(iv), tag_bits: 128 }, data: B64.enc(ct),
    });
  };
  RTM.seal = async (obj, passphrase, head, iterations) => {
    const salt = crypto.getRandomValues(new Uint8Array(16)), it = iterations || RTM.SEAL_ITER;
    const k = { key: await RTM.deriveKey(passphrase, salt, it), salt, iterations: it };
    return { env: await RTM.sealWith(obj, k, head), k };
  };
  RTM.unseal = async (env, passphrase) => {
    if (!env || env.schema !== RTM.SCHEMA.sealed) throw new Error('This is not a protected file.');
    const kd = env.kdf || {}, ci = env.cipher || {};
    if (kd.name !== 'PBKDF2' || kd.hash !== 'SHA-256' || ci.name !== 'AES-GCM' || !Number.isInteger(kd.iterations) || kd.iterations < 100000 || kd.iterations > 5000000)
      throw new Error('This protected file uses a method this tool does not support.');
    let salt, iv, data;
    try { salt = B64.dec(kd.salt); iv = B64.dec(ci.iv); data = B64.dec(env.data); } catch (e) { throw new Error('The protected file is damaged.'); }
    const k = { key: await RTM.deriveKey(passphrase, salt, kd.iterations), salt, iterations: kd.iterations };
    const aad = new TextEncoder().encode(RTM.canon(RTM.sealHeader(env)));
    let pt;
    try { pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv, additionalData: aad, tagLength: ci.tag_bits || 128 }, k.key, data); }
    catch (e) { const err = new Error('That passphrase does not open this file, or the file was changed after it was protected.'); err.code = 'passphrase'; throw err; }
    let obj;
    try { obj = JSON.parse(new TextDecoder().decode(pt)); } catch (e) { throw new Error('The protected content is not readable.'); }
    if (!obj || obj.schema !== env.contains) throw new Error('The protected content is not what its label says.');
    return { obj, k };
  };

  // ---- past exports (the enumerator's own earlier logs, for the performance view) ----
  RTM.readExport = (text, name) => {
    let rows = [], meta = { name };
    const t = String(text).trim();
    if (t.startsWith('{')) {
      const o = JSON.parse(t);
      if (o.schema !== RTM.SCHEMA.calllog) throw new Error(`${name}: not a call-log export (schema "${o.schema || 'missing'}").`);
      rows = o.dials || []; meta.enumerator_id = o.enumerator_id; meta.round = o.round; meta.program = o.program;
    } else {
      rows = RTM.parseCSV(t);
      if (!rows.length || !('ts' in rows[0]) || !('status' in rows[0])) throw new Error(`${name}: not a call-log export (no ts and status columns).`);
      meta.enumerator_id = rows[0].operator || rows[0].logged_by; meta.round = +rows[0].round; meta.program = rows[0].program;
    }
    rows = rows.map(r => Object.fromEntries(RTM.CSV_COLS.map(c => [c, r[c] === undefined || r[c] === null ? '' : String(r[c])])));
    return { meta, rows };
  };
  RTM.rowInstant = r => new Date(Date.parse(r.ts.replace(' ', 'T') + (r.utc_offset || '')));

  // ---- performance (Box 3.0 definitions) ----
  // a successful dial is the one on which the interview took place (3.5); a complete needs 3 minutes or more (Box 3.0)
  RTM.qualifies = r => r.status === 'COMPLETE' && (r.dur_min === '' || r.dur_min === null || r.dur_min === undefined || +r.dur_min >= RTM.MIN_COMPLETE_MIN);
  RTM.perf = (rows, tz) => {
    const out = { dials: 0, completes: 0, complete_codes: 0, first: 0, first_ok: 0, days: new Set(), hours: Array.from({ length: 24 }, () => ({ dials: 0, ok: 0 })) };
    for (const r of rows) {
      const t = RTM.rowInstant(r); if (isNaN(t)) continue;
      const p = RTM.partsIn(t, tz), ok = RTM.qualifies(r);
      out.dials++; out.days.add(p.key); out.hours[p.h].dials++;
      if (r.status === 'COMPLETE') out.complete_codes++;
      if (ok) { out.completes++; out.hours[p.h].ok++; }
      if (+r.attempt === 1) { out.first++; if (ok) out.first_ok++; }
    }
    out.edays = out.days.size;
    out.success = out.dials ? out.completes / out.dials : null;
    out.dpc = out.completes ? out.dials / out.completes : null;
    out.first_rate = out.first ? out.first_ok / out.first : null;
    out.cpd = out.edays ? out.completes / out.edays : null;
    return out;
  };
  RTM.monthKey = (r, tz) => { const p = RTM.partsIn(RTM.rowInstant(r), tz); return `${p.y}-${p2(p.m)}`; };

  G.RTM = RTM;
})(typeof window !== 'undefined' ? window : globalThis);
