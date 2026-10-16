<script setup lang="ts">
import { type FunctionalComponent, computed, h } from 'vue'

import { type GlyphPart, LINE_PAINTS, propGlyph, propPaintClass } from '@/lib/venue-decor'

/**
 * One decoration glyph (tree, bench, tent, …) as SVG, in its 48-unit local
 * frame. Meant for an `<svg>`: the map passes plan-unit transforms from
 * `propPlacement`, the editor palette draws it bare in a
 * `viewBox="-26 -26 52 52"`.
 *
 * The shadow goes first, under its own transform (offset in world space), then
 * the body. Colours come from `.vp-<paint>` in `index.css`.
 */
const props = withDefaults(
  defineProps<{
    prop: string
    transform?: string
    shadowTransform?: string
    showShadow?: boolean
  }>(),
  { transform: undefined, shadowTransform: undefined, showShadow: true },
)

const glyph = computed(() => propGlyph(props.prop))

const Part: FunctionalComponent<{ part: GlyphPart }> = ({ part }) => {
  const attrs: Record<string, string | number> = { class: propPaintClass(part.paint) }
  switch (part.el) {
    case 'circle':
      if (part.cx) attrs.cx = part.cx
      if (part.cy) attrs.cy = part.cy
      attrs.r = part.r
      break
    case 'ellipse':
      if (part.cx) attrs.cx = part.cx
      if (part.cy) attrs.cy = part.cy
      attrs.rx = part.rx
      attrs.ry = part.ry
      break
    case 'rect':
      attrs.x = part.x
      attrs.y = part.y
      attrs.width = part.width
      attrs.height = part.height
      if (part.rx) attrs.rx = part.rx
      if (part.rotate) attrs.transform = `rotate(${part.rotate})`
      break
    case 'path':
      attrs.d = part.d
      if (part.rotate) attrs.transform = `rotate(${part.rotate})`
      if (LINE_PAINTS.has(part.paint)) attrs['stroke-width'] = part.strokeWidth ?? 1
      break
  }
  return h(part.el, attrs)
}
Part.props = ['part']
</script>

<template>
  <g class="venue-prop" :data-prop="prop">
    <g
      v-if="showShadow && glyph.shadow.length"
      class="vp-shadows"
      :transform="shadowTransform ?? transform"
    >
      <Part v-for="(part, i) in glyph.shadow" :key="i" :part="part" />
    </g>
    <g :transform="transform">
      <Part v-for="(part, i) in glyph.body" :key="i" :part="part" />
    </g>
  </g>
</template>
