<script setup lang="ts">
/**
 * A shared list's public page, `/l/<code>`: pick a shift, say who you are,
 * done. No account, no sign-in, and nothing kept in the browser.
 *
 * Three steps on one page (list, form, done), each taking focus as it appears,
 * so a screen reader hears where it is. A paused or closed list shows that
 * instead, whichever step was open: the server may say so at any submit.
 *
 * A long list can be narrowed to one task, one day or the shifts with a place
 * left (`PublicShiftFilters`). A demo's list says so in the header, out of the
 * way of the shifts (`GuestDemoNotice`).
 */
import { computed, nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'

import { CircleAlertIcon, CirclePauseIcon, InfoIcon, LinkIcon, LockIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useGuestSignupStore } from '@/stores/guestSignup'

import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

import EventZoneHint from '@/components/events/EventZoneHint.vue'
import GuestDemoNotice from '@/components/guest/GuestDemoNotice.vue'
import GuestSignupDone from '@/components/guest/GuestSignupDone.vue'
import GuestSignupForm from '@/components/guest/GuestSignupForm.vue'
import GuestStateMessage from '@/components/guest/GuestStateMessage.vue'
import PublicListHeader from '@/components/guest/PublicListHeader.vue'
import PublicShiftFilters from '@/components/guest/PublicShiftFilters.vue'
import PublicShiftList from '@/components/guest/PublicShiftList.vue'

import type { PublicShift } from '@/client/types.gen'
import {
  ALL_SHIFTS,
  NO_SHIFT_FILTER,
  type ShiftFilter,
  filterDays,
  listTasks,
} from '@/lib/guest-signup'

type Step = { kind: 'list' } | { kind: 'form'; shift: PublicShift; date: string } | { kind: 'done' }

const { t } = useI18n()
const route = useRoute()
const store = useGuestSignupStore()
const authStore = useAuthStore()

const header = useTemplateRef<InstanceType<typeof PublicListHeader>>('header')
const step = ref<Step>({ kind: 'list' })
const undoing = ref(false)

const code = computed(() => String(route.params.code ?? ''))
const list = computed(() => store.list)
/** Some shift on the list gives vouchers, which guests earn too. */
const earnsVouchers = computed(
  () => list.value?.days.some((day) => day.shifts.some((s) => (s.vouchers ?? 0) > 0)) ?? false,
)

/**
 * Somebody signed in who opens a list still signs up as a guest, and should
 * know that before they look for the shift in their account. Their details are
 * not filled in: on a tablet at the stand the account is the organiser's.
 */
const signedInName = computed(() =>
  authStore.isAuthenticated ? (authStore.profile?.name ?? null) : null,
)

const filter = ref<ShiftFilter>({ ...NO_SHIFT_FILTER })
const tasks = computed(() => listTasks(list.value?.days ?? []))
const dates = computed(() => (list.value?.days ?? []).map((day) => day.date))
const anyFull = computed(
  () => list.value?.days.some((day) => day.shifts.some((shift) => shift.full)) ?? false,
)
const shownDays = computed(() => filterDays(list.value?.days ?? [], filter.value))

// A reload may drop the task or day a filter names; the filter lets go of it.
watch([tasks, dates], () => {
  const { task, day } = filter.value
  if (task !== ALL_SHIFTS && !tasks.value.some((option) => option.id === task)) {
    filter.value = { ...filter.value, task: ALL_SHIFTS }
  }
  if (day !== ALL_SHIFTS && !dates.value.includes(day)) {
    filter.value = { ...filter.value, day: ALL_SHIFTS }
  }
})

function clearFilter(): void {
  filter.value = { ...NO_SHIFT_FILTER }
}

/** Back to the top of the page, with focus on the list's title. */
async function showList(): Promise<void> {
  step.value = { kind: 'list' }
  await nextTick()
  window.scrollTo({ top: 0 })
  header.value?.focus()
}

function pick(shift: PublicShift, date: string): void {
  step.value = { kind: 'form', shift, date }
  window.scrollTo({ top: 0 })
}

function signedUp(): void {
  step.value = { kind: 'done' }
  window.scrollTo({ top: 0 })
}

async function undo(): Promise<void> {
  if (undoing.value) return
  undoing.value = true
  const undone = await store.undo()
  undoing.value = false
  if (!undone) return
  toast.success(t('guestSignup.done.undone'))
  await showList()
}

/** The next person at a shared device starts afresh, filters included. */
async function nextPerson(): Promise<void> {
  store.reset()
  clearFilter()
  await showList()
}

watch(
  code,
  (next) => {
    step.value = { kind: 'list' }
    void store.load(next)
  },
  { immediate: true },
)

onBeforeUnmount(() => store.clear())
</script>

<template>
  <div>
    <div
      v-if="store.listState === 'idle' || store.listState === 'loading'"
      class="space-y-4"
      role="status"
      data-testid="shared-list-loading"
    >
      <span class="sr-only">{{ t('utils.loading') }}</span>
      <Skeleton class="h-36 w-full rounded-2xl" />
      <Skeleton class="h-20 w-full rounded-xl" />
      <Skeleton class="h-20 w-full rounded-xl" />
    </div>

    <GuestStateMessage
      v-else-if="store.listState === 'missing'"
      :icon="LinkIcon"
      heading-tag="h1"
      :title="t('guestSignup.states.notFound.title')"
      :text="t('guestSignup.states.notFound.text')"
      data-testid="shared-list-not-found"
    />

    <GuestStateMessage
      v-else-if="store.listState === 'failed' || !list"
      :icon="CircleAlertIcon"
      heading-tag="h1"
      :title="t('guestSignup.page.error.title')"
      data-testid="shared-list-error"
    >
      <Button variant="outline" class="h-11" @click="store.load(code)">
        {{ t('guestSignup.page.error.retry') }}
      </Button>
    </GuestStateMessage>

    <article v-else class="space-y-5" data-testid="shared-list-page">
      <PublicListHeader ref="header" :list="list" />
      <GuestDemoNotice v-if="list.event.is_sandbox" />
      <EventZoneHint :zone="list.event.timezone" />

      <GuestStateMessage
        v-if="list.status === 'paused'"
        :icon="CirclePauseIcon"
        :title="t('guestSignup.states.paused.title')"
        :text="t('guestSignup.states.paused.text')"
        data-testid="shared-list-paused"
      />

      <GuestStateMessage
        v-else-if="list.status === 'closed'"
        :icon="LockIcon"
        :title="t('guestSignup.states.closed.title')"
        :text="t('guestSignup.states.closed.text')"
        data-testid="shared-list-closed"
      />

      <GuestSignupForm
        v-else-if="step.kind === 'form'"
        :list="list"
        :shift="step.shift"
        :date="step.date"
        @back="showList"
        @done="signedUp"
      />

      <GuestSignupDone
        v-else-if="step.kind === 'done' && store.last"
        :result="store.last"
        :list="list"
        :mailed-to="store.mailedTo"
        :link-to-keep="store.linkToKeep"
        :undoing="undoing"
        @another="showList"
        @undo="undo"
        @next="nextPerson"
      />

      <template v-else>
        <div class="space-y-1">
          <p class="font-semibold">{{ t('guestSignup.list.lead') }}</p>
          <p
            v-if="list.max_per_person"
            class="text-sm text-muted-foreground"
            data-testid="shared-list-max"
          >
            {{
              t(
                'guestSignup.list.maxPerPerson',
                { count: list.max_per_person },
                list.max_per_person,
              )
            }}
          </p>
          <p
            v-if="earnsVouchers"
            class="text-sm text-muted-foreground"
            data-testid="shared-list-vouchers-hint"
          >
            {{ t('guestSignup.list.vouchersHint') }}
          </p>
        </div>

        <p
          v-if="signedInName"
          class="flex items-start gap-1.5 text-sm text-muted-foreground"
          data-testid="guest-signed-in"
        >
          <InfoIcon class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {{ t('guestSignup.page.signedIn', { name: signedInName }) }}
        </p>

        <template v-if="list.days.length > 0">
          <PublicShiftFilters v-model="filter" :tasks="tasks" :dates="dates" :any-full="anyFull" />
          <PublicShiftList
            v-if="shownDays.length > 0"
            :days="shownDays"
            :show-names="list.show_names === 'first'"
            @pick="pick"
          />
          <div
            v-else
            class="grid justify-items-center gap-3 rounded-xl border border-dashed px-4 py-8 text-center text-sm"
            data-testid="shared-list-filtered-empty"
          >
            <p class="text-muted-foreground">{{ t('guestSignup.list.filters.none') }}</p>
            <Button variant="outline" class="h-10" @click="clearFilter">
              {{ t('guestSignup.list.filters.reset') }}
            </Button>
          </div>
        </template>
        <p v-else class="text-sm text-muted-foreground" data-testid="shared-list-empty">
          {{ t('guestSignup.states.empty') }}
        </p>
      </template>
    </article>
  </div>
</template>
