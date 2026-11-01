<template>
  <div class="attributes q-pa-md">
    <div class="row items-center q-col-gutter-sm q-mb-md">
      <div class="text-h5 text-weight-medium col-12 col-sm-auto" data-testid="attributes-title">
        Attributes ({{ shown.length }})
      </div>
      <div class="col-auto">
        <CreateButton :disable="!collectionId || tagsState !== 'ready'" data-testid="attribute-create" @click="createAttribute" />
      </div>
      <div class="col-grow col-sm-auto">
        <q-input v-model="filter" dense outlined clearable debounce="200" placeholder="Search" aria-label="Search attributes and values">
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
      </div>
      <q-space class="gt-xs" />
      <div class="col-auto">
        <q-toggle v-model="showRetired" label="Show retired" data-testid="attribute-show-retired" />
      </div>
    </div>

    <q-banner v-if="error" rounded class="bg-red-1 text-negative q-mb-md" role="alert">
      {{ error }}
      <template #action>
        <q-btn flat no-caps label="Try again" @click="reload" />
      </template>
    </q-banner>
    <q-banner v-else-if="tagsState === 'failed'" rounded class="bg-red-1 text-negative q-mb-md" role="alert" data-testid="attribute-tags-error">
      The tags could not be loaded, so attributes cannot be created or edited.
      <template #action>
        <q-btn flat no-caps label="Try again" @click="loadTags" />
      </template>
    </q-banner>

    <!-- A match the Show retired setting hides is said, not shown and not left unexplained. -->
    <div v-if="search.hiddenMatches" class="row items-center q-gutter-x-sm text-grey-8 q-mb-sm" data-testid="attribute-hidden-matches">
      <span>{{ plural(search.hiddenMatches, 'retired match', 'retired matches') }} hidden.</span>
      <q-btn flat dense no-caps color="primary" label="Show retired" @click="showRetired = true" />
    </div>

    <div v-if="loading && !attributes.length" class="row justify-center q-pa-lg">
      <q-spinner size="32px" color="primary" />
    </div>

    <div v-else-if="!shown.length && !error" class="text-grey-8 q-pa-md" data-testid="attributes-empty">
      <template v-if="attributes.length && !search.hiddenMatches">No attributes match.</template>
      <template v-else-if="!attributes.length">
        No attributes yet. An attribute classifies approved annotations, for example a speaker type with the values
        politician and journalist; its values are assigned in the Annotations tab.
      </template>
    </div>

    <q-card
      v-for="{ attribute, values, scope } in cards"
      :key="attribute.id"
      flat
      bordered
      class="attribute q-mb-md"
      :class="{ 'attribute--retired': attribute.retired }"
      data-testid="attribute"
    >
      <q-card-section class="row items-start no-wrap q-pb-xs">
        <div class="col">
          <div class="row items-center q-gutter-x-sm">
            <span class="text-h6 attribute__name" data-testid="attribute-name">
              <HighlightedText :text="attribute.name" :needle="filter" />
            </span>
            <q-badge v-if="attribute.retired" color="grey-7" label="Retired" />
          </div>
          <div class="text-caption text-grey-8" data-testid="attribute-cardinality">
            {{ attribute.cardinality === Cardinality.multi ? 'Multiple values per annotation' : 'One value per annotation' }}
          </div>
        </div>
        <div class="col-auto row no-wrap">
          <q-btn
            flat
            round
            dense
            color="primary"
            icon="edit"
            :disable="tagsState !== 'ready'"
            :aria-label="`Edit ${attribute.name}`"
            @click="editAttribute(attribute)"
          >
            <q-tooltip>Edit the attribute and its values</q-tooltip>
          </q-btn>
          <q-btn
            flat
            round
            dense
            color="grey-8"
            :icon="attribute.retired ? 'unarchive' : 'archive'"
            :loading="retiring.has(attribute.id)"
            :aria-label="`${attribute.retired ? 'Restore' : 'Retire'} ${attribute.name}`"
            @click="setAttributeRetired(attribute, !attribute.retired)"
          >
            <q-tooltip>{{ attribute.retired ? 'Restore: can be assigned again' : 'Retire: annotations keep its values, but no new ones are assigned' }}</q-tooltip>
          </q-btn>
        </div>
      </q-card-section>

      <q-card-section class="q-pt-none">
        <ClampedText
          v-if="attribute.description"
          :text="attribute.description"
          class="text-body2 q-mb-sm"
          data-testid="attribute-description"
        />

        <div class="attribute__field">
          <div class="attribute__field-label text-caption text-grey-8">Applies to</div>
          <div class="col" data-testid="attribute-tags">
            <span v-if="scope.kind === 'all'">All tags</span>
            <span v-else-if="scope.kind === 'none'" class="text-grey-7">No tags</span>
            <span v-else-if="scope.kind === 'loading'" class="text-grey-7">
              <q-spinner size="14px" class="q-mr-xs" />Loading tags…
            </span>
            <span v-else-if="scope.kind === 'failed'" class="text-grey-7">Tags could not be loaded</span>
            <span v-else-if="!scope.names.length" class="text-grey-7">Only deleted tags</span>
            <WrappingBadges v-else :watch-key="scope" :badge-height="22" :expanded-lines="4">
              <span v-for="tagName in scope.names" :key="tagName" class="attribute__chip">{{ tagName }}</span>
              <span v-if="scope.deleted" class="attribute__chip attribute__chip--muted">
                {{ plural(scope.deleted, 'deleted tag') }}
              </span>
            </WrappingBadges>
          </div>
        </div>

        <div class="attribute__field q-mt-xs">
          <!-- Counted like the Edit dialog: the ordinary values, not Unknown / Not applicable. -->
          <div class="attribute__field-label text-caption text-grey-8">Values ({{ values.filter(v => !isSpecial(v)).length }})</div>
          <div class="col">
            <WrappingBadges
              v-if="values.length"
              :watch-key="[values.map(v => v.id), filter]"
              :lines="2"
              :expanded-lines="8"
              :badge-height="22"
            >
              <span
                v-for="value in values"
                :key="value.id"
                class="attribute__chip"
                :class="{
                  'attribute__chip--special': isSpecial(value),
                  'attribute__chip--retired': value.retired,
                  'attribute__chip--match': matches(valueName(value), filter)
                }"
                data-testid="attribute-value"
              >
                <HighlightedText :text="valueName(value)" :needle="filter" data-testid="attribute-value-label" />
                <span v-if="value.retired" class="attribute__chip-badge">Retired</span>
                <q-tooltip v-if="value.description" max-width="320px">{{ value.description }}</q-tooltip>
              </span>
            </WrappingBadges>
            <span v-else class="text-grey-7">
              {{ attribute.values?.length ? 'Only retired values, which are hidden' : 'No values yet' }}
            </span>
          </div>
        </div>
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useQuasar } from 'quasar'
import { useRoute } from 'vue-router'

