import { Link, Navigate, Route, Routes } from 'react-router-dom';
import { AppShell } from '@/components/layout/AppShell';
import { TopologyPage } from '@/pages/TopologyPage';
import { HealthPage } from '@/pages/HealthPage';
import { IncidentsPage } from '@/pages/IncidentsPage';
import { IncidentDetailPage } from '@/pages/IncidentDetailPage';
import { DiagnosisPage } from '@/pages/DiagnosisPage';

/** 默认落地页：健康总览（先给结论，再进拓扑/告警/诊断）。 */
export function AppRoutes() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/health" replace />} />
        <Route path="/topology" element={<TopologyPage />} />
        <Route path="/health" element={<HealthPage />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/incidents/:id" element={<IncidentDetailPage />} />
        <Route path="/diagnosis" element={<DiagnosisPage />} />
        <Route
          path="*"
          element={
            <div style={{ padding: 24, fontSize: 13 }}>
              路径不存在。<Link to="/health">返回健康总览</Link>
            </div>
          }
        />
      </Routes>
    </AppShell>
  );
}
