/* Kitchen Memory - N-back working memory. Answer by swiping the dish card or pressing buttons. */
(function () {
  "use strict";
  const SWIPE_MIN_PX = 80;     // committed swipe
  const SWIPE_UNCLEAR_PX = 25; // movement that looks like an attempted swipe

  async function run(cfg, ctx) {
    const { stage } = ctx;
    const trials = [];
    const card = SK.el("div", { class: "big-item", role: "img" });
    const label = SK.el("p", { class: "lead", "aria-live": "polite" });
    const hint = SK.el("p", { class: "hint" });
    const same = SK.el("button", { class: "btn btn-primary", type: "button" }, "✓ Same");
    const diff = SK.el("button", { class: "btn", type: "button" }, "✗ Different");
    const buttons = SK.el("div", { class: "answer-row" }, diff, same);
    const switchBtn = SK.el("button", { class: "btn", type: "button" }, "Use buttons instead");
    stage.replaceChildren(label, card, buttons, hint, switchBtn);

    function layout() {
      const swipe = SK.settings.input_mode === "swipe";
      buttons.hidden = swipe;
      switchBtn.hidden = !swipe;
      hint.textContent = swipe ? "Swipe right → Same    ·    Swipe left ← Different" : "";
    }
    switchBtn.addEventListener("click", async () => {
      SK.applySettings({ input_mode: "tap" });
      layout();
      try { await SK.api("PUT", `/api/users/${ctx.userId}/settings`, { input_mode: "tap" }); } catch (e) { /* keep playing */ }
    });
    layout();

    for (let i = 0; i < cfg.trials.length; i++) {
      const stim = cfg.trials[i];
      card.textContent = stim.item;
      card.setAttribute("aria-label", stim.name);
      card.classList.remove("gone");
      card.style.transform = "";

      if (!stim.scored) {
        // The first n dishes have nothing to compare against: just remember them.
        label.textContent = i === 0 ? "Remember this dish" : "And remember this one";
        buttons.style.visibility = "hidden";
        await SK.sleep(Math.max(1500, cfg.isi_ms * 3));
        trials.push({ response: null, timed_out: false, rt_ms: null, input_mode: SK.settings.input_mode });
        card.classList.add("gone");
        await SK.sleep(cfg.isi_ms);
        continue;
      }
      buttons.style.visibility = "";
      label.textContent = cfg.n === 1 ? "Same as the last one?" : `Same as ${cfg.n} dishes ago?`;

      const rec = SK.recorder(stage);
      let unclear = 0;
      const answer = new Promise((resolve) => {
        const cleanup = [];
        const done = (v) => { cleanup.forEach((f) => f()); resolve(v); };
        const on = (node, ev, fn) => { node.addEventListener(ev, fn); cleanup.push(() => node.removeEventListener(ev, fn)); };
        on(same, "click", () => done({ response: "same" }));
        on(diff, "click", () => done({ response: "different" }));

        let start = null;
        on(card, "pointerdown", (e) => {
          if (SK.settings.input_mode !== "swipe") return;
          start = { x: e.clientX, y: e.clientY, t: performance.now() };
          card.setPointerCapture(e.pointerId);
        });
        on(card, "pointermove", (e) => {
          if (start) card.style.transform = `translateX(${e.clientX - start.x}px) rotate(${(e.clientX - start.x) / 20}deg)`;
        });
        on(card, "pointerup", (e) => {
          if (!start) return;
          const dx = e.clientX - start.x, dy = e.clientY - start.y;
          const swipe_ms = Math.round(performance.now() - start.t);
          const swipe_px = Math.round(Math.hypot(dx, dy));
          start = null;
          if (Math.abs(dx) >= SWIPE_MIN_PX && Math.abs(dx) > Math.abs(dy)) {
            done({ response: dx > 0 ? "same" : "different", swipe_ms, swipe_px });
          } else {
            card.style.transform = "";
            if (swipe_px >= SWIPE_UNCLEAR_PX) unclear += 1;
          }
        });
        on(stage, "pointerdown", (e) => {
          if (!card.contains(e.target) && !buttons.contains(e.target) && e.target !== switchBtn) rec.offTarget();
        });
      });

      const result = await SK.withTimeout(answer, cfg.response_window_ms);
      const trial = rec.finish(result);
      if (unclear) trial.error_type = "swipe_unclear"; // lets the sensory controller offer buttons
      trials.push(trial);

      const good = !trial.timed_out && trial.response === stim.answer;
      if (good) { SK.sound.good(); ctx.addPoints(10); } else SK.sound.bad();
      await SK.flash(card, good);
      card.classList.add("gone");
      await SK.sleep(cfg.isi_ms);
    }
    return trials;
  }

  function demo() {
    return "🍎 → 🍎  = Same      🍎 → 🥕  = Different";
  }

  (window.SKGames = window.SKGames || {}).nback = { run, demo };
})();
