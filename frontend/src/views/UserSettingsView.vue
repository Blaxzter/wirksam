<template>
  <div class="mx-auto max-w-5xl space-y-8">
    <!-- Header -->
    <div class="pb-3">
      <h1 class="text-3xl font-bold tracking-tight">{{ $t('user.settings.title') }}</h1>
      <p class="text-muted-foreground mt-2">
        {{ $t('user.settings.subtitle') }}
      </p>
    </div>

    <!-- Profile Section -->
    <div class="grid grid-cols-1 gap-6">
      <!-- Current Profile Card -->
      <CurrentProfileCard :user="user" />

      <!-- Edit Profile Form -->
      <EditProfileForm
        :user="user"
        :can-edit-profile-picture="canEditProfilePicture"
        :auth-provider-name="authProvider.name"
        @profile-updated="handleProfileUpdated"
      />

      <!-- Password Reset (Auth0 users only) -->
      <PasswordResetCard v-if="authProvider.isAuth0" />

      <!-- Notification Preferences -->
      <NotificationSettingsCard />

      <!-- Language Settings -->
      <LanguageSettingsCard />

      <!-- Data Export -->
      <DataExportCard />

      <!-- Delete Account (danger zone) -->
      <DeleteAccountCard />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

import CurrentProfileCard from '@/components/account/user/CurrentProfileCard.vue'
import DataExportCard from '@/components/account/user/DataExportCard.vue'
import DeleteAccountCard from '@/components/account/user/DeleteAccountCard.vue'
import EditProfileForm from '@/components/account/user/EditProfileForm.vue'
import LanguageSettingsCard from '@/components/account/user/LanguageSettingsCard.vue'
import NotificationSettingsCard from '@/components/account/user/NotificationSettingsCard.vue'
import PasswordResetCard from '@/components/account/user/PasswordResetCard.vue'
import { useAuthProvider } from '@/components/account/user/useAuthProvider.ts'

// Store
const authStore = useAuthStore()
useI18n()

// Computed properties
const user = computed(() => authStore.user)

// Determine auth provider
const authProvider = useAuthProvider(user.value)

// Check if current provider is Auth0 (allows profile picture changes)
const canEditProfilePicture = computed(() => authProvider.value.isAuth0)

// Handle profile updated event
const handleProfileUpdated = async (values: Record<string, unknown>) => {
  // Optionally refresh user data from Auth0
  authStore.updateUser({
    ...authStore.user,
    ...values,
  })
}
</script>
