<script setup lang="ts">
/**
 * Event admins decide whether the people in charge of tasks may share them
 * on lists themselves. Switched off, those people can still pause and end
 * their lists, but not reopen, edit or create one.
 */
import { computed, ref } from 'vue'

import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useSharedListsStore } from '@/stores/sharedLists'

import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

import { toastApiError } from '@/lib/api-errors'

const props = defineProps<{
  /** `managers_share_lists` as the server has it. */
  enabled: boolean
  /** Only event admins see the switch. */
  isAdmin: boolean
}>()

const { t } = useI18n()
const store = useSharedListsStore()

/** What was asked for while the server is being told, so the switch does not jump back. */
const pending = ref<boolean | null>(null)
const shown = computed(() => pending.value ?? props.enabled)

async function change(value: boolean) {
  if (pending.value !== null) return
  pending.value = value
  try {
    await store.setManagersShareLists(value)
    toast.success(t(value ? 'sharedLists.toasts.managersOn' : 'sharedLists.toasts.managersOff'))
  } catch (error) {
    toastApiError(error)
  } finally {
    pending.value = null
  }
}
</script>

<template>
  <div
    v-if="props.isAdmin"
    class="flex items-start justify-between gap-4 rounded-xl border bg-card p-4"
    data-testid="shared-lists-managers"
  >
    <div class="min-w-0 space-y-1">
      <Label for="shared-lists-managers-switch" class="text-[15px] leading-snug font-bold">
        {{ t('sharedLists.managersSwitch.label') }}
      </Label>
      <p id="shared-lists-managers-hint" class="text-sm text-muted-foreground">
        {{ shown ? t('sharedLists.managersSwitch.on') : t('sharedLists.managersSwitch.off') }}
      </p>
    </div>
    <!-- aria-disabled while saving: a disabled switch would drop its focus. -->
    <Switch
      id="shared-lists-managers-switch"
      class="mt-0.5 aria-disabled:opacity-50"
      :model-value="shown"
      :aria-disabled="pending !== null || undefined"
      :aria-busy="pending !== null || undefined"
      aria-describedby="shared-lists-managers-hint"
      data-testid="shared-lists-managers-switch"
      @update:model-value="(value: boolean) => change(value)"
    />
  </div>
</template>
