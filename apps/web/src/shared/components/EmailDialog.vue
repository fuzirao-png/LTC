<script setup lang="ts">
import { computed, ref } from 'vue';
import { useAppStore } from '../../stores/app';

const store = useAppStore();
const prompt = ref('');
const isGenerating = ref(false);
const feedbackText = ref('');
const subject = ref('Re: Enterprise eSIM Solution for 8-Country Coverage');
const body = ref(`Dear Sarah,

Thank you for your interest in our enterprise eSIM solution. Based on your travel management needs across 8 countries, our platform offers transparent cost management for corporate communications with full GDPR compliance.

Our enterprise pricing is based on tiered usage, which can help reduce your communication costs by up to 40%.

I would love to schedule a 30-minute meeting to discuss how we can support GlobalLink's expansion plans.

Best regards,
李明`);

const activeContact = ref('Sarah Chen');
const editSubject = ref('');
const editBody = ref('');
const activeHistoryId = ref('default');

const contactEmailMap: Record<string, string> = {
  'Sarah Chen': 's.chen@globallink.com',
  'James Wilson': 'j.wilson@globallink.com',
  'Maria Garcia': 'm.garcia@globallink.com',
};

const historyEmailMap = {
  reply: {
    subject: 'Re: Enterprise eSIM Solution for 8-Country Coverage',
    body: `Dear Sarah,

Thank you for your reply. I have attached the multi-country coverage list and an overview of our enterprise pricing tiers for your review.

We can support GDPR-compliant connectivity management across your 8 target countries while simplifying supplier coordination and cost visibility.

If helpful, I can also walk your team through the pricing model in a 30-minute call this week.

Best regards,
李明`,
  },
  outbound: {
    subject: 'Managing roaming costs across 8 countries',
    body: `Dear Sarah,

Thank you for your interest in our enterprise eSIM solution. Based on your travel management needs across 8 countries, our platform offers transparent cost management for corporate communications with full GDPR compliance.

Our enterprise pricing is based on tiered usage, which can help reduce your communication costs by up to 40%.

I would love to schedule a 30-minute meeting to discuss how we can support GlobalLink's expansion plans.

Best regards,
李明`,
  },
} as const;

const activeContactEmail = computed(() => contactEmailMap[activeContact.value] || 'contact@example.com');

const regenerate = () => {
  isGenerating.value = true;
  feedbackText.value = '';
  activeHistoryId.value = '';
  setTimeout(() => {
    isGenerating.value = false;
    body.value = `Dear Sarah,\n\nThank you for your continued interest. Based on your specific requirements for 8-country coverage and GDPR compliance, I'm pleased to share our tailored enterprise solution.\n\nKey highlights:\n• Full GDPR compliance across all 8 countries\n• Up to 40% cost reduction on communications\n• Dedicated enterprise support\n\nWould you be available for a 30-minute demo this week?\n\nBest regards,\n李明`;
    feedbackText.value = '✅ 已根据你的指令重新生成';
  }, 1500);
};

const closeDialog = () => {
  store.isEmailDialogOpen = false;
  store.isEmailEditPopupOpen = false;
};

const getCustomerName = () =>
  typeof store.activeCustomer === 'string'
    ? store.activeCustomer
    : store.activeCustomer?.name || 'GlobalLink Travel';

const send = async () => {
  const result = await store.sendEmail({
    customerName: getCustomerName(),
    recipientName: activeContact.value,
    recipientEmail: activeContactEmail.value,
    subject: subject.value,
    body: body.value,
  });
  if (!result.success) {
    alert(result.message || '邮件发送失败');
    return;
  }
  alert('邮件已成功发送！');
  closeDialog();
};

const emailFeedback = (type: 'up' | 'down') => {
  if (type === 'up') {
    feedbackText.value = '👍 已反馈满意，AI将参考此偏好继续优化';
    return;
  }
  feedbackText.value = '👎 已反馈不满意，AI将根据你的指令重新生成';
};

const selectContact = (name: string) => {
  activeContact.value = name;
};

const openEmailEditPopup = () => {
  editSubject.value = subject.value;
  editBody.value = body.value;
  store.isEmailEditPopupOpen = true;
};

const closeEmailEditPopup = () => {
  store.isEmailEditPopupOpen = false;
};

const applyEmailEdit = () => {
  subject.value = editSubject.value;
  body.value = editBody.value;
  activeHistoryId.value = '';
  feedbackText.value = '✏️ 邮件已手动编辑';
  closeEmailEditPopup();
};

