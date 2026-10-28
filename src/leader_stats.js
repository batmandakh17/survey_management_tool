/* RTM interview tool, leader side: attrition and operational analytics computed the way the handbook computes them.
   Each function follows a handbook script (named in its comment) on the same definitions: the harmonized dial and
   case tables of 10_build_attempts.py, Section 3.3 (11_s33_attempts.py), 3.4 (14_s34_contacts.py), 2.4.4 and Box 2.0
   (20d_s36_benchmarks.py), 3.1 (12_s31_enumerators.py) and 3.5 (15_s35_scheduling.py). Unweighted; local clock time. */
(function () {
  'use strict';
  const S = window.LSTATS = {};
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  S.MIN_COMPLETE_MIN = 3.0;
  S.MIN_CELL = 10;

  S.wilson = (k, n) => {
    if (!n) return null;
    const z = 1.96, p = k / n, d = 1 + z * z / n, c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
    return { k, n, p, lo: Math.max(0, c - h), hi: Math.min(1, c + h) };
  };
  const median = arr => {
    const a = arr.filter(x => x !== null && x !== undefined && !isNaN(x)).slice().sort((x, y) => x - y);
    if (!a.length) return null;
    const m = a.length >> 1;
    return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
  };
  S.median = median;
  const dayNum = k => Date.UTC(+k.slice(0, 4), +k.slice(5, 7) - 1, +k.slice(8, 10)) / 86400000;
  const weekday = k => (new Date(dayNum(k) * 86400000).getUTCDay() + 6) % 7;   // Monday 0 … Sunday 6
  const normOp = s => String(s || '').trim().replace(/_/g, '').toUpperCase();
  const blankOp = s => ['', 'nan', 'None', 'undefined', 'null'].includes(String(s === undefined || s === null ? '' : s).trim());

  // ---- the harmonized dial and case tables (10_build_attempts.py, finish_cases) ----
  // input dials: {hhid, round, wall 'YYYY-MM-DD HH:MM:SS' (the recorded local clock), status, cmp_code, dur (minutes or null), operator}
  S.build = input => {
    let d = input.filter(x => x.hhid && x.round && x.wall && /^\d{4}-\d\d-\d\d/.test(x.wall)).map((x, i) => Object.assign({}, x, { seq: i }));
    const seen = new Set();
    d = d.filter(x => { const k = `${x.hhid}|${x.round}|${x.wall}|${x.status}`; if (seen.has(k)) return false; seen.add(k); return true; });
    d.sort((a, b) => cmpStr(a.hhid, b.hhid) || a.round - b.round || cmpStr(a.wall, b.wall) || a.seq - b.seq);
    d.forEach(x => { x.date = x.wall.slice(0, 10); x.dn = dayNum(x.date); x.hour = +x.wall.slice(11, 13); x.minute = +x.wall.slice(14, 16); });
    // clock errors: more than 90 whole days from the round's median dial date
    const byRound = new Map();
    d.forEach(x => { if (!byRound.has(x.round)) byRound.set(x.round, []); byRound.get(x.round).push(x.dn); });
    const med = new Map([...byRound].map(([r, a]) => [r, median(a)]));
    const dropped = { clock: 0, after_complete: 0, duplicates: input.length - seen.size };
    d = d.filter(x => { const bad = Math.floor(Math.abs(x.dn - med.get(x.round))) > 90; if (bad) dropped.clock++; return !bad; });
    d.forEach(x => { x.is_cmp = !!x.cmp_code && x.dur !== null && x.dur !== undefined && x.dur >= S.MIN_COMPLETE_MIN; });
    // attempt, day index and new day within the case; the completing dial, with the scripts' fallback
    const cases = new Map();
    for (const x of d) {
      const key = `${x.hhid}|${x.round}`;
      if (!cases.has(key)) cases.set(key, { hhid: x.hhid, round: x.round, dials: [] });
      cases.get(key).dials.push(x);
    }
    const kept = [];
    for (const c of cases.values()) {
      let prevDate = null, day = 0;
      c.dials.forEach((x, i) => {
        x.attempt = i + 1;
        if (x.date !== prevDate) day++;
        x.day_idx = day;
        x.new_day = i === 0 || x.date > prevDate;
        prevDate = x.date;
      });
      const q = c.dials.find(x => x.is_cmp), f = c.dials.find(x => x.cmp_code);
      c.k_complete = q ? q.attempt : f ? f.attempt : null;
      c.fallback = !q && !!f;
      if (c.k_complete) { dropped.after_complete += c.dials.length - c.k_complete; c.dials = c.dials.slice(0, c.k_complete); }
      c.dials.forEach(x => { x.k_complete = c.k_complete; x.ok = x.attempt === c.k_complete; kept.push(x); });
      c.n_att = c.dials.length;
      c.n_days = c.dials[c.dials.length - 1].day_idx;
      c.completed = !!c.k_complete;
      c.first_date = c.dials[0].date;
      const op = c.dials.find(x => !blankOp(x.operator));
      c.operator = op ? op.operator : null;
      c.complete_dial = c.completed ? c.dials[c.k_complete - 1] : null;
    }
    const rounds = [...new Set(kept.map(x => x.round))].sort((a, b) => a - b);
    return { dials: kept, cases, rounds, dropped, fallbacks: [...cases.values()].filter(c => c.fallback).length };
  };

  // ---- Section 3.3: dials per complete, hazard by dial, and missed households (11_s33_attempts.py) ----
  const K = 20;
  S.s33 = (T, rounds) => {
    const cs = [...T.cases.values()].filter(c => rounds.includes(c.round));
    const sum = list => {
      const done = list.filter(c => c.completed), n = list.length, dials = list.reduce((s, c) => s + c.n_att, 0);
      const cum = Array(K).fill(0);
      done.forEach(c => { cum[Math.min(c.k_complete, K) - 1]++; });
      for (let k = 1; k < K; k++) cum[k] += cum[k - 1];
      const share = cum.map(x => (done.length ? x / done.length : null));
      const firstAt = th => { const i = share.findIndex(x => x !== null && x >= th); return i < 0 ? null : i + 1; };
      return { cases: n, dials, completes: done.length, dials_per_complete: done.length ? dials / done.length : null, completion_rate: n ? done.length / n : null,
        first_dial_share: done.length ? done.filter(c => c.k_complete === 1).length / done.length : null, k50: firstAt(0.5), k90: firstAt(0.9),
        median_dials_noncomplete: median(list.filter(c => !c.completed).map(c => c.n_att)), share_of_completes: share };
    };
    const pooled = sum(cs);
    const byRound = rounds.map(r => Object.assign({ round: r }, sum(cs.filter(c => c.round === r))));
    // hazard: at risk at k = cases with at least k dials (dials after a complete are deleted, so these are the pending cases)
    const hazard = [];
    for (let k = 1; k <= K; k++) {
      const atRisk = cs.filter(c => c.n_att >= k).length;
      const comp = cs.filter(c => c.completed && (k < K ? c.k_complete === k : c.k_complete >= K)).length;
      const w = atRisk >= S.MIN_CELL ? S.wilson(comp, atRisk) : null;
      hazard.push({ k, at_risk: atRisk, completes: comp, hazard: w ? w.p : null, lo: w ? w.lo : null, hi: w ? w.hi : null });
    }
    // 3.3.5: households completed in r-1, dialled and not completed in r, with round r+1 in the data
    const done = new Set(cs.filter(c => c.completed).map(c => `${c.hhid}|${c.round}`));
    const dialled = new Set(cs.map(c => `${c.hhid}|${c.round}`));
    const lost = cs.filter(c => done.has(`${c.hhid}|${c.round - 1}`) && !c.completed && rounds.includes(c.round + 1));
    const redial = lost.filter(c => dialled.has(`${c.hhid}|${c.round + 1}`));
    const back = redial.filter(c => done.has(`${c.hhid}|${c.round + 1}`));
    const missed = { newly_missed: lost.length, redialled: S.wilson(redial.length, lost.length),
      back_given_redial: redial.length >= S.MIN_CELL ? S.wilson(back.length, redial.length) : null,
      median_dials: median(lost.map(c => c.n_att)), median_days: median(lost.map(c => c.n_days)) };
    return { pooled, byRound, hazard, missed };
  };

  // ---- who was interviewed in each round: interview records where loaded, otherwise call-log completes ----
  S.interviewed = (T, records) => {
    const m = new Map();
    for (const c of T.cases.values()) if (c.completed) { if (!m.has(c.round)) m.set(c.round, new Set()); m.get(c.round).add(c.hhid); }
    const source = new Map([...m.keys()].map(r => [r, 'call log']));
    if (records) for (const [r, recs] of records) {
      const s = new Set();
      for (const [h, x] of recs) if (x.complete) s.add(h);
      m.set(r, s); source.set(r, 'interview records');
    }
    return { sets: m, source };
  };

  // ---- Box 2.0, Section 2.4.4 and Section 3.4.3: continuation, retention, loss and returns (20d_s36_benchmarks.py, 14_s34_contacts.py) ----
  S.s34 = (I, rounds, roundDates) => {
    const sets = I.sets, rs = rounds.filter(r => sets.has(r)).sort((a, b) => a - b);
    const out = { rounds: rs, consecutive: rs.every((r, i) => i === 0 || r === rs[i - 1] + 1) };
    if (!rs.length) return out;
    const has = (h, r) => sets.has(r) && sets.get(r).has(h);
    const last = rs[rs.length - 1], W = 3;
    // continuation, consecutive pairs only
    out.continuation = [];
    for (let i = 1; i < rs.length; i++) {
      const a = rs[i - 1], b = rs[i];
      if (b !== a + 1) continue;
      const prev = sets.get(a), both = [...prev].filter(h => sets.get(b).has(h)).length;
      const later = new Set(); rs.filter(r => r > b).forEach(r => sets.get(r).forEach(h => later.add(h)));
      const missedThenBack = [...prev].filter(h => !sets.get(b).has(h) && later.has(h)).length;
      out.continuation.push({ from: a, round: b, base: prev.size, share: prev.size ? both / prev.size : null, loss: prev.size ? 1 - both / prev.size : null,
        back_later: rs.some(r => r > b) && prev.size ? missedThenBack / prev.size : null });
    }
    const shares = out.continuation.map(x => x.share).filter(x => x !== null);
    out.continuation_median = median(shares);
    out.continuation_min = shares.length ? Math.min(...shares) : null;
    // Box 2.0 / 2.4.4 retention: first-round households interviewed in that round, without returns
    const first = rs[0], base = sets.get(first);
    out.retention_first = rs.map(r => ({ round: r, k: r - first, months: roundDates && roundDates.get(r) && roundDates.get(first) ? (dayNum(roundDates.get(r)) - dayNum(roundDates.get(first))) / 30.4375 : null,
      share: base.size ? [...base].filter(h => has(h, r)).length / base.size : null, base: base.size }));
    // entry round, newcomers and recruitment waves (14_s34, l.158-198)
    const entry = new Map();
    for (const r of rs) for (const h of sets.get(r)) if (!entry.has(h)) entry.set(h, r);
    const newShare = new Map(rs.map(r => [r, sets.get(r).size ? [...sets.get(r)].filter(h => entry.get(h) === r).length / sets.get(r).size : 0]));
    out.newcomers = rs.map(r => ({ round: r, share: newShare.get(r), interviews: sets.get(r).size }));
    out.newcomers_median = median(rs.slice(1).map(r => newShare.get(r)));
    const opening = [first];
    for (const r of rs.slice(1)) { if (newShare.get(r) >= 0.05) opening.push(r); else break; }
    const later = [];
    let run = [];
    for (const r of rs) {
      if (opening.includes(r)) continue;
      if (newShare.get(r) >= 0.05) run.push(r); else { if (run.length >= 3) later.push(...run); run = []; }
    }
    if (run.length >= 3) later.push(...run);
    out.waves = { opening, later };
    const original = h => opening.includes(entry.get(h)) || later.includes(entry.get(h));
    // retention by rounds since joining, pooled over entry cohorts (by_k)
    out.retention = [];
    for (let k = 1; k <= 36; k++) {
      const elig = [...entry].filter(([, e]) => e + k + W <= last);
      if (elig.length < S.MIN_CELL) break;
      const hit = elig.filter(([h, e]) => has(h, e + k)).length;
      const still = elig.filter(([h, e]) => [0, 1, 2, 3].some(j => has(h, e + k + j))).length;
      out.retention.push({ k, n: elig.length, share: S.wilson(hit, elig.length), still: S.wilson(still, elig.length) });
    }
    // retention by entry cohort: share interviewed in each later round (strict), cells of 10 or more
    out.cohorts = [];
    for (const e of rs) {
      const hs = [...entry].filter(([, x]) => x === e).map(([h]) => h);
      if (!hs.length) continue;
      out.cohorts.push({ entry: e, n: hs.length, original: opening.includes(e) || later.includes(e),
        by_round: rs.filter(r => r > e).map(r => ({ round: r, k: r - e, share: hs.length >= S.MIN_CELL ? hs.filter(h => has(h, r)).length / hs.length : null })) });
    }
    // loss by rounds since joining among current respondents, and returns (pairs interviewed in r, with r + 4 in the data)
    const pairs = [];
    for (const r of rs) for (const h of sets.get(r)) {
      if (r + 1 + W > last) continue;
      const lost = !has(h, r + 1), outW = ![1, 2, 3, 4].some(j => has(h, r + j));
      pairs.push({ h, r, k: r + 1 - entry.get(h), lost, out: outW, group: original(h) ? 'original' : 'later' });
    }
    const lostPairs = pairs.filter(p => p.lost);
    out.returns = { pairs: pairs.length, lost: lostPairs.length, back_within: lostPairs.length ? 1 - lostPairs.filter(p => p.out).length / lostPairs.length : null,
      lost_share: pairs.length ? lostPairs.length / pairs.length : null };
    const band = (p, lo, hi) => p.k >= lo && p.k <= hi;
    out.loss = ['original', 'later'].map(g => {
      const ps = pairs.filter(p => p.group === g && p.k <= 24);
      const cell = list => (list.length >= S.MIN_CELL ? { n: list.length, loss: S.wilson(list.filter(p => p.lost).length, list.length), out: S.wilson(list.filter(p => p.out).length, list.length) } : { n: list.length, loss: null, out: null });
      return { group: g, by_k: Array.from({ length: 24 }, (_, i) => Object.assign({ k: i + 1 }, cell(ps.filter(p => p.k === i + 1)))).filter(x => x.n),
        bands: { k1: cell(ps.filter(p => p.k === 1)), k2_6: cell(ps.filter(p => band(p, 2, 6))), k7_12: cell(ps.filter(p => band(p, 7, 12))), k13_24: cell(ps.filter(p => band(p, 13, 24))) } };
    });
    out.judged_until = last - 4 >= first ? last - 4 + 1 : null;   // the last round r + 1 that loss and returns can judge
    return out;
  };

  // ---- Section 3.1: completes per enumerator-day, dial minutes, attendance (12_s31_enumerators.py) ----
  S.s31 = (T, rounds) => {
    let d = T.dials.filter(x => rounds.includes(x.round) && !blankOp(x.operator)).map(x => Object.assign({}, x, { op: String(x.operator).trim() }));
    const bad = x => x.dur !== null && x.dur !== undefined && (x.dur < 0 || x.dur > 120);
    const med = { true: median(d.filter(x => x.ok && !bad(x) && x.dur !== null).map(x => x.dur)), false: median(d.filter(x => !x.ok && !bad(x) && x.dur !== null).map(x => x.dur)) };
    let fixed = 0;
    d.forEach(x => { x.min = x.dur === null || x.dur === undefined ? 0 : bad(x) ? (fixed++, med[x.ok] || 0) : x.dur; });
    const days = new Map();
    for (const r of rounds) {
      const ds = [...new Set(d.filter(x => x.round === r).map(x => x.date))].sort();
      days.set(r, new Map(ds.map((k, i) => [k, i + 1])));
    }
    d.forEach(x => { const m = days.get(x.round); x.fday = m.get(x.date); x.tenth = Math.min(Math.ceil(x.fday / m.size * 10), 10); });
    const od = new Map();
    d.forEach(x => {
      const key = `${x.round}|${x.op}|${x.date}`;
      if (!od.has(key)) od.set(key, { round: x.round, op: x.op, date: x.date, dials: 0, cmp: 0, talk: 0, tenth: x.tenth });
      const o = od.get(key); o.dials++; if (x.ok) o.cmp++; o.talk += x.min;
    });
    const ods = [...od.values()];
    const agg = list => {
      const n = list.length, cmp = list.reduce((s, o) => s + o.cmp, 0), talk = list.reduce((s, o) => s + o.talk, 0), dials = list.reduce((s, o) => s + o.dials, 0);
      return { enumerator_days: n, completes: cmp, dials, completes_per_day: n ? cmp / n : null, minutes_per_day: n ? talk / n : null, minutes_per_complete: cmp ? talk / cmp : null, dials_per_day: n ? dials / n : null };
    };
    const byRound = rounds.map(r => {
      const list = ods.filter(o => o.round === r), ops = new Set(list.map(o => o.op)), fw = days.get(r).size;
      return Object.assign({ round: r, enumerators: ops.size, fieldwork_days: fw, attendance: ops.size && fw ? list.length / (ops.size * fw) : null,
        minutes_per_day_median: median(list.map(o => o.talk)) }, agg(list));
    });
    const dd = d;
    const iv = dd.filter(x => x.ok), fd = dd.filter(x => !x.ok);
    const ivMin = iv.reduce((s, x) => s + x.min, 0), fdMin = fd.reduce((s, x) => s + x.min, 0);
    const pooled = Object.assign(agg(ods), {
      interview_minutes_mean: iv.length ? ivMin / iv.length : null, failed_minutes_per_complete: iv.length ? fdMin / iv.length : null,
      failed_dials_per_complete: iv.length ? fd.length / iv.length : null, failed_share_of_time: ivMin + fdMin ? fdMin / (ivMin + fdMin) : null,
      interview_minutes_median: median(iv.map(x => x.min)), attendance: median(byRound.map(x => x.attendance)), enumerators: median(byRound.map(x => x.enumerators)),
      fieldwork_days: median(byRound.map(x => x.fieldwork_days)), durations_replaced: fixed });
    const early = agg(ods.filter(o => o.tenth <= 3)), late = agg(ods.filter(o => o.tenth >= 8));
    pooled.early = early; pooled.late = late;
    pooled.decline = early.completes_per_day ? 1 - late.completes_per_day / early.completes_per_day : null;
    const byEnum = new Map();
    ods.forEach(o => { const k = `${o.round}|${o.op}`; if (!byEnum.has(k)) byEnum.set(k, []); byEnum.get(k).push(o); });
    const perEnum = [...byEnum].map(([k, list]) => Object.assign({ round: +k.split('|')[0], op: k.split('|').slice(1).join('|') }, agg(list))).sort((a, b) => a.round - b.round || cmpStr(a.op, b.op));
    return { pooled, byRound, perEnum };
  };

  // ---- Section 3.5: hours, weekdays, the last interview's time, continuity, holidays, Ramadan (15_s35_scheduling.py) ----
  S.s35 = (T, rounds, opts) => {
    const o = Object.assign({ holidays: new Map(), ramadan: new Set() }, opts || {});
    const d = T.dials.filter(x => rounds.includes(x.round));
    const out = {};
    // hours with at least 50 dials; success = the dial on which the interview took place
    const byH = new Map();
    d.forEach(x => { if (!byH.has(x.hour)) byH.set(x.hour, { n: 0, ok: 0 }); const h = byH.get(x.hour); h.n++; if (x.ok) h.ok++; });
    const N = d.length;
    out.hours = [...byH].sort((a, b) => a[0] - b[0]).map(([h, v]) => ({ hour: h, n: v.n, dial_share: N ? v.n / N : 0, success: v.n >= 50 ? S.wilson(v.ok, v.n) : null }));
    const elig = out.hours.filter(r => r.success && r.dial_share >= 0.02);
    const best = elig.slice().sort((a, b) => b.success.p - a.success.p).slice(0, 3);
    const busy = elig.slice().sort((a, b) => b.dial_share - a.dial_share).slice(0, 3);
    const wavg = rs => { const n = rs.reduce((s, r) => s + r.n, 0); return n ? rs.reduce((s, r) => s + r.success.p * r.n, 0) / n : null; };
    out.best = { hours: best.map(r => r.hour).sort((a, b) => a - b), success: wavg(best) };
    out.busy = { hours: busy.map(r => r.hour).sort((a, b) => a - b), success: wavg(busy) };
    out.evening_share = N ? d.filter(x => x.hour >= 18).length / N : null;
    const heat = new Map();
    d.forEach(x => { const k = `${weekday(x.date)}|${x.hour}`; if (!heat.has(k)) heat.set(k, { n: 0, ok: 0 }); const c = heat.get(k); c.n++; if (x.ok) c.ok++; });
    out.heat = [...heat].map(([k, v]) => ({ wd: +k.split('|')[0], hour: +k.split('|')[1], n: v.n, success: v.n >= 50 ? v.ok / v.n : null }));
    const groups = { weekday: x => weekday(x.date) <= 4, saturday: x => weekday(x.date) === 5, sunday: x => weekday(x.date) === 6 };
    out.week = Object.entries(groups).map(([g, f]) => { const l = d.filter(f); return { group: g, n: l.length, dial_share: N ? l.length / N : 0, success: S.wilson(l.filter(x => x.ok).length, l.length) }; });
    // first dial of round r against the start of round r-1's completing dial (3.5.2) and continuity (3.5.3)
    const comp = new Map(), firstD = new Map(), working = new Map();
    for (const c of T.cases.values()) {
      if (c.completed) comp.set(`${c.hhid}|${c.round + 1}`, c.complete_dial);
      firstD.set(`${c.hhid}|${c.round}`, { dial: c.dials[0], case: c });
    }
    T.dials.forEach(x => { if (!blankOp(x.operator)) { if (!working.has(x.round)) working.set(x.round, new Set()); working.get(x.round).add(normOp(x.operator)); } });
    const rows = [];
    for (const [key, f] of firstD) {
      if (!rounds.includes(f.case.round)) continue;
      const prev = comp.get(key);
      if (!prev) continue;
      const tod = x => x.hour + x.minute / 60, diff = Math.abs(tod(f.dial) - tod(prev));
      rows.push({ gap: Math.min(diff, 24 - diff), ok: f.dial.ok, done: f.case.completed, op: f.dial.operator, prev_op: prev.operator, round: f.case.round });
    }
    const bin = (lab, f) => { const l = rows.filter(f); return { bin: lab, n: l.length, first_dial_success: S.wilson(l.filter(x => x.ok).length, l.length), round_completion: S.wilson(l.filter(x => x.done).length, l.length) }; };
    out.same_time = [bin('within 1 hour', x => x.gap <= 1), bin('1 to 3 hours', x => x.gap > 1 && x.gap <= 3), bin('over 3 hours', x => x.gap > 3)];
    const cont = rows.filter(x => !blankOp(x.op) && !blankOp(x.prev_op)).map(x => Object.assign({}, x, { same: normOp(x.op) === normOp(x.prev_op) }));
    const sw = cont.filter(x => !x.same);
    const staffing = sw.filter(x => !(working.get(x.round) || new Set()).has(normOp(x.prev_op)));
    out.continuity = {
      same: S.wilson(cont.filter(x => x.same && x.done).length, cont.filter(x => x.same).length),
      different: S.wilson(sw.filter(x => x.done).length, sw.length),
      same_share: cont.length ? cont.filter(x => x.same).length / cont.length : null, n: cont.length,
      switch_staffing: staffing.length >= S.MIN_CELL ? S.wilson(staffing.filter(x => x.done).length, staffing.length) : null,
      switch_reassigned: sw.length - staffing.length >= S.MIN_CELL ? S.wilson(sw.filter(x => x.done).length - staffing.filter(x => x.done).length, sw.length - staffing.length) : null,
      staffing_share_of_switches: sw.length ? staffing.length / sw.length : null,
    };
    // holidays inside each round's fieldwork window, its first and last dial dates excluded
    out.holidays = [];
    for (const r of rounds) {
      const ds = d.filter(x => x.round === r);
      if (!ds.length) continue;
      const dates = ds.map(x => x.date).sort(), a = dates[0], b = dates[dates.length - 1];
      const hol = o.holidays.get(r) || new Map();
      const perDay = new Map();
      ds.forEach(x => { if (!perDay.has(x.date)) perDay.set(x.date, { n: 0, ops: new Set() }); const p = perDay.get(x.date); p.n++; if (!blankOp(x.operator)) p.ops.add(normOp(x.operator)); });
      const typical = [...perDay].filter(([k]) => weekday(k) < 5 && !hol.has(k));
      const medN = median(typical.map(([, v]) => v.n)), medOps = median(typical.map(([, v]) => v.ops.size));
      for (let k = a, n = 0; k <= b && n < 400; n++, k = new Date((dayNum(k) + 1) * 86400000).toISOString().slice(0, 10)) {
        if (k === a || k === b || !hol.has(k)) continue;
        const p = perDay.get(k);
        out.holidays.push({ round: r, date: k, name: hol.get(k), called: !!p, rel_dials: p && medN ? p.n / medN : (p ? null : 0), rel_enumerators: p && medOps ? p.ops.size / medOps : (p ? null : 0) });
      }
    }
    const called = out.holidays.filter(h => h.called && h.rel_dials !== null);
    out.holiday_summary = { in_windows: out.holidays.length, called: out.holidays.filter(h => h.called).length,
      rel_dials_median: median(called.map(h => h.rel_dials)), rel_dials_median_all: median(out.holidays.filter(h => h.rel_dials !== null).map(h => h.rel_dials)),
      success_on_holidays: S.wilson(d.filter(x => (o.holidays.get(x.round) || new Map()).has(x.date) && x.ok).length, d.filter(x => (o.holidays.get(x.round) || new Map()).has(x.date)).length),
      success_other_days: S.wilson(d.filter(x => !(o.holidays.get(x.round) || new Map()).has(x.date) && x.ok).length, d.filter(x => !(o.holidays.get(x.round) || new Map()).has(x.date)).length) };
    // Ramadan: evening (18-21) minus daytime (10-17) success per date, dates with 10 or more dials in each band
    const perDate = new Map();
    d.filter(x => x.hour >= 10 && x.hour <= 21).forEach(x => {
      if (!perDate.has(x.date)) perDate.set(x.date, { ev: [0, 0], day: [0, 0] });
      const b = x.hour >= 18 ? perDate.get(x.date).ev : perDate.get(x.date).day; b[0]++; if (x.ok) b[1]++;
    });
    const gaps = [...perDate].filter(([, v]) => v.ev[0] >= 10 && v.day[0] >= 10).map(([k, v]) => ({ date: k, ramadan: o.ramadan.has(k), gap: v.ev[1] / v.ev[0] - v.day[1] / v.day[0] }));
    const ram = gaps.filter(g => g.ramadan), oth = gaps.filter(g => !g.ramadan);
    const mean = a => (a.length ? a.reduce((s, x) => s + x.gap, 0) / a.length : null);
    out.ramadan = { dates: ram.length, other_dates: oth.length, contrast: ram.length >= 5 && oth.length ? mean(ram) - mean(oth) : null };
    return out;
  };
})();
