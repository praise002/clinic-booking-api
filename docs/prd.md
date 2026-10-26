---
doc: prd
status: approved
---

# Clinic Booking API — Product Requirements

A deployed clinic booking API that follows the Koya Task 1 contract exactly, plus one plain web page where a patient can find a free slot, book it, and later find or cancel their bookings.
Source: `scope.md > Who It's For`, `scope.md > The Core Loop`.

## The Core Journey

1. A patient opens the page. At the top they see the **Slots** section: every slot, earliest first, each showing the provider and a readable date and time, and marked **available** or **unavailable**.
2. Optionally, they pick one provider to see only that provider's slots.
3. They choose an available slot. A booking form appears for that slot with **name** and **email** fields and a **Book** button.
4. They press Book. On success they see a **confirmation** that shows the **booking id** prominently, plus the provider, time, name, email and status "confirmed". The slot list refreshes, and that slot now shows as unavailable.
5. If booking fails, they see a plain-language message that tells them what to do next (see **Booking Errors**).
6. Later, they come back and use **My Bookings**: they type their email and see their bookings, oldest first, one page at a time, cancelled ones included.
7. They press **Cancel** on a booking and confirm "are you sure?". The booking stays in the list, now marked **cancelled**, and the slot becomes available again for someone else.

Success is the loop closing: book → confirmation with id → find it again → cancel → the slot is free again.

## Screens and Layout

One page, arranged as sections stacked top to bottom (`scope.md > The POC Boundary`: "a simple web page with a UI for every endpoint"):

1. **Slots**: the provider filter, then the slot list.
2. **Book a Slot**: the form for the chosen slot, then the confirmation or error.
3. **Find a Booking**: look up one booking by its id.
4. **My Bookings**: look up all of a person's bookings by email, with paging and cancel.
5. **Admin**: reset all slots, gated by typing the API key (`scope.md > Decisions Already Made`).

There's no navigation and no other pages.

## Look and Feel

- **Simple and plain, "nothing too fancy"** (`scope.md > Inspiration & Identity`). Functional over polished.
- **"Clinic colour"**: the learner's phrase. *Interpretation (assumption):* a calm clinical palette, white or very light background, one blue or teal accent for buttons and links, plain dark text. The cancelled and unavailable states use muted grey, and errors use one clear red.
- A readable system font, generous spacing, and no decorative imagery, gradients or animations.
- No reference site was given. Avoid the generic AI-app look: no hero banners, glassmorphism or card-heavy dashboards.

## Features and Behavior

### API Contract

The API itself is fixed by `task-1.md` and is normative: endpoints, status codes, bodies, the `{"error": "<message>"}` shape, `X-API-Key` on every request, and `Retry-After`. This PRD doesn't restate it. The proof standard comes from `scope.md > The Unique Kernel` and `scope.md > What "Working" Looks Like`:

- [ ] All five levels in `task-1.md` pass, built in level order and verified per level.
- [ ] **Concurrency:** 50 simultaneous `POST /bookings` for one slot give exactly one 201 and 49 409s, and leave exactly one confirmed booking.
- [ ] **Idempotency:** repeating a request with the same `Idempotency-Key` and body returns the same status and the same booking id and creates no second booking. The same key with a different body returns 422.
- [ ] **Rate limit:** the 6th attempt for one email within a minute (failed attempts count) returns 429 with a whole-seconds `Retry-After`, and a different email is unaffected.
- [ ] Bookings survive a restart of the deployed service.
- [ ] A smoke script run against the live https URL passes end to end.

### Slots

- As a patient, I want to see every slot with who it's with and when, so I can pick a time that suits me.
  - [ ] Slots appear earliest first. Each row shows the **provider name**, the **date**, and the **start–end time** in a readable form (e.g. "Thu 10 Dec 2026, 09:00–09:30"), never a raw timestamp.
  - [ ] The slot id is not shown to patients.
  - [ ] Slots that are booked **or already started** stay visible, marked **unavailable**, greyed out, and can't be booked. Available slots can be chosen.
  - [ ] Choosing a provider filter shows only that provider's slots. Clearing it shows all again.
  - [ ] *Assumption:* times display in the patient's own (browser) timezone.
  - [ ] *Assumption:* the provider filter is a dropdown of the providers present in the slot list, with an "All providers" option, so a patient can't mistype a name (the API matches exactly).

### Book a Slot

- As a patient, I want to book a slot with my name and email and get something I can use later, so I can find or cancel the booking.
  - [ ] Choosing an available slot shows the form with the chosen slot's provider and time, name and email fields, and a Book button.
  - [ ] A successful booking shows a confirmation with the **booking id** (prominent and easy to copy), provider, time, name, email (as stored, i.e. lower case) and status "confirmed".
  - [ ] After a successful booking, the slot list refreshes and the booked slot shows as unavailable.
  - [ ] *Assumption:* the Book button is disabled while a request is in flight, so a double click doesn't send two bookings.

### Booking Errors

Each failure shows a plain-language message near the form, never raw JSON:

- [ ] **Slot just taken (409):** the message says someone else just booked it, the slot list refreshes automatically so the slot now shows as unavailable, and the patient picks another.
- [ ] **Bad details (400):** the message names the problem (e.g. missing name, invalid email), the patient's input stays in the form, and they can correct it and retry.
- [ ] **Slot already started (400) or no longer exists (404):** the message says the slot can't be booked, and the slot list refreshes.
- [ ] **Too many attempts (429):** the message says how many seconds to wait, from `Retry-After`.

