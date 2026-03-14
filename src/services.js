async function request(path, options = {}) {
  const requestOptions = {
    method: options.method ?? "GET",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  };

  const response = await fetch(path, requestOptions);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `请求失败: ${response.status}`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function applyPayload(state, payload) {
  return {
    ...state,
    pending: false,
    initialized: true,
    authRequired: false,
    error: "",
    viewModel: payload.viewModel ?? state.viewModel,
    session: payload.session ?? state.session,
    auditLogs: payload.auditLogs ?? state.auditLogs,
    adminView: payload.adminView ?? state.adminView,
  };
}

export function createServices(store) {
  async function run(action, options = {}) {
    const preserveViewModel = options.preserveViewModel ?? false;
    store.update((state) => ({ ...state, pending: true, error: "" }));
    try {
      const payload = await action();
      store.update((state) => applyPayload(state, payload));
      return payload;
    } catch (error) {
      const message = error instanceof Error ? error.message : "请求失败";
      if (error?.status === 401) {
        store.update((state) => ({
          ...state,
          pending: false,
          initialized: true,
          authRequired: true,
          error: message,
          viewModel: preserveViewModel ? state.viewModel : null,
          session: null,
          auditLogs: [],
          adminView: null,
        }));
      } else {
        store.update((state) => ({
          ...state,
          pending: false,
          initialized: true,
          error: message,
        }));
      }
      throw error;
    }
  }

  return {
    bootstrap() {
      return run(() => request("/api/view-model"));
    },
    login(credentials) {
      return run(() => request("/api/login", { method: "POST", body: credentials }));
    },
    async logout() {
      store.update((state) => ({ ...state, pending: true, error: "" }));
      try {
        await request("/api/logout", { method: "POST" });
      } finally {
        store.update((state) => ({
          ...state,
          pending: false,
          initialized: true,
          authRequired: true,
          error: "",
          viewModel: null,
          session: null,
          auditLogs: [],
          adminView: null,
        }));
      }
    },
    loadViewModel() {
      return run(() => request("/api/view-model"), { preserveViewModel: true });
    },
    createOrder(input) {
      return run(() => request("/api/orders", { method: "POST", body: input }), {
        preserveViewModel: true,
      });
    },
    shipAllocatedStock(orderId) {
      return run(() => request(`/api/orders/${orderId}/ship`, { method: "POST" }), {
        preserveViewModel: true,
      });
    },
    collectPayment(receivableId, amount) {
      return run(
        () =>
          request(`/api/receivables/${receivableId}/payments`, {
            method: "POST",
            body: { amount },
          }),
        { preserveViewModel: true }
      );
    },
    receivePurchase(taskId, quantity) {
      return run(
        () =>
          request(`/api/purchases/${taskId}/receive`, {
            method: "POST",
            body: { quantity },
          }),
        { preserveViewModel: true }
      );
    },
    createUser(input) {
      return run(() => request("/api/users", { method: "POST", body: input }), {
        preserveViewModel: true,
      });
    },
    updateUser(userId, input) {
      return run(() => request(`/api/users/${userId}/update`, { method: "POST", body: input }), {
        preserveViewModel: true,
      });
    },
    resetUserPassword(userId, password) {
      return run(
        () =>
          request(`/api/users/${userId}/reset-password`, {
            method: "POST",
            body: { password },
          }),
        { preserveViewModel: true }
      );
    },
    updateRoleMenuAccess(role, menuKeys) {
      return run(
        () =>
          request(`/api/roles/${role}/menu-access`, {
            method: "POST",
            body: { menuKeys },
          }),
        { preserveViewModel: true }
      );
    },
    resetDemoState() {
      return run(() => request("/api/reset-demo", { method: "POST" }), {
        preserveViewModel: true,
      });
    },
  };
}
