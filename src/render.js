const DEMO_ACCOUNTS = [
  { username: "admin", password: "admin123", roleLabel: "系统管理员", summary: "全量权限、用户与菜单配置" },
  { username: "sales", password: "sales123", roleLabel: "销售", summary: "录入订单与查看库存" },
  { username: "warehouse", password: "warehouse123", roleLabel: "仓库", summary: "处理发货与库存查看" },
  { username: "procurement", password: "purchase123", roleLabel: "采购", summary: "处理采购入库任务" },
  { username: "finance", password: "finance123", roleLabel: "财务", summary: "登记回款与应收查看" },
];

const MENU_META = {
  dashboard: { label: "经营概览", summary: "先看销售、应收、库存和动作流。" },
  orders: { label: "订单中心", summary: "销售录单、仓库发货都在这里协同。" },
  purchases: { label: "采购补货", summary: "把欠货订单转成可跟踪的补货任务。" },
  receivables: { label: "应收回款", summary: "围绕账期、应收余额和回款登记展开。" },
  inventory: { label: "库存总览", summary: "在手、锁库、可用与安全库存一屏看清。" },
  audit: { label: "操作审计", summary: "登录、业务动作和系统配置都有留痕。" },
  users: { label: "用户管理", summary: "新增账号、分配角色、启停用和重置密码。" },
  "menu-config": { label: "菜单权限", summary: "按角色控制前端可见菜单范围。" },
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function currency(value) {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
  }).format(value ?? 0);
}

function formatDate(value, options) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "--";
  return new Intl.DateTimeFormat("zh-CN", options).format(parsed);
}

