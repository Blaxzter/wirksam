<script setup lang="ts">
import { computed } from 'vue'

import { useColorMode } from '@vueuse/core'
import { RouterView } from 'vue-router'
import 'vue-sonner/style.css'

import { useAuthStore } from '@/stores/auth'

import { useAuth } from '@/composables/useAuth'
import { usePalette } from '@/composables/usePalette'

import { Toaster } from '@/components/ui/sonner'

import SandboxBanner from '@/components/sandbox/SandboxBanner.vue'
import SandboxWelcomeDialog from '@/components/sandbox/SandboxWelcomeDialog.vue'
import GlobalDialog from '@/components/utils/GlobalDialog.vue'

const { isLoading: sessionLoading } = useAuth()
const authStore = useAuthStore()

// Both halves of "who is this?" have to answer before anything renders: the
// session restore at boot, and the profile fetch that follows it. Rendering in
// between flashes the signed-out shell at someone who is signed in.
const isLoading = computed(() => sessionLoading.value || authStore.profileLoading)

// Initialize color mode + palette early so the right classes are on <html>
// before the first render.
useColorMode()
usePalette()
</script>

<template>
  <Toaster />
  <GlobalDialog />

  <!-- Above the loading/outlet pair, not inside it: this is the only node that
       outlives every layout, and anywhere lower would be unmounted on the first
       navigation, resetting the countdown it is there to show. -->
  <SandboxBanner />

  <!-- Opened by `tour/install.ts` on a demo session's first arrival at the
       dashboard, and mounted here for the same reason the banner is: the
       layout underneath it is rebuilt on every navigation. -->
  <SandboxWelcomeDialog />

  <!-- Loading state -->
  <div v-if="isLoading" class="min-h-screen flex items-center justify-center bg-background">
    <div class="text-center space-y-4">
      <div
        class="animate-spin h-8 w-8 border-4 border-primary border-t-transparent rounded-full mx-auto"
      ></div>
      <p class="text-muted-foreground">{{ $t('utils.loading') }}</p>
    </div>
  </div>

  <!-- Router outlet - layouts will be handled by nested routes -->
  <RouterView v-else />
</template>

<style scoped></style>
