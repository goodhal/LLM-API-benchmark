<template>
  <div class="system-monitor">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>系统资源监控</span>
          <el-button size="small" @click="refresh" :loading="loading" :icon="Refresh">刷新</el-button>
        </div>
      </template>

      <div v-if="metrics" class="metrics-grid">
        <!-- CPU -->
        <div class="metric-card">
          <div class="metric-label">CPU 使用率</div>
          <el-progress
            :percentage="metrics.cpu_percent"
            :color="getProgressColor(metrics.cpu_percent)"
            :stroke-width="18"
            :text-inside="true"
          />
          <div class="metric-detail">{{ metrics.cpu_count }} 核心</div>
        </div>

        <!-- 内存 -->
        <div class="metric-card">
          <div class="metric-label">内存使用率</div>
          <el-progress
            :percentage="metrics.memory_percent"
            :color="getProgressColor(metrics.memory_percent)"
            :stroke-width="18"
            :text-inside="true"
          />
          <div class="metric-detail">{{ metrics.memory_used_gb }}GB / {{ metrics.memory_total_gb }}GB</div>
        </div>

        <!-- 磁盘 -->
        <div class="metric-card">
          <div class="metric-label">磁盘使用率</div>
          <el-progress
            :percentage="metrics.disk_percent"
            :color="getProgressColor(metrics.disk_percent)"
            :stroke-width="18"
            :text-inside="true"
          />
          <div class="metric-detail">{{ metrics.disk_used_gb }}GB / {{ metrics.disk_total_gb }}GB</div>
        </div>

        <!-- 进程内存 -->
        <div class="metric-card">
          <div class="metric-label">服务进程内存</div>
          <div class="metric-value">{{ metrics.process_memory_mb }} MB</div>
        </div>

        <!-- 运行时间 -->
        <div class="metric-card">
          <div class="metric-label">系统运行时间</div>
          <div class="metric-value">{{ formatUptime(metrics.uptime_seconds) }}</div>
        </div>

        <!-- GPU -->
        <div v-if="metrics.gpu && metrics.gpu.length > 0" class="metric-card gpu-card">
          <div class="metric-label">GPU</div>
          <div v-for="gpu in metrics.gpu" :key="gpu.index" class="gpu-item">
            <div class="gpu-name">{{ gpu.name }}</div>
            <el-progress
              :percentage="gpu.utilization_percent || (gpu.allocated_gb / gpu.total_memory_gb * 100)"
              :color="getProgressColor(gpu.utilization_percent || (gpu.allocated_gb / gpu.total_memory_gb * 100))"
              :stroke-width="14"
              :text-inside="true"
            />
            <div class="metric-detail">
              {{ gpu.allocated_gb || gpu.used_memory_gb || 0 }}GB / {{ gpu.total_memory_gb }}GB
            </div>
          </div>
        </div>

        <div v-if="metrics.gpu === null" class="metric-card">
          <div class="metric-label">GPU</div>
          <div class="metric-value" style="color: #909399">未检测到</div>
        </div>
      </div>

      <el-empty v-else description="加载中..." />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import api from '@/utils/api'

const metrics = ref(null)
const loading = ref(false)
let timer = null

onMounted(async () => {
  await refresh()
  // 每30秒自动刷新
  timer = setInterval(refresh, 30000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

async function refresh() {
  loading.value = true
  try {
    const data = await api.get('/compare/system-metrics')
    metrics.value = data
  } catch (e) {
    console.error('获取系统指标失败:', e)
  } finally {
    loading.value = false
  }
}

function getProgressColor(percent) {
  if (percent >= 90) return '#f56c6c'
  if (percent >= 70) return '#e6a23c'
  return '#67c23a'
}

function formatUptime(seconds) {
  if (!seconds) return '-'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}天${h}小时`
  if (h > 0) return `${h}小时${m}分钟`
  return `${m}分钟`
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.metric-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
}

.metric-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.metric-value {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
}

.metric-detail {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}

.gpu-card {
  grid-column: span 3;
}

.gpu-item {
  margin-bottom: 12px;
}

.gpu-item:last-child {
  margin-bottom: 0;
}

.gpu-name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}

@media (max-width: 768px) {
  .metrics-grid {
    grid-template-columns: 1fr;
  }
  .gpu-card {
    grid-column: span 1;
  }
}
</style>
