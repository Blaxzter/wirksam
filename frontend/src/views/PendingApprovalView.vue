<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { Ban, Clock, Eye, EyeOff, KeyRound, LogOut } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import Button from '@/components/ui/button/Button.vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import Input from '@/components/ui/input/Input.vue'

import LanguageSwitch from '@/components/utils/LanguageSwitch.vue'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const { get, post, delete: del } = useAuthenticatedClient()

const isRejected = computed(() => !!authStore.profile?.rejection_reason)
const rejectionReason = computed(() => authStore.profile?.rejection_reason)

const showDeleteDialog = ref(false)
const isDeleting = ref(false)
const errorMessage = ref<string | null>(null)

// Approval password
const hasApprovalPassword = ref(false)
const approvalPasswordInput = ref('')
const isApproving = ref(false)
const approvalError = ref<string | null>(null)
const showPassword = ref(false)

const loadApprovalPasswordStatus = async () => {
  try {
    const response = await get<{ data: { has_approval_password: boolean } }>({
      url: '/users/approval-password-status',
    })
    hasApprovalPassword.value = response.data.has_approval_password
  } catch {
    // Silently fail — just don't show the input
  }
}

const submitApprovalPassword = async () => {
  if (!approvalPasswordInput.value.trim()) return
  isApproving.value = true
  approvalError.value = null
  try {
    await post({ url: '/users/self-approve', body: { password: approvalPasswordInput.value } })
    toast.success(t('common.pendingApproval.approvalSuccess'))
    await authStore.loadProfile()
    await router.push({ name: 'home' })
  } catch {
    approvalError.value = t('common.pendingApproval.approvalWrongPassword')
  } finally {
    isApproving.value = false
  }
}

const handleDeleteAccount = async () => {
  isDeleting.value = true
  errorMessage.value = null

  try {
    await del({ url: '/users/me' })
    authStore.logout()
  } catch (error) {
    console.error('Account deletion error:', error)
    errorMessage.value = t('common.pendingApproval.deleteError')
    showDeleteDialog.value = false
  } finally {
    isDeleting.value = false
  }
}

onMounted(loadApprovalPasswordStatus)
</script>

<template>
  <div class="flex items-center justify-center">
    <div class="mx-auto max-w-md text-center">
      <div class="mb-6 flex justify-center">
        <div class="rounded-full p-4" :class="isRejected ? 'bg-destructive/10' : 'bg-muted'">
          <Ban v-if="isRejected" class="h-12 w-12 text-destructive" />
          <Clock v-else class="h-12 w-12 text-muted-foreground" />
        </div>
      </div>
      <h1 data-testid="page-heading" class="text-3xl font-bold">
        {{
          isRejected ? t('common.pendingApproval.rejectedTitle') : t('common.pendingApproval.title')
        }}
      </h1>
      <p class="mt-3 text-muted-foreground">
        {{
          isRejected
            ? t('common.pendingApproval.rejectedDescription')
            : t('common.pendingApproval.description')
        }}
      </p>
      <div
        v-if="rejectionReason"
        class="mt-4 rounded-lg border border-destructive bg-destructive/10 p-4 text-left"
      >
        <p class="text-xs font-medium text-destructive-foreground mb-1">
          {{ t('common.pendingApproval.rejectionReasonLabel') }}
        </p>
        <p class="text-sm text-destructive-foreground">{{ rejectionReason }}</p>
      </div>
      <p v-if="!isRejected" class="mt-2 text-sm text-muted-foreground">
        {{ t('common.pendingApproval.hint') }}
      </p>

      <!-- Approval password self-approve -->
      <div v-if="hasApprovalPassword && !isRejected" class="mt-6 rounded-lg border bg-muted/50 p-4">
        <div class="flex items-center justify-center gap-2 mb-2">
          <KeyRound class="h-4 w-4 text-muted-foreground" />
          <p class="text-sm font-medium">{{ t('common.pendingApproval.approvalCodeLabel') }}</p>
        </div>
        <form class="flex gap-2" @submit.prevent="submitApprovalPassword">
          <div class="relative flex-1">
            <Input
              data-testid="input-approval-code"
              v-model="approvalPasswordInput"
              :type="showPassword ? 'text' : 'password'"
              :placeholder="t('common.pendingApproval.approvalCodePlaceholder')"
            />
            <button
              type="button"
              class="absolute inset-y-0 right-0 flex items-center px-2.5 text-muted-foreground hover:text-foreground"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" class="h-4 w-4" />
              <Eye v-else class="h-4 w-4" />
            </button>
          </div>
          <Button data-testid="btn-approve" type="submit" :disabled="isApproving || !approvalPasswordInput.trim()">
            {{
              isApproving
                ? t('common.pendingApproval.approving')
                : t('common.pendingApproval.approveButton')
            }}
          </Button>
        </form>
        <p v-if="approvalError" class="mt-2 text-sm text-destructive">{{ approvalError }}</p>
      </div>

      <div class="mt-8 flex items-center justify-center gap-3">
        <Button data-testid="btn-logout" variant="outline" @click="authStore.logout()">
          {{ t('common.pendingApproval.logout') }}
          <LogOut class="h-4 w-4 ml-2" />
        </Button>

        <LanguageSwitch variant="outline" size="default" :show-text="false" />
      </div>

      <div
        v-if="errorMessage"
        class="mt-4 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive-foreground"
      >
        {{ errorMessage }}
      </div>

      <Dialog v-model:open="showDeleteDialog">
        <DialogTrigger as-child>
          <button
            data-testid="btn-withdraw"
            class="mt-6 text-xs text-muted-foreground underline-offset-4 hover:underline hover:text-destructive transition-colors"
          >
            {{ t('common.pendingApproval.deleteAccount') }}
          </button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{{ t('common.pendingApproval.deleteConfirmTitle') }}</DialogTitle>
            <DialogDescription>
              {{ t('common.pendingApproval.deleteConfirmDescription') }}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" @click="showDeleteDialog = false">
              {{ t('common.pendingApproval.cancel') }}
            </Button>
            <Button variant="destructive" :disabled="isDeleting" @click="handleDeleteAccount">
              {{
                isDeleting
                  ? t('common.pendingApproval.deleting')
                  : t('common.pendingApproval.confirmDelete')
              }}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  </div>
</template>
