<script setup lang="ts">
/**
 * Signing up for one shift of a shared list, without an account.
 *
 * It asks for a name, then an address and a phone number as far as the list
 * wants them, and says plainly who will see what. The fields live in the store,
 * not here, so they survive "sign up for another shift" and go only when the
 * guest is done.
 *
 * The fine print also says how long the details are kept, naming only what the
 * list asks for, with the server's number of days, and that unredeemed vouchers
 * expire then where the shift gives some.
 *
 * The checks before sending mirror the server's (`lib/guest-signup.ts`). Every
 * refused field shows its reason under it, and focus goes to the first of them
 * in the order the form reads, so a keyboard user lands on the problem.
 */
import { computed, nextTick, onMounted, reactive, ref, useTemplateRef } from 'vue'

import { ChevronLeftIcon, LoaderIcon, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useGuestSignupStore } from '@/stores/guestSignup'

import { useAppConfig } from '@/composables/useAppConfig'
import { useFormatters } from '@/composables/useFormatters'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

import TurnstileWidget from '@/components/auth/TurnstileWidget.vue'
import GuestFormField from '@/components/guest/GuestFormField.vue'
import FormError from '@/components/utils/FormError.vue'

import type { PublicSharedList, PublicShift } from '@/client/types.gen'
import {
  type FieldProblems,
  type GuestField,
  type RetentionVariant,
  LONG_DAY,
  checkGuestFields,
  dayAndTime,
  retentionVariant,
} from '@/lib/guest-signup'

const props = defineProps<{
  list: PublicSharedList
  shift: PublicShift
  /** The shift's day, `YYYY-MM-DD`. */
  date: string
}>()

const emit = defineEmits<{ back: []; done: [] }>()

const { t } = useI18n()
const { formatDateLabel, formatTimeRange } = useFormatters()
const store = useGuestSignupStore()

/** The deployment's bot check, rendered only where it has a site key (see `RegisterView`). */
const turnstileSiteKey = useAppConfig().TURNSTILE_SITE_KEY
const turnstileToken = ref<string | null>(null)
const turnstile = useTemplateRef<InstanceType<typeof TurnstileWidget>>('turnstile')
const awaitingChallenge = computed(() => Boolean(turnstileSiteKey) && !turnstileToken.value)

const form = useTemplateRef<HTMLFormElement>('form')
const heading = useTemplateRef<HTMLElement>('heading')
const busy = ref(false)
const submitError = ref<string | null>(null)
const errors = reactive<Partial<Record<GuestField, string>>>({})

const asksEmail = computed(() => props.list.ask_email !== 'off')
const asksPhone = computed(() => props.list.ask_phone !== 'off')
/** The reminder goes by mail, so it is offered once there is an address to send it to. */
const offersReminder = computed(() => asksEmail.value && store.fields.email.trim() !== '')

const when = computed(() =>
  dayAndTime(
    formatDateLabel(props.date, LONG_DAY),
    formatTimeRange(props.shift.start_time, props.shift.end_time),
  ),
)

/** What the shift earns; 0 for a task without vouchers. */
const vouchers = computed(() => props.shift.vouchers ?? 0)

/** Who sees the contact details: named only for the fields this list asks for. */
const CONTACT_NOTE: Record<RetentionVariant, string | null> = {
  name: null,
  nameEmail: 'guestSignup.privacyNote.contact.email',
  namePhone: 'guestSignup.privacyNote.contact.phone',
  all: 'guestSignup.privacyNote.contact.emailPhone',
}

/**
 * Who sees what, and how long it is kept. One string, so the space before the
 * link survives the template's whitespace.
 */
const privacyNote = computed(() => {
  const days = props.list.retention_days
  const variant = retentionVariant(asksEmail.value, asksPhone.value)
  const contact = CONTACT_NOTE[variant]
  const parts = [t('guestSignup.privacyNote.names')]
  if (contact) parts.push(t(contact))
  if (props.list.show_names === 'first') parts.push(t('guestSignup.privacyNote.firstName'))
  parts.push(t(`guestSignup.retention.${variant}`, { days }, days))
  if (vouchers.value > 0) parts.push(t('guestSignup.retention.vouchers'))
  return parts.join(' ')
})

const optionalLabel = (mode: PublicSharedList['ask_email']) =>
  mode === 'optional' ? t('guestSignup.form.optional') : undefined

function showProblems(problems: FieldProblems): void {
  for (const field of ['name', 'email', 'phone'] as const) {
    const key = problems[field]
    if (key) errors[field] = t(key)
    else delete errors[field]
  }
}

/** The first refused field in the order the form lays them out. */
async function focusFirstInvalid(): Promise<void> {
  await nextTick()
  form.value?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()
}

async function submit(): Promise<void> {
  if (busy.value) return
  submitError.value = null
  const problems = checkGuestFields(store.fields, props.list.ask_email, props.list.ask_phone)
  showProblems(problems)
  if (Object.keys(problems).length > 0) {
    await focusFirstInvalid()
    return
  }

  busy.value = true
  try {
    const outcome = await store.signUp({
      shiftId: props.shift.id,
      showNames: props.list.show_names,
      turnstileToken: turnstileToken.value,
    })
    if (outcome.ok) {
      emit('done')
      return
    }
    // A Turnstile token is single-use, so any refusal needs a fresh one before
    // the next attempt, whatever the refusal was about.
    turnstile.value?.reset()
    if (outcome.field) {
      errors[outcome.field] = outcome.message
      await focusFirstInvalid()
    } else {
      submitError.value = outcome.message
    }
  } finally {
    busy.value = false
  }
}

