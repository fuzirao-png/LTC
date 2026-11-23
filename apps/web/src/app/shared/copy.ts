export const allocationStatusLabel: Record<string, string> = {
  claimable: '待认领', claimed: '已分配', released: '已回池', transferred: '已交接',
}

export const pipelineStageLabel: Record<string, string> = {
  new: '新线索', contacted: '已联系', engaged: '已沟通', meeting: '已约会', proposal: '方案中', won: '已成交', lost: '已流失', dormant: '沉默',
}

export const relationshipRoleLabel: Record<string, string> = {
  decision_maker: '决策人', influencer: '影响人', champion: '支持者', contact: '联系人',
}

export const emailStatusLabel: Record<string, string> = {
  valid: '邮箱有效', invalid: '邮箱无效', unknown: '未验证',
}

export const zh = {
  action: '操作', activeAssignments: '当前分配', addContact: '添加联系人', assign: '分配', back: '返回',
  changeStage: '更新阶段', channel: '沟通渠道', claim: '认领', claimableLeads: '可认领线索', company: '公司',
  companyProfile: '公司简介', contactName: '联系人', contacts: '联系人列表', currentCustomers: '当前客户数', currentView: '当前视图',
  customerAllocation: '客户分配', dashboardSubtitle: '查看当前客户和线索池状态', department: '部门', details: '查看详情', email: '邮箱',
  filteredByScope: '按权限范围筛选', firstTouch: '记录首次触达', followupStages: '跟进阶段', leadDetails: '线索详情', live: '实时',
  liveLeadData: '实时线索数据', liveLeadSuffix: '条线索', loadingDashboard: '正在加载驾驶舱', loadingLeads: '正在加载线索', manageLeads: '管理当前客户与线索',
  matchingRegionTier: '匹配区域和销售等级', mineStages: '我的跟进阶段', myCustomerOverview: '我的客户概览', myCustomers: '我的客户', noOwnedLeads: '暂无已分配客户',
  noOwner: '未分配', noPermittedLeads: '暂无可见线索', note: '备注', ownVisibility: '仅显示本人负责', owner: '负责人', phone: '电话',
  pipeline: '销售阶段', pipelineStage: '销售阶段', refresh: '刷新', regionTier: '区域 / 等级', release: '回收到池', resourcePool: '资源池',
  salesAllocation: '销售分配', salesDashboard: '销售驾驶舱', salesWorkspace: '销售工作台', save: '保存', stageReason: '原因', status: '状态',
  targetSales: '目标销售', title: '职位', transfer: '交接', type: '行业', updatedAt: '更新时间', waiting: '等待数据',
}
