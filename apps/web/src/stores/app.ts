import { defineStore } from 'pinia'
import { reactive, ref, computed } from 'vue'

export const useAppStore = defineStore('app', () => {
  // --- state ---
  const currentRole = ref<'sales' | 'ceo'>('sales')
  const currentView = ref('dashboard')
  const activeNavTab = ref('tab-ai-staff')
  const roleSelectorOpen = ref(false)
  const isProfileOpen = ref(false)
  const isPAPopupOpen = ref(false)
  const isEmailDialogOpen = ref(false)
  const isEmailEditPopupOpen = ref(false)
  const isAnalysisReportOpen = ref(false)
  const isMeetingUploaderOpen = ref(false)
  const isMeetingRecordOpen = ref(false)
  const activeCustomer = ref<string | { name: string }>('')
  const pendingClaimLead = ref<any>(null)
  const isClaimConfirmDialogOpen = ref(false)

  interface LeadItem {
    id: number
    name: string
    desc: string
    industry: string
    city: string
  }

  const leads = ref<LeadItem[]>([
    { id: 1, name: 'Sakura Travel Corp', desc: '日本领先的差旅平台服务商，专注企业差旅管理', industry: '差旅平台', city: '东京' },
    { id: 2, name: 'Osaka Corporate Services', desc: '大阪企业差旅解决方案提供商，服务中型企业客户群', industry: '企业服务', city: '大阪' },
    { id: 3, name: 'Kyoto Business Travel', desc: '京都老牌商务旅行 OTA，政府及企业客户为主', industry: '差旅平台', city: '京都' },
    { id: 4, name: 'Fukuoka OTA Group', desc: '九州地区商旅 OTA 平台，覆盖国内及东南亚线路', industry: '商旅 OTA', city: '福冈' },
    { id: 5, name: 'Sapporo Travel Desk', desc: '北海道地区企业差旅服务商，冬季旅游旺季客户', industry: '差旅服务', city: '札幌' },
    { id: 6, name: 'Nagoya Corp Travel', desc: '名古屋地区制造业企业差旅管理服务商', industry: '企业服务', city: '名古屋' },
    { id: 7, name: 'Sendai Biz Connect', desc: '东北地区新兴商旅连接平台，本地化服务优势明显', industry: '商旅平台', city: '仙台' },
  ])

  const user = reactive({
    avatar: '李',
    name: '李明',
    role: '日本销售 · L5',
  })

  const metrics = reactive({
    dealAmount: '$52,800',
    dealTarget: '目标 $120,000（43%）',
    convRate: '8.6%',
    convPeriod: '过去30天',
    goalProgress: 43,
  })

  // --- actions ---
  function setView(view: string) {
    currentView.value = view
  }

  function setRole(role: 'sales' | 'ceo') {
    currentRole.value = role
  }

  function toggleProfile() {
    isProfileOpen.value = !isProfileOpen.value
  }

  function openEmailDialog(customerName: string | { name: string }) {
    activeCustomer.value = customerName
    isEmailDialogOpen.value = true
  }

  function openMeetingRecord(customerName: string | { name: string }) {
    activeCustomer.value = customerName
    isMeetingRecordOpen.value = true
  }

  function openManualRecord(customerName: string | { name: string }) {
    activeCustomer.value = customerName
    isMeetingRecordOpen.value = true
  }

  function openMgmtDetail(_customerId: string) {
    // Navigate to customer management detail
    currentView.value = 'customer-mgmt'
  }

  async function claimLead(lead: { id: number; name: string }) {
    // Mock claim — would call a real API in production
    await new Promise(resolve => setTimeout(resolve, 300))
    leads.value = leads.value.filter(l => l.id !== lead.id)
  }

  async function sendEmail(_opts: {
    customerName: string
    recipientName: string
    recipientEmail: string
    subject: string
    body: string
  }): Promise<{ success: boolean; message?: string }> {
    // Mock email send — would call a real API in production
    return { success: true }
  }

  return {
    currentRole,
    currentView,
    activeNavTab,
    roleSelectorOpen,
    isProfileOpen,
    isPAPopupOpen,
    isEmailDialogOpen,
    isEmailEditPopupOpen,
    isAnalysisReportOpen,
    isMeetingUploaderOpen,
    isMeetingRecordOpen,
    activeCustomer,
    pendingClaimLead,
    isClaimConfirmDialogOpen,
    leads,
    user,
    metrics,
    setView,
    setRole,
    toggleProfile,
    openEmailDialog,
    openMeetingRecord,
    openManualRecord,
    openMgmtDetail,
    claimLead,
    sendEmail,
  }
})
