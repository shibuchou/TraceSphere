import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { HashRouter } from 'react-router-dom';
import { App as AntdApp, ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import 'antd/dist/reset.css';
import './styles/global.css';
import { AppRoutes } from './App';
import { AppProvider } from './state/AppContext';
import { COLORS } from './theme/tokens';

const root = document.getElementById('root');
if (!root) throw new Error('#root 节点缺失，请检查 index.html');

// 可选：?token=xxx 一次性写入 localStorage（诊断服务启用 TRACESPHERE_RCA_TOKEN 时使用）
try {
  const token = new URLSearchParams(window.location.search).get('token');
  if (token) window.localStorage.setItem('tracesphere.auth_token', token);
} catch {
  /* 忽略（隐私模式等） */
}

createRoot(root).render(
  <StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: COLORS.primary,
          colorInfo: COLORS.primary,
          colorSuccess: COLORS.healthy,
          colorWarning: COLORS.warning,
          colorError: COLORS.critical,
          borderRadius: 2,
          fontSize: 13,
          fontFamily:
            '"Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif',
          colorTextBase: COLORS.ink,
          colorBorder: COLORS.rule,
          colorBorderSecondary: COLORS.rule,
          controlHeightSM: 26,
          controlHeight: 30,
          wireframe: false,
        },
        components: {
          Table: { cellPaddingBlockSM: 6, headerBg: '#fafbfc' },
          Drawer: { padding: 14 },
          Card: { paddingLG: 14 },
          Descriptions: { itemPaddingBottom: 6 },
          Timeline: { itemPaddingBottom: 8 },
          Tabs: { horizontalItemPadding: '8px 0' },
        },
      }}
    >
      <HashRouter>
        <AntdApp>
          <AppProvider>
            <AppRoutes />
          </AppProvider>
        </AntdApp>
      </HashRouter>
    </ConfigProvider>
  </StrictMode>,
);
