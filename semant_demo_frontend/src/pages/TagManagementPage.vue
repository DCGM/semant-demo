<template>
  <q-page class="q-pa-md">
    <div class="row justify-center">
          <span class="text-h6">Manage automatic tags</span>
        </div>
    <div class="row justify-left">
      <q-btn label="Create Tag" class="center" color="primary" icon="add" @click="tagCreateDialogVisible = true" />
    </div>
    <q-dialog v-model="tagCreateDialogVisible">
      <q-card style="width: 25rem; max-width: 90vw;">
        <q-card-section class="q-pa-md">
          <div class="row items-center">
            <div class="col text-center">
              <div class="text-h6">Create Tag</div>
            </div>
            <div class="col-auto absolute-right q-mr-sm">
              <q-btn flat dense round icon="close" @click="tagCreateDialogVisible = false" />
            </div>
          </div>
        </q-card-section>
        <q-card-section>
          <q-form @submit.prevent="onCreateTag">
            <div class="col q-col-gutter-md">
              <!--
              <div class="row justify-center">
                <span class="text-h6">Create Tag</span>
              </div> -->
              <div class="row">
                <q-input v-model="tagForm.collection_name" type="text" label="Collection name" dense outlined />
              </div>
              <div class="row">
                <div class="col">
                  <q-input v-model="tagForm.tag_name" label="Tag Name" dense outlined required />
                </div>
                <div class="col">
                  <q-input v-model="tagForm.tag_shorthand" type="text" label="Shorthand" dense outlined />
                </div>
              </div>
              <div class="row">
                <!-- Color -->
                <div class="col">
                  <q-select
                    v-model="tagForm.tag_color"
                    :options="colors"
                    option-label="name"
                    option-value="color" type="text" label="Color" emit-value map-options dense outlined
                  >
                  <template v-slot:option="scope">
                    <q-item v-bind="scope.itemProps">
                    <q-item-section avatar>
                      <div
                        class="color-swatch"
                        :style="{ backgroundColor: scope.opt.color }"
                      ></div>
                    </q-item-section>
                    <q-item-section>
                      <q-item-label>{{ scope.opt.name }}</q-item-label>
                    </q-item-section>
                    </q-item>
                  </template>
                  <template v-slot:selected>
                    <q-item v-if="tagForm.tag_color">
                      <q-item-section avatar>
                        <div class="color-swatch" :style="{ backgroundColor: tagForm.tag_color }">
                        </div>
                      </q-item-section>
                      <q-item-section>
                        {{ colors.find(c => c.color === tagForm.tag_color)?.name }}
                      </q-item-section>
                    </q-item>
                  </template>
                  </q-select>
                </div>
                <!-- Pictogram -->
                <div class="col">
                  <q-select
                    v-model="tagForm.tag_pictogram"
                    :options="pictograms"
                    option-label="name"
                    option-value="icon" type="text" label="Pictogram" emit-value map-options dense outlined
                  >
                  <template v-slot:option="scope">
                    <q-item v-bind="scope.itemProps">
                    <q-item-section avatar>
                      <q-icon :name="scope.opt.icon" />
                    </q-item-section>
                    <q-item-section>
                      <q-item-label>{{ scope.opt.name }}</q-item-label>
                    </q-item-section>
                    </q-item>
                  </template>
                  <template v-slot:selected>
                    <q-item v-if="tagForm.tag_pictogram">
                      <q-item-section avatar>
                        <q-icon :name="tagForm.tag_pictogram" />
                      </q-item-section>
                      <q-item-section>
                        {{ pictograms.find(p => p.icon === tagForm.tag_pictogram)?.name }}
                      </q-item-section>
                    </q-item>
                  <!--span v-else>Select a Pictogram</span-->
                  </template>
                  </q-select>
                </div>
              </div>
              <div class="col">
                <q-input v-model="tagForm.tag_definition" type="text" label="Tag definition" dense outlined />
              </div>
              <div class="col">
                <div class="text-caption q-mb-sm">Tag Examples</div>
                <div v-for="(example, index) in tagForm.tag_examples" :key="index" class="row items-center q-mb-sm">
                  <q-input
                    v-model="tagForm.tag_examples[index]"
                    :label="`Example ${index + 1}`"
                    dense
                    outlined
                    class="col-grow"
                  />
                  <q-btn
                    v-if="tagForm.tag_examples.length > 1"
                    @click="removeExample(index)"
                    icon="delete"
                    color="negative"
                    flat
                    dense
                    class="q-ml-sm"
                  />
                </div>
                <q-btn
                  @click="addExample"
                  icon="add"
                  label="Add Another Example"
                  color="primary"
                  outline
                  dense
                />
              </div>
              <div class="col-auto flex flex-center">
                <q-btn type="submit" color="primary" label="Create Tag" :loading="loading" />
              </div>
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <div v-if="tagCreation.action == true" class="col-auto flex flex-center">
      <div v-if="tagCreation.created == true" class="q-mt-sm">
        <div class="text-caption">Tag created</div>
      </div>
      <div v-if="tagCreation.created == false" class="q-mt-sm">
        <div class="text-caption">Tag not created</div>
      </div>
    </div>

    <!-- Tag Confirmation - automatic tags -->

    <q-form @submit.prevent="onTagManage">
      <div class="col q-col-gutter-md">
        <!--
        <div class="row justify-center">
          <span class="text-h6">Manage automatic tags</span>
        </div>-->
        <div class="col">
          <div class="text-caption q-mb-sm">Choose Tags</div>
          <div v-for="(example, index) in tagFormManage.tag_uuids" :key="index" class="row items-center q-mb-sm">
            <q-select
              v-model="tagFormManage.tag_uuids[index]"
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
              @popup-show="fetchTags"
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
                    <AvatarItem
                      :annotation-class="{
                        short: scope.opt.tag_shorthand || '?',
                        colorString: scope.opt.tag_color || '#ccc',
                        textColor: 'black'
                      }"
                      size="sm"
                    />
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
                <q-item v-if="tagFormManage.tag_uuids[index]">
                  <!--<q-item-section avatar>
                    <div
                      class="color-swatch"
                      :style="{ backgroundColor: tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_color }"
                    ></div>
                  </q-item-section>  -->
                  <q-item-section>
                    <div class="row q-gutter-md items-center">
                    <AvatarItem
                      :annotation-class="{
                        short: tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_shorthand || '?',
                        colorString: tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_color || '#ccc',
                        textColor: 'black'
                      }"
                      size="sm"
                    />
                    <q-space/>
                    <div class="col-grow">
                      <q-item-label>{{ tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_pictogram }}</q-item-label>
                      <q-icon :name="tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_pictogram" />
                    </div>
                    <div class="col-grow">
                      <q-item-label caption> Name: </q-item-label>
                      <q-item-label> {{ tags.find(t => t.tag_uuid === tagFormManage.tag_uuids[index])?.tag_name }} </q-item-label>
                    </div>
                    <div class="col-grow">
                      <q-item-label caption>Tag uuid:</q-item-label>
                      <q-item-label caption class="text-mono">
                        {{ tagFormManage.tag_uuids[index] }}
                      </q-item-label>
                    </div>
                  </div>
                  </q-item-section>
                </q-item>
              </template>
            </q-select>
            <q-btn
              v-if="tagFormManage.tag_uuids.length > 1"
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
            v-if="tagsLen > tagFormManage.tag_uuids.length"
            icon="add"
            label="Add Another Tag"
            color="primary"
            outline
            dense
          />
        </div>
        <div class="row items-center" style="width: 100%;">
          <!-- left spacer -->
          <div class="col">
            <q-btn
              @click="onRunTask"
              icon="assignment"
              label="Run Tagging task"
              color="primary"
              outline
              dense
            />
          </div>

          <!-- center button -->
          <div class="col-auto flex justify-center">
            <q-btn type="submit" color="primary" label="Get tagged texts" :loading="loading" />
          </div>
          <div class="col"></div>

          <!-- right button -->
          <div class="col-auto flex justify-end">
            <q-btn type="button" color="negative" label="Remove Selected Automatic Tags" icon="delete" :loading="loading" @click="removeSelectedTags" />
          </div>
        </div>
      </div>
    </q-form>

    <!-- tasks item -->
    <q-expansion-item icon="assignment" label="Tasks" expand-separator @show="onShowTasks">
            <!-- Task Status Cards -->
            <div v-for="task in allTaskInfo" :key="task.task_id" class="q-mt-lg">
              <q-card :class="getTaskCardClass(task.status)">
                <q-card-section>
                  <div class="row items-center">
                    <q-icon :name="getTaskIcon(task.status)" class="q-mr-sm" />
                    <div class="text-h6">Task #{{ allTaskInfo.length - allTaskInfo.indexOf(task) }}</div>
                    <q-space />
                    <div v-if="task.status === 'PROCESSING' || task.status === 'PENDING' || task.status === 'RUNNING' || task.status === 'STARTED'" >
                      <q-btn
                        @click="() => cancelTask(task.task_id, task)"
                                icon="fa fa-close"
                                label="Cancel Task"
                                color="negative"
                                outline
                                dense
                        />
                    </div>
                    <div class="text-caption">{{ formatDate(task.timestamp) }}</div>
                  </div>
                </q-card-section>
                <q-card-section>
                  <div class="text-subtitle2">ID: {{ task.task_id }}</div>
                  <div class="text-caption">Status: {{ task.status }}</div>
                  <q-linear-progress v-if="task.status === 'PROCESSING' || task.status === 'PENDING' || task.status === 'RUNNING' || task.status === 'STARTED'" indeterminate class="q-mt-sm"/>
                  <div v-if="task.status === 'RUNNING' || task.status === 'PENDING'" class="q-mt-sm">
                    <div class="text-caption">Processed: {{ task.processed_count ?? 0 }} / {{ task.all_texts_count ?? 0 }}</div>
                  </div>
                  <div v-if="task.status === 'COMPLETED'" class="q-mt-sm">
                    <div class="text-positive">Completed</div>
                    <div v-if="task.result" class="q-mt-sm">
                      <div class="text-weight-bold">Results:</div>
                      <div v-for="(item, idx) in task.tag_processing_data" :key="idx" class="q-pl-md">
                        {{ idx + 1 }}. <strong>{{ item.tag }}</strong> : {{ item.text }}
                      </div>
                    </div>
                  </div>
                  <div v-if="task.status === 'FAILED'" class="text-negative q-mt-sm">
                    Error: {{ task.error }}
                  </div>
                </q-card-section>
              </q-card>
            </div>
    </q-expansion-item>

    <!-- Text Chunk Data automatic -->
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
                    <div class="text-h6 q-mt-sm">
                      Tag type: Automatic
                    </div>
                    <div class="row">
                      <div class="col-auto">
                        <q-btn-group>
                          <div>
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
      <div class="text-caption q-mt-md">No automatic tagged chunks found.</div>
    </div>

    <!-- Positive chunks -->
    <div v-if="chunkDataPositive?.chunks_with_tags?.length">
      <div v-for="chunk_id in [...new Set(chunkDataPositive.chunks_with_tags.map(c => c.chunk_id))]" :key="chunk_id" class="q-mb-md">
        <q-card>
          <q-card-section>
            <div class="col">
              <div class="text-subtitle2">Chunk ID: {{ chunk_id }}</div>
              <div class="text-body1">{{ chunkDataPositive.chunks_with_tags.find(c => c.chunk_id === chunk_id)?.text_chunk }}</div>
              <div class="text-subtitle2">Chunk Collection Name: {{ chunkDataPositive.chunks_with_tags.find(c => c.chunk_id === chunk_id)?.chunk_collection_name }}</div>
              <div class="text-caption q-mt-sm">
                Tags <!-- {{ chunk.tag_uuids?.join(', ') || 'No tags' }} -->
               <div v-for="tag in chunkDataPositive.chunks_with_tags.filter(c => c.chunk_id === chunk_id)" :key="tag.tag_uuid" class="q-mb-md" >
                    <div class="row items-center col-auto">
                      <div class="color-swatch" :style="{ backgroundColor: tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_color }"></div>
                      <q-icon :name="tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_pictogram" />
                      <q-label class="q-mr-sm"> {{ tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_name }} </q-label>
                      <q-label class="q-mr-sm"> Definition: {{ tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_definition }} </q-label>
                    </div>
                    <div class="text-caption q-mt-sm">
                      Tag id: {{ tag.tag_uuid }}
                    </div>
                    <div class="text-h6 q-mt-sm">
                      Tag type: Positive
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

      <!-- Negative chunks -->
    <div v-if="chunkDataNegative?.chunks_with_tags?.length">
      <div v-for="chunk_id in [...new Set(chunkDataNegative.chunks_with_tags.map(c => c.chunk_id))]" :key="chunk_id" class="q-mb-md">
        <q-card>
          <q-card-section>
            <div class="col">
              <div class="text-subtitle2">Chunk ID: {{ chunk_id }}</div>
              <div class="text-body1">{{ chunkDataNegative.chunks_with_tags.find(c => c.chunk_id === chunk_id)?.text_chunk }}</div>
              <div class="text-subtitle2">Chunk Collection Name: {{ chunkDataNegative.chunks_with_tags.find(c => c.chunk_id === chunk_id)?.chunk_collection_name }}</div>
              <div class="text-caption q-mt-sm">
                Tags <!-- {{ chunk.tag_uuids?.join(', ') || 'No tags' }} -->
               <div v-for="tag in chunkDataNegative.chunks_with_tags.filter(c => c.chunk_id === chunk_id)" :key="tag.tag_uuid" class="q-mb-md" >
                    <div class="row items-center col-auto">
                      <div class="color-swatch" :style="{ backgroundColor: tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_color }"></div>
                      <q-icon :name="tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_pictogram" />
                      <q-label class="q-mr-sm"> {{ tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_name }} </q-label>
                      <q-label class="q-mr-sm"> Definition: {{ tags.find(t => t.tag_uuid === tag.tag_uuid)?.tag_definition }} </q-label>
                    </div>
                    <div class="text-caption q-mt-sm">
                      Tag id: {{ tag.tag_uuid }}
                    </div>
                    <div class="text-h6 q-mt-sm">
                      Tag type: Negative
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
import type { TagRequest, CreateTagResponse, TagStartResponse, StatusResponse, TagResult, ProcessedTagData, GetTaggedChunksResponse, RemoveTagsResponse, ApproveTagResponse, TagData, TagType, CancelTaskResponse } from 'src/models'
import { api } from 'src/boot/axios'
import axios from 'axios'
import AvatarItem from 'src/components/AvatarItem.vue'

