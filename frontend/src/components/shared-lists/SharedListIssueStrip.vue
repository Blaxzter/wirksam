<script setup lang="ts">
/**
 * What a list needs from the people running it, under its row: free places
 * that no open list offers while it is paused or expired ("Fortsetzen",
 * "Wieder öffnen"), or a list about to close with places left ("Verlängern").
 */
import { computed } from 'vue'

import { Clock, TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { ListAction } from '@/stores/sharedLists'

import { Button } from '@/components/ui/button'

import { useSharedListText } from '@/components/shared-lists/sharedListText'
import { issueFix } from '@/components/shared-lists/useSharedListActions'

import type { SharedListIssue } from '@/client/types.gen'
import type { EffectiveStatus } from '@/lib/shared-lists'

const props = defineProps<{
  issue: SharedListIssue
  /** The list's title, which names the button for a screen reader. */
  title: string
  status: EffectiveStatus
  busy?: boolean
  /** The viewer may not reopen or extend lists (`reshareLocked`): the fix is not theirs. */
  locked?: boolean
}>()

const emit = defineEmits<{ fix: [action: ListAction] }>()

const { t } = useI18n()
const { quotedNames, inDays } = useSharedListText()

const fix = computed(() => issueFix({ issue: props.issue, effective_status: props.status }))

const text = computed(() => {
  const { issue } = props
  if (issue.kind === 'expires_soon') {
    return t('sharedLists.issues.expiresSoon', {
      when: inDays(issue.days_left ?? 0),
      places: t('sharedLists.issues.placesLeft', { count: issue.free }, issue.free),
    })
  }
  return t(
    'sharedLists.issues.stranded',
    { count: issue.free, names: quotedNames(issue.task_names) },
    issue.free,
  )
})
</script>

<template>
  <div
    class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 rounded-lg bg-warning/10 py-1.5 pr-1.5 pl-3 text-[13px] whitespace-normal"
    :data-kind="props.issue.kind"
    data-testid="shared-list-issue"
  >
    <component
      :is="props.issue.kind === 'expires_soon' ? Clock : TriangleAlert"
      class="size-4 shrink-0 text-warning"
      aria-hidden="true"
    />
    <p class="min-w-0 flex-1 basis-56">{{ text }}</p>
    <!-- Busy is aria-disabled, so the button keeps focus until the fix lands. -->
    <Button
      v-if="fix"
      size="sm"
      variant="outline"
      class="bg-card aria-disabled:opacity-50 max-sm:h-10"
      :disabled="props.locked"
      :aria-disabled="props.busy || undefined"
      :aria-label="`${t(fix.labelKey)}: ${props.title}`"
      data-testid="shared-list-issue-fix"
      @click="!props.busy && emit('fix', fix.action)"
    >
      {{ t(fix.labelKey) }}
    </Button>
  </div>
</template>
