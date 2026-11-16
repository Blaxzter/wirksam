<script setup lang="ts">
/**
 * A list as its row and its card name it: the title (which opens the
 * details), "closes in 2 days" or "all taken", where it was shared and by
 * whom, its tasks, and the days it is limited to.
 */
import { computed } from 'vue'

import { MessageSquare } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Badge } from '@/components/ui/badge'

import SharedListStatusBadge from '@/components/shared-lists/SharedListStatusBadge.vue'
import { useSharedListText } from '@/components/shared-lists/sharedListText'

import type { SharedListRow } from '@/client/types.gen'
import { wallClockIn } from '@/lib/shift-time'

const props = defineProps<{
  row: SharedListRow
  /** The event's zone, for "today" on its clock. */
  zone: string
  /** The status pill in front of the title, where there is no status column. */
  withStatus?: boolean
}>()

const emit = defineEmits<{ open: [] }>()

const { t } = useI18n()
const { daysText, inDays } = useSharedListText()

const DAY_MS = 86_400_000

const dimmed = computed(
  () => props.row.effective_status === 'ended' || props.row.effective_status === 'expired',
)

/** The issue strip already says it is about to close; the pill would repeat it. */
const daysLeft = computed<number | null>(() => {
  const { row } = props
  if (!row.expires_soon || row.issue || !row.ends_on) return null
  const today = wallClockIn(props.zone).date
  return Math.round((Date.parse(row.ends_on) - Date.parse(today)) / DAY_MS)
})

const meta = computed(() =>
  [
    props.row.share_note || t('sharedLists.rows.noShareNote'),
    props.row.created_by_name ? t('sharedLists.rows.by', { name: props.row.created_by_name }) : '',
  ]
    .filter(Boolean)
    .join(' · '),
)
</script>

<template>
  <div class="grid min-w-0 gap-1.5 whitespace-normal">
    <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
      <SharedListStatusBadge v-if="props.withStatus" :status="props.row.effective_status" />
      <button
        type="button"
        class="rounded-sm text-left text-[15px] leading-snug font-bold underline-offset-3 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50"
        :class="dimmed ? 'text-muted-foreground' : ''"
        data-list-title
        data-testid="shared-list-title"
        @click="emit('open')"
      >
        {{ props.row.title }}
      </button>
      <Badge
        v-if="daysLeft !== null"
        variant="warning"
        class="rounded-full"
        data-testid="shared-list-expires"
      >
        {{ t('sharedLists.rows.expires', { when: inDays(daysLeft) }) }}
      </Badge>
      <Badge
        v-if="props.row.is_full && props.row.effective_status === 'live'"
        variant="outline"
        class="rounded-full text-muted-foreground"
        data-testid="shared-list-full"
      >
        {{ t('sharedLists.rows.full') }}
      </Badge>
    </div>
    <p class="flex items-start gap-1.5 text-[13px] text-muted-foreground">
      <MessageSquare class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
      <span class="min-w-0">{{ meta }}</span>
    </p>
    <ul class="flex flex-wrap gap-1.5" :aria-label="t('sharedLists.rows.tasksLabel')">
      <li
        v-for="task in props.row.tasks"
        :key="task.id"
        class="max-w-full truncate rounded-md bg-muted px-1.5 py-px text-xs"
      >
        {{ task.name }}
      </li>
      <li
        v-if="props.row.only_days"
        class="rounded-md bg-warning/15 px-1.5 py-px text-xs font-semibold text-warning"
        data-testid="shared-list-only-days"
      >
        {{ t('sharedLists.rows.onlyDays', { days: daysText(props.row.only_days) }) }}
      </li>
    </ul>
  </div>
</template>
