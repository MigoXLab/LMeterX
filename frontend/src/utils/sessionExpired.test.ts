import { beforeEach, describe, expect, it, vi } from 'vitest';

const { clearAuthMock, locationAssignMock, messageErrorMock, translateMock } =
  vi.hoisted(() => ({
    clearAuthMock: vi.fn(),
    locationAssignMock: vi.fn(),
    messageErrorMock: vi.fn(),
    translateMock: vi.fn(() => '登录状态已过期，请重新登录'),
  }));

vi.mock('antd', () => ({
  message: {
    error: messageErrorMock,
  },
}));

vi.mock('../i18n', () => ({
  default: {
    t: translateMock,
  },
}));

vi.mock('./auth', () => ({
  clearAuth: clearAuthMock,
}));

const loadSessionExpired = () => import('./sessionExpired');

describe('session expiration handling', () => {
  beforeEach(() => {
    vi.resetModules();
    clearAuthMock.mockReset();
    locationAssignMock.mockReset();
    messageErrorMock.mockReset();
    translateMock.mockClear();
    messageErrorMock.mockResolvedValue(true);
    vi.stubGlobal('window', {
      location: {
        pathname: '/jobs',
        assign: locationAssignMock,
      },
    });
  });

  it('keeps login endpoint 401 in the login error flow', async () => {
    const { handleUnauthorizedError } = await loadSessionExpired();

    const handled = handleUnauthorizedError({
      response: { status: 401 },
      config: { url: '/auth/login' },
    });

    expect(handled).toBe(false);
    expect(clearAuthMock).not.toHaveBeenCalled();
    expect(messageErrorMock).not.toHaveBeenCalled();
    expect(locationAssignMock).not.toHaveBeenCalled();
  });

  it('shows the expiration toast and redirects when stopping a task returns 401', async () => {
    const { handleUnauthorizedError } = await loadSessionExpired();

    const handled = handleUnauthorizedError({
      response: { status: 401 },
      config: { url: '/llm-tasks/stop/task-1' },
    });

    expect(handled).toBe(true);
    expect(clearAuthMock).toHaveBeenCalledOnce();
    expect(messageErrorMock).toHaveBeenCalledWith({
      content: '登录状态已过期，请重新登录',
      duration: 1.5,
    });
    await vi.waitFor(() => {
      expect(locationAssignMock).toHaveBeenCalledWith('/login');
    });
  });

  it('only shows one toast and redirects once for concurrent 401 responses', async () => {
    let closeToast: (value: boolean) => void = () => {};
    messageErrorMock.mockReturnValue(
      new Promise<boolean>(resolve => {
        closeToast = resolve;
      })
    );
    const { handleUnauthorizedError } = await loadSessionExpired();
    const unauthorizedError = {
      response: { status: 401 },
      config: { url: '/http-tasks/stop/task-1' },
    };

    const firstHandled = handleUnauthorizedError(unauthorizedError);
    const secondHandled = handleUnauthorizedError(unauthorizedError);

    expect(firstHandled).toBe(true);
    expect(secondHandled).toBe(true);
    expect(clearAuthMock).toHaveBeenCalledOnce();
    expect(messageErrorMock).toHaveBeenCalledOnce();
    expect(locationAssignMock).not.toHaveBeenCalled();

    closeToast(true);
    await vi.waitFor(() => {
      expect(locationAssignMock).toHaveBeenCalledOnce();
      expect(locationAssignMock).toHaveBeenCalledWith('/login');
    });
  });
});
