<script setup lang="ts">
/**
 * In the print toolbar: why a shared list's QR code would lead nowhere now or
 * soon, and the fix its management page offers (resume, reopen, extend or
 * share again), so nobody hangs up a dead code. Nothing while it is open.
 *
 * A viewer, or a person in charge whom the organisers stopped from sharing,
 * gets the reason without the button the server would refuse. `changed`
 * follows a fix that worked, for the page to load the list again.
 */
import { computed } from 'vue'

import { CalendarClock, Play, Share2 } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { Button } from '@/components/ui/button'

import { useSharedListText } from '@/components/shared-lists/sharedListText'
import {
  canManageList,
  resumeLabelKey,
  useSharedListActions,
} from '@/components/shared-lists/useSharedListActions'

import type { SharedListDetail } from '@/client/types.gen'

const props = defineProps<{
  list: Pick<
    SharedListDetail,
    | 'id'
    | 'title'
    | 'effective_status'
    | 'expires_soon'
    | 'access'
    | 'ends_mode'
    | 'ends_on'
    | 'closes_at'
    | 'event'
  >
  /** The organisers turned sharing off for people in charge. */
  locked: boolean
}>()

const emit = defineEmits<{ changed: [] }>()

const { t } = useI18n()
const router = useRouter()
const { endsText } = useSharedListText()
const { busyId, run } = useSharedListActions()

const status = computed(() => props.list.effective_status)
const busy = computed(() => busyId.value === props.list.id)

const message = computed(() => {
  if (status.value === 'live') {
    return props.list.expires_soon ? t('print.list.closesSoon', { ends: endsText(props.list) }) : ''
  }
  return t(`print.list.${status.value}`)
})

const fix = computed(() => {
  if (!canManageList(props.list) || props.locked) return null
  if (status.value === 'ended') {
    return { action: null, label: t('sharedLists.actions.shareAgain'), icon: Share2 }
  }
  if (status.value === 'live') {
    return {
      action: 'extend' as const,
      label: t('sharedLists.actions.extend'),
      icon: CalendarClock,
    }
  }
  return { action: 'resume' as const, label: t(resumeLabelKey(status.value)), icon: Play }
})

const hint = computed(() => {
  if (props.list.access === 'viewer') return t('print.list.readOnly')
  return props.locked ? t('sharedLists.page.managersOff') : ''
})

async function apply() {
  const action = fix.value?.action
  if (action === undefined || busy.value) return
  if (action === null) {
    // An ended list stays ended: a new one with the same tasks and settings.
    void router.push({
      name: 'shared-list-create',
      params: { eventId: props.list.event.id },
      query: { from: props.list.id },
    })
  } else if (await run(props.list, action)) {
    emit('changed')
  }
}
</script>

<template>
  <div
    v-if="message"
    class="space-y-2 rounded-md border border-warning/50 bg-warning/10 p-2 text-sm"
    role="status"
    data-testid="print-list-status"
  >
    <p>{{ message }}</p>
    <p v-if="hint" class="text-xs text-muted-foreground">{{ hint }}</p>
    <Button
      v-if="fix"
      size="sm"
      class="w-full aria-disabled:opacity-50"
      :aria-disabled="busy || undefined"
      data-testid="print-list-fix"
      @click="apply"
    >
      <component :is="fix.icon" aria-hidden="true" />
      {{ fix.label }}
    </Button>
  </div>
</template>
