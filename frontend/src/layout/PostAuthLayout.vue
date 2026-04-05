<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { Sparkles } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { RouterLink, RouterView, useRouter } from 'vue-router'

import { useChangelogStatus } from '@/composables/useChangelogStatus'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'

import PostAuthHeader from '@/components/layout/postauth/PostAuthHeader.vue'
import AppSidebar from '@/components/navigation/AppSidebar.vue'
import ErrorBoundary from '@/components/utils/ErrorBoundary.vue'

const { t } = useI18n()
const router = useRouter()
const open = ref(true)

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
  <SidebarProvider v-model:open="open">
    <AppSidebar :open="open" />
    <SidebarInset class="flex flex-col">
      <PostAuthHeader />

      <div class="flex-1 p-4 pt-0" data-testid="main-content">
        <ErrorBoundary>
          <RouterView :key="($route.meta.routerViewKey as string | undefined) ?? $route.fullPath" />
        </ErrorBoundary>
      </div>

      <footer
        data-testid="layout-footer"
        class="flex items-center justify-center gap-3 px-4 py-1.5 text-xs text-muted-foreground/60"
      >
        <RouterLink :to="{ name: 'privacy' }" class="hover:text-muted-foreground transition-colors">
          {{ $t('preauth.layout.footer.privacy') }}
        </RouterLink>
        <RouterLink :to="{ name: 'terms' }" class="hover:text-muted-foreground transition-colors">
          {{ $t('preauth.layout.footer.terms') }}
        </RouterLink>
        <RouterLink
          :to="{ name: 'impressum' }"
          class="hover:text-muted-foreground transition-colors"
        >
          {{ $t('preauth.layout.footer.impressum') }}
        </RouterLink>
      </footer>
    </SidebarInset>

    <!-- What's New dialog -->
    <Dialog
      :open="showWhatsNew"
      @update:open="
        (v: boolean) => {
          if (!v) dismissWhatsNew()
        }
      "
    >
      <DialogContent class="sm:max-w-md" data-testid="dialog-whats-new">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <Sparkles class="size-5" />
            <template v-if="newVersionCount === 1">
              {{ t('changelog.whatsNew.titleSingle', { version: `v${latestVersion}` }) }}
            </template>
            <template v-else>
              {{ t('changelog.whatsNew.titleMultiple', { count: newVersionCount }) }}
            </template>
          </DialogTitle>
          <DialogDescription>
            <template v-if="newVersionCount === 1 && latestTitle">
              {{ latestTitle }}
            </template>
            <template v-else>
              {{ t('changelog.whatsNew.description') }}
            </template>
          </DialogDescription>
        </DialogHeader>
        <DialogFooter class="flex-row gap-2 sm:justify-end">
          <Button variant="ghost" data-testid="btn-dismiss-whats-new" @click="dismissWhatsNew">
            {{ t('changelog.whatsNew.dismiss') }}
          </Button>
          <Button @click="goToChangelog">
            {{ t('changelog.whatsNew.showMe') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </SidebarProvider>
</template>
