<script setup lang="ts">
/**
 * The frame of the pages a shared list's guests open: the list behind
 * `/l/<code>` and the page that manages their sign-ups.
 *
 * Deliberately bare. Whoever lands here came from a link in a group chat or a
 * QR code at a stand, has no account and is here for one thing, so there is
 * nowhere to wander off to: the wordmark is not a link. The footer is the auth
 * screens' own, with the legal links and the language and appearance controls.
 * There is no cookie notice, because these pages store nothing themselves and
 * the two controls store a choice only when the visitor makes one.
 */
import { RouterView } from 'vue-router'

import logo from '@/assets/logo/logo.svg'

import AuthShellFooter from '@/components/auth/AuthShellFooter.vue'
import ErrorBoundary from '@/components/utils/ErrorBoundary.vue'
</script>

<template>
  <div class="flex min-h-svh flex-col bg-background">
    <header class="border-b border-border/60">
      <div class="mx-auto flex h-14 w-full max-w-2xl items-center gap-2 px-4">
        <img :src="logo" alt="" class="size-8 shrink-0 rounded-lg" />
        <span class="text-base font-bold">{{ $t('preauth.layout.appName') }}</span>
      </div>
    </header>

    <main class="mx-auto w-full max-w-2xl flex-1 px-4 py-6" data-testid="main-content">
      <ErrorBoundary>
        <RouterView />
      </ErrorBoundary>
    </main>

    <AuthShellFooter />
  </div>
</template>
