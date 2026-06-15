<template>
  <div class="perf-results">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>服务压力测试结果</span>
          <el-button @click="loadResults">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </template>
      
      <!-- 筛选条件 -->
      <el-form :inline="true" :model="filters" class="filter-form">
        <el-form-item label="任务">
          <el-select v-model="filters.task_id" placeholder="全部任务" clearable style="width: 300px">
            <el-option
              v-for="task in tasks"
              :key="task.id"
              :label="task.name"
              :value="task.id"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="模型名称">
          <el-select
            v-model="filters.model"
            placeholder="全部模型"
            clearable
            style="width: 200px"
            @change="handleModelChange"
          >
            <el-option
              v-for="model in models"
              :key="model"
              :label="model"
              :value="model"
            />
          </el-select>
        </el-form-item>
        
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.dateRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="loadResults">查询</el-button>
        </el-form-item>
      </el-form>
      
      <!-- 历史趋势图表 -->
      <div v-if="chartData.labels.length > 0" class="history-chart-section">
        <el-divider content-position="left">
          <el-icon><TrendCharts /></el-icon>
          历史趋势
        </el-divider>
        
        <el-card shadow="hover" class="main-chart-card">
          <div ref="mainChart" style="height: 400px"></div>
        </el-card>
        
        <!-- 详细指标图表 -->
        <el-row :gutter="20" style="margin-top: 20px">
          <el-col :span="12">
            <el-card shadow="hover">
              <template #header>
                <span>延迟趋势</span>
              </template>
              <div ref="latencyChart" style="height: 300px"></div>
            </el-card>
          </el-col>
          
          <el-col :span="12">
            <el-card shadow="hover">
              <template #header>
                <span>TTFT 趋势</span>
              </template>
              <div ref="ttftChart" style="height: 300px"></div>
            </el-card>
          </el-col>
        </el-row>
        
        <el-row :gutter="20" style="margin-top: 20px">
          <el-col :span="12">
            <el-card shadow="hover">
              <template #header>
                <span>RPS 趋势</span>
              </template>
              <div ref="rpsChart" style="height: 300px"></div>
            </el-card>
          </el-col>
          
          <el-col :span="12">
            <el-card shadow="hover">
              <template #header>
                <span>生成速度趋势</span>
              </template>
              <div ref="genToksChart" style="height: 300px"></div>
            </el-card>
          </el-col>
        </el-row>
      </div>
      
      <el-empty v-else description="暂无数据" />
      
      <!-- 结果列表 -->
      <el-divider content-position="left">
        <el-icon><Document /></el-icon>
        执行历史
      </el-divider>
      
      <el-table :data="results" style="width: 100%">
        <el-table-column prop="execution_time" label="执行时间" min-width="160">
          <template #default="{ row }">
            {{ formatDate(row.execution_time) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="task_name" label="任务名称" min-width="180">
          <template #default="{ row }">
            {{ row.task_name || '-' }}
          </template>
        </el-table-column>
        
        <el-table-column prop="model_name" label="模型名称" min-width="150">
          <template #default="{ row }">
            {{ row.model_name || '-' }}
          </template>
        </el-table-column>
        
        <el-table-column prop="concurrency" label="并发数" width="90">
          <template #default="{ row }">
            {{ row.concurrency || '-' }}
          </template>
        </el-table-column>

        <el-table-column prop="schedule_mode" label="调度模式" width="100">
          <template #default="{ row }">
            <el-tag :type="getScheduleModeType(row.schedule_mode)" size="small">
              {{ getScheduleModeLabel(row.schedule_mode) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="avg_latency" label="平均延迟" min-width="100">
          <template #default="{ row }">
            {{ row.avg_latency?.toFixed(2) }}s
          </template>
        </el-table-column>
        
        <el-table-column prop="p99_latency" label="P99延迟" width="100">
          <template #default="{ row }">
            {{ row.p99_latency?.toFixed(2) }}s
          </template>
        </el-table-column>
        
        <el-table-column prop="avg_ttft" label="平均TTFT" width="100">
          <template #default="{ row }">
            {{ row.avg_ttft?.toFixed(2) }}s
          </template>
        </el-table-column>
        
        <el-table-column prop="rps" label="RPS" width="100">
          <template #default="{ row }">
            {{ row.rps?.toFixed(2) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="gen_toks" label="生成速度" width="100">
          <template #default="{ row }">
            {{ row.gen_toks?.toFixed(2) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="success_rate" label="成功率" width="100">
          <template #default="{ row }">
            <el-tag :type="row.success_rate >= 95 ? 'success' : 'danger'">
              {{ row.success_rate?.toFixed(1) }}%
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="310" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="viewReport(row)">查看报告</el-button>
            <el-button size="small" type="success" @click="viewDetail(row)">详情</el-button>
            <el-button size="small" @click="viewFile(row)">查看日志</el-button>
            <el-button size="small" type="danger" @click="deleteResult(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 日志查看对话框 -->
    <el-dialog v-model="logDialogVisible" title="执行日志" width="80%">
      <pre class="log-content">{{ logContent }}</pre>
    </el-dialog>

    <!-- 详细报告对话框 -->
    <el-dialog v-model="detailDialogVisible" title="详细测试报告" width="700px">
      <template v-if="detailResult">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务名称">{{ detailResult.task_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="模型名称">{{ detailResult.model_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="执行时间">{{ formatDate(detailResult.execution_time) }}</el-descriptions-item>
          <el-descriptions-item label="调度模式">
            <el-tag :type="getScheduleModeType(detailResult.schedule_mode)" size="small">
              {{ getScheduleModeLabel(detailResult.schedule_mode) }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="并发数">{{ detailResult.concurrency || '-' }}</el-descriptions-item>
          <el-descriptions-item label="总耗时">{{ detailResult.elapsed_seconds ? detailResult.elapsed_seconds.toFixed(2) + 's' : '-' }}</el-descriptions-item>
          <el-descriptions-item label="总请求数">{{ detailResult.total_requests || '-' }}</el-descriptions-item>
          <el-descriptions-item label="成功/失败">{{ detailResult.success_requests || 0 }} / {{ detailResult.error_requests || 0 }}</el-descriptions-item>
          <el-descriptions-item label="成功率">
            <el-tag :type="detailResult.success_rate >= 95 ? 'success' : 'danger'">
              {{ detailResult.success_rate?.toFixed(1) }}%
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="RPS">{{ detailResult.rps?.toFixed(2) }}</el-descriptions-item>
          <el-descriptions-item label="生成速度">{{ detailResult.gen_toks?.toFixed(2) }} tok/s</el-descriptions-item>
        </el-descriptions>

        <!-- 核心指标 -->
        <el-divider content-position="left">核心指标</el-divider>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="平均延迟">{{ detailResult.avg_latency?.toFixed(3) }}s</el-descriptions-item>
          <el-descriptions-item label="P99 延迟">{{ detailResult.p99_latency?.toFixed(3) }}s</el-descriptions-item>
          <el-descriptions-item label="平均 TTFT">{{ detailResult.avg_ttft?.toFixed(2) }}ms</el-descriptions-item>
          <el-descriptions-item label="P99 TTFT">{{ detailResult.p99_ttft?.toFixed(2) }}ms</el-descriptions-item>
          <el-descriptions-item label="平均 TPOT">{{ detailResult.avg_tpot?.toFixed(2) }}ms</el-descriptions-item>
          <el-descriptions-item label="P99 TPOT">{{ detailResult.p99_tpot?.toFixed(2) }}ms</el-descriptions-item>
        </el-descriptions>

        <!-- 延迟分布统计 -->
        <template v-if="detailResult.latency_stats">
          <el-divider content-position="left">延迟分布统计</el-divider>
          <el-descriptions :column="3" border>
            <el-descriptions-item label="均值">{{ detailResult.latency_stats.mean?.toFixed(4) }}s</el-descriptions-item>
            <el-descriptions-item label="中位数">{{ detailResult.latency_stats.median?.toFixed(4) }}s</el-descriptions-item>
            <el-descriptions-item label="标准差">{{ detailResult.latency_stats.std_dev?.toFixed(4) }}s</el-descriptions-item>
            <el-descriptions-item label="最小值">{{ detailResult.latency_stats.min?.toFixed(4) }}s</el-descriptions-item>
            <el-descriptions-item label="最大值">{{ detailResult.latency_stats.max?.toFixed(4) }}s</el-descriptions-item>
            <el-descriptions-item label="样本数">{{ detailResult.latency_stats.count }}</el-descriptions-item>
          </el-descriptions>
        </template>

        <!-- 完整百分位统计 -->
        <template v-if="detailResult.percentiles?.latency">
          <el-divider content-position="left">延迟百分位分布</el-divider>
          <el-table :data="Object.entries(detailResult.percentiles.latency).map(([k, v]) => ({name: k, value: v}))" size="small" border>
            <el-table-column prop="name" label="百分位" width="100" />
            <el-table-column label="延迟 (秒)">
              <template #default="{ row }">
                {{ row.value?.toFixed(4) }}s
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-if="detailResult.percentiles?.ttft">
          <el-divider content-position="left">TTFT 百分位分布</el-divider>
          <el-table :data="Object.entries(detailResult.percentiles.ttft).map(([k, v]) => ({name: k, value: v}))" size="small" border>
            <el-table-column prop="name" label="百分位" width="100" />
            <el-table-column label="TTFT (ms)">
              <template #default="{ row }">
                {{ row.value?.toFixed(2) }}ms
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-if="detailResult.percentiles?.tpot">
          <el-divider content-position="left">TPOT 百分位分布</el-divider>
          <el-table :data="Object.entries(detailResult.percentiles.tpot).map(([k, v]) => ({name: k, value: v}))" size="small" border>
            <el-table-column prop="name" label="百分位" width="100" />
            <el-table-column label="TPOT (ms)">
              <template #default="{ row }">
                {{ row.value?.toFixed(2) }}ms
              </template>
            </el-table-column>
          </el-table>
        </template>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch } from 'vue'
import { useRoute } from 'vue-router'
import { resultAPI, taskAPI } from '@/utils/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'

dayjs.extend(utc)
dayjs.extend(timezone)
import * as echarts from 'echarts'
import { TrendCharts, Document } from '@element-plus/icons-vue'

const tasks = ref([])
const models = ref([])
const results = ref([])
const chartData = ref({
  labels: [],
  datasets: {}
})

const filters = reactive({
  task_id: null,
  model: '',
  dateRange: [
    dayjs().subtract(1, 'month').toDate(),
    dayjs().toDate()
  ]
})

const logDialogVisible = ref(false)
const logContent = ref('')

const route = useRoute()

const mainChart = ref(null)
const latencyChart = ref(null)
const ttftChart = ref(null)
const rpsChart = ref(null)
const genToksChart = ref(null)

let charts = []

const loadTasks = async () => {
  try {
    const params = { type: 'perf_test' }
    
    // 如果选择了模型，筛选包含该模型的任务
    if (filters.model) {
      params.model = filters.model
    }
    
    const res = await taskAPI.getTasks(params)
    tasks.value = res.tasks
  } catch (error) {
    console.error('Failed to load tasks:', error)
  }
}

const loadModels = async () => {
  try {
    const res = await resultAPI.getPerfModels()
    models.value = res.models
  } catch (error) {
    console.error('Failed to load models:', error)
  }
}

const handleModelChange = () => {
  // 清空任务选择
  filters.task_id = null
  // 重新加载任务列表
  loadTasks()
}

const loadResults = async () => {
  try {
    const params = {}
    
    if (filters.task_id) {
      params.task_id = filters.task_id
    }
    
    if (filters.model) {
      params.model = filters.model
    }
    
    if (filters.dateRange && filters.dateRange.length === 2) {
      params.start_time = dayjs(filters.dateRange[0]).toISOString()
      params.end_time = dayjs(filters.dateRange[1]).toISOString()
    }
    
    const [resultsRes, chartRes] = await Promise.all([
      resultAPI.getPerfResults(params),
      resultAPI.getPerfChartData(params)
    ])
    
    results.value = resultsRes.results
    chartData.value = chartRes.chart_data
    
    // 渲染图表
    await nextTick()
    renderCharts()
  } catch (error) {
    console.error('Failed to load results:', error)
  }
}

const renderCharts = () => {
  // 销毁旧图表
  charts.forEach(chart => chart.dispose())
  charts = []

  if (chartData.value.labels.length === 0) return

  // 颜色配置
  const colors = [
    '#5470c6', '#91cc75', '#fac858', '#ee6666', '#73c0de',
    '#3ba272', '#fc8452', '#9a60b4', '#ea7ccc', '#48b8d0'
  ]

  // 获取所有分组名称
  const groupNames = Object.keys(chartData.value.datasets)

  const baseOption = {
    tooltip: {
      trigger: 'axis'
    },
    legend: {
      data: groupNames,
      top: 10,
      type: 'scroll'
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      top: 60,
      containLabel: true
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: chartData.value.labels,
      axisLabel: {
        rotate: 45,
        interval: Math.floor(chartData.value.labels.length / 10) || 0
      }
    },
    yAxis: {
      type: 'value'
    }
  }

  // 主图表 - 综合展示所有关键指标
  if (mainChart.value) {
    const chart = echarts.init(mainChart.value)

    // 为每个分组创建系列数据
    const series = []
    groupNames.forEach((groupName, index) => {
      const groupData = chartData.value.datasets[groupName]
      const color = colors[index % colors.length]

      series.push({
        name: groupName,
        type: 'line',
        data: groupData.avg_latency,
        smooth: true,
        itemStyle: { color }
      })
    })

    chart.setOption({
      title: {
        text: filters.task_id ? '任务历史性能趋势' : '所有任务性能趋势',
        left: 'center',
        top: 5,
        textStyle: {
          fontSize: 16,
          fontWeight: 'bold'
        }
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: {
          type: 'cross'
        }
      },
      legend: {
        data: groupNames,
        top: 35,
        type: 'scroll'
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '15%',
        top: 80,
        containLabel: true
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: chartData.value.labels,
        axisLabel: {
          rotate: 45,
          interval: Math.floor(chartData.value.labels.length / 10) || 0
        }
      },
      yAxis: {
        type: 'value',
        name: '平均延迟(s)'
      },
      series
    })
    charts.push(chart)
  }

  // 延迟图表
  if (latencyChart.value) {
    const chart = echarts.init(latencyChart.value)

    const series = []
    const legendData = []
    groupNames.forEach((groupName, index) => {
      const groupData = chartData.value.datasets[groupName]
      const color = colors[index % colors.length]

      series.push({
        name: `${groupName} - 平均`,
        type: 'line',
        data: groupData.avg_latency,
        smooth: true,
        itemStyle: { color }
      })
      series.push({
        name: `${groupName} - P99`,
        type: 'line',
        data: groupData.p99_latency,
        smooth: true,
        lineStyle: { type: 'dashed' },
        itemStyle: { color }
      })
      legendData.push(`${groupName} - 平均`, `${groupName} - P99`)
    })

    chart.setOption({
      ...baseOption,
      legend: { data: legendData, type: 'scroll' },
      yAxis: { type: 'value', name: '延迟(s)' },
      series
    })
    charts.push(chart)
  }

  // TTFT 图表
  if (ttftChart.value) {
    const chart = echarts.init(ttftChart.value)

    const series = []
    const legendData = []
    groupNames.forEach((groupName, index) => {
      const groupData = chartData.value.datasets[groupName]
      const color = colors[index % colors.length]

      series.push({
        name: `${groupName} - 平均`,
        type: 'line',
        data: groupData.avg_ttft,
        smooth: true,
        itemStyle: { color }
      })
      series.push({
        name: `${groupName} - P99`,
        type: 'line',
        data: groupData.p99_ttft,
        smooth: true,
        lineStyle: { type: 'dashed' },
        itemStyle: { color }
      })
      legendData.push(`${groupName} - 平均`, `${groupName} - P99`)
    })

    chart.setOption({
      ...baseOption,
      legend: { data: legendData, type: 'scroll' },
      yAxis: { type: 'value', name: 'TTFT(s)' },
      series
    })
    charts.push(chart)
  }

  // RPS 图表
  if (rpsChart.value) {
    const chart = echarts.init(rpsChart.value)

    const series = []
    groupNames.forEach((groupName, index) => {
      const groupData = chartData.value.datasets[groupName]
      const color = colors[index % colors.length]

      series.push({
        name: groupName,
        type: 'line',
        data: groupData.rps,
        smooth: true,
        itemStyle: { color }
      })
    })

    chart.setOption({
      ...baseOption,
      legend: { data: groupNames, type: 'scroll' },
      yAxis: { type: 'value', name: 'RPS' },
      series
    })
    charts.push(chart)
  }

  // 生成速度图表
  if (genToksChart.value) {
    const chart = echarts.init(genToksChart.value)

    const series = []
    groupNames.forEach((groupName, index) => {
      const groupData = chartData.value.datasets[groupName]
      const color = colors[index % colors.length]

      series.push({
        name: groupName,
        type: 'line',
        data: groupData.gen_toks,
        smooth: true,
        itemStyle: { color }
      })
    })

    chart.setOption({
      ...baseOption,
      legend: { data: groupNames, type: 'scroll' },
      yAxis: { type: 'value', name: '生成速度(tokens/s)' },
      series
    })
    charts.push(chart)
  }
}

const viewFile = async (row) => {
  try {
    const response = await fetch(`/api/results/perf/${row.id}/file`)
    const text = await response.text()
    logContent.value = text
    logDialogVisible.value = true
  } catch (error) {
    console.error('Failed to load file:', error)
  }
}

const viewReport = (row) => {
  window.open(`/api/results/perf/${row.id}/view`, '_blank')
}

const viewDetail = (row) => {
  detailResult.value = row
  detailDialogVisible.value = true
}

const detailDialogVisible = ref(false)
const detailResult = ref(null)

const deleteResult = async (row) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除这条测试结果吗？执行时间：${formatDate(row.execution_time)}`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await resultAPI.deletePerfResult(row.id)
    ElMessage.success('删除成功')
    loadResults()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to delete result:', error)
    }
  }
}

const getScheduleModeLabel = (mode) => {
  const map = {
    'concurrent': '并发',
    'constant_rate': '恒速',
    'poisson': '泊松',
    'throughput': '吞吐',
    'sweep': '扫描',
    'replay': '回放',
  }
  return map[mode] || '并发'
}

const getScheduleModeType = (mode) => {
  const map = {
    'concurrent': '',
    'constant_rate': 'success',
    'poisson': 'warning',
    'throughput': 'danger',
    'sweep': 'info',
    'replay': '',
  }
  return map[mode] || ''
}

const formatDate = (date) => {
  if (!date) return '-'
  // 后端返回的已经是本地时间（北京时间），直接格式化显示
  let normalizedDate = date
  if (!date.includes('T')) {
    normalizedDate = date.replace(' ', 'T')
  }
  return dayjs(normalizedDate).format('YYYY-MM-DD HH:mm')
}

onMounted(async () => {
  // 检查 URL 参数中是否有 task_id
  if (route.query.task_id) {
    filters.task_id = parseInt(route.query.task_id)
  }
  
  await loadTasks()
  await loadModels()
  loadResults()
})

// 监听窗口大小变化，重新渲染图表
window.addEventListener('resize', () => {
  charts.forEach(chart => chart.resize())
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

.history-chart-section {
  margin-bottom: 20px;
}

.main-chart-card {
  margin-bottom: 20px;
}

.charts-container {
  margin-bottom: 20px;
}

.log-content {
  background-color: #f5f5f5;
  padding: 15px;
  border-radius: 4px;
  overflow: auto;
  max-height: 600px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
}
</style>