<template>
  <q-page class="q-pa-md">
    <q-form @submit.prevent="onTag">
      <div class="col q-col-gutter-md">
        <div class="row justify-center">
          <span class="text-h6">Tag collection</span>
        </div>
        <div class="row">
          <q-input v-model="tagForm.collection_name" type="text" label="Collection name" dense outlined />
        </div>
        <div class="row">
          <q-input v-model="tagForm.tag_name" label="Tag Name" dense outlined required />
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
          <q-btn type="submit" color="primary" label="Tag" :loading="loading" />
        </div>
      </div>
    </q-form>

    <!-- Task Status Cards -->
    <div v-for="task in allTaskInfo" :key="task.task_id" class="q-mt-lg">
      <q-card :class="getTaskCardClass(task.status)">
        <q-card-section>
          <div class="row items-center">
            <q-icon :name="getTaskIcon(task.status)" class="q-mr-sm" />
            <div class="text-h6">Task #{{ allTaskInfo.length - allTaskInfo.indexOf(task) }}</div>
            <q-space />
            <div class="text-caption">{{ formatDate(task.timestamp) }}</div>
          </div>
        </q-card-section>
        <q-card-section>
          <div class="text-subtitle2">ID: {{ task.task_id }}</div>
          <div class="text-caption">Status: {{ task.status }}</div>
          <q-linear-progress v-if="task.status === 'PROCESSING' || task.status === 'STARTED'" indeterminate class="q-mt-sm"/>
          <div v-if="task.status === 'COMPLETED'" class="q-mt-sm">
            <div class="text-positive">Completed</div>
            <div v-if="task.result" class="q-mt-sm">
              <div class="text-weight-bold">Results:</div>
              <div v-for="(text, index) in task.result.texts" :key="index" class="q-pl-md">
                {{ index + 1 }}. <strong>{{ task.result.tags[index] }} </strong> : {{ text }}
              </div>
            </div>
          </div>
          <div v-if="task.status === 'FAILED'" class="text-negative q-mt-sm">
            Error: {{ task.error }}
          </div>
        </q-card-section>
      </q-card>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import type { TagRequest, TagStartResponse, StatusResponse, TagResult } from 'src/models'
import { api } from 'src/boot/axios'

interface TaskInfo {
  task_id: string;
  status: 'STARTED' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  message?: string;
  timestamp: string;
  result?: TagResult;
  error?: string;
}

const tagForm = ref<TagRequest>({
  tag_name: '',
  tag_definition: '',
  tag_examples: [''],
  collection_name: 'Chunks'
})

const loading = ref(false)
const allTaskInfo = ref<TaskInfo[]>([])
const pollingIntervals = ref<Map<string, number>>(new Map())

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
    const payload = { ...tagForm.value, tag_examples: tagForm.value.tag_examples.filter(example => example.trim() !== '') }
    const { data } = await api.post<TagStartResponse>('/tag', payload)
    console.log('Tagging response received:', data)
    // Store task information
    const newTaskInfo: TaskInfo = {
      task_id: data.task_id,
      status: 'STARTED',
      message: data.message,
      timestamp: new Date().toISOString()
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
      timestamp: new Date().toISOString()
    }
    allTaskInfo.value.unshift(errorTaskInfo)
  } finally {
    loading.value = false
  }
}
function startPolling (taskId: string) {
  // clear existing interval if any
  // stopPolling(taskId)
  const interval: ReturnType<typeof setInterval> = setInterval(async () => {
    try {
      // server response is inside data
      const { data } = await api.get<StatusResponse>(`/tag/status/${taskId}`)
      console.log('Polling response:', data) // Debug log
      updateTaskStatus(taskId, data.status, data.result.result)
      // stop polling when task done
      if (['COMPLETED', 'FAILED'].includes(data.status)) {
        console.log(`Stopping polling for task ${taskId}, status: ${data.status}`)
        stopPolling(taskId)
      }
    } catch (error) {
      console.error('Polling error:', error)
      // mark as failed if can't reach the status endpoint
      updateTaskStatus(taskId, 'FAILED')
      stopPolling(taskId)
    }
  }, 10000) // poll every 10 seconds
  pollingIntervals.value.set(taskId, interval)
}

function stopPolling (taskId: string) {
  const interval = pollingIntervals.value.get(taskId)
  if (interval) {
    clearInterval(interval)
    pollingIntervals.value.delete(taskId)
  }
}

function updateTaskStatus (taskId: string, status: string, result?: TagResult) {
  const index = allTaskInfo.value.findIndex(task => task.task_id === taskId)
  if (index !== -1) {
    allTaskInfo.value[index] = {
      ...allTaskInfo.value[index],
      status: status,
      result: result,
      // Preserve existing data
      timestamp: allTaskInfo.value[index].timestamp,
      message: allTaskInfo.value[index].message
    }
    console.log('Updated task status:', allTaskInfo.value[index])
  }
}

// Cleanup intervals when component is destroyed
onUnmounted(() => {
  pollingIntervals.value.forEach((interval, taskId) => { clearInterval(interval) })
  pollingIntervals.value.clear()
})
</script>
