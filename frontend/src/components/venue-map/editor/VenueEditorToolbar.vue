<script setup lang="ts">
import type { Component } from 'vue'

import {
  Check,
  Grid3x3,
  LoaderCircle,
  MousePointer2,
  Pentagon,
  Redo2,
  Spline,
  Square,
  Type,
  Undo2,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { Tool } from '@/composables/useShapeEditor'

import { Button } from '@/components/ui/button'

/**
 * The drawing tools above the editor's canvas: select, rectangle, shape
 * (polygon), line (path), text, snapping, undo and redo, and whether the last
 * edits are saved yet. Every button names its shortcut (`aria-keyshortcuts`
 * and the tooltip); the shortcuts themselves live in `useShapeEditor`.
 */
defineProps<{
  tool: Tool
  snapEnabled: boolean
  canUndo: boolean
  canRedo: boolean
  /** Edits not yet confirmed by the server. */
  pending: number
}>()

const emit = defineEmits<{
  'set-tool': [tool: Tool]
  'toggle-snap': []
  undo: []
  redo: []
}>()

const { t } = useI18n()

const TOOLS: { tool: Tool; icon: Component; key: string }[] = [
  { tool: 'select', icon: MousePointer2, key: 'V' },
  { tool: 'rect', icon: Square, key: 'R' },
  { tool: 'polygon', icon: Pentagon, key: 'P' },
  { tool: 'path', icon: Spline, key: 'L' },
  { tool: 'label', icon: Type, key: 'T' },
]

const isMac = typeof navigator !== 'undefined' && /Mac|iP(hone|ad)/.test(navigator.platform)
const mod = isMac ? '⌘' : 'Ctrl'
</script>

<template>
  <div
    class="bg-card flex min-w-0 items-center gap-1 overflow-x-auto rounded-lg border p-1 shadow-xs"
    role="toolbar"
    :aria-label="t('mapEditor.tools.title')"
    aria-describedby="map-editor-shortcuts"
    data-testid="draw-toolbar"
  >
    <Button
      v-for="item in TOOLS"
      :key="item.tool"
      size="icon-sm"
      :variant="tool === item.tool ? 'default' : 'ghost'"
      :aria-label="t(`mapEditor.tools.${item.tool}`)"
      :title="`${t(`mapEditor.tools.${item.tool}`)} (${item.key})`"
      :aria-pressed="tool === item.tool"
      :aria-keyshortcuts="item.key"
      :data-testid="`tool-${item.tool}`"
      @click="emit('set-tool', item.tool)"
    >
      <component :is="item.icon" />
    </Button>

    <span class="bg-border mx-1 h-5 w-px shrink-0" aria-hidden="true" />

    <Button
      size="icon-sm"
      :variant="snapEnabled ? 'secondary' : 'ghost'"
      :aria-label="t('mapEditor.tools.snap')"
      :title="`${t('mapEditor.tools.snap')} (G)`"
      :aria-pressed="snapEnabled"
      aria-keyshortcuts="G"
      data-testid="tool-snap"
      @click="emit('toggle-snap')"
    >
      <Grid3x3 />
    </Button>
    <Button
      size="icon-sm"
      variant="ghost"
      :disabled="!canUndo"
      :aria-label="t('mapEditor.tools.undo')"
      :title="`${t('mapEditor.tools.undo')} (${mod}+Z)`"
      :aria-keyshortcuts="isMac ? 'Meta+Z' : 'Control+Z'"
      data-testid="tool-undo"
      @click="emit('undo')"
    >
      <Undo2 />
    </Button>
    <Button
      size="icon-sm"
      variant="ghost"
      :disabled="!canRedo"
      :aria-label="t('mapEditor.tools.redo')"
      :title="`${t('mapEditor.tools.redo')} (${mod}+Shift+Z)`"
      :aria-keyshortcuts="isMac ? 'Meta+Shift+Z' : 'Control+Shift+Z Control+Y'"
      data-testid="tool-redo"
      @click="emit('redo')"
    >
      <Redo2 />
    </Button>

    <span
      class="text-muted-foreground ml-auto flex shrink-0 items-center gap-1 px-2 text-xs"
      role="status"
      data-testid="draw-save-state"
    >
      <template v-if="pending > 0">
        <LoaderCircle class="size-3.5 animate-spin" aria-hidden="true" />
        <span>{{ t('mapEditor.draw.saving') }}</span>
      </template>
      <template v-else>
        <Check class="size-3.5" aria-hidden="true" />
        <span class="sr-only sm:not-sr-only">{{ t('mapEditor.draw.saved') }}</span>
      </template>
    </span>
    <p id="map-editor-shortcuts" class="sr-only">{{ t('mapEditor.tools.shortcutsHint') }}</p>
  </div>
</template>
