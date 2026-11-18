<script setup lang="ts">
/**
 * The shifts a shared list offers, by day: what, when and where, how many
 * places are free, and the button to sign up for one.
 *
 * Names appear only while the list shows first names, and then only those the
 * server sends: guests who were told so when they signed up. Everyone else on
 * the shift is a number.
 *
 * A shift whose task gives vouchers says how many: signing up here earns them
 * as well.
 */
import { useId } from 'vue'

import { Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import type { PublicDay, PublicShift } from '@/client/types.gen'
import { LONG_DAY, dayAndTime } from '@/lib/guest-signup'

withDefaults(
  defineProps<{
    days: PublicDay[]
    showNames: boolean
    /** The organisers' preview: no buttons, nothing to pick. */
    readonly?: boolean
    /** `p` inside the preview, which is a picture of the page and not part of the outline. */
    dayHeadingTag?: 'h2' | 'p'
  }>(),
  { readonly: false, dayHeadingTag: 'h2' },
)

const emit = defineEmits<{ pick: [shift: PublicShift, date: string] }>()

const { t } = useI18n()
const { formatDateLabel, formatTimeRange } = useFormatters()
const uid = useId()

function whenAndWhere(shift: PublicShift): string {
  return [formatTimeRange(shift.start_time, shift.end_time), shift.location]
    .filter(Boolean)
    .join(' · ')
}

function namesLine(shift: PublicShift): string {
  const names = (shift.names ?? []).join(', ')
  const others = shift.others_count ?? 0
  return others > 0
    ? t('guestSignup.list.namesAndOthers', { names, count: others }, others)
    : t('guestSignup.list.names', { names })
}

/**
 * Every button reads "Sign up", so each names its shift for a screen reader.
 * The visible word comes first (`pickLabel` starts with it), so voice control
 * still finds the button by what it says.
 */
function pickLabel(shift: PublicShift, date: string): string {
  const when = dayAndTime(
    formatDateLabel(date, LONG_DAY),
    formatTimeRange(shift.start_time, shift.end_time),
  )
  return t('guestSignup.list.pickLabel', { task: shift.task_name, when })
}
</script>

<template>
  <div class="space-y-6" data-testid="public-shift-list">
    <section
      v-for="day in days"
      :key="day.date"
      :aria-labelledby="dayHeadingTag === 'h2' ? `${uid}-${day.date}` : undefined"
      class="space-y-2"
    >
      <component
        :is="dayHeadingTag"
        :id="`${uid}-${day.date}`"
        class="text-xs font-semibold tracking-wider text-muted-foreground uppercase"
      >
        {{ formatDateLabel(day.date, LONG_DAY) }}
      </component>
      <ul class="space-y-2">
        <li
          v-for="shift in day.shifts"
          :key="shift.id"
          class="flex items-center justify-between gap-3 rounded-xl border p-3"
          :class="shift.full ? 'bg-muted/40' : 'bg-card'"
          data-testid="public-shift"
          :data-shift-id="shift.id"
          :data-full="shift.full"
        >
          <div class="min-w-0 space-y-0.5">
            <p class="font-semibold break-words">{{ shift.task_name }}</p>
            <p v-if="whenAndWhere(shift)" class="text-sm break-words text-muted-foreground">
              {{ whenAndWhere(shift) }}
            </p>
            <Badge
              v-if="(shift.vouchers ?? 0) > 0"
              variant="secondary"
              class="gap-1"
              data-testid="public-shift-vouchers"
            >
              <Ticket class="size-3.5" aria-hidden="true" />
              {{ t('guestSignup.list.vouchersBadge', { n: shift.vouchers }, shift.vouchers ?? 0) }}
            </Badge>
            <p
              v-if="showNames && shift.names?.length"
              class="text-sm break-words"
              data-testid="public-shift-names"
            >
              {{ namesLine(shift) }}
            </p>
          </div>
          <div class="flex shrink-0 flex-col items-end gap-1.5">
            <span
              class="text-xs font-semibold"
              :class="shift.full ? 'text-muted-foreground' : 'text-primary'"
              data-testid="public-shift-free"
            >
              {{
                shift.full
                  ? t('guestSignup.list.full')
                  : t('guestSignup.list.free', { count: shift.free })
              }}
            </span>
            <Button
              v-if="!readonly"
              class="h-10 px-4"
              :disabled="shift.full"
              :aria-label="pickLabel(shift, day.date)"
              :data-testid="`btn-pick-shift-${shift.id}`"
              @click="emit('pick', shift, day.date)"
            >
              {{ t('guestSignup.list.pick') }}
            </Button>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>
