<script setup lang="ts">
import { ref } from 'vue'

import { RouterView } from 'vue-router'

import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'

import PostAuthHeader from '@/components/layout/postauth/PostAuthHeader.vue'
import AppSidebar from '@/components/navigation/AppSidebar.vue'
import ErrorBoundary from '@/components/utils/ErrorBoundary.vue'

const open = ref(true)
</script>

<template>
  <SidebarProvider v-model:open="open">
    <AppSidebar :open="open" />
    <SidebarInset>
      <PostAuthHeader />

      <div class="flex-1 p-4 pt-0">
        <ErrorBoundary>
          <RouterView :key="$route.fullPath" />
        </ErrorBoundary>
      </div>
    </SidebarInset>
  </SidebarProvider>
</template>
