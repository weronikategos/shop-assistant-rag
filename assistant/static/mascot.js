// Benny, the shop's coffee bean. One SVG drawing; CSS classes on the wrapper switch his mood:
// "waving", "thinking", "searching", "happy" and "sad". Without a class he just breathes and blinks.

let mascotCount = 0;

function mascotSvg() {
  const id = `bean-${++mascotCount}`;
  return `
<svg class="mascot-svg" viewBox="0 0 120 140" aria-hidden="true">
  <defs>
    <radialGradient id="${id}-skin" cx="38%" cy="30%" r="75%">
      <stop offset="0" stop-color="#a4724c"/>
      <stop offset="0.6" stop-color="#7a4f33"/>
      <stop offset="1" stop-color="#55361f"/>
    </radialGradient>
  </defs>

  <ellipse class="shadow" cx="60" cy="133" rx="30" ry="4"/>

  <g class="thought">
    <circle cx="96" cy="26" r="3"/>
    <circle cx="104" cy="15" r="4.5"/>
    <circle cx="113" cy="3" r="6"/>
  </g>

  <g class="figure">
    <g class="legs">
      <path d="M50 118 v10 h-6"/>
      <path d="M70 118 v10 h6"/>
    </g>

    <g class="body">
      <ellipse cx="60" cy="70" rx="37" ry="50" fill="url(#${id}-skin)"/>
      <path class="crease" d="M62 22 C57 31 58 40 60 46 M60 95 C63 104 61 112 57 119"/>
      <ellipse class="shine" cx="44" cy="40" rx="8" ry="14" transform="rotate(-20 44 40)"/>

      <g class="eyes">
        <g class="eye"><ellipse cx="47" cy="62" rx="7.5" ry="8.5"/><circle class="pupil" cx="48" cy="63" r="3.6"/></g>
        <g class="eye"><ellipse cx="73" cy="62" rx="7.5" ry="8.5"/><circle class="pupil" cx="74" cy="63" r="3.6"/></g>
      </g>
      <g class="brows"><path d="M40 50 q7 -4 13 -1"/><path d="M67 49 q6 -3 13 1"/></g>
      <circle class="cheek" cx="39" cy="78" r="5"/>
      <circle class="cheek" cx="81" cy="78" r="5"/>

      <path class="mouth mouth-smile" d="M51 81 Q60 90 69 81"/>
      <ellipse class="mouth mouth-o" cx="62" cy="84" rx="3.2" ry="3.8"/>
      <path class="mouth mouth-sad" d="M52 87 Q60 81 68 87"/>
    </g>

    <g class="laptop">
      <path class="laptop-screen" d="M36 86 h48 a3 3 0 0 1 3 3 v27 h-54 v-27 a3 3 0 0 1 3 -3 z"/>
      <g class="laptop-lines">
        <rect x="40" y="92" width="22" height="3" rx="1.5"/>
        <rect x="40" y="99" width="34" height="3" rx="1.5"/>
        <rect x="40" y="106" width="16" height="3" rx="1.5"/>
      </g>
      <path class="laptop-base" d="M28 116 h64 l-5 7 h-54 z"/>
    </g>

    <!-- arms go last so the hands can rest on the chin or the keyboard -->
    <g class="arm arm-left"><path d="M25 78 Q15 88 14 100"/><circle cx="14" cy="101" r="4.5"/></g>
    <g class="arm arm-right"><path d="M95 78 Q105 88 106 100"/><circle cx="106" cy="101" r="4.5"/></g>
  </g>
</svg>`;
}

// Returns the wrapper element; set its className to change the mood.
function createMascot(mood = "") {
  const wrapper = document.createElement("div");
  wrapper.className = `mascot ${mood}`.trim();
  wrapper.innerHTML = mascotSvg();
  return wrapper;
}

function setMood(mascot, mood) {
  mascot.classList.remove("waving", "thinking", "searching", "happy", "sad");
  if (mood) mascot.classList.add(mood);
}

// While waiting for an answer Benny takes turns: thinking, then looking things up on his laptop.
function startWorking(mascot) {
  let searching = false;
  setMood(mascot, "thinking");
  const timer = setInterval(() => {
    searching = !searching;
    setMood(mascot, searching ? "searching" : "thinking");
  }, 2600);
  return () => clearInterval(timer);
}
