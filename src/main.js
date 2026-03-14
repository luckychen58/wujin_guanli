import { createStore } from "./store.js";
import { createServices } from "./services.js";
import { createRenderer } from "./render.js";

const root = document.querySelector("#app");
const store = createStore({
  viewModel: null,
  session: null,
  auditLogs: [],
  pending: false,
  error: "",
  authRequired: false,
  initialized: false,
});
const services = createServices(store);
const renderer = createRenderer(root, store, services);

store.subscribe(() => renderer.render());
renderer.render();
services.bootstrap().catch((error) => {
  console.error(error);
});
