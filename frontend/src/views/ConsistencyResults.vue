<template>
  <div class="consistency-results">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>一致性测试结果</span>
          <el-button @click="loadResults()">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="任务">
          <el-select v-model="filters.task_id" placeholder="全部任务" clearable style="width: 300px">
            <el-option v-for="t in tasks" :key="t.id" :label="t.name" :value="t.id" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadResults">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="results" style="width: 100%" border stripe>
        <el-table-column prop="execution_time" label="执行时间" min-width="140">
          <template #default="{ row }">{{ formatDate(row.execution_time) }}</template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型" min-width="120" />
        <el-table-column prop="prompt_ref" label="Prompt" min-width="160" show-overflow-tooltip />
        <el-table-column prop="iterations" label="迭代次数" min-width="80" />
        <el-table-column label="平均相似度" min-width="100">
          <template #default="{ row }">
            <span :class="getScoreClass(row.similarity_mean)">
              {{ row.similarity_mean != null ? (row.similarity_mean * 100).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="最低相似度" min-width="100">
          <template #default="{ row }">
            <span :class="getScoreClass(row.similarity_min)">
              {{ row.similarity_min != null ? (row.similarity_min * 100).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="通过" min-width="80">
          <template #default="{ row }">
            <el-tag :type="row.passed ? 'success' : 'danger'">{{ row.passed ? '通过' : '失败' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" min-width="80">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'success'" type="success">成功</el-tag>
            <el-tag v-else type="danger">失败</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="响应详情" min-width="120">
          <template #default="{ row }">
            <el-button size="small" @click="viewResponses(row)">查看</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="deleteResult(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="responsesVisible" title="迭代响应详情" width="70%" top="5vh">
      <div v-for="(resp, idx) in selectedResponses" :key="idx" class="response-item">
        <h4>第 {{ idx + 1 }} 次调用</h4>
        <div class="response-text">{{ resp }}</div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { consistencyAPI, taskAPI } from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const results = ref([])
const tasks = ref([])
const filters = reactive({ task_id: null })
const responsesVisible = ref(false)
const selectedResponses = ref([])

const loadTasks = async () => {
  try {
    const res = await taskAPI.getTasks({ type: 'consistency_test' })
    tasks.value = res.tasks
  } catch (e) { /* ignore */ }
}

const loadResults = async () => {
  try {
    const params = {}
    if (filters.task_id) params.task_id = filters.task_id
    const res = await consistencyAPI.getResults(params)
    results.value = res.results || []
  } catch (e) {
    console.error('Failed to load consistency results:', e)
  }
}

const viewResponses = (row) => {
  selectedResponses.value = row.responses || []
  responsesVisible.value = true
}

const deleteResult = async (row) => {
  try {
    await ElMessageBox.confirm('确定删除该结果？', '提示', { type: 'warning' })
    await consistencyAPI.deleteResult(row.id)
    ElMessage.success('已删除')
    loadResults()
  } catch (e) { /* cancelled */ }
}

const formatDate = (d) => {
  if (!d) return '-'
  return dayjs(d.includes('T') ? d : d.replace(' ', 'T')).format('YYYY-MM-DD HH:mm')
}

const getScoreClass = (val) => {
  if (val == null) return ''
  if (val >= 0.8) return 'score-high'
  if (val >= 0.5) return 'score-mid'
  return 'score-low'
}

onMounted(() => {
  loadTasks()
  loadResults()
})
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.filter-form { margin-bottom: 16px; }
.response-item { margin-bottom: 16px; border-left: 3px solid #409EFF; padding-left: 12px; }
.response-item h4 { margin: 0 0 8px 0; color: #409EFF; }
.response-text { white-space: pre-wrap; font-size: 14px; line-height: 1.7; color: #333; }
.score-high { color: #67C23A; font-weight: 600; }
.score-mid { color: #E6A23C; font-weight: 600; }
.score-low { color: #F56C6C; font-weight: 600; }
</style>
