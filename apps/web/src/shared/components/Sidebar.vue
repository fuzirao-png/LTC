<script setup lang="ts">
import { computed, ref } from 'vue';
import { useAppStore } from '../../stores/app';

const store = useAppStore();
const gearMenuOpen = ref(false);
const isSalesProfileActive = computed(() => store.currentRole === 'sales' && store.isProfileOpen);
const isCeoProfileActive = computed(() => store.currentRole === 'ceo' && store.isProfileOpen);

const isNavItemActive = (view: string) => !store.isProfileOpen && store.currentView === view;
const isNavTabActive = (tabId: string) => !store.isProfileOpen && store.activeNavTab === tabId;

const switchNavTab = (tabId: string) => {
  store.activeNavTab = tabId;
};

const toggleRoleSelector = () => {
  store.roleSelectorOpen = !store.roleSelectorOpen;
};

const toggleGearMenu = (event: Event) => {
  event.stopPropagation();
  gearMenuOpen.value = !gearMenuOpen.value;
};

const selectRole = (role: 'sales' | 'ceo') => {
  store.setRole(role);
  store.roleSelectorOpen = false;
};

const alertMsg = (msg: string) => {
  alert(msg);
};
</script>

<template>
  <!-- Sales Sidebar -->
  <aside v-if="store.currentRole === 'sales'" class="sidebar">
    <div class="logo">
      <span class="icon">◆</span> TGT AI Native
    </div>

    <div :class="['user-switch', { active: isSalesProfileActive }]">
      <div style="position:relative;" @click="store.toggleProfile()">
        <div class="avatar">{{ store.user.avatar }}</div>
        <div class="nav-dot green" style="position:absolute;bottom:-2px;right:-2px;width:12px;height:12px;border:2px solid #0F172A;"></div>
      </div>
      <div class="info" @click="toggleRoleSelector">
        <div class="name">{{ store.user.name }}</div>
        <div class="role">{{ store.user.role }}</div>
      </div>
      <!-- Role Selector -->
      <div :class="['role-selector', { open: store.roleSelectorOpen }]" id="roleSelector">
        <div class="role-option active" @click.stop="selectRole('sales')"> 李明 · 日本销售</div>
        <div class="role-option" @click.stop="selectRole('ceo')"> 张总 · 战略视角</div>
      </div>
    </div>

    <div class="nav-section static">
      <div class="nav-group-title">总览</div>
      <div :class="['nav-item', { active: isNavItemActive('dashboard') }]" @click="store.setView('dashboard')">
        <span class="nav-icon"></span> 我的业绩
      </div>
    </div>

    <div class="nav-tab-bar">
      <div :class="['nav-tab', { active: isNavTabActive('tab-ai-staff') }]" @click="switchNavTab('tab-ai-staff')">AI agent</div>
      <div :class="['nav-tab', { active: isNavTabActive('tab-database') }]" @click="switchNavTab('tab-database')">数据库</div>
      <div class="nav-tab" style="color:var(--text-muted);">更多功能</div>
    </div>

    <div v-if="store.activeNavTab === 'tab-ai-staff'" class="nav-tab-content active">
      <div :class="['nav-item', { active: isNavItemActive('lead-assign') }]" @click="store.setView('lead-assign')">
        <span class="nav-icon"></span> 线索分配
        <span style="margin-left:auto;display:flex;gap:3px;align-items:center;">
          <span class="nav-dot red"></span>
        </span>
      </div>
      <div :class="['nav-item', { active: isNavItemActive('customer-mgmt') }]" @click="store.setView('customer-mgmt')">
        <span class="nav-icon"></span> 客户管理
        <span style="margin-left:auto;display:flex;gap:3px;align-items:center;">
          <span class="nav-dot yellow"></span>
        </span>
      </div>
      <div :class="['nav-item', { active: isNavItemActive('customer-analysis') }]" @click="store.setView('customer-analysis')">
        <span class="nav-icon"></span> 客户分析
        <span style="margin-left:auto;display:flex;gap:3px;align-items:center;">
          <span class="nav-dot green"></span>
        </span>
      </div>
    </div>

    <div v-else-if="store.activeNavTab === 'tab-database'" class="nav-tab-content active">
      <div :class="['nav-item', { active: isNavItemActive('db-cases') }]" @click="store.setView('db-cases')">
        <span class="nav-icon"></span> 案例库<span class="badge green">23</span>
      </div>
      <div :class="['nav-item', { active: isNavItemActive('db-scripts') }]" @click="store.setView('db-scripts')">
        <span class="nav-icon"></span> 话术库<span class="badge info">28</span>
      </div>
    </div>

    <div class="sidebar-footer" style="position:relative;">
      <div style="display:flex;align-items:center;">
        <span class="gear-btn" @click="toggleGearMenu" style="font-size:18px;cursor:pointer;">⚙</span>
      </div>
      <div v-if="gearMenuOpen" class="gear-menu" style="position:absolute;bottom:40px;left:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,0.15);width:160px;z-index:200;">
        <div class="gear-item" @click="gearMenuOpen = false; alertMsg('登录页面 · 演示模式')">登录</div>
        <div class="gear-item" @click="gearMenuOpen = false; alertMsg('安全设置 · 演示模式')">安全</div>
        <div class="gear-item" @click="gearMenuOpen = false; alertMsg('Token用量 · 演示模式')">Token 用量</div>
        <div class="gear-item" @click="gearMenuOpen = false; alertMsg('反馈与帮助 · 演示模式')">反馈 &amp; 帮助</div>
      </div>
    </div>
  </aside>

  <!-- CEO Sidebar -->
  <aside v-else class="sidebar ceo-sidebar" id="ceoSidebar">
    <div class="logo">
      <span class="icon">◆</span> TGT AI Native
      <div class="status">战略视角</div>
    </div>

    <div :class="['user-switch', { active: isCeoProfileActive }]" @click="toggleRoleSelector">
      <div class="avatar" style="background:linear-gradient(135deg,#1E40AF,#7C3AED);">张</div>
      <div class="info">
        <div class="name">张总</div>
        <div class="role">战略决策人</div>
      </div>
      <!-- CEO Role Selector -->
      <div :class="['role-selector', { open: store.roleSelectorOpen }]" id="ceoRoleSelector">
        <div class="role-option" @click.stop="selectRole('sales')"> 李明 · 日本销售</div>
        <div class="role-option active" @click.stop="selectRole('ceo')"> 张总 · 战略视角</div>
      </div>
    </div>

    <div class="nav-section static">
      <div class="nav-group-title">总览</div>
      <div :class="['nav-item', { active: isNavItemActive('ceo-dashboard') }]" @click="store.setView('ceo-dashboard')">
        <span class="nav-icon"></span> 战略驾驶舱
      </div>
    </div>

    <div class="nav-tab-bar">
      <div :class="['nav-tab', { active: isNavTabActive('ceo-tab-agents') }]" @click="switchNavTab('ceo-tab-agents')">Agent流水线</div>
      <div :class="['nav-tab', { active: isNavTabActive('ceo-tab-data') }]" @click="switchNavTab('ceo-tab-data')">数据总览</div>
    </div>

    <div v-if="store.activeNavTab === 'ceo-tab-agents'" class="nav-tab-content active">
      <div :class="['nav-item', { active: isNavItemActive('ceo-lead-collect') }]" @click="store.setView('ceo-lead-collect')">
        <span class="nav-icon"></span> 线索收集Agent
      </div>
      <div :class="['nav-item', { active: isNavItemActive('ceo-lead-analyze') }]" @click="store.setView('ceo-lead-analyze')">
        <span class="nav-icon"></span> 线索分析Agent
      </div>
      <div :class="['nav-item', { active: isNavItemActive('ceo-lead-assign') }]" @click="store.setView('ceo-lead-assign')">
        <span class="nav-icon"></span> 线索分配
      </div>
    </div>

    <div v-else-if="store.activeNavTab === 'ceo-tab-data'" class="nav-tab-content active">
      <div :class="['nav-item', { active: isNavItemActive('ceo-team') }]" @click="store.setView('ceo-team')">
        <span class="nav-icon"></span> 销售团队
      </div>
      <div :class="['nav-item', { active: isNavItemActive('ceo-pipeline') }]" @click="store.setView('ceo-pipeline')">
        <span class="nav-icon"></span> 全局Pipeline
      </div>
    </div>

    <div class="sidebar-footer" style="position:relative;">
      <div style="display:flex;align-items:center;">
        <span class="gear-btn" @click="toggleGearMenu" style="font-size:18px;cursor:pointer;">⚙</span>
      </div>
      <div v-if="gearMenuOpen" class="gear-menu" style="position:absolute;bottom:40px;left:16px;background:var(--bg-card);border:1px solid var(--border);border-radius:8px;box-shadow:0 10px 30px rgba(0,0,0,0.15);width:160px;z-index:200;color:var(--text-primary);">
        <div class="gear-item" @click="gearMenuOpen = false; alertMsg('登录页面 · 演示模式')">登录</div>
        <div class="gear-item" @click="gearMenuOpen = false; alertMsg('Token用量 · 演示模式')">Token 用量</div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 240px;
  min-width: 240px;
  background: linear-gradient(180deg, #EAF4FF 0%, #D8EAFE 100%);
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(37,99,235,0.18);
  height: 100vh;
  overflow-y: auto;
  position: fixed;
  top: 0;
  left: 0;
  z-index: 200;
}

