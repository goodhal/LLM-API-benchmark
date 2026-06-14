<template>
  <div class="model-compare">
    <!-- 输入区域 -->
    <el-card class="input-card">
      <template #header>
        <div class="card-header">
          <span>模型对比测试</span>
          <el-tag type="info" size="small">支持多模型并行对比</el-tag>
        </div>
      </template>

      <div class="input-area">
        <div class="input-row">
          <el-input
            v-model="testPrompt"
            type="textarea"
            :rows="3"
            placeholder="请输入测试文本，或从右侧选择测试用例..."
            class="prompt-input"
          />
          <div class="test-case-select">
            <el-select
              v-model="selectedTestCase"
              placeholder="选择测试用例"
              clearable
              @change="onTestCaseChange"
            >
              <el-option-group
                v-for="cat in categories"
                :key="cat"
                :label="cat"
              >
                <el-option
                  v-for="tc in getCasesByCategory(cat)"
                  :key="tc.id"
                  :label="tc.name"
                  :value="tc.id"
                >
                  <span>{{ tc.name }}</span>
                  <span class="case-desc">{{ tc.description }}</span>
                </el-option>
              </el-option-group>
            </el-select>
            <el-select
              v-model="selectedDataset"
              placeholder="从数据集选择"
              clearable
              style="margin-top: 8px"
              @change="onDatasetChange"
            >
              <el-option
                v-for="ds in datasetList"
                :key="ds.path"
                :label="`${ds.name} (${ds.format})`"
                :value="ds.path"
              />
            </el-select>
          </div>
        </div>

        <div class="action-row">
          <el-button type="primary" @click="addModelCard" :icon="Plus">添加模型</el-button>
          <el-button
            type="success"
            @click="runCompare"
            :loading="isRunning"
            :disabled="modelCards.length === 0 || !testPrompt.trim()"
          >
            执行对比测试
          </el-button>
          <el-button @click="clearAll" :disabled="isRunning">清空</el-button>
        </div>
      </div>
    </el-card>

    <!-- 模型卡片区域 -->
    <div class="cards-row" v-if="modelCards.length > 0">
      <div
        v-for="(card, index) in modelCards"
        :key="card.id"
        class="model-card"
        :class="{ 'card-running': card.status === 'running', 'card-error': card.status === 'error' }"
      >
        <div class="card-header-bar">
          <div class="card-title">
            <el-tag :type="card.config.type === 'ollama' ? 'success' : 'primary'" size="small">
              {{ card.config.type === 'ollama' ? 'Ollama' : 'OpenAI' }}
            </el-tag>
            <span class="model-name">{{ card.config.model || '未配置' }}</span>
          </div>
          <el-button
            type="danger"
            size="small"
            circle
            :icon="Close"
            @click="removeCard(index)"
            :disabled="isRunning"
          />
        </div>

        <!-- 测试主题 -->
        <div v-if="currentTestCase" class="test-title-bar">
          <el-tag type="warning" size="small">{{ currentTestCase.name }}</el-tag>
        </div>

        <!-- 输出区域 -->
        <div class="output-area" ref="outputAreas">
          <div v-if="card.status === 'pending'" class="status-placeholder">
            等待执行...
          </div>
          <div v-else-if="card.status === 'running'" class="status-placeholder running">
            <el-icon class="is-loading"><Loading /></el-icon>
            正在生成...
          </div>
          <div v-else class="output-text">{{ card.output }}</div>
        </div>

        <!-- 异常检测 -->
        <div v-if="card.anomalies.length > 0" class="anomaly-section">
          <div v-for="(a, ai) in card.anomalies" :key="ai" class="anomaly-item" :class="'anomaly-' + a.severity">
            <el-icon v-if="a.severity === 'error'"><CircleCloseFilled /></el-icon>
            <el-icon v-else-if="a.severity === 'warning'"><WarningFilled /></el-icon>
            <el-icon v-else><InfoFilled /></el-icon>
            {{ a.message }}
          </div>
        </div>

        <!-- 指标 -->
        <div class="metrics-bar">
          <span v-if="card.latencyMs > 0" class="metric">
            耗时: <strong>{{ card.latencyMs }}ms</strong>
          </span>
          <span v-if="card.output" class="metric">
            字数: <strong>{{ card.output.length }}</strong>
          </span>
          <el-tag v-if="card.status === 'completed' && card.anomalies.length === 0" type="success" size="small">
            正常
          </el-tag>
          <el-tag v-else-if="card.status === 'completed' && card.anomalies.length > 0" type="warning" size="small">
            {{ card.anomalies.length }}个异常
          </el-tag>
          <el-tag v-else-if="card.status === 'error'" type="danger" size="small">
            失败
          </el-tag>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <el-empty v-else description="请添加模型开始对比测试" />

    <!-- 添加模型弹窗 -->
    <el-dialog v-model="addDialogVisible" title="添加测试模型" width="500px">
      <el-form :model="newModelForm" label-width="100px">
        <el-form-item label="模型类型">
          <el-radio-group v-model="newModelForm.type">
            <el-radio label="openai">OpenAI 兼容 API</el-radio>
            <el-radio label="ollama">Ollama 本地模型</el-radio>
          </el-radio-group>
        </el-form-item>

        <template v-if="newModelForm.type === 'openai'">
          <el-form-item label="API URL">
            <el-input v-model="newModelForm.url" placeholder="https://api.example.com/v1" />
          </el-form-item>
          <el-form-item label="API Key">
            <el-input v-model="newModelForm.api_key" type="password" placeholder="sk-xxxx" />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-input v-model="newModelForm.model" placeholder="gpt-3.5-turbo" />
          </el-form-item>
        </template>

        <template v-if="newModelForm.type === 'ollama'">
          <el-form-item label="Ollama地址">
            <el-input v-model="newModelForm.url" placeholder="http://localhost:11434" />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-input v-model="newModelForm.model" placeholder="qwen2:7b" />
          </el-form-item>
        </template>

        <el-form-item label="Temperature">
          <el-slider v-model="newModelForm.temperature" :min="0" :max="2" :step="0.1" show-input />
        </el-form-item>

        <el-form-item label="Max Tokens">
          <el-input-number v-model="newModelForm.max_tokens" :min="64" :max="8192" :step="256" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddModel">确认添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Close, Loading, CircleCloseFilled, WarningFilled, InfoFilled } from '@element-plus/icons-vue'