import { Cardinality, type Attribute, type PatchAttribute, type PostAttribute } from 'src/generated/api'
import CreateButton from 'src/shared/ui/CreateButton.vue'
import ClampedText from 'src/shared/ui/ClampedText.vue'
import WrappingBadges from 'src/shared/ui/WrappingBadges.vue'
import { errorNotification, successNotification } from 'src/shared/notification'
import { plural } from 'src/shared/plural'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import { useAttributesStore } from './attributesStore'
import { isSpecial, tagScope, valueName, type TagsState, type ValueActions } from './attributeForm'
import { matches, searchAttributes } from './attributeSearch'
import AttributeDialog from './AttributeDialog.vue'
import HighlightedText from './HighlightedText.vue'

const $q = useQuasar()
const route = useRoute()
const store = useAttributesStore()
const { attributes, loading, error } = storeToRefs(store)
const tagsStore = useTagsStore()
const { tags } = storeToRefs(tagsStore)

const filter = ref<string | null>('')
const showRetired = ref(true)

const collectionId = computed(() => {
  const value = route.params.collectionId
  return typeof value === 'string' ? value : ''
})

const search = computed(() => searchAttributes(attributes.value, filter.value, showRetired.value))
const shown = computed(() => search.value.shown)

// The dialogs need the collection's tags (the options, and which applicable ids are deleted
// tags), so creating and editing wait for them; until then no card names a tag.
const tagsState = ref<TagsState>('loading')
let tagRequest = 0

