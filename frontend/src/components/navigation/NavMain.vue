<script setup lang="ts">
import { ChevronRight, type LucideIcon } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from '@/components/ui/sidebar'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

const props = defineProps<{
  open: boolean
  groupLabelKey?: string
  items: {
    title: string
    titleKey?: string
    url?: string
    routeName?: string
    icon?: LucideIcon
    isActive?: boolean
    items?: {
      title: string
      titleKey?: string
      url?: string
      routeName?: string
    }[]
  }[]
}>()

const resolveTitle = (item: { title: string; titleKey?: string }) =>
  item.titleKey ? t(item.titleKey) : item.title

const handleSidebarToggle = (item: { isActive?: boolean; routeName?: string; url?: string }) => {
  if (props.open) {
    item.isActive = !item.isActive
  } else {
    if (item.routeName) {
      router.push({ name: item.routeName })
    } else if (item.url) {
      window.location.href = item.url
    }
  }
}

const hasSubItems = (item: { items?: unknown[] }) => item.items && item.items.length > 0

const isRouteActive = (routeName?: string) => {
  if (!routeName) return false
  return route.name === routeName || route.matched.some(r => r.name === routeName)
}
</script>

<template>
  <SidebarGroup>
    <SidebarGroupLabel>{{ $t(props.groupLabelKey ?? 'navigation.sidebar.platform') }}</SidebarGroupLabel>
    <SidebarMenu>
      <template v-for="item in items" :key="item.routeName ?? item.titleKey ?? item.title">
        <!-- Direct link (no sub-items) -->
        <SidebarMenuItem v-if="!hasSubItems(item)">
          <SidebarMenuButton :tooltip="resolveTitle(item)" :is-active="isRouteActive(item.routeName)" as-child>
            <RouterLink v-if="item.routeName" :to="{ name: item.routeName }">
              <component :is="item.icon" v-if="item.icon" />
              <span>{{ resolveTitle(item) }}</span>
              <span v-if="isRouteActive(item.routeName)" class="ml-auto size-1.5 rounded-full bg-foreground" />
            </RouterLink>
            <a v-else :href="item.url">
              <component :is="item.icon" v-if="item.icon" />
              <span>{{ resolveTitle(item) }}</span>
            </a>
          </SidebarMenuButton>
        </SidebarMenuItem>

        <!-- Collapsible group (has sub-items) -->
        <Collapsible
          v-else
          as-child
          :default-open="item.isActive"
          class="group/collapsible"
        >
          <SidebarMenuItem>
            <CollapsibleTrigger as-child>
              <SidebarMenuButton :tooltip="resolveTitle(item)" @click="handleSidebarToggle(item)">
                <component :is="item.icon" v-if="item.icon" />
                <span>{{ resolveTitle(item) }}</span>
                <ChevronRight
                  class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90"
                />
              </SidebarMenuButton>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <SidebarMenuSub>
                <SidebarMenuSubItem
                  v-for="subItem in item.items"
                  :key="subItem.routeName ?? subItem.titleKey ?? subItem.title"
                >
                  <SidebarMenuSubButton :is-active="isRouteActive(subItem.routeName)" as-child>
                    <RouterLink v-if="subItem.routeName" :to="{ name: subItem.routeName }">
                      <span>{{ resolveTitle(subItem) }}</span>
                      <span v-if="isRouteActive(subItem.routeName)" class="ml-auto size-1.5 rounded-full bg-foreground" />
                    </RouterLink>
                    <a v-else :href="subItem.url">
                      <span>{{ resolveTitle(subItem) }}</span>
                    </a>
                  </SidebarMenuSubButton>
                </SidebarMenuSubItem>
              </SidebarMenuSub>
            </CollapsibleContent>
          </SidebarMenuItem>
        </Collapsible>
      </template>
    </SidebarMenu>
  </SidebarGroup>
</template>
