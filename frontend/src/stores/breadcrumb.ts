import { computed, ref, watch } from 'vue'

import { defineStore } from 'pinia'
import type { RouteLocationNormalized } from 'vue-router'
import { useRoute } from 'vue-router'

export interface BreadcrumbItem {
  title: string
  titleKey?: string
  to?: string | { name: string; params?: Record<string, unknown> }
  disabled?: boolean
}

export const useBreadcrumbStore = defineStore('breadcrumb', () => {
  // State
  const dynamicBreadcrumbs = ref<BreadcrumbItem[]>([])
  const currentRoute = ref<RouteLocationNormalized | null>(null)

  // Set up route watcher
  const route = useRoute()

  // Getters
  const breadcrumbs = computed(() => {
    // If dynamic breadcrumbs are set, use them
    if (dynamicBreadcrumbs.value.length > 0) {
      return dynamicBreadcrumbs.value
    }

    // Otherwise, generate breadcrumbs from route meta
    if (currentRoute.value?.meta?.breadcrumbs) {
      return currentRoute.value.meta.breadcrumbs as BreadcrumbItem[]
    }

    // Fallback: generate breadcrumbs from route path segments
    return generateBreadcrumbsFromRoute(currentRoute.value)
  })

  // Actions
  const setBreadcrumbs = (items: BreadcrumbItem[]) => {
    dynamicBreadcrumbs.value = items
  }

  const clearBreadcrumbs = () => {
    dynamicBreadcrumbs.value = []
  }

  const addBreadcrumb = (item: BreadcrumbItem) => {
    dynamicBreadcrumbs.value.push(item)
  }

  const setDynamicTitle = (title: string) => {
    const items = breadcrumbs.value
    if (items.length > 0) {
      const updated = [...items]
      updated[updated.length - 1] = { ...updated[updated.length - 1], title, titleKey: undefined }
      dynamicBreadcrumbs.value = updated
    }
  }

  const updateCurrentRoute = (route: RouteLocationNormalized) => {
    currentRoute.value = route
    // Clear dynamic breadcrumbs when route changes (unless you want to keep them)
    // This ensures automatic breadcrumb updates on navigation
    if (dynamicBreadcrumbs.value.length > 0) {
      // Only clear if the new route has its own breadcrumb meta
      if (route.meta?.breadcrumbs) {
        dynamicBreadcrumbs.value = []
      }
    }
  }

  // Helper function to generate breadcrumbs from route path
  const generateBreadcrumbsFromRoute = (
    route: RouteLocationNormalized | null,
  ): BreadcrumbItem[] => {
    if (!route) return []

    const items: BreadcrumbItem[] = []
    const pathSegments = route.path.split('/').filter((segment) => segment !== '')

    // Always add home
    if (route.path !== '/') {
      items.push({ title: 'Home', to: '/' })
    }

    // Add segments as breadcrumbs
    let currentPath = ''
    pathSegments.forEach((segment, index) => {
      currentPath += `/${segment}`

      // Skip dynamic segments like :id unless we have a way to resolve them
      if (!segment.startsWith(':')) {
        const isLast = index === pathSegments.length - 1
        const title = segment.charAt(0).toUpperCase() + segment.slice(1).replace('-', ' ')

        items.push({
          title,
          to: isLast ? undefined : currentPath,
        })
      }
    })

    return items
  }

  watch(
    () => route,
    (newRoute) => {
      if (newRoute) {
        updateCurrentRoute(newRoute)
      }
    },
    { immediate: true, deep: true },
  )

  return {
    // State
    breadcrumbs,
    currentRoute,

    // Actions
    setBreadcrumbs,
    clearBreadcrumbs,
    addBreadcrumb,
    setDynamicTitle,
    updateCurrentRoute,
  }
})

// Extend route meta type
declare module 'vue-router' {
  interface RouteMeta {
    breadcrumbs?: BreadcrumbItem[]
  }
}
