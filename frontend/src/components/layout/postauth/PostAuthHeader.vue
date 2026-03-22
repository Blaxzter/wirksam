<script setup lang="ts">
import { useI18n } from 'vue-i18n'

import { useBreadcrumbStore } from '@/stores/breadcrumb'

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Separator } from '@/components/ui/separator'
import { SidebarTrigger } from '@/components/ui/sidebar'

import NotificationBell from '@/components/navigation/NotificationBell.vue'

const breadcrumbStore = useBreadcrumbStore()
const { t } = useI18n()

const resolveBreadcrumbTitle = (title: string, titleKey?: string) => {
  if (!titleKey) return title
  return t(titleKey)
}
</script>

<template>
  <header
    class="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12"
  >
    <div class="flex flex-1 items-center gap-2 px-4">
      <SidebarTrigger class="-ml-1" />
      <Separator orientation="vertical" class="mr-2 h-4" />
      <Breadcrumb>
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
      <div class="ml-auto">
        <NotificationBell />
      </div>
    </div>
  </header>
</template>
