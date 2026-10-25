<template>
  <div class="attributes q-pa-md">
    <div class="row items-center q-col-gutter-sm q-mb-md">
      <div class="text-h5 text-weight-medium col-12 col-sm-auto" data-testid="attributes-title">
        Attributes ({{ shown.length }})
      </div>
      <div class="col-auto">
        <CreateButton :disable="!collectionId || !tagsReady" data-testid="attribute-create" @click="createAttribute" />
      </div>
      <div class="col-grow col-sm-auto">
        <q-input v-model="filter" dense outlined clearable debounce="200" placeholder="Search" aria-label="Search attributes">
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
    <q-banner v-else-if="tagsFailed" rounded class="bg-red-1 text-negative q-mb-md" role="alert" data-testid="attribute-tags-error">
      The tags could not be loaded, so attributes cannot be created or edited.
      <template #action>
        <q-btn flat no-caps label="Try again" @click="loadTags" />
      </template>
    </q-banner>

    <div v-if="loading && !attributes.length" class="row justify-center q-pa-lg">
      <q-spinner size="32px" color="primary" />
    </div>

    <div v-else-if="!shown.length && !error" class="text-grey-8 q-pa-md" data-testid="attributes-empty">
      <template v-if="attributes.length">No attributes match.</template>
      <template v-else>
        No attributes yet. An attribute classifies approved annotations, for example a speaker type with the values
        politician and journalist; its values are assigned in the Annotations tab.
      </template>
    </div>

    <q-card
      v-for="attribute in shown"
      :key="attribute.id"
      flat
      bordered
      class="attribute q-mb-md"
      :class="{ 'attribute--retired': attribute.retired }"
      data-testid="attribute"
    >
      <q-card-section class="row items-start no-wrap q-pb-sm">
        <div class="col">
          <div class="row items-center q-gutter-x-sm">
            <span class="text-h6 attribute__name" data-testid="attribute-name">{{ attribute.name }}</span>
            <q-badge v-if="attribute.retired" color="grey-7" label="Retired" />
          </div>
          <div class="text-caption text-grey-8 q-mt-xs">
            {{ attribute.cardinality === Cardinality.single ? 'One value' : 'Several values' }} per annotation ·
            <span data-testid="attribute-tags">{{ appliesTo(attribute, tags) }}</span>
          </div>
          <div v-if="attribute.description" class="text-body2 q-mt-sm attribute__description">{{ attribute.description }}</div>
        </div>
        <div class="col-auto row no-wrap">
          <q-btn
            flat
            round
            dense
            color="primary"
            icon="edit"
            :disable="!tagsReady"
            :aria-label="`Edit ${attribute.name}`"
            @click="editAttribute(attribute)"
          >
            <q-tooltip>Edit</q-tooltip>
          </q-btn>
          <q-btn
            flat
            round
            dense
            color="grey-8"
            :icon="attribute.retired ? 'unarchive' : 'archive'"
            :aria-label="`${attribute.retired ? 'Restore' : 'Retire'} ${attribute.name}`"
            @click="setAttributeRetired(attribute, !attribute.retired)"
          >
            <q-tooltip>{{ attribute.retired ? 'Restore: can be assigned again' : 'Retire: keeps its values, but no new ones are assigned' }}</q-tooltip>
          </q-btn>
          <q-btn flat round dense color="negative" icon="delete" :aria-label="`Delete ${attribute.name}`" @click="removeAttribute(attribute)">
            <q-tooltip>Delete</q-tooltip>
          </q-btn>
        </div>
      </q-card-section>

      <q-separator inset />

      <q-list dense class="q-py-xs">
        <q-item
          v-for="value in valuesOf(attribute)"
          :key="value.id"
          :class="{ 'attribute--retired': value.retired }"
          data-testid="attribute-value"
        >
          <q-item-section>
            <q-item-label>
              <span data-testid="attribute-value-label">{{ value.label }}</span>
              <q-badge v-if="value.kind !== ValueKind.value" outline color="primary" class="q-ml-sm" :label="KIND_LABELS[value.kind ?? ValueKind.value]" />
              <q-badge v-if="value.retired" color="grey-7" class="q-ml-sm" label="Retired" />
            </q-item-label>
            <q-item-label v-if="value.description || value.examples?.length" caption class="attribute__description">
              {{ value.description }}<template v-if="value.description && value.examples?.length"> · </template>
              <template v-if="value.examples?.length">e.g. {{ value.examples.join('; ') }}</template>
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <div class="row no-wrap">
              <q-btn flat round dense size="sm" color="primary" icon="edit" :aria-label="`Edit ${value.label}`" @click="editValue(attribute, value)" />
              <q-btn
                flat
                round
                dense
                size="sm"
                color="grey-8"
                :icon="value.retired ? 'unarchive' : 'archive'"
                :aria-label="`${value.retired ? 'Restore' : 'Retire'} ${value.label}`"
                @click="setValueRetired(attribute, value, !value.retired)"
              />
              <q-btn flat round dense size="sm" color="negative" icon="delete" :aria-label="`Delete ${value.label}`" @click="removeValue(attribute, value)" />
            </div>
          </q-item-section>
        </q-item>
        <q-item v-if="!valuesOf(attribute).length">
          <q-item-section class="text-grey-7">No values yet.</q-item-section>
        </q-item>
      </q-list>

      <q-card-actions>
        <q-btn
          flat
          no-caps
          color="primary"
          icon="add"
          label="Add value"
          :disable="(attribute.values ?? []).length >= MAX_VALUES"
          :aria-label="`Add a value to ${attribute.name}`"
          @click="addValue(attribute)"
        />
      </q-card-actions>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useQuasar } from 'quasar'
