import type { ReactNode } from 'react';
import { Collapse } from 'antd';
import styles from './Panel.module.css';
import { Icon, type IconName } from './Icon';

/** 控制台统一面板：标题栏 + 内容区（可选页脚）。 */
export function Panel({
  title,
  subtitle,
  icon,
  extra,
  footer,
  children,
  bodyPadding = 'default',
  className,
  id,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: IconName;
  extra?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
  bodyPadding?: 'default' | 'flush' | 'tight';
  className?: string;
  id?: string;
}) {
  return (
    <section className={`${styles.panel} ${className ?? ''}`} id={id}>
      <header className={styles.head}>
        <div className={styles.headLeft}>
          <span className={styles.bar} />
          {icon ? <Icon name={icon} size={14} style={{ color: 'var(--ts-ink-2)' }} /> : null}
          <span className={styles.title}>{title}</span>
          {subtitle ? <span className={styles.sub}>{subtitle}</span> : null}
        </div>
        {extra ? <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>{extra}</div> : null}
      </header>
      <div
        className={`${styles.body} ${
          bodyPadding === 'flush' ? styles.bodyFlush : bodyPadding === 'tight' ? styles.bodyTight : ''
        }`}
      >
        {children}
      </div>
      {footer ? <footer className={styles.footer}>{footer}</footer> : null}
    </section>
  );
}

export function VStack({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={`${styles.stack} ${className ?? ''}`}>{children}</div>;
}

export function Grid2({ children }: { children: ReactNode }) {
  return <div className={styles.grid2}>{children}</div>;
}

/**
 * 可折叠面板：用于诊断页「规则库」「评分明细」等信息密度高的区域。
 * 默认收起，保持首屏以结论为中心。
 */
export function FoldPanel({
  title,
  meta,
  icon,
  children,
  defaultActive = false,
  items,
}: {
  title: ReactNode;
  meta?: ReactNode;
  icon?: IconName;
  children?: ReactNode;
  defaultActive?: boolean;
  /** 需要多个折叠项时直接传 items（此时忽略 children） */
  items?: { key: string; label: ReactNode; children: ReactNode }[];
}) {
  const collapseItems =
    items?.map((i) => ({
      key: i.key,
      label: (
        <span className={styles.collapseHead}>
          {icon ? <Icon name={icon} size={13} /> : null}
          {i.label}
        </span>
      ),
      children: i.children,
    })) ??
    [
      {
        key: 'single',
        label: (
          <span className={styles.collapseHead}>
            {icon ? <Icon name={icon} size={13} /> : null}
            {title}
            {meta ? <span className={styles.collapseMeta}>{meta}</span> : null}
          </span>
        ),
        children,
      },
    ];

  const activeKeys = defaultActive ? collapseItems.map((i) => i.key) : undefined;

  return (
    <div className={styles.panel}>
      <Collapse
        ghost
        bordered={false}
        defaultActiveKey={activeKeys}
        items={collapseItems}
        style={{ background: 'transparent' }}
      />
    </div>
  );
}