### Find a Booking

- As a patient, I want to look up one booking by its id, so I can check its status (`scope.md > What "Working" Looks Like`: "view a booking").
  - [ ] Entering an id shows that booking's provider, time, name, email and status.
  - [ ] An unknown id shows "No booking with that id".
  - [ ] A confirmed booking found here has a Cancel button, with the same "are you sure?" step, so a patient who kept only the id can cancel without their email.

### My Bookings

- As a patient, I want to see all my bookings by email and page through them, so I can find the one I want.
  - [ ] Entering an email shows that person's bookings, oldest first, regardless of the email's capitalisation.
  - [ ] Each row shows the provider, time, booking id and status. Cancelled bookings stay in the list, marked **cancelled** and greyed.
  - [ ] *Assumption:* the page shows 10 bookings at a time (the API default), with a **Next page** button while there are more. The button disappears on the last page.
  - [ ] An email with no bookings shows "No bookings for this email".

### Cancel a Booking

- As a patient, I want to cancel a booking, so the slot is freed for someone else.
  - [ ] Confirmed bookings have a Cancel button. Cancelled ones don't.
  - [ ] Pressing Cancel asks "are you sure?". Saying no changes nothing.
  - [ ] Confirming marks the booking **cancelled** in place, and that slot shows as available again in the slot list (if it hasn't started).
  - [ ] Cancelling an already cancelled booking (e.g. from another tab) shows "This booking is already cancelled" (409).

### Admin Reset

- As the developer or a Koya reviewer, I want to replace all slots and wipe all bookings, so I can set up a known state.
  - [ ] The Admin section has an **API key** field and a field for the slot list (JSON in the `task-1.md` reset shape), plus a Reset button.
  - [ ] The request carries the key typed in, never the server's own key. A wrong key shows "Wrong API key" (401) and changes nothing.
  - [ ] *Assumption:* Reset asks "are you sure? This deletes every booking." before sending.
  - [ ] After a successful reset, the slot list refreshes.

## States and Boundaries

- **First use / no slots:** the Slots section says "No slots yet". Every other section still works.
- **No slots for a provider:** "No slots for this provider".
- **Loading:** a short "Loading…" while any request is in flight.
- **API unreachable:** "Couldn't reach the booking service, please try again", never a blank section.
- **Persistence:** slots and bookings live on the server, so closing the page and coming back shows the same data. The page itself remembers nothing (no login, no saved email).
- **Permissions:** patients never see or type the API key. Patient actions go through the server, which adds it (`scope.md > Decisions Already Made`). Only someone who knows the key can reset.

## Product Decisions

- **One page with stacked sections.** The learner chose it as the simplest layout.
- **Unavailable slots stay visible, marked unavailable** ("just feel it should be that way"). Patients see the whole schedule, not just gaps.
- **Readable dates and times**, not raw timestamps.
- **Provider name on every slot row.** A clinic has several doctors, and a patient may choose between them.
- **The confirmation leads with the booking id**, the handle for finding and cancelling a booking later.
- **Friendly error messages, each with a way forward.** On a 409 the slot list refreshes to show the new state. On a 429 the page says how long to wait.
- **Cancel asks "are you sure?" first.**
- **Cancel is available from both My Bookings and Find a Booking.** A patient who only kept their booking id can still cancel.
- **Cancelled bookings stay in My Bookings, marked cancelled.** Hiding them would contradict what the API returns and break page sizes.
- **"Clinic colour", plain, no reference site.**
- The API key and reset decisions carry over from `scope.md > Decisions Already Made`.

## What We're Building

- The full `task-1.md` contract, Levels 1–5, each with real tests, including the 50-concurrent-bookings proof, idempotency and rate-limit tests.
- The one-page web UI above, covering every endpoint: list and filter slots, book, view a booking, list bookings by email with paging, cancel, and admin reset.
- A deployment at an https URL with persistent storage, plus a smoke script that passes against it.

## Deferred From the POC

- **Saved email or "remember me":** would need browser storage or accounts. Typing the email again is fine for the proof.
- **Previous-page paging:** the contract's cursor only moves forward. Next page is enough.
- **Visual polish beyond clean and plain** (`scope.md > Later`).

## Possible Later Enhancements

- A calendar or grouped-by-day view of slots instead of a flat list.
- Emailed confirmations.

## Non-Goals

- **Patient accounts or login:** the contract identifies people by email only.
- **Roles or RBAC:** the API key is the only secret, and it protects reset.
- **Editing or rescheduling a booking:** not in the contract. Cancel and rebook instead.
- **Demo video, Devpost form, Discord post:** replaced by deployed URLs, a live smoke test and Koya's submission (`CLAUDE.md`).
- **Changing the deployment after submission** until Koya makes contact.

## Open Questions

- **Does the API's `available` flag cover slots that have already started, or only booked ones?** The contract doesn't say. Either way, the page marks started slots unavailable. Decide in `4-spec`; it doesn't block approval.
- **Booking rows from `GET /bookings` contain only `slot_id`.** Showing the provider and time in My Bookings means the page matches bookings against the slot list. That's a `4-spec` detail, and the product behaviour above stands either way.
- **Rate-limit window semantics** (fixed vs sliding minute) and **how long idempotency keys are kept** are design choices for `4-spec`, within the contract.
