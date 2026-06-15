<template>
  <div class="regression-results">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>回归测试结果</span>
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
        <el-table-column label="基线均分" min-width="90">
          <template #default="{ row }">
            {{ row.baseline_avg_score != null ? row.baseline_avg_score.toFixed(3) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="当前均分" min-width="90">
          <template #default="{ row }">
            {{ row.current_avg_score != null ? row.current_avg_score.toFixed(3) : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="分数变化" min-width="90">
          <template #default="{ row }">
            <span :class="row.score_delta >= 0 ? 'score-up' : 'score-down'">
              {{ row.score_delta != null ? (row.score_delta >= 0 ? '+' : '') + row.score_delta.toFixed(3) : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="基线延迟" min-width="90">
          <template #default="{ row }">
            {{ row.baseline_avg_latency != null ? row.baseline_avg_latency.toFixed(3) + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="当前延迟" min-width="90">
          <template #default="{ row }">
            {{ row.current_avg_latency != null ? row.current_avg_latency.toFixed(3) + 's' : '-' }}
          </template>
        </el-table-column>
        <el-table-column label="延迟比" min-width="80">
          <template #default="{ row }">
            <span :class="row.latency_ratio > 1.0 ? 'score-down' : 'score-up'">
              {{ row.latency_ratio != null ? row.latency_ratio.toFixed(2) + 'x' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="准确率退化" min-width="100">
          <template #default="{ row }">
            <el-tag v-if="row.accuracy_degraded" type="danger">是</el-tag>
            <el-tag v-else type="success">否</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="延迟退化" min-width="90">
          <template #default="{ row }">
            <el-tag v-if="row.latency_degraded" type="danger">是</el-tag>
            <el-tag v-else type="success">否</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="通过" min-width="80">
          <template #default="{ row }">
            <el-tag :type="row.passed ? 'success' : 'danger'">{{ row.passed ? '通过' : '未通过' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="详情" min-width="80">
          <template #default="{ row }">
            <el-button size="small" @click="viewDetail(row)">查看</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="80">
          <template #default="{ row }">
            <el-button size="small" type="danger" @click="deleteResult(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailVisible" title="逐样本对比详情" width="80%" top="5vh">
      <el-table :data="selectedDetail" border stripe max-height="500">
        <el-table-column prop="prompt_name" label="Prompt" min-width="160" />
        <el-table-column label="当前分数" min-width="90">
          <template #default="{ row }">{{ row.score?.toFixed(3) }}</template>
        </el-table-column>
        <el-table-column label="基线分数" min-width="90">
          <template #default="{ row }">{{ row.baseline_score != null ? row.baseline_score.toFixed(3) : '-' }}</template>
        </el-table-column>
        <el-table-column label="当前延迟" min-width="90">
          <template #default="{ row }">{{ row.latency?.toFixed(3) }}s</template>
        </el-table-column>
        <el-table-column label="基线延迟" min-width="90">
          <template #default="{ row }">{{ row.baseline_latency != null ? row.baseline_latency.toFixed(3) + 's' : '-' }}</template>
        </el-table-column>
        <el-table-column prop="response" label="响应" min-width="300" show-overflow-tooltip />
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { regressionAPI, taskAPI } from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'

const results = ref([])
const tasks = ref([])
const filters = reactive({ task_id: null })
const detailVisible = ref(false)
const selectedDetail = ref([])

const loadTasks = async () => {
  try {
    const res = await taskAPI.getTasks({ type: 'regression_test' })
    tasks.value = res.tasks
  } catch (e) { /* ignore */ }
}

const loadResults = async () => {
  try {
    const params = {}
    if (filters.task_id) params.task_id = filters.task_id
    const res = await regressionAPI.getResults(params)
    results.value = res.results || []
  } catch (e) {
    console.error('Failed to load regression results:', e)
  }
}

const viewDetail = (row) => {
  selectedDetail.value = row.detail || []
  detailVisible.value = true
}

const deleteResult = async (row) => {
  try {
    await ElMessageBox.confirm('确定删除该结果？', '提示', { type: 'warning' })
    await regressionAPI.deleteResult(row.id)
    ElMessage.success('已删除')
    loadResults()
  } catch (e) { /* cancelled */ }
}

const formatDate = (d) => {
  if (!d) return '-'
  return dayjs(d.includes('T') ? d : d.replace(' ', 'T')).format('YYYY-MM-DD HH:mm')
}

onMounted(() => {
  loadTasks()
  loadResults()
})
</script>

<style scoped>
.card-header { display: flex; justify-content: space-between; align-items: center; }
.filter-form { margin-bottom: 16px; }
.score-up { color: #67C23A; font-weight: 600; }
.score-down { color: #F56C6C; font-weight: 600; }
</style>
