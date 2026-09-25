/* Colour Clash - Stroop attention task. Press the button for the INK colour, not the word. */
(function () {
  "use strict";

  async function run(cfg, ctx) {
    const { stage } = ctx;
    const trials = [];
    const word = SK.el("div", { class: "stroop-word", "aria-live": "polite" });
    const prompt = SK.el("p", { class: "lead" }, "What colour is the ink?");
    const grid = SK.el("div", { class: "colour-grid" });
    const buttons = cfg.palette.map((c) => {
      const b = SK.el("button", { class: "btn colour-btn", type: "button", "data-colour": c.name },
        SK.el("span", { class: "swatch", style: { background: c.hex } }),
        c.name.charAt(0) + c.name.slice(1).toLowerCase());
      grid.append(b);
      return b;
    });
    stage.replaceChildren(prompt, word, grid);

    for (const stim of cfg.trials) {
      word.textContent = "";
      await SK.sleep(cfg.isi_ms);
      word.textContent = stim.word;
      word.style.color = stim.ink;

      const rec = SK.recorder(stage);
      const cleanup = [];
      const answer = new Promise((resolve) => {
        for (const b of buttons) {
          const fn = () => resolve({ response: b.dataset.colour });
          b.addEventListener("click", fn);
          cleanup.push(() => b.removeEventListener("click", fn));
        }
        const miss = (e) => { if (!e.target.closest(".colour-btn")) rec.offTarget(); };
        stage.addEventListener("pointerdown", miss);
        cleanup.push(() => stage.removeEventListener("pointerdown", miss));
      });
      const result = await SK.withTimeout(answer, cfg.response_window_ms);
      cleanup.forEach((f) => f());
      const trial = rec.finish(result);
      trials.push(trial);

      const good = !trial.timed_out && trial.response === stim.answer;
      if (good) { SK.sound.good(); ctx.addPoints(10); } else SK.sound.bad();
      await SK.flash(grid, good);
    }
    word.textContent = "";
    return trials;
  }

  function demo() {
    return "The word BLUE in red ink → press Red";
  }

  (window.SKGames = window.SKGames || {}).stroop = { run, demo };
})();
