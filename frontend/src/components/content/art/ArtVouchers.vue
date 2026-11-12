<script setup lang="ts">
/**
 * Vouchers: worked shifts drop vouchers onto the stack, the phone shows its
 * code, and at the stand one voucher is redeemed.
 */
// A made-up code: three finder squares in the corners and noise in between.
const NOISE = [
  [3, 0],
  [3, 1],
  [4, 2],
  [3, 3],
  [5, 3],
  [6, 3],
  [0, 4],
  [2, 4],
  [4, 4],
  [6, 5],
  [3, 5],
  [4, 6],
  [6, 6],
  [5, 4],
  [3, 6],
  [1, 3],
]
const FINDERS = [
  [0, 0],
  [4, 0],
  [0, 4],
]
const CELL = 12
const tickets = [
  { y: 200, delay: '0s' },
  { y: 144, delay: '0.55s' },
  { y: 88, delay: '1.1s' },
]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <g class="a-lift">
      <rect x="34" y="22" width="132" height="256" rx="26" class="a-card phone" />
    </g>
    <rect x="80" y="34" width="40" height="7" rx="3.5" class="a-muted" />

    <g transform="translate(58 66)">
      <rect x="-6" y="-6" width="96" height="96" rx="10" class="a-on" />
      <g v-for="([x, y], index) in FINDERS" :key="`f-${index}`">
        <rect
          :x="x! * CELL + 1.5"
          :y="y! * CELL + 1.5"
          :width="CELL * 3 - 3"
          :height="CELL * 3 - 3"
          rx="5"
          class="finder"
        />
        <rect :x="x! * CELL + 10" :y="y! * CELL + 10" width="16" height="16" rx="3" class="a-ink" />
      </g>
      <rect
        v-for="([x, y], index) in NOISE"
        :key="`n-${index}`"
        :x="x! * CELL + 1"
        :y="y! * CELL + 1"
        :width="CELL - 2"
        :height="CELL - 2"
        rx="2.5"
        class="a-ink"
      />
      <rect x="-8" y="-2" width="100" height="3" rx="1.5" class="a-fill scan" />
    </g>
    <rect x="58" y="176" width="84" height="8" rx="4" class="a-line" />
    <rect x="68" y="190" width="64" height="7" rx="3.5" class="a-line" />
    <rect x="54" y="214" width="92" height="30" rx="10" class="a-ok" />

    <!-- The stack of vouchers, newest on top. -->
    <g v-for="(ticket, index) in tickets" :key="index" class="drop" :style="{ animationDelay: ticket.delay }">
      <g class="a-lift">
        <path
          :d="`M206 ${ticket.y + 12}a12 12 0 0 1 12-12h126a12 12 0 0 1 12 12v8a8 8 0 0 0 0 16v8a12 12 0 0 1-12 12H218a12 12 0 0 1-12-12v-8a8 8 0 0 0 0-16z`"
          class="a-soft"
        />
      </g>
      <circle cx="234" :cy="ticket.y + 28" r="13" class="a-fill" />
      <path
        :d="`M234 ${ticket.y + 21}l2.2 4.6 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5-3.6-3.5 5-.7z`"
        class="a-on"
      />
      <rect x="256" :y="ticket.y + 19" width="56" height="8" rx="4" class="a-line" />
      <rect x="256" :y="ticket.y + 32" width="36" height="7" rx="3.5" class="a-line" />
      <path :d="`M326 ${ticket.y + 8}v40`" class="a-dash" />
    </g>

    <!-- Redeemed at the stand. -->
    <g class="stamp">
      <circle cx="344" cy="92" r="15" class="a-ok" />
      <path d="M337 92l5 5 9-10" class="a-tick" />
    </g>
  </svg>
</template>

<style scoped>
.phone {
  stroke: color-mix(in oklab, var(--foreground) 22%, transparent);
  stroke-width: 3;
}
.finder {
  fill: none;
  stroke: var(--art-ink);
  stroke-width: 3;
}

.scan {
  opacity: 0.85;
  animation: scan 2.6s ease-in-out infinite;
}
@keyframes scan {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(86px);
  }
}

.drop {
  animation: drop 8s cubic-bezier(0.3, 0.7, 0.4, 1) infinite both;
}
@keyframes drop {
  0%,
  4% {
    opacity: 0;
    transform: translateY(-50px);
  }
  12% {
    opacity: 1;
    transform: translateY(3px);
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
  }
}

.stamp {
  transform-box: fill-box;
  transform-origin: center;
  animation: stamp 8s ease-out infinite both;
}
@keyframes stamp {
  0%,
  42% {
    opacity: 0;
    transform: scale(1.8) rotate(-20deg);
  }
  46% {
    opacity: 1;
    transform: scale(0.92);
  }
  48% {
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
