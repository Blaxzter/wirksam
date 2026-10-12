<script setup lang="ts">
import { computed } from 'vue'

import { ArrowLeft } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { useBreadcrumbStore } from '@/stores/breadcrumb'

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import Button from '@/components/ui/button/Button.vue'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'

import MobileUserMenu from '@/components/navigation/MobileUserMenu.vue'
import NotificationBell from '@/components/navigation/NotificationBell.vue'

const breadcrumbStore = useBreadcrumbStore()
const router = useRouter()
const { t } = useI18n()

const resolveBreadcrumbTitle = (title: string, titleKey?: string) => {
  if (!titleKey) return title
  return t(titleKey)
}

const mobileParent = computed(() => {
  const crumbs = breadcrumbStore.breadcrumbs
  // Walk backward from penultimate, skipping items marked mobileSkip,
  // until we find a linkable parent.
  for (let i = crumbs.length - 2; i >= 0; i--) {
    const item = crumbs[i]
    if (item.mobileSkip) continue
    if (!item.to) continue
    return item
  }
  return null
})
</script>

<template>
  <header
    class="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear event-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12"
  >
    <div class="flex flex-1 items-center gap-2 px-4">
      <!-- Phones reach the rest of the app through the bottom nav's "More" tab. -->
      <SidebarTrigger data-testid="btn-sidebar-toggle" class="-ml-1 hidden md:inline-flex" />
      <Separator orientation="vertical" class="mr-2 hidden h-4 md:block" />

      <!-- Mobile: show parent crumb as back link -->
      <Button
        v-if="mobileParent"
        variant="ghost"
        size="sm"
        class="xl:hidden -ml-1"
        @click="mobileParent.to && router.push(mobileParent.to)"
      >
        <ArrowLeft class="mr-1.5 h-4 w-4" />
        {{ resolveBreadcrumbTitle(mobileParent.title, mobileParent.titleKey) }}
      </Button>

      <!-- Desktop: full breadcrumb trail -->
      <Breadcrumb class="hidden xl:block">
        <BreadcrumbList>
          <template v-for="(item, index) in breadcrumbStore.breadcrumbs" :key="index">
            <BreadcrumbItem>
              <BreadcrumbLink
                v-if="item.to && index < breadcrumbStore.breadcrumbs.length - 1"
                @click="$router.push(item.to)"
              >
                {{ resolveBreadcrumbTitle(item.title, item.titleKey) }}
              </BreadcrumbLink>
              <BreadcrumbPage v-else>
                {{ resolveBreadcrumbTitle(item.title, item.titleKey) }}
              </BreadcrumbPage>
            </BreadcrumbItem>
            <BreadcrumbSeparator v-if="index < breadcrumbStore.breadcrumbs.length - 1" />
          </template>
        </BreadcrumbList>
      </Breadcrumb>

      <div class="ml-auto hidden md:block">
        <NotificationBell />
      </div>
      <div class="ml-auto md:hidden">
        <MobileUserMenu />
      </div>
    </div>
  </header>
</template>
