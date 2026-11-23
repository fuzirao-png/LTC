<script setup lang="ts">
import { useAppStore } from '../../stores/app';

const store = useAppStore();

</script>

<template>
<div
  id="view-customer-mgmt"
  class="detail-view"
  style="position:absolute;top:0;left:0;right:0;bottom:0;background:var(--bg-base);z-index:50;overflow-y:auto;"
>
<div style="padding:16px 20px;max-width:1400px;margin:0 auto;">
  <div class="agent-live-bar">
    <div class="live-dot"></div>
    <span style="font-weight:700;">客户管理 · 运行中</span>
    <div class="live-stat">
      <span>数量: <strong>6家</strong></span>
      <span>今日跟进: <strong>5次</strong></span>
      <span>今日会议: <strong>1场</strong></span>
    </div>
  </div>

  <div style="font-size:18px;font-weight:700;margin-bottom:14px;"> 客户管理</div>

  <!-- AI科技感动点 -->
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;padding:8px 12px;background:linear-gradient(135deg,#F0F9FF,#ECFDF5);border-radius:8px;border:1px solid var(--border);">
    <div style="position:relative;width:12px;height:12px;">
      <div style="width:12px;height:12px;border-radius:50%;background:linear-gradient(135deg,var(--blue-primary),var(--cyan-accent));animation:pulse-dot 1.5s infinite;"></div>
      <div style="position:absolute;top:-2px;left:-2px;width:16px;height:16px;border-radius:50%;border:2px solid var(--blue-primary);opacity:0.3;animation:pulse-dot 1.5s infinite 0.3s;"></div>
    </div>
    <span style="font-size:12px;font-weight:600;background:linear-gradient(90deg,var(--blue-primary),var(--cyan-accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent;">AI Agent 实时监控中</span>
  </div>

  <div style="display:flex;flex-direction:column;gap:10px;">

    <!-- GlobalLink Travel -->
    <div class="panel" style="border-left:4px solid var(--orange-warn);">
      <div style="padding:12px 16px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:18px;"></span>
            <span style="font-size:15px;font-weight:700;">GlobalLink Travel</span>
            <span style="font-size:10px;padding:2px 8px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">TMC</span>
          </div>
          <span style="font-size:10px;color:var(--text-muted);">联系人：Sarah Chen · Head of Technology</span>
        </div>
        <div style="margin-bottom:10px;">
          <div class="progress-bar" style="height:6px;margin-bottom:8px;"><div class="fill" style="width:65%;background:linear-gradient(90deg,var(--blue-primary),#D97706);"></div></div>
          <div style="display:flex;justify-content:space-between;font-size:10px;">
            <div style="text-align:center;flex:1;"><div style="color:var(--green-ok);font-weight:600;">已获得</div><div style="color:var(--text-muted);font-size:9px;">6/03</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--green-ok);font-weight:600;">已邮件</div><div style="color:var(--text-muted);font-size:9px;">6/04</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--green-ok);font-weight:600;">已回复</div><div style="color:var(--text-muted);font-size:9px;">6/05</div></div>
            <div style="text-align:center;flex:1;"><div style="color:#D97706;font-weight:600;">会议(x1)</div><div style="color:var(--text-muted);font-size:9px;">6/05</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">方案</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">成交</div><div style="font-size:9px;">—</div></div>
          </div>
        </div>

        <!-- 邮件交互记录 -->
        <div style="padding:8px;background:var(--bg-base);border-radius:6px;margin-bottom:10px;font-size:11px;">
          <div style="font-weight:600;margin-bottom:6px;"> 最近邮件交互</div>
          <div style="padding:6px;background:var(--bg-card);border-radius:4px;margin-bottom:4px;">
            <div style="display:flex;justify-content:space-between;"><span style="font-weight:600;"> #3 客户回复</span><span style="color:var(--text-muted);font-size:10px;">6/05 14:23</span></div>
            <div style="color:var(--text-secondary);margin-top:2px;">"Hi, we manage travel across 8 countries. Could you share the coverage list and enterprise pricing?"</div>
            <div style="margin-top:3px;padding:3px;background:#ECFDF5;border-radius:3px;font-size:10px;color:var(--green-ok);"> 信号：明确需求+决策推进 → 强意向</div>
          </div>
          <div style="padding:6px;background:var(--bg-card);border-radius:4px;">
            <div style="display:flex;justify-content:space-between;"><span style="font-weight:600;"> #2 触达邮件</span><span style="color:var(--text-muted);font-size:10px;">6/05 11:30</span></div>
            <div style="color:var(--text-secondary);margin-top:2px;">主题："Managing roaming costs across 8 countries"</div>
            <div style="margin-top:3px;font-size:10px;color:var(--text-muted);">ℹ 3小时内获得回复</div>
          </div>
        </div>

        <div style="display:flex;gap:4px;">
          <span class="btn-xs primary" @click="store.openEmailDialog('GlobalLink Travel')"> 邮件沟通</span>
          <span class="btn-xs" @click="store.openMeetingRecord('GlobalLink Travel')"> 会议沟通</span>
          <span class="btn-xs" @click="store.openManualRecord('GlobalLink Travel')"> 手动记录</span>
        </div>
      </div>
    </div>

    <!-- Pacific TMC -->
    <div class="panel" style="border-left:4px solid var(--blue-primary);">
      <div style="padding:12px 16px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:18px;"></span>
            <span style="font-size:15px;font-weight:700;">Pacific TMC Japan</span>
            <span style="font-size:10px;padding:2px 8px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">TMC</span>
          </div>
          <span style="font-size:10px;color:var(--text-muted);">联系人：Tanaka Kenji</span>
        </div>
        <div style="margin-bottom:10px;">
          <div class="progress-bar" style="height:6px;margin-bottom:8px;"><div class="fill" style="width:35%;background:var(--blue-primary);"></div></div>
          <div style="display:flex;justify-content:space-between;font-size:10px;">
            <div style="text-align:center;flex:1;"><div style="color:var(--green-ok);font-weight:600;">已获得</div><div style="color:var(--text-muted);font-size:9px;">6/01</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--green-ok);font-weight:600;">已邮件</div><div style="color:var(--text-muted);font-size:9px;">6/02</div></div>
            <div style="text-align:center;flex:1;"><div style="color:#D97706;font-weight:600;">已回复</div><div style="color:var(--text-muted);font-size:9px;">6/04</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">会议</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">方案</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">成交</div><div style="font-size:9px;">—</div></div>
          </div>
        </div>
        <div style="display:flex;gap:4px;">
          <span class="btn-xs primary" @click="store.openEmailDialog('Pacific TMC Japan')">邮件沟通</span>
          <span class="btn-xs" @click="store.openMeetingRecord('Pacific TMC Japan')">会议沟通</span>
          <span class="btn-xs" @click="store.openManualRecord('Pacific TMC Japan')">手动记录</span>
        </div>
      </div>
    </div>

    <!-- TechTravel Inc. -->
    <div class="panel" style="border-left:4px solid var(--blue-primary);">
      <div style="padding:12px 16px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:18px;"></span>
            <span style="font-size:15px;font-weight:700;">TechTravel Inc.</span>
            <span style="font-size:10px;padding:2px 8px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">OTA</span>
          </div>
          <span style="font-size:10px;color:var(--text-muted);">联系人：Michael Zhang</span>
        </div>
        <div style="margin-bottom:10px;">
          <div class="progress-bar" style="height:6px;margin-bottom:8px;"><div class="fill" style="width:20%;background:var(--blue-primary);"></div></div>
          <div style="display:flex;justify-content:space-between;font-size:10px;">
            <div style="text-align:center;flex:1;"><div style="color:var(--green-ok);font-weight:600;">已获得</div><div style="color:var(--text-muted);font-size:9px;">6/05</div></div>
            <div style="text-align:center;flex:1;"><div style="color:#D97706;font-weight:600;">已邮件</div><div style="color:var(--text-muted);font-size:9px;">6/05</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">已回复</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">会议</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">方案</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">成交</div><div style="font-size:9px;">—</div></div>
          </div>
        </div>
        <div style="display:flex;gap:4px;">
          <span class="btn-xs primary" @click="store.openEmailDialog('TechTravel Inc.')">邮件沟通</span>
          <span class="btn-xs" @click="store.openMeetingRecord('TechTravel Inc.')">会议沟通</span>
          <span class="btn-xs" @click="store.openManualRecord('TechTravel Inc.')">手动记录</span>
        </div>
      </div>
    </div>

    <!-- AsiaBiz Travel -->
    <div class="panel" style="border-left:4px solid var(--blue-primary);">
      <div style="padding:12px 16px;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:18px;"></span>
            <span style="font-size:15px;font-weight:700;">AsiaBiz Travel</span>
            <span style="font-size:10px;padding:2px 8px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">TMC</span>
          </div>
          <span style="font-size:10px;color:var(--text-muted);">联系人：—</span>
        </div>
        <div style="margin-bottom:10px;">
          <div class="progress-bar" style="height:6px;margin-bottom:8px;"><div class="fill" style="width:20%;background:var(--blue-primary);"></div></div>
          <div style="display:flex;justify-content:space-between;font-size:10px;">
            <div style="text-align:center;flex:1;"><div style="color:var(--green-ok);font-weight:600;">已获得</div><div style="color:var(--text-muted);font-size:9px;">6/04</div></div>
            <div style="text-align:center;flex:1;"><div style="color:#D97706;font-weight:600;">已邮件</div><div style="color:var(--text-muted);font-size:9px;">6/04</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">已回复</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">会议</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">方案</div><div style="font-size:9px;">—</div></div>
            <div style="text-align:center;flex:1;"><div style="color:var(--text-muted);">成交</div><div style="font-size:9px;">—</div></div>
          </div>
        </div>
        <div style="display:flex;gap:4px;">
          <span class="btn-xs primary" @click="store.openEmailDialog('AsiaBiz Travel')">邮件沟通</span>
          <span class="btn-xs" @click="store.openMeetingRecord('AsiaBiz Travel')">会议沟通</span>
          <span class="btn-xs" @click="store.openManualRecord('AsiaBiz Travel')">手动记录</span>
        </div>
      </div>
    </div>

  </div>
</div></div>
</template>

<style scoped>
/* Scoped styles can be added here if needed, but we rely on global css mostly */
</style>
