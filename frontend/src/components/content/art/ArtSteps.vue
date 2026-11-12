<script setup lang="ts">
/**
 * The guides: a guide page, and a path of four steps that are ticked off one by
 * one until the flag at the end.
 */
const PATH = 'M60 238C112 238 104 182 158 182S190 126 242 126S286 72 340 72'
const stops = [
  { x: 60, y: 238, at: 'stop-1' },
  { x: 158, y: 182, at: 'stop-2' },
  { x: 242, y: 126, at: 'stop-3' },
  { x: 340, y: 72, at: 'stop-4' },
]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <!-- A guide page. -->
    <g class="a-float">
      <g class="a-lift">
        <rect x="30" y="34" width="122" height="96" rx="14" class="a-card" />
      </g>
      <rect x="46" y="50" width="70" height="9" rx="4.5" class="a-line" />
      <g v-for="i in 3" :key="i">
        <circle cx="52" :cy="74 + (i - 1) * 18" r="5" class="a-fill" />
        <rect x="64" :y="70 + (i - 1) * 18" :width="[66, 52, 60][i - 1]" height="8" rx="4" class="a-line" />
      </g>
    </g>

    <path :d="PATH" class="track" />
    <path :d="PATH" pathLength="1" class="progress" />

    <g v-for="stop in stops" :key="stop.at" :transform="`translate(${stop.x} ${stop.y})`">
      <circle r="17" class="a-card stop" />
      <g class="done" :style="{ animationName: stop.at }">
        <circle r="17" class="a-fill" />
        <path d="M-7 0l5 5 9-10" class="a-tick" />
      </g>
    </g>

    <g class="flag">
      <path d="M340 52V18" class="pole" />
      <path d="M340 18h30l-8 9 8 9h-30z" class="a-fill" />
    </g>
  </svg>
</template>

<style scoped>
.stop {
  stroke-width: 3;
}
.track {
  fill: none;
  stroke: var(--muted);
  stroke-width: 12;
  stroke-linecap: round;
}
.progress {
  fill: none;
  stroke: var(--art);
  stroke-width: 12;
  stroke-linecap: round;
  stroke-dasharray: 1;
  animation: progress 8s linear infinite both;
}
@keyframes progress {
  0%,
  6% {
    stroke-dashoffset: 1;
    opacity: 1;
  }
  56% {
    stroke-dashoffset: 0;
  }
  84% {
    opacity: 1;
    stroke-dashoffset: 0;
  }
  90%,
  100% {
    opacity: 0;
    stroke-dashoffset: 0;
  }
}

.done {
  transform-box: fill-box;
  transform-origin: center;
  animation-duration: 8s;
  animation-timing-function: ease-out;
  animation-iteration-count: infinite;
  animation-fill-mode: both;
}
/* Each stop is ticked as the line reaches it. */
@keyframes stop-1 {
  0%,
  4% {
    opacity: 0;
    transform: scale(0.4);
  }
  8%,
  84% {
    opacity: 1;
    transform: none;
  }
  90%,
  100% {
    opacity: 0;
  }
}
@keyframes stop-2 {
  0%,
  23% {
    opacity: 0;
    transform: scale(0.4);
  }
  27%,
  84% {
    opacity: 1;
    transform: none;
  }
  90%,
  100% {
    opacity: 0;
  }
}
@keyframes stop-3 {
  0%,
  38% {
    opacity: 0;
    transform: scale(0.4);
  }
  42%,
  84% {
    opacity: 1;
    transform: none;
  }
  90%,
  100% {
    opacity: 0;
  }
}
@keyframes stop-4 {
  0%,
  55% {
    opacity: 0;
    transform: scale(0.4);
  }
  59%,
  84% {
    opacity: 1;
    transform: none;
  }
  90%,
  100% {
    opacity: 0;
  }
}

.pole {
  fill: none;
  stroke: var(--art-ink);
  stroke-width: 3;
  stroke-linecap: round;
}
.flag {
  transform-box: fill-box;
  transform-origin: 0% 100%;
  animation: flag 8s ease-out infinite both;
}
@keyframes flag {
  0%,
  58% {
    opacity: 0;
    transform: scaleY(0.2);
  }
  63% {
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
</style>