// TODO put back status 'STARTED' | 'PROCESSING' | 'COMPLETED' | 'FAILED' | 'RUNNING' | 'CANCELED';

interface TaskInfo { // Task
  task_id: string;
  status: string;
  all_texts_count: number;
  processed_count: number;
  tag_processing_data: ProcessedTagData[];
  message?: string;
  timestamp: string;
  result?: TagResult;
  error?: string;
}

interface TagCreationOption {
  created: boolean;
  action: boolean;
  error: string;
}

const tagForm = ref<TagRequest>({
  tag_name: 'Prezident',
  tag_shorthand: 'p',
  tag_color: '#4caf50',
  tag_pictogram: 'circle',
  tag_definition: 'Hlava statu',
  tag_examples: ['EU Cesko'],
  collection_name: 'Chunks'
})

const tagFormManage = ref<TagData>({
  tag_uuids: ['']
})

/*
const tagForm = ref<TagRequest>({
  tag_name: '',
  tag_shorthand: '',
  tag_color: '',
  tag_pictogram: '',
  tag_definition: '',
  tag_examples: [''],
  collection_name: 'Chunks'
})
*/
const pictograms = ref([
  { name: 'Circle', icon: 'circle' },
  { name: 'Key', icon: 'key' },
  { name: 'Square', icon: 'square' },
  { name: 'Lock', icon: 'lock' }
])

