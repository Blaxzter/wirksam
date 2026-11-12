<script setup lang="ts">
import type { Component } from 'vue'

import ShiftBoardConcept from '@/components/landing/ShiftBoardConcept.vue'

import type { ArtKind } from '@/lib/content-pages'

import ArtBooking from './art/ArtBooking.vue'
import ArtClone from './art/ArtClone.vue'
import ArtCompare from './art/ArtCompare.vue'
import ArtFestival from './art/ArtFestival.vue'
import ArtInCharge from './art/ArtInCharge.vue'
import ArtMembers from './art/ArtMembers.vue'
import ArtNotify from './art/ArtNotify.vue'
import ArtReports from './art/ArtReports.vue'
import ArtShifts from './art/ArtShifts.vue'
import ArtSteps from './art/ArtSteps.vue'
import ArtTeams from './art/ArtTeams.vue'
import ArtTerminal from './art/ArtTerminal.vue'
import ArtVenue from './art/ArtVenue.vue'
import ArtVouchers from './art/ArtVouchers.vue'

/**
 * The drawing beside a content page's title: what the page is about, drawn
 * from the theme's colours and played as a short loop.
 *
 * It replaced cropped screenshots, which at that size were mostly unreadable
 * text cut off at odd places. The drawings carry no words, so they need no
 * translation and no alt text: the title and lede beside them say it all, and
 * the drawing stays out of the accessibility tree. Each one is drawn in
 * `--art`, the page's colour, which `ContentPageShell` sets.
 *
 * Every drawing is built so that its resting state is the finished picture.
 * With reduced motion the animations are switched off, and that is what shows.
 */
defineProps<{ kind: ArtKind }>()

const ARTS: Record<Exclude<ArtKind, 'roster'>, Component> = {
  shifts: ArtShifts,
  venue: ArtVenue,
  members: ArtMembers,
  inCharge: ArtInCharge,
  teams: ArtTeams,
  booking: ArtBooking,
  notify: ArtNotify,
  vouchers: ArtVouchers,
  reports: ArtReports,
  terminal: ArtTerminal,
  clone: ArtClone,
  steps: ArtSteps,
  festival: ArtFestival,
  compare: ArtCompare,
}
</script>

<template>
  <ShiftBoardConcept
    v-if="kind === 'roster'"
    data-testid="page-art"
    data-art="roster"
    class="mx-auto w-full max-w-md lg:max-w-none"
  />
  <div
    v-else
    data-testid="page-art"
    :data-art="kind"
    aria-hidden="true"
    class="page-art relative overflow-hidden rounded-3xl border bg-card shadow-xl ring-1 ring-black/5"
  >
    <div class="art-canvas absolute inset-0" />
    <component :is="ARTS[kind]" class="relative block h-auto w-full" />
  </div>
</template>

<style>
/*
 * Shared by the drawings in ./art. Unscoped so they can use these classes, and
 * kept under .page-art so nothing else picks them up. Each drawing keeps its own
 * story (what moves when) in scoped keyframes; these are the materials and the
 * loops that run on their own.
 */
.page-art {
  --art-soft: color-mix(in oklab, var(--art) 24%, var(--card));
  --art-edge: color-mix(in oklab, var(--art) 60%, transparent);
  --art-ink: color-mix(in oklab, var(--foreground) 62%, transparent);
  --art-line: color-mix(in oklab, var(--muted-foreground) 28%, transparent);
  --art-ok-soft: color-mix(in oklab, var(--primary) 18%, var(--card));
}

/* Dots on paper, lit from the top right in the page's colour. */
.page-art .art-canvas {
  background:
    radial-gradient(
      circle at 82% 12%,
      color-mix(in oklab, var(--art) 26%, transparent),
      transparent 55%
    ),
    radial-gradient(
      circle at 8% 96%,
      color-mix(in oklab, var(--art) 16%, transparent),
      transparent 50%
    ),
    radial-gradient(
        color-mix(in oklab, var(--muted-foreground) 18%, transparent) 1px,
        transparent 1.5px
      )
      0 0 / 18px 18px;
}

.page-art .a-card {
  fill: var(--card);
  stroke: var(--border);
  stroke-width: 1.5;
}
.page-art .a-muted {
  fill: var(--muted);
}
/* A line of text, drawn as a bar: the drawings say nothing in words. */
.page-art .a-line {
  fill: var(--art-line);
}
.page-art .a-fill {
  fill: var(--art);
}
.page-art .a-soft {
  fill: var(--art-soft);
  stroke: var(--art-edge);
  stroke-width: 1.5;
}
.page-art .a-ok {
  fill: var(--primary);
}
.page-art .a-ok-soft {
  fill: var(--art-ok-soft);
  stroke: color-mix(in oklab, var(--primary) 45%, transparent);
  stroke-width: 1.5;
}
.page-art .a-warn {
  fill: var(--warning);
}
.page-art .a-ink {
  fill: var(--art-ink);
}
.page-art .a-on {
  fill: var(--card);
}
.page-art .a-person {
  fill: color-mix(in oklab, var(--foreground) 42%, transparent);
}
.page-art .a-tick {
  fill: none;
  stroke: var(--card);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.page-art .a-stroke {
  fill: none;
  stroke: var(--art);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.page-art .a-rule {
  fill: none;
  stroke: var(--border);
  stroke-width: 2;
  stroke-linecap: round;
}
.page-art .a-dash {
  fill: none;
  stroke: color-mix(in oklab, var(--muted-foreground) 55%, transparent);
  stroke-width: 2;
  stroke-dasharray: 5 6;
  stroke-linecap: round;
}
.page-art .a-free {
  fill: var(--card);
  stroke: var(--art-edge);
  stroke-width: 1.5;
  stroke-dasharray: 4 3;
}
.page-art .a-lift {
  filter: drop-shadow(0 6px 10px rgb(0 0 0 / 0.08));
}
.page-art .a-box {
  transform-box: fill-box;
  transform-origin: center;
}

@keyframes art-flow {
  to {
    stroke-dashoffset: -22;
  }
}
.page-art .a-flow {
  animation: art-flow 1.1s linear infinite;
}

@keyframes art-pulse {
  from {
    opacity: 0.6;
    transform: scale(0.7);
  }
  to {
    opacity: 0;
    transform: scale(1.9);
  }
}
.page-art .a-pulse {
  transform-box: fill-box;
  transform-origin: center;
  animation: art-pulse 2s ease-out infinite;
}

@keyframes art-float {
  50% {
    transform: translateY(-6px);
  }
}
.page-art .a-float {
  animation: art-float 5s ease-in-out infinite;
}

@keyframes art-sway {
  0%,
  100% {
    transform: rotate(-7deg);
  }
  50% {
    transform: rotate(7deg);
  }
}
.page-art .a-sway {
  transform-box: fill-box;
  transform-origin: 50% 0;
  animation: art-sway 3.2s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .page-art *,
  .page-art *::before,
  .page-art *::after {
    animation: none !important;
  }
}
</style>
