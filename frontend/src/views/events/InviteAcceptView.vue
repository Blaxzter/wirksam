<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { CalendarDays, CheckCircle2, XCircle } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

import type { EventInvitationPreview, EventRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { roleLabelKey } from '@/lib/event-roles'
import { formatDate } from '@/lib/format'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { get, post } = useAuthenticatedClient()

const token = computed(() => String(route.params.token ?? ''))

const preview = ref<EventInvitationPreview | null>(null)
const loading = ref(true)
const accepting = ref(false)
const notFound = ref(false)

/**
 * Why this link cannot be used, as a human sentence.
 *
 * A dead link deserves a reason — "expired" and "sent to a different address"
 * call for very different next steps from the person holding it.
 */
const invalidMessage = computed(() => {
  const reason = preview.value?.invalid_reason
  if (!reason) return null
  return t(`duties.events.invite.invalid.${reason}`)
})

/**
 * The preview needs a signed-in user, so a visitor without an account would
 * only ever see "invitation not found". Offer them the two ways in instead,
 * carrying the invitation along: back here after signing in, and to the
 * registration form, where it is what lets an invitation-only deployment
 * accept the signup.
 */
const signedOut = computed(() => !authStore.isAuthenticated)
const returnPath = computed(() => `/invite/${encodeURIComponent(token.value)}`)

async function loadPreview() {
  if (signedOut.value) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const res = await get<{ data: EventInvitationPreview }>({
      url: `/invitations/${token.value}`,
    })
    preview.value = res.data
  } catch {
    notFound.value = true
  } finally {
    loading.value = false
  }
}

async function accept() {
  accepting.value = true
  try {
    const res = await post<{ data: EventRead }>({
      url: `/invitations/${token.value}/accept`,
    })
    // Refresh the profile so the new membership is reflected in the store,
    // then drop the user straight into the event they just joined.
    await authStore.loadProfile()
    await authStore.setSelectedEvent(res.data.id)
    toast.success(t('duties.events.invite.joined', { name: res.data.name }))
    router.push({ name: 'home' })
  } catch (error) {
    toastApiError(error)
    accepting.value = false
  }
}

function goToEvent() {
  if (!preview.value) return
  void authStore.setSelectedEvent(preview.value.event_id).then(() => {
    router.push({ name: 'home' })
  })
}

onMounted(loadPreview)
</script>

<template>
  <div class="flex min-h-screen items-center justify-center p-4">
    <Card class="w-full max-w-md" data-testid="invite-card">
      <template v-if="loading">
        <CardContent class="py-12 text-center text-muted-foreground">
          {{ t('common.states.loading') }}
        </CardContent>
      </template>

      <template v-else-if="signedOut">
        <CardHeader class="text-center">
          <CheckCircle2 class="mx-auto h-10 w-10 text-primary" />
          <CardTitle data-testid="invite-signed-out">
            {{ t('duties.events.invite.signedOutTitle') }}
          </CardTitle>
          <CardDescription>{{ t('duties.events.invite.signedOutBody') }}</CardDescription>
        </CardHeader>
        <CardContent class="space-y-2">
          <Button
            class="w-full"
            data-testid="btn-invite-register"
            @click="
              router.push({
                name: 'register',
                query: { invite: token, redirect: returnPath },
              })
            "
          >
            {{ t('duties.events.invite.createAccount') }}
          </Button>
          <Button
            class="w-full"
            variant="outline"
            data-testid="btn-invite-login"
            @click="router.push({ name: 'login', query: { redirect: returnPath } })"
          >
            {{ t('duties.events.invite.signIn') }}
          </Button>
        </CardContent>
      </template>

      <template v-else-if="notFound || !preview">
        <CardHeader class="text-center">
          <XCircle class="mx-auto h-10 w-10 text-destructive" />
          <CardTitle data-testid="invite-not-found">
            {{ t('duties.events.invite.notFoundTitle') }}
          </CardTitle>
          <CardDescription>{{ t('duties.events.invite.notFoundBody') }}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button class="w-full" variant="outline" @click="router.push({ name: 'home' })">
            {{ t('duties.events.invite.goHome') }}
          </Button>
        </CardContent>
      </template>

      <template v-else>
        <CardHeader class="space-y-3 text-center">
          <CheckCircle2
            v-if="preview.is_valid || preview.already_member"
            class="mx-auto h-10 w-10 text-primary"
          />
          <XCircle v-else class="mx-auto h-10 w-10 text-destructive" />

          <CardTitle data-testid="invite-event-name">{{ preview.event_name }}</CardTitle>
          <CardDescription>
            <template v-if="preview.invited_by_name">
              {{ t('duties.events.invite.fromNamed', { name: preview.invited_by_name }) }}
            </template>
            <template v-else>{{ t('duties.events.invite.from') }}</template>
          </CardDescription>
        </CardHeader>

        <CardContent class="space-y-4">
          <div class="space-y-2 rounded-lg border p-3 text-sm">
            <p class="flex items-center gap-2 text-muted-foreground">
              <CalendarDays class="h-4 w-4 shrink-0" />
              {{ formatDate(preview.start_date) }} – {{ formatDate(preview.end_date) }}
            </p>
            <p v-if="preview.event_description" class="text-muted-foreground">
              {{ preview.event_description }}
            </p>
            <p class="flex items-center gap-2">
              <span class="text-muted-foreground">
                {{ t('duties.events.invite.asRole') }}
              </span>
              <Badge variant="secondary">{{ t(roleLabelKey(preview.role)) }}</Badge>
            </p>
          </div>

          <template v-if="preview.already_member">
            <p
              class="text-center text-sm text-muted-foreground"
              data-testid="invite-already-member"
            >
              {{ t('duties.events.invite.alreadyMember') }}
            </p>
            <Button class="w-full" data-testid="btn-open-event" @click="goToEvent">
              {{ t('duties.events.invite.openEvent') }}
            </Button>
          </template>

          <template v-else-if="preview.is_valid">
            <Button
              class="w-full"
              data-testid="btn-accept-invite"
              :disabled="accepting"
              @click="accept"
            >
              {{ t('duties.events.invite.accept') }}
            </Button>
            <Button
              class="w-full"
              variant="ghost"
              :disabled="accepting"
              @click="router.push({ name: 'home' })"
            >
              {{ t('duties.events.invite.decline') }}
            </Button>
          </template>

          <template v-else>
            <p class="text-center text-sm text-destructive" data-testid="invite-invalid">
              {{ invalidMessage }}
            </p>
            <Button class="w-full" variant="outline" @click="router.push({ name: 'home' })">
              {{ t('duties.events.invite.goHome') }}
            </Button>
          </template>
        </CardContent>
      </template>
    </Card>
  </div>
</template>