const colors = ref([
  { name: 'Green', color: '#4caf50' },
  { name: 'Light Green', color: '#8bc34a' },
  { name: 'Lime', color: '#cddc39' },
  { name: 'Light Blue', color: '#03a9f4' },
  { name: 'Blue', color: '#2196f3' },
  { name: 'Cyan', color: '#00bcd4' },
  { name: 'Yellow', color: '#ffeb3b' },
  { name: 'Orange', color: '#ff9800' },
  { name: 'Red', color: '#f44336' },
  { name: 'Pink', color: '#e91e63' },
  { name: 'Purple', color: '#9c27b0' },
  { name: 'Brown', color: '#795548' },
  { name: 'Grey', color: '#9e9e9e' }
])

const loading = ref(false)
const allTaskInfo = ref<TaskInfo[]>([])
const pollingIntervals = ref<Map<string, ReturnType<typeof setInterval>>>(new Map())
const taskIDs = ref<string[]>([])

const tagCreation = ref<TagCreationOption>({
  created: false,
  action: false,
  error: ""
})

const tags = ref<TagData[]>([])
const loadingSpinner = ref(false)

const chunkData = ref<GetTaggedChunksResponse|null>(null)
const chunkDataPositive = ref<GetTaggedChunksResponse|null>(null)
const chunkDataNegative = ref<GetTaggedChunksResponse|null>(null)

