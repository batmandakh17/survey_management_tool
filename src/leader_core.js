/* RTM interview tool, leader side: reading the round's inputs, the assignment rules, planning, the round files,
   the merge of enumerators' exports, and the round's outputs. Pure functions over plain objects; no network,
   no storage. Uses window.RTM (core.js). Section letters refer to PROPOSAL.md. */
(function () {
  'use strict';
  const R = window.RTM;
  const L = window.LCORE = {};
  L.SCHEMA = { manifest: 'rtm-roundmanifest-1.0', leader: 'rtm-leader-1.0' };
  L.ACOLS = ['program', 'round', 'hhid', 'action', 'target_hhid', 'reason', 'note', 'via', 'logged_by', 'logged_at', 'event_id'];
  L.RULES = {
    keep_same: 'Keep the same enumerator',
    random: 'Random',
    equal_split: 'Equal split',
    share_of_total: 'Share of total',
    manual: 'Manual',
  };
  const STATUS_SET = new Set(R.STATUS.map(s => s.code));
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const p2 = n => String(n).padStart(2, '0');

  // ---- seeded random numbers (mulberry32): the same seed and inputs give the same assignment (C) ----
  L.rng = seed => {
    let a = (Number(seed) >>> 0) || 1;
    return () => {
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };
  L.shuffled = (arr, rnd) => { const a = arr.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };

  // ---- tables ----
  const norm = s => String(s || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
  L.readTable = text => {
    const rows = R.parseCSV(String(text).replace(/^\uFEFF/, ''));
    const cols = rows.length ? Object.keys(rows[0]) : (String(text).split(/\r?\n/)[0] || '').split(',');
    const map = {};
    cols.forEach(c => { map[norm(c)] = c; });
    return { rows, cols, col: name => map[norm(name)] };
  };
  const isSci = v => /^[+-]?\d(\.\d+)?e[+-]?\d+$/i.test(String(v).trim());
  const baseName = n => String(n).replace(/\.(csv|json)$/i, '').replace(/ \(\d+\)$/, '');
  L.baseName = baseName;

  // ---- a small reader for Excel workbooks (proposal G): the first sheet, as a CSV text, offline ----
  // An .xlsx file is a ZIP of XML parts; the browser inflates them (DecompressionStream) and parses the XML.
  L.readXlsx = async buf => {
    const u8 = new Uint8Array(buf), dv = new DataView(u8.buffer, u8.byteOffset, u8.byteLength);
    let eocd = -1;
    for (let i = u8.length - 22; i >= Math.max(0, u8.length - 66000); i--) if (dv.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    if (eocd < 0) throw new Error('This is not an Excel workbook (.xlsx).');
    const n = dv.getUint16(eocd + 10, true);
    let p = dv.getUint32(eocd + 16, true);
    const dec = new TextDecoder('utf-8'), entries = new Map();
    for (let k = 0; k < n; k++) {
      if (dv.getUint32(p, true) !== 0x02014b50) break;
      const method = dv.getUint16(p + 10, true), csize = dv.getUint32(p + 20, true);
      const nl = dv.getUint16(p + 28, true), el = dv.getUint16(p + 30, true), cl = dv.getUint16(p + 32, true), off = dv.getUint32(p + 42, true);
      entries.set(dec.decode(u8.subarray(p + 46, p + 46 + nl)), { method, csize, off });
      p += 46 + nl + el + cl;
    }
    const part = async name => {
      const e = entries.get(name);
      if (!e) return null;
      const start = e.off + 30 + dv.getUint16(e.off + 26, true) + dv.getUint16(e.off + 28, true);
      const data = u8.subarray(start, start + e.csize);
      if (e.method === 0) return dec.decode(data);
      if (e.method !== 8 || typeof DecompressionStream === 'undefined') throw new Error('This browser cannot read this workbook; save it as CSV UTF-8.');
      const out = await new Response(new Blob([data]).stream().pipeThrough(new DecompressionStream('deflate-raw'))).arrayBuffer();
      return dec.decode(out);
    };
    const xml = t => new DOMParser().parseFromString(t, 'application/xml');
    const wb = xml(await part('xl/workbook.xml') || '<x/>');
    const sheet = wb.getElementsByTagName('sheet')[0];
    if (!sheet) throw new Error('The workbook has no sheet.');
    const rid = sheet.getAttribute('r:id') || sheet.getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id');
    let target = 'worksheets/sheet1.xml';
    const rels = await part('xl/_rels/workbook.xml.rels');
    if (rels) for (const r of xml(rels).getElementsByTagName('Relationship')) if (r.getAttribute('Id') === rid) target = r.getAttribute('Target');
    const path = target.startsWith('/') ? target.slice(1) : 'xl/' + target.replace(/^\.\//, '');
    const ssText = await part('xl/sharedStrings.xml');
    const shared = ssText ? [...xml(ssText).getElementsByTagName('si')].map(si => [...si.getElementsByTagName('t')].map(t => t.textContent).join('')) : [];
    const sh = xml(await part(path) || '<x/>');
    const colIdx = ref => { let c = 0; for (const ch of ref.replace(/\d+$/, '')) c = c * 26 + (ch.charCodeAt(0) - 64); return c - 1; };
    const grid = [], numeric = new Set();
    for (const row of sh.getElementsByTagName('row')) {
      const r = (+row.getAttribute('r') || grid.length + 1) - 1, line = grid[r] = grid[r] || [];
      for (const c of row.getElementsByTagName('c')) {
        const t = c.getAttribute('t'), v = c.getElementsByTagName('v')[0], i = colIdx(c.getAttribute('r') || 'A');
        let val = '';
        if (t === 's') val = v ? shared[+v.textContent] || '' : '';
        else if (t === 'inlineStr') val = [...c.getElementsByTagName('t')].map(x => x.textContent).join('');
        else if (t === 'b') val = v && v.textContent === '1' ? 'TRUE' : 'FALSE';
        else { val = v ? v.textContent : ''; if (v && (!t || t === 'n')) numeric.add(i); }
        line[i] = val;
      }
    }
    const rows = grid.filter(Boolean);
    if (!rows.length) throw new Error('The first sheet is empty.');
    const header = rows[0].map(x => String(x || '').trim());
    const objs = rows.slice(1).filter(l => l.some(x => x !== undefined && x !== '')).map(l => Object.fromEntries(header.map((h, i) => [h, l[i] === undefined ? '' : String(l[i])])));
    const warnings = [];
    const numCols = header.filter((h, i) => numeric.has(i) && /^(hhid|unit_id|replacement_hhid|psu|stratum|phone(_\d+)?)$/i.test(h));
    if (numCols.length) warnings.push(`In the workbook, ${numCols.join(', ')} ${numCols.length > 1 ? 'are' : 'is'} stored as numbers: leading zeros and a leading + are lost. Format ${numCols.length > 1 ? 'those columns' : 'that column'} as Text in Excel, or save the sheet as CSV UTF-8.`);
    return { text: R.toCSV(objs, header), warnings, rows: objs.length };
  };

  // ---- household list (A.1) ----
  const STD_COLS = new Set(['hhid', 'psu', 'stratum', 'contact_name', 'respondent_member', 'language', 'tz', 'status', 'phone', 'phone_label']);
  L.STD_COLS = STD_COLS;
  L.parseHouseholds = text => {
    const T = L.readTable(text), errors = [], warnings = [];
    const need = ['hhid', 'psu', 'stratum'];
    need.forEach(c => { if (!T.col(c)) errors.push(`The household list has no "${c}" column.`); });
    const phoneCols = T.cols.map(c => /^phone_?(\d+)$/i.exec(norm(c))).filter(Boolean).map(m => +m[1]).sort((a, b) => a - b);
    if (T.col('phone') && !phoneCols.includes(1)) phoneCols.unshift(0);
    if (!phoneCols.length) errors.push('The household list has no phone column (phone_1, phone_2, …).');
    if (errors.length) return { errors, warnings, households: new Map(), counts: {} };
    const H = new Map(), counts = { rows: T.rows.length, active: 0, removed: 0, reserve: 0, no_phone: 0 };
    const get = (r, c) => { const k = T.col(c); return k ? String(r[k] == null ? '' : r[k]).trim() : ''; };
    T.rows.forEach((r, i) => {
      const hhid = get(r, 'hhid');
      if (!hhid) { errors.push(`Row ${i + 2} has no household ID.`); return; }
      if (isSci(hhid)) { errors.push(`Row ${i + 2}: the ID "${hhid}" was written in scientific notation, so it no longer matches. Save the IDs as text.`); return; }
      if (H.has(hhid)) { errors.push(`Household ${hhid} appears twice.`); return; }
      const given = get(r, 'status'), status = (given || 'active').toLowerCase();
      if (!['active', 'removed', 'reserve'].includes(status)) { errors.push(`Household ${hhid}: status "${status}" is not active, removed or reserve.`); return; }
      const phones = [];
      phoneCols.forEach(k => {
        const num = get(r, k === 0 ? 'phone' : `phone_${k}`);
        if (!num) return;
        if (isSci(num)) warnings.push(`Household ${hhid}: phone ${k || 1} looks like a number Excel converted ("${num}"). Check it.`);
        phones.push(R.clean({ slot: k || 1, number: num, label: get(r, k === 0 ? 'phone_label' : `phone_${k}_label`) }));
      });
      const tz = get(r, 'tz');
      if (tz && !R.validTZ(tz)) warnings.push(`Household ${hhid}: the time zone "${tz}" is not known; the round's time zone is used.`);
      const h = R.clean({ hhid, psu: get(r, 'psu'), stratum: get(r, 'stratum'), name: get(r, 'contact_name'), member: get(r, 'respondent_member'),
        language: get(r, 'language'), tz: tz && R.validTZ(tz) ? tz : '', status });
      h.phones = phones;
      h.status_given = !!given;
      // every other column travels with the household, for the matching criteria (sex, dialect, region…)
      h.extra = {};
      T.cols.forEach(c => { const k = norm(c); if (!STD_COLS.has(k) && !/^phone_?\d*(_label)?$/.test(k)) { const v = String(r[c] == null ? '' : r[c]).trim(); if (v) h.extra[k] = v; } });
      if (!h.psu || !h.stratum) warnings.push(`Household ${hhid} has no ${!h.psu ? 'PSU' : 'stratum'}.`);
      H.set(hhid, h);
      counts[status]++;
      if (!phones.length && status === 'active') counts.no_phone++;
    });
    if (counts.no_phone) warnings.push(`${R.plural(counts.no_phone, 'active household')} ${counts.no_phone === 1 ? 'has' : 'have'} no phone number.`);
    return { errors, warnings, households: H, counts };
  };

  // ---- replacement lists (A.2): rtmtools selection.csv, or the program's own hhid, replacement_hhid, rank ----
  L.parseReplacements = (text, H) => {
    const T = L.readTable(text), errors = [], warnings = [];
    const lists = new Map();
    const has = c => !!T.col(c);
    let format;
    if (has('unit_id') && has('stratum') && has('selected') && has('reserve')) format = 'rtmtools';
    else if (has('hhid') && has('replacement_hhid')) format = 'program';
    else return { errors: ['This is not a replacement list: expected rtmtools columns (unit_id, stratum, selected, reserve) or hhid, replacement_hhid, rank.'], warnings, lists, format: null };
    const v = (r, c) => String(r[T.col(c)] == null ? '' : r[T.col(c)]).trim();
    const sci = T.rows.filter(r => isSci(v(r, format === 'rtmtools' ? 'unit_id' : 'hhid'))).length;
    if (sci) return { errors: [`${sci} IDs were written in scientific notation (such as 1.10e+08), as rtmtools did before its fix of 27 October 2026. Update rtmtools in Stata (ado update rtmtools, update) and export the selection again.`], warnings, lists, format };
    const owner = new Map();
    const add = (main, rep, rank) => {
      if (owner.has(rep)) { errors.push(`Replacement ${rep} is listed for two households (${owner.get(rep)} and ${main}).`); return; }
      owner.set(rep, main);
      if (!lists.has(main)) lists.set(main, []);
      lists.get(main).push({ hhid: rep, rank });
    };
    if (format === 'rtmtools') {
      const by = new Map();
      T.rows.forEach((r, i) => {
        const s = v(r, 'stratum');
        if (!by.has(s)) by.set(s, { mains: [], reserves: [] });
        const g = by.get(s);
        const sel = v(r, 'selected'), res = parseFloat(v(r, 'reserve'));
        if (sel === '1') g.mains.push({ id: v(r, 'unit_id'), rank: parseFloat(T.col('rank') ? v(r, 'rank') : '') || parseFloat(T.col('order') ? v(r, 'order') : '') || i + 1 });
        else if (res > 0) g.reserves.push({ id: v(r, 'unit_id'), k: res });
      });
      for (const [s, g] of by) {
        if (!g.reserves.length) continue;
        if (!g.mains.length) { warnings.push(`Stratum or PSU ${s} has replacements but no selected household; they are not used.`); continue; }
        g.mains.sort((a, b) => a.rank - b.rank);
        g.reserves.sort((a, b) => a.k - b.k);
        // D6: the PSU's ordered reserve dealt round-robin to its main households in selection order
        g.reserves.forEach((x, j) => add(g.mains[j % g.mains.length].id, x.id, Math.floor(j / g.mains.length) + 1));
      }
    } else {
      const rows = T.rows.map((r, i) => ({ main: v(r, 'hhid'), rep: v(r, 'replacement_hhid'), rank: parseFloat(T.col('rank') ? v(r, 'rank') : '') || i + 1 }))
        .filter(x => x.main && x.rep).sort((a, b) => cmpStr(a.main, b.main) || a.rank - b.rank);
      rows.forEach(x => add(x.main, x.rep, x.rank));
      for (const l of lists.values()) l.forEach((x, i) => { x.rank = i + 1; });
    }
    let noContact = 0, noMain = 0;
    for (const [main, l] of lists) {
      if (H && !H.has(main)) noMain++;
      l.forEach(x => { if (H && !H.has(x.hhid)) noContact++; });
    }
    if (noMain) warnings.push(`${R.plural(noMain, 'main household')} of the replacement list ${noMain === 1 ? 'is' : 'are'} not in the household list.`);
    if (noContact) warnings.push(`${R.plural(noContact, 'replacement')} ${noContact === 1 ? 'is' : 'are'} not in the household list, so ${noContact === 1 ? 'it has' : 'they have'} no contact details and cannot be used.`);
    return { errors, warnings, lists, format, counts: { mains: lists.size, replacements: owner.size } };
  };

  // ---- history: earlier rounds' merged logs, actions, manifests, or interview records ----
  // Times without an offset are read in the program's time zone.
  L.instant = (ts, off, tz) => {
    const s = String(ts || '').trim();
    if (!s) return null;
    if (/[zZ]$|[+-]\d\d:\d\d$/.test(s)) { const t = Date.parse(s.replace(' ', 'T')); return isNaN(t) ? null : new Date(t); }
    const m = /^(\d{4}-\d\d-\d\d)[ T](\d\d):(\d\d)(?::(\d\d))?/.exec(s);
    if (!m) { const t = Date.parse(s); return isNaN(t) ? null : new Date(t); }
    if (off && /^[+-]\d\d:\d\d$/.test(off)) return new Date(Date.parse(`${m[1]}T${m[2]}:${m[3]}:${m[4] || '00'}${off}`));
    const z = R.zoned(m[1], +m[2], +m[3], tz);
    return new Date(z.getTime() + (+(m[4] || 0)) * 1000);
  };
  L.readHistoryFile = (name, text) => {
    const t = String(text).trim();
    if (t.startsWith('{')) {
      let o; try { o = JSON.parse(t); } catch (e) { return { kind: 'unknown', name, error: 'not readable JSON' }; }
      if (o.schema === L.SCHEMA.manifest) return { kind: 'manifest', name, round: o.round, program: o.program, manifest: o };
      if (o.schema === R.SCHEMA.calllog) return { kind: 'export', name, round: o.round, program: o.program, export: o };
      return { kind: 'unknown', name, error: `schema "${o.schema || 'missing'}" is not a history file` };
    }
    const T = L.readTable(t);
    const c = n => !!T.col(n);
    const fileRound = (/_R(\d+)/i.exec(name) || [])[1];
    if (c('hhid') && c('ts') && c('status')) return { kind: 'calls', name, table: T, fileRound: fileRound ? +fileRound : null };
    if (c('hhid') && c('action') && c('round')) return { kind: 'actions', name, table: T, fileRound: fileRound ? +fileRound : null };
    if (c('hhid') && c('interview_date')) return { kind: 'interviews', name, table: T, fileRound: fileRound ? +fileRound : null };
    return { kind: 'unknown', name, error: 'not a calls, actions, interviews or manifest file' };
  };
  // the program's own status codes that are not the tool's; the leader maps each once (A.4)
  L.unknownCodes = files => {
    const out = new Map();
    files.filter(f => f.kind === 'calls').forEach(f => {
      const T = f.table, sc = T.col('status');
      T.rows.forEach(r => { const s = String(r[sc] || '').trim(); if (s && !STATUS_SET.has(s)) out.set(s, (out.get(s) || 0) + 1); });
    });
    return out;
  };
  L.buildHistory = (files, opts) => {
    const o = Object.assign({ tz: null, mapping: {}, program: null }, opts || {});
    const H = { dials: new Map(), actions: new Map(), roster: new Map(), manifests: new Map(), interviews: new Map(), notes: [], rounds: [] };
    const put = (m, r, x) => { if (!m.has(r)) m.set(r, []); m.get(r).push(x); };
    for (const f of files) {
      if (f.kind === 'manifest') {
        H.manifests.set(f.round, f.manifest);
        const ro = new Map(); (f.manifest.households || []).forEach(h => ro.set(h.hhid, h.enumerator_id));
        H.roster.set(f.round, ro);
      } else if (f.kind === 'calls') {
        const T = f.table, g = (r, n) => { const k = T.col(n); return k ? String(r[k] == null ? '' : r[k]).trim() : ''; };
        T.rows.forEach(r => {
          const rnd = parseInt(g(r, 'round'), 10) || f.fileRound;
          if (!rnd) return;
          const raw = g(r, 'status');
          const status = STATUS_SET.has(raw) ? raw : (o.mapping[raw] || 'OTHER');
          const ts = L.instant(g(r, 'ts'), g(r, 'utc_offset'), o.tz);
          if (!ts) return;
          const end = L.instant(g(r, 'end_ts'), g(r, 'utc_offset'), o.tz);
          const dm = g(r, 'dur_min');
          const dur = dm !== '' && !isNaN(+dm) ? +dm : (end ? Math.max(0, (end - ts) / 60000) : null);
          const cmpCode = g(r, 'is_cmp_code');
          const wm = /^(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d)(:\d\d)?/.exec(g(r, 'ts'));
          const wall = wm ? `${wm[1]} ${wm[2]}${wm[3] || ':00'}` : R.wallFromISO(R.localISO(ts));     // the clock time the call system recorded
          put(H.dials, rnd, { hhid: g(r, 'hhid'), round: rnd, ts, end, dur, status, raw, wall,
            cmp: cmpCode !== '' ? cmpCode === '1' : status === 'COMPLETE', operator: g(r, 'operator') || g(r, 'logged_by'),
            slot: parseInt(g(r, 'phone_slot'), 10) || null, action: g(r, 'action'), event_id: g(r, 'event_id') });
        });
      } else if (f.kind === 'actions') {
        const T = f.table, g = (r, n) => { const k = T.col(n); return k ? String(r[k] == null ? '' : r[k]).trim() : ''; };
        T.rows.forEach(r => {
          const rnd = parseInt(g(r, 'round'), 10) || f.fileRound;
          if (rnd) put(H.actions, rnd, { hhid: g(r, 'hhid'), action: g(r, 'action'), target_hhid: g(r, 'target_hhid'), via: g(r, 'via'), logged_by: g(r, 'logged_by'), logged_at: g(r, 'logged_at') });
        });
      } else if (f.kind === 'interviews') {
        const T = f.table, g = (r, n) => { const k = T.col(n); return k ? String(r[k] == null ? '' : r[k]).trim() : ''; };
        T.rows.forEach(r => {
          const rnd = parseInt(g(r, 'round'), 10) || f.fileRound;
          if (!rnd) return;
          if (!H.interviews.has(rnd)) H.interviews.set(rnd, new Map());
          const out = g(r, 'outcome').toLowerCase();
          H.interviews.get(rnd).set(g(r, 'hhid'), { date: g(r, 'interview_date'), enumerator: g(r, 'enumerator'), outcome: out,
            complete: ['complete', 'completed', '1', 'cmp'].includes(out) });
        });
      }
    }
    // dial actions from the calls' action column, when no actions file gives them
    for (const [rnd, ds] of H.dials) {
      if (H.actions.has(rnd)) continue;
      ds.filter(d => d.action).forEach(d => put(H.actions, rnd, { hhid: d.hhid, action: d.action, via: 'dial', logged_by: d.operator }));
    }
    const rounds = new Set([...H.dials.keys(), ...H.roster.keys(), ...H.interviews.keys()]);
    H.rounds = [...rounds].sort((a, b) => a - b);
    // a qualifying complete per household and round: the first complete-coded dial of 3 minutes or more (Box 3.0)
    H.complete = new Map();
    for (const rnd of H.rounds) {
      const m = new Map();
      (H.dials.get(rnd) || []).slice().sort((a, b) => a.ts - b.ts).forEach(d => {
        if (d.cmp && (d.dur === null || d.dur >= R.MIN_COMPLETE_MIN) && !m.has(d.hhid)) m.set(d.hhid, d);
      });
      const iv = H.interviews.get(rnd);
      if (iv) for (const [hid, x] of iv) if (x.complete && !m.has(hid)) {
        const ts = x.date ? L.instant(x.date.length > 10 ? x.date : x.date + ' 12:00:00', '', o.tz) : null;
        m.set(hid, { hhid: hid, round: rnd, ts, operator: x.enumerator, fromInterviews: true, noHour: x.date.length <= 10 });
      }
      H.complete.set(rnd, m);
    }
    // households present in each round: rostered, dialed or interviewed
    H.present = new Map();
    for (const rnd of H.rounds) {
      const s = new Set();
      (H.roster.get(rnd) || new Map()).forEach((_, k) => s.add(k));
      (H.dials.get(rnd) || []).forEach(d => s.add(d.hhid));
      (H.interviews.get(rnd) || new Map()).forEach((_, k) => s.add(k));
      H.present.set(rnd, s);
    }
    return H;
  };

  // what the history says about one household before round t (A.3 history, C, D)
  L.summaryOf = (H, hhid, t, tz) => {
    let joined = null;
    for (const r of H.rounds) if (r < t && H.present.get(r).has(hhid)) { joined = r; break; }
    let last = null;
    for (let r = t - 1; r >= 1; r--) {
      const c = H.complete.get(r) && H.complete.get(r).get(hhid);
      if (c) {
        const p = c.ts ? R.partsIn(c.ts, tz) : null;
        last = R.clean({ round: r, date: p ? p.key : undefined, hour: p && !c.noHour ? p.h : undefined, enumerator: c.operator });
        break;
      }
    }
    const interviewed = r => !!(H.complete.get(r) && H.complete.get(r).has(hhid));
    const last3 = joined === null ? null : [t - 3, t - 2, t - 1].map(r => (r < joined || r < 1 ? null : interviewed(r)));
    const prevRoster = H.roster.get(t - 1);
    let prev = prevRoster ? prevRoster.get(hhid) || null : null;
    const dl = (H.dials.get(t - 1) || []).filter(d => d.hhid === hhid).sort((a, b) => a.ts - b.ts);
    if (!prev && dl.length) prev = dl[dl.length - 1].operator || null;
    const acts = (H.actions.get(t - 1) || []).filter(a => a.hhid === hhid);
    const slotLast = {};
    dl.forEach(d => { if (d.slot) slotLast[d.slot] = d.status; });
    return {
      joined_round: joined, last_interview: last, last3, previous: prev, dials_last: dl.length, interviewed_last: interviewed(t - 1),
      in_last: H.present.has(t - 1) && H.present.get(t - 1).has(hhid),
      switch_requested: acts.some(a => a.action === 'SWITCH_REQUEST'), remove_requested: acts.some(a => a.action === 'REMOVE_REQUEST'),
      activated: [...H.actions.values()].some(l => l.some(a => a.action === 'ACTIVATE_REPLACEMENT' && a.target_hhid === hhid)),
      slot_last: slotLast,
    };
  };
  // the program's own best hours, once it has enough dials at each hour (3.5.1); otherwise none
  L.bestHours = (H, tz, hours, minDials) => {
    const n = {}, ok = {};
    for (const [rnd, ds] of H.dials) {
      const cm = H.complete.get(rnd) || new Map();
      ds.forEach(d => { const h = R.partsIn(d.ts, tz).h; n[h] = (n[h] || 0) + 1; const c = cm.get(d.hhid); if (c && c === d) ok[h] = (ok[h] || 0) + 1; });
    }
    const rows = [];
    for (let h = hours.start; h < hours.end; h++) if ((n[h] || 0) >= (minDials || 50)) rows.push({ h, rate: (ok[h] || 0) / n[h] });
    rows.sort((a, b) => b.rate - a.rate || a.h - b.h);
    return rows.slice(0, 3).map(x => x.h);
  };

  // ---- dealing (C): sort by stratum and a seeded key, deal by largest-remainder quotas ----
  L.quotas = (n, enums, shares) => {
    const tot = enums.reduce((s, e) => s + (shares.get(e) || 0), 0) || 1;
    const raw = enums.map(e => n * (shares.get(e) || 0) / tot);
    const q = raw.map(Math.floor);
    let left = n - q.reduce((a, b) => a + b, 0);
    raw.map((x, i) => ({ i, f: x - Math.floor(x) })).sort((a, b) => b.f - a.f || a.i - b.i).forEach(x => { if (left > 0) { q[x.i]++; left--; } });
    return new Map(enums.map((e, i) => [e, q[i]]));
  };
  // matching criteria: a household goes only to an enumerator whose values for each criterion include the household's
  // (language, respondent's sex, dialect or region, any column of the household list). A household without a value can
  // go to anyone. The criteria and each enumerator's values are written into the manifest and the assignment files.
  L.splitVals = s => String(s == null ? '' : s).toLowerCase().split(/[\s,;/|]+/).map(x => x.trim()).filter(Boolean);
  L.hhValue = (h, col) => { const k = norm(col); const v = h && h.extra && h.extra[k] !== undefined ? h.extra[k] : (h ? h[k] : ''); return String(v == null ? '' : v).trim().toLowerCase(); };
  L.eligibleFn = (criteria, team) => {
    const crit = [...new Set((criteria || []).map(norm).filter(Boolean))];
    if (!crit.length) return null;
    const attrs = new Map((team || []).map(t => [t.id, Object.fromEntries(crit.map(c => [c, new Set(L.splitVals((t.attrs || {})[c]))]))]));
    const f = (h, e) => { const a = attrs.get(e); return !!a && crit.every(c => { const v = L.hhValue(h, c); return !v || a[c].has(v); }); };
    f.criteria = crit; f.attrs = attrs;
    f.values = e => Object.fromEntries(crit.map(c => [c, [...(attrs.get(e) || {})[c] || []].sort()]));
    f.of = h => Object.fromEntries(crit.map(c => [c, L.hhValue(h, c)]).filter(([, v]) => v));
    return f;
  };
  // the enumerators who can take a household: all of them without criteria, else those who match (none: unassignable)
  L.deal = (items, enums, shares, rnd, exclude, eligible) => {
    const keyed = items.map(h => ({ h, k: rnd() })).sort((a, b) => cmpStr(a.h.stratum || '', b.h.stratum || '') || a.k - b.k).map(x => x.h);
    const N = keyed.length, quota = L.quotas(N, enums, shares), got = new Map(enums.map(e => [e, 0])), out = new Map();
    keyed.forEach((h, i) => {
      const k = i + 1, ex = exclude && exclude.get(h.hhid), ok = e => !eligible || eligible(h, e);
      let allowed = enums.filter(e => e !== ex && ok(e) && quota.get(e) > 0);
      if (!allowed.length) allowed = enums.filter(e => e !== ex && ok(e));
      if (!allowed.length) allowed = enums.filter(ok);
      if (!allowed.length) { out.set(h.hhid, null); return; }
      let best = null, bv = -Infinity;
      for (const e of allowed) { const v = quota.get(e) * k / N - got.get(e); if (v > bv + 1e-12) { bv = v; best = e; } }
      out.set(h.hhid, best); got.set(best, got.get(best) + 1);
    });
    return out;
  };

  // ---- the assignment rules (C) ----
  // input: {round, households: [{hhid, stratum, psu, ...}], team: [{id, available, share}], hist, tz, cap, rule: {name, rotation_share, seed, order_by, method}, manual: Map}
  L.assign = inp => {
    const rule = inp.rule, rnd = L.rng(rule.seed), t = inp.round;
    const team = inp.team.filter(e => e.available);
    const enums = team.map(e => e.id);
    const shares = new Map(team.map(e => [e.id, e.share > 0 ? e.share : 1]));
    const out = new Map(), notes = [], warnings = [], unmatched = [];
    if (!enums.length) return { out, notes, warnings: ['No enumerator is available.'], errors: ['Mark at least one enumerator as available.'], unmatched };
    const elig = L.eligibleFn(inp.criteria, team);
    const byId = new Map(inp.households.map(h => [h.hhid, h]));
    const sumOf = new Map(inp.households.map(h => [h.hhid, L.summaryOf(inp.hist, h.hhid, t, inp.tz)]));
    const before = h => { const s = sumOf.get(h.hhid); return (s.last_interview && s.last_interview.enumerator) || s.previous || null; };
    const isNew = h => { const s = sumOf.get(h.hhid); return s.joined_round === null; };
    // e === null: no available enumerator matches the household's criteria; the leader assigns it by hand
    const set = (h, e, reason, prev) => {
      if (e === null) { out.delete(h.hhid); if (!unmatched.includes(h.hhid)) unmatched.push(h.hhid); return; }
      out.set(h.hhid, R.clean({ enumerator_id: e, reason, previous_enumerator: prev && prev !== e ? prev : undefined, matched: elig ? elig(h, e) : undefined }));
    };
    const reasonFor = (h, e, moved) => (isNew(h) ? 'new' : before(h) === e ? 'keep' : moved);
    const dealTo = (items, sh, excl) => L.deal(items, enums, sh, rnd, excl, elig);
    if (rule.name === 'keep_same') {
      if (!Number.isFinite(rule.rotation_share) || rule.rotation_share < 0 || rule.rotation_share > 1) return { out, notes, warnings, errors: ['Enter the rotation share for this round (0 to 100%). It has no default: the handbook calls its size a judgment.'], unmatched };
      const fresh = [], away = [], hard = [], mis = [];
      const lm = inp.hist.manifests.get(t - 1), lastCap = (lm && lm.calendar && lm.calendar.dial_cap) || inp.cap;
      for (const h of inp.households) {
        const s = sumOf.get(h.hhid), start = before(h);
        if (!start || isNew(h)) { fresh.push(h); continue; }                                          // step 1: new households
        if (!enums.includes(start)) { away.push(h); continue; }                                      // step 2: enumerator away
        if ((!s.interviewed_last && s.in_last && s.dials_last >= lastCap) || s.switch_requested) { hard.push(h); continue; } // step 3 (D5)
        if (elig && !elig(h, start)) { mis.push(h); continue; }                                       // the criteria: the kept enumerator does not match
        set(h, start, 'keep');                                                                        // step 1: keep
      }
      dealTo(fresh, shares).forEach((e, id) => set(byId.get(id), e, 'new'));
      const awayPrev = new Map(away.map(h => [h.hhid, before(h)]));
      dealTo(away, shares).forEach((e, id) => set(byId.get(id), e, 'enumerator_unavailable', awayPrev.get(id)));
      const hardPrev = new Map(hard.map(h => [h.hhid, before(h)]));
      dealTo(hard, shares, hardPrev).forEach((e, id) => set(byId.get(id), e, 'switch_hard_to_reach', hardPrev.get(id)));
      const misPrev = new Map(mis.map(h => [h.hhid, before(h)]));
      dealTo(mis, shares, misPrev).forEach((e, id) => set(byId.get(id), e, 'match', misPrev.get(id)));
      // step 4: rotation, a share r of each enumerator's kept households, dealt to the others
      const given = new Map(), pool = [], from = new Map();
      for (const e of enums) {
        const kept = inp.households.filter(h => out.get(h.hhid) && out.get(h.hhid).enumerator_id === e && out.get(h.hhid).reason === 'keep').sort((a, b) => cmpStr(a.hhid, b.hhid));
        const k = Math.round(rule.rotation_share * kept.length);
        given.set(e, k);
        L.shuffled(kept, rnd).slice(0, k).forEach(h => { pool.push(h); from.set(h.hhid, e); });
      }
      if (pool.length && enums.length > 1) {
        dealTo(pool, given, from).forEach((e, id) => set(byId.get(id), e, e === from.get(id) ? 'keep' : 'rotation', from.get(id)));
      }
      notes.push(`Kept ${[...out.values()].filter(x => x.reason === 'keep').length}, new ${fresh.length}, enumerator away ${away.length}, hard to reach ${hard.length}, rotated ${[...out.values()].filter(x => x.reason === 'rotation').length}${elig ? `, moved to match the criteria ${[...out.values()].filter(x => x.reason === 'match').length}` : ''}.`);
    } else if (rule.name === 'random' || (rule.name === 'share_of_total' && rule.method !== 'blocks') || (elig && (rule.name === 'equal_split' || rule.name === 'share_of_total'))) {
      const sh = rule.name === 'equal_split' ? new Map(enums.map(e => [e, 1])) : shares;
      if (elig && rule.name !== 'random') notes.push('With matching criteria, households are dealt to the enumerators who match them; the list is not cut into blocks.');
      dealTo(inp.households, sh).forEach((e, id) => { const h = byId.get(id); set(h, e, reasonFor(h, e, 'rule'), before(h)); });
    } else if (rule.name === 'equal_split' || rule.name === 'share_of_total') {
      const key = rule.order_by || 'psu';
      const sorted = inp.households.slice().sort((a, b) => cmpStr(L.hhValue(a, key), L.hhValue(b, key)) || cmpStr(a.hhid, b.hhid));
      const q = rule.name === 'equal_split' ? L.quotas(sorted.length, enums, new Map(enums.map(e => [e, 1]))) : L.quotas(sorted.length, enums, shares);
      let i = 0;
      for (const e of enums) for (let k = 0; k < q.get(e); k++, i++) { const h = sorted[i]; set(h, e, reasonFor(h, e, 'rule'), before(h)); }
      warnings.push('With consecutive blocks, enumerator and area effects cannot be told apart (Section 3.2).');
    } else if (rule.name === 'manual') {
      const m = inp.manual || new Map();
      const unknown = new Set(), mism = [];
      for (const h of inp.households) {
        const e = m.get(h.hhid);
        if (!e) continue;
        if (!enums.includes(e)) { unknown.add(e); continue; }
        set(h, e, reasonFor(h, e, 'manual'), before(h));
        if (elig && !elig(h, e)) mism.push(h.hhid);
      }
      const missing = inp.households.filter(h => !out.has(h.hhid)).length;
      if (unknown.size) warnings.push(`Unknown or unavailable enumerator IDs in the manual list: ${[...unknown].join(', ')}.`);
      if (missing) warnings.push(`${R.plural(missing, 'household')} ${missing === 1 ? 'has' : 'have'} no enumerator in the manual list.`);
      if (mism.length) warnings.push(`${R.plural(mism.length, 'household')} in the manual list ${mism.length === 1 ? 'does' : 'do'} not match ${mism.length === 1 ? 'its' : 'their'} enumerator's values (${elig.criteria.join(', ')}): ${mism.slice(0, 8).join(', ')}${mism.length > 8 ? '…' : ''}. Kept as listed, marked as not matched.`);
    }
    if (unmatched.length) {
      unmatched.sort(cmpStr);
      const show = id => `${id} (${elig.criteria.map(c => `${c} ${L.hhValue(byId.get(id), c) || '–'}`).join(', ')})`;
      warnings.push(`${R.plural(unmatched.length, 'household')} ${unmatched.length === 1 ? 'matches' : 'match'} no available enumerator on ${elig.criteria.join(', ')}: ${unmatched.slice(0, 8).map(show).join('; ')}${unmatched.length > 8 ? '…' : ''}. Give an enumerator these values in step 5, or assign them by hand in step 7. No file is written while a household has no enumerator.`);
    }
    return { out, notes, warnings, errors: [], summaries: sumOf, unmatched, criteria: elig ? elig.criteria : [] };
  };

  // step 5, the load check: each enumerator's households and expected dials, using last round's dials per household
  L.expectedDials = (inp, sums) => {
    const last = [...sums.values()].filter(s => s.in_last).map(s => s.dials_last);
    const mean = last.length ? last.reduce((a, b) => a + b, 0) / last.length : inp.cap / 2;
    return id => { const s = sums.get(id); return s && s.in_last ? s.dials_last : mean; };
  };
  L.loads = (inp, out, sums) => {
    const team = inp.team.filter(e => e.available);
    const exp = L.expectedDials(inp, sums);
    const tot = team.reduce((s, e) => s + (e.share > 0 ? e.share : 1), 0);
    const all = [...out.entries()];
    const totalDials = all.reduce((s, [id]) => s + exp(id), 0);
    return team.map(e => {
      const mine = all.filter(([, x]) => x.enumerator_id === e.id);
      const dials = mine.reduce((s, [id]) => s + exp(id), 0);
      const target = totalDials * (e.share > 0 ? e.share : 1) / tot;
      return { id: e.id, households: mine.length, dials, target, departure: target ? dials / target - 1 : 0 };
    });
  };
  // move kept households, chosen at random, from the most to the least loaded enumerator while a load is outside the margin
  L.balance = (inp, out, sums, margin, seed) => {
    const rnd = L.rng((seed || 1) + 7), moves = [], exp = L.expectedDials(inp, sums);
    const elig = L.eligibleFn(inp.criteria, inp.team.filter(e => e.available)), hh = new Map(inp.households.map(h => [h.hhid, h]));
    for (let guard = 0; guard < 5000; guard++) {
      const ld = L.loads(inp, out, sums).sort((a, b) => b.departure - a.departure);
      const hi = ld[0], lo = ld[ld.length - 1];
      if (!hi || hi.id === lo.id || (hi.departure <= margin && lo.departure >= -margin)) break;
      // only a move that narrows the gap between the two, and only to an enumerator who matches the household (criteria)
      const cand = [...out.entries()].filter(([id, x]) => x.enumerator_id === hi.id && x.reason === 'keep' && exp(id) < hi.dials - lo.dials && (!elig || elig(hh.get(id), lo.id))).map(([id]) => id).sort();
      if (!cand.length) break;
      const id = cand[Math.floor(rnd() * cand.length)];
      out.set(id, R.clean({ enumerator_id: lo.id, reason: 'capacity', previous_enumerator: hi.id, matched: elig ? true : undefined }));
      moves.push({ hhid: id, from: hi.id, to: lo.id });
    }
    return moves;
  };

  // ---- planning first dials (D) ----
  L.workingDays = cal => {
    const out = [], hol = new Map((cal.holidays || []).map(h => [h.date, h]));
    for (let k = cal.window_start; k <= cal.window_end; k = R.addDaysKey(k, 1)) {
      const h = hol.get(k);
      if (cal.working_weekdays.includes(R.weekdayOfKey(k)) && !(h && !h.working)) out.push(k);
    }
    return out;
  };
  L.plan = (inp, out, sums, H) => {
    const cal = inp.calendar, days = L.workingDays(cal);
    const first = days.slice(0, Math.max(1, Math.round((inp.spread || 0.5) * days.length)));
    const hours = cal.call_hours, ram = new Set((cal.ramadan && cal.ramadan.dates) || []), bf = cal.ramadan && cal.ramadan.break_fast_hour;
    const best = L.bestHours(H, inp.tz, hours, 50);
    const byEnum = new Map();
    for (const [id, x] of out) { if (!byEnum.has(x.enumerator_id)) byEnum.set(x.enumerator_id, []); byEnum.get(x.enumerator_id).push(id); }
    const hh = new Map(inp.households.map(h => [h.hhid, h]));
    const plans = new Map();
    for (const [, ids] of byEnum) {
      const pri = id => {
        const s = sums.get(id), x = out.get(id), h = hh.get(id);
        // new to the panel, switched as hard to reach, or in the high dropout tier: first (Section 3.4 box)
        return [s.joined_round === null || x.reason === 'switch_hard_to_reach' || (inp.highRisk && inp.highRisk.has(id)) ? 0 : 1, (h.phones || []).length <= 1 ? 0 : 1];
      };
      ids.sort((a, b) => { const pa = pri(a), pb = pri(b); return pa[0] - pb[0] || pa[1] - pb[1] || cmpStr(a, b); });
      let spread = 0;
      ids.forEach((id, i) => {
        const s = sums.get(id);
        const date = first[Math.floor(i * first.length / ids.length)];
        let hour = s.last_interview && Number.isInteger(s.last_interview.hour) ? s.last_interview.hour
          : best.length ? best[spread++ % best.length] : hours.start + (spread++ % Math.max(1, hours.end - hours.start));
        hour = Math.max(hours.start, Math.min(hours.end - 1, hour));
        if (ram.has(date) && hour === bf) hour = hour + 1 < hours.end ? hour + 1 : hour - 1;
        plans.set(id, { first_dial_date: date, target_hour: hour, order: i + 1 });
      });
    }
    return { plans, best, firstDays: first.length, workingDays: days.length };
  };

  // ---- the round files (A.3, A.6) ----
  const contactOf = (h, slotLast) => R.clean({ name: h.name, phones: (h.phones || []).map(p => R.clean(Object.assign({}, p, { last_status: slotLast ? slotLast[p.slot] : undefined }))) });
  L.buildFiles = inp => {
    const files = [], byEnum = new Map();
    for (const [id, x] of inp.out) { if (!byEnum.has(x.enumerator_id)) byEnum.set(x.enumerator_id, []); byEnum.get(x.enumerator_id).push(id); }
    const hh = new Map(inp.households.map(h => [h.hhid, h]));
    const rule = R.clean(Object.assign({ name: inp.rule.name }, inp.rule.name === 'keep_same' ? { rotation_share: inp.rule.rotation_share, hard_to_reach: 'missed_with_full_cap_or_request', fallback: 'random' } : {},
      inp.rule.order_by && /split|share/.test(inp.rule.name) ? { order_by: inp.rule.order_by } : {}, inp.rule.method ? { method: inp.rule.method } : {}, { seed: inp.rule.seed }));
    const team = inp.team.filter(e => e.available);
    const elig = L.eligibleFn(inp.criteria, team);
    for (const e of team.map(x => x.id)) {
      const ids = (byEnum.get(e) || []).slice().sort(cmpStr);
      const households = ids.map(id => {
        const h = hh.get(id), s = inp.sums.get(id), x = inp.out.get(id);
        const reps = (inp.replacements.get(id) || []).map((r, i) => ({ hhid: r.hhid, rank: i + 1, contact: contactOf(inp.allHouseholds.get(r.hhid) || { phones: [] }) }));
        const last = s.last_interview ? R.clean({ round: s.last_interview.round, date: s.last_interview.date, hour: s.last_interview.hour }) : undefined;
        const crit = elig ? elig.of(h) : null;
        return R.clean({
          hhid: id, psu: h.psu, stratum: h.stratum, tz: h.tz,
          contact: contactOf(h, s.slot_last),
          history: R.clean({ joined_round: s.joined_round === null ? inp.round : s.joined_round, last_interview: last, last3: s.last3 || undefined,
            last_enumerator: s.last_interview ? s.last_interview.enumerator : undefined }),
          assignment: R.clean({ reason: x.reason, previous_enumerator: x.previous_enumerator, matched: elig ? (x.matched !== undefined ? x.matched : elig(h, e)) : undefined }),
          criteria: crit && Object.keys(crit).length ? crit : undefined,
          plan: inp.plans.get(id), replacements: reps.length ? reps : undefined,
        });
      });
      const a = R.clean({
        schema: R.SCHEMA.assign, tool_version: R.VERSION, program: inp.program, country: inp.country, round: inp.round, enumerator_id: e,
        generated_by: inp.leader, generated_at: inp.generated_at, revision: 1, rule, replacement_policy: inp.replacement_policy,
        matching: elig ? { criteria: elig.criteria, enumerator: elig.values(e) } : undefined,
        synthetic: inp.synthetic ? true : undefined, calendar: inp.calendar, households,
      });
      a.fingerprint = R.fingerprint(a);
      files.push({ enumerator_id: e, name: `${e}_assignment_R${p2(inp.round)}.json`, obj: a });
    }
    const manifest = R.clean({
      schema: L.SCHEMA.manifest, tool_version: R.VERSION, program: inp.program, country: inp.country, round: inp.round,
      generated_by: inp.leader, generated_at: inp.generated_at, revision: 1, synthetic: inp.synthetic ? true : undefined, rule, replacement_policy: inp.replacement_policy,
      matching: elig ? { criteria: elig.criteria, enumerators: Object.fromEntries(team.map(t => [t.id, elig.values(t.id)])) } : undefined,
      calendar: inp.calendar, away: inp.team.filter(e => !e.available).map(e => e.id),
      enumerators: team.map(t => ({ enumerator_id: t.id, available: true, share: t.share > 0 ? t.share : 1, households: (byEnum.get(t.id) || []).length,
        file: `${t.id}_assignment_R${p2(inp.round)}.json`, fingerprint: files.find(f => f.enumerator_id === t.id).obj.fingerprint })),
      households: [...inp.out.entries()].sort((a, b) => cmpStr(a[0], b[0])).map(([id, x]) => R.clean({
        hhid: id, enumerator_id: x.enumerator_id, reason: x.reason, previous_enumerator: x.previous_enumerator, matched: x.matched,
        psu: hh.get(id).psu, stratum: hh.get(id).stratum,
        replacements: (inp.replacements.get(id) || []).length ? inp.replacements.get(id).map(r => r.hhid) : undefined })),
    });
    manifest.fingerprint = R.fingerprint(manifest);
    return { files, manifest, calendarRow: { round: inp.round, start: inp.calendar.window_start, end: inp.calendar.window_end } };
  };
  // which households take part in the round: those to assign, the reserves still unused, and those removed.
  // A household listed as a replacement, never activated and without an explicit status is a reserve.
  L.roundHouseholds = (Hl, lists, hist, t) => {
    const asRepl = new Set();
    for (const l of (lists || new Map()).values()) l.forEach(r => asRepl.add(r.hhid));
    const reserves = new Set(), mains = [], removed = [], warnings = [];
    for (const h of Hl.values()) {
      const s = L.summaryOf(hist, h.hhid, t, null);
      const unused = s.joined_round === null && !s.activated;
      if (h.status === 'removed') { removed.push(h); continue; }
      if (h.status === 'reserve' || (asRepl.has(h.hhid) && unused && !h.status_given)) { if (unused) reserves.add(h.hhid); continue; }
      mains.push(h);
    }
    const replaced = new Set(), asked = new Set();
    for (const [, l] of hist.actions) l.forEach(a => { if (a.action === 'ACTIVATE_REPLACEMENT') replaced.add(a.hhid); });
    (hist.actions.get(t - 1) || []).forEach(a => { if (a.action === 'REMOVE_REQUEST') asked.add(a.hhid); });
    const stillActive = mains.filter(h => replaced.has(h.hhid)).map(h => h.hhid);
    if (stillActive.length) warnings.push(`${R.plural(stillActive.length, 'household')} ${stillActive.length === 1 ? 'was' : 'were'} replaced in an earlier round but ${stillActive.length === 1 ? 'is' : 'are'} still active in the list: ${stillActive.slice(0, 8).join(', ')}${stillActive.length > 8 ? '…' : ''}. Mark them removed if they leave the panel.`);
    const askedActive = mains.filter(h => asked.has(h.hhid)).map(h => h.hhid);
    if (askedActive.length) warnings.push(`${R.plural(askedActive.length, 'household')} ${askedActive.length === 1 ? 'was' : 'were'} asked to be removed last round (no number works) and ${askedActive.length === 1 ? 'is' : 'are'} still active: ${askedActive.slice(0, 8).join(', ')}.`);
    return { mains, reserves, removed, warnings };
  };
  // the replacements each main household still has: unused reserves with contacts in the list, in order
  L.availableReplacements = (lists, reserves, Hl) => {
    const out = new Map();
    for (const [main, l] of lists) {
      const free = l.filter(r => reserves.has(r.hhid) && Hl.has(r.hhid));
      if (free.length) out.set(main, free);
    }
    return out;
  };
  // ---- reading an enumerator's export (A.4) ----
  const enumFromName = n => (/^([^_]+)_\d{4}-\d\d-\d\d/.exec(baseName(n)) || [])[1] || '';
  L.readImport = (name, text) => {
    const sha = R.sha256(String(text)), base = baseName(name), t = String(text).replace(/^﻿/, '').trim();
    if (t.startsWith('{')) {
      let o; try { o = JSON.parse(t); } catch (e) { return { name, sha, base, kind: 'unknown', problem: 'not readable JSON' }; }
      if (o.schema === R.SCHEMA.calllog) {
        const ev = Array.isArray(o.events) ? o.events : [];
        return { name, sha, base, kind: 'json', program: o.program, round: o.round, enumerator_id: o.enumerator_id || enumFromName(name), exported_at: o.exported_at,
          at: Date.parse(o.exported_at) || 0, events: ev, dials: o.dials || [], chain: R.verifyChain(ev, o.chain_genesis),
          lastOk: (ev.length ? ev[ev.length - 1].hash : o.chain_genesis) === o.last_hash, genesis: o.chain_genesis, fingerprint: o.assignment_fingerprint, count: ev.length,
          contact_updates: o.contact_updates || [] };
      }
      if (o.schema === R.SCHEMA.contacts) return { name, sha, base, kind: 'contacts', program: o.program, round: o.round, enumerator_id: o.enumerator_id, exported_at: o.exported_at, updates: o.updates || [] };
      if (o.schema === R.SCHEMA.sealed) return { name, sha, base, kind: 'sealed', env: o, contains: o.contains, program: o.program, round: o.round, enumerator_id: o.enumerator_id };
      if (o.schema === L.SCHEMA.manifest) return { name, sha, base, kind: 'manifest', manifest: o, program: o.program, round: o.round };
      return { name, sha, base, kind: 'unknown', problem: `its schema is "${o.schema || 'missing'}"` };
    }
    const head = (t.split(/\r?\n/)[0] || '').split(',');
    if (head.join(',') === R.CSV_COLS.join(',')) {
      const rows = R.parseCSV(t);
      const ids = [...new Set(rows.map(r => r.logged_by || r.operator).filter(Boolean))];
      // a CSV's time is its last logged entry, kept in the enumerator's own clock as a JSON's export time is
      const last = rows.reduce((m, r) => ((Date.parse(r.logged_at) || 0) > (m ? Date.parse(m.logged_at) || 0 : 0) ? r : m), null);
      const at = last ? Date.parse(last.logged_at) || 0 : 0;
      return { name, sha, base, kind: 'csv', program: rows.length ? rows[0].program : '', round: rows.length ? +rows[0].round : null,
        enumerator_id: ids.length === 1 ? ids[0] : enumFromName(name), several: ids.length > 1, rows, at, exported_at: last ? last.logged_at : '', count: rows.length };
    }
    return { name, sha, base, kind: 'unknown', problem: 'not a call-log export, contacts file or manifest' };
  };
  // a CSV row back into a dial (the CSV holds dials with corrections applied, so no further correction is possible)
  const rowDial = r => {
    const off = r.utc_offset || '';
    const iso = w => (w ? w.replace(' ', 'T') + off : undefined);
    return R.clean({ event_id: r.event_id, type: 'dial', program: r.program, round: +r.round, hhid: r.hhid, phone_slot: +r.phone_slot || undefined,
      ts: iso(r.ts), end_ts: iso(r.end_ts), status: r.status, operator: r.operator, appointment_ts: iso(r.appointment_ts), action: r.action,
      replaces: r.replaces, note: r.note, logged_by: r.logged_by, logged_at: r.logged_at, prev_hash: r.prev_hash, corrected: r.corrected === '1' ? 1 : 0 });
  };
  const sameRows = (csvRows, jsonDials) => {
    if (csvRows.length !== jsonDials.length) return false;
    for (let i = 0; i < csvRows.length; i++) for (const c of R.CSV_COLS) {
      const a = csvRows[i][c] == null ? '' : String(csvRows[i][c]), b = jsonDials[i][c] == null ? '' : String(jsonDials[i][c]);
      if (a !== b) return false;
    }
    return true;
  };
  L.qualifies = d => d.status === 'COMPLETE' && (d.dur_min === null || d.dur_min === undefined || d.dur_min >= R.MIN_COMPLETE_MIN);

  // ---- the merge (F): every situation gives a line in the merge report; nothing is resolved silently ----
  // resolutions: Map issue key -> {decision, note, logged_by, logged_at}
  L.merge = (M, imports, resolutions, now) => {
    const res = resolutions || new Map(), issues = [], files = [];
    const nowMs = (now || R.now()).getTime();
    const issue = x => {
      const r = res.get(x.key);
      issues.push(Object.assign(x, r ? { status: 'resolved', decision: r.decision, note: r.note, by: r.logged_by, at: r.logged_at } : { status: 'open' }));
      return r ? r.decision : null;
    };
    const roster = new Map(M.enumerators.map(e => [e.enumerator_id, e]));
    const assignedTo = new Map(M.households.map(h => [h.hhid, h.enumerator_id]));
    const replOf = new Map();
    M.households.forEach(h => (h.replacements || []).forEach(r => replOf.set(r, h.hhid)));
    // households moved during the round: the previous holder's dials up to the move were theirs to make
    const movesOf = new Map();
    (M.moves || []).forEach(m => { if (!movesOf.has(m.hhid)) movesOf.set(m.hhid, []); movesOf.get(m.hhid).push(m); });
    const heldBefore = (e, h, ts) => (movesOf.get(h) || []).some(m => m.from === e && Date.parse(ts) <= Date.parse(m.at));
    const fingerprintsOf = e => (roster.get(e) ? [roster.get(e).fingerprint].concat(roster.get(e).previous_fingerprints || []) : []);
    // 1. files: duplicates, other rounds, other kinds
    const seen = new Map(), usable = [], contactFiles = [];
    for (const f of imports) {
      const row = { name: f.name, kind: f.kind, enumerator_id: f.enumerator_id || '', exported_at: f.exported_at || '', count: f.count || 0, use: '' };
      files.push(row);
      if (seen.has(f.sha)) {
        row.use = 'duplicate, ignored';
        issue({ key: `duplicate:${f.name}`, type: 'duplicate', severity: 'info', file: f.name, enumerator: f.enumerator_id, detail: `Identical to ${seen.get(f.sha)}: the copy is ignored.` });
        continue;
      }
      seen.set(f.sha, f.name);
      // a log or contacts file of another round or program is not merged here; the leader opens it in that round's session (F)
      const isLog = f.kind === 'json' || f.kind === 'csv', isContacts = f.kind === 'contacts' || f.kind === 'sealed';
      const otherRound = (isLog && (f.program !== M.program || +f.round !== +M.round))
        || (isContacts && f.program !== undefined && f.round !== undefined && (f.program !== M.program || +f.round !== +M.round));
      if (otherRound) {
        row.use = 'other round, not merged';
        issue({ key: `wrong_round:${f.sha}`, type: 'wrong_round', severity: 'action', file: f.name, enumerator: f.enumerator_id,
          detail: `This is ${f.program || '?'} round ${f.round || '?'}, not ${M.program} round ${M.round}. It is not merged into this round: open it in the leader session for ${f.program || 'its program'} round ${f.round || '?'}.` });
        continue;
      }
      if (isLog) usable.push({ f, row });
      else if (isContacts) { row.use = f.kind === 'sealed' ? 'protected contacts file' : 'contacts file'; contactFiles.push(f); }
      else if (f.kind === 'manifest') row.use = 'a manifest, not a log';
      else { row.use = 'not read'; issue({ key: `unknown:${f.sha}`, type: 'unknown_file', severity: 'info', file: f.name, detail: `Not a file the merge reads: ${f.problem}.` }); }
    }
    const stampOf = f => (f.exported_at || '').slice(0, 16).replace('T', ' ');
    // 2. per enumerator: the latest export, CSVs checked against their JSON, chains verified
    const groups = new Map();
    usable.forEach(x => { const e = x.f.enumerator_id; if (!groups.has(e)) groups.set(e, []); groups.get(e).push(x); });
    const perEnum = new Map(), excludedEvents = new Set(), eventSource = new Map();
    for (const [e, xs] of groups) {
      if (!roster.has(e)) issue({ key: `unknown_enumerator:${e}`, type: 'unknown_enumerator', severity: 'action', enumerator: e,
        detail: `${e} is not in this round's manifest. Their dials are kept and flagged.` });
      const js = xs.filter(x => x.f.kind === 'json'), cs = xs.filter(x => x.f.kind === 'csv');
      // a CSV pairs with the JSON of the same name whose rows it matches; same-day exports share a name
      for (const c of cs) {
        const same = js.filter(x => x.f.base === c.f.base);
        if (!same.length) continue;
        c.paired = true;
        const j = same.find(x => sameRows(c.f.rows, x.f.dials));
        if (j) { c.row.use = `checked against ${j.f.name}${same.length > 1 ? `, exported ${stampOf(j.f)}` : ''}`; continue; }
        // same-day exports share a name. A CSV logged after every same-name JSON is a later export whose JSON did not
        // arrive (F: the later export is used, a CSV alone as unverified); a dial voided in between shows as a gap,
        // which the leader settles. A CSV whose dials the JSON already knows, unchanged or corrected since, is an
        // earlier export. Anything else is a CSV that differs from its JSON.
        if (same.every(x => c.f.at > x.f.at)) { c.paired = false; continue; }
        const evs = same.flatMap(x => x.f.events || []);
        const known = new Map(evs.filter(ev => ev.type === 'dial').map(ev => [ev.event_id, ev]));
        const fixed = new Set(evs.filter(ev => ev.type === 'correction').map(ev => ev.target));
        const earlier = c.f.rows.every(r => { const ev = known.get(r.event_id); return ev && (fixed.has(r.event_id) || (ev.hhid === r.hhid && ev.status === r.status && String(ev.phone_slot || '') === String(r.phone_slot || ''))); });
        // an earlier export holds every dial logged before it; one lacking such a dial was written after a void, or edited
        const ids = new Set(c.f.rows.map(r => r.event_id));
        const whole = same.every(x => x.f.dials.filter(d => (Date.parse(d.logged_at) || 0) <= c.f.at).every(d => ids.has(d.event_id)));
        if (earlier && whole && c.f.at <= Math.max(...same.map(x => x.f.at))) { c.paired = false; continue; }
        const near = same.slice().sort((a, b) => Math.abs(a.f.at - c.f.at) - Math.abs(b.f.at - c.f.at))[0];
        c.row.use = `differs from ${near.f.name}`;
        issue({ key: `csv_differs:${c.f.sha}`, type: 'csv_differs', severity: 'action', file: c.f.name, enumerator: e,
          detail: `The CSV's rows match no JSON export of the same name (nearest: ${near.f.name}). The JSON is used.` });
      }
      js.forEach(x => {
        if (!x.f.chain.ok) issue({ key: `chain:${x.f.sha}`, type: 'chain_broken', severity: 'action', file: x.f.name, enumerator: e,
          detail: `Integrity check failed at event ${x.f.chain.index + 1} of ${x.f.count}: ${x.f.chain.reason}. The file is imported and marked.` });
        else if (!x.f.lastOk) issue({ key: `lasthash:${x.f.sha}`, type: 'chain_broken', severity: 'action', file: x.f.name, enumerator: e,
          detail: 'The file’s last hash does not match its last event: events may have been removed at the end.' });
        const fps = fingerprintsOf(e);
        if (fps.length && x.f.genesis && !fps.includes(x.f.genesis)) issue({ key: `genesis:${x.f.sha}`, type: 'other_assignment', severity: 'info', file: x.f.name, enumerator: e,
          detail: 'The log did not start from the assignment file this manifest lists for this enumerator.' });
      });
      const lone = cs.filter(c => !c.paired);
      const cands = js.concat(lone).sort((a, b) => (b.f.at - a.f.at) || ((b.f.chain && b.f.chain.ok ? 1 : 0) - (a.f.chain && a.f.chain.ok ? 1 : 0)) || (b.f.count - a.f.count) || cmpStr(a.f.name, b.f.name));
      const latest = cands[0];
      latest.row.use = latest.f.kind === 'json' ? (latest.f.chain.ok ? 'used' : 'used, integrity check failed') : 'used, unverified';
      if (latest.f.kind === 'csv') {
        const prior = cands.slice(1).find(x => x.f.kind === 'json');
        issue({ key: `unverified:${latest.f.sha}`, type: 'unverified', severity: 'info', file: latest.f.name, enumerator: e,
          detail: `A CSV without its JSON: imported as unverified, because its hash chain cannot be checked.${prior ? ` Its dials and the actions taken with them are used; other actions and contact updates come from the earlier ${prior.f.name}.` : ' Only its dials and the actions taken with them are known: releases or requests made apart from a call, and contact updates, come only with the JSON.'}` });
      }
      cands.slice(1).forEach(x => {
        const sameTime = x.f.at === latest.f.at, ok = latest.f.kind === 'json' && latest.f.chain.ok ? ', whose integrity check passes,' : '';
        x.row.use = sameTime ? `not used: ${latest.f.name}${ok} has the same time` : `replaced by the later export, ${latest.f.name} of ${stampOf(latest.f)}`;
        issue({ key: `older:${x.f.sha}`, type: 'older_export', severity: 'info', file: x.f.name, enumerator: e,
          detail: sameTime ? `Another export of ${e} with the same time (${stampOf(x.f)}): ${latest.f.name}${ok} is used.`
            : `An earlier export of ${e} (${stampOf(x.f)}): the later ${latest.f.name} (${stampOf(latest.f)}) is used.` });
      });
      let events;
      if (latest.f.kind === 'json') {
        const byId = new Map(latest.f.events.map(ev => [ev.event_id, ev]));
        const extra = [];
        for (const x of cands.slice(1)) {
          if (x.f.kind !== 'json') continue;
          const missing = x.f.events.filter(ev => !byId.has(ev.event_id));
          if (missing.length) {
            issue({ key: `gap:${x.f.sha}`, type: 'gap', severity: 'action', file: x.f.name, enumerator: e,
              detail: `${latest.f.name} lacks ${R.plural(missing.length, 'event')} that the earlier ${x.f.name} has. Both are kept.` });
            missing.forEach(ev => { byId.set(ev.event_id, ev); extra.push(ev); eventSource.set(ev.event_id, x.f.name); });
          }
        }
        for (const x of cands.slice(1)) {
          if (x.f.kind !== 'csv') continue;
          const missing = x.f.rows.map(rowDial).filter(d => !byId.has(d.event_id));
          if (missing.length) {
            issue({ key: `gap:${x.f.sha}`, type: 'gap', severity: 'action', file: x.f.name, enumerator: e,
              detail: `${latest.f.name} lacks ${R.plural(missing.length, 'dial')} that the earlier ${x.f.name} has. Both are kept.` });
            missing.forEach(d => { byId.set(d.event_id, d); extra.push(d); eventSource.set(d.event_id, x.f.name); });
          }
        }
        // the same event in two files with different content
        for (const x of cands.slice(1)) {
          if (x.f.kind !== 'json') continue;
          for (const ev of x.f.events) {
            const mine = byId.get(ev.event_id);
            if (!mine || R.canon(R.publicPart(mine)) === R.canon(R.publicPart(ev))) continue;   // compare content: an edit leaves the stored hash unchanged
            const d = issue({ key: `event_conflict:${ev.event_id}`, type: 'event_conflict', severity: 'action', file: x.f.name, enumerator: e, hhid: ev.hhid, event_id: ev.event_id,
              detail: `Event ${ev.event_id.slice(0, 8)} differs between ${latest.f.name} and ${x.f.name}. It is left out of the counts until you choose a version.`,
              choices: [{ value: `use:${latest.f.sha}`, label: `Use ${latest.f.name}` }, { value: `use:${x.f.sha}`, label: `Use ${x.f.name}` }, { value: 'exclude', label: 'Leave it out' }] });
            if (!d || d === 'exclude') excludedEvents.add(ev.event_id);
            else if (d === `use:${x.f.sha}`) byId.set(ev.event_id, ev);
          }
        }
        events = latest.f.events.map(ev => byId.get(ev.event_id)).concat(extra);
        const eff = R.effective({ events });
        perEnum.set(e, { file: latest.f, dials: eff.dials, actions: eff.actions, contacts: eff.contacts, events });
      } else {
        const dials = latest.f.rows.map(rowDial);
        dials.forEach(d => { d.dur_min = d.end_ts ? Math.max(0, (Date.parse(d.end_ts) - Date.parse(d.ts)) / 60000) : null; });
        const viaDial = d => ({ event_id: d.event_id, type: 'action', hhid: d.hhid, action: d.action, logged_by: d.logged_by, logged_at: d.logged_at, via: 'dial' });
        const actions = dials.filter(d => d.action).map(viaDial);
        const haveD = new Set(dials.map(d => d.event_id)), haveA = new Set(actions.map(a => a.event_id));
        let contacts = [];
        const prior = cands.slice(1).find(x => x.f.kind === 'json');
        if (prior) {
          const eff = R.effective({ events: prior.f.events });
          eff.standaloneActions.filter(a => !haveA.has(a.event_id)).forEach(a => { actions.push(a); haveA.add(a.event_id); });
          contacts = eff.contacts;
        }
        // dials an earlier export has and this CSV lacks. A CSV holds only the dials in force, so a dial voided after the
        // earlier export also looks missing: kept, with any action taken with it, unless the leader says it was voided
        const lost = new Map();
        for (const x of cands.slice(1)) {
          const ds = x.f.kind === 'json' ? R.effective({ events: x.f.events }).dials : x.f.rows.map(rowDial);
          ds.filter(d => !haveD.has(d.event_id) && !lost.has(d.event_id)).forEach(d => lost.set(d.event_id, { d, from: x.f.name }));
        }
        if (lost.size) {
          const froms = [...new Set([...lost.values()].map(v => v.from))].join(', ');
          const dec = issue({ key: `gap:${latest.f.sha}`, type: 'gap', severity: 'action', file: latest.f.name, enumerator: e,
            detail: `${latest.f.name} lacks ${R.plural(lost.size, 'dial')} that the earlier ${froms} ${froms.includes(',') ? 'have' : 'has'}. They are kept, as for any gap, unless they were voided after that export.`,
            choices: [{ value: 'keep', label: 'Keep them' }, { value: 'exclude', label: 'Leave them out: voided after the earlier export' }] });
          if (dec !== 'exclude') {
            for (const { d } of lost.values()) {
              if (d.dur_min === undefined) d.dur_min = d.end_ts ? Math.max(0, (Date.parse(d.end_ts) - Date.parse(d.ts)) / 60000) : null;
              dials.push(d);
              if (d.action && !haveA.has(d.event_id)) { actions.push(viaDial(d)); haveA.add(d.event_id); }
            }
          }
        }
        perEnum.set(e, { file: latest.f, dials, actions, contacts, events: null, unverified: true });
      }
    }
    // 3. households: dials outside the enumerator's assignment, two completes, implausible clocks
    const excludedDials = new Set();
    const activatedBy = new Map();
    for (const [e, x] of perEnum) x.actions.filter(a => a.action === 'ACTIVATE_REPLACEMENT' && a.target_hhid).forEach(a => activatedBy.set(a.target_hhid, { e, main: a.hhid, at: a.logged_at }));
    // a replacement's dials name the household they replace, which is all a CSV without its JSON can tell
    for (const [e, x] of perEnum) x.dials.filter(d => d.replaces && !activatedBy.has(d.hhid)).forEach(d => activatedBy.set(d.hhid, { e, main: d.replaces, at: d.logged_at }));
    const mine = (e, h) => assignedTo.get(h) === e || (replOf.has(h) && assignedTo.get(replOf.get(h)) === e) || (activatedBy.has(h) && activatedBy.get(h).e === e);
    for (const [e, x] of perEnum) {
      const byHH = new Map();
      x.dials.forEach(d => { if (!byHH.has(d.hhid)) byHH.set(d.hhid, []); byHH.get(d.hhid).push(d); });
      for (const [h, ds] of byHH) {
        if (mine(e, h)) continue;
        const after = ds.filter(d => !heldBefore(e, h, d.ts));
        if (!after.length) continue;                                   // dials made while the household was theirs, before it was moved
        const mv = (movesOf.get(h) || []).filter(m => m.from === e).slice(-1)[0];
        if (mv) {
          const d = issue({ key: `after_move:${e}:${h}`, type: 'after_move', severity: 'action', enumerator: e, hhid: h,
            detail: `${e} logged ${R.plural(after.length, 'dial')} on ${h} after it was moved to ${mv.to} on ${mv.at.slice(0, 16).replace('T', ' ')}: a double call. Kept and flagged.`,
            choices: [{ value: 'accept', label: 'Keep them' }, { value: 'exclude', label: 'Leave them out' }] });
          if (d === 'exclude') after.forEach(dd => excludedDials.add(dd.event_id));
          continue;
        }
        const known = assignedTo.has(h) || replOf.has(h);
        const d = issue({ key: `not_assigned:${e}:${h}`, type: known ? 'not_assigned' : 'unknown_household', severity: 'action', enumerator: e, hhid: h,
          detail: known ? `${e} logged ${R.plural(ds.length, 'dial')} on ${h}, which is assigned to ${assignedTo.get(h) || assignedTo.get(replOf.get(h))}. Kept and flagged.`
            : `${e} logged ${R.plural(ds.length, 'dial')} on ${h}, which is not in this round's manifest: perhaps a mistyped ID. Kept and flagged.`,
          choices: [{ value: 'reassign', label: `Confirm: ${e} called ${h}` }, { value: 'typo', label: 'Mistyped ID: leave these dials out' }] });
        if (d === 'typo') ds.forEach(dd => excludedDials.add(dd.event_id));
      }
    }
    const window0 = R.zoned(M.calendar.window_start, 0, 0, M.calendar.time_zone).getTime();
    const window1 = R.zoned(R.addDaysKey(M.calendar.window_end, 1), 0, 0, M.calendar.time_zone).getTime();
    for (const [e, x] of perEnum) {
      const expAt = x.file.at || nowMs;
      // an export dated after this computer's clock: one note for the file, not one per dial
      if (x.file.at && x.file.at > nowMs + 86400000) issue({ key: `future_export:${x.file.sha}`, type: 'future_export', severity: 'info', file: x.file.name, enumerator: e,
        detail: `This export is dated ${x.file.exported_at}, later than this computer's clock (${R.localISO(new Date(nowMs)).slice(0, 16)}). One of the two clocks is wrong.` });
      for (const d of x.dials) {
        const ts = Date.parse(d.ts), te = d.end_ts ? Date.parse(d.end_ts) : null, la = Date.parse(d.logged_at);
        const why = [];
        if (ts < window0 || ts >= window1) why.push('outside the round window');
        if (ts > expAt + 300000) why.push('later than its own export');
        if (te !== null && te < ts) why.push('ends before it starts');
        if (la < ts - 60000) why.push('logged before the call started');
        if (!why.length) continue;
        const dd = issue({ key: `clock:${d.event_id}`, type: 'clock', severity: 'action', enumerator: e, hhid: d.hhid, event_id: d.event_id,
          detail: `A dial at ${R.localISO(new Date(ts))} is ${why.join(', ')}. Kept and flagged.`,
          choices: [{ value: 'accept', label: 'Keep it' }, { value: 'exclude', label: 'Leave it out' }] });
        if (dd === 'exclude') excludedDials.add(d.event_id);
      }
    }
    // all valid dials, with the enumerator whose file they came from
    const all = [];
    for (const [e, x] of perEnum) x.dials.forEach(d => { if (!excludedEvents.has(d.event_id) && !excludedDials.has(d.event_id)) all.push(Object.assign({}, d, { source: e })); });
    all.sort((a, b) => cmpStr(a.hhid, b.hhid) || (Date.parse(a.ts) - Date.parse(b.ts)) || cmpStr(a.logged_at, b.logged_at) || cmpStr(a.event_id, b.event_id));
    const n = {};
    all.forEach(d => { n[d.hhid] = (n[d.hhid] || 0) + 1; d.attempt = n[d.hhid]; });
    const actions = [];
    for (const [e, x] of perEnum) x.actions.forEach(a => { if (!excludedEvents.has(a.event_id) && !excludedDials.has(a.event_id)) actions.push(Object.assign({ program: M.program, round: M.round }, a, { source: e })); });
    actions.sort((a, b) => cmpStr(a.logged_at, b.logged_at) || cmpStr(a.event_id, b.event_id));
    // two completes for one household
    const counted = new Map(), conflictHH = new Set();
    const byHH = new Map();
    all.forEach(d => { if (!byHH.has(d.hhid)) byHH.set(d.hhid, []); byHH.get(d.hhid).push(d); });
    for (const [h, ds] of byHH) {
      const cmp = ds.filter(L.qualifies);
      if (cmp.length < 2) { if (cmp.length) counted.set(h, cmp[0]); continue; }
      const who = [...new Set(cmp.map(d => d.source))];
      const dec = issue({ key: `two_completes:${h}`, type: 'two_completes', severity: 'action', hhid: h, enumerator: who.join(', '),
        detail: `${cmp.length} completes for ${h}${who.length > 1 ? ` from ${who.join(' and ')}` : ` from ${who[0]}`}. Left out of the completion counts until you choose one.`,
        choices: cmp.map(d => ({ value: `keep:${d.event_id}`, label: `Keep ${d.source}'s, ${R.localISO(new Date(Date.parse(d.ts))).slice(0, 16).replace('T', ' ')}` }))
          .concat([{ value: 'reinterview', label: 'A re-interview: count the first' }]) });
      if (!dec) { conflictHH.add(h); continue; }
      if (dec === 'reinterview') counted.set(h, cmp[0]);
      else counted.set(h, cmp.find(d => `keep:${d.event_id}` === dec) || cmp[0]);
    }
    // 4. enumerators with no file
    for (const [e, r] of roster) {
      if (perEnum.has(e) || !r.households) continue;
      issue({ key: `missing:${e}`, type: 'missing', severity: 'action', enumerator: e,
        detail: `No export from ${e} for this round. Their ${R.plural(r.households, 'household')} show as "not reported", apart from completes and misses.`,
        choices: [{ value: 'acknowledged', label: 'Noted' }] });
    }
    // contacts files
    const updates = [];
    const digestOf = new Map();
    for (const [, x] of perEnum) (x.contacts || []).forEach(c => digestOf.set(c.event_id, c.private_digest));
    const lastUpd = new Map();                       // a later contacts file repeats the earlier updates: each counts once
    contactFiles.filter(f => f.kind === 'contacts').sort((a, b) => cmpStr(a.exported_at || '', b.exported_at || '') || cmpStr(a.name, b.name))
      .forEach(f => f.updates.forEach(u => lastUpd.set(u.event_id, { f, u })));
    [...lastUpd.values()].forEach(({ f, u }) => {
      const okNum = !u.number || u.private_digest === R.sha256(R.canon({ number: u.number }));
      const okLog = !digestOf.has(u.event_id) || digestOf.get(u.event_id) === u.private_digest;
      updates.push(Object.assign({ enumerator_id: f.enumerator_id, file: f.name, digest_ok: okNum && okLog }, u));
      if (!okNum || !okLog) issue({ key: `contact:${u.event_id}`, type: 'contact_mismatch', severity: 'info', file: f.name, hhid: u.hhid, enumerator: f.enumerator_id,
        detail: `The number for ${u.hhid}, slot ${u.slot}, does not match the digest ${okNum ? 'in the call log' : 'beside it'}.` });
    });
    return { files, issues, perEnum, dials: all, actions, counted, conflictHH, activatedBy, updates, sealedContacts: contactFiles.filter(f => f.kind === 'sealed') };
  };

  // ---- cases and progress: one line per household of the round (manifest households and activated replacements) ----
  L.cases = (M, G) => {
    const out = new Map();
    const reported = new Set(G.perEnum.keys());
    const add = (h, e, extra) => out.set(h, Object.assign({ hhid: h, enumerator_id: e, dials: [], actions: [] }, extra || {}));
    M.households.forEach(h => add(h.hhid, h.enumerator_id, { reason: h.reason, psu: h.psu, stratum: h.stratum }));
    for (const [h, a] of G.activatedBy) if (!out.has(h)) {
      const m = M.households.find(x => x.hhid === a.main);
      add(h, a.e, { reason: 'replacement', replaces: a.main, psu: m && m.psu, stratum: m && m.stratum });
    }
    G.dials.forEach(d => { if (out.has(d.hhid)) out.get(d.hhid).dials.push(d); });
    G.actions.forEach(a => { if (out.has(a.hhid)) out.get(a.hhid).actions.push(a); });
    const replacedMains = new Set([...G.activatedBy.values()].map(a => a.main));
    for (const c of out.values()) {
      const has = code => c.actions.some(a => a.action === code) || (code === 'ACTIVATE_REPLACEMENT' && replacedMains.has(c.hhid));
      c.complete = G.counted.get(c.hhid) || null;
      c.conflict = G.conflictHH.has(c.hhid);
      c.short = !c.complete && c.dials.some(d => d.status === 'COMPLETE');
      if (c.conflict) c.state = 'conflict';
      else if (c.complete) c.state = 'complete';
      else if (has('ACTIVATE_REPLACEMENT')) c.state = 'replaced';
      else if (has('RELEASE')) c.state = 'released';
      else if (has('REMOVE_REQUEST')) c.state = 'remove_requested';
      else if (c.dials.length) c.state = 'in_progress';
      else c.state = reported.has(c.enumerator_id) ? 'not_started' : 'not_reported';
      c.n = c.dials.length;
    }
    return out;
  };
  L.STATES = { complete: 'Complete', in_progress: 'In progress', not_started: 'Not started', released: 'Released', replaced: 'Replaced',
    remove_requested: 'Removal requested', not_reported: 'Not reported', conflict: 'Two completes' };
  L.progress = (M, C, G) => {
    const tz = M.calendar.time_zone;
    const rows = new Map();
    const row = e => { if (!rows.has(e)) rows.set(e, { enumerator_id: e, households: 0, complete: 0, in_progress: 0, not_started: 0, released: 0, replaced: 0, remove_requested: 0, not_reported: 0, conflict: 0, dials: 0, days: new Set(), last_export: '' }); return rows.get(e); };
    M.enumerators.forEach(e => row(e.enumerator_id));
    for (const c of C.values()) { const r = row(c.enumerator_id); r.households++; r[c.state]++; }
    G.dials.forEach(d => { const r = row(d.source); r.dials++; r.days.add(R.partsIn(new Date(Date.parse(d.ts)), tz).key); });
    for (const [e, x] of G.perEnum) row(e).last_export = x.file.exported_at || '';
    const list = [...rows.values()].sort((a, b) => cmpStr(a.enumerator_id, b.enumerator_id));
    list.forEach(r => { r.enumerator_days = r.days.size; delete r.days; r.completes_per_day = r.enumerator_days ? r.complete / r.enumerator_days : null; });
    const tot = { enumerator_id: 'All', households: 0, complete: 0, in_progress: 0, not_started: 0, released: 0, replaced: 0, remove_requested: 0, not_reported: 0, conflict: 0, dials: 0, enumerator_days: 0 };
    list.forEach(r => Object.keys(tot).forEach(k => { if (k !== 'enumerator_id') tot[k] += r[k]; }));
    tot.completes_per_day = tot.enumerator_days ? tot.complete / tot.enumerator_days : null;
    // completes by day of the window, and by stratum
    const byDay = new Map();
    for (const c of C.values()) if (c.complete) { const k = R.partsIn(new Date(Date.parse(c.complete.ts)), tz).key; byDay.set(k, (byDay.get(k) || 0) + 1); }
    const days = [];
    let cum = 0;
    for (let k = M.calendar.window_start; k <= M.calendar.window_end; k = R.addDaysKey(k, 1)) { cum += byDay.get(k) || 0; days.push({ day: k, completes: byDay.get(k) || 0, cumulative: cum }); }
    const strata = new Map();
    for (const c of C.values()) {
      const s = c.stratum || '–';
      if (!strata.has(s)) strata.set(s, { stratum: s, households: 0, complete: 0 });
      strata.get(s).households++; if (c.state === 'complete') strata.get(s).complete++;
    }
    return { list, total: tot, days, strata: [...strata.values()].sort((a, b) => cmpStr(a.stratum, b.stratum)) };
  };

  // ---- moving waiting households during the round: who will not finish at the current pace ----
  // Pace = completes per enumerator-day so far (Box 3.0); capacity = pace × working days left; need = open − capacity.
  // Only enumerators whose export is from today and who have two or more enumerator-days are judged.
  L.pace = (M, C, P, now) => {
    const cal = R.calendarOf({ calendar: M.calendar }), today = R.partsIn(now, cal.tz).key;
    const left = R.workingDaysLeft(cal, today);
    const rows = P.list.map(r => {
      const open = r.not_started + r.in_progress, exportDay = r.last_export ? r.last_export.slice(0, 10) : '';
      const known = r.enumerator_days >= 2 && r.completes_per_day !== null;
      const row = { enumerator_id: r.enumerator_id, households: r.households, complete: r.complete, open, waiting: r.not_started, in_progress: r.in_progress,
        pace: r.completes_per_day, enumerator_days: r.enumerator_days, days_left: left, export_at: r.last_export || '', export_day: exportDay, fresh: exportDay === today, known };
      row.capacity = known ? r.completes_per_day * left : null;
      row.need = known ? open - row.capacity : null;
      row.projected = known ? Math.min(r.households, r.complete + Math.floor(row.capacity + 1e-9)) : null;
      row.why = !r.last_export ? 'no export yet' : !row.fresh ? `last export ${exportDay}, not today` : !known ? 'fewer than two enumerator-days: the pace cannot be judged yet' : '';
      return row;
    });
    return { rows, today, days_left: left };
  };
  // which households may move: never dialed; or, if the leader allows, dialed without a booked callback or a hard refusal
  L.movable = (c, include) => {
    if (c.replaces) return false;
    if (c.state === 'not_started') return true;
    if (include !== 'in_progress' || c.state !== 'in_progress') return false;
    const last = c.dials[c.dials.length - 1];
    if (last && last.appointment_ts) return false;
    return !c.dials.some(d => d.status === 'REFUSAL_HARD');
  };
  // one household at a time from the enumerator furthest behind to the one with most spare capacity, latest-planned first,
  // only to an enumerator who matches the household's criteria, until nobody is more than half a household behind or ahead
  L.proposeMoves = (pace, C, opts) => {
    const o = Object.assign({ include: 'not_started', from: null, to: null, eligible: null, hh: null, planOf: null, allowStale: false }, opts || {});
    const judged = r => r.known && (r.fresh || o.allowStale);
    const rows = pace.rows.filter(judged);
    const need = new Map(rows.map(r => [r.enumerator_id, r.need]));
    const planned = id => (o.planOf && o.planOf(id)) || '';
    const rank = c => (c.state === 'not_started' ? 0 : 1);          // never dialed households first, then the latest planned
    const cands = new Map(rows.map(r => [r.enumerator_id, [...C.values()].filter(c => c.enumerator_id === r.enumerator_id && L.movable(c, o.include))
      .sort((a, b) => rank(a) - rank(b) || cmpStr(planned(b.hhid), planned(a.hhid)) || cmpStr(b.hhid, a.hhid))]));
    const moves = [];
    for (let guard = 0; guard < 5000; guard++) {
      const donors = rows.filter(r => need.get(r.enumerator_id) > 0.5 && (!o.from || o.from.includes(r.enumerator_id))).sort((a, b) => need.get(b.enumerator_id) - need.get(a.enumerator_id) || cmpStr(a.enumerator_id, b.enumerator_id));
      const takers = rows.filter(r => need.get(r.enumerator_id) < -0.5 && (!o.to || o.to.includes(r.enumerator_id))).sort((a, b) => need.get(a.enumerator_id) - need.get(b.enumerator_id) || cmpStr(a.enumerator_id, b.enumerator_id));
      let done = false;
      for (const d of donors) {
        const list = cands.get(d.enumerator_id);
        for (const t of takers) {
          const i = list.findIndex(c => !o.eligible || !o.hh || !o.hh.get(c.hhid) || o.eligible(o.hh.get(c.hhid), t.enumerator_id));
          if (i < 0) continue;
          const c = list.splice(i, 1)[0];
          moves.push({ hhid: c.hhid, from: d.enumerator_id, to: t.enumerator_id, state: c.state, dials: c.n, planned: planned(c.hhid) });
          need.set(d.enumerator_id, need.get(d.enumerator_id) - 1); need.set(t.enumerator_id, need.get(t.enumerator_id) + 1);
          done = true; break;
        }
        if (done) break;
      }
      if (!done) break;
    }
    return { moves, need, judged: rows.map(r => r.enumerator_id), left_out: pace.rows.filter(r => !judged(r)).map(r => ({ id: r.enumerator_id, why: r.why || (!r.fresh ? `last export ${r.export_day}, not today` : 'pace not known') })) };
  };
  // the revised files: a new assignment file for each enumerator who gives or receives a household, and the manifest's next
  // revision. Contacts come from the household list (with the numbers enumerators corrected this round); a moved household
  // carries the dials made before the move (handover), a first dial on the next working day, and its usual hour.
  L.reviseFiles = inp => {
    const M = inp.M, at = inp.at, moved = new Map(inp.moves.map(m => [m.hhid, m]));
    const affected = new Set(); inp.moves.forEach(m => { affected.add(m.from); affected.add(m.to); });
    const cal = R.calendarOf({ calendar: M.calendar }), today = R.partsIn(inp.now || R.now(), cal.tz).key;
    let first = today < cal.start ? cal.start : today, guard = 0;
    while (!cal.isWorking(first) && first < cal.end && guard++ < 60) first = R.addDaysKey(first, 1);
    const upd = new Map();                           // hhid -> slot -> the corrected number, from the merged contacts files
    (inp.updates || []).filter(u => u.digest_ok && u.number).forEach(u => { if (!upd.has(u.hhid)) upd.set(u.hhid, new Map()); upd.get(u.hhid).set(+u.slot, u); });
    const contactNow = (H, id, slotLast) => {
      const c = contactOf(H || { phones: [] }, slotLast), m = upd.get(id);
      if (m) {
        for (const [slot, u] of m) {
          const p = c.phones.find(x => x.slot === slot);
          if (p) { p.number = u.number; if (u.label) p.label = u.label; delete p.last_status; } else c.phones.push(R.clean({ slot, number: u.number, label: u.label }));
        }
        c.phones.sort((a, b) => a.slot - b.slot);
      }
      return c;
    };
    const elig = M.matching ? { criteria: M.matching.criteria } : null;
    const households = M.households.map(h => (moved.has(h.hhid) ? Object.assign({}, h, { enumerator_id: moved.get(h.hhid).to, reason: 'mid_round', previous_enumerator: h.enumerator_id,
      matched: M.matching ? (inp.matchedNow ? inp.matchedNow(h.hhid, moved.get(h.hhid).to) : undefined) : undefined }) : h));
    const files = [];
    for (const e of [...affected].sort(cmpStr)) {
      const mine = households.filter(h => h.enumerator_id === e).sort((a, b) => cmpStr(a.hhid, b.hhid));
      const entries = mine.map(h => {
        const H = inp.hh.get(h.hhid), c = inp.C.get(h.hhid), s = inp.sumOf ? inp.sumOf(h.hhid) : null, m = moved.get(h.hhid);
        const reps = (h.replacements || []).map((id, i) => ({ hhid: id, rank: i + 1, contact: contactNow(inp.hh.get(id), id) }));
        const last = c && c.dials.length ? c.dials[c.dials.length - 1] : null;
        const li = s && s.last_interview ? R.clean({ round: s.last_interview.round, date: s.last_interview.date, hour: s.last_interview.hour }) : undefined;
        const pl = inp.plans ? inp.plans.get(h.hhid) : null;
        const crit = elig && H ? Object.fromEntries(elig.criteria.map(k => [k, L.hhValue(H, k)]).filter(([, v]) => v)) : null;
        return R.clean({
          hhid: h.hhid, psu: h.psu, stratum: h.stratum, tz: H && H.tz,
          contact: contactNow(H, h.hhid, s && s.slot_last),
          history: s ? R.clean({ joined_round: s.joined_round === null ? M.round : s.joined_round, last_interview: li, last3: s.last3 || undefined, last_enumerator: s.last_interview ? s.last_interview.enumerator : undefined }) : undefined,
          assignment: R.clean({ reason: h.reason, previous_enumerator: h.previous_enumerator, matched: h.matched }),
          criteria: crit && Object.keys(crit).length ? crit : undefined,
          plan: m ? R.clean({ first_dial_date: first, target_hour: pl && Number.isInteger(pl.target_hour) ? pl.target_hour : (li && Number.isInteger(li.hour) ? li.hour : undefined) }) : pl || undefined,
          handover: m ? R.clean({ from: m.from, moved_at: at, dials: c ? c.n : 0, last_status: last ? last.status : undefined, last_ts: last ? last.ts : undefined }) : undefined,
          replacements: reps.length ? reps : undefined,
        });
      });
      const old = M.enumerators.find(x => x.enumerator_id === e);
      const a = R.clean({
        schema: R.SCHEMA.assign, tool_version: R.VERSION, program: M.program, country: M.country, round: M.round, enumerator_id: e,
        generated_by: inp.leader, generated_at: at, revision: (M.revision || 1) + 1, supersedes: old ? old.fingerprint : undefined,
        rule: M.rule, replacement_policy: M.replacement_policy, matching: M.matching ? { criteria: M.matching.criteria, enumerator: (M.matching.enumerators || {})[e] || {} } : undefined,
        synthetic: M.synthetic ? true : undefined, note: `Revision ${(M.revision || 1) + 1} of this round's assignment: ${inp.moves.filter(x => x.to === e).length} household(s) moved to you, ${inp.moves.filter(x => x.from === e).length} moved from you.`,
        calendar: M.calendar, households: entries,
      });
      a.fingerprint = R.fingerprint(a);
      files.push({ enumerator_id: e, name: `${e}_assignment_R${p2(M.round)}.json`, obj: a });
    }
    const manifest = Object.assign({}, M, {
      generated_at: at, revision: (M.revision || 1) + 1, supersedes: M.fingerprint,
      enumerators: M.enumerators.map(x => {
        const f = files.find(y => y.enumerator_id === x.enumerator_id);
        return f ? Object.assign({}, x, { households: f.obj.households.length, fingerprint: f.obj.fingerprint, previous_fingerprints: (x.previous_fingerprints || []).concat([x.fingerprint]) }) : x;
      }),
      households, moves: (M.moves || []).concat(inp.moves.map(m => ({ hhid: m.hhid, from: m.from, to: m.to, at, by: inp.leader }))),
    });
    delete manifest.fingerprint;
    manifest.fingerprint = R.fingerprint(manifest);
    return { files, manifest, affected: [...affected].sort(cmpStr) };
  };

  // ---- the round's outputs (A.6) ----
  L.callsRows = G => G.dials.map(d => Object.assign(R.dialRow(d), { attempt: d.attempt }));
  L.actionsRows = G => G.actions.map(a => ({ program: a.program, round: a.round, hhid: a.hhid, action: a.action, target_hhid: a.target_hhid || '', reason: a.reason || '',
    note: a.note || '', via: a.via || '', logged_by: a.logged_by, logged_at: a.logged_at, event_id: a.event_id }));
  L.REPORT_COLS = ['type', 'severity', 'status', 'enumerator', 'hhid', 'file', 'detail', 'decision', 'resolved_by', 'resolved_at', 'note', 'key'];
  L.reportRows = G => G.issues.map(i => ({ type: i.type, severity: i.severity, status: i.status, enumerator: i.enumerator || '', hhid: i.hhid || '', file: i.file || '',
    detail: i.detail, decision: i.decision || '', resolved_by: i.by || '', resolved_at: i.at || '', note: i.note || '', key: i.key }));
  L.CONTACT_COLS = ['hhid', 'slot', 'change', 'number', 'label', 'enumerator_id', 'logged_by', 'logged_at', 'event_id', 'digest_ok', 'file'];
  L.contactRows = G => G.updates.map(u => ({ hhid: u.hhid, slot: u.slot, change: u.change, number: u.number || '', label: u.label || '', enumerator_id: u.enumerator_id,
    logged_by: u.logged_by, logged_at: u.logged_at, event_id: u.event_id, digest_ok: u.digest_ok ? 1 : 0, file: u.file }));
  L.validManifest = m => !!(m && m.schema === L.SCHEMA.manifest && Array.isArray(m.households) && Array.isArray(m.enumerators) && m.calendar);
})();
