<script setup lang="ts">
/**
 * WirkSam and the alternatives: a pile of spreadsheet versions on the left,
 * one tidy roster on the right.
 */
const ROWS = 8
const COLS = 4
// Cells someone coloured by hand, each in a different idea of what it means.
const marked = [
  { c: 1, r: 1, tone: 'amber' },
  { c: 2, r: 2, tone: 'red' },
  { c: 0, r: 3, tone: 'green' },
  { c: 3, r: 4, tone: 'amber' },
  { c: 1, r: 5, tone: 'red' },
  { c: 2, r: 6, tone: 'green' },
]
const columns = [0, 1, 2]
const rows = [0, 1, 2, 3]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <!-- Versions upon versions. -->
    <rect x="40" y="62" width="148" height="186" rx="8" class="a-card sheet" transform="rotate(-9 114 155)" />
    <rect x="40" y="62" width="148" height="186" rx="8" class="a-card sheet" transform="rotate(-4 114 155)" />
    <g class="wobble">
      <g class="a-lift">
        <rect x="40" y="62" width="148" height="186" rx="8" class="a-card" />
      </g>
      <rect x="40" y="62" width="148" height="20" rx="8" class="a-muted" />
      <path
        v-for="r in ROWS"
        :key="`r-${r}`"
        :d="`M40 ${82 + r * 20.75}h148`"
        class="grid"
      />
      <path
        v-for="c in COLS - 1"
        :key="`c-${c}`"
        :d="`M${40 + c * 37} 62v186`"
        class="grid"
      />
      <rect
        v-for="(cell, index) in marked"
        :key="index"
        :x="41 + cell.c * 37"
        :y="83 + cell.r * 20.75"
        width="35"
        height="19"
        :class="cell.tone"
      />
    </g>

    <path d="M200 156h26" class="a-dash a-flow" />
    <path d="M224 149l8 7-8 7" class="a-rule" />

    <!-- One plan. -->
    <g class="a-lift">
      <rect x="240" y="62" width="140" height="186" rx="18" class="a-card" />
    </g>
    <path d="M240 80a18 18 0 0 1 18-18h104a18 18 0 0 1 18 18v10H240z" class="a-fill" />
    <g v-for="c in columns" :key="c">
      <g
        v-for="r in rows"
        :key="r"
        class="chip"
        :style="{ animationDelay: `${(c * 4 + r) * 0.08}s` }"
      >
        <rect :x="254 + c * 40" :y="104 + r * 35" width="34" height="28" rx="8" class="a-ok-soft" />
        <circle :cx="271 + c * 40" :cy="118 + r * 35" r="5" class="a-ok" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.sheet {
  opacity: 0.75;
}
.grid {
  fill: none;
  stroke: var(--border);
  stroke-width: 1;
}
.amber {
  fill: color-mix(in oklab, var(--chart-3) 45%, var(--card));
}
.red {
  fill: color-mix(in oklab, var(--chart-5) 30%, var(--card));
}
.green {
  fill: color-mix(in oklab, var(--chart-1) 30%, var(--card));
}

.wobble {
  transform-box: fill-box;
  transform-origin: center;
  animation: wobble 4s ease-in-out infinite;
}
@keyframes wobble {
  0%,
  100% {
    transform: rotate(1.5deg);
  }
  50% {
    transform: rotate(-1.5deg);
  }
}

.chip {
  transform-box: fill-box;
  transform-origin: center;
  animation: chip 8s ease-out infinite both;
}
@keyframes chip {
  0%,
  12% {
    opacity: 0;
    transform: scale(0.5);
  }
  17% {
    opacity: 1;
    transform: scale(1.06);
  }
  19% {
    transform: none;
  }
  82% {
    opacity: 1;
  }
  88%,
  100% {
    opacity: 0;
  }
}
</style>
