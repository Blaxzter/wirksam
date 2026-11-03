<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { TriangleAlert } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import Label from '@/components/ui/label/Label.vue'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import Separator from '@/components/ui/separator/Separator.vue'
import Switch from '@/components/ui/switch/Switch.vue'

import type { EventRead, TaskRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

/**
 * "Voucher rules" in the event settings' Vouchers tab, for organisers: two
 * rules that hold for every task of the event, so they are set once here and
 * not on each task.
 *
 * - Who may redeem without a code (pick the person from the list): also
 *   whoever is on shift at a place that takes vouchers (the default), or only
 *   organisers and the people in charge.
 * - Whether people in charge may add, move and delete the shifts of tasks that
 *   earn vouchers. Off by default, since every extra shift earns vouchers.
 *
 * Nothing is sent until "Save", which patches only these two fields.
 */
type ManualRedeem = NonNullable<EventRead['voucher_manual_redeem']>

const props = defineProps<{
  event: EventRead
  /** The event's tasks, for the list of places that take vouchers. */
  tasks: TaskRead[]
}>()

const emit = defineEmits<{ updated: [event: EventRead] }>()

const { t } = useI18n()
const { patch } = useAuthenticatedClient()
const authStore = useAuthStore()

const manual = ref<ManualRedeem>('on_shift')
const managersEditShifts = ref(false)
const saving = ref(false)

const savedManual = computed<ManualRedeem>(() => props.event.voucher_manual_redeem ?? 'on_shift')
const savedManagersEditShifts = computed(() => props.event.managers_edit_voucher_shifts ?? false)

watch(
  [savedManual, savedManagersEditShifts],
  ([m, s]) => {
    manual.value = m
    managersEditShifts.value = s
  },
  { immediate: true },
)

const dirty = computed(
  () =>
    manual.value !== savedManual.value ||
    managersEditShifts.value !== savedManagersEditShifts.value,
)

/** The radio group's model is a plain string; only our two values come back. */
function setManual(value: unknown) {
  if (value === 'on_shift' || value === 'in_charge') manual.value = value
}

/** Places that take vouchers, as links, so the rule above reads concretely. */
const points = computed(() =>
  props.tasks.filter((task) => task.is_voucher_point && task.status !== 'archived'),
)

const options = computed(() => [
  {
    value: 'on_shift' as const,
    title: t('vouchers.eventSettings.manualOnShift'),
    hint: t('vouchers.eventSettings.manualOnShiftHint'),
  },
  {
    value: 'in_charge' as const,
    title: t('vouchers.eventSettings.manualInCharge'),
    hint: t('vouchers.eventSettings.manualInChargeHint'),
  },
])

async function save() {
  if (!dirty.value || saving.value) return
  saving.value = true
  try {
    const res = await patch<{ data: EventRead }>({
      url: `/events/${props.event.id}`,
      body: {
        voucher_manual_redeem: manual.value,
        managers_edit_voucher_shifts: managersEditShifts.value,
      },
    })
    toast.success(t('vouchers.eventSettings.saved'))
    emit('updated', res.data)
    void authStore.refreshSelectedEvent(props.event.id)
  } catch (error) {
    toastApiError(error)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Card class="rounded-[20px] sm:rounded-[22px]" data-testid="section-event-voucher-rules">
    <CardHeader>
      <CardTitle class="text-[17px] leading-snug font-bold sm:text-lg">
        {{ t('vouchers.eventSettings.title') }}
      </CardTitle>
      <CardDescription class="max-sm:hidden">
        {{ t('vouchers.eventSettings.description') }}
      </CardDescription>
    </CardHeader>

    <CardContent class="space-y-5">
      <!-- Who may pick the person instead of scanning a code -->
      <div class="space-y-3">
        <div class="space-y-1">
          <h3 id="voucher-manual-title" class="text-[15px] font-bold">
            {{ t('vouchers.eventSettings.manualTitle') }}
          </h3>
          <p id="voucher-manual-hint" class="text-sm text-muted-foreground">
            {{ t('vouchers.eventSettings.manualHint') }}
          </p>
        </div>

        <RadioGroup
          :model-value="manual"
          aria-labelledby="voucher-manual-title"
          aria-describedby="voucher-manual-hint"
          class="grid gap-3 sm:grid-cols-2"
          data-testid="voucher-manual-redeem"
          @update:model-value="setManual"
        >
          <Label
            v-for="option in options"
            :key="option.value"
            :for="`voucher-manual-${option.value}`"
            class="flex cursor-pointer items-start gap-3 rounded-xl border p-3.5 font-normal transition-colors has-[[data-state=checked]]:border-primary has-[[data-state=checked]]:bg-primary/5 has-[[data-state=checked]]:ring-1 has-[[data-state=checked]]:ring-primary"
          >
            <RadioGroupItem
              :id="`voucher-manual-${option.value}`"
              :value="option.value"
              class="mt-0.5"
              :data-testid="`voucher-manual-${option.value}`"
            />
            <span class="space-y-1">
              <span class="block text-[15px] font-bold leading-snug">{{ option.title }}</span>
              <span class="block text-[13px] leading-snug text-foreground/80">{{ option.hint }}</span>
              <span
                v-if="option.value === 'on_shift' && manual === 'on_shift'"
                class="flex gap-1.5 text-xs leading-snug text-warning"
                data-testid="voucher-manual-on-shift-warning"
              >
                <TriangleAlert class="mt-px size-3.5 shrink-0" aria-hidden="true" />
                {{ t('vouchers.eventSettings.manualOnShiftWarning') }}
              </span>
            </span>
          </Label>
        </RadioGroup>

        <p
          class="flex flex-wrap items-center gap-1.5 text-[13px] text-muted-foreground"
          data-testid="voucher-points"
        >
          <span>{{ t('vouchers.eventSettings.points') }}</span>
          <template v-if="points.length > 0">
            <RouterLink
              v-for="point in points"
              :key="point.id"
              :to="{ name: 'task-detail', params: { eventId: point.id } }"
              class="rounded-full bg-muted px-2.5 py-0.5 font-semibold text-foreground/80 transition-colors hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {{ point.name }}
            </RouterLink>
          </template>
          <span v-else>{{ t('vouchers.eventSettings.noPoints') }}</span>
          <span>· {{ t('vouchers.eventSettings.pointsWhere') }}</span>
        </p>
      </div>

      <Separator />

      <!-- May people in charge change the shifts of tasks that earn vouchers? -->
      <div class="flex items-start justify-between gap-4">
        <div class="min-w-0 space-y-1">
          <Label for="voucher-managers-edit-shifts" class="text-[15px] font-bold leading-snug">
            {{ t('vouchers.eventSettings.shiftsTitle') }}
          </Label>
          <p
            id="voucher-managers-edit-shifts-hint"
            class="text-sm text-muted-foreground"
            data-testid="voucher-managers-edit-shifts-hint"
          >
            {{
              managersEditShifts
                ? t('vouchers.eventSettings.shiftsOn')
                : t('vouchers.eventSettings.shiftsOff')
            }}
          </p>
        </div>
        <Switch
          id="voucher-managers-edit-shifts"
          :model-value="managersEditShifts"
          aria-describedby="voucher-managers-edit-shifts-hint"
          class="mt-0.5"
          data-testid="switch-managers-edit-voucher-shifts"
          @update:model-value="(v: boolean) => (managersEditShifts = v)"
        />
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
        <p class="min-w-0 flex-1 basis-80 text-xs text-muted-foreground">
          {{ t('vouchers.admin.afterEventHint') }}
        </p>
        <Button
          class="h-11 rounded-xl px-5 font-bold max-sm:h-12 max-sm:w-full"
          :disabled="!dirty || saving"
          data-testid="btn-save-voucher-rules"
          @click="save"
        >
          {{ saving ? t('common.states.saving') : t('common.actions.save') }}
        </Button>
      </div>
    </CardContent>
  </Card>
</template>
