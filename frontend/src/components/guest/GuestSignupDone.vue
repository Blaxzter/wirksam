<script setup lang="ts">
/**
 * "Du bist eingetragen": the shift, how to get back to it, and what next.
 *
 * Getting back is the confirmation mail's link where one went out. Where none
 * did (no address, or the mail could not be sent) the page shows the manage
 * link itself, since it is then the guest's only way to take their name off.
 *
 * The link is the guest's only key: whoever holds it can change their sign-ups
 * and, where the shift gives vouchers, spend them. So the page asks them not to
 * pass it on, says where the vouchers are redeemed, and how long the details
 * are kept (the list's own number of days, naming only what it asks for).
 *
 * The page is also the hand-over point on a shared device, a tablet at the
 * stand. "Fertig – nächste Person", or two minutes without a touch, forget the
 * guest entirely (`store.reset()` in the parent), so the next person is handed
 * neither their address nor their undo button.
 */
import { computed, onMounted, useTemplateRef, watch } from 'vue'

import { CheckIcon, CopyIcon, LoaderIcon, Ticket } from '@lucide/vue'
import { useIdle } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useClipboardCopy } from '@/composables/useClipboardCopy'
import { useFormatters } from '@/composables/useFormatters'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

import type { PublicSharedList, PublicSignupResult } from '@/client/types.gen'
import {
  IDLE_RESET_MS,
  LONG_DAY,
  dayAndTime,
  guestManageUrl,
  retentionVariant,
} from '@/lib/guest-signup'

const props = withDefaults(
  defineProps<{
    result: PublicSignupResult
    /** The list signed up on: what it asks for, and how long that is kept. */
    list: PublicSharedList
    /** Where the chain's confirmation went, if one went. */
    mailedTo: string | null
    /** The manage token to show as a link to keep, when no mail carries it. */
    linkToKeep: string | null
    undoing?: boolean
  }>(),
  { undoing: false },
)

const emit = defineEmits<{ another: []; undo: []; next: [] }>()

const { t } = useI18n()
const { formatDateLabel, formatTimeRange } = useFormatters()

const heading = useTemplateRef<HTMLElement>('heading')
const { copied, copy } = useClipboardCopy<'manageLink'>()

const manageUrl = computed(() => (props.linkToKeep ? guestManageUrl(props.linkToKeep) : null))
/** `remaining` is null when the list sets no limit per person. */
const canAddAnother = computed(() => props.result.remaining !== 0)
/** Only a chain's first sign-up is mailed or shows the link; later ones point back to it. */
const first = computed(() => props.result.mail_queued || props.result.show_manage_link)

const when = computed(() =>
  dayAndTime(
    formatDateLabel(props.result.date, LONG_DAY),
    formatTimeRange(props.result.shift.start_time, props.result.shift.end_time),
  ),
)

/** What the shift earns; 0 for a task without vouchers. */
const vouchers = computed(() => props.result.shift.vouchers ?? 0)

/** Where the vouchers are redeemed: through the mail's link, or the one shown here. */
const redeemHint = computed(() => {
  if (vouchers.value === 0) return null
  if (props.mailedTo) return t('guestSignup.done.redeemMail')
  return manageUrl.value ? t('guestSignup.done.redeemLink') : null
})

/** Whoever has the link can change the sign-ups, and spend the vouchers. */
const linkPrivate = computed(() =>
  vouchers.value > 0
    ? t('guestSignup.done.linkPrivateVouchers')
    : t('guestSignup.done.linkPrivate'),
)

/** How long the details are kept, as the form said it: the same sentence. */
const retention = computed(() => {
  const days = props.list.retention_days
  const variant = retentionVariant(props.list.ask_email !== 'off', props.list.ask_phone !== 'off')
  const line = t(`guestSignup.retention.${variant}`, { days }, days)
  return vouchers.value > 0 ? `${line} ${t('guestSignup.retention.vouchers')}` : line
})

async function copyLink(): Promise<void> {
  const url = manageUrl.value
  if (!url) return
  if (await copy('manageLink', url)) {
    toast.success(t('guestSignup.done.keepLink.copied'))
  } else {
    // A blocked clipboard: the link stays selectable in the field.
    toast.info(url)
  }
}

const { idle } = useIdle(IDLE_RESET_MS)
watch(idle, (isIdle) => {
  if (isIdle) emit('next')
})

onMounted(() => heading.value?.focus({ preventScroll: true }))
</script>