import { useRoute } from 'vue-router'

import {
  Cardinality, ValueKind, type Attribute, type AttributeValue, type PatchAttribute, type PatchAttributeValue,
  type PostAttribute, type PostAttributeValue
} from 'src/generated/api'
import CreateButton from 'src/shared/ui/CreateButton.vue'
import useConfirmDelete from 'src/shared/useConfirmDelete'
import { errorNotification, successNotification } from 'src/shared/notification'
import { useTagsStore } from 'src/features/annotations/tagsStore'
import { AttributeWriteError, useAttributesStore } from './attributesStore'
import { KIND_LABELS, MAX_VALUES, appliesTo } from './attributeForm'
import AttributeDialog from './AttributeDialog.vue'
import AttributeValueDialog from './AttributeValueDialog.vue'

const $q = useQuasar()
const route = useRoute()
const confirmDelete = useConfirmDelete()
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

const shown = computed(() => {
  const needle = (filter.value ?? '').trim().toLowerCase()
  return attributes.value.filter(a =>
    (showRetired.value || !a.retired) &&
    (!needle || a.name.toLowerCase().includes(needle) || (a.values ?? []).some(v => v.label.toLowerCase().includes(needle))))
})

function valuesOf (attribute: Attribute): AttributeValue[] {
  return (attribute.values ?? []).filter(v => showRetired.value || !v.retired)
}

// The dialogs need the collection's tags (the options, and which applicable ids are deleted
// tags), so creating and editing wait for them.
const tagsReady = ref(false)
const tagsFailed = ref(false)
let tagRequest = 0

async function loadTags () {
  const id = collectionId.value
  const request = ++tagRequest
  tagsReady.value = false
  tagsFailed.value = false
  if (!id) return
  await tagsStore.fetchTagsByCollection(id)
  if (request !== tagRequest) return
  tagsFailed.value = !!tagsStore.error
  tagsReady.value = !tagsFailed.value
}

function reload () {
  if (!collectionId.value) return
  void store.load(collectionId.value)
  void loadTags()
}

onMounted(reload)
watch(collectionId, reload)

