<template>
  <q-page class="q-pa-md">
    <q-form @submit.prevent="onTag">
      <div class="col q-col-gutter-md">
        <div class="row justify-center">
          <span class="text-h6">Manage Tagged Chunks</span>
        </div>
        <div class="col">
          <div class="text-caption q-mb-sm">Choose Tags</div>
          <div v-for="(example, index) in tagForm.tag_uuids" :key="index" class="row items-center q-mb-sm">
            <q-select
              v-model="tagForm.tag_uuids[index]"
              :options="tags"
              option-label="tag_name"
              option-value="tag_uuid"
              type="text"
              label="Tag"
              class="col"
              emit-value
              map-options
              dense
              outlined
              :loading="loadingSpinner"
            >
              <!-- No option slot -->
              <template v-slot:no-option>
                <q-item>
                  <q-item-section class="text-grey">
                    No tags found
                  </q-item-section>
                </q-item>
              </template>
              <!-- Custom option rendering -->
              <template v-slot:option="scope">
                <q-item v-bind="scope.itemProps">
                  <q-item-section avatar>
                    <div
                      class="color-swatch"
                      :style="{ backgroundColor: scope.opt.tag_color }"
                    ></div>
                  </q-item-section>
                  <q-item-section avatar>
                    <q-item-label>{{ scope.opt.tag_pictogram }}</q-item-label>
                    <q-icon :name="scope.opt.tag_pictogram" />
                  </q-item-section>
                  <q-item-section>
                    <q-item-label>{{ scope.opt.tag_name }}</q-item-label>
                  </q-item-section>
                  <q-item-section>
                    <q-item-label> Definition: </q-item-label>
                    <q-item-label caption>
                      {{ scope.opt.tag_definition }}
                    </q-item-label>
                  </q-item-section>
                  <q-item-section>
                    <q-item-label> Examples: </q-item-label>
                    <div v-for="(example, index) in scope.opt.tag_examples" :key="index" class="row items-center q-mb-sm">
                      <q-item-label caption>
                        {{ example }}
                      </q-item-label>
                    </div>
                  </q-item-section>
                  <q-item-section>
                    <q-item-label> Collection name: </q-item-label>
                    <q-item-label caption>
                      {{ scope.opt.collection_name }}
                    </q-item-label>
                  </q-item-section>
                  <q-item-section>
                    <q-item-label> Tag uuid: </q-item-label>
                    <q-item-label caption>
                      {{ scope.opt.tag_uuid }}
                    </q-item-label>
                  </q-item-section>
                </q-item>
              </template>

              <!-- Custom selected rendering -->
              <template v-slot:selected>
                <q-item v-if="tagForm.tag_uuids[index]">
                  <q-item-section avatar>
                    <div
                      class="color-swatch"
                      :style="{ backgroundColor: tags.find(t => t.tag_uuid === tagForm.tag_uuids[index])?.tag_color }"
                    ></div>
                  </q-item-section>
                  <q-item-section avatar>
                    <q-item-label>{{ tags.find(t => t.tag_uuid === tagForm.tag_uuids[index])?.tag_pictogram }}</q-item-label>
                    <q-icon :name="tags.find(t => t.tag_uuid === tagForm.tag_uuids[index])?.tag_pictogram" />
                  </q-item-section>
                  <q-item-section >
                    <q-item-label caption> Name: </q-item-label>
                    <q-item-label> {{ tags.find(t => t.tag_uuid === tagForm.tag_uuids[index])?.tag_name }} </q-item-label>
                  </q-item-section>
                  <q-item-section class="col-grow">
                    <q-item-label caption>Tag uuid:</q-item-label>
                    <q-item-label caption class="text-mono">
                      {{ tagForm.tag_uuids[index] }}
                    </q-item-label>
                  </q-item-section>
                </q-item>
              </template>
            </q-select>
            <q-btn
              v-if="tagForm.tag_uuids.length > 1"
              @click="removeTag(index)"
              icon="fa fa-close"
              color="negative"
              flat
              dense
              class="q-ml-sm"
            />
          </div>
          <q-btn
            @click="addTag"
            v-if="tagsLen > tagForm.tag_uuids.length"
            icon="add"
            label="Add Another Tag"
            color="primary"
            outline
            dense
          />
        </div>
        <div class="row items-center" style="width: 100%;">
          <!-- left spacer -->
          <div class="col"></div>

          <!-- center button -->
          <div class="col-auto flex justify-center">
            <q-btn type="submit" color="primary" label="Get tagged texts" :loading="loading" />
          </div>
          <div class="col"></div>

          <!-- right button -->
          <div class="col-auto flex justify-end">
            <q-btn type="button" color="negative" label="Remove selected Tags" icon="delete" :loading="loading" @click="removeSelectedTags" />
          </div>
        </div>
      </div>
    </q-form>

    <!-- Text Chunk Data -->
    <div v-if="chunkData?.chunks_with_tags?.length">
      <div v-for="chunk_id in [...new Set(chunkData.chunks_with_tags.map(c => c.chunk_id))]" :key="chunk_id" class="q-mb-md">
        <q-card>
          <q-card-section>
            <div class="col">
              <div class="text-subtitle2">Chunk ID: {{ chunk_id }}</div>
              <div class="text-body1">{{ chunkData.chunks_with_tags.find(c => c.chunk_id === chunk_id)?.text_chunk }}</div>
              <div class="text-subtitle2">Chunk Collection Name: {{ chunkData.chunks_with_tags.find(c => c.chunk_id === chunk_id)?.chunk_collection_name }}</div>
              <div class="text-caption q-mt-sm">
                Tags <!-- {{ chunk.tag_uuids?.join(', ') || 'No tags' }} -->
               <div v-for="tag in chunkData.chunks_with_tags.filter(c => c.chunk_id === chunk_id)" :key="tag.tag_uuid" class="q-mb-md" >
                    <div class="row items-center col-auto">
                      <div class="color-swatch" :style="{ backgroundColor: tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_color }"></div>
                      <q-icon :name="tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_pictogram" />
                      <q-label class="q-mr-sm"> {{ tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_name }} </q-label>
                      <q-label class="q-mr-sm"> Definition: {{ tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_definition }} </q-label>
                    </div>
                    <div class="text-caption q-mt-sm">
                      Tag id: {{ tag.tag_uuid }}
                    </div>
                    <div class="row">
                      <div class="col-auto">
                        <q-btn-group>
                          <div>
                            <div class="text-positive"> Approvals: {{ tag.approved_count }} </div>
                            <q-btn
                              @click="() => approveTag(true, chunk_id, tag.tag_uuid, tag.chunk_collection_name)"
                              icon="fa fa-check"
                              label="Approve Tag"
                              color="positive"
                              outline
                              dense
                            />
                          </div>
                          <div>
                            <div class="text-negative"> Disapprovals: {{ tag.disapproved_count }} </div>
                            <q-btn
                              @click="() => approveTag(false, chunk_id, tag.tag_uuid, tag.chunk_collection_name)"
                              icon="fa fa-close"
                              label="Disapprove Tag"
                              color="negative"
                              outline
                              dense
                            />
                          </div>
                          <span v-if="tagApproveStatus.find(item => item.tag_id === tag.tag_uuid)" class="q-ml-sm">
                            {{ tagApproveStatus.find(item => item.tag_id === tag.tag_uuid).status }}
                          </span>
                        </q-btn-group>
                      </div>
                    </div>
                </div>
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>
    <div v-else>
      <div class="text-caption q-mt-md">No tagged chunks found.</div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onUnmounted, onMounted } from 'vue'
