<script setup lang="ts">
import { computed, ref } from 'vue';
import { useAppStore } from '../../stores/app';
import { useAuthStore } from '../../stores/auth';

const store = useAppStore();
const auth = useAuthStore();
const paAssistantName = computed(
  () => auth.currentUser?.name || auth.currentUser?.username || '李明',
);
const message = ref('');
const ceoMessage = ref('');
const chatHistory = ref<any[]>([]);
const ceoChatHistory = ref<any[]>([]);

const sendMessage = () => {
  if (!message.value.trim()) return;
  chatHistory.value.push({ type: 'user', text: message.value });
  const userMsg = message.value;
  message.value = '';

  setTimeout(() => {
    let reply = `收到指令「${userMsg.substring(0, 12)}」正在处理...`;
    if (userMsg.includes('断点')) reply = '今日3条待处理断点：Pacific TMC回复 · 🔛TravelCorp跟进 · 🔛CrossBorder连接';
    if (userMsg.includes('话术')) reply = '正在为你生成针对日本 TMC 决策人的话术模板...';
    chatHistory.value.push({ type: 'pa', text: reply });
  }, 500);
};

const sendCeoMessage = () => {
  if (!ceoMessage.value.trim()) return;
  const userMsg = ceoMessage.value;
  ceoChatHistory.value.push({ type: 'user', text: userMsg });
  ceoMessage.value = '';
  setTimeout(() => {
    ceoChatHistory.value.push({ type: 'pa', text: 'PA正在调整资源分配，预计15分钟内生效' });
  }, 500);
};

const quickAction = (text: string) => {
  message.value = text;
  sendMessage();
};

const quickCeoAction = (text: string) => {
  ceoMessage.value = text;
  sendCeoMessage();
};
</script>