const tagApproveStatus = ref<{ chunk_id: string; tag_id: string; status: string; chunk_collection_name: string }[]>([])

const tagsLen = ref(5)

const tagCreateDialogVisible = ref(false)

// add examples field
const addTag = () => {
  tagFormManage.value.tag_uuids.push('')
}

// remove examples field
const removeTag = (index: number) => {
  if (tagFormManage.value.tag_uuids.length > 1) {
    tagFormManage.value.tag_uuids.splice(index, 1)
  }
}

// approve tag pass true to approve or false to diapprove
async function approveTag (approved: boolean, chunkID: string, tagID: string, chunkCollectionName: string) {
  const payload = { approved: approved, chunkID: chunkID, tagID: tagID, chunk_collection_name: chunkCollectionName }
  const { data } = await api.put<ApproveTagResponse>('/tag_approval', payload)
  if (data.successful) {
    await onTagManage() // may use lighter version to refetch the state
  } else {
    tagApproveStatus.value.push({
      chunk_id: chunkID,
      tag_id: tagID,
      status: 'Error',
      chunk_collection_name: chunkCollectionName
    })
  }
}

// add examples field
const addExample = () => {
  tagForm.value.tag_examples.push('')
}

// remove examples field
const removeExample = (index: number) => {
  if (tagForm.value.tag_examples.length > 1) {
    tagForm.value.tag_examples.splice(index, 1)
  }
}

