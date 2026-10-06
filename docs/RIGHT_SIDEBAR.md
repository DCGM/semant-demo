# Right Sidebar

This document describes the reusable right sidebar of the frontend, how it works and how to add new tools (panels) to it.

## Overview
The right sidebar is a place for page specific tools, such as the summary of search results on the search page. It is defined once in the main layout and every page decides what content (if any) it shows there.

- **Content switches with the page.** A page registers its tools while it is mounted. When the user navigates away, the tools are removed automatically.
- **Hidden without content.** When the current page provides no tool, the sidebar and its toggle button in the header are not shown.
- **Multiple tools.** A page can provide several tools. Each one has an icon in the rail on the edge of the sidebar and the user switches between them by clicking the icons.
- **Communication with the page.** The content of a tool stays part of the page that defines it, so the page and the tool talk to each other through ordinary props and events (e.g. a citation in the summary moves the user to the corresponding search result).
- **Behaves like the left drawer.** It pushes the page content on wide screens, becomes an overlay on narrow screens (below 1024 px) and has a mini state that shows only the narrow (48 px) icon rail. The open and mini states are not remembered between pages.

## 1. Components
All files are in `semant_demo_frontend/src`.

| File | Purpose |
|------|---------|
| `components/rightSidebar/RightSidebar.vue` | The sidebar shell (`q-drawer`). Placed once in `layouts/MainLayout.vue`. Knows nothing about the individual pages. |
| `components/rightSidebar/RightSidebarPanel.vue` | Wrapper a page uses to add a tool to the sidebar. |
| `components/rightSidebar/panels/` | The tools themselves, e.g. `SearchSummaryPanel.vue`. |
| `stores/rightSidebarStore.ts` | Pinia store with the registered panels, the active panel, the open and mini states. |

## 2. How It Works
1. `RightSidebar.vue` renders the icon rail, the title of the active panel and an empty container. When mounted, it stores the container element in `rightSidebarStore.targetEl`.
2. A page renders `<RightSidebarPanel>`. On mount it registers itself (`id`, `label`, `icon`, `order`) in the store, on unmount it unregisters.
3. `RightSidebarPanel` moves its slot content into the sidebar container using Vue's `<Teleport>`. Only the DOM is moved; in the component tree, the content is still a child of the page. That is why the page can pass props to it and listen to its events directly.
4. The sidebar is shown whenever at least one panel is registered (`rightSidebarStore.hasPanels`).

Notes on the implementation:
- The teleport targets the element itself, not a CSS selector. During the first load a page can mount before the layout is attached to the document, and a selector would not be found (Vue 3.3 has no `<Teleport defer>`).
- Inactive panels are hidden with `v-show`, not destroyed, so a tool keeps its state when the user switches to another one and back.
- The sidebar does not scroll with the page, it has its own scroller (`q-scroll-area`), like the left drawer. This requires the right drawer to be fixed in the layout, i.e. the uppercase `R` in `<q-layout view="hHh LpR fff">` in `MainLayout.vue`. With a lowercase `r` the sidebar would scroll together with the page content.
- The drawer does not use the `mini` slot of `q-drawer`, as that would recreate the content and destroy the teleport target. The mini state is handled with `v-show` instead.

## 3. Adding a Tool to a Page

### Step 1: Create the tool component
Put the component in `components/rightSidebar/panels/`. It should not know that it is displayed in a sidebar. It gets its data through props and reports user actions through events, so it can be reused on any page.

```vue
<!-- components/rightSidebar/panels/NotesPanel.vue -->
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

Keep larger logic (API calls, state) in a composable, as done for the search summary in `composables/useSearchSummary.ts`. The page then only connects the composable with the component.

### Step 2: Use it in the page
Wrap the tool in `RightSidebarPanel`. Anywhere in the page template is fine, the content ends up in the sidebar.

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
import RightSidebarPanel from 'src/components/rightSidebar/RightSidebarPanel.vue'
import NotesPanel from 'src/components/rightSidebar/panels/NotesPanel.vue'
// ...
</script>
```

`RightSidebarPanel` props:

| Prop | Type | Description |
|------|------|-------------|
| `id` | `string` | Unique identifier of the panel. Must be unique among the panels shown at the same time. |
| `label` | `string` | Title shown in the sidebar header and in the tooltip of the rail icon. |
| `icon` | `string` | Icon in the rail ([Material icon](https://fonts.google.com/icons) name). |
| `order` | `number` | Optional, default `0`. Panels are sorted in ascending order. |

To show a tool only in some situations, use `v-if` on `RightSidebarPanel`. For example, the search page shows the summary only while there are results or a search is running:

```vue
<RightSidebarPanel v-if="results.length || loading" id="search-summary" label="Summary" icon="auto_awesome">
```

If no panel remains registered, the whole sidebar is hidden.

### Communication
| Direction | How |
|-----------|-----|
| page → tool | Props of the tool component. They are reactive, as in any other component. |
| tool → page | Events of the tool component, handled by the page. |
| page → sidebar | `useRightSidebarStore()`, e.g. `activate(id)` to switch to a panel and make sure the sidebar is open and expanded. |

Example from the search page, where clicking a citation in the summary calls the page's `jumpToResult`. It switches pagination to the right page, highlights the result and scrolls to it:

```vue
<SearchSummaryPanel
  :tokens="searchSummary.tokens"
  ...
  @summarize="searchSummary.summarize"
  @cite="jumpToResult"
/>
```

Bringing a panel to front from the page:

```ts
import { useRightSidebarStore } from 'src/stores/rightSidebarStore'

const rightSidebar = useRightSidebarStore()
rightSidebar.activate('search-summary')
```

## 4. Store API
`useRightSidebarStore()` in `stores/rightSidebarStore.ts`:

| Member | Description |
|--------|-------------|
| `panels`, `sortedPanels` | Registered panels (`sortedPanels` ordered by `order`). |
| `hasPanels` | Whether at least one panel is registered. Controls the visibility of the sidebar. |
| `activePanelId`, `activePanel` | The currently shown panel. |
| `open` | Whether the drawer is open (toggled by the button in the header). |
| `miniState` | Whether only the icon rail is shown. |
| `activate(id)` | Shows the given panel, opens the sidebar and leaves the mini state. |
| `toggleOpen()`, `toggleMiniState()` | Toggle the open and mini states. |
| `register(panel)`, `unregister(id)`, `targetEl` | Used internally by `RightSidebarPanel` and `RightSidebar`. Pages should not call them. |

## 5. Existing Tools
| Page | Panel id | Component | Description |
|------|----------|-----------|-------------|
| Search (`pages/SearchPage.vue`) | `search-summary` | `SearchSummaryPanel.vue` | Summarization of search results with brevity and scope options. Citations move the user to the cited result. Logic in `composables/useSearchSummary.ts`. |
