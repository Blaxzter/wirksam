<script setup lang="ts">
/**
 * The emergency stop, asked inline under the toolbar: pause every open list
 * of the event at once. Ticking "people in charge cannot reopen them" also
 * turns sharing off for them, so nobody can undo the stop list by list.
 *
 * It takes focus when it opens, so it is read out; the caller gives focus
 * back to its button when it closes.
 */
import { onMounted, ref, useTemplateRef } from 'vue'

import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useSharedListsStore } from '@/stores/sharedLists'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'

import { toastApiError } from '@/lib/api-errors'

const props = defineProps<{
  /** How many lists are open now. */
  count: number
}>()

const emit = defineEmits<{ close: [] }>()

const { t } = useI18n()
const store = useSharedListsStore()

const box = useTemplateRef<HTMLElement>('box')
const lockManagers = ref(false)
const running = ref(false)

onMounted(() => box.value?.focus())

async function pauseAll() {
  running.value = true
  try {
    const result = await store.pauseAll(lockManagers.value)
    const paused = result.changed.length
    toast.success(t('sharedLists.toasts.pausedAll', { count: paused }, paused))
    if (result.skipped.length > 0) {
      const skipped = result.skipped.length
      toast.warning(t('sharedLists.toasts.bulkSkipped', { count: skipped }, skipped))
    }
    emit('close')
  } catch (error) {
    toastApiError(error)
  } finally {
    running.value = false
  }
}
</script>

<template>
  <div
    ref="box"
    role="alert"
    tabindex="-1"
    class="grid gap-3 rounded-xl border border-destructive/35 bg-destructive/5 p-4 text-sm outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
    data-testid="shared-lists-pause-all-confirm"
  >
    <p>
      <strong>{{ t('sharedLists.pauseAll.title', { count: props.count }, props.count) }}</strong>
      {{ t('sharedLists.pauseAll.text') }}
    </p>
    <label class="flex cursor-pointer items-start gap-2.5">
      <Checkbox
        class="mt-0.5"
        :model-value="lockManagers"
        data-testid="shared-lists-pause-all-lock"
        @update:model-value="(value) => (lockManagers = value === true)"
      />
      <span class="grid gap-0.5">
        <span class="font-medium">{{ t('sharedLists.pauseAll.lockManagers') }}</span>
        <span class="text-xs text-muted-foreground">
          {{ t('sharedLists.pauseAll.lockManagersHint') }}
        </span>
      </span>
    </label>
    <div class="flex flex-wrap gap-2">
      <Button
        variant="destructive"
        size="sm"
        class="max-sm:h-10"
        :disabled="running"
        data-testid="shared-lists-pause-all-confirm-button"
        @click="pauseAll"
      >
        {{ t('sharedLists.pauseAll.confirm') }}
      </Button>
      <Button variant="ghost" size="sm" class="max-sm:h-10" @click="emit('close')">
        {{ t('common.actions.cancel') }}
      </Button>
    </div>
  </div>
</template>
