# ADR 0007 - Annotation editing without membership editing

Status: service-level enforcement, shared annotation rights, and local real-time scope
agreed in discussion; documentation adoption pending.
Date: 2026-10-07. Q1/Q4 clarification supersedes the earlier read-only-share proposal.

## Permission boundary

Authenticate at the HTTP boundary; enforce resource-specific authorization in service
functions, including non-HTTP callers. Small functions in `collections/access.py` are
enough. Do not introduce a generalized authorization engine.

Shared users can read a collection and **edit its annotations**, but **cannot change
collection membership**: adding/removing chunks or documents is not an annotation right.
Use distinct checks rather than a generic `require_edit` reused for every mutation:

| Check | Intended distinction |
| --- | --- |
| `require_collection_read` | Owner/shared access to collection content. |
| `require_annotation_edit` | Owner/shared annotation editing, including AI suggestions and review. |
| `require_membership_edit` | Owner permission; sharing alone never grants this. |
| `require_collection_owner` | Preserve owner-only sharing management. |

Preserve existing explicitly authorized admin ownership actions. Do not create a global
admin bypass or infer permissions for tag definitions, collection metadata, or ownership
from the shared-annotation rule. Those operations need their own checks; this decision
does not grant new rights to them. No author-only annotation restriction is introduced.

Use direct resource lookup, not enumeration of all a user's collections. Resolve the
owning collection for tag/span-only endpoints. Verify documents/chunks, ranges, and
provider-returned IDs against the authorized scope. Annotation edits must not implicitly
attach new chunks to a collection as a side effect. Source-read permission is also needed
when an authorized membership operation adds a source document/chunk.

The same document/chunk may belong to several collections; access through one does not
grant access to annotations in another. Preserve this distinction in cache keys, service
calls, and query filters. Public corpus access is separate from private collection data.
Validate an entire small batch before mutation; authorization failure is not a successful
best-effort item. Do not fail open on permission-store errors.

## Local real-time Document view

'Real time' means responsive tag annotation in Document view, especially AI-generated
automatic annotations being **displayed immediately as they are saved/streamed**.
Generation is request-scoped; stored results survive cancellation (ADR 0003).

This does not require cross-browser synchronization, WebSockets, collaborative text
editing, or a new durable-job system. Preserve annotation editing by shared users without
promising that one user's view is automatically synchronized with another user's changes.
Show pending/saved/failed states and discard late responses from a different context.
Do not infer a guarantee against concurrent edit overwrites from local responsiveness.

## Verification

Shared users can create/edit/review/delete annotations within the authorized collection
but cannot add/remove documents or chunks, including through bulk endpoints or annotation
side effects. Unrelated/anonymous users are denied; explicit owner/admin actions retain
separate tests. Check mixed-scope batches, revocation, and member-list access.

Test progressive AI results and cancellation in Document view, plus collection switching
for a shared chunk and late completion after navigation/logout. Denied operations do not
perform protected reads, writes, or external provider calls. Treat ownership/sharing
writes more cautiously than ordinary best-effort annotation work.
