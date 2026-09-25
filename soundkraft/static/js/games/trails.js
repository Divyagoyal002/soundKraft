/* Trail Walk - Trail Making (A: 1-2-3…, B: 1-A-2-B…). Each step to the next circle is one trial.
   A step's response is the FIRST circle tapped, so a wrong first tap makes the step incorrect. */
(function () {
  "use strict";
  const SVG_NS = "http://www.w3.org/2000/svg";

  async function run(cfg, ctx) {
    const { stage } = ctx;
    const prompt = SK.el("p", { class: "lead", "aria-live": "polite" });
    const board = SK.el("div", { class: "trail-board" });
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.setAttribute("preserveAspectRatio", "none");
    board.append(svg);
    const dots = {};
    for (const t of cfg.targets) {
      const d = SK.el("button", { class: "trail-dot", type: "button", "data-label": t.label,
        style: { left: `${t.x * 100}%`, top: `${t.y * 100}%` } }, t.label);
      dots[t.label] = d;
      board.append(d);
    }
    stage.replaceChildren(prompt, board);

    const trials = [];
    const deadline = performance.now() + cfg.response_window_ms;
    let prev = null;

    for (let i = 0; i < cfg.trials.length; i++) {
      const want = cfg.trials[i].target;
      prompt.textContent = i === 0 ? `Start at ${want}` : `Next: ${want}`;
      const remaining = deadline - performance.now();
      if (remaining <= 0) {
        trials.push({ response: null, timed_out: true, off_target_touches: 0, wrong_taps: 0, input_mode: SK.settings.input_mode });
        continue;
      }
      const rec = SK.recorder(board);
      let first = null, wrong = 0;
      const cleanup = [];
      const answer = new Promise((resolve) => {
        const onTap = (e) => {
          const dot = e.target.closest(".trail-dot");
          if (!dot || dot.classList.contains("done")) { rec.offTarget(); return; }
          const label = dot.dataset.label;
          if (first === null) first = label;
          if (label === want) {
            resolve({ response: first });
          } else {
            wrong += 1; // a thinking error (wrong circle), not a motor miss
            SK.sound.bad();
            dot.classList.remove("wrong");
            void dot.offsetWidth;
            dot.classList.add("wrong");
            setTimeout(() => dot.classList.remove("wrong"), 400);
          }
        };
        board.addEventListener("click", onTap);
        cleanup.push(() => board.removeEventListener("click", onTap));
      });
      const result = await SK.withTimeout(answer, remaining);
      cleanup.forEach((f) => f());
      if (result.timed_out) result.response = first;
      result.wrong_taps = wrong;
      const trial = rec.finish(result);
      trials.push(trial);
      if (result.timed_out) continue;

      const dot = dots[want];
      dot.classList.add("done");
      if (trial.response === want) ctx.addPoints(5);
      SK.sound.blip(i);
      if (prev) {
        const a = cfg.targets.find((t) => t.label === prev), b = cfg.targets.find((t) => t.label === want);
        const line = document.createElementNS(SVG_NS, "line");
        line.setAttribute("x1", a.x * 100); line.setAttribute("y1", a.y * 100);
        line.setAttribute("x2", b.x * 100); line.setAttribute("y2", b.y * 100);
        line.setAttribute("vector-effect", "non-scaling-stroke");
        svg.append(line);
      }
      prev = want;
    }
    prompt.textContent = trials.some((t) => t.timed_out) ? "Time's up – well done for trying!" : "Trail complete!";
    SK.sound.good();
    await SK.sleep(900);
    return trials;
  }

  function demo() {
    return "① → Ⓐ → ② → Ⓑ → ③ …";
  }

  (window.SKGames = window.SKGames || {}).trails = { run, demo };
})();
