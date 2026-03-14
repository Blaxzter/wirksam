# E2E Test Coverage Report

## Summary

| Area | Tests | Status |
|------|-------|--------|
| **Public Pages** | 6 | Landing, About, How It Works, navigation |
| **Dashboard** | 16 | Stats cards, calendar, quick actions |
| **Events List** | 12 | Navigation, list view, search, view modes, admin create |
| **Event Creation** | 9 | Form wizard sections, date modes, full flow |
| **Event Detail** | 14 | Page structure, booking/cancelling, admin status, delete |
| **Event Groups** | 25 | Navigation, list, CRUD, detail, availability |
| **My Bookings** | 11 | Navigation, filters, grouping, cancel |
| **Settings** | 8 | Profile, language, notifications |
| **Admin Users** | 6 | Navigation, page structure, RBAC |
| **Navigation** | 16 | Sidebar links, breadcrumbs, 404, toggle |
| **Member RBAC** | 9 | Events, event groups, sidebar restrictions |
| **Cross-User** | 5 | Event booking flow, event group visibility |
| **Total** | ~137 | |

## Coverage by Feature

### Public Pages (pre-auth)
- [x] Landing page hero and CTA buttons
- [x] About page accessible
- [x] How It Works page accessible
- [x] Navigation between public pages
- [x] PreAuth layout renders correctly

### Dashboard (`/app/home`)
- [x] Page heading renders
- [x] Events stat card visible with count
- [x] My Bookings stat card visible with count
- [x] Pending Users stat card (admin)
- [x] Stats cards navigate to correct pages
- [x] Calendar section with month heading
- [x] Calendar view toggle (Month/Week)
- [x] Today button
- [x] Filter button
- [x] Quick Actions section
- [x] Browse Events → `/app/events`
- [x] My Bookings → `/app/bookings`

### Events (`/app/events`)
- [x] Sidebar navigation link
- [x] Direct URL navigation
- [x] Heading and search input visible
- [x] Created event appears in list
- [x] Search filters by name
- [x] Clicking event navigates to detail
- [x] Switch to box view
- [x] Switch to calendar view
- [x] Switch back to list view
- [x] Admin sees Create button
- [x] Create button navigates to create page

### Event Creation (`/app/events/create`)
- [x] Page accessible via URL
- [x] Back button visible and functional
- [x] Details section open by default
- [x] Fill details and advance to next section
- [x] Event group section with 3 options (none/existing/new)
- [x] Date section with 3 modes (single/range/specific)
- [x] Full creation flow attempt
- [ ] End-to-end event creation with slot verification (needs date picker automation)

### Event Detail (`/app/events/:id`)
- [x] Shows event name and status badge
- [x] Shows event description
- [x] Shows location and category in header
- [x] Shows duty slots section
- [x] Shows slot time cards with availability counts
- [x] Back button navigates to events list
- [x] Click slot to book → count updates
- [x] Booked slot shows in My Bookings summary
- [x] Click booked slot to cancel → count reverts
- [x] Admin: change status (published → archived)
- [x] Admin: edit button visible
- [x] Admin: delete button visible
- [x] Admin: Add Slots button visible
- [x] Admin: delete event with confirmation dialog

### Event Groups (`/app/event-groups`)
- [x] Sidebar navigation
- [x] Direct URL navigation
- [x] Heading and search input
- [x] Created group appears with published badge
- [x] Search filters list
- [x] Click card navigates to detail
- [x] Admin: Create button visible
- [x] Admin: create via dialog
- [x] Admin: delete via trash icon
- [x] Detail page: name and status badge
- [x] Detail page: date range
- [x] Detail page: My Availability section
- [x] Detail page: Events in this Group section
- [x] Detail page: back button
- [x] Detail page: non-existent group handling
- [x] Availability: Register button when none set
- [x] Availability: dialog opens with type options
- [x] Availability: cancel dialog without saving
- [x] Availability: register as fully available
- [x] Availability: add note when registering
- [x] Availability: remove availability
- [x] Availability: update existing availability
- [x] Availability: specific dates option with date builder
- [x] Availability: register specific dates
- [x] Availability: API-registered dates visible in UI
- [x] Admin: member availabilities table visible
- [x] Admin: empty state when no registrations
- [x] Admin: registered availability in table

### My Bookings (`/app/bookings`)
- [x] Sidebar navigation
- [x] Heading visible
- [x] Filter tabs (upcoming, this month, all)
- [x] Show cancelled toggle
- [x] Booked slot appears in list
- [x] Booking shows confirmed status
- [x] Cancel booking from bookings page
- [x] Filter switching (all, this month)
- [x] Grouping buttons visible

### Settings (`/app/settings`)
- [x] Page accessible via URL
- [x] Current profile card visible
- [x] Edit profile section
- [x] Language settings
- [x] Notification settings link
- [x] Password reset section
- [x] Delete account / danger zone
- [x] Language switching (English ↔ German)
- [x] Notification preferences page loads

### Admin User Management (`/app/admin/users`)
- [x] Sidebar shows link for admin
- [x] Navigation via sidebar
- [x] Direct URL access
- [x] Page heading
- [x] Stats cards (total, active)
- [x] User table with columns
- [x] Current admin appears in list
- [x] Approval password section
- [x] Member cannot access page (RBAC)

### Navigation & Layout
- [x] All sidebar links visible (Home, Event Groups, Events, My Bookings)
- [x] Admin sidebar links (User Management, Demo Data)
- [x] User profile button in sidebar
- [x] All sidebar links navigate correctly (6 links)
- [x] Breadcrumbs on dashboard and events
- [x] Toggle Sidebar button
- [x] 404 page for non-existent routes
- [x] `/404` direct access

### Member RBAC
- [x] No Create button on events list
- [x] No edit/delete/add-slots on event detail
- [x] Cannot access event create page
- [x] Can see published events
- [x] Can view event detail
- [x] Can book a slot
- [x] No Create button on event groups
- [x] No Delete button on event group cards
- [x] No member availabilities admin table
- [x] Can see published groups, cannot see drafts
- [x] Can manage own availability
- [x] No User Management sidebar link
- [x] No Demo Data sidebar link

### Cross-User Scenarios
- [x] Admin creates event → member sees in list
- [x] Member books slot → admin sees updated count
- [x] Admin publishes group → member sees it
- [x] Admin draft group → hidden from member
- [x] Member registers availability → admin sees in table
- [x] Member removes availability → admin sees empty state
- [x] Multiple members' availability visible to admin

## Not Covered (would need additional setup)
- End-to-end event creation with date picker (shadcn DatePicker interaction)
- Event editing workflow (requires existing event with specific batch config)
- Add slots to existing event
- Notification bell and notification feed
- Push notification / Telegram binding
- Demo data creation/deletion
- Pending approval flow (requires unapproved user)
- Account deletion flow (destructive, would break test user)
- Admin user actions (activate/deactivate, grant/revoke admin)
- Approval password management
- Pagination on user management table
