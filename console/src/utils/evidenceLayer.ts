import type { EvidenceLayer } from '@/types';

const VALID_LAYERS = new Set<EvidenceLayer>(['application', 'container', 'vm', 'zsvirt']);

/** 旧采集器可能未填写 layer；按资源标识补齐用于展示的层级。 */
export function normalizeEvidenceLayer(layer: unknown, resourceId?: string): EvidenceLayer {
  if (typeof layer === 'string' && VALID_LAYERS.has(layer as EvidenceLayer)) return layer as EvidenceLayer;

  const id = resourceId?.toLowerCase() ?? '';
  if (id.startsWith('container:') || id.startsWith('container-')) return 'container';
  if (id.startsWith('vm:') || id.startsWith('vm-')) return 'vm';
  if (/^(task|service|process):/.test(id)) return 'application';
  return 'zsvirt';
}
