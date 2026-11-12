<script setup lang="ts">
/**
 * People in charge: someone takes over one task. They move into the task's
 * empty slot, get the shield, and the task's shifts are theirs to look after.
 */
const shifts = [0, 1, 2, 3]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <g class="a-lift">
      <rect x="54" y="44" width="248" height="212" rx="20" class="a-card" />
    </g>

    <!-- The task. -->
    <rect x="76" y="66" width="42" height="42" rx="12" class="a-soft" />
    <rect x="87" y="76" width="20" height="25" rx="3" class="a-stroke" />
    <rect x="92" y="72" width="10" height="7" rx="2" class="a-fill" />
    <rect x="130" y="72" width="124" height="10" rx="5" class="a-line" />
    <rect x="130" y="90" width="80" height="8" rx="4" class="a-line" />

    <rect x="76" y="126" width="70" height="7" rx="3.5" class="a-line" />
    <circle cx="96" cy="164" r="19" class="slot" />
    <rect x="126" y="156" width="84" height="8" rx="4" class="a-line" />
    <rect x="126" y="170" width="54" height="7" rx="3.5" class="a-line" />

    <g v-for="i in shifts" :key="i">
      <rect :x="76 + i * 54" y="198" width="46" height="38" rx="10" class="a-muted" />
      <g class="own" :style="{ animationDelay: `${i * 0.12}s` }">
        <rect :x="76 + i * 54" y="198" width="46" height="38" rx="10" class="a-soft" />
        <path :d="`M${91 + i * 54} 217l5 5 9-10`" class="a-stroke" />
      </g>
    </g>

    <!-- The person, arriving from outside the task. -->
    <g transform="translate(96 164)">
      <g class="arrive">
        <circle r="21" class="face" />
        <circle cy="-6" r="7" class="a-person" />
        <path d="M-12 13a12 10 0 0 1 24 0z" class="a-person" />
        <g class="shield" transform="translate(15 -15)">
          <path d="M0 -11l9 3.5v6c0 6-4.5 9.5-9 12-4.5-2.5-9-6-9-12v-6z" class="a-fill" />
          <path d="M-3.5 0l2.5 2.5 4.5-5" class="a-tick" />
        </g>
      </g>
    </g>
  </svg>
</template>

<style scoped>
.face {
  fill: color-mix(in oklab, var(--art) 34%, var(--card));
  stroke: var(--card);
  stroke-width: 3;
}
.slot {
  fill: none;
  stroke: color-mix(in oklab, var(--muted-foreground) 55%, transparent);
  stroke-width: 2;
  stroke-dasharray: 5 5;
  opacity: 0;
  animation: slot 8s linear infinite;
}
@keyframes slot {
  0%,
  21% {
    opacity: 1;
  }
  23%,
  100% {
    opacity: 0;
  }
}

.arrive {
  animation: arrive 8s cubic-bezier(0.4, 0, 0.2, 1) infinite both;
}
@keyframes arrive {
  0% {
    opacity: 0;
    transform: translate(250px, -40px);
  }
  6% {
    opacity: 1;
    transform: translate(250px, -40px);
  }
  22% {
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

.shield {
  animation: shield 8s ease-out infinite both;
}
@keyframes shield {
  0%,
  25% {
    opacity: 0;
  }
  29%,
  84% {
    opacity: 1;
  }
  90%,
  100% {
    opacity: 0;
  }
}

.own {
  transform-box: fill-box;
  transform-origin: center;
  animation: own 8s ease-out infinite both;
}
@keyframes own {
  0%,
  32% {
    opacity: 0;
    transform: scale(0.7);
  }
  36% {
    opacity: 1;
    transform: scale(1.05);
  }
  38% {
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