.ceo-sidebar {
  background: linear-gradient(180deg, #1E293B 0%, #0F172A 100%);
  color: #fff;
}

.ceo-sidebar .logo, .ceo-sidebar .nav-group-title, .ceo-sidebar .nav-item {
  color: #CBD5E1;
}

.ceo-sidebar .nav-item:hover {
  background: rgba(255,255,255,0.1);
  color: #fff;
}

.ceo-sidebar .nav-item.active {
  background: var(--tuge-gradient);
  color: #fff;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  font-size: 14px;
  font-weight: 700;
  color: var(--blue-dark);
  border-bottom: 1px solid rgba(37,99,235,0.12);
}

.user-switch {
  padding: 10px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  border-bottom: 1px solid rgba(37,99,235,0.12);
  cursor: pointer;
  transition: background 0.2s;
  position: relative;
}

.user-switch:hover {
  background: rgba(37,99,235,0.06);
}

.user-switch.active {
  background: rgba(37,99,235,0.1);
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--tuge-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  box-shadow: 0 0 12px rgba(37,99,235,0.4);
}

.info {
  flex: 1;
}

.name { font-weight: 600; font-size: 13px; }
.role { font-size: 11px; color: var(--text-secondary); }

.nav-section { padding: 8px 0; border-bottom: 1px solid rgba(37,99,235,0.1); }
.nav-group-title { font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: rgba(29,78,216,0.55); padding: 8px 16px 4px; font-weight: 700; }

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 16px;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 13px;
  transition: all 0.2s;
  border-radius: 8px;
  margin: 2px 8px;
}

