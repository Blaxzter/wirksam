# Shared lists: guests earn vouchers, and one guest account per confirmed address

Created 2026-11-12 on `feat/shared-lists`, on top of the finished shared-lists backend
(uncommitted in that worktree). Revised 2026-11-13 after a review: the first
confirmation promotes the chain in place, a sign-up keeps its own name and phone, a
confirmation deletes unused codes, the merge locks the chain's `users` row, and the
guest rate limits count per guest. It amends `2026-11-10-shared-lists.md`. It
supersedes:

- D10's "a shift that ends while a guest holds it earns nothing" and open question Q3;
- D12's "consent stored on the chain": the consent, and the name and phone it was
  given with, move to the booking (V7);
- the wizard hint of §7.4 ("Wer sich ohne Konto einträgt, bekommt keine Marken");
- §4.17 step 4 ("frozen at 0");
- the main plan's `guest_manage_limiter` "keyed by IP" (§5 here).

Everything else in that plan stands. Paths are relative to the repository root;
`app/` means `backend/app/` and `src/` means `frontend/src/`. Line numbers are those
of the worktree on 2026-11-12. Once this is built, the code wins over this document.

---

## 1. Summary

People who sign up through a shared list earn vouchers ("Marken") on voucher tasks,
exactly as members do. They spend them at a stand by showing the same six-character,
two-minute, single-use code members show. They get that code from their manage page,
through a public endpoint that the manage token authenticates. Redeeming *by code*
accepts a guest of the event; picking a person *by hand* stays members-only.

Marken belong to whoever holds the sign-up:

- **A sign-up chain** (one guest user, as today) holds its own Marken. Any token of that
  chain can show a code for them. This covers guests without an email address
  (product goal 3) and guests who never confirm their address.
- **A guest account**: for each event and each *confirmed* address there is at most
  one. It is a `shared_list_guests` row with `confirmed_at` set. Someone opens a
  chain's mail link and presses "Ja, das bin ich":
  - if the address has no account at that event yet, that chain **becomes** the
    account, in place;
  - otherwise the chain is **merged** into the account: its bookings, reminders,
    earnings and redemptions move to the account's user, its unused codes are
    deleted, and its user is deleted.

  One manage page then shows every confirmed sign-up with that address at that event,
  with one pooled balance.
- An address that someone only typed into the form opens nothing beyond the chain it
  created. Only a mail link can confirm, and only a mail link opens an account.

Every sign-up keeps its own name, phone number and first-name consent on its booking.
Pooling adds Marken up; it never puts one person's name on another person's shift.

Old mail links keep working after a merge: a small alias table maps the merged
chain's id and nonce to the account. A chain's sign-up-response token stops working
at its confirmation, whether the chain was promoted or merged. That token is the one
an attacker who typed someone else's address would hold, and every code issued before
the confirmation dies with it.

Transparency. The API now returns:

- the Marken each shift earns (public list, form, done page, manage page);
- the retention period, `GUEST_DATA_RETENTION_DAYS`. Today no endpoint returns it, so
  the guest pages would have to write "30" into their text, and the text would be
  wrong on a server set to another value;
- on the manage page, the date the guest's data will be deleted.

The confirmation mail also mentions the Marken, how to redeem them, how to confirm the
address and the retention period. Marken that are not redeemed when a guest's data is
deleted expire. Every place that names the retention period says so, and names only
the data that list actually stores.

The model changes are amended into `app/alembic/versions/20261110_0001_shared_lists.py`:

- `shared_list_guests.confirmed_at`, with a partial unique index per (event, address);
- `bookings.show_first_name`, `bookings.guest_name` and `bookings.guest_phone`;
  `shared_list_guests.show_first_name` is dropped;
- a new table, `shared_list_guest_aliases`.

---

## 2. Decisions with rationale

### V1. Guests earn like members

`settle_earnings` (`app/logic/vouchers.py:221`) stops writing
`case((User.is_list_guest, 0), …)` (l. 262) and writes `Task.vouchers_per_shift` for
everyone. The derived select in `_voucher_shifts` (l. 383-408) drops its join on `User`
and the `is_list_guest IS FALSE` filter (l. 405). "Earned is earned" is unchanged:

- Ownership does not enter the derivation (`counts_as_worked()` is `status ==
  'confirmed'`, `app/logic/work_hours.py:50-63`). Moving a booking from one guest user
  to another therefore changes no amount, and the merge needs no settling, except in
  the defensive duplicate case of §4.2.
- Nothing is released yet, so no guest booking anywhere was settled at 0. No data fix
  is needed.

Rejected:

- **Keep 0.** The 0 was a placeholder for "no account to pay into", and the product
  owner wants guests to earn.
- **Earn only after confirming.** Guests without an address could never earn
  (contradicts goal 3), and a confirmation would change what an ended shift earned.

**No-shows.** Members who do not show up earn Marken today too, until attendance
(#177) changes `counts_as_worked()`. Guests are cheaper to create, and organiser
removal refuses ended shifts (`booking.shift_over`, `removal.py:181-185`). So the
organisers' tool is a negative correction. Corrections already work for guests,
because `_appears_in_event` (`app/api/routes/vouchers.py:629`) counts confirmed bookings
(§4.5).

### V2. A guest account is the first confirmed chain of its address; later ones merge into it

`voucher_earnings`, `voucher_entries` and `voucher_passes` are keyed by `user_id`. So are
`lock_ledger` (`app/crud/voucher.py:237`), `available_for`, the organiser overview
`balances` and the redeem path. One user per balance keeps all of that untouched. So:

- An account is a `shared_list_guests` row with `confirmed_at IS NOT NULL`, and at most
  one exists per `(event_id, lower(email))`, enforced by a partial unique index (§3).
- The **first** confirmation of an address at an event **promotes** the confirming
  chain in place: `confirmed_at = now`, and the chain's unused codes are deleted.
  Nothing moves.
  - Its response token dies with that, because `resolve()` accepts a response-key
    token only from a row with `confirmed_at IS NULL` (§4.3). No nonce rotation is
    needed.
  - Its mail token, the link in its own confirmation mail, is now the account's. No
    alias is needed.
- Every later confirmation of the same address at the same event **merges** that chain
  into the account's user (§4.2).
- The event is `shared_list_guests.event_id`, the list's event at the chain's first
  sign-up. "Within an event" means within that event. The same address at another
  event is another account.

Most addresses have one chain, so the common path writes one column and one `DELETE`
and takes no ledger lock. The merge's machinery, and its races (§4.8), run only when
one address really has several chains.

Rejected:

- **Pool at read time across the chain users** (or a `guest_accounts` table plus
  `shared_list_guests.account_id`). Every function in `app/logic/vouchers.py` would need
  a "holder" abstraction: `_tally` groups by booker, `lock_ledger` locks one user, and
  `redeem` writes `VoucherEntry.user_id`. One chain could show a negative balance while
  the pool is positive. The organiser overview would list each chain separately. And
  erasing one chain would CASCADE away redemption entries the pool relied on.
- **A fresh guest user for every account**, into which even the first chain is merged.
  It makes the first confirmation the same operation as every later one, but it runs
  the whole merge (row moves, ledger locks, alias, user delete) and its races on the
  common path for nothing. The argument for it, that a promoted chain's response token
  would need a nonce rotation, does not hold: `confirmed_at` already retires it.

### V3. Confirming: one explicit POST from a button, only with a mail link

`POST /public/guest-signups/confirm` exists only as a button on the manage page:
"Ja, das bin ich". The page shows it only when it was opened with the chain's **mail**
token (`GuestKey.from_mail`, `app/logic/shared_lists/guest_tokens.py:45-51`).

- The page's automatic POST to `/manage` on load stays read-only.
- The SPA shell is the only GET.
- The endpoint verifies the token before it takes any lock or hashes any address
  (§4.2 step 1).

So link prefetchers, and scanners that run JavaScript, confirm nothing.

Rejected:

- **Confirm on load.** Scanners that run scripts would confirm, and the owner would
  never see which sign-ups were merged into their page. With the button, the owner sees
  the chain's shifts first and chooses "Ja, das bin ich" or "Das war ich nicht".
- **Confirm with the response token.** Anyone can type anyone's address.

### V4. Merged chains leave an alias, so old mail links still open the account

The merge deletes the chain's user. Without help, every mail sent to that chain (the
confirmation mail most of all) would then lead to "Dieser Link funktioniert nicht
(mehr)". So `shared_list_guest_aliases` stores the merged chain's user id and nonce
with the account's user id. `guest_tokens.resolve()` falls back to it:

| Token presented | Found | Resolves to |
|---|---|---|
| mail key, unconfirmed chain | guest row | the chain, `from_mail=True` |
| response key, unconfirmed chain | guest row | the chain, `from_mail=False` |
| mail key, account (`confirmed_at` set) | guest row | the account, `from_mail=True`. For a promoted chain this is the link in its own confirmation mail |
| response key, account | guest row | **nothing**. Issued to the promoted chain at its sign-up and retired by the promotion. `guest_tokens.retired_response_token()` reports it, so a sign-up continuation with it starts a new chain (§4.2) |
| mail key, merged chain | alias | the alias's account, `from_mail=True` |
| response key, merged chain | alias | **nothing**. `retired_response_token()` reports it too |
| anything else | | nothing (404 `guest_signup.not_found`) |

Aliases die with the account: FK `account_user_id` ON DELETE CASCADE, and an explicit
delete in `anonymise` (§4.6).

**Residual risk: a mail link is a key to the wallet.** Every mail link of a confirmed
address opens the whole account, through its alias if the chain was merged. Pressing
"Ja, das bin ich" on a not-yet-merged chain's mail link hands the account's token to
whoever presses it. People forward sign-up mails ("ich hab uns eingetragen").
Whoever gets one can show a code and spend the pooled Marken, cancel shifts, or erase.
Before this change, a forwarded link reached one chain with no Marken. This plan does
not close the gap: the link is the only key a guest has. It says so wherever the link
is handed out. Every guest mail and the done page carry `link_private` (§6, §7.2), and
docs/SHARED_LISTS.md names the risk.

Rejected:

- **Dead links after a merge.** The confirmation mail is the one link guests keep.
- **Keep merged chain users as empty shells.** The retention sweep deletes nameless
  guest users without bookings (`retention.py:106-115`); `shared_list_guests.user_id`
  is unique, and the shell's row would still carry an address.

### V5. Unconfirmed chains see only themselves; any token of the chain can show a code

This is goal 2's second bullet. Until a confirmation, a chain's tokens open the chain
and nothing else: its bookings and its own Marken. The response token can issue a code
for those Marken.

- That is the only key a guest without an address has (goal 3).
- For a guest with an address, the response token holder made those sign-ups.
- Pooled Marken are reachable only through a mail token, because only mail tokens
  resolve to an account (V4).
- If someone later confirms the chain from its mail, the response token dies at that
  moment, so whoever typed the address loses access. Every code issued before dies
  too: promote and merge both delete the chain's unused codes (§4.2). A code kept on
  a screen can never spend Marken pooled by the confirmation.

### V6. Accounts only ever hand out mail tokens

- The confirm response returns `mail_token(account)` so the page can carry on. For a
  promotion it is the token the page already holds.
- Every later mail to the account links `mail_token(account)`. Mail tokens are already
  what `deliver_notice` and `removal` build; they look the guest up by user id.
- A sign-up never continues an account: `_chain` (`signup.py:96`) only accepts a live,
  **unconfirmed** chain of this list. So `PublicSignupResult.guest_token` is never an
  account's live token.

### V7. A sign-up's consent, name and phone move to the booking

A merge puts sign-ups from different lists, different forms and possibly different
people (a family that shares one address) under one guest user. One `users` row cannot
say "yes for this shift, no for that one", nor "Tom on this shift, Maria on that one".
So each guest booking carries its own person:

- `bookings.show_first_name` is set on every sign-up to `form.show_names == "first" and
  list.show_names == "first"`. That is today's rule (`signup.py:296-299`), applied per
  sign-up, including a reactivated row.
- `bookings.guest_name` and `bookings.guest_phone` are set on every sign-up, including a
  reactivated row, from the chain user's `name` and `phone_number`. That is what the
  chain stored; a continuation's typed fields lose to the chain, as today
  (`signup.py:250-251`).
- Member bookings keep `false`, `NULL` and `NULL`. Members are never named publicly,
  and their profile stays the source of their name.

**The rule.** Wherever a booking's person is shown, a list guest's booking shows
`guest_name` and `guest_phone`, never the guest user's `name` and `phone_number`.
`app/crud/booking.py` gets the helpers: `person_name(booking, user)`,
`person_phone(booking, user)`, and the SQL expressions `person_name_sql()` and
`person_phone_sql()`, for example `case((User.is_list_guest, Booking.guest_name),
else_=User.name)`. These readers switch:

- `public_page.first_names` (l. 46-70) reads `Booking.guest_name`, filtered on
  `Booking.show_first_name` and `User.is_list_guest`. It **keeps** the inner join to
  `shared_list_guests` with `erased_at IS NULL`. So a guest whose event was deleted
  has no row and is never named, even when a moved task took their booking to another
  event (main plan §4.14).
- `crud_booking.confirmed_bookers` (`crud/booking.py:342-374`, the names on shift cards).
- `list_shift_bookings` (`routes/shifts.py:361-381`) and `list_task_bookings`
  (`routes/tasks/crud.py:335-360`): name and phone.
- The affected-bookings preview of a shift regeneration (`routes/tasks/shifts.py:536-545`).
- The bookings CSV (`routes/reporting.py:101`).
- `signups_query.list_signups` (l. 59-180): name, phone, search, sort and the duplicate
  hint. `search_guests` (l. 218-246) also matches booking snapshots, so the operator
  finds Tom inside Maria's account.