import api from '@/utils/api'
import { taskAPI } from '@/utils/api'

const testPrompt = ref('')
const selectedTestCase = ref('')
const selectedDataset = ref('')
const datasetList = ref([])
const datasetPrompts = ref([])
const testCases = ref([])
const categories = ref([])
const currentTestCase = ref(null)
const isRunning = ref(false)
const addDialogVisible = ref(false)

const modelCards = ref([])
let cardIdCounter = 0

const newModelForm = ref({
  type: 'openai',
  url: '',
  api_key: '',
  model: '',
  temperature: 0.7,
  max_tokens: 2000
})

const outputAreas = ref([])

onMounted(async () => {
  await loadTestCases()
  loadDatasets()
})

async function loadDatasets() {
  try {
    const res = await taskAPI.getDatasets()
    datasetList.value = res.datasets || []
  } catch (e) {
    console.error('加载数据集列表失败:', e)
  }
}

async function loadTestCases() {
  try {
    const [casesRes, catRes] = await Promise.all([
      api.get('/compare/test-cases'),
      api.get('/compare/test-cases/categories')
    ])
    testCases.value = casesRes.cases || []
    categories.value = catRes.categories || []
  } catch (e) {
    console.error('加载测试用例失败:', e)
  }
}

function getCasesByCategory(cat) {
  return testCases.value.filter(c => c.category === cat)
}

function onTestCaseChange(id) {
  if (!id) {
    currentTestCase.value = null
    return
  }
  const tc = testCases.value.find(c => c.id === id)
  if (tc) {
    testPrompt.value = tc.prompt
    currentTestCase.value = tc
    selectedDataset.value = ''
  }
}

async function onDatasetChange(path) {
  if (!path) {
    datasetPrompts.value = []
    return
  }
  try {
    const res = await api.get('/compare/dataset-prompts', { params: { path } })
    const prompts = res.prompts || []
    if (prompts.length === 0) {
      ElMessage.warning('数据集为空')
      return
    }
    datasetPrompts.value = prompts
    // 默认填入第一条
    testPrompt.value = prompts[0].prompt
    selectedTestCase.value = ''
    currentTestCase.value = null
    ElMessage.success(`已加载数据集，共 ${prompts.length} 条`)
  } catch (e) {
    ElMessage.error('加载数据集失败: ' + (e.response?.data?.error || e.message))
  }
}

function addModelCard() {
  newModelForm.value = {
    type: 'openai',
    url: '',
    api_key: '',
    model: '',
    temperature: 0.7,
    max_tokens: 2000
  }
  addDialogVisible.value = true
}

