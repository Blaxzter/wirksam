<script setup lang="ts">
/**
 * The venue map: a drawn site with a pin per place. The pins drop in, one
 * place still needs help and pulses, and then it fills up as well.
 */
const PIN = 'M0 0C-3 -7 -12 -13 -12 -22A12 12 0 1 1 12 -22C12 -13 3 -7 0 0Z'

const pins = [
  { x: 84, y: 98, short: false },
  { x: 152, y: 176, short: false },
  { x: 280, y: 132, short: true },
  { x: 318, y: 214, short: false },
]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <g class="a-lift">
      <rect x="24" y="24" width="352" height="252" rx="22" class="a-card" />
    </g>
    <rect x="24" y="228" width="352" height="22" class="a-muted" />

    <!-- A building with rooms, and a hall with its rows of seats. -->
    <rect x="46" y="46" width="144" height="160" rx="12" class="room" />
    <path d="M118 46v72M46 118h144" class="a-rule" />
    <rect x="208" y="46" width="146" height="122" rx="12" class="room" />
    <rect x="244" y="58" width="74" height="18" rx="6" class="a-soft" />
    <g v-for="r in 4" :key="r">
      <rect x="226" :y="88 + (r - 1) * 18" width="50" height="8" rx="4" class="a-line" />
      <rect x="286" :y="88 + (r - 1) * 18" width="50" height="8" rx="4" class="a-line" />
    </g>
    <circle cx="214" cy="198" r="9" class="tree" />
    <circle cx="240" cy="208" r="7" class="tree" />
    <circle cx="352" cy="190" r="9" class="tree" />
    <circle cx="66" cy="222" r="7" class="tree" />

    <g v-for="(pin, index) in pins" :key="index" :transform="`translate(${pin.x} ${pin.y})`">
      <g class="drop" :style="{ animationDelay: `${index * 0.15}s` }">
        <ellipse cx="0" cy="1" rx="8" ry="3" class="shade" />
        <path :d="PIN" :class="pin.short ? 'a-warn' : 'a-ok'" />
        <circle cx="0" cy="-22" r="5" class="a-on" />
      </g>
      <template v-if="pin.short">
        <!-- Still short of people: it calls for attention, then fills up. -->
        <g class="alarm">
          <circle cx="0" cy="-22" r="17" class="ring a-pulse" />
        </g>
        <g class="filled">
          <path :d="PIN" class="a-ok" />
          <circle cx="0" cy="-22" r="5" class="a-on" />
        </g>
      </template>
    </g>
  </svg>
</template>

<style scoped>
.room {
  fill: color-mix(in oklab, var(--muted) 55%, var(--card));
  stroke: var(--border);
  stroke-width: 2;
}
.tree {
  fill: color-mix(in oklab, var(--primary) 32%, var(--card));
}
.shade {
  fill: color-mix(in oklab, var(--foreground) 14%, transparent);
}
.ring {
  fill: none;
  stroke: var(--warning);
  stroke-width: 3;
}

.drop {
  animation: drop 8s cubic-bezier(0.3, 0.7, 0.4, 1) infinite both;
}
@keyframes drop {
  0%,
  2% {
    opacity: 0;
    transform: translateY(-40px);
  }
  8% {
    opacity: 1;
    transform: translateY(3px);
  }
  10% {
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

.alarm {
  opacity: 0;
  animation: alarm 8s linear infinite;
}
@keyframes alarm {
  0%,
  10% {
    opacity: 0;
  }
  12%,
  54% {
    opacity: 1;
  }
  56%,
  100% {
    opacity: 0;
  }
}

.filled {
  transform-box: fill-box;
  transform-origin: 50% 100%;
  animation: filled 8s ease-out infinite both;
}
@keyframes filled {
  0%,
  55% {
    opacity: 0;
    transform: scale(0.6);
  }
  59% {
    opacity: 1;
    transform: scale(1.12);
  }
  62% {
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
