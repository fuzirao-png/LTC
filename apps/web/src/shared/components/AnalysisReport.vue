<script setup lang="ts">
import { useAppStore } from '../../stores/app';

const store = useAppStore();
</script>

<template>
  <div v-if="store.isAnalysisReportOpen" id="analysisReportPanel" style="position:fixed;top:48px;left:240px;right:0;bottom:0;background:var(--bg-card);z-index:200;overflow-y:auto;">
    <span class="fixed-close-btn" @click="store.isAnalysisReportOpen = false">✕</span>
    <div style="padding:20px 32px;max-width:1400px;margin:0 auto;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:24px;padding-bottom:16px;border-bottom:2px solid var(--border);">
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-size:28px;">📊</span>
          <div>
            <div style="font-size:20px;font-weight:700;">客户深度分析报告</div>
            <div style="font-size:13px;color:var(--text-muted);">AI 智能分析 · 基于多维度数据生成</div>
          </div>
        </div>
      </div>

      <!-- 报告内容 -->
      <div id="reportContent">
        <!-- 客户基本信息 -->
        <div style="padding:16px;background:linear-gradient(135deg,#F0F9FF,#ECFDF5);border-radius:12px;margin-bottom:20px;border:1px solid var(--border);">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">
            <span style="font-size:28px;">🏢</span>
            <div>
              <div style="font-size:18px;font-weight:700;">GlobalLink Travel</div>
              <div style="font-size:12px;color:var(--text-secondary);">TMC · 英国伦敦 · 2000+员工 · 企业通讯管理</div>
            </div>
            <span style="margin-left:auto;font-size:10px;padding:4px 12px;background:linear-gradient(135deg,var(--blue-primary),var(--cyan-accent));color:#fff;border-radius:20px;font-weight:600;">✨ AI分析报告</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">
            <div style="text-align:center;padding:8px;background:var(--bg-card);border-radius:8px;">
              <div style="font-size:24px;font-weight:800;color:var(--green-ok);">86%</div>
              <div style="font-size:10px;color:var(--text-muted);">画像完整度</div>
            </div>
            <div style="text-align:center;padding:8px;background:var(--bg-card);border-radius:8px;">
              <div style="font-size:18px;font-weight:800;color:var(--blue-primary);">$8,000/年</div>
              <div style="font-size:10px;color:var(--text-muted);">预算</div>
            </div>
            <div style="text-align:center;padding:8px;background:var(--bg-card);border-radius:8px;">
              <div style="font-size:16px;font-weight:800;">Sarah Chen</div>
              <div style="font-size:10px;color:var(--text-muted);">关键决策人</div>
            </div>
            <div style="text-align:center;padding:8px;background:var(--bg-card);border-radius:8px;">
              <div style="font-size:18px;font-weight:800;color:var(--green-ok);">2周</div>
              <div style="font-size:10px;color:var(--text-muted);">决策周期</div>
            </div>
          </div>
        </div>

        <!-- 1. 市场分析 -->
        <div style="margin-bottom:24px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="font-size:20px;">📈</span>
            <span style="font-size:18px;font-weight:700;">1. 市场分析</span>
            <span style="font-size:10px;padding:3px 10px;background:var(--blue-light);color:var(--blue-primary);border-radius:10px;">区域竞争情况</span>
          </div>
          <div style="padding:20px;background:var(--bg-base);border-radius:12px;line-height:1.8;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
              <div>
                <div style="font-weight:600;margin-bottom:10px;color:var(--blue-primary);font-size:14px;">📊 竞争格局</div>
                <div style="font-size:12px;color:var(--text-secondary);">
                  · 英国TMC市场竞争激烈，前5大玩家占据75%份额<br>
                  · 主要竞争对手：CorporateTravel.com, BCD Travel, CWT<br>
                  · 差异化机会：多国通讯成本统一管理方案<br>
                  · 市场进入壁垒：品牌认知度、客户关系、技术能力
                </div>
              </div>
              <div>
                <div style="font-weight:600;margin-bottom:10px;color:var(--green-ok);font-size:14px;">📈 市场趋势</div>
                <div style="font-size:12px;color:var(--text-secondary);">
                  · 企业差旅复苏强劲，同比增长23%<br>
                  · eSIM企业渗透率从8%提升至25%<br>
                  · 合规性需求成为采购决策关键因素<br>
                  · 数字化转型加速，AI赋能差旅管理
                </div>
              </div>
            </div>
            <div style="margin-top:16px;padding:12px;background:var(--bg-card);border-radius:8px;">
              <div style="font-weight:600;margin-bottom:8px;">📊 市场机会评估</div>
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;">
                <div style="text-align:center;padding:8px;background:var(--bg-base);border-radius:6px;">
                  <div style="font-size:18px;font-weight:800;color:var(--green-ok);">高</div>
                  <div style="font-size:10px;color:var(--text-muted);">市场潜力</div>
                </div>
                <div style="text-align:center;padding:8px;background:var(--bg-base);border-radius:6px;">
                  <div style="font-size:18px;font-weight:800;color:#D97706;">中</div>
                  <div style="font-size:10px;color:var(--text-muted);">竞争强度</div>
                </div>
                <div style="text-align:center;padding:8px;background:var(--bg-base);border-radius:6px;">
                  <div style="font-size:18px;font-weight:800;color:var(--green-ok);">高</div>
                  <div style="font-size:10px;color:var(--text-muted);">进入机会</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 2. 公司分析 -->
        <div style="margin-bottom:24px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="font-size:20px;">🏢</span>
            <span style="font-size:18px;font-weight:700;">2. 公司分析</span>
          </div>
          <div style="padding:20px;background:var(--bg-base);border-radius:12px;line-height:1.8;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
              <div>
                <div style="font-weight:600;margin-bottom:10px;font-size:14px;">📋 公司简介</div>
                <div style="font-size:12px;color:var(--text-secondary);">
                  · 成立于2012年，英国伦敦总部<br>
                  · 2000+员工，管理8个国家差旅业务<br>
                  · Series B融资$12M（2周前）<br>
                  · 年营收$50M+，增长率23%
                </div>
              </div>
              <div>
                <div style="font-weight:600;margin-bottom:10px;font-size:14px;">📅 发展历程</div>
                <div style="font-size:12px;color:var(--text-secondary);">
                  · 2012年成立，专注英国本土差旅<br>
                  · 2018年扩展至欧洲市场<br>
                  · 2023年进入亚太市场<br>
                  · 2026年计划IPO
                </div>
              </div>
              <div>
                <div style="font-weight:600;margin-bottom:10px;font-size:14px;">🌐 产品与全球布局</div>
                <div style="font-size:12px;color:var(--text-secondary);">
                  · 核心产品：企业差旅管理平台<br>
                  · 覆盖区域：英国、欧洲8国、亚太8国<br>
                  · 客户规模：500+企业客户<br>
                  · 技术栈：云原生、AI驱动
                </div>
              </div>
            </div>
            <div style="margin-top:16px;padding:12px;background:var(--bg-card);border-radius:8px;">
              <div style="font-weight:600;margin-bottom:8px;">📊 公司健康度评估</div>
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">
                <div style="text-align:center;padding:8px;background:var(--bg-base);border-radius:6px;">
                  <div style="font-size:16px;font-weight:800;color:var(--green-ok);">A</div>
                  <div style="font-size:10px;color:var(--text-muted);">财务状况</div>
                </div>
                <div style="text-align:center;padding:8px;background:var(--bg-base);border-radius:6px;">
                  <div style="font-size:16px;font-weight:800;color:var(--green-ok);">A+</div>
                  <div style="font-size:10px;color:var(--text-muted);">技术能力</div>
                </div>
                <div style="text-align:center;padding:8px;background:var(--bg-base);border-radius:6px;">
                  <div style="font-size:16px;font-weight:800;color:var(--blue-primary);">B+</div>
                  <div style="font-size:10px;color:var(--text-muted);">市场地位</div>
                </div>
                <div style="text-align:center;padding:8px;background:var(--bg-base);border-radius:6px;">
                  <div style="font-size:16px;font-weight:800;color:var(--green-ok);">A</div>
                  <div style="font-size:10px;color:var(--text-muted);">增长潜力</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 3. 产品建议 -->
        <div style="margin-bottom:24px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="font-size:20px;">💡</span>
            <span style="font-size:18px;font-weight:700;">3. 产品建议</span>
          </div>
          <div style="padding:20px;background:var(--bg-base);border-radius:12px;line-height:1.8;">
            <div style="margin-bottom:16px;">
              <div style="font-weight:600;margin-bottom:10px;color:var(--blue-primary);font-size:14px;">📦 推荐套餐</div>
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;">
                <div style="padding:16px;background:var(--bg-card);border-radius:10px;border:2px solid var(--blue-primary);position:relative;">
                  <div style="position:absolute;top:-10px;left:16px;padding:2px 10px;background:var(--blue-primary);color:#fff;border-radius:10px;font-size:10px;font-weight:600;">基础版</div>
                  <div style="font-size:24px;font-weight:800;margin:8px 0;">$5,000<span style="font-size:12px;color:var(--text-muted);">/年</span></div>
                  <div style="font-size:11px;color:var(--text-secondary);">
                    · 覆盖3个国家<br>
                    · 基础通讯管理<br>
                    · 邮件支持
                  </div>
                </div>
                <div style="padding:16px;background:var(--bg-card);border-radius:10px;border:2px solid var(--green-ok);position:relative;">
                  <div style="position:absolute;top:-10px;left:16px;padding:2px 10px;background:var(--green-ok);color:#fff;border-radius:10px;font-size:10px;font-weight:600;">✅ 推荐版</div>
                  <div style="font-size:24px;font-weight:800;margin:8px 0;color:var(--green-ok);">$8,000<span style="font-size:12px;color:var(--text-muted);">/年</span></div>
                  <div style="font-size:11px;color:var(--text-secondary);">
                    · 覆盖8个国家<br>
                    · GDPR合规保障<br>
                    · 专属客户经理<br>
                    · 优先技术支持
                  </div>
                </div>
                <div style="padding:16px;background:var(--bg-card);border-radius:10px;border:2px solid var(--border);position:relative;">
                  <div style="position:absolute;top:-10px;left:16px;padding:2px 10px;background:var(--text-muted);color:#fff;border-radius:10px;font-size:10px;font-weight:600;">企业版</div>
                  <div style="font-size:24px;font-weight:800;margin:8px 0;">$15,000<span style="font-size:12px;color:var(--text-muted);">/年</span></div>
                  <div style="font-size:11px;color:var(--text-secondary);">
                    · 全球覆盖<br>
                    · 定制化方案<br>
                    · 7×24专属支持<br>
                    · SLA保障
                  </div>
                </div>
              </div>
            </div>
            <div>
              <div style="font-weight:600;margin-bottom:10px;font-size:14px;">🎯 切入角度</div>
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                <div style="padding:10px;background:var(--bg-card);border-radius:6px;">
                  <div style="font-weight:600;color:var(--blue-primary);margin-bottom:4px;">💰 成本优化</div>
                  <div style="font-size:11px;color:var(--text-secondary);">多国差旅通讯成本统一管理 · 匹配客户8国场景，预计节省30%成本</div>
                </div>
                <div style="padding:10px;background:var(--bg-card);border-radius:6px;">
                  <div style="font-weight:600;color:var(--green-ok);margin-bottom:4px;">🛡️ 合规保障</div>
                  <div style="font-size:11px;color:var(--text-secondary);">GDPR合规保障 · 解决客户核心顾虑，避免合规风险</div>
                </div>
                <div style="padding:10px;background:var(--bg-card);border-radius:6px;">
                  <div style="font-weight:600;color:#D97706;margin-bottom:4px;">⚡ 效率提升</div>
                  <div style="font-size:11px;color:var(--text-secondary);">统一管理平台 · 提升管理效率，减少人工操作</div>
                </div>
                <div style="padding:10px;background:var(--bg-card);border-radius:6px;">
                  <div style="font-weight:600;color:var(--cyan-accent);margin-bottom:4px;">📊 ROI分析</div>
                  <div style="font-size:11px;color:var(--text-secondary);">预计12个月内收回投资，长期ROI 3.5倍</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 4. 风险提示 -->
        <div style="margin-bottom:24px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <span style="font-size:20px;">⚠️</span>
            <span style="font-size:18px;font-weight:700;">4. 风险提示</span>
          </div>
          <div style="padding:20px;background:#FFFBF5;border-radius:12px;border-left:4px solid var(--orange-warn);line-height:1.8;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;">
              <div>
                <div style="font-weight:600;margin-bottom:10px;color:#D97706;font-size:14px;">⏰ 决策时间</div>
                <div style="font-size:12px;color:var(--text-secondary);">
                  · 决策周期约2周<br>
                  · 需在1周内推动到方案演示阶段<br>
                  · 关键节点：6月12日方案演示<br>
                  · 预算审批周期：1-2周
                </div>
              </div>
              <div>
                <div style="font-weight:600;margin-bottom:10px;color:#D97706;font-size:14px;">❄️ 冷却期风险</div>
                <div style="font-size:12px;color:var(--text-secondary);">
                  · 若1周内未推进，可能进入冷却期<br>
                  · 冷却期预计3-6周<br>
                  · 竞争对手可能趁虚而入<br>
                  · 客户需求可能发生变化
                </div>
              </div>
            </div>
            <div style="margin-top:16px;padding:12px;background:var(--bg-card);border-radius:8px;">
              <div style="font-weight:600;margin-bottom:8px;font-size:14px;">📅 策略建议</div>
              <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">
                <div style="padding:10px;background:var(--bg-base);border-radius:6px;text-align:center;">
                  <div style="font-size:16px;font-weight:800;color:var(--blue-primary);">Day1</div>
                  <div style="font-size:10px;color:var(--text-secondary);">发送个性化邮件<br>提及融资+8国场景</div>
                </div>
                <div style="padding:10px;background:var(--bg-base);border-radius:6px;text-align:center;">
                  <div style="font-size:16px;font-weight:800;color:var(--blue-primary);">Day3</div>
                  <div style="font-size:10px;color:var(--text-secondary);">未回复则<br>二次触达</div>
                </div>
                <div style="padding:10px;background:var(--bg-base);border-radius:6px;text-align:center;">
                  <div style="font-size:16px;font-weight:800;color:#D97706;">Day5</div>
                  <div style="font-size:10px;color:var(--text-secondary);">LinkedIn连接<br>+ 行业洞察</div>
                </div>
                <div style="padding:10px;background:var(--bg-base);border-radius:6px;text-align:center;">
                  <div style="font-size:16px;font-weight:800;color:var(--green-ok);">Day7</div>
                  <div style="font-size:10px;color:var(--text-secondary);">电话跟进<br>如已回复则加速</div>
                </div>
              </div>
            </div>
            <div style="margin-top:12px;padding:10px;background:rgba(239,68,68,0.1);border-radius:6px;">
              <div style="font-weight:600;margin-bottom:4px;color:var(--red-badge);">⚠️ 风险等级：中高</div>
              <div style="font-size:11px;color:var(--text-secondary);">决策窗口期短，竞争激烈，需快速响应并建立深度联系</div>
            </div>
          </div>
        </div>

        <!-- AI生成说明 -->
        <div style="text-align:center;padding:16px;color:var(--text-muted);font-size:11px;">
          <span style="font-size:14px;">✨</span> 本报告由AI智能分析系统生成 · 基于客户画像、邮件历史、市场数据等多维度信息
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Inline styles matching the original HTML */
</style>
