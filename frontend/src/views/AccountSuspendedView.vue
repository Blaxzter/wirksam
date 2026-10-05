<script setup lang="ts">
/**
 * Shown when an account may sign in but not use the app.
 *
 * Three reasons, one screen: a moderator suspended the account (`is_active`),
 * or, on a deployment running `REGISTRATION_MODE=approval`, it is waiting for
 * a superadmin or was turned away. Each needs to be told rather than left on a
 * home page where every request comes back 403, and each can still sign out or
 * delete the account. The router guard picks the route; the text comes from
 * the store, so both routes render whatever is actually true.
 */
import { computed, ref } from 'vue'

import { Ban, Hourglass, LogOut, RefreshCw } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import {
  ResponsiveDialog,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
  ResponsiveDialogTrigger,
} from '@/components/ui/responsive-dialog'

import LanguageSwitch from '@/components/utils/LanguageSwitch.vue'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { delete: del } = useAuthenticatedClient()

type BlockedState = 'suspended' | 'pending' | 'rejected'

const state = computed<BlockedState>(() => {
  if (!authStore.isActive) return 'suspended'
  return authStore.approvalStatus === 'pending' ? 'pending' : 'rejected'
})

const reason = computed(() =>
  state.value === 'pending' ? null : authStore.profile?.rejection_reason,
)

const title = computed(() =>
  state.value === 'suspended'
    ? t('common.accountSuspended.title')
    : t(`common.accountApproval.${state.value}.title`),
)
const description = computed(() =>
  state.value === 'suspended'
    ? t('common.accountSuspended.description')
    : t(`common.accountApproval.${state.value}.description`),
)

const checking = ref(false)

/** Ask again whether the account was approved, without signing out and in. */
const checkAgain = async () => {
  checking.value = true
  try {
    await authStore.loadProfile()
    if (authStore.isApproved && authStore.isActive) {
      await router.replace({ name: 'home' })
    }
  } finally {
    checking.value = false
  }
}

const showDeleteDialog = ref(false)
const isDeleting = ref(false)
const errorMessage = ref<string | null>(null)

const handleDeleteAccount = async () => {
  isDeleting.value = true
  errorMessage.value = null
  try {
    await del({ url: '/users/me' })
    authStore.logout()
  } catch (error) {
    console.error('Account deletion error:', error)
    errorMessage.value = t('common.accountSuspended.deleteError')
    showDeleteDialog.value = false
  } finally {
    isDeleting.value = false
  }
}
</script>

<template>
  <div class="flex items-center justify-center">
    <div class="mx-auto max-w-md text-center">
      <div class="mb-6 flex justify-center">
        <div v-if="state === 'pending'" class="rounded-full bg-primary/10 p-4">
          <Hourglass class="h-12 w-12 text-primary" />
        </div>
        <div v-else class="rounded-full bg-destructive/10 p-4">
          <Ban class="h-12 w-12 text-destructive" />
        </div>
      </div>

      <h1 data-testid="page-heading" class="text-2xl font-bold sm:text-3xl">
        {{ title }}
      </h1>
      <p class="mt-3 text-muted-foreground">
        {{ description }}
      </p>

      <div
        v-if="reason"
        class="mt-4 rounded-lg border border-destructive bg-destructive/10 p-4 text-left"
        data-testid="suspension-reason"
      >
        <p class="mb-1 text-xs font-medium text-destructive-foreground">
          {{ t('common.accountSuspended.reasonLabel') }}
        </p>
        <p class="text-sm text-destructive-foreground">{{ reason }}</p>
      </div>

      <div class="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Button
          v-if="state === 'pending'"
          data-testid="btn-check-approval"
          :disabled="checking"
          @click="checkAgain"
        >
          <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': checking }" />
          {{ t('common.accountApproval.pending.checkAgain') }}
        </Button>
        <Button data-testid="btn-logout" variant="outline" @click="authStore.logout()">
          {{ t('common.accountSuspended.logout') }}
          <LogOut class="ml-2 h-4 w-4" />
        </Button>

        <LanguageSwitch variant="outline" size="default" :show-text="false" />
      </div>

      <div
        v-if="errorMessage"
        class="mt-4 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive-foreground"
      >
        {{ errorMessage }}
      </div>

      <ResponsiveDialog v-model:open="showDeleteDialog">
        <ResponsiveDialogTrigger as-child>
          <button
            data-testid="btn-delete-account"
            class="mt-6 text-xs text-muted-foreground underline-offset-4 transition-colors hover:text-destructive hover:underline"
          >
            {{ t('common.accountSuspended.deleteAccount') }}
          </button>
        </ResponsiveDialogTrigger>
        <ResponsiveDialogContent>
          <ResponsiveDialogHeader>
            <ResponsiveDialogTitle>{{
              t('common.accountSuspended.deleteConfirmTitle')
            }}</ResponsiveDialogTitle>
            <ResponsiveDialogDescription>
              {{ t('common.accountSuspended.deleteConfirmDescription') }}
            </ResponsiveDialogDescription>
          </ResponsiveDialogHeader>
          <ResponsiveDialogFooter>
            <Button variant="outline" @click="showDeleteDialog = false">
              {{ t('common.accountSuspended.cancel') }}
            </Button>
            <Button variant="destructive" :disabled="isDeleting" @click="handleDeleteAccount">
              {{
                isDeleting
                  ? t('common.accountSuspended.deleting')
                  : t('common.accountSuspended.confirmDelete')
              }}
            </Button>
          </ResponsiveDialogFooter>
        </ResponsiveDialogContent>
      </ResponsiveDialog>
    </div>
  </div>
</template>
