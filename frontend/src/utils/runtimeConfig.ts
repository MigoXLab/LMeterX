export type RuntimeConfig = {
  VITE_API_BASE_URL?: string;
  VITE_LDAP_ENABLED?: string | boolean;
  VITE_PERSIST_ACCESS_TOKEN?: string | boolean;
};

const normalizeEnvFlag = (value?: string | boolean): boolean => {
  if (typeof value === 'boolean') {
    return value;
  }
  const normalized = (value || '').toLowerCase().trim();
  return ['true', '1', 'yes', 'on'].includes(normalized);
};

const readRuntimeConfig = (): RuntimeConfig => {
  if (typeof window === 'undefined') {
    return {};
  }
  return window.RUNTIME_CONFIG || {};
};

export const getApiBaseUrl = (): string =>
  readRuntimeConfig().VITE_API_BASE_URL ||
  import.meta.env.VITE_API_BASE_URL ||
  '/api';

export const getLdapEnabled = (): boolean =>
  normalizeEnvFlag(
    readRuntimeConfig().VITE_LDAP_ENABLED ||
      import.meta.env.VITE_LDAP_ENABLED ||
      'false'
  );

export const getPersistAccessToken = (): boolean =>
  normalizeEnvFlag(
    readRuntimeConfig().VITE_PERSIST_ACCESS_TOKEN ||
      import.meta.env.VITE_PERSIST_ACCESS_TOKEN ||
      'true'
  );
