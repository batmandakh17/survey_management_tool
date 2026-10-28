/* RTM interview tool, leader side: the dropout-risk and return-likelihood models (Step 4; PROPOSAL.md section E).
   The models were trained and backtested locally on the handbook's tables (models/train_risk.py); this file computes each
   household's features from the leader's loaded history exactly as the training did, scores them, ranks them within the
   round (D7: tiers tied to workload), explains the score by groups of features, and recalibrates or refits the model on the
   program's own rounds, with a backtest the leader sees before switching. Leader only; never written to assignment files. */
(function () {
  'use strict';
  const R = window.RTM, S = window.LSTATS;
  const K = window.LRISK = {};
  K.model = () => window.RTM_RISK || null;
  const sig = x => 1 / (1 + Math.exp(-x));
  const normOp = s => String(s || '').trim().replace(/_/g, '').toUpperCase();
  const blank = s => ['', 'nan', 'None', 'undefined', 'null'].includes(String(s === undefined || s === null ? '' : s).trim());
  const circGap = (h1, m1, h2, m2) => { const d = Math.abs((h1 + m1 / 60) - (h2 + m2 / 60)); return Math.min(d, 24 - d); };
  const log1pCap = (x, cap) => Math.log1p(Math.min(x, cap));

  // ---- the case facts the features rest on: the completing dial, the first dial, and the categories of the other dials ----
  K.facts = (T, model) => {
    const tc = model.tool_codes, cat = new Map();
    Object.entries(tc).forEach(([k, codes]) => codes.forEach(c => cat.set(c, k)));
    const F = new Map();
    for (const c of T.cases.values()) {
      const cd = c.complete_dial, fd = c.dials[0];
      const others = c.dials.filter(d => !(c.completed && d.attempt === c.k_complete));
      F.set(`${c.hhid}|${c.round}`, {
        hhid: c.hhid, round: c.round, completed: c.completed, k_complete: c.k_complete, n_att: c.n_att, n_days: c.n_days,
        day_complete: cd ? cd.day_idx : null,
        c_hour: cd ? cd.hour : null, c_min: cd ? cd.minute : null, c_op: cd && !blank(cd.operator) ? normOp(cd.operator) : '', c_dur: cd && cd.dur !== null && cd.dur !== undefined ? cd.dur : null,
        f_hour: fd.hour, f_min: fd.minute, f_op: !blank(fd.operator) ? normOp(fd.operator) : '',
        any_number: others.some(d => cat.get(d.status) === 'number'), any_refusal: others.some(d => cat.get(d.status) === 'refusal'),
        any_contact: others.some(d => cat.get(d.status) === 'contact'),
      });
    }
    const rounds = [...new Set([...F.values()].map(f => f.round))].sort((a, b) => a - b);
    const entry = new Map();
    for (const f of [...F.values()].filter(x => x.completed).sort((a, b) => a.round - b.round)) if (!entry.has(f.hhid)) entry.set(f.hhid, f.round);
    return { F, rounds, rset: new Set(rounds), entry, done: f => !!f && f.completed };
  };
  const tenure = (model, k) => {
    const out = {};
    model.tenure_bins.forEach(([lo, hi, name]) => { if (name !== model.tenure_reference) out[name] = k >= lo && k <= hi ? 1 : 0; });
    return out;
  };
  const missedPrev = (X, h, t, e) => {
    let n = 0;
    for (const j of [1, 2, 3]) { const r = t - j; if (X.rset.has(r) && r >= e && !X.done(X.F.get(`${h}|${r}`))) n++; }
    return n;
  };
  // dropout features of a household interviewed in round t, for round t + 1 (train_risk.py, build_pairs, the dropout part)
  K.dropoutRow = (model, X, h, t) => {
    const f = X.F.get(`${h}|${t}`);
    if (!f || !f.completed) return null;
    const e = X.entry.get(h), k = t + 1 - e, p = X.F.get(`${h}|${t - 1}`), prevOk = !!(p && p.completed);
    const row = Object.assign(tenure(model, k), {
      missed_prev: missedPrev(X, h, t, e), missed_t1: X.rset.has(t - 1) && t - 1 >= e && !X.done(p) ? 1 : 0,
      dials_needed: log1pCap(f.k_complete, 20), days_needed: Math.min(f.day_complete, 10),
      same_enum: prevOk && f.c_op !== '' && f.c_op === p.c_op ? 1 : 0,
      first_within_hour: prevOk && f.f_hour !== null && p.c_hour !== null && circGap(f.f_hour, f.f_min, p.c_hour, p.c_min) <= 1 ? 1 : 0,
      hour_evening: f.c_hour === null ? null : (f.c_hour >= 18 ? 1 : 0), hour_morning: f.c_hour === null ? null : (f.c_hour < 12 ? 1 : 0),
      interview_min: f.c_dur === null ? null : Math.max(0, Math.min(120, f.c_dur)),
      number_problem: f.any_number ? 1 : 0, refusal: f.any_refusal ? 1 : 0,
    });
    row._ = { hhid: h, t, k, prev_completed: prevOk, k_complete: f.k_complete, days: f.day_complete, hour: f.c_hour, dur: f.c_dur, missed: row.missed_prev };
    return row;
  };
  // return features of a household interviewed in t and missed in t + 1 (train_risk.py, the return part)
  K.returnRow = (model, X, h, t) => {
    const f = X.F.get(`${h}|${t}`);
    if (!f || !f.completed || !X.rset.has(t + 1)) return null;
    const m = X.F.get(`${h}|${t + 1}`);
    if (m && m.completed) return null;
    const e = X.entry.get(h), k = t + 1 - e, dialled = !!m;
    const row = Object.assign(tenure(model, k), {
      missed_prev: missedPrev(X, h, t, e), dialled_miss: dialled ? 1 : 0,
      dials_miss: log1pCap(dialled ? m.n_att : 0, 20), days_miss: Math.min(dialled ? m.n_days : 0, 10),
      contact_miss: dialled && m.any_contact ? 1 : 0, refusal_miss: dialled && m.any_refusal ? 1 : 0, number_problem_miss: dialled && m.any_number ? 1 : 0,
      dials_needed: log1pCap(f.k_complete, 20), same_enum_miss: dialled && f.c_op !== '' && m.f_op === f.c_op ? 1 : 0,
    });
    row._ = { hhid: h, t, k, dialled, n_att: dialled ? m.n_att : 0, n_days: dialled ? m.n_days : 0, k_complete: f.k_complete, missed: row.missed_prev,
      contact: row.contact_miss, refusal: row.refusal_miss, number: row.number_problem_miss, same: row.same_enum_miss };
    return row;
  };

  // ---- scoring ----
  K.z = (spec, row) => spec.features.map(f => { const v = row[f.key]; return v === null || v === undefined || isNaN(v) ? 0 : (v - f.mean) / f.sd; });
  // version: {kind: 'pooled'} | {kind: 'recalibrated', a, b} | {kind: 'refit', intercept, coef, means, sds}
  K.score = (spec, rows, version) => rows.map(row => {
    let lp, contrib;
    if (version && version.kind === 'refit') {
      const z = spec.features.map((f, j) => { const v = row[f.key]; return v === null || v === undefined || isNaN(v) ? 0 : (v - version.means[j]) / version.sds[j]; });
      contrib = z.map((v, j) => v * version.coef[j]);
      lp = version.intercept + contrib.reduce((a, b) => a + b, 0);
    } else {
      const z = K.z(spec, row);
      contrib = z.map((v, j) => v * spec.features[j].coef);
      lp = spec.mean_intercept + contrib.reduce((a, b) => a + b, 0);
      if (version && version.kind === 'recalibrated') { lp = version.a + version.b * lp; contrib = contrib.map(c => c * version.b); }
    }
    const groups = spec.groups.map(g => ({ key: g.key, label: g.label, value: g.features.reduce((s, k) => s + contrib[spec.features.findIndex(f => f.key === k)], 0) }));
    return { row, lp, p: sig(lp), groups };
  });
  // within the round, the top 15% are high, the next 35% medium, the rest low; ties keep the household order (D7)
  K.tiers = (model, scored, used) => {
    const order = scored.map((s, i) => ({ s, i })).sort((a, b) => b.s.lp - a.s.lp || (a.s.row._.hhid < b.s.row._.hhid ? -1 : 1));
    const n = order.length, hi = model.tiers.high, med = model.tiers.medium;
    order.forEach((o, r) => {
      const q = (r + 1) / n;
      let t = q <= hi ? 'high' : q <= hi + med ? 'medium' : 'low';
      if (!used.includes('medium') && t === 'medium') t = 'low';
      o.s.tier = t;
    });
    const mean = scored.reduce((a, s) => a + s.p, 0) / (n || 1);
    scored.forEach(s => { s.relative = mean ? s.p / mean : null; });
    return scored;
  };
  // the three groups of features that move the score most, in the household's own values
  const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
  K.explain = (kind, s) => {
    const x = s.row._, r = s.row;
    const say = {
      dropout: {
        tenure: () => `Rounds since joining: ${x.k}`,
        history: () => (x.missed ? `Missed ${x.missed} of the three rounds before` : 'No round missed before the last interview'),
        effort: () => `Needed ${plural(x.k_complete, 'dial')} over ${plural(x.days, 'day')} last round`,
        continuity: () => (!x.prev_completed ? 'No interview the round before' : r.same_enum ? 'Same enumerator in the last two interviews' : 'A different enumerator in the last two interviews'),
        timing: () => (x.hour === null ? 'Time of the last interview not known' : `Last interview at ${String(x.hour).padStart(2, '0')}:00${r.first_within_hour ? ', its first dial within an hour of the time before' : ''}`),
        length: () => (x.dur === null ? 'Length of the last interview not known' : `Last interview ${Math.round(x.dur)} minutes`),
        numbers: () => (r.number_problem ? 'A number not working or switched off last round' : 'No number problem last round'),
        refusal: () => (r.refusal ? 'A refusal last round before the interview' : 'No refusal last round'),
      },
      return: {
        tenure: () => `Rounds since joining: ${x.k}`,
        history: () => (x.missed ? `Missed ${x.missed} of the three rounds before the last interview` : 'No round missed before the last interview'),
        miss_effort: () => (x.dialled ? `Dialed ${plural(x.n_att, 'time')} over ${plural(x.n_days, 'day')} in the missed round` : 'Not dialed in the missed round'),
        contact: () => (x.contact ? 'Reached in the missed round, no interview' : 'Not reached in the missed round'),
        refusal: () => (x.refusal ? 'A refusal in the missed round' : 'No refusal in the missed round'),
        numbers: () => (x.number ? 'A number not working in the missed round' : 'No number problem in the missed round'),
        effort: () => `Needed ${plural(x.k_complete, 'dial')} at the last interview`,
        continuity: () => (x.same ? 'The enumerator of the last interview dialed first in the missed round' : 'Another enumerator dialed first in the missed round'),
      },
    }[kind];
    return s.groups.slice().sort((a, b) => Math.abs(b.value) - Math.abs(a.value)).slice(0, 3).filter(g => Math.abs(g.value) > 1e-6)
      .map(g => ({ text: say[g.key](), up: g.value > 0, value: g.value }));
  };

  // ---- the program's own rounds: pairs with known outcomes, recalibration, refit, and a rolling backtest ----
  K.ownPairs = (model, X, kind) => {
    const out = [];
    const spec = model[kind];
    for (const f of X.F.values()) {
      if (!f.completed) continue;
      const t = f.round;
      if (kind === 'dropout') {
        if (!X.rset.has(t + 1)) continue;
        const row = K.dropoutRow(model, X, f.hhid, t);
        row._.y = X.done(X.F.get(`${f.hhid}|${t + 1}`)) ? 0 : 1;
        row._.outcome = t + 1;
        out.push(row);
      } else {
        const last = X.rounds[X.rounds.length - 1];
        if (t + 4 > last) continue;
        const row = K.returnRow(model, X, f.hhid, t);
        if (!row) continue;
        row._.y = [2, 3, 4].some(j => X.done(X.F.get(`${f.hhid}|${t + j}`))) ? 1 : 0;
        row._.outcome = t + 4;
        out.push(row);
      }
    }
    void spec;
    return out;
  };
  K.recalibrate = (lp, y) => {
    let a = 0, b = 1;
    for (let it = 0; it < 60; it++) {
      let g0 = 0, g1 = 0, h00 = 1e-9, h01 = 0, h11 = 1e-9;
      for (let i = 0; i < lp.length; i++) {
        const p = sig(a + b * lp[i]), w = p * (1 - p), r = p - y[i];
        g0 += r; g1 += r * lp[i]; h00 += w; h01 += w * lp[i]; h11 += w * lp[i] * lp[i];
      }
      const det = h00 * h11 - h01 * h01;
      if (Math.abs(det) < 1e-12) break;
      const da = (h11 * g0 - h01 * g1) / det, db = (h00 * g1 - h01 * g0) / det;
      a -= da; b -= db;
      if (Math.abs(da) < 1e-10 && Math.abs(db) < 1e-10) break;
    }
    return { a, b };
  };
  // ridge logistic regression with an unpenalised intercept, by Newton's method (the training script's fit, one program)
  K.fitLogit = (Z, y, lambda) => {
    const n = Z.length, p = Z[0] ? Z[0].length : 0, d = p + 1;
    let w = new Array(d).fill(0);
    for (let it = 0; it < 60; it++) {
      const g = new Array(d).fill(0), H = Array.from({ length: d }, () => new Array(d).fill(0));
      for (let i = 0; i < n; i++) {
        const x = [1].concat(Z[i]);
        let eta = 0; for (let j = 0; j < d; j++) eta += w[j] * x[j];
        const pr = sig(eta), wt = pr * (1 - pr), r = pr - y[i];
        for (let j = 0; j < d; j++) { g[j] += r * x[j]; const xj = wt * x[j]; for (let k = j; k < d; k++) H[j][k] += xj * x[k]; }
      }
      for (let j = 0; j < d; j++) { for (let k = 0; k < j; k++) H[j][k] = H[k][j]; if (j > 0) { H[j][j] += lambda; g[j] += lambda * w[j]; } H[j][j] += 1e-9; }
      const step = solve(H, g);
      w = w.map((v, j) => v - step[j]);
      if (Math.max(...step.map(Math.abs)) < 1e-8) break;
    }
    return { intercept: w[0], coef: w.slice(1) };
  };
  function solve(A, b) {
    const n = b.length, M = A.map((r, i) => r.concat([b[i]]));
    for (let c = 0; c < n; c++) {
      let piv = c; for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[piv][c])) piv = r;
      [M[c], M[piv]] = [M[piv], M[c]];
      const v = M[c][c] || 1e-12;
      for (let r = 0; r < n; r++) if (r !== c) { const f = M[r][c] / v; for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k]; }
    }
    return M.map((r, i) => r[n] / (r[i] || 1e-12));
  }
  K.refit = (spec, pairs, lambda) => {
    const means = spec.features.map(f => { const v = pairs.map(r => r[f.key]).filter(x => x !== null && x !== undefined && !isNaN(x)); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : 0; });
    const sds = spec.features.map((f, j) => { const v = pairs.map(r => r[f.key]).filter(x => x !== null && x !== undefined && !isNaN(x)); if (!v.length) return 1; const m = means[j]; const sd = Math.sqrt(v.reduce((a, x) => a + (x - m) * (x - m), 0) / v.length); return sd > 1e-9 ? sd : 1; });
    const Z = pairs.map(r => spec.features.map((f, j) => { const v = r[f.key]; return v === null || v === undefined || isNaN(v) ? 0 : (v - means[j]) / sds[j]; }));
    const m = K.fitLogit(Z, pairs.map(r => r._.y), lambda);
    return { kind: 'refit', intercept: m.intercept, coef: m.coef, means, sds };
  };
  const auc = (y, s) => {
    const idx = s.map((v, i) => i).sort((a, b) => s[a] - s[b]);
    const rank = new Array(s.length);
    for (let i = 0; i < idx.length;) { let j = i; while (j + 1 < idx.length && s[idx[j + 1]] === s[idx[i]]) j++; for (let k = i; k <= j; k++) rank[idx[k]] = (i + j) / 2 + 1; i = j + 1; }
    const n1 = y.filter(v => v === 1).length, n0 = y.length - n1;
    if (!n1 || !n0) return null;
    return (y.reduce((a, v, i) => a + (v === 1 ? rank[i] : 0), 0) - n1 * (n1 + 1) / 2) / (n1 * n0);
  };
  K.auc = auc;
  // rolling origin on the program's own rounds: at each outcome round, use only the outcomes already known
  K.backtest = (model, X, kind) => {
    const spec = model[kind], pairs = K.ownPairs(model, X, kind);
    const outcomes = [...new Set(pairs.map(p => p._.outcome))].sort((a, b) => a - b);
    const res = { pooled: { y: [], p: [], r: [] }, recalibrated: { y: [], p: [], r: [] }, refit: { y: [], p: [], r: [] } };
    let steps = 0, refitSteps = 0;
    for (const r of outcomes) {
      const past = pairs.filter(p => p._.outcome < r), test = pairs.filter(p => p._.outcome === r);
      const pastY = past.map(p => p._.y), events = pastY.reduce((a, b) => a + b, 0);
      if (new Set(past.map(p => p._.outcome)).size < 2 || events < 10 || past.length - events < 10 || !test.length) continue;
      steps++;
      const lpPast = K.score(spec, past, { kind: 'pooled' }).map(s => s.lp);
      const cal = K.recalibrate(lpPast, pastY);
      const sp = K.score(spec, test, { kind: 'pooled' }), sr = K.score(spec, test, Object.assign({ kind: 'recalibrated' }, cal));
      test.forEach((t, i) => { res.pooled.y.push(t._.y); res.pooled.p.push(sp[i].p); res.pooled.r.push(r); res.recalibrated.y.push(t._.y); res.recalibrated.p.push(sr[i].p); res.recalibrated.r.push(r); });
      if (events >= K.REFIT_MIN) {
        refitSteps++;
        const v = K.refit(spec, past, 1.0), sf = K.score(spec, test, v);
        test.forEach((t, i) => { res.refit.y.push(t._.y); res.refit.p.push(sf[i].p); res.refit.r.push(r); });
      }
    }
    const summary = x => {
      if (!x.y.length) return null;
      const n = x.y.length, ev = x.y.reduce((a, b) => a + b, 0), rate = ev / n;
      const scored = x.p.map((p, i) => ({ lp: Math.log(p / (1 - p)), p, row: { _: { hhid: String(i) } }, r: x.r[i], y: x.y[i] }));
      let capture = 0, highN = 0;
      for (const r of [...new Set(x.r)]) {
        const g = scored.filter(s => s.r === r).sort((a, b) => b.lp - a.lp);
        const top = Math.max(1, Math.floor(g.length * model.tiers.high + 1e-9));
        g.slice(0, top).forEach(s => { capture += s.y; highN++; });
      }
      return { n, events: ev, rate, auc: auc(x.y, x.p), brier: x.y.reduce((a, y, i) => a + (x.p[i] - y) ** 2, 0) / n,
        brier_null: x.y.reduce((a, y) => a + (rate - y) ** 2, 0) / n, capture_high: ev ? capture / ev : null, high_n: highN };
    };
    return { kind, pairs: pairs.length, events: pairs.reduce((a, p) => a + p._.y, 0), outcome_rounds: outcomes.length, steps, refit_steps: refitSteps,
      pooled: summary(res.pooled), recalibrated: summary(res.recalibrated), refit: summary(res.refit) };
  };
  K.REFIT_MIN = 300;     // about 20 events per feature (proposal E)
  // the version the leader may switch to: fitted on every outcome known now
  K.fitVersion = (model, X, kind, which) => {
    const spec = model[kind], pairs = K.ownPairs(model, X, kind), y = pairs.map(p => p._.y);
    if (which === 'recalibrated') return Object.assign({ kind: 'recalibrated', fitted_on: pairs.length, events: y.reduce((a, b) => a + b, 0) }, K.recalibrate(K.score(spec, pairs, { kind: 'pooled' }).map(s => s.lp), y));
    if (which === 'refit') return Object.assign(K.refit(spec, pairs, 1.0), { fitted_on: pairs.length, events: y.reduce((a, b) => a + b, 0) });
    return { kind: 'pooled' };
  };

  // ---- the model card, rendered from the bundled MODEL_CARD.md (headings, paragraphs, lists, tables, bold, code) ----
  K.cardHTML = () => {
    const md = window.RTM_RISK_CARD || '', esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>');
    const out = [], lines = md.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (/^#{1,3} /.test(l)) { const n = l.match(/^#+/)[0].length; out.push(`<h${n + 2}>${inline(l.replace(/^#+ /, ''))}</h${n + 2}>`); }
      else if (l.startsWith('|')) {
        const rows = [];
        while (i < lines.length && lines[i].startsWith('|')) { rows.push(lines[i]); i++; }
        i--;
        const cells = r => r.split('|').slice(1, -1).map(c => c.trim());
        out.push(`<div class="tablewrap"><table class="grid small"><thead><tr>${cells(rows[0]).map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${rows.slice(2).map(r => `<tr>${cells(r).map(c => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
      } else if (l.startsWith('- ')) {
        const items = [];
        while (i < lines.length && lines[i].startsWith('- ')) { items.push(lines[i].slice(2)); i++; }
        i--;
        out.push(`<ul>${items.map(x => `<li>${inline(x)}</li>`).join('')}</ul>`);
      } else if (l.trim()) out.push(`<p>${inline(l)}</p>`);
    }
    return out.join('');
  };
})();
