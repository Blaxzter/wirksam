<script setup lang="ts">
/**
 * "Shared in" for one task: a chip per list that offers it (status dot,
 * opens the list), "on no list", how many lists ended, and the free places
 * that no open list offers, with "Share" when they are on no list at all.
 * A task only a team can book is never shared openly, and says so.
 */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import type { SharedListTaskRow } from '@/client/types.gen'
import type { EffectiveStatus } from '@/lib/shared-lists'

const props = defineProps<{ row: SharedListTaskRow }>()

const emit = defineEmits<{
  open: [listId: string]
  share: [taskId: string]
}>()

const { t } = useI18n()

/** "2 ended", after the chips with a separator. */
const endedText = computed(() => {
  const count = props.row.ended_list_count
  const text = t('sharedLists.tasks.endedCount', { count }, count)
  return props.row.lists.length > 0 ? `· ${text}` : text
})

const DOT: Record<EffectiveStatus, string> = {
  live: 'bg-primary',
  paused: 'bg-warning',
  expired: 'bg-muted-foreground',
  ended: 'bg-muted-foreground',
}
</script>

<template>
  <div
    class="flex min-w-0 flex-wrap items-center gap-1.5 whitespace-normal"
    data-testid="task-shared-in"
  >
    <span v-if="props.row.team" class="text-[13px] text-muted-foreground">
      {{ t('sharedLists.tasks.teamOnly') }}
    </span>
    <template v-else>
      <button
        v-for="chip in props.row.lists"
        :key="chip.id"
        type="button"
        class="inline-flex max-w-full items-center gap-1.5 rounded-full border bg-background py-0.5 pr-2.5 pl-2 text-[12.5px] outline-none hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50"
        :aria-label="
          t('sharedLists.tasks.chipLabel', {
            title: chip.title,
            status: t(`sharedLists.status.${chip.effective_status}`),
          })
        "
        :data-status="chip.effective_status"
        data-testid="task-list-chip"
        @click="emit('open', chip.id)"
      >
        <span class="size-1.5 shrink-0 rounded-full" :class="DOT[chip.effective_status]" />
        <span class="truncate">{{ chip.title }}</span>
      </button>
      <span
        v-if="props.row.lists.length === 0 && props.row.stranded_free === 0"
        class="text-[13px] text-muted-foreground"
      >
        {{ t('sharedLists.tasks.inNoList') }}
      </span>
      <span v-if="props.row.ended_list_count > 0" class="text-[13px] text-muted-foreground">
        {{ endedText }}
      </span>
      <span
        v-if="props.row.stranded_free > 0"
        class="flex basis-full flex-wrap items-baseline gap-x-2.5 gap-y-0.5"
      >
        <span class="text-[13px] font-semibold text-warning" data-testid="task-stranded">
          {{
            t(
              'sharedLists.tasks.stranded',
              { count: props.row.stranded_free },
              props.row.stranded_free,
            )
          }}
        </span>
        <Button
          v-if="props.row.unlisted_free > 0 && props.row.can_share"
          variant="link"
          size="sm"
          class="h-auto p-0 text-[13px]"
          :aria-label="`${t('sharedLists.actions.share')}: ${props.row.name}`"
          data-testid="task-share"
          @click="emit('share', props.row.id)"
        >
          {{ t('sharedLists.actions.share') }}
        </Button>
      </span>
    </template>
  </div>
</template>
