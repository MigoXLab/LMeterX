/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_LDAP_ENABLED?: string;
  readonly VITE_PERSIST_ACCESS_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  RUNTIME_CONFIG?: {
    VITE_API_BASE_URL?: string;
    VITE_LDAP_ENABLED?: string;
    VITE_PERSIST_ACCESS_TOKEN?: string;
  };
}
