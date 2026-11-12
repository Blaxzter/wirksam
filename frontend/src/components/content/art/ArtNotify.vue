<script setup lang="ts">
/**
 * Reminders: the bell rings, and the reminder goes out the ways a person chose:
 * email, push, Telegram, and always the inbox in the app.
 */
const channels = [
  { key: 'mail', x: 76, y: 74 },
  { key: 'push', x: 324, y: 74 },
  { key: 'telegram', x: 324, y: 224 },
  { key: 'inbox', x: 76, y: 224 },
] as const
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <path d="M76 74L200 150L324 74M76 224L200 150L324 224" class="a-dash" />

    <g
      v-for="(channel, index) in channels"
      :key="channel.key"
      :transform="`translate(${channel.x} ${channel.y})`"
    >
      <g
        class="out"
        :style="{
          animationDelay: `${index * 0.15}s`,
          '--from': `translate(${200 - channel.x}px, ${150 - channel.y}px) scale(0.3)`,
        }"
      >
        <g class="a-lift">
          <rect x="-30" y="-30" width="60" height="60" rx="16" class="a-card" />
        </g>
        <template v-if="channel.key === 'mail'">
          <rect x="-15" y="-10" width="30" height="21" rx="3" class="a-stroke" />
          <path d="M-14 -8l14 10 14-10" class="a-stroke" />
        </template>
        <template v-else-if="channel.key === 'push'">
          <rect x="-10" y="-16" width="20" height="32" rx="5" class="ink-stroke" />
          <circle cx="10" cy="-15" r="6" class="a-fill" />
        </template>
        <template v-else-if="channel.key === 'telegram'">
          <path d="M-15 0l29-13-7 27-8-8-7 5 1-9z" class="plane" />
        </template>
        <template v-else>
          <path d="M-15 0l5-12h20l5 12v11h-30z" class="ink-stroke" />
          <path d="M-15 0h8l3 5h8l3-5h8" class="ink-stroke" />
        </template>
      </g>
    </g>

    <!-- The bell, with a clock: reminders come before the shift. -->
    <g transform="translate(200 146)">
      <path d="M-62 -26a44 44 0 0 0 0 52M62 -26a44 44 0 0 1 0 52" class="a-stroke wave" />
      <g class="ring">
        <path
          d="M0 -48c4 0 7 3 7 7v3c16 4 26 18 26 36v22l10 13H-43l10-13V-2c0-18 10-32 26-36v-3c0-4 3-7 7-7z"
          class="a-fill"
        />
        <circle cy="40" r="8" class="a-fill" />
        <path d="M-16 -18c-4 4-6 9-6 15" class="shine" />
      </g>
      <g transform="translate(34 -36)">
        <circle r="14" class="a-card" />
        <path d="M0 -7v7l5 3" class="ink-stroke" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.ink-stroke {
  fill: none;
  stroke: var(--art-ink);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.plane {
  fill: var(--chart-4);
}
.shine {
  fill: none;
  stroke: var(--card);
  stroke-width: 3;
  stroke-linecap: round;
  opacity: 0.6;
}

.ring {
  transform-box: fill-box;
  transform-origin: 50% 0;
  animation: ring 6s ease-in-out infinite;
}
@keyframes ring {
  0%,
  4% {
    transform: none;
  }
  7% {
    transform: rotate(-14deg);
  }
  10% {
    transform: rotate(12deg);
  }
  13% {
    transform: rotate(-9deg);
  }
  16% {
    transform: rotate(6deg);
  }
  19% {
    transform: rotate(-3deg);
  }
  21%,
  100% {
    transform: none;
  }
}

.wave {
  opacity: 0;
  animation: wave 6s ease-out infinite;
}
@keyframes wave {
  0%,
  5% {
    opacity: 0;
  }
  8%,
  18% {
    opacity: 1;
  }
  24%,
  100% {
    opacity: 0;
  }
}

.out {
  animation: out 6s cubic-bezier(0.3, 0.7, 0.4, 1) infinite both;
}
@keyframes out {
  0%,
  18% {
    opacity: 0;
    transform: var(--from);
  }
  20% {
    opacity: 1;
  }
  30% {
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
