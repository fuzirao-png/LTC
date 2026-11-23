<script setup lang="ts">
import { useAppStore } from '../../stores/app';

const store = useAppStore();

const confirmClaim = (lead: { id: number; name: string; desc: string; industry: string; city: string }) => {
  store.pendingClaimLead = lead;
  store.isClaimConfirmDialogOpen = true;
};

const executeClaim = async () => {
  if (store.pendingClaimLead) {
    try {
      await store.claimLead(store.pendingClaimLead);
      store.isClaimConfirmDialogOpen = false;
      store.pendingClaimLead = null;
      alert('已领取线索');
    } catch (error) {
      alert(error instanceof Error ? error.message : '领取失败');
    }
  }
};

const cancelClaim = () => {
  store.isClaimConfirmDialogOpen = false;
  store.pendingClaimLead = null;
};

</script>

<template>
<div
  id="view-lead-assign"
  class="detail-view"
  style="position:absolute;top:0;left:0;right:0;bottom:0;background:var(--bg-base);z-index:50;overflow-y:auto;"
>
<div style="padding:16px 20px;max-width:1400px;margin:0 auto;">
  <div class="agent-live-bar">
    <div class="live-dot"></div>
    <span style="font-weight:700;">线索分配 · 运行中</span>
    <div class="live-stat">
    </div>
  </div>

  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
    <div style="font-size:18px;font-weight:700;"> 线索分配</div>
  </div>

  <div class="metric-cards" style="margin-bottom:14px;">
    <div class="metric-card"><div class="metric-label">待领取</div><div class="metric-val" style="color:var(--blue-primary);" id="pendingLeadCount">{{ store.leads.length }}</div><div class="metric-sub">系统已匹配到你名下</div></div>
    <div class="metric-card"><div class="metric-label">已领取</div><div class="metric-val" id="claimedLeadCount">19</div><div class="metric-sub">本月累计</div></div>
    <div class="metric-card"><div class="metric-label">跟进率</div><div class="metric-val" style="color:var(--green-ok);">88%</div><div class="metric-sub">本月</div></div>
    <div class="metric-card"><div class="metric-label">转化率</div><div class="metric-val" style="color:var(--green-ok);">12.1%</div><div class="metric-sub">领取→成交</div></div>
  </div>

  <!-- 资源池 -->
  <div class="panel" style="margin-bottom:14px;">
    <div class="panel-header"><span>资源池</span></div>
    <div class="panel-body" style="padding:0;">
      <table class="matrix-table"><thead><tr><th>公司名称</th><th>公司简介</th><th>所在行业</th><th>所在城市</th><th>操作</th></tr></thead><tbody id="pendingLeadTable">
        <tr
          v-for="(lead, index) in store.leads"
          :key="lead.id"
          :style="index < 2 ? 'background:#FFFBF5;' : ''"
        >
          <td style="font-weight:600;">{{ lead.name }}</td>
          <td style="font-size:11px;color:var(--text-secondary);">{{ lead.desc }}</td>
          <td>{{ lead.industry }}</td>
          <td>{{ lead.city }}</td>
          <td><span class="btn-xs primary" @click="confirmClaim(lead)">领取</span></td>
        </tr>
      </tbody></table>
    </div>
  </div>

  <!-- 我的线索 -->
  <div class="panel">
    <div class="panel-header"><span>我的线索</span></div>
    <div class="panel-body" style="padding:0;">
      <table class="matrix-table"><thead><tr><th>公司名称</th><th>领取时间</th><th>所在城市</th><th>所在行业</th><th>状态</th><th>操作</th></tr></thead><tbody id="claimedLeadTable">
        <tr style="background:#FFFBF5;">
          <td style="font-weight:600;">Pacific TMC Japan</td>
          <td>6/01</td>
          <td>东京</td>
          <td>TMC</td>
          <td><span style="color:#D97706;">有回复</span></td>
          <td><span class="btn-xs primary" @click="store.openMgmtDetail('pacific')">跟进</span></td>
        </tr>
        <tr>
          <td style="font-weight:600;">Sakura Travel Corp</td>
          <td>5/20</td>
          <td>东京</td>
          <td>TMC</td>
          <td><span style="color:var(--green-ok);">已成交</span></td>
          <td><span class="btn-xs" @click="store.openMgmtDetail('sakura')">查看</span></td>
        </tr>
        <tr>
          <td style="font-weight:600;">Nagoya Business Travel</td>
          <td>6/03</td>
          <td>名古屋</td>
          <td>TMC</td>
          <td><span style="color:var(--blue-primary);">已触达</span></td>
          <td><span class="btn-xs" @click="store.openMgmtDetail('nagoya')">查看</span></td>
        </tr>
      </tbody></table>
    </div>
  </div>

<!-- 领取确认弹窗 -->
<div id="claimConfirmDialog" v-if="store.isClaimConfirmDialogOpen" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.4);z-index:500;align-items:center;justify-content:center;display:flex;">
  <div style="background:var(--bg-card);border-radius:14px;width:380px;box-shadow:0 8px 32px rgba(0,0,0,0.2);">
    <div style="padding:18px 20px;text-align:center;">
      <div style="font-size:15px;font-weight:700;margin-bottom:8px;">确认领取线索</div>
      <div style="font-size:12px;color:var(--text-secondary);margin-bottom:16px;">确定领取 <strong id="claimCompanyName">{{ store.pendingClaimLead?.name || "—" }}</strong> 的线索？领取后需在7天内完成首次跟进。</div>
      <div style="display:flex;gap:10px;justify-content:center;">
        <span class="btn-primary" style="padding:8px 24px;" @click="executeClaim">确认领取</span>
        <span class="btn-outline" style="padding:8px 24px;" @click="cancelClaim">取消</span>
      </div>
    </div>
  </div>
</div>

</div></div>
</template>

<style scoped>
.status-tag { font-size: 12px; }
.status-tag.有回复 { color: #D97706; }
.status-tag.已成交 { color: var(--green-ok); }
.status-tag.已触达 { color: var(--blue-primary); }
.status-tag.强意向 { color: #D97706; font-weight: 700; }
.status-tag.已领取 { color: var(--blue-primary); }
</style>