function confirmAddModel() {
  const form = newModelForm.value
  if (!form.model) {
    ElMessage.warning('请输入模型名称')
    return
  }
  if (form.type === 'openai' && !form.url) {
    ElMessage.warning('请输入 API URL')
    return
  }

  modelCards.value.push({
    id: ++cardIdCounter,
    config: { ...form },
    status: 'pending',
    output: '',
    anomalies: [],
    latencyMs: 0
  })
  addDialogVisible.value = false
  ElMessage.success(`已添加模型: ${form.model}`)
}

function removeCard(index) {
  modelCards.value.splice(index, 1)
}

function clearAll() {
  modelCards.value = []
  testPrompt.value = ''
  selectedTestCase.value = ''
  selectedDataset.value = ''
  datasetPrompts.value = []
  currentTestCase.value = null
}

async function runCompare() {
  if (modelCards.value.length === 0) {
    ElMessage.warning('请先添加模型')
    return
  }
  if (!testPrompt.value.trim()) {
    ElMessage.warning('请输入测试文本')
    return
  }

  isRunning.value = true

  // 重置所有卡片状态
  modelCards.value.forEach(card => {
    card.status = 'pending'
    card.output = ''
    card.anomalies = []
    card.latencyMs = 0
  })

  try {
    const payload = {
      models: modelCards.value.map(card => ({
        name: card.config.model,
        type: card.config.type,
        url: card.config.url,
        api_key: card.config.api_key,
        model: card.config.model,
        temperature: card.config.temperature,
        max_tokens: card.config.max_tokens
      })),
      prompt: testPrompt.value,
      test_case_id: selectedTestCase.value || ''
    }

    const token = localStorage.getItem('token')
    const response = await fetch('/api/compare/run', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify(payload)
    })

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const dataStr = line.slice(6)
        try {
          const data = JSON.parse(dataStr)
          handleStreamEvent(data)
        } catch (e) {
          // 忽略解析错误
        }
      }
    }
  } catch (e) {
    ElMessage.error(`对比测试失败: ${e.message}`)
  } finally {
    isRunning.value = false
  }
}

function handleStreamEvent(data) {
  const card = modelCards.value.find(c => c.config.model === data.model)
  if (!card) return

  switch (data.type) {
    case 'start':
      card.status = 'running'
      card.output = ''
      break
    case 'chunk':
      card.status = 'running'
      card.output += data.text
      break
    case 'complete':
      card.status = 'completed'
      card.latencyMs = data.latency_ms
      card.anomalies = data.anomalies || []
      break
    case 'error':
      card.status = 'error'
      card.output = data.error || '未知错误'
      break
    case 'test_case':
      if (data.test_case) {
        currentTestCase.value = data.test_case
      }
      break
    case 'summary':
      // 汇总完成
      break
  }
}
</script>

<style scoped>
.model-compare {
  padding: 0;
}

.input-card {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.input-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.input-row {
  display: flex;
  gap: 12px;
}

.prompt-input {
  flex: 2;
}

.test-case-select {
  flex: 1;
}

.test-case-select .el-select {
  width: 100%;
}

.case-desc {
  float: right;
  color: #8492a6;
  font-size: 12px;
}

.action-row {
  display: flex;
  gap: 10px;
}

.cards-row {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  padding-bottom: 10px;
}

.model-card {
  flex: 0 0 380px;
  min-width: 320px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  height: 500px;
  transition: all 0.3s ease;
}

.model-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.card-running {
  border-color: #409eff;
  box-shadow: 0 0 8px rgba(64, 158, 255, 0.2);
}

.card-error {
  border-color: #f56c6c;
}

.card-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid #ebeef5;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.model-name {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.test-title-bar {
  padding: 4px 14px;
  background: #fdf6ec;
}

.output-area {
  flex: 1;
  overflow-y: auto;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.status-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #909399;
  font-size: 14px;
}

.status-placeholder.running {
  color: #409eff;
  gap: 8px;
}

.output-text {
  color: #303133;
}

.anomaly-section {
  padding: 6px 14px;
  border-top: 1px solid #ebeef5;
  max-height: 80px;
  overflow-y: auto;
}

.anomaly-item {
  font-size: 12px;
  padding: 2px 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.anomaly-error {
  color: #f56c6c;
}

.anomaly-warning {
  color: #e6a23c;
}

.anomaly-info {
  color: #909399;
}

.metrics-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-top: 1px solid #ebeef5;
  font-size: 12px;
  color: #606266;
}

.metric strong {
  color: #303133;
}
</style>