import type { TagData, GetTaggedChunksResponse, RemoveTagsResponse, ApproveTagResponse, StatusResponse, TagResult } from 'src/models'
import { api } from 'src/boot/axios'
import axios from 'axios'

interface TaskInfo {
  task_id: string;
  status: 'STARTED' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'RUNNING';
  all_texts_count: number,
  processed_count: number,
  message?: string;
  timestamp: string;
  result?: TagResult;
  error?: string;
}

const tagForm = ref<TagData>({
  tag_uuids: ['']
})

const loading = ref(false)
const allTaskInfo = ref<TaskInfo[]>([])

const tags = ref<TagData[]>([])
const loadingSpinner = ref(false)

const chunkData = ref<GetTaggedChunksResponse|null>(null)

const tagApproveStatus = ref<{ chunk_id: string; tag_id: string; status: string; chunk_collection_name: string }[]>([])

const tagsLen = ref(5)

// add examples field
const addTag = () => {
  tagForm.value.tag_uuids.push('')
}

// remove examples field
const removeTag = (index: number) => {
  if (tagForm.value.tag_uuids.length > 1) {
    tagForm.value.tag_uuids.splice(index, 1)
  }
}

// approve tag pass true to approve or false to diapprove
async function approveTag (approved: boolean, chunkID: string, tagID: string, chunkCollectionName: string) {
  const payload = { approved: approved, chunkID: chunkID, tagID: tagID, chunk_collection_name: chunkCollectionName }
  const { data } = await api.post<ApproveTagResponse>('/approve_tag', payload)
  if (data.successful) {
    await onTag() // may use lighter version to refetch the state
  } else {
    tagApproveStatus.value.push({
      chunk_id: chunkID,
      tag_id: tagID,
      status: 'Error',
      chunk_collection_name: chunkCollectionName
    })
  }
}

onMounted(async () => {
  loadingSpinner.value = true
  try {
    const res = await axios.get('/api/get_tags')
    tags.value = res.data.tags_lst
    tagsLen.value = tags.value.length
  } finally {
    loadingSpinner.value = false
  }
})

function formatDate (dateString: string): string {
  return new Date(dateString).toLocaleString()
}
function getTaskCardClass (status: 'started' | 'processing' | 'completed' | 'failed'): string {
  const classes = {
    started: 'bg-orange-1',
    processing: 'bg-blue-1',
    completed: 'bg-green-1',
    failed: 'bg-red-1'
  }
  return classes[status] || 'bg-grey-1'
}
function getTaskIcon (status: 'started' | 'processing' | 'completed' | 'failed'): string {
  const icons = {
    started: 'schedule',
    processing: 'hourglass_empty',
    completed: 'check_circle',
    failed: 'error'
  }
  return icons[status] || 'help'
}
async function onTag () {
  loading.value = true
  try {
    console.log('Tagging will start', tagForm.value)
    const payload = { tag_uuids: tagForm.value.tag_uuids }
    const { data } = await api.post<GetTaggedChunksResponse>('/tagged_texts', payload)
    console.log('Tagging response received:', data)
    chunkData.value = data
  } catch (e) {
    console.error('Tagging error:', e)
  } finally {
    loading.value = false
  }
}

async function removeSelectedTags () {
  try {
    const payload = { tag_uuids: tagForm.value.tag_uuids }
    const { data } = await api.post<RemoveTagsResponse>('/remove_tags', payload)
    console.log('Removing response received:', data)
    if (data.successful) {
      window.location.reload()
    }
  } catch (e) {
    console.error('Tag removing error:', e)
  }
}

</script>
