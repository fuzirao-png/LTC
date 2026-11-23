import { createRouter, createWebHistory } from 'vue-router'
import RuntimeStatusView from '../../app/providers/RuntimeStatusView.vue'
import { loadCandidateLanding, loadSalesLanding } from '../../services/landingQueries'

// Lazy-load legacy views
const CustomerListPage = () => import('../../features/customer-analysis/CustomerListPage.vue')
const CustomerDetailPage = () => import('../../features/customer-analysis/CustomerDetailPage.vue')
const LoginView = () => import('../../features/auth/LoginView.vue')
const DashboardView = () => import('../../features/dashboards/DashboardView.vue')
const CustomerAllocation = () => import('../../features/customer-allocation/CustomerAllocation.vue')
const CustomerAnalysis = () => import('../../features/customer-analysis/CustomerAnalysis.vue')
const CustomerOperation = () => import('../../features/customer-operation/CustomerOperation.vue')
const Database = () => import('../../features/database/Database.vue')
const BossDashboard = () => import('../../features/boss-dashboard/BossDashboard.vue')
const WelcomeView = () => import('../../features/boss-dashboard/WelcomeView.vue')
const LeadCollection = () => import('../../features/lead-collection/LeadCollection.vue')
const LeadAnalysis = () => import('../../features/lead-analysis/LeadAnalysis.vue')
const EmailAutomation = () => import('../../features/lead-analysis/EmailAutomation.vue')
const BossLeadAssign = () => import('../../features/boss-dashboard/BossLeadAssign.vue')
const BossSalesManagement = () => import('../../features/boss-dashboard/BossSalesManagement.vue')
const MeetingAnalysis = () => import('../../features/meeting/MeetingAnalysis.vue')

export function prefetchLanding(path: string, userId: string, isSales: boolean) {
  if (path === '/dashboard' && isSales) {
    void DashboardView().catch(() => undefined)
    void loadSalesLanding(userId).catch(() => undefined)
  } else if (path === '/lead-collection' && !isSales) {
    void LeadCollection().catch(() => undefined)
    void loadCandidateLanding(userId).catch(() => undefined)
  }
}

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/login', name: 'login', component: LoginView, meta: { title: '登录' } },
    { path: '/dashboard', name: 'dashboard', component: DashboardView, meta: { title: '我的业绩' } },
    { path: '/customer-allocation', name: 'customerAllocation', component: CustomerAllocation, meta: { title: '客户分配' } },
    { path: '/customer-analysis', name: 'customerAnalysis', component: CustomerAnalysis, meta: { title: '客户分析' } },
    { path: '/customer-operation', name: 'customerOperation', component: CustomerOperation, meta: { title: '客户运营' } },
    { path: '/db-cases', name: 'dbCases', component: Database, meta: { title: '案例库' } },
    { path: '/db-scripts', name: 'dbScripts', component: Database, meta: { title: '话术库' } },
    { path: '/boss-dashboard', name: 'bossDashboard', component: BossDashboard, meta: { title: '经营驾驶舱' } },
    { path: '/welcome', name: 'welcome', component: WelcomeView, meta: { title: '工作台' } },
    { path: '/lead-collection', name: 'leadCollection', component: LeadCollection, meta: { title: '线索收集' } },
    { path: '/lead-analysis', name: 'leadAnalysis', component: LeadAnalysis, meta: { title: '线索分析' } },
    { path: '/email-automation', name: 'emailAutomation', component: EmailAutomation, meta: { title: '\u90ae\u4ef6\u89e6\u8fbe\u5386\u53f2' } },
    { path: '/boss-lead-assign', name: 'bossLeadAssign', component: BossLeadAssign, meta: { title: '客户分配' } },
    { path: '/boss-sales-mgmt', name: 'bossSalesMgmt', component: BossSalesManagement, meta: { title: '销售管理' } },
    { path: '/strategy', redirect: '/boss-dashboard' },
    { path: '/meeting-analysis', name: 'meetingAnalysis', component: MeetingAnalysis, meta: { title: '会议沟通' } },
  ],
})
