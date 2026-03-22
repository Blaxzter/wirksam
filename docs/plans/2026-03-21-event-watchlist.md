# Event Watchlist — Feature Plan (Draft)

**Status:** Idea — not yet approved for implementation
**Created:** 2026-03-21

**Goal:** Let users mark events they want to keep track of, and surface those events in the sidebar for quick access.

**Motivation:** The left side of the navigation feels sparse. A watchlist section below "Events" would add utility and fill the space with contextually relevant content.

---

## Concept

Users can star/bookmark events. Starred events appear in a collapsible list in the sidebar below the "Events" nav item, giving quick navigation to events the user cares about.

### Sidebar sketch

```
Home
Event Groups
Events
  Watchlist               v
     Morning Shift A
     Weekend Duty
     Night Coverage
My Bookings
```

---

## Open Questions

These need answers before implementation:

### 1. What happens with past events on the watchlist?
- **Auto-hide** events whose `end_date` is in the past? After how long — immediately, 1 week, 1 month?
- **Auto-remove** from watchlist entirely after some threshold?
- **Move to a separate section** ("Past" vs "Upcoming")?
- Or leave it to the user to clean up manually?

### 2. Should the watchlist tie into notifications?
- Watching an event could mean "notify me when new slots open" or "notify me of changes"
- Or it could be purely a navigation shortcut with no notification side-effects
- The notification system already exists — extending it would be straightforward but adds scope

### 3. Naming
- "Watchlist" / "Merkliste"
- "Favorites" / "Favoriten"
- "Pinned" / "Angepinnt"
- "Starred" / "Markiert"

### 4. How many events will users realistically watch?
- If users watch 2-3 events, a sidebar list works great
- If users watch 20+, the sidebar list needs pagination or a "show top N" approach
- This depends on how the system is actually used in practice

### 5. Scope of the sidebar section
- Show only event names (compact)?
- Show next available slot date (useful but more data to fetch)?
- Show a badge with open slot count?

---

## Technical Approach (if approved)

### Backend
1. New `UserEventWatch` model — simple join table: `user_id` + `event_id` + `created_at`
2. Endpoints: `POST /events/{id}/watch`, `DELETE /events/{id}/watch`, `GET /users/me/watchlist`
3. Alembic migration
4. Optional: filter/sort options (e.g. exclude past events server-side)

### Frontend
1. Pinia `watchlist` store
2. Star/bookmark toggle component (reusable on list, card, detail, and calendar views)
3. New collapsible sidebar section in `AppSidebar` / `NavMain`
4. i18n keys in `en/` and `de/`
5. Regenerate API client

### Effort estimate
- Small-medium feature. Backend is straightforward (join table + 3 endpoints). Frontend is the bulk of the work (sidebar integration, toggle button across views).

---

## Decision Log

| Date | Decision |
|------|----------|
| 2026-03-21 | Idea captured. Parking until real usage patterns emerge. |
