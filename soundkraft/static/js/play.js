/* Session controller: runs the daily battery round by round against the Python API. */
(function () {
  "use strict";
  const app = document.getElementById("app");
  const userId = Number(app.dataset.user);
  SK.applySettings(JSON.parse(app.dataset.settings));

  const $ = (id) => document.getElementById(id);
  function show(id) {
    for (const s of document.querySelectorAll(".screen")) s.hidden = s.id !== id;
    window.scrollTo(0, 0);
  }
  const click = (id) => new Promise((r) => $(id).addEventListener("click", r, { once: true }));

  let sessionPoints = 0;
  const ctx = {
    userId,
    stage: $("stage"),
    addPoints(n) { sessionPoints += n; $("hud-points").textContent = `${sessionPoints} pts`; },
  };

  async function runSession() {
    SK.sound.unlock();
    const session = await SK.api("POST", "/api/sessions", {
      user_id: userId,
      device: { ua: navigator.userAgent, w: screen.width, h: screen.height, touch: navigator.maxTouchPoints || 0 },
    });
    const battery = session.battery;

    for (let g = 0; g < battery.length; g++) {
      const game = battery[g];
      const rounds = session.rounds_per_game[game];
      for (let r = 0; r < rounds; r++) {
        const cfg = await SK.api("POST", `/api/sessions/${session.session_id}/rounds`, { game });
        SK.applySettings(cfg.settings);

        if (r === 0) {
          $("intro-progress").textContent = `Game ${g + 1} of ${battery.length}`;
          $("intro-title").textContent = cfg.title;
          $("intro-text").textContent = cfg.instructions;
          $("intro-demo").textContent = window.SKGames[game].demo();
          show("screen-intro");
          SK.speak(cfg.instructions);
          const speakBtn = $("intro-speak");
          const speak = () => SK.speak(cfg.instructions, true);
          speakBtn.addEventListener("click", speak);
          await click("intro-go");
          speakBtn.removeEventListener("click", speak);
          if ("speechSynthesis" in window) speechSynthesis.cancel();
        }

        $("hud-title").textContent = cfg.title;
        $("hud-round").textContent = `Round ${r + 1} of ${rounds} · Level ${cfg.level}`;
        show("screen-game");
        const trials = await window.SKGames[game].run(cfg, ctx);
        const res = await SK.api("POST", `/api/rounds/${cfg.round_id}/results`, { trials });

        $("round-heading").textContent = res.next_level > res.level ? "Level up!" : "Well done!";
        $("round-stars").textContent = "★".repeat(res.stars) + "☆".repeat(3 - res.stars);
        $("round-stars").setAttribute("aria-label", `${res.stars} of 3 stars`);
        $("round-points").textContent = `+${res.points} points`;
        const adapt = $("round-adapt");
        adapt.hidden = !res.adaptations.length;
        adapt.textContent = res.adaptations.map((a) => a.message).join(" ");
        if (res.next_level > res.level) SK.sound.fanfare();
        show("screen-round");
        await click("round-next");
      }
    }

    const done = await SK.api("POST", `/api/sessions/${session.session_id}/finish`);
    $("done-points").textContent = `You earned ${done.points} points today · ${done.total_points} in total.`;
    SK.sound.fanfare();
    show("screen-done");
  }

  $("start-session").addEventListener("click", () => {
    runSession().catch((err) => {
      console.error(err);
      $("error-text").textContent = err.message;
      show("screen-error");
    });
  });
})();
