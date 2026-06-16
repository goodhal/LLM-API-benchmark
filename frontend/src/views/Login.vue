<template>
  <div class="login-container">
    <el-card class="login-card">
      <template #header>
        <div class="logo-container">
          <img src="@/views/logo.png" alt="Logo" class="logo">
        </div>
        <h2>模型质量测试平台V1.5</h2>
      </template>
      
      <el-form :model="loginForm" :rules="rules" ref="loginFormRef">
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="用户名"
            prefix-icon="User"
            size="large"
          />
        </el-form-item>
        
        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            prefix-icon="Lock"
            size="large"
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        
        <el-form-item>
          <el-button
            type="primary"
            size="large"
            style="width: 100%"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { authAPI } from '@/utils/api'

const router = useRouter()
const loginFormRef = ref(null)
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: ''
})

const rules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ]
}

const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  await loginFormRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        const res = await authAPI.login(loginForm)
        localStorage.setItem('token', res.user?.id ? `session-${res.user.id}` : 'logged-in')
        localStorage.setItem('username', loginForm.username)
        ElMessage.success('登录成功')
        router.push('/')
      } catch (error) {
        console.error('Login failed:', error)
      } finally {
        loading.value = false
      }
    }
  })
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #e8eef5 0%, #c5d0e6 100%);
}

.login-card {
  width: 450px;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
  padding: 30px;
}

.logo-container {
  text-align: center;
  margin-bottom: 15px;
}

.logo {
  width: 280px;
  height: 120px;
  object-fit: contain;
}

.login-card h2 {
  text-align: center;
  color: #000000;
  margin: 0 0 25px 0;
  font-size: 24px;
  font-weight: bold;
}

.el-form-item {
  margin-bottom: 20px;
}

.el-input__wrapper {
  border-radius: 12px;
}

.el-button--primary {
  border-radius: 12px;
  height: 48px;
  font-size: 16px;
  font-weight: bold;
}
</style>