- Guest mails about bookings. Removal (`removal.py:229`) and `deliver_notice`
  (`guest_mail.py:541`) greet the booking's `guest_name`. A mail about several
  bookings with different names uses `greeting_no_name`.

A guest user's own `name` and `phone_number` belong to the wallet holder. They are used
for the manage page's header, the organisers' voucher overview, the redeemer's check
sheet and the top fields of the Art. 15 export. For an account that is the first
confirmed chain.

The merge therefore changes no name or phone anywhere, and nothing is copied into the
account. The confirm card says that each sign-up keeps its name (§7.2). `anonymise`
nulls the snapshots together with the user's name (§4.6), so they follow the user's
retention clock. After a merge, that is the account's last pooled shift (V9).

This is what D12 promised ("stored on the sign-up"). The form's fine print already
speaks of "dieser Schicht".

Rejected:

- **The account's name and phone for every pooled booking.** Take a family address.
  Maria signs up on L1, which promised "Niemand sieht, wer sich eingetragen hat", and
  confirms. Tom signs up on L2, which shows first names, with the same address. Maria
  confirms Tom's chain. L2 would then show "Maria" at Tom's shift: the D12 flaw the
  main plan fixed, a name published from a form that promised anonymity. Organisers
  would see Maria at Tom's shift, and Tom's phone would be lost or copied onto Maria's
  account and kept past the retention Tom was told.
- **Refusing a merge when the names differ.** Nicknames and typos ("Max", "Maximilian
  M.") make a name comparison unreliable, and the product goal pools by address, not
  by name.
- **AND-ing the consent flags on merge.** That un-names shifts the guest agreed to,
  silently. It is privacy-safe, but untrue to what the form said.

### V8. Redeeming: by code for live guests of the event, by hand for members only

`_member_or_404` (`vouchers.py:653`) becomes `_holder_or_404(…, allow_guest)`:

- `check` and `redeem` pass `allow_guest=True` on the code path and `False` on the
  `user_id` path;
- `available_for_members` and `list_point_people` (the redeem picker) are unchanged, so
  guest names never reach a picker that on-shift members see;
- a guest qualifies when `users.is_list_guest`, the guest row exists with a live
  `manage_nonce` (not erased, event not deleted), and `appears_in_event(event_id,
  user_id)` holds (§4.5).

Showing the code is the guest's consent to be named to the redeemer, as it is for
members (`may_redeem_manually` docstring, `permissions.py:619-636`).

For a guest whose phone is dead, the fallback is the existing correction: an event
admin books a negative amount with a note such as "am Stand eingelöst". A note is
free text, and the natural one names the person. So `anonymise` clears the notes of a
guest's corrections (§4.6), and a name written into one does not outlive the guest's
data.

Rejected: a manual redemption for guests. Their names would reach the picker of every
on-shift member at a point.

### V9. Erasing, "Das war ich nicht" and retention with accounts

- Erasing an account erases everything pooled in it. An account is one confirmed
  address, and whoever reads that inbox may erase what was confirmed under it. The
  same `erase_guests` rules apply (`erase.py:78`).
- It erases only what is pooled. A chain with the same address that nobody confirmed
  stays: its mail never went out, or was never opened. Such a chain is erased through
  its own link, or by the operator on request. The copy says "die Eintragungen auf
  dieser Seite", never "alle Eintragungen mit dieser Adresse" (§7.2). A confirmation
  is never sent when `reserve_mail` refuses (`signup.py:344-362`: the daily ceiling, a
  suppressed address, no SMTP), so such chains are real (open question 10).
- "Das war ich nicht" is offered and accepted only for **unconfirmed** chains opened
  from their mail. On an account it answers 409 `guest_signup.reject_confirmed`: the
  person confirmed those sign-ups themselves; they can cancel shifts or erase.
- "Das war ich nicht" on a chain erases the chain. It suppresses the address only
  while the address has **no** live account at any event; the suppression is global
  (`guest_quota.py:261`). Only the inbox owner holds a chain's mail token. If that
  person confirmed an account, a suppression would silently stop their own reminders
  and "moved" and "removed" mails, since `reserve_mail` refuses a suppressed address.
  So in that case the chain is erased and the address stays mailable.
  `GuestSignupManage.reject_suppresses` tells the dialog which of the two texts to
  show (open question 11).
- Unredeemed Marken **expire** when the data is anonymised: erase, "not me" or the
  retention sweep. The manage link is gone, so no code can be shown. Every place that
  states the retention period says so (goal 6).
- Retention stays per guest user, from that user's own bookings
  (`retention.py:43-80`). An account's clock is therefore its latest pooled shift. That
  also holds for the names and phones on its pooled bookings.
- A guest user with voucher entries, or with earnings worth something, is anonymised
  but never deleted. Deleting it would CASCADE away redemptions, and with them the
  stand's history and `point_totals`. Members already keep such rows until they
  delete their account. A nameless guest row costs nothing. The notes of its
  corrections are cleared (V8).

### V10. The API delivers the numbers; the frontend hard-codes none

- `PublicShift.vouchers`;
- `PublicSharedList.retention_days`, which the organisers' preview gets too, through
  the same builder;
- `GuestSignupBooking.vouchers`, `.show_first_name` and `.name`;
- `GuestSignupManage.retention_days`, `.erase_on`, `.confirmed`, `.can_confirm`,
  `.reject_suppresses`, `.has_phone` and `.vouchers` (per event);
- the confirmation mail reads `settings.GUEST_DATA_RETENTION_DAYS`
  (`app/core/config.py:301`).

The prerendered privacy page is the one exception (open question 5).

### V11. Organisers see guests in the voucher overview

`balances` (`vouchers.py:540`) already lists non-members with a non-zero tally as
"former" rows. Guests now reach it:

- `VoucherBalance.is_guest` is new;
- the guest's address is filled from `crud_shared_list_guest.contact_emails` (D12: event
  admins see guest contact data, and `/vouchers/people` is admin-only);
- the frontend tags those rows "Ohne Konto" instead of "Nicht mehr dabei".

`VoucherCheckResult.is_guest` tags the redeemer's confirm sheet the same way.
`PointRedemptionRead` gets no flag: no screen renders its `user_name` today.

### V12. Forward-compatible with the deferred claim

The merge is `guest_account.merge_guest(session, *, source, target_user_id, now)`, and
its target is any user id. Its caller holds the locks of §4.7: the guest rows, the
ledger locks of both users and the source's `users` row. The deferred claim (§4.17 of
the main plan) can call it with the verified account's id. It then adds:

- the membership;
- `replace_for_booking` with the account's `default_reminder_offsets`;
- clearing the moved bookings' `guest_name` and `guest_phone`: a member's booking reads
  the member's profile (V7);
- deleting the guest user.

Lock order: the claim takes `guest-account:{event_id}:{hash}` for every event of the
guest rows it picks up, sorted, **before** any guest row, as confirm does (§4.7). The
main plan's claim row ("guest rows `FOR UPDATE` → …") predates this lock. Taking it
after a guest row would invert confirm's order and could deadlock against it.

The claim no longer needs §4.17's "settle at 0" step. Aliases point at the guest
account, so they die when the claim deletes it. Confirmed accounts are also exactly the
unit a claim should pick up ("this inbox already proved it owns these").

---

## 3. Data model changes (amend `20261110_0001`)

All datetimes are naive `sa.DateTime`. CHECKs and server defaults are mirrored by hand
in the model and the migration.

**`app/models/shared_list.py`, `SharedListGuest`** (l. 226-306)

- Drop `show_first_name` (l. 282-292).
- Add:

  ```python
  confirmed_at: dt.datetime | None = Field(
      default=None, sa_column=sa.Column(sa.DateTime, nullable=True),
      description=(
          "Set when this row is the guest account of (event_id, email): the address "
          "was confirmed through a mail link. The first confirmed chain of an address "
          "becomes the account in place; later ones are merged into it "
          "(logic/shared_lists/guest_account.py)."
      ),
  )
  ```

- Add to `__table_args__`, next to `ix_shared_list_guests_email_lower`:

  ```python
  sa.Index(
      "uq_shared_list_guests_account",
      "event_id", sa.text("lower(email)"),
      unique=True,
      postgresql_where=sa.text("confirmed_at IS NOT NULL"),
  ),
  ```

  An erased account has `email = NULL`, and NULLs are distinct, so erasing frees the
  slot for a new account.
- Docstring: a row is a chain, or an account (a chain promoted by its confirmation). An
  account is only ever reached through mail tokens.

**New `SharedListGuestAlias`** (`shared_list_guest_aliases`), in the same module:

| Column | Type | Notes |
|---|---|---|
| id, created_at, updated_at | Base | `ix_shared_list_guest_aliases_id` |
| user_id | Uuid, NOT NULL, **no FK**, `unique=True, index=True` | the merged chain's former user id → `ix_shared_list_guest_aliases_user_id` (unique) |
| manage_nonce | String(32), NOT NULL | the chain's nonce at the merge; it verifies the chain's old tokens |
| account_user_id | Uuid FK `users.id` ON DELETE CASCADE, NOT NULL, `index=True` | `ix_shared_list_guest_aliases_account_user_id` |

Its docstring says three things:

- the alias is a credential, not data about a person, so it is left out of the Art. 15
  export, like the nonce;
- `user_id` has no FK because that user row is deleted by the merge;
- `anonymise` deletes the account's aliases.

**`app/models/booking.py`**, next to `shared_list_id` (l. 64-71):

```python
# List guests only (D12, as amended by V7): this sign-up's own person. Whether its
# form said the first name appears on shared lists that show first names, and the
# name and phone the chain stored when it signed up. Member bookings: false, NULL,
# NULL; their person is the user. Cleared by logic/shared_lists/erase.anonymise.
show_first_name: bool = Field(
    default=False,
    sa_column=sa.Column(sa.Boolean, nullable=False, server_default=sa.text("false")),
)
guest_name: str | None = Field(
    default=None, sa_column=sa.Column(sa.String, nullable=True)
)
guest_phone: str | None = Field(
    default=None, sa_column=sa.Column(sa.String, nullable=True)
)
```

**`app/models/__init__.py`**: import `SharedListGuestAlias`.

**Migration `20261110_0001_shared_lists.py`**, amended in place. The revision id and the
`down_revision` stay.

- Step 2: after `bookings.shared_list_id` (l. 68), add `show_first_name`
  (`sa.Boolean()`, `nullable=False`, `server_default=sa.text("false")`), `guest_name`
  and `guest_phone` (`sa.String()`, nullable). A constant default and nullable columns
  add no table rewrite on Postgres 11 or later.
- Step 7: in `create_table("shared_list_guests", …)`, drop the `show_first_name` column
  (l. 204-209) and add `confirmed_at`. After the email index, create
  `uq_shared_list_guests_account` with `unique=True` and
  `postgresql_where=sa.text("confirmed_at IS NOT NULL")`.
- New step 7a, after `shared_list_guests`: `create_table("shared_list_guest_aliases",
  …)` with its id index, the unique `user_id` index and the `account_user_id` index.
- Downgrade: the reverse, written so that it also runs on a database that ran the
  **old** `20261110_0001`:
  - `op.execute("DROP TABLE IF EXISTS shared_list_guest_aliases")`; its indexes go with
    it;
  - `uq_shared_list_guests_account` goes with `shared_list_guests`, with no separate
    `drop_index`;
  - `op.execute("ALTER TABLE bookings DROP COLUMN IF EXISTS show_first_name, DROP
    COLUMN IF EXISTS guest_name, DROP COLUMN IF EXISTS guest_phone")`, before
    `shared_list_id` is dropped.
- Docstring: one paragraph each on accounts, aliases and the per-booking person.

**Databases that already ran the old `20261110_0001`.** Test databases need nothing:
the suite drops and recreates its database every session
(`tests/fixtures/database.py:61-73`). A **dev** database at the old head goes down and
up once:

```
uv run --directory backend alembic downgrade 20261104_0004
just migrate
```

The downgrade runs the file on disk, which is the amended one. Its `IF EXISTS` drops
make it work on the old schema too. Without them it would fail on the objects the old
schema never had. The fallbacks are to run the downgrade before the amended file is in
place (before pulling the change), or to reset the dev database volume.

`just check-migrations` is `alembic upgrade head && alembic check` (justfile:124-125).
On a database left at the old head, the upgrade is a no-op and `check` reports the
model drift. That is the signal to run the two commands above.

No new settings. `GUEST_DATA_RETENTION_DAYS` (`config.py:301`) is now also returned by
the API.

---

## 4. Algorithms

### 4.1 Earning

`settle_earnings` and `_voucher_shifts` as in V1. Their docstrings, and the module
docstring of `app/logic/vouchers.py` (l. 40-42), say:

> Guests who signed up through a shared list earn like everyone else. Their
> earnings belong to their guest user, which a confirmation may merge into the guest
> account of their address (`logic/shared_lists/guest_account.py`).

`SharedListCandidate.earns_vouchers`'s comment (`app/schemas/shared_list.py:238-239`)
becomes "The wizard says that guests earn them too."

### 4.2 Confirm, promote and merge: new `app/logic/shared_lists/guest_account.py`

**Step 1 runs in the route**, so the rate limits can tell a miss from a hit (§5):

1. **Verify the token before any lock.** `peeked = await guest_tokens.peek(session,
   token)` parses the user id (the current `_user_id`, l. 86-93) and reads the guest
   row, or the alias, without a lock. It then compares the token with
   `hmac.compare_digest` against the mail key and the response key over that row's (or
   alias's) nonce. It returns a `Peeked` (the row or alias, and which key matched) only
   for a verified match, else None. Then:
   - None → the IP bucket for misses, then 404 `guest_signup.not_found`. That covers a
     forged tag, no row or alias, and an erased row (no nonce).
   - Otherwise the per-guest bucket, then `guest_account.confirm(session,
     peeked=peeked, token=token, now=clock.utc_now())`.