/** Runs a list action, reporting its outcome; a refusal shows the backend's message. */
async function run (action: () => Promise<unknown>, done: string): Promise<boolean> {
  try {
    await action()
    successNotification(done)
    return true
  } catch (e) {
    errorNotification(e instanceof Error ? e.message : 'The change could not be saved.')
    return false
  }
}

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
  $q.dialog({
    component: AttributeDialog,
    componentProps: {
      attribute,
      tags: () => tags.value,
      save: (patch: PatchAttribute) => store.updateAttribute(id, attribute.id, patch)
    }
  }).onOk((saved: Attribute | null) => {
    if (saved) successNotification('Attribute saved')
  })
}

function setAttributeRetired (attribute: Attribute, retired: boolean) {
  void run(() => store.updateAttribute(collectionId.value, attribute.id, { retired }),
    `"${attribute.name}" ${retired ? 'retired' : 'restored'}`)
}

/** Offers retiring instead when the backend refused a deletion because annotations hold values. */
function offerRetire (e: unknown, retire: (() => void) | null) {
  const message = e instanceof Error ? e.message : 'It could not be deleted.'
  if (!(e instanceof AttributeWriteError) || e.status !== 409 || !retire) {
    errorNotification(message)
    return
  }
  $q.dialog({
    title: 'Still in use',
    message,
    ok: { label: 'Retire instead', color: 'primary', unelevated: true },
    cancel: { label: 'Keep', flat: true, color: 'primary' }
  }).onOk(retire)
}

function removeAttribute (attribute: Attribute) {
  const id = collectionId.value
  confirmDelete({
    title: 'Delete Attribute',
    message: `Delete the attribute "${attribute.name}" and its values? Only an attribute no annotation has a value of can be deleted.`,
    alsoDeletes: async () => ''
  }).onOk(async () => {
    try {
      await store.deleteAttribute(id, attribute.id)
      successNotification(`Attribute "${attribute.name}" deleted`)
    } catch (e) {
      offerRetire(e, attribute.retired ? null : () => setAttributeRetired(attribute, true))
    }
  })
}

function takenKinds (attribute: Attribute): ValueKind[] {
  return (attribute.values ?? []).map(v => v.kind ?? ValueKind.value).filter(kind => kind !== ValueKind.value)
}

function addValue (attribute: Attribute) {
  const id = collectionId.value
  $q.dialog({
    component: AttributeValueDialog,
    componentProps: {
      attributeName: attribute.name,
      takenKinds: takenKinds(attribute),
      save: (value: PostAttributeValue) => store.addValue(id, attribute.id, value)
    }
  }).onOk((saved: Attribute | null) => {
    if (saved) successNotification('Value added')
  })
}

function editValue (attribute: Attribute, value: AttributeValue) {
  const id = collectionId.value
  $q.dialog({
    component: AttributeValueDialog,
    componentProps: {
      attributeName: attribute.name,
      value,
      save: (patch: PatchAttributeValue) => store.updateValue(id, attribute.id, value.id, patch)
    }
  }).onOk((saved: Attribute | null) => {
    if (saved) successNotification('Value saved')
  })
}

function setValueRetired (attribute: Attribute, value: AttributeValue, retired: boolean) {
  void run(() => store.updateValue(collectionId.value, attribute.id, value.id, { retired }),
    `"${value.label}" ${retired ? 'retired' : 'restored'}`)
}

function removeValue (attribute: Attribute, value: AttributeValue) {
  const id = collectionId.value
  confirmDelete({
    title: 'Delete Value',
    message: `Delete the value "${value.label}" of "${attribute.name}"? Only a value no annotation has can be deleted.`,
    alsoDeletes: async () => ''
  }).onOk(async () => {
    try {
      await store.deleteValue(id, attribute.id, value.id)
      successNotification(`Value "${value.label}" deleted`)
    } catch (e) {
      offerRetire(e, value.retired ? null : () => setValueRetired(attribute, value, true))
    }
  })
}
</script>

<style scoped>
.attributes {
  max-width: 1100px;
}

.attribute__name,
.attribute__description {
  overflow-wrap: anywhere;
}

.attribute__description {
  white-space: pre-line;
}

.attribute--retired .attribute__name,
.attribute--retired [data-testid='attribute-value-label'] {
  color: rgba(0, 0, 0, 0.5);
  text-decoration: line-through;
}
</style>
