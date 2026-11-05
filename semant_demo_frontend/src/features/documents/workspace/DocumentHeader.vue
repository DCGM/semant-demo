<template>
  <!-- One row of fixed height (#600): the title never wraps; the whole of it, the subtitle
       and the byline are in its tooltip and the Document panel of the right sidebar. -->
  <header class="document-header" data-testid="document-header">
    <BackLink v-if="back" :to="back.to" :label="back.label" :aria-label="back.ariaLabel" class="document-header__back" />
    <div class="document-header__name" :title="fullTitle">
      <h1 class="document-header__title" data-testid="document-title">{{ title }}</h1>
      <span v-if="detail" class="document-header__detail">{{ detail }}</span>
    </div>
    <OriginalSourceLink
      v-if="document"
      :document="document"
      :page-id="pageId"
      label="Original"
      class="document-header__source"
    />
    <q-space />
    <slot />
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import type { Document } from 'src/generated/api'
import BackLink from 'src/shared/ui/BackLink.vue'
import OriginalSourceLink from '../OriginalSourceLink.vue'

// The header of the public and the collection document views: the back link, the title with
// the subtitle or byline after it, the link to the original and the owner's context (the
// default slot, e.g. the collection).
const props = withDefaults(defineProps<{
  /** The title shown; a placeholder while the document loads or when it is not available. */
  title: string
  /** Shown after the title, muted, and cut first when the row is too narrow. */
  detail?: string
  document?: Document | null
  /** The original is opened at this page. */
  pageId?: string | null
  back?: { to: RouteLocationRaw, label: string, ariaLabel?: string } | null
}>(), { detail: '', document: null, pageId: null, back: null })

const fullTitle = computed(() => [props.title, props.detail].filter(Boolean).join(' · '))
</script>

<style scoped>
.document-header {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: none;
  height: 48px;
  padding: 0 16px;
  background: #fff;
  border-bottom: 1px solid #e2e8f0;
  color: #1f2a37;
  white-space: nowrap;
}

.document-header__back {
  flex: none;
  margin-bottom: 0;
}

/* The title shrinks before anything else, then the detail inside it. */
.document-header__name {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
}

.document-header__title {
  flex: 0 1 auto;
  min-width: 4em;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 1.05rem;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: normal;
}

.document-header__detail {
  flex: 0 100 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 0.85rem;
  color: #64748b;
}

.document-header__source {
  flex: none;
  font-size: 0.85rem;
}

/* Clear of the drawers' collapse buttons, which overhang the edges on a wide screen. */
@media (min-width: 1024px) {
  .document-header {
    padding: 0 28px;
  }
}

@media (max-width: 599px) {
  .document-header {
    gap: 8px;
    padding: 0 8px;
  }
}
</style>