<template>
  <section
    class="grid justify-items-center gap-4 py-4 text-center"
    aria-labelledby="guest-done-title"
    data-testid="guest-signup-done"
  >
    <span
      aria-hidden="true"
      class="grid size-13 place-items-center rounded-full bg-primary/15 text-primary"
    >
      <CheckIcon class="size-6" />
    </span>
    <h2
      id="guest-done-title"
      ref="heading"
      tabindex="-1"
      class="text-xl font-bold focus:outline-none"
    >
      {{ t('guestSignup.done.title') }}
    </h2>

    <div class="space-y-0.5" data-testid="guest-done-shift">
      <p class="font-semibold break-words">{{ result.shift.task_name }}</p>
      <p class="text-sm">{{ when }}</p>
      <p v-if="result.shift.location" class="text-sm break-words">{{ result.shift.location }}</p>
    </div>

    <div
      v-if="vouchers > 0"
      class="max-w-prose space-y-1 rounded-xl bg-primary/10 p-3 text-sm"
      data-testid="guest-done-vouchers"
    >
      <p class="flex items-start justify-center gap-1.5 font-medium">
        <Ticket class="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        {{ t('guestSignup.form.vouchers', { n: vouchers }, vouchers) }}
      </p>
      <p v-if="redeemHint" class="text-muted-foreground" data-testid="guest-done-redeem">
        {{ redeemHint }}
      </p>
    </div>

    <p
      v-if="mailedTo"
      class="max-w-prose text-sm text-muted-foreground"
      data-testid="guest-done-mail"
    >
      {{
        first
          ? t('guestSignup.done.mailSent', { email: mailedTo })
          : t('guestSignup.done.mailSentBefore', { email: mailedTo })
      }}
      <span class="block pt-1" data-testid="guest-done-link-private">{{ linkPrivate }}</span>
    </p>

    <div
      v-if="manageUrl"
      class="w-full space-y-2 rounded-xl border bg-card p-4 text-left"
      data-testid="guest-done-keep-link"
    >
      <p class="text-sm font-semibold">
        {{
          vouchers > 0
            ? t('guestSignup.done.keepLink.textVouchers')
            : t('guestSignup.done.keepLink.text')
        }}
      </p>
      <div class="flex gap-2">
        <Input
          :model-value="manageUrl"
          readonly
          class="h-11 min-w-0 flex-1 font-mono text-xs"
          :aria-label="t('guestSignup.done.keepLink.label')"
          data-testid="guest-manage-link"
        />
        <Button
          type="button"
          variant="outline"
          class="h-11 shrink-0"
          data-testid="btn-copy-manage-link"
          @click="copyLink"
        >
          <CheckIcon v-if="copied === 'manageLink'" class="size-4" aria-hidden="true" />
          <CopyIcon v-else class="size-4" aria-hidden="true" />
          <span class="max-sm:sr-only">{{ t('guestSignup.done.keepLink.copy') }}</span>
        </Button>
      </div>
      <p
        v-if="!mailedTo"
        class="text-xs text-muted-foreground"
        data-testid="guest-done-link-private"
      >
        {{ linkPrivate }}
      </p>
    </div>

    <div class="grid w-full gap-2 pt-2">
      <Button
        v-if="canAddAnother"
        class="h-12 w-full text-base"
        data-testid="btn-guest-another"
        @click="emit('another')"
      >
        {{ t('guestSignup.done.another') }}
      </Button>
      <p v-else class="text-sm text-muted-foreground" data-testid="guest-done-no-more">
        {{ t('guestSignup.done.noMore') }}
      </p>
      <Button
        :variant="canAddAnother ? 'outline' : 'default'"
        class="h-12 w-full text-base"
        data-testid="btn-guest-next"
        @click="emit('next')"
      >
        {{ t('guestSignup.done.nextPerson') }}
      </Button>
      <!-- aria-disabled while it runs: a refusal leaves focus on the button. -->
      <Button
        variant="ghost"
        class="h-11 w-full text-destructive hover:text-destructive aria-disabled:opacity-50"
        :aria-disabled="undoing || undefined"
        data-testid="btn-guest-undo"
        @click="!undoing && emit('undo')"
      >
        <LoaderIcon v-if="undoing" class="size-4 animate-spin" aria-hidden="true" />
        {{ t('guestSignup.done.undo') }}
      </Button>
    </div>

    <p class="max-w-prose text-xs text-muted-foreground" data-testid="guest-done-retention">
      {{ retention }}
    </p>
    <p class="max-w-prose text-xs text-muted-foreground">{{ t('guestSignup.done.idleHint') }}</p>
  </section>
</template>
