<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  ArrowLeft,
  CalendarDays,
  Check,
  ChevronDown,
  Info,
  List,
  Pencil,
  Plus,
  Printer,
  Trash2,
  UserCheck,
  Users,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useAuthStore } from '@/stores/auth'
import { useBreadcrumbStore } from '@/stores/breadcrumb'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useDialog } from '@/composables/useDialog'

import { Alert, AlertDescription } from '@/components/ui/alert'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import Separator from '@/components/ui/separator/Separator.vue'

import AvailabilityDialog from '@/components/events/AvailabilityDialog.vue'
import AvailabilityDisplay from '@/components/events/AvailabilityDisplay.vue'
import StatusDropdown from '@/components/events/StatusDropdown.vue'

import type {
  EventGroupRead,
  EventListResponse,
  EventRead,
  UserAvailabilityRead,
  UserAvailabilityWithUser,
} from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'
import { formatDate, formatDateWithTime } from '@/lib/format'
import { statusVariant } from '@/lib/status'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const breadcrumbStore = useBreadcrumbStore()
const { get, post, patch, delete: del } = useAuthenticatedClient()
const { confirmDestructive } = useDialog()

const groupId = computed(() => route.params.groupId as string)
const group = ref<EventGroupRead | null>(null)
const groupEvents = ref<EventRead[]>([])
const myAvailability = ref<UserAvailabilityRead | null>(null)
const allAvailabilities = ref<UserAvailabilityWithUser[]>([])
const loading = ref(false)
const showAvailabilityDialog = ref(false)

const handleStatusChange = async (status: 'draft' | 'published' | 'archived') => {
  if (!group.value || group.value.status === status) return
  try {
    const res = await patch<{ data: EventGroupRead }>({
      url: `/event-groups/${groupId.value}`,
      body: { status },
    })
    group.value = res.data
    toast.success(t(`duties.eventGroups.statuses.${status}`))
  } catch (error) {
    toastApiError(error)
  }
}

