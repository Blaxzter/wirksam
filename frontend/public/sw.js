/**
 * Service Worker: Web Push notifications and an offline fallback page.
 *
 * Deliberately not an app-shell cache. The built assets are fingerprinted and
 * the API is live data, so caching either would only risk serving a stale app
 * after a deploy. The one thing cached is offline.html, shown when a page
 * navigation fails because the device has no connection.
 */

// Bump to replace the cached offline page after changing it.
const OFFLINE_CACHE = 'wirksam-offline-v1'
const OFFLINE_URLS = ['/offline.html', '/icon.svg']

self.addEventListener('install', (task) => {
  task.waitUntil(
    caches
      .open(OFFLINE_CACHE)
      .then((cache) => cache.addAll(OFFLINE_URLS))
      .then(() => self.skipWaiting()),
  )
})

self.addEventListener('activate', (task) => {
  task.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => key.startsWith('wirksam-offline-') && key !== OFFLINE_CACHE)
            .map((key) => caches.delete(key)),
        ),
      )
      // Starts the navigation request in parallel with booting the worker,
      // so routing navigations through it costs nothing.
      .then(() => self.registration.navigationPreload?.enable())
      .then(() => self.clients.claim()),
  )
})

/**
 * Network as usual; the offline page only when the request fails outright,
 * never for an error status, which the app handles itself.
 */
async function navigate(task) {
  try {
    return (await task.preloadResponse) ?? (await fetch(task.request))
  } catch {
    return (await caches.match('/offline.html')) ?? Response.error()
  }
}

self.addEventListener('fetch', (task) => {
  const { request } = task
  if (request.method !== 'GET') return

  if (request.mode === 'navigate') {
    task.respondWith(navigate(task))
    return
  }

  // The offline page's logo, which it cannot fetch while offline.
  if (new URL(request.url).pathname === '/icon.svg') {
    task.respondWith(
      fetch(request).catch(async () => (await caches.match('/icon.svg')) ?? Response.error()),
    )
  }
})

self.addEventListener('push', (task) => {
  if (!task.data) return

  let data
  try {
    data = task.data.json()
  } catch {
    data = { title: 'Notification', body: task.data.text() }
  }

  const options = {
    body: data.body || '',
    icon: data.icon || '/favicon.ico',
    badge: '/favicon.ico',
    data: data.data || {},
    tag: data.data?.notification_type_code || 'default',
    renotify: true,
  }

  task.waitUntil(self.registration.showNotification(data.title || 'WirkSam', options))
})

self.addEventListener('notificationclick', (task) => {
  task.notification.close()

  const data = task.notification.data || {}
  let url = '/app/home'

  if (data.task_id) {
    url = `/app/tasks/${data.task_id}`
  } else if (data.event_id) {
    url = `/app/events/${data.event_id}`
  } else if (data.booking_id) {
    url = '/app/bookings'
  }

  task.waitUntil(
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
