"""Shared lists: public links through which people sign up for shifts without an
account.

For organisers:

* ``manage`` — creating, editing, pausing, resuming, ending and rotating lists,
  singly or in bulk.
* ``overview`` — the management views of one event (tables, figures, the
  wizard's choices), worked out in one pass.
* ``signups_query`` — who signed up through a list, and the operator's lookup
  and export of guest data.
* ``removal`` — organisers taking guests off shifts they signed up for.

For guests:

* ``offer`` — which shifts a list offers right now, and its status on the
  event's clock. The public page and the sign-up read shifts only through it.
* ``public_page`` — what the public page shows, also in the organisers' preview.
* ``signup`` — signing up for a shift through a list.
* ``guest_manage`` — what a guest can do through their manage link.
* ``guest_tokens`` — the manage link, and the keyed hash that stands for an
  address.
* ``guest_mail`` — every mail a guest gets, written from database fields only.
* ``guest_quota`` — the daily ceilings on guest sign-ups and guest mail.
* ``normalize`` — the one way names, addresses and phone numbers typed into a
  list's form are cleaned before they are stored or compared.

What a guest typed:

* ``erase`` — erasing a guest, however it is asked for.
* ``retention`` — the sweep that anonymises guests after their last shift.

Who may see and manage a list is decided by the shared-list gates in
``app.logic.permissions``; the rows live in ``app.models.shared_list``.
"""
