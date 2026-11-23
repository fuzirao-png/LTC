<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue';

import { useAppStore } from '../../stores/app';
import { useAuthStore } from '../../stores/auth';
import { regionLabel } from '../utils/labels';

const store = useAppStore();
const auth = useAuthStore();
const displayName = computed(() => auth.currentUser?.name || auth.currentUser?.username || '当前用户');
const isStrategic = computed(() => auth.currentUser?.accountType !== 'sales');
const displayRole = computed(() => {
  const user = auth.currentUser;
  if (!user) return '账号信息';
  return user.accountType === 'sales'
    ? `${regionLabel(user.regionCode)}区域-${user.salesTier || '未分级'}等级`
    : '战略负责人';
});
const roleDetail = computed(() => isStrategic.value ? '公司战略管理' : 'L5 · 日本市场负责人');
const departmentName = computed(() => isStrategic.value ? '总经办' : '国际销售部');
const departmentDetail = computed(() => isStrategic.value ? '战略管理 · 决策中心' : '亚太区 · 日本组');
const closeProfile = () => {
  store.isProfileOpen = false;
};
const closeOnEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && store.isProfileOpen) closeProfile();
};
onMounted(() => document.addEventListener('keydown', closeOnEscape));
onUnmounted(() => document.removeEventListener('keydown', closeOnEscape));
</script>

