<script setup lang="ts">
import { ChevronRight, type LucideIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { type LocationQueryRaw, RouterLink, useRoute, useRouter } from 'vue-router'

import { Badge } from '@/components/ui/badge'
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
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

import SidebarSplitButton from '@/components/navigation/SidebarSplitButton.vue'

const router = useRouter()
const route = useRoute()
const { t } = useI18n()

export interface NavSubItem {
  title: string
  titleKey?: string
  url?: string
  routeName?: string
  routeParams?: Record<string, string>
  routeQuery?: LocationQueryRaw
  badge?: {
    text: string
    tooltip?: string
    variant?: 'default' | 'secondary' | 'destructive' | 'outline'
    /** Drawn before the text; with no text, `tooltip` is also what a screen reader hears. */
    icon?: LucideIcon
  }
}

export interface NavItem {
  title: string
  titleKey?: string
  url?: string
  routeName?: string
  icon?: LucideIcon
  isActive?: boolean
  items?: NavSubItem[]
  /**
   * A count that wants attention (e.g. team requests to decide), drawn like
   * the Notifications badge. `badgeLabel` is what a screen reader hears.
   */
  badge?: number
  badgeLabel?: string
}

const props = defineProps<{
  open: boolean
  groupLabelKey?: string
  items: NavItem[]
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

const isRouteActive = (routeName?: string, routeParams?: Record<string, string>) => {
  if (!routeName) return false
  const nameMatch = route.name === routeName || route.matched.some((r) => r.name === routeName)
  if (!nameMatch || !routeParams) return nameMatch
  // When routeParams are provided, also check they match (e.g. eventId)
  return Object.entries(routeParams).every(
    ([key, value]) => String(route.params[key]) === String(value),
  )
}
</script>

<template>
  <SidebarGroup>
    <SidebarGroupLabel>{{
      $t(props.groupLabelKey ?? 'navigation.sidebar.platform')
    }}</SidebarGroupLabel>
    <SidebarMenu>
      <template v-for="item in items" :key="item.routeName ?? item.titleKey ?? item.title">
        <!-- Direct link (no sub-items) -->
        <SidebarMenuItem v-if="!hasSubItems(item)">
          <SidebarMenuButton
            :tooltip="resolveTitle(item)"
            :is-active="isRouteActive(item.routeName)"
            as-child
          >
            <RouterLink
              v-if="item.routeName"
              :to="{ name: item.routeName }"
              :data-testid="'sidebar-link-' + item.routeName"
            >
              <component :is="item.icon" v-if="item.icon" />
              <span>{{ resolveTitle(item) }}</span>
              <span
                v-if="item.badge"
                class="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full bg-red-700 px-1 text-[10px] font-bold text-white"
                :data-testid="'sidebar-badge-' + item.routeName"
              >
                <span aria-hidden="true">{{ item.badge > 99 ? '99+' : item.badge }}</span>
                <span class="sr-only">{{ item.badgeLabel ?? item.badge }}</span>
              </span>
              <span
                v-else-if="isRouteActive(item.routeName)"
                class="ml-auto size-1.5 rounded-full bg-foreground"
              />
            </RouterLink>
            <a v-else :href="item.url">
              <component :is="item.icon" v-if="item.icon" />
              <span>{{ resolveTitle(item) }}</span>
            </a>
          </SidebarMenuButton>
        </SidebarMenuItem>

        <!-- Collapsible event (has sub-items) — split: left navigates, right toggles -->
        <Collapsible v-else as-child :default-open="item.isActive" class="group/collapsible">
          <SidebarMenuItem>
            <SidebarSplitButton :is-active="isRouteActive(item.routeName)">
              <template #link>
                <RouterLink
                  v-if="item.routeName"
                  :to="{ name: item.routeName }"
                  :data-testid="'sidebar-link-' + item.routeName"
                  class="flex min-w-0 flex-1 items-center gap-2 overflow-hidden rounded-l-md p-2 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors"
                >
                  <component :is="item.icon" v-if="item.icon" class="size-4 shrink-0" />
                  <span class="truncate">{{ resolveTitle(item) }}</span>
                </RouterLink>
              </template>
              <template #action>
                <CollapsibleTrigger as-child>
                  <button
                    class="flex shrink-0 items-center justify-center rounded-r-md px-2 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground transition-colors group-data-[collapsible=icon]:hidden"
                    :aria-label="
                      t('navigation.sidebar.toggleSubmenu', { title: resolveTitle(item) })
                    "
                    @click="handleSidebarToggle(item)"
                  >
                    <ChevronRight
                      class="size-4 transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90"
                    />
                  </button>
                </CollapsibleTrigger>
              </template>
            </SidebarSplitButton>
            <CollapsibleContent>
              <SidebarMenuSub class="mr-0 max-h-48 overflow-y-auto scrollbar-none">
                <SidebarMenuSubItem
                  v-for="subItem in item.items"
                  :key="subItem.routeName ?? subItem.titleKey ?? subItem.title"
                >
                  <SidebarMenuSubButton
                    :is-active="isRouteActive(subItem.routeName, subItem.routeParams)"
                    as-child
                  >
                    <RouterLink
                      v-if="subItem.routeName"
                      :to="{
                        name: subItem.routeName,
                        params: subItem.routeParams,
                        query: subItem.routeQuery,
                      }"
                    >
                      <span class="truncate">{{ resolveTitle(subItem) }}</span>
                      <Tooltip v-if="subItem.badge">
                        <TooltipTrigger as-child>
                          <Badge
                            :variant="subItem.badge.variant ?? 'secondary'"
                            class="ml-auto shrink-0 text-[10px] px-1.5 py-0 leading-4"
                          >
                            <component
                              :is="subItem.badge.icon"
                              v-if="subItem.badge.icon"
                              class="size-3"
                              aria-hidden="true"
                            />
                            {{ subItem.badge.text }}
                            <span
                              v-if="!subItem.badge.text && subItem.badge.tooltip"
                              class="sr-only"
                            >
                              {{ subItem.badge.tooltip }}
                            </span>
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent v-if="subItem.badge.tooltip" side="right">
                          {{ subItem.badge.tooltip }}
                        </TooltipContent>
                      </Tooltip>
                      <span
                        v-else-if="isRouteActive(subItem.routeName, subItem.routeParams)"
                        class="ml-auto size-1.5 rounded-full bg-foreground"
                      />
                    </RouterLink>
                    <a v-else :href="subItem.url">
                      <span class="truncate">{{ resolveTitle(subItem) }}</span>
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
