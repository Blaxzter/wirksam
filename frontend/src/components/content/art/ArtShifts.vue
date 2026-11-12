<script setup lang="ts">
/**
 * Shift planning: a task with its hours on the left, cut into pieces, and the
 * shifts that come out of it on the right, three days of four, each with two
 * free places.
 */
const columns = [0, 1, 2]
const rows = [0, 1, 2, 3]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <g class="a-lift">
      <rect x="22" y="62" width="142" height="176" rx="18" class="a-card" />
    </g>
    <circle cx="50" cy="92" r="14" class="a-soft" />
    <path d="M50 84v8l6 4" class="a-stroke" />
    <rect x="74" y="84" width="72" height="9" rx="4.5" class="a-line" />
    <rect x="74" y="98" width="46" height="7" rx="3.5" class="a-line" />

    <!-- The day, cut into four. -->
    <rect x="36" y="122" width="114" height="20" rx="10" class="a-muted" />
    <rect
      v-for="i in 4"
      :key="i"
      :x="36 + (i - 1) * 29"
      y="122"
      width="27"
      height="20"
      rx="8"
      class="a-fill seg"
      :style="{ animationDelay: `${(i - 1) * 0.18}s` }"
    />

    <rect x="36" y="154" width="54" height="28" rx="9" class="a-muted" />
    <rect x="44" y="165" width="30" height="6" rx="3" class="a-line" />
    <rect x="96" y="154" width="54" height="28" rx="9" class="a-muted" />
    <circle cx="113" cy="168" r="4.5" class="a-person" />
    <circle cx="127" cy="168" r="4.5" class="a-person" />

    <g class="press">
      <rect x="36" y="194" width="114" height="30" rx="10" class="a-ok" />
      <path d="M84 209h18m-6-6 6 6-6 6" class="a-tick" />
    </g>

    <path d="M172 150h30" class="a-dash a-flow" />
    <path d="M200 143l8 7-8 7" class="a-rule" />

    <!-- What comes out: three days of four shifts. -->
    <g v-for="c in columns" :key="c">
      <rect :x="226 + c * 58" y="52" width="30" height="8" rx="4" class="a-line" />
      <g
        v-for="r in rows"
        :key="r"
        class="chip"
        :style="{ animationDelay: `${(c * 4 + r) * 0.09}s` }"
      >
        <rect :x="216 + c * 58" :y="70 + r * 52" width="50" height="44" rx="11" class="a-soft" />
        <circle :cx="233 + c * 58" :cy="92 + r * 52" r="5.5" class="place" />
        <circle :cx="249 + c * 58" :cy="92 + r * 52" r="5.5" class="place" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.place {
  fill: var(--card);
  stroke: var(--art-edge);
  stroke-width: 2;
}

.seg {
  transform-box: fill-box;
  transform-origin: left center;
  animation: seg 7s ease-out infinite both;
}
@keyframes seg {
  0%,
  3% {
    opacity: 0;
    transform: scaleX(0.2);
  }
  9% {
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

.press {
  transform-box: fill-box;
  transform-origin: center;
  animation: press 7s ease-in-out infinite;
}
@keyframes press {
  0%,
  13% {
    transform: none;
  }
  15% {
    transform: scale(0.93);
  }
  18%,
  100% {
    transform: none;
  }
}

.chip {
  transform-box: fill-box;
  transform-origin: center;
  animation: chip 7s ease-out infinite both;
}
@keyframes chip {
  0%,
  17% {
    opacity: 0;
    transform: scale(0.5);
  }
  22% {
    opacity: 1;
    transform: scale(1.06);
  }
  25% {
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