```python
async def confirm(session, *, peeked: Peeked, token: str, now: dt.datetime) -> GuestKey
```

`now` is naive UTC. It returns the account's key (`from_mail=True`), and the route
answers with `mail_token(key.guest)`. Before any lock:

- mail key, alias → `resolve()`. If it resolves to an account → return it (idempotent:
  merged already). Otherwise 404.
- mail key, guest row with `confirmed_at` set → `resolve()` and return it (idempotent).
- response key, unconfirmed chain → 403 `guest_signup.mail_link_required`.
- response key, account or alias → 404 `guest_signup.not_found` (retired, V4).
- mail key, unconfirmed chain **without** `email` → 404. Lists with `ask_email='off'`
  store no address (`signup.py:232`), and `address_hash` needs a string
  (`guest_tokens.py:117-121`). Such a chain never reaches step 3.
- mail key, unconfirmed chain with `email` → carry on with that chain.

Then, in order:

2. **The event first.** `crud_event.lock(session, chain.event_id, mode="key_share")`
   (`app/crud/event.py:33`). This is the sign-up's reason: a promotion changes the
   account set of the event, and deleting the event takes the event row before the
   guest rows its CASCADE reaches. None → 404.
3. **The address's account lock.** `guest_quota.lock_account(session, event_id,
   address_hash(chain.email))`, an advisory xact lock
   `guest-account:{event_id}:{address_hash}`. Only confirm, and later the claim, takes
   it, always before any guest row (§4.7). It serialises the creation of the one
   account per address.
4. **Find the account.** `crud_shared_list_guest.find_account(session, event_id=…,
   email=…)`, without a lock: `event_id = :event_id AND confirmed_at IS NOT NULL AND
   erased_at IS NULL AND lower(email) = :email`, served by
   `uq_shared_list_guests_account`. The same address at another event is another
   account. It may return the chain itself, when a concurrent confirm of the same link
   promoted it after step 1.
5. **Lock the rows in one ordered statement.**
   `crud_shared_list_guest.lock_many(session, user_ids={chain.user_id} |
   ({account.user_id} if account else set()))`, deduplicated, which is `ORDER BY
   user_id FOR UPDATE` with `populate_existing`, the same shape as
   `removal._lock_guests` (l. 91-106).
6. **Verify again under the lock.** `key = await guest_tokens.resolve(session, token)`.
   It re-locks rows already held, so it does not wait.
   - None → 404 `guest_signup.not_found`. The chain was erased or swept in between.
   - `not key.from_mail` → 403 `guest_signup.mail_link_required`. Unreachable after
     step 1; it stays as the check of record.
   - `key.guest.confirmed_at` set → return key. A concurrent confirm of the same link
     won: it promoted the chain, or it merged it and the alias resolved to the account.
7. **Re-check the account**, refreshed by step 5: still `confirmed_at` set, `erased_at`
   None, the same event and the same `lower(email)`? An erase does not take the
   account lock, so it can win the race between steps 4 and 5. If the account is no
   longer valid, carry on as if there were none.
8. **No account: promote the chain.**
   - `chain.confirmed_at = now`.
   - `crud_voucher.delete_unused_passes(session, user_ids=[chain.user_id])`, which is
     `DELETE FROM voucher_passes WHERE user_id IN (:ids) AND used_at IS NULL`. It is the
     statement `anonymise` also uses (§4.6). A code shown from the response token dies
     with that token.
   - Flush inside a savepoint. `uq_shared_list_guests_account` is the backstop and is
     unreachable under the step-3 lock. An `IntegrityError` there is re-raised unmapped
     (the `issue_pass` precedent, `crud/voucher.py:297`).
   - Return `GuestKey(guest=chain, from_mail=True)`. Nothing moves, so there is no
     ledger lock, no `users` row lock and no alias.
9. **An account: merge the chain into it.**
   1. **Ledger locks.** `events = await guest_vouchers.ledger_event_ids(session,
      user_id=chain.user_id)` (§4.4): every event in which `appears_in_event` can
      hold for the chain, plus the events of its passes. For each `(event_id,
      user_id)` in `sorted(product(events, {chain.user_id, account.user_id}),
      key=str)`, call `crud_voucher.lock_ledger(session, event_id=…, user_id=…)`.
      - A redemption of the chain's code holds `vouchers:{event}:{chain}` until it
        commits. The merge waits for it, so the new entry moves too.
      - A correction for the chain holds the same lock. The correction route admits
        any event in which the chain has a confirmed booking, even on a task without
        Marken (`routes/vouchers.py:647-651`), so `ledger_event_ids` covers those
        events too. The correction lands before the merge, or answers 404 after it.
   2. **The chain's `users` row.** `crud_shared_list_guest.lock_guest_user(session,
      user_id=chain.user_id)`, which is `SELECT id FROM users WHERE id = :chain AND
      is_list_guest FOR UPDATE`.
      - Every insert of a row keyed by the chain takes `FOR KEY SHARE` on this row for
        its foreign key: an earning by `settle_earnings`, a correction, a redemption,
        a pass. A writer that has already inserted commits before the merge goes on,
        and the moves of step 3 see its row. A writer that comes later blocks on the
        row, and fails its foreign key once step 6 has deleted the user. That is an
        error the organiser retries, never a row that step 6's CASCADE deletes behind
        everyone's back.
      - `settle_earnings` takes no lock by design (`vouchers.py:46-50`, l. 241-243), and
        `voucher_earnings.booking_id` has no foreign key (`models/voucher.py:156-160`).
        So this row is the only thing that orders a settle against the merge. Without
        it, an organiser lowering a rate during a merge would insert the chain's frozen
        earning after step 3 moved the others, the CASCADE of step 6 would delete it,
        and the booking would then derive at the new rate. That breaks "earned is
        earned".
      - Only after the ledger locks: a redemption that holds the chain's ledger lock
        inserts its entry under this row's key-share lock, so taking the row first
        would deadlock with it.
   3. `merge_guest(session, source=chain, target_user_id=account.user_id, now=now)`.
   4. `account.last_signup_at = max(account.last_signup_at, chain.last_signup_at)`.
      Name, phone and language stay the account's: the first confirmed chain's.
      Nothing is copied from the chain, because its bookings carry their own name and
      phone (V7).
   5. `session.add(SharedListGuestAlias(user_id=chain.user_id, manage_nonce=chain.
      manage_nonce, account_user_id=account.user_id))`.
   6. `DELETE FROM users WHERE id = :chain AND is_list_guest`. Its `shared_list_guests`
      row, and anything the merge left, go by CASCADE.
   7. Return `GuestKey(guest=account, from_mail=True)`.

```python
async def merge_guest(session, *, source: SharedListGuest, target_user_id: UUID,
                      now: dt.datetime) -> MergeResult   # (moved, dropped, passes_deleted)