onMounted(() => heading.value?.focus({ preventScroll: true }))
</script>

<template>
  <form
    ref="form"
    class="space-y-5"
    novalidate
    data-testid="guest-signup-form"
    @submit.prevent="submit"
  >
    <Button
      type="button"
      variant="ghost"
      class="-ml-3 h-10 text-primary"
      data-testid="btn-guest-back"
      @click="emit('back')"
    >
      <ChevronLeftIcon class="size-4" aria-hidden="true" />
      {{ t('guestSignup.form.back') }}
    </Button>

    <section
      class="space-y-0.5 rounded-xl bg-primary/10 p-4"
      aria-labelledby="guest-signup-summary"
      data-testid="guest-signup-summary"
    >
      <p class="text-xs font-semibold tracking-wider text-muted-foreground uppercase">
        {{ t('guestSignup.form.summary') }}
      </p>
      <h2
        id="guest-signup-summary"
        ref="heading"
        tabindex="-1"
        class="font-semibold break-words focus:outline-none"
      >
        {{ shift.task_name }}
      </h2>
      <p class="text-sm">{{ when }}</p>
      <p v-if="shift.location" class="text-sm break-words">{{ shift.location }}</p>
      <p
        v-if="vouchers > 0"
        class="flex items-start gap-1.5 pt-1 text-sm font-medium"
        data-testid="guest-signup-vouchers"
      >
        <Ticket class="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
        {{ t('guestSignup.form.vouchers', { n: vouchers }, vouchers) }}
      </p>
    </section>

    <GuestFormField
      id="guest-name"
      :label="t('guestSignup.form.fields.name.label')"
      :error="errors.name"
    >
      <template #default="field">
        <Input
          :id="field.id"
          v-model="store.fields.name"
          name="name"
          type="text"
          autocomplete="name"
          maxlength="100"
          class="h-11"
          :placeholder="t('guestSignup.form.fields.name.placeholder')"
          :aria-invalid="field.invalid"
          :aria-describedby="field.describedBy"
          data-testid="guest-input-name"
        />
      </template>
    </GuestFormField>

    <GuestFormField
      v-if="asksEmail"
      id="guest-email"
      :label="t('guestSignup.form.fields.email.label')"
      :optional-label="optionalLabel(list.ask_email)"
      :hint="t('guestSignup.form.fields.email.hint')"
      :error="errors.email"
    >
      <template #default="field">
        <Input
          :id="field.id"
          v-model="store.fields.email"
          name="email"
          type="email"
          inputmode="email"
          autocomplete="email"
          maxlength="254"
          class="h-11"
          :aria-invalid="field.invalid"
          :aria-describedby="field.describedBy"
          data-testid="guest-input-email"
        />
      </template>
    </GuestFormField>

    <GuestFormField
      v-if="asksPhone"
      id="guest-phone"
      :label="t('guestSignup.form.fields.phone.label')"
      :optional-label="optionalLabel(list.ask_phone)"
      :hint="t('guestSignup.form.fields.phone.hint')"
      :error="errors.phone"
    >
      <template #default="field">
        <Input
          :id="field.id"
          v-model="store.fields.phone"
          name="phone"
          type="tel"
          autocomplete="tel"
          maxlength="30"
          class="h-11"
          :aria-invalid="field.invalid"
          :aria-describedby="field.describedBy"
          data-testid="guest-input-phone"
        />
      </template>
    </GuestFormField>

    <div v-if="offersReminder" class="flex items-start gap-3">
      <Checkbox
        id="guest-remind"
        :model-value="store.fields.remind"
        class="mt-0.5 size-5"
        data-testid="guest-check-remind"
        @update:model-value="(value) => (store.fields.remind = value === true)"
      />
      <Label for="guest-remind" class="leading-snug font-normal">
        {{ t('guestSignup.form.remind') }}
      </Label>
    </div>

    <TurnstileWidget
      v-if="turnstileSiteKey"
      ref="turnstile"
      :site-key="turnstileSiteKey"
      action="shared-list-signup"
      @update:token="turnstileToken = $event"
    />

    <FormError :message="submitError" />

    <div class="space-y-2">
      <Button
        type="submit"
        class="h-12 w-full text-base"
        :disabled="busy || awaitingChallenge"
        data-testid="btn-guest-submit"
      >
        <LoaderIcon v-if="busy" class="size-4 animate-spin" aria-hidden="true" />
        {{ busy ? t('guestSignup.form.submitting') : t('guestSignup.form.submit') }}
      </Button>
      <p
        v-if="awaitingChallenge"
        class="text-center text-sm text-muted-foreground"
        aria-live="polite"
        data-testid="guest-awaiting-check"
      >
        {{ t('guestSignup.form.awaitingCheck') }}
      </p>
    </div>

    <p class="text-xs leading-relaxed text-muted-foreground" data-testid="guest-privacy-note">
      {{ privacyNote }}
      <RouterLink
        :to="{ name: 'privacy' }"
        target="_blank"
        rel="noopener"
        class="font-medium text-primary underline underline-offset-4"
      >
        {{ t('guestSignup.privacyNote.link') }}
      </RouterLink>
    </p>
  </form>
</template>
