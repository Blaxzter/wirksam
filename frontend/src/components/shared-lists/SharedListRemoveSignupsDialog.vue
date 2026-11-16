<script setup lang="ts">
/**
 * Taking people off a list: one sign-up, the ticked ones, or one and every
 * newer one (the clean-up after a wave of made-up sign-ups). It says what
 * happens, asks whether to tell them by email (on by default, off for spam,
 * so typed addresses are not written to) and lets event admins delete the
 * people's data at the same time. Someone who confirmed their address has
 * every sign-up made with it pooled under it, perhaps other people's, and
 * those go too: the dialog says how many before the box is ticked, and the
 * toast counts them.
 *
 * Once something was taken off, the control that opened the dialog may be
 * gone with its row, so the dialog asks the parent (`refocus`) where focus
 * goes instead of handing it back to nothing.
 */
import { computed, ref, watch } from 'vue'

import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useSharedListsStore } from '@/stores/sharedLists'

import { useFormatters } from '@/composables/useFormatters'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import type { SharedListSignupRemoveRequest } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { parseServerDate } from '@/lib/server-time'

export type RemoveTarget =
  | {
      kind: 'bookings'
      bookingIds: string[]
      /** A single sign-up, named in the title and the text: who, from what, when. */
      one?: { name: string; task: string; when: string }
      /** Sign-ups beyond these that deleting the data takes along (`pooledBeyond`). */
      pooled: number
    }
  | {
      kind: 'since'
      /** The sign-up's `created_at`, naive UTC as the server sent it. */
      createdAt: string
    }

const props = defineProps<{
  listId: string
  target: RemoveTarget | null
  /** Event admins may also erase the people's data. */
  canErase: boolean
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  done: []
  /** The dialog has closed after a removal: focus is the parent's to place. */
  refocus: []
}>()

const { t } = useI18n()
const { formatDateTime } = useFormatters()
const store = useSharedListsStore()

const notify = ref(true)
const erase = ref(false)
const running = ref(false)
/** Something was taken off: the row that opened the dialog may be gone. */
let finished = false

watch(open, (now) => {
  if (!now) return
  notify.value = true
  erase.value = false
  finished = false
})

function onCloseAutoFocus(event: Event) {
  if (!finished) return
  finished = false
  event.preventDefault()
  emit('refocus')
}

/** How many people the wording is about; "since" may be several. */
const many = computed(() =>
  props.target?.kind === 'bookings' ? props.target.bookingIds.length : 2,
)

const pooled = computed(() => (props.target?.kind === 'bookings' ? props.target.pooled : 0))

const title = computed(() => {
  const target = props.target
  if (!target) return ''
  if (target.kind === 'since') return t('sharedLists.remove.titleSince')
  if (target.one) {
    return t('sharedLists.remove.titleOne', { name: target.one.name, task: target.one.task })
  }
  const count = target.bookingIds.length
  return t('sharedLists.remove.titleMany', { count }, count)
})

const text = computed(() => {
  const target = props.target
  if (!target) return ''
  if (target.kind === 'bookings') {
    return target.one
      ? t('sharedLists.remove.textOne', { when: target.one.when })
      : t('sharedLists.remove.text', target.bookingIds.length)
  }
  const since = parseServerDate(target.createdAt)
  return t('sharedLists.remove.sinceText', {
    when: since ? formatDateTime(since.toISOString()) : target.createdAt,
  })
})

function body(target: RemoveTarget): SharedListSignupRemoveRequest {
  const options = { notify: notify.value, erase: props.canErase && erase.value }
  return target.kind === 'bookings'
    ? { booking_ids: target.bookingIds, ...options }
    : { created_since: target.createdAt, ...options }
}

async function submit() {
  if (!props.target || running.value) return
  running.value = true
  try {
    const result = await store.removeSignups(props.listId, body(props.target))
    const removed = result.removed.length + result.also_removed
    const skipped = result.skipped.length
    if (removed > 0) toast.success(t('sharedLists.toasts.removed', { count: removed }, removed))
    if (result.erased_guests > 0) {
      const erased = result.erased_guests
      toast.success(t('sharedLists.toasts.erased', { count: erased }, erased))
    }
    if (skipped > 0)
      toast.warning(t('sharedLists.toasts.removeSkipped', { count: skipped }, skipped))
    if (removed === 0 && skipped === 0) toast.info(t('sharedLists.toasts.nothingRemoved'))
    finished = true
    open.value = false
    emit('done')
  } catch (error) {
    toastApiError(error)
  } finally {
    running.value = false
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent
      priority
      dialog-class="sm:max-w-md"
      data-testid="shared-list-remove-dialog"
      @close-auto-focus="onCloseAutoFocus"
    >
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle class="text-lg font-bold">{{ title }}</ResponsiveDialogTitle>
        <ResponsiveDialogDescription>{{ text }}</ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="grid gap-3 pb-3 text-sm">
        <label class="flex cursor-pointer items-start gap-2.5">
          <Checkbox
            class="mt-0.5"
            :model-value="notify"
            data-testid="shared-list-remove-notify"
            @update:model-value="(value) => (notify = value === true)"
          />
          <span class="grid gap-0.5">
            <span class="font-medium">{{ t('sharedLists.remove.notify') }}</span>
            <span class="text-xs text-muted-foreground">{{
              t('sharedLists.remove.notifyHint')
            }}</span>
          </span>
        </label>
        <label v-if="props.canErase" class="flex cursor-pointer items-start gap-2.5">
          <Checkbox
            class="mt-0.5"
            :model-value="erase"
            data-testid="shared-list-remove-erase"
            @update:model-value="(value) => (erase = value === true)"
          />
          <span class="grid gap-0.5">
            <span class="font-medium">{{ t('sharedLists.remove.erase', many) }}</span>
            <span class="text-xs text-muted-foreground" data-testid="shared-list-remove-erase-hint">
              {{ t('sharedLists.remove.eraseHint') }} {{ t('sharedLists.remove.eraseVouchers') }}
            </span>
            <span
              v-if="pooled > 0"
              class="text-xs font-medium text-destructive"
              data-testid="shared-list-remove-erase-pooled"
            >
              {{ t('sharedLists.remove.erasePooled', { n: pooled }, pooled) }}
            </span>
          </span>
        </label>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter>
        <Button variant="outline" :disabled="running" @click="open = false">
          {{ t('common.actions.cancel') }}
        </Button>
        <!-- aria-disabled while it runs, so a refusal leaves focus where it was. -->
        <Button
          variant="destructive"
          class="aria-disabled:opacity-50"
          :disabled="!props.target"
          :aria-disabled="running || undefined"
          data-testid="shared-list-remove-confirm"
          @click="submit"
        >
          {{ t('sharedLists.actions.remove') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