async function loadTags () {
  const id = collectionId.value
  const request = ++tagRequest
  tagsState.value = 'loading'
  if (!id) return
  await tagsStore.fetchTagsByCollection(id)
  if (request !== tagRequest) return
  tagsState.value = tagsStore.error ? 'failed' : 'ready'
}

function reload () {
  if (!collectionId.value) return
  void store.load(collectionId.value)
  void loadTags()
}

const cards = computed(() => shown.value.map(card => ({
  ...card,
  scope: tagScope(card.attribute, tags.value, tagsState.value)
})))

onMounted(reload)
watch(collectionId, reload)

function createAttribute () {
  const id = collectionId.value
  $q.dialog({
    component: AttributeDialog,
    componentProps: {
      tags: () => tags.value,
      save: (payload: PostAttribute) => store.createAttribute(id, payload)
    }
  }).onOk((created: Attribute | null) => {
    if (created) successNotification(`Attribute "${created.name}" created`)
  })
}

function editAttribute (attribute: Attribute) {
  const id = collectionId.value
  const valueActions: ValueActions = {
    addValue: value => store.addValue(id, attribute.id, value),
    updateValue: (valueId, patch) => store.updateValue(id, attribute.id, valueId, patch),
    setSpecialValue: (current, kind, allowed) => store.setSpecialValue(id, current, kind, allowed)
  }
  $q.dialog({
    component: AttributeDialog,
    componentProps: {
      attribute,
      tags: () => tags.value,
      save: (patch: PatchAttribute) => store.updateAttribute(id, attribute.id, patch),
      valueActions
    }
  }).onOk((saved: Attribute | null) => {
    if (saved) successNotification('Attribute saved')
  })
}

// Attributes whose retire or restore is running, so it is not sent twice.
const retiring = reactive(new Set<string>())

async function setAttributeRetired (attribute: Attribute, retired: boolean) {
  if (retiring.has(attribute.id)) return
  retiring.add(attribute.id)
  try {
    await store.updateAttribute(collectionId.value, attribute.id, { retired })
    successNotification(`"${attribute.name}" ${retired ? 'retired' : 'restored'}`)
  } catch (e) {
    errorNotification(e instanceof Error ? e.message : 'The change could not be saved.')
  } finally {
    retiring.delete(attribute.id)
  }
}
</script>

<style scoped>
.attributes {
  max-width: 1100px;
}

.attribute__name {
  overflow-wrap: anywhere;
}

.attribute--retired .attribute__name {
  color: rgba(0, 0, 0, 0.5);
  text-decoration: line-through;
}

.attribute__field {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.attribute__field-label {
  flex: none;
  width: 84px;
  line-height: 22px;
}

.attribute__chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  max-width: 100%;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid #d8d8d8;
  background: #f1f1f1;
  color: rgba(0, 0, 0, 0.8);
  font-size: 12px;
  line-height: 20px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attribute__chip--special {
  border-style: dashed;
  border-color: var(--q-primary);
  background: transparent;
  font-style: italic;
}

.attribute__chip--retired {
  color: rgba(0, 0, 0, 0.5);
}

.attribute__chip--retired [data-testid='attribute-value-label'] {
  text-decoration: line-through;
}

.attribute__chip--match {
  border-color: #c9a600;
}

.attribute__chip--muted {
  color: rgba(0, 0, 0, 0.55);
  background: transparent;
}

.attribute__chip-badge {
  padding: 0 4px;
  border-radius: 3px;
  background: #757575;
  color: #fff;
  font-size: 10px;
  line-height: 14px;
}

@media (max-width: 599px) {
  .attribute__field {
    flex-direction: column;
    gap: 2px;
  }

  .attribute__field-label {
    width: auto;
    line-height: 16px;
  }
}
</style>
