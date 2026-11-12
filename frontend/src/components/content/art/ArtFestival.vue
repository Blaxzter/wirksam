<script setup lang="ts">
/**
 * A club festival: bunting, two stands with striped awnings, and the shifts on
 * each counter filling up.
 */
const START = { x: 6, y: 40 }
const CONTROL = { x: 200, y: 92 }
const END = { x: 394, y: 40 }

// Points along the bunting's curve, one flag each.
const flags = Array.from({ length: 11 }, (_, index) => {
  const t = (index + 0.5) / 11
  const u = 1 - t
  return {
    x: u * u * START.x + 2 * u * t * CONTROL.x + t * t * END.x,
    y: u * u * START.y + 2 * u * t * CONTROL.y + t * t * END.y,
    tone: ['art', 'amber', 'green', 'blue'][index % 4],
  }
})

const stands = [
  { x: 36, stripe: 'a-fill' },
  { x: 214, stripe: 'blue' },
]
const STRIPES = 6
const WIDTH = 150
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <path
      :d="`M${START.x} ${START.y}Q${CONTROL.x} ${CONTROL.y} ${END.x} ${END.y}`"
      class="string"
    />
    <path
      v-for="(flag, index) in flags"
      :key="index"
      :d="`M${flag.x - 10} ${flag.y}h20l-10 22z`"
      class="a-sway"
      :class="flag.tone"
      :style="{ animationDelay: `${index * -0.3}s` }"
    />

    <path d="M20 252h360" class="a-rule" />

    <g v-for="(stand, index) in stands" :key="index">
      <rect :x="stand.x + 8" y="132" width="6" height="120" rx="3" class="post" />
      <rect :x="stand.x + WIDTH - 14" y="132" width="6" height="120" rx="3" class="post" />
      <!-- The awning: stripes with a scalloped edge. -->
      <rect :x="stand.x - 4" y="102" :width="WIDTH + 8" height="8" rx="4" class="post" />
      <g v-for="s in STRIPES" :key="s">
        <rect
          :x="stand.x + (s - 1) * (WIDTH / STRIPES)"
          y="108"
          :width="WIDTH / STRIPES"
          height="28"
          :class="s % 2 ? stand.stripe : 'a-on'"
        />
        <circle
          :cx="stand.x + (s - 0.5) * (WIDTH / STRIPES)"
          cy="136"
          :r="WIDTH / STRIPES / 2"
          :class="s % 2 ? stand.stripe : 'a-on'"
        />
      </g>
      <rect :x="stand.x" y="108" :width="WIDTH" height="28" class="edge" />

      <g class="a-lift">
        <rect :x="stand.x + 12" y="180" :width="WIDTH - 24" height="56" rx="10" class="a-card" />
      </g>
      <g v-for="c in 3" :key="c">
        <rect :x="stand.x + 24 + (c - 1) * 36" y="194" width="30" height="28" rx="7" class="a-free" />
        <g class="fill" :style="{ animationDelay: `${(index * 3 + c - 1) * 0.35}s` }">
          <rect :x="stand.x + 24 + (c - 1) * 36" y="194" width="30" height="28" rx="7" class="a-ok-soft" />
          <circle :cx="stand.x + 39 + (c - 1) * 36" cy="208" r="5" class="a-ok" />
        </g>
      </g>
    </g>
  </svg>
</template>

<style scoped>
.string {
  fill: none;
  stroke: var(--art-ink);
  stroke-width: 2;
}
.art {
  fill: var(--art);
}
.amber {
  fill: var(--chart-3);
}
.green {
  fill: var(--chart-1);
}
.blue {
  fill: var(--chart-4);
}
.post {
  fill: var(--art-ink);
}
.edge {
  fill: none;
}

.fill {
  transform-box: fill-box;
  transform-origin: center;
  animation: fill 8s ease-out infinite both;
}
@keyframes fill {
  0%,
  10% {
    opacity: 0;
    transform: scale(0.5);
  }
  14% {
    opacity: 1;
    transform: scale(1.08);
  }
  16% {
    transform: none;
  }
  80% {
    opacity: 1;
  }
  86%,
  100% {
    opacity: 0;
  }
}
</style>
