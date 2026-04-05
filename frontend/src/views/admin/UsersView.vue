<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Ban,
  Check,
  EllipsisVertical,
  Eye,
  EyeOff,
  KeyRound,
  Shield,
  ShieldOff,
  Trash2,
  UserCheck,
  UserRoundX,
  UserX,
  Users,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { toast } from 'vue-sonner'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar'
import Badge from '@/components/ui/badge/Badge.vue'
import Button from '@/components/ui/button/Button.vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import Input from '@/components/ui/input/Input.vue'
import {
  Pagination,
  PaginationContent,
  PaginationEllipsis,
  PaginationFirst,
  PaginationItem,
  PaginationLast,
  PaginationNext,
  PaginationPrevious,
} from '@/components/ui/pagination'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import Textarea from '@/components/ui/textarea/Textarea.vue'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

import type { UserRead } from '@/client/types.gen'
import { toastApiError } from '@/lib/api-errors'

const { t } = useI18n()
const { get, patch } = useAuthenticatedClient()

const PAGE_SIZE = 10

const users = ref<UserRead[]>([])
const loading = ref(false)
const updatingId = ref<string | null>(null)
const currentPage = ref(1)

// Approval password
const hasApprovalPassword = ref(false)
const approvalPasswordInput = ref('')
const approvalPasswordLoading = ref(false)
const showClearPasswordDialog = ref(false)
const showPassword = ref(false)

// Rejected users visibility
const showRejected = ref(false)

// Sorting
type SortKey = 'name' | 'email' | 'status' | 'created_at'
type SortDir = 'asc' | 'desc'
const sortKey = ref<SortKey>('created_at')
const sortDir = ref<SortDir>('desc')

const toggleSort = (key: SortKey) => {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
  currentPage.value = 1
}

// Reject dialog state
const showRejectDialog = ref(false)
const rejectingUser = ref<UserRead | null>(null)
const rejectionReason = ref('')
const isRejecting = ref(false)

// Stats
const totalUsers = computed(() => users.value.length)
const activeUsers = computed(() => users.value.filter((u) => u.is_active).length)
const pendingUsers = computed(
  () => users.value.filter((u) => !u.is_active && !u.rejection_reason).length,
)
const rejectedUsers = computed(
  () => users.value.filter((u) => !u.is_active && u.rejection_reason).length,
)

const getUserStatus = (user: UserRead): 'active' | 'rejected' | 'pending' => {
  if (user.is_active) return 'active'
  if (user.rejection_reason) return 'rejected'
  return 'pending'
}

// Filtered, sorted & paginated users
const filteredUsers = computed(() =>
  showRejected.value ? users.value : users.value.filter((u) => getUserStatus(u) !== 'rejected'),
)
const sortedUsers = computed(() => {
  const dir = sortDir.value === 'asc' ? 1 : -1
  return [...filteredUsers.value].sort((a, b) => {
    let cmp = 0
    switch (sortKey.value) {
      case 'name':
        cmp = (a.name ?? '').localeCompare(b.name ?? '')
        break
      case 'email':
        cmp = (a.email ?? '').localeCompare(b.email ?? '')
        break
      case 'status': {
        const order = { active: 0, pending: 1, rejected: 2 }
        cmp = order[getUserStatus(a)] - order[getUserStatus(b)]
        break
      }
      case 'created_at':
        cmp = a.created_at.localeCompare(b.created_at)
        break
    }
    return cmp * dir
  })
})
const totalPages = computed(() => Math.max(1, Math.ceil(sortedUsers.value.length / PAGE_SIZE)))
const paginatedUsers = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return sortedUsers.value.slice(start, start + PAGE_SIZE)
})

