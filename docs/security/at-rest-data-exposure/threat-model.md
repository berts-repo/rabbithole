# Threat-Model Context

Parent: [`../at-rest-data-exposure.md`](../at-rest-data-exposure.md).
Managed under [`../../../LIBRARIAN.md`](../../../LIBRARIAN.md).

This exposure is **not a surprise and not negligence**. It is a deliberate,
recorded scoping decision. Honesty matters here, so the relevant project
statements are quoted directly.

`CONTEXT.md`, in its Hard Constraints, defines the threat model:

> "Preserve the current threat model: privacy toward malicious onion sites and
> relays is in scope; physical/device security is deferred unless the owner
> changes the threat model."

`docs/reference/features.md` ("Product Boundaries") restates the same boundary:

> "The current threat model prioritizes privacy toward malicious onion sites
> and relays. Physical/device security, seizure resistance, and full at-rest
> encryption are deferred unless the project threat model changes."

The crawler-privacy plan at `docs/work/active/2026-05-21-crawler-privacy-
cleanup/plan.md` records the owner's reasoning explicitly, in a section titled
"At-rest encryption (deferred)":

> "Owner decision: device seizure is not in the current threat model, so
> encrypting the project database is deferred. It should remain *possible to
> add later as an option*."

So the project has, on purpose:

- decided that **privacy toward malicious onion sites and relays** is the
  priority threat (and has done substantial work there — Tor routing, SOCKS5h,
  per-site circuit isolation, request profiles, pacing);
- decided that **physical/device compromise — theft, loss, seizure, disk
  imaging — is out of scope *for now***; and
- **written that decision down in three places**, with a stated condition for
  revisiting it ("unless the owner changes the threat model").

That is the responsible way to defer a control. The purpose of *this* document
is to keep the deferral honest and visible: the database **is** unencrypted, the
data **is** sensitive, and the only thing standing between that file and a
reader is *not losing the file*. If the project's audience or risk context
changes — for example, if Rabbithole is used by people who could face device
seizure or border inspection — this deferral should be reopened.

Non-alarmist bottom line: nothing is broken, and nobody made a mistake. There is
simply an accepted gap, and it should stay a *decision*, not drift into being a
forgotten omission.

---
