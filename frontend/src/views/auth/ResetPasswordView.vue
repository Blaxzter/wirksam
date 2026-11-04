<script setup lang="ts">
/**
 * Redeem a reset link and choose a new password.
 *
 * The secret arrives as `?token=` and never leaves this component except in the
 * request body — it is not put in a route param, where it would end up in the
 * breadcrumb trail, nor kept after the flow finishes.
 *
 * A link that has expired, been used, or been mangled by a mail client is a
 * dead end, and it is treated as one: the form is replaced outright by a panel
 * that says so and offers the one thing that helps, a fresh link. Leaving the
 * form up would only collect a password that cannot be saved.
 */
import { computed, ref, watch } from 'vue'

import { EyeIcon, EyeOffIcon, LoaderIcon, LockKeyholeIcon, TriangleAlertIcon } from '@lucide/vue'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { z } from 'zod'

import AuthShell from '@/components/auth/AuthShell.vue'
import PasswordRequirement from '@/components/auth/PasswordRequirement.vue'
import { Button } from '@/components/ui/button'
import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import FormError from '@/components/utils/FormError.vue'

import { client } from '@/client/client.gen'
import { zResetPasswordRequest } from '@/client/zod.gen'
import { normalizeApiError, toastApiError } from '@/lib/api-errors'

/** Mirrors `settings.PASSWORD_MIN_LENGTH`; see the note in `RegisterView.vue`. */
const PASSWORD_MIN_LENGTH = 8

/** Mirrors `BCRYPT_MAX_PASSWORD_BYTES`; see the note in `RegisterView.vue`. */
const PASSWORD_MAX_BYTES = 72

const byteLength = (value: string) => new TextEncoder().encode(value).length

/** The two problem codes that mean "this link is over", whatever the reason. */
const DEAD_LINK_CODES = new Set(['auth.invalid_token', 'auth.token_expired'])

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()

const token = typeof route.query.token === 'string' ? route.query.token : ''

const busy = ref(false)
const showPassword = ref(false)
const formRef = ref<HTMLFormElement | null>(null)
/** The server's refusal of the last attempt, shown above the submit button. */
const submitError = ref<string | null>(null)
/** True once the link is known to be unusable — either on arrival or on submit. */
const linkIsDead = ref(token === '')

const resetSchema = computed(() => {
  void locale.value
  return toTypedSchema(
    zResetPasswordRequest
      .extend({
        password: z
          .string()
          .min(PASSWORD_MIN_LENGTH)
          .refine((value) => byteLength(value) <= PASSWORD_MAX_BYTES, {
            error: () => t('auth.password.maxBytes'),
          }),
        confirm_password: z.string(),
      })
      .refine((values) => values.password === values.confirm_password, {
        error: () => t('auth.password.mismatch'),
        path: ['confirm_password'],
      }),
  )
})

const { errors, values, handleSubmit } = useForm({
  validationSchema: resetSchema,
  // The token rides along as an ordinary form value so the generated schema
  // validates it with everything else, but it has no field of its own.
  initialValues: { token, password: '', confirm_password: '' },
})

/** Cleared once either password changes — see `LoginView.vue`. */
watch(values, () => (submitError.value = null), { deep: true })

const passwordLongEnough = computed(
  () => String(values.password ?? '').length >= PASSWORD_MIN_LENGTH,
)

/** See the note on the same helper in `LoginView.vue`. */
const liveValidate = (field: 'password' | 'confirm_password') => Boolean(errors.value[field])

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
      // Public endpoint, and `confirm_password` is a UI-only field — send
      // exactly what the schema on the other side expects.
      await client.post<unknown, unknown, true>({
        url: '/auth/reset-password',
        body: { token: formValues.token, password: formValues.password },
        throwOnError: true,
      })
      toast.success(t('auth.resetPassword.success'))
      await router.replace({ name: 'login' })
    } catch (error) {
      const normalized = normalizeApiError(error)
      if (normalized.code && DEAD_LINK_CODES.has(normalized.code)) {
        linkIsDead.value = true
        return
      }
      submitError.value = toastApiError(error).message
    } finally {
      busy.value = false
    }
  },
  ({ errors: invalid }) => {
    focusFirstInvalid(formRef.value, invalid)
  },
)
</script>

