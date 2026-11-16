<script setup lang="ts">
/**
 * A shared list's public page, `/l/<code>`: pick a shift, say who you are,
 * done. No account, no sign-in, and nothing kept in the browser.
 *
 * Three steps on one page (list, form, done), each taking focus as it appears,
 * so a screen reader hears where it is. A paused or closed list shows that
 * instead, whichever step was open: the server may say so at any submit.
 */
import { computed, nextTick, onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'

import { CircleAlertIcon, CirclePauseIcon, LinkIcon, LockIcon } from '@lucide/vue'
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
import PublicShiftList from '@/components/guest/PublicShiftList.vue'

import type { PublicShift } from '@/client/types.gen'

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

async function nextPerson(): Promise<void> {
  store.reset()
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
          class="rounded-lg border bg-muted/40 p-3 text-sm"
          data-testid="guest-signed-in"
        >
          {{ t('guestSignup.page.signedIn', { name: signedInName }) }}
        </p>

        <PublicShiftList
          v-if="list.days.length > 0"
          :days="list.days"
          :show-names="list.show_names === 'first'"
          @pick="pick"
        />
        <p v-else class="text-sm text-muted-foreground" data-testid="shared-list-empty">
          {{ t('guestSignup.states.empty') }}
        </p>
      </template>
    </article>
  </div>
</template>
