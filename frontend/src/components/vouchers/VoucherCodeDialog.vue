<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { CircleCheck, LinkIcon, Loader2, RefreshCw } from '@lucide/vue'
import { useDocumentVisibility, useWakeLock } from '@vueuse/core'
import { useI18n } from 'vue-i18n'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'

import QrCode from '@/components/print/QrCode.vue'

import type { VoucherPassRead, VoucherPassStatus } from '@/client/types.gen'
import { normalizeApiError } from '@/lib/api-errors'
import {
  PassSourceGone,
  type VoucherPassSource,
  formatVoucherCode,
  secondsLeft,
} from '@/lib/vouchers'

/**
 * The volunteer's code, shown at a stand: a QR code and the same six
 * characters underneath for typing.
 *
 * A code works once and for two minutes, so the dialog issues a new one just
 * before it runs out. It asks the server every two seconds what became of the
 * code: while a redeemer holds it the countdown gives way to "Being
 * redeemed…" and nothing rotates; once it is used the dialog says how many
 * were taken where and stops. The screen is kept awake while it is open.
 *
 * A member's codes come from their own event (`eventId`). A shared list's
 * guest has no account, so their page hands in a `source` that asks through
 * the guest's link instead. Once that link stops working the source says so
 * (`PassSourceGone`), and the dialog ends on `source.goneMessage` without
 * asking again: a dead link would only be refused every two seconds.
 *
 * A code can also vanish before its time (`voucher.pass_not_found` for the
 * code on screen): confirming a guest's address deletes the codes shown for
 * the sign-up, and a code shown on another screen replaces this one. The
 * dialog then asks for a new code at once, but only once per sitting. After
 * that it says the code is on another screen and waits for "Show it here",
 * so two screens of one person never take turns deleting each other's codes.
 * A code its own rotation is replacing is not vanished: issuing deletes it,
 * and a status answer can overtake the new code.
 */
