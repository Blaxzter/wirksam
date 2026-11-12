<script setup lang="ts">
/**
 * Hours and reports: three numbers at the top, bookings per day as bars, and
 * the trend drawn over them. The clock keeps counting.
 */
const BARS = [34, 54, 76, 60, 90, 80, 48]
const BASE = 244
const points = BARS.map((height, index) => ({ x: 75 + index * 41, y: BASE - height - 16 }))
const line = points.map((point, index) => `${index ? 'L' : 'M'}${point.x} ${point.y}`).join('')
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <g class="a-lift">
      <rect x="30" y="30" width="340" height="240" rx="20" class="a-card" />
    </g>
    <rect x="54" y="52" width="96" height="10" rx="5" class="a-line" />
    <rect x="54" y="68" width="60" height="7" rx="3.5" class="a-line" />

    <g transform="translate(330 62)">
      <circle r="20" class="a-soft" />
      <path d="M0 0v-10" class="hand" />
      <path d="M0 0h12" class="hand minute" />
      <circle r="2.5" class="a-ink" />
    </g>

    <g v-for="i in 3" :key="i">
      <rect :x="54 + (i - 1) * 90" y="88" width="80" height="40" rx="10" class="a-muted" />
      <rect :x="64 + (i - 1) * 90" y="98" width="34" height="11" rx="3" class="a-ink" />
      <rect :x="64 + (i - 1) * 90" y="114" width="50" height="6" rx="3" class="a-line" />
      <circle :cx="120 + (i - 1) * 90" cy="103" r="4" class="a-fill" />
    </g>

    <path :d="`M54 ${BASE}h292`" class="a-rule" />
    <rect
      v-for="(height, index) in BARS"
      :key="index"
      :x="62 + index * 41"
      :y="BASE - height"
      width="26"
      :height="height"
      rx="6"
      class="bar"
      :style="{ animationDelay: `${index * 0.1}s` }"
    />
    <path :d="line" pathLength="1" class="trend" />
    <circle
      v-for="(point, index) in points"
      :key="`p-${index}`"
      :cx="point.x"
      :cy="point.y"
      r="4.5"
      class="dot"
      :style="{ animationDelay: `${index * 0.06}s` }"
    />
  </svg>
</template>

<style scoped>
.hand {
  fill: none;
  stroke: var(--art-ink);
  stroke-width: 3;
  stroke-linecap: round;
}
.minute {
  transform-box: fill-box;
  transform-origin: 0% 50%;
  animation: spin 6s linear infinite;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.bar {
  fill: color-mix(in oklab, var(--art) 72%, var(--card));
  transform-box: fill-box;
  transform-origin: 50% 100%;
  animation: grow 8s cubic-bezier(0.3, 0.7, 0.4, 1) infinite both;
}
@keyframes grow {
  0%,
  4% {
    transform: scaleY(0);
  }
  14% {
    transform: none;
  }
  84% {
    opacity: 1;
  }
  90%,
  100% {
    opacity: 0;
    transform: none;
  }
}

.trend {
  fill: none;
  stroke: var(--primary);
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 1;
  animation: trend 8s ease-in-out infinite both;
}
@keyframes trend {
  0%,
  20% {
    stroke-dashoffset: 1;
    opacity: 1;
  }
  38% {
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

.dot {
  fill: var(--card);
  stroke: var(--primary);
  stroke-width: 2.5;
  transform-box: fill-box;
  transform-origin: center;
  animation: dot 8s ease-out infinite both;
}
@keyframes dot {
  0%,
  38% {
    opacity: 0;
    transform: scale(0.3);
  }
  42% {
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
