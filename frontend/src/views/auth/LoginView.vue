<script setup lang="ts">
/**
 * Sign in with an email address and a password.
 *
 * The screen is a split: the pitch on the left, this form on the right, and no
 * navigation anywhere. Someone being asked for a password should not also be
 * offered a bar full of places to go instead — the only ways out are the two
 * links below the form, one to recover a forgotten password and one to create
 * an account.
 */
import { computed, ref } from 'vue'

import { EyeIcon, EyeOffIcon, LoaderIcon, LogInIcon } from '@lucide/vue'
import { toTypedSchema } from '@vee-validate/zod'
import { useForm } from 'vee-validate'
import { useI18n } from 'vue-i18n'
import type { RouteLocationRaw } from 'vue-router'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { z } from 'zod'

import { useAuth } from '@/composables/useAuth'

import AuthShell from '@/components/auth/AuthShell.vue'
import { Button } from '@/components/ui/button'
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form'
import { Input } from '@/components/ui/input'

import { zLoginRequest } from '@/client/zod.gen'
import { toastApiError } from '@/lib/api-errors'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const { login } = useAuth()

const busy = ref(false)
const showPassword = ref(false)
const formRef = ref<HTMLFormElement | null>(null)

/**
 * Where to land once signed in.
 *
 * `?redirect=` is written by the route guard, but it arrives through the URL
 * bar like any other query — so only a same-origin path is honoured. An
 * absolute URL there would make this screen an open redirect for anybody who
 * can get a link clicked, and the phishing version of that link is a real
 * sign-in page that hands the visitor onwards to a fake one.
 */
const redirectTarget = computed<RouteLocationRaw>(() => {
  const target = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  const isSameOrigin =
    target.startsWith('/') && !target.startsWith('//') && !target.startsWith('/\\')
  return isSameOrigin ? target : { name: 'home' }
})

/**
 * The generated schema, plus the one rule it cannot carry.
 *
 * `LoginRequest.password` is a bare `str` on the server, deliberately: accounts
 * predate the current policy, and validating a *login* against today's minimum
 * would tell somebody their own correct password is invalid. So the only rule
 * added here is "not empty", which spares a round trip and accuses nobody.
 *
 * Wrapped in a `computed` that reads `locale` so that switching language
 * re-runs validation — vee-validate re-validates when the schema *reference*
 * changes, and the messages themselves come from `lib/zod-i18n.ts` at parse
 * time.
 */
const loginSchema = computed(() => {
  void locale.value
  return toTypedSchema(zLoginRequest.extend({ password: z.string().min(1) }))
})

const { errors, handleSubmit } = useForm({
  validationSchema: loginSchema,
  initialValues: { email: '', password: '' },
})

/**
 * Live-validate a field only once it is already showing an error.
 *
 * vee-validate's defaults are `validateOnBlur` *and* `validateOnModelUpdate`,
 * so the first character typed into an empty email field turns it red — the
 * visitor is told they are wrong before they have finished being right. Blur is
 * the honest first verdict; from then on a keystroke can only clear an error
 * they are already looking at, and once it does this flips back off on its own.
 */
const liveValidate = (field: 'email' | 'password') => Boolean(errors.value[field])

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
  async (values) => {
    busy.value = true
    try {
      await login(values)
      toast.success(t('auth.login.success'))
      // Replace rather than push: the back button should return to wherever the
      // visitor came from, not to a sign-in form they have already used.
      await router.replace(redirectTarget.value)
    } catch (error) {
      toastApiError(error)
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
    hero="login"
    :icon="LogInIcon"
    :title="t('auth.login.title')"
    :description="t('auth.login.description')"
  >
    <form ref="formRef" class="space-y-4" data-testid="login-form" @submit="onSubmit">
      <FormField
        v-slot="{ componentField }"
        name="email"
        :validate-on-model-update="liveValidate('email')"
      >
        <FormItem>
          <FormLabel>{{ t('auth.login.fields.email.label') }}</FormLabel>
          <FormControl>
            <Input
              type="email"
              autocomplete="email"
              data-testid="input-email"
              :placeholder="t('auth.login.fields.email.placeholder')"
              v-bind="componentField"
            />
          </FormControl>
          <FormMessage />
        </FormItem>
      </FormField>

      <FormField
        v-slot="{ componentField }"
        name="password"
        :validate-on-model-update="liveValidate('password')"
      >
        <FormItem>
          <FormLabel>{{ t('auth.login.fields.password.label') }}</FormLabel>
          <div class="relative">
            <FormControl>
              <Input
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                class="pr-11"
                data-testid="input-password"
                :placeholder="t('auth.login.fields.password.placeholder')"
                v-bind="componentField"
              />
            </FormControl>
            <!-- Inset from the field's edge rather than flush with it: at
                 `right-0` the 36px button covered the border and both corner
                 arcs, and its 3px focus ring bled outside the field entirely. -->
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
          <FormMessage />
        </FormItem>
      </FormField>

      <Button class="w-full" type="submit" :disabled="busy" data-testid="btn-login">
        <LoaderIcon v-if="busy" class="size-4 animate-spin" />
        {{ busy ? t('auth.login.actions.submitting') : t('auth.login.actions.submit') }}
      </Button>

      <!-- Below the submit button, not beside the password label: anything
           focusable between the two inputs breaks the tab order the E2E suite
           asserts on. -->
      <div class="text-center">
        <RouterLink
          class="text-sm text-muted-foreground underline-offset-4 hover:underline"
          data-testid="link-forgot-password"
          :to="{ name: 'forgot-password' }"
        >
          {{ t('auth.login.actions.forgotPassword') }}
        </RouterLink>
      </div>
    </form>

    <template #footer>
      {{ t('auth.login.registerPrompt.text') }}
      <RouterLink
        class="font-medium text-primary underline-offset-4 hover:underline"
        data-testid="link-register"
        :to="{ name: 'register', query: route.query }"
      >
        {{ t('auth.login.registerPrompt.action') }}
      </RouterLink>
    </template>
  </AuthShell>
</template>