onMounted(async () => {
  await onShowTasks()
  // the tag management part
  loadingSpinner.value = true
  try {
    const res = await axios.get('/api/all_tags')
    tags.value = res.data.tags_lst
    tagsLen.value = tags.value.length
  } finally {
    loadingSpinner.value = false
  }
})

function formatDate (dateString: string): string {
  return new Date(dateString).toLocaleString()
}
function getTaskCardClass (status: string): string {
  const classes = {
    started: 'bg-orange-1',
    processing: 'bg-blue-1',
    completed: 'bg-green-1',
    failed: 'bg-red-1'
  }
  return status || 'bg-grey-1'
}
function getTaskIcon (status: string): string {
  const icons: Record<string, string> = {
    started: 'schedule',
    processing: 'hourglass_empty',
    completed: 'check_circle',
    failed: 'error'
  }
  return icons[status] || 'help'
}

async function loadExistingTagsList () {
  loadingSpinner.value = true
  try {
    const res = await axios.get('/api/all_tags')
    tags.value = res.data.tags_lst
    tagsLen.value = tags.value.length
  } finally {
    loadingSpinner.value = false
  }
}

async function onCreateTag () {
  tagCreateDialogVisible.value = false
  loading.value = true
  try {
    console.log('Tagging will start', tagForm.value)
    const payload = { ...tagForm.value, tag_examples: tagForm.value.tag_examples.filter(example => example.trim() !== '') }
    const { data } = await api.post<CreateTagResponse>('/create_tag', payload)
    console.log('Tagging response received:', data)
    tagCreation.value.created = data.tag_created
    tagCreation.value.action = true
    tagCreation.value.error = data.message
  } catch (e) {
    console.error('Tagging error:', e)
  } finally {
    loading.value = false
    loadExistingTagsList()
  }
}

