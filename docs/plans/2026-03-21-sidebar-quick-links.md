# Sidebar Quick Links — Feature Plan

**Status:** Draft — ready for review
**Created:** 2026-03-21

**Goal:** Populate the sidebar navigation with contextual quick links derived from a dashboard endpoint, making the left nav feel useful and alive rather than empty.

---

## Concept

Instead of a user-managed watchlist, the sidebar automatically shows relevant items under each nav entry using data from the existing `GET /api/v1/dashboard/feed` endpoint (or a new dedicated sidebar endpoint). No user action required — the system decides what's relevant.

### Sidebar sketch

```
Home
Event Groups                    v
   Pfingsten 2026
   Kirchentag 2026
Events                          v
   Morning Shift A    (3 open)
   Night Coverage     (1 open)
My Bookings                     v
   Sat 22.03 — Morning Shift
   Mon 24.03 — Night Coverage
```

Each section is collapsible. Items are links that navigate directly to the detail view.

---

## What counts as "relevant"

### Event Groups

- Published groups whose `end_date >= today` (active or upcoming)
- Sorted by `start_date` ascending
- Limit: ~5, with "View all" link if more exist

### Events

- Published events whose `end_date >= today`
- Optionally: only events with open slots (slots where `current_bookings < max_bookings`)
- Sorted by `start_date` ascending or by next open slot date maybe color coded by urgency (15 minutes until start = red badge etc...)
- Limit: ~10, with "View all" link

### My Bookings

- User's confirmed bookings where `slot.date >= today`
- Sorted by `slot.date, slot.start_time` ascending
- Limit: ~5, with "View all" link

### Admin section (if admin)

- Pending user count badge (already available in dashboard feed)

---

## Open Questions

### 1. New endpoint or extend existing?

- **Option A:** Extend `GET /api/v1/dashboard/feed` with a `sidebar` section — keeps it to one request on app load
- **Option B:** New `GET /api/v1/dashboard/sidebar` — lighter payload, can be cached/polled independently
- Leaning toward **Option A** since the home view already calls `/feed` on load, but the sidebar needs this data on _every_ authenticated page, not just home. A separate lightweight endpoint may be cleaner.

Answer new endpoint..

### 2. When to fetch?

- On app load (PostAuthLayout mount) + periodic refresh?
- On sidebar expand only?
- Event-driven (refetch after booking/cancellation)?
- Keep it simple: fetch once on auth, refetch on navigation to home

yeah feetch once on page load is enough. We can add event-driven refetch later if needed.

### 3. How many items per section?

- Too few (1-2) and it doesn't fill the space
- Too many (10+) and the sidebar becomes overwhelming
- Suggestion: 5 per section, configurable server-side via query param

i defeined the values above.
and make each scrollable with a max height maybe?

### 4. What to show per item?

- **Event Groups:** name only (compact)
- **Events:** name + open slot count badge (useful context)
- **Bookings:** date + slot title (e.g. "Sat 22.03 — Morning Shift")

Yeah sounds good including the color stuff :)

### 5. Empty states

- No upcoming events → hide the sub-list entirely (nav item stays as direct link)
- No bookings → hide sub-list or show "No upcoming bookings" text?

---

## Technical Approach

### Backend

**New endpoint** `GET /api/v1/dashboard/sidebar`:

```python
class SidebarEventGroup(BaseModel):
    id: uuid.UUID
    name: str

class SidebarEvent(BaseModel):
    id: uuid.UUID
    name: str
    open_slots: int  # slots where current_bookings < max_bookings and date >= today

class SidebarBooking(BaseModel):
    id: uuid.UUID
    slot_id: uuid.UUID
    slot_title: str
    slot_date: dt.date
    slot_start_time: dt.time | None

class SidebarResponse(BaseModel):
    event_groups: list[SidebarEventGroup]
    events: list[SidebarEvent]
    bookings: list[SidebarBooking]
```

Query for events with open slot count:

```sql
SELECT e.id, e.name,
       COUNT(ds.id) FILTER (
         WHERE ds.date >= CURRENT_DATE
           AND ds.max_bookings > (
             SELECT COUNT(*) FROM booking b
             WHERE b.duty_slot_id = ds.id AND b.status = 'confirmed'
           )
       ) AS open_slots
FROM event e
LEFT JOIN duty_slot ds ON ds.event_id = e.id
WHERE e.status = 'published' AND e.end_date >= CURRENT_DATE
GROUP BY e.id
ORDER BY e.start_date
LIMIT 5
```

### Frontend

1. **New composable or store** — `useSidebarData()` or extend existing dashboard store
    - Fetches `GET /api/v1/dashboard/sidebar` on PostAuthLayout mount
    - Exposes reactive `eventGroups`, `events`, `bookings` lists
    - Refetch on key navigation events (e.g. after booking)

2. **Make `navMain` in AppSidebar reactive** — convert from static array to computed, populating `items` sub-arrays from the sidebar store:

    ```ts
    const navMain = computed(() => [
        {
            title: "Event Groups",
            titleKey: "...",
            icon: CalendarRange,
            routeName: "event-groups",
            isActive: true,
            items: sidebarStore.eventGroups.map((g) => ({
                title: g.name,
                routeName: "event-group-detail",
                routeParams: { groupId: g.id },
            })),
        },
        // ... events, bookings
    ]);
    ```

3. **Extend NavMain sub-item type** — add optional `routeParams` so sub-items can link to detail views (e.g. `/app/events/:eventId`)

4. **i18n** — add keys for empty states and "View all" links in `en/` and `de/`

5. **Regenerate API client** after backend changes

### Effort

- Backend: small (one new endpoint with 3 queries)
- Frontend: medium (reactive nav items, store, NavMain route params extension)

---

## Relationship to Watchlist

This feature and the [Event Watchlist](2026-03-21-event-watchlist.md) are complementary but independent:

- **Quick links** = automatic, system-driven, shows what's relevant _now_
- **Watchlist** = manual, user-driven, shows what the user _chose_ to track

Quick links should be built first. A watchlist can be layered on later if users need to pin specific events beyond what the system surfaces automatically.

---

## Decision Log

| Date       | Decision                                                                                                                     |
| ---------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 2026-03-21 | Idea captured. Preferred over watchlist as first step — no user action needed, solves the empty sidebar problem immediately. |
