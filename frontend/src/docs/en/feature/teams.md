---
title: Teams and checks
lede: A team lets you reserve tasks for the people who should do them, such as the cash desk or the drivers. You decide who joins, and tick off checks such as a police certificate or first-aid course before approving, without keeping a copy.
related: guide/teams, feature/people-in-charge, feature/booking, feature/vouchers
---

Normally anyone in an event can book any shift. That doesn't suit every task: you want someone you know at the cash desk, and only people who have shown a police certificate looking after children.

Teams stay off until you use them. If no task is reserved, booking works as before, and volunteers don't see the Teams menu item until there is a team. A team belongs to one event. A task can be reserved for one team, and a team can have many tasks.

## Reserving a task for a team

When creating or editing a task, organisers set who can book its shifts under "Who can book". The default is "Everyone in the event". With "Only one team" you pick a team from the list, or create one there with "New team…". Until you pick one, everyone can still book.

Organisers can always book these shifts, in the team or not. [People in charge](/features/people-in-charge) can't: they need to be in the team.

## What everyone else sees

A reserved task stays visible to everyone in the event, and is only locked. The task list says "Cash desk only" with a padlock, the task page says "Only members of Cash desk can book these shifts.", and each shift has a padlock.

The way in is right there: "Join Cash desk" for an open team, "Ask to join Cash desk" for one that needs approval. After asking, it says "Request sent".

Anyone who only wants to see what they can book can turn on "Only tasks I can book" in the filters. It's off by default.

On the Teams page, people find their own teams under "Your teams" and the rest under "More teams". That list says what a team does and how many shifts are still open.

## Open teams and teams with approval

New teams start with "Approval needed to join" on. Someone who wants in sends a request, with a note if they like. Team leads and organisers get an email and a push message, and the request appears at the top of the Teams page. For a team without checks, they decide right in the row with "Approve" or "Decline".

Turn approval off and the team is open: anyone in the event can join straight away and book. That suits tasks where people can judge for themselves. If requests are waiting when you turn it off, they are all approved when you save, and any files attached to them are deleted. The form says how many before you do.

The person hears the result: by email and push if they're in, by email if they're not, and in their inbox either way. A decline needs no reason, and they can ask again.

![The Teams page with waiting requests, the list of teams and the members of the chosen team](shot:teams)

## Team leads and adding people directly

Organisers make a member a lead with "Make team lead" in the menu on their row. A team lead decides requests, adds people, records checks and removes members, all from their team under "Your teams". Editing or deleting the team, reserving tasks, appointing leads and removing other leads stay with the organisers.

"Add someone from the event" puts a person straight into the team, with no request. They have to be in the event already. If the team has checks, the same ticks are needed as for a request. WirkSam tells them they're in, unless you added yourself.

## Checks and reviewing

A team can list up to ten checks that someone has to see before a person joins. A new team has none. A team with checks always needs approval.

There are three templates, and you can change all of them:

- **Extended police certificate:** asks for the issue date, valid for 5 years, no file
- **First-aid course:** asks for the issue date, valid for 2 years, file allowed
- **Driving licence class B:** no date, doesn't run out, no file

"Something else" adds your own. For each check you set what to check, an optional note, whether to ask for the issue date, whether people may attach a file and how many years it's valid.

A request with checks opens with "Review request". Approving only works once every check is ticked, with the issue date where asked. WirkSam refuses a date in the future, and one so old the check would already have run out. Validity counts from the issue date, or from the day of the check if no date is asked for.

![Reviewing a request to join, with a tick and the issue date for each check](shot:team-review)

## What is stored and what isn't

A tick stores who checked, when, the issue date and until when the check is valid. WirkSam keeps no copy of the document for it. Team leads and organisers see in the member list which check is valid until when.

If the same person has already been checked in another team of this event for a check with the same name, the review says so and fills in the date. You still tick it yourself. This never carries over to another event.

When someone leaves the team or the event, or is removed, their ticks go too.

## Attached files

If "People may attach a file" is on for a check, the person can attach, replace or remove a file when asking, or later under "Your teams". It's optional: one PDF or photo (PNG, JPEG, WebP) per check, up to 5 MB.

The person, the team leads and the organisers can open it, and other volunteers can't. It is deleted as soon as the request is decided, whichever way, and also if the person withdraws the request or leaves the event. After an approval, only the tick remains. When a photo is uploaded, WirkSam removes embedded data such as where it was taken. Demo events take no files.

## When a check runs out

An expired check locks nobody out. The person stays in the team and can keep booking. The member list shows "Needs a new check" next to them, and under "Your teams" they read: "One of your checks for this team has run out. You can still book; talk to the team lead about a new one." WirkSam sends no message about it.

Once you've seen a new one, choose "Record a new check" in the menu on their row and tick it. The same flag appears if you add a check after someone joined, or if you rename a check or start asking for its issue date, because the old ticks then no longer apply.

## Frequently asked questions

### Does WirkSam store the police certificate?

No. The "Extended police certificate" template takes no file: the person shows it, and you tick it off. WirkSam stores who saw it and when, the issue date and until when the check is valid. That stays so unless you turn on "People may attach a file" for it yourself.

### What happens to booked shifts when someone leaves the team?

They stay booked, and only new bookings stop. In a team with approval, the person has to ask again to come back. If they leave the whole event, they also lose their bookings for shifts that aren't over yet.

### Can we reserve a task for a team later on?

Yes. Whoever has already booked stays booked. The rule only applies to new bookings.

### What happens if we delete a team?

Its tasks are open to everyone in the event again, and booked shifts stay booked. Its memberships and ticks go with it.

### Do teams and checks come along when we copy an event?

The teams and the checks they ask for do, the ticks don't. If you copy the members too, they stay in their teams and show "Needs a new check" where a team asks for checks. Waiting requests stay behind. More in the guide [Copy an event for next year](/guides/next-year).
