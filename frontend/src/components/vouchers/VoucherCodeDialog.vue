<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { CircleCheck, Loader2, RefreshCw } from '@lucide/vue'
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
import { formatVoucherCode, secondsLeft } from '@/lib/vouchers'

/**
 * The volunteer's code, shown at a stand: a QR code and the same six
 * characters underneath for typing.
 *
 * A code works once and for two minutes, so the dialog issues a new one just
 * before it runs out. It asks the server every two seconds what became of the
 * code: while a redeemer holds it the countdown gives way to "Being
 * redeemed…" and nothing rotates; once it is used the dialog says how many
 * were taken where and stops. The screen is kept awake while it is open.
 */
const props = defineProps<{ eventId: string }>()

const open = defineModel<boolean>('open', { required: true })

/** Something was redeemed, so the balance behind the dialog is stale. */
const emit = defineEmits<{ redeemed: [] }>()

const { t } = useI18n()
const { get, post } = useAuthenticatedClient()
const visibility = useDocumentVisibility()
const wakeLock = useWakeLock()

/** Issue the next code this many seconds before the current one runs out. */
const ROTATE_AT_SECONDS = 5
const POLL_MS = 2000

const pass = ref<VoucherPassRead | null>(null)
const receivedAt = ref(0)
const now = ref(Date.now())
const state = ref<VoucherPassStatus['status'] | null>(null)
const used = ref<{ amount: number; place: string } | null>(null)
const issuing = ref(false)
const failed = ref(false)
/** Codes replaced by a newer one but perhaps still being redeemed. */
const previousIds = ref<string[]>([])
/** The one line screen readers hear: state changes, never the seconds. */
const announcement = ref('')

const remaining = computed(() =>
  pass.value ? secondsLeft(receivedAt.value, pass.value.ttl_seconds, now.value) : 0,
)
const settled = computed(() => state.value === 'used')
const holding = computed(() => state.value === 'checking')

let tickTimer: ReturnType<typeof setInterval> | null = null
let pollTimer: ReturnType<typeof setInterval> | null = null
let polling = false

async function issue() {
  if (issuing.value) return
  issuing.value = true
  failed.value = false
  try {
    const res = await post<{ data: VoucherPassRead }>({
      url: `/events/${props.eventId}/vouchers/me/pass`,
    })
    if (!open.value) return
    // A rotated code may still be in a redeemer's hands; keep asking about it.
    if (pass.value && state.value !== 'expired') previousIds.value.push(pass.value.id)
    const isRotation = pass.value !== null
    pass.value = res.data
    receivedAt.value = Date.now()
    now.value = receivedAt.value
    state.value = 'active'
    used.value = null
    if (isRotation) announcement.value = t('vouchers.code.newCode')
  } catch {
    failed.value = true
  } finally {
    issuing.value = false
  }
}

function markUsed(status: VoucherPassStatus) {
  state.value = 'used'
  used.value = {
    amount: status.redeemed_amount ?? 0,
    place: status.task_name ?? '',
  }
  previousIds.value = []
  announcement.value = t(
    'vouchers.code.redeemed',
    { n: used.value.amount, place: used.value.place },
    used.value.amount,
  )
  emit('redeemed')
}

async function statusOf(id: string): Promise<VoucherPassStatus | null> {
  try {
    const res = await get<{ data: VoucherPassStatus }>({
      url: `/events/${props.eventId}/vouchers/me/pass/${id}`,
    })
    return res.data
  } catch {
    // Replaced or gone (404), or a network blip: the next poll asks again.
    return null
  }
}

async function poll() {
  if (polling || !pass.value || settled.value) return
  polling = true
  try {
    const current = pass.value.id
    for (const id of [...previousIds.value]) {
      const status = await statusOf(id)
      if (status?.status === 'used') {
        markUsed(status)
        return
      }
      if (!status || status.status === 'expired') {
        previousIds.value = previousIds.value.filter((p) => p !== id)
      }
    }
    const status = await statusOf(current)
    // A rotation may have happened while this was in flight.
    if (!status || pass.value?.id !== current) return
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
  if (!pass.value || issuing.value || failed.value) return
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
  previousIds.value = []
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
  if (v !== 'visible' || !open.value) return
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
            pass ? t('vouchers.code.forEvent', { event: pass.event_name }) : t('vouchers.code.title')
          }}
        </ResponsiveDialogTitle>
        <ResponsiveDialogDescription>{{ t('vouchers.code.hint') }}</ResponsiveDialogDescription>
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
          </div>

          <div
            v-else-if="failed"
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
          </template>

          <div v-else class="flex min-h-[292px] items-center justify-center">
            <Loader2 class="size-8 animate-spin text-muted-foreground" aria-hidden="true" />
          </div>

          <p class="sr-only" aria-live="polite">{{ announcement }}</p>
        </div>
      </ResponsiveDialogBody>

      <ResponsiveDialogFooter v-if="settled">
        <Button variant="outline" @click="open = false">{{ t('common.actions.close') }}</Button>
        <Button data-testid="btn-voucher-code-new" @click="showNew">
          {{ t('vouchers.code.showNew') }}
        </Button>
      </ResponsiveDialogFooter>
    </ResponsiveDialogContent>
  </ResponsiveDialog>
</template>