const selectHistoryEmail = (historyId: 'reply' | 'outbound') => {
  const historyItem = historyEmailMap[historyId];
  activeHistoryId.value = historyId;
  subject.value = historyItem.subject;
  body.value = historyItem.body;
  feedbackText.value = '📨 已切换到历史邮件';
};
</script>

<template>
  <div v-if="store.isEmailDialogOpen">
    <div id="emailDialog" style="position:fixed;top:48px;left:240px;right:0;bottom:0;background:var(--bg-base);z-index:500;">
      <span class="fixed-close-btn" @click="closeDialog">✕</span>
      <div class="email-dialog-shell">
        <!-- 左侧：联系人信息 + 公司邮件信息 -->
        <div class="email-left-panel">
          <!-- 顶部标题 -->
          <div style="padding:14px 16px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-size:18px;">✉️</span>
              <div style="font-size:14px;font-weight:700;">邮件沟通</div>
            </div>
          </div>

          <!-- 收件人 -->
          <div style="padding:12px 16px;border-bottom:1px solid var(--border-light);">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">收件人</div>
            <div style="display:flex;align-items:center;gap:8px;">
              <div style="width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,var(--blue-primary),var(--cyan-accent));display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:12px;">{{ activeContact.charAt(0) }}</div>
              <div>
              <div style="font-size:12px;font-weight:600;">{{ activeContact }}</div>
              <div style="font-size:10px;color:var(--text-muted);">{{ activeContactEmail }}</div>
              </div>
            </div>
          </div>

          <!-- 相关部门联系人 -->
          <div style="padding:12px 16px;border-bottom:1px solid var(--border-light);">
            <div style="font-size:12px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:6px;"> 相关部门联系人 <span style="font-size:9px;color:var(--text-muted);font-weight:400;">（点击选择收件人）</span></div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              <div :class="['email-contact-item', { selected: activeContact === 'Sarah Chen' }]" @click="selectContact('Sarah Chen')" style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--bg-base);border-radius:6px;cursor:pointer;border:2px solid transparent;transition:all 0.15s;">
                <div style="width:28px;height:28px;border-radius:50%;background:var(--blue-primary);display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;font-weight:700;">S</div>
                <div style="flex:1;">
                  <div style="font-size:11px;font-weight:600;">Sarah Chen</div>
                  <div style="font-size:9px;color:var(--text-muted);">Head of Technology</div>
                </div>
                <span style="font-size:9px;padding:2px 6px;background:var(--green-ok);color:#fff;border-radius:4px;">决策人</span>
              </div>
              <div :class="['email-contact-item', { selected: activeContact === 'James Wilson' }]" @click="selectContact('James Wilson')" style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--bg-base);border-radius:6px;cursor:pointer;border:2px solid transparent;transition:all 0.15s;">
                <div style="width:28px;height:28px;border-radius:50%;background:var(--cyan-accent);display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;font-weight:700;">J</div>
                <div style="flex:1;">
                  <div style="font-size:11px;font-weight:600;">James Wilson</div>
                  <div style="font-size:9px;color:var(--text-muted);">CFO · 预算审批</div>
                </div>
              </div>
              <div :class="['email-contact-item', { selected: activeContact === 'Maria Garcia' }]" @click="selectContact('Maria Garcia')" style="display:flex;align-items:center;gap:8px;padding:6px 8px;background:var(--bg-base);border-radius:6px;cursor:pointer;border:2px solid transparent;transition:all 0.15s;">
                <div style="width:28px;height:28px;border-radius:50%;background:#D97706;display:flex;align-items:center;justify-content:center;color:#fff;font-size:10px;font-weight:700;">M</div>
                <div style="flex:1;">
                  <div style="font-size:11px;font-weight:600;">Maria Garcia</div>
                  <div style="font-size:9px;color:var(--text-muted);">VP Ops · 供应商管理</div>
                </div>
              </div>
            </div>
          </div>

          <!-- 公司邮件信息 -->
          <div style="padding:12px 16px;border-bottom:1px solid var(--border-light);">
            <div style="font-size:12px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:6px;"> 公司邮件信息</div>
            <div style="padding:8px;background:var(--bg-base);border-radius:6px;font-size:11px;line-height:1.6;">
              <div><strong>公司：</strong>GlobalLink Travel Management</div>
              <div><strong>行业：</strong>TMC · 英国伦敦</div>
              <div><strong>规模：</strong>2000+员工</div>
              <div><strong>融资：</strong>Series B $12M（2周前）</div>
            </div>
          </div>

          <!-- 历史邮件 -->
          <div style="padding:12px 16px;flex:1;overflow-y:auto;">
            <div style="font-size:12px;font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:6px;"> 历史邮件</div>
            <div style="display:flex;flex-direction:column;gap:6px;">
              <div
                :class="['email-history-item', { active: activeHistoryId === 'reply' }]"
                @click="selectHistoryEmail('reply')"
                style="padding:8px;background:var(--bg-base);border-radius:6px;border-left:3px solid var(--green-ok);cursor:pointer;transition:all 0.15s;"
              >
                <div style="display:flex;justify-content:space-between;margin-bottom:2px;"><span style="font-size:11px;font-weight:600;color:var(--green-ok);">收到 · 客户回复</span><span style="font-size:9px;color:var(--text-muted);">6/04 14:23</span></div>
                <div style="font-size:10px;color:var(--text-secondary);">"Could you share the coverage list and enterprise pricing?"</div>
              </div>
              <div
                :class="['email-history-item', { active: activeHistoryId === 'outbound' }]"
                @click="selectHistoryEmail('outbound')"
                style="padding:8px;background:var(--bg-base);border-radius:6px;border-left:3px solid var(--blue-primary);cursor:pointer;transition:all 0.15s;"
              >
                <div style="display:flex;justify-content:space-between;margin-bottom:2px;"><span style="font-size:11px;font-weight:600;color:var(--blue-primary);">发出 · 触达邮件</span><span style="font-size:9px;color:var(--text-muted);">6/02 10:30</span></div>
                <div style="font-size:10px;color:var(--text-secondary);">Subject: Managing roaming costs across 8 countries...</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 右侧：邮件编辑区 -->
        <div class="email-right-panel">
          <!-- 顶部工具栏 -->
          <div style="padding:12px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;background:var(--bg-card);">
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="font-size:11px;color:var(--text-muted);">收件人：<strong style="color:var(--text-primary);">{{ activeContact }}</strong></span>
            </div>
            <div style="display:flex;align-items:center;gap:6px;">
              <span style="font-size:10px;padding:3px 8px;background:var(--tuge-gradient);color:#fff;border-radius:6px;font-weight:600;">✨ AI Generated</span>
            </div>
          </div>

          <!-- 主题栏 -->
          <div style="padding:12px 20px;border-bottom:1px solid var(--border-light);background:var(--bg-card);">
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">Subject</div>
            <input type="text" v-model="subject" style="width:100%;border:none;outline:none;font-size:14px;font-weight:600;padding:4px 0;background:transparent;" placeholder="输入邮件主题...">
          </div>

          <!-- 格式化工具栏 -->
          <div style="padding:6px 20px;border-bottom:1px solid var(--border-light);background:var(--bg-card);display:flex;gap:4px;align-items:center;">
            <span style="padding:4px 8px;border-radius:4px;cursor:pointer;font-weight:700;font-size:12px;background:var(--bg-base);transition:background 0.15s;" title="加粗">B</span>
            <span style="padding:4px 8px;border-radius:4px;cursor:pointer;font-style:italic;font-size:12px;background:var(--bg-base);transition:background 0.15s;" title="斜体">I</span>
            <span style="padding:4px 8px;border-radius:4px;cursor:pointer;text-decoration:underline;font-size:12px;background:var(--bg-base);transition:background 0.15s;" title="下划线">U</span>
            <div style="width:1px;height:16px;background:var(--border);margin:0 4px;"></div>
            <span style="padding:4px 8px;border-radius:4px;cursor:pointer;font-size:12px;background:var(--bg-base);transition:background 0.15s;" title="链接">🔗</span>
            <span style="padding:4px 8px;border-radius:4px;cursor:pointer;font-size:12px;background:var(--bg-base);transition:background 0.15s;" title="列表">📋</span>
          </div>

          <!-- AI生成预览 + 编辑区 -->
          <div class="email-preview-stack">
            <!-- AI生成内容预览 -->
            <div class="email-preview-body">
              <div style="position:absolute;top:0;left:0;right:0;height:2px;background:linear-gradient(90deg,var(--blue-primary),var(--cyan-accent),var(--green-ok));background-size:200% 100%;animation:gradientMove 3s linear infinite;"></div>
              <div style="position:absolute;top:12px;right:12px;display:flex;align-items:center;gap:6px;z-index:2;">
                <div style="width:8px;height:8px;border-radius:50%;background:var(--green-ok);animation:pulse-dot 1.5s infinite;"></div>
                <span style="font-size:10px;padding:3px 8px;background:var(--tuge-gradient);color:#fff;border-radius:6px;font-weight:600;">✨ AI</span>
              </div>
              <div v-if="isGenerating" class="email-loading-surface">
                <div style="display:flex;gap:4px;">
                  <div style="width:8px;height:8px;border-radius:50%;background:var(--cyan-accent);animation:pulse-dot 1s infinite 0s;"></div>
                  <div style="width:8px;height:8px;border-radius:50%;background:var(--cyan-accent);animation:pulse-dot 1s infinite 0.2s;"></div>
                  <div style="width:8px;height:8px;border-radius:50%;background:var(--cyan-accent);animation:pulse-dot 1s infinite 0.4s;"></div>
                </div>
                <span style="color:var(--cyan-accent);font-size:13px;font-weight:600;">AI 正在根据你的指令重新生成...</span>
              </div>
              <div v-else class="email-preview-content">
                <div id="emailAIContent" style="position:relative;z-index:1;">{{ body }}</div>
                <div
                  v-if="feedbackText"
                  class="email-feedback-text"
                  style="position:relative;z-index:1;font-size:10px;color:rgba(255,255,255,0.5);"
                >
                  {{ feedbackText }}
                </div>
              </div>
            </div>

            <!-- AI指令输入区 -->
            <div style="padding:12px 20px;border-top:1px solid var(--border);background:var(--bg-card);">
              <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
                <span style="font-size:12px;">✨</span>
                <span style="font-size:11px;font-weight:600;color:var(--blue-primary);">给AI的指令</span>
              </div>
              <div style="display:flex;gap:8px;">
                <input type="text" v-model="prompt" @keyup.enter="regenerate" style="flex:1;border:1px solid var(--border);border-radius:6px;padding:8px 12px;font-size:11px;outline:none;" placeholder="例如：强调GDPR合规、使用更正式的语气、添加ROI数据...">
                <span class="btn-xs primary" @click="regenerate" style="font-size:10px;padding:6px 12px;cursor:pointer;">✨ 重新生成</span>
              </div>
              <div style="display:flex;gap:6px;margin-top:6px;">
                <span class="btn-xs" @click="regenerate" style="font-size:9px;padding:3px 8px;background:var(--bg-base);border:1px solid var(--border);border-radius:12px;cursor:pointer;"> 强调GDPR合规</span>
                <span class="btn-xs" @click="regenerate" style="font-size:9px;padding:3px 8px;background:var(--bg-base);border:1px solid var(--border);border-radius:12px;cursor:pointer;"> 添加ROI数据</span>
                <span class="btn-xs" @click="regenerate" style="font-size:9px;padding:3px 8px;background:var(--bg-base);border:1px solid var(--border);border-radius:12px;cursor:pointer;"> 更正式语气</span>
                <span class="btn-xs" @click="regenerate" style="font-size:9px;padding:3px 8px;background:var(--bg-base);border:1px solid var(--border);border-radius:12px;cursor:pointer;"> 突出多国覆盖</span>
              </div>
            </div>
          </div>

          <!-- 底部操作栏 -->
          <div style="padding:12px 20px;border-top:1px solid var(--border);background:var(--bg-card);display:flex;align-items:center;justify-content:space-between;flex-shrink:0;">
            <div style="display:flex;gap:8px;">
              <span class="btn-xs" style="font-size:11px;cursor:pointer;" @click="emailFeedback('up')">👍 满意</span>
              <span class="btn-xs" style="font-size:11px;cursor:pointer;" @click="emailFeedback('down')">👎 不满意</span>
              <span class="btn-xs" style="font-size:11px;background:var(--blue-light);color:var(--blue-primary);border-color:var(--blue-primary);cursor:pointer;" @click="openEmailEditPopup">✏️ 编辑</span>
            </div>
            <div style="display:flex;gap:8px;">
              <span class="btn-outline" style="padding:8px 16px;font-size:12px;cursor:pointer;" @click="closeDialog">取消</span>
              <span class="btn-primary" style="padding:8px 16px;font-size:12px;cursor:pointer;" @click="send"> 发送邮件</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="store.isEmailEditPopupOpen"
      id="emailEditPopup"
      style="position:fixed;top:50%;left:calc(240px + (100vw - 240px)/2);transform:translate(-50%,-50%);width:560px;max-height:70vh;background:var(--bg-card);border-radius:16px;box-shadow:0 12px 48px rgba(0,0,0,0.2);z-index:600;display:flex;flex-direction:column;overflow:hidden;border:1px solid var(--border);"
    >
      <div style="padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;background:linear-gradient(135deg,#F0F7FF,#ECFDF5);">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="font-size:18px;">✏️</span>
          <div style="font-size:15px;font-weight:700;">编辑邮件</div>
        </div>
        <span style="cursor:pointer;font-size:16px;color:var(--text-muted);padding:4px 8px;border-radius:6px;" @click="closeEmailEditPopup">✕</span>
      </div>
      <div style="padding:16px 20px;flex:1;overflow-y:auto;">
        <div style="margin-bottom:12px;">
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">主题</div>
          <input
            id="editEmailSubject"
            v-model="editSubject"
            type="text"
            style="width:100%;border:1px solid var(--border);border-radius:8px;padding:10px 12px;font-size:13px;outline:none;font-family:inherit;"
          >
        </div>
        <div>
          <div style="font-size:12px;font-weight:600;color:var(--text-muted);margin-bottom:4px;">邮件内容</div>
          <textarea
            id="editEmailBody"
            v-model="editBody"
            style="width:100%;border:1px solid var(--border);border-radius:8px;padding:12px;font-size:13px;outline:none;min-height:280px;resize:vertical;font-family:inherit;line-height:1.8;"
          />
        </div>
      </div>
      <div style="padding:12px 20px;border-top:1px solid var(--border);display:flex;justify-content:flex-end;gap:8px;background:var(--bg-base);">
        <span class="btn-outline" style="padding:8px 20px;font-size:12px;cursor:pointer;" @click="closeEmailEditPopup">取消</span>
        <span class="btn-primary" style="padding:8px 20px;font-size:12px;cursor:pointer;" @click="applyEmailEdit">✓ 应用修改</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Scoped styles are mostly inline or in style.css now to match the original HTML exactly */
