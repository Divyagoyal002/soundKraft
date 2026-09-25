/* SoundKraft shared browser helpers: API, settings, audio, speech and the trial recorder. */
(function () {
  "use strict";

  const SK = (window.SK = {});

  SK.sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  SK.api = async function (method, url, body) {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch (e) { /* not JSON */ }
      throw new Error(`${res.status}: ${detail}`);
    }
    return res.json();
  };

  SK.el = function (tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") node.className = v;
      else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const c of children.flat()) if (c != null) node.append(c);
    return node;
  };

  /* ---------------------------------------------------------------- settings */

  SK.settings = {};
  SK.applySettings = function (s) {
    SK.settings = Object.assign({}, SK.settings, s || {});
    const b = document.body;
    b.style.setProperty("--text-scale", SK.settings.text_scale || 1.25);
    b.style.setProperty("--target-scale", SK.settings.target_scale || 1);
    b.classList.toggle("contrast-high", SK.settings.contrast === "high");
  };

  /* ---------------------------------------------------------------- audio */

  let ctx = null;
  function audioCtx() {
    if (!ctx) {
      const AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }

  function tone(freq, start, dur, gain) {
    const c = audioCtx();
    if (!c) return;
    const osc = c.createOscillator();
    const g = c.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    const t = c.currentTime + start;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g).connect(c.destination);
    osc.start(t);
    osc.stop(t + dur + 0.05);
  }

  SK.sound = {
    unlock() { audioCtx(); },
    test() { tone(523, 0, 0.35, 0.3); tone(784, 0.35, 0.5, 0.3); },
    good() { if (SK.settings.audio_cues) { tone(660, 0, 0.12, 0.2); tone(880, 0.1, 0.18, 0.2); } },
    bad() { if (SK.settings.audio_cues) tone(220, 0, 0.25, 0.15); },
    blip(i) { if (SK.settings.audio_cues) tone(392 + 40 * (i % 8), 0, 0.2, 0.15); },
    fanfare() { if (SK.settings.audio_cues) [523, 659, 784, 1047].forEach((f, i) => tone(f, i * 0.12, 0.25, 0.2)); },
  };

  SK.speak = function (text, force) {
    if (!("speechSynthesis" in window)) return;
    if (!force && !SK.settings.spoken_instructions) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.85;
    window.speechSynthesis.speak(u);
  };

  /* ---------------------------------------------------------------- trial recorder
     Records timing and touch dynamics for one trial:
       rt_ms            stimulus onset -> committed response
       first_touch_ms   stimulus onset -> first touch anywhere (decision latency / hesitation)
       tap_duration_ms  finger down -> finger up for the committing touch
       swipe_ms/px      duration and distance of a committing swipe
       touch_x/y        committing touch position, normalised 0..1 within the stage
       off_target       touches that missed every target                           */

  SK.recorder = function (root) {
    const t0 = performance.now();
    let firstTouch = null, downAt = null, tapDuration = null, off = 0, xy = [null, null];
    const rect = () => root.getBoundingClientRect();
    function down(e) {
      const t = performance.now();
      if (firstTouch === null) firstTouch = t - t0;
      downAt = t;
      const r = rect();
      xy = [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height];
    }
    function up() {
      if (downAt !== null) { tapDuration = performance.now() - downAt; downAt = null; }
    }
    root.addEventListener("pointerdown", down, true);
    root.addEventListener("pointerup", up, true);
    return {
      t0,
      offTarget() { off += 1; },
      elapsed() { return performance.now() - t0; },
      finish(extra) {
        root.removeEventListener("pointerdown", down, true);
        root.removeEventListener("pointerup", up, true);
        const timedOut = !!(extra && extra.timed_out);
        const round = (v) => (v == null ? null : Math.round(v * 10) / 10);
        return Object.assign({
          rt_ms: timedOut ? null : round(performance.now() - t0),
          first_touch_ms: round(firstTouch),
          tap_duration_ms: round(tapDuration),
          swipe_ms: null,
          swipe_px: null,
          touch_x: xy[0] == null ? null : Math.round(xy[0] * 1000) / 1000,
          touch_y: xy[1] == null ? null : Math.round(xy[1] * 1000) / 1000,
          off_target_touches: off,
          input_mode: SK.settings.input_mode,
          timed_out: timedOut,
          response: null,
          error_type: null,
        }, extra || {});
      },
    };
  };

  /* Resolve with the first of several promises, or {timed_out:true} after ms. */
  SK.withTimeout = function (promise, ms) {
    let timer;
    return Promise.race([
      promise,
      new Promise((r) => { timer = setTimeout(() => r({ timed_out: true }), ms); }),
    ]).finally(() => clearTimeout(timer));
  };

  SK.flash = async function (node, good) {
    node.classList.add(good ? "flash-good" : "flash-bad");
    await SK.sleep(350);
    node.classList.remove("flash-good", "flash-bad");
  };
})();
