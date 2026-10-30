<template>
  <q-page>
    <!-- Tags and the attributes that classify their annotations (#331) share one tab of the
         collection; each part keeps its own route, so either can be linked to. -->
    <q-tabs
      dense
      no-caps
      align="left"
      inline-label
      active-color="primary"
      indicator-color="primary"
      class="text-grey-8 q-px-md"
    >
      <q-route-tab name="tags" label="Tags" icon="label" exact :to="{ name: 'collectionTags' }" />
      <q-route-tab name="attributes" label="Attributes" icon="category" exact :to="{ name: 'collectionAttributes' }" />
    </q-tabs>
    <AttributesList v-if="$route.name === 'collectionAttributes'" />
    <TagsAttributesTable v-else />
  </q-page>
</template>

<script setup lang="ts">
import TagsAttributesTable from 'src/features/attributes/TagsAttributesTable.vue'
import AttributesList from 'src/features/attributes/AttributesList.vue'
</script>
