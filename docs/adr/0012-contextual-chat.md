# ADR 0012 - Contextual chat in the right sidebar

Status: proposed with #243. Product decisions made by a maintainer on 2026-11-02; the
technical contract below is the target. Delivery starts with a small document chat
prototype (#248, see Delivery); this ADR is refined from what users say about it before
Search and collection chat are built.
Date: 2026-11-02. Parent: #104. Refines ADR 0003 (request-scoped AI) and ADR 0006 (search
chat scope); implemented by #245 (Search), #247 (collection) and #248 (document).

## Context

Three pages get a Chat tool in the shared right sidebar: Search (#245), a user collection
(#247) and a document in a collection (#248). Each must answer only from what its page is
about, and the three must not invent incompatible rules for scope, history, citations and
the backend. Already in place:

- The sidebar shell and panel registration, with page-owned state and `createContextGuard()`
  for stale requests (`docs/RIGHT_SIDEBAR.md`, sections 2-5).
- Source navigation: conversation-wide `S1`, `S2`... labels, the Sources panel and the
  Document panel with *Return to cited passage* (#246, #244), and summary citations that
  scroll the reader (#249).
- ADR 0006 (confirmed): search chat uses the retrieved results or an explicitly selected
  subset, never a wider set; a new search or selection is a new context; chat history
  persistence (Q6) is deferred.
- Backend: `POST /api/rag` (corpus Chat assistant; it takes source text from the client,
  which ADR 0006 does not allow for new chats), `POST /api/summarize/{type}` and the
  document summary route (#249), the streamed span discussion `POST /api/ai/discuss_span`,
  the agentic RAG pipeline with tool calls, `count_annotations`, and the daily AI allowance
  (#396, #408).

## Product decisions (maintainer, 2026-11-02)

1. **History lives in memory, one conversation per scope.** Changing the scope (another
   search, selection, document or collection) starts a new conversation and drops the old
   one; a reload or leaving the page loses it. Nothing is stored on the server; Q6 stays
   deferred.
2. **Which chat a page shows.** Search: Search chat. Collection pages (overview,
   documents, tags...): Collection chat. A document page inside a collection: Document chat
   only, not Collection chat.
3. **Search chat (#245)**
   - Scope: the selected results if any are checked, otherwise all retrieved results of the
     current search. The panel says which ("Asking about 3 selected results").
   - Changing the selection mid-conversation shows a notice; the next question starts a new
     conversation about the new set (ADR 0006).
   - The **Summary panel stays** a separate tool. A *Discuss in chat* action on a summary
     starts a chat about the same result set with the summary as its first assistant message
     (with its citations).
   - Signed-out users may use it under the daily AI allowance and its warnings, like Summary
     and the Chat assistant.
4. **Document chat (#248)**
   - The whole document goes to the model when it fits the feature's input limit. A longer
     document: each question retrieves the most relevant chunks of this document only, and
     the answer says it is based on a part of the document.
   - Asking about a selected passage comes later; the contract below leaves room for it.
   - The span discussion (*Discuss with AI* in an annotation's popover,
     `POST /api/ai/discuss_span`) stays a separate chat about one annotation and its tag.
     Document chat does not replace it.
5. **Collection chat (#247)**
   - It starts with the collection's name, description and document count.
   - More information is fetched by the model, per question, through read-only tools limited
     to the collection: search the collection's text; tags with approved / unresolved
     suggestion / rejected counts (overall or per document); list documents (title, year,
     annotation counts); annotated passages of a tag.
   - Members are not given to the model.
   - #339 stays the tool for explicit annotation-set analysis and inconsistency review; the
     passages tool returns a bounded sample, not a whole annotation set.

## Technical contract (proposed)

### Backend

- **One feature, three routes.** A new `features/chat/` with one service; the routes name
  their scope in the path, so access checks reuse the existing collection/document rules:

  | Route | Scope | Access |
  |---|---|---|
  | `POST /api/search/chat` | `chunk_ids`: the result set the page chose | optional user, allowance |
  | `POST /api/user_collections/{cid}/chat` | the collection | collection read access |
  | `POST /api/user_collections/{cid}/documents/{did}/chat` | the document, which must belong to the collection | collection read access |

- **Request:** `question`, `history` (role + text of earlier turns, bounded like
  `RAG_HISTORY_LIMIT`), and for Search the `chunk_ids` (bounded by the search result limit).
  The server loads every source by ID and rechecks access on each request. The client never
  sends source text, and history never adds sources: earlier answers' citations are reloaded
  only when they are inside the scope.
- **Response:** NDJSON stream, like the span discussion:
  - `{"event": "progress", "step": "search_collection"}` while a tool runs (collection and
    long document chat);
  - `{"event": "delta", "text": ...}`;
  - `{"event": "sources", "sources": [{"citation": N, "chunk_id", "document_id", "order",
    "from_page", "to_page"}]}`;
  - a final `{"event": "end", "coverage": "all" | "part", "used_chunks", "total_chunks"}`
    or `{"event": "error", "message"}`. No `end` means interrupted.
- **Citations:** the model cites `[docN]` as in Summary and RAG; the server maps N to a
  chunk it gave the model and drops citations it cannot map, so the client never gets a
  chunk outside the scope.
- **Tools** (collection chat; document chat uses only its in-document search): the
  collection id and user come from the route, never from the model's arguments; at most 4
  tool calls per question; every tool result is bounded (rows and characters). Tool output
  and document text are data, not instructions.
- **Limits and cost:** one LLM feature `context_chat` in the model catalog with its own
  input/output limits; one AI operation per question, admitted before the stream (429 when
  refused) and settled when it ends or the client disconnects (ADR 0003). An oversized
  input is 413, as in the document summary.
- **Errors** are content-free in logs (questions and document text are user content).

### Frontend

- `features/chat/`: one composable `useScopedChat(scope)` and one `ScopedChatPanel.vue`,
  used by all three pages. The page owns the scope (`SearchResultsContext` plus selection,
  `collectionId`, `collectionId` + `documentId`) and passes it in.
- A scope change, a new question replacing a running one, or unmount aborts the request
  through `createContextGuard()`; a late event cannot reach the new conversation.
- Citations use the conversation-wide `S` labels of #246. Search: a citation selects its
  result and opens it in the Document panel (#244). Collection: the Document panel, with a
  link to open the document in the reader. Document: the reader scrolls to the chunk and
  highlights it, as summary citations do (#249), without touching an open annotation or
  selection.
- The panel shows the scope above the input, the coverage notice for a partial document,
  the allowance warnings, errors, and a *New conversation* action.

## Delivery

1. **Prototype: document chat (#248), first version.** The Chat panel in the document's
   sidebar, the document route with server-side loading and access checks, streamed answers,
   `[S1]` citations that scroll the reader, in-memory history. A document that does not fit
   the input limit is cut to its first chunks with a "based on the first N passages" note,
   as the document summary does; retrieval within the document comes later if users need it.
2. **Feedback** from users on test-main; this ADR is updated with what changes.
3. Then the rest of document chat, Search chat (#245) and collection chat (#247).

## Consequences

- Each child issue implements its route, page wiring and tests on top of the shared
  service and panel; the first one (planned: #248) also adds them.
- The existing Chat assistant (`/api/rag`) is not changed by this ADR. Its client-supplied
  source text and history stay as they are until it is aligned in a separate issue.
- Persistent or shared history, passage scope in document chat, and annotation-set analysis
  (#339) are separate decisions.

## Verification

- Backend: denial for a collection or document without access (including after sharing is
  revoked), a document not in the collection, `chunk_ids` the user may not read, history or
  tool arguments trying to reach another collection, citations outside the scope dropped,
  tool-call and result bounds, allowance admit/settle on success, error and disconnect.
- Search chat (ADR 0006): full retrieved set, selected subset, empty selection, missing or
  revoked sources, no fallback to broader retrieval, selection change starting a new
  conversation.
- Document chat: whole document vs. retrieval with the coverage notice.
- Frontend: scope change and route leave during a stream, a late answer after a new
  question, citation navigation per page, annotation state preserved in the reader.