```

It takes no locks; the caller holds the guest rows, the ledger locks and the source's
`users` row (step 9). It leaves `guest_activity_log` alone: the log has no user ids,
and booking ids survive. In this fixed order:

1. `crud_voucher.delete_unused_passes(session, user_ids=[source.user_id])`. A code on a
   screen at this moment belongs to whoever held the chain's tokens, and that may be
   someone who only typed the address. Moving it would let that person spend the
   account's pooled Marken for up to `PASS_TTL` plus `PASS_HOLD` (`vouchers.py:95-99`).
   The confirmer's own dialog asks for a new code after its next status call fails.
2. Read `(id, shift_id, status)` of every booking of `source` and `target` whose
   `shift_id IS NOT NULL`. A shift with a row from each is a collision:
   `uq_booking_shift_user`, `app/models/booking.py:18`, covers every status.
3. Resolve each collision:

   | source | target | keep | drop |
   |---|---|---|---|
   | cancelled | confirmed | target's | source's |
   | confirmed | cancelled | source's (it moves) | target's |
   | cancelled | cancelled | target's | source's |
   | confirmed | confirmed | target's | source's, see below |

   - Confirmed on both sides cannot arise. D3 refuses the same address twice on one
     shift under the shift lock (`signup._refuse_if_taken`, l. 150-163), and merged
     chains share the address. The merge still handles it defensively:
     `vouchers.settle_earnings(session, now=clock.wall_clock_now(zone),
     shift_ids=[…])` per zone first, so an ended shift's earning row survives the
     dropped booking. Step 7 re-points that row to the target, because earned is
     earned. Then `logger.warning` without an address.
4. `DELETE FROM bookings WHERE id IN (:drops)`. Their reminders go by the
   `booking_reminders.booking_id` CASCADE.
5. `UPDATE bookings SET user_id = :target WHERE user_id = :source`. The ids stay, so
   `shared_list_id`, `show_first_name`, `guest_name`, `guest_phone`, the D17 log rows
   and the earning rows stay attached.
6. `crud_reminder.reassign_user(session, from_user=source, to_user=target)`, a new method
   that runs `UPDATE booking_reminders SET user_id = :target WHERE user_id = :source`.
   - Each booking keeps its own reminder. The guest switch on the manage page still
     rewrites them all through `replace_for_booking` (`guest_manage.set_reminders`,
     l. 176-215).
   - The merge does not rewrite them through `replace_for_booking`: no offset changes,
     and `uq_reminder_booking_offset` is per booking.
   - The claim will call `replace_for_booking` with the account's defaults (V12).
7. `crud_voucher.reassign_user(session, from_user=source, to_user=target)`, a new method
   with three statements: `UPDATE voucher_earnings | voucher_entries | voucher_passes SET
   user_id = :target WHERE user_id = :source`. Step 1 left only used passes; they move
   for the history ("eingelöst" on a status call, the stand's records).
8. Return the counts.

**Sign-up continuation after a confirmation** (`signup._chain`, l. 96-106):

- If `resolve()` gives a live **unconfirmed** chain of this list → continue it, as
  today.
- Otherwise, if `guest_tokens.retired_response_token(session, token)` (§4.3), or the
  token resolves to an account → `return None`, which starts a new chain from the
  typed fields.
- Otherwise 403 `shared_list.guest_token_invalid`, as today.

This keeps "Noch eine Schicht eintragen" working in a tab whose chain was confirmed
meanwhile, promoted or merged, without a second Turnstile challenge.

### 4.3 `guest_tokens.resolve` after this change

`resolve(session, token) -> GuestKey | None`:

1. `uid = _user_id(token)`; None → None.
2. `guest = crud_guest.get_for_update(uid)`. If it exists and has a nonce:
   - mail-key match → `GuestKey(guest, from_mail=True)`;
   - response-key match **and** `guest.confirmed_at is None` → `GuestKey(guest,
     from_mail=False)`;
   - anything else → None.
3. Otherwise `alias = crud_guest.get_alias(uid)`. If the token matches the mail key over
   `(uid, alias.manage_nonce)`, take `account = get_for_update(alias.account_user_id)`.
   If the account exists, has a nonce and is not erased → `GuestKey(account,
   from_mail=True)`.
4. Otherwise None.

`retired_response_token(session, token) -> bool` is true when the token matches the
**response** key over a guest row with `confirmed_at` set (a promoted chain) or over an
alias's `(user_id, manage_nonce)` (a merged chain). `peek(session, token) -> Peeked |
None` is step 1 plus unlocked reads, and it verifies the tag against both keys before
it returns anything (§4.2 step 1); it never hands back an unverified row. All of them
compare with `hmac.compare_digest`, as now. The alias branch locks only the account
row, so the lock order stays "guest rows before anything else but `guest-account`".

### 4.4 Guest vouchers: new `app/logic/shared_lists/guest_vouchers.py`

- `voucher_event_ids(session, *, user_id) -> list[UUID]` returns the events in which the
  guest has, or will have, Marken. It drives the manage page's vouchers cards and the
  code gate. One `UNION` of:
  - `Task.event_id` of confirmed bookings on tasks with `vouchers_per_shift > 0` and
    `Task.event_id IS NOT NULL`;
  - `VoucherEarning.event_id` with `amount > 0`;
  - `VoucherEntry.event_id`;
  - `VoucherPass.event_id` with `used_at IS NULL`.

  Usually there is one event. A task moved to another event makes two: what it earns
  there is still earned.
- `ledger_event_ids(session, *, user_id) -> list[UUID]` is the merge's lock set (§4.2
  step 9.1). It is wider on purpose: `Task.event_id` of confirmed bookings on **any**
  task (as `appears_in_event`, which counts bookings without Marken), and every
  `VoucherEarning.event_id`, `VoucherEntry.event_id` and `VoucherPass.event_id`. A
  correction is allowed wherever `appears_in_event` holds, so the merge must hold that
  event's ledger lock too. `voucher_event_ids` stays narrow, so a guest with no Marken
  sees no empty vouchers card.
- `guest_vouchers(session, *, user_id, own_event_id: UUID | None) ->
  list[GuestVoucherAccount]` loads the user and the events of `voucher_event_ids`. It
  takes a user id, because a guest whose event was deleted has no guest row but may
  still have Marken (the Art. 15 export, §5). `own_event_id` comes first, then the
  others by `start_date`. Per event:
  - `vouchers.account(session, event_id, user, now=clock.wall_clock_now(event.timezone))`
    (`vouchers.py:518`);
  - every entry's `actor_name` and `note` set to None, because a guest page shows no
    member's name and no organiser free text (the D13 rule for guest content);
  - `summary.email` set to None.
- `issue_pass(session, *, guest, event_id, now_utc) -> VoucherPassRead`:
  - `event_id not in voucher_event_ids(...)` → 404 `guest_signup.not_found`. One
    answer for every failure, as for tokens;
  - otherwise `vouchers.issue_pass(session, event_id=…, user_id=guest.user_id,
    now=now_utc)` (l. 578), mapped exactly as `issue_my_pass` maps it
    (`routes/vouchers.py:132-139`). No ledger lock, as for members.
- `pass_status(session, *, guest, event_id, pass_id) -> VoucherPassStatus`:
  `vouchers.pass_status(…)` (l. 597) with the event's clock. 404
  `voucher.pass_not_found` once the pass was replaced or deleted. `VoucherCodeDialog`
  already treats that as "ask again".

Codes for guests keep all the member rules:

- 6 characters from `CODE_ALPHABET`, QR `WV1:` + code;
- `PASS_TTL` 120 s, `PASS_HOLD` 60 s;
- unique across the installation;
- issuing deletes the guest's other unused, unheld passes in that event.

### 4.5 Redeeming

In `app/logic/vouchers.py`:

- **Move** `_appears_in_event` from `app/api/routes/vouchers.py:629-652` to
  `vouchers.appears_in_event(session, *, event_id, user_id) -> bool`, unchanged
  (membership, entries, earnings, confirmed bookings). The route calls it, so
  corrections, `get_voucher_account` and the new guest branch share one rule.
- **Replace** `_member_or_404` (l. 653-664) with:

  ```python
  async def _holder_or_404(session, *, event_id, user_id, allow_guest: bool) -> User:
      if await crud_membership.get(session, user_id=user_id, event_id=event_id):
          user = await session.get(User, user_id); assert user; return user
      if allow_guest:
          user = await session.get(User, user_id)
          guest = await crud_shared_list_guest.get_by_user_id(session, user_id=user_id)
          if (user is not None and user.is_list_guest and guest is not None
                  and guest.manage_nonce is not None
                  and await appears_in_event(session, event_id=event_id, user_id=user_id)):
              return user
      raise_problem(404, code="event.member_not_found", …)   # today's answer
  ```

  The guest row is read without a lock, so a redemption never waits for a guest row
  (§4.7).
- `check` (l. 695): `allow_guest=code is not None`. Add `is_guest=volunteer.
  is_list_guest` to `VoucherCheckResult`. After `hold_pass` (l. 722), read the pass
  again: `fresh = await crud_voucher.reload_pass(…)`. None → 404
  `voucher.code_invalid`; `fresh.user_id != volunteer.id` → 409 `voucher.code_expired`.
  - `check` takes no ledger lock (l. 695-728), and `hold_pass` has no user filter
    (`crud/voucher.py:365-394`).
  - A check that read the chain's pass before a confirmation committed waits in
    `hold_pass` on the confirmation's `DELETE`. Without the re-read it would then
    answer with the deleted chain's id and name and `available` 0.
- `redeem` (l. 766): `allow_guest=code is not None`.
  - After `fresh = await crud_voucher.reload_pass(…)` (l. 813-818), add: `if
    fresh.user_id != volunteer.id: raise_problem(409, code="voucher.code_expired", …)`.
    This is defence in depth. A confirmation deletes unused passes rather than moving
    them, so a pass the redemption is about to use is either gone (`fresh` is None →
    the existing 404 `voucher.code_invalid`) or still the volunteer's.
  - A promotion takes no ledger lock. A redemption racing it either used the pass
    first (the `DELETE` skips used passes) or finds it gone: 404, or 409
    `voucher.code_used` if it was already waiting in `consume_pass`. The guest shows
    a new code.
- `_Tally.summary` (l. 199) sets `is_guest=user.is_list_guest`. `balances` (l. 540)
  fills `email` for guest rows from `crud_shared_list_guest.contact_emails` with one
  query.
- `require_voucher_redeemer` (`permissions.py:639`) is unchanged: it gates the
  *redeemer*, who is always a member or an organiser. A guest on shift at a point
  cannot redeem for others, because a guest has no account.

`app/logic/vouchers.py` may import `app.crud.shared_list_guest`, which is plain CRUD. It
still must not import `app.logic.permissions`.

### 4.6 Erase, "Das war ich nicht", retention, removal

`app/logic/shared_lists/erase.py`:

- `anonymise` (l. 56-75) also runs, for the same user ids:
  - `UPDATE bookings SET guest_name = NULL, guest_phone = NULL WHERE user_id IN (:ids)`.
    These are the kept, worked bookings; `erase_guests` deleted the rest. A booking
    without a name is never named, so `show_first_name` may stay.
  - `DELETE FROM shared_list_guest_aliases WHERE account_user_id IN (:ids)`. The
    account's old chain links die with it.
  - `crud_voucher.delete_unused_passes(session, user_ids=ids)`. A code on a screen
    stops working. Used passes stay for the history.
  - `UPDATE voucher_entries SET note = NULL WHERE user_id IN (:ids) AND kind =
    'adjustment'`. A correction's note is required free text (`models/voucher.py:80-81`),
    and the natural one names the person ("für Tom M., Handy leer"). The amount stays,
    so the books still add up. `VoucherHistory` already renders an adjustment without
    a note (`VoucherHistory.vue:187`). Redemptions carry no note.
- `erase_guests` (l. 78-127) computes `keeping` from bookings, as now, plus every user
  with a `voucher_entries` row or a `voucher_earnings` row with `amount > 0` (one
  `EXISTS` query). Those users are anonymised, not deleted (V9).

`app/logic/shared_lists/retention.py`:

- `_due_guests` (l. 43-80) also counts a guest as still holding something while one of
  its bookings has a `guest_name` or a `guest_phone`.
- `sweep_guest_data` step 2 (l. 106-115) adds `~exists(VoucherEntry.user_id ==
  User.id)` and `~exists(VoucherEarning.user_id == User.id, VoucherEarning.amount > 0)`
  to the delete. Step 1 already anonymises through `anonymise`, so snapshots, aliases,
  unused passes and correction notes go there.
- New `async def erase_on(session, *, user_id, retention_days) -> dt.date` returns
  `last_day + retention_days + 1`, the first day `_due_guests` counts the guest as due.
  `last_day` is the coalesce expression of `_due_guests`, moved into a helper
  `_last_day()` so both use one rule.

`public_shared_lists.reject_guest_signup` (l. 173-191), after the `from_mail` check:

- `if key.guest.confirmed_at is not None: raise_problem(409,
  code="guest_signup.reject_confirmed", detail="You confirmed these sign-ups yourself")`;
- suppress the address only when `not await crud_shared_list_guest.has_live_account(
  session, email=key.guest.email)`. That query is `confirmed_at IS NOT NULL AND
  erased_at IS NULL AND lower(email) = :email`, at **any** event, because the
  suppression is global (V9). It is served by `ix_shared_list_guests_email_lower`.
- Then erase the chain, as today.

`guest_manage.manage_view` sets `reject_suppresses` from the same query.

`erase_guest_data` (l. 163-169) is unchanged. On an account token it erases the
account, and nothing else (V9).

`app/logic/shared_lists/removal.py`, `remove_signups` (l. 109-…): after the second read
(l. 134-146), skip every booking whose booker is not in `guests` with
`shared_list.signup_not_found`. The organiser retries, and the retry locks the right
row.

- `_lock_guests` locks the guest rows of the bookings' users as its statement saw them
  (l. 91-106). If it waited on a chain row and a merge then committed, the chain row is
  gone, `guests` lacks the account, and the second read sees the account as the
  booker.
- Going on would cancel without the account's row lock. With `erase=true` it would call
  `erase_guests` on the whole account (l. 197-199) without the lock that
  `erase.py:83-84` requires. A second confirm merging another chain into the same
  account at that moment could then leave that chain's future bookings confirmed under
  a nameless account with no manage link.

### 4.7 Lock order: the main plan's §4.5 table, completed

New rows are marked ★. Three rules hold throughout:

- guest rows are locked before advisory locks, with one exception:
  `guest-account:{event_id}:{hash}`. Only confirm and the claim take it, right after
  the event row and before any guest row;
- several guest rows are locked in one statement, in user-id order;
- a merge locks the chain's `users` row last, after every ledger lock it takes.

| Path | Locks, in order |
|---|---|
| Guest sign-up | event row `FOR KEY SHARE` → list row `FOR KEY SHARE` → chain's guest row `FOR UPDATE` (chains only) → `guest-address:{hash}` → `shared-list-day:{list_id}` → shift lock |
| Member booking | membership `FOR KEY SHARE` → shift lock |
| ★ Guest confirm, promote | event row `FOR KEY SHARE` → `guest-account:{event_id}:{hash}` → chain's guest row `FOR UPDATE` → the chain's unused pass rows (its `DELETE`). No ledger lock, no shift lock |
| ★ Guest confirm, merge | event row `FOR KEY SHARE` → `guest-account:{event_id}:{hash}` → chain's and account's guest rows `FOR UPDATE`, one statement in user-id order → `vouchers:{event}:{user}` for each event of `ledger_event_ids(chain)` × {chain, account}, sorted → the chain's `users` row `FOR UPDATE` → the rows the moves touch (passes, bookings, reminders, earnings, entries). No shift lock: a merge only moves or frees places |
| ★ Claim (deferred) | `guest-account:{event_id}:{hash}` per event, sorted → guest rows `FOR UPDATE`, sorted by id → as the main plan's claim row (V12) |
| Guest manage (read, cancel, reminders, erase) | guest row `FOR UPDATE` (an alias resolves to its account's row) |
| "Das war ich nicht" (chains only) | guest row `FOR UPDATE` → `guest-address:{hash}` (only when it suppresses) |
| ★ Guest code: issue or status | guest row `FOR UPDATE` (resolve) → the user's `users` row `FOR KEY SHARE` when issuing (the pass insert). Issuing takes no ledger lock, as for members |
| Redeem (member at a stand) | `vouchers:{event}:{holder}` → the pass row (`consume_pass`) → the holder's `users` row `FOR KEY SHARE` (the entry insert). The guest-row read in `_holder_or_404` takes no lock |
| Check (member at a stand) | no ledger lock: the pass row (`hold_pass`) only |
| Correction (event admin) | `vouchers:{event}:{user}` → the user's `users` row `FOR KEY SHARE` (the entry insert) |
| Settling (`settle_earnings`, inside organiser changes) | no lock of its own; each earning insert takes its user's `users` row `FOR KEY SHARE` |
| Organiser removal | guest rows `FOR UPDATE`, one statement in id order → `guest-address:{hash}` per mail, in hash order |
| Patch / pause / resume / end / rotate | event row `FOR SHARE` → list rows `FOR UPDATE` in id order |
| Pause-all | event row `FOR NO KEY UPDATE` → list rows `FOR UPDATE` in id order |
| Deleting the event (existing) | event row `FOR UPDATE` → list and guest rows by CASCADE |
| Guest mail (background) | `guest-address:{hash}` only, in its own transaction |

Why there is no cycle:

- The account lock is taken only by confirm and the claim, as the first waitable lock
  after the event row. Nobody holding a guest row ever waits for it.
- The only multi-row lockers (confirm, removal, the claim) sort.
- Ledger holders (redeem, correction) never wait for a guest row. They may wait for a
  chain's `users` row. A merge takes that row only after it holds every ledger lock it
  needs, so a ledger holder never waits for a merge that waits for it.
- A settling organiser holds nothing the merge needs before the `users` row. The
  merge touches bookings and reminders only after it holds that row. The settle either
  inserted first, and its transaction runs to its commit while the merge waits, or it
  blocks on the row before it touches anything of the chain's (the routes settle
  before they change anything).
- Paths that hold a guest row and then wait for `guest-address` (sign-up, not-me,
  removal) are never waited for by a confirm holding `guest-address`, because confirm
  does not take it.
- Event delete and confirm both start at the event row.

The retention sweep updates guest rows without ordering, as it does today. A collision
with a confirm is left to Postgres's deadlock detection: one side is aborted and the
sweep runs again within the hour. The same holds for an operator deleting a guest user
by hand (`DELETE /users/{id}`) while that user is being merged. This is documented and
not engineered further.

### 4.8 Races and idempotency

| Race | Outcome |
|---|---|
| Two mail links of the same address confirmed at once (two chains) | the account lock serialises them: the first promotes its chain, and the second merges into it (READ COMMITTED: its statements after the lock see the first's commit). One account. The unique index is never hit |
| The same link pressed twice (double click, two tabs) | both may pass step 1 before either commits. The second waits for the account lock; then `find_account` returns the chain itself (promoted) or its account (merged), and step 6 returns it. Both answer 200 with the same token |
| A code shown from the chain's tokens while the chain is confirmed | promote and merge both delete the chain's unused codes. At the stand that code answers 404 `voucher.code_invalid`, and its status call 404. A tab holding the response token is dead (last row); a tab holding the mail token gets a new code for the account |
| Confirm (merge) vs. a redemption of the chain's code | step 9.1 waits for the redemption's ledger lock; the entry then moves with the rest. A redemption arriving during the merge waits for that lock, then finds its pass deleted: 404 `voucher.code_invalid` |
| Confirm (promote) vs. a redemption of the chain's code | no ledger lock. The redemption either used the pass first (the `DELETE` skips used passes, and its entry stays on the same user) or finds it gone: 404, or 409 `voucher.code_used` if it was already waiting in `consume_pass` |
| Confirm vs. a check of the chain's code | the check's `hold_pass` waits for the confirmation's `DELETE`; the re-read then finds no pass: 404 `voucher.code_invalid` (§4.5) |
| A redemption retried with the same `request_id` after a merge moved its entry | `redeem` finds the used pass under the account, `_holder_or_404` passes, and `_replayed` (`vouchers.py:731-763`) replays the first result, naming the account and its pooled `available`. No second debit. If the account was erased meanwhile, `_holder_or_404` answers 404 first, as for a member who left |
| Confirm (merge) vs. an organiser change that settles earnings (rate change, shift moved or deleted, task deleted or moved, zone change) | an earning inserted before step 9.2 commits first and moves with the rest. One inserted after waits on the chain's `users` row and fails its foreign key after the merge; the organiser retries. Never deleted by step 9.6's CASCADE |
| Confirm (merge) vs. a correction | the correction's ledger lock is in step 9.1's set, so it lands before the merge and moves, or answers 404 after it |
| Confirm vs. "Noch eine Schicht" with the chain's response token | the sign-up waits on the chain row. Afterwards `resolve()` is None and `retired_response_token()` is true, so a new chain starts |
| Confirm vs. organiser removal of the chain's booking | both sort their row locks, so one waits. Promote: the row survives; the removal locks it and goes on as before. Merge: a removal that waited on the chain row finds the row gone and the booking under the account. It skips the booking with `shared_list.signup_not_found` (§4.6), and the organiser retries. With `erase=true` this also keeps it from erasing the whole account without its lock |
| Confirm vs. deleting the event | both start at the event row; the confirm 404s or the delete waits |
| Confirm vs. erasing the account | the erase does not take the account lock. Step 7 sees the erased row and promotes the confirming chain, which the partial index allows (the erased row's email is NULL) |
| Confirm vs. the reminder poller | the poller's reminder row update and the merge's `reassign_user` serialise on the row. A mail built before the merge links the chain's mail token, which the alias resolves to the account |
| A guest screen holding the chain's response token (the done page, a `/guest-signup#<response token>` tab) | it dies at the confirmation, promoted or merged: `resolve()` returns None, so `/manage`, issuing a code and its status answer 404 `guest_signup.not_found`. The code dialog switches to a final state, "Dieser Link funktioniert nicht mehr …" (§7.1), and stops polling, so a dead tab does not drain the IP bucket for misses |

