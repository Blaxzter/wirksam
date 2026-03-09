# TODO

## User Notification System

When an admin regenerates duty slots for an event and existing confirmed bookings are
affected (their slots no longer exist), the system currently only informs the admin
via a confirmation dialog. The affected users are **not** notified.

### Requirements

- [ ] Notify users when their confirmed booking is cancelled due to slot regeneration
- [ ] Notification channel TBD (in-app notification, email, or both)
- [ ] Include details: event name, original slot date/time, reason for cancellation
- [ ] Consider a notification preferences model (opt-in/out per channel)
- [ ] Backend: create a `notifications` table and CRUD
- [ ] Backend: trigger notifications from the `regenerate-slots` endpoint when `affected_bookings` is non-empty
- [ ] Frontend: notification bell / inbox UI for users to see their notifications
