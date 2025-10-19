<template>
  <q-page class="q-pa-md">
    <div class="row justify-center">
      <span class="text-h6">Manage User Collections</span>
    </div>
    <div class="row justify-between">
      <div>
        <q-btn label="Create Collection" class="center" color="primary" icon="add" @click="collectionCreateDialogVisible = true" />
      </div>
      <div>
        <q-input
        v-model="username"
        label="Username"
        dense
        outlined
        style="width: 200px"
        @keyup.enter="handleAddUser"/>
      </div>
    </div>
    <q-dialog v-model="collectionCreateDialogVisible">
      <q-card style="width: 25rem; max-width: 90vw;">
        <q-card-section class="q-pa-md">
          <div class="row items-center">
            <div class="col text-center">
              <div class="text-h6">Create Tag</div>
            </div>
            <div class="col-auto absolute-right q-mr-sm">
              <q-btn flat dense round icon="close" @click="collectionCreateDialogVisible = false" />
            </div>
          </div>
        </q-card-section>
        <q-card-section>
          <q-form @submit.prevent="onCreateCollection">
            <div class="col q-col-gutter-md">
              <!--
              <div class="row justify-center">
                <span class="text-h6">Create Tag</span>
              </div> -->
              <div class="row">
                <q-input v-model="collectionForm.collection_name" type="text" label="Collection name" dense outlined />
              </div>
              <div class="col-auto flex flex-center">
                <q-btn type="submit" color="primary" label="Create Collection" :loading="loading" />
              </div>
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>
    <div class="row items-center q-gutter-md">

      <!-- choose a collection -->
      <q-select
        v-model="selectedCollectionId"
        :options="collectionOptions"
        label="Select a Collection"
        outlined
        emit-value
        map-options
        :loading="loading"
        style="width: 300px;"
      />
      <!-- Select the collection -->
      <q-btn
        label="Reload Collections"
        color="primary"
        @click="loadCollections"
        class="q-mb-md"
      />
    </div>

    <div v-if="selectedCollectionId" class="q-mt-md text-subtitle2">
      <div>Selected Collection ID: {{ selectedCollectionId }}</div>
      <div>
        Selected Collection info:
        <span v-if="selectedCollection">
          Name: {{ selectedCollection.name }} <br />
          User ID: {{ selectedCollection.user_id }}
        </span>
        <span v-else>
          Not found
        </span>
      </div>
    </div>

    <div class="row">
  </div>

  <div v-if="chunkData.length">
      <div v-for="chunk in chunkData" :key="chunk.chunk_id" class="q-mb-md">
        <q-card>
          <q-card-section>
            <div class="col">
              <!--<div class="text-subtitle2">Chunk ID: {{ chunk.chunk_id }}</div> -->
              <div class="text-body1">{{ chunk.text_chunk }}</div>

            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

  </q-page>

</template>

<script setup lang="ts">
import { ref, computed, onUnmounted, onMounted } from 'vue'
import { Notify } from 'quasar'
import type { CollectionRequest, CreateResponse, TagStartResponse, StatusResponse, TagResult, ProcessedTagData, GetTaggedChunksResponse, RemoveTagsResponse, ApproveTagResponse, TagData, TagType, CancelTaskResponse, GetCollectionChunksResponse, CollectionChunks } from 'src/models'
import { api } from 'src/boot/axios'
import axios from 'axios'
import AvatarItem from 'src/components/AvatarItem.vue'
import BadgeAvatar from 'src/components/BadgeAvatar.vue'
import { useCollectionStore } from 'src/stores/chunk_collection-store'

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

interface ItemCreationOption {
  created: boolean;
  action: boolean;
  error: string;
}

const collectionForm = ref<CollectionRequest>({
  collection_name: 'GreatCollection',
  user_id: '123'
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
  { name: 'Grey', color: '#9e9e9e' },
  { name: 'Black', color: '#000000' }
])

const loading = ref(false)
const allTaskInfo = ref<TaskInfo[]>([])
const pollingIntervals = ref<Map<string, ReturnType<typeof setInterval>>>(new Map())
const taskIDs = ref<string[]>([])

