<script setup lang="ts">
import { useAppStore } from '../../stores/app';

const store = useAppStore();

</script>

<template>
  <div class="content-main" id="dashboardView">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
      <div style="font-size:18px;font-weight:700;"> 我的业绩</div>
      <div style="font-size:12px;color:var(--text-muted);">李明 · 日本销售 · 今日 2026.06.05</div>
    </div>

      <!-- 成交额度（本年） -->
      <div class="metric-cards col3">
        <div class="metric-card"><div class="metric-label">成交额度（本年）</div><div class="metric-val" style="color:var(--green-ok);" id="dealAmount">{{ store.metrics.dealAmount }}</div><div class="metric-sub" id="dealTarget">{{ store.metrics.dealTarget }}</div></div>
        <div class="metric-card"><div class="metric-label">转化率</div><div class="metric-val" style="color:var(--blue-primary);" id="convRate">{{ store.metrics.convRate }}</div><div class="metric-sub"><span class="change up">↑2%</span> <span id="convPeriod">{{ store.metrics.convPeriod }}</span></div></div>
        <div class="metric-card"><div class="metric-label">个人目标完成度</div><div class="metric-val" style="color:#D97706;" id="goalProgress">{{ store.metrics.goalProgress }}%</div><div class="metric-sub"><div class="progress-bar" style="height:4px;margin-top:4px;"><div class="fill" id="goalBar" :style="`width:${store.metrics.goalProgress}%;background:linear-gradient(90deg,var(--blue-primary),var(--green-ok));`"></div></div></div></div>
      </div>
  <!-- 业绩详情 -->
  <div class="panel">
    <div class="panel-header"><span> 本月业绩详情</span></div>
    <div class="panel-body" style="font-size:12px;">
      <div style="margin-bottom:12px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;"><span>成交额进度</span><span style="font-weight:700;">$6,200 / $12,000</span></div>
        <div class="progress-bar" style="height:8px;"><div class="fill" style="width:52%;background:linear-gradient(90deg,var(--blue-primary),var(--green-ok));"></div></div>
        <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">完成52% · 本月还剩25天</div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px;margin-bottom:12px;">
        <div style="padding:8px;background:var(--bg-base);border-radius:6px;text-align:center;">
          <div style="font-size:18px;font-weight:800;color:var(--blue-primary);">19</div>
          <div style="font-size:10px;color:var(--text-muted);">我的线索</div>
        </div>
        <div style="padding:8px;background:var(--bg-base);border-radius:6px;text-align:center;">
          <div style="font-size:18px;font-weight:800;color:var(--green-ok);">12.1%</div>
          <div style="font-size:10px;color:var(--text-muted);">转化率</div>
        </div>
        <div style="padding:8px;background:var(--bg-base);border-radius:6px;text-align:center;">
          <div style="font-size:18px;font-weight:800;color:#D97706;">88%</div>
          <div style="font-size:10px;color:var(--text-muted);">客户跟进率</div>
        </div>
        <div style="padding:8px;background:var(--bg-base);border-radius:6px;text-align:center;">
          <div style="font-size:18px;font-weight:800;color:var(--text-primary);">21天</div>
          <div style="font-size:10px;color:var(--text-muted);">平均成单周期</div>
        </div>
      </div>
      <div style="padding:8px;background:var(--bg-base);border-radius:6px;">
        <div style="font-weight:600;margin-bottom:4px;"> AI建议</div>
        <div style="font-size:11px;color:var(--text-secondary);">你本月日本市场回复率16%高于团队均值，继续保持。当前有2条客户待跟进，建议优先处理Pacific TMC（强意向）。</div>
      </div>
    </div>
  </div>

    <!-- 客户列表 -->
    <div class="panel">
      <div class="panel-header"><span> 我的客户概览</span><span style="font-size:10px;color:var(--text-muted);">6家客户 · 3家活跃</span></div>
      <div class="panel-body" style="padding:0;">
        <table class="matrix-table"><thead><tr><th>客户</th><th>阶段</th><th>成交额</th><th>最近跟进</th><th>操作</th></tr></thead><tbody>
          <tr><td style="font-weight:600;">Pacific TMC Japan</td><td><span class="status-tag 有回复"> 有回复</span></td><td>—</td><td>6/04</td><td><span class="btn-xs primary" @click="store.setView('customer-mgmt')">跟进</span></td></tr>
          <tr><td style="font-weight:600;">Sakura Travel Corp</td><td><span class="status-tag 已成交"> 已成交</span></td><td>$2,400/年</td><td>5/28</td><td><span class="btn-xs" @click="store.setView('customer-mgmt')">查看</span></td></tr>
          <tr><td style="font-weight:600;">Nagoya Business Travel</td><td><span class="status-tag 已触达">已触达</span></td><td>—</td><td>6/03</td><td><span class="btn-xs" @click="store.setView('customer-mgmt')">查看</span></td></tr>
          <tr><td style="font-weight:600;">Kyoto Business Travel</td><td><span style="color:var(--text-muted);">待领取</span></td><td>—</td><td>—</td><td><span class="btn-xs primary" @click="store.setView('lead-assign')">领取</span></td></tr>
          <tr><td style="font-weight:600;">GlobalLink Travel</td><td><span class="status-tag 强意向"> 强意向</span></td><td>—</td><td>6/05</td><td><span class="btn-xs primary" @click="store.setView('customer-mgmt')">跟进</span></td></tr>
          <tr><td style="font-weight:600;">TechTravel Inc.</td><td><span class="status-tag 已触达">已触达</span></td><td>—</td><td>6/05</td><td><span class="btn-xs" @click="store.setView('customer-mgmt')">查看</span></td></tr>
        </tbody></table>
      </div>
    </div>

    <!-- 团队指标 -->
      <div class="metric-cards" style="margin-top:12px;margin-bottom:20px;">
        <div class="metric-card"><div class="metric-label">本月团队额度</div><div class="metric-val" style="color:var(--blue-primary);">$42,800</div><div class="metric-sub">目标 $80,000 · 53%</div></div>
        <div class="metric-card"><div class="metric-label">我的业绩排名（团队内）</div><div class="metric-val" style="color:var(--green-ok);">2<span style="font-size:14px;">/4</span></div><div class="metric-sub">团队共4人</div></div>
        <div class="metric-card"><div class="metric-label">我的团队业绩排名（公司内）</div><div class="metric-val" style="color:var(--blue-primary);">2<span style="font-size:14px;">/4</span></div><div class="metric-sub">本月 · 同比上月持平</div></div>
      </div>
  </div>
</template>

<style scoped>
.status-tag { font-size: 12px; }
.status-tag.有回复 { color: #D97706; }
.status-tag.已成交 { color: var(--green-ok); }
.status-tag.已触达 { color: var(--blue-primary); }
.status-tag.强意向 { color: #D97706; font-weight: 700; }
</style>
