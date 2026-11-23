<script setup lang="ts">
import { useAppStore } from '../../stores/app';

const store = useAppStore();
</script>

<template>
  <div class="content-main">
    <!-- CEO Dashboard -->
    <div v-if="store.currentView === 'ceo-dashboard'">
      <div style="padding:16px 20px;max-width:1400px;margin:0 auto;">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
          <div><div style="font-size:18px;font-weight:700;"> 张总 · 战略驾驶舱</div><div style="font-size:12px;color:var(--text-muted);">线索收集→线索分析→线索分配 全链路总览</div></div>
        </div>

        <!-- 核心指标 -->
        <div class="metric-cards" style="margin-bottom:14px;">
          <div class="metric-card"><div class="metric-label">本月线索总量</div><div class="metric-val" style="color:var(--blue-primary);">1,247</div><div class="metric-sub">线索收集Agent产出</div></div>
          <div class="metric-card"><div class="metric-label">分析完成</div><div class="metric-val">892</div><div class="metric-sub">线索分析Agent处理</div></div>
          <div class="metric-card"><div class="metric-label">已分配到人</div><div class="metric-val" style="color:var(--green-ok);">156</div><div class="metric-sub">线索分配分配</div></div>
          <div class="metric-card"><div class="metric-label">本月成交额</div><div class="metric-val" style="color:var(--green-ok);">$42,800</div><div class="metric-sub">目标 $80,000 · 53%</div></div>
        </div>

        <!-- 流水线全景 -->
        <div class="panel" style="margin-bottom:14px;">
          <div class="panel-header"><span> Agent流水线全景 <span style="font-size:10px;color:var(--text-muted);">谁在什么阶段做什么事情</span></span></div>
          <div class="panel-body">
            <div style="display:flex;align-items:stretch;gap:12px;">
              <!-- 线索收集 -->
              <div style="flex:1;padding:14px;background:var(--blue-light);border-radius:8px;border-top:3px solid var(--blue-primary);">
                <div style="font-weight:700;font-size:13px;margin-bottom:8px;"> 线索收集Agent</div>
                <div style="font-size:11px;color:var(--text-secondary);line-height:1.6;margin-bottom:8px;">
                  <strong>职责：</strong>从多渠道主动发现潜在客户<br>
                  <strong>渠道：</strong>B端 · C端 · GEO · 手动上传<br>
                  <strong>产出：</strong>原始线索 + 基础信息
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;">
                  <div style="padding:6px;background:var(--bg-card);border-radius:4px;text-align:center;">
                    <div style="font-weight:800;font-size:16px;color:var(--blue-primary);">1,247</div>
                    <div style="font-size:10px;color:var(--text-muted);">本月发现</div>
                  </div>
                  <div style="padding:6px;background:var(--bg-card);border-radius:4px;text-align:center;">
                    <div style="font-weight:800;font-size:16px;color:var(--blue-primary);">38</div>
                    <div style="font-size:10px;color:var(--text-muted);">今日新增</div>
                  </div>
                </div>
                <div style="margin-top:8px;font-size:10px;color:var(--blue-primary);cursor:pointer;" @click="store.setView('ceo-lead-collect')">查看详情 →</div>
              </div>

              <div style="display:flex;align-items:center;font-size:24px;color:var(--text-muted);">→</div>

              <!-- 线索分析 -->
              <div style="flex:1;padding:14px;background:#F0F9FF;border-radius:8px;border-top:3px solid var(--cyan-accent);">
                <div style="font-weight:700;font-size:13px;margin-bottom:8px;"> 线索分析Agent</div>
                <div style="font-size:11px;color:var(--text-secondary);line-height:1.6;margin-bottom:8px;">
                  <strong>职责：</strong>对线索进行评分、富化、分类<br>
                  <strong>维度：</strong>7维ICP评分 · 融资信号 · 招聘信号<br>
                  <strong>产出：</strong>评分后的线索 + 分类标签
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;">
                  <div style="padding:6px;background:var(--bg-card);border-radius:4px;text-align:center;">
                    <div style="font-weight:800;font-size:16px;color:var(--cyan-accent);">892</div>
                    <div style="font-size:10px;color:var(--text-muted);">已分析</div>
                  </div>
                  <div style="padding:6px;background:var(--bg-card);border-radius:4px;text-align:center;">
                    <div style="font-weight:800;font-size:16px;color:var(--cyan-accent);">91%</div>
                    <div style="font-size:10px;color:var(--text-muted);">准确率</div>
                  </div>
                </div>
                <div style="margin-top:8px;font-size:10px;color:var(--cyan-accent);cursor:pointer;" @click="store.setView('ceo-lead-analyze')">查看详情 →</div>
              </div>

              <div style="display:flex;align-items:center;font-size:24px;color:var(--text-muted);">→</div>

              <!-- 线索分配 -->
              <div style="flex:1;padding:14px;background:#ECFDF5;border-radius:8px;border-top:3px solid var(--green-ok);">
                <div style="font-weight:700;font-size:13px;margin-bottom:8px;"> 线索分配</div>
                <div style="font-size:11px;color:var(--text-secondary);line-height:1.6;margin-bottom:8px;">
                  <strong>职责：</strong>按地域/类型将线索分配给销售<br>
                  <strong>规则：</strong>A类→资深销售 · B类→按地域分配<br>
                  <strong>产出：</strong>人机断点 → 销售直接跟进
                </div>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px;">
                  <div style="padding:6px;background:var(--bg-card);border-radius:4px;text-align:center;">
                    <div style="font-weight:800;font-size:16px;color:var(--green-ok);">156</div>
                    <div style="font-size:10px;color:var(--text-muted);">已分配</div>
                  </div>
                  <div style="padding:6px;background:var(--bg-card);border-radius:4px;text-align:center;">
                    <div style="font-weight:800;font-size:16px;color:var(--green-ok);">92%</div>
                    <div style="font-size:10px;color:var(--text-muted);">跟进率</div>
                  </div>
                </div>
                <div style="margin-top:8px;font-size:10px;color:var(--green-ok);cursor:pointer;" @click="store.setView('ceo-lead-assign')">查看详情 →</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 销售团队 + 全局Pipeline -->
        <div class="row-2" style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
          <div class="panel"><div class="panel-header"><span> 销售团队概览</span><span class="btn-xs" @click="store.setView('ceo-team')">详情</span></div><div class="panel-body" style="padding:0;">
            <table class="matrix-table"><thead><tr><th>姓名</th><th>区域</th><th>线索</th><th>转化率</th><th>成交额</th><th>状态</th></tr></thead><tbody>
              <tr><td>张伟</td><td>北美</td><td>23</td><td>15.2%</td><td>$8,400</td><td><span style="color:var(--green-ok);"></span></td></tr>
              <tr style="background:#F0FDF4;"><td style="font-weight:700;">李明 </td><td>日本</td><td>19</td><td>12.1%</td><td>$6,200</td><td><span style="color:var(--green-ok);"></span></td></tr>
              <tr><td>陈静</td><td>东南亚</td><td>16</td><td>11.4%</td><td>$5,800</td><td><span style="color:var(--green-ok);"></span></td></tr>
              <tr><td>王芳</td><td>欧洲</td><td>14</td><td>8.3%</td><td>$2,100</td><td><span style="color:#D97706;"></span></td></tr>
            </tbody></table>
          </div></div>

          <div class="panel"><div class="panel-header"><span> 全局Pipeline</span></div><div class="panel-body" style="font-size:12px;">
            <div class="funnel-row"><span class="funnel-label">线索池</span><div class="funnel-bar"><div class="funnel-fill" style="width:100%;"></div></div><span class="funnel-val">1,247</span></div>
            <div class="funnel-row"><span class="funnel-label">已分析</span><div class="funnel-bar"><div class="funnel-fill" style="width:72%;"></div></div><span class="funnel-val">892</span></div>
            <div class="funnel-row"><span class="funnel-label">已分配</span><div class="funnel-bar"><div class="funnel-fill" style="width:12.5%;background:var(--green-ok);"></div></div><span class="funnel-val">156</span></div>
            <div class="funnel-row"><span class="funnel-label">已成交</span><div class="funnel-bar"><div class="funnel-fill" style="width:1.6%;background:var(--green-ok);"></div></div><span class="funnel-val">5</span></div>
            <div style="margin-top:10px;padding:8px;background:var(--bg-base);border-radius:6px;font-size:11px;">
              <div style="font-weight:600;margin-bottom:4px;"> 流水线健康度</div>
              <div style="color:var(--text-secondary);">收集→分析转化率72%（正常）· 分析→分配转化率17.5%（正常）· 分配→成交转化率3.2%（需关注）</div>
            </div>
          </div></div>
        </div>
      </div>
    </div>

    <!-- CEO Lead Collect -->
    <div v-else-if="store.currentView === 'ceo-lead-collect'">
      <div style="padding:16px 20px;max-width:1400px;margin:0 auto;">
        <div class="agent-live-bar" style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:linear-gradient(90deg, #F0F9FF, #E0F2FE);border-radius:8px;border-left:4px solid var(--blue-primary);margin-bottom:14px;">
          <div class="live-dot" style="width:8px;height:8px;background:var(--green-ok);border-radius:50%;animation:pulse-dot 1.5s infinite;"></div>
          <span style="font-weight:700;">线索收集Agent · 运行中</span>
          <div class="live-stat" style="margin-left:auto;display:flex;gap:16px;font-size:12px;color:var(--text-secondary);">
            <span>今日执行: <strong>38次</strong></span>
            <span>新发现: <strong>12条</strong></span>
            <span>渠道: <strong>4个</strong></span>
          </div>
        </div>
        <div style="font-size:18px;font-weight:700;margin-bottom:14px;"> 线索收集Agent</div>
        <div style="font-size:12px;color:var(--text-secondary);margin-bottom:14px;">从多渠道主动发现潜在客户线索，完成基础信息采集后流转给线索分析Agent</div>

        <div class="metric-cards" style="margin-bottom:14px;">
          <div class="metric-card"><div class="metric-label">本月总发现</div><div class="metric-val">1,247</div><div class="metric-sub">累计</div></div>
          <div class="metric-card"><div class="metric-label">今日新发现</div><div class="metric-val" style="color:var(--green-ok);">38</div><div class="metric-sub">持续更新</div></div>
          <div class="metric-card"><div class="metric-label">渠道覆盖</div><div class="metric-val">4</div><div class="metric-sub">B端·C端·GEO·手动上传</div></div>
          <div class="metric-card"><div class="metric-label">数据完整度</div><div class="metric-val">94%</div><div class="metric-sub">基础信息覆盖率</div></div>
        </div>

        <div class="row-2" style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
          <div class="panel"><div class="panel-header"><span> 渠道产出分布</span></div><div class="panel-body" style="font-size:12px;">
            <div style="margin-bottom:10px;display:flex;align-items:center;gap:8px;">
              <span style="width:80px;font-weight:600;">B端</span>
              <div class="progress-bar" style="flex:1;"><div class="fill" style="width:42%;background:var(--blue-primary);"></div></div>
              <span style="width:60px;text-align:right;font-weight:700;">524</span>
            </div>
            <div style="margin-bottom:10px;display:flex;align-items:center;gap:8px;">
              <span style="width:80px;font-weight:600;">GEO</span>
              <div class="progress-bar" style="flex:1;"><div class="fill" style="width:28%;background:var(--green-ok);"></div></div>
              <span style="width:60px;text-align:right;font-weight:700;">349</span>
            </div>
            <div style="margin-bottom:10px;display:flex;align-items:center;gap:8px;">
              <span style="width:80px;font-weight:600;">C端</span>
              <div class="progress-bar" style="flex:1;"><div class="fill" style="width:20%;background:var(--cyan-accent);"></div></div>
              <span style="width:60px;text-align:right;font-weight:700;">249</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="width:80px;font-weight:600;">手动上传</span>
              <div class="progress-bar" style="flex:1;"><div class="fill" style="width:10%;background:#D97706;"></div></div>
              <span style="width:60px;text-align:right;font-weight:700;">125</span>
            </div>
          </div></div>
          <div class="panel"><div class="panel-header"><span> 最近发现</span></div><div class="panel-body" style="font-size:11px;color:var(--text-secondary);line-height:1.8;">
            · B端渠道今日发现12条新线索（日本TMC为主）<br>
            · GEO被动引流本周新增8条（日本市场增长明显）<br>
            · C端裂变渠道新增5条（东南亚用户推荐）<br>
            · 手动上传今日导入3条（来自行业展会名片）
          </div></div>
        </div>
      </div>
    </div>

    <!-- CEO Lead Analyze -->
    <div v-else-if="store.currentView === 'ceo-lead-analyze'">
      <div style="padding:16px 20px;max-width:1400px;margin:0 auto;">
        <div class="agent-live-bar" style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:linear-gradient(90deg, #F0F9FF, #E0F2FE);border-radius:8px;border-left:4px solid var(--blue-primary);margin-bottom:14px;">
          <div class="live-dot" style="width:8px;height:8px;background:var(--green-ok);border-radius:50%;animation:pulse-dot 1.5s infinite;"></div>
          <span style="font-weight:700;">线索分析Agent · 运行中</span>
          <div class="live-stat" style="margin-left:auto;display:flex;gap:16px;font-size:12px;color:var(--text-secondary);">
            <span>今日分析: <strong>42次</strong></span>
            <span>评分完成: <strong>38条</strong></span>
            <span>准确率: <strong>91%</strong></span>
          </div>
        </div>
        <div style="font-size:18px;font-weight:700;margin-bottom:14px;"> 线索分析Agent</div>
        <div style="font-size:12px;color:var(--text-secondary);margin-bottom:14px;">对线索进行7维ICP评分、富化、分类，完成后流转给线索分配</div>

        <div class="metric-cards" style="margin-bottom:14px;">
          <div class="metric-card"><div class="metric-label">已分析</div><div class="metric-val">892</div><div class="metric-sub">本月累计</div></div>
          <div class="metric-card"><div class="metric-label">评分准确率</div><div class="metric-val" style="color:var(--green-ok);">91%</div><div class="metric-sub"><span class="change up">↑4%</span></div></div>
          <div class="metric-card"><div class="metric-label">富化完成率</div><div class="metric-val">86%</div><div class="metric-sub">信息补全</div></div>
          <div class="metric-card"><div class="metric-label">驳回率</div><div class="metric-val" style="color:var(--orange-warn);">18%</div><div class="metric-sub">不符合ICP</div></div>
        </div>

        <div class="row-2" style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
          <div class="panel"><div class="panel-header"><span> 评分分布</span></div><div class="panel-body" style="font-size:12px;">
            <div style="margin-bottom:10px;display:flex;align-items:center;gap:8px;">
              <span style="width:60px;font-weight:600;color:var(--green-ok);">A类</span>
              <div class="progress-bar" style="flex:1;"><div class="fill" style="width:28%;background:var(--green-ok);"></div></div>
              <span style="width:80px;text-align:right;font-weight:700;">250条 (28%)</span>
            </div>
            <div style="margin-bottom:10px;display:flex;align-items:center;gap:8px;">
              <span style="width:60px;font-weight:600;color:var(--blue-primary);">B类</span>
              <div class="progress-bar" style="flex:1;"><div class="fill" style="width:42%;background:var(--blue-primary);"></div></div>
              <span style="width:80px;text-align:right;font-weight:700;">375条 (42%)</span>
            </div>
            <div style="margin-bottom:10px;display:flex;align-items:center;gap:8px;">
              <span style="width:60px;font-weight:600;color:#D97706;">C类</span>
              <div class="progress-bar" style="flex:1;"><div class="fill" style="width:12%;background:#D97706;"></div></div>
              <span style="width:80px;text-align:right;font-weight:700;">107条 (12%)</span>
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
              <span style="width:60px;font-weight:600;color:var(--text-muted);">驳回</span>
              <div class="progress-bar" style="flex:1;"><div class="fill" style="width:18%;background:var(--text-muted);"></div></div>
              <span style="width:80px;text-align:right;font-weight:700;">160条 (18%)</span>
            </div>
          </div></div>
          <div class="panel"><div class="panel-header"><span> 分析维度</span></div><div class="panel-body" style="font-size:11px;color:var(--text-secondary);line-height:1.8;">
            <strong>7维ICP评分模型：</strong><br>
            · D1 公司规模 (15%)<br>
            · D2 行业匹配 (20%)<br>
            · D3 融资状态 (15%)<br>
            · D4 地理区域 (10%)<br>
            · D5 技术栈 (15%)<br>
            · D6 招聘信号 (15%)<br>
            · D7 决策人可触达 (10%)<br>
            <div style="margin-top:6px;font-size:10px;color:var(--text-muted);">模型版本 v1.2 · 上次校准 2026.06.01</div>
          </div></div>
        </div>
      </div>
    </div>

    <!-- CEO Lead Assign -->
    <div v-else-if="store.currentView === 'ceo-lead-assign'">
      <div style="padding:16px 20px;max-width:1400px;margin:0 auto;">
        <div class="agent-live-bar" style="display:flex;align-items:center;gap:12px;padding:12px 16px;background:linear-gradient(90deg, #F0F9FF, #E0F2FE);border-radius:8px;border-left:4px solid var(--blue-primary);margin-bottom:14px;">
          <div class="live-dot" style="width:8px;height:8px;background:var(--green-ok);border-radius:50%;animation:pulse-dot 1.5s infinite;"></div>
          <span style="font-weight:700;">线索分配 · 运行中</span>
          <div class="live-stat" style="margin-left:auto;display:flex;gap:16px;font-size:12px;color:var(--text-secondary);">
            <span>今日分配: <strong>18条</strong></span>
            <span>分配准确率: <strong>95%</strong></span>
            <span>跟进率: <strong>92%</strong></span>
          </div>
        </div>
        <div style="font-size:18px;font-weight:700;margin-bottom:14px;"> 线索分配</div>
        <div style="font-size:12px;color:var(--text-secondary);margin-bottom:14px;">按地域、客户类型将分析后的线索分配给对应销售，生成人机断点供销售直接跟进</div>

        <div class="metric-cards" style="margin-bottom:14px;">
          <div class="metric-card"><div class="metric-label">已分配</div><div class="metric-val">156</div><div class="metric-sub">本月累计</div></div>
          <div class="metric-card"><div class="metric-label">今日分配</div><div class="metric-val" style="color:var(--green-ok);">18</div><div class="metric-sub">A类6 · B类12</div></div>
          <div class="metric-card"><div class="metric-label">分配准确率</div><div class="metric-val" style="color:var(--green-ok);">95%</div><div class="metric-sub">按地域匹配</div></div>
          <div class="metric-card"><div class="metric-label">整体跟进率</div><div class="metric-val" style="color:var(--green-ok);">92%</div><div class="metric-sub">销售响应</div></div>
        </div>

        <div class="row-2" style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
          <div class="panel"><div class="panel-header"><span> 分配规则</span></div><div class="panel-body" style="font-size:11px;line-height:1.8;">
            <div style="margin-bottom:8px;padding:8px;background:var(--bg-base);border-radius:6px;">
              <div style="font-weight:600;color:var(--green-ok);">A类线索 → 资深销售</div>
              <div style="color:var(--text-secondary);">高评分线索优先分配给转化率最高的销售</div>
            </div>
            <div style="margin-bottom:8px;padding:8px;background:var(--bg-base);border-radius:6px;">
              <div style="font-weight:600;color:var(--blue-primary);">B类线索 → 按地域分配</div>
              <div style="color:var(--text-secondary);">北美→张伟 · 日本→李明 · 东南亚→陈静 · 欧洲→王芳</div>
            </div>
            <div style="padding:8px;background:var(--bg-base);border-radius:6px;">
              <div style="font-weight:600;color:var(--text-muted);">C类线索 → 暂存线索池</div>
              <div style="color:var(--text-secondary);">低评分线索暂不分配，等待二次分析</div>
            </div>
          </div></div>
          <div class="panel"><div class="panel-header"><span> 今日分配明细</span></div><div class="panel-body" style="padding:0;">
            <table class="matrix-table"><thead><tr><th>销售</th><th>区域</th><th>今日分配</th><th>本月累计</th><th>跟进率</th></tr></thead><tbody>
              <tr><td>张伟</td><td>北美</td><td>6</td><td>23</td><td><span style="color:var(--green-ok);">94%</span></td></tr>
              <tr style="background:#F0FDF4;"><td style="font-weight:700;">李明 </td><td>日本</td><td>5</td><td>19</td><td><span style="color:var(--green-ok);">88%</span></td></tr>
              <tr><td>陈静</td><td>东南亚</td><td>4</td><td>16</td><td><span style="color:var(--green-ok);">85%</span></td></tr>
              <tr><td>王芳</td><td>欧洲</td><td>3</td><td>14</td><td><span style="color:#D97706;">71%</span></td></tr>
            </tbody></table>
          </div></div>
        </div>
      </div>
    </div>

    <!-- CEO Team -->
    <div v-else-if="store.currentView === 'ceo-team'">
      <div style="padding:16px 20px;max-width:1400px;margin:0 auto;">
        <div style="font-size:18px;font-weight:700;margin-bottom:14px;"> 销售团队</div>
        <div class="panel" style="margin-bottom:14px;"><div class="panel-header"><span> 团队排行</span></div><div class="panel-body" style="padding:0;">
          <table class="matrix-table"><thead><tr><th>排名</th><th>姓名</th><th>区域</th><th>线索量</th><th>跟进率</th><th>转化率</th><th>成交额</th><th>状态</th></tr></thead><tbody>
            <tr><td>1</td><td>张伟</td><td>北美</td><td>23</td><td>94%</td><td>15.2%</td><td>$8,400</td><td><span style="color:var(--green-ok);"> 正常</span></td></tr>
            <tr style="background:#F0FDF4;"><td>2</td><td style="font-weight:700;">李明 </td><td>日本</td><td>19</td><td>88%</td><td>12.1%</td><td>$6,200</td><td><span style="color:var(--green-ok);"> 正常</span></td></tr>
            <tr><td>3</td><td>陈静</td><td>东南亚</td><td>16</td><td>85%</td><td>11.4%</td><td>$5,800</td><td><span style="color:var(--green-ok);"> 正常</span></td></tr>
            <tr><td>4</td><td>王芳</td><td>欧洲</td><td>14</td><td>71%</td><td>8.3%</td><td>$2,100</td><td><span style="color:#D97706;"> 需关注</span></td></tr>
          </tbody></table>
        </div></div>
        <div class="panel">
          <div class="panel-header"><span> 异常预警</span></div>
          <div class="panel-body" style="display:flex;flex-direction:column;gap:8px;">
            <div class="insight-card yellow" style="padding:12px;background:#FEF3C7;border-radius:6px;border-left:4px solid #D97706;font-size:12px;"><strong>🟡 王芳欧洲区跟进率71%低于团队均值</strong><br>建议：检查线索质量 + 分享高转化话术</div>
            <div class="insight-card green" style="padding:12px;background:#ECFDF5;border-radius:6px;border-left:4px solid var(--green-ok);font-size:12px;"><strong>🟢 张伟北美区转化率15.2%领先</strong><br>建议：分享其跟进策略给其他销售</div>
          </div>
        </div>
      </div>
    </div>

    <!-- CEO Pipeline -->
    <div v-else-if="store.currentView === 'ceo-pipeline'">
      <div style="padding:16px 20px;max-width:1400px;margin:0 auto;">
        <div style="font-size:18px;font-weight:700;margin-bottom:14px;"> 全局Pipeline</div>
        <div class="metric-cards" style="margin-bottom:14px;">
          <div class="metric-card"><div class="metric-label">Pipeline总额</div><div class="metric-val" style="color:var(--blue-primary);">$186,400</div><div class="metric-sub">18个商机</div></div>
          <div class="metric-card"><div class="metric-label">本月成交</div><div class="metric-val" style="color:var(--green-ok);">$42,800</div><div class="metric-sub">目标53%</div></div>
          <div class="metric-card"><div class="metric-label">平均成单周期</div><div class="metric-val">18<span style="font-size:14px;">天</span></div></div>
          <div class="metric-card"><div class="metric-label">预测月底</div><div class="metric-val" style="color:var(--blue-primary);">$68,000</div><div class="metric-sub">目标85%</div></div>
        </div>
        <div class="panel"><div class="panel-header"><span> 全局漏斗</span></div><div class="panel-body">
          <div class="funnel-row"><span class="funnel-label">线索池</span><div class="funnel-bar"><div class="funnel-fill" style="width:100%;"></div></div><span class="funnel-val">1,247</span><span class="funnel-pct">100%</span></div>
          <div class="funnel-row"><span class="funnel-label">已触达</span><div class="funnel-bar"><div class="funnel-fill" style="width:25%;"></div></div><span class="funnel-val">312</span><span class="funnel-pct">25%</span></div>
          <div class="funnel-row"><span class="funnel-label">有意向</span><div class="funnel-bar"><div class="funnel-fill" style="width:5.8%;background:#D97706;"></div></div><span class="funnel-val">18</span><span class="funnel-pct">5.8%</span></div>
          <div class="funnel-row"><span class="funnel-label">商机</span><div class="funnel-bar"><div class="funnel-fill" style="width:2.4%;background:var(--blue-primary);"></div></div><span class="funnel-val">8</span><span class="funnel-pct">2.4%</span></div>
          <div class="funnel-row"><span class="funnel-label">成交</span><div class="funnel-bar"><div class="funnel-fill" style="width:1.6%;background:var(--green-ok);"></div></div><span class="funnel-val">5</span><span class="funnel-pct">1.6%</span></div>
        </div></div>
        <div class="row-2" style="margin-top:14px;display:grid;grid-template-columns:1fr 1fr;gap:14px;">
          <div class="panel"><div class="panel-header"><span> 区域分布</span></div><div class="panel-body" style="font-size:12px;">
            <div style="margin-bottom:8px;padding:8px;background:var(--bg-base);border-radius:6px;display:flex;justify-content:space-between;"><span> 北美</span><span style="font-weight:700;">$18,200</span><span style="color:var(--green-ok);">+18%</span></div>
            <div style="margin-bottom:8px;padding:8px;background:var(--bg-base);border-radius:6px;display:flex;justify-content:space-between;"><span> 日本</span><span style="font-weight:700;">$12,400</span><span style="color:var(--green-ok);">+31%</span></div>
            <div style="margin-bottom:8px;padding:8px;background:var(--bg-base);border-radius:6px;display:flex;justify-content:space-between;"><span> 东南亚</span><span style="font-weight:700;">$8,600</span><span style="color:var(--green-ok);">+8%</span></div>
            <div style="padding:8px;background:var(--bg-base);border-radius:6px;display:flex;justify-content:space-between;"><span> 欧洲</span><span style="font-weight:700;">$3,600</span><span style="color:var(--red-badge);">-12%</span></div>
          </div></div>
          <div class="panel"><div class="panel-header"><span> 渠道ROI</span></div><div class="panel-body" style="font-size:12px;">
            <div style="margin-bottom:8px;display:flex;align-items:center;gap:8px;"><span style="width:80px;">B端</span><div class="progress-bar" style="flex:1;"><div class="fill" style="width:85%;background:var(--blue-primary);"></div></div><span style="font-weight:700;">4.2x</span></div>
            <div style="margin-bottom:8px;display:flex;align-items:center;gap:8px;"><span style="width:80px;">GEO</span><div class="progress-bar" style="flex:1;"><div class="fill" style="width:78%;background:var(--green-ok);"></div></div><span style="font-weight:700;">3.9x</span></div>
            <div style="margin-bottom:8px;display:flex;align-items:center;gap:8px;"><span style="width:80px;">C端</span><div class="progress-bar" style="flex:1;"><div class="fill" style="width:55%;background:var(--cyan-accent);"></div></div><span style="font-weight:700;">2.8x</span></div>
            <div style="display:flex;align-items:center;gap:8px;"><span style="width:80px;">手动上传</span><div class="progress-bar" style="flex:1;"><div class="fill" style="width:24%;background:#D97706;"></div></div><span style="font-weight:700;">1.2x</span></div>
          </div></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content-main { display: flex; flex-direction: column; width: 100%; }
.metric-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.metric-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow-sm); }
.metric-label { font-size: 11px; color: var(--text-muted); margin-bottom: 4px; }
.metric-val { font-size: 24px; font-weight: 700; }
.metric-sub { font-size: 10px; color: var(--text-muted); }

.funnel-row { display: flex; align-items: center; padding: 6px 0; border-bottom: 1px solid var(--border-light); font-size: 12px; }
.funnel-label { width: 60px; }
.funnel-bar { flex: 1; height: 16px; background: var(--bg-base); border-radius: 4px; margin: 0 10px; overflow: hidden; }
.funnel-fill { height: 100%; background: var(--tuge-gradient); }
.funnel-val { width: 50px; text-align: right; font-weight: 600; }
.funnel-pct { width: 40px; text-align: right; color: var(--text-muted); font-size: 10px; }
</style>