<template>
  <div v-if="store.isProfileOpen" id="userProfilePopup" class="user-profile-popup" style="background:var(--bg-base);padding:24px;" @click.self="closeProfile">
    <div style="max-width:1200px;margin:0 auto;position:relative;top:20px;padding-bottom: 40px;">
      <!-- 顶部标题区 -->
      <div style="margin-bottom:20px;">
        <div style="font-size:11px;color:var(--blue-primary);font-weight:600;margin-bottom:4px;">途鸽科技工作台</div>
        <div style="font-size:28px;font-weight:800;background:var(--tuge-gradient);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{{ displayName }}，欢迎回来</div>
        <div style="font-size:12px;color:var(--text-muted);margin-top:4px;">下方展示基础环境信息，下方按行业为你整理今日值得关注的时讯。</div>
      </div>

      <!-- 环境信息卡片 -->
      <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px;">
        <div style="padding:16px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">当前天气</div>
          <div style="font-size:14px;font-weight:700;">晴朗 微风</div>
        </div>
        <div style="padding:16px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">空气湿度</div>
          <div style="font-size:14px;font-weight:700;">68%</div>
        </div>
        <div style="padding:16px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">体感温度</div>
          <div style="font-size:14px;font-weight:700;">27°C</div>
        </div>
        <div style="padding:16px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">更新时间</div>
          <div style="font-size:14px;font-weight:700;">6/9 18:14:56 更新</div>
        </div>
      </div>

      <!-- 个人信息卡片：入职时间、岗位、部门 -->
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px;">
        <div style="padding:16px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);border-left:4px solid var(--blue-primary);">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">入职时间</div>
          <div style="font-size:14px;font-weight:700;">2024年6月</div>
          <div style="font-size:11px;color:var(--text-secondary);margin-top:2px;">已入职2年1个月</div>
        </div>
        <div style="padding:16px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);border-left:4px solid var(--green-ok);">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">岗位</div>
          <div style="font-size:14px;font-weight:700;">{{ displayRole }}</div>
          <div style="font-size:11px;color:var(--text-secondary);margin-top:2px;">{{ roleDetail }}</div>
        </div>
        <div style="padding:16px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);border-left:4px solid var(--cyan-accent);">
          <div style="font-size:11px;color:var(--text-muted);margin-bottom:4px;">部门</div>
          <div style="font-size:14px;font-weight:700;">{{ departmentName }}</div>
          <div style="font-size:11px;color:var(--text-secondary);margin-top:2px;">{{ departmentDetail }}</div>
        </div>
      </div>

      <!-- 双列资讯卡片 -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
        <!-- 左列：物联网行业时讯 -->
        <div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
            <div style="font-size:16px;font-weight:700;">物联网行业时讯</div>
            <div style="font-size:10px;color:var(--text-muted);">连接、感知与行业落地</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:10px;">
            <div style="padding:14px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:10px;padding:2px 8px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">平台连接</span>
                <span style="font-size:10px;color:var(--text-muted);">09:20</span>
              </div>
              <div style="font-size:13px;font-weight:600;margin-bottom:6px;">工业园区设备接入需求升温，边缘采集与统一管理成为升级重点</div>
              <div style="font-size:11px;color:var(--text-secondary);line-height:1.5;">制造、仓储与能源场景正在加快接入改造，企业更关注低成本部署、稳定联网和数据可视化能力。</div>
            </div>
            <div style="padding:14px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:10px;padding:2px 8px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">智慧城市</span>
                <span style="font-size:10px;color:var(--text-muted);">10:05</span>
              </div>
              <div style="font-size:13px;font-weight:600;margin-bottom:6px;">城市感知项目从单点试验转向联动治理，视频与传感协同成为主流</div>
              <div style="font-size:11px;color:var(--text-secondary);line-height:1.5;">路侧设备、安防告警和环境监测的联动能力持续增强，平台侧更强调跨系统集成与实时响应。</div>
            </div>
            <div style="padding:14px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:10px;padding:2px 8px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">车联网</span>
                <span style="font-size:10px;color:var(--text-muted);">11:30</span>
              </div>
              <div style="font-size:13px;font-weight:600;margin-bottom:6px;">车队运营正在加码终端在线率与远程诊断，运维数字化需求明显上升</div>
              <div style="font-size:11px;color:var(--text-secondary);line-height:1.5;">物流与出行企业开始更看重设备在线稳定性、位置精度和异常预警，以降低调度与维护成本。</div>
            </div>
          </div>
        </div>

        <!-- 右列：日本销售市场资讯 -->
        <div>
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
            <div style="font-size:16px;font-weight:700;">日本销售市场资讯</div>
            <div style="font-size:10px;color:var(--text-muted);">TMC、OTA与企业差旅</div>
          </div>
          <div style="display:flex;flex-direction:column;gap:10px;">
            <div style="padding:14px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:10px;padding:2px 8px;background:#ECFDF5;color:var(--green-ok);border-radius:4px;">市场动态</span>
                <span style="font-size:10px;color:var(--text-muted);">09:30</span>
              </div>
              <div style="font-size:13px;font-weight:600;margin-bottom:6px;">日本企业差旅市场Q2同比增长18%，TMC数字化转型加速</div>
              <div style="font-size:11px;color:var(--text-secondary);line-height:1.5;">受日元贬值影响，日本企业海外差旅需求持续增长，TMC服务商加速部署数字化管理工具以提升效率。</div>
            </div>
            <div style="padding:14px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:10px;padding:2px 8px;background:var(--blue-light);color:var(--blue-primary);border-radius:4px;">行业趋势</span>
                <span style="font-size:10px;color:var(--text-muted);">10:15</span>
              </div>
              <div style="font-size:13px;font-weight:600;margin-bottom:6px;">eSIM企业渗透率在日本市场从12%提升至22%，成本优势明显</div>
              <div style="font-size:11px;color:var(--text-secondary);line-height:1.5;">日本企业对通讯成本控制需求强烈，eSIM方案平均可节省35%国际漫游费用，大型TMC客户采购意愿显著提升。</div>
            </div>
            <div style="padding:14px;background:var(--bg-card);border-radius:var(--radius);border:1px solid var(--border);box-shadow:var(--shadow-sm);">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <span style="font-size:10px;padding:2px 8px;background:#FEF3C7;color:#D97706;border-radius:4px;">竞品情报</span>
                <span style="font-size:10px;color:var(--text-muted);">11:00</span>
              </div>
              <div style="font-size:13px;font-weight:600;margin-bottom:6px;">竞品SoftBank企业通讯方案降价15%，需关注价格战风险</div>
              <div style="font-size:11px;color:var(--text-secondary);line-height:1.5;">SoftBank近期针对TMC客户推出优惠套餐，建议在方案中强化多国覆盖和合规性差异化优势。</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 用户资料弹窗 - 途鸽科技工作台风格 */
.user-profile-popup{position:fixed;top:48px;left:240px;right:0;bottom:0;background:var(--bg-base);z-index:500;overflow-y:auto;}
.fixed-close-btn{position:sticky;top:0;z-index:2;display:grid;width:36px;height:36px;margin-left:auto;place-items:center;color:var(--text-main);cursor:pointer;background:var(--bg-card);border:1px solid var(--border);border-radius:6px;box-shadow:var(--shadow-sm);}
</style>
