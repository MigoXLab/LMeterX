import {
  getApiBaseUrl,
  getLdapEnabled,
  getPersistAccessToken,
} from './runtimeConfig';

export type StoredUser = {
  username: string;
  display_name?: string | null;
  email?: string | null;
};

const TOKEN_KEY = 'lmeterx_token';
const TOKEN_EXP_KEY = 'lmeterx_token_exp';
const USER_KEY = 'lmeterx_user';
const COOKIE_NAME = 'access_token';
const SESSION_FLAG_COOKIE = `${COOKIE_NAME}_present`;
const SHOULD_PERSIST_TOKEN = getPersistAccessToken();
const LDAP_ENABLED = getLdapEnabled();
const API_BASE = getApiBaseUrl();

const decodeBase64 = (value: string): string => {
  try {
    // Convert JWT base64url to base64 and pad if needed
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(
      normalized.length + ((4 - (normalized.length % 4)) % 4),
      '='
    );
    return atob(padded);
  } catch {
    return '';
  }
};

const readCookie = (name: string): string | null => {
  try {
    const cookie = document.cookie || '';
    const match = cookie.match(
      new RegExp(
        `(?:^|;\\s*)${name.replace(/[-/\\^$*+?.()|[\\]{}]/g, '\\$&')}=([^;]+)`
      )
    );
    return match ? decodeURIComponent(match[1]) : null;
  } catch {
    return null;
  }
};

const getCookieToken = (): string | null => readCookie(COOKIE_NAME);

const getStoredTokenExpiry = (): number | null => {
  const exp = localStorage.getItem(TOKEN_EXP_KEY);
  if (!exp) return null;
  const parsed = Number(exp);
  if (Number.isNaN(parsed)) return null;
  return parsed;
};

const isStoredTokenExpired = () => {
  const exp = getStoredTokenExpiry();
  return Boolean(exp && Date.now() >= exp * 1000);
};

export const getToken = (): string | null => {
  const localToken = SHOULD_PERSIST_TOKEN
    ? localStorage.getItem(TOKEN_KEY)
    : null;
  if (localToken) {
    if (isStoredTokenExpired()) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TOKEN_EXP_KEY);
      return null;
    }
    return localToken;
  }
  // Fallback to a readable (non-HttpOnly) cookie token if present
  return getCookieToken();
};

const extractTokenExp = (token: string): number | null => {
  try {
    const [, payload] = token.split('.');
    if (!payload) return null;
    const decoded = decodeBase64(payload);
    const parsed = JSON.parse(decoded);
    return typeof parsed?.exp === 'number' ? parsed.exp : null;
  } catch {
    return null;
  }
};

export const saveAuth = (token: string, user?: StoredUser) => {
  if (token && SHOULD_PERSIST_TOKEN) {
    localStorage.setItem(TOKEN_KEY, token);
    const exp = extractTokenExp(token);
    if (exp) {
      localStorage.setItem(TOKEN_EXP_KEY, exp.toString());
    }
  }
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }
};

export const clearAuth = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(TOKEN_EXP_KEY);
  localStorage.removeItem(USER_KEY);
  // Ask backend to clear HttpOnly cookie; ignore failures to avoid blocking UI
  try {
    fetch(`${API_BASE}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
  } catch {
    // noop
  }
};

export const getStoredUser = (): StoredUser | null => {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredUser;
  } catch {
    return null;
  }
};

const hasSessionCookie = (): boolean =>
  Boolean(readCookie(SESSION_FLAG_COOKIE));

export const isAuthenticated = (): boolean => {
  if (!LDAP_ENABLED) {
    return true;
  }
  return Boolean(getToken()) || hasSessionCookie();
};
