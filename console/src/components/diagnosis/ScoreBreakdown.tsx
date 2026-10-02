import styles from './ScoreBreakdown.module.css';
import { Icon } from '@/components/common/Icon';
import { COLORS, SCORE_DIMENSION_TEXT } from '@/theme/tokens';
import type { AlternativeCause, Diagnosis, ScoreBreakdownItem } from '@/types';

/**
 * 单维度条形：score / max + detail。
 * 进度条宽度用百分比，颜色恒定为主色——**刻意不使用红/绿**，
 * 避免读者把维度分数误读为「好/坏」或概率。
 */
export function DimensionBars({ items }: { items: ScoreBreakdownItem[] }) {
  return (
    <div className={styles.dims}>
      {items.map((item) => {
        const pct = item.max > 0 ? Math.max(0, Math.min(100, (item.score / item.max) * 100)) : 0;
        return (
          <div key={item.dimension} className={styles.dimRow}>
            <div className={styles.dim}>
              <span className={styles.dimName} title={SCORE_DIMENSION_TEXT[item.dimension] ?? item.label}>
                {item.label || SCORE_DIMENSION_TEXT[item.dimension] || item.dimension}
              </span>
              <span className={styles.dimScore}>
                {item.score}
                <span className={styles.dimScoreMax}>/{item.max}</span>
              </span>
              <span
                className={styles.track}
                role="img"
                aria-label={`${item.label}：${item.score} / ${item.max}`}
              >
                <span
                  className={`${styles.fill} ${pct === 0 ? styles.fillZero : ''}`}
                  style={{ width: `${pct === 0 ? 100 : pct}%`, opacity: pct === 0 ? 0.85 : 1 }}
                />
              </span>
            </div>
            <div className={styles.dimDetail}>{item.detail}</div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Evidence Match 总分展示。
 * 醒目数字 + 明确的「非概率」声明（方案 §6.3 硬性要求）。
 */
export function MatchScoreHeader({ diagnosis, compact = false }: { diagnosis: Diagnosis; compact?: boolean }) {
  const score = Math.round(diagnosis.match_score);
  const tone = score >= 80 ? COLORS.critical : score >= 55 ? COLORS.warning : COLORS.inkSecondary;
  return (
    <div className={styles.score}>
      <div className={styles.gauge}>
        <span className={styles.gaugeValue} style={{ color: tone }}>
          {score}
        </span>
        <span className={styles.gaugeMax}>/100</span>
        <span className={styles.gaugeUnit}>Evidence&nbsp;Match</span>
      </div>
      <div className={styles.gaugeSide}>
        <span className={styles.gaugeLabel}>{diagnosis.title}</span>
        <span className={styles.caption}>
          根因：<span className="ts-mono">{diagnosis.root_cause}</span> · 规则{' '}
          <span className="ts-mono">
            {diagnosis.rule}@v{diagnosis.rule_version}
          </span>
        </span>
        {!compact ? <span className={styles.caption}>{diagnosis.root_cause_label}</span> : null}
        <span className={styles.note}>
          <Icon name="info" size={12} />
          {diagnosis.match_note || 'Evidence Match 为规则证据命中评分（0–100），非概率'}
        </span>
      </div>
    </div>
  );
}

/** 备选候选：解释 Top-N 的排序语义，而非只显示 Top-1。 */
export function CandidateList({
  candidates,
  currentRule,
  onSelect,
}: {
  candidates: (Diagnosis | AlternativeCause)[];
  currentRule?: string;
  onSelect?: (rule: string) => void;
}) {
  return (
    <div className={styles.candidates}>
      {candidates.map((c) => {
        const isCurrent = c.rule === currentRule;
        const reason = 'reason' in c ? c.reason : undefined;
        return (
          <div key={c.rule} className={`${styles.candidate} ${isCurrent ? styles.candidateCurrent : ''}`}>
            <div>
              <div className={styles.candidateTitle}>
                {onSelect ? (
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      onSelect(c.rule);
                    }}
                  >
                    {c.title}
                  </a>
                ) : (
                  c.title
                )}
              </div>
              <div className={styles.candidateRule}>
                {c.rule}
                {'root_cause' in c && c.root_cause ? ` · ${c.root_cause}` : ''}
                {isCurrent ? ' · 当前选中' : ''}
              </div>
            </div>
            <span className={styles.track} aria-hidden="true">
              <span className={styles.fill} style={{ width: `${Math.min(100, c.match_score)}%` }} />
            </span>
            <span className={styles.candidateScore}>{Math.round(c.match_score)}</span>
            {reason ? <div className={styles.candidateReason}>未入选原因：{reason}</div> : null}
          </div>
        );
      })}
    </div>
  );
}
