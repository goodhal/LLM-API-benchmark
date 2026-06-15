<template>
  <div class="quality-results">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>安全审计结果</span>
          <el-button @click="loadAuditResults()">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>

      <el-form :inline="true" :model="auditFilters" class="filter-form">
        <el-form-item label="任务">
          <el-select v-model="auditFilters.task_id" placeholder="全部任务" clearable style="width: 300px">
            <el-option
              v-for="task in auditTasks"
              :key="task.id"
              :label="task.name"
              :value="task.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="auditFilters.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadAuditResults">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="auditResults" style="width: 100%" border stripe>
        <el-table-column type="expand">
          <template #default="{ row }">
            <div v-if="row.enhanced_scores" class="enhanced-scores-panel">
              <h4>增强评分详情（PyRIT 多维度评分体系）</h4>
              <el-descriptions :column="3" border>
                <el-descriptions-item label="总样本数">{{ row.enhanced_scores.total_samples }}</el-descriptions-item>
                <el-descriptions-item label="拒答次数">{{ row.enhanced_scores.refusal_count }}</el-descriptions-item>
                <el-descriptions-item label="拒答率">
                  {{ row.enhanced_scores.total_samples > 0
                    ? (row.enhanced_scores.refusal_count / row.enhanced_scores.total_samples * 100).toFixed(1) + '%'
                    : 'N/A' }}
                </el-descriptions-item>
              </el-descriptions>
              <h5 style="margin-top: 12px;">平均评分</h5>
              <el-descriptions :column="3" border>
                <el-descriptions-item
                  v-for="(val, key) in row.enhanced_scores.avg_scores"
                  :key="key"
                  :label="key"
                >{{ val.toFixed(4) }}</el-descriptions-item>
              </el-descriptions>
              <h5 style="margin-top: 12px;">伤害类别分布</h5>
              <el-descriptions :column="3" border>
                <el-descriptions-item
                  v-for="(count, cat) in row.enhanced_scores.harm_categories"
                  :key="cat"
                  :label="cat"
                >{{ count }}</el-descriptions-item>
              </el-descriptions>
            </div>
            <div v-else style="padding: 20px; color: #999;">
              无增强评分数据（此结果由标准 audit.py 生成）
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="execution_time" label="执行时间" min-width="140">
          <template #default="{ row }">
            {{ formatDate(row.execution_time) }}
          </template>
        </el-table-column>
        <el-table-column prop="overall_rating" label="总体评级" min-width="120">
          <template #default="{ row }">
            <el-tag :type="getRatingType(row.overall_rating)">
              {{ row.overall_rating || '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="1.基础设施侦察" min-width="180">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.infrastructure_recon">{{ row.infrastructure_recon }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="2.模型列表枚举" min-width="180">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.models_enumerated">{{ row.models_enumerated }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="3.Token注入检测" min-width="180">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.token_injection">{{ row.token_injection }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="4.Prompt提取" min-width="180">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.prompt_extraction">{{ row.prompt_extraction }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="5.指令冲突+身份替换" min-width="200">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.instruction_override">{{ row.instruction_override }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="6.越狱测试" min-width="180">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.jailbreak_test">{{ row.jailbreak_test }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="7.上下文长度扫描" min-width="200">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.context_boundary">{{ row.context_boundary }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="8.工具调用改写" min-width="180">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.tool_call_substitution">{{ row.tool_call_substitution }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="9.错误响应泄漏" min-width="180">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.error_response_leakage">{{ row.error_response_leakage }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="10.流完整性" min-width="180">
          <template #default="{ row }">
            <div class="risk-item" v-if="row.stream_integrity">{{ row.stream_integrity }}</div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewReport(row)">查看报告</el-button>
            <el-button size="small" type="danger" @click="deleteAuditResult(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { resultAPI, taskAPI } from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)

const auditTasks = ref([])
const auditResults = ref([])
const auditFilters = reactive({ task_id: null, dateRange: null })

const loadAuditTasks = async () => {
  try {
    const res = await taskAPI.getTasks({ type: 'safety_audit' })
    auditTasks.value = res.tasks
  } catch (error) {
    console.error('Failed to load audit tasks:', error)
  }
}

const loadAuditResults = async () => {
  try {
    const params = {}
    if (auditFilters.task_id) params.task_id = auditFilters.task_id
    if (auditFilters.dateRange && auditFilters.dateRange.length === 2) {
      params.start_time = dayjs(auditFilters.dateRange[0]).toISOString()
      params.end_time = dayjs(auditFilters.dateRange[1]).toISOString()
    }
    const res = await resultAPI.getQualityResults(params)
    auditResults.value = res.results
  } catch (error) {
    console.error('Failed to load audit results:', error)
  }
}

const viewReport = (row) => {
  window.open(`/api/results/quality/${row.id}/view`, '_blank')
}

const deleteAuditResult = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除这条测试结果吗？执行时间：${formatDate(row.execution_time)}`,
      '确认删除',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
    await resultAPI.deleteQualityResult(row.id)
    ElMessage.success('删除成功')
    loadAuditResults()
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

const getRatingType = (rating) => {
  if (!rating) return 'info'
  if (rating.includes('HIGH')) return 'danger'
  if (rating.includes('MEDIUM')) return 'warning'
  if (rating.includes('LOW')) return 'success'
  return 'info'
}

onMounted(() => {
  loadAuditTasks()
  loadAuditResults()
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

.risk-item {
  word-break: break-word;
  line-height: 1.5;
}
</style>