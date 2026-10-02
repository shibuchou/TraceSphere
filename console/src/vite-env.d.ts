/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_DATA_SOURCE?: 'api' | 'fixture';
  readonly VITE_RCA_BASE_URL?: string;
  readonly VITE_API_PROXY_TARGET?: string;
  readonly VITE_PLATFORM_BASE_URL?: string;
  readonly VITE_DEFAULT_SCENARIO?: string;
  readonly VITE_ENV_LABEL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module '*.json' {
  const value: unknown;
  export default value;
}