function dateTime(value) {
  return formatDate(value, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function dateOnly(value) {
  return formatDate(value, { year: "numeric", month: "2-digit", day: "2-digit" });
}

function toneForStatus(status) {
  const text = String(status ?? "");
  if (text === "ACTIVE" || text.includes("已闭环") || text.includes("已完成") || text.includes("已收清")) return "tone-success";
  if (text === "DISABLED" || text.includes("逾期") || text.includes("超信用")) return "tone-danger";
  if (text.includes("待采购") || text.includes("欠货") || text.includes("断货") || text.includes("低于")) return "tone-warning";
  if (text.includes("待") || text.includes("部分") || text.includes("项权限") || text.includes("个菜单")) return "tone-info";
  return "tone-neutral";
}

function renderStatus(status) {
  return `<span class="status ${toneForStatus(status)}">${escapeHtml(status)}</span>`;
}

function createDraftLine(id) {
  return { id };
}

function nextDraftId(lines) {
  return lines.reduce((max, line) => Math.max(max, line.id), 0) + 1;
}

function hasPermission(session, permission) {
  return Boolean(session?.permissions?.includes(permission));
}

function renderGuard(message) {
  return `<div class="forbidden-card">${escapeHtml(message)}</div>`;
}

function menuMeta(menuKey) {
  return MENU_META[menuKey] || { label: menuKey, summary: "未配置菜单说明。" };
}

function menuSummary(menuKeys) {
  if (!menuKeys?.length) return "未分配菜单";
  return menuKeys.map((menuKey) => menuMeta(menuKey).label).join(" / ");
}

function renderCustomerOptions(customers) {
  return customers
    .map((customer) => `<option value="${escapeHtml(customer.id)}">${escapeHtml(customer.name)} | ${escapeHtml(customer.tier)} 类客户</option>`)
    .join("");
}

function renderProductOptions(products) {
  return products
    .map((product) => `<option value="${escapeHtml(product.id)}">${escapeHtml(product.name)} | ${escapeHtml(product.sku)} | 库存 ${product.stock.onHand}</option>`)
    .join("");
}

function renderRoleOptions(roles, currentRole) {
  return roles
    .map((role) => `<option value="${escapeHtml(role.key)}" ${role.key === currentRole ? "selected" : ""}>${escapeHtml(role.label)}</option>`)
    .join("");
}

function renderOrderLines(order) {
  return order.lines
    .map((line) => {
      const shortage = line.shortageQty > 0 ? ` / 欠 ${line.shortageQty}${line.unit}` : "";
      const shipped = line.shippedQty > 0 ? ` / 已发 ${line.shippedQty}${line.unit}` : "";
      return `<span>${escapeHtml(line.productName)} (${escapeHtml(line.sku)}) x ${line.quantity}${escapeHtml(line.unit)}${shortage}${shipped}</span>`;
    })
    .join("");
}

function renderAuditDetails(details) {
  const entries = Object.entries(details || {});
  if (!entries.length) return "无附加字段";
  return entries.map(([key, value]) => `${key}: ${typeof value === "object" ? JSON.stringify(value) : value}`).join(" / ");
}

export function createRenderer(root, store, services) {
  const uiState = {
    draftLines: [createDraftLine(1)],
    activeMenu: "dashboard",
    selectedUserId: "",
  };

  const resetDraft = () => {
    uiState.draftLines = [createDraftLine(1)];
  };

  function ensureActiveMenu(snapshot) {
    const visibleMenus = snapshot.session?.menus ?? [];
    if (!visibleMenus.length) {
      uiState.activeMenu = "";
      return;
    }
    if (!visibleMenus.includes(uiState.activeMenu)) {
      uiState.activeMenu = visibleMenus[0];
    }
  }

  function ensureSelectedUser(snapshot) {
    const users = snapshot.adminView?.users ?? [];
    if (!users.length) {
      uiState.selectedUserId = "";
      return;
    }
    if (!users.find((user) => user.id === uiState.selectedUserId)) {
      uiState.selectedUserId = users[0].id;
    }
  }

  function renderLoading(snapshot) {
    root.innerHTML = `<div class="page"><section class="hero"><div class="hero-banner"><span class="hero-kicker">Hardware OMS / API</span><h1>正在连接服务</h1><p>正在加载会话状态、数据库视图和后台配置。</p></div><aside class="hero-side"><div class="empty-state">${escapeHtml(snapshot.error || "正在加载中...")}</div></aside></section></div>`;
  }

  function renderLogin(snapshot) {
    root.innerHTML = `<div class="page"><section class="login-shell"><article class="hero-banner"><span class="hero-kicker">Hardware OMS / Auth</span><h1>登录后进入按角色裁剪的后台</h1><p>这一版已经补上用户管理和菜单级权限配置，可以直接切账号验证页面差异。</p><div class="demo-grid">${DEMO_ACCOUNTS.map((account) => `<button type="button" class="demo-card" data-fill-login="${escapeHtml(account.username)}" data-fill-password="${escapeHtml(account.password)}"><strong>${escapeHtml(account.username)}</strong><span>${escapeHtml(account.roleLabel)}</span><small>${escapeHtml(account.summary)}</small><small>密码：${escapeHtml(account.password)}</small></button>`).join("")}</div></article><aside class="login-card"><span class="hero-kicker">账号登录</span><h2>输入用户名和密码</h2><p class="login-copy">会话通过 HttpOnly Cookie 保持，页面菜单按角色动态可见。</p>${snapshot.error ? `<div class="empty-state">${escapeHtml(snapshot.error)}</div>` : ""}<form id="login-form" class="login-form"><div class="field"><label for="login-username">用户名</label><input id="login-username" name="username" placeholder="例如：admin" ${snapshot.pending ? "disabled" : ""} /></div><div class="field"><label for="login-password">密码</label><input id="login-password" name="password" type="password" placeholder="输入密码" ${snapshot.pending ? "disabled" : ""} /></div><button type="submit" class="btn btn-primary" ${snapshot.pending ? "disabled" : ""}>登录系统</button></form></aside></section></div>`;
    bindAuthEvents();
  }

  function renderTopStrip(snapshot) {
    const session = snapshot.session;
    const currentUser = session?.currentUser;
    return `<div class="top-strip"><div class="top-strip-info"><span class="hero-kicker">已登录</span><span class="user-chip">${escapeHtml(currentUser?.displayName ?? "")}</span>${renderStatus(currentUser?.roleLabel ?? "")}${renderStatus(`${session?.permissions?.length ?? 0} 项权限`)}${renderStatus(`${session?.menus?.length ?? 0} 个菜单`)}</div><div class="actions">${snapshot.pending ? renderStatus("同步中") : renderStatus("在线")}<button type="button" class="btn btn-secondary" id="logout-btn" ${snapshot.pending ? "disabled" : ""}>退出登录</button></div></div>`;
  }

  function renderMenuNavigation(snapshot) {
    const menus = snapshot.session?.menus ?? [];
    return `<section class="menu-shell"><div class="menu-list">${menus.map((menuKey) => { const meta = menuMeta(menuKey); const activeClass = menuKey === uiState.activeMenu ? "menu-tab-active" : ""; return `<button type="button" class="menu-tab ${activeClass}" data-menu-key="${escapeHtml(menuKey)}"><strong>${escapeHtml(meta.label)}</strong><small>${escapeHtml(meta.summary)}</small></button>`; }).join("")}</div></section>`;
  }

  function renderWorkspaceHero(snapshot) {
    const view = snapshot.viewModel;
    const activeMeta = menuMeta(uiState.activeMenu);
    const canResetDemo = hasPermission(snapshot.session, "system:reset");
    return `<section class="hero"><div class="hero-banner"><span class="hero-kicker">Workspace</span><h1>${escapeHtml(activeMeta.label)}</h1><p>${escapeHtml(activeMeta.summary)}</p><div class="tag-row">${renderStatus(`${view.dashboard.readyToShip} 单待出库`)}${renderStatus(`${view.dashboard.shortageOrders} 单欠货`)}${renderStatus(`${view.dashboard.lowStockCount} 个库存预警`)}</div><div class="button-row">${canResetDemo ? `<button type="button" class="btn btn-secondary" id="reset-demo" ${snapshot.pending ? "disabled" : ""}>重置演示数据</button>` : ""}</div></div><aside class="hero-side"><div class="highlight"><span class="hero-kicker">今日视图</span><strong>${escapeHtml(view.now)}</strong><div class="tag-row">${renderStatus(currency(view.dashboard.totalSales))}${renderStatus(currency(view.dashboard.outstandingReceivables))}</div></div><div class="kpi-list"><div class="kpi-item"><div><strong>活跃订单</strong><small>仍在履约、补货或回款中</small></div><div><strong>${view.dashboard.activeOrders}</strong><small>当前总量</small></div></div><div class="kpi-item"><div><strong>库存预警</strong><small>低于安全库存或断货</small></div><div><strong>${view.dashboard.lowStockCount}</strong><small>待处理</small></div></div><div class="kpi-item"><div><strong>待发货</strong><small>已锁库但尚未出库</small></div><div><strong>${view.dashboard.readyToShip}</strong><small>订单数</small></div></div></div></aside></section>`;
  }

  function renderOverviewSection(snapshot) {
    const view = snapshot.viewModel;
    const lowStock = view.inventory.filter((product) => product.health !== "健康").slice(0, 6);
    const recentOrders = view.orders.slice(0, 5);
    return `<section class="metrics"><article class="metric-card"><h3>活跃订单</h3><div class="metric-value">${view.dashboard.activeOrders}</div><div class="metric-footnote">仍在履约、补货或回款中</div></article><article class="metric-card"><h3>累计销售额</h3><div class="metric-value">${currency(view.dashboard.totalSales)}</div><div class="metric-footnote">数据库实时汇总</div></article><article class="metric-card"><h3>未回款</h3><div class="metric-value">${currency(view.dashboard.outstandingReceivables)}</div><div class="metric-footnote">用于判断应收风险</div></article><article class="metric-card"><h3>库存预警</h3><div class="metric-value">${view.dashboard.lowStockCount}</div><div class="metric-footnote">低于安全库存或断货</div></article></section><section class="dashboard-grid"><div class="stack"><section class="panel"><div class="panel-header"><div><h2>重点客户</h2><p>按累计销售额排序，方便销售优先跟进。</p></div></div>${view.topCustomers.length === 0 ? `<div class="empty-state">当前还没有客户成交数据。</div>` : `<div class="kpi-list">${view.topCustomers.map((customer) => `<div class="kpi-item"><div><strong>${escapeHtml(customer.name)}</strong><small>${escapeHtml(customer.city)} / ${escapeHtml(customer.owner)}</small></div><div><strong>${currency(customer.orderAmount)}</strong><small>未回款 ${currency(customer.outstandingAmount)}</small></div></div>`).join("")}</div>`}</section><section class="panel"><div class="panel-header"><div><h2>最近订单</h2><p>快速确认履约、欠货和回款状态。</p></div></div>${recentOrders.length === 0 ? `<div class="empty-state">还没有订单。</div>` : `<div class="table-shell"><table><thead><tr><th>订单</th><th>状态</th><th>金额</th></tr></thead><tbody>${recentOrders.map((order) => `<tr><td><strong>${escapeHtml(order.id)}</strong><div class="meta">${escapeHtml(order.customerName)} / ${dateTime(order.createdAt)}</div></td><td><div class="status-wrap">${renderStatus(order.status)}${renderStatus(order.shipmentStatus)}${renderStatus(order.paymentStatus)}</div></td><td><strong>${currency(order.totalAmount)}</strong><div class="meta">待补 ${order.shortageQty} / 已发 ${order.shippedQty}</div></td></tr>`).join("")}</tbody></table></div>`}</section></div><div class="stack"><section class="panel"><div class="panel-header"><div><h2>最近动作</h2><p>库存、采购、回款动作统一留在这里。</p></div></div>${view.activityFeed.length === 0 ? `<div class="empty-state">动作流为空。</div>` : `<div class="timeline">${view.activityFeed.map((item) => `<div class="timeline-item"><div><strong>${escapeHtml(item.type)} / ${escapeHtml(item.productName)}</strong><small>${escapeHtml(item.note)}</small></div><div><strong>${item.quantity}</strong><small>${dateTime(item.happenedAt)}</small></div></div>`).join("")}</div>`}</section><section class="panel"><div class="panel-header"><div><h2>库存风险</h2><p>优先关注断货和低于安全库存的商品。</p></div></div>${lowStock.length === 0 ? `<div class="empty-state">当前库存状态健康。</div>` : `<div class="kpi-list">${lowStock.map((product) => `<div class="kpi-item"><div><strong>${escapeHtml(product.name)}</strong><small>${escapeHtml(product.sku)} / ${escapeHtml(product.brand)}</small></div><div><strong>${product.available}</strong><small>${escapeHtml(product.health)}</small></div></div>`).join("")}</div>`}</section></div></section>`;
  }

  function renderOrdersSection(snapshot) {
    const view = snapshot.viewModel;
    const session = snapshot.session;
    const canCreateOrder = hasPermission(session, "orders:create");
    const canShipOrder = hasPermission(session, "orders:ship");
    const disabledAttr = snapshot.pending ? "disabled" : "";
    return `<section class="dashboard-grid"><div class="stack"><section class="panel"><div class="panel-header"><div><h2>新建订单</h2><p>销售和管理员可录入订单，系统会自动锁库并生成欠货采购。</p></div>${canCreateOrder ? `<button type="button" class="btn btn-primary" id="add-line" ${disabledAttr}>继续加一行商品</button>` : ""}</div>${canCreateOrder ? `<form id="order-form" class="stack"><div class="form-grid"><div class="field"><label for="customer-id">客户</label><select id="customer-id" name="customerId" ${disabledAttr}>${renderCustomerOptions(view.customers)}</select></div><div class="field"><label for="sales-note">备注</label><input id="sales-note" name="notes" placeholder="例如：项目急单" ${disabledAttr} /></div><div class="field field-wide"><label>订单明细</label><div class="line-items">${uiState.draftLines.map((line, index) => `<div class="line-row"><div class="field"><label for="product-${line.id}">商品 ${index + 1}</label><select id="product-${line.id}" name="product-${line.id}" ${disabledAttr}>${renderProductOptions(view.products)}</select></div><div class="field"><label for="qty-${line.id}">数量</label><input id="qty-${line.id}" name="qty-${line.id}" type="number" min="1" value="1" ${disabledAttr} /></div><button type="button" class="btn btn-ghost" data-remove-line="${line.id}" ${uiState.draftLines.length === 1 || snapshot.pending ? "disabled" : ""}>删除</button></div>`).join("")}</div></div></div><div class="actions"><button class="btn btn-primary" type="submit" ${disabledAttr}>创建订单</button></div></form>` : renderGuard("当前账号没有录入订单的权限。")}</section></div><div class="stack"><section class="panel"><div class="panel-header"><div><h2>订单列表</h2><p>仓库和管理员可以直接执行已锁库存出库。</p></div></div>${view.orders.length === 0 ? `<div class="empty-state">还没有订单。</div>` : `<div class="table-shell"><table><thead><tr><th>订单</th><th>商品明细</th><th>状态</th><th>金额</th><th>操作</th></tr></thead><tbody>${view.orders.map((order) => `<tr><td><strong>${escapeHtml(order.id)}</strong><div class="meta">${escapeHtml(order.customerName)} / ${dateTime(order.createdAt)}</div><div class="meta">应收 ${currency(order.outstandingAmount)}</div></td><td><div class="order-lines">${renderOrderLines(order)}</div></td><td><div class="status-wrap">${renderStatus(order.status)}${renderStatus(order.shipmentStatus)}${renderStatus(order.paymentStatus)}</div>${order.reviewFlags.length > 0 ? `<div class="flag-wrap">${order.reviewFlags.map((flag) => renderStatus(flag)).join("")}</div>` : ""}</td><td><strong>${currency(order.totalAmount)}</strong><div class="meta">已发 ${order.shippedQty} / 下单 ${order.orderedQty}</div><div class="meta">待补 ${order.shortageQty}</div></td><td>${canShipOrder ? `<button type="button" class="btn btn-secondary" data-ship-order="${escapeHtml(order.id)}" ${order.shippableQty <= 0 || snapshot.pending ? "disabled" : ""}>发出已锁库存</button>` : `<span class="meta">当前角色不可发货</span>`}</td></tr>`).join("")}</tbody></table></div>`}</section></div></section>`;
  }

  function renderPurchasesSection(snapshot) {
    const view = snapshot.viewModel;
    const canReceivePurchase = hasPermission(snapshot.session, "purchases:receive");
    return `<section class="stack"><section class="panel"><div class="panel-header"><div><h2>采购补货任务</h2><p>欠货和安全库存缺口会自动汇总成采购任务。</p></div></div>${view.purchaseTasks.length === 0 ? `<div class="empty-state">目前没有待处理采购任务。</div>` : `<div class="table-shell"><table><thead><tr><th>任务</th><th>关联订单</th><th>数量</th><th>状态</th><th>操作</th></tr></thead><tbody>${view.purchaseTasks.map((task) => `<tr><td><strong>${escapeHtml(task.id)}</strong><div class="meta">${escapeHtml(task.product?.name ?? "未知商品")}</div><div class="meta">${escapeHtml(task.product?.sku ?? "")}</div></td><td><div class="order-lines">${task.linkedOrders.map((order) => `<span>${escapeHtml(order.id)} / ${escapeHtml(order.customerName)}</span>`).join("")}</div></td><td><strong>欠货 ${task.shortageQty}</strong><div class="meta">建议采购 ${task.recommendedQty}</div><div class="meta">已入库 ${task.receivedQty}</div></td><td>${renderStatus(task.status)}</td><td>${canReceivePurchase ? `<button type="button" class="btn btn-secondary" data-receive-task="${escapeHtml(task.id)}" data-default-qty="${task.recommendedQty || task.shortageQty || 1}" ${task.status === "已完成" || snapshot.pending ? "disabled" : ""}>执行采购入库</button>` : `<span class="meta">当前角色不可入库</span>`}</td></tr>`).join("")}</tbody></table></div>`}</section></section>`;
  }

  function renderReceivablesSection(snapshot) {
    const view = snapshot.viewModel;
    const canCollectPayment = hasPermission(snapshot.session, "receivables:collect");
    return `<section class="stack"><section class="panel"><div class="panel-header"><div><h2>应收回款</h2><p>按到期日排序，方便财务优先处理高风险账款。</p></div></div>${view.receivables.length === 0 ? `<div class="empty-state">当前没有应收记录。</div>` : `<div class="table-shell"><table><thead><tr><th>客户 / 单号</th><th>账期</th><th>金额</th><th>状态</th><th>操作</th></tr></thead><tbody>${view.receivables.map((receivable) => `<tr><td><strong>${escapeHtml(receivable.customer?.name ?? "")}</strong><div class="meta">${escapeHtml(receivable.orderId)}</div></td><td><strong>${dateOnly(receivable.dueDate)}</strong><div class="meta">创建 ${dateOnly(receivable.createdAt)}</div></td><td><strong>${currency(receivable.outstandingAmount)}</strong><div class="meta">总额 ${currency(receivable.totalAmount)}</div><div class="meta">已收 ${currency(receivable.receivedAmount)}</div></td><td>${renderStatus(receivable.status)}</td><td>${canCollectPayment ? `<button type="button" class="btn btn-secondary" data-pay-receivable="${escapeHtml(receivable.id)}" data-default-amount="${receivable.outstandingAmount}" ${receivable.outstandingAmount <= 0 || snapshot.pending ? "disabled" : ""}>登记回款</button>` : `<span class="meta">当前角色不可回款</span>`}</td></tr>`).join("")}</tbody></table></div>`}</section></section>`;
  }

  function renderInventorySection(snapshot) {
    const view = snapshot.viewModel;
    return `<section class="stack"><section class="panel"><div class="panel-header"><div><h2>库存总览</h2><p>所有角色都能查看库存现状和预警状态。</p></div></div><div class="table-shell"><table><thead><tr><th>商品</th><th>在手 / 锁定 / 可用</th><th>安全库存</th><th>状态</th></tr></thead><tbody>${view.inventory.map((product) => `<tr><td><strong>${escapeHtml(product.name)}</strong><div class="meta">${escapeHtml(product.sku)} / ${escapeHtml(product.unit)}</div></td><td><strong>${product.stock.onHand} / ${product.stock.reserved} / ${product.available}</strong><div class="meta">品牌 ${escapeHtml(product.brand)}</div></td><td>${product.stock.reorderPoint}</td><td>${renderStatus(product.health)}</td></tr>`).join("")}</tbody></table></div></section></section>`;
  }

  function renderAuditSection(snapshot) {
    if (!hasPermission(snapshot.session, "audit:view")) {
      return renderGuard("当前账号没有查看操作审计的权限。");
    }
    return `<section class="stack"><section class="panel"><div class="panel-header"><div><h2>操作审计</h2><p>系统记录最近登录、业务动作和配置类操作。</p></div></div>${(snapshot.auditLogs || []).length === 0 ? `<div class="empty-state">当前还没有审计记录。</div>` : `<div class="audit-list">${snapshot.auditLogs.map((item) => `<div class="audit-item"><div><strong>${escapeHtml(item.displayName)} / ${escapeHtml(item.roleLabel)}</strong><small>${escapeHtml(item.action)} · ${escapeHtml(item.entityType)} · ${escapeHtml(item.entityId)}</small><small>${escapeHtml(renderAuditDetails(item.details))}</small></div><div><strong>${escapeHtml(item.username)}</strong><small>${dateTime(item.happenedAt)}</small></div></div>`).join("")}</div>`}</section></section>`;
  }

  function renderUsersSection(snapshot) {
    if (!hasPermission(snapshot.session, "users:manage")) {
      return renderGuard("当前账号没有管理用户的权限。");
    }
    const adminView = snapshot.adminView;
    const users = adminView?.users ?? [];
    const roles = adminView?.accessControl?.roles ?? [];
    const selectedUser = users.find((user) => user.id === uiState.selectedUserId) || null;
    return `<section class="admin-grid"><section class="panel"><div class="panel-header"><div><h2>新增用户</h2><p>创建新账号时即可分配角色和初始状态。</p></div></div><form id="create-user-form" class="stack"><div class="form-grid"><div class="field"><label for="new-username">用户名</label><input id="new-username" name="username" placeholder="如：sales-east" ${snapshot.pending ? "disabled" : ""} /></div><div class="field"><label for="new-display-name">显示名称</label><input id="new-display-name" name="displayName" placeholder="如：华东销售" ${snapshot.pending ? "disabled" : ""} /></div><div class="field"><label for="new-role">角色</label><select id="new-role" name="role" ${snapshot.pending ? "disabled" : ""}>${renderRoleOptions(roles, "sales")}</select></div><div class="field"><label for="new-status">状态</label><select id="new-status" name="status" ${snapshot.pending ? "disabled" : ""}><option value="ACTIVE">启用</option><option value="DISABLED">停用</option></select></div><div class="field field-wide"><label for="new-password">初始密码</label><input id="new-password" name="password" type="password" placeholder="至少 6 位" ${snapshot.pending ? "disabled" : ""} /></div></div><div class="actions"><button type="submit" class="btn btn-primary" ${snapshot.pending ? "disabled" : ""}>创建用户</button></div></form></section><section class="panel"><div class="panel-header"><div><h2>编辑用户</h2><p>切换角色和停用账号会立即影响后续会话。</p></div></div>${selectedUser ? `<div class="detail-card"><div class="detail-row"><strong>${escapeHtml(selectedUser.displayName)}</strong><small>${escapeHtml(selectedUser.username)}</small></div><div class="tag-row">${renderStatus(selectedUser.roleLabel)}${renderStatus(selectedUser.status === "ACTIVE" ? "ACTIVE" : "DISABLED")}${renderStatus(`${selectedUser.activeSessionCount} 个在线会话`)}</div><div class="subtle-tip">最近登录：${escapeHtml(selectedUser.lastSeenAt ? dateTime(selectedUser.lastSeenAt) : "从未登录")}<br/>可见菜单：${escapeHtml(menuSummary(selectedUser.menus))}</div></div><form id="edit-user-form" class="stack"><div class="form-grid"><div class="field"><label for="edit-display-name">显示名称</label><input id="edit-display-name" name="displayName" value="${escapeHtml(selectedUser.displayName)}" ${snapshot.pending ? "disabled" : ""} /></div><div class="field"><label for="edit-role">角色</label><select id="edit-role" name="role" ${snapshot.pending ? "disabled" : ""}>${renderRoleOptions(roles, selectedUser.role)}</select></div><div class="field"><label for="edit-status">状态</label><select id="edit-status" name="status" ${snapshot.pending ? "disabled" : ""}><option value="ACTIVE" ${selectedUser.status === "ACTIVE" ? "selected" : ""}>启用</option><option value="DISABLED" ${selectedUser.status === "DISABLED" ? "selected" : ""}>停用</option></select></div><div class="field"><label>账号能力</label><div class="subtle-tip">${escapeHtml(`${selectedUser.permissions.length} 项操作权限`)}</div></div></div><div class="actions"><button type="submit" class="btn btn-primary" ${snapshot.pending ? "disabled" : ""}>保存用户信息</button><button type="button" class="btn btn-secondary" data-reset-password="${escapeHtml(selectedUser.id)}" ${snapshot.pending ? "disabled" : ""}>重置密码</button></div></form>` : `<div class="empty-state">请选择一个用户后再编辑。</div>`}</section><section class="panel admin-span"><div class="panel-header"><div><h2>用户列表</h2><p>默认管理员账号固定保留，避免系统完全失管。</p></div></div>${users.length === 0 ? `<div class="empty-state">当前没有用户。</div>` : `<div class="table-shell"><table><thead><tr><th>账号</th><th>角色 / 状态</th><th>菜单</th><th>最近登录</th><th>操作</th></tr></thead><tbody>${users.map((user) => `<tr class="${user.id === uiState.selectedUserId ? "row-selected" : ""}"><td><strong>${escapeHtml(user.displayName)}</strong><div class="meta">${escapeHtml(user.username)}</div></td><td><div class="status-wrap">${renderStatus(user.roleLabel)}${renderStatus(user.status === "ACTIVE" ? "ACTIVE" : "DISABLED")}</div><div class="meta">${user.activeSessionCount} 个在线会话</div></td><td><div class="menu-summary">${escapeHtml(menuSummary(user.menus))}</div></td><td><strong>${escapeHtml(user.lastSeenAt ? dateTime(user.lastSeenAt) : "从未登录")}</strong><div class="meta">创建于 ${dateOnly(user.createdAt)}</div></td><td><div class="actions"><button type="button" class="btn btn-secondary" data-select-user="${escapeHtml(user.id)}" ${snapshot.pending ? "disabled" : ""}>查看 / 编辑</button><button type="button" class="btn btn-ghost" data-reset-password="${escapeHtml(user.id)}" ${snapshot.pending ? "disabled" : ""}>重置密码</button></div></td></tr>`).join("")}</tbody></table></div>`}</section></section>`;
  }

  function renderMenuConfigSection(snapshot) {
    if (!hasPermission(snapshot.session, "menus:manage")) {
      return renderGuard("当前账号没有配置菜单权限的权限。");
    }
    const accessControl = snapshot.adminView?.accessControl;
    const roles = accessControl?.roles ?? [];
    const menuCatalog = accessControl?.menuCatalog ?? [];
    const roleMenus = accessControl?.roleMenus ?? {};
    return `<section class="stack"><section class="panel"><div class="panel-header"><div><h2>菜单级权限配置</h2><p>这里控制的是“页面可见性”，接口动作权限仍由角色能力决定。</p></div></div><div class="subtle-tip">例如给销售开放“采购补货”菜单，只会让他看见页面；如果没有采购入库权限，按钮依然不可操作。</div></section>${roles.map((role) => { const allowedMenus = new Set(roleMenus[role.key] || []); return `<form class="panel role-menu-card" data-role-menu-form="${escapeHtml(role.key)}"><div class="panel-header"><div><h2>${escapeHtml(role.label)}</h2><p>${role.userCount} 个账号正在使用这个角色。</p></div><button type="submit" class="btn btn-primary" ${snapshot.pending ? "disabled" : ""}>保存 ${escapeHtml(role.label)} 菜单</button></div><div class="checkbox-grid">${menuCatalog.map((menu) => `<label class="checkbox-card"><input type="checkbox" name="menuKeys" value="${escapeHtml(menu.key)}" ${allowedMenus.has(menu.key) ? "checked" : ""} ${snapshot.pending ? "disabled" : ""} /><span>${escapeHtml(menu.label)}</span><small>${escapeHtml(menu.description)}</small></label>`).join("")}</div></form>`; }).join("")}</section>`;
  }

  function renderActiveSection(snapshot) {
    switch (uiState.activeMenu) {
      case "dashboard":
        return renderOverviewSection(snapshot);
      case "orders":
        return renderOrdersSection(snapshot);
      case "purchases":
        return renderPurchasesSection(snapshot);
      case "receivables":
        return renderReceivablesSection(snapshot);
      case "inventory":
        return renderInventorySection(snapshot);
      case "audit":
        return renderAuditSection(snapshot);
      case "users":
        return renderUsersSection(snapshot);
      case "menu-config":
        return renderMenuConfigSection(snapshot);
      default:
        return renderGuard("当前没有可展示的菜单，请联系管理员分配。");
    }
  }

  function renderDashboard(snapshot) {
    ensureActiveMenu(snapshot);
    ensureSelectedUser(snapshot);
    const visibleMenus = snapshot.session?.menus ?? [];
    root.innerHTML = `<div class="page">${snapshot.error ? `<div class="empty-state">${escapeHtml(snapshot.error)}</div>` : ""}${renderTopStrip(snapshot)}${visibleMenus.length ? `${renderMenuNavigation(snapshot)}${renderWorkspaceHero(snapshot)}${renderActiveSection(snapshot)}` : renderGuard("当前角色还没有被分配任何菜单，请先用管理员账号去“菜单权限”里配置。")}<div class="footer-note">当前版本已经支持角色菜单可见性、用户管理和基础操作审计。</div></div>`;
    bindDashboardEvents(snapshot);
  }

  function bindAuthEvents() {
    root.querySelector("#login-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(event.currentTarget);
      try {
        await services.login({
          username: String(formData.get("username") ?? ""),
          password: String(formData.get("password") ?? ""),
        });
      } catch (error) {
        window.alert(error.message);
      }
    });

    root.querySelectorAll("[data-fill-login]").forEach((button) => {
      button.addEventListener("click", () => {
        root.querySelector("#login-username").value = button.getAttribute("data-fill-login") || "";
        root.querySelector("#login-password").value = button.getAttribute("data-fill-password") || "";
      });
    });
  }

  function bindDashboardEvents(snapshot) {
    root.querySelector("#logout-btn")?.addEventListener("click", async () => {
      await services.logout();
    });

    root.querySelector("#reset-demo")?.addEventListener("click", async () => {
      const confirmed = window.confirm("这会清空数据库里的演示业务数据，并重新生成示例订单。是否继续？");
      if (!confirmed) return;
      resetDraft();
      try {
        await services.resetDemoState();
      } catch (error) {
        window.alert(error.message);
      }
    });

    root.querySelectorAll("[data-menu-key]").forEach((button) => {
      button.addEventListener("click", () => {
        uiState.activeMenu = button.getAttribute("data-menu-key") || "";
        render();
      });
    });

    root.querySelector("#add-line")?.addEventListener("click", () => {
      if (snapshot.pending) return;
      uiState.draftLines.push(createDraftLine(nextDraftId(uiState.draftLines)));
      render();
    });

    root.querySelectorAll("[data-remove-line]").forEach((button) => {
      button.addEventListener("click", () => {
        if (uiState.draftLines.length === 1 || snapshot.pending) return;
        const lineId = Number(button.getAttribute("data-remove-line"));
        uiState.draftLines = uiState.draftLines.filter((line) => line.id !== lineId);
        render();
      });
    });

    root.querySelector("#order-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(event.currentTarget);
      const lines = uiState.draftLines.map((line) => ({ productId: String(formData.get(`product-${line.id}`) ?? ""), quantity: Number(formData.get(`qty-${line.id}`)) })).filter((line) => line.productId && line.quantity > 0);
      try {
        await services.createOrder({
          customerId: String(formData.get("customerId") ?? ""),
          notes: String(formData.get("notes") ?? ""),
          lines,
        });
        resetDraft();
        render();
      } catch (error) {
        window.alert(error.message);
      }
    });

    root.querySelectorAll("[data-ship-order]").forEach((button) => {
      button.addEventListener("click", async () => {
        try {
          await services.shipAllocatedStock(String(button.getAttribute("data-ship-order")));
        } catch (error) {
          window.alert(error.message);
        }
      });
    });

    root.querySelectorAll("[data-pay-receivable]").forEach((button) => {
      button.addEventListener("click", async () => {
        const defaultAmount = Number(button.getAttribute("data-default-amount")) || 0;
        const value = window.prompt("输入本次回款金额", String(defaultAmount));
        if (value === null) return;
        try {
          await services.collectPayment(String(button.getAttribute("data-pay-receivable")), Number(value));
        } catch (error) {
          window.alert(error.message);
        }
      });
    });

    root.querySelectorAll("[data-receive-task]").forEach((button) => {
      button.addEventListener("click", async () => {
        const defaultQty = Number(button.getAttribute("data-default-qty")) || 1;
        const value = window.prompt("输入本次采购到货数量", String(defaultQty));
        if (value === null) return;
        try {
          await services.receivePurchase(String(button.getAttribute("data-receive-task")), Number(value));
        } catch (error) {
          window.alert(error.message);
        }
      });
    });

    root.querySelector("#create-user-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(event.currentTarget);
      try {
        await services.createUser({
          username: String(formData.get("username") ?? ""),
          displayName: String(formData.get("displayName") ?? ""),
          role: String(formData.get("role") ?? ""),
          status: String(formData.get("status") ?? ""),
          password: String(formData.get("password") ?? ""),
        });
        const users = store.getState().adminView?.users ?? [];
        uiState.selectedUserId = users[users.length - 1]?.id ?? uiState.selectedUserId;
        render();
        window.alert("用户已创建。");
      } catch (error) {
        window.alert(error.message);
      }
    });

    root.querySelector("#edit-user-form")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!uiState.selectedUserId) return;
      const formData = new FormData(event.currentTarget);
      try {
        await services.updateUser(uiState.selectedUserId, {
          displayName: String(formData.get("displayName") ?? ""),
          role: String(formData.get("role") ?? ""),
          status: String(formData.get("status") ?? ""),
        });
        render();
        window.alert("用户信息已保存。");
      } catch (error) {
        window.alert(error.message);
      }
    });

    root.querySelectorAll("[data-select-user]").forEach((button) => {
      button.addEventListener("click", () => {
        uiState.selectedUserId = button.getAttribute("data-select-user") || "";
        render();
      });
    });

    root.querySelectorAll("[data-reset-password]").forEach((button) => {
      button.addEventListener("click", async () => {
        const password = window.prompt("输入新密码（至少 6 位）", "");
        if (password === null) return;
        try {
          await services.resetUserPassword(String(button.getAttribute("data-reset-password")), password);
          window.alert("密码已重置，目标账号需要重新登录。");
        } catch (error) {
          window.alert(error.message);
        }
      });
    });

    root.querySelectorAll("[data-role-menu-form]").forEach((form) => {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const role = form.getAttribute("data-role-menu-form") || "";
        const formData = new FormData(form);
        try {
          await services.updateRoleMenuAccess(role, formData.getAll("menuKeys").map((value) => String(value)));
          render();
          window.alert(`已保存 ${role} 的菜单配置。`);
        } catch (error) {
          window.alert(error.message);
        }
      });
    });
  }

  function render() {
    const snapshot = store.getState();
    if (snapshot.authRequired) {
      renderLogin(snapshot);
      return;
    }
    if (!snapshot.viewModel) {
      renderLoading(snapshot);
      return;
    }
    renderDashboard(snapshot);
  }

  return { render };
}
