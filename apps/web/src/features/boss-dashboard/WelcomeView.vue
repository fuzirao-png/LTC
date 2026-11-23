<script setup lang="ts">
import { computed, ref } from 'vue'

import { accountTypeLabel, regionLabel, salesTierLabel } from '../../shared/utils/labels'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const selectedNews = ref<string | null>(null)

const displayName = computed(() => {
  return auth.currentUser?.name || auth.currentUser?.username || '未登录'
})
const isSales = computed(() => auth.currentUser?.accountType === 'sales')
const profileItems = computed(() => {
  const user = auth.currentUser
  if (!user) return []
  const status = user.status === 'active' ? '在职' : user.status === 'disabled' ? '已停用' : user.status === 'departed' ? '已离职' : user.status
  if (!isSales.value) {
    return [
      { label: '账号状态', value: status, sub: user.username },
      { label: '账号角色', value: accountTypeLabel(user.accountType), sub: '经营视角' },
      { label: '权限数量', value: String(user.capabilities.length), sub: '当前已授权能力' },
    ]
  }
  return [
    { label: '账号状态', value: status, sub: user.username },
    { label: '销售层级', value: salesTierLabel(user.salesTier), sub: user.salesTier || '未分级' },
    { label: '负责区域', value: regionLabel(user.regionCode), sub: user.regionCode || '未分配' },
    { label: '客户容量', value: `${user.activeAssignmentCount}/${user.capacityLimit ?? '—'}`, sub: '当前有效分配 / 上限' },
  ]
})
const marketRegion = computed(() => regionLabel(auth.currentUser?.regionCode))
const news = [
  { tag: '平台连接', time: '09:20', title: '工业园区设备接入需求升温，边缘采集与统一管理成为升级重点', body: '制造、仓储与能源场景正在加快接入改造，企业更关注低成本部署、稳定联网和数据可视化能力。' },
  { tag: '智慧城市', time: '10:05', title: '城市感知项目从单点试验转向联动治理，视频与传感协同成为主流', body: '路侧设备、安防告警和环境监测的联动能力持续增强，平台侧更强调跨系统集成与实时响应。' },
  { tag: '车联网', time: '11:30', title: '车队运营正在加码终端在线率与远程诊断，运维数字化需求明显上升', body: '物流与出行企业开始更看重设备在线稳定性、位置精度和异常预警，以降低调度与维护成本。' },
]
const marketNews = [
  { tag: '市场动态', time: '09:30', title: '日本企业差旅市场Q2同比增长18%，差旅平台数字化转型加速', body: '受日元贬值影响，日本企业海外差旅需求持续增长，差旅平台服务商加速部署数字化管理工具以提升效率。' },
  { tag: '行业趋势', time: '10:15', title: 'eSIM企业渗透率在日本市场从12%提升至22%，成本优势明显', body: '日本企业对通讯成本控制需求强烈，eSIM方案平均可节省35%国际漫游费用，大型差旅平台客户采购意愿显著提升。' },
  { tag: '竞品情报', time: '11:00', title: '竞品SoftBank企业通讯方案降价15%，需关注价格战风险', body: 'SoftBank近期针对差旅平台客户推出优惠套餐，建议在方案中强化多国覆盖和合规性差异化优势。' },
]
</script>

<template>
  <div class="alex-workbench">
    <section class="alex-welcome">
      <div class="alex-eyebrow">途鸽科技工作台</div>
      <h1>{{ displayName }}，欢迎回来</h1>
      <p>下方展示基础环境信息，下方按行业为你整理今日值得关注的时讯。</p>

      <div class="alex-weather-grid">
        <article><span>当前天气</span><strong>晴朗 微风</strong></article>
        <article><span>空气湿度</span><strong>68%</strong></article>
        <article><span>体感温度</span><strong>27°C</strong></article>
        <article><span>更新时间</span><strong>6/9 18:14:56 更新</strong></article>
      </div>

      <div class="alex-profile-grid">
        <article v-for="item in profileItems" :key="item.label">
          <span>{{ item.label }}</span><strong>{{ item.value }}</strong><small>{{ item.sub }}</small>
        </article>
      </div>

      <div class="alex-news-grid">
        <section>
          <header><h2>物联网行业时讯</h2><span>连接、感知与行业落地</span></header>
          <button v-for="item in news" :key="item.title" class="alex-news-card" type="button" @click="selectedNews = item.title">
            <div><b>{{ item.tag }}</b><time>{{ item.time }}</time></div><strong>{{ item.title }}</strong><p>{{ item.body }}</p>
          </button>
        </section>
        <section>
          <header><h2>{{ marketRegion }}销售市场资讯</h2><span>差旅平台、商旅OTA与企业差旅</span></header>
          <button v-for="item in marketNews" :key="item.title" class="alex-news-card" type="button" @click="selectedNews = item.title">
            <div><b>{{ item.tag }}</b><time>{{ item.time }}</time></div><strong>{{ item.title }}</strong><p>{{ item.body }}</p>
          </button>
        </section>
      </div>
    </section>

    <div v-if="selectedNews" class="alex-news-modal" role="dialog" aria-modal="true" @click.self="selectedNews = null">
      <div class="alex-news-modal-card"><button type="button" @click="selectedNews = null">×</button><h2>{{ selectedNews }}</h2><p>已加入今日关注。你可以从左侧 Agent 菜单继续进入线索收集、线索分析或客户分配。</p></div>
    </div>
  </div>
</template>

<style scoped>
.alex-workbench {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 28px 24px 20px;
  max-width: 1200px;
  margin: 0 auto;
}
.alex-welcome {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.alex-eyebrow {
  font-size: 11px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1.5px;
}
.alex-welcome h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.alex-welcome p {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0;
}
.alex-weather-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.alex-weather-grid article {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
}
.alex-weather-grid article span {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.alex-weather-grid article strong {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.alex-profile-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.alex-profile-grid article {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
}
.alex-profile-grid article span {
  display: block;
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.alex-profile-grid article strong {
  display: block;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.alex-profile-grid article small {
  display: block;
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 2px;
}
.alex-news-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.alex-news-grid section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
}
.alex-news-grid section header {
  margin-bottom: 12px;
}
.alex-news-grid section header h2 {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}
.alex-news-grid section header span {
  font-size: 10px;
  color: var(--text-muted);
}
.alex-news-card {
  display: block;
  width: 100%;
  text-align: left;
  background: var(--bg-base);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}
.alex-news-card:hover {
  border-color: var(--blue);
  box-shadow: var(--shadow-sm);
  transform: translateX(2px);
}
.alex-news-card div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.alex-news-card div b {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--blue-light);
  color: var(--blue);
  font-weight: 600;
}
.alex-news-card div time {
  font-size: 10px;
  color: var(--text-muted);
}
.alex-news-card strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
  display: block;
}
.alex-news-card p {
  font-size: 11px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}
.alex-news-modal {
  position: fixed;
  inset: 0;
  background: rgba(15,23,42,0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}
.alex-news-modal-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 28px 32px;
  max-width: 480px;
  width: 90%;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}
.alex-news-modal-card button {
  float: right;
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
  color: var(--text-muted);
}
.alex-news-modal-card h2 {
  font-size: 16px;
  font-weight: 700;
  margin: 0 0 8px;
}
.alex-news-modal-card p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}
</style>
