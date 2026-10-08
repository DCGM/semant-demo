# Right Sidebar

This document describes the application-level right sidebar of the frontend, how it works
and how to add a tool (panel) to it. It was introduced by PR #194 and integrated into the
refactored frontend in #209.

## Overview

The right sidebar is the place for page-specific tools, such as the summary of search
results on the search page. It is defined once in the main layout; every page decides
which tools (if any) it shows there.

- **Content switches with the page.** A page registers its tools while it is mounted. When
  the user navigates away, the tools are removed automatically.
- **Hidden without content.** When the current page provides no tool, the sidebar and its
  toggle button in the header are not shown.
- **Multiple tools.** A page can provide several tools. Each one has an icon in the rail on
  the edge of the sidebar; the user switches between them by clicking the icons.
- **Explicit context.** A tool works only on what its page passes to it through props
  (e.g. the search summary gets the current search results and the selected result ids).
  It does not read feature state from the sidebar or from unrelated global stores, and it
  reports user actions back to the page through events (a citation in the summary moves
  the user to the cited result).
- **Behaves like the left drawer.** It pushes the page content on wide screens, becomes an
  overlay on narrow screens (below 1024 px) and has a mini state that shows only the
  narrow (48 px) icon rail. The open and mini states are not remembered between pages.

The document view (`/collections/:cid/documents/:did/v1`) still has its own right drawer
(tags, AI assist, document metadata) inside its page layout; it is not a sidebar panel yet.

## 1. Files

All files are in `semant_demo_frontend/src`.

| File | Purpose |
|------|---------|
| `app/sidebar/RightSidebar.vue` | The sidebar shell (`q-drawer`). Placed once in `layouts/MainLayout.vue`. Knows nothing about the individual pages. |
| `app/sidebar/RightSidebarPanel.vue` | Wrapper a page uses to add a tool to the sidebar. |
| `app/sidebar/rightSidebarStore.ts` | Pinia store with the shell state only: registered panels, active panel, open and mini states, the element panels render into. |
| `features/<feature>/` | The tools themselves, next to the feature they belong to, e.g. `features/search/SearchSummaryPanel.vue`. |

The store holds no feature or business state (results, summaries, documents). That state
stays with the page and its feature composables.

## 2. How It Works

1. `RightSidebar.vue` renders the icon rail, the title of the active panel and an empty
   container. When mounted, it stores the container element in `rightSidebarStore.targetEl`.
2. A page renders `<RightSidebarPanel>`. On mount it registers itself (`id`, `label`,
   `icon`, `order`) in the store; on unmount it removes the registration it made.
3. `RightSidebarPanel` moves its slot content into the sidebar container using Vue's
   `<Teleport>`. Only the DOM is moved; in the component tree the content is still a child
   of the page, so the page passes props to it and listens to its events directly.
4. The sidebar is shown whenever at least one panel is registered (`hasPanels`).

Notes on the implementation:

- `register()` returns the function that removes exactly that registration. A second panel
  with an id that is already registered is refused with a warning, and removing it does
  not remove the first one.
- The teleport targets the element itself, not a CSS selector. During the first load a
  page can mount before the layout is attached to the document, and a selector would not
  be found (Vue 3.3 has no `<Teleport defer>`).
- Inactive panels are hidden with `v-show`, not destroyed, so a tool keeps its state when
  the user switches to another one and back.
- The sidebar does not scroll with the page; it has its own scroller (`q-scroll-area`),
  like the left drawer. This requires the right drawer to be fixed in the layout, i.e. the
  uppercase `R` in `<q-layout view="hHh LpR fff">` in `MainLayout.vue`.
- The drawer does not use the `mini` slot of `q-drawer`, as that would recreate the
  content and destroy the teleport target. The mini state is handled with `v-show`.

## 3. Adding a Tool to a Page

### Step 1: Create the tool component

Put the component in the feature it belongs to (`features/<feature>/`). It should not know
that it is displayed in a sidebar. It gets its data through props and reports user actions
through events, so it can be reused on any page.

```vue
<!-- features/notes/NotesPanel.vue -->
<template>
  <q-input
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    type="textarea"
    outlined
  />
  <q-btn label="Save" color="primary" class="q-mt-sm" @click="emit('save')" />
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  save: []
}>()
</script>
```

