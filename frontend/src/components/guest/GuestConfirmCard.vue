<script setup lang="ts">
/**
 * "Ist das deine Adresse?" on a guest's manage page, opened from the link in
 * one of our mails: confirming it puts every sign-up confirmed with that
 * address for the event on one page, with one balance of vouchers. Each
 * sign-up keeps its own name. Opening the page confirms nothing; only the
 * button does, so a link scanner that runs scripts cannot.
 *
 * "Das war ich nicht" sits next to it: whoever did not sign up has the same
 * mail in front of them.
 *
 * A page opened from the link the sign-up page showed cannot confirm (anyone
 * can type anyone's address). With an address it says where confirming
 * happens instead, conditionally, since the mail may never have gone out.
 */
import { computed } from 'vue'

import { LoaderIcon, MailCheckIcon, ShieldOffIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import type { GuestSignupManage } from '@/client/types.gen'

const props = withDefaults(
  defineProps<{
    view: GuestSignupManage
    /** The confirmation is on its way. */
    confirming?: boolean
    /** Any action of the page is running: neither button starts another. */
    busy?: boolean
  }>(),
  { confirming: false, busy: false },
)

const emit = defineEmits<{ confirm: []; notMe: [] }>()

const { t } = useI18n()

const text = computed(() =>
  t(
    props.view.vouchers.length > 0
      ? 'guestSignup.manage.confirm.textVouchers'
      : 'guestSignup.manage.confirm.text',
    { email: props.view.email ?? '', event: props.view.event.name },
  ),
)

const offersHint = computed(
  () => !props.view.can_confirm && !props.view.confirmed && !!props.view.email,
)
</script>

<template>
  <section
    v-if="view.can_confirm"
    class="space-y-3 rounded-xl border border-primary/40 bg-primary/5 p-4"
    aria-labelledby="guest-confirm-title"
    data-testid="guest-confirm"
  >
    <h2 id="guest-confirm-title" class="flex items-center gap-2 font-semibold">
      <MailCheckIcon class="size-5 shrink-0 text-primary" aria-hidden="true" />
      {{ t('guestSignup.manage.confirm.title') }}
    </h2>
    <p class="text-sm break-words" data-testid="guest-confirm-text">{{ text }}</p>
    <div class="flex flex-col gap-2 sm:flex-row">
      <!-- aria-disabled while it runs: focus stays on the button, and a second
           press sends nothing. -->
      <Button
        class="h-11 w-full aria-disabled:opacity-50 sm:w-auto"
        :aria-disabled="busy || undefined"
        data-testid="btn-guest-confirm"
        @click="!busy && emit('confirm')"
      >
        <LoaderIcon v-if="confirming" class="size-4 animate-spin" aria-hidden="true" />
        {{ t('guestSignup.manage.confirm.yes') }}
      </Button>
      <Button
        v-if="view.can_reject"
        variant="outline"
        class="h-11 w-full aria-disabled:opacity-50 sm:w-auto"
        :aria-disabled="busy || undefined"
        data-testid="btn-guest-not-me"
        @click="!busy && emit('notMe')"
      >
        <ShieldOffIcon class="size-4" aria-hidden="true" />
        {{ t('guestSignup.manage.notMe.button') }}
      </Button>
    </div>
  </section>

  <p
    v-else-if="offersHint"
    class="rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground"
    data-testid="guest-confirm-from-mail"
  >
    {{ t('guestSignup.manage.confirm.fromMailOnly') }}
  </p>
</template>
