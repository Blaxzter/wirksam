<script setup lang="ts">
/**
 * Booking a shift: a phone with the open shifts, a tap on one, and it is
 * booked. The last free place fills, and the shift lands in the calendar.
 */
const rows = [0, 1, 2, 3]
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <!-- The shift's places, before and after. -->
    <g class="a-lift">
      <rect x="26" y="118" width="88" height="40" rx="20" class="a-card" />
    </g>
    <circle cx="54" cy="138" r="9" class="a-ok" />
    <circle cx="84" cy="138" r="9" class="a-free" />
    <circle cx="84" cy="138" r="9" class="a-ok seat" />

    <g class="a-lift">
      <rect x="128" y="16" width="144" height="268" rx="28" class="a-card phone" />
    </g>
    <rect x="180" y="28" width="40" height="7" rx="3.5" class="a-muted" />
    <rect x="146" y="48" width="72" height="9" rx="4.5" class="a-line" />

    <g v-for="r in rows" :key="r">
      <rect x="144" :y="68 + r * 50" width="112" height="42" rx="12" class="a-muted" />
      <rect x="152" :y="77 + r * 50" width="26" height="24" rx="7" class="a-on" />
      <rect x="186" :y="80 + r * 50" width="52" height="7" rx="3.5" class="a-line" />
      <rect x="186" :y="93 + r * 50" width="32" height="6" rx="3" class="a-line" />
    </g>

    <!-- The one being booked. -->
    <g class="picked">
      <rect x="144" y="118" width="112" height="42" rx="12" class="a-soft" />
      <rect x="152" y="127" width="26" height="24" rx="7" class="a-on" />
      <rect x="186" y="130" width="40" height="7" rx="3.5" class="a-line" />
      <rect x="186" y="143" width="26" height="6" rx="3" class="a-line" />
      <circle cx="240" cy="139" r="10" class="a-ok" />
      <path d="M235 139l3.5 3.5 6.5-7" class="a-tick" />
    </g>
    <circle cx="200" cy="139" r="8" class="finger" />
    <circle cx="200" cy="139" r="18" class="ripple" />

    <!-- And in the calendar. -->
    <g class="cal">
      <g class="a-lift">
        <rect x="290" y="166" width="88" height="88" rx="18" class="a-card" />
      </g>
      <path d="M290 184a18 18 0 0 1 18-18h52a18 18 0 0 1 18 18v6h-88z" class="a-fill" />
      <rect x="308" y="158" width="7" height="16" rx="3.5" class="a-ink" />
      <rect x="353" y="158" width="7" height="16" rx="3.5" class="a-ink" />
      <g v-for="cell in 9" :key="cell">
        <circle
          :cx="310 + ((cell - 1) % 3) * 24"
          :cy="208 + Math.floor((cell - 1) / 3) * 16"
          r="4"
          class="a-line"
        />
      </g>
      <circle cx="334" cy="224" r="7" class="a-fill mark" />
    </g>
  </svg>
</template>

<style scoped>
.phone {
  stroke: color-mix(in oklab, var(--foreground) 22%, transparent);
  stroke-width: 3;
}
.finger {
  fill: color-mix(in oklab, var(--foreground) 30%, transparent);
  opacity: 0;
  animation: finger 8s ease-out infinite;
}
@keyframes finger {
  0%,
  14% {
    opacity: 0;
    transform: translate(40px, 60px);
  }
  20% {
    opacity: 1;
    transform: none;
  }
  27% {
    opacity: 1;
  }
  31%,
  100% {
    opacity: 0;
  }
}
.ripple {
  fill: none;
  stroke: color-mix(in oklab, var(--foreground) 35%, transparent);
  stroke-width: 2;
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
  animation: ripple 8s ease-out infinite;
}
@keyframes ripple {
  0%,
  22% {
    opacity: 0;
    transform: scale(0.3);
  }
  23% {
    opacity: 0.6;
  }
  31%,
  100% {
    opacity: 0;
    transform: scale(1.5);
  }
}

.picked {
  animation: picked 8s ease-out infinite both;
}
@keyframes picked {
  0%,
  24% {
    opacity: 0;
  }
  28%,
  84% {
    opacity: 1;
  }
  90%,
  100% {
    opacity: 0;
  }
}

.seat,
.mark {
  transform-box: fill-box;
  transform-origin: center;
  animation: fill 8s ease-out infinite both;
}
.mark {
  animation-delay: 0.6s;
}
@keyframes fill {
  0%,
  30% {
    opacity: 0;
    transform: scale(0.3);
  }
  34% {
    opacity: 1;
    transform: scale(1.2);
  }
  37% {
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

.cal {
  transform-box: fill-box;
  transform-origin: center;
  animation: bump 8s ease-in-out infinite;
}
@keyframes bump {
  0%,
  37% {
    transform: none;
  }
  40% {
    transform: scale(1.06);
  }
  43%,
  100% {
    transform: none;
  }
}
</style>