<template>
  <AuthShell
    hero="resetPassword"
    :hero-problem="linkIsDead"
    :icon="linkIsDead ? TriangleAlertIcon : LockKeyholeIcon"
    :tone="linkIsDead ? 'destructive' : 'primary'"
    :title="linkIsDead ? t('auth.resetPassword.invalid.title') : t('auth.resetPassword.title')"
    :description="
      linkIsDead
        ? t('auth.resetPassword.invalid.description')
        : t('auth.resetPassword.description')
    "
    :description-testid="linkIsDead ? 'reset-password-invalid' : undefined"
  >
    <template v-if="linkIsDead">
      <div class="space-y-4">
        <Button class="w-full" as-child data-testid="link-request-new">
          <RouterLink :to="{ name: 'forgot-password' }">
            {{ t('auth.resetPassword.actions.requestNew') }}
          </RouterLink>
        </Button>
        <Button class="w-full" variant="ghost" as-child data-testid="link-back-to-login">
          <RouterLink :to="{ name: 'login' }">
            {{ t('auth.forgotPassword.actions.backToLogin') }}
          </RouterLink>
        </Button>
      </div>
    </template>

    <template v-else>
      <form ref="formRef" class="space-y-4" data-testid="reset-password-form" @submit="onSubmit">
        <FormField
          v-slot="{ componentField, errorMessage }"
          name="password"
          :validate-on-model-update="liveValidate('password')"
        >
          <FormItem>
            <FormLabel>{{ t('auth.resetPassword.fields.password.label') }}</FormLabel>
            <div class="relative">
              <FormControl>
                <Input
                  :type="showPassword ? 'text' : 'password'"
                  autocomplete="new-password"
                  class="pr-11"
                  data-testid="input-password"
                  :placeholder="t('auth.resetPassword.fields.password.placeholder')"
                  v-bind="componentField"
                />
              </FormControl>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                class="absolute top-1/2 right-1 size-7 -translate-y-1/2 rounded-sm text-muted-foreground hover:bg-transparent hover:text-foreground focus-visible:ring-2"
                data-testid="btn-toggle-password"
                :aria-label="
                  showPassword ? t('common.actions.hidePassword') : t('common.actions.showPassword')
                "
                @click="showPassword = !showPassword"
              >
                <EyeOffIcon v-if="showPassword" class="size-4" />
                <EyeIcon v-else class="size-4" />
              </Button>
            </div>
            <!-- One row for the rule, the tick and the error. See RegisterView. -->
            <FormDescription aria-live="polite">
              <PasswordRequirement
                :label="t('auth.password.requirement.unmet', { min: PASSWORD_MIN_LENGTH })"
                :met-label="t('auth.password.requirement.met')"
                :met="passwordLongEnough"
                :message="errorMessage"
              />
            </FormDescription>
          </FormItem>
        </FormField>

        <FormField
          v-slot="{ componentField }"
          name="confirm_password"
          :validate-on-model-update="liveValidate('confirm_password')"
        >
          <FormItem>
            <FormLabel>{{ t('auth.resetPassword.fields.confirmPassword.label') }}</FormLabel>
            <FormControl>
              <Input
                :type="showPassword ? 'text' : 'password'"
                autocomplete="new-password"
                data-testid="input-confirm-password"
                :placeholder="t('auth.resetPassword.fields.confirmPassword.placeholder')"
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
          data-testid="btn-reset-password-submit"
        >
          <LoaderIcon v-if="busy" class="size-4 animate-spin" />
          {{
            busy
              ? t('auth.resetPassword.actions.submitting')
              : t('auth.resetPassword.actions.submit')
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