const loadGroup = async () => {
  if (!groupId.value) return
  loading.value = true
  try {
    const [groupRes, eventsRes] = await Promise.all([
      get<{ data: EventGroupRead }>({ url: `/event-groups/${groupId.value}` }),
      get<{ data: EventListResponse }>({ url: '/events/', query: { limit: 200 } }),
    ])
    group.value = groupRes.data
    groupEvents.value = eventsRes.data.items.filter(
      (e: EventRead) => e.event_group_id === groupId.value,
    )

    breadcrumbStore.setDynamicTitle(group.value.name)

    try {
      const availRes = await get<{ data: UserAvailabilityRead }>({
        url: `/event-groups/${groupId.value}/availability/me`,
      })
      myAvailability.value = availRes.data
    } catch {
      myAvailability.value = null
    }

    if (authStore.isAdmin) {
      try {
        const adminRes = await get<{ data: UserAvailabilityWithUser[] }>({
          url: `/event-groups/${groupId.value}/availabilities`,
        })
        allAvailabilities.value = adminRes.data
      } catch {
        allAvailabilities.value = []
      }
    }
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

const handleSaveAvailability = async (payload: {
  availability_type: 'fully_available' | 'specific_dates' | 'time_range'
  notes?: string
  default_start_time?: string
  default_end_time?: string
  dates: { date: string; start_time?: string; end_time?: string }[]
}) => {
  try {
    const res = await post<{ data: UserAvailabilityRead }>({
      url: `/event-groups/${groupId.value}/availability`,
      body: {
        availability_type: payload.availability_type,
        notes: payload.notes,
        default_start_time: payload.default_start_time,
        default_end_time: payload.default_end_time,
        dates: payload.dates,
      },
    })
    myAvailability.value = res.data
    showAvailabilityDialog.value = false
    toast.success(t('duties.availability.update'))
    if (authStore.isAdmin) {
      const adminRes = await get<{ data: UserAvailabilityWithUser[] }>({
        url: `/event-groups/${groupId.value}/availabilities`,
      })
      allAvailabilities.value = adminRes.data
    }
  } catch (error) {
    toastApiError(error)
  }
}

const handleRemoveAvailability = async () => {
  const confirmed = await confirmDestructive(t('duties.availability.removeConfirm'))
  if (!confirmed) return

  try {
    await del({ url: `/event-groups/${groupId.value}/availability/me` })
    myAvailability.value = null
    toast.success(t('duties.availability.remove'))
    if (authStore.isAdmin) {
      const adminRes = await get<{ data: UserAvailabilityWithUser[] }>({
        url: `/event-groups/${groupId.value}/availabilities`,
      })
      allAvailabilities.value = adminRes.data
    }
  } catch (error) {
    toastApiError(error)
  }
}

const navigateToEvent = (event: EventRead) => {
  router.push({ name: 'event-detail', params: { eventId: event.id } })
}

onMounted(loadGroup)
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <!-- Back -->
    <Button variant="ghost" size="sm" data-testid="btn-back" @click="router.push({ name: 'event-groups' })">
      <ArrowLeft class="mr-2 h-4 w-4" />
      {{ t('duties.eventGroups.title') }}
    </Button>

    <div v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else-if="group">
      <!-- Draft banner -->
      <Alert
        v-if="group.status === 'draft'"
        variant="default"
        class="border-amber-500/50 bg-amber-50 text-amber-900 dark:bg-amber-950/30 dark:text-amber-200 dark:border-amber-500/30"
      >
        <Info class="h-4 w-4 text-amber-600 dark:text-amber-400" />
        <AlertDescription>
          {{ t('duties.eventGroups.draftBanner') }}
        </AlertDescription>
      </Alert>

      <!-- Group Header -->
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="space-y-1">
          <div class="flex items-center gap-3">
            <h1 data-testid="page-heading" class="text-3xl font-bold">{{ group.name }}</h1>
            <StatusDropdown
              data-testid="group-status"
              :status="group.status"
              i18n-prefix="duties.eventGroups.statuses"
              :editable="authStore.isAdmin"
              @change="handleStatusChange"
            />
          </div>
          <p v-if="group.description" class="text-muted-foreground">{{ group.description }}</p>
          <p class="text-sm text-muted-foreground">
            <CalendarDays class="mr-1 inline h-3.5 w-3.5" />
            {{ formatDate(group.start_date) }} – {{ formatDate(group.end_date) }}
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm">
              <Printer class="mr-2 h-4 w-4" />
              {{ t('print.printButton') }}
              <ChevronDown class="ml-1 h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              @click="
                router.push({
                  name: 'print-event-group',
                  params: { groupId },
                  query: { mode: 'overview' },
                })
              "
            >
              <List class="mr-2 h-4 w-4" />
              {{ t('print.overview') }}
            </DropdownMenuItem>
            <DropdownMenuItem
              @click="
                router.push({
                  name: 'print-event-group',
                  params: { groupId },
                  query: { mode: 'all' },
                })
              "
            >
              <Printer class="mr-2 h-4 w-4" />
              {{ t('print.allEvents') }}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Separator />

      <!-- My Availability -->
      <Card data-testid="section-my-availability">
        <CardHeader>
          <div class="flex items-center justify-between gap-2">
            <div class="min-w-0 space-y-1">
              <CardTitle class="flex items-center gap-2">
                <UserCheck class="h-5 w-5 shrink-0" />
                {{ t('duties.availability.title') }}
              </CardTitle>
              <CardDescription>{{ t('duties.availability.subtitle') }}</CardDescription>
            </div>
            <div class="flex gap-2 shrink-0">
              <Button
                v-if="myAvailability"
                data-testid="btn-availability"
                variant="outline"
                size="sm"
                @click="showAvailabilityDialog = true"
              >
                <Pencil class="sm:mr-2 h-4 w-4" />
                <span class="hidden sm:inline">{{ t('duties.availability.update') }}</span>
              </Button>
              <Button
                v-if="myAvailability"
                data-testid="btn-remove-availability"
                variant="ghost"
                size="sm"
                class="text-destructive"
                @click="handleRemoveAvailability"
              >
                <Trash2 class="sm:mr-1.5 h-4 w-4" />
                <span class="hidden sm:inline">{{ t('duties.availability.remove') }}</span>
              </Button>
              <Button v-if="!myAvailability" data-testid="btn-availability" size="sm" @click="showAvailabilityDialog = true">
                <Check class="sm:mr-2 h-4 w-4" />
                <span class="hidden sm:inline">{{ t('duties.availability.register') }}</span>
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <AvailabilityDisplay v-if="myAvailability" :availability="myAvailability" />
          <p v-else class="text-sm text-muted-foreground">
            {{ t('duties.availability.notRegistered') }}
          </p>
        </CardContent>
      </Card>

      <!-- Events in group -->
      <div data-testid="section-events" class="space-y-3">
        <div class="flex items-center justify-between">
          <h2 class="text-xl font-semibold">{{ t('duties.eventGroups.detail.events') }}</h2>
          <Button
            v-if="authStore.isAdmin"
            size="sm"
            @click="router.push({ name: 'event-create', query: { groupId: groupId } })"
          >
            <Plus class="mr-1.5 h-4 w-4" />
            {{ t('duties.events.create') }}
          </Button>
        </div>
        <p v-if="groupEvents.length === 0" class="text-sm text-muted-foreground">
          {{ t('duties.eventGroups.detail.eventsEmpty') }}
        </p>
        <div v-else class="grid gap-3 sm:grid-cols-2">
          <Card
            v-for="event in groupEvents"
            :key="event.id"
            class="cursor-pointer transition-colors hover:bg-muted/50"
            @click="navigateToEvent(event)"
          >
            <CardHeader class="pb-2">
              <div class="flex items-start justify-between">
                <CardTitle class="text-base">{{ event.name }}</CardTitle>
                <Badge :variant="statusVariant(event.status)">
                  {{ t(`duties.events.statuses.${event.status ?? 'draft'}`) }}
                </Badge>
              </div>
              <CardDescription v-if="event.description">{{ event.description }}</CardDescription>
            </CardHeader>
            <CardContent>
              <p class="text-sm text-muted-foreground">
                {{ formatDate(event.start_date) }} – {{ formatDate(event.end_date) }}
              </p>
            </CardContent>
          </Card>
        </div>
      </div>

      <!-- Admin: all member availabilities -->
      <template v-if="authStore.isAdmin">
        <Separator />
        <div data-testid="section-admin-availabilities" class="space-y-3">
          <h2 class="flex items-center gap-2 text-xl font-semibold">
            <Users class="h-5 w-5" />
            {{ t('duties.availability.adminTitle') }}
          </h2>
          <p v-if="allAvailabilities.length === 0" class="text-sm text-muted-foreground">
            {{ t('duties.availability.adminEmpty') }}
          </p>
          <div v-else class="overflow-hidden rounded-lg border">
            <table class="w-full text-sm">
              <thead class="bg-muted/50">
                <tr>
                  <th class="px-4 py-2 text-left font-medium">User</th>
                  <th class="px-4 py-2 text-left font-medium">
                    {{ t('duties.availability.fields.type') }}
                  </th>
                  <th class="px-4 py-2 text-left font-medium">
                    {{ t('duties.availability.fields.dates') }}
                  </th>
                  <th class="px-4 py-2 text-left font-medium">
                    {{ t('duties.availability.fields.notes') }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y">
                <tr v-for="avail in allAvailabilities" :key="avail.id" class="hover:bg-muted/30">
                  <td class="px-4 py-2">
                    <div>{{ avail.user_full_name ?? '—' }}</div>
                    <div class="text-xs text-muted-foreground">{{ avail.user_email ?? '' }}</div>
                  </td>
                  <td class="px-4 py-2">
                    <div class="flex flex-wrap items-center gap-1.5">
                      <Badge variant="secondary">
                        {{ t(`duties.availability.types.${avail.availability_type}`) }}
                      </Badge>
                      <span
                        v-if="avail.default_start_time || avail.default_end_time"
                        class="text-xs text-muted-foreground"
                      >
                        {{
                          [avail.default_start_time, avail.default_end_time]
                            .filter(Boolean)
                            .join(' – ')
                        }}
                      </span>
                    </div>
                  </td>
                  <td class="px-4 py-2">
                    <span v-if="avail.available_dates?.length">
                      <span class="text-xs">
                        {{ avail.available_dates.map((d) => formatDateWithTime(d)).join(', ') }}
                      </span>
                    </span>
                    <span v-else class="text-muted-foreground">—</span>
                  </td>
                  <td class="max-w-48 px-4 py-2 text-muted-foreground">
                    <p class="line-clamp-3" :title="avail.notes ?? undefined">
                      {{ avail.notes ?? '—' }}
                    </p>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </template>

    <!-- Availability Dialog -->
    <AvailabilityDialog
      v-if="group"
      v-model:open="showAvailabilityDialog"
      :group="group"
      :existing-availability="myAvailability"
      @save="handleSaveAvailability"
    />
  </div>
</template>
