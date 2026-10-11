<script setup lang="ts">
import { computed } from 'vue'

import { useColorMode } from '@vueuse/core'
import { Monitor, Moon, Sun } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { type Palette, usePalette } from '@/composables/usePalette'

import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

import ThemePreview from '@/components/layout/ThemePreview.vue'

const { t } = useI18n()
const mode = useColorMode()
const palette = usePalette()

withDefaults(
  defineProps<{
    variant?: 'ghost' | 'outline' | 'default'
    size?: 'sm' | 'default' | 'icon'
  }>(),
  {
    variant: 'ghost',
    size: 'sm',
  },
)

const palettes: { id: Palette; label: string; description: string }[] = [
  {
    id: 'default',
    label: t('user.settings.appearance.theme.default'),
    description: t('user.settings.appearance.theme.defaultDescription'),
  },
  {
    id: 'classic',
    label: t('user.settings.appearance.theme.classic'),
    description: t('user.settings.appearance.theme.classicDescription'),
  },
]

const modes = [
  { id: 'light' as const, label: t('user.settings.appearance.mode.light'), icon: Sun },
  { id: 'dark' as const, label: t('user.settings.appearance.mode.dark'), icon: Moon },
  { id: 'auto' as const, label: t('user.settings.appearance.mode.system'), icon: Monitor },
]

/** Resolve auto → actual mode for previewing the palette tile. */
const previewMode = computed<'light' | 'dark'>(() => {
  if (mode.value === 'dark') return 'dark'
  if (mode.value === 'light') return 'light'
  return typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
})
</script>

<template>
  <Popover>
    <PopoverTrigger as-child>
      <Button
        :variant="variant"
        :size="size"
        :aria-label="t('preauth.layout.navigation.appearance')"
      >
        <!-- Picked by CSS from the `dark` class, not by `previewMode`: the
             prerendered page cannot know the visitor's theme, and the inline
             script in index.html sets that class before the first paint. -->
        <Sun class="h-4 w-4 dark:hidden" />
        <Moon class="hidden h-4 w-4 dark:block" />
      </Button>
    </PopoverTrigger>
    <PopoverContent class="w-72 p-4" align="end" :side-offset="8">
      <div class="space-y-4">
        <!-- Theme tiles -->
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            {{ t('user.settings.appearance.theme.title') }}
          </p>
          <div class="grid grid-cols-2 gap-2">
            <button
              v-for="p in palettes"
              :key="p.id"
              type="button"
              class="group flex flex-col items-stretch gap-2 rounded-lg p-2 text-left transition-colors hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              :class="palette === p.id ? 'bg-accent' : ''"
              @click="palette = p.id"
            >
              <ThemePreview
                :palette="p.id"
                :mode="previewMode"
                size="sm"
                :selected="palette === p.id"
                class="mx-auto"
              />
              <span class="text-xs font-medium leading-tight">{{ p.label }}</span>
            </button>
          </div>
        </div>

        <!-- Mode picker -->
        <div>
          <p class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            {{ t('user.settings.appearance.mode.title') }}
          </p>
          <div class="grid grid-cols-3 gap-1 rounded-md bg-muted p-1">
            <button
              v-for="m in modes"
              :key="m.id"
              type="button"
              class="flex items-center justify-center gap-1.5 rounded-sm py-1.5 text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              :class="
                mode === m.id
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              "
              @click="mode = m.id"
            >
              <component :is="m.icon" class="h-3.5 w-3.5" />
              {{ m.label }}
            </button>
          </div>
        </div>
      </div>
    </PopoverContent>
  </Popover>
</template>