const props = defineProps<{
  /** The member's event; unused when a `source` is given. */
  eventId?: string
  source?: VoucherPassSource
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{
  /** Something was redeemed, so the balance behind the dialog is stale. */
  redeemed: []
  /** The source's link stopped working, so the page behind the dialog is too. */
  gone: []
}>()

const { t } = useI18n()
const { get, post } = useAuthenticatedClient()
const visibility = useDocumentVisibility()
const wakeLock = useWakeLock()

/** Issue the next code this many seconds before the current one runs out. */
const ROTATE_AT_SECONDS = 5
const POLL_MS = 2000

/** A member's own codes, in the event the dialog is about. */
const memberSource: VoucherPassSource = {
  async issue() {
    const res = await post<{ data: VoucherPassRead }>({
      url: `/events/${props.eventId}/vouchers/me/pass`,
    })
    return res.data
  },
  async status(id) {
    const res = await get<{ data: VoucherPassStatus }>({
      url: `/events/${props.eventId}/vouchers/me/pass/${id}`,
    })
    return res.data
  },
  goneMessage: '',
}

const source = (): VoucherPassSource => props.source ?? memberSource

const pass = ref<VoucherPassRead | null>(null)
const receivedAt = ref(0)
const now = ref(Date.now())
const state = ref<VoucherPassStatus['status'] | null>(null)
const used = ref<{ amount: number; place: string; available: number } | null>(null)
const issuing = ref(false)
const failed = ref(false)
/** The code vanished a second time: another screen shows this person's code. */
const elsewhere = ref(false)
/** The source's key stopped working: final, nothing more is asked. */
const gone = ref(false)
/** Codes replaced by a newer one but perhaps still being redeemed. */
const previousIds = ref<string[]>([])
/** A code vanished before its time and was replaced once already. */
let replacedVanished = false
/** The one line screen readers hear: state changes, never the seconds. */
const announcement = ref('')

const remaining = computed(() =>
  pass.value ? secondsLeft(receivedAt.value, pass.value.ttl_seconds, now.value) : 0,
)
const settled = computed(() => state.value === 'used')
const holding = computed(() => state.value === 'checking')
/** The code on screen still works: a failed renewal must not take it away. */
const passUsable = computed(() => !!pass.value && state.value !== 'expired' && remaining.value > 0)

let tickTimer: ReturnType<typeof setInterval> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let polling = false

/** The link behind the codes died: hide the code, stop every timer, say so. */
function endGone() {
  gone.value = true
  stop()
  pass.value = null
  state.value = null
  previousIds.value = []
  announcement.value = source().goneMessage
  emit('gone')
}

async function issue() {
  // Closed: a new code would delete the one another screen may be showing.
  if (issuing.value || gone.value || !open.value) return
  issuing.value = true
  failed.value = false
  elsewhere.value = false
  try {
    const next = await source().issue()
    if (!open.value || gone.value) return
    // A rotated code may still be in a redeemer's hands; keep asking about it.
    if (pass.value && state.value !== 'expired') previousIds.value.push(pass.value.id)
    const isRotation = pass.value !== null
    pass.value = next
    receivedAt.value = Date.now()
    now.value = receivedAt.value
    state.value = 'active'
    used.value = null
    // A code is on screen: no earlier miss still stands.
    failed.value = false
    if (isRotation) announcement.value = t('vouchers.code.newCode')
  } catch (error) {
    if (error instanceof PassSourceGone) endGone()
    else failed.value = true
  } finally {
    issuing.value = false
  }
}

function markUsed(status: VoucherPassStatus) {
  state.value = 'used'
  used.value = {
    amount: status.redeemed_amount ?? 0,
    place: status.task_name ?? '',
    available: status.available,
  }
  previousIds.value = []
  announcement.value = t(
    'vouchers.code.redeemed',
    { n: used.value.amount, place: used.value.place },
    used.value.amount,
  )
  emit('redeemed')
}

/**
 * What became of a code: its status, `'vanished'` when the server no longer
 * has it (replaced or deleted), or null for a network blip, after which the
 * next poll asks again.
 */
async function statusOf(id: string): Promise<VoucherPassStatus | 'vanished' | null> {
  try {
    return await source().status(id)
  } catch (error) {
    if (error instanceof PassSourceGone) endGone()
    else if (normalizeApiError(error).code === 'voucher.pass_not_found') return 'vanished'
    return null
  }
}

/**
 * The code on screen no longer exists: one new code at once. The next time,
 * the dead code goes, nothing is asked about it any more, and "Show it here"
 * waits for the volunteer.
 */
function replaceVanished() {
  state.value = 'expired'
  if (replacedVanished) {
    pass.value = null
    elsewhere.value = true
    announcement.value = t('vouchers.code.elsewhere')
    return
  }
  replacedVanished = true
  void issue()
}

async function poll() {
  if (polling || !pass.value || settled.value || gone.value) return
  polling = true
  try {
    const current = pass.value.id
    for (const id of [...previousIds.value]) {
      const status = await statusOf(id)
      if (gone.value) return
      if (status !== null && status !== 'vanished' && status.status === 'used') {
        markUsed(status)
        return
      }
      if (status === null || status === 'vanished' || status.status === 'expired') {
        previousIds.value = previousIds.value.filter((p) => p !== id)
      }
    }
    const status = await statusOf(current)
    // A rotation may have happened while this was in flight.
    if (!status || gone.value || !open.value || pass.value?.id !== current) return
    if (status === 'vanished') {
      // Unless a rotation still in flight deleted it: its new code is coming.
      if (!issuing.value) replaceVanished()
      return
    }
    if (status.status === 'used') {
      markUsed(status)
      return
    }
    if (status.status === 'checking' && state.value !== 'checking') {
      announcement.value = t('vouchers.code.checking')
    }
    state.value = status.status
    if (status.status === 'expired') void issue()
  } finally {
    polling = false
  }
}

function tick() {
  now.value = Date.now()
  if (!pass.value || issuing.value || failed.value || gone.value) return
  if (state.value === 'active' && remaining.value <= ROTATE_AT_SECONDS) void issue()
}

function start() {
  stop()
  tickTimer = setInterval(tick, 1000)
  pollTimer = setInterval(() => void poll(), POLL_MS)
}

function stop() {
  if (tickTimer) clearInterval(tickTimer)
  if (pollTimer) clearInterval(pollTimer)
  tickTimer = null
  pollTimer = null
}

function reset() {
  pass.value = null
  state.value = null
  used.value = null
  failed.value = false
  elsewhere.value = false
  gone.value = false
  previousIds.value = []
  replacedVanished = false
  announcement.value = ''
}

async function keepAwake(on: boolean) {
  try {
    if (on && wakeLock.isSupported.value) await wakeLock.request('screen')
    else if (!on && wakeLock.isActive.value) await wakeLock.release()
  } catch {
    // Refused (battery saver, an iframe): the code still works, the screen may dim.
  }
}

/** "Show a new code" after one was used. */
function showNew() {
  reset()
  void issue()
}

watch(
  open,
  (isOpen) => {
    if (isOpen) {
      reset()
      void issue()
      start()
      void keepAwake(true)
    } else {
      stop()
      void keepAwake(false)
    }
  },
  { immediate: true },
)

// Back from another app or a locked screen: the code has usually run out by
// then, and nobody should have to wait five seconds for the next one.
watch(visibility, (v) => {
  if (v !== 'visible' || !open.value || gone.value) return
  now.value = Date.now()
  if (state.value === 'active' && remaining.value <= ROTATE_AT_SECONDS) void issue()
  void poll()
})

onBeforeUnmount(() => {
  stop()
  void keepAwake(false)
})
</script>

<template>
  <ResponsiveDialog v-model:open="open">
    <ResponsiveDialogContent dialog-class="sm:max-w-sm" data-testid="voucher-code-dialog">
      <ResponsiveDialogHeader>
        <ResponsiveDialogTitle>
          {{
            pass
              ? t('vouchers.code.forEvent', { event: pass.event_name })
              : t('vouchers.code.title')
          }}
        </ResponsiveDialogTitle>
        <!-- With the link dead there is no code to show: the message below says why. -->
        <ResponsiveDialogDescription v-if="!gone">{{
          t('vouchers.code.hint')
        }}</ResponsiveDialogDescription>
      </ResponsiveDialogHeader>

      <ResponsiveDialogBody class="pb-4">
        <div class="flex flex-col items-center gap-3 py-2">
          <!-- Used: say how many went where, and stop -->
          <div
            v-if="settled && used"
            class="flex min-h-[292px] flex-col items-center justify-center gap-3 text-center"
            data-testid="voucher-code-used"
          >
            <CircleCheck class="size-16 text-green-600 dark:text-green-400" aria-hidden="true" />
            <p class="text-lg font-semibold">
              {{ t('vouchers.code.redeemed', { n: used.amount, place: used.place }, used.amount) }}
            </p>
            <p class="text-sm text-muted-foreground" data-testid="voucher-code-left">
              {{
                used.available > 0
                  ? t('vouchers.available', { n: used.available }, used.available)
                  : t('vouchers.noneAvailable')
              }}
            </p>
          </div>

          <!-- The link behind the codes died: nothing to try again -->
          <div
            v-else-if="gone"
            class="flex min-h-[292px] flex-col items-center justify-center gap-3 text-center"
            data-testid="voucher-code-gone"
          >
            <span
              class="grid size-13 place-items-center rounded-full bg-muted text-muted-foreground"
              aria-hidden="true"
            >
              <LinkIcon class="size-6" />
            </span>
            <ResponsiveDialogDescription class="max-w-xs text-pretty">
              {{ source().goneMessage }}
            </ResponsiveDialogDescription>
          </div>

          <!-- Another screen shows this person's code: this one takes over only when asked -->
          <div
            v-else-if="elsewhere"
            class="flex min-h-[292px] flex-col items-center justify-center gap-3 text-center"
            data-testid="voucher-code-elsewhere"
          >
            <p class="max-w-xs text-sm text-pretty text-muted-foreground">
              {{ t('vouchers.code.elsewhere') }}
            </p>
            <Button variant="outline" data-testid="btn-voucher-code-retry" @click="issue">
              <RefreshCw class="mr-2 size-4" />
              {{ t('vouchers.code.showHere') }}
            </Button>
          </div>

          <!-- Nothing that still scans: say so, and offer to try again -->
          <div
            v-else-if="failed && !passUsable"
            class="flex min-h-[292px] flex-col items-center justify-center gap-3 text-center"
          >
            <p class="text-sm text-muted-foreground">{{ t('vouchers.code.failed') }}</p>
            <Button variant="outline" data-testid="btn-voucher-code-retry" @click="issue">
              <RefreshCw class="mr-2 size-4" />
              {{ t('vouchers.code.retry') }}
            </Button>
          </div>

          <template v-else-if="pass">
            <!-- Always white, so it scans in dark mode too -->
            <div
              class="rounded-lg bg-white p-4 transition-opacity"
              :class="holding ? 'opacity-40' : ''"
            >
              <QrCode
                :value="pass.qr_payload"
                :size="260"
                :pixel-ratio="2"
                alt=""
                data-testid="voucher-code-qr"
              />
            </div>
            <p
              class="font-mono text-2xl font-semibold tracking-widest"
              data-testid="voucher-code-text"
            >
              {{ formatVoucherCode(pass.code) }}
            </p>
            <p
              class="flex items-center gap-1.5 text-sm text-muted-foreground"
              data-testid="voucher-code-status"
            >
              <template v-if="holding">
                <Loader2 class="size-4 animate-spin" aria-hidden="true" />
                {{ t('vouchers.code.checking') }}
              </template>
              <template v-else>
                {{ t('vouchers.code.expiresIn', { s: remaining }) }}
              </template>
            </p>
            <!-- The next code did not arrive, but this one still works for now -->
            <p
              v-if="failed"
              class="flex items-center gap-2 text-sm text-muted-foreground"
              data-testid="voucher-code-renew-failed"
            >
              {{ t('vouchers.code.renewFailed') }}
              <Button
                variant="link"
                size="sm"
                class="h-auto p-0"
                data-testid="btn-voucher-code-retry"
                @click="issue"
              >
                {{ t('vouchers.code.retry') }}
              </Button>
            </p>
          </template>

          <div v-else class="flex min-h-[292px] items-center justify-center">
            <Loader2 class="size-8 animate-spin text-muted-foreground" aria-hidden="true" />
          </div>

          <p class="sr-only" aria-live="polite">{{ announcement }}</p>
        </div>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter v-if="gone">
        <Button variant="outline" data-testid="btn-voucher-code-close" @click="open = false">
          {{ t('common.actions.close') }}
        </Button>
      </ResponsiveDialogFooter>
      <ResponsiveDialogFooter v-else-if="settled">
        <Button variant="outline" @click="open = false">{{ t('common.actions.close') }}</Button>
        <!-- Nothing left: a new code would only be turned away at the stand -->
        <Button
          v-if="(used?.available ?? 0) > 0"
          data-testid="btn-voucher-code-new"
          @click="showNew"
        >
          {{ t('vouchers.code.showNew') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
