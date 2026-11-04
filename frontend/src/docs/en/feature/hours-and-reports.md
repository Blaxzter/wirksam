---
title: Hours and reports
lede: WirkSam counts each volunteer's hours from the shifts they booked, so you don't need a list of your own. You add work no shift covers by hand, export the list as CSV, and the Reports page shows how full your shifts are and when it's busiest.
related: feature/booking, feature/vouchers, feature/people-in-charge, guide/first-event
---

Hours are counted on their own, with nothing to turn on. Volunteers see their own hours on My Bookings, and organisers see everyone's in the event's settings.

On top of that there's the Reports page, for an overview of all your events, and a print view for every task.

## What counts as worked

A shift counts once it's over and the person has a confirmed booking on it. Until then it's shown as planned and stays out of the total. Cancelled bookings don't count.

The length comes from the shift's start and end time. A shift past midnight comes out right too: 22:00 to 02:00 is four hours. A shift without a start or end time counts as 0 hours, and the overview says below the list how many of those there are.

WirkSam doesn't record who actually turned up. So a confirmed booking counts even if the person didn't come.

## What volunteers see

My Bookings has a "Your hours" card for the selected event: the hours worked, what's still to come from booked shifts, and how the total splits into "From shifts" and "Additional". On a phone it's a small "Hours" tile on the Bookings tab.

"Breakdown" lists every shift and all hours added by hand, with the name of whoever added them. Shifts still to come are marked "Upcoming".

![My Bookings on a phone with the hours tile above the list of shifts](phone:bookings-phone)

## The organisers' overview

Under "Manage Events", open the event and choose the "People" tab. The "Worked hours" card lists everyone who has hours or booked shifts, most hours first: shifts, shift hours, additional hours and the total.

Click a row to see the shifts and entries behind it. People who left the event stay in the list with the hours they worked, marked "no longer in the event".

Only organisers see this overview. People in charge and volunteers see their own hours.

![The "Worked hours" card on the People tab with shifts, shift hours and the total for each person](shot:event-hours)

## Adding hours by hand

This is for work no shift covers: setting up the day before, an errand, a shift someone covered without booking it. "Add hours" asks for the volunteer, date, hours and "What was done". Enter the hours as a decimal, so 1.5 for an hour and a half, at most 24 per entry. The description is required.

Added hours count straight away and appear in the "Additional" column. You can edit or delete an entry in the person's details. You can only add hours for current members of the event, and you can't take hours away this way.

## Exporting as CSV

"Export CSV" on the "Worked hours" card downloads the list, for example for certificates or thank-you letters. It includes every member of the event, also those with no hours, and every former member with hours.

The file has the name, email, role, shifts worked, shift hours, additional hours, the total, and upcoming shifts and hours. The column headings are in English, and hours are decimals with a point, such as 1.50.

## The Reports page

"Reports" is in the sidebar, and under "More" on a phone. You see the page once you organise at least one event. It combines all the events you organise, and there's no filter for a single one.

It shows:

- "Total Bookings", split into confirmed and cancelled
- "Fill Rate": booked places against all places
- "Tasks", with the number of shifts and how many of them have at least one booking
- "Active Volunteers": the people with a confirmed booking in the date range. "Total Volunteers" beside it also counts everyone else in those events
- "Bookings Over Time", by day or month
- "Bookings by Time of Day": confirmed bookings by the start time of their shift, which shows your busy times
- "Most Active Volunteers": the ten people with the most confirmed bookings
- "By Category" and "Fill Rate by Task": places, bookings and fill rate in detail

![The Reports page with the numbers for bookings and fill rate and the bookings over time](shot:reports)

## Date range and export

You choose the date range at the top of the page. By default it runs from the start of this month to the end of next month. It goes by the date of the shift, whenever it was booked. For last year's event, set the range to its days.

"Export CSV" downloads all bookings in the range, one line per booking, including cancelled ones with their reason. Each line also has the name and email, shift, date, times, hours, place, category and task. On a phone the export is in the menu with the three dots.

## Printing a task

On a task's page, the button with the printer opens the print view. Organisers find "Print" in the menu with the three dots. Anyone who can see the task can print it.

The sheet has one line for each place on a shift. At the top are the task, its days and a QR code with the note "Scan to sign up online". By default the lines stay empty, for writing names in by hand. Beside the sheet, "Display options" decide what goes on it:

- "Show booked names" fills in who booked. Phone numbers only appear if you're an organiser or in charge of the task.
- "Show title column" and "Show location column" start out on when the shifts differ in title or place.
- "Repeat header on each page" is on by default.
- "Show location map" appears when the task has one place with a pin on the venue map.
- "Filter dates" appears when there are several days, and prints only the ones you choose.

## Frequently asked questions

### What happens to the hours when I move or delete a shift?

The hours follow the shift, because WirkSam works them out from its times each time. If you change the times, the hours of everyone booked on it change too. If you move a worked shift into the future, it counts as planned again. If you delete it, its hours are gone. [Vouchers](/features/vouchers) are different: they stay. If you still want to delete a worked shift, add the hours back afterwards with "Add hours".

### Someone booked but didn't come. Do the hours still count?

Yes. WirkSam doesn't record who was there, and once a shift has ended the booking can't be cancelled. You can only add hours by hand. For a certificate, the simplest fix is to correct the number in the exported file.

### Can people in charge see other people's hours?

No. The overview and the export are for organisers only. People in charge see their own hours on My Bookings, like everyone else.

### Why is my report empty?

It's usually the date range, which by default runs from the start of this month to the end of next month. If your event's shifts fall outside that, set the range to its days.

### Which list do I use for certificates?

The export from the "Worked hours" card. It includes the hours added by hand. The export from Reports lists single bookings, including cancelled ones and ones not worked yet.
