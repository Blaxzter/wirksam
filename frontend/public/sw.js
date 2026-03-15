 
/**
 * Service Worker for Web Push Notifications
 */

self.addEventListener('push', (event) => {
  if (!event.data) return

  let data
  try {
    data = event.data.json()
  } catch {
    data = { title: 'Notification', body: event.data.text() }
  }

  const options = {
    body: data.body || '',
    icon: data.icon || '/favicon.ico',
    badge: '/favicon.ico',
    data: data.data || {},
    tag: data.data?.notification_type_code || 'default',
    renotify: true,
  }

  event.waitUntil(self.registration.showNotification(data.title || 'WirkSam', options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const data = event.notification.data || {}
  let url = '/app/home'

  if (data.event_id) {
    url = `/app/events/${data.event_id}`
  } else if (data.event_group_id) {
    url = `/app/event-groups/${data.event_group_id}`
  } else if (data.booking_id) {
    url = '/app/bookings'
  }

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes('/app') && 'focus' in client) {
          client.navigate(url)
          return client.focus()
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(url)
      }
    }),
  )
})
