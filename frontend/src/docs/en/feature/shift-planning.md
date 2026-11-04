---
title: Shift planning
lede: In WirkSam you describe a task once, and its shifts are built from days, times, shift length and headcount. A preview shows what you'll get beforehand, and volunteers only see the task once you publish it.
related: guide/first-event, guide/next-year, feature/venue-map, feature/booking
---

A drinks stand from 10 to 6, changing over every two hours, two people each, on three days: that's twelve shifts. You enter the pattern once, WirkSam creates them, and everyone in the event sees the same plan.

Organisers can plan, and so can the [people in charge](/features/people-in-charge) of a task for that task. On tasks with [vouchers](/features/vouchers), only organisers change the shifts by default.

## Event, task, shift

A plan has three levels:

- The **event** is the whole thing, say the summer festival. It has a name and a date range and is private by default, so only people you invite can find it.
- A **task** is something that needs covering over a stretch of time, such as the drinks stand or the clear-down. It has a name and, if you like, a description, a place and a category.
- A **shift** is a block of time on that task with a set number of places. That's what volunteers book.

Tasks can only be scheduled inside the event's dates.

Every event has a time zone, and shift times count in it: 10:00 means 10:00 at the venue, wherever someone opens the plan. If their device is set to another zone, the task and their booking say so in a short note. If you change the zone later, a shift at 10:00 stays at 10:00, and reminders and calendars follow.

WirkSam shows you one event at a time. Tasks, shifts and bookings all stay in that event, so you don't have to hunt for the right list. If you're part of several, switch at the top of the sidebar, or on a phone under "More" with "Change event". Once an event is over, WirkSam asks you to pick the next one.

## Shifts from a pattern

"Create Task" takes you through five sections: "Task Details", "Event", "Task Dates", "Schedule & Shifts" and "Preview". The pattern lives in two of them.

Under "Task Dates" you choose the days. "One day" is selected to begin with, and there's also "Date range", and "Specific dates" for scattered days.

Under "Schedule & Shifts" you set how each of those days is split up:

- "Default Start Time" and "Default End Time", filled in with 10:00 and 18:00
- "Shift Duration" of 15, 30, 45, 60, 90 or 120 minutes, filled in with 30
- "People per Shift", filled in with 2

![The form that builds the shifts, next to the preview of what it creates](shot:shift-schedule)

## Leftover time, exceptions and the preview

If the time doesn't divide evenly, a "Remaining time" question appears. 10:00 to 18:00 in 90-minute shifts, for example, gives five shifts until 17:30, with half an hour left over:

- "Ignore remaining time" is selected to begin with: the last shift ends at 17:30.
- "Create a shorter final shift" adds a shift from 17:30 to 18:00.
- "Extend the last shift" makes the last shift run from 16:00 to 18:00.

With "Date range" and "Specific dates", one day can have different times, such as a Sunday that finishes at 14:00. Under "Date Exceptions", "Add Exception" lets you pick the day and its times. Shift length and headcount stay the same.

The "Preview" lists every shift, day by day, with the total above. Click a shift to strike it out and leave it out, such as a Sunday morning nobody works. Click again to bring it back. Nothing is created until you press "Create Task".

## Changing and adding later

On a task's page, "Add Shifts" offers two routes:

- "Generate shift batch" opens the same pattern, for more days or different times. A batch can have its own place and category.
- "Add single shift" creates exactly one shift, say for setting up the evening before.

If a task has several batches, they're listed separately there, each with its own "Edit" and delete.

When you change days or times under "Edit", the save button becomes "Regenerate Shifts". Shifts with the same day and times stay, new ones are added and any that no longer fit are deleted. If that touches booked shifts, "Affected Bookings" lists who first. Those people aren't told automatically, so you let them know yourself.

If the whole event moves, enter a new start date under "Shift Dates" in its settings. Every task, shift and availability entry moves by the same number of days.

## Categories and places

The "Category" is free text, such as "Kitchen" or "Set-up". There's no fixed list. It shows with the task in the list, on its page and on the printout.

For "Location", "No location" is selected to begin with. Below it are the event's places, "New location…" creates one on the spot, and "Other (type it in)…" takes free text. The shifts take on what you choose when you create them. If you change a task's place later without touching days or times, its shifts keep the one they had.

You look after places in the event's settings on the "Locations" tab, with a description, address, map link and contact. Volunteers see all that when they open a shift. Only these places appear on the [venue map](/features/venue-map) and in the "Location" filter of the task list. Typed-in text stays plain text.

If the shifts of a task have different places or categories, filters for them appear on its page.

![A shift's details with its place, the people in charge and who's on it](shot:shift-dialog)

## Drafts and publishing

Every new task starts as a draft. Volunteers can't see it or book it, though its people in charge can see it. On the home screen, "Needs your attention" shows organisers how many tasks are still drafts.

Only organisers can publish, on the task's page: with "Publish now" or through the status next to its name. That covers the whole task with all its shifts. The same status lets you set a task to "Archived". Volunteers then no longer see it in the plan, though anyone who booked it can still open their shift.

A newly created event is published straight away. Whether anyone can book depends only on its tasks.

![A task's page with the cards for people in charge and vouchers, and the shifts](shot:task-detail)

## List, cards and calendar

"Tasks" has three views:

- "List" is the default: each task is a row with a strip of its shifts, day by day. The "Centre on today" and "Jump to first available" buttons decide where the strip starts.
- "Cards" shows each task as a card with its description and dates.
- "Calendar" shows the plan by "Month", "Week" or "Day".

List and cards have a search, a date range that starts "From today", and a "Filters" menu with "My bookings only", "Hide fully booked" (list only), "Only tasks I can book" and "Location". The calendar has its own navigation instead.

By default, volunteers only see tasks in the list and cards that still have a free shift to come. Choosing another date range shows the rest as well. Organisers and people in charge see their tasks even when they're fully booked.

![The task list with a week strip of shifts](shot:tasks)

## Printing and reusing

On a task's page, "Print" opens a printable view: organisers find it in the "⋯" menu, everyone else as a printer icon. By default it's a sign-up sheet, with an empty line per place for a name and contact, and a QR code for signing up online.

Next to it you choose what goes on paper: "Show title column", "Show location column", "Repeat header on each page", "Show booked names" and "Filter dates". "Show location map" appears when all the shifts share one place with a pin.

Next year you don't have to build it all again. "Copy this event" puts the tasks on new dates, with last time's shifts or freshly planned ones. Sign-ups stay behind. The steps are in [Copy an event for next year](/guides/next-year).

## Frequently asked questions

### Can a shift run past midnight?

Not in the pattern, where the end time has to be after the start time. A single shift can: under "Add single shift", enter 22:00 to 02:00, for example, and it runs into the next morning.

### Can shifts on one task need different numbers of people?

Yes. Within a batch the number is the same. For a different number, add another batch, or a single shift with its own figure under "Max Bookings".

### Can we change shifts once people have booked?

Yes. Shifts whose day and times stay the same keep their bookings. If a booked shift would go, WirkSam names the people affected first and you decide whether to go ahead. Once a booked shift has started, only organisers can do that.

### Do we have to publish each shift separately?

No. You publish a task with all its shifts. Each task is published on its own, so you can keep working on one while another is already open for booking.
