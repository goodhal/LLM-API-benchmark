<template>
  <el-container class="layout-container">
    <el-aside width="220px">
      <div class="logo">
        <img src="@/views/logo.png" alt="Logo" class="logo-img">
        <div class="logo-text">
          <h3>模型质量测试平台V1.0</h3>
        </div>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        background-color="#ffffff"
        text-color="#606266"
        active-text-color="#409EFF"
        border="false"
      >
        <el-menu-item index="/">
          <span>首页</span>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <span>任务管理</span>
        </el-menu-item>
        <el-sub-menu index="test-report">
          <template #title>
            <span>测试报告</span>
          </template>
          <el-menu-item index="/perf-results">压力测试</el-menu-item>
          <el-menu-item index="/quality-results">质量测试</el-menu-item>
          <el-menu-item index="/availability-monitor">可用性监控</el-menu-item>
        </el-sub-menu>
        <el-menu-item index="/model-compare">
          <span>模型对比</span>
        </el-menu-item>
        <el-menu-item index="/system-monitor">
          <span>系统监控</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header>
        <div class="header-left">
        </div>
        <div class="header-right">
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <span>{{ username }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { authAPI } from '@/utils/api'
import {
  TrendCharts, Document, List
} from '@element-plus/icons-vue'


const router = useRouter()
const route = useRoute()
const username = ref(localStorage.getItem('username') || 'huangxuan')
const searchText = ref('')

const activeMenu = computed(() => {
  const path = route.path
  if (path === '/tasks') return 'api-test'
  if (path === '/perf-results') return 'perf-test'
  return path
})

const pageTitle = computed(() => {
  const titles = {
    '/': '首页',
    '/tasks': '任务管理',
    '/perf-results': '场景管理',
    '/quality-results': '测试报告'
  }
  return titles[route.path] || '模型质量测试平台'
})

const toggleMenu = () => {
}

const handleCommand = async (command) => {
  if (command === 'logout') {
    try {
      await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      })

      await authAPI.logout()
      localStorage.removeItem('token')
      ElMessage.success('已退出登录')
      router.push('/login')
    } catch (error) {
      if (error !== 'cancel') {
        console.error('Logout failed:', error)
      }
    }
  }
}
</script>

<style scoped>
.layout-container {
  min-height: 100vh;
}

.el-aside {
  background-color: #ffffff;
  color: #606266;
  border-right: 1px solid #e4e7ed;
}

.logo {
  height: 140px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 10px 5px;
  border-bottom: 1px solid #e4e7ed;
}

.logo-img {
  width: 144px;
  height: 72px;
  border-radius: 8px;
  margin-bottom: 8px;
  object-fit: contain;
}

.logo-text {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.logo-text h3 {
  color: #303133;
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.el-menu {
  border-right: none;
}

.el-menu-item,
.el-sub-menu__title {
  height: 44px;
  line-height: 44px;
}

.el-menu-item.is-active {
  background-color: #ecf5ff !important;
  color: #409EFF;
}

.el-sub-menu .el-menu-item {
  padding-left: 52px !important;
}

.el-header {
  background-color: #ffffff;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 20px;
}

.header-left {
  display: flex;
  align-items: center;
}

.menu-toggle {
  font-size: 20px;
  margin-right: 16px;
  cursor: pointer;
  color: #606266;
}

.search-input {
  width: 300px;
}

.header-right {
  display: flex;
  align-items: center;
}

.header-btn {
  margin-right: 12px;
  font-size: 18px;
  color: #606266;
}

.user-info {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 8px 12px;
  border-radius: 20px;
  background-color: #ecf5ff;
  color: #409EFF;
}

.user-icon {
  margin-right: 8px;
  font-size: 20px;
}

.el-main {
  background-color: #f5f7fa;
  padding: 20px;
}
</style>