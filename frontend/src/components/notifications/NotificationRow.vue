<script setup lang="ts">
import { type Component, computed } from 'vue'

import {
  AlarmClock,
  Ban,
  Bell,
  CalendarCheck,
  CalendarClock,
  CalendarPlus,
  CalendarRange,
  CalendarX,
  CheckCheck,
  ChevronRight,
  Copy,
  Mail,
  MailCheck,
  Megaphone,
  ShieldCheck,
  Trash2,
  UserCheck,
  UserMinus,
  UserPlus,
  UserX,
  Users,
  UsersRound,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import type { NotificationItem } from '@/stores/notification'

import { Button } from '@/components/ui/button'

import HintTooltip from '@/components/utils/HintTooltip.vue'

import { noticeTime, notificationTarget } from '@/lib/notifications'

/**
 * One notice in the inbox, as a card: an icon for what it is about, the
 * title, the text and how old it is.
 *
 * Unread ones stand out the way the Inbox design draws them: a green icon
 * tile, a green edge, a bold title and a dot, plus "Open task ›" (or whatever
 * it opens) under the text. Read ones keep a grey tile and recede.
 *
 * A notice with somewhere to go is a link; clicking it (`open`) is for the
 * parent to mark it read. "Mark as read" and "Delete" show on hover or
 * keyboard focus, so a pointer and a keyboard reach them while the card
 * stays as calm as the design; on a phone the inbox page swipes instead.
 * `dense` is the smaller card of the bell's dropdown.
 */
const props = defineProps<{
  notification: NotificationItem
  /** Passed in so a list ages all its notices from one clock. */
  now: Date
  dense?: boolean
}>()

const emit = defineEmits<{ open: []; read: []; dismiss: [] }>()

const { t, locale } = useI18n()

/** What the notice is about, as a picture, by its type. */
const ICONS: Record<string, Component> = {
  'booking.confirmed': CalendarCheck,
  'booking.cancelled_by_user': CalendarX,
  'booking.cancelled_by_admin': CalendarX,
  'booking.shift_cobooked': Users,
  'booking.reminder': AlarmClock,
  'shift.starting_soon_unfilled': AlarmClock,
  'shift.time_changed': CalendarClock,
  'task.published': CalendarPlus,
  'task.manager_added': UserCheck,
  'task.manager_removed': UserMinus,
  'event.published': Megaphone,
  'event.cloned': Copy,
  'availability.reminder': CalendarRange,
  'event.invitation': Mail,
  'event.invitation_accepted': MailCheck,
  'event.join_requested': UserPlus,
  'event.join_approved': UserCheck,
  'event.join_declined': UserX,
  'event.role_changed': ShieldCheck,
  'team.join_requested': UserPlus,
  'team.join_approved': UsersRound,
  'team.join_declined': UserX,
  'user.registered': UserPlus,
  'user.approved': UserCheck,
  'user.rejected': UserX,
  'user.suspended': Ban,
  'user.reinstated': UserCheck,
}

const icon = computed(() => ICONS[props.notification.notification_type_code] ?? Bell)
const target = computed(() => notificationTarget(props.notification.data))
const unread = computed(() => !props.notification.is_read)
const age = computed(() => noticeTime(props.notification.created_at, props.now, t, locale.value))
</script>

<template>
  <div class="group relative" data-testid="notification-row">
    <component
      :is="target ? RouterLink : 'div'"
      :to="target?.to"
      class="flex w-full rounded-2xl border text-left text-card-foreground transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
      :class="[
        dense ? 'gap-2.5 p-3' : 'gap-3 py-3.5 pr-3.5 pl-3',
        unread ? 'border-primary/30 bg-card' : 'bg-card/60',
        target || unread ? 'cursor-pointer hover:bg-card' : '',
      ]"
      :data-unread="unread || undefined"
      @click="emit('open')"
    >
      <span
        class="flex shrink-0 items-center justify-center"
        :class="[
          dense ? 'size-9 rounded-[10px]' : 'size-10.5 rounded-xl',
          unread ? 'bg-primary/15 text-primary' : 'bg-secondary text-muted-foreground',
        ]"
        aria-hidden="true"
      >
        <component :is="icon" :class="dense ? 'size-[18px]' : 'size-5'" />
      </span>
      <span class="min-w-0 flex-1 pr-4">
        <span
          class="block leading-snug"
          :class="[dense ? 'text-sm' : 'text-[15px]', unread ? 'font-bold' : 'font-semibold']"
        >
          {{ notification.title }}
        </span>
        <span
          v-if="notification.body"
          class="mt-1 block text-muted-foreground"
          :class="dense ? 'line-clamp-2 text-[13px]' : 'text-sm'"
        >
          {{ notification.body }}
        </span>
        <span
          class="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-muted-foreground"
          :class="dense ? 'mt-1.5 text-xs' : 'mt-2 text-[13px]'"
        >
          <span data-testid="notification-time">{{ age }}</span>
          <span
            v-if="unread && target"
            class="flex items-center gap-0.5 font-bold text-primary"
            data-testid="notification-open"
          >
            {{ t(`notifications.open.${target.kind}`) }}
            <ChevronRight class="size-3.5" aria-hidden="true" />
          </span>
        </span>
      </span>
      <span v-if="unread" class="sr-only">{{ t('notifications.unread') }}</span>
    </component>

    <span
      v-if="unread"
      aria-hidden="true"
      class="pointer-events-none absolute size-2.5 rounded-full bg-primary transition-opacity group-focus-within:opacity-0 group-hover:opacity-0"
      :class="dense ? 'top-3 right-3' : 'top-3.5 right-3'"
      data-testid="notification-unread-dot"
    />

    <!-- On hover or keyboard focus only; still in the page for screen readers -->
    <div
      data-no-swipe
      class="pointer-events-none absolute top-2 right-2 flex gap-0.5 rounded-lg border bg-popover p-0.5 opacity-0 shadow-sm transition-opacity group-focus-within:pointer-events-auto group-focus-within:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100"
    >
      <HintTooltip v-if="unread" :label="t('notifications.markRead')">
        <Button
          variant="ghost"
          size="icon"
          class="size-8 hover:bg-primary/10 hover:text-primary"
          :aria-label="t('notifications.markRead')"
          data-testid="btn-notification-read"
          @click.stop="emit('read')"
        >
          <CheckCheck class="size-4" />
        </Button>
      </HintTooltip>
      <HintTooltip :label="t('notifications.dismiss')">
        <Button
          variant="ghost"
          size="icon"
          class="size-8 hover:bg-destructive/10 hover:text-destructive"
          :aria-label="t('notifications.dismiss')"
          data-testid="btn-notification-dismiss"
          @click.stop="emit('dismiss')"
        >
          <Trash2 class="size-4" />
        </Button>
      </HintTooltip>
    </div>
  </div>
</template>
