/* First-run sensory profile: text size, contrast, hearing check and a swipe test. */
(function () {
  "use strict";
  const root = document.getElementById("setup");
  const userId = Number(root.dataset.user);
  const chosen = {};
  SK.applySettings(JSON.parse(root.dataset.settings));

  let step = 1;
  function go(n) {
    step = n;
    for (const s of root.querySelectorAll(".setup-step")) s.hidden = Number(s.dataset.step) !== n;
    document.getElementById("step-no").textContent = Math.min(n, 4);
    window.scrollTo(0, 0);
    if (n === 5) save();
  }

  async function save() {
    try { await SK.api("PUT", `/api/users/${userId}/settings`, chosen); } catch (e) { console.error(e); }
  }

  root.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-set]");
    if (!btn) return;
    const key = btn.dataset.set, value = btn.dataset.value;
    if (key === "text_scale") { chosen.text_scale = Number(value); SK.applySettings({ text_scale: chosen.text_scale }); go(2); }
    else if (key === "contrast") { chosen.contrast = value; SK.applySettings({ contrast: value }); go(3); }
    else if (key === "sound") {
      const heard = value === "yes";
      chosen.audio_cues = heard;
      chosen.spoken_instructions = heard;
      SK.applySettings({ audio_cues: heard, spoken_instructions: heard });
      go(4);
    } else if (key === "input_mode") { chosen.input_mode = value; go(5); }
  });

  document.getElementById("play-sound").addEventListener("click", () => {
    SK.sound.test();
    SK.speak("Hello! Can you hear me?", true);
  });

  // Swipe test: a successful drag to the right keeps swipe mode; two failed tries switch to buttons.
  const card = document.getElementById("swipe-card");
  const box = document.getElementById("swipe-demo");
  const msg = document.getElementById("swipe-msg");
  let start = null, fails = 0;
  card.addEventListener("pointerdown", (e) => { start = e.clientX; card.setPointerCapture(e.pointerId); });
  card.addEventListener("pointermove", (e) => {
    if (start !== null) card.style.transform = `translateX(${Math.max(0, e.clientX - start)}px)`;
  });
  card.addEventListener("pointerup", (e) => {
    if (start === null) return;
    const dx = e.clientX - start;
    start = null;
    if (dx > Math.min(160, box.clientWidth * 0.4)) {
      msg.textContent = "Great swipe!";
      chosen.input_mode = "swipe";
      setTimeout(() => go(5), 700);
    } else {
      card.style.transform = "";
      fails += 1;
      msg.textContent = fails >= 2 ? "No problem – we'll use buttons instead." : "Nearly! Try sliding a bit further.";
      if (fails >= 2) { chosen.input_mode = "tap"; setTimeout(() => go(5), 1200); }
    }
  });

  go(1);
})();