async function onRunTask () {
  loading.value = true
  for (const [index, uuid] of tagFormManage.value.tag_uuids.entries()) {
    try {
      const tagValues = tags.value.find(t => t.tag_uuid === uuid)
      console.log('Tagging will start', tagValues)
      const payload = { ...tagValues, tag_examples: tagValues.tag_examples.filter(example => example.trim() !== '') }
      const { data } = await api.post<TagStartResponse>('/tagging_task', payload)
      console.log('Tagging response received:', data)
      // Store task information
      const newTaskInfo: TaskInfo = {
        task_id: data.task_id,
        status: 'STARTED',
        all_texts_count: 0,
        processed_count: 0,
        message: data.message,
        timestamp: new Date().toISOString(),
        tag_processing_data: []
      }
      allTaskInfo.value.unshift(newTaskInfo) // order newest on top
      startPolling(data.task_id)
    } catch (e) {
      console.error('Tagging error:', e)
      // add error task info
      const errorTaskInfo: TaskInfo = {
        task_id: 'error-' + Date.now(),
        status: 'FAILED',
        message: 'Failed to submit task',
        error: e instanceof Error ? e.message : 'Unknown error',
        timestamp: new Date().toISOString(),
        all_texts_count: 0,
        processed_count: 0,
        tag_processing_data: []
      }
      allTaskInfo.value.unshift(errorTaskInfo)
    } finally {
      loading.value = false
    }
  }
}

// cancel task
async function cancelTask (taskID: string) {
  const payload = { params: { taskId: taskID } }
  const { data: data1 } = await api.delete<CancelTaskResponse>(`/tagging_task/${taskID}`, payload)
  console.log("Canceled: ", data1.taskCanceled)
  const { data } = await api.get<StatusResponse>(`/tag_status/${taskID}`)
  stopPolling(taskID)
  updateTaskStatus(taskID, data.status, data.result, data.all_texts_count, data.processed_count, data.tag_processing_data)
}

function startPolling (taskId: string) {
  // clear existing interval if any
  // stopPolling(taskId)
  const interval: ReturnType<typeof setInterval> = setInterval(async () => {
    try {
      // server response is inside data
      const { data } = await api.get<StatusResponse>(`/tag_status/${taskId}`)
      console.log('Polling response:', data) // Debug log
      console.log('processed count: ', data.processed_count, 'all count: ', data.all_texts_count)
      updateTaskStatus(taskId, data.status, data.result, data.all_texts_count, data.processed_count, data.tag_processing_data)
      // stop polling when task done
      if (['COMPLETED', 'FAILED', 'CANCELED'].includes(data.status)) {
        console.log(`Stopping polling for task ${taskId}, status: ${data.status}`)
        stopPolling(taskId)
      }
    } catch (error) {
      console.error('Polling error:', error)
      // mark as failed if can't reach the status endpoint
      updateTaskStatus(taskId, 'FAILED')
      stopPolling(taskId)
    }
  }, 1000) // poll every 10000 10 seconds
  pollingIntervals.value.set(taskId, interval)
}

