<script setup lang="ts">
/**
 * Ask for a password-reset link.
 *
 * The endpoint answers 202 whether or not the address belongs to anybody, and
 * this screen has to keep that promise: there is exactly one confirmation, it
 * is worded so that it says nothing either way, and it is shown for every
 * address that was typed. A "no such account" message here would turn the form
 * into a membership oracle — type an address, learn whether that person uses
 * the service.
 */
import { computed, ref, watch } from 'vue'

import { KeyRoundIcon, LoaderIcon, MailCheckIcon } from '@lucide/vue'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { useI18n } from 'vue-i18n'

import AuthShell from '@/components/auth/AuthShell.vue'
import { Button } from '@/components/ui/button'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import FormError from '@/components/utils/FormError.vue'

import { client } from '@/client/client.gen'
import { zForgotPasswordRequest } from '@/client/zod.gen'
import { toastApiError } from '@/lib/api-errors'

const { t, locale } = useI18n()

const busy = ref(false)
/** The address the confirmation is about — never a claim that it was found. */
const submittedEmail = ref<string | null>(null)
const formRef = ref<HTMLFormElement | null>(null)
/** The server's refusal of the last attempt, shown above the submit button. */
const submitError = ref<string | null>(null)

/** Wrapped so a language switch re-runs validation — see `LoginView.vue`. */
const forgotSchema = computed(() => {
  void locale.value
  return toTypedSchema(zForgotPasswordRequest)
})

const { errors, values, handleSubmit, resetForm } = useForm({
  validationSchema: forgotSchema,
  initialValues: { email: '' },
})

/** Cleared once the address changes — see `LoginView.vue`. */
watch(values, () => (submitError.value = null), { deep: true })

const liveValidate = (field: 'email') => Boolean(errors.value[field])

/**
 * Send the cursor to the first field that is actually wrong.
 *
 * Somebody submitting from the keyboard has to be told *where* the problem is,
 * not just that there is one. Walked in DOM order rather than over
 * `Object.keys(errors)`, whose order comes from the generated schema and does
 * not have to match the order the fields are laid out in — on the register form
 * it lists `email` before `name`, and the cursor would skip the first field on
 * the screen. Scoped to this form, so nothing else on the page can steal focus.
 */
function focusFirstInvalid(form: HTMLFormElement | null, invalid: Record<string, unknown>): void {
  if (!form) return
  const fields = Array.from(form.querySelectorAll<HTMLElement>('[name]'))
  const first = fields.find((field) => invalid[field.getAttribute('name') ?? ''])
  first?.focus()
}

const onSubmit = handleSubmit(
  async (formValues) => {
    busy.value = true
    submitError.value = null
    try {
      // A public endpoint: no bearer token to attach, so this goes straight to
      // the generated client rather than through `useAuthenticatedClient`, which
      // would throw for the anonymous visitor this page exists for.
      await client.post<unknown, unknown, true>({
        url: '/auth/forgot-password',
        body: formValues,
        throwOnError: true,
      })
      submittedEmail.value = formValues.email
    } catch (error) {
      // Reached by a rate limit or an outage — never by "no such address".
      submitError.value = toastApiError(error).message
    } finally {
      busy.value = false
    }
  },
  ({ errors: invalid }) => {
    focusFirstInvalid(formRef.value, invalid)
  },
)

function startOver() {
  submittedEmail.value = null
  resetForm()
}
</script>

<template>
  <AuthShell
    hero="forgotPassword"
    :icon="submittedEmail ? MailCheckIcon : KeyRoundIcon"
    :title="submittedEmail ? t('auth.forgotPassword.sent.title') : t('auth.forgotPassword.title')"
    :description="
      submittedEmail
        ? t('auth.forgotPassword.sent.description', { email: submittedEmail })
        : t('auth.forgotPassword.description')
    "
    :description-testid="submittedEmail ? 'forgot-password-sent' : undefined"
  >
    <template v-if="submittedEmail">
      <div class="space-y-4">
        <p class="text-sm text-muted-foreground">
          {{ t('auth.forgotPassword.sent.hint') }}
        </p>
        <Button
          class="w-full"
          variant="outline"
          data-testid="btn-forgot-password-retry"
          @click="startOver"
        >
          {{ t('auth.forgotPassword.sent.retry') }}
        </Button>
        <Button class="w-full" variant="ghost" as-child data-testid="link-back-to-login">
          <RouterLink :to="{ name: 'login' }">
            {{ t('auth.forgotPassword.actions.backToLogin') }}
          </RouterLink>
        </Button>
      </div>
    </template>

    <template v-else>
      <form
        ref="formRef"
        class="space-y-4"
        data-testid="forgot-password-form"
        @submit="onSubmit"
      >
        <FormField
          v-slot="{ componentField }"
          name="email"
          :validate-on-model-update="liveValidate('email')"
        >
          <FormItem>
            <FormLabel>{{ t('auth.forgotPassword.fields.email.label') }}</FormLabel>
            <FormControl>
              <Input
                type="email"
                autocomplete="email"
                data-testid="input-email"
                :placeholder="t('auth.forgotPassword.fields.email.placeholder')"
                v-bind="componentField"
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        </FormField>

        <FormError :message="submitError" />

        <Button
          class="w-full"
          type="submit"
          :disabled="busy"
          data-testid="btn-forgot-password-submit"
        >
          <LoaderIcon v-if="busy" class="size-4 animate-spin" />
          {{
            busy
              ? t('auth.forgotPassword.actions.submitting')
              : t('auth.forgotPassword.actions.submit')
          }}
        </Button>

        <Button class="w-full" variant="ghost" as-child data-testid="link-back-to-login">
          <RouterLink :to="{ name: 'login' }">
            {{ t('auth.forgotPassword.actions.backToLogin') }}
          </RouterLink>
        </Button>
      </form>
    </template>
  </AuthShell>
</template>
