<script setup lang="ts">
import { Check, ChevronDown } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/badge/Badge.vue'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

import { statusVariant } from '@/lib/status'

defineProps<{
  status?: string | null
  i18nPrefix: string
  editable?: boolean
}>()

const emit = defineEmits<{
  change: [status: 'draft' | 'published' | 'archived']
}>()

const { t } = useI18n()

const statuses = ['draft', 'published', 'archived'] as const
</script>

<template>
  <span v-bind="$attrs">
    <DropdownMenu v-if="editable">
      <DropdownMenuTrigger as-child>
        <button class="inline-flex cursor-pointer items-center gap-1">
          <Badge :variant="statusVariant(status)">
            {{ t(`${i18nPrefix}.${status ?? 'draft'}`) }}
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
    <Badge v-else :variant="statusVariant(status)">
      {{ t(`${i18nPrefix}.${status ?? 'draft'}`) }}
    </Badge>
  </span>
</template>