Side effects only by POST from the page: the only writing endpoints are POSTs sent by
buttons (confirm, cancel, reminders, erase, not-me, code). `/manage` stays read-only.

---

## 5. API changes

All new routes live in `app/api/routes/public_shared_lists.py`. They have no identity
dependency and no kill switch, like every `/guest-signups/*` route (fixer finding 8).

| Method and path | Function (operation id `public-shared-lists-<name>`) | Body → response | Limits, after `guest_ip_limiter(ip)` |
|---|---|---|---|
| POST `/public/guest-signups/confirm` | `confirm_guest_address` | `GuestTokenRequest` → 200 `GuestConfirmResult` | miss: `guest_link_miss_limiter(ip)`; hit: `guest_manage_limiter("guest:<user id>")` |
| POST `/public/guest-signups/vouchers/pass` | `issue_guest_voucher_pass` | `GuestPassRequest` → 201 `VoucherPassRead` | miss: `guest_link_miss_limiter(ip)`; hit: `voucher_pass_limiter("guest:<user id>")` (20/min, `rate_limit.py:196`) |
| POST `/public/guest-signups/vouchers/pass-status` | `read_guest_voucher_pass` | `GuestPassStatusRequest` → 200 `VoucherPassStatus` | miss: `guest_link_miss_limiter(ip)`; hit: `guest_pass_status_limiter("guest:<user id>")` |

**Rate limits for every `/guest-signups/*` route.** The IP-keyed
`guest_manage_limiter` (30 per 10 minutes, `rate_limit.py:226-230`) cannot serve a
stand. `VoucherCodeDialog` polls every 2 s (`POLL_MS`, `VoucherCodeDialog.vue:50`),
for the code shown and any it replaced (l. 134-144). That is 300 to 600 calls per 10
minutes per open dialog, and the manage page is now the wallet a queue of guests opens
behind one venue NAT. The token is the real key, an HMAC tag nobody guesses. So calls
are counted per guest once the token resolves, and per IP only when it does not:

`_guest()` (l. 121-131) becomes `_guest(request, session, token, *, limiter:
RateLimiter = guest_manage_limiter)`:

1. `guest_ip_limiter.check(ip)`, before any database work: a flood guard only;
2. `key = await guest_tokens.resolve(session, token)`;
3. None → `guest_link_miss_limiter.check(ip)`, then 404 `guest_signup.not_found`;
4. otherwise `limiter.check(f"guest:{key.guest.user_id}")`.

`/manage`, `/cancel`, `/reminders`, `/erase` and `/not-me` keep `guest_manage_limiter`,
now keyed per guest. The code routes pass their own. `/confirm` applies the same
sequence around `guest_tokens.peek` (§4.2 step 1).

**`app/core/rate_limit.py`**, replacing the `guest_manage_limiter` block (l. 226-230):

```python
# Shared-list guests (/public/guest-signups/*). The manage token is the real key:
# an HMAC tag nobody guesses. A call whose token resolves is counted per guest, so
# a queue of guests at a stand behind one venue NAT never shares a bucket; only
# misses are counted per IP.

# 30 per 10 minutes, keyed by "guest:<user id>": reading and changing one's
# sign-ups (/manage, /cancel, /reminders, /erase, /not-me, /confirm). The page
# loads once and reloads after each redemption.
guest_manage_limiter = RateLimiter(
    limit=30, window_seconds=10 * 60, code="guest_signup.rate_limited"
)

# 120 per minute, keyed by "guest:<user id>": the status a guest's code screen asks
# for every two seconds, for the code shown and any it replaced.
guest_pass_status_limiter = RateLimiter(
    limit=120, window_seconds=60, code="guest_signup.rate_limited"
)

# 30 per 10 minutes, keyed by IP, counted only for a token that does not resolve.
# A scan for live tokens meets it at once. A dead link opened again does not, and
# code screens stop asking on a dead link.
guest_link_miss_limiter = RateLimiter(
    limit=30, window_seconds=10 * 60, code="guest_signup.rate_limited"
)

# 6000 per 10 minutes, keyed by IP, on every call before any database work: a flood
# guard only. Ten code screens on one venue NAT ask about five times a second and
# stay well below it.
guest_ip_limiter = RateLimiter(
    limit=6000, window_seconds=10 * 60, code="guest_signup.rate_limited"
)
```

Issuing a code reuses `voucher_pass_limiter` (20 per minute) with the key
`guest:<user id>`. No `guest_voucher_limiter` is added.

Changed routes:

- `/guest-signups/manage`, `/cancel` and `/reminders` return the extended
  `GuestSignupManage`; all five existing `/guest-signups/*` routes switch to the split
  limits above.
- `/not-me` gains the 409 of §4.6, and suppresses only without a live account.
- `/vouchers/check` and `/vouchers/redeem` accept guests by code (§4.5).
- `/vouchers/people` and `/vouchers/check` tag guests (`is_guest`).
- The rosters and lists of V7 show each guest booking's own name and phone. Their
  response shapes do not change.

Test-only, in `app/api/routes/testing.py`, which is registered only under `TESTING`:
POST `/testing/guest-mail-link` (`guest_mail_link`), body `{token}` → `{token:
mail_token(guest)}` for the chain behind a response token. E2E has no mailbox, so this
is how it gets a mail link (§8.2).

**`app/schemas/public_shared_list.py`**

```python
class PublicShift(BaseModel):            # + (l. 47)
    vouchers: int = 0                    # Task.vouchers_per_shift; 0 for none

class PublicSharedList(BaseModel):       # + (l. 78)
    retention_days: int                  # settings.GUEST_DATA_RETENTION_DAYS

class PublicSignupRequest(BaseModel):    # show_names docstring: "stored on this booking"

class GuestSignupBooking(BaseModel):     # + (l. 157)
    vouchers: int = 0                    # what the shift earns (0 for a removed shift)
    show_first_name: bool = False        # this sign-up's consent
    #: The name this sign-up was made under (bookings.guest_name). The page shows it
    #: when it differs from the page's name, after a family's sign-ups were pooled.
    name: str | None = None

class GuestVoucherAccount(BaseModel):    # new
    event_id: uuid.UUID
    event_name: str
    #: VoucherAccount (app/schemas/voucher.py:98) with actor_name and note blanked
    account: VoucherAccount

class GuestSignupManage(BaseModel):      # + (l. 171)
    confirmed: bool                      # this is a guest account (confirmed_at set)
    can_confirm: bool                    # from_mail and not confirmed and email given
    can_reject: bool                     # NOW: from_mail and not confirmed
    #: "Das war ich nicht" also stops all mail to the address: false while the
    #: address has a confirmed account at any event (V9).
    reject_suppresses: bool
    #: A phone number is stored for this guest or one of its sign-ups. With
    #: email, it picks the retention text.
    has_phone: bool
    retention_days: int
    erase_on: dt.date                    # retention.erase_on(): first day the data may go
    vouchers: list[GuestVoucherAccount]  # [] when nothing earns; the own event first

class GuestConfirmResult(BaseModel):     # new
    #: The account's mail token: the page uses it from now on.
    token: str
    manage: GuestSignupManage

class GuestPassRequest(GuestTokenRequest):          # new
    event_id: uuid.UUID
class GuestPassStatusRequest(GuestPassRequest):     # new
    pass_id: uuid.UUID
```

**`app/schemas/voucher.py`**:

- `VoucherBalance.is_guest: bool = False` (l. 73);
- `VoucherCheckResult.is_guest: bool = False` (l. 164).

**`app/schemas/shared_list_guest.py`**, `ListGuestExport` (the operator's Art. 15
export):

- drops `show_first_name`, which is now per booking;
- gains `confirmed_at: dt.datetime | None`;
- gains `vouchers: list[GuestVoucherAccount]`, from `guest_vouchers.guest_vouchers`:
  what the guest earned and redeemed, and the corrections, per event, without member
  names or notes. The privacy text promises that this is stored (§9);