const userCollectionCreation = ref<ItemCreationOption>({
  created: false,
  action: false,
  error: ""
})

const tags = ref<TagData[]>([])
const loadingSpinner = ref(false)

const chunkData = ref<CollectionChunks[]>([])
const chunkDataPositive = ref<GetTaggedChunksResponse|null>(null)
const chunkDataNegative = ref<GetTaggedChunksResponse|null>(null)

const tagApproveStatus = ref<{ chunk_id: string; tag_id: string; status: string; chunk_collection_name: string }[]>([])

const tagsLen = ref(5)

const collectionCreateDialogVisible = ref(false)

const collectionStore = useCollectionStore()
const username = ref("")

interface MergedTag {
  tag_uuid: string
  tag_type: string
  chunk_collection_name: string
  // plus any other fields you get from API
}

interface MergedChunk {
  chunk_id: string
  text_chunk: string
  chunk_collection_name: string
  tags: MergedTag[]
}
const mergedChunks = ref<MergedChunk[]>([])

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
    // await onTagManage() // may use lighter version to refetch the state
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

async function onCreateCollection () {
  collectionCreateDialogVisible.value = false
  loading.value = true
  try {
    const payload = { ...collectionForm.value }
    const { data } = await api.post<CreateResponse>('/user_collection', payload)
    console.log('User collection creation response received:', data)
    userCollectionCreation.value.created = data.created
    userCollectionCreation.value.action = true
    userCollectionCreation.value.error = data.message
    if (userCollectionCreation.value.created) {
      // Show success popup
      Notify.create({
        message: 'Collection added successfully!',
        color: 'positive',
        position: 'top',
        timeout: 2000,
        icon: 'check'
      })
    } else {
      Notify.create({
        message: 'Failed to add Collection.',
        color: 'negative',
        position: 'top',
        timeout: 2000,
        icon: 'error'
      })
    }
  } catch (e) {
    console.error('Create collection error:', e)
    Notify.create({
      message: 'Failed to add Collection.',
      color: 'negative',
      position: 'top',
      timeout: 2000,
      icon: 'error'
    })
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

async function fetchCollectionChunks () {
  loading.value = true
  try {
    console.log('selectedCollectionId.value =', selectedCollectionId.value)
    const { data: data1 } = await api.get<GetCollectionChunksResponse>('/chunks_of_collection', {
      params: { collectionId: selectedCollection.value?.id } // 'f69088d1-9d9f-4f60-8c2a-746a51a9a159' }
    })
    console.log('Chunks response received:', data1)
    chunkData.value = data1.chunks_of_collection
  } catch (e) {
    console.error('Collecting chunks error:', e)
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
      // await onTagManage()
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
    // if (task.status === "RUNNING" or task.status === "PENDING" or === "STARTED") {
    //   startPolling(task.taskId)
    // }
  }
}

const handleAddUser = async () => {
  if (username.value.trim()) {
    console.log('Username entered:', username.value)
    collectionStore.setUser(username.value)
    await loadCollections() // load collections of the user
  }
}

// local reactive refs
const selectedCollectionId = ref<string | null>(null)
const selectedCollection = computed(() =>
  collectionStore.collections.find(c => c.id === selectedCollectionId.value)
)

// computed to transform collections
const collectionOptions = computed(() =>
  collectionStore.collections.map(c => ({
    label: c.name ?? `Collection ${c.id}`,
    value: c.id
  }))
)

// load collections from weaviate
const loadCollections = async () => {
  if (!collectionStore.userId) {
    Notify.create({ message: 'No user set', position: 'top', color: 'negative' })
    return
  }

  loading.value = true
  try {
    await collectionStore.fetchCollections(collectionStore.userId)
    Notify.create({ message: 'Collections loaded', position: 'top', color: 'positive' })
    fetchCollectionChunks()
  } catch (err) {
    console.error(err)
    Notify.create({ message: 'Failed to load collections', position: 'top', color: 'negative' })
  } finally {
    loading.value = false
  }
}

// Cleanup intervals when component is destroyed
onUnmounted(() => {
  pollingIntervals.value.forEach((interval, taskId) => { clearInterval(interval) })
  pollingIntervals.value.clear()
})
</script>
