<script setup lang="ts">
import { computed } from 'vue'

import { Check, ChevronDown } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/badge/Badge.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import { statusVariant } from '@/lib/status'
import { cn } from '@/lib/utils'

const props = defineProps<{
  status?: string | null
  i18nPrefix: string
  editable?: boolean
  /**
   * A soft rounded pill (tinted green for published, amber for a draft) next
   * to a page title, as on the task page, instead of the solid badge.
   */
  pill?: boolean
}>()

const emit = defineEmits<{
  change: [status: 'draft' | 'published' | 'archived']
}>()

const { t } = useI18n()

const statuses = ['draft', 'published', 'archived'] as const

const label = computed(() => t(`${props.i18nPrefix}.${props.status ?? 'draft'}`))

const PILL_TONES: Record<string, string> = {
  published: 'bg-primary/12 text-primary',
  draft: 'bg-warning/12 text-warning',
}

const pillClass = computed(() =>
  cn(
    'inline-flex min-h-[26px] items-center gap-1 rounded-full px-2.5 text-[13px] font-bold whitespace-nowrap',
    PILL_TONES[props.status ?? 'draft'] ?? 'bg-muted text-muted-foreground',
  ),
)
</script>

<template>
  <span v-bind="$attrs">
    <DropdownMenu v-if="editable">
      <DropdownMenuTrigger as-child>
        <button
          v-if="pill"
          type="button"
          :aria-label="t('common.actions.changeStatus', { status: label })"
          :class="
            cn(
              pillClass,
              'min-h-[30px] cursor-pointer pr-2 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50',
            )
          "
        >
          {{ label }}
          <ChevronDown class="size-3.5" stroke-width="2.5" aria-hidden="true" />
        </button>
        <button v-else class="inline-flex cursor-pointer items-center gap-1">
          <Badge :variant="statusVariant(status)">
            {{ label }}
            <ChevronDown class="ml-1 h-3 w-3" />
          </Badge>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        <DropdownMenuItem
          v-for="s in statuses"
          :key="s"
          :disabled="status === s"
          @click="emit('change', s)"
        >
          <Check v-if="status === s" class="mr-2 h-4 w-4" />
          <span v-else class="mr-2 h-4 w-4" />
          {{ t(`${i18nPrefix}.${s}`) }}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    <span v-else-if="pill" :class="pillClass">{{ label }}</span>
    <Badge v-else :variant="statusVariant(status)">
      {{ label }}
    </Badge>
  </span>
</template>
