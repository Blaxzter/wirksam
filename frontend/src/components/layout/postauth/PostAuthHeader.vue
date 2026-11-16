<script setup lang="ts">
import { computed, onBeforeUnmount, useTemplateRef } from 'vue'

import { ArrowLeft } from '@lucide/vue'
import { useResizeObserver, useWindowScroll } from '@vueuse/core'
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
import HintTooltip from '@/components/utils/HintTooltip.vue'

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

/**
 * The bar stays at the top of the window while the page scrolls, so the way
 * back, the inbox and the account menu are always one tap away.
 *
 * Its height goes on the root as `--app-header-height` for whatever pins itself
 * beneath it (`StickyPageBar`, the settings and changelog side navs), and
 * `data-app-header` turns on the matching `scroll-padding-top` in index.css, so
 * `scrollIntoView` and focus never park something under the bar. It is measured
 * rather than restated because the bar shrinks while the sidebar is collapsed.
 */
const header = useTemplateRef<HTMLElement>('header')

useResizeObserver(header, ([entry]) => {
  const height = entry.borderBoxSize?.[0]?.blockSize ?? entry.contentRect.height
  const root = document.documentElement
  root.style.setProperty('--app-header-height', `${height}px`)
  root.dataset.appHeader = ''
})

onBeforeUnmount(() => {
  const root = document.documentElement
  root.style.removeProperty('--app-header-height')
  delete root.dataset.appHeader
})

// A hairline under the bar once the page has scrolled beneath it.
const { y: scrollY } = useWindowScroll()
const scrolled = computed(() => scrollY.value > 0)
</script>

<template>
  <!-- A shadow rather than a border, so the line costs no height and nothing
       below shifts by a pixel when it appears. -->
  <header
    ref="header"
    class="sticky top-0 z-30 flex h-16 shrink-0 items-center gap-2 bg-background transition-[width,height,box-shadow] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12"
    :class="scrolled ? 'shadow-[0_1px_0_var(--border)]' : undefined"
  >
    <div class="flex flex-1 items-center gap-2 px-4">
      <!-- Phones reach the rest of the app through the bottom nav's "More" tab. -->
      <HintTooltip :label="t('navigation.sidebar.toggle')" side="bottom">
        <SidebarTrigger
          data-testid="btn-sidebar-toggle"
          class="-ml-1 hidden md:inline-flex"
          :aria-label="t('navigation.sidebar.toggle')"
        />
      </HintTooltip>
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

      <!-- A page can put its own control in the free space here (the venue map
           its plan picker) with <Teleport defer to="#page-header-slot">. -->
      <div id="page-header-slot" class="flex min-w-0 flex-1 items-center" />

      <div class="ml-auto hidden md:block">
        <NotificationBell />
      </div>
      <div class="ml-auto md:hidden">
        <MobileUserMenu />
      </div>
    </div>
  </header>
</template>
