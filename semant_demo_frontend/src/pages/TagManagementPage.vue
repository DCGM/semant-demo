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
                  <q-item-section >
                    <q-item-label> Name: </q-item-label>
                    {{ tags.find(t => t.tag_uuid === tagForm.tag_uuids[index])?.tag_name }}
                  </q-item-section>
                  <q-item-section class="col-grow">
                    <q-item-label>Tag uuid:</q-item-label>
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
              icon="delete"
              color="negative"
              flat
              dense
              class="q-ml-sm"
            />
          </div>
          <q-btn
            @click="addTag"
            icon="add"
            label="Add Another Tag"
            color="primary"
            outline
            dense
          />
        </div>
        <div class="col-auto flex flex-center">
          <q-btn type="submit" color="primary" label="Get tagged texts" :loading="loading" />
        </div>
      </div>
    </q-form>

    <!-- Text Chunk Data -->
    <div v-if="chunkData?.chunks_with_tags?.length">
      <div v-for="chunk in chunkData.chunks_with_tags" :key="chunk.chunk_id" class="q-mb-md">
        <q-card>
          <q-card-section>
            <div class="col">
              <div class="text-subtitle2">Chunk ID: {{ chunk.chunk_id }}</div>
              <div class="text-body1">{{ chunk.text_chunk }}</div>
              <div class="text-subtitle2">Chunk Collection Name: {{ chunk.chunk_collection_name }}</div>
              <div class="text-caption q-mt-sm">
                Tags <!-- {{ chunk.tag_uuids?.join(', ') || 'No tags' }} -->
                <div v-for="tag_id in chunk.tag_uuids" :key="tag_id" class="q-mb-md">
                    <div class="text-caption q-mt-sm">
                      Tag id: {{ tag_id }}
                    </div>
                    <div class="row">
                      <div class="col-auto">
                        <q-btn-group>
                          <q-btn
                            @click="() => approveTag(true, chunk.chunk_id, tag_id, chunk.chunk_collection_name)"
                            icon="fa fa-check"
                            label="Approve Tag"
                            color="primary"
                            outline
                            dense
                          />
                          <q-btn
                            @click="() => approveTag(false, chunk.chunk_id, tag_id, chunk.chunk_collection_name)"
                            icon="fa fa-close"
                            label="Disapprove Tag"
                            color="primary"
                            outline
                            dense
                          />
                          <span v-if="tagApproveStatus.find(item => item.tag_id === tag_id)" class="q-ml-sm">
                            {{ tagApproveStatus.find(item => item.tag_id === tag_id).status }}
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
import type { TagData, GetTaggedChunksResponse, ApproveTagResponse, StatusResponse, TagResult } from 'src/models'
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

const tags = ref([])
const loadingSpinner = ref(false)

const chunkData = ref<GetTaggedChunksResponse|null>(null)

const tagApproveStatus = ref<{ chunk_id: string; tag_id: string; status: string; chunk_collection_name: string }[]>([])

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
  tagApproveStatus.value.push({
    chunk_id: chunkID,
    tag_id: tagID,
    status: data.successful ? (data.approved ? 'Approved' : 'Disapproved') : 'Error',
    chunk_collection_name: chunkCollectionName
  })
}

onMounted(async () => {
  loadingSpinner.value = true
  try {
    const res = await axios.get('/api/get_tags')
    tags.value = res.data.tags_lst
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
</script>
