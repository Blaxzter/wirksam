<script setup lang="ts">
/**
 * Copying an event to next year: last year's event, full of bookings, and its
 * copy sliding out beside it with the same shifts, all of them still empty.
 */
const cells = [0, 1, 2, 3, 4, 5, 6, 7, 8]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <path d="M118 66C156 22 246 22 284 66" class="a-dash a-flow" />
    <path d="M272 58l13 9-15 4" class="a-rule" />
    <g class="plus">
      <circle cx="200" cy="34" r="15" class="a-fill" />
      <path d="M200 27v14M193 34h14" class="a-tick" />
    </g>

    <!-- Last year. -->
    <g class="a-lift">
      <rect x="34" y="76" width="152" height="176" rx="18" class="a-card" />
    </g>
    <path d="M34 94a18 18 0 0 1 18-18h116a18 18 0 0 1 18 18v12H34z" class="old" />
    <g v-for="cell in cells" :key="`a-${cell}`">
      <rect
        :x="52 + (cell % 3) * 42"
        :y="122 + Math.floor(cell / 3) * 40"
        width="34"
        height="32"
        rx="8"
        class="a-ok-soft"
      />
      <circle :cx="69 + (cell % 3) * 42" :cy="138 + Math.floor(cell / 3) * 40" r="5" class="a-ok" />
    </g>

    <!-- This year: the same shifts, nobody on them yet. -->
    <g class="copy">
      <g class="a-lift">
        <rect x="214" y="76" width="152" height="176" rx="18" class="a-card" />
      </g>
      <path d="M214 94a18 18 0 0 1 18-18h116a18 18 0 0 1 18 18v12H214z" class="a-fill" />
      <rect
        v-for="cell in cells"
        :key="`b-${cell}`"
        :x="232 + (cell % 3) * 42"
        :y="122 + Math.floor(cell / 3) * 40"
        width="34"
        height="32"
        rx="8"
        class="a-free shift"
        :style="{ animationDelay: `${cell * 0.07}s` }"
      />
    </g>
  </svg>
</template>

<style scoped>
.old {
  fill: color-mix(in oklab, var(--muted-foreground) 45%, var(--card));
}

.plus {
  transform-box: fill-box;
  transform-origin: center;
  animation: plus 8s ease-out infinite both;
}
@keyframes plus {
  0%,
  6% {
    opacity: 0;
    transform: scale(0.4);
  }
  10% {
    opacity: 1;
    transform: scale(1.1);
  }
  12% {
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

.copy {
  animation: copy 8s cubic-bezier(0.4, 0, 0.2, 1) infinite both;
}
@keyframes copy {
  0%,
  10% {
    opacity: 0;
    transform: translateX(-180px);
  }
  14% {
    opacity: 1;
  }
  26% {
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

.shift {
  transform-box: fill-box;
  transform-origin: center;
  animation: shift 8s ease-out infinite both;
}
@keyframes shift {
  0%,
  27% {
    opacity: 0;
    transform: scale(0.5);
  }
  31% {
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
