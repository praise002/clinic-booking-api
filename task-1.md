Build a booking API
A clinic needs an API that lets patients book appointment slots, plus a simple web page that uses it: see available slots, book one, and see the confirmation. Build both and deploy them.
The task has five levels. You don't need to finish everything, but do each level properly before moving on.
• Level 1: List slots, book one, and look up a booking.
• Level 2: Only requests with your API key get in, and bookings with missing or invalid details are turned away.
• Level 3: Two people can never book the same slot, even at the exact same moment. Bookings can be cancelled.
• Level 4: A retried request never creates a duplicate booking, and a person can page through their bookings.
• Level 5: Stop anyone from spamming bookings.
The exact endpoints and responses are in the technical spec: koyaacademy.com/assessment-api. Follow it closely.
Rules
• Use any language, framework, database and host. You can use AI.
• Deploy it at an https URL. Render, Vercel, Supabase and Neon all have free plans, so it shouldn't cost you anything.
• Bookings must still be there on the next request. If you host on serverless functions, use a database.
• After you submit, keep it running and don't change it until we contact you.


The exact contract for Task 1 of the Koya Cohort 4 assessment. Build these endpoints so our checks can talk to your API.

Everything is JSON. Each endpoint says which level it belongs to. Every error response looks like {"error": "<message>"}.

Every request needs the X-API-Key header (level 2). A missing or wrong key returns 401.

/reset - Level 1 - Replace all slots POST

Deletes every booking and replaces all slots with the ones you send, including slots in the past.

Parameters
No parameters

Request body

application/json
Example Value
Schema
{
  "slots": [
    {
      "id": "s1",
      "provider": "Dr Ade",
      "start": "2026-12-10T09:00:00Z",
      "end": "2026-12-10T09:30:00Z"
    }
  ]
}

Responses
Code	Description	Links
200	
Done

No links

/slots - Level 1 - List slots - GET
Every slot, earliest start first.

Parameters
Name	Description
provider
string
(query)
Only this provider's slots (exact match)

provider
Responses
Code	Description	Links
200	
The slots

Media type

application/json
Controls Accept header.
Example Value
Schema
{
  "slots": [
    {
      "id": "s1",
      "provider": "Dr Ade",
      "start": "2026-12-10T09:00:00Z",
      "end": "2026-12-10T09:30:00Z",
      "available": true
    }
  ]
}

/bookings - Book a slot (Levels 1 - 5)  POST
Level 1: returns 201 with the booking, status confirmed.

Level 2: 400 if slot_id, name or email is missing or empty, or the email isn't valid. 404 if the slot doesn't exist. 400 if the slot has already started. Trim spaces from name and email, and store email in lower case.

Level 3: a slot that already has a confirmed booking returns 409. This must hold when many requests arrive at the same moment.

Level 4: the optional Idempotency-Key header. The same key with the same body returns the same response (same status code, same booking id) and never creates a second booking. The same key with a different body returns 422.

Level 5: at most 5 attempts per email per minute, failed attempts included. The 6th returns 429 with a Retry-After header in whole seconds. Other emails aren't affected.

Parameters
Name	Description
Idempotency-Key
string
(header)
Level 4

Idempotency-Key
Request body

application/json
Example Value
Schema
{
  "slot_id": "s1",
  "name": "Ada Obi",
  "email": "ada@example.com"
}

Responses
Code	Description	Links
201	
Booked

Media type

application/json
Controls Accept header.
Example Value
Schema
{
  "id": "string",
  "slot_id": "s1",
  "name": "Ada Obi",
  "email": "ada@example.com",
  "status": "confirmed",
  "created_at": "2026-10-25T23:18:20.836Z"
}
No links
400	
Missing or invalid field, or the slot has already started (level 2)

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}
No links
404	
The slot doesn't exist (level 2)

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}
No links
409	
Slot already booked (level 3)

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}
No links
422	
Idempotency-Key reused with a different body (level 4)

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}
No links
429	
Too many attempts for this email (level 5)

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}
Headers:
Name	Description	Type
Retry-After	
Seconds to wait

integer
No links

/bookings - Level 4 - List a person's bookings - GET
That person's bookings, oldest first. The email match ignores case. Use cursor pagination: pass next_cursor back as cursor to get the next page. The last page has next_cursor: null.

Parameters
Name	Description
email *
string
(query)
email
limit
integer
(query)
1 to 50. Anything else returns 400.

Default value : 10

10
cursor
string
(query)
cursor

Responses
Code	Description	Links
200	
A page of bookings

Media type

application/json
Controls Accept header.
Example Value
Schema
{
  "bookings": [
    {
      "id": "string",
      "slot_id": "s1",
      "name": "Ada Obi",
      "email": "ada@example.com",
      "status": "confirmed",
      "created_at": "2026-10-25T23:20:13.030Z"
    }
  ],
  "next_cursor": "string"
}
No links
400	
Invalid limit

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}

/bookings{id} - Level 1 Get a booking - GET

Parameters
Name	Description
id *
string
(path)
id
Responses
Code	Description	Links
200	
The booking

Media type

application/json
Controls Accept header.
Example Value
Schema
{
  "id": "string",
  "slot_id": "s1",
  "name": "Ada Obi",
  "email": "ada@example.com",
  "status": "confirmed",
  "created_at": "2026-10-25T23:24:59.885Z"
}
No links
404	
No booking with that id

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}

/bookings/{id} - Level 3 - Cancel a booking - DELETE

Sets status to cancelled and frees the slot.

Parameters
Name	Description
id *
string
(path)
id
Responses
Code	Description	Links
200	
The cancelled booking

Media type

application/json
Controls Accept header.
Example Value
Schema
{
  "id": "string",
  "slot_id": "s1",
  "name": "Ada Obi",
  "email": "ada@example.com",
  "status": "confirmed",
  "created_at": "2026-10-25T23:26:13.300Z"
}
No links
404	
No booking with that id

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}
No links
409	
Already cancelled

Media type

application/json
Example Value
Schema
{
  "error": "slot not found"
}