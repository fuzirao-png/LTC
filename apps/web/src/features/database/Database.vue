<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRoute } from 'vue-router';
import { knowledgeApi, type KnowledgeItem } from '../../services/knowledgeApi';
import { getApiErrorMessage } from '../../services/http';

const route = useRoute();
const isCases = computed(() => route.path === '/db-cases');
const scriptTypeFilter = ref('all');
const scriptScenarioFilter = ref('all');
const knowledgeQuery = ref('');
const knowledgeLoading = ref(false);
const knowledgeError = ref('');
const knowledgeItems = ref<KnowledgeItem[]>([]);
const knowledgeSearchedQuery = ref('');

const searchKnowledge = async () => {
  const query = knowledgeQuery.value.trim();
  if (!query || knowledgeLoading.value) return;
  knowledgeLoading.value = true;
  knowledgeError.value = '';
  knowledgeSearchedQuery.value = query;
  try {
    const result = await knowledgeApi.search(query);
    knowledgeItems.value = result.data.items;
  } catch (error) {
    knowledgeItems.value = [];
    knowledgeError.value = getApiErrorMessage(error, '知识库暂时不可用');
  } finally {
    knowledgeLoading.value = false;
  }
};

const cases = [
  {
    id: 'C023',
    name: 'Sakura Travel Corp',
    date: '2026.05.28',
    industry: '差旅平台',
    size: '200-500人',
    region: '日本',
    amount: '$2,400/年',
    cycle: '21天',
    actions: '融资信号触发、成本透明化话术、两轮邮件后会议成交',
    successFactors: '决策人明确、预算窗口打开、合规诉求强',
    version: 'Good Case v1.2',
  },
  {
    id: 'C022',
    name: 'Kansai Mobility Services',
    date: '2026.05.14',
    industry: '企业服务',
    size: '500-1000人',
    region: '日本',
    amount: '$4,800/年',
    cycle: '28天',
    actions: '先补决策链，再用企业管理能力推进采购',
    successFactors: '多人决策链完整、试点范围清晰',
    version: 'Good Case v1.1',
  },
  {
    id: 'C021',
    name: 'Seoul Business Trip',
    date: '2026.04.30',
    industry: '商旅 OTA',
    size: '100-200人',
    region: '东亚',
    amount: '$1,900/年',
    cycle: '18天',
    actions: '用亚太覆盖和开通链路作为主卖点',
    successFactors: '使用场景明确、采购阻力低',
    version: 'Good Case v1.0',
  },
];

const scripts = [
  { id: 'S007', name: '个性化主题行邮件', type: '邮件', scenario: '首次触达', replyRate: '16.7%', version: 'v1.3', recommended: true },
  { id: 'S008', name: '行业洞察 LinkedIn', type: 'LinkedIn', scenario: '亚太区客户', replyRate: '12.1%', version: 'v1.1', recommended: true },
  { id: 'S009', name: '融资信号跟进邮件', type: '邮件', scenario: '有融资信号', replyRate: '14.2%', version: 'v1.0', recommended: true },
  { id: 'S010', name: '二次触达邮件', type: '邮件', scenario: '未回复客户', replyRate: '8.5%', version: 'v1.0' },
  { id: 'S011', name: '电话开场白', type: '电话', scenario: '高意向客户', replyRate: '22%', version: 'v1.0' },
];

const scriptTypeOptions = [...new Set(scripts.map((item) => item.type))];
const scriptScenarioOptions = [...new Set(scripts.map((item) => item.scenario))];
const filteredScripts = computed(() => scripts.filter((item) => (
  (scriptTypeFilter.value === 'all' || item.type === scriptTypeFilter.value)
  && (scriptScenarioFilter.value === 'all' || item.scenario === scriptScenarioFilter.value)
)));
</script>

