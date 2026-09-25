/* Garden Path - Corsi block spatial memory. Watch flowers light up, then tap them in the same order. */
(function () {
  "use strict";

  async function run(cfg, ctx) {
    const { stage } = ctx;
    const trials = [];
    const prompt = SK.el("p", { class: "lead", "aria-live": "polite" });
    const grid = SK.el("div", { class: "corsi-grid", style: { gridTemplateColumns: `repeat(${cfg.grid}, 1fr)` } });
    const tiles = [];
    for (let i = 0; i < cfg.grid * cfg.grid; i++) {
      const t = SK.el("button", { class: "tile", type: "button", "data-i": i, "aria-label": `Flower ${i + 1}` }, "🌼");
      tiles.push(t);
      grid.append(t);
    }
    stage.replaceChildren(prompt, grid);

    for (const stim of cfg.trials) {
      tiles.forEach((t) => { t.disabled = true; t.classList.remove("tapped", "lit"); });
      prompt.textContent = "Watch carefully…";
      await SK.sleep(900);
      for (let k = 0; k < stim.sequence.length; k++) {
        const t = tiles[stim.sequence[k]];
        t.classList.add("lit");
        SK.sound.blip(k);
        await SK.sleep(cfg.flash_ms);
        t.classList.remove("lit");
        await SK.sleep(cfg.gap_ms);
      }

      prompt.textContent = "Your turn!";
      tiles.forEach((t) => { t.disabled = false; });
      const rec = SK.recorder(stage);
      const taps = [];
      const cleanup = [];
      const answer = new Promise((resolve) => {
        for (const t of tiles) {
          const fn = () => {
            taps.push(Number(t.dataset.i));
            t.classList.add("tapped");
            SK.sound.blip(taps.length - 1);
            setTimeout(() => t.classList.remove("tapped"), 250);
            if (taps.length === stim.sequence.length) resolve({ response: taps.slice() });
          };
          t.addEventListener("click", fn);
          cleanup.push(() => t.removeEventListener("click", fn));
        }
        const miss = (e) => { if (!e.target.closest(".tile")) rec.offTarget(); };
        stage.addEventListener("pointerdown", miss);
        cleanup.push(() => stage.removeEventListener("pointerdown", miss));
      });
      const result = await SK.withTimeout(answer, cfg.response_window_ms);
      cleanup.forEach((f) => f());
      if (result.timed_out) result.response = taps.slice();
      const trial = rec.finish(result);
      trials.push(trial);

      const good = !trial.timed_out && taps.join(",") === stim.sequence.join(",");
      tiles.forEach((t) => { t.disabled = true; });
      if (good) { SK.sound.good(); ctx.addPoints(10); prompt.textContent = "Perfect!"; }
      else { SK.sound.bad(); prompt.textContent = "Not quite – let's try another."; }
      await SK.flash(grid, good);
      await SK.sleep(600);
    }
    return trials;
  }

  function demo() {
    return "🌼 ① → 🌼 ② → 🌼 ③  …then tap them in the same order";
  }

  (window.SKGames = window.SKGames || {}).corsi = { run, demo };
})();
