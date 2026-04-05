<template>
  <div class="flex min-h-screen items-center justify-center">
    <div class="text-center">
      <h1 data-testid="page-heading" class="text-6xl font-bold text-gray-900 dark:text-gray-100">
        {{ $t('common.errors.notFound.title') }}
      </h1>
      <p class="mt-4 text-xl text-gray-600 dark:text-gray-400">
        {{ $t('common.errors.notFound.subtitle') }}
      </p>
      <p class="mt-2 text-gray-500 dark:text-gray-500">
        {{ $t('common.errors.notFound.description') }}
      </p>
      <router-link
        data-testid="btn-go-home"
        to="/"
        class="mt-6 inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90"
      >
        {{ $t('common.errors.notFound.goHome') }}
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
// This component handles 404 errors when users navigate to non-existent routes
import { useI18n } from 'vue-i18n'

useI18n()
</script>
