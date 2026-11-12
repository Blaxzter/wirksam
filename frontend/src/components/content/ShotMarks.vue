<script setup lang="ts">
import type { DocMark } from '@/lib/doc-types'

/**
 * The numbered marks on a screenshot, which the text beside it names with the
 * same numbers. Laid over the capture, so a share of its size is a share of
 * this box. Pointing at a mark, here or in the text, outlines the part it marks
 * and dims the rest.
 *
 * Hidden from screen readers: the screenshot's alt text describes it, and the
 * text says in words what each number points at.
 */
defineProps<{
  marks: DocMark[]
  /** The mark being pointed at, here or in the text. */
  active?: string | null
}>()

const emit = defineEmits<{ point: [key: string | null] }>()

const percent = (share: number) => `${(share * 100).toFixed(2)}%`

// Beside its part, where the capture showed nothing a number could cover
// (`placePins` in `scripts/take-screenshots.ts`).
const pinStyle = ({ pin: [x, y] }: DocMark) => ({ left: percent(x), top: percent(y) })

const boxStyle = ({ box: [left, top, width, height] }: DocMark) => ({
  left: percent(left),
  top: percent(top),
  width: percent(width),
  height: percent(height),
})
</script>

<template>
  <span aria-hidden="true" class="shot-marks" data-testid="shot-marks">
    <!-- Every outline before every number, so a dimmed outline never covers a
         number. -->
    <span
      v-for="mark in marks"
      :key="`box-${mark.key}`"
      class="shot-mark-box"
      :class="{ 'is-active': mark.key === active }"
      :style="boxStyle(mark)"
    />
    <span
      v-for="mark in marks"
      :key="mark.key"
      class="shot-mark"
      :class="{ 'is-active': mark.key === active }"
      :data-mark="mark.key"
      :style="pinStyle(mark)"
      @mouseenter="emit('point', mark.key)"
      @mouseleave="emit('point', null)"
    >
      {{ mark.n }}
    </span>
  </span>
</template>

<style scoped>
.shot-marks {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
}

.shot-mark-box {
  position: absolute;
  border-radius: 0.375rem;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.shot-mark-box.is-active {
  opacity: 1;
  outline: 3px solid var(--art, var(--primary));
  outline-offset: 3px;
  box-shadow: 0 0 0 100vmax rgb(0 0 0 / 0.4);
}

.shot-mark {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.25rem;
  height: 1.25rem;
  translate: -50% -50%;
  border-radius: 9999px;
  background: color-mix(in oklab, var(--art, var(--primary)) 30%, var(--card));
  box-shadow:
    0 0 0 2px var(--art, var(--primary)),
    0 2px 8px rgb(0 0 0 / 0.35);
  color: var(--foreground);
  font-size: 0.6875rem;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  pointer-events: auto;
  transition: scale 0.15s ease;
}

.shot-mark.is-active {
  scale: 1.25;
}

@media (prefers-reduced-motion: reduce) {
  .shot-mark,
  .shot-mark-box {
    transition: none;
  }
}
</style>