const formatDate = (iso: string) => {
  return new Date(iso).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

const getInitials = (user: UserRead) => {
  if (user.name) {
    return user.name
      .split(' ')
      .map((w) => w.replace(/[^a-zA-Z]/g, '')[0])
      .filter(Boolean)
      .join('')
      .toUpperCase()
      .slice(0, 2)
  }
  return user.email?.[0]?.toUpperCase() ?? '?'
}

const loadUsers = async () => {
  loading.value = true
  try {
    const response = await get<{ data: UserRead[] }>({ url: '/users/' })
    users.value = response.data
  } catch (error) {
    toastApiError(error)
  } finally {
    loading.value = false
  }
}

const toggleAdmin = async (user: UserRead) => {
  updatingId.value = user.id
  const hasAdmin = user.roles.includes('admin')
  const newRoles = hasAdmin ? user.roles.filter((r) => r !== 'admin') : [...user.roles, 'admin']
  try {
    const response = await patch<{ data: UserRead }>({
      url: `/users/${user.id}`,
      body: { roles: newRoles },
    })
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx !== -1) users.value[idx] = response.data
    toast.success(
      hasAdmin
        ? t('admin.users.removedAdmin', { name: user.name ?? user.email })
        : t('admin.users.grantedAdmin', { name: user.name ?? user.email }),
    )
  } catch (error) {
    toastApiError(error)
  } finally {
    updatingId.value = null
  }
}

const toggleActive = async (user: UserRead) => {
  updatingId.value = user.id
  try {
    const body: Record<string, unknown> = { is_active: !user.is_active }
    if (!user.is_active) {
      body.rejection_reason = null
    }
    const response = await patch<{ data: UserRead }>({
      url: `/users/${user.id}`,
      body,
    })
    const idx = users.value.findIndex((u) => u.id === user.id)
    if (idx !== -1) users.value[idx] = response.data
    toast.success(
      user.is_active
        ? t('admin.users.deactivated', { name: user.name ?? user.email })
        : t('admin.users.activated', { name: user.name ?? user.email }),
    )
  } catch (error) {
    toastApiError(error)
  } finally {
    updatingId.value = null
  }
}

const openRejectDialog = (user: UserRead) => {
  rejectingUser.value = user
  rejectionReason.value = ''
  showRejectDialog.value = true
}

const submitRejection = async () => {
  if (!rejectingUser.value) return
  isRejecting.value = true
  try {
    const response = await patch<{ data: UserRead }>({
      url: `/users/${rejectingUser.value.id}`,
      body: {
        is_active: false,
        rejection_reason: rejectionReason.value || null,
      },
    })
    const idx = users.value.findIndex((u) => u.id === rejectingUser.value!.id)
    if (idx !== -1) users.value[idx] = response.data
    toast.success(
      t('admin.users.rejectedToast', {
        name: rejectingUser.value.name ?? rejectingUser.value.email,
      }),
    )
    showRejectDialog.value = false
  } catch (error) {
    toastApiError(error)
  } finally {
    isRejecting.value = false
  }
}

const getStatusVariant = (status: string) => {
  if (status === 'active') return 'default' as const
  if (status === 'rejected') return 'destructive' as const
  return 'secondary' as const
}

const loadApprovalPassword = async () => {
  try {
    const response = await get<{ data: { has_approval_password: boolean } }>({
      url: '/settings/',
    })
    hasApprovalPassword.value = response.data.has_approval_password
  } catch (error) {
    toastApiError(error)
  }
}

const saveApprovalPassword = async () => {
  approvalPasswordLoading.value = true
  try {
    const password = approvalPasswordInput.value.trim() || null
    const response = await patch<{ data: { has_approval_password: boolean } }>({
      url: '/settings/',
      body: { approval_password: password },
    })
    hasApprovalPassword.value = response.data.has_approval_password
    if (password) {
      await navigator.clipboard.writeText(password)
    }
    approvalPasswordInput.value = ''
    showPassword.value = false
    toast.success(
      password
        ? t('admin.users.approvalPassword.savedAndCopied')
        : t('admin.users.approvalPassword.cleared'),
    )
  } catch (error) {
    toastApiError(error)
  } finally {
    approvalPasswordLoading.value = false
  }
}

