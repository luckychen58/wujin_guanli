function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

export function createStore(initialState) {
  let state = deepClone(initialState);
  const listeners = new Set();

  function getState() {
    return deepClone(state);
  }

  function emit() {
    const snapshot = getState();
    listeners.forEach((listener) => listener(snapshot));
  }

  function update(updater) {
    state = typeof updater === "function" ? updater(getState()) : { ...state, ...updater };
    emit();
    return getState();
  }

  function subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return {
    getState,
    update,
    subscribe,
  };
}

