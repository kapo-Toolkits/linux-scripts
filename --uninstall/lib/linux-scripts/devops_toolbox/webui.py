"""The single page of the web app: HTML + CSS + JavaScript in one string, served by web.py with a per-response nonce (a strict
Content-Security-Policy: no inline handlers, no external files, no style attributes). The page builds its DOM with textContent only,
so a rule description can never become markup. All words come from i18n.TEXT (embedded as JSON), all colours from themes.PALETTES."""
import json

PAGE = r"""<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DevOps Toolbox</title>
<style nonce="__NONCE__">
__PALETTE_CSS__
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.45 system-ui,-apple-system,"Noto Sans","Noto Sans Georgian",sans-serif}
header{display:flex;align-items:center;gap:12px;padding:10px 16px;flex-wrap:wrap}
header h1{font-size:20px;margin:0}
header .sub{color:var(--muted);flex:1;min-width:140px}
select,input,button{font:inherit;color:var(--text);background:var(--field);border:1px solid var(--border);border-radius:6px;padding:6px 10px}
button{cursor:pointer;background:var(--panel)}
button:hover:not(:disabled){background:var(--select)}
button:disabled{opacity:.5;cursor:not-allowed}
button.accent{background:var(--accent);color:var(--accent_text);border-color:var(--accent);font-weight:600}
button.danger{background:var(--bad);color:#fff;border-color:var(--bad);font-weight:600}
.layout{display:grid;grid-template-columns:220px 1fr;gap:0;min-height:calc(100vh - 56px)}
aside{background:var(--side);padding:12px}
aside h2{font-size:13px;margin:0 0 8px}
aside .cat{display:block;width:100%;text-align:left;background:transparent;border:0;border-radius:6px;padding:7px 8px}
aside .cat.on{background:var(--select)}
main{padding:12px 16px;min-width:0}
.card{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px}
.card h2{margin:0 0 6px;font-size:18px}
.muted{color:var(--muted);font-size:13px;margin:3px 0}
table{border-collapse:collapse;width:100%;margin:6px 0}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)}
th{background:var(--side);font-size:13px}
tbody tr.sel{background:var(--select)}
tbody tr{cursor:pointer}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end;margin-top:10px}
.row label{display:flex;flex-direction:column;font-size:13px;color:var(--muted);gap:3px}
.row label.grow{flex:1;min-width:180px}
.bar{display:flex;gap:8px;justify-content:space-between;align-items:center;flex-wrap:wrap}
pre{margin:8px 0 0;padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--field);white-space:pre-wrap;word-break:break-word;font:13px/1.45 ui-monospace,Menlo,Consolas,monospace;min-height:48px;max-height:260px;overflow:auto}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.cmd{font-weight:700}
.tabs{display:flex;gap:4px;margin-bottom:6px}
.tabs button.on{background:var(--select)}
dialog{background:var(--panel);color:var(--text);border:1px solid var(--border);border-radius:10px;max-width:560px;width:92vw}
dialog::backdrop{background:rgba(0,0,0,.45)}
dialog h3{margin-top:0}
dialog pre{max-height:180px}
.dlgbtns{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
.hidden{display:none}
.banner{background:var(--bad);color:#fff;font-weight:700;padding:5px 10px;border-radius:6px;margin-top:6px}
.radio{display:flex;align-items:center;gap:4px;font-size:14px}
.opsgrid{display:grid;grid-template-columns:260px 1fr;gap:14px}
#oplist{display:flex;flex-direction:column;gap:2px;max-height:430px;overflow:auto;border:1px solid var(--border);border-radius:8px;padding:4px;background:var(--field)}
#oplist button{text-align:left;background:transparent;border:0;border-radius:6px;padding:6px 8px}
#oplist button.on{background:var(--select)}
#opform h3{margin:0 0 4px;font-size:17px}
.fld{display:flex;flex-direction:column;gap:3px;font-size:13px;color:var(--muted);margin:6px 0}
.fld input[type=text],.fld select{min-width:260px;max-width:100%}
@media (max-width:900px){.opsgrid{grid-template-columns:1fr}}
@media (max-width:760px){.layout{grid-template-columns:1fr}aside{display:flex;gap:8px;align-items:center}}
</style>
</head>
<body>
<header>
  <h1 id="title"></h1><span class="sub" id="subtitle"></span>
  <label><span id="lbl-lang"></span> <select id="lang"><option value="en">English</option><option value="ka">ქართული</option></select></label>
  <button id="theme" type="button"></button>
</header>
<div class="layout">
  <aside><h2 id="lbl-cats"></h2><div id="cats"></div></aside>
  <main>
    <section class="card" id="target">
      <div class="row">
        <strong id="tg-title"></strong>
        <label class="radio"><input type="radio" name="tkind" value="local" id="tk-local" checked> <span id="tk-local-l"></span></label>
        <label class="radio"><input type="radio" name="tkind" value="remote" id="tk-remote"> <span id="tk-remote-l"></span></label>
        <label class="fld"><span id="tg-host-l"></span><input type="text" id="tg-host" autocomplete="off" size="18"></label>
        <label class="fld"><span id="tg-port-l"></span><input type="text" id="tg-port" autocomplete="off" size="5" value="22"></label>
        <label class="fld"><span id="tg-user-l"></span><input type="text" id="tg-user" autocomplete="off" size="12"></label>
        <label class="fld"><span id="tg-key-l"></span><select id="tg-key"></select></label>
        <button id="tg-hostkey" type="button"></button><button id="tg-connect" class="accent" type="button"></button><button id="tg-use" type="button"></button>
      </div>
      <div id="tbanner" class="banner hidden"></div>
      <p class="muted" id="tg-note"></p>
    </section>
    <section class="card" id="fw">
      <h2 id="fw-title"></h2>
      <div id="fw-state"></div>
      <p class="muted" id="note1"></p><p class="muted" id="note2"></p>
      <div class="bar"><strong id="fw-rules-h"></strong><span><button id="del" type="button"></button> <button id="refresh" type="button"></button></span></div>
      <table><thead><tr><th id="th-a"></th><th id="th-p"></th><th id="th-pr"></th><th id="th-c"></th></tr></thead><tbody id="rules"></tbody></table>
      <p class="muted" id="other"></p>
      <div class="row">
        <label><span id="l-port"></span><input id="port" inputmode="numeric" maxlength="5" size="8" autocomplete="off"></label>
        <label><span id="l-proto"></span><select id="proto"><option value="tcp">TCP</option><option value="udp">UDP</option></select></label>
        <label><span id="l-action"></span><select id="action"></select></label>
        <label class="grow"><span id="l-comment"></span><input id="comment" maxlength="80" autocomplete="off"></label>
      </div>
      <div class="row"><button id="preview" type="button"></button><button id="execute" class="accent" type="button" disabled></button></div>
      <pre id="pv"></pre>
    </section>
    <section class="card" id="ops">
      <div class="opsgrid"><div id="oplist"></div><div id="opform">
        <h3 id="op-name"></h3><p class="muted" id="op-desc"></p><div id="op-params"></div>
        <div class="row"><button id="op-preview" type="button"></button><button id="op-run" class="accent" type="button"></button></div>
        <pre id="op-pv"></pre></div></div>
    </section>
    <section class="card">
      <div class="tabs"><button id="tab-res" class="on" type="button"></button><button id="tab-hist" type="button"></button></div>
      <pre id="res"></pre>
      <div id="hist" class="hidden"><table><thead><tr><th id="h-time"></th><th id="h-op"></th><th id="h-st"></th><th id="h-ex"></th><th id="h-sum"></th></tr></thead><tbody id="hist-body"></tbody></table>
        <button id="clear" type="button"></button></div>
      <p class="muted" id="status"></p>
    </section>
  </main>
</div>
<dialog id="dlg"><h3 id="dlg-title"></h3><pre id="dlg-body"></pre><div class="dlgbtns"><button id="dlg-no" type="button"></button><button id="dlg-yes" class="danger" type="button"></button></div></dialog>
<script nonce="__NONCE__">
"use strict";
const TEXT = __TEXT_JSON__;
const KEY = new URLSearchParams(location.search).get("key") || "";
const $ = (id) => document.getElementById(id);
let lang = "en", theme = "light", state = null, tform = { kind: "local", host: "", port: "22", user: "", key: "" }, pending = null, selected = null, busy = false, current = "res", cat = null, opId = null, opPending = null, opValues = {};
try { lang = localStorage.getItem("dt_lang") || "en"; theme = localStorage.getItem("dt_theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"); } catch (e) {}
if (!TEXT[lang]) lang = "en";
const t = (key, vars) => { let s = (TEXT[lang] && TEXT[lang][key]) || TEXT.en[key] || key; for (const k in (vars || {})) s = s.split("{" + k + "}").join(String(vars[k])); return s; };

function el(tag, text, cls) { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; }
function put(node, parts) { node.textContent = ""; for (const [text, cls] of parts) node.appendChild(el("span", text, cls)); }

async function api(path, body) {
  const opts = { headers: { "X-Toolbox-Key": KEY } };
  if (body) { opts.method = "POST"; opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(Object.assign({ lang }, body)); }
  const r = await fetch(path + (body ? "" : (path.includes("?") ? "&" : "?") + "lang=" + lang), opts);
  return r.json();
}

function texts() {
  document.documentElement.lang = lang; document.documentElement.dataset.theme = theme; document.title = t("app_title");
  const set = (id, key) => { $(id).textContent = t(key); };
  for (const [id, key] of [["title", "app_title"], ["subtitle", "app_subtitle"], ["lbl-lang", "language"], ["lbl-cats", "categories"],
    ["fw-title", "fw_title"], ["note1", "no_reload_note"], ["note2", "off_note"], ["fw-rules-h", "fw_rules"], ["del", "btn_delete_selected"],
    ["refresh", "btn_refresh"], ["th-a", "fw_col_action"], ["th-p", "fw_col_port"], ["th-pr", "fw_col_proto"], ["th-c", "fw_col_comment"],
    ["l-port", "p_port"], ["l-proto", "p_proto"], ["l-action", "p_action"], ["l-comment", "p_comment"], ["preview", "btn_preview"],
    ["execute", "btn_execute"], ["tab-res", "res_title"], ["tab-hist", "hist_title"], ["h-time", "hist_time"], ["h-op", "hist_operation"],
    ["h-st", "hist_status"], ["h-ex", "hist_exit"], ["h-sum", "hist_summary"], ["clear", "btn_clear_history"], ["dlg-no", "btn_cancel"],
    ["dlg-yes", "btn_confirm"], ["tg-title", "tg_title"], ["tk-local-l", "tg_local"], ["tk-remote-l", "tg_remote"], ["tg-host-l", "tg_host"], ["tg-port-l", "tg_port"],
    ["tg-user-l", "tg_user"], ["tg-key-l", "tg_key"], ["tg-hostkey", "tg_hostkey"], ["tg-connect", "tg_connect"], ["tg-use", "tg_use"], ["tg-note", "tg_note"]]) set(id, key);
  $("theme").textContent = t(theme === "light" ? "theme_dark" : "theme_light");
  $("lang").value = lang;
  const sel = $("action"), keep = sel.value || "allow"; sel.textContent = "";
  for (const a of ["allow", "deny", "reject", "delete"]) { const o = el("option", t(a === "delete" ? "act_delete" : "act_" + a)); o.value = a; sel.appendChild(o); }
  sel.value = keep;
}

function renderTarget() {
  const info = state && state.target; if (!info) return;
  const sel = $("tg-key"); const keep = tform.key; sel.textContent = "";
  for (const k of [""].concat(info.keys)) { const o = el("option", k || t("tg_key_default")); o.value = k; sel.appendChild(o); }
  sel.value = keep;
  const remote = $("tk-remote").checked;
  for (const id of ["tg-host", "tg-port", "tg-user", "tg-key", "tg-hostkey", "tg-connect"]) $(id).disabled = !remote || busy;
  const b = $("tbanner");
  if (info.kind === "remote") { b.textContent = t("tg_remote_banner", { label: info.label }); b.classList.remove("hidden"); } else { b.classList.add("hidden"); }
}

function readTarget() {
  tform = { kind: $("tk-remote").checked ? "remote" : "local", host: $("tg-host").value.trim(), port: $("tg-port").value.trim() || "22", user: $("tg-user").value.trim(), key: $("tg-key").value };
  return tform;
}

async function applyTarget() {
  const f = readTarget();
  const r = await api("/api/target", { kind: f.kind, host: f.host, port: f.port, user: f.user, identity: f.key });
  if (!r.ok) { put($("res"), r.errors.map((e) => ["✖ " + e.message + "\n", "bad"])); showTab("res"); return false; }
  state.target = r.target; state.info = r.info; state.history = r.history; opPending = null; pending = null; opId = null;
  render(); await buildForm();
  return true;
}

async function connectTarget() {
  if (!(await applyTarget())) return;
  await work(async () => { const r = await api("/api/target/test", {}); put($("res"), [[(r.ok ? "✔ " : "✖ ") + r.message + "\n", r.ok && r.sudo !== false ? "ok" : r.ok ? "warn" : "bad"]]); showTab("res"); });
}

async function checkHostKey() {
  const f = readTarget();
  if (!f.host) { put($("res"), [["✖ " + t("tg_unknown_host") + "\n", "bad"]]); showTab("res"); return; }
  await work(async () => {
    const r = await api("/api/target/hostkey", { host: f.host, port: f.port });
    if (!r.ok) { put($("res"), [["✖ " + r.message + "\n", "bad"]]); showTab("res"); return; }
    if (r.trusted) { put($("res"), [["✔ " + t("tg_trusted_already", { host: r.host }) + "\n", "ok"], [r.fingerprints.join("\n") + "\n", ""]]); showTab("res"); return; }
    $("dlg-title").textContent = t("tg_trust_title");
    $("dlg-body").textContent = t("tg_trust_text", { host: r.host, port: r.port, prints: r.fingerprints.join("\n") });
    const yes = await new Promise((resolve) => { const d = $("dlg"); let a = false; $("dlg-yes").onclick = () => { a = true; d.close(); }; $("dlg-no").onclick = () => { a = false; d.close(); }; d.onclose = () => resolve(a); d.showModal(); });
    if (yes) { const done = await api("/api/target/trust", { token: r.token, confirmed: true }); put($("res"), [[(done.ok ? "✔ " : "✖ ") + done.message + "\n", done.ok ? "ok" : "bad"]]); showTab("res"); }
  });
}

function render() {
  texts();
  renderTarget();
  const cats = $("cats"); cats.textContent = "";
  if (state && !cat) cat = state.catalog.categories[0].id;
  if (state) for (const c of state.catalog.categories) {
    const b = el("button", c.name, "cat" + (c.id === cat ? " on" : "")); b.type = "button";
    b.addEventListener("click", () => { cat = c.id; opId = null; opPending = null; render(); if (c.id === "firewall" && state.info.ufw.installed && !state.info.ufw.rules_loaded) refreshRules(); });
    cats.appendChild(b);
  }
  $("fw").classList.toggle("hidden", cat !== "firewall");
  renderOps();
  const u = state && state.info.ufw;
  const st = $("fw-state");
  if (!u) { st.textContent = ""; }
  else if (!u.installed) { put(st, [[t("fw_not_installed"), "bad"]]); }
  else {
    let s = t("fw_state") + ": " + t(u.active === true ? "fw_active" : u.active === false ? "fw_inactive" : "fw_unknown");
    if (u.policy && (u.policy.incoming || u.policy.outgoing)) s += "   |   " + t("fw_policy", { incoming: u.policy.incoming || "?", outgoing: u.policy.outgoing || "?" });
    put(st, [[s, u.active === true ? "ok" : u.active === false ? "warn" : ""]]);
  }
  const body = $("rules"); body.textContent = "";
  for (const [i, r] of ((u && u.rules) || []).entries()) {
    const tr = document.createElement("tr"); if (selected === i) tr.className = "sel";
    for (const v of [t("act_" + r.action), String(r.port), r.proto === "any" ? t("proto_any") : r.proto, r.comment]) tr.appendChild(el("td", v));
    tr.addEventListener("click", () => { selected = i; render(); });
    body.appendChild(tr);
  }
  if (u && u.installed && !u.rules_loaded) { const tr = document.createElement("tr"); tr.appendChild(el("td", "")); tr.appendChild(el("td", "")); tr.appendChild(el("td", "")); tr.appendChild(el("td", t("fw_rules_not_loaded"))); body.appendChild(tr); }
  else if (u && u.installed && !u.rules.length) { const tr = document.createElement("tr"); tr.appendChild(el("td", "")); tr.appendChild(el("td", "")); tr.appendChild(el("td", "")); tr.appendChild(el("td", t("fw_no_rules"))); body.appendChild(tr); }
  $("other").textContent = u && u.other && u.other.length ? t("fw_other") + ": " + u.other.join("; ") : "";
  $("del").disabled = busy || selected === null || !u || !u.rules[selected];
  $("refresh").disabled = busy; $("preview").disabled = busy; $("execute").disabled = busy || !pending;
  renderHistory();
  $("status").textContent = busy ? t("working") : "";
}

function renderHistory() {
  const body = $("hist-body"); body.textContent = "";
  const list = (state && state.history) || [];
  if (!list.length) { const tr = document.createElement("tr"); for (let i = 0; i < 4; i++) tr.appendChild(el("td", "")); tr.appendChild(el("td", t("hist_empty"))); body.appendChild(tr); }
  for (const e of list) { const tr = document.createElement("tr"); for (const v of [e.time || "", e.op || "", e.status || "", e.exit_code === null || e.exit_code === undefined ? "" : String(e.exit_code), e.summary || ""]) tr.appendChild(el("td", v)); body.appendChild(tr); }
}

const CORE_UFW = ["ufw.status", "ufw.rule.add", "ufw.rule.delete"];
function catOps() {
  if (!state) return [];
  const c = state.catalog.categories.find((x) => x.id === cat);
  return c ? c.operations.filter((o) => cat !== "firewall" || !CORE_UFW.includes(o.id)) : [];
}

function renderOps() {
  const list = $("oplist"); list.textContent = "";
  const ops = catOps();
  if (!ops.length) { $("ops").classList.add("hidden"); return; }
  $("ops").classList.remove("hidden");
  if (!opId || !ops.find((o) => o.id === opId)) { opId = ops[0].id; opValues = {}; opPending = null; buildForm(); }
  for (const o of ops) {
    const b = el("button", (o.risk === "high" ? "⚠ " : o.risk === "low" || o.risk === "medium" ? "✎ " : "   ") + o.name, o.id === opId ? "on" : ""); b.type = "button";
    b.addEventListener("click", () => { opId = o.id; opValues = {}; opPending = null; buildForm(); render(); });
    list.appendChild(b);
  }
  const op = ops.find((o) => o.id === opId);
  $("op-preview").textContent = t("btn_preview"); $("op-run").textContent = t(op.risk === "info" ? "btn_run" : "btn_execute");
  $("op-run").disabled = busy || (op.risk !== "info" && !opPending); $("op-preview").disabled = busy;
}

async function buildForm() {
  const op = catOps().find((o) => o.id === opId); if (!op) return;
  $("op-name").textContent = op.name; $("op-desc").textContent = op.description; put($("op-pv"), []);
  const box = $("op-params"); box.textContent = "";
  if (!op.params.length) box.appendChild(el("p", t("no_input"), "muted"));
  for (const p of op.params) {
    const wrap = el("label", "", "fld"); wrap.appendChild(el("span", t(p.label)));
    let input;
    if (p.kind === "bool") { input = document.createElement("input"); input.type = "checkbox"; }
    else if (p.kind === "choice") {
      input = document.createElement("select");
      const values = p.dynamic ? (await api("/api/choices", { op: op.id, param: p.name })).choices : p.choices;
      for (const v of values.length ? values : [""]) { const o = el("option", v || t("choice_none")); o.value = v; input.appendChild(o); }
      if (p.default && values.includes(p.default)) input.value = p.default;
    } else { input = document.createElement("input"); input.type = "text"; input.autocomplete = "off"; input.value = p.default || ""; }
    input.dataset.name = p.name; input.dataset.kind = p.kind;
    input.addEventListener("input", () => { opPending = null; $("op-run").disabled = busy || op.risk !== "info"; });
    input.addEventListener("change", () => { opPending = null; $("op-run").disabled = busy || op.risk !== "info"; });
    wrap.appendChild(input); box.appendChild(wrap);
  }
}

function formParams() {
  const out = {};
  for (const e of $("op-params").querySelectorAll("[data-name]")) {
    if (e.dataset.kind === "bool") out[e.dataset.name] = e.checked;
    else if (e.value.trim()) out[e.dataset.name] = e.dataset.kind === "text" ? e.value : e.value.trim();
  }
  return out;
}

async function opPreview() {
  const op = catOps().find((o) => o.id === opId); if (!op || busy) return;
  const params = formParams();
  const p = await api("/api/preview", { op: op.id, params });
  const parts = [];
  if (p.errors && p.errors.length) for (const e of p.errors) parts.push(["✖ " + e.message + "\n", "bad"]);
  else {
    parts.push([t("pv_title") + ": " + p.name + "\n", "cmd"]);
    if (p.remote) parts.push([t("tg_running_on") + ": " + p.target + "\n", "warn"]);
    for (const c of p.commands) { parts.push(["$ " + c.display + "\n", "cmd"]); parts.push(["  " + t("pv_exact") + ": " + c.exact + "\n", ""]); }
    if (!p.commands.length && !p.blocked) parts.push([t("pv_nothing") + "\n", ""]);
    parts.push([t("pv_risk") + ": " + p.level_text + "\n", p.risk === "high" ? "bad" : ""]);
    parts.push([t("pv_root") + ": " + t(p.needs_root ? "pv_root_yes" : "pv_root_no") + "\n", ""]);
    if (p.blocked) parts.push(["✖ " + p.blocked + "\n", "bad"]);
    for (const w of p.warnings) parts.push(["⚠ " + w + "\n", "warn"]);
    for (const x of p.explain) parts.push(["• " + x + "\n", ""]);
  }
  put($("op-pv"), parts);
  opPending = p.token ? { op: op.id, params, token: p.token, commands: p.commands.map((c) => c.display), deleting: p.risk === "high" } : null;
  render();
}

async function opRun() {
  const op = catOps().find((o) => o.id === opId); if (!op || busy) return;
  if (op.risk === "info") {
    await work(async () => { const r = await api("/api/run", { op: op.id, params: formParams() }); state.info = r.info; state.history = r.history; showResult(r.result); });
    return;
  }
  if (!opPending) return;
  const job = opPending;
  if (!(await confirmDialog(job.deleting, job.commands))) return;
  opPending = null;
  await work(async () => {
    const r = await api("/api/execute", { op: job.op, params: job.params, token: job.token, confirmed: true });
    state.info = r.info; state.history = r.history; showResult(r.result);
  });
}

function showTab(which) { current = which; $("res").classList.toggle("hidden", which !== "res"); $("hist").classList.toggle("hidden", which !== "hist"); $("tab-res").classList.toggle("on", which === "res"); $("tab-hist").classList.toggle("on", which === "hist"); }

function formOp() {
  const port = $("port").value.trim(), proto = $("proto").value, action = $("action").value, comment = $("comment").value;
  if (action === "delete") return ["ufw.rule.delete", { port, proto }];
  const params = { port, proto, action }; if (comment.trim()) params.comment = comment;
  return ["ufw.rule.add", params];
}

function showPreview(p, op, params) {
  const parts = [];
  if (p.errors && p.errors.length) for (const e of p.errors) parts.push(["✖ " + e.message + "\n", "bad"]);
  else {
    parts.push([t("pv_title") + ": " + p.name + "\n", "cmd"]);
    for (const c of p.commands) { parts.push(["$ " + c.display + "\n", "cmd"]); parts.push(["  " + t("pv_exact") + ": " + c.exact + "\n", ""]); }
    if (!p.commands.length && !p.blocked) parts.push([t("pv_nothing") + "\n", ""]);
    parts.push([t("pv_risk") + ": " + p.level_text + "\n", p.risk === "high" ? "bad" : ""]);
    parts.push([t("pv_root") + ": " + t(p.needs_root ? "pv_root_yes" : "pv_root_no") + "\n", ""]);
    if (p.blocked) parts.push(["✖ " + p.blocked + "\n", "bad"]);
    for (const w of p.warnings) parts.push(["⚠ " + w + "\n", "warn"]);
    for (const x of p.explain) parts.push(["• " + x + "\n", ""]);
  }
  put($("pv"), parts);
  pending = p.token ? { op, params, token: p.token, commands: p.commands.map((c) => c.display), deleting: op === "ufw.rule.delete" } : null;
  render();
}

async function doPreview(op, params) {
  const p = await api("/api/preview", { op, params });
  showPreview(p, op, params);
  return p;
}

function confirmDialog(deleting, commands) {
  return new Promise((resolve) => {
    const where = state && state.target && state.target.kind === "remote" ? "\n\n" + t("tg_running_on") + ": " + state.target.label : "";
    $("dlg-title").textContent = t(deleting ? "confirm_delete_title" : "confirm_title");
    $("dlg-body").textContent = t(deleting ? "confirm_delete_text" : "confirm_text", { commands: commands.join("\n") + where });
    const dlg = $("dlg"); let answer = false;
    const done = (v) => { answer = v; dlg.close(); };
    $("dlg-yes").onclick = () => done(true); $("dlg-no").onclick = () => done(false);
    dlg.onclose = () => resolve(answer);
    dlg.showModal();
  });
}

function showResult(res) {
  const parts = [[(res.status === "refused" ? t("res_refused") : res.ok ? t("res_ok") : t("res_failed")) + ": " + res.message + "\n", res.ok ? "ok" : "bad"]];
  for (const c of res.commands || []) parts.push(["$ " + c + "\n", "cmd"]);
  if (res.exit_code !== null && res.exit_code !== undefined) parts.push([t("res_exit") + ": " + res.exit_code + "\n", ""]);
  if (res.output) parts.push([t("res_output") + ":\n" + res.output + "\n", ""]);
  put($("res"), parts); showTab("res");
}

async function work(fn) {
  busy = true; render();
  try { await fn(); } catch (e) { put($("res"), [[String(e), "bad"]]); }
  busy = false; render();
}

async function load() { state = await api("/api/state"); render(); }
async function refreshRules() { await work(async () => { const r = await api("/api/status", {}); state.info = r.info; state.history = r.history; showResult(r.result); }); }
async function execute() {
  if (!pending) return;
  const job = pending;
  if (!(await confirmDialog(job.deleting, job.commands))) return;
  pending = null;
  await work(async () => {
    const r = await api("/api/execute", { op: job.op, params: job.params, token: job.token, confirmed: true });
    state.info = r.info; state.history = r.history; showResult(r.result);
  });
}
async function deleteSelected() {
  const u = state.info.ufw; const r = u.rules[selected]; if (!r || busy) return;
  const p = await doPreview("ufw.rule.delete", { port: r.port, proto: r.proto, action: r.action });
  if (pending) await execute();
}

for (const id of ["tk-local", "tk-remote"]) $(id).addEventListener("change", async () => { readTarget(); if (!$("tk-remote").checked && state.target.kind === "remote") await applyTarget(); else renderTarget(); });
for (const id of ["tg-host", "tg-port", "tg-user", "tg-key"]) $(id).addEventListener("input", readTarget);
$("tg-use").addEventListener("click", applyTarget); $("tg-connect").addEventListener("click", connectTarget); $("tg-hostkey").addEventListener("click", checkHostKey);
$("op-preview").addEventListener("click", opPreview);
$("op-run").addEventListener("click", opRun);
$("preview").addEventListener("click", () => { const [op, params] = formOp(); doPreview(op, params); });
$("execute").addEventListener("click", execute);
$("del").addEventListener("click", deleteSelected);
$("refresh").addEventListener("click", refreshRules);
$("clear").addEventListener("click", async () => { const r = await api("/api/history/clear", {}); state.history = r.history; render(); });
$("tab-res").addEventListener("click", () => showTab("res")); $("tab-hist").addEventListener("click", () => showTab("hist"));
for (const id of ["port", "proto", "action", "comment"]) { $(id).addEventListener("input", () => { pending = null; render(); }); }
$("lang").addEventListener("change", async () => { readTarget(); lang = $("lang").value; try { localStorage.setItem("dt_lang", lang); } catch (e) {} await load(); put($("pv"), []); opPending = null; buildForm(); });
$("theme").addEventListener("click", () => { theme = theme === "light" ? "dark" : "light"; try { localStorage.setItem("dt_theme", theme); } catch (e) {} render(); });
render(); showTab("res"); put($("res"), [[t("status_ready"), "cmd"]]);
load().then(() => { render(); buildForm(); });
</script>
</body>
</html>
"""


def palette_css(palettes):
    out = []
    for name, colors in palettes.items():
        out.append(':root[data-theme="%s"]{%s}' % (name, ";".join("--%s:%s" % (k, v) for k, v in colors.items())))
    return "\n".join(out)


def render(nonce, text, palettes):
    """The page for one response. `nonce` must be a fresh random value per response (it is also in the CSP header)."""
    data = json.dumps(text, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (PAGE.replace("__NONCE__", nonce).replace("__PALETTE_CSS__", palette_css(palettes)).replace("__TEXT_JSON__", data))