const clearApprovalPassword = async () => {
  approvalPasswordInput.value = ''
  approvalPasswordLoading.value = true
  try {
    const response = await patch<{ data: { has_approval_password: boolean } }>({
      url: '/settings/',
      body: { approval_password: null },
    })
    hasApprovalPassword.value = response.data.has_approval_password
    showClearPasswordDialog.value = false
    toast.success(t('admin.users.approvalPassword.cleared'))
  } catch (error) {
    toastApiError(error)
  } finally {
    approvalPasswordLoading.value = false
  }
}

const approvalPasswordDirty = computed(() => {
  return approvalPasswordInput.value.trim().length > 0
})

onMounted(() => {
  loadUsers()
  loadApprovalPassword()
})
</script>

<template>
  <div class="mx-auto max-w-5xl space-y-6">
    <div class="space-y-2">
      <h1 data-testid="page-heading" class="text-3xl font-bold">{{ t('admin.users.title') }}</h1>
      <p class="text-muted-foreground">{{ t('admin.users.subtitle') }}</p>
    </div>

    <!-- Stats Cards -->
    <div data-testid="section-stats" class="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <Card data-testid="stat-total">
        <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle class="text-sm font-medium">{{ t('admin.users.statsTotal') }}</CardTitle>
          <Users class="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div class="text-2xl font-bold">{{ totalUsers }}</div>
        </CardContent>
      </Card>
      <Card data-testid="stat-active">
        <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle class="text-sm font-medium">{{ t('admin.users.active') }}</CardTitle>
          <UserCheck class="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div class="text-2xl font-bold">{{ activeUsers }}</div>
        </CardContent>
      </Card>
      <Card data-testid="stat-pending">
        <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle class="text-sm font-medium">{{ t('admin.users.pending') }}</CardTitle>
          <UserX class="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div class="text-2xl font-bold">{{ pendingUsers }}</div>
        </CardContent>
      </Card>
      <Card data-testid="stat-rejected">
        <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle class="text-sm font-medium">{{ t('admin.users.rejected') }}</CardTitle>
          <UserRoundX class="h-4 w-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div class="text-2xl font-bold">{{ rejectedUsers }}</div>
        </CardContent>
      </Card>
    </div>

    <!-- Approval Password Card -->
    <Card data-testid="section-approval-password">
      <CardHeader>
        <div class="flex items-center gap-2">
          <KeyRound class="h-5 w-5 text-muted-foreground" />
          <div>
            <CardTitle class="text-base">{{ t('admin.users.approvalPassword.title') }}</CardTitle>
            <CardDescription>{{ t('admin.users.approvalPassword.description') }}</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div class="flex items-center gap-2">
          <div class="relative w-full max-w-sm">
            <Input
              v-model="approvalPasswordInput"
              :type="showPassword ? 'text' : 'password'"
              :placeholder="
                hasApprovalPassword
                  ? t('admin.users.approvalPassword.changePlaceholder')
                  : t('admin.users.approvalPassword.placeholder')
              "
              class="pr-9"
            />
            <button
              type="button"
              class="absolute inset-y-0 right-0 flex items-center px-2.5 text-muted-foreground hover:text-foreground"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" class="h-4 w-4" />
              <Eye v-else class="h-4 w-4" />
            </button>
          </div>
          <Button
            size="icon"
            variant="outline"
            :disabled="approvalPasswordLoading || !approvalPasswordDirty"
            @click="saveApprovalPassword"
          >
            <Check class="h-4 w-4" />
          </Button>
          <TooltipProvider v-if="hasApprovalPassword">
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  size="icon"
                  variant="outline"
                  :disabled="approvalPasswordLoading"
                  @click="showClearPasswordDialog = true"
                >
                  <Trash2 class="h-4 w-4" />
                </Button>
              </TooltipTrigger>
              <TooltipContent>
                {{ t('admin.users.approvalPassword.clear') }}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </CardContent>
    </Card>

    <div v-if="loading" class="py-12 text-center text-muted-foreground">
      {{ t('common.states.loading') }}
    </div>

    <template v-else>
      <div v-if="rejectedUsers > 0" class="flex justify-end">
        <Button variant="outline" size="sm" @click="showRejected = !showRejected">
          <EyeOff v-if="showRejected" class="mr-2 h-4 w-4" />
          <Eye v-else class="mr-2 h-4 w-4" />
          {{ showRejected ? t('admin.users.hideRejected') : t('admin.users.showRejected') }}
        </Button>
      </div>

      <div data-testid="users-table" class="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead class="cursor-pointer select-none" @click="toggleSort('name')">
                <div class="flex items-center gap-1">
                  {{ t('admin.users.columns.name') }}
                  <ArrowUp v-if="sortKey === 'name' && sortDir === 'asc'" class="h-3.5 w-3.5" />
                  <ArrowDown
                    v-else-if="sortKey === 'name' && sortDir === 'desc'"
                    class="h-3.5 w-3.5"
                  />
                  <ArrowUpDown v-else class="h-3.5 w-3.5 text-muted-foreground/50" />
                </div>
              </TableHead>
              <TableHead class="cursor-pointer select-none" @click="toggleSort('email')">
                <div class="flex items-center gap-1">
                  {{ t('admin.users.columns.email') }}
                  <ArrowUp v-if="sortKey === 'email' && sortDir === 'asc'" class="h-3.5 w-3.5" />
                  <ArrowDown
                    v-else-if="sortKey === 'email' && sortDir === 'desc'"
                    class="h-3.5 w-3.5"
                  />
                  <ArrowUpDown v-else class="h-3.5 w-3.5 text-muted-foreground/50" />
                </div>
              </TableHead>
              <TableHead>{{ t('admin.users.columns.roles') }}</TableHead>
              <TableHead class="cursor-pointer select-none" @click="toggleSort('status')">
                <div class="flex items-center gap-1">
                  {{ t('admin.users.columns.status') }}
                  <ArrowUp v-if="sortKey === 'status' && sortDir === 'asc'" class="h-3.5 w-3.5" />
                  <ArrowDown
                    v-else-if="sortKey === 'status' && sortDir === 'desc'"
                    class="h-3.5 w-3.5"
                  />
                  <ArrowUpDown v-else class="h-3.5 w-3.5 text-muted-foreground/50" />
                </div>
              </TableHead>
              <TableHead class="cursor-pointer select-none" @click="toggleSort('created_at')">
                <div class="flex items-center gap-1">
                  {{ t('admin.users.columns.memberSince') }}
                  <ArrowUp
                    v-if="sortKey === 'created_at' && sortDir === 'asc'"
                    class="h-3.5 w-3.5"
                  />
                  <ArrowDown
                    v-else-if="sortKey === 'created_at' && sortDir === 'desc'"
                    class="h-3.5 w-3.5"
                  />
                  <ArrowUpDown v-else class="h-3.5 w-3.5 text-muted-foreground/50" />
                </div>
              </TableHead>
              <TableHead class="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow v-for="user in paginatedUsers" :key="user.id">
              <TableCell>
                <div class="flex items-center gap-3">
                  <Avatar class="h-8 w-8 rounded-sm">
                    <AvatarImage v-if="user.picture" :src="user.picture" :alt="user.name ?? ''" />
                    <AvatarFallback class="rounded-sm text-xs">{{
                      getInitials(user)
                    }}</AvatarFallback>
                  </Avatar>
                  <span class="font-medium">{{ user.name ?? '—' }}</span>
                </div>
              </TableCell>
              <TableCell class="text-muted-foreground">{{ user.email ?? '—' }}</TableCell>
              <TableCell>
                <div class="flex flex-wrap gap-1">
                  <Badge v-for="role in user.roles" :key="role" variant="secondary">
                    {{ role }}
                  </Badge>
                  <span v-if="user.roles.length === 0" class="text-xs text-muted-foreground"
                    >—</span
                  >
                </div>
              </TableCell>
              <TableCell>
                <Badge :variant="getStatusVariant(getUserStatus(user))">
                  {{ t(`admin.users.${getUserStatus(user)}`) }}
                </Badge>
              </TableCell>
              <TableCell class="text-muted-foreground">
                {{ formatDate(user.created_at) }}
              </TableCell>
              <TableCell>
                <DropdownMenu>
                  <DropdownMenuTrigger as-child>
                    <Button
                      variant="ghost"
                      size="icon"
                      class="h-8 w-8"
                      :disabled="updatingId === user.id"
                    >
                      <EllipsisVertical class="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem @click="toggleActive(user)">
                      <UserX v-if="user.is_active" class="mr-2 h-4 w-4 text-destructive" />
                      <UserCheck v-else class="mr-2 h-4 w-4" />
                      {{ user.is_active ? t('admin.users.deactivate') : t('admin.users.activate') }}
                    </DropdownMenuItem>
                    <DropdownMenuItem v-if="!user.is_active" @click="openRejectDialog(user)">
                      <Ban class="mr-2 h-4 w-4 text-destructive" />
                      {{ t('admin.users.reject') }}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem @click="toggleAdmin(user)">
                      <ShieldOff
                        v-if="user.roles.includes('admin')"
                        class="mr-2 h-4 w-4 text-destructive"
                      />
                      <Shield v-else class="mr-2 h-4 w-4" />
                      {{
                        user.roles.includes('admin')
                          ? t('admin.users.removeAdmin')
                          : t('admin.users.makeAdmin')
                      }}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </div>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="flex justify-center">
        <Pagination
          v-model:page="currentPage"
          :total="sortedUsers.length"
          :items-per-page="PAGE_SIZE"
          :sibling-count="1"
        >
          <PaginationContent>
            <PaginationFirst />
            <PaginationPrevious />
            <template v-for="(item, index) in totalPages" :key="index">
              <PaginationItem
                v-if="Math.abs(item - currentPage) <= 1 || item === 1 || item === totalPages"
                :value="item"
                :is-active="currentPage === item"
                as-child
              >
                <Button
                  variant="outline"
                  size="icon"
                  class="h-9 w-9"
                  :class="currentPage === item ? '!bg-primary !text-primary-foreground !border-primary' : ''"
                >
                  {{ item }}
                </Button>
              </PaginationItem>
              <PaginationEllipsis v-else-if="Math.abs(item - currentPage) === 2" />
            </template>
            <PaginationNext />
            <PaginationLast />
          </PaginationContent>
        </Pagination>
      </div>
    </template>

    <!-- Reject Dialog -->
    <Dialog v-model:open="showRejectDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('admin.users.rejectDialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{
              t('admin.users.rejectDialogDescription', {
                name: rejectingUser?.name ?? rejectingUser?.email,
              })
            }}
          </DialogDescription>
        </DialogHeader>
        <Textarea
          v-model="rejectionReason"
          :placeholder="t('admin.users.rejectReasonPlaceholder')"
          rows="3"
        />
        <DialogFooter>
          <Button variant="outline" @click="showRejectDialog = false">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button variant="destructive" :disabled="isRejecting" @click="submitRejection">
            {{ t('admin.users.reject') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Clear Approval Password Dialog -->
    <Dialog v-model:open="showClearPasswordDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t('admin.users.approvalPassword.clearDialogTitle') }}</DialogTitle>
          <DialogDescription>
            {{ t('admin.users.approvalPassword.clearDialogDescription') }}
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" @click="showClearPasswordDialog = false">
            {{ t('common.actions.cancel') }}
          </Button>
          <Button
            variant="destructive"
            :disabled="approvalPasswordLoading"
            @click="clearApprovalPassword"
          >
            {{ t('admin.users.approvalPassword.clear') }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
