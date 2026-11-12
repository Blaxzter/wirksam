<script setup lang="ts">
/**
 * Teams: someone asks to join. Their checks are ticked one by one, and then
 * they move into the team's free place.
 */
const members = [
  { x: 232, y: 112 },
  { x: 322, y: 112 },
  { x: 232, y: 200 },
]
const checks = [0, 1]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <!-- The team. -->
    <rect x="182" y="46" width="196" height="214" rx="30" class="crew" />
    <rect x="246" y="34" width="68" height="26" rx="13" class="a-fill" />
    <circle cx="270" cy="47" r="5" class="a-on" />
    <circle cx="290" cy="47" r="5" class="a-on" />

    <g v-for="(member, index) in members" :key="index" :transform="`translate(${member.x} ${member.y})`">
      <circle r="25" class="face" />
      <circle cy="-6" r="8" class="a-person" />
      <path d="M-14 15a14 12 0 0 1 28 0z" class="a-person" />
    </g>
    <circle cx="322" cy="200" r="25" class="slot" />

    <!-- The request, with what has to be checked. -->
    <g class="a-lift">
      <rect x="20" y="128" width="134" height="110" rx="16" class="a-card" />
    </g>
    <g v-for="i in checks" :key="i">
      <rect x="36" :y="148 + i * 44" width="24" height="24" rx="7" class="box" />
      <g class="tick" :style="{ animationName: i === 0 ? 'tick-a' : 'tick-b' }">
        <rect x="36" :y="148 + i * 44" width="24" height="24" rx="7" class="a-fill" />
        <path :d="`M42 ${160 + i * 44}l4.5 4.5 8-9`" class="a-tick" />
      </g>
      <rect x="70" :y="152 + i * 44" width="68" height="8" rx="4" class="a-line" />
      <rect x="70" :y="165 + i * 44" width="44" height="7" rx="3.5" class="a-line" />
    </g>
    <path d="M160 182h18" class="a-dash a-flow" />

    <!-- The person asking: next to their request first, then in the team. -->
    <g transform="translate(322 200)">
      <circle r="25" class="joined" />
      <g class="move">
        <circle r="25" class="face new" />
        <circle cy="-6" r="8" class="a-person" />
        <path d="M-14 15a14 12 0 0 1 28 0z" class="a-person" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.crew {
  fill: color-mix(in oklab, var(--art) 10%, transparent);
  stroke: var(--art-edge);
  stroke-width: 2;
  stroke-dasharray: 8 6;
}
.face {
  fill: color-mix(in oklab, var(--chart-4) 26%, var(--card));
  stroke: var(--card);
  stroke-width: 3;
}
.new {
  fill: color-mix(in oklab, var(--art) 38%, var(--card));
}
.box {
  fill: var(--card);
  stroke: var(--border);
  stroke-width: 2;
}
.slot {
  fill: none;
  stroke: var(--art-edge);
  stroke-width: 2;
  stroke-dasharray: 5 5;
  opacity: 0;
  animation: slot 8s linear infinite;
}
@keyframes slot {
  0%,
  50% {
    opacity: 1;
  }
  52%,
  100% {
    opacity: 0;
  }
}

.tick {
  transform-box: fill-box;
  transform-origin: center;
  animation-duration: 8s;
  animation-timing-function: ease-out;
  animation-iteration-count: infinite;
  animation-fill-mode: both;
}
@keyframes tick-a {
  0%,
  12% {
    opacity: 0;
    transform: scale(0.5);
  }
  16% {
    opacity: 1;
    transform: none;
  }
  84% {
    opacity: 1;
  }
  90%,
  100% {
    opacity: 0;
  }
}
@keyframes tick-b {
  0%,
  24% {
    opacity: 0;
    transform: scale(0.5);
  }
  28% {
    opacity: 1;
    transform: none;
  }
  84% {
    opacity: 1;
  }
  90%,
  100% {
    opacity: 0;
  }
}

.move {
  animation: move 8s cubic-bezier(0.4, 0, 0.2, 1) infinite both;
}
@keyframes move {
  0% {
    opacity: 0;
    transform: translate(-235px, -118px);
  }
  5%,
  36% {
    opacity: 1;
    transform: translate(-235px, -118px);
  }
  52% {
    transform: none;
  }
  84% {
    opacity: 1;
  }
  90%,
  100% {
    opacity: 0;
  }
}

/* A ring that opens once as the new member arrives. */
.joined {
  fill: none;
  stroke: var(--art);
  stroke-width: 3;
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
  animation: joined 8s ease-out infinite;
}
@keyframes joined {
  0%,
  51% {
    opacity: 0;
    transform: scale(1);
  }
  53% {
    opacity: 0.7;
  }
  64%,
  100% {
    opacity: 0;
    transform: scale(1.8);
  }
}
</style>
