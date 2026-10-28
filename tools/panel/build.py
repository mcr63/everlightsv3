#!/usr/bin/env python3
"""Build preview.html: a single self-contained page that runs the EverLights
panel against the mock `hass`. No external requests.

    python3 build.py
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>EverLights panel preview</title>
<style>
/* Home Assistant default theme variables (approximate 2026 values). */
:root, .theme-light {
  color-scheme: light;
  --primary-color: #009ac7;
  --accent-color: #ff9800;
  --dark-primary-color: #0288d1;
  --light-primary-color: #b3e5fc;
  --text-primary-color: #ffffff;
  --primary-background-color: #fafafa;
  --secondary-background-color: #f2f2f2;
  --card-background-color: #ffffff;
  --ha-card-background: #ffffff;
  --primary-text-color: #141414;
  --secondary-text-color: #5e5e5e;
  --disabled-text-color: #bdbdbd;
  --divider-color: rgba(0, 0, 0, .12);
  --error-color: #db4437;
  --warning-color: #ffa600;
  --success-color: #43a047;
  --info-color: #039be5;
  --app-header-background-color: #fafafa;
  --app-header-text-color: #141414;
  --app-header-border-bottom: 1px solid rgba(0, 0, 0, .12);
  --sidebar-background-color: #ffffff;
  --sidebar-text-color: #212121;
  --ha-card-border-radius: 12px;
  --ha-card-border-width: 1px;
  --ha-card-border-color: #e0e0e0;
  --ha-card-box-shadow: none;
  --mdc-theme-primary: var(--primary-color);
  --state-icon-color: #44739e;
}
.theme-dark {
  color-scheme: dark;
  --primary-color: #009ac7;
  --accent-color: #ff9800;
  --text-primary-color: #ffffff;
  --primary-background-color: #111111;
  --secondary-background-color: #282828;
  --card-background-color: #1c1c1c;
  --ha-card-background: #1c1c1c;
  --primary-text-color: #e1e1e1;
  --secondary-text-color: #9b9b9b;
  --disabled-text-color: #6f6f6f;
  --divider-color: rgba(225, 225, 225, .12);
  --error-color: #ef5350;
  --app-header-background-color: #111111;
  --app-header-text-color: #e1e1e1;
  --app-header-border-bottom: 1px solid rgba(225, 225, 225, .12);
  --sidebar-background-color: #1c1c1c;
  --sidebar-text-color: #e1e1e1;
  --ha-card-border-color: rgba(225, 225, 225, .12);
  --ha-card-box-shadow: none;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  background: var(--primary-background-color);
  color: var(--primary-text-color);
  font-family: Roboto, "Noto Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 14px;
  display: flex; flex-direction: column;
}
.topbar {
  flex: none; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  padding: 8px 16px; background: #1f2a33; color: #e9eef2; font-size: 13px;
}
.topbar strong { font-weight: 600; margin-right: auto; }
.topbar label { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; cursor: pointer; }
.topbar input { width: 18px; height: 18px; margin: 0; accent-color: #4fc3f7; }
.topbar button {
  min-height: 32px; padding: 0 12px; border-radius: 16px; border: 1px solid rgba(255,255,255,.25);
  background: transparent; color: inherit; font: inherit; cursor: pointer;
}
.stage { flex: 1; display: flex; min-height: 0; }
.frame { flex: 1; min-width: 0; display: flex; justify-content: center; background: var(--primary-background-color); }
.frame.phone { background: #2a2f35; padding: 12px 0; }
.frame-inner { width: 100%; height: 100%; min-height: 0; }
.frame.phone .frame-inner { width: 390px; max-width: 100%; border-radius: 18px; overflow: hidden; box-shadow: 0 0 0 1px rgba(255,255,255,.12); }
everlights-panel { display: block; height: 100%; }
.log {
  flex: none; width: 380px; display: flex; flex-direction: column; min-height: 0;
  background: #161b20; color: #d6dde3; border-left: 1px solid #000;
  font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.log header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #2a323a; font-family: system-ui, sans-serif; font-size: 13px; }
.log header strong { margin-right: auto; }
.log header button { min-height: 28px; padding: 0 10px; border-radius: 14px; border: 1px solid #3a444d; background: transparent; color: inherit; cursor: pointer; }
.log ol { list-style: none; margin: 0; padding: 0; overflow: auto; flex: 1; }
.log li { padding: 8px 12px; border-bottom: 1px solid #222a31; white-space: pre-wrap; word-break: break-word; }
.log li .k { color: #4fc3f7; }
.log li.err .k { color: #ff8a80; }
.log li .t { color: #6b7a86; }
.log li .res { color: #9fb3c2; }
.log .empty { padding: 12px; color: #6b7a86; font-family: system-ui, sans-serif; }
body.log-hidden .log { display: none; }
@media (max-width: 900px) {
  .stage { flex-direction: column; }
  .log { width: auto; height: 34vh; border-left: 0; border-top: 1px solid #000; }
}
</style>
</head>
<body class="theme-light">
<div class="topbar">
  <strong>EverLights panel preview (mock hass, nothing reaches the lights)</strong>
  <label><input type="checkbox" id="dark"> Dark theme</label>
  <label><input type="checkbox" id="narrow"> Narrow (phone)</label>
  <label><input type="checkbox" id="showlog" checked> Call log</label>
  <button type="button" id="fail">Fail next call</button>
</div>
<div class="stage">
  <div class="frame" id="frame"><div class="frame-inner"><everlights-panel id="panel"></everlights-panel></div></div>
  <aside class="log" aria-label="Call log">
    <header><strong>Call log</strong><span id="logcount">0 calls</span><button type="button" id="clearlog">Clear</button></header>
    <ol id="log"><li class="empty">Calls the panel makes to Home Assistant appear here.</li></ol>
  </aside>
</div>
<script>
/* ---- mock-hass.js ---- */
__MOCK__
</script>
<script>
/* Minimal ha-menu-button stand-in (HA provides the real one). */
customElements.define('ha-menu-button', class extends HTMLElement {
  connectedCallback() {
    if (this.shadowRoot) return;
    const root = this.attachShadow({ mode: 'open' });
    root.innerHTML = '<style>:host{display:inline-flex}button{width:48px;height:48px;border:0;border-radius:50%;background:transparent;color:inherit;cursor:pointer;display:inline-flex;align-items:center;justify-content:center}button:hover{background:rgba(127,127,127,.15)}</style><button type="button" aria-label="Open sidebar"><svg viewBox="0 0 24 24" width="24" height="24"><path fill="currentColor" d="M3 6h18v2H3V6m0 5h18v2H3v-2m0 5h18v2H3v-2z"/></svg></button>';
    root.querySelector('button').addEventListener('click', () => logEntry({ kind: 'ui', payload: 'ha-menu-button clicked (HA would open the sidebar)', result: '', time: new Date() }));
  }
});
</script>
<script>
/* ---- everlights-panel.js ---- */
__PANEL__
</script>
<script>
(function () {
  const logEl = document.getElementById('log');
  const countEl = document.getElementById('logcount');
  let count = 0;
  window.__calls = [];
  window.logEntry = function (e) {
    window.__calls.push(e);
    if (e.kind !== 'ui') count++;
    countEl.textContent = count + (count === 1 ? ' call' : ' calls');
    const empty = logEl.querySelector('.empty');
    if (empty) empty.remove();
    const li = document.createElement('li');
    if (e.error) li.className = 'err';
    const t = e.time.toTimeString().slice(0, 8);
    const fmt = (x) => typeof x === 'string' ? x : JSON.stringify(x, null, 1).replace(/\n\s*/g, ' ');
    let head;
    if (e.kind === 'callService' && e.payload && e.payload.domain) {
      head = 'callService(' + JSON.stringify(e.payload.domain) + ', ' + JSON.stringify(e.payload.service) + ', ' + fmt(e.payload.data) + ')';
    } else {
      head = e.kind + ' ' + fmt(e.payload);
    }
    li.innerHTML = '<span class="t"></span> <span class="k"></span>\n<span class="res"></span>';
    li.querySelector('.t').textContent = t;
    li.querySelector('.k').textContent = head;
    li.querySelector('.res').textContent = e.result === '' || e.result === undefined ? '' : (e.error ? 'ERROR ' : '→ ') + fmt(e.result);
    logEl.prepend(li);
  };
  document.getElementById('clearlog').onclick = () => {
    logEl.innerHTML = '<li class="empty">Calls the panel makes to Home Assistant appear here.</li>';
    count = 0; countEl.textContent = '0 calls';
  };

  const panel = document.getElementById('panel');
  const mock = createMockHass({ onLog: window.logEntry });
  window.__mock = mock;
  panel.narrow = false;
  panel.route = { prefix: '/everlights', path: '' };
  panel.panel = { component_name: 'custom', url_path: 'everlights', config: { _panel_custom: { name: 'everlights-panel' } } };
  mock.attach(panel);

  const dark = document.getElementById('dark');
  const narrow = document.getElementById('narrow');
  const frame = document.getElementById('frame');
  const params = new URLSearchParams(location.search);
  function applyTheme() {
    document.body.classList.toggle('theme-dark', dark.checked);
    document.body.classList.toggle('theme-light', !dark.checked);
    mock.setDarkMode(dark.checked);
  }
  function applyNarrow() {
    frame.classList.toggle('phone', narrow.checked && window.innerWidth > 430);
    panel.narrow = narrow.checked;
  }
  dark.checked = params.get('dark') === '1' || (params.get('dark') === null && window.matchMedia('(prefers-color-scheme: dark)').matches);
  narrow.checked = params.get('narrow') === '1' || window.innerWidth <= 600;
  dark.onchange = applyTheme;
  narrow.onchange = applyNarrow;
  window.addEventListener('resize', applyNarrow);
  document.getElementById('showlog').onchange = (e) => document.body.classList.toggle('log-hidden', !e.target.checked);
  if (params.get('log') === '0') { document.getElementById('showlog').checked = false; document.body.classList.add('log-hidden'); }
  document.getElementById('fail').onclick = () => {
    mock.failNext('callService');
    window.logEntry({ kind: 'ui', payload: 'The next service call will fail', result: '', time: new Date() });
  };
  applyTheme();
  applyNarrow();
})();
</script>
</body>
</html>
"""


def main() -> None:
    mock = (HERE / "mock-hass.js").read_text(encoding="utf-8")
    panel = (
        HERE.parent.parent
        / "custom_components/everlights_v3/frontend/everlights-panel.js"
    ).read_text(encoding="utf-8")
    for name, src in (("mock-hass.js", mock), ("everlights-panel.js", panel)):
        if "</script" in src.lower():
            raise SystemExit(f"{name} contains '</script', which would break inlining")
    html = TEMPLATE.replace("__MOCK__", mock).replace("__PANEL__", panel)
    out = HERE / "preview.html"
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
