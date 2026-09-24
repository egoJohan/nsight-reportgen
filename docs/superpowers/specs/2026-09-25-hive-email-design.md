# nSight sends its mail through the hive

Agreed with Johan 2026-09-25. nSight's own mail (invitations, access-request
notices) goes out through the hive's email API; SMTP stays as the fallback. An
invitation can be sent again from the Users list.

nSight works only on its own side. The hive's route and its configuration (the
sender address, the relay) are egoHive's.

## The hive's route

`POST {NSIGHT_DATAHIVE_URL}/api/v1/email/hive/send` with nSight's hive token,
body `{to, subject, body}`, `body` HTML. It sends as the hive itself, from the
hive's configured sender through its relay; the caller cannot choose the From.
Answers: 200 sent; 400 a caller fault (including *"this hive has no configured
sender address"*); 403 not a primary bearer / consent refused; 503 no working
relay; 502 the relay failed. A hive older than the route answers 404/405. The
hive limits caller-composed sends to 60 an hour.

Probed on nSight's staging hive 2026-09-25: the route exists, nSight's token
passes the bearer and consent checks, and the send is refused with 400 because
the hive has no sender address yet. Until egoHive sets one, sending falls back
as below.

## Delivery order — `mailer.deliver`

1. `send_via_hive(to, subject, html)`: True only on 200. Never raises; every
   refusal is logged with the hive's own words.
2. Otherwise, when `settings/email.json` holds an SMTP setup, `send_via_smtp`
   with the plain-text body — as before.
3. Otherwise not sent: an invitation answers `emailed: false` and the admin
   copies the link, exactly as when nothing was configured before.

Every message has a text and an HTML body; values in the HTML are escaped.

## Resend invitation

- `POST /invites/{invite_id}/resend`, admin only. A pending or expired
  invitation is emailed again and its `expires` restarts at 14 days from now;
  grants, inviter and `invited_at` are unchanged. The resending admin signs the
  message. Accepted → 409; unknown → 404. The answer is a new invitation's:
  the invite, `link`, `emailed`.
- Settings → Users: a **Resend invitation** button on the row of someone who
  has never signed in and has an invitation not yet accepted (the newest one
  for their address). Emailed → "Invitation emailed to X again". Not emailed →
  a warning that shows the sign-in link and copies it when the browser allows.

## Testing

Fake transports only; no test reaches a hive or an SMTP server. Covered: the
hive request's URL, body and bearer; every refusal status and an unreachable
hive → False; no hive configured → no call; hive first, SMTP fallback with the
text body, neither → False; the invitation's HTML link and escaping; resend of
a pending, an expired (live again afterwards), an accepted (refused) and an
unknown invitation; the route's 200/409/404/403.
