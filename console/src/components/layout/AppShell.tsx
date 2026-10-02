import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import { Button, Modal, Segmented, Tooltip } from 'antd';
import styles from './AppShell.module.css';
import { Icon, LogoMark, type IconName } from '@/components/common/Icon';
import { DataSourceBadge, SourceStatusStrip } from '@/components/common/DataSourceBadge';
import { useApp } from '@/state/AppContext';
import { SCENARIOS } from '@/data/scenarios';
import { api } from '@/data/client';
import { useAsync } from '@/hooks/useAsync';
import { fmtClock } from '@/utils/format';
import type { ScenarioId } from '@/types';

interface NavItem {
  to: string;
  label: string;
  index: string;
  icon: IconName;
}

const NAV: NavItem[] = [
  { to: '/topology', label: '拓扑', index: '01', icon: 'topology' },
  { to: '/health', label: '健康', index: '02', icon: 'pulse' },
  { to: '/incidents', label: '告警', index: '03', icon: 'alert' },
  { to: '/diagnosis', label: '诊断', index: '04', icon: 'diagnose' },
];

export function AppShell({ children }: { children: ReactNode }) {
  const app = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [switchOpen, setSwitchOpen] = useState(false);

  /** 顶栏告警角标：轻量轮询，失败静默（页面自身会显示错误态）。 */
  const incidents = useAsync((signal) => api.getIncidents({ signal }), [app.refreshToken]);

  const health = useAsync((signal) => api.getServiceHealth({ signal }), [app.refreshToken], {
    pollMs: 30000,
  });

  const openIncidents = useMemo(
    () => (incidents.data?.incidents ?? []).filter((i) => i.status === 'open').length,
    [incidents.data],
  );

  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(app.refresh, 20000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, app.refresh]);

  /** 场景切换：保留当前路由，把 correlation_id / resource_id 带进查询串（api 与 fixture 语义一致）。 */
  const applyScenario = (id: ScenarioId) => {
    app.setScenario(id);
    const s = SCENARIOS.find((x) => x.id === id);
    if (!s) return;
    const params = new URLSearchParams(location.search);
    params.set('scenario', s.id);
    if (location.pathname.startsWith('/diagnosis')) {
      params.set('correlation_id', s.correlation_id);
      params.delete('resource_id');
    } else {
      params.set('resource_id', s.resource_id);
    }
    navigate(`${location.pathname}?${params.toString()}`, { replace: true });
    app.refresh();
  };

  const lastUpdated = incidents.data?.generated_at;

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <LogoMark size={22} />
          <span className={styles.brandText}>
            <span className={styles.brandName}>TraceSphere</span>
            <span className={styles.brandSub}>RCA Console</span>
          </span>
        </div>

        <nav className={styles.nav} aria-label="主导航">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={`${item.to}${location.search}`}
              className={({ isActive }) => `${styles.navItem} ${isActive ? styles.navItemActive : ''}`}
            >
              <Icon name={item.icon} size={14} />
              <span className={styles.navIndex}>{item.index}</span>
              {item.label}
              {item.to === '/incidents' && openIncidents > 0 ? (
                <span className={styles.navBadge} title={`${openIncidents} 个未处理告警`}>
                  {openIncidents}
                </span>
              ) : null}
            </NavLink>
          ))}
        </nav>

        <div className={styles.headRight}>
          <span className={styles.env} title={app.envLabel}>
            {app.envLabel}
          </span>
          <DataSourceBadge blink={health.loading} />
          <Tooltip title="切换到 fixture 回放模式的命令">
            <Button size="small" type="text" onClick={() => setSwitchOpen(true)}>
              数据源切换
            </Button>
          </Tooltip>
        </div>
      </header>

      <div className={styles.strip}>
        <span className={styles.stripGroup}>
          <span className="ts-eyebrow">演示路径</span>
          {SCENARIOS.map((s) => (
            <Tooltip key={s.id} title={s.hint} placement="bottomLeft">
              <button
                type="button"
                aria-pressed={app.scenarioId === s.id}
                className={`${styles.scenarioBtn} ${
                  app.scenarioId === s.id ? styles.scenarioBtnActive : ''
                }`}
                onClick={() => applyScenario(s.id)}
              >
                <span className={styles.scenarioIndex}>{s.index}</span>
                {s.label.replace(/^Case\d+ · /, '')}
              </button>
            </Tooltip>
          ))}
        </span>

        <span className={styles.stripGroup}>
          <span className="ts-eyebrow">当前场景</span>
          <span className={styles.hintText} title={app.scenario.hint}>
            {app.scenario.correlation_id} · {app.scenario.rule} · {app.scenario.hint}
          </span>
        </span>

        <span className={styles.stripSpacer} />

        <span className={styles.stripGroup}>
          <Button
            size="small"
            icon={<Icon name="refresh" size={13} />}
            onClick={() => app.refresh()}
            loading={incidents.loading && !incidents.data}
          >
            刷新
          </Button>
          <Segmented
            size="small"
            value={autoRefresh ? 'on' : 'off'}
            onChange={(v) => setAutoRefresh(v === 'on')}
            options={[
              { label: '手动', value: 'off' },
              { label: '自动 20s', value: 'on' },
            ]}
          />
        </span>
      </div>

      <main className={styles.main}>{children}</main>

      <footer className={styles.footer}>
        <span className={styles.footerItem}>
          <Icon name="clock" size={12} />
          最近取数 {fmtClock(lastUpdated ?? new Date())} UTC
        </span>
        <span className={styles.footerItem}>
          <Icon name="external" size={12} />
          API {app.apiBase}
        </span>
        <SourceStatusStrip
          source={
            incidents.data?.source ??
            (health.data
              ? {
                  platform: health.data.sources.platform,
                  prometheus: health.data.sources.prometheus,
                  fixture: health.data.sources.fixture,
                }
              : undefined)
          }
        />
        <span className={styles.footerSpacer} />
        <span className={styles.footerItem}>
          TraceSphere v0.1 · 中国研究生操作系统开源创新大赛 · 智算云赛道 ZSvirt
        </span>
      </footer>

      <Modal
        open={switchOpen}
        onCancel={() => setSwitchOpen(false)}
        onOk={() => setSwitchOpen(false)}
        title="切换数据源（构建期环境变量）"
        okText="知道了"
        cancelButtonProps={{ style: { display: 'none' } }}
        width={620}
      >
        <p style={{ fontSize: 12 }}>
          数据源模式由 <code>VITE_DATA_SOURCE</code> 在启动 / 构建时决定，修改后需重启 dev server
          或重新构建（这是刻意设计：评审必须能从页脚一眼确认当前是真实还是回放数据）。
        </p>
        <pre
          style={{
            background: '#f7f9fa',
            border: '1px solid var(--ts-rule)',
            padding: 10,
            fontSize: 11,
            fontFamily: 'var(--ts-mono)',
            whiteSpace: 'pre-wrap',
            margin: 0,
          }}
        >{`# Linux / macOS：fixture 回放（无需后端）
VITE_DATA_SOURCE=fixture npm run dev

# Linux / macOS：api 模式联调诊断服务
VITE_DATA_SOURCE=api VITE_RCA_BASE_URL=http://127.0.0.1:8010 npm run dev

# Windows PowerShell
$env:VITE_DATA_SOURCE="fixture"; npm run dev

# 也可写入 .env.local（复制 .env.example 后修改）
VITE_DATA_SOURCE=fixture`}</pre>
        <p style={{ fontSize: 12, marginTop: 10, marginBottom: 0 }}>
          当前模式：<b>{app.dataSource === 'api' ? 'api（请求真实诊断服务）' : 'fixture（本地夹具回放）'}</b>
          ，请求基址 <code>{app.apiBase}</code>。
        </p>
      </Modal>
    </div>
  );
}
