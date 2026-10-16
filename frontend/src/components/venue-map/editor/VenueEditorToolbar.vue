<script setup lang="ts">
import { type Component, type ComponentPublicInstance, useTemplateRef } from 'vue'

import {
  Check,
  Ellipsis,
  Grid3x3,
  LoaderCircle,
  MousePointer2,
  Pentagon,
  Redo2,
  Spline,
  Square,
  Trees,
  Type,
  Undo2,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { Tool } from '@/composables/useShapeEditor'

import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import HintTooltip from '@/components/utils/HintTooltip.vue'

/**
 * The drawing tools above the editor's canvas: select, rectangle, shape
 * (polygon), line (path), text, decoration (prop), snapping, undo and redo,
 * and whether the last edits are saved yet. Every button names its shortcut (`aria-keyshortcuts`
 * and the tooltip); the shortcuts themselves live in `useShapeEditor`.
 *
 * Below the `lg` breakpoint (the editor puts it under the plan there, in thumb
 * reach) the buttons share the width and are touch-sized, and redo and
 * snapping move into a "More" menu, so everything fits a 360px phone without
 * scrolling. While edits are saving, that menu's button spins.
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
  { tool: 'prop', icon: Trees, key: 'D' },
]

/** Phone layout: share the row, touch height. Desktop keeps `icon-sm`. */
const touch = 'max-lg:h-11 max-lg:w-auto max-lg:min-w-0 max-lg:flex-1'

const isMac = typeof navigator !== 'undefined' && /Mac|iP(hone|ad)/.test(navigator.platform)
const mod = isMac ? '⌘' : 'Ctrl'

// The menu trigger sits inside a HintTooltip, so it anchors to the tooltip,
// not to its own menu: the menu content is told where the button is, or it
// opens off-screen (reka-ui finds an anchor through the nearest popup root).
const moreButton = useTemplateRef<ComponentPublicInstance>('moreButton')
</script>

<template>
  <div
    class="bg-card flex min-w-0 items-center gap-1 rounded-lg border p-1 shadow-xs max-lg:gap-0.5 max-lg:p-0.5 lg:overflow-x-auto"
    role="toolbar"
    :aria-label="t('mapEditor.tools.title')"
    aria-describedby="map-editor-shortcuts"
    data-testid="draw-toolbar"
  >
    <HintTooltip
      v-for="item in TOOLS"
      :key="item.tool"
      :label="`${t(`mapEditor.tools.${item.tool}`)} (${item.key})`"
    >
      <Button
        size="icon-sm"
        :variant="tool === item.tool ? 'default' : 'ghost'"
        :class="touch"
        :aria-label="t(`mapEditor.tools.${item.tool}`)"
        :aria-pressed="tool === item.tool"
        :aria-keyshortcuts="item.key"
        :data-testid="`tool-${item.tool}`"
        @click="emit('set-tool', item.tool)"
      >
        <component :is="item.icon" />
      </Button>
    </HintTooltip>

    <span class="bg-border mx-1 h-5 w-px shrink-0 max-lg:hidden" aria-hidden="true" />

    <HintTooltip :label="`${t('mapEditor.tools.snap')} (G)`">
      <Button
        size="icon-sm"
        :variant="snapEnabled ? 'secondary' : 'ghost'"
        class="max-lg:hidden"
        :aria-label="t('mapEditor.tools.snap')"
        :aria-pressed="snapEnabled"
        aria-keyshortcuts="G"
        data-testid="tool-snap"
        @click="emit('toggle-snap')"
      >
        <Grid3x3 />
      </Button>
    </HintTooltip>
    <!-- A disabled button gets no pointer events, so it has no tooltip either. -->
    <HintTooltip :label="`${t('mapEditor.tools.undo')} (${mod}+Z)`" :disabled="!canUndo">
      <Button
        size="icon-sm"
        variant="ghost"
        :disabled="!canUndo"
        :class="touch"
        :aria-label="t('mapEditor.tools.undo')"
        :aria-keyshortcuts="isMac ? 'Meta+Z' : 'Control+Z'"
        data-testid="tool-undo"
        @click="emit('undo')"
      >
        <Undo2 />
      </Button>
    </HintTooltip>
    <HintTooltip :label="`${t('mapEditor.tools.redo')} (${mod}+Shift+Z)`" :disabled="!canRedo">
      <Button
        size="icon-sm"
        variant="ghost"
        :disabled="!canRedo"
        class="max-lg:hidden"
        :aria-label="t('mapEditor.tools.redo')"
        :aria-keyshortcuts="isMac ? 'Meta+Shift+Z' : 'Control+Shift+Z Control+Y'"
        data-testid="tool-redo"
        @click="emit('redo')"
      >
        <Redo2 />
      </Button>
    </HintTooltip>

    <!-- Phones: redo and snapping, behind one button. -->
    <DropdownMenu>
      <HintTooltip :label="t('mapEditor.tools.more')">
        <DropdownMenuTrigger as-child>
          <Button
            ref="moreButton"
            size="icon-sm"
            variant="ghost"
            class="lg:hidden"
            :class="touch"
            :aria-label="t('mapEditor.tools.more')"
            data-testid="tool-more"
          >
            <LoaderCircle v-if="pending > 0" class="animate-spin" aria-hidden="true" />
            <Ellipsis v-else />
          </Button>
        </DropdownMenuTrigger>
      </HintTooltip>
      <DropdownMenuContent align="end" side="top" :reference="moreButton?.$el">
        <DropdownMenuItem :disabled="!canRedo" data-testid="tool-redo-menu" @select="emit('redo')">
          <Redo2 />
          {{ t('mapEditor.tools.redo') }}
        </DropdownMenuItem>
        <DropdownMenuCheckboxItem
          :model-value="snapEnabled"
          data-testid="tool-snap-menu"
          @update:model-value="emit('toggle-snap')"
        >
          {{ t('mapEditor.tools.snap') }}
        </DropdownMenuCheckboxItem>
      </DropdownMenuContent>
    </DropdownMenu>

    <span
      class="text-muted-foreground ml-auto flex shrink-0 items-center gap-1 px-2 text-xs max-lg:sr-only"
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