.nav-item:hover { background: rgba(37,99,235,0.08); color: var(--blue-dark); }
.nav-item.active { background: var(--tuge-gradient); color: #fff; font-weight: 600; box-shadow: 0 4px 12px rgba(37,99,235,0.3); }

.nav-tab-bar { display: flex; border-bottom: 1px solid rgba(37,99,235,0.12); }
.nav-tab { flex: 1; text-align: center; padding: 8px 4px; font-size: 11px; cursor: pointer; color: rgba(29,78,216,0.55); border-bottom: 2px solid transparent; transition: all 0.2s; }
.nav-tab.active { color: var(--blue-primary); border-bottom-color: var(--blue-primary); font-weight: 700; }

.sidebar-footer { margin-top: auto; padding: 12px 16px; border-top: 1px solid rgba(37,99,235,0.1); }
.gear-btn { font-size: 18px; cursor: pointer; }

.nav-dot { width: 8px; height: 8px; border-radius: 50%; }
.nav-dot.red { background: var(--red-badge); }
.nav-dot.yellow { background: var(--orange-warn); }
.nav-dot.green { background: var(--green-ok); }

.role-selector {
  display: none;
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
  z-index: 300;
  padding: 4px;
}
.role-selector.open { display: block; }
.role-option { padding: 8px 12px; cursor: pointer; border-radius: 6px; font-size: 12px; display: flex; align-items: center; gap: 8px; color: var(--text-primary); }
.role-option:hover { background: var(--bg-hover); }
.role-option.active { background: var(--blue-light); color: var(--blue-primary); }

.badge { margin-left: auto; font-size: 10px; padding: 1px 7px; border-radius: 10px; font-weight: 600; }
.badge.green { background: rgba(16,185,129,0.2); color: var(--green-ok); }
.badge.info { background: rgba(37,99,235,0.12); color: var(--blue-primary); }

.gear-item {
  padding: 8px 14px;
  cursor: pointer;
  font-size: 12px;
  border-bottom: 1px solid var(--border-light);
  color: var(--text-primary);
}
.gear-item:last-child { border-bottom: none; }
.gear-item:hover { background: var(--bg-hover); }
</style>
