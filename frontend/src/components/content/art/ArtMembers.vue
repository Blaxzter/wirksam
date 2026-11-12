<script setup lang="ts">
/**
 * Invitations and roles: an invitation flies to the event, and people join
 * around it. One of them owns the event, two organise it.
 */
const people = [
  { x: 74, y: 84, tint: 'tint-2', role: 'organiser' },
  { x: 62, y: 204, tint: 'tint-4', role: '' },
  { x: 328, y: 80, tint: 'tint-1', role: 'owner' },
  { x: 340, y: 200, tint: 'tint-3', role: 'organiser' },
  { x: 200, y: 256, tint: 'tint-2', role: '' },
] as const
</script>

<template>
  <svg viewBox="0 0 400 300" focusable="false">
    <path
      v-for="(person, index) in people"
      :key="`link-${index}`"
      :d="`M200 150L${person.x} ${person.y}`"
      pathLength="1"
      class="link"
      :style="{ animationDelay: `${index * 0.1}s` }"
    />

    <!-- The event, as a calendar page. -->
    <g class="a-lift">
      <rect x="150" y="98" width="100" height="104" rx="18" class="a-card" />
    </g>
    <path d="M150 116a18 18 0 0 1 18-18h64a18 18 0 0 1 18 18v12H150z" class="a-fill" />
    <rect x="172" y="88" width="7" height="18" rx="3.5" class="a-ink" />
    <rect x="221" y="88" width="7" height="18" rx="3.5" class="a-ink" />
    <g v-for="cell in 6" :key="cell">
      <rect
        :x="166 + ((cell - 1) % 3) * 24"
        :y="142 + Math.floor((cell - 1) / 3) * 24"
        width="18"
        height="16"
        rx="5"
        :class="cell === 5 ? 'a-soft' : 'a-muted'"
      />
    </g>

    <g
      v-for="(person, index) in people"
      :key="`person-${index}`"
      :transform="`translate(${person.x} ${person.y})`"
    >
      <g class="join" :style="{ animationDelay: `${index * 0.1}s` }">
        <circle r="25" :class="person.tint" class="face" />
        <circle cy="-6" r="8" class="a-person" />
        <path d="M-14 15a14 12 0 0 1 28 0z" class="a-person" />
      </g>
      <g v-if="person.role === 'owner'" class="badge" transform="translate(19 -19)">
        <circle r="11" class="a-fill" />
        <path d="M-6 4l-1-8 4.5 3.5L0 -5l2.5 4.5L7 -4l-1 8z" class="a-on" />
      </g>
      <g v-else-if="person.role === 'organiser'" class="badge" transform="translate(19 -19)">
        <circle r="9" class="a-ok" />
        <path d="M-4 0l3 3 5-6" class="a-tick" />
      </g>
    </g>

    <!-- The invitation on its way. -->
    <g transform="translate(200 150)">
      <g class="letter">
        <rect x="-24" y="-16" width="48" height="32" rx="6" class="a-card" />
        <path d="M-21 -12l21 15 21-15" class="a-stroke" />
      </g>
    </g>
  </svg>
</template>

<style scoped>
.face {
  stroke: var(--card);
  stroke-width: 3;
}
.tint-1 {
  fill: color-mix(in oklab, var(--art) 34%, var(--card));
}
.tint-2 {
  fill: color-mix(in oklab, var(--chart-4) 30%, var(--card));
}
.tint-3 {
  fill: color-mix(in oklab, var(--chart-3) 40%, var(--card));
}
.tint-4 {
  fill: color-mix(in oklab, var(--chart-1) 28%, var(--card));
}
.link {
  fill: none;
  stroke: var(--art-edge);
  stroke-width: 2;
  stroke-dasharray: 1;
  animation: link 8s ease-out infinite both;
}
@keyframes link {
  0%,
  19% {
    stroke-dashoffset: 1;
    opacity: 1;
  }
  27% {
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

.join {
  transform-box: fill-box;
  transform-origin: center;
  animation: join 8s ease-out infinite both;
}
@keyframes join {
  0%,
  23% {
    opacity: 0;
    transform: scale(0.4);
  }
  28% {
    opacity: 1;
    transform: scale(1.08);
  }
  31% {
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

.badge {
  animation: badge 8s ease-out infinite both;
}
@keyframes badge {
  0%,
  35% {
    opacity: 0;
  }
  39%,
  84% {
    opacity: 1;
  }
  90%,
  100% {
    opacity: 0;
  }
}

.letter {
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
  animation: letter 8s ease-in-out infinite;
}
@keyframes letter {
  0% {
    opacity: 0;
    transform: translate(-160px, 20px) rotate(-14deg);
  }
  5% {
    opacity: 1;
  }
  16% {
    opacity: 1;
    transform: none;
  }
  21% {
    opacity: 0;
    transform: scale(0.4);
  }
  100% {
    opacity: 0;
  }
}
</style>