<template>
  <div class="content-main legacy-database">
    <section class="panel knowledge-search-panel">
      <div class="panel-header"><span>搜索 WeKnora 知识</span><small>只读检索，不修改 LTC 业务数据</small></div>
      <div class="panel-body knowledge-search-form">
        <input v-model="knowledgeQuery" class="knowledge-search-input" type="search" placeholder="输入客户场景、产品问题或销售话术" @keyup.enter="searchKnowledge" />
        <button class="btn-xs primary" type="button" :disabled="knowledgeLoading || !knowledgeQuery.trim()" @click="searchKnowledge">{{ knowledgeLoading ? '检索中…' : '检索' }}</button>
      </div>
      <div v-if="knowledgeError" class="knowledge-message error">{{ knowledgeError }}</div>
      <div v-else-if="knowledgeSearchedQuery && !knowledgeLoading && !knowledgeItems.length" class="knowledge-message">未找到与“{{ knowledgeSearchedQuery }}”相关的知识片段</div>
      <div v-if="knowledgeItems.length" class="knowledge-results">
        <article v-for="item in knowledgeItems" :key="item.id" class="knowledge-result">
          <div class="knowledge-result-head">
            <strong>{{ item.knowledge_title || item.knowledge_filename || '知识片段' }}</strong>
            <span v-if="item.score !== null && item.score !== undefined">相似度 {{ Math.round(item.score * 100) }}%</span>
          </div>
          <p>{{ item.content }}</p>
          <small>{{ item.knowledge_filename || item.knowledge_source || 'WeKnora' }}</small>
        </article>
      </div>
    </section>
    <template v-if="isCases">
      <div class="dashboard-title-row">
        <div>
          <div class="dashboard-title">案例库</div>
          <div class="dashboard-subtitle">{{ cases.length }}条案例 · 个人客户沉淀</div>
        </div>
      </div>
      <section class="panel">
        <div class="panel-header"><span>最新案例</span></div>
        <div class="panel-body no-padding">
          <article v-for="item in cases" :key="item.id" class="case-item">
            <div class="case-head">
              <span class="case-status">已成交</span>
              <strong>{{ item.name }}</strong>
              <small>{{ item.date }}</small>
            </div>
            <div class="case-body">
              <p><strong>行业：</strong>{{ item.industry }} · <strong>规模：</strong>{{ item.size }} · <strong>区域：</strong>{{ item.region }}</p>
              <p><strong>成交金额：</strong>{{ item.amount }} · <strong>成单周期：</strong>{{ item.cycle }}</p>
              <p><strong>关键动作：</strong>{{ item.actions }}</p>
              <p><strong>成功因素：</strong>{{ item.successFactors }}</p>
            </div>
            <div class="case-tags">
              <span>{{ item.version }}</span>
              <span>{{ item.amount }}</span>
            </div>
          </article>
        </div>
      </section>
    </template>

    <template v-else>
      <div class="dashboard-title-row">
        <div>
          <div class="dashboard-title">话术库</div>
          <div class="dashboard-subtitle">{{ scripts.length }}条有效话术模板 · 持续从 goodcase 中沉淀</div>
        </div>
      </div>
      <section class="panel">
        <div class="panel-header"><span>话术列表</span></div>
        <div class="panel-body no-padding">
          <table class="matrix-table">
            <thead>
              <tr>
                <th>编号</th>
                <th>话术名称</th>
                <th><label class="table-header-filter"><span>类型</span><select v-model="scriptTypeFilter" aria-label="话术类型"><option value="all">全部</option><option v-for="type in scriptTypeOptions" :key="type" :value="type">{{ type }}</option></select></label></th>
                <th><label class="table-header-filter"><span>适用场景</span><select v-model="scriptScenarioFilter" aria-label="话术适用场景"><option value="all">全部</option><option v-for="scenario in scriptScenarioOptions" :key="scenario" :value="scenario">{{ scenario }}</option></select></label></th>
                <th>回复率</th>
                <th>版本</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredScripts" :key="item.id">
                <td>{{ item.id }}</td>
                <td class="customer-name">{{ item.name }}</td>
                <td>{{ item.type }}</td>
                <td>{{ item.scenario }}</td>
                <td><span :class="['stage-text', item.recommended ? 'green' : 'amber']">{{ item.replyRate }}</span></td>
                <td>{{ item.version }}</td>
                <td><button :class="['btn-xs', { primary: item.recommended }]" type="button">使用</button></td>
              </tr>
              <tr v-if="!filteredScripts.length"><td colspan="7" class="table-empty">没有符合当前筛选条件的话术</td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.table-header-filter { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
.table-header-filter select { max-width: 130px; padding: 3px 5px; border: 1px solid var(--border); border-radius: 5px; background: #fff; color: var(--text-primary); font-size: 10px; cursor: pointer; }
.table-empty { padding: 24px !important; color: var(--text-muted); text-align: center; }
.knowledge-search-form { display: flex; align-items: center; gap: 10px; }
.knowledge-search-input { flex: 1; min-width: 0; border: 1px solid var(--border); border-radius: 5px; padding: 9px 11px; background: #fff; color: var(--text-primary); font: inherit; }
.knowledge-message { padding: 0 16px 16px; color: var(--text-muted); font-size: 12px; }
.knowledge-message.error { color: #b42318; }
.knowledge-results { display: grid; gap: 10px; padding: 0 16px 16px; }
.knowledge-result { border-top: 1px solid var(--border); padding-top: 10px; }
.knowledge-result-head { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
.knowledge-result-head span, .knowledge-result small { color: var(--text-muted); font-size: 11px; }
.knowledge-result p { margin: 7px 0 5px; line-height: 1.6; white-space: pre-wrap; font-size: 13px; }
@media (max-width: 560px) { .knowledge-search-form { align-items: stretch; flex-direction: column; } .knowledge-search-form .btn-xs { width: 100%; } }
</style>
