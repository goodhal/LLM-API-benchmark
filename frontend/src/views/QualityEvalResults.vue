<template>
  <div class="quality-eval-results">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>质量评测结果</span>
          <el-button @click="loadEvalResults()">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-form :inline="true" :model="evalFilters" class="filter-form">
        <el-form-item label="任务">
          <el-select v-model="evalFilters.task_id" placeholder="全部任务" clearable style="width: 300px">
            <el-option
              v-for="task in evalTasks"
              :key="task.id"
              :label="task.name"
              :value="task.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="evalFilters.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadEvalResults">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="evalResults" style="width: 100%" border stripe>
        <el-table-column prop="execution_time" label="执行时间" min-width="140">
          <template #default="{ row }">
            {{ formatDate(row.execution_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="model_name" label="模型" min-width="150" />
        <el-table-column prop="sample_count" label="样本数" min-width="80" />
        <el-table-column label="Exact Match" min-width="100">
          <template #default="{ row }">
            <span :class="getScoreClass(row.metrics?.exact_match)">{{ formatScore(row.metrics?.exact_match) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Contains Match" min-width="110">
          <template #default="{ row }">
            <span :class="getScoreClass(row.metrics?.contains_match)">{{ formatScore(row.metrics?.contains_match) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Token F1" min-width="100">
          <template #default="{ row }">
            <span :class="getScoreClass(row.metrics?.token_f1)">{{ formatScore(row.metrics?.token_f1) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Rouge-L" min-width="100">
          <template #default="{ row }">
            <span :class="getScoreClass(row.metrics?.rouge_l)">{{ formatScore(row.metrics?.rouge_l) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="LLM Judge" min-width="100">
          <template #default="{ row }">
            <span :class="getScoreClass(row.metrics?.llm_judge)">{{ formatJudgeScore(row.metrics?.llm_judge) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="dataset_path" label="数据集" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" min-width="120">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'success'" type="success">成功</el-tag>
            <el-tag v-else-if="row.status === 'error'" type="danger">失败</el-tag>
            <el-tag v-else type="info">{{ row.status }}</el-tag>
            <div v-if="row.error_message" class="error-tip">{{ row.error_message }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="240" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewReport(row)">查看报告</el-button>
            <el-button size="small" @click="viewLog(row)">日志</el-button>
            <el-button size="small" type="danger" @click="deleteEvalResult(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 执行日志对话框 -->
    <el-dialog v-model="logVisible" title="执行日志" width="80%" :close-on-click-modal="false" top="5vh">
      <div class="log-content">
        <pre>{{ logContent }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { resultAPI, taskAPI, logAPI } from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

const evalTasks = ref([])
const evalResults = ref([])
const evalFilters = reactive({ task_id: null, dateRange: null })

const loadEvalTasks = async () => {
  try {
    const res = await taskAPI.getTasks({ type: 'quality_eval' })
    evalTasks.value = res.tasks
  } catch (error) {
    console.error('Failed to load eval tasks:', error)
  }
}

const loadEvalResults = async () => {
  try {
    const params = {}
    if (evalFilters.task_id) params.task_id = evalFilters.task_id
    if (evalFilters.dateRange && evalFilters.dateRange.length === 2) {
      params.start_time = dayjs(evalFilters.dateRange[0]).toISOString()
      params.end_time = dayjs(evalFilters.dateRange[1]).toISOString()
    }
    const res = await resultAPI.getQualityEvalResults(params)
    evalResults.value = res.results
  } catch (error) {
    console.error('Failed to load eval results:', error)
  }
}

const viewReport = (row) => {
  window.open(`/api/results/quality-eval/${row.id}/view`, '_blank')
}

// 日志查看
const logVisible = ref(false)
const logContent = ref('')

const viewLog = async (row) => {
  try {
    const res = await logAPI.getQualityEvalLog(row.id)
    logContent.value = res.log || '(无日志内容)'
    logVisible.value = true
  } catch (error) {
    if (error.response?.status === 404) {
      ElMessage.warning('该结果没有日志文件')
    } else {
      ElMessage.error('加载日志失败')
    }
  }
}

const deleteEvalResult = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除这条评测结果吗？执行时间：${formatDate(row.execution_time)}`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await resultAPI.deleteQualityEvalResult(row.id)
    ElMessage.success('删除成功')
    loadEvalResults()
  } catch (error) {
    if (error !== 'cancel') console.error('Failed to delete result:', error)
  }
}

const formatDate = (date) => {
  if (!date) return '-'
  let normalizedDate = date
  if (!date.includes('T')) normalizedDate = date.replace(' ', 'T')
  return dayjs(normalizedDate).format('YYYY-MM-DD HH:mm')
}

const formatScore = (val) => {
  if (val === undefined || val === null || isNaN(val)) return '-'
  return (val * 100).toFixed(1) + '%'
}

const formatJudgeScore = (val) => {
  if (val === undefined || val === null || isNaN(val)) return '-'
  // 归一化值还原为1-5分制
  const score = val * 4 + 1
  return score.toFixed(1) + '/5'
}

const getScoreClass = (val) => {
  if (val === undefined || val === null || isNaN(val)) return ''
  if (val >= 0.8) return 'score-high'
  if (val >= 0.5) return 'score-medium'
  return 'score-low'
}

onMounted(() => {
  loadEvalTasks()
  loadEvalResults()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-form {
  margin-bottom: 20px;
}

.score-high {
  color: #67c23a;
  font-weight: 600;
}

.score-medium {
  color: #e6a23c;
  font-weight: 600;
}

.score-low {
  color: #f56c6c;
  font-weight: 600;
}

.error-tip {
  font-size: 12px;
  color: #f56c6c;
  margin-top: 4px;
}

.log-content {
  max-height: 70vh;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: 4px;
  padding: 16px;
}

.log-content pre {
  color: #d4d4d4;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