.email-contact-item.selected { border-color:var(--blue-primary)!important; background:var(--blue-light)!important; box-shadow:0 0 0 3px rgba(37,99,235,0.1); }
.email-contact-item:hover { border-color:var(--blue-primary); background:var(--blue-light); transform:translateX(2px); }
.email-dialog-shell { display:block; height:100%; overflow:hidden; position:relative; width:100%; }
.email-left-panel { position:absolute; left:0; top:0; bottom:0; width:320px; min-width:320px; max-width:320px; border-right:1px solid var(--border); background:var(--bg-card); overflow-y:auto; display:flex; flex-direction:column; z-index:1; }
.email-right-panel { position:absolute; left:320px; right:0; top:0; bottom:0; width:auto!important; min-width:0; max-width:none; display:flex!important; flex-direction:column!important; overflow:hidden!important; height:auto!important; }
.email-right-panel > div { width:100%; }
.email-preview-stack { flex:1 1 auto; display:flex; flex-direction:column; overflow:hidden; min-height:0; min-width:0; }
.email-preview-body { padding:16px 20px; background:linear-gradient(135deg,#0F172A,#1E293B); position:relative; overflow:auto; flex:1 1 auto; min-height:0; min-width:0; display:flex; flex-direction:column; }
.email-preview-content { display:flex; flex-direction:column; gap:12px; min-height:100%; }
#emailAIContent { display:block; width:100%; flex:1 0 auto; overflow-wrap:break-word!important; word-break:break-word!important; white-space:pre-wrap; color:#E2E8F0; font-size:13px; line-height:1.9; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei','Noto Sans SC',sans-serif; }
.email-feedback-text { margin-top:auto; padding-top:8px; border-top:1px solid rgba(255,255,255,0.08); }
.email-loading-surface { display:flex; align-items:center; justify-content:center; gap:10px; width:100%; min-height:100%; padding:40px 20px; box-sizing:border-box; }
.email-history-item.active { background:var(--blue-light)!important; box-shadow:0 0 0 1px rgba(37,99,235,0.15); }
.email-history-item:hover { background:var(--bg-hover)!important; }
</style>
