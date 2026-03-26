<template>
  <div class="col-xs-12 col-sm-6 col-lg-4 col-xl-3">
    <q-card :style="`--project-stripe-color: ${props.collection.color}`" class="fit project-card cursor-pointer" flat title="Enter project" @click="handleEnterProject(props.collection.id)">
      <q-card-section horizontal class="fit">
        <q-card-section class="col column no-wrap">
          <q-item>
            <q-item-section avatar>
              <q-avatar color="primary" text-color="white">
                {{ ownerInitials }}
                <q-tooltip> {{ props.collection.userId }} </q-tooltip>
              </q-avatar>
            </q-item-section>
            <q-item-section>
              <q-item-label class="text-h5" lines="2">
                {{ props.collection.name }}
              </q-item-label>
            </q-item-section>
          </q-item>
          <q-separator />
          <div class="description-container text-caption q-pa-sm col">
            {{ props.collection.description }}
          </div>
          <q-separator />
          <div class="text-caption q-px-sm q-pt-sm col-auto">
            <div class="row no-wrap">
              <span class="col-5"> Created on: </span>
              <span class="col"> {{ createdOn }} </span>
            </div>
            <div class="row no-wrap">
              <span class="col-5"> Last modified: </span>
              <span class="col"> {{ updatedOn }} </span>
            </div>
          </div>
        </q-card-section>
        <q-separator vertical />
        <q-card-actions vertical class="justify-around no-wrap">
          <q-btn round flat icon="input" color="primary" @click="handleEnterProject(props.collection.id)">
            <q-tooltip> Enter project </q-tooltip>
          </q-btn>
          <q-btn
            round
            flat
            icon="favorite"
            color="red"
            @click.stop="handleToggleFavorite"
          >
            <q-tooltip> Add to favorites </q-tooltip>
          </q-btn>
          <q-btn round flat icon="edit" color="indigo-12" @click.stop="handleEditProject">
            <q-tooltip> Edit project info </q-tooltip>
          </q-btn>
          <q-btn round flat icon="delete" color="negative" @click.stop="handleDeleteProject">
            <q-tooltip> Delete project </q-tooltip>
          </q-btn>
        </q-card-actions>
      </q-card-section>
    </q-card>
  </div>
</template>

<script setup lang="ts">
import { Collection } from 'src/models/collection'
import { computed } from 'vue'

interface Props {
  collection: Collection
}

const emit = defineEmits(['edit', 'delete', 'enter'])

const props = defineProps<Props>()

const createdOn = computed(() => {
  return props.collection.createdAt.toLocaleString()
})
const updatedOn = computed(() => {
  return props.collection.updatedAt.toLocaleString()
})

const ownerInitials = computed(() => {
  if (!props.collection.userId) return ''
  const names = props.collection.userId.trim().split(' ')
  if (names[0] && names[1]) {
    return (names[0]?.[0] ?? '') + (names[1]?.[0] ?? '')
  } else if (names[0]) {
    return names[0][0]
  }
  return ''
})

const handleToggleFavorite = () => {
  // TODO implement toggle favorite --- IGNORE ---
  console.log('Toggling favorite for collection with id: ', props.collection.id)
}

const handleEditProject = () => {
  emit('edit', props.collection)
}

const handleDeleteProject = () => {
  emit('delete', props.collection)
}

const handleEnterProject = (collectionId: string) => {
  emit('enter', collectionId)
}

</script>

<style lang="scss" scoped>
.project-card {
  aspect-ratio: 16 / 10.5;

  border: 1px solid $card-border-color;
  border-radius: 15px 5px 5px 15px;
  outline: 0px solid transparent;
  transition:
    outline 0.07s ease-in-out,
    transform 0.07s ease-in-out;
  &:hover {
    outline: 1px solid $primary;
    transform: scale(1.02) translateY(-8px);
  }
  &::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    width: 11px;
    height: 100%;
    background-color: var(--project-stripe-color, #1976d2);
    border-radius: 15px 0 0 15px;
  }

  .description-container {
    overflow: hidden;
  }
}
</style>
