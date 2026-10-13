<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { Clock } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import { NativeSelect } from '@/components/ui/native-select'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import { Textarea } from '@/components/ui/textarea'

import type { EventMemberRead, WorkLogRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const open = defineModel<boolean>('open', { required: true })

const props = defineProps<{
  eventId: string
  /** Who can be picked. Ignored when `userId` or `entry` fixes the volunteer. */
  members: EventMemberRead[]
  /** Preselect and lock the volunteer. */
  userId?: string | null
  /** Edit this entry instead of creating one. */
  entry?: WorkLogRead | null
}>()

const emit = defineEmits<{ saved: [] }>()

const { t } = useI18n()
const { post, patch } = useAuthenticatedClient()

const MAX_HOURS = 24

const memberId = ref('')
const date = ref('')
const hours = ref('')
const note = ref('')
const saving = ref(false)

const isEdit = computed(() => !!props.entry)
const lockedUser = computed(() => props.entry?.user_id ?? props.userId ?? null)

function todayIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

watch(open, (isOpen) => {
  if (!isOpen) return
  memberId.value = lockedUser.value ?? ''
  date.value = props.entry?.date ?? todayIso()
  hours.value = props.entry ? String(props.entry.minutes / 60) : ''
  note.value = props.entry?.description ?? ''
})

/** Accept "1,5" as well as "1.5" — German keyboards type the comma. */
const minutes = computed(() => {
  const value = Number(hours.value.replace(',', '.'))
  return Number.isFinite(value) ? Math.round(value * 60) : NaN
})

const valid = computed(
  () =>
    !!memberId.value &&
    !!date.value &&
    minutes.value > 0 &&
    minutes.value <= MAX_HOURS * 60 &&
    note.value.trim().length > 0,
)

async function save() {
  if (!valid.value) {
    toast.error(t('duties.hours.form.invalid'))
    return
  }
  saving.value = true
  try {
    const body = { date: date.value, minutes: minutes.value, description: note.value.trim() }
    if (props.entry) {
      await patch({ url: `/events/${props.eventId}/work-logs/${props.entry.id}`, body })
      toast.success(t('duties.hours.form.updated'))
    } else {
      await post({
        url: `/events/${props.eventId}/work-logs`,
        body: { ...body, user_id: memberId.value },
      })
      toast.success(t('duties.hours.form.created'))
    }
    open.value = false
    emit('saved')
  } catch (error) {
    toastApiError(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent dialog-class="sm:max-w-md">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle class="flex items-center gap-2">
          <Clock class="h-5 w-5" />
          {{ isEdit ? t('duties.hours.form.editTitle') : t('duties.hours.form.createTitle') }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription class="text-left">
          {{ t('duties.hours.form.description') }}
        </ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="space-y-4 pb-2">
        <div v-if="!lockedUser" class="space-y-2">
          <Label for="work-log-member">{{ t('duties.hours.form.member') }}</Label>
          <NativeSelect id="work-log-member" v-model="memberId" data-testid="work-log-member">
            <option value="">{{ t('duties.hours.form.memberPlaceholder') }}</option>
            <option v-for="m in members" :key="m.user_id" :value="m.user_id">
              {{ m.name ?? m.email }}
            </option>
          </NativeSelect>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-2">
            <Label for="work-log-date">{{ t('duties.hours.form.date') }}</Label>
            <Input id="work-log-date" v-model="date" type="date" data-testid="work-log-date" />
          </div>
          <div class="space-y-2">
            <Label for="work-log-hours">{{ t('duties.hours.form.hours') }}</Label>
            <Input
              id="work-log-hours"
              v-model="hours"
              inputmode="decimal"
              placeholder="1.5"
              data-testid="work-log-hours"
            />
          </div>
        </div>
        <p class="-mt-2 text-xs text-muted-foreground">{{ t('duties.hours.form.hoursHint') }}</p>

        <div class="space-y-2">
          <Label for="work-log-note">{{ t('duties.hours.form.note') }}</Label>
          <Textarea
            id="work-log-note"
            v-model="note"
            :placeholder="t('duties.hours.form.notePlaceholder')"
            maxlength="500"
            rows="2"
            data-testid="work-log-note"
          />
        </div>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter class="sm:justify-start">
        <Button variant="outline" @click="open = false">
          {{ t('common.dialog.confirm.cancelText') }}
        </Button>
        <Button :disabled="saving" data-testid="btn-save-work-log" @click="save">
          {{ t('duties.hours.form.save') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
