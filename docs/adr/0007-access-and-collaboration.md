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

## Decided for the implementation (#201, 2026-10-07)

The rights left open above were decided by the maintainer and are implemented in
`semant_demo/features/collections/access.py`:

| Operation | Owner | Shared user | Others / admin |
| --- | --- | --- | --- |
| Read collection content, annotations, member list | yes | yes | not found |
| Create/edit/delete annotations, run AI suggestions/review | yes | yes | not found |
| Create/edit/delete tag definitions | yes | yes | not found |
| Add/remove documents or chunks | yes | forbidden | not found |
| Edit metadata (name, description, color), delete collection | yes | forbidden | not found |
| Share/unshare | yes | forbidden | not found |
| Change owner | no | no | admin only (existing explicit action) |

Users without read access get "not found" so other users' collection ids are not
confirmed; anonymous users get 401. A tag or span resolves to its single owning
collection; one referencing no collection or several is treated as inaccessible.
Collection+document requests also require the document to be linked to that collection
(the document's collection reference, not chunk membership, since the Document view
shows non-member chunks of member documents).
Corpus reads without a collection (document metadata, corpus browse, chunk counts,
search without a collection) remain public. Restricting search tag filters to
authorized tags belongs to the Search migration (#205).

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
