/*
 * EverLights pattern builder: Home Assistant custom sidebar panel.
 *
 * Served from /everlights_v3_static/everlights-panel.js and registered with
 * panel_custom as <everlights-panel>. No imports, no external requests, no
 * tokens: every call goes through the `hass` object HA hands the panel.
 *
 * The effect engine (renderFrame) is a pure function exposed as
 * globalThis.EverLights.renderFrame so it can be tested outside the browser.
 */
(() => {
  'use strict';

  // ---------------------------------------------------------------------------
  // Constants
  // ---------------------------------------------------------------------------
  const EFFECT_TYPES = ['fade', 'blink', 'strobe', 'chase', 'reverseChase', 'wipe', 'random',
    'twinkle', 'lightning', 'gradient', 'bars', 'pingPong', 'melt'];
  const EFFECT_SET = new Set(EFFECT_TYPES);
  const EFFECT_LABELS = {
    fade: 'Fade', blink: 'Blink', strobe: 'Strobe', chase: 'Chase', reverseChase: 'Reverse chase',
    wipe: 'Wipe', random: 'Random', twinkle: 'Twinkle', lightning: 'Lightning', gradient: 'Gradient',
    bars: 'Bars', pingPong: 'Ping pong', melt: 'Melt',
  };
  const STRIP_PIXELS = 333;
  const MINI_PIXELS = 60;
  const MAX_COLORS = 16;
  const ALIAS_PREFIX = '';
  const DRAFT_KEY = 'everlights-panel-draft';
  const SEND_OK_KEY = 'everlights-panel-send-confirmed';
  const DEFAULT_PATTERN = { colors: ['FF6A00', '6D04FF'], effects: [{ effectType: 'chase', value: 60 }] };
  const FETCH_CONCURRENCY = 4;

  // ---------------------------------------------------------------------------
  // Small pure helpers
  // ---------------------------------------------------------------------------
  const clamp = (x, lo, hi) => (x < lo ? lo : x > hi ? hi : x);
  const smoothstep = (e0, e1, x) => {
    if (e1 <= e0) return x >= e1 ? 1 : 0;
    const k = clamp((x - e0) / (e1 - e0), 0, 1);
    return k * k * (3 - 2 * k);
  };
  const fract = (x) => x - Math.floor(x);
  const mod = (a, n) => ((a % n) + n) % n;

  /** Normalize a hex color to uppercase RRGGBB without '#'. Returns null if invalid. */
  function normHex(value) {
    let h = String(value == null ? '' : value).trim().replace(/^#/, '');
    if (/^[0-9a-f]{3}$/i.test(h)) h = h.split('').map((c) => c + c).join('');
    return /^[0-9a-f]{6}$/i.test(h) ? h.toUpperCase() : null;
  }

  function hexToRgb(value) {
    const h = normHex(value);
    if (!h) return [0, 0, 0];
    const n = parseInt(h, 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }

  function rgbToHex([r, g, b]) {
    return [r, g, b].map((v) => clamp(Math.round(v), 0, 255).toString(16).padStart(2, '0')).join('').toUpperCase();
  }

  /** Deterministic hash of three integers to [0, 1). */
  function hash3(a, b, c) {
    let h = Math.imul((a | 0) ^ 0x9e3779b9, 0x85ebca6b);
    h ^= Math.imul((b | 0) + 0x632be5ab, 0xc2b2ae35);
    h ^= Math.imul((c | 0) + 0x7f4a7c15, 0x27d4eb2f);
    h ^= h >>> 15; h = Math.imul(h, 0x2c1b3c6d);
    h ^= h >>> 12; h = Math.imul(h, 0x297a2d39);
    h ^= h >>> 15;
    return (h >>> 0) / 4294967296;
  }

  function hashString(s) {
    let h = 2166136261;
    for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h | 0;
  }

  // ---------------------------------------------------------------------------
  // Effect engine
  // ---------------------------------------------------------------------------
  /**
   * Render one frame of a strip.
   *
   * Emulation model (an approximation of the bridge, tuned to feel right):
   *   Layout:     bars widen each color into a block; gradient blends neighbours.
   *   Motion:     chase / reverseChase scroll, pingPong swings back and forth,
   *               melt warps and drifts like running wax. Offsets add up.
   *   Selection:  random reassigns each block's color on a staggered timer.
   *   Brightness: fade breathes, twinkle sparkles per LED, lightning dims the
   *               strip and throws white flashes over part of it.
   *   Masks:      wipe reveals and hides the strip; blink and strobe gate it.
   * Higher values are faster or more intense. Stacked effects compose in that
   * order, whatever order they appear in the list.
   *
   * @param {string[]} colors hex colors (with or without '#')
   * @param {{effectType:string,value:number}[]} effects
   * @param {number} tMs time in milliseconds
   * @param {number} n pixel count
   * @param {number} seed integer seed for random-looking effects
   * @returns {number[][]} n entries of [r, g, b], 0-255
   */
  function renderFrame(colors, effects, tMs, n, seed) {
    n = Math.max(0, n | 0);
    seed = seed | 0;
    const pal = [];
    for (const c of Array.isArray(colors) ? colors : []) pal.push(hexToRgb(c));
    if (!pal.length) pal.push([0, 0, 0]);
    const nc = pal.length;
    const t = (Number(tMs) || 0) / 1000;
    const TAU = Math.PI * 2;

    const fx = [];
    for (const e of Array.isArray(effects) ? effects : []) {
      if (e && EFFECT_SET.has(e.effectType)) fx.push({ type: e.effectType, v: clamp(Number(e.value) || 0, 0, 255) / 255 });
    }

    // Pass 1: layout.
    let bars = 0;
    let grad = -1;
    for (const { type, v } of fx) {
      if (type === 'bars') bars = Math.max(bars, 2 + Math.round(v * 10));
      else if (type === 'gradient') grad = Math.max(grad, v);
    }
    let seg = 1;
    let blend = 0;
    if (bars) {
      seg = bars;
      if (grad >= 0) blend = 0.3 + 0.7 * grad;
    } else if (grad >= 0) {
      seg = 3 + grad * 29;
      blend = 1;
    }
    const period = seg * nc;

    // Pass 2: motion, selection, brightness parameters.
    let offset = 0;
    let meltAmp = 0;
    let meltW = 0;
    let randomRate = 0;
    let fadeGain = 1;
    let gate = 1;
    const twinkles = [];
    const strikes = [];
    const wipes = [];
    let stormBase = 1;

    for (const { type, v } of fx) {
      switch (type) {
        case 'chase': offset -= t * (1 + v * 90); break;
        case 'reverseChase': offset += t * (1 + v * 90); break;
        case 'pingPong': offset += Math.max(period, 6) * Math.sin(TAU * t * (0.05 + v * 0.9)); break;
        case 'melt':
          meltAmp += Math.max(period * 0.6, 4);
          meltW = Math.max(meltW, 0.2 + v * 3);
          offset -= t * (0.3 + v * 4);
          blend = Math.max(blend, 0.65);
          break;
        case 'random': randomRate = Math.max(randomRate, 0.25 + v * 6); break;
        case 'fade': fadeGain *= 0.06 + 0.94 * (0.5 - 0.5 * Math.cos(TAU * t * (0.03 + v * 1.0))); break;
        case 'blink': gate *= fract(t * (0.2 + v * 3)) < 0.5 ? 1 : 0.02; break;
        case 'strobe': gate *= fract(t * (1 + v * 9)) < 0.3 ? 1 : 0; break;
        case 'twinkle': twinkles.push(v); break;
        case 'wipe': wipes.push(v); break;
        case 'lightning': {
          stormBase *= 0.55;
          const slotDur = 3.4 - v * 2.8;
          const slot = Math.floor(t / slotDur);
          const lt = t - slot * slotDur;
          if (hash3(slot, 101, seed) < 0.55 + 0.4 * v) {
            const start = hash3(slot, 102, seed) * slotDur * 0.55;
            const flicks = 1 + Math.floor(hash3(slot, 103, seed) * 3);
            let F = 0;
            let s = start;
            for (let k = 0; k < flicks; k++) {
              if (lt >= s) F = Math.max(F, Math.exp(-(lt - s) / 0.06) * (k === 0 ? 1 : 0.75));
              s += 0.07 + 0.06 * hash3(slot, 110 + k, seed);
            }
            if (F > 0.002) {
              strikes.push({
                F,
                center: hash3(slot, 104, seed) * n,
                half: Math.max(3, n * (0.2 + 0.4 * hash3(slot, 105, seed))),
              });
            }
          }
          break;
        }
        default: break;
      }
    }

    const cellColor = (cell) => {
      if (randomRate > 0) {
        const epoch = Math.floor(t * randomRate + hash3(cell, 1, seed));
        return pal[Math.floor(hash3(cell, epoch, seed) * nc) % nc];
      }
      return pal[mod(cell, nc)];
    };

    const out = new Array(n);
    for (let i = 0; i < n; i++) {
      // Sample the pattern.
      let p = i + offset;
      if (meltAmp) p += meltAmp * Math.sin(i * 0.045 + t * meltW);
      const q = p / seg;
      const cell = Math.floor(q);
      let c = cellColor(cell);
      if (blend > 0) {
        const f = smoothstep(1 - blend, 1, q - cell);
        if (f > 0) {
          const d = cellColor(cell + 1);
          c = [c[0] + (d[0] - c[0]) * f, c[1] + (d[1] - c[1]) * f, c[2] + (d[2] - c[2]) * f];
        }
      }

      // Brightness.
      let b = fadeGain;
      let white = 0;
      for (const v of twinkles) {
        const rate = (0.15 + v * 2.2) * (0.6 + 0.8 * hash3(i, 7, seed));
        const s = 0.5 + 0.5 * Math.sin(TAU * (t * rate + hash3(i, 13, seed)));
        const sp = s * s * s * s * s * s;
        b *= 0.22 + 0.78 * sp;
        white = Math.max(white, sp * sp * 0.25);
      }
      let r = (c[0] + (255 - c[0]) * white) * b * stormBase;
      let g = (c[1] + (255 - c[1]) * white) * b * stormBase;
      let bl = (c[2] + (255 - c[2]) * white) * b * stormBase;

      for (const s of strikes) {
        const d = Math.abs(i - s.center) / s.half;
        if (d < 1) {
          const k = s.F * (1 - d * d);
          r += k * (c[0] + (255 - c[0]) * 0.65);
          g += k * (c[1] + (255 - c[1]) * 0.65);
          bl += k * (c[2] + (255 - c[2]) * 0.65);
        }
      }

      // Masks.
      let m = gate;
      for (const v of wipes) {
        const L = n;
        const d = mod(t * (10 + v * 170) * (n / STRIP_PIXELS), 2.4 * L);
        if (d < L) m *= clamp(d - i, 0, 1);
        else if (d < 2.2 * L) m *= d < 1.2 * L ? 1 : 1 - clamp(d - 1.2 * L - i, 0, 1);
        else m = 0;
      }
      out[i] = [clamp(Math.round(r * m), 0, 255), clamp(Math.round(g * m), 0, 255), clamp(Math.round(bl * m), 0, 255)];
    }
    return out;
  }

  // ---------------------------------------------------------------------------
  // Domain helpers
  // ---------------------------------------------------------------------------
  /** Lowercase a-z0-9 and underscores. */
  function slugify(name) {
    return String(name || '')
      .normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .replace(/['’]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '');
  }

  function displayName(alias, fallback) {
    const a = String(alias || '').trim();
    if (!a) return fallback || '';
    return a.toLowerCase().startsWith(ALIAS_PREFIX.toLowerCase()) ? a.slice(ALIAS_PREFIX.length).trim() : a;
  }

  function cleanEffects(list) {
    const out = [];
    for (const e of Array.isArray(list) ? list : []) {
      if (e && EFFECT_SET.has(e.effectType)) out.push({ effectType: e.effectType, value: clamp(Math.round(Number(e.value) || 0), 0, 255) });
    }
    return out;
  }

  function effectSummary(effects) {
    if (!effects || !effects.length) return 'Solid, no effects';
    return effects.map((e) => `${EFFECT_LABELS[e.effectType] || e.effectType} ${e.value}`).join(' + ');
  }

  function errMessage(err) {
    if (!err) return 'Unknown error';
    if (typeof err === 'string') return err;
    const body = err.body;
    if (body && typeof body === 'object' && body.message) return body.message;
    if (typeof body === 'string' && body) return body;
    if (err.message) return err.message;
    if (err.error) return String(err.error);
    if (err.status_code) return `HTTP ${err.status_code}`;
    try { return JSON.stringify(err); } catch (_) { return String(err); }
  }

  function fmtInterval(sec) {
    sec = Math.round(Number(sec) || 0);
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    if (!m) return `${s} s`;
    return s ? `${m} min ${s} s` : `${m} min`;
  }

  function splitItems(value) {
    return String(value || '').split(',').map((s) => s.trim()).filter(Boolean);
  }

  function storageGet(store, key) {
    try { return window[store].getItem(key); } catch (_) { return null; }
  }
  function storageSet(store, key, value) {
    try { window[store].setItem(key, value); } catch (_) { /* storage unavailable */ }
  }

  function nextColor(prevHex) {
    const [r, g, b] = hexToRgb(prevHex || 'FF6A00').map((v) => v / 255);
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    let h = 0;
    const d = max - min;
    if (d) {
      if (max === r) h = ((g - b) / d) % 6;
      else if (max === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
    }
    h = mod(h * 60 + 48, 360);
    const s = 1;
    const v = 1;
    const c = v * s;
    const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
    const [rr, gg, bb] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
      : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
    return rgbToHex([rr * 255, gg * 255, bb * 255]);
  }

  function readableOn(hex) {
    const [r, g, b] = hexToRgb(hex);
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? 'rgba(0,0,0,.78)' : 'rgba(255,255,255,.92)';
  }

  globalThis.EverLights = Object.assign(globalThis.EverLights || {}, {
    renderFrame, slugify, effectSummary, normHex, EFFECT_TYPES,
  });

  if (typeof HTMLElement === 'undefined' || typeof customElements === 'undefined') return;

  // ---------------------------------------------------------------------------
  // DOM helpers
  // ---------------------------------------------------------------------------
  const PROP_KEYS = new Set(['value', 'checked', 'disabled', 'min', 'max', 'step', 'type', 'placeholder', 'tabIndex', 'title']);
  function el(tag, props, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else if (k === 'html') e.innerHTML = v; // static markup only (icons)
      else if (k.startsWith('on') && typeof v === 'function') e.addEventListener(k.slice(2), v);
      else if (PROP_KEYS.has(k)) e[k] = v;
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      e.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return e;
  }

  const svg = (d, size = 20) => `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" focusable="false"><path fill="currentColor" d="${d}"/></svg>`;
  const ICON = {
    play: svg('M8 5.14v13.72a1 1 0 0 0 1.5.86l11-6.86a1 1 0 0 0 0-1.72l-11-6.86A1 1 0 0 0 8 5.14z', 18),
    plus: svg('M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z'),
    close: svg('M19 6.41 17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z', 18),
    grip: svg('M9 3a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm6 0a2 2 0 1 1 0 4 2 2 0 0 1 0-4zM9 10a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm6 0a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm-6 7a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm6 0a2 2 0 1 1 0 4 2 2 0 0 1 0-4z', 18),
    send: svg('M2.01 21 23 12 2.01 3 2 10l15 2-15 2z'),
    refresh: svg('M17.65 6.35A7.96 7.96 0 0 0 12 4a8 8 0 1 0 7.74 10h-2.08A6 6 0 1 1 12 6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z', 18),
    trash: svg('M6 19a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z', 18),
  };

  // ---------------------------------------------------------------------------
  // Strip view: draws an array of pixels as glowing LEDs on a canvas
  // ---------------------------------------------------------------------------
  class StripView {
    constructor(canvas, n, { multiRow }) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.n = n;
      this.multiRow = multiRow;
      this.w = 0;
      this.layout = null;
      this.ro = new ResizeObserver(() => this.measure());
      this.ro.observe(canvas);
      this.measure();
    }

    measure() {
      const w = Math.floor(this.canvas.clientWidth);
      if (!w || w === this.w) return;
      this.w = w;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      let perRow;
      let pitch;
      let rowH;
      let rows;
      if (this.multiRow) {
        const target = w < 520 ? 11 : 13;
        perRow = Math.max(8, Math.floor(w / target));
        pitch = w / perRow;
        rows = Math.ceil(this.n / perRow);
        rowH = pitch * 1.3;
      } else {
        perRow = this.n;
        pitch = w / this.n;
        rows = 1;
        rowH = Math.max(18, pitch * 2.6);
      }
      const h = Math.ceil(rows * rowH);
      this.canvas.style.height = `${h}px`;
      this.canvas.width = Math.round(w * dpr);
      this.canvas.height = Math.round(h * dpr);
      this.layout = { perRow, pitch, rowH, dpr, w, h, core: pitch * (this.multiRow ? 0.26 : 0.3), halo: pitch * (this.multiRow ? 0.42 : 0.45) };
    }

    draw(pixels) {
      const L = this.layout;
      if (!L || !pixels) return;
      const { ctx } = this;
      const rows = Math.max(1, Math.ceil(pixels.length / L.perRow));
      // Glow: one texel per LED, upscaled with bilinear smoothing. Cheap, and it
      // works everywhere (ctx.filter blur is not reliable on Safari).
      if (!this.glow || this.glow.width !== L.perRow || this.glow.height !== rows) {
        this.glow = document.createElement('canvas');
        this.glow.width = L.perRow;
        this.glow.height = rows;
        this.glowCtx = this.glow.getContext('2d');
        this.glowImg = this.glowCtx.createImageData(L.perRow, rows);
      }
      const data = this.glowImg.data;
      data.fill(0);
      for (let i = 0; i < pixels.length; i++) {
        const o = i * 4;
        data[o] = pixels[i][0]; data[o + 1] = pixels[i][1]; data[o + 2] = pixels[i][2]; data[o + 3] = 255;
      }
      this.glowCtx.putImageData(this.glowImg, 0, 0);

      ctx.setTransform(L.dpr, 0, 0, L.dpr, 0, 0);
      ctx.globalCompositeOperation = 'source-over';
      ctx.globalAlpha = 1;
      ctx.clearRect(0, 0, L.w, L.h);
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.globalAlpha = 0.55;
      ctx.drawImage(this.glow, 0, 0, L.perRow, rows, 0, 0, L.perRow * L.pitch, rows * L.rowH);
      ctx.globalAlpha = 1;
      const pos = (i) => [(i % L.perRow + 0.5) * L.pitch, (Math.floor(i / L.perRow) + 0.5) * L.rowH];
      // Unlit LEDs, one path.
      ctx.fillStyle = 'rgba(255,255,255,0.08)';
      ctx.beginPath();
      for (let i = 0; i < pixels.length; i++) {
        const [x, y] = pos(i);
        ctx.moveTo(x + L.core, y);
        ctx.arc(x, y, L.core, 0, Math.PI * 2);
      }
      ctx.fill();
      ctx.globalCompositeOperation = 'lighter';
      for (let i = 0; i < pixels.length; i++) {
        const [r, g, b] = pixels[i];
        if (r + g + b < 6) continue;
        const [x, y] = pos(i);
        ctx.fillStyle = `rgba(${r},${g},${b},0.35)`;
        ctx.beginPath();
        ctx.arc(x, y, L.halo, 0, Math.PI * 2);
        ctx.fill();
        // Hot centre: lift toward white so bright LEDs read as light, not paint.
        ctx.fillStyle = `rgb(${(r + (255 - r) * 0.25) | 0},${(g + (255 - g) * 0.25) | 0},${(b + (255 - b) * 0.25) | 0})`;
        ctx.beginPath();
        ctx.arc(x, y, L.core, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    destroy() { this.ro.disconnect(); }
  }

  // ---------------------------------------------------------------------------
  // Styles
  // ---------------------------------------------------------------------------
  const STYLE = `
:host {
  display: block;
  height: 100%;
  --el-gap: 16px;
  --el-radius: var(--ha-card-border-radius, 12px);
  --el-text: var(--primary-text-color, #212121);
  --el-muted: var(--secondary-text-color, #727272);
  --el-divider: var(--divider-color, rgba(0, 0, 0, .12));
  --el-primary: var(--primary-color, #03a9f4);
  --el-on-primary: var(--text-primary-color, #fff);
  --el-card: var(--ha-card-background, var(--card-background-color, #fff));
  --el-input: var(--secondary-background-color, #f2f2f2);
  --el-error: var(--error-color, #db4437);
  --el-strip-bg: var(--everlights-strip-background, #06070a);
  color: var(--el-text);
  background: var(--primary-background-color, #fafafa);
  font-family: var(--ha-font-family-body, var(--paper-font-body1_-_font-family, Roboto, "Noto Sans", system-ui, sans-serif));
  font-size: 14px;
  line-height: 1.45;
  -webkit-font-smoothing: antialiased;
}
:host([dark]) { color-scheme: dark; }
* { box-sizing: border-box; }
[hidden] { display: none !important; }
button, input, select { font: inherit; color: inherit; }
button svg { flex: none; }
.layout { display: flex; flex-direction: column; height: 100%; }
header {
  display: flex; align-items: center; gap: 4px;
  min-height: 56px; padding: 0 16px;
  background: var(--app-header-background-color, var(--primary-background-color, #fafafa));
  color: var(--app-header-text-color, var(--el-text));
  border-bottom: var(--app-header-border-bottom, 1px solid var(--el-divider));
  flex: none;
}
header.has-menu { padding-left: 4px; }
header h1 { margin: 0; font-size: 20px; font-weight: 400; letter-spacing: 0; }
.menu-slot:empty { display: none; }
.page { flex: 1; overflow-y: auto; overflow-x: hidden; container-type: inline-size; -webkit-overflow-scrolling: touch; }
.grid {
  display: grid; grid-template-columns: minmax(0, 7fr) minmax(320px, 5fr);
  gap: var(--el-gap); padding: var(--el-gap); max-width: 1480px; margin: 0 auto; align-items: start;
  padding-bottom: calc(var(--el-gap) + env(safe-area-inset-bottom, 0px));
}
.col { display: flex; flex-direction: column; gap: var(--el-gap); min-width: 0; }
@container (max-width: 800px) {
  .grid { grid-template-columns: minmax(0, 1fr); --el-gap: 12px; }
}
.card {
  background: var(--el-card);
  border-radius: var(--el-radius);
  box-shadow: var(--ha-card-box-shadow, none);
  border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--el-divider));
  padding: 16px;
  min-width: 0;
}
h2 { margin: 0; font-size: 16px; font-weight: 500; }
h3 { margin: 20px 0 10px; font-size: 14px; font-weight: 500; display: flex; align-items: baseline; gap: 8px; }
h3:first-child { margin-top: 0; }
.muted { color: var(--el-muted); font-weight: 400; font-size: 13px; }
.row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.spacer { flex: 1; }

/* Buttons */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  min-height: 40px; padding: 0 16px; border-radius: 20px;
  border: 1px solid var(--el-divider); background: transparent; cursor: pointer;
  font-weight: 500; white-space: nowrap; -webkit-tap-highlight-color: transparent;
}
.btn:hover:not(:disabled) { background: color-mix(in srgb, var(--el-primary) 8%, transparent); }
.btn:disabled { opacity: .45; cursor: default; }
.btn.primary { background: var(--el-primary); color: var(--el-on-primary); border-color: transparent; }
.btn.primary:hover:not(:disabled) { background: color-mix(in srgb, var(--el-primary) 88%, #000); }
.btn.text { border-color: transparent; color: var(--el-primary); padding: 0 12px; }
.btn.danger { color: var(--el-error); border-color: color-mix(in srgb, var(--el-error) 40%, transparent); }
.btn.danger.solid { background: var(--el-error); color: #fff; border-color: transparent; }
.icon-btn {
  width: 40px; height: 40px; min-width: 40px; display: inline-flex; align-items: center; justify-content: center;
  border-radius: 50%; border: 0; background: transparent; cursor: pointer; color: var(--el-muted);
  -webkit-tap-highlight-color: transparent;
}
.icon-btn:hover:not(:disabled) { background: color-mix(in srgb, var(--el-text) 8%, transparent); color: var(--el-text); }
.icon-btn:disabled { opacity: .35; cursor: default; }
:focus-visible { outline: 2px solid var(--el-primary); outline-offset: 2px; }

/* Preview */
.preview-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; min-height: 40px; }
.preview-head h2 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dirty { color: var(--el-muted); font-size: 13px; white-space: nowrap; }
.dirty[hidden] { display: none; }
.housing {
  --glow: 80, 80, 80;
  background: var(--el-strip-bg);
  border-radius: calc(var(--el-radius) - 4px);
  padding: 12px 10px;
  box-shadow: inset 0 0 0 1px rgba(255,255,255,.05), 0 10px 36px -14px rgba(var(--glow), .75);
  transition: box-shadow .6s linear;
}
.housing canvas { display: block; width: 100%; }
.preview-foot { display: flex; align-items: center; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
.preview-foot .muted { flex: 1 1 200px; }

/* Colors */
.swatches { display: flex; flex-wrap: wrap; gap: 10px; }
.swatch {
  width: 80px; border-radius: 10px; background: var(--el-input);
  border: 1px solid var(--el-divider); position: relative; touch-action: auto;
  transition: transform .12s ease;
}
.swatch.dragging { z-index: 3; transition: none; box-shadow: 0 10px 24px rgba(0,0,0,.35); cursor: grabbing; }
.swatch.drop-before::before, .swatch.drop-after::after {
  content: ""; position: absolute; top: 4px; bottom: 4px; width: 3px; border-radius: 2px; background: var(--el-primary);
}
.swatch.drop-before::before { left: -7px; }
.swatch.drop-after::after { right: -7px; }
.swatch-color {
  position: relative; display: flex; align-items: flex-end; justify-content: center;
  height: 56px; border-radius: 9px 9px 0 0; cursor: pointer; overflow: hidden;
}
.swatch-color input {
  position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; cursor: pointer; border: 0; padding: 0;
}
.swatch-color:focus-within { outline: 2px solid var(--el-primary); outline-offset: 2px; }
.swatch-hex { font-size: 11px; font-variant-numeric: tabular-nums; letter-spacing: .02em; padding-bottom: 4px; pointer-events: none; }
.swatch-tools { display: flex; justify-content: space-between; }
.swatch-tools .icon-btn { border-radius: 8px; }
.grip { cursor: grab; touch-action: none; }
.add-swatch {
  width: 80px; height: 97px; border-radius: 10px; border: 1.5px dashed var(--el-divider);
  background: transparent; cursor: pointer; color: var(--el-muted);
  display: inline-flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; font-size: 13px;
}
.add-swatch:hover:not(:disabled) { color: var(--el-primary); border-color: var(--el-primary); }
.add-swatch:disabled { display: none; }

/* Effects */
.fx-list { display: flex; flex-direction: column; gap: 8px; }
.fx-row {
  display: grid; grid-template-columns: minmax(130px, 170px) minmax(0, 1fr) 68px 40px;
  align-items: center; gap: 10px;
}
.fx-empty { color: var(--el-muted); margin: 0; padding: 4px 0; }
select, input[type=number], input[type=text], input[type=search] {
  min-height: 40px; border-radius: 8px; border: 1px solid var(--el-divider);
  background: var(--el-input); padding: 0 10px; width: 100%; min-width: 0;
}
input[type=number] { font-variant-numeric: tabular-nums; text-align: right; padding-right: 6px; }
input[type=range] { width: 100%; min-width: 0; height: 40px; margin: 0; accent-color: var(--el-primary); background: transparent; }
.add-fx { margin-top: 10px; }
@container (max-width: 520px) {
  .fx-row { grid-template-columns: minmax(0, 1fr) 68px 40px; gap: 4px 8px; padding-bottom: 8px; border-bottom: 1px solid var(--el-divider); }
  .fx-row select { grid-column: 1 / 3; }
  .fx-row .fx-remove { grid-column: 3; grid-row: 1; }
  .fx-row input[type=range] { grid-column: 1 / 2; grid-row: 2; }
  .fx-row input[type=number] { grid-column: 2 / 4; grid-row: 2; }
  .swatch, .add-swatch { width: calc((100% - 30px) / 4); min-width: 64px; }
}

/* Save */
.save-field { display: flex; flex-direction: column; gap: 6px; }
.save-field label { font-weight: 500; }
.slug-hint { font-size: 12px; color: var(--el-muted); overflow-wrap: anywhere; }
.save-actions { margin-top: 12px; }

/* Playlist */
.pl-head { display: flex; align-items: center; gap: 8px; }
.switch {
  margin-left: auto; position: relative; width: 52px; height: 40px; border: 0; background: transparent; cursor: pointer; padding: 0;
  -webkit-tap-highlight-color: transparent;
}
.switch::before {
  content: ""; position: absolute; left: 4px; right: 4px; top: 10px; height: 20px; border-radius: 10px;
  background: color-mix(in srgb, var(--el-text) 26%, transparent); transition: background .15s;
}
.switch::after {
  content: ""; position: absolute; left: 4px; top: 8px; width: 24px; height: 24px; border-radius: 50%;
  background: var(--el-card); box-shadow: 0 1px 3px rgba(0,0,0,.4); transition: transform .15s;
}
.switch[aria-checked="true"]::before { background: color-mix(in srgb, var(--el-primary) 55%, transparent); }
.switch[aria-checked="true"]::after { transform: translateX(20px); background: var(--el-primary); }
.switch:disabled { opacity: .45; }
.pl-status { color: var(--el-muted); font-size: 13px; margin: 2px 0 0; }
.field { margin-top: 14px; }
.field > .label { display: block; font-weight: 500; margin-bottom: 6px; }
.interval { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.interval input { width: 72px; flex: none; }
.interval .muted { margin-left: 4px; }
.seg { display: inline-flex; border: 1px solid var(--el-divider); border-radius: 20px; overflow: hidden; }
.seg button {
  min-height: 40px; padding: 0 16px; border: 0; background: transparent; cursor: pointer; font-weight: 500;
}
.seg button + button { border-left: 1px solid var(--el-divider); }
.seg button[aria-pressed="true"] { background: color-mix(in srgb, var(--el-primary) 18%, transparent); color: var(--el-primary); }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  display: inline-flex; align-items: center; gap: 2px; min-height: 36px; padding-left: 12px; border-radius: 18px;
  background: var(--el-input); border: 1px solid var(--el-divider); max-width: 100%;
}
.chip span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip.missing { border-style: dashed; color: var(--el-muted); }
.chip .icon-btn { width: 36px; height: 36px; min-width: 36px; }
.chips-empty { color: var(--el-muted); margin: 0; }
.pl-foot { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.pl-foot .muted { flex: 1; }
.mixes { display: flex; flex-wrap: wrap; gap: 8px; }
.missing-note { color: var(--el-muted); font-size: 13px; margin: 0; }

/* Gallery */
.gal-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gal-head h2 { margin-right: auto; }
.gal-filter { margin: 12px 0; }
.gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(160px, 100%), 1fr)); gap: 10px; }
.pcard {
  display: flex; flex-direction: column; border-radius: 10px; border: 1px solid var(--el-divider);
  background: var(--el-card); overflow: hidden; min-width: 0;
}
.pcard.active { border-color: var(--el-primary); box-shadow: 0 0 0 1px var(--el-primary); }
.pcard .load {
  display: flex; flex-direction: column; align-items: stretch; gap: 2px; text-align: left; width: 100%;
  border: 0; background: transparent; padding: 0 0 6px; cursor: pointer; min-width: 0;
}
.pcard .load:hover .pname { color: var(--el-primary); }
.mini { position: relative; background: var(--el-strip-bg); padding: 4px 6px; margin-bottom: 6px; min-height: 26px; }
.mini canvas { display: block; width: 100%; }
.skeleton {
  position: absolute; inset: 9px 8px; border-radius: 6px;
  background: linear-gradient(90deg, rgba(255,255,255,.05) 0%, rgba(255,255,255,.14) 50%, rgba(255,255,255,.05) 100%);
  background-size: 200% 100%; animation: shimmer 1.2s linear infinite;
}
@keyframes shimmer { from { background-position: 100% 0; } to { background-position: -100% 0; } }
.pname { font-weight: 500; padding: 0 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.psum { color: var(--el-muted); font-size: 12px; padding: 0 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-height: 17px; }
.psum.err { color: var(--el-error); }
.pactions { display: flex; gap: 4px; padding: 0 6px 6px; margin-top: auto; }
.pactions .btn { flex: 1; padding: 0 8px; min-width: 0; font-size: 13px; }
.gal-empty { color: var(--el-muted); margin: 8px 0 0; }

/* Dialog + toast */
.scrim {
  position: fixed; inset: 0; z-index: 10; display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,.45); padding: 16px;
}
.dialog {
  background: var(--el-card); color: var(--el-text); border-radius: 16px; padding: 20px; width: min(420px, 100%);
  box-shadow: 0 18px 48px rgba(0,0,0,.4);
}
.dialog h2 { font-size: 18px; margin-bottom: 8px; }
.dialog p { margin: 0 0 18px; color: var(--el-muted); overflow-wrap: anywhere; }
.dialog .row { justify-content: flex-end; }
.toast {
  position: fixed; left: 50%; bottom: calc(20px + env(safe-area-inset-bottom, 0px)); transform: translate(-50%, 20px);
  z-index: 11; max-width: min(560px, calc(100% - 32px)); padding: 12px 16px; border-radius: 8px;
  background: var(--el-toast-bg, #323232); color: #fff; box-shadow: 0 6px 18px rgba(0,0,0,.3);
  opacity: 0; pointer-events: none; transition: opacity .2s, transform .2s;
}
.toast.show { opacity: 1; transform: translate(-50%, 0); pointer-events: auto; }
.toast.error { border-left: 4px solid var(--el-error); }
@media (prefers-reduced-motion: reduce) {
  .skeleton { animation: none; }
  .toast, .swatch, .housing { transition: none; }
}
`;

  // ---------------------------------------------------------------------------
  // Panel
  // ---------------------------------------------------------------------------
  class EverLightsPanel extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      this._hass = null;
      this._narrow = false;
      this._built = false;
      this._editor = this._loadDraft() || {
        colors: DEFAULT_PATTERN.colors.slice(), effects: DEFAULT_PATTERN.effects.map((e) => ({ ...e })),
        name: '', loadedId: null, dirty: false,
      };
      this._configs = new Map(); // object_id -> { status, config, parsed, promise }
      this._cards = new Map(); // object_id -> card record
      this._galleryKey = '';
      this._fetchQueue = [];
      this._activeFetches = 0;
      this._fetchErrorShown = false;
      this._last = {};
      this._raf = 0;
      this._frame = 0;
      this._busy = new Set();
      this._sendConfirmed = storageGet('sessionStorage', SEND_OK_KEY) === '1';
      this._reducedMotion = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
      this._tick = this._tick.bind(this);
      this._onVisibility = () => this._syncLoop();
    }

    // HA-provided properties ---------------------------------------------------
    set hass(hass) {
      const old = this._hass;
      this._hass = hass;
      if (this._built) this._hassChanged(old, hass);
    }
    get hass() { return this._hass; }
    set narrow(v) {
      v = !!v;
      if (v === this._narrow) return;
      this._narrow = v;
      if (this._built) this._updateMenuButton();
    }
    get narrow() { return this._narrow; }
    set route(v) { this._route = v; }
    get route() { return this._route; }
    set panel(v) { this._panel = v; }
    get panel() { return this._panel; }

    connectedCallback() {
      if (!this._built) this._build();
      document.addEventListener('visibilitychange', this._onVisibility);
      this._syncLoop();
      this._poll=setInterval(()=>this._refreshData(),5000);
    }

    disconnectedCallback() {
      clearInterval(this._poll);
      document.removeEventListener('visibilitychange', this._onVisibility);
      this._syncLoop();
    }

    // Build once ---------------------------------------------------------------
    _build() {
      this._built = true;
      const root = this.shadowRoot;
      root.innerHTML = '';
      root.append(el('style', { text: STYLE }));

      this._menuSlot = el('div', { class: 'menu-slot' });
      this._zonePicker=el('select',{'aria-label':'Zone',onchange:()=>{this._entryId=null;this._playlistDraft=null;this._playlistEdited=false;this._intervalEdited=false;this._refreshData(true);}});
      this._brightnessInput=el('input',{type:'range',min:'0',max:'255',value:'255','aria-label':'Brightness'});
      this._header = el('header', {}, this._menuSlot, el('h1', { text: 'EverLights' }),this._zonePicker,el('label',{},'Brightness',this._brightnessInput));

      // Preview card
      this._edTitle = el('h2', { text: 'New pattern' });
      this._dirtyEl = el('span', { class: 'dirty', text: 'Unsaved changes', hidden: true });
      this._mainCanvas = el('canvas', { 'aria-label': 'Live preview of the 333-pixel strip', role: 'img' });
      this._housing = el('div', { class: 'housing' }, this._mainCanvas);
      this._stripMeta = el('span', { class: 'muted' });
      this._sendBtn = el('button', { class: 'btn primary send', html: `${ICON.send}<span>Send to lights</span>`, onclick: () => this._send() });
      const previewCard = el('section', { class: 'card preview' },
        el('div', { class: 'preview-head' }, this._edTitle, this._dirtyEl, el('span', { class: 'spacer' }),
          el('button', { class: 'btn text new-pattern', text: 'Start over', onclick: () => this._newPattern() })),
        this._housing,
        el('div', { class: 'preview-foot' }, this._stripMeta, this._sendBtn));

      // Editor card
      this._colorCount = el('span', { class: 'muted' });
      this._swatches = el('div', { class: 'swatches', role: 'list' });
      this._fxList = el('div', { class: 'fx-list' });
      this._addFxBtn = el('button', { class: 'btn add-fx', html: `${ICON.plus}<span>Add effect</span>`, onclick: () => this._addEffect() });
      const editorCard = el('section', { class: 'card editor' },
        el('h3', {}, 'Colors', this._colorCount),
        this._swatches,
        el('h3', {}, 'Effects', el('span', { class: 'muted', text: 'Higher values are faster or stronger' })),
        this._fxList, this._addFxBtn);

      // Save card
      this._nameInput = el('input', {
        type: 'text', id: 'pattern-name', placeholder: 'e.g. Haunted lightning', autocomplete: 'off', maxlength: '60',
        oninput: (e) => { this._editor.name = e.target.value; this._editor.dirty = true; this._saveDraft(); this._renderMeta(); },
        onkeydown: (e) => { if (e.key === 'Enter') this._save(false); },
      });
      this._slugHint = el('span', { class: 'slug-hint' });
      this._saveBtn = el('button', { class: 'btn primary save', text: 'Save', onclick: () => this._save(false) });
      this._saveNewBtn = el('button', { class: 'btn save-new', text: 'Save as new', onclick: () => this._save(true) });
      this._deleteBtn = el('button', { class: 'btn danger delete', html: `${ICON.trash}<span>Delete</span>`, onclick: () => this._delete() });
      const saveCard = el('section', { class: 'card save-card' },
        el('div', { class: 'save-field' }, el('label', { for: 'pattern-name', text: 'Pattern name' }), this._nameInput, this._slugHint),
        el('div', { class: 'row save-actions' }, this._saveBtn, this._saveNewBtn, el('span', { class: 'spacer' }), this._deleteBtn));

      // Playlist card
      this._plSwitch = el('button', { class: 'switch', role: 'switch', 'aria-checked': 'false', 'aria-label': 'Playlist on or off', onclick: () => this._togglePlaylist() });
      this._plStatus = el('p', { class: 'pl-status' });
      this._ivMin = el('input', { type: 'number', min: '0', step: '1', inputmode: 'numeric', 'aria-label': 'Minutes', onchange: () => this._setInterval() });
      this._ivSec = el('input', { type: 'number', min: '0', max: '59', step: '1', inputmode: 'numeric', 'aria-label': 'Seconds', onchange: () => this._setInterval() });
      this._ivRange = el('span', { class: 'muted' });
      this._intervalField = el('div', { class: 'field' }, el('span', { class: 'label', text: 'Change every' }),
        el('div', { class: 'interval' }, this._ivMin, el('span', { text: 'min' }), this._ivSec, el('span', { text: 's' }), this._ivRange));
      this._orderSeg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Playlist order' });
      this._orderField = el('div', { class: 'field' }, el('span', { class: 'label', text: 'Order' }), this._orderSeg);
      this._chips = el('div', { class: 'chips' });
      this._itemsCount = el('span', { class: 'muted' });
      this._clearBtn = el('button', { class: 'btn text clear', text: 'Clear playlist', onclick: () => this._clearPlaylist() });
      this._itemsField = el('div', { class: 'field' }, el('span', { class: 'label', text: 'Patterns in the playlist' }), this._chips,
        el('div', { class: 'pl-foot' }, this._itemsCount, this._clearBtn));
      this._mixes = el('div', { class: 'mixes' });
      this._mixField = el('div', { class: 'field', hidden: true }, el('span', { class: 'label', text: 'Load a mix' }), this._mixes);
      this._plMissing = el('p', { class: 'missing-note', hidden: true });
      this._playlistCard = el('section', { class: 'card playlist' },
        el('div', { class: 'pl-head' }, el('h2', { text: 'Playlist' }), this._plSwitch),
        this._plStatus, this._plMissing, this._intervalField, this._orderField, this._itemsField, this._mixField);

      // Gallery card
      this._galCount = el('span', { class: 'muted' });
      this._gallery = el('div', { class: 'gallery' });
      this._galEmpty = el('p', { class: 'gal-empty', text: 'Waiting for Home Assistant.' });
      this._filter = el('input', {
        type: 'search', class: 'gal-filter', placeholder: 'Filter saved patterns', 'aria-label': 'Filter saved patterns',
        oninput: () => this._applyFilter(),
      });
      const galleryCard = el('section', { class: 'card gallery-card' },
        el('div', { class: 'gal-head' }, el('h2', {}, 'Saved patterns ', this._galCount),
          el('button', { class: 'btn text refresh', html: `${ICON.refresh}<span>Refresh</span>`, onclick: () => this._refreshGallery() })),
        this._filter, this._gallery, this._galEmpty);

      this._page = el('div', { class: 'page' },
        el('div', { class: 'grid' },
          el('div', { class: 'col col-editor' }, previewCard, editorCard, saveCard),
          el('div', { class: 'col col-side' }, this._playlistCard, galleryCard)));

      this._toast = el('div', { class: 'toast', role: 'status', 'aria-live': 'polite' });
      root.append(el('div', { class: 'layout' }, this._header, this._page), this._toast);

      this._mainStrip = new StripView(this._mainCanvas, STRIP_PIXELS, { multiRow: true });
      this._io = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          const card = this._cards.get(entry.target.dataset.id);
          if (!card) continue;
          card.visible = entry.isIntersecting;
          if (card.visible) this._ensureConfig(card.id).catch(() => {});
        }
      }, { rootMargin: '200px 0px' });

      this._renderSwatches();
      this._renderEffects();
      this._renderMeta();
      this._updateMenuButton();
      if (this._hass) this._hassChanged(null, this._hass);
    }

    // hass updates: touch only what changed -----------------------------------
    _hassChanged(old, hass) {
      if (!hass) return;
      this.toggleAttribute('dark',!!hass.themes?.darkMode);
      this._refreshData();
    }

    _updateMenuButton() {
      const Ctor = customElements.get('ha-menu-button');
      const show = this._narrow && !!Ctor;
      if (show && !this._menuBtn) {
        this._menuBtn = document.createElement('ha-menu-button');
        this._menuSlot.append(this._menuBtn);
      }
      if (this._menuBtn) {
        this._menuBtn.hass = this._hass;
        this._menuBtn.narrow = this._narrow;
        this._menuBtn.hidden = !show;
      }
      this._header.classList.toggle('has-menu', show);
      if (!Ctor && this._narrow && customElements.whenDefined && !this._menuWait) {
        this._menuWait = true;
        customElements.whenDefined('ha-menu-button').then(() => this._updateMenuButton());
      }
    }

    // Animation loop -----------------------------------------------------------
    _syncLoop() {
      const run = this.isConnected && !document.hidden;
      if (run && !this._raf) this._raf = requestAnimationFrame(this._tick);
      else if (!run && this._raf) { cancelAnimationFrame(this._raf); this._raf = 0; }
    }

    _tick(ts) {
      this._raf = requestAnimationFrame(this._tick);
      this._frame++;
      const ed = this._editor;
      const px = renderFrame(ed.colors, ed.effects, ts, STRIP_PIXELS, 1);
      this._mainStrip.draw(px);
      if (this._frame % 10 === 0) {
        let r = 0; let g = 0; let b = 0;
        for (const p of px) { r += p[0]; g += p[1]; b += p[2]; }
        const k = px.length || 1;
        const boost = (v) => Math.min(255, Math.round((v / k) * 1.6));
        this._housing.style.setProperty('--glow', `${boost(r)}, ${boost(g)}, ${boost(b)}`);
      }
      for (const card of this._cards.values()) {
        if (!card.visible || !card.parsed || card.hiddenByFilter) continue;
        if (this._reducedMotion && card.drawn) continue;
        card.strip.draw(renderFrame(card.parsed.colors, card.parsed.effects, this._reducedMotion ? 1500 : ts, MINI_PIXELS, card.seed));
        card.drawn = true;
      }
    }

    // Editor rendering ---------------------------------------------------------
    _renderSwatches(focusIndex) {
      const ed = this._editor;
      const list = this._swatches;
      list.textContent = '';
      ed.colors.forEach((hex, i) => {
        const hexLabel = el('span', { class: 'swatch-hex', text: `#${hex}` });
        hexLabel.style.color = readableOn(hex);
        const input = el('input', {
          type: 'color', value: `#${hex.toLowerCase()}`, 'aria-label': `Color ${i + 1}`,
          oninput: (e) => {
            const v = normHex(e.target.value);
            if (!v) return;
            ed.colors[i] = v;
            colorBox.style.background = `#${v}`;
            hexLabel.textContent = `#${v}`;
            hexLabel.style.color = readableOn(v);
            this._markDirty();
          },
        });
        const colorBox = el('label', { class: 'swatch-color' }, input, hexLabel);
        colorBox.style.background = `#${hex}`;
        const grip = el('button', {
          class: 'icon-btn grip', html: ICON.grip, 'aria-label': `Move color ${i + 1}. Drag, or use the arrow keys.`,
          onkeydown: (e) => {
            const dir = e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : 0;
            if (!dir) return;
            e.preventDefault();
            this._moveColor(i, i + dir, true);
          },
        });
        grip.addEventListener('pointerdown', (e) => this._dragStart(e, i, tile, grip));
        const remove = el('button', {
          class: 'icon-btn swatch-remove', html: ICON.close, 'aria-label': `Remove color ${i + 1}`,
          disabled: ed.colors.length <= 1,
          onclick: () => { ed.colors.splice(i, 1); this._markDirty(); this._renderSwatches(); },
        });
        const tile = el('div', { class: 'swatch', role: 'listitem', 'data-index': String(i) }, colorBox,
          el('div', { class: 'swatch-tools' }, grip, remove));
        list.append(tile);
        if (focusIndex === i) grip.focus();
      });
      const add = el('button', {
        class: 'add-swatch', html: `${ICON.plus}<span>Add color</span>`, disabled: ed.colors.length >= MAX_COLORS,
        onclick: () => {
          if (ed.colors.length >= MAX_COLORS) return;
          ed.colors.push(nextColor(ed.colors[ed.colors.length - 1]));
          this._markDirty();
          this._renderSwatches();
        },
      });
      list.append(add);
      this._colorCount.textContent = `${ed.colors.length} of ${MAX_COLORS}`;
      this._renderMeta();
    }

    _moveColor(from, to, focus) {
      const c = this._editor.colors;
      if (to < 0 || to >= c.length || from === to) return;
      const [v] = c.splice(from, 1);
      c.splice(to, 0, v);
      this._markDirty();
      this._renderSwatches(focus ? to : undefined);
    }

    _dragStart(e, index, tile, grip) {
      if (e.button > 0) return;
      e.preventDefault();
      try { grip.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
      const tiles = [...this._swatches.querySelectorAll('.swatch')];
      const rects = tiles.map((t) => t.getBoundingClientRect());
      const st = { x: e.clientX, y: e.clientY, moved: false, pos: index };
      const clearMarks = () => tiles.forEach((t) => t.classList.remove('drop-before', 'drop-after'));
      const move = (ev) => {
        const dx = ev.clientX - st.x;
        const dy = ev.clientY - st.y;
        if (!st.moved && Math.hypot(dx, dy) < 4) return;
        st.moved = true;
        tile.classList.add('dragging');
        tile.style.transform = `translate(${dx}px, ${dy}px)`;
        let best = 0;
        let bestD = Infinity;
        rects.forEach((r, i) => {
          const d = Math.hypot(ev.clientX - (r.left + r.width / 2), ev.clientY - (r.top + r.height / 2));
          if (d < bestD) { bestD = d; best = i; }
        });
        const r = rects[best];
        st.pos = ev.clientX > r.left + r.width / 2 ? best + 1 : best;
        clearMarks();
        if (st.pos !== index && st.pos !== index + 1) {
          if (st.pos < tiles.length) tiles[st.pos].classList.add('drop-before');
          else tiles[tiles.length - 1].classList.add('drop-after');
        }
      };
      const end = (ev) => {
        grip.removeEventListener('pointermove', move);
        grip.removeEventListener('pointerup', end);
        grip.removeEventListener('pointercancel', end);
        clearMarks();
        tile.classList.remove('dragging');
        tile.style.transform = '';
        if (ev.type === 'pointerup' && st.moved) {
          const to = st.pos > index ? st.pos - 1 : st.pos;
          if (to !== index) this._moveColor(index, to, false);
        }
      };
      grip.addEventListener('pointermove', move);
      grip.addEventListener('pointerup', end);
      grip.addEventListener('pointercancel', end);
    }

    _renderEffects() {
      const ed = this._editor;
      this._fxList.textContent = '';
      if (!ed.effects.length) {
        this._fxList.append(el('p', { class: 'fx-empty', text: 'No effects. The colors hold still as a solid pattern.' }));
      }
      ed.effects.forEach((fx, i) => {
        const select = el('select', {
          'aria-label': `Effect ${i + 1} type`,
          onchange: (e) => { fx.effectType = e.target.value; this._markDirty(); },
        }, EFFECT_TYPES.map((t) => el('option', { value: t, text: EFFECT_LABELS[t] })));
        select.value = fx.effectType;
        const num = el('input', { type: 'number', min: '0', max: '255', step: '1', value: String(fx.value), 'aria-label': `Effect ${i + 1} value` });
        const range = el('input', { type: 'range', min: '0', max: '255', step: '1', value: String(fx.value), 'aria-label': `Effect ${i + 1} speed or intensity` });
        range.addEventListener('input', () => { fx.value = Number(range.value); num.value = range.value; this._markDirty(); });
        num.addEventListener('input', () => {
          if (num.value === '') return;
          fx.value = clamp(Math.round(Number(num.value) || 0), 0, 255);
          range.value = String(fx.value);
          this._markDirty();
        });
        num.addEventListener('change', () => { num.value = String(fx.value); });
        const remove = el('button', {
          class: 'icon-btn fx-remove', html: ICON.close, 'aria-label': `Remove effect ${i + 1}`,
          onclick: () => { ed.effects.splice(i, 1); this._markDirty(); this._renderEffects(); },
        });
        this._fxList.append(el('div', { class: 'fx-row' }, select, range, num, remove));
      });
    }

    _addEffect() {
      const used = new Set(this._editor.effects.map((e) => e.effectType));
      const type = EFFECT_TYPES.find((t) => !used.has(t)) || 'fade';
      this._editor.effects.push({ effectType: type, value: 100 });
      this._markDirty();
      this._renderEffects();
      const rows = this._fxList.querySelectorAll('select');
      if (rows.length) rows[rows.length - 1].focus();
    }

    _markDirty() {
      this._editor.dirty = true;
      this._saveDraft();
      this._renderMeta();
    }

    _renderMeta() {
      if (!this._built) return;
      const ed = this._editor;
      this._edTitle.textContent = ed.loadedId ? this._nameFor(ed.loadedId) : 'New pattern';
      this._dirtyEl.hidden = !ed.dirty;
      this._stripMeta.textContent = `${STRIP_PIXELS} pixels · ${ed.colors.length} colors`;
      if (this.shadowRoot.activeElement !== this._nameInput) this._nameInput.value = ed.name;
      this._saveBtn.disabled = !ed.name.trim();
      this._saveNewBtn.hidden = true;
      this._deleteBtn.hidden = !ed.loadedId;
      this._slugHint.textContent = 'Saved on the selected bridge. Matching names update an existing pattern.';
    }

    _newPattern() {
      this._confirmDiscard().then((ok) => {
        if (!ok) return;
        this._setEditor({ colors: DEFAULT_PATTERN.colors.slice(), effects: DEFAULT_PATTERN.effects.map((e) => ({ ...e })), name: '', loadedId: null });
      });
    }

    _setEditor({ colors, effects, name, loadedId }) {
      this._editor = { colors: colors.slice(0, MAX_COLORS), effects: effects.map((e) => ({ ...e })), name: name || '', loadedId: loadedId || null, dirty: false };
      this._nameInput.value = this._editor.name;
      this._saveDraft();
      this._renderSwatches();
      this._renderEffects();
      this._renderMeta();
    }

    _confirmDiscard() {
      if (!this._editor.dirty) return Promise.resolve(true);
      return this._confirm({ title: 'Discard unsaved changes?', body: 'The pattern in the editor has changes that are not saved.', confirm: 'Discard' });
    }

    _loadDraft() {
      const raw = storageGet('sessionStorage', DRAFT_KEY);
      if (!raw) return null;
      try {
        const d = JSON.parse(raw);
        const colors = (d.colors || []).map(normHex).filter(Boolean).slice(0, MAX_COLORS);
        if (!colors.length) return null;
        return { colors, effects: cleanEffects(d.effects), name: String(d.name || ''), loadedId: d.loadedId || null, dirty: !!d.dirty };
      } catch (_) { return null; }
    }

    _saveDraft() {
      storageSet('sessionStorage', DRAFT_KEY, JSON.stringify(this._editor));
    }

    _nameFor(id) { return this._configs.get(id)?.config?.alias || id; }
    async _call(service, data = {}) {
      if (!this._zonePicker.value) throw new Error('Choose a zone first');
      return this._hass.callService('everlights_v3', service, data, {entity_id: this._zonePicker.value});
    }
    _effects() { return this._editor.effects.map(e => ({type:e.effectType, value:e.value})); }
    async _action(fn) { try { await fn(); } catch(e) { this._showToast(errMessage(e), true); } }
    async _send() { await this._action(async () => { await this._call('set_pattern', {colors:this._editor.colors, effects:this._effects(), brightness:Number(this._brightnessInput.value), alias:this._editor.name || 'Home Assistant'}); this._showToast('Pattern sent'); }); }
    async _save() { await this._action(async () => {
      await this._call('save_preset', {name:this._editor.name, colors:this._editor.colors, effects:this._effects()});
      this._editor.dirty=false; await this._refreshGallery(); this._renderMeta(); this._showToast('Pattern saved');
    }); }
    async _loadPattern(id) {
      if (!await this._confirmDiscard()) return;
      const p=this._configs.get(id)?.config;
      if (p) this._setEditor({colors:p.pattern || ['000000'], effects:cleanEffects(p.effects), name:p.alias, loadedId:id});
    }
    async _delete() { await this._action(async () => {
      if (!await this._confirm({title:'Delete pattern?',body:'This removes the saved pattern from the bridge.',confirm:'Delete'})) return;
      await this._call('delete_preset',{preset:this._editor.loadedId});
      this._editor.loadedId=null; await this._refreshGallery(); this._renderMeta();
    }); }
    async _refreshGallery() { await this._refreshData(true); }
    async _refreshData(force=false) {
      if (!this._hass || this._loading) return;
      this._loading=true;
      try {
        this._zones=await this._hass.callWS({type:'everlights_v3/zones'});
        const selected=this._zonePicker.value;
        this._zonePicker.replaceChildren(...this._zones.map(z=>el('option',{value:z.entity_id,text:z.name})));
        if (this._zones.some(z=>z.entity_id===selected)) this._zonePicker.value=selected;
        const zone=this._zones.find(z=>z.entity_id===this._zonePicker.value);
        const entry=zone?.entry_id;
        if (entry && (force || entry!==this._entryId)) {
          this._entryId=entry;
          const presets=await this._hass.callWS({type:'everlights_v3/presets',entry_id:entry});
          for (const c of this._cards.values()) { this._io.unobserve(c.el); c.strip.destroy(); }
          this._cards.clear(); this._configs.clear(); this._gallery.replaceChildren();
          for (const p of presets.filter(p=>!p.builtin)) {
            this._configs.set(p.id,{status:'ok',config:p,parsed:{colors:p.pattern || [],effects:cleanEffects(p.effects)}});
            const c=this._createCard(p.id); c.nameEl.textContent=p.alias; this._gallery.append(c.el);
          }
          this._galCount.textContent=String(this._cards.size);
          this._galEmpty.hidden=!!this._cards.size; this._galEmpty.textContent='No saved patterns yet.';
          this._applyFilter();
        }
        if (zone) { this._playlistState=zone.playlist; this._updatePlaylist(); }
      } catch(e) { this._showToast(errMessage(e),true); }
      finally { this._loading=false; }
    }
    _createCard(id) {
      const canvas = el('canvas', { 'aria-hidden': 'true' });
      const skeleton = el('div', { class: 'skeleton' });
      const nameEl = el('span', { class: 'pname' });
      const sumEl = el('span', { class: 'psum', text: '' });
      const loadBtn = el('button', { class: 'load', onclick: () => this._loadPattern(id) },
        el('div', { class: 'mini' }, canvas, skeleton), nameEl, sumEl);
      const runBtn = el('button', { class: 'btn run', html: `${ICON.play}<span>Run</span>`, onclick: () => this._runSaved(id, runBtn) });
      const addBtn = el('button', { class: 'btn add-playlist', html: `${ICON.plus}<span>Playlist</span>`, onclick: () => this._addToPlaylist(id) });
      const cardEl = el('div', { class: 'pcard', 'data-id': id }, loadBtn, el('div', { class: 'pactions' }, runBtn, addBtn));
      const card = {
        id, el: cardEl, canvas, skeleton, nameEl, sumEl, loadBtn, runBtn, addBtn,
        strip: new StripView(canvas, MINI_PIXELS, { multiRow: false }),
        seed: hashString(id), visible: false, parsed: null, drawn: false, hiddenByFilter: false,
      };
      this._cards.set(id, card);
      this._io.observe(cardEl);
      const cached = this._configs.get(id);
      if (cached && cached.status !== 'loading') this._applyConfigToCard(card);
      return card;
    }


    _ensureConfig(id) { return Promise.resolve(this._configs.get(id)); }
    _applyConfigToCard(card) {
      const entry=this._configs.get(card.id);
      card.parsed=entry.parsed; card.skeleton.hidden=true;
      card.sumEl.textContent=effectSummary(entry.parsed.effects);
    }
    _applyFilter() {
      const query=this._filter.value.toLowerCase();
      for (const card of this._cards.values()) { card.hiddenByFilter=!this._nameFor(card.id).toLowerCase().includes(query); card.el.hidden=card.hiddenByFilter; }
    }
    async _runSaved(id) { await this._action(()=>this._call('play_preset',{preset:id})); }
    _updatePlaylist() {
      const p=this._playlistState || {running:false,presets:[],interval:60};
      this._plSwitch.setAttribute('aria-checked',String(p.running));
      this._plStatus.textContent=p.running ? 'Running' : 'Stopped';
      if (!this._playlistEdited) { this._playlistDraft=[...p.presets]; this._shuffle=!!p.shuffle; }
      if (!this._intervalEdited) { this._ivMin.value=String(Math.floor(p.interval/60)); this._ivSec.value=String(p.interval%60); }
      this._ivRange.textContent='5 seconds to 24 hours';
      this._orderSeg.replaceChildren(el('button',{class:'btn',text:this._shuffle?'Shuffle':'In order',onclick:()=>{this._playlistEdited=true;this._shuffle=!this._shuffle;this._updatePlaylist();}}));
      this._chips.replaceChildren(...this._playlistDraft.map((id,i)=>el('button',{class:'chip',text:`${this._nameFor(id)} ×`,onclick:()=>this._removeFromPlaylist(i)})));
      this._itemsCount.textContent=String(this._playlistDraft.length);
    }
    async _addToPlaylist(id) { this._playlistEdited=true; this._playlistDraft ||= []; this._playlistDraft.push(id); this._updatePlaylist(); }
    async _removeFromPlaylist(i) { this._playlistEdited=true; this._playlistDraft.splice(i,1); this._updatePlaylist(); }
    async _togglePlaylist() { await this._action(async()=>{
      if (this._playlistState?.running) await this._call('stop_playlist');
      else await this._call('start_playlist',{presets:this._playlistDraft || [],interval:this._interval(),shuffle:!!this._shuffle});
      this._playlistEdited=false; this._intervalEdited=false;
      await this._refreshData();
    }); }
    _interval() { return clamp(Number(this._ivMin.value)*60+Number(this._ivSec.value),5,86400); }
    _setInterval() { this._intervalEdited=true; }
    async _clearPlaylist() { await this._action(async()=>{await this._call('stop_playlist');this._playlistEdited=true;this._playlistDraft=[];await this._refreshData();}); }

    // Dialog + toast -----------------------------------------------------------
    _confirm({ title, body, confirm = 'OK', cancel = 'Cancel', danger = false }) {
      return new Promise((resolve) => {
        const prevFocus = this.shadowRoot.activeElement;
        const done = (v) => {
          scrim.remove();
          document.removeEventListener('keydown', onKey, true);
          if (prevFocus && prevFocus.isConnected) prevFocus.focus();
          resolve(v);
        };
        const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); done(false); } };
        const okBtn = el('button', { class: `btn ${danger ? 'danger solid' : 'primary'} confirm-ok`, text: confirm, onclick: () => done(true) });
        const dialog = el('div', { class: 'dialog', role: 'alertdialog', 'aria-modal': 'true', 'aria-labelledby': 'dlg-title', 'aria-describedby': 'dlg-body' },
          el('h2', { id: 'dlg-title', text: title }),
          el('p', { id: 'dlg-body', text: body }),
          el('div', { class: 'row' }, el('button', { class: 'btn text confirm-cancel', text: cancel, onclick: () => done(false) }), okBtn));
        const scrim = el('div', { class: 'scrim', onclick: (e) => { if (e.target === scrim) done(false); } }, dialog);
        this.shadowRoot.append(scrim);
        document.addEventListener('keydown', onKey, true);
        okBtn.focus();
      });
    }

    _showToast(message, isError) {
      const t = this._toast;
      t.textContent = message;
      t.classList.toggle('error', !!isError);
      t.setAttribute('role', isError ? 'alert' : 'status');
      t.classList.add('show');
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => t.classList.remove('show'), isError ? 7000 : 3500);
    }
  }

  if (!customElements.get('everlights-panel')) customElements.define('everlights-panel', EverLightsPanel);
})();