function stopPolling (taskId: string) {
  const interval = pollingIntervals.value.get(taskId)
  if (interval) {
    clearInterval(interval)
    pollingIntervals.value.delete(taskId)
  }
}

function updateTaskStatus (taskId: string, status: string, result?: TagResult, allTextsCount?: number, processedCount?: number, tagProcessingData?: ProcessedTagData[]) {
  const index = allTaskInfo.value.findIndex(task => task.task_id === taskId)
  if (index !== -1) {
    allTaskInfo.value[index] = {
      ...allTaskInfo.value[index],
      status: status,
      result: result,
      all_texts_count: allTextsCount ?? 0,
      processed_count: processedCount ?? 0,
      tag_processing_data: tagProcessingData ?? [],
      // Preserve existing data
      timestamp: allTaskInfo.value[index].timestamp,
      message: allTaskInfo.value[index].message
    }
    console.log('Updated task status:', allTaskInfo.value[index])
  }
}

async function onTagManage () {
  loading.value = true
  try {
    // console.log('Tagging will start', tagFormManage.value)
    const payload = { tag_uuids: tagFormManage.value.tag_uuids, tag_type: "automatic" }
    const { data: data1 } = await api.post<GetTaggedChunksResponse>('/tagged_texts', payload)
    console.log('Tagging response received:', data1)
    chunkData.value = data1
    // positive
    const payload2 = { tag_uuids: tagFormManage.value.tag_uuids, tag_type: "positive" }
    const { data: data2 } = await api.post<GetTaggedChunksResponse>('/tagged_texts', payload2)
    console.log('Tagging response received:', data2)
    chunkDataPositive.value = data2
    // negative
    const payload3 = { tag_uuids: tagFormManage.value.tag_uuids, tag_type: "negative" }
    const { data: data3 } = await api.post<GetTaggedChunksResponse>('/tagged_texts', payload3)
    console.log('Tagging response received:', data3)
    chunkDataNegative.value = data3
  } catch (e) {
    console.error('Tagging error:', e)
  } finally {
    loading.value = false
  }
}

async function removeSelectedTags () {
  try {
    const payload = { tag_uuids: tagFormManage.value.tag_uuids }
    const { data } = await api.delete<RemoveTagsResponse>('/automatic_tags', { data: payload })
    console.log('Removing response received:', data)
    if (data.successful) {
      // window.location.reload()
      await onTagManage()
    }
  } catch (e) {
    console.error('Tag removing error:', e)
  }
}

// fetch tag info
async function fetchTags () {
  loadingSpinner.value = true
  try {
    const res = await api.get('/all_tags')
    tags.value = res.data.tags_lst
    tagsLen.value = tags.value.length
  } finally {
    loadingSpinner.value = false
  }
}

async function onShowTasks () {
  const res = await axios.get('/api/all_tasks')
  const tasks = res.data.taskData
  for (const task of tasks) {
    // skip if this task is already in allTaskInfo
    const exists = allTaskInfo.value.some(t => t.task_id === task.taskId)
    if (exists) continue
    const newTaskInfo: TaskInfo = {
      task_id: task.taskId,
      status: task.status,
      all_texts_count: task.all_texts_count,
      processed_count: task.processed_count,
      tag_processing_data: task.tag_processing_data,
      message: "Loaded data",
      result: task.result,
      timestamp: task.timestamp
    }
    allTaskInfo.value.unshift(newTaskInfo)
  }
}

// Cleanup intervals when component is destroyed
onUnmounted(() => {
  pollingIntervals.value.forEach((interval, taskId) => { clearInterval(interval) })
  pollingIntervals.value.clear()
})
</script>