<template>
  <div>
    <!-- 销售 PA 浮动气泡 -->
    <button v-if="store.currentRole === 'sales'" class="pa-fab" id="salesFab" @click="store.isPAPopupOpen = !store.isPAPopupOpen" title="PA 助手">
      <span class="icon" style="font-size:24px;">✨</span>
      <span class="fab-badge">3</span>
    </button>

    <!-- 张总 PA 浮动气泡 -->
    <button v-if="store.currentRole === 'ceo'" class="pa-fab ceo-fab" id="ceoFab" @click="store.isPAPopupOpen = !store.isPAPopupOpen" title="战略指令">
      <span class="icon" style="font-size:24px;">🎯</span>
      <span class="fab-badge">2</span>
    </button>

    <!-- 销售 PA 弹窗 -->
    <div v-if="store.isPAPopupOpen && store.currentRole === 'sales'" class="pa-popup open" id="salesPopup" style="width:420px;max-width:90vw;bottom:86px;right:24px;top:auto;left:auto;transform:none;height:520px;animation:none;">
      <div class="pa-popup-header" style="background:linear-gradient(135deg,var(--blue-light),#F0F9FF);">
        <span> PA · {{ paAssistantName }}的助手</span>
        <span class="pa-close" @click="store.isPAPopupOpen = false" style="font-size:18px;padding:6px 10px;">✕</span>
      </div>
      <div class="pa-popup-body">
        <!-- 重要事项 -->
        <div>
          <div class="pa-section-title"> 重要事项 <span style="color:var(--red-badge);">5条</span></div>
          <div style="display:flex;flex-direction:column;gap:4px;margin-bottom:10px;">
            <!-- 人机断点 -->
            <div style="padding:6px 8px;background:#FFF5F5;border-radius:6px;display:flex;align-items:center;gap:6px;border-left:3px solid var(--red-badge);font-size:11px;">
              <span style="font-size:12px;">🔴</span>
              <span style="flex:1;"><strong>Pacific TMC</strong> 回复邮件，询问成本方案</span>
              <span class="btn-xs primary" @click="store.setView('customer-mgmt');store.isPAPopupOpen=false;" style="font-size:9px;">处理</span>
            </div>
            <div style="padding:6px 8px;background:#FFFBF5;border-radius:6px;display:flex;align-items:center;gap:6px;border-left:3px solid var(--orange-warn);font-size:11px;">
              <span style="font-size:12px;">🔛</span>
              <span style="flex:1;"><strong>Nagoya</strong> 邮件已发3天，AI建议二次触达</span>
              <span class="btn-xs" @click="store.setView('customer-mgmt');store.isPAPopupOpen=false;" style="font-size:9px;">跟进</span>
            </div>
            <!-- TODO -->
            <div style="padding:6px 8px;background:var(--bg-base);border-radius:6px;display:flex;align-items:center;gap:6px;border-left:3px solid var(--red-badge);font-size:11px;cursor:pointer;" @click="store.setView('customer-mgmt');store.isPAPopupOpen=false;">
              <span style="font-size:12px;">📌</span>
              <span style="flex:1;">回复 Pacific TMC（强意向）</span>
              <span style="font-size:10px;color:var(--red-badge);font-weight:600;">紧急</span>
            </div>
            <div style="padding:6px 8px;background:var(--bg-base);border-radius:6px;display:flex;align-items:center;gap:6px;border-left:3px solid var(--orange-warn);font-size:11px;cursor:pointer;" @click="store.setView('customer-mgmt');store.isPAPopupOpen=false;">
              <span style="font-size:12px;">📌</span>
              <span style="flex:1;">跟进 Nagoya Business Travel</span>
              <span style="font-size:10px;color:var(--text-muted);">今天</span>
            </div>
            <div style="padding:6px 8px;background:var(--bg-base);border-radius:6px;display:flex;align-items:center;gap:6px;border-left:3px solid var(--orange-warn);font-size:11px;cursor:pointer;" @click="store.setView('customer-mgmt');store.isPAPopupOpen=false;">
              <span style="font-size:12px;">📌</span>
              <span style="flex:1;">LinkedIn连接 CrossBorder</span>
              <span style="font-size:10px;color:var(--text-muted);">今天</span>
            </div>
          </div>
        </div>

        <!-- 日程 -->
        <div>
          <div class="pa-section-title"> 日程</div>
          <div style="display:flex;flex-direction:column;gap:4px;">
            <div style="padding:8px 10px;background:linear-gradient(135deg,#F0F9FF,#ECFDF5);border-radius:8px;display:flex;align-items:center;gap:10px;border-left:3px solid var(--green-ok);">
              <div style="text-align:center;min-width:40px;">
                <div style="font-size:18px;font-weight:800;color:var(--blue-primary);">10</div>
                <div style="font-size:9px;color:var(--text-muted);">6月</div>
              </div>
              <div style="flex:1;">
                <div style="font-size:12px;font-weight:600;">Pacific TMC 产品演示</div>
                <div style="font-size:10px;color:var(--text-muted);">明天 10:00 · 线上会议</div>
              </div>
              <span style="font-size:10px;padding:2px 6px;background:var(--green-ok);color:#fff;border-radius:4px;">已确认</span>
            </div>
            <div style="padding:8px 10px;background:var(--bg-base);border-radius:8px;display:flex;align-items:center;gap:10px;border-left:3px solid var(--blue-primary);">
              <div style="text-align:center;min-width:40px;">
                <div style="font-size:18px;font-weight:800;color:var(--blue-primary);">12</div>
                <div style="font-size:9px;color:var(--text-muted);">6月</div>
              </div>
              <div style="flex:1;">
                <div style="font-size:12px;font-weight:600;">GlobalLink 方案演示</div>
                <div style="font-size:10px;color:var(--text-muted);">周四 14:00 · 线上会议</div>
              </div>
              <span style="font-size:10px;padding:2px 6px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">待确认</span>
            </div>
            <div style="padding:8px 10px;background:var(--bg-base);border-radius:8px;display:flex;align-items:center;gap:10px;border-left:3px solid var(--text-muted);">
              <div style="text-align:center;min-width:40px;">
                <div style="font-size:18px;font-weight:800;color:var(--text-muted);">15</div>
                <div style="font-size:9px;color:var(--text-muted);">6月</div>
              </div>
              <div style="flex:1;">
                <div style="font-size:12px;font-weight:600;">GBTA 行业大会</div>
                <div style="font-size:10px;color:var(--text-muted);">周日 · 线下活动</div>
              </div>
              <span style="font-size:10px;padding:2px 6px;background:var(--bg-base);color:var(--text-muted);border-radius:4px;">计划中</span>
            </div>
          </div>
        </div>

        <!-- 聊天区域 -->
        <div id="salesChatArea" style="flex:1;overflow-y:auto;font-size:11px;color:var(--text-secondary);display:flex;flex-direction:column;gap:6px;">
          <div v-for="(chat, i) in chatHistory" :key="i" style="padding:3px 0;" :style="chat.type==='pa' ? 'color:var(--blue-primary);' : ''">
            <strong>{{ chat.type === 'pa' ? 'PA：' : '你：' }}</strong>{{ chat.text }}
          </div>
        </div>
      </div>
      <div class="pa-popup-input">
        <input type="text" id="salesPaInput" v-model="message" placeholder="输入指令..." @keyup.enter="sendMessage">
        <button class="pa-send-btn" @click="sendMessage">发送</button>
      </div>
    </div>

    <!-- 张总 PA 弹窗 -->
    <div v-if="store.isPAPopupOpen && store.currentRole === 'ceo'" class="pa-popup open" id="ceoPopup">
      <div class="pa-popup-header" style="background:linear-gradient(135deg,#EDE9FE,#F0F9FF);">
        <span> 张总 · 战略指令</span>
        <span class="pa-close" @click="store.isPAPopupOpen = false">✕</span>
      </div>
      <div class="pa-popup-body">
        <!-- 早安问候 + 资讯 -->
        <div style="padding:5px 10px;background:linear-gradient(135deg,#EDE9FE,#F0F9FF);border-radius:6px;border-left:3px solid #7C3AED;font-size:11px;line-height:1.4;">
          <div style="font-weight:700;margin-bottom:2px;"> 张总，早上好！今天是2026年6月10日 星期三</div>
          <div style="color:var(--text-secondary);margin-bottom:4px;">
             今日天气：北京 32°C 晴 · 上海 30°C 多云 · 东京 22°C 晴转多云<br>
             日经指数 38,420 (+1.2%) · 美元/日元 155.3 · 恒生指数 18,200 (+0.8%)
          </div>
          <div style="font-weight:600;margin-bottom:2px;color:var(--text-primary);"> 公司与业务资讯</div>
          <div style="color:var(--text-secondary);">
            · <strong>公司动态：</strong>企业多国通讯费统一管理方案正式上线，3家TMC客户试用中<br>
            · <strong>业务进展：</strong>日本市场增长11%表现最佳，TMC线索占比18%→27%<br>
            · <strong>销售数据：</strong>Pipeline $186,400 · 本月成交$42,800（目标43%）· 预测月底$68,000<br>
            · <strong>团队表现：</strong>张伟转化率5.2%领先，王芳跟进率71%需关注<br>
            · <strong>渠道ROI：</strong>B端5.2x > GEO 3.9x > C端2.8x > 手动上传1.2x<br>
            · <strong>风险提示：</strong>欧洲成交下滑12%，跳出率5.8%超阈值，需排查发件域名<br>
            · <strong>近期活动：</strong>GBTA大会下周举行，建议安排团队参会拓展线索<br>
            · <strong>融资进展：</strong>Pre-A轮进行中，本月需提交增长数据
          </div>
          <div style="margin-top:3px;padding:3px 6px;background:var(--bg-card);border-radius:4px;color:#7C3AED;font-size:10px;">
             战略简报：线索1,247条 · 已分配856条 · 成交$42,800 · Agent健康度94%
          </div>
        </div>

        <!-- 待决策 -->
        <div>
          <div class="pa-section-title"> 待决策 <span style="color:var(--red-badge);">2条</span></div>
          <div class="pa-todo-item">
            <div class="pa-dot red"></div>
            <span style="flex:1;">欧洲区转化率下滑12%，需决策是否调整资源</span>
          </div>
          <div class="pa-todo-item">
            <div class="pa-dot orange"></div>
            <span style="flex:1;">日本区增速11%，是否增加资源投入？</span>
          </div>
        </div>

        <!-- 快捷指令 -->
        <div>
          <div class="pa-section-title"> 快捷战略指令</div>
          <div style="display:flex;gap:4px;flex-wrap:wrap;">
            <span class="pa-cmd-btn" @click="quickCeoAction('增加日本资源')">增加日本资源</span>
            <span class="pa-cmd-btn" @click="quickCeoAction('主攻B端客群')">主攻B端客群</span>
            <span class="pa-cmd-btn" @click="quickCeoAction('暂停欧洲触达')">暂停欧洲触达</span>
            <span class="pa-cmd-btn" @click="quickCeoAction('扩大GEO投放')">扩大GEO投放</span>
            <span class="pa-cmd-btn" @click="quickCeoAction('冲刺本月目标')">冲刺本月目标</span>
          </div>
        </div>

        <!-- 指令对话区 -->
        <div style="padding:8px 10px;background:var(--bg-base);border-radius:6px;font-size:11px;">
          <div class="pa-section-title"> 指令记录</div>
          <div id="ceoChatArea" style="color:var(--text-secondary);line-height:1.6;">
            <div style="padding:4px 0;border-bottom:1px solid var(--border-light);">上次指令：「本月优先开拓日本TMC市场」已执行</div>
            <div style="padding:4px 0;font-size:10px;color:var(--text-muted);">效果：日本TMC线索占比 18%→27%</div>
            <div v-for="(chat, i) in ceoChatHistory" :key="i" style="padding:4px 0;border-bottom:1px solid var(--border-light);">
              <template v-if="chat.type === 'user'">
                指令：「{{ chat.text }}」<span style="color:var(--green-ok);margin-left:4px;">已下达</span>
              </template>
              <template v-else>
                <div style="font-size:10px;color:var(--text-muted);">{{ chat.text }}</div>
              </template>
            </div>
          </div>
        </div>
      </div>
      <div class="pa-popup-input">
        <input type="text" id="ceoPaInput" v-model="ceoMessage" placeholder="输入战略指令..." @keyup.enter="sendCeoMessage">
        <button class="pa-send-btn" style="background:#7C3AED;" @click="sendCeoMessage">下达</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Scoped styles are mostly inherited from global style.css */
</style>