- its `bookings` become `list[ListGuestExportBooking]`, a `GuestSignupBooking` plus
  `phone` (the booking's `guest_phone`). The manage page shows each sign-up's name but
  no phone; the operator's export shows both.

`signups_query.export_guest` (l. 249-268) follows.

**Logic wiring**:

- `public_page.public_shift` (l. 73-89) sets `vouchers=offered.task.vouchers_per_shift`.
  `build_public_list` (l. 99-142) sets `retention_days`.
- `guest_manage.bookings_of` (l. 49-112) adds `Task.vouchers_per_shift`,
  `Booking.show_first_name` and `Booking.guest_name`. `manage_view` (l. 115-129) fills
  the new fields: `guest_vouchers.guest_vouchers`, `retention.erase_on`,
  `has_live_account` for `reject_suppresses`, and `has_phone` from the user and the
  bookings.

**Error codes**

| Code | Status | When |
|---|---|---|
| `guest_signup.reject_confirmed` (new) | 409 | "Das war ich nicht" on a confirmed account |
| `guest_signup.not_found` | 404 | any token failure, including a confirm with a retired response token or a chain without an address; a code for an event the guest has no Marken in |
| `guest_signup.mail_link_required` | 403 | confirm with a live chain's sign-up-response token |
| `guest_signup.rate_limited` | 429 | the guest buckets (per guest, per IP for misses, the IP flood guard) |
| `voucher.rate_limited` | 429 | more than 20 codes a minute for one guest |
| `voucher.pass_not_found` | 404 | the status of a replaced or deleted code |
| `voucher.code_invalid` | 404 | also: a code deleted by a confirmation |
| `voucher.code_expired` | 409 | also: a checked pass that no longer belongs to the volunteer (defence in depth) |
| `shared_list.signup_not_found` | (skip) | also: a removal whose booking changed hands between its lock and its read |
| `event.member_not_found` | 404 | redeeming a guest by hand; a guest by code who is erased or has no part in the event |

Only the first is new. It goes into `src/locales/{en,de}/errorCodes.json`.

---

## 6. Mail changes

`app/logic/shared_lists/guest_mail.py`:

- `GuestShift` (l. 185-192) gains `vouchers: int = 0`, filled by `guest_shift()`
  (l. 326-333) from `task.vouchers_per_shift`. A cancellation built from a snapshot
  keeps 0.
- `GuestMail` (l. 196-208) gains `retention_days: int | None = None` and `has_phone:
  bool = False`. Only `signup.sign_up` sets them, for the confirmation (l. 353-362):
  `settings.GUEST_DATA_RETENTION_DAYS`, and whether the chain stored a phone.
- `GuestMail.name` is the booking's `guest_name` for mails about bookings (V7).
- `render()` (l. 231-295) adds paragraphs between the details table and `manage`:
  - for `confirmation` and `reminder` with one shift and `vouchers > 0`:
    `vouchers_{one|other}` and then `redeem`;
  - for `confirmation`: `confirm_hint`, then `retention` (or `retention_phone` with
    `has_phone`), then `retention_vouchers` if the shift earns.
- It adds, for **every** kind, small print after the button, next to `not_me`:
  `link_private_vouchers` when a shift in the mail earns, else `link_private`.

  All of it goes into both the text and the HTML (`paragraphs_html`,
  `small_print_html`). Every value is escaped as now. No organiser free text is added:
  the voucher count is a number from the task.

New `_STRINGS` keys:

| Key | en | de |
|---|---|---|
| `vouchers_one` | This shift earns {count} voucher once it is over. | Für diese Schicht bekommst du {count} Marke, sobald sie vorbei ist. |
| `vouchers_other` | This shift earns {count} vouchers once it is over. | Für diese Schicht bekommst du {count} Marken, sobald sie vorbei ist. |
| `redeem` | To redeem vouchers at a stand, open your sign-ups with the button below and tap “Show code”. | Einlösen kannst du Marken an den Ständen: Öffne über den Button deine Eintragungen und tipp auf „Code zeigen“. |
| `confirm_hint` | On that page you can also confirm that this is your address. Every sign-up you confirm with it for “{event}” is then shown on one page, and your vouchers are added up. | Dort kannst du auch bestätigen, dass das deine Adresse ist. Dann stehen alle Eintragungen, die du mit dieser Adresse bei „{event}“ bestätigst, auf einer Seite, und deine Marken werden zusammengezählt. |
| `retention` | We delete your name and email address {days} days after your last shift. | Wir löschen deinen Namen und deine E-Mail-Adresse {days} Tage nach deiner letzten Schicht. |
| `retention_phone` | We delete your name, email address and phone number {days} days after your last shift. | Wir löschen deinen Namen, deine E-Mail-Adresse und deine Telefonnummer {days} Tage nach deiner letzten Schicht. |
| `retention_vouchers` | Vouchers you have not redeemed by then expire. | Marken, die du bis dahin nicht eingelöst hast, verfallen dann. |
| `link_private` | Anyone with this link can change your sign-ups, so please do not forward this mail. | Wer diesen Link hat, kann deine Eintragungen ändern. Leite die Mail deshalb nicht weiter. |
| `link_private_vouchers` | Anyone with this link can change your sign-ups and redeem your vouchers, so please do not forward this mail. | Wer diesen Link hat, kann deine Eintragungen ändern und deine Marken einlösen. Leite die Mail deshalb nicht weiter. |

The subject, the button label (`cta`) and `not_me` are unchanged. The confirm itself
sends no mail and writes no `guest_activity_log` row.

---

## 7. Frontend changes

The guest views and stores are WP8's, the wizard is WP7's and the management page is
WP6's, all per §7.3-§7.5 of the main plan. Most of those files do not exist yet, apart
from the WP5 stubs `src/views/guest/GuestSignupManageView.vue`,
`SharedListPublicView.vue` and `src/components/guest/PublicListPreview.vue`. The
frontend package of this plan therefore runs **after** WP6-WP8 have merged and edits
their files (§10). German uses "du" throughout. The privacy page keeps "Sie". No
"admin", no jargon ("Konto" only for real accounts; the guest account is "deine
Eintragungen bei …").

### 7.1 Files

**Shared voucher components** (existing):

- `src/lib/vouchers.ts` (+ `src/lib/__tests__/vouchers.spec.ts`) gains:
  - `export interface VoucherPassSource { issue(): Promise<VoucherPassRead>;
    status(passId: string): Promise<VoucherPassStatus>; goneMessage: string }`;
  - `export class PassSourceGone extends Error`. A source rejects with it when the key
    behind it no longer works.
- `src/components/vouchers/VoucherCodeDialog.vue` gains the prop `source?:
  VoucherPassSource` and makes `eventId` optional.
  - `issue()` (l. 76-99) and `statusOf()` (l. 117-127) call `source.issue()` and
    `source.status(id)` when the prop is given, and the member URLs (l. 82, 120)
    otherwise.
  - A `PassSourceGone` from either call moves the dialog to a final `gone` state. It
    stops the tick and poll timers, hides the code and shows `source.goneMessage`. It
    never retries: a dead link would otherwise poll every two seconds into the IP
    bucket for misses. The member path never raises it.
  - The three member callers (`views/HomeView.vue:299`,
    `views/bookings/MyBookingsView.vue:622`, `views/vouchers/MyVouchersView.vue:206`) do
    not change.
  - New spec `src/components/vouchers/__tests__/VoucherCodeDialog.spec.ts`, with fake
    timers and a fake source: issue, rotation 5 s before expiry, `checking`, `used` →
    emits `redeemed`, `PassSourceGone` → `gone` and no further calls.
- `src/components/vouchers/VoucherRedeemConfirm.vue`: `RedeemSubject` (l. 38-45) gains
  `isGuest: boolean`, shown as a `Badge variant="outline"` next to the name.
  `src/views/vouchers/RedeemVouchersView.vue` (l. 207) fills it from
  `VoucherCheckResult.is_guest`. Spec: `VoucherRedeemConfirm.spec.ts`.
- `src/components/events/EventVouchers.vue` (l. 285-286, 345-346): `v-if="!row.role"`
  shows:
  - `vouchers.admin.guestErased` when `row.is_guest && !row.name`;
  - `vouchers.admin.guest` when `row.is_guest`;
  - else `vouchers.admin.left`.

**WP8 guest files** (edits after WP8):

- `src/stores/guestSignup.ts` (+ spec):
  - `confirm()` POSTs `/public/guest-signups/confirm`, **replaces the in-memory token**
    with `result.token` and sets the manage state;
  - `passSource(eventId): VoucherPassSource` posts `/vouchers/pass` and
    `/vouchers/pass-status` with the current token. It maps 404
    `guest_signup.not_found` to `PassSourceGone`, with `goneMessage` =
    `manage.vouchers.linkGone`. A 404 `voucher.pass_not_found` stays an ordinary failed
    status (ask again);
  - `refresh()` re-POSTs `/manage` after a redemption.

  It uses the anonymous client from `@/client/client.gen`, as WP8's other calls do.
- `src/views/guest/GuestSignupManageView.vue`:
  - mounts the two new cards;
  - the erase confirm text adds the Marken that will expire, and on an account
    `manage.erase.scopeAccount`;
  - the not-me confirm text is the main plan's when `reject_suppresses`, else
    `manage.notMe.keepsMail`;
  - each booking row shows `manage.signedUpAs` when `booking.name` differs from
    `manage.name`.
- `src/components/guest/GuestConfirmCard.vue` (new, + spec), shown when `can_confirm`.
  - Text (`manage.confirm.text`, which says each sign-up keeps its name), then "Ja,
    das bin ich" (primary) and "Das war ich nicht" (`variant="outline"`, the existing
    not-me flow).
  - On success: a toast (`manage.confirm.done`), and the card disappears.
  - When `confirmed`: a small "Adresse bestätigt" line in the header instead.
  - When `!can_confirm && !confirmed && email`: the `fromMailOnly` hint, which is
    worded conditionally, because the confirmation may never have been sent.
- `src/components/guest/GuestVouchersCard.vue` (new, + spec), one per
  `manage.vouchers[i]`:
  - `VoucherBalanceSummary` with `summary` (`src/components/vouchers/
    VoucherBalanceSummary.vue`);
  - "Code zeigen", disabled with `nothingYet` while `available === 0`, which opens
    `VoucherCodeDialog` with `:source="store.passSource(eventId)"`;
  - `howTo`;
  - `VoucherHistory` with `:account="account" with-upcoming`. It renders entries
    without `actor_name` or `note` already (`VoucherHistory.vue:84-88, 187-190`).
- `src/components/guest/PublicShiftList.vue`: a `vouchersBadge` on each shift card when
  `shift.vouchers > 0`.
- `src/views/guest/SharedListPublicView.vue`: the `list.vouchersHint` line under the
  intro when any shift has `vouchers > 0`.
- `src/components/guest/GuestSignupForm.vue`:
  - `form.vouchers` under the shift summary when it earns;
  - the fine print gains the `retention.*` variant picked from the list's `ask_email`
    and `ask_phone` (`name` when both are `off`, `nameEmail`, `namePhone`, `all`),
    plus `retentionVouchers` when it earns, with `{days}` = `list.retention_days`.
- `src/components/guest/GuestSignupDone.vue`:
  - `done.vouchers`;
  - then `done.redeemMail` when `mail_queued`, else `done.redeemLink`;
  - `done.keepLinkVouchers` replaces `done.keepLink` when it earns;
  - `done.linkPrivateVouchers` (when it earns) or `done.linkPrivate` under the manage
    link and under the mail sentence;
  - the retention lines, with the same variant as the form.
- On the manage page:
  - each booking row shows `vouchersBadge` and, when `show_first_name`,
    `manage.firstNamePublic`;
  - the retention line is the `manage.retention.*` variant picked from `email` and
    `has_phone`, plus `manage.retentionVouchers` when `vouchers` is not empty.
- Dates use `formatDateLabel` (`erase_on` is a date), never `formatDate`.

**WP7 wizard** (edit after WP7): `src/components/shared-lists/wizard/
WizardTaskPicker.vue`. The hint on `earns_vouchers` rows switches to
`sharedListWizard.picker.vouchers`.

**WP6 management** (edit after WP6): `src/components/shared-lists/
SharedListRemoveSignupsDialog.vue` puts `sharedLists.remove.eraseVouchers` under the
"Auch die Daten dieser Person löschen" checkbox. The Vorschau tab shows the badges
through `PublicListPreview` → `PublicShiftList` with no further change.

**Privacy** (WP8's file): `src/views/preauth/PrivacyView.vue` + `preauth.privacy.*`,
see §9.

**Generated client**: `just generate-client` after the backend package; never
hand-edited.

### 7.2 Copy

`src/locales/{de,en}/guestSignup.json` (WP8 namespace). Plurals use
`t(key, {n}, n)`. `retention.*` is shared by the form and the done page.

| Key | de | en |
|---|---|---|
| `list.vouchersBadge` | {n} Marke \| {n} Marken | {n} voucher \| {n} vouchers |
| `list.vouchersHint` | Für Schichten mit Marken bekommst du sie, sobald die Schicht vorbei ist, auch ohne Konto. | Shifts with vouchers earn them once the shift is over, also without an account. |
| `form.vouchers` | Für diese Schicht bekommst du {n} Marke, sobald sie vorbei ist. \| Für diese Schicht bekommst du {n} Marken, sobald sie vorbei ist. | This shift earns {n} voucher once it is over. \| This shift earns {n} vouchers once it is over. |
| `retention.name` | Wir löschen deinen Namen {days} Tage nach deiner letzten Schicht. | We delete your name {days} days after your last shift. |
| `retention.nameEmail` | Wir löschen deinen Namen und deine E-Mail-Adresse {days} Tage nach deiner letzten Schicht. | We delete your name and email address {days} days after your last shift. |
| `retention.namePhone` | Wir löschen deinen Namen und deine Telefonnummer {days} Tage nach deiner letzten Schicht. | We delete your name and phone number {days} days after your last shift. |
| `retention.all` | Wir löschen deinen Namen, deine E-Mail-Adresse und deine Telefonnummer {days} Tage nach deiner letzten Schicht. | We delete your name, email address and phone number {days} days after your last shift. |
| `retentionVouchers` | Marken, die du bis dahin nicht eingelöst hast, verfallen dann. | Vouchers you have not redeemed by then expire. |
| `done.vouchers` | = `form.vouchers` | = `form.vouchers` |
| `done.redeemMail` | Einlösen kannst du sie an den Ständen: Öffne den Link aus der Mail und tipp auf „Code zeigen“. | To redeem them at a stand, open the link in the mail and tap “Show code”. |
| `done.redeemLink` | Einlösen kannst du sie an den Ständen: Öffne den Link unten und tipp auf „Code zeigen“. | To redeem them at a stand, open the link below and tap “Show code”. |
| `done.keepLinkVouchers` | Speichere diesen Link. Nur damit kannst du dich wieder austragen und deine Marken einlösen. | Save this link. It is your only way to take your name off again and to redeem your vouchers. |
| `done.linkPrivate` | Wer diesen Link hat, kann deine Eintragungen ändern. Gib ihn nicht weiter. | Anyone with this link can change your sign-ups. Do not pass it on. |
| `done.linkPrivateVouchers` | Wer diesen Link hat, kann deine Eintragungen ändern und deine Marken einlösen. Gib ihn nicht weiter. | Anyone with this link can change your sign-ups and redeem your vouchers. Do not pass it on. |
| `manage.vouchers.title` | Deine Marken | Your vouchers |
| `manage.vouchers.titleEvent` | Deine Marken bei „{event}“ | Your vouchers for “{event}” |
| `manage.vouchers.showCode` | Code zeigen | Show code |
| `manage.vouchers.howTo` | Zeig den Code am Stand. Er gilt zwei Minuten und nur einmal. | Show the code at the stand. It works once, for two minutes. |
| `manage.vouchers.nothingYet` | Sobald eine Schicht mit Marken vorbei ist, kannst du sie hier einlösen. | Once a shift with vouchers is over, you can redeem them here. |
| `manage.vouchers.linkGone` | Dieser Link funktioniert nicht mehr. Hast du eine Mail von uns bekommen, öffne den Link darin. | This link no longer works. If you got a mail from us, open the link in it. |
| `manage.confirm.title` | Ist das deine Adresse? | Is this your address? |
| `manage.confirm.text` | Bestätige {email}. Dann stehen alle Eintragungen, die du mit dieser Adresse bei „{event}“ bestätigst, auf dieser Seite, und deine Marken werden zusammengezählt. Jede Eintragung behält ihren Namen. | Confirm {email}. Every sign-up you confirm with this address for “{event}” is then shown on this page, and your vouchers are added up. Each sign-up keeps its own name. |
| `manage.confirm.yes` | Ja, das bin ich | Yes, that's me |
| `manage.confirm.done` | Bestätigt. Hier stehen jetzt alle Eintragungen, die du für „{event}“ bestätigt hast. | Confirmed. This page now shows every sign-up you confirmed for “{event}”. |
| `manage.confirm.confirmed` | Adresse bestätigt | Address confirmed |
| `manage.confirm.fromMailOnly` | Wenn wir dir eine Mail geschickt haben, kannst du deine Adresse über den Link darin bestätigen. | If we sent you a mail, you can confirm your address through the link in it. |
| `manage.signedUpAs` | Eingetragen als {name} | Signed up as {name} |
| `manage.retention.name` | Am {date} löschen wir deinen Namen, wenn {days} volle Tage seit deiner letzten Schicht vergangen sind. | On {date} we delete your name, once {days} full days have passed since your last shift. |
| `manage.retention.nameEmail` | Am {date} löschen wir deinen Namen und deine E-Mail-Adresse, wenn {days} volle Tage seit deiner letzten Schicht vergangen sind. | On {date} we delete your name and email address, once {days} full days have passed since your last shift. |
| `manage.retention.namePhone` | Am {date} löschen wir deinen Namen und deine Telefonnummer, wenn {days} volle Tage seit deiner letzten Schicht vergangen sind. | On {date} we delete your name and phone number, once {days} full days have passed since your last shift. |
| `manage.retention.all` | Am {date} löschen wir deinen Namen, deine E-Mail-Adresse und deine Telefonnummer, wenn {days} volle Tage seit deiner letzten Schicht vergangen sind. | On {date} we delete your name, email address and phone number, once {days} full days have passed since your last shift. |
| `manage.retentionVouchers` | Marken, die du bis dahin nicht eingelöst hast, verfallen. | Vouchers you have not redeemed by then expire. |
| `manage.erase.vouchersLost` | Deine {n} nicht eingelöste Marke verfällt. \| Deine {n} nicht eingelösten Marken verfallen. | Your {n} unredeemed voucher expires. \| Your {n} unredeemed vouchers expire. |
| `manage.erase.scopeAccount` | Wir löschen die Eintragungen auf dieser Seite. Andere Eintragungen mit dieser Adresse, die du nicht bestätigt hast, löschst du über ihren eigenen Link oder auf Anfrage über die Kontaktadresse in der Datenschutzerklärung. | We delete the sign-ups on this page. Other sign-ups with this address that you did not confirm are deleted through their own link, or on request through the contact in the privacy policy. |
| `manage.notMe.keepsMail` | Wir löschen diese Eintragung. Mails zu deinen bestätigten Eintragungen bekommst du weiter. | We delete this sign-up. You keep getting mail about the sign-ups you confirmed. |
| `manage.firstNamePublic` | Dein Vorname steht bei dieser Schicht auf geteilten Listen. | Your first name is shown for this shift on shared lists. |

Other namespaces:

| File | Key | de | en |
|---|---|---|---|
| `vouchers.json` | `admin.guest` | Ohne Konto | No account |
| `vouchers.json` | `admin.guestErased` | Gast (gelöscht) | Guest (deleted) |
| `vouchers.json` | `redeem.guest` | ohne Konto | no account |
| `errorCodes.json` | `guest_signup.reject_confirmed` | Diese Eintragungen hast du selbst bestätigt. Du kannst dich austragen oder deine Daten löschen. | You confirmed these sign-ups yourself. You can take your name off or delete your data. |
| `sharedListWizard.json` | `picker.vouchers` (replaces the "keine Marken" hint) | Gibt Marken, auch für alle ohne Konto. | Earns vouchers, also for people without an account. |
| `sharedLists.json` | `remove.eraseVouchers` | Nicht eingelöste Marken verfallen dann. | Unredeemed vouchers expire with it. |

---

## 8. Tests

### 8.1 Backend (one file at a time locally; the full suite with `just test-backend`)

**Earning and redeeming**:

`tests/logic/test_vouchers.py`, class `TestListGuests` (l. 646-…). Rewrite its
docstring and both tests, and add more:

- `test_an_ended_guest_booking_earns_the_rate` (derived);
- `test_a_guest_booking_is_settled_at_the_rate` (`settle_earnings` writes
  `vouchers_per_shift`);
- `test_a_guest_shows_in_the_overview_tagged_with_their_address` (`balances`:
  `is_guest`, the contact email);
- `test_the_redeem_picker_never_lists_a_guest` (`available_for_members`);
- `test_check_by_code_names_a_guest_as_a_guest` (`is_guest`);
- `test_redeem_by_code_takes_from_a_live_guest`;
- `test_redeem_by_hand_refuses_a_guest` (404 `event.member_not_found`);
- `test_an_erased_guest_cannot_redeem` (its unused code is gone: 404
  `voucher.code_invalid`);
- `test_a_guest_of_another_event_cannot_redeem_here` (409 `voucher.code_other_event`);
- `test_a_code_issued_before_a_merge_is_invalid_after_it`: 404 `voucher.code_invalid`,
  and the pooled balance is untouched. The same for a promotion;
- `test_check_answers_code_invalid_for_a_pass_deleted_after_its_read` (the re-read
  after `hold_pass`);
- `test_a_redemption_retried_after_a_merge_replays` (the same `request_id` →
  `replayed`, the account's name, no second debit).

`tests/api/routes/test_vouchers.py`:

- `test_an_admin_corrects_a_guest` (`_appears_in_event` through bookings);
- `test_appears_in_event_moved_to_logic` (route and logic agree).

`tests/logic/test_voucher_concurrency.py` adds, with committed connections and an
`asyncio.Barrier(2)`:

- `test_a_merge_waits_for_a_redemption_in_flight`: the entry ends on the account, and
  `available` equals earned minus redeemed, with no refund;
- `test_a_check_beside_a_merge_answers_code_invalid`: no answer names the deleted
  chain.

**Confirm, promote and merge**, new `tests/logic/test_shared_list_guest_account.py`:

- the first confirmation promotes the chain in place: the same user id, `confirmed_at`
  set, no alias, its unused passes deleted and its used ones kept. Its response token
  resolves to nothing and `retired_response_token` is true; its mail token resolves to
  the account;
- a second chain of the address merges into it. Bookings, reminders (`user_id`),
  earnings, entries and used passes move; unused passes are deleted; the chain user is
  deleted; one alias is written. The pooled `available` is the sum;
- the collision table of §4.2, one test per row. Confirmed on both sides settles first,
  keeps both earning rows on the account, and leaves the total unchanged;
- each booking keeps its own person: after a merge of chains named "Maria" and "Tom",
  `first_names` names exactly the bookings whose forms said so, each with its own
  name; `confirmed_bookers`, `list_shift_bookings`, `list_task_bookings` and
  `list_signups` show each booking's own name and phone; the account user's name and
  phone are unchanged;
- `first_names` never names a guest without a live `shared_list_guests` row (event
  deleted, task moved to another event);
- `guest_activity_log` has the same rows before and after;
- the same address at another event is never merged (`find_account` filters on the
  event);
- `ledger_event_ids` includes an event where the chain only has a booking on a task
  without Marken; `voucher_event_ids` does not;
- `merge_guest` with a plain user id as the target works (claim forward-compat, V12).

**Tokens**, `tests/logic/test_guest_tokens.py`. Every row of the V4 table:

- the old mail link of a merged chain opens the account (`from_mail`);
- a promoted chain's mail token resolves to the account, and its response token to
  nothing, with `retired_response_token` true;
- a merged chain's response token resolves to nothing, with `retired_response_token`
  true;
- `peek` returns nothing for a forged tag, and reports which key matched;
- erasing the account kills the alias.

**Routes**, `tests/api/routes/test_public_shared_lists.py`. New classes, plus the
existing ones extended:

- `TestVouchersOnThePublicPage` (new):
  - `PublicShift.vouchers` for a voucher task, and 0 otherwise;
  - `retention_days` equals the setting (patched to 14) on the public GET and the
    organisers' `/preview`.
- `TestConfirm` (new):
  - 200 with a mail token. The first confirmation answers with the same token
    (promote); a second chain's answers with the account's;
  - 403 `guest_signup.mail_link_required` with a live chain's response token;
  - the response token of a chain without an address (`ask_email='off'`) → 403, and its
    mail-key twin → 404, never a 500;
  - a forged tag → 404, without taking a lock (`crud_event.lock` and
    `guest_quota.lock_account` patched to fail if called);
  - idempotent (the same link twice → the same account);
  - `/manage` with a retired response token → 404, after a promotion and after a
    merge;
  - "Noch eine Schicht" with that token starts a new chain (`mail_queued` for a new
    confirmation);
  - an unconfirmed chain's view never lists another chain's bookings or Marken (goal
    2, second bullet);
  - not-me on an account → 409 `guest_signup.reject_confirmed`;
  - not-me on a chain while the address has an account (at this event, and at another
    one) → the chain is erased, the address is **not** suppressed, and the account's
    reminder still goes out; without an account → suppressed, as today.
- `TestGuestVoucherPass` (new):
  - 201 `VoucherPassRead` with `qr_payload == "WV1:" + code`;
  - status `active` → `used` after a member redeems by code;
  - a response token of an unconfirmed chain may issue;
  - an event without Marken → 404 `guest_signup.not_found`;
  - not kill-switched;
  - buckets: the 121st status call of one guest in a minute → 429; two guests behind
    one IP each keep their own bucket; 31 misses from one IP → 429 for misses, while a
    valid token from that IP still works.
- **Extend the existing `TestManage` (l. 1212). Do not define a second class:** ruff
  F811 would flag it, and the old manage tests would otherwise silently stop running.
  - `vouchers` per event, with a moved voucher task giving a second entry;
  - `erase_on` = last shift + days + 1;
  - the `confirmed` / `can_confirm` / `can_reject` / `reject_suppresses` matrix for
    mail token, response token and account;
  - `has_phone`, and each booking's `name`;
  - entries carry no `actor_name` or `note`;
  - 31 manage calls of one guest → 429; another guest on the same IP is unaffected.
- `TestFirstNames` and `TestSignUp` (existing, l. 332 and l. 408) move to the
  per-booking flag and snapshots. A continuation records its own form's `show_names`,
  and the chain's name and phone.

**Other backend tests**:

- `tests/api/routes/test_testing.py`: `/testing/guest-mail-link` returns the chain's
  mail token.
- `tests/logic/test_guest_mail.py`:
  - the confirmation mail mentions Marken only for a voucher shift;
  - `retention` or `retention_phone` by `has_phone`, carrying the setting;
  - `confirm_hint` names the event;
  - the reminder carries the voucher line;
  - every kind carries `link_private`, and `link_private_vouchers` when a shift earns;
  - a mail about a pooled booking greets its own `guest_name`.

  All in en and de.
- `tests/logic/test_shared_list_erase.py` and `test_shared_list_retention.py`:
  - erase and the sweep delete aliases and unused passes, null `guest_name` and
    `guest_phone` on the kept bookings, and null the notes of the guest's corrections
    (the amounts stay);
  - a guest with a redemption entry is anonymised and not deleted;
  - an erased account frees `uq_shared_list_guests_account`, so the next confirmation
    promotes a new account;
  - erasing an account leaves an unconfirmed chain with the same address at the event
    untouched (the documented scope).
- `tests/api/routes/test_list_guests_admin.py`: the export carries `confirmed_at`,
  `vouchers` (earned, redeemed, a correction without its note) and each booking's
  `name` and `phone`. `search_guests` finds a pooled booking's name.
- The roster tests that cover guests (`is_guest` cases of `GET /shifts/`,
  `/shifts/{id}/bookings`, `/tasks/{id}/bookings` and the bookings CSV) gain an account
  with two pooled names.
- `tests/core/test_rate_limit.py`: the new buckets, their keys and their code.
- `tests/migrations/test_shared_lists_schema.py`:
  - `bookings.show_first_name` (server default `false`), `bookings.guest_name` and
    `bookings.guest_phone` (nullable);
  - `shared_list_guests.confirmed_at`, and no `shared_list_guests.show_first_name`;
  - the partial unique index with its predicate;
  - the alias table, its indexes and its FK `ON DELETE CASCADE`;
  - the round trip, `test_downgrade_and_upgrade_again`, on the fresh test database.
- Update for the moved consent and the snapshots:
  - `tests/fixtures/shared_lists.py` (`make_list_guest` sets `show_first_name`,
    `guest_name` and `guest_phone` on its bookings) and `tests/fixtures/README.md`;
  - `tests/crud/test_shared_list_guest.py`;
  - `tests/logic/test_shared_list_change_concurrency.py`.

**Concurrency**, new `tests/logic/test_shared_list_guest_account_concurrency.py`. It
uses committed setup on separate connections, like
`test_shared_list_signup_concurrency.py`, with the ceilings switched on. Run it three
times in a row.

- two chains of one address confirmed at once → one account (one promoted, one
  merged), no deadlock;
- the same link confirmed twice at once → one promotion, two 200s with the same token;
  the same for a link whose chain merges;
- confirm vs. "Noch eine Schicht" on the chain → the continuation becomes a new chain;
- confirm (merge) vs. organiser removal of the chain's booking with `erase=true` → the
  removal skips it with `shared_list.signup_not_found` and the account is not erased;
  a retry removes it and erases the account;
- confirm vs. deleting the event → no deadlock;
- confirm vs. erase of the account → the chain is promoted to a fresh account; the
  partial index holds;
- confirm (merge) vs. a rate change (`settle_earnings` with `include_zero`) and vs. a
  shift delete → every earning ends on the account, none is lost, no deadlock;
- confirm (merge) vs. a correction in an event where the chain only has a booking
  without Marken → the correction lands first and moves, or answers 404 after; it is
  never deleted;
- confirm vs. the reminder poller sending the chain's reminder → no deadlock, the
  reminder row ends on the account and is sent once.

### 8.2 Frontend

**Unit tests** (vitest; the 90 % gate applies to `src/lib`, `src/stores` and
`src/composables`):

- `src/stores/__tests__/guestSignup.spec.ts`:
  - `confirm` swaps the token;
  - `passSource` posts the token and the event id;
  - a 404 `voucher.pass_not_found` from status is an ordinary failed status; a 404
    `guest_signup.not_found` rejects with `PassSourceGone`.
- `src/components/vouchers/__tests__/VoucherCodeDialog.spec.ts` (new, §7.1).
- `src/components/guest/__tests__/GuestConfirmCard.spec.ts` and
  `GuestVouchersCard.spec.ts`:
  - no code button at 0;
  - the history without names;
  - the per-event title only when there are several events;
  - the `fromMailOnly` hint only without `can_confirm`.
- WP8's specs:
  - `GuestSignupDone.spec.ts` / `GuestSignupForm.spec.ts`: rendered with
    `retention_days: 14`, they show "14", and **no "30" appears in any guest
    component**. A list with `ask_email: 'off'` and `ask_phone: 'off'` names neither
    address nor phone in its retention line. The done page shows `done.linkPrivate`;
  - `GuestSignupManageView.spec.ts`: the not-me text by `reject_suppresses`, the erase
    scope on an account, `manage.signedUpAs` only for a booking under another name;
  - `PublicShiftList.spec.ts`: the badge only above 0.
- `VoucherRedeemConfirm.spec.ts`: the guest tag.
- The `EventVouchers` rendering of guest and erased rows, in the existing spec if
  there is one, else a new `src/components/events/__tests__/EventVouchers.spec.ts`.
- The usual gates: `just check-locales` (en and de keys equal) and `wording.spec.ts`.

**E2E**:

- `frontend/e2e/tests/guest/guest-vouchers.spec.ts`, in WP8's `guest` project:
  1. The organiser gives the task 2 Marken a shift, and another task becomes a point
     (the same UI steps as `e2e/tests/multi-user/vouchers.spec.ts:83-105`).
  2. The guest signs up with `publicSignup`.
  3. The organiser moves the shift to yesterday (`PATCH /shifts/{id}`, the same trick
     as l. 95), so it has earned.
  4. The guest opens `/guest-signup#<response token>`, sees 2, presses "Code zeigen"
     and reads the code.
  5. The organiser redeems it on the redeem page; the guest's dialog shows "eingelöst"
     and the balance 0.
- A second test covers the confirm flow:
  1. Two sign-ups with one address and two names.
  2. `guestMailLink(token)` (new helper in `frontend/e2e/helpers/api.ts`, calling
     `/testing/guest-mail-link`) for each.
  3. Open the first and confirm, then the second and confirm.
  4. One page lists both shifts, the second as "Eingetragen als <name>". The first
     response token now shows the not-found state.
- `frontend/e2e/tests/a11y/guest-pages.spec.ts` (WP8): the manage page with the
  vouchers card and the open code dialog.
- `frontend/e2e/COVERAGE.md` is regenerated.

---

## 9. Docs to update

- **`docs/VOUCHERS.md`**:
  - "Who may redeem" (l. 26-66): a row or note saying that a list guest is redeemed
    *by code only*, never picked, and why;
  - "What someone has" (l. 87-100): guests earn like members; whose balance is whose
    (chain or account), the promotion and the merge, and `appears_in_event`;
  - "Codes" (l. 236-263): the public guest endpoints and their per-guest limits; a
    confirmation deletes the chain's unused codes; `check` re-reads its pass after
    the hold;
  - "Gotchas" (l. 309-…): a guest user with entries is never deleted; a merge takes the
    ledger locks of both users, then the chain's `users` row, because `settle_earnings`
    takes no lock; unredeemed Marken expire at anonymisation, and the notes of a
    guest's corrections are cleared.
- **`docs/SHARED_LISTS.md`** (created by WP4b), new sections:
  - "Guest accounts" (V2-V6, promote and merge, the token table, aliases), with the
    residual risk of a forwarded mail link (V4);
  - "Vouchers for guests" (§4.4-§4.5);
  - "A sign-up's person" (V7): the rule and its readers;
  - the lock-order table of §4.7 replacing the old one;
  - retention with accounts and expiring Marken, what erasing an account does and does
    not erase, and "Das war ich nicht" without a suppression (V9);
  - the guest rate limits (§5).
- **`docs/plans/2026-11-10-shared-lists.md`**: a one-line note under "Decisions taken
  before implementation" and at D10, D12, §4.5 (the claim row) and §4.17: "Amended by
  2026-11-12-shared-lists-guest-vouchers.md".
- **`CLAUDE.md`**, in the shared-lists paragraph WP4b writes:
  - guests earn vouchers;
  - `guest_account.confirm` is the only code that promotes or merges guest users,
    under the lock order in docs/SHARED_LISTS.md;
  - a guest booking's person is `bookings.guest_name` / `guest_phone`, and its consent
    `bookings.show_first_name`. Never show a list guest's `users.name` for a booking;
    use `crud_booking.person_name`.
- **Privacy** (`src/views/preauth/PrivacyView.vue` + `preauth.privacy.*`, the guest
  section WP8 adds; "Sie"):
  - de: "Für Schichten mit Marken speichern wir, wie viele Marken Sie verdient und
    eingelöst haben. Bestätigen Sie Ihre Adresse über den Link in unserer Mail,
    zeigen wir die Eintragungen, die Sie mit dieser Adresse bei derselben
    Veranstaltung bestätigen, auf einer Seite und zählen ihre Marken zusammen. Jede
    Eintragung behält ihren Namen." And: "{days} Tage nach Ihrer letzten Schicht
    anonymisieren wir Ihre Angaben; Marken, die Sie bis dahin nicht eingelöst haben,
    verfallen."
  - en: "For shifts with vouchers we store how many you earned and redeemed. If you
    confirm your address through the link in our mail, we show the sign-ups you
    confirm with that address for the same event on one page and add up their
    vouchers. Each sign-up keeps its own name." And: "{days} days after your last shift
    we anonymise your details; vouchers you have not redeemed by then expire."
  - The number: open question 5.
- **Feature docs** (`frontend/src/docs/{en,de}/feature/shared-lists.md`, WP8's new
  page): an FAQ "Bekomme ich ohne Konto Marken?", a section on confirming the address,
  and the advice not to forward the mail. In `feature/vouchers.md` (the main plan cites
  :63), guests now earn, by code only.
- **Changelog** (WP8's shared-lists entry): in the hero, "Auch wer sich ohne Konto
  einträgt, bekommt Marken und löst sie mit einem Code ein". That is the default for
  every voucher task, so it belongs in the hero. The version: open question 6.

---

## 10. Work breakdown

### Package V-B: backend (one package, after the shared-lists backend; before any frontend work below)

Files:

- `app/models/shared_list.py`, `app/models/booking.py`, `app/models/__init__.py`
- `app/alembic/versions/20261110_0001_shared_lists.py` (amended, with the `IF EXISTS`
  downgrade of §3)
- `app/crud/shared_list_guest.py`:
  - `create` loses `show_first_name`;
  - new `find_account`, `has_live_account`, `lock_many`, `lock_guest_user`,
    `get_alias`;
  - `search_guests` support for booking snapshots, if the query lives here.
- `app/crud/voucher.py` (`reassign_user`, `delete_unused_passes`),
  `app/crud/booking_reminder.py` (`reassign_user`), `app/crud/booking.py`
  (`person_name`, `person_phone`, `person_name_sql`, `person_phone_sql`;
  `confirmed_bookers`)
- `app/logic/shared_lists/guest_account.py` (new: `confirm`, `merge_guest`,
  `MergeResult`)
- `app/logic/shared_lists/guest_vouchers.py` (new: `voucher_event_ids`,
  `ledger_event_ids`, `guest_vouchers`, `issue_pass`, `pass_status`)
- `app/logic/shared_lists/guest_tokens.py` (`resolve` per §4.3, `peek`, `Peeked`,
  `retired_response_token`)
- `app/logic/shared_lists/guest_quota.py` (`lock_account`)
- `app/logic/shared_lists/signup.py` (per-booking consent and snapshots, `_chain` per
  §4.2)
- `app/logic/shared_lists/public_page.py`, `guest_manage.py`, `erase.py`,
  `retention.py`, `removal.py` (the skip of §4.6, the greeting), `guest_mail.py`,
  `signups_query.py`, `__init__.py` (docstring lists the two new modules)
- `app/logic/vouchers.py`
- `app/api/routes/public_shared_lists.py`, `app/api/routes/vouchers.py`,
  `app/api/routes/testing.py`, and the V7 readers `app/api/routes/shifts.py`,
  `app/api/routes/tasks/crud.py`, `app/api/routes/tasks/shifts.py`,
  `app/api/routes/reporting.py`
- `app/schemas/public_shared_list.py`, `app/schemas/voucher.py`,
  `app/schemas/shared_list_guest.py`, `app/schemas/shared_list.py` (comment)
- `app/core/rate_limit.py`
- the tests of §8.1
- `docs/VOUCHERS.md`, and the `docs/SHARED_LISTS.md` sections (if WP4b has not merged
  yet, hand WP4b the section text instead)

Accepted when:

- `just lint-backend` is clean;
- `uv run --directory backend basedpyright` reports 0 errors;
- `just check-migrations` is clean on a fresh dev database, and on a dev database that
  had the old `20261110_0001` after the two commands of §3. That old-schema case is
  checked by hand once. The automated round trip is
  `tests/migrations/test_shared_lists_schema.py::test_downgrade_and_upgrade_again`,
  on the fresh test database;
- the full `just test-backend` passes at a coverage of 95 % or more;
- the concurrency files pass three runs in a row;
- the confirmation mail is checked in en and de in the mailcatcher (`just dev local`,
  `http://localhost:1080`), with and without a phone, for a voucher shift and for one
  without Marken;
- `just generate-client` has been run, and the diff is only the additions of §5.

### Package V-F: frontend (after V-B's client regeneration and after WP6, WP7 and WP8 have merged)

Files:

- `src/client/**` (regenerated)
- `src/lib/vouchers.ts` (+ spec: `VoucherPassSource`, `PassSourceGone`)
- `src/components/vouchers/VoucherCodeDialog.vue` (+ new spec, with the `gone` state),
  `VoucherRedeemConfirm.vue` (+ spec)
- `src/views/vouchers/RedeemVouchersView.vue`, `src/components/events/EventVouchers.vue`
- `src/stores/guestSignup.ts` (+ spec)
- `src/views/guest/GuestSignupManageView.vue` (+ spec), `SharedListPublicView.vue`
- `src/components/guest/GuestConfirmCard.vue`, `GuestVouchersCard.vue` (new, + specs),
  `PublicShiftList.vue`, `GuestSignupForm.vue`, `GuestSignupDone.vue`
- `src/components/shared-lists/wizard/WizardTaskPicker.vue`
- `src/components/shared-lists/SharedListRemoveSignupsDialog.vue`
- `src/views/preauth/PrivacyView.vue`
- `src/locales/{en,de}/guestSignup.json`, `vouchers.json`, `errorCodes.json`,
  `sharedListWizard.json`, `sharedLists.json`, `preauth.json`
- `frontend/src/docs/{en,de}/feature/shared-lists.md`, `feature/vouchers.md`
- the shared-lists changelog entry
- `frontend/e2e/helpers/api.ts` (`guestMailLink`),
  `frontend/e2e/tests/guest/guest-vouchers.spec.ts`,
  `frontend/e2e/tests/a11y/guest-pages.spec.ts`, `frontend/e2e/COVERAGE.md`

Accepted when:

- `pnpm --prefix frontend exec eslint .` is clean, and `just check-locales`, both
  type-checks, `test:unit:coverage` and `build-only` pass;
- `--project=guest`, `--project=multi-user` (the existing voucher spec unchanged) and
  `--project=a11y` pass;
- at 375 px the code dialog and the vouchers card scroll no page sideways.

If WP6-WP8 are still open when V-B lands, their owners may take the V-F edits to their
files instead of waiting. The file lists above say which edits belong to whom.

---

## 11. Open questions (each with the default this plan assumes)

1. **Confirm on a click, or on opening the mail link?** Auto-confirming would pool more
   guests without effort, but scanners that run JavaScript would confirm, and the owner
   would not see what joined their page. *Default: an explicit "Ja, das bin ich"
   button.*
2. **What happens to unredeemed Marken at deletion?** *Default: they expire when the
   data is anonymised (erase, "Das war ich nicht", or `GUEST_DATA_RETENTION_DAYS` after
   the last shift), and every place that names the period says so. The organisers
   still see the amount on an anonymous row and can correct it to 0 to close the
   books.*
3. **May organisers redeem by hand for a guest whose phone died?** *Default: no. The
   picker stays members-only. An event admin books a negative correction instead. Its
   note is cleared when the guest's data is anonymised.*
4. **Should the public list show the Marken per shift?** *Default: yes, when the task
   earns some. There is no per-list switch; organisers who want to hide it set the
   task's rate.*
5. **The retention number on the prerendered privacy page.** The guest pages and the
   mail now take it from the API. The privacy page is prerendered without an API.
   *Default: expose `GUEST_DATA_RETENTION_DAYS` as runtime config (`AppConfig`,
   `useAppConfig.ts` default 30, the `docker-entrypoint.sh` line). The page shows the
   deployed number after hydration; the prerendered HTML carries the hosted default,
   30. `feature/self-hosting.md` says so. The alternative, wording without a number,
   is vaguer than a privacy text should be.*
6. **Changelog version.** `main` already released 0.29.0 and 0.29.1 ("Join requests,
   one click away"), while the main plan still names 0.29.0 for shared lists.
   *Default: the shared-lists entry, including this, ships as 0.30.0; WP8 renames its
   file.*
7. **Whose name does a pooled account carry?** *Default: the first confirmed chain's,
   for the wallet only: the manage page's header, the organisers' voucher overview and
   the redeemer's check sheet. Every booking keeps its own name and phone (V7), so a
   family's pooled sign-ups each show their own person on lists and rosters.*
8. **Should a confirmed address get looser D17 ceilings?** *Default: no. Ceilings count
   addresses, not accounts, and confirming changes nothing about mail volume.*
9. **No-show guests keep their Marken** until attendance (#177) exists, as no-show
   members do. *Default: accept, and name the negative correction in
   docs/VOUCHERS.md.*
10. **Should erasing an account also erase unconfirmed chains with the same address at
    that event?** It would match "Meine Daten löschen" more closely. But it would
    erase, on one click, sign-ups of other people who share the address (a family),
    and it would have to lock guest rows the request does not hold yet, against
    confirm's lock order. *Default: no. The erase dialog says what it erases and how
    the rest is erased (V9, §7.2); the operator erases on request.*
11. **Should "Das war ich nicht" still suppress an address that has a confirmed
    account?** Suppressing would also stop the mails about the sign-ups the person
    confirmed, without saying so. *Default: no (V9). The chain is erased, the address
    stays mailable, and the dialog says that mail about the confirmed sign-ups
    continues.*
