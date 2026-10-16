<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { Sparkles } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import {
  type RouteLocationNormalizedLoadedGeneric,
  RouterView,
  useRoute,
  useRouter,
} from 'vue-router'

import { useChangelogStatus } from '@/composables/useChangelogStatus'

import { Button } from '@/components/ui/button'
import {
  ResponsiveDialog,
  ResponsiveDialogContent,
  ResponsiveDialogDescription,
  ResponsiveDialogFooter,
  ResponsiveDialogHeader,
  ResponsiveDialogTitle,
} from '@/components/ui/responsive-dialog'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'

import PostAuthHeader from '@/components/layout/postauth/PostAuthHeader.vue'
import AppSidebar from '@/components/navigation/AppSidebar.vue'
import MobileBottomNav from '@/components/navigation/MobileBottomNav.vue'
import ErrorBoundary from '@/components/utils/ErrorBoundary.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const open = ref(true)

/**
 * `meta.fullHeight` routes (the venue map) fill exactly the viewport below the
 * header, the demo banner included, and never scroll the document: the shell
 * gets a fixed height and the page a flex column it can grow into.
 */
const fullHeight = computed(() => route.meta.fullHeight === true)

function routeViewKey(r: RouteLocationNormalizedLoadedGeneric): string {
  const key = r.meta.routerViewKey
  if (typeof key === 'function')
    return (key as (r: RouteLocationNormalizedLoadedGeneric) => string)(r)
  if (typeof key === 'string') return key
  return r.fullPath
}

const { hasNewVersions, newVersionCount, latestVersion, latestTitle, markAsSeen } =
  useChangelogStatus()
const showWhatsNew = ref(false)

onMounted(() => {
  if (hasNewVersions.value) {
    showWhatsNew.value = true
  }
})

function dismissWhatsNew() {
  showWhatsNew.value = false
  markAsSeen()
}

function goToChangelog() {
  showWhatsNew.value = false
  // markAsSeen is called in ChangelogView onMounted
  router.push({ name: 'changelog' })
}
</script>

<template>
  <SidebarProvider
    v-model:open="open"
    :class="fullHeight ? 'h-[calc(100dvh-var(--demo-banner-height,0px))] min-h-0' : undefined"
  >
    <AppSidebar :open="open" />
    <SidebarInset
      class="flex flex-col pb-[calc(4rem+env(safe-area-inset-bottom))] md:pb-0"
      :class="fullHeight ? 'min-h-0 overflow-hidden' : undefined"
    >
      <PostAuthHeader />

      <div
        class="flex-1 p-4 pt-0"
        :class="fullHeight ? 'flex min-h-0 flex-col' : undefined"
        data-testid="main-content"
      >
        <ErrorBoundary>
          <RouterView :key="routeViewKey(route)" />
        </ErrorBoundary>
      </div>
    </SidebarInset>

    <MobileBottomNav />

    <!-- What's New dialog -->
    <ResponsiveDialog
      :open="showWhatsNew"
      @update:open="
        (v: boolean) => {
          if (!v) dismissWhatsNew()
        }
      "
    >
      <ResponsiveDialogContent dialog-class="sm:max-w-md" data-testid="dialog-whats-new">
        <ResponsiveDialogHeader>
          <ResponsiveDialogTitle class="flex items-center gap-2">
            <Sparkles class="size-5" />
            <template v-if="newVersionCount === 1">
              {{ t('changelog.whatsNew.titleSingle', { version: `v${latestVersion}` }) }}
            </template>
            <template v-else>
              {{ t('changelog.whatsNew.titleMultiple', { count: newVersionCount }) }}
            </template>
          </ResponsiveDialogTitle>
          <ResponsiveDialogDescription>
            <template v-if="newVersionCount === 1 && latestTitle">
              {{ latestTitle }}
            </template>
            <template v-else>
              {{ t('changelog.whatsNew.description') }}
            </template>
          </ResponsiveDialogDescription>
        </ResponsiveDialogHeader>
        <ResponsiveDialogFooter layout="row" class="justify-end">
          <Button variant="ghost" data-testid="btn-dismiss-whats-new" @click="dismissWhatsNew">
            {{ t('changelog.whatsNew.dismiss') }}
          </Button>
          <Button @click="goToChangelog">
            {{ t('changelog.whatsNew.showMe') }}
          </Button>
        </ResponsiveDialogFooter>
      </ResponsiveDialogContent>
    </ResponsiveDialog>
  </SidebarProvider>
</template>
