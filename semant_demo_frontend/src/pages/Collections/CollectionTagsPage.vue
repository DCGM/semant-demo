<template>
  <div class="q-pa-md">
    <TagsTable
      :tags="tags"
      :loading="loading"
      @refresh="handleRefresh"
      @create="openCreateDialog"
    />

    <q-dialog v-model="createDialogVisible" persistent>
      <q-card style="width: 640px; max-width: 92vw;">
        <q-card-section class="row items-center q-pb-none">
          <div class="text-h6">Create Tag</div>
          <q-space />
          <q-btn
            flat
            dense
            round
            icon="close"
            :disable="submitting"
            @click="closeCreateDialog"
          />
        </q-card-section>

        <q-card-section>
          <q-form @submit.prevent="handleCreateTag">
            <div class="column q-gutter-md">
              <div class="row q-col-gutter-md">
                <div class="col-12 col-md-7">
                  <q-input
                    v-model="createForm.tagName"
                    label="Tag name"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Tag name is required']"
                  />
                </div>
                <div class="col-12 col-md-5">
                  <q-input
                    v-model="createForm.tagShorthand"
                    label="Shorthand"
                    outlined
                    dense
                  />
                </div>
              </div>

              <div class="row q-col-gutter-md">
                <div class="col-12 col-md-6">
                  <q-input
                    v-model="createForm.tagColor"
                    label="Color"
                    outlined
                    dense
                    hint="Hex or named color"
                  >
                    <template #prepend>
                      <span class="tag-color-preview" :style="{ backgroundColor: createForm.tagColor || '#BDBDBD' }" />
                    </template>
                  </q-input>
                </div>
                <div class="col-12 col-md-6">
                  <q-input
                    v-model="createForm.tagPictogram"
                    label="Pictogram"
                    outlined
                    dense
                    hint="Material icon name"
                  >
                    <template #prepend>
                      <q-icon :name="createForm.tagPictogram || 'label'" />
                    </template>
                  </q-input>
                </div>
              </div>

              <q-input
                v-model="createForm.tagDefinition"
                label="Definition"
                outlined
                dense
                type="textarea"
                autogrow
              />

              <div>
                <div class="text-caption text-grey-7 q-mb-sm">Examples</div>
                <div
                  v-for="(example, index) in createForm.tagExamples"
                  :key="index"
                  class="row items-center q-gutter-sm q-mb-sm"
                >
                  <q-input
                    v-model="createForm.tagExamples[index]"
                    dense
                    outlined
                    class="col"
                    :label="`Example ${index + 1}`"
                  />
                  <q-btn
                    flat
                    dense
                    round
                    icon="delete"
                    color="negative"
                    :disable="createForm.tagExamples.length === 1"
                    @click="removeExample(index)"
                  />
                </div>
                <q-btn
                  flat
                  dense
                  icon="add"
                  color="primary"
                  label="Add example"
                  @click="addExample"
                />
              </div>
            </div>

            <q-card-actions align="right" class="q-pr-none q-pt-lg">
              <q-btn
                flat
                label="Cancel"
                :disable="submitting"
                @click="closeCreateDialog"
              />
              <q-btn
                color="primary"
                label="Create Tag"
                type="submit"
                :loading="submitting"
              />
            </q-card-actions>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useQuasar } from 'quasar'

import useTags from 'src/composables/useTags'
import TagsTable from 'src/components/tables/TagsTable.vue'

const $route = useRoute()
const $q = useQuasar()
const { tags, loading, error, loadTags, createTag } = useTags()

const createDialogVisible = ref(false)
const submitting = ref(false)
const createForm = reactive({
  tagName: '',
  tagShorthand: '',
  tagColor: '#90CAF9',
  tagPictogram: 'label',
  tagDefinition: '',
  tagExamples: ['']
})

const collectionId = computed<string>(() => {
  const value = $route.params.collectionId
  if (typeof value !== 'string') {
    throw new Error('Missing required route param: collectionId')
  }
  return value
})

const handleRefresh = async () => {
  await loadTags(collectionId.value)
}

const resetCreateForm = () => {
  createForm.tagName = ''
  createForm.tagShorthand = ''
  createForm.tagColor = '#90CAF9'
  createForm.tagPictogram = 'label'
  createForm.tagDefinition = ''
  createForm.tagExamples = ['']
}

const openCreateDialog = () => {
  resetCreateForm()
  createDialogVisible.value = true
}

const closeCreateDialog = () => {
  if (submitting.value) {
    return
  }
  createDialogVisible.value = false
}

const addExample = () => {
  createForm.tagExamples.push('')
}

const removeExample = (index: number) => {
  if (createForm.tagExamples.length === 1) {
    return
  }
  createForm.tagExamples.splice(index, 1)
}

const handleCreateTag = async () => {
  if (!createForm.tagName.trim()) {
    $q.notify({ type: 'negative', message: 'Tag name is required' })
    return
  }

  submitting.value = true
  try {
    await createTag(collectionId.value, {
      tagName: createForm.tagName.trim(),
      tagShorthand: createForm.tagShorthand.trim(),
      tagColor: createForm.tagColor.trim(),
      tagPictogram: createForm.tagPictogram.trim(),
      tagDefinition: createForm.tagDefinition.trim(),
      tagExamples: createForm.tagExamples.map((example) => example.trim()).filter(Boolean)
    })
    createDialogVisible.value = false
    await handleRefresh()
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await handleRefresh()
})
</script>

<style scoped lang="scss">
.tag-color-preview {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  border: 1px solid rgba(0, 0, 0, 0.2);
}
</style>
