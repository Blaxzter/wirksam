<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  ChevronDown,
  CircleAlert,
  Info,
  Keyboard,
  MapPin,
  ScanLine,
  Ticket,
  UserSearch,
} from '@lucide/vue'
import { useMediaQuery } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Alert, AlertDescription } from '@/components/ui/alert'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import Input from '@/components/ui/input/Input.vue'
import Label from '@/components/ui/label/Label.vue'
import { NativeSelect } from '@/components/ui/native-select'
import {
  RESPONSIVE_DIALOG_MOBILE_QUERY,
  ResponsiveDialog,
  ResponsiveDialogBody,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import { Skeleton } from '@/components/ui/skeleton'

import EventMemberPicker from '@/components/events/EventMemberPicker.vue'
import { joinNames } from '@/components/events/teams/teamHelpers'
import VoucherRedeemConfirm, {
  type RedeemSubject,
} from '@/components/vouchers/VoucherRedeemConfirm.vue'
import VoucherScanner, { type ScannerError } from '@/components/vouchers/VoucherScanner.vue'

import type {
  EventMemberRead,
  PointPersonVouchers,
  PointRedemptionList,
  VoucherCheckResult,
  VoucherPointRead,
} from '@/client/types.gen'
import { getApiErrorMessage, toastApiError } from '@/lib/api-errors'
import { parseServerDate } from '@/lib/server-time'
import {
  codeUsedDetails,
  createDetectionGate,
  noPhoneContact,
  normalizeVoucherCode,
  parseVoucherPayload,
} from '@/lib/vouchers'

/**
 * Taking vouchers at a stand: a full page, not a dialog, so one camera stream
 * stays open across a whole queue.
 *
 * The camera sits on top and is never unmounted or paused between people (on
 * iOS a stopped stream can mean asking for permission again); typing the code
 * is a collapsible section under it rather than a tab, because a tab would
 * unmount or hide the scanner. A code in view goes to `check`, which says who
 * it is and how many they have, and the confirm step takes it from there.
 */
const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { get, post } = useAuthenticatedClient()

const eventId = computed(
  () => (route.params.eventId as string | undefined) || authStore.selectedEventId || null,
)

const points = ref<VoucherPointRead[]>([])
const loading = ref(false)
const pointId = ref('')

const redeemable = computed(() => points.value.filter((p) => p.can_redeem))
const point = computed(() => redeemable.value.find((p) => p.task_id === pointId.value) ?? null)

const isAdmin = computed(() => authStore.canManageEvent(eventId.value))
const isInCharge = computed(
  () => !!point.value?.managers.some((m) => m.user_id === authStore.profile?.id),
)
/** Someone redeeming only because they are on shift sees just their own. */
const seesAllEntries = computed(() => isAdmin.value || isInCharge.value)

/** Who to send someone without a phone to, when the caller may not pick the person. */
const askManagers = computed(() => {
  const contact = point.value ? noPhoneContact(point.value) : null
  if (!contact) return null
  if (contact.kind === 'organisers') return t('vouchers.redeem.askOrganisers')
  return t('vouchers.redeem.askManagers', { names: joinNames(contact.names, locale.value) })
})

// --- Which point ---

const LAST_POINT_KEY = 'wirksam.voucherRedeem.lastPoint'

function readLastPoint(id: string): string | null {
  try {
    return localStorage.getItem(`${LAST_POINT_KEY}.${id}`)
  } catch {
    return null
  }
}

function rememberPoint(id: string, taskId: string) {
  try {
    localStorage.setItem(`${LAST_POINT_KEY}.${id}`, taskId)
  } catch {
    // Private mode: the picker simply starts empty next time.
  }
}

function choosePoint(id: string) {
  const list = redeemable.value
  const fromQuery = typeof route.query.task === 'string' ? route.query.task : null
  const last = readLastPoint(id)
  const pick =
    list.find((p) => p.task_id === fromQuery) ??
    (list.length === 1 ? list[0] : undefined) ??
    list.find((p) => p.task_id === last) ??
    list[0]
  pointId.value = pick?.task_id ?? ''
}

async function loadPoints() {
  const id = eventId.value
  points.value = []
  pointId.value = ''
  if (!id) return
  loading.value = true
  try {
    const res = await get<{ data: VoucherPointRead[] }>({ url: `/events/${id}/vouchers/points` })
    if (eventId.value !== id) return
    points.value = res.data
    choosePoint(id)
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

watch(eventId, loadPoints, { immediate: true })

watch(pointId, (taskId) => {
  checkProblem.value = null
  if (!taskId || !eventId.value) return
  rememberPoint(eventId.value, taskId)
  if (route.query.task !== taskId) {
    void router.replace({ query: { ...route.query, task: taskId } })
  }
  void loadRecent()
})

// --- Recent redemptions here ---

const recent = ref<PointRedemptionList | null>(null)

async function loadRecent() {
  const id = eventId.value
  const taskId = pointId.value
  if (!id || !taskId) {
    recent.value = null
    return
  }
  try {
    const res = await get<{ data: PointRedemptionList }>({
      url: `/events/${id}/vouchers/points/${taskId}/entries`,
      query: { limit: 20 },
    })
    if (pointId.value === taskId) recent.value = res.data
  } catch {
    recent.value = null
  }
}

/** The time, with the weekday in front once it was not today. */
function timeOf(iso: string): string {
  const d = parseServerDate(iso)
  if (!d) return ''
  const today = d.toDateString() === new Date().toDateString()
  return d.toLocaleString(locale.value, {
    ...(today ? {} : { weekday: 'short' }),
    hour: '2-digit',
    minute: '2-digit',
  })
}

// --- Who is at the counter ---

/** From a detection until the confirm closes again; detections are dropped meanwhile. */
const busy = ref(false)
const confirmOpen = ref(false)
const subject = ref<RedeemSubject | null>(null)
const gate = createDetectionGate()
/** "Pick a person" is open: a code held up meanwhile must not open the confirm on top. */
const pickOpen = ref(false)

/**
 * Why the last code went nowhere, shown under the camera until the next code
 * or the next keystroke. A toast is gone in four seconds, often before anyone
 * at a busy counter has looked down at the phone.
 */
const checkProblem = ref<{ kind: 'used' | 'error'; text: string } | null>(null)

function timeOfDay(d: Date | null): string {
  return d ? d.toLocaleTimeString(locale.value, { hour: '2-digit', minute: '2-digit' }) : ''
}

async function check(body: { code: string } | { user_id: string }) {
  const id = eventId.value
  const p = point.value
  if (!id || !p || busy.value) return
  busy.value = true
  checkProblem.value = null
  try {
    const res = await post<{ data: VoucherCheckResult }>({
      url: `/events/${id}/vouchers/check`,
      body: { task_id: p.task_id, ...body },
    })
    subject.value = {
      code: 'code' in body ? body.code : null,
      userId: res.data.user_id,
      name: res.data.name ?? null,
      avatarEtag: res.data.avatar_etag ?? null,
      available: res.data.available,
    }
    confirmOpen.value = true
  } catch (error) {
    const used = codeUsedDetails(error)
    checkProblem.value = used
      ? {
          kind: 'used',
          text: t(
            'vouchers.redeem.alreadyRedeemed',
            { n: used.amount ?? 0, place: used.taskName ?? '?', time: timeOfDay(used.usedAt) },
            used.amount ?? 0,
          ),
        }
      : { kind: 'error', text: getApiErrorMessage(error) }
    busy.value = false
  }
}

watch(confirmOpen, (isOpen) => {
  if (isOpen) return
  // However long the confirm stayed open, the code it was about is still in
  // front of the camera now: count it as handled from this moment.
  if (subject.value?.code) gate.remember(subject.value.code, Date.now())
  busy.value = false
  void loadRecent()
})

function onDetect(data: string) {
  if (busy.value || pickOpen.value || !point.value) return
  const now = Date.now()
  const code = parseVoucherPayload(data)
  // Even a stranger's QR code is handled once, not reported on every frame.
  if (!gate.accept(code ?? data, now)) return
  if (!code) {
    checkProblem.value = { kind: 'error', text: t('vouchers.redeem.notAVoucher') }
    return
  }
  void check({ code })
}

const scannerError = ref<ScannerError | null>(null)
const typeOpen = ref(false)

const scannerMessage = computed(() => {
  switch (scannerError.value) {
    case 'insecure':
      return t('vouchers.redeem.insecure')
    case 'denied':
      return t('vouchers.redeem.cameraDenied')
    case 'no-camera':
      return t('vouchers.redeem.noCamera')
    case 'other':
      return t('vouchers.redeem.cameraFailed')
    default:
      return null
  }
})

function onScannerError(kind: ScannerError) {
  scannerError.value = kind
  typeOpen.value = true
}

// --- Typing the code ---

const typed = ref('')

// What was said about the last code no longer applies to a new one.
watch(typed, () => {
  checkProblem.value = null
})

function submitTyped() {
  const code = normalizeVoucherCode(typed.value)
  if (!code) {
    checkProblem.value = { kind: 'error', text: t('vouchers.redeem.notAVoucher') }
    return
  }
  gate.accept(code, Date.now())
  void check({ code }).then(() => {
    if (confirmOpen.value) typed.value = ''
  })
}

// --- Picking the person ---

/** A phone picks in a full-screen sheet; a wider screen in a dialog with a dropdown. */
const isPhone = useMediaQuery(RESPONSIVE_DIALOG_MOBILE_QUERY)

const members = ref<EventMemberRead[]>([])
const membersLoading = ref(false)

/**
 * user id → how many they can redeem, beside each name in the picker. Read
 * from the point itself (`…/points/{task}/people`), which answers everyone
 * who may pick the person there: organisers, the people in charge and, when
 * the event allows it, the staff on shift. `null` until it loaded, or when it
 * could not: the picker then shows names alone.
 */
const balances = ref<Record<string, number> | null>(null)

/**
 * Nobody can be picked who has nothing to redeem; the picker says why. Someone
 * missing from the numbers joined after they were read, and has none either.
 */
const noVouchers = computed<Record<string, string> | undefined>(() => {
  const counts = balances.value
  if (!counts) return undefined
  const reason = t('vouchers.redeem.noVouchersLeft')
  return Object.fromEntries(
    members.value.filter((m) => !counts[m.user_id]).map((m) => [m.user_id, reason]),
  )
})

const countOf = (member: EventMemberRead) => balances.value?.[member.user_id] ?? 0

const pickContext = computed(() =>
  t(balances.value ? 'vouchers.redeem.pickContextCounts' : 'vouchers.redeem.pickContext', {
    place: point.value?.name ?? '',
  }),
)

async function loadMembers(id: string) {
  membersLoading.value = true
  try {
    const res = await get<{ data: EventMemberRead[] }>({ url: `/events/${id}/members` })
    if (eventId.value === id) members.value = res.data
  } catch (error) {
    toastApiError(error)
  } finally {
    membersLoading.value = false
  }
}

/**
 * Read afresh on every opening: a shift that ended a minute ago counts
 * already, and so does what was redeemed meanwhile at another stand.
 */
async function loadBalances(id: string, taskId: string) {
  balances.value = null
  try {
    const res = await get<{ data: PointPersonVouchers[] }>({
      url: `/events/${id}/vouchers/points/${taskId}/people`,
    })
    if (eventId.value !== id || pointId.value !== taskId) return
    balances.value = Object.fromEntries(res.data.map((b) => [b.user_id, b.available]))
  } catch {
    // Without the numbers the picker still works; it just shows names, and
    // the server still refuses more than someone has.
    balances.value = null
  }
}

async function openPicker() {
  pickOpen.value = true
  const id = eventId.value
  const taskId = point.value?.task_id
  if (!id || !taskId) return
  await Promise.all([members.value.length > 0 ? null : loadMembers(id), loadBalances(id, taskId)])
}

function pickMember(member: EventMemberRead) {
  pickOpen.value = false
  void check({ user_id: member.user_id })
}

/**
 * "Next person" in the confirm, once it has closed: the next one is taken the
 * way this one was. Picked by hand, the picker opens again; a typed code
 * leaves the cursor in the empty code field. The camera needs nothing: it
 * scans again as soon as the confirm is gone.
 */
function readyNext() {
  if (!subject.value?.code && point.value?.can_redeem_manually) {
    void openPicker()
    return
  }
  if (typeOpen.value) document.getElementById('voucher-code-input')?.focus()
}

watch(eventId, () => {
  members.value = []
  balances.value = null
})
</script>

<template>
  <div class="mx-auto max-w-xl space-y-5">
    <div class="space-y-1">
      <h1 data-testid="page-heading" class="text-2xl font-bold sm:text-3xl">
        {{ t('vouchers.redeem.title') }}
      </h1>
    </div>

    <div v-if="loading" class="space-y-4">
      <Skeleton class="h-10 w-full" />
      <Skeleton class="aspect-square w-full rounded-lg" />
    </div>

    <!-- Nowhere this person may take vouchers right now -->
    <Card v-else-if="redeemable.length === 0" data-testid="voucher-redeem-empty">
      <CardHeader>
        <CardTitle class="text-lg">{{ t('vouchers.redeem.noPlacesTitle') }}</CardTitle>
      </CardHeader>
      <CardContent>
        <p class="text-sm text-muted-foreground">{{ t('vouchers.redeem.noPlaces') }}</p>
      </CardContent>
    </Card>

    <template v-else-if="eventId">
      <!-- Where: one line at the top -->
      <div class="flex items-center gap-2">
        <Label for="voucher-point" class="flex shrink-0 items-center gap-1.5">
          <MapPin class="size-4 text-muted-foreground" aria-hidden="true" />
          {{ t('vouchers.redeem.place') }}
        </Label>
        <!-- The wrapper, not the select, is the flex child: let it fill the line
             and let a long name be cut off by the select instead of widening it. -->
        <div class="min-w-0 flex-1 [&_[data-slot=native-select-wrapper]]:w-full">
          <NativeSelect
            id="voucher-point"
            v-model="pointId"
            class="w-full truncate"
            data-testid="voucher-point"
          >
            <option v-for="p in redeemable" :key="p.task_id" :value="p.task_id">
              {{ p.location ? `${p.name} · ${p.location}` : p.name }}
            </option>
          </NativeSelect>
        </div>
      </div>

      <!-- The camera: always mounted while it works, never hidden -->
      <div v-if="!scannerError" class="mx-auto w-full space-y-2 sm:max-w-sm">
        <VoucherScanner :paused="busy || pickOpen" @detect="onDetect" @error="onScannerError" />
        <p class="flex items-center gap-1.5 text-sm text-muted-foreground">
          <ScanLine class="size-4 shrink-0" aria-hidden="true" />
          {{ t('vouchers.redeem.scanHint') }}
        </p>
      </div>
      <Alert v-else data-testid="voucher-scanner-error">
        <AlertDescription>{{ scannerMessage }}</AlertDescription>
      </Alert>

      <!-- What became of the last code: stays until the next one -->
      <div
        v-if="checkProblem"
        role="alert"
        class="flex items-start gap-2 rounded-md border p-3 text-sm"
        :class="
          checkProblem.kind === 'used'
            ? 'border-amber-500/40 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200'
            : 'border-destructive/40 bg-destructive/5 text-destructive'
        "
        data-testid="voucher-check-problem"
      >
        <Info
          v-if="checkProblem.kind === 'used'"
          class="mt-0.5 size-4 shrink-0"
          aria-hidden="true"
        />
        <CircleAlert v-else class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>{{ checkProblem.text }}</span>
      </div>

      <!-- Typing the code: under the camera, not a tab beside it -->
      <Collapsible v-model:open="typeOpen" class="rounded-lg border">
        <CollapsibleTrigger as-child>
          <button
            type="button"
            class="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm font-medium"
            data-testid="btn-voucher-type-code"
          >
            <span class="flex items-center gap-2">
              <Keyboard class="size-4 text-muted-foreground" aria-hidden="true" />
              {{ t('vouchers.redeem.typeInstead') }}
            </span>
            <ChevronDown
              class="size-4 text-muted-foreground transition-transform"
              :class="typeOpen ? 'rotate-180' : ''"
              aria-hidden="true"
            />
          </button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <form class="flex items-end gap-2 px-4 pb-4" @submit.prevent="submitTyped">
            <div class="min-w-0 flex-1 space-y-1.5">
              <Label for="voucher-code-input">{{ t('vouchers.redeem.codeLabel') }}</Label>
              <Input
                id="voucher-code-input"
                v-model="typed"
                class="h-11 font-mono text-lg uppercase tracking-widest placeholder:font-sans placeholder:text-base placeholder:normal-case placeholder:tracking-normal"
                :placeholder="t('vouchers.redeem.codePlaceholder')"
                autocomplete="off"
                autocapitalize="characters"
                spellcheck="false"
                maxlength="12"
                data-testid="voucher-code-input"
              />
            </div>
            <Button
              type="submit"
              class="h-11"
              :disabled="busy || !typed.trim()"
              data-testid="btn-voucher-check"
            >
              {{ t('vouchers.redeem.continue') }}
            </Button>
          </form>
        </CollapsibleContent>
      </Collapsible>

      <!-- No phone: pick the person (organisers, people in charge, and the staff
           on shift unless the event keeps this with those two) -->
      <div v-if="point?.can_redeem_manually" class="space-y-1">
        <Button
          variant="outline"
          class="w-full"
          :disabled="busy"
          data-testid="btn-voucher-pick-person"
          @click="openPicker"
        >
          <UserSearch class="mr-2 size-4" />
          {{ t('vouchers.redeem.pickPerson') }}
        </Button>
        <p class="text-center text-xs text-muted-foreground">
          {{ t('vouchers.redeem.personHint') }}
        </p>
      </div>
      <p
        v-else-if="askManagers"
        class="text-sm text-muted-foreground"
        data-testid="voucher-ask-managers"
      >
        {{ askManagers }}
      </p>

      <!-- Redeemed here recently -->
      <Card v-if="recent" data-testid="voucher-recent">
        <CardHeader class="pb-2">
          <div class="flex items-baseline justify-between gap-2">
            <CardTitle class="text-base">
              {{ seesAllEntries ? t('vouchers.redeem.recent') : t('vouchers.redeem.recentOwn') }}
            </CardTitle>
            <span
              class="shrink-0 text-sm text-muted-foreground tabular-nums"
              data-testid="voucher-recent-today"
            >
              {{
                t('vouchers.redeem.recentToday', { n: recent.today_amount }, recent.today_amount)
              }}
            </span>
          </div>
        </CardHeader>
        <CardContent>
          <p v-if="recent.items.length === 0" class="text-sm text-muted-foreground">
            {{
              seesAllEntries
                ? t('vouchers.redeem.recentEmpty')
                : t('vouchers.redeem.recentOwnEmpty')
            }}
          </p>
          <ul v-else class="divide-y">
            <li
              v-for="entry in recent.items"
              :key="entry.id"
              class="flex items-center gap-3 py-2 text-sm"
              data-testid="voucher-recent-row"
            >
              <span class="shrink-0 whitespace-nowrap tabular-nums text-muted-foreground">
                {{ timeOf(entry.created_at) }}
              </span>
              <span class="min-w-0 flex-1 truncate">
                {{ entry.user_name ?? '?' }}
                <span v-if="seesAllEntries && entry.actor_name" class="text-muted-foreground">
                  · {{ t('vouchers.history.by', { name: entry.actor_name }) }}
                </span>
              </span>
              <span class="shrink-0 font-semibold tabular-nums">
                {{ t('vouchers.redeem.rowAmount', { n: -entry.amount }, -entry.amount) }}
              </span>
            </li>
          </ul>
        </CardContent>
      </Card>

      <VoucherRedeemConfirm
        v-if="point"
        v-model:open="confirmOpen"
        :event-id="eventId"
        :task-id="point.task_id"
        :subject="subject"
        @next="readyNext"
      />

      <!-- Phone: straight into a full-screen list, the keyboard already up -->
      <EventMemberPicker
        v-if="isPhone"
        v-model:sheet-open="pickOpen"
        :members="members"
        :unavailable="noVouchers"
        :label="t('vouchers.redeem.pickPerson')"
        :placeholder="t('vouchers.redeem.searchPerson')"
        :empty-text="membersLoading ? t('common.states.loading') : undefined"
        testid="voucher-pick-person"
        phone-sheet
        hide-field
        :sheet-title="t('vouchers.redeem.pickSheetTitle')"
        :sheet-context="pickContext"
        @pick="pickMember"
      >
        <template v-if="balances" #trailing="{ member }">
          <span
            class="flex shrink-0 items-center gap-1 rounded-full px-2.5 py-0.5 text-[13px] font-bold tabular-nums"
            :class="
              countOf(member) > 0
                ? 'bg-hero-chip text-hero-chip-foreground'
                : 'bg-secondary text-secondary-foreground'
            "
            :data-testid="`voucher-pick-count-${member.user_id}`"
          >
            <Ticket class="size-3.5 shrink-0" aria-hidden="true" />
            <span aria-hidden="true">{{ countOf(member) }}</span>
            <span class="sr-only">
              {{ t('vouchers.available', { n: countOf(member) }, countOf(member)) }}
            </span>
          </span>
        </template>
      </EventMemberPicker>

      <ResponsiveDialog v-else v-model:open="pickOpen">
        <ResponsiveDialogContent dialog-class="sm:max-w-md" data-testid="voucher-pick-dialog">
          <ResponsiveDialogHeader>
            <ResponsiveDialogTitle>{{
              t('vouchers.redeem.pickPersonTitle')
            }}</ResponsiveDialogTitle>
            <ResponsiveDialogDescription>
              {{ t('vouchers.redeem.personHint') }}
            </ResponsiveDialogDescription>
          </ResponsiveDialogHeader>
          <ResponsiveDialogBody class="pb-6">
            <EventMemberPicker
              :members="members"
              :unavailable="noVouchers"
              :label="t('vouchers.redeem.pickPerson')"
              :placeholder="t('vouchers.redeem.searchPerson')"
              :empty-text="membersLoading ? t('common.states.loading') : undefined"
              input-id="voucher-pick-person"
              :action-hint="t('vouchers.redeem.enterToPick')"
              testid="voucher-pick-person"
              @pick="pickMember"
            >
              <template v-if="balances" #trailing="{ member }">
                <span
                  class="flex shrink-0 items-center gap-1 rounded-full px-2 py-px text-xs font-bold tabular-nums"
                  :class="
                    countOf(member) > 0
                      ? 'bg-hero-chip text-hero-chip-foreground'
                      : 'bg-secondary text-secondary-foreground'
                  "
                  :data-testid="`voucher-pick-count-${member.user_id}`"
                >
                  <Ticket class="size-3 shrink-0" aria-hidden="true" />
                  <span aria-hidden="true">{{ countOf(member) }}</span>
                  <span class="sr-only">
                    {{ t('vouchers.available', { n: countOf(member) }, countOf(member)) }}
                  </span>
                </span>
              </template>
            </EventMemberPicker>
          </ResponsiveDialogBody>
        </ResponsiveDialogContent>
      </ResponsiveDialog>
    </template>
  </div>
</template>
