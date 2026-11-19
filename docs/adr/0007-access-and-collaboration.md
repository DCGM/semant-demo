# ADR 0007 - Annotation editing without membership editing

Status: adopted and implemented across #201, #206, #207 and #209; amended for corpus
document rights by #279 (2026-11-18, below). Future collaborative real-time synchronization
is outside the current contract.
Date: 2026-10-07. Q1/Q4 clarification supersedes the earlier read-only-share proposal.

## Permission boundary

Authenticate at the HTTP boundary; enforce resource-specific authorization in service
functions, including non-HTTP callers. Small functions in `user_collections/access.py` are
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
`semant_demo/features/user_collections/access.py`:

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
search without a collection or tags) cover public documents only; see "Corpus document
rights" below (#279). Search tag filters (#205): every
requested tag must belong to a collection the user can read, and to the searched
collection when one is given; unknown, malformed and inaccessible tags all get the same
"Tag not found" (anonymous users: 401). This is checked before any embedding or
retrieval, also for tags sent without a selected tag kind.

## Corpus document rights (#279, decided 2026-11-18)

Private collection data (membership, annotations, tags) and source-document rights are
related but distinct. A corpus document's rights come from its source library record,
`Documents.public` (copied by the Kramerius metadata sync, docs/DATA_MAINTENANCE.md):

| `Documents.public` | Without a collection (anonymous or signed in) | Through a collection the user can read |
| --- | --- | --- |
| `true` | readable | readable |
| `false` (UI: **Restricted**) | not found | readable when the document belongs to the collection |
| no value (UI: **Access unknown**) | not found | readable when the document belongs to the collection |

- **Signing in is not enough.** A restricted or unknown document is readable only through a
  specific collection the user owns or reads through sharing, *and* the document's link to
  that collection (`Documents.collection`). Membership is document-level: such a read shows
  all the document's chunks, also those not selected as collection chunks (see above). A
  document or chunk id, or a collection id the user cannot read or that does not hold the
  document, grants nothing. Unknown and unreadable documents get the same "not found".
- **One rule, applied at the service boundary.** `features/documents/service.py`
  (`readable_document`) decides every single-document read (metadata, chunk count, passage
  window, adjacent chunks, page chunks, page manifest and assets; also for MCP, which calls
  anonymously); every corpus-wide read applies it inside the store query, before ranking,
  limits, pagination and counts: document browse and search, passage search and its readback
  by client ids, Search chat, RAG, ranked-result analytics and the corpus overview and
  distributions (`DocumentRepository`, `ChunkQuery.readable_collection_id`,
  `CorpusAnalyticsRepository`). Unscoped Explore is public-only; a selected collection scope
  adds that collection's documents, never the union of every collection a user can read.
- **Page assets.** The browser loads scans and layout files without a bearer token. A public
  document's assets need none and are cached as `public, no-cache` (revalidated with `ETag`
  on every use, so a document that stops being public is not served from a cache). The page
  manifest read through a collection gives a restricted or unknown document signed asset URLs
  (`features/documents/asset_access.py`: an HMAC over document, collection, user and expiry);
  every asset read with one checks again that the user can read that collection and that it
  still holds the document, and such responses are `private, no-store`.
- **Adding documents.** An owner can add a document or chunk to a collection only when the
  document is already readable by them: public, or linked to a collection they can read
  (`access.require_document_addable`). Owning a collection does not unlock a restricted id.
- **Uploaded documents (#785).** A text document uploaded into a collection by its owner
  ([TEXT_UPLOAD.md](../TEXT_UPLOAD.md)) is created with `public` false, so this rule alone
  governs it; nothing the client sends can make it public. It is linked to its collection only
  after all its chunks and vectors are stored, so a failed upload is readable by nobody.
- **Revocation and removal.** Unsharing a collection or removing the document from it denies
  that route at the next request, including signed asset URLs already handed out. Existing
  memberships, annotations and sharing are never changed by the rule.
- **Annotations stay collection data.** A collection's annotation views (concordance,
  exports, span chat) are authorized by the collection, not by document rights; they read
  their annotated documents whatever their rights.

There is no per-document ACL, no source-library login or entitlement federation, and no
generalized permission engine: the collection owner/shared-user rights above are the only
route to a document that is not public.

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