Keep larger logic (API calls, state) in a composable of the feature, as done for the
search summary in `features/search/useSearchSummary.ts`. Network calls go through the
shared transport (`src/shared/api`: generated client via `useApi()`, NDJSON streams via
`postNdjson()`); do not configure another client. Give the work the context it belongs to
and drop answers that arrive after the context changed (see section 5).

### Step 2: Use it in the page

Wrap the tool in `RightSidebarPanel`. Anywhere in the page template is fine; the content
ends up in the sidebar.

```vue
<template>
  <q-page>
    <!-- page content -->

    <RightSidebarPanel id="my-page-notes" label="Notes" icon="edit_note" :order="1">
      <NotesPanel v-model="notes" @save="saveNotes" />
    </RightSidebarPanel>
  </q-page>
</template>

<script setup lang="ts">
import RightSidebarPanel from 'src/app/sidebar/RightSidebarPanel.vue'
import NotesPanel from 'src/features/notes/NotesPanel.vue'
// ...
</script>
```

`RightSidebarPanel` props:

| Prop | Type | Description |
|------|------|-------------|
| `id` | `string` | Unique identifier of the panel among the panels shown at the same time. |
| `label` | `string` | Title shown in the sidebar header and in the tooltip (and accessible name) of the rail icon. |
| `icon` | `string` | Icon in the rail ([Material icon](https://fonts.google.com/icons) name). |
| `order` | `number` | Optional, default `0`. Panels are sorted in ascending order. |

To show a tool only in some situations, use `v-if` on `RightSidebarPanel`. For example,
the search page shows the summary only while there are results or a search is running:

```vue
<RightSidebarPanel v-if="results.length || loading" id="search-summary" label="Summary" icon="auto_awesome">
```

If no panel remains registered, the whole sidebar is hidden.

### Communication

| Direction | How |
|-----------|-----|
| page → tool | Props of the tool component (its context). They are reactive, as in any other component. |
| tool → page | Events of the tool component, handled by the page. |
| page → sidebar | `useRightSidebarStore()`, e.g. `activate(id)` to switch to a panel and make sure the sidebar is open and expanded. |

Bringing a panel to front from the page:

```ts
import { useRightSidebarStore } from 'src/app/sidebar/rightSidebarStore'

const rightSidebar = useRightSidebarStore()
rightSidebar.activate('search-summary')
```

## 4. Store API

`useRightSidebarStore()` in `app/sidebar/rightSidebarStore.ts`:

| Member | Description |
|--------|-------------|
| `sortedPanels` | Registered panels ordered by `order` (`id`, `label`, `icon`, `order`). |
| `hasPanels` | Whether at least one panel is registered. Controls the visibility of the sidebar. |
| `activePanelId`, `activePanel` | The currently shown panel. |
| `open` | Whether the drawer is open (toggled by the button in the header). |
| `miniState` | Whether only the icon rail is shown. |
| `activate(id)` | Shows the given registered panel, opens the sidebar and leaves the mini state. |
| `toggleOpen()`, `toggleMiniState()` | Toggle the open and mini states. |
| `register(panel)` (returns its removal function), `targetEl` | Used internally by `RightSidebarPanel` and `RightSidebar`. Pages should not call them. |

## 5. Context of a tool

A tool works on an explicit context its page passes in, never on a wider one it finds by
itself. For search results this is `SearchResultsContext` (`features/search/searchResults.ts`):
the response of one search, as retrieved, with an `id` that changes with every new search.
`selectResults(context, scope)` picks the results a tool works on: the first N, all of
them, or exactly the selected ones. It never reruns the query or adds unselected results,
and an empty selection is reported, not widened. Hits keep their source references (chunk
id, document id, page ids); their text is display text, not the canonical text annotation
offsets refer to. Future search-result chat takes the same input.

Requests belong to their context: when the page's context changes (a new search) or a new
request supersedes an old one, the old request is aborted and its late answer is dropped
(`createContextGuard()` in `src/shared/api`), so it can neither show an old result nor end
the new request's loading state.

## 6. Existing Tools

| Page | Panel id | Component | Description |
|------|----------|-----------|-------------|
| Search (`pages/SearchPage.vue`) | `search-summary` | `features/search/SearchSummaryPanel.vue` | Summarization of the current search results (focused: first 3, broader: first 10, extensive: all, selected: the selected results). Citations move the user to the cited result. Logic in `features/search/useSearchSummary.ts`. |
