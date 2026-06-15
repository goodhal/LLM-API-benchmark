<template>
  <div class="tasks">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>任务管理</span>
          <el-button type="primary" @click="showCreateDialog">
            <el-icon><Plus /></el-icon>
            新建任务
          </el-button>
        </div>
      </template>
      
      <el-table :data="tasks" style="width: 100%">
        <el-table-column prop="name" label="任务名称" min-width="200" />
        
        <el-table-column prop="task_type" label="任务类型" min-width="120">
          <template #default="{ row }">
            <el-tag :type="getTaskTypeColor(row.task_type)">
              {{ getTaskTypeLabel(row.task_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="model" label="模型名称" min-width="150">
          <template #default="{ row }">
            {{ getModelName(row) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="schedule_type" label="调度类型" min-width="120">
          <template #default="{ row }">
            {{ getScheduleLabel(row.schedule_type) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="is_enabled" label="状态" min-width="100">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_enabled"
              @change="handleEnableChange(row)"
            />
          </template>
        </el-table-column>
        
        <el-table-column prop="status" label="执行状态" min-width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="last_run_time" label="最后执行" min-width="160">
          <template #default="{ row }">
            {{ row.last_run_time ? formatDate(row.last_run_time) : '-' }}
          </template>
        </el-table-column>
        
        <el-table-column prop="next_run_time" label="下次执行" min-width="160">
          <template #default="{ row }">
            {{ row.next_run_time ? formatDate(row.next_run_time) : '-' }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" min-width="320">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              @click="handleRun(row)"
              :disabled="row.status === 'running'"
            >
              执行
            </el-button>
            <el-button
              size="small"
              type="warning"
              @click="handleStop(row)"
              :disabled="row.status !== 'running'"
            >
              停止
            </el-button>
            <el-button
              size="small"
              type="info"
              @click="viewLiveLog(row)"
              :disabled="row.status !== 'running'"
            >
              查看日志
            </el-button>
            <el-button size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    
    <!-- 创建/编辑任务对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑任务' : '新建任务'"
      width="600px"
    >
      <el-form :model="taskForm" :rules="rules" ref="taskFormRef" label-width="120px">
        <el-form-item label="任务名称" prop="name">
          <el-input v-model="taskForm.name" placeholder="请输入任务名称" />
        </el-form-item>
        
        <el-form-item label="任务类型" prop="task_type">
          <el-radio-group v-model="taskForm.task_type" :disabled="isEdit">
            <el-radio label="perf_test">服务压力测试</el-radio>
            <el-radio label="safety_audit">安全审计</el-radio>
            <el-radio label="quality_eval">模型质量评测</el-radio>
            <el-radio label="availability_test">服务可用性测试</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <!-- 压力测试配置 -->
        <template v-if="taskForm.task_type === 'perf_test'">
          <el-form-item label="API URL" prop="config.url">
            <el-input v-model="taskForm.config.url" placeholder="https://api.example.com" />
          </el-form-item>
          
          <el-form-item label="API Key" prop="config.api_key">
            <el-input v-model="taskForm.config.api_key" type="password" placeholder="sk-xxxx" />
          </el-form-item>
          
          <el-form-item label="模型名称" prop="config.model">
            <el-input v-model="taskForm.config.model" placeholder="gpt-3.5-turbo" />
          </el-form-item>
          
          <el-form-item label="并发数">
            <el-input-number v-model="taskForm.config.parallel" :min="1" :max="1000" />
          </el-form-item>
          
          <el-form-item label="请求数">
            <el-input-number v-model="taskForm.config.number" :min="1" :max="100000" />
          </el-form-item>
          
          <el-divider>高级配置</el-divider>
          
          <el-form-item label="测试引擎">
            <el-radio-group v-model="taskForm.config.engine">
              <el-radio label="evalscope">EvalScope (CLI)</el-radio>
              <el-radio label="native">Native (内置)</el-radio>
            </el-radio-group>
            <div class="form-tip">Native 引擎支持实时指标和精确 TTFT/TPOT 测量</div>
          </el-form-item>

          <el-form-item label="调度模式">
            <el-select v-model="taskForm.config.schedule_mode" style="width: 100%">
              <el-option label="固定并发 (concurrent)" value="concurrent" />
              <el-option label="固定速率 (constant_rate)" value="constant_rate" />
              <el-option label="泊松分布 (poisson)" value="poisson" />
              <el-option label="最大吞吐 (throughput)" value="throughput" />
              <el-option label="自适应扫描 (sweep)" value="sweep" />
              <el-option label="追踪回放 (replay)" value="replay" />
            </el-select>
            <div class="form-tip">concurrent: 固定并发；constant_rate: 恒定QPS；poisson: 泊松分布；throughput: 最大吞吐量；sweep: 自动扫描最优区间；replay: 按trace回放</div>
          </el-form-item>

          <el-form-item v-if="taskForm.config.schedule_mode === 'constant_rate' || taskForm.config.schedule_mode === 'poisson'" label="请求速率(QPS)">
            <el-input-number v-model="taskForm.config.rate" :min="0.1" :max="10000" :step="1" :precision="1" />
          </el-form-item>

          <el-divider>数据源配置</el-divider>

          <el-form-item label="数据源">
            <el-select v-model="taskForm.config.data_source" style="width: 100%">
              <el-option label="默认 Prompt 列表" value="default" />
              <el-option label="合成数据生成" value="synthetic" />
            </el-select>
            <div class="form-tip">合成数据支持配置 prompt/output 长度分布，模拟真实场景</div>
          </el-form-item>

          <template v-if="taskForm.config.data_source === 'synthetic'">
            <el-form-item label="平均提示Token数">
              <el-input-number v-model="taskForm.config.prompt_tokens" :min="1" :max="100000" />
            </el-form-item>

            <el-form-item label="提示Token标准差">
              <el-input-number v-model="taskForm.config.prompt_tokens_stdev" :min="0" :max="10000" />
              <div class="form-tip">0 表示固定长度，越大表示长度波动越大</div>
            </el-form-item>

            <el-form-item label="平均生成Token数">
              <el-input-number v-model="taskForm.config.output_tokens" :min="1" :max="100000" />
            </el-form-item>
          </template>

          <template v-if="taskForm.config.data_source === 'default'">
            <el-form-item label="最小提示长度">
              <el-input-number v-model="taskForm.config.min_prompt_length" :min="1" :max="1000000" />
            </el-form-item>

            <el-form-item label="最大提示长度">
              <el-input-number v-model="taskForm.config.max_prompt_length" :min="1" :max="1000000" />
            </el-form-item>
          </template>

          <el-form-item label="最小生成Token数">
            <el-input-number v-model="taskForm.config.min_tokens" :min="1" :max="1000000" />
          </el-form-item>

          <el-form-item label="最大生成Token数">
            <el-input-number v-model="taskForm.config.max_tokens" :min="1" :max="1000000" />
          </el-form-item>

          <el-divider>约束条件</el-divider>

          <el-form-item label="最大时长(秒)">
            <el-input-number v-model="taskForm.config.max_duration" :min="0" :max="86400" />
            <div class="form-tip">0 表示不限制，超过时长自动停止测试</div>
          </el-form-item>

          <el-form-item label="最大错误率(%)">
            <el-input-number v-model="taskForm.config.max_error_rate" :min="0" :max="100" />
            <div class="form-tip">0 表示不限制，错误率超过阈值自动停止测试</div>
          </el-form-item>

          <el-form-item label="过饱和检测">
            <el-switch v-model="taskForm.config.over_saturation" />
            <div class="form-tip">启用后，当 TTFT 持续恶化时自动停止测试（参考 GuideLLM OSD 算法）</div>
          </el-form-item>

          <el-divider>超时配置</el-divider>
          
          <el-form-item label="连接超时(秒)">
            <el-input-number v-model="taskForm.config.connect_timeout" :min="1" :max="600" />
          </el-form-item>
          
          <el-form-item label="读取超时(秒)">
            <el-input-number v-model="taskForm.config.read_timeout" :min="1" :max="600" />
          </el-form-item>
        </template>
        
        <!-- 安全审计配置 -->
        <template v-if="taskForm.task_type === 'safety_audit'">
          <el-form-item label="API URL" prop="config.url">
            <el-input v-model="taskForm.config.url" placeholder="https://relay.example.com/v1" />
          </el-form-item>
          
          <el-form-item label="API Key" prop="config.api_key">
            <el-input v-model="taskForm.config.api_key" type="password" placeholder="sk-xxxx" />
          </el-form-item>
          
          <el-form-item label="模型名称" prop="config.model">
            <el-input v-model="taskForm.config.model" placeholder="claude-opus-4-6" />
          </el-form-item>
        </template>

        <!-- 模型质量评测配置 -->
        <template v-if="taskForm.task_type === 'quality_eval'">
          <el-form-item label="API URL" prop="config.url">
            <el-input v-model="taskForm.config.url" placeholder="https://api.example.com/v1/chat/completions" />
          </el-form-item>

          <el-form-item label="API Key" prop="config.api_key">
            <el-input v-model="taskForm.config.api_key" type="password" placeholder="sk-xxxx" />
          </el-form-item>

          <el-form-item label="模型名称" prop="config.model">
            <el-input v-model="taskForm.config.model" placeholder="gpt-3.5-turbo" />
          </el-form-item>

          <el-divider>数据集配置</el-divider>

          <el-form-item label="数据集" prop="config.dataset_path">
            <el-select v-model="taskForm.config.dataset_path" placeholder="选择数据集" allow-create filterable>
              <el-option
                v-for="ds in datasetList"
                :key="ds.path"
                :label="`${ds.name} (${ds.format})`"
                :value="ds.path"
              />
            </el-select>
            <div class="form-tip">可选择已有数据集，或输入服务器上的 JSONL/CSV 文件路径</div>
          </el-form-item>

          <el-form-item label="输入列名">
            <el-input v-model="taskForm.config.input_column" placeholder="prompt" />
          </el-form-item>

          <el-form-item label="答案列名">
            <el-input v-model="taskForm.config.answer_column" placeholder="answer" />
          </el-form-item>

          <el-form-item label="样本数量限制">
            <el-input-number v-model="taskForm.config.limit" :min="1" :max="100000" />
            <div class="form-tip">留空则使用全部样本</div>
          </el-form-item>

          <el-divider>评测配置</el-divider>

          <el-form-item label="评测指标">
            <el-checkbox-group v-model="taskForm.config.metrics">
              <el-checkbox label="exact_match">Exact Match</el-checkbox>
              <el-checkbox label="contains_match">Contains Match</el-checkbox>
              <el-checkbox label="token_f1">Token F1</el-checkbox>
              <el-checkbox label="rouge_l">Rouge-L</el-checkbox>
              <el-checkbox label="llm_judge" :disabled="!taskForm.config.judge_model_ids || taskForm.config.judge_model_ids.length === 0">LLM Judge</el-checkbox>
            </el-checkbox-group>
            <div class="form-tip">Contains Match 适用于短答案QA/数学数据集；LLM Judge 需配置评价模型后自动启用</div>
          </el-form-item>

          <el-divider>评价模型</el-divider>

          <el-form-item label="评价模型">
            <div style="display: flex; gap: 8px; width: 100%;">
              <el-select
                v-model="taskForm.config.judge_model_ids"
                multiple
                placeholder="选择评价模型（可选）"
                style="flex: 1"
              >
                <el-option
                  v-for="jm in judgeModelList"
                  :key="jm.id"
                  :label="`${jm.name} (${jm.model})`"
                  :value="jm.id"
                />
              </el-select>
              <el-button @click="showJudgeModelDialog" type="primary" plain>管理</el-button>
            </div>
            <div class="form-tip">不配置评价模型则仅使用文本匹配指标；配置后自动启用 LLM Judge 指标，多个评价模型评分取平均值</div>
          </el-form-item>

          <el-form-item label="最大生成Token数">
            <el-input-number v-model="taskForm.config.max_tokens" :min="1" :max="32000" />
          </el-form-item>

          <el-form-item label="简洁回答">
            <el-switch v-model="taskForm.config.concise_mode" />
            <div class="form-tip">开启后会提示被测模型尽量简短回答，提高文本匹配指标的准确性</div>
          </el-form-item>
        </template>

        <!-- 可用性测试配置 -->
        <template v-if="taskForm.task_type === 'availability_test'">
          <el-form-item label="模型名称" prop="config.model">
            <el-select v-model="taskForm.config.model" placeholder="选择或输入模型名称" allow-create filterable>
              <el-option label="gpt-3.5-turbo" value="gpt-3.5-turbo" />
              <el-option label="gpt-4" value="gpt-4" />
              <el-option label="gpt-4o" value="gpt-4o" />
              <el-option label="claude-3-opus" value="claude-3-opus" />
              <el-option label="claude-3-sonnet" value="claude-3-sonnet" />
              <el-option label="claude-3-haiku" value="claude-3-haiku" />
            </el-select>
          </el-form-item>

          <el-divider>渠道配置</el-divider>

          <div v-for="(channel, index) in taskForm.config.channels" :key="index" class="channel-item">
            <el-card shadow="hover">
              <el-form-item :label="`渠道${index + 1}名称`">
                <el-input v-model="channel.name" placeholder="渠道名称" />
              </el-form-item>

              <el-form-item :label="`渠道${index + 1} API URL`">
                <el-input v-model="channel.url" placeholder="API URL (如: https://api.openai.com/v1/chat/completions)" />
              </el-form-item>

              <el-form-item :label="`渠道${index + 1} API Key`">
                <el-input v-model="channel.api_key" placeholder="API Key" :type="channel.showPassword ? 'text' : 'password'">
                  <template #suffix>
                    <el-icon
                      class="toggle-password"
                      @click="channel.showPassword = !channel.showPassword"
                    >
                      <View v-if="!channel.showPassword" />
                      <Hide v-else />
                    </el-icon>
                  </template>
                </el-input>
              </el-form-item>

              <el-button
                v-if="taskForm.config.channels.length > 1"
                type="danger"
                size="small"
                @click="removeChannel(index)"
                style="margin-left: 10px"
              >
                删除渠道
              </el-button>
            </el-card>
          </div>

          <el-button type="primary" size="small" @click="addChannel" style="margin-top: 10px">
            添加渠道
          </el-button>

          <el-divider>测试参数</el-divider>

          <el-form-item label="并发数">
            <el-input-number v-model="taskForm.config.parallel" :min="1" :max="100" />
          </el-form-item>

          <el-form-item label="请求数">
            <el-input-number v-model="taskForm.config.number" :min="1" :max="1000" />
          </el-form-item>

          <el-form-item label="连接超时(秒)">
            <el-input-number v-model="taskForm.config.connect_timeout" :min="1" :max="120" />
          </el-form-item>

          <el-form-item label="读取超时(秒)">
            <el-input-number v-model="taskForm.config.read_timeout" :min="1" :max="1200" />
          </el-form-item>
        </template>
        
        <el-divider>调度设置</el-divider>
        
        <el-form-item label="调度类型">
          <el-radio-group v-model="taskForm.schedule_type">
            <el-radio label="manual">手动执行</el-radio>
            <el-radio label="cron">Cron 表达式</el-radio>
            <el-radio label="interval">固定间隔</el-radio>
          </el-radio-group>
        </el-form-item>
        
        <el-form-item v-if="taskForm.schedule_type === 'cron'" label="Cron 表达式">
          <el-input v-model="taskForm.cron_expression" placeholder="0 */30 * * * *" />
          <div class="form-tip">格式：秒 分 时 日 月 周</div>
        </el-form-item>
        
        <el-form-item v-if="taskForm.schedule_type === 'interval'" label="间隔时间">
          <el-input-number v-model="taskForm.interval_seconds" :min="60" :step="60" />
          <span style="margin-left: 10px">秒</span>
        </el-form-item>
        
        <el-form-item label="开始时间">
          <el-date-picker
            v-model="taskForm.start_time"
            type="datetime"
            placeholder="选择开始时间"
          />
        </el-form-item>
        
        <el-form-item label="结束时间">
          <el-date-picker
            v-model="taskForm.end_time"
            type="datetime"
            placeholder="选择结束时间"
          />
        </el-form-item>
        
        <el-form-item label="立即启用">
          <el-switch v-model="taskForm.is_enabled" />
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">
          {{ isEdit ? '保存' : '创建' }}
        </el-button>
      </template>
    </el-dialog>
    
    <!-- 实时日志查看对话框 -->
    <el-dialog
      v-model="logDialogVisible"
      title="实时执行日志"
      width="80%"
      :close-on-click-modal="false"
      @close="closeLogDialog"
    >
      <!-- 实时指标面板（Native 引擎） -->
      <div v-if="liveMetrics" class="live-metrics-panel">
        <el-row :gutter="16">
          <el-col :span="4">
            <div class="metric-card">
              <div class="metric-value">{{ liveMetrics.rps }}</div>
              <div class="metric-label">RPS</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-card">
              <div class="metric-value">{{ liveMetrics.avg_latency?.toFixed(2) }}s</div>
              <div class="metric-label">平均延迟</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-card">
              <div class="metric-value">{{ liveMetrics.avg_ttft?.toFixed(0) }}ms</div>
              <div class="metric-label">平均TTFT</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-card">
              <div class="metric-value">{{ liveMetrics.success_rate?.toFixed(1) }}%</div>
              <div class="metric-label">成功率</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-card">
              <div class="metric-value">{{ liveMetrics.request_count }}</div>
              <div class="metric-label">请求数</div>
            </div>
          </el-col>
          <el-col :span="4">
            <div class="metric-card">
              <div class="metric-value">{{ liveMetrics.gen_toks?.toFixed(1) }}</div>
              <div class="metric-label">tok/s</div>
            </div>
          </el-col>
        </el-row>
      </div>
      <div class="log-header">
        <span>任务: {{ currentLogTask?.name }}</span>
        <el-switch v-model="autoScroll" active-text="自动滚动" />
      </div>
      <pre ref="logContentRef" class="log-content">{{ logContent }}</pre>
      <template #footer>
        <el-button @click="refreshLog">手动刷新</el-button>
        <el-button type="primary" @click="logDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 评价模型管理弹窗 -->
    <el-dialog v-model="judgeModelDialogVisible" title="评价模型管理" width="700px">
      <div style="margin-bottom: 16px;">
        <el-button type="primary" @click="addJudgeModel">添加评价模型</el-button>
      </div>
      <el-table :data="judgeModelList" border style="width: 100%">
        <el-table-column prop="name" label="名称" width="140" />
        <el-table-column prop="model" label="模型" width="160" />
        <el-table-column prop="url" label="API URL" show-overflow-tooltip />
        <el-table-column label="操作" width="140">
          <template #default="{ row }">
            <el-button link type="primary" @click="editJudgeModel(row)">编辑</el-button>
            <el-button link type="danger" @click="deleteJudgeModel(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- 评价模型编辑弹窗 -->
    <el-dialog v-model="judgeModelEditVisible" :title="judgeModelEditId ? '编辑评价模型' : '添加评价模型'" width="500px">
      <el-form :model="judgeModelForm" label-width="100px">
        <el-form-item label="名称">
          <el-input v-model="judgeModelForm.name" placeholder="如：GPT-4 Judge" />
        </el-form-item>
        <el-form-item label="API URL">
          <el-input v-model="judgeModelForm.url" placeholder="https://api.example.com/v1/chat/completions" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="judgeModelForm.api_key" type="password" placeholder="sk-xxxx" />
        </el-form-item>
        <el-form-item label="模型名称">
          <el-input v-model="judgeModelForm.model" placeholder="gpt-4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="judgeModelEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveJudgeModel" :loading="judgeModelSaving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { taskAPI, judgeAPI } from '@/utils/api'
import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
import { View, Hide } from '@element-plus/icons-vue'

dayjs.extend(utc)
dayjs.extend(timezone)

const tasks = ref([])
const datasetList = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)
const taskFormRef = ref(null)
const editingTaskId = ref(null)

// 实时日志相关
const logDialogVisible = ref(false)
const logContent = ref('')
const liveMetrics = ref(null)
const logContentRef = ref(null)
const currentLogTask = ref(null)
const autoScroll = ref(true)
let logRefreshTimer = null
const isEditing = ref(false)

const taskForm = reactive({
  name: '',
  task_type: 'perf_test',
  config: {
    url: '',
    api_key: '',
    model: '',
    parallel: 8,
    number: 50,
    min_prompt_length: 10,
    max_prompt_length: 20,
    min_tokens: 128,
    max_tokens: 128,
    connect_timeout: 60,
    read_timeout: 120,
    engine: 'evalscope',
    // 调度策略（参考 GuideLLM）
    schedule_mode: 'concurrent',
    rate: 10,
    // 数据源配置
    data_source: 'default',
    prompt_tokens: 256,
    prompt_tokens_stdev: 0,
    output_tokens: 128,
    // 约束条件
    max_duration: 0,
    max_error_rate: 0,
    over_saturation: false,
    channels: [
      { name: '渠道1', url: '', api_key: '', showPassword: false }
    ],
    dataset_path: '',
    input_column: 'prompt',
    answer_column: 'answer',
    limit: null
  },
  schedule_type: 'manual',
  cron_expression: '',
  interval_seconds: 1800,
  start_time: null,
  end_time: null,
  is_enabled: false
})

// 切换任务类型时重置 config，避免残留旧字段（编辑时跳过）
watch(() => taskForm.task_type, (newType) => {
  if (isEditing.value) return
  const commonConfig = {
    url: taskForm.config.url,
    api_key: taskForm.config.api_key,
    model: taskForm.config.model,
  }
  const typeSpecific = {
    perf_test: {
      ...commonConfig,
      parallel: 8, number: 50, min_prompt_length: 10, max_prompt_length: 20,
      min_tokens: 128, max_tokens: 128, connect_timeout: 60, read_timeout: 120,
      engine: 'evalscope',
      channels: [{ name: '渠道1', url: '', api_key: '', showPassword: false }]
    },
    safety_audit: { ...commonConfig, test_cases: [] },
    quality_eval: {
      ...commonConfig,
      dataset_path: '', input_column: 'prompt', answer_column: 'answer',
      metrics: ['exact_match', 'contains_match', 'token_f1', 'rouge_l'],
      max_tokens: 1024, limit: null, judge_model_ids: [], concise_mode: true
    },
    availability_test: { ...commonConfig, check_interval: 60, timeout: 30 }
  }
  Object.assign(taskForm.config, typeSpecific[newType] || commonConfig)
})

const rules = {
  name: [{ required: true, message: '请输入任务名称', trigger: 'blur' }],
  task_type: [{ required: true, message: '请选择任务类型', trigger: 'change' }],
  'config.url': [{ required: true, message: '请输入 API URL', trigger: 'blur' }],
  'config.api_key': [{ required: true, message: '请输入 API Key', trigger: 'blur' }],
  'config.dataset_path': [{ required: true, message: '请选择数据集', trigger: 'change' }]
}

const loadTasks = async () => {
  try {
    const res = await taskAPI.getTasks()
    tasks.value = res.tasks
  } catch (error) {
    console.error('Failed to load tasks:', error)
  }
}

// 评价模型相关
const judgeModelList = ref([])
const judgeModelDialogVisible = ref(false)
const judgeModelEditVisible = ref(false)
const judgeModelEditId = ref(null)
const judgeModelSaving = ref(false)
const judgeModelForm = reactive({
  name: '',
  url: '',
  api_key: '',
  model: ''
})

const loadJudgeModels = async () => {
  try {
    const res = await judgeAPI.getJudgeModels()
    judgeModelList.value = res.judge_models || []
  } catch (error) {
    console.error('Failed to load judge models:', error)
  }
}

const showJudgeModelDialog = () => {
  judgeModelDialogVisible.value = true
}

const addJudgeModel = () => {
  judgeModelEditId.value = null
  Object.assign(judgeModelForm, { name: '', url: '', api_key: '', model: '' })
  judgeModelEditVisible.value = true
}

const editJudgeModel = (row) => {
  judgeModelEditId.value = row.id
  Object.assign(judgeModelForm, { name: row.name, url: row.url, api_key: '******', model: row.model })
  judgeModelEditVisible.value = true
}

const saveJudgeModel = async () => {
  if (!judgeModelForm.name || !judgeModelForm.url || !judgeModelForm.model) {
    ElMessage.warning('请填写名称、API URL 和模型名称')
    return
  }
  judgeModelSaving.value = true
  try {
    const data = { ...judgeModelForm }
    if (judgeModelEditId.value) {
      await judgeAPI.updateJudgeModel(judgeModelEditId.value, data)
      ElMessage.success('更新成功')
    } else {
      if (!data.api_key) {
        ElMessage.warning('请填写 API Key')
        judgeModelSaving.value = false
        return
      }
      await judgeAPI.createJudgeModel(data)
      ElMessage.success('添加成功')
    }
    judgeModelEditVisible.value = false
    await loadJudgeModels()
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    judgeModelSaving.value = false
  }
}

const deleteJudgeModel = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除评价模型 "${row.name}"？`, '提示', { type: 'warning' })
    await judgeAPI.deleteJudgeModel(row.id)
    ElMessage.success('删除成功')
    await loadJudgeModels()
    // 从已选列表中移除
    if (taskForm.config.judge_model_ids) {
      taskForm.config.judge_model_ids = taskForm.config.judge_model_ids.filter(id => id !== row.id)
    }
  } catch (error) {
    if (error !== 'cancel') ElMessage.error('删除失败')
  }
}

const showCreateDialog = () => {
  isEdit.value = false
  resetForm()
  dialogVisible.value = true
}

const handleEdit = (row) => {
  isEdit.value = true
  editingTaskId.value = row.id
  isEditing.value = true
  
  const parsedConfig = JSON.parse(row.config)
  
  Object.assign(taskForm, {
    name: row.name,
    task_type: row.task_type,
    config: {
      // 默认值
      url: '',
      api_key: '',
      model: '',
      parallel: 8,
      number: 50,
      min_prompt_length: 10,
      max_prompt_length: 20,
      min_tokens: 128,
      max_tokens: 128,
      connect_timeout: 60,
      read_timeout: 120,
      engine: 'evalscope',
      // 覆盖为实际值
      ...parsedConfig
    },
    schedule_type: row.schedule_type,
    cron_expression: row.cron_expression || '',
    interval_seconds: row.interval_seconds || 1800,
    start_time: row.start_time ? new Date(row.start_time) : null,
    end_time: row.end_time ? new Date(row.end_time) : null,
    is_enabled: row.is_enabled
  })

  // 在下一个 tick 解除编辑标志，让 watch 恢复正常
  nextTick(() => { isEditing.value = false })
  
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!taskFormRef.value) return
  
  await taskFormRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true
      try {
        const data = {
          name: taskForm.name,
          task_type: taskForm.task_type,
          config: JSON.stringify(taskForm.config),
          schedule_type: taskForm.schedule_type,
          cron_expression: taskForm.cron_expression,
          interval_seconds: taskForm.interval_seconds,
          start_time: taskForm.start_time ? dayjs(taskForm.start_time).toISOString() : null,
          end_time: taskForm.end_time ? dayjs(taskForm.end_time).toISOString() : null,
          is_enabled: taskForm.is_enabled
        }
        
        if (isEdit.value) {
          await taskAPI.updateTask(editingTaskId.value, data)
          ElMessage.success('任务更新成功')
        } else {
          await taskAPI.createTask(data)
          ElMessage.success('任务创建成功')
        }
        
        dialogVisible.value = false
        loadTasks()
      } catch (error) {
        console.error('Failed to save task:', error)
      } finally {
        submitting.value = false
      }
    }
  })
}

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确定要删除该任务吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    await taskAPI.deleteTask(row.id)
    ElMessage.success('任务删除成功')
    loadTasks()
  } catch (error) {
    if (error !== 'cancel') {
      console.error('Failed to delete task:', error)
    }
  }
}

const handleRun = async (row) => {
  try {
    await taskAPI.runTask(row.id)
    ElMessage.success('任务已开始执行')
    loadTasks()
  } catch (error) {
    console.error('Failed to run task:', error)
  }
}

const handleStop = async (row) => {
  try {
    await taskAPI.stopTask(row.id)
    ElMessage.success('任务已停止')
    loadTasks()
  } catch (error) {
    console.error('Failed to stop task:', error)
  }
}

// 实时日志查看
const viewLiveLog = async (row) => {
  currentLogTask.value = row
  logContent.value = ''
  logDialogVisible.value = true
  
  // 立即加载一次
  await refreshLog()
  
  // 启动定时刷新（每 2 秒）
  logRefreshTimer = setInterval(async () => {
    await refreshLog()
  }, 2000)
}

const refreshLog = async () => {
  if (!currentLogTask.value) return
  
  try {
    // 并行获取日志内容和实时指标
    const [logResponse, metricsResponse] = await Promise.all([
      fetch(`/api/tasks/${currentLogTask.value.id}/output-content`, {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
      }).then(r => r.json()),
      taskAPI.getLiveMetrics(currentLogTask.value.id).catch(() => ({ metrics: null, running: false }))
    ])
    
    if (logResponse.exists) {
      logContent.value = logResponse.content
      
      // 自动滚动到底部
      if (autoScroll.value && logContentRef.value) {
        await nextTick()
        logContentRef.value.scrollTop = logContentRef.value.scrollHeight
      }
    }
    
    // 更新实时指标
    if (metricsResponse.running && metricsResponse.metrics) {
      liveMetrics.value = metricsResponse.metrics
    } else {
      liveMetrics.value = null
    }
    
    // 如果任务不再是 running 状态，停止刷新
    if (currentLogTask.value) {
      await loadTasks()
      const updatedTask = tasks.value.find(t => t.id === currentLogTask.value.id)
      if (updatedTask && updatedTask.status !== 'running') {
        closeLogDialog()
        ElMessage.info('任务执行完成')
      }
    }
  } catch (error) {
    console.error('Failed to refresh log:', error)
  }
}

const closeLogDialog = () => {
  if (logRefreshTimer) {
    clearInterval(logRefreshTimer)
    logRefreshTimer = null
  }
  logDialogVisible.value = false
  currentLogTask.value = null
  liveMetrics.value = null
}

const handleEnableChange = async (row) => {
  try {
    await taskAPI.updateTask(row.id, { is_enabled: row.is_enabled })
    ElMessage.success(row.is_enabled ? '任务已启用' : '任务已禁用')
  } catch (error) {
    row.is_enabled = !row.is_enabled
    console.error('Failed to update task:', error)
  }
}

const resetForm = () => {
  Object.assign(taskForm, {
    name: '',
    task_type: 'perf_test',
    config: {
      url: '',
      api_key: '',
      model: '',
      parallel: 8,
      number: 50,
      min_prompt_length: 10,
      max_prompt_length: 20,
      min_tokens: 128,
      max_tokens: 128,
      connect_timeout: 60,
      read_timeout: 120,
      engine: 'evalscope',
      channels: [
        { name: '渠道1', api_key: '', showPassword: false }
      ]
    },
    schedule_type: 'manual',
    cron_expression: '',
    interval_seconds: 1800,
    start_time: null,
    end_time: null,
    is_enabled: false
  })
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

const getScheduleLabel = (type) => {
  const labels = {
    manual: '手动执行',
    cron: 'Cron',
    interval: '固定间隔'
  }
  return labels[type] || type
}

const getStatusLabel = (status) => {
  const labels = {
    idle: '空闲',
    running: '运行中',
    success: '成功',
    failed: '失败'
  }
  return labels[status] || status
}

const getStatusType = (status) => {
  const types = {
    idle: 'info',
    running: 'warning',
    success: 'success',
    failed: 'danger'
  }
  return types[status] || 'info'
}

const getModelName = (row) => {
  try {
    const config = JSON.parse(row.config)
    return config.model || '-'
  } catch {
    return '-'
  }
}

const getTaskTypeLabel = (type) => {
  const labels = {
    perf_test: '压力测试',
    safety_audit: '安全审计',
    quality_eval: '质量评测',
    availability_test: '可用性测试'
  }
  return labels[type] || type
}

const getTaskTypeColor = (type) => {
  const colors = {
    perf_test: 'success',
    safety_audit: 'warning',
    quality_eval: 'danger',
    availability_test: 'primary'
  }
  return colors[type] || 'info'
}

const addChannel = () => {
  taskForm.config.channels.push({
    name: `渠道${taskForm.config.channels.length + 1}`,
    url: '',
    api_key: '',
    showPassword: false
  })
}

const removeChannel = (index) => {
  if (taskForm.config.channels.length > 1) {
    taskForm.config.channels.splice(index, 1)
  }
}

onMounted(() => {
  loadTasks()
  loadDatasets()
  loadJudgeModels()
})

async function loadDatasets() {
  try {
    const res = await taskAPI.getDatasets()
    datasetList.value = res.datasets || []
  } catch (e) {
    console.error('加载数据集列表失败:', e)
  }
}
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

.channel-item {
  margin-bottom: 15px;
}

.toggle-password {
  cursor: pointer;
}

.log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
  padding-bottom: 10px;
  border-bottom: 1px solid #ebeef5;
}

.log-content {
  background-color: #1e1e1e;
  color: #d4d4d4;
  padding: 15px;
  border-radius: 4px;
  overflow: auto;
  max-height: 500px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.live-metrics-panel {
  margin-bottom: 16px;
  padding: 12px;
  background: #f0f9eb;
  border-radius: 8px;
  border: 1px solid #e1f3d8;
}

.metric-card {
  text-align: center;
  padding: 8px 4px;
}

.metric-value {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
  line-height: 1.4;
}

.metric-label {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
</style>