<script setup lang="ts">
import { ref } from 'vue'

import { RouterView } from 'vue-router'

import CookieNotice from '@/components/CookieNotice.vue'
import PreAuthFooter from '@/components/layout/preauth/PreAuthFooter.vue'
import PreAuthHeader from '@/components/layout/preauth/PreAuthHeader.vue'
import ErrorBoundary from '@/components/utils/ErrorBoundary.vue'

// Toggle between fixed header with scrollable content vs full-height layout
const useFixedHeader = ref(true)
</script>

<template>
  <div
    :class="useFixedHeader ? 'h-screen flex flex-col' : 'min-h-screen bg-background flex flex-col'"
  >
    <PreAuthHeader :use-fixed-header="useFixedHeader" />

    <main :class="useFixedHeader ? 'flex-1 overflow-auto flex flex-col' : 'flex-1 flex flex-col'" data-testid="main-content">
      <div class="max-w-7xl w-full mx-auto px-4 py-8 flex-1">
        <ErrorBoundary>
          <RouterView />
        </ErrorBoundary>
      </div>

      <PreAuthFooter />
    </main>

    <CookieNotice />
  </div>
</template>
