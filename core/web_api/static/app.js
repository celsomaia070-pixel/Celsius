"use strict";

const state = {
  conversationId: "",
  activeJobId: "",
  streamingText: "",
  busy: false,
  sendPending: false,
  files: [],
  streamMessage: null,
  websocket: null,
  reconnectDelay: 800,
  pollTimer: null,
  modelId: "",
  voiceEnabled: false,
  voiceRequiresInternet: false,
  speechBuffer: "",
  speechSynthesisChain: Promise.resolve(),
  speechPlaybackChain: Promise.resolve(),
  speechPendingPlayback: 0,
  speechAbortController: null,
  currentAudio: null,
  currentAudioStop: null,
  speechGeneration: 0,
  speechReceivedChunks: false,
  jarvisEnabled: false,
  jarvisMode: "idle",
  jarvisAnimationId: null,
  jarvisParticles: [],
  jarvisParticleCount: 420,
  jarvisDrag: null,
  activeView: "chat",
  chatTitle: "Nova conversa",
  agendaItems: [],
  agendaVisible: false,
  agendaRefreshTimer: null,
  reminderItems: new Map(),
  reminderBeepTimer: null,
  audioContext: null,
  documentsVisible: false,
  documentItems: [],
  documentFiles: [],
  customersVisible: false,
  suppliersVisible: false,
  relationshipKind: "customers",
  relationshipItems: [],
  inventoryVisible: false,
  inventoryItems: [],
  inventoryMovements: [],
  inventoryMode: "items",
  productsVisible: false,
  productItems: [],
  quotesVisible: false,
  quoteItems: [],
  reportsVisible: false,
  reportItems: [],
  casesVisible: false,
  caseItems: [],
  voiceInputRecording: false,
  voiceInputBusy: false,
  voiceInputStream: null,
  voiceInputContext: null,
  voiceInputSource: null,
  voiceInputProcessor: null,
  voiceInputChunks: [],
  voiceInputTimer: null,
  voiceInputSpeechDetected: false,
  voiceInputSilenceStartedAt: 0,
};

const elements = {
  body: document.body,
  sidebar: document.querySelector("#sidebar"),
  backdrop: document.querySelector("#sidebar-backdrop"),
  menuButton: document.querySelector("#menu-button"),
  sidebarClose: document.querySelector("#sidebar-close"),
  newChat: document.querySelector("#new-chat"),
  chatButton: document.querySelector("#chat-button"),
  agendaButton: document.querySelector("#agenda-button"),
  documentsButton: document.querySelector("#documents-button"),
  customersButton: document.querySelector("#customers-button"),
  suppliersButton: document.querySelector("#suppliers-button"),
  inventoryButton: document.querySelector("#inventory-button"),
  productsButton: document.querySelector("#products-button"),
  quotesButton: document.querySelector("#quotes-button"),
  reportsButton: document.querySelector("#reports-button"),
  casesButton: document.querySelector("#cases-button"),
  refreshConversations: document.querySelector("#refresh-conversations"),
  memoryButton: document.querySelector("#memory-button"),
  memoryDialog: document.querySelector("#memory-dialog"),
  memoryClose: document.querySelector("#memory-close"),
  memoryForm: document.querySelector("#memory-form"),
  memoryInput: document.querySelector("#memory-input"),
  memoryList: document.querySelector("#memory-list"),
  memoryCount: document.querySelector("#memory-count"),
  conversationList: document.querySelector("#conversation-list"),
  conversationTitle: document.querySelector("#conversation-title"),
  companyLabel: document.querySelector("#company-label"),
  chatStage: document.querySelector("#chat-stage"),
  composerBand: document.querySelector("#composer-band"),
  messages: document.querySelector("#messages"),
  emptyState: document.querySelector("#empty-state"),
  emptySubtitle: document.querySelector("#empty-subtitle"),
  scrollLatest: document.querySelector("#scroll-latest"),
  localState: document.querySelector("#local-state"),
  themeButtons: [...document.querySelectorAll("[data-theme-option]")],
  mobilePairButton: document.querySelector("#mobile-pair-button"),
  mobilePairDialog: document.querySelector("#mobile-pair-dialog"),
  mobilePairClose: document.querySelector("#mobile-pair-close"),
  mobilePairDone: document.querySelector("#mobile-pair-done"),
  mobilePairCopy: document.querySelector("#mobile-pair-copy"),
  mobilePairQr: document.querySelector("#mobile-pair-qr"),
  mobilePairLink: document.querySelector("#mobile-pair-link"),
  mobilePairStatus: document.querySelector("#mobile-pair-status"),
  mobilePairNote: document.querySelector("#mobile-pair-note"),
  composer: document.querySelector("#composer"),
  input: document.querySelector("#message-input"),
  sendButton: document.querySelector("#send-button"),
  voiceInputButton: document.querySelector("#voice-input-button"),
  voiceInputStatus: document.querySelector("#voice-input-status"),
  composerDefaultNote: document.querySelector("#composer-default-note"),
  attachButton: document.querySelector("#attach-button"),
  fileInput: document.querySelector("#file-input"),
  attachmentList: document.querySelector("#attachment-list"),
  modelSelect: document.querySelector("#model-select"),
  voiceToggle: document.querySelector("#voice-toggle"),
  jarvisToggle: document.querySelector("#jarvis-toggle"),
  jarvisVisual: document.querySelector("#jarvis-visual"),
  jarvisCanvas: document.querySelector("#jarvis-canvas"),
  jarvisStatus: document.querySelector("#jarvis-status"),
  agendaView: document.querySelector("#agenda-view"),
  agendaSummary: document.querySelector("#agenda-summary"),
  agendaList: document.querySelector("#agenda-list"),
  agendaEmpty: document.querySelector("#agenda-empty"),
  agendaRefresh: document.querySelector("#agenda-refresh"),
  agendaAdd: document.querySelector("#agenda-add"),
  agendaSearch: document.querySelector("#agenda-search"),
  agendaStatusFilter: document.querySelector("#agenda-status-filter"),
  agendaDialog: document.querySelector("#agenda-dialog"),
  agendaForm: document.querySelector("#agenda-form"),
  agendaDialogTitle: document.querySelector("#agenda-dialog-title"),
  agendaClose: document.querySelector("#agenda-close"),
  agendaCancel: document.querySelector("#agenda-cancel"),
  agendaSave: document.querySelector("#agenda-save"),
  agendaId: document.querySelector("#agenda-id"),
  agendaTitle: document.querySelector("#agenda-title"),
  agendaType: document.querySelector("#agenda-type"),
  agendaStartsAt: document.querySelector("#agenda-starts-at"),
  agendaCustomer: document.querySelector("#agenda-customer"),
  agendaResponsible: document.querySelector("#agenda-responsible"),
  agendaLocation: document.querySelector("#agenda-location"),
  agendaReminder: document.querySelector("#agenda-reminder"),
  agendaStatus: document.querySelector("#agenda-status"),
  agendaNotes: document.querySelector("#agenda-notes"),
  agendaAlert: document.querySelector("#agenda-alert"),
  agendaAlertList: document.querySelector("#agenda-alert-list"),
  agendaAlertDismiss: document.querySelector("#agenda-alert-dismiss"),
  documentsView: document.querySelector("#documents-view"),
  documentsSummary: document.querySelector("#documents-summary"),
  documentsTotal: document.querySelector("#documents-total"),
  documentsIndexed: document.querySelector("#documents-indexed"),
  documentsProcessing: document.querySelector("#documents-processing"),
  documentsChunks: document.querySelector("#documents-chunks"),
  documentsRefresh: document.querySelector("#documents-refresh"),
  documentsAdd: document.querySelector("#documents-add"),
  documentsFilter: document.querySelector("#documents-filter"),
  documentsStatusFilter: document.querySelector("#documents-status-filter"),
  documentsList: document.querySelector("#documents-list"),
  documentsEmpty: document.querySelector("#documents-empty"),
  knowledgeSearchForm: document.querySelector("#knowledge-search-form"),
  knowledgeSearchInput: document.querySelector("#knowledge-search-input"),
  knowledgeSearchButton: document.querySelector("#knowledge-search-button"),
  knowledgeResults: document.querySelector("#knowledge-results"),
  knowledgeResultsList: document.querySelector("#knowledge-results-list"),
  knowledgeResultsClose: document.querySelector("#knowledge-results-close"),
  documentsDialog: document.querySelector("#documents-dialog"),
  documentsForm: document.querySelector("#documents-form"),
  documentsClose: document.querySelector("#documents-close"),
  documentsCancel: document.querySelector("#documents-cancel"),
  documentsUpload: document.querySelector("#documents-upload"),
  documentsFiles: document.querySelector("#documents-files"),
  documentDropzone: document.querySelector("#document-dropzone"),
  selectedDocumentList: document.querySelector("#selected-document-list"),
  documentsType: document.querySelector("#documents-type"),
  documentsCategory: document.querySelector("#documents-category"),
  documentsOrigin: document.querySelector("#documents-origin"),
  documentsResponsible: document.querySelector("#documents-responsible"),
  relationshipsView: document.querySelector("#relationships-view"),
  relationshipsHeading: document.querySelector("#relationships-heading"),
  relationshipsSummary: document.querySelector("#relationships-summary"),
  relationshipsRefresh: document.querySelector("#relationships-refresh"),
  relationshipsAdd: document.querySelector("#relationships-add"),
  relationshipsTotal: document.querySelector("#relationships-total"),
  relationshipsActive: document.querySelector("#relationships-active"),
  relationshipsContactable: document.querySelector("#relationships-contactable"),
  relationshipsProfiled: document.querySelector("#relationships-profiled"),
  relationshipsProfiledLabel: document.querySelector("#relationships-profiled-label"),
  relationshipsFilter: document.querySelector("#relationships-filter"),
  relationshipsStatusFilter: document.querySelector("#relationships-status-filter"),
  relationshipsProfileHeading: document.querySelector("#relationships-profile-heading"),
  relationshipsList: document.querySelector("#relationships-list"),
  relationshipsEmpty: document.querySelector("#relationships-empty"),
  relationshipDialog: document.querySelector("#relationship-dialog"),
  relationshipForm: document.querySelector("#relationship-form"),
  relationshipDialogTitle: document.querySelector("#relationship-dialog-title"),
  relationshipDialogSubtitle: document.querySelector("#relationship-dialog-subtitle"),
  relationshipClose: document.querySelector("#relationship-close"),
  relationshipCancel: document.querySelector("#relationship-cancel"),
  relationshipSave: document.querySelector("#relationship-save"),
  relationshipId: document.querySelector("#relationship-id"),
  relationshipName: document.querySelector("#relationship-name"),
  relationshipDocument: document.querySelector("#relationship-document"),
  relationshipStatus: document.querySelector("#relationship-status"),
  relationshipContact: document.querySelector("#relationship-contact"),
  relationshipPhone: document.querySelector("#relationship-phone"),
  relationshipEmail: document.querySelector("#relationship-email"),
  relationshipCustomerType: document.querySelector("#relationship-customer-type"),
  relationshipSegment: document.querySelector("#relationship-segment"),
  relationshipResponsible: document.querySelector("#relationship-responsible"),
  relationshipAddress: document.querySelector("#relationship-address"),
  relationshipCategory: document.querySelector("#relationship-category"),
  relationshipLeadTime: document.querySelector("#relationship-lead-time"),
  relationshipProducts: document.querySelector("#relationship-products"),
  relationshipPaymentTerms: document.querySelector("#relationship-payment-terms"),
  relationshipNotes: document.querySelector("#relationship-notes"),
  inventoryView: document.querySelector("#inventory-view"),
  inventorySummary: document.querySelector("#inventory-summary"),
  inventoryRefresh: document.querySelector("#inventory-refresh"),
  inventoryAdd: document.querySelector("#inventory-add"),
  inventoryTotal: document.querySelector("#inventory-total"),
  inventoryUnits: document.querySelector("#inventory-units"),
  inventoryCritical: document.querySelector("#inventory-critical"),
  inventoryCategories: document.querySelector("#inventory-categories"),
  inventoryItemsTab: document.querySelector("#inventory-items-tab"),
  inventoryMovementsTab: document.querySelector("#inventory-movements-tab"),
  inventoryItemsPanel: document.querySelector("#inventory-items-panel"),
  inventoryMovementsPanel: document.querySelector("#inventory-movements-panel"),
  inventoryFilter: document.querySelector("#inventory-filter"),
  inventoryHealthFilter: document.querySelector("#inventory-health-filter"),
  inventoryList: document.querySelector("#inventory-list"),
  inventoryEmpty: document.querySelector("#inventory-empty"),
  inventoryMovementsList: document.querySelector("#inventory-movements-list"),
  inventoryMovementsEmpty: document.querySelector("#inventory-movements-empty"),
  inventoryDialog: document.querySelector("#inventory-dialog"),
  inventoryForm: document.querySelector("#inventory-form"),
  inventoryDialogTitle: document.querySelector("#inventory-dialog-title"),
  inventoryClose: document.querySelector("#inventory-close"),
  inventoryCancel: document.querySelector("#inventory-cancel"),
  inventorySave: document.querySelector("#inventory-save"),
  inventoryId: document.querySelector("#inventory-id"),
  inventoryName: document.querySelector("#inventory-name"),
  inventoryCategory: document.querySelector("#inventory-category"),
  inventoryQuantityField: document.querySelector("#inventory-quantity-field"),
  inventoryQuantity: document.querySelector("#inventory-quantity"),
  inventoryMinimum: document.querySelector("#inventory-minimum"),
  inventoryMaximum: document.querySelector("#inventory-maximum"),
  inventoryLocation: document.querySelector("#inventory-location"),
  movementDialog: document.querySelector("#movement-dialog"),
  movementForm: document.querySelector("#movement-form"),
  movementDialogTitle: document.querySelector("#movement-dialog-title"),
  movementItemName: document.querySelector("#movement-item-name"),
  movementClose: document.querySelector("#movement-close"),
  movementCancel: document.querySelector("#movement-cancel"),
  movementSave: document.querySelector("#movement-save"),
  movementItemId: document.querySelector("#movement-item-id"),
  movementType: document.querySelector("#movement-type"),
  movementQuantity: document.querySelector("#movement-quantity"),
  productsView: document.querySelector("#products-view"),
  productsSummary: document.querySelector("#products-summary"),
  productsRefresh: document.querySelector("#products-refresh"),
  productsAdd: document.querySelector("#products-add"),
  productsTotal: document.querySelector("#products-total"),
  productsActive: document.querySelector("#products-active"),
  productsProducts: document.querySelector("#products-products"),
  productsServices: document.querySelector("#products-services"),
  productsMargin: document.querySelector("#products-margin"),
  productsFilter: document.querySelector("#products-filter"),
  productsTypeFilter: document.querySelector("#products-type-filter"),
  productsStatusFilter: document.querySelector("#products-status-filter"),
  productsList: document.querySelector("#products-list"),
  productsEmpty: document.querySelector("#products-empty"),
  productDialog: document.querySelector("#product-dialog"),
  productForm: document.querySelector("#product-form"),
  productDialogTitle: document.querySelector("#product-dialog-title"),
  productClose: document.querySelector("#product-close"),
  productCancel: document.querySelector("#product-cancel"),
  productSave: document.querySelector("#product-save"),
  productId: document.querySelector("#product-id"),
  productCode: document.querySelector("#product-code"),
  productType: document.querySelector("#product-type"),
  productName: document.querySelector("#product-name"),
  productCategory: document.querySelector("#product-category"),
  productUnit: document.querySelector("#product-unit"),
  productPrice: document.querySelector("#product-price"),
  productCost: document.querySelector("#product-cost"),
  productDefaultSupplier: document.querySelector("#product-default-supplier"),
  productStatus: document.querySelector("#product-status"),
  productNotes: document.querySelector("#product-notes"),
  quotesView: document.querySelector("#quotes-view"),
  quotesSummary: document.querySelector("#quotes-summary"),
  quotesRefresh: document.querySelector("#quotes-refresh"),
  quotesAdd: document.querySelector("#quotes-add"),
  quotesTotal: document.querySelector("#quotes-total"),
  quotesSent: document.querySelector("#quotes-sent"),
  quotesApproved: document.querySelector("#quotes-approved"),
  quotesValue: document.querySelector("#quotes-value"),
  quotesFilter: document.querySelector("#quotes-filter"),
  quotesStatusFilter: document.querySelector("#quotes-status-filter"),
  quotesList: document.querySelector("#quotes-list"),
  quotesEmpty: document.querySelector("#quotes-empty"),
  quoteDialog: document.querySelector("#quote-dialog"),
  quoteForm: document.querySelector("#quote-form"),
  quoteDialogTitle: document.querySelector("#quote-dialog-title"),
  quoteClose: document.querySelector("#quote-close"),
  quoteCancel: document.querySelector("#quote-cancel"),
  quoteSave: document.querySelector("#quote-save"),
  quoteId: document.querySelector("#quote-id"),
  quoteNumber: document.querySelector("#quote-number"),
  quoteTitle: document.querySelector("#quote-title"),
  quoteCustomer: document.querySelector("#quote-customer"),
  quoteValidUntil: document.querySelector("#quote-valid-until"),
  quoteValue: document.querySelector("#quote-value"),
  quoteMargin: document.querySelector("#quote-margin"),
  quoteResponsible: document.querySelector("#quote-responsible"),
  quoteStatus: document.querySelector("#quote-status"),
  quoteItems: document.querySelector("#quote-items"),
  quoteNotes: document.querySelector("#quote-notes"),
  reportsView: document.querySelector("#reports-view"),
  reportsSummary: document.querySelector("#reports-summary"),
  reportsRefresh: document.querySelector("#reports-refresh"),
  reportsAdd: document.querySelector("#reports-add"),
  reportsTotal: document.querySelector("#reports-total"),
  reportsGenerated: document.querySelector("#reports-generated"),
  reportsPdf: document.querySelector("#reports-pdf"),
  reportsSources: document.querySelector("#reports-sources"),
  reportsFilter: document.querySelector("#reports-filter"),
  reportsFormatFilter: document.querySelector("#reports-format-filter"),
  reportsList: document.querySelector("#reports-list"),
  reportsEmpty: document.querySelector("#reports-empty"),
  reportDialog: document.querySelector("#report-dialog"),
  reportForm: document.querySelector("#report-form"),
  reportClose: document.querySelector("#report-close"),
  reportCancel: document.querySelector("#report-cancel"),
  reportGenerate: document.querySelector("#report-generate"),
  reportTitle: document.querySelector("#report-title"),
  reportType: document.querySelector("#report-type"),
  reportPeriod: document.querySelector("#report-period"),
  reportSource: document.querySelector("#report-source"),
  reportIndicator: document.querySelector("#report-indicator"),
  reportPeriodicity: document.querySelector("#report-periodicity"),
  reportResponsible: document.querySelector("#report-responsible"),
  reportFormat: document.querySelector("#report-format"),
  reportNotes: document.querySelector("#report-notes"),
  casesView: document.querySelector("#cases-view"),
  casesSummary: document.querySelector("#cases-summary"),
  casesRefresh: document.querySelector("#cases-refresh"),
  casesAdd: document.querySelector("#cases-add"),
  casesTotal: document.querySelector("#cases-total"),
  casesOpen: document.querySelector("#cases-open"),
  casesDue: document.querySelector("#cases-due"),
  casesOverdue: document.querySelector("#cases-overdue"),
  casesFilter: document.querySelector("#cases-filter"),
  casesPriorityFilter: document.querySelector("#cases-priority-filter"),
  casesDeadlineFilter: document.querySelector("#cases-deadline-filter"),
  casesList: document.querySelector("#cases-list"),
  casesEmpty: document.querySelector("#cases-empty"),
  caseDialog: document.querySelector("#case-dialog"),
  caseForm: document.querySelector("#case-form"),
  caseDialogTitle: document.querySelector("#case-dialog-title"),
  caseClose: document.querySelector("#case-close"),
  caseCancel: document.querySelector("#case-cancel"),
  caseSave: document.querySelector("#case-save"),
  caseId: document.querySelector("#case-id"),
  caseTitle: document.querySelector("#case-title"),
  caseCustomer: document.querySelector("#case-customer"),
  caseType: document.querySelector("#case-type"),
  caseDeadline: document.querySelector("#case-deadline"),
  casePriority: document.querySelector("#case-priority"),
  caseResponsible: document.querySelector("#case-responsible"),
  caseStatus: document.querySelector("#case-status"),
  caseNextStep: document.querySelector("#case-next-step"),
  caseNotes: document.querySelector("#case-notes"),
  toastRegion: document.querySelector("#toast-region"),
  themeColor: document.querySelector('meta[name="theme-color"]'),
};

const svg = {
  message: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"/></svg>',
  file: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>',
  close: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>',
  edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2M19 6l-1 15H6L5 6M10 11v6M14 11v6"/></svg>',
  download: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>',
  reindex: '<svg viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3M20 5v4M15 17h6v-6M20 17a8 8 0 0 1-14 2"/></svg>',
  plus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  minus: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>',
};

function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.json);
    delete options.json;
  }
  return fetch(`/api/v1${path}`, { ...options, headers }).then(async (response) => {
    let data = {};
    try {
      data = await response.json();
    } catch (_error) {
      data = {};
    }
    if (!response.ok) {
      if (response.status === 401) {
        window.location.assign("/app");
      }
      throw new Error(data.error || data.detail || `Erro HTTP ${response.status}`);
    }
    return data;
  });
}

async function apiBinary(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.json);
    delete options.json;
  }
  const response = await fetch(`/api/v1${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `Erro HTTP ${response.status}`;
    try {
      const data = await response.json();
      message = data.error || data.detail || message;
    } catch (_error) {
      // Keep the HTTP fallback when the server did not return JSON.
    }
    throw new Error(message);
  }
  return response.blob();
}

function setTheme(theme) {
  const value = ["light", "green", "dark"].includes(theme) ? theme : "light";
  elements.body.dataset.theme = value;
  elements.themeButtons.forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.themeOption === value));
  });
  const themeColors = { light: "#f4f7f6", green: "#101715", dark: "#050505" };
  elements.themeColor.setAttribute("content", themeColors[value]);
  localStorage.setItem("celsius-theme-v2", value);
}

async function openMobilePairing() {
  elements.mobilePairDialog.showModal();
  elements.mobilePairStatus.textContent = "Preparando acesso local...";
  elements.mobilePairNote.textContent = "";
  elements.mobilePairLink.textContent = "";
  elements.mobilePairQr.hidden = true;
  try {
    const data = await api("/mobile/pairing");
    elements.mobilePairLink.href = data.url;
    elements.mobilePairLink.textContent = data.url;
    elements.mobilePairQr.src = data.qr_code || "";
    elements.mobilePairQr.hidden = !data.qr_code;
    elements.mobilePairStatus.textContent = data.lan_access_enabled
      ? "Pronto para conectar"
      : "Acesso pela rede ainda nao esta ativo";
    elements.mobilePairNote.textContent = data.lan_access_enabled
      ? "Mantenha o computador e o celular conectados a mesma rede."
      : "Reinicie o servidor Celsius com o acesso pela rede local habilitado.";
  } catch (error) {
    elements.mobilePairStatus.textContent = "Nao foi possivel preparar o pareamento";
    elements.mobilePairNote.textContent = error.message;
  }
}

async function copyMobilePairingLink() {
  const url = elements.mobilePairLink.href;
  if (!url || url.endsWith("#")) return;
  try {
    await navigator.clipboard.writeText(url);
    showToast("Link de pareamento copiado.");
  } catch (_error) {
    showToast("Nao foi possivel copiar o link automaticamente.", "error");
  }
}

function openSidebar() {
  elements.body.classList.add("sidebar-open");
  elements.backdrop.hidden = false;
}

function closeSidebar() {
  elements.body.classList.remove("sidebar-open");
  elements.backdrop.hidden = true;
}

function showToast(message, type = "info") {
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  elements.toastRegion.append(toast);
  window.setTimeout(() => toast.remove(), 4200);
}

function setConnected(connected) {
  elements.localState.classList.toggle("offline", !connected);
  elements.localState.querySelector("span:last-child").textContent = connected
    ? "IA local"
    : "Reconectando";
}

function renderMemories(items) {
  elements.memoryList.replaceChildren();
  elements.memoryCount.textContent = `${items.length} ${items.length === 1 ? "memoria" : "memorias"}`;
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "memory-empty";
    empty.textContent = "Nenhuma memoria cadastrada.";
    elements.memoryList.append(empty);
    return;
  }
  for (const memory of [...items].reverse()) {
    const row = document.createElement("div");
    row.className = "memory-item";
    const text = document.createElement("p");
    text.textContent = memory.text;
    const date = document.createElement("time");
    date.textContent = memory.date || "Local";
    row.append(text, date);
    elements.memoryList.append(row);
  }
}

async function openMemories() {
  closeSidebar();
  try {
    const data = await api("/memories");
    renderMemories(data.items || []);
    elements.memoryDialog.showModal();
    elements.memoryInput.focus();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function saveMemory(event) {
  event.preventDefault();
  const text = elements.memoryInput.value.trim();
  if (!text) return;
  try {
    await api("/memories", { method: "POST", json: { text } });
    elements.memoryInput.value = "";
    const data = await api("/memories");
    renderMemories(data.items || []);
    showToast("Memoria salva apenas neste computador.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function showView(view) {
  const agendaActive = view === "agenda" && state.agendaVisible;
  const documentsActive = view === "documents" && state.documentsVisible;
  const customersActive = view === "customers" && state.customersVisible;
  const suppliersActive = view === "suppliers" && state.suppliersVisible;
  const inventoryActive = view === "inventory" && state.inventoryVisible;
  const productsActive = view === "products_services" && state.productsVisible;
  const quotesActive = view === "quotes" && state.quotesVisible;
  const reportsActive = view === "reports" && state.reportsVisible;
  const casesActive = view === "cases_deadlines" && state.casesVisible;
  const relationshipsActive = customersActive || suppliersActive;
  if (relationshipsActive) state.relationshipKind = customersActive ? "customers" : "suppliers";
  state.activeView = agendaActive
    ? "agenda"
    : documentsActive
      ? "documents"
      : relationshipsActive
        ? state.relationshipKind
        : inventoryActive
          ? "inventory"
          : productsActive
            ? "products_services"
            : quotesActive
              ? "quotes"
              : reportsActive
                ? "reports"
                : casesActive
                  ? "cases_deadlines"
                  : "chat";
  const moduleActive = agendaActive || documentsActive || relationshipsActive || inventoryActive || productsActive || quotesActive || reportsActive || casesActive;
  elements.chatStage.hidden = moduleActive;
  elements.composerBand.hidden = moduleActive;
  elements.agendaView.hidden = !agendaActive;
  elements.documentsView.hidden = !documentsActive;
  elements.relationshipsView.hidden = !relationshipsActive;
  elements.inventoryView.hidden = !inventoryActive;
  elements.productsView.hidden = !productsActive;
  elements.quotesView.hidden = !quotesActive;
  elements.reportsView.hidden = !reportsActive;
  elements.casesView.hidden = !casesActive;
  elements.chatButton.classList.toggle("active", !moduleActive);
  elements.agendaButton.classList.toggle("active", agendaActive);
  elements.documentsButton.classList.toggle("active", documentsActive);
  elements.customersButton.classList.toggle("active", customersActive);
  elements.suppliersButton.classList.toggle("active", suppliersActive);
  elements.inventoryButton.classList.toggle("active", inventoryActive);
  elements.productsButton.classList.toggle("active", productsActive);
  elements.quotesButton.classList.toggle("active", quotesActive);
  elements.reportsButton.classList.toggle("active", reportsActive);
  elements.casesButton.classList.toggle("active", casesActive);
  elements.chatButton.toggleAttribute("aria-current", !moduleActive);
  elements.agendaButton.toggleAttribute("aria-current", agendaActive);
  elements.documentsButton.toggleAttribute("aria-current", documentsActive);
  elements.customersButton.toggleAttribute("aria-current", customersActive);
  elements.suppliersButton.toggleAttribute("aria-current", suppliersActive);
  elements.inventoryButton.toggleAttribute("aria-current", inventoryActive);
  elements.productsButton.toggleAttribute("aria-current", productsActive);
  elements.quotesButton.toggleAttribute("aria-current", quotesActive);
  elements.reportsButton.toggleAttribute("aria-current", reportsActive);
  elements.casesButton.toggleAttribute("aria-current", casesActive);
  elements.conversationTitle.textContent = agendaActive
    ? "Agenda"
    : documentsActive
      ? "Documentos"
      : customersActive
        ? "Clientes"
        : suppliersActive
          ? "Fornecedores"
          : inventoryActive
            ? "Estoque"
            : productsActive
              ? "Produtos e servicos"
              : quotesActive
                ? "Orcamentos"
                : reportsActive
                  ? "Relatorios"
                  : casesActive
                    ? "Processos e prazos"
                    : state.chatTitle;
  closeSidebar();
  if (agendaActive) loadAgenda();
  if (documentsActive) loadDocuments();
  if (relationshipsActive) loadRelationships();
  if (inventoryActive) loadInventory();
  if (productsActive) loadProducts();
  if (quotesActive) loadQuotes();
  if (reportsActive) loadReports();
  if (casesActive) loadCases();
}

async function loadNavigation() {
  try {
    const data = await api("/navigation");
    state.agendaVisible = (data.items || []).some((item) => item.id === "agenda");
    state.documentsVisible = (data.items || []).some((item) => item.id === "knowledge");
    state.customersVisible = (data.items || []).some((item) => item.id === "customers");
    state.suppliersVisible = (data.items || []).some((item) => item.id === "suppliers");
    state.inventoryVisible = (data.items || []).some((item) => item.id === "inventory");
    state.productsVisible = (data.items || []).some((item) => item.id === "products_services");
    state.quotesVisible = (data.items || []).some((item) => item.id === "quotes");
    state.reportsVisible = (data.items || []).some((item) => item.id === "reports");
    state.casesVisible = (data.items || []).some((item) => item.id === "cases_deadlines");
    elements.agendaButton.hidden = !state.agendaVisible;
    elements.documentsButton.hidden = !state.documentsVisible;
    elements.customersButton.hidden = !state.customersVisible;
    elements.suppliersButton.hidden = !state.suppliersVisible;
    elements.inventoryButton.hidden = !state.inventoryVisible;
    elements.productsButton.hidden = !state.productsVisible;
    elements.quotesButton.hidden = !state.quotesVisible;
    elements.reportsButton.hidden = !state.reportsVisible;
    elements.casesButton.hidden = !state.casesVisible;
    if (!state.agendaVisible && state.activeView === "agenda") showView("chat");
    if (!state.documentsVisible && state.activeView === "documents") showView("chat");
    if (!state.customersVisible && state.activeView === "customers") showView("chat");
    if (!state.suppliersVisible && state.activeView === "suppliers") showView("chat");
    if (!state.inventoryVisible && state.activeView === "inventory") showView("chat");
    if (!state.productsVisible && state.activeView === "products_services") showView("chat");
    if (!state.quotesVisible && state.activeView === "quotes") showView("chat");
    if (!state.reportsVisible && state.activeView === "reports") showView("chat");
    if (!state.casesVisible && state.activeView === "cases_deadlines") showView("chat");
  } catch (error) {
    showToast(`Modulos: ${error.message}`, "error");
  }
}

function agendaDateParts(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return { date: "Data invalida", time: "" };
  return {
    date: new Intl.DateTimeFormat("pt-BR", {
      weekday: "short",
      day: "2-digit",
      month: "short",
    }).format(date),
    time: new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
    }).format(date),
  };
}

function matchesAgendaFilters(item) {
  const query = elements.agendaSearch.value.trim().toLocaleLowerCase("pt-BR");
  const status = elements.agendaStatusFilter.value;
  const haystack = [item.title, item.customer, item.responsible, item.location, item.notes]
    .join(" ")
    .toLocaleLowerCase("pt-BR");
  return (!query || haystack.includes(query)) && (!status || item.status === status);
}

function agendaStatusSelect(item) {
  const select = document.createElement("select");
  select.className = "agenda-status-select";
  select.setAttribute("aria-label", `Status de ${item.title}`);
  for (const status of ["Agendado", "Confirmado", "Concluido", "Remarcar", "Cancelado"]) {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    option.selected = status === item.status;
    select.append(option);
  }
  select.addEventListener("change", async () => {
    const previous = item.status;
    try {
      await api(`/agenda/${encodeURIComponent(item.id)}`, {
        method: "PATCH",
        json: { status: select.value },
      });
      showToast("Status atualizado.");
      await loadAgenda();
    } catch (error) {
      select.value = previous;
      showToast(error.message, "error");
    }
  });
  return select;
}

function renderAgenda() {
  const items = state.agendaItems.filter(matchesAgendaFilters);
  elements.agendaList.replaceChildren();
  elements.agendaEmpty.hidden = items.length > 0;
  const activeCount = state.agendaItems.filter(
    (item) => !["Concluido", "Cancelado"].includes(item.status),
  ).length;
  elements.agendaSummary.textContent = `${activeCount} ${activeCount === 1 ? "compromisso ativo" : "compromissos ativos"} · ${state.agendaItems.length} no total`;

  for (const item of items) {
    const row = document.createElement("tr");
    const parts = agendaDateParts(item.starts_at);

    const dateCell = document.createElement("td");
    dateCell.className = "agenda-date";
    const dateStrong = document.createElement("strong");
    dateStrong.textContent = parts.date;
    const time = document.createElement("span");
    time.textContent = parts.time;
    dateCell.append(dateStrong, time);

    const titleCell = document.createElement("td");
    titleCell.className = "agenda-title";
    const title = document.createElement("strong");
    title.textContent = item.title;
    const responsible = document.createElement("span");
    responsible.textContent = item.responsible ? `Responsavel: ${item.responsible}` : "Sem responsavel definido";
    titleCell.append(title, responsible);

    const contactCell = document.createElement("td");
    contactCell.className = "agenda-contact";
    const customer = document.createElement("span");
    customer.textContent = item.customer || "Sem cliente vinculado";
    const location = document.createElement("span");
    location.textContent = item.location || "Local nao informado";
    contactCell.append(customer, location);

    const statusCell = document.createElement("td");
    statusCell.append(agendaStatusSelect(item));

    const actionsCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "agenda-row-actions";
    const edit = document.createElement("button");
    edit.className = "icon-button";
    edit.type = "button";
    edit.title = "Editar compromisso";
    edit.setAttribute("aria-label", `Editar ${item.title}`);
    edit.innerHTML = svg.edit;
    edit.addEventListener("click", () => openAgendaDialog(item));
    const remove = document.createElement("button");
    remove.className = "icon-button delete-action";
    remove.type = "button";
    remove.title = "Excluir compromisso";
    remove.setAttribute("aria-label", `Excluir ${item.title}`);
    remove.innerHTML = svg.trash;
    remove.addEventListener("click", () => deleteAgendaItem(item));
    actions.append(edit, remove);
    actionsCell.append(actions);
    row.append(dateCell, titleCell, contactCell, statusCell, actionsCell);
    elements.agendaList.append(row);
  }
}

async function loadAgenda() {
  if (!state.agendaVisible) return;
  try {
    const data = await api("/agenda");
    state.agendaItems = data.items || [];
    renderAgenda();
  } catch (error) {
    showToast(`Agenda: ${error.message}`, "error");
  }
}

function defaultAgendaDate() {
  const date = new Date(Date.now() + 60 * 60 * 1000);
  date.setMinutes(Math.ceil(date.getMinutes() / 15) * 15, 0, 0);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function openAgendaDialog(item = null) {
  elements.agendaForm.reset();
  elements.agendaId.value = item?.id || "";
  elements.agendaDialogTitle.textContent = item ? "Editar compromisso" : "Novo compromisso";
  elements.agendaTitle.value = item?.title || "";
  elements.agendaType.value = item?.event_type || "Reuniao";
  elements.agendaStartsAt.value = item?.starts_at || defaultAgendaDate();
  elements.agendaCustomer.value = item?.customer || "";
  elements.agendaResponsible.value = item?.responsible || "";
  elements.agendaLocation.value = item?.location || "";
  elements.agendaReminder.value = String(item?.reminder_minutes ?? 15);
  elements.agendaStatus.value = item?.status || "Agendado";
  elements.agendaNotes.value = item?.notes || "";
  elements.agendaDialog.showModal();
  elements.agendaTitle.focus();
}

async function saveAgendaItem(event) {
  event.preventDefault();
  const eventId = elements.agendaId.value;
  const payload = {
    title: elements.agendaTitle.value.trim(),
    event_type: elements.agendaType.value,
    starts_at: elements.agendaStartsAt.value,
    customer: elements.agendaCustomer.value.trim(),
    responsible: elements.agendaResponsible.value.trim(),
    location: elements.agendaLocation.value.trim(),
    reminder_minutes: Number(elements.agendaReminder.value),
    status: elements.agendaStatus.value,
    notes: elements.agendaNotes.value.trim(),
  };
  elements.agendaSave.disabled = true;
  try {
    await api(eventId ? `/agenda/${encodeURIComponent(eventId)}` : "/agenda", {
      method: eventId ? "PATCH" : "POST",
      json: payload,
    });
    elements.agendaDialog.close();
    await loadAgenda();
    await loadDueReminders();
    showToast(eventId ? "Compromisso atualizado." : "Compromisso criado.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.agendaSave.disabled = false;
  }
}

async function deleteAgendaItem(item) {
  if (!window.confirm(`Excluir o compromisso "${item.title}"?`)) return;
  try {
    await api(`/agenda/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    state.reminderItems.delete(item.id);
    renderAgendaReminder();
    await loadAgenda();
    showToast("Compromisso excluido.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function playReminderBeep() {
  try {
    const AudioEngine = window.AudioContext || window.webkitAudioContext;
    if (!AudioEngine) return;
    state.audioContext ||= new AudioEngine();
    const context = state.audioContext;
    const start = context.currentTime;
    for (const [offset, frequency] of [[0, 740], [0.18, 940]]) {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.frequency.value = frequency;
      gain.gain.setValueAtTime(0.0001, start + offset);
      gain.gain.exponentialRampToValueAtTime(0.12, start + offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.14);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(start + offset);
      oscillator.stop(start + offset + 0.16);
    }
  } catch (_error) {
    // The visual alert remains active when the browser blocks automatic audio.
  }
}

function renderAgendaReminder() {
  const reminders = [...state.reminderItems.values()];
  elements.agendaAlert.hidden = reminders.length === 0;
  elements.agendaAlertList.replaceChildren();
  if (!reminders.length) {
    window.clearInterval(state.reminderBeepTimer);
    state.reminderBeepTimer = null;
    return;
  }
  for (const reminder of reminders) {
    const line = document.createElement("div");
    const parts = agendaDateParts(reminder.starts_at);
    line.textContent = `${reminder.title} · ${parts.date}, ${parts.time}${reminder.location ? ` · ${reminder.location}` : ""}`;
    elements.agendaAlertList.append(line);
  }
  playReminderBeep();
  if (!state.reminderBeepTimer) {
    state.reminderBeepTimer = window.setInterval(playReminderBeep, 8_000);
  }
}

function showAgendaReminders(items) {
  for (const item of items) state.reminderItems.set(item.id, item);
  renderAgendaReminder();
}

async function loadDueReminders() {
  if (!state.agendaVisible) return;
  try {
    const data = await api("/agenda/reminders/due");
    showAgendaReminders(data.items || []);
  } catch (_error) {
    // The next refresh or WebSocket event retries the local reminder check.
  }
}

async function acknowledgeAgendaReminders() {
  const ids = [...state.reminderItems.keys()];
  if (!ids.length) return;
  elements.agendaAlertDismiss.disabled = true;
  try {
    await Promise.all(
      ids.map((eventId) => api(`/agenda/${encodeURIComponent(eventId)}/acknowledge`, { method: "POST" })),
    );
    state.reminderItems.clear();
    renderAgendaReminder();
    await loadAgenda();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.agendaAlertDismiss.disabled = false;
  }
}

function formatFileSize(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return size ? `${size} B` : "Arquivo legado";
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function documentStatusClass(status) {
  const normalized = (status || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  if (normalized === "indexado") return "indexed";
  if (normalized === "processando") return "processing";
  if (normalized === "revisar") return "review";
  return "";
}

function matchesDocumentFilters(item) {
  const query = elements.documentsFilter.value.trim().toLocaleLowerCase("pt-BR");
  const status = elements.documentsStatusFilter.value;
  const haystack = [item.title, item.filename, item.category, item.origin, item.responsible]
    .join(" ")
    .toLocaleLowerCase("pt-BR");
  return (!query || haystack.includes(query)) && (!status || item.status === status);
}

function renderDocumentMetrics() {
  const indexed = state.documentItems.filter((item) => item.status === "Indexado").length;
  const processing = state.documentItems.filter((item) => item.status === "Processando").length;
  const chunks = state.documentItems.reduce((total, item) => total + (Number(item.chunk_count) || 0), 0);
  const bytes = state.documentItems.reduce((total, item) => total + (Number(item.size) || 0), 0);
  elements.documentsTotal.textContent = String(state.documentItems.length);
  elements.documentsIndexed.textContent = String(indexed);
  elements.documentsProcessing.textContent = String(processing);
  elements.documentsChunks.textContent = String(chunks);
  elements.documentsSummary.textContent = `${indexed} indexados · ${formatFileSize(bytes)} armazenados localmente`;
}

function documentActionButton({ icon, label, className = "", handler, disabled = false }) {
  const button = document.createElement("button");
  button.className = `icon-button ${className}`.trim();
  button.type = "button";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.innerHTML = icon;
  button.disabled = disabled;
  button.addEventListener("click", handler);
  return button;
}

function renderDocuments() {
  renderDocumentMetrics();
  const items = state.documentItems.filter(matchesDocumentFilters);
  elements.documentsList.replaceChildren();
  elements.documentsEmpty.hidden = items.length > 0;

  for (const item of items) {
    const row = document.createElement("tr");
    const titleCell = document.createElement("td");
    titleCell.className = "document-title";
    const title = document.createElement("strong");
    title.textContent = item.title;
    title.title = item.title;
    const file = document.createElement("span");
    file.textContent = `${item.document_type || "Outro"} · ${formatFileSize(item.size)}`;
    titleCell.append(title, file);

    const metadataCell = document.createElement("td");
    metadataCell.className = "document-metadata";
    const category = document.createElement("strong");
    category.textContent = item.category || "Sem categoria";
    const origin = document.createElement("span");
    origin.textContent = item.origin || item.responsible || "Origem nao informada";
    metadataCell.append(category, origin);

    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = `document-status ${documentStatusClass(item.status)}`;
    status.textContent = item.status;
    if (item.error) status.title = item.error;
    statusCell.append(status);

    const indexCell = document.createElement("td");
    indexCell.className = "document-index";
    const chunks = document.createElement("strong");
    chunks.textContent = `${item.chunk_count || 0} trechos`;
    const updated = document.createElement("span");
    updated.textContent = item.updated_at || (item.managed ? "Aguardando indexacao" : "Indice existente");
    indexCell.append(chunks, updated);

    const actionsCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "document-row-actions";
    if (item.file_available) {
      actions.append(
        documentActionButton({
          icon: svg.download,
          label: `Baixar ${item.filename}`,
          handler: () => downloadDocument(item),
        }),
      );
    }
    if (item.managed && item.file_available) {
      actions.append(
        documentActionButton({
          icon: svg.reindex,
          label: `Reindexar ${item.title}`,
          disabled: item.status === "Processando",
          handler: () => reindexDocument(item),
        }),
      );
    }
    actions.append(
      documentActionButton({
        icon: svg.trash,
        label: `Excluir ${item.title}`,
        className: "delete-action",
        handler: () => deleteDocument(item),
      }),
    );
    actionsCell.append(actions);
    row.append(titleCell, metadataCell, statusCell, indexCell, actionsCell);
    elements.documentsList.append(row);
  }
}

async function loadDocuments() {
  if (!state.documentsVisible) return;
  try {
    const data = await api("/documents");
    state.documentItems = data.items || [];
    renderDocuments();
  } catch (error) {
    showToast(`Documentos: ${error.message}`, "error");
  }
}

function openDocumentsDialog() {
  state.documentFiles = [];
  elements.documentsForm.reset();
  renderSelectedDocuments();
  elements.documentsDialog.showModal();
}

function renderSelectedDocuments() {
  elements.selectedDocumentList.replaceChildren();
  elements.selectedDocumentList.hidden = state.documentFiles.length === 0;
  for (const [index, file] of state.documentFiles.entries()) {
    const row = document.createElement("div");
    row.className = "selected-document-item";
    const name = document.createElement("span");
    name.textContent = file.name;
    const details = document.createElement("span");
    details.textContent = formatFileSize(file.size);
    const remove = document.createElement("button");
    remove.className = "icon-button compact";
    remove.type = "button";
    remove.setAttribute("aria-label", `Remover ${file.name}`);
    remove.innerHTML = svg.close;
    remove.addEventListener("click", () => {
      state.documentFiles.splice(index, 1);
      renderSelectedDocuments();
    });
    row.append(name, details, remove);
    elements.selectedDocumentList.append(row);
  }
}

function selectDocumentFiles(fileList) {
  for (const file of Array.from(fileList || [])) {
    const duplicate = state.documentFiles.some(
      (current) => current.name === file.name && current.size === file.size,
    );
    if (!duplicate) state.documentFiles.push(file);
  }
  elements.documentsFiles.value = "";
  renderSelectedDocuments();
}

async function uploadDocuments(event) {
  event.preventDefault();
  if (!state.documentFiles.length) {
    showToast("Selecione ao menos um documento.", "error");
    return;
  }
  const files = [...state.documentFiles];
  elements.documentsUpload.disabled = true;
  try {
    for (const [index, file] of files.entries()) {
      elements.documentsUpload.textContent = `Enviando ${index + 1} de ${files.length}`;
      await api("/documents/upload", {
        method: "POST",
        headers: {
          "X-Celsius-Filename": encodeURIComponent(file.name),
          "X-Celsius-Document-Type": encodeURIComponent(elements.documentsType.value),
          "X-Celsius-Category": encodeURIComponent(elements.documentsCategory.value.trim()),
          "X-Celsius-Origin": encodeURIComponent(elements.documentsOrigin.value.trim()),
          "X-Celsius-Responsible": encodeURIComponent(elements.documentsResponsible.value.trim()),
        },
        body: file,
      });
    }
    elements.documentsDialog.close();
    state.documentFiles = [];
    await loadDocuments();
    showToast(`${files.length} ${files.length === 1 ? "documento enviado" : "documentos enviados"} para indexacao.`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.documentsUpload.disabled = false;
    elements.documentsUpload.textContent = "Importar e indexar";
  }
}

async function searchKnowledge(event) {
  event.preventDefault();
  const query = elements.knowledgeSearchInput.value.trim();
  if (!query) return;
  elements.knowledgeSearchButton.disabled = true;
  elements.knowledgeSearchButton.textContent = "Pesquisando";
  try {
    const data = await api(`/documents/search?query=${encodeURIComponent(query)}&top_k=6`);
    elements.knowledgeResultsList.replaceChildren();
    if (!(data.items || []).length) {
      const empty = document.createElement("div");
      empty.className = "knowledge-result";
      empty.textContent = "Nenhum trecho relevante foi encontrado na base local.";
      elements.knowledgeResultsList.append(empty);
    } else {
      for (const result of data.items) {
        const item = document.createElement("div");
        item.className = "knowledge-result";
        item.textContent = result;
        elements.knowledgeResultsList.append(item);
      }
    }
    elements.knowledgeResults.hidden = false;
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.knowledgeSearchButton.disabled = false;
    elements.knowledgeSearchButton.textContent = "Pesquisar";
  }
}

function downloadDocument(item) {
  const link = document.createElement("a");
  link.href = `/api/v1/documents/${encodeURIComponent(item.id)}/file`;
  link.download = item.filename;
  document.body.append(link);
  link.click();
  link.remove();
}

async function reindexDocument(item) {
  try {
    await api(`/documents/${encodeURIComponent(item.id)}/reindex`, { method: "POST" });
    await loadDocuments();
    showToast("Reindexacao iniciada.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deleteDocument(item) {
  if (!window.confirm(`Excluir "${item.title}" da base local?`)) return;
  try {
    await api(`/documents/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    await loadDocuments();
    showToast("Documento removido da base local.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function relationshipConfig() {
  const customers = state.relationshipKind === "customers";
  return customers
    ? {
        singular: "cliente",
        plural: "clientes",
        profileHeading: "Segmento",
        profileMetric: "com segmento",
      }
    : {
        singular: "fornecedor",
        plural: "fornecedores",
        profileHeading: "Categoria / produtos",
        profileMetric: "com categoria",
      };
}

function matchesRelationshipFilters(item) {
  const query = elements.relationshipsFilter.value.trim().toLocaleLowerCase("pt-BR");
  const status = elements.relationshipsStatusFilter.value;
  const haystack = Object.values(item).join(" ").toLocaleLowerCase("pt-BR");
  return (!query || haystack.includes(query)) && (!status || item.status === status);
}

function renderRelationshipMetrics() {
  const items = state.relationshipItems;
  const customers = state.relationshipKind === "customers";
  const active = items.filter((item) => (item.status || "Ativo") !== "Inativo").length;
  const contactable = items.filter((item) => item.phone || item.email || item.contact).length;
  const profiled = items.filter((item) => (customers ? item.segment : item.category)).length;
  elements.relationshipsTotal.textContent = String(items.length);
  elements.relationshipsActive.textContent = String(active);
  elements.relationshipsContactable.textContent = String(contactable);
  elements.relationshipsProfiled.textContent = String(profiled);
}

function renderRelationships() {
  const config = relationshipConfig();
  const customers = state.relationshipKind === "customers";
  const items = state.relationshipItems.filter(matchesRelationshipFilters);
  elements.relationshipsHeading.textContent = customers ? "Clientes" : "Fornecedores";
  elements.relationshipsSummary.textContent = `${state.relationshipItems.length} ${config.plural} armazenados localmente`;
  elements.relationshipsAdd.querySelector("span").textContent = `Novo ${config.singular}`;
  elements.relationshipsProfileHeading.textContent = config.profileHeading;
  elements.relationshipsProfiledLabel.textContent = config.profileMetric;
  renderRelationshipMetrics();
  elements.relationshipsList.replaceChildren();
  elements.relationshipsEmpty.hidden = items.length > 0;

  for (const item of items) {
    const row = document.createElement("tr");

    const primaryCell = document.createElement("td");
    primaryCell.className = "relationship-primary";
    const name = document.createElement("strong");
    name.textContent = item.name;
    const documentText = document.createElement("span");
    documentText.textContent = item.document || "Documento nao informado";
    primaryCell.append(name, documentText);

    const contactCell = document.createElement("td");
    contactCell.className = "relationship-contact";
    const contact = document.createElement("strong");
    contact.textContent = item.contact || item.phone || "Sem contato principal";
    const channel = document.createElement("span");
    channel.textContent = item.email || item.phone || "Contato nao informado";
    contactCell.append(contact, channel);

    const profileCell = document.createElement("td");
    profileCell.className = "relationship-profile";
    const profile = document.createElement("strong");
    profile.textContent = customers
      ? item.segment || item.customer_type || "Sem segmento"
      : item.category || "Sem categoria";
    const detail = document.createElement("span");
    detail.textContent = customers
      ? item.responsible || item.address || "Sem responsavel interno"
      : item.products || item.payment_terms || "Produtos nao informados";
    profileCell.append(profile, detail);

    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = `relationship-status${item.status === "Inativo" ? " inactive" : ""}`;
    status.textContent = item.status || "Ativo";
    statusCell.append(status);

    const actionsCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "relationship-row-actions";
    actions.append(
      documentActionButton({
        icon: svg.edit,
        label: `Editar ${item.name}`,
        handler: () => openRelationshipDialog(item),
      }),
      documentActionButton({
        icon: svg.trash,
        label: `Excluir ${item.name}`,
        className: "delete-action",
        handler: () => deleteRelationship(item),
      }),
    );
    actionsCell.append(actions);
    row.append(primaryCell, contactCell, profileCell, statusCell, actionsCell);
    elements.relationshipsList.append(row);
  }
}

async function loadRelationships() {
  const visible = state.relationshipKind === "customers"
    ? state.customersVisible
    : state.suppliersVisible;
  if (!visible) return;
  try {
    const data = await api(`/${state.relationshipKind}`);
    state.relationshipItems = data.items || [];
    renderRelationships();
  } catch (error) {
    showToast(`${relationshipConfig().plural}: ${error.message}`, "error");
  }
}

function openRelationshipDialog(item = null) {
  const config = relationshipConfig();
  const customers = state.relationshipKind === "customers";
  elements.relationshipForm.reset();
  elements.relationshipId.value = item?.id || "";
  elements.relationshipDialogTitle.textContent = `${item ? "Editar" : "Novo"} ${config.singular}`;
  elements.relationshipDialogSubtitle.textContent = customers
    ? "Dados comerciais locais que o Celsius pode consultar."
    : "Dados de fornecimento locais que o Celsius pode consultar.";
  document.querySelectorAll(".customer-field").forEach((field) => {
    field.hidden = !customers;
  });
  document.querySelectorAll(".supplier-field").forEach((field) => {
    field.hidden = customers;
  });
  if (item) {
    elements.relationshipName.value = item.name || "";
    elements.relationshipDocument.value = item.document || "";
    elements.relationshipStatus.value = item.status || "Ativo";
    elements.relationshipContact.value = item.contact || "";
    elements.relationshipPhone.value = item.phone || "";
    elements.relationshipEmail.value = item.email || "";
    elements.relationshipNotes.value = item.notes || "";
    elements.relationshipCustomerType.value = item.customer_type || "Outro";
    elements.relationshipSegment.value = item.segment || "";
    elements.relationshipResponsible.value = item.responsible || "";
    elements.relationshipAddress.value = item.address || "";
    elements.relationshipCategory.value = item.category || "";
    elements.relationshipLeadTime.value = item.lead_time_days || "";
    elements.relationshipProducts.value = item.products || "";
    elements.relationshipPaymentTerms.value = item.payment_terms || "";
  }
  elements.relationshipDialog.showModal();
  elements.relationshipName.focus();
}

async function saveRelationship(event) {
  event.preventDefault();
  const customers = state.relationshipKind === "customers";
  const id = elements.relationshipId.value;
  const payload = {
    name: elements.relationshipName.value.trim(),
    document: elements.relationshipDocument.value.trim(),
    status: elements.relationshipStatus.value,
    contact: elements.relationshipContact.value.trim(),
    phone: elements.relationshipPhone.value.trim(),
    email: elements.relationshipEmail.value.trim(),
    notes: elements.relationshipNotes.value.trim(),
  };
  if (customers) {
    Object.assign(payload, {
      customer_type: elements.relationshipCustomerType.value,
      segment: elements.relationshipSegment.value.trim(),
      responsible: elements.relationshipResponsible.value.trim(),
      address: elements.relationshipAddress.value.trim(),
    });
  } else {
    Object.assign(payload, {
      category: elements.relationshipCategory.value.trim(),
      lead_time_days: elements.relationshipLeadTime.value.trim(),
      products: elements.relationshipProducts.value.trim(),
      payment_terms: elements.relationshipPaymentTerms.value.trim(),
    });
  }
  elements.relationshipSave.disabled = true;
  elements.relationshipSave.textContent = "Salvando";
  try {
    await api(`/${state.relationshipKind}${id ? `/${encodeURIComponent(id)}` : ""}`, {
      method: id ? "PATCH" : "POST",
      json: payload,
    });
    elements.relationshipDialog.close();
    await loadRelationships();
    showToast(`${relationshipConfig().singular} salvo localmente.`);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.relationshipSave.disabled = false;
    elements.relationshipSave.textContent = "Salvar cadastro";
  }
}

async function deleteRelationship(item) {
  const config = relationshipConfig();
  if (!window.confirm(`Excluir o ${config.singular} "${item.name}"?`)) return;
  try {
    await api(`/${state.relationshipKind}/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    await loadRelationships();
    showToast(`${config.singular} removido.`);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function inventoryHealthClass(health) {
  if (health === "Critico") return "critical";
  if (health === "Sem estoque") return "empty";
  if (health === "Acima do maximo") return "excess";
  return "";
}

function renderInventoryMetrics() {
  const items = state.inventoryItems;
  const units = items.reduce((total, item) => total + Number(item.quantity || 0), 0);
  const critical = items.filter((item) => item.needs_restock).length;
  const categories = new Set(items.map((item) => item.category).filter(Boolean)).size;
  elements.inventoryTotal.textContent = String(items.length);
  elements.inventoryUnits.textContent = String(units);
  elements.inventoryCritical.textContent = String(critical);
  elements.inventoryCategories.textContent = String(categories);
  elements.inventorySummary.textContent = `${items.length} itens · ${critical} precisam de reposicao`;
}

function matchesInventoryFilters(item) {
  const query = elements.inventoryFilter.value.trim().toLocaleLowerCase("pt-BR");
  const health = elements.inventoryHealthFilter.value;
  const haystack = `${item.name} ${item.category}`.toLocaleLowerCase("pt-BR");
  return (!query || haystack.includes(query)) && (!health || item.health === health);
}

function renderInventory() {
  renderInventoryMetrics();
  const items = state.inventoryItems.filter(matchesInventoryFilters);
  elements.inventoryList.replaceChildren();
  elements.inventoryEmpty.hidden = items.length > 0;
  for (const item of items) {
    const row = document.createElement("tr");
    const primaryCell = document.createElement("td");
    primaryCell.className = "inventory-primary";
    const name = document.createElement("strong");
    name.textContent = item.name;
    const category = document.createElement("span");
    category.textContent = item.category || "Sem categoria";
    primaryCell.append(name, category);

    const quantityCell = document.createElement("td");
    quantityCell.className = "inventory-quantity";
    const quantity = document.createElement("strong");
    quantity.textContent = `${item.quantity} un.`;
    const limits = document.createElement("span");
    limits.textContent = `Min. ${item.minimum} · Max. ${item.maximum}`;
    quantityCell.append(quantity, limits);

    const healthCell = document.createElement("td");
    const health = document.createElement("span");
    health.className = `stock-health ${inventoryHealthClass(item.health)}`.trim();
    health.textContent = item.health;
    healthCell.append(health);

    const locationCell = document.createElement("td");
    locationCell.className = "inventory-location";
    const location = document.createElement("strong");
    location.textContent = item.location_label;
    const updated = document.createElement("span");
    updated.textContent = item.updated_at || "Local";
    locationCell.append(location, updated);

    const actionsCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "inventory-row-actions";
    actions.append(
      documentActionButton({
        icon: svg.plus,
        label: `Registrar entrada de ${item.name}`,
        className: "movement-in",
        handler: () => openMovementDialog(item, "entrada"),
      }),
      documentActionButton({
        icon: svg.minus,
        label: `Registrar saida de ${item.name}`,
        className: "movement-out",
        disabled: item.quantity <= 0,
        handler: () => openMovementDialog(item, "saida"),
      }),
      documentActionButton({
        icon: svg.edit,
        label: `Editar ${item.name}`,
        handler: () => openInventoryDialog(item),
      }),
      documentActionButton({
        icon: svg.trash,
        label: `Excluir ${item.name}`,
        className: "delete-action",
        handler: () => deleteInventoryItem(item),
      }),
    );
    actionsCell.append(actions);
    row.append(primaryCell, quantityCell, healthCell, locationCell, actionsCell);
    elements.inventoryList.append(row);
  }
}

function renderInventoryMovements() {
  elements.inventoryMovementsList.replaceChildren();
  elements.inventoryMovementsEmpty.hidden = state.inventoryMovements.length > 0;
  for (const movement of state.inventoryMovements) {
    const row = document.createElement("tr");
    const dateCell = document.createElement("td");
    dateCell.textContent = movement.timestamp;
    const itemCell = document.createElement("td");
    itemCell.className = "movement-primary";
    const itemName = document.createElement("strong");
    itemName.textContent = movement.item_name;
    const itemId = document.createElement("span");
    itemId.textContent = `Item ${movement.item_id}`;
    itemCell.append(itemName, itemId);
    const typeCell = document.createElement("td");
    const type = document.createElement("span");
    type.className = `movement-type${movement.type === "saida" ? " output" : ""}`;
    type.textContent = `${movement.type === "saida" ? "Saida" : "Entrada"} de ${movement.quantity}`;
    typeCell.append(type);
    const balanceCell = document.createElement("td");
    balanceCell.textContent = `${movement.previous_quantity} → ${movement.new_quantity}`;
    row.append(dateCell, itemCell, typeCell, balanceCell);
    elements.inventoryMovementsList.append(row);
  }
}

function setInventoryMode(mode) {
  state.inventoryMode = mode === "movements" ? "movements" : "items";
  const movements = state.inventoryMode === "movements";
  elements.inventoryItemsPanel.hidden = movements;
  elements.inventoryMovementsPanel.hidden = !movements;
  elements.inventoryItemsTab.classList.toggle("active", !movements);
  elements.inventoryMovementsTab.classList.toggle("active", movements);
  elements.inventoryItemsTab.setAttribute("aria-selected", String(!movements));
  elements.inventoryMovementsTab.setAttribute("aria-selected", String(movements));
}

async function loadInventory() {
  if (!state.inventoryVisible) return;
  try {
    const [inventory, movements] = await Promise.all([
      api("/inventory"),
      api("/inventory-movements?limit=100"),
    ]);
    state.inventoryItems = inventory.items || [];
    state.inventoryMovements = movements.items || [];
    renderInventory();
    renderInventoryMovements();
  } catch (error) {
    showToast(`Estoque: ${error.message}`, "error");
  }
}

function openInventoryDialog(item = null) {
  elements.inventoryForm.reset();
  elements.inventoryId.value = item?.id || "";
  elements.inventoryDialogTitle.textContent = item ? "Editar item" : "Novo item";
  elements.inventoryQuantityField.hidden = Boolean(item);
  if (item) {
    elements.inventoryName.value = item.name;
    elements.inventoryCategory.value = item.category || "";
    elements.inventoryMinimum.value = String(item.minimum);
    elements.inventoryMaximum.value = String(item.maximum);
    elements.inventoryLocation.value = item.location || "";
  }
  elements.inventoryDialog.showModal();
  elements.inventoryName.focus();
}

async function saveInventoryItem(event) {
  event.preventDefault();
  const id = elements.inventoryId.value;
  const payload = {
    name: elements.inventoryName.value.trim(),
    category: elements.inventoryCategory.value.trim() || "Geral",
    minimum: Number(elements.inventoryMinimum.value),
    maximum: Number(elements.inventoryMaximum.value),
    location: elements.inventoryLocation.value,
  };
  if (!id) payload.quantity = Number(elements.inventoryQuantity.value);
  elements.inventorySave.disabled = true;
  elements.inventorySave.textContent = "Salvando";
  try {
    await api(`/inventory${id ? `/${encodeURIComponent(id)}` : ""}`, {
      method: id ? "PATCH" : "POST",
      json: payload,
    });
    elements.inventoryDialog.close();
    await loadInventory();
    showToast("Item de estoque salvo localmente.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.inventorySave.disabled = false;
    elements.inventorySave.textContent = "Salvar item";
  }
}

function openMovementDialog(item, type) {
  elements.movementForm.reset();
  elements.movementItemId.value = item.id;
  elements.movementType.value = type;
  elements.movementDialogTitle.textContent = type === "saida" ? "Registrar saida" : "Registrar entrada";
  elements.movementItemName.textContent = `${item.name} · saldo atual: ${item.quantity}`;
  elements.movementQuantity.max = type === "saida" ? String(item.quantity) : "1000000000";
  elements.movementDialog.showModal();
  elements.movementQuantity.focus();
  elements.movementQuantity.select();
}

async function saveMovement(event) {
  event.preventDefault();
  const itemId = elements.movementItemId.value;
  elements.movementSave.disabled = true;
  elements.movementSave.textContent = "Registrando";
  try {
    await api(`/inventory/${encodeURIComponent(itemId)}/movements`, {
      method: "POST",
      json: {
        type: elements.movementType.value,
        quantity: Number(elements.movementQuantity.value),
      },
    });
    elements.movementDialog.close();
    await loadInventory();
    showToast("Movimentacao registrada no estoque.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.movementSave.disabled = false;
    elements.movementSave.textContent = "Registrar movimentacao";
  }
}

async function deleteInventoryItem(item) {
  if (!window.confirm(`Excluir "${item.name}" e retira-lo do estoque?`)) return;
  try {
    await api(`/inventory/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    await loadInventory();
    showToast("Item removido do estoque.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function parseLocalNumber(value) {
  let normalized = String(value || "").replace("R$", "").replace(/\s/g, "");
  if (normalized.includes(",")) normalized = normalized.replace(/\./g, "").replace(",", ".");
  const number = Number(normalized);
  return Number.isFinite(number) ? number : 0;
}

function displayCurrency(value) {
  if (!String(value || "").trim()) return "Nao informado";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(parseLocalNumber(value));
}

function matchesProductFilters(item) {
  const query = elements.productsFilter.value.trim().toLocaleLowerCase("pt-BR");
  const type = elements.productsTypeFilter.value;
  const status = elements.productsStatusFilter.value;
  const haystack = `${item.code} ${item.name} ${item.category} ${item.default_supplier}`.toLocaleLowerCase("pt-BR");
  return (!query || haystack.includes(query)) && (!type || item.type === type) && (!status || item.status === status);
}

function renderProductMetrics() {
  const items = state.productItems;
  const margins = items.map((item) => item.margin_percent).filter((value) => value !== null);
  const average = margins.length ? margins.reduce((sum, value) => sum + value, 0) / margins.length : null;
  elements.productsTotal.textContent = String(items.length);
  elements.productsActive.textContent = String(items.filter((item) => item.status === "Ativo").length);
  elements.productsProducts.textContent = String(items.filter((item) => item.type === "Produto").length);
  elements.productsServices.textContent = String(items.filter((item) => item.type === "Servico").length);
  elements.productsMargin.textContent = average === null ? "--" : `${average.toFixed(1)}%`;
  elements.productsSummary.textContent = `${items.length} ofertas no catalogo comercial local`;
}

function renderProducts() {
  renderProductMetrics();
  const items = state.productItems.filter(matchesProductFilters);
  elements.productsList.replaceChildren();
  elements.productsEmpty.hidden = items.length > 0;
  for (const item of items) {
    const row = document.createElement("tr");
    const primaryCell = document.createElement("td");
    primaryCell.className = "product-primary";
    const name = document.createElement("strong");
    name.textContent = item.name;
    const code = document.createElement("span");
    code.textContent = item.code || "Sem codigo / SKU";
    primaryCell.append(name, code);
    const profileCell = document.createElement("td");
    profileCell.className = "product-profile";
    const type = document.createElement("strong");
    type.textContent = item.type;
    const category = document.createElement("span");
    category.textContent = item.category || item.unit || "Sem categoria";
    profileCell.append(type, category);
    const priceCell = document.createElement("td");
    priceCell.className = "product-price";
    const price = document.createElement("strong");
    price.textContent = displayCurrency(item.price);
    const cost = document.createElement("span");
    cost.textContent = `Custo: ${displayCurrency(item.cost)}`;
    priceCell.append(price, cost);
    const marginCell = document.createElement("td");
    marginCell.textContent = item.margin_percent === null ? "--" : `${item.margin_percent.toFixed(1)}%`;
    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    status.className = `product-status${item.status === "Inativo" ? " inactive" : ""}`;
    status.textContent = item.status;
    statusCell.append(status);
    const actionsCell = document.createElement("td");
    const actions = document.createElement("div");
    actions.className = "product-row-actions";
    actions.append(
      documentActionButton({icon: svg.edit, label: `Editar ${item.name}`, handler: () => openProductDialog(item)}),
      documentActionButton({icon: svg.trash, label: `Excluir ${item.name}`, className: "delete-action", handler: () => deleteProduct(item)}),
    );
    actionsCell.append(actions);
    row.append(primaryCell, profileCell, priceCell, marginCell, statusCell, actionsCell);
    elements.productsList.append(row);
  }
}

async function loadProducts() {
  if (!state.productsVisible) return;
  try {
    const data = await api("/products-services");
    state.productItems = data.items || [];
    renderProducts();
  } catch (error) {
    showToast(`Produtos e servicos: ${error.message}`, "error");
  }
}

function openProductDialog(item = null) {
  elements.productForm.reset();
  elements.productId.value = item?.id || "";
  elements.productDialogTitle.textContent = item ? "Editar produto ou servico" : "Novo produto ou servico";
  if (item) {
    elements.productCode.value = item.code || "";
    elements.productType.value = item.type || "Produto";
    elements.productName.value = item.name;
    elements.productCategory.value = item.category || "";
    elements.productUnit.value = item.unit || "";
    elements.productPrice.value = item.price || "";
    elements.productCost.value = item.cost || "";
    elements.productDefaultSupplier.value = item.default_supplier || "";
    elements.productStatus.value = item.status || "Ativo";
    elements.productNotes.value = item.notes || "";
  }
  elements.productDialog.showModal();
  elements.productName.focus();
}

async function saveProduct(event) {
  event.preventDefault();
  const id = elements.productId.value;
  const payload = {
    code: elements.productCode.value.trim(),
    name: elements.productName.value.trim(),
    type: elements.productType.value,
    category: elements.productCategory.value.trim(),
    unit: elements.productUnit.value.trim(),
    price: elements.productPrice.value.trim(),
    cost: elements.productCost.value.trim(),
    default_supplier: elements.productDefaultSupplier.value.trim(),
    status: elements.productStatus.value,
    notes: elements.productNotes.value.trim(),
  };
  elements.productSave.disabled = true;
  elements.productSave.textContent = "Salvando";
  try {
    await api(`/products-services${id ? `/${encodeURIComponent(id)}` : ""}`, {
      method: id ? "PATCH" : "POST",
      json: payload,
    });
    elements.productDialog.close();
    await loadProducts();
    showToast("Cadastro comercial salvo localmente.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.productSave.disabled = false;
    elements.productSave.textContent = "Salvar cadastro";
  }
}

async function deleteProduct(item) {
  if (!window.confirm(`Excluir "${item.name}" do catalogo comercial?`)) return;
  try {
    await api(`/products-services/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    await loadProducts();
    showToast("Cadastro removido do catalogo.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function workflowPrimaryCell(title, subtitle = "") {
  const cell = document.createElement("td");
  cell.className = "workflow-primary";
  const strong = document.createElement("strong");
  strong.textContent = title;
  const span = document.createElement("span");
  span.textContent = subtitle || "Sem informacao complementar";
  cell.append(strong, span);
  return cell;
}

function workflowTextCell(primary, secondary = "") {
  const cell = document.createElement("td");
  cell.className = "workflow-detail";
  const strong = document.createElement("strong");
  strong.textContent = primary || "Nao informado";
  const span = document.createElement("span");
  span.textContent = secondary || "";
  cell.append(strong, span);
  return cell;
}

function workflowStatusCell(label, tone = "") {
  const cell = document.createElement("td");
  const badge = document.createElement("span");
  badge.className = `workflow-status ${tone}`.trim();
  badge.textContent = label;
  cell.append(badge);
  return cell;
}

function workflowActions(...buttons) {
  const cell = document.createElement("td");
  const wrap = document.createElement("div");
  wrap.className = "workflow-row-actions";
  wrap.append(...buttons);
  cell.append(wrap);
  return cell;
}

function renderQuotes() {
  const items = state.quoteItems;
  const approved = items.filter((item) => item.status === "Aprovado");
  const approvedValue = approved.reduce((sum, item) => sum + Number(item.value_number || 0), 0);
  elements.quotesTotal.textContent = String(items.length);
  elements.quotesSent.textContent = String(items.filter((item) => item.status === "Enviado").length);
  elements.quotesApproved.textContent = String(approved.length);
  elements.quotesValue.textContent = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(approvedValue);
  elements.quotesSummary.textContent = `${items.length} propostas · ${approved.length} aprovadas`;
  const query = elements.quotesFilter.value.trim().toLocaleLowerCase("pt-BR");
  const status = elements.quotesStatusFilter.value;
  const filtered = items.filter((item) => {
    const haystack = `${item.number} ${item.title} ${item.customer} ${item.responsible}`.toLocaleLowerCase("pt-BR");
    return (!query || haystack.includes(query)) && (!status || item.status === status);
  });
  elements.quotesList.replaceChildren();
  elements.quotesEmpty.hidden = filtered.length > 0;
  for (const item of filtered) {
    const row = document.createElement("tr");
    const statusLabel = item.expired ? "Validade vencida" : item.status;
    const tone = item.status === "Aprovado" ? "success" : item.expired ? "danger" : item.status === "Enviado" ? "info" : "";
    row.append(
      workflowPrimaryCell(item.title, item.number || "Numero automatico"),
      workflowTextCell(item.customer, item.responsible),
      workflowTextCell(displayCurrency(item.value), item.margin ? `Margem: ${item.margin}` : "Margem nao informada"),
      workflowTextCell(item.valid_until ? formatShortDate(item.valid_until) : "Sem validade", item.expired ? "Vencida" : ""),
      workflowStatusCell(statusLabel, tone),
      workflowActions(
        documentActionButton({ icon: svg.edit, label: `Editar ${item.title}`, handler: () => openQuoteDialog(item) }),
        documentActionButton({ icon: svg.trash, label: `Excluir ${item.title}`, className: "delete-action", handler: () => deleteQuote(item) }),
      ),
    );
    elements.quotesList.append(row);
  }
}

async function loadQuotes() {
  if (!state.quotesVisible) return;
  try {
    const data = await api("/quotes");
    state.quoteItems = data.items || [];
    renderQuotes();
  } catch (error) {
    showToast(`Orcamentos: ${error.message}`, "error");
  }
}

function openQuoteDialog(item = null) {
  elements.quoteForm.reset();
  elements.quoteId.value = item?.id || "";
  elements.quoteDialogTitle.textContent = item ? "Editar orcamento" : "Novo orcamento";
  if (item) {
    elements.quoteNumber.value = item.number || "";
    elements.quoteTitle.value = item.title;
    elements.quoteCustomer.value = item.customer || "";
    elements.quoteValidUntil.value = item.valid_until || "";
    elements.quoteValue.value = item.value || "";
    elements.quoteMargin.value = item.margin || "";
    elements.quoteResponsible.value = item.responsible || "";
    elements.quoteStatus.value = item.status || "Rascunho";
    elements.quoteItems.value = item.items || "";
    elements.quoteNotes.value = item.notes || "";
  }
  elements.quoteDialog.showModal();
  elements.quoteTitle.focus();
}

async function saveQuote(event) {
  event.preventDefault();
  const id = elements.quoteId.value;
  const payload = {
    number: elements.quoteNumber.value.trim(), title: elements.quoteTitle.value.trim(),
    customer: elements.quoteCustomer.value.trim(), valid_until: elements.quoteValidUntil.value,
    value: elements.quoteValue.value.trim(), margin: elements.quoteMargin.value.trim(),
    responsible: elements.quoteResponsible.value.trim(), status: elements.quoteStatus.value,
    items: elements.quoteItems.value.trim(), notes: elements.quoteNotes.value.trim(),
  };
  elements.quoteSave.disabled = true;
  elements.quoteSave.textContent = "Salvando";
  try {
    await api(`/quotes${id ? `/${encodeURIComponent(id)}` : ""}`, { method: id ? "PATCH" : "POST", json: payload });
    elements.quoteDialog.close();
    await loadQuotes();
    showToast("Orcamento salvo localmente.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    elements.quoteSave.disabled = false;
    elements.quoteSave.textContent = "Salvar orcamento";
  }
}

async function deleteQuote(item) {
  if (!window.confirm(`Excluir o orcamento "${item.title}"?`)) return;
  try {
    await api(`/quotes/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    await loadQuotes();
    showToast("Orcamento removido.");
  } catch (error) { showToast(error.message, "error"); }
}

function renderReports() {
  const items = state.reportItems;
  elements.reportsTotal.textContent = String(items.length);
  elements.reportsGenerated.textContent = String(items.filter((item) => item.status === "Gerado").length);
  elements.reportsPdf.textContent = String(items.filter((item) => item.format === "pdf").length);
  elements.reportsSources.textContent = String(new Set(items.map((item) => item.source).filter(Boolean)).size);
  elements.reportsSummary.textContent = `${items.length} arquivos e modelos registrados localmente`;
  const query = elements.reportsFilter.value.trim().toLocaleLowerCase("pt-BR");
  const format = elements.reportsFormatFilter.value;
  const filtered = items.filter((item) => {
    const haystack = `${item.title} ${item.source} ${item.indicator} ${item.type}`.toLocaleLowerCase("pt-BR");
    return (!query || haystack.includes(query)) && (!format || item.format === format);
  });
  elements.reportsList.replaceChildren();
  elements.reportsEmpty.hidden = filtered.length > 0;
  for (const item of filtered) {
    const row = document.createElement("tr");
    const actions = [];
    if (item.downloadable) {
      actions.push(documentActionButton({ icon: svg.download, label: `Baixar ${item.title}`, handler: () => downloadReport(item) }));
    }
    actions.push(documentActionButton({ icon: svg.trash, label: `Excluir ${item.title}`, className: "delete-action", handler: () => deleteReport(item) }));
    row.append(
      workflowPrimaryCell(item.title, item.type),
      workflowTextCell(item.source, item.period || "Periodo atual"),
      workflowTextCell(item.indicator || "Resumo operacional", item.periodicity),
      workflowTextCell((item.format || "--").toUpperCase(), item.updated_at),
      workflowStatusCell(item.status, item.status === "Gerado" ? "success" : ""),
      workflowActions(...actions),
    );
    elements.reportsList.append(row);
  }
}

async function loadReports() {
  if (!state.reportsVisible) return;
  try {
    const data = await api("/reports");
    state.reportItems = data.items || [];
    renderReports();
  } catch (error) { showToast(`Relatorios: ${error.message}`, "error"); }
}

function openReportDialog() {
  elements.reportForm.reset();
  elements.reportPeriod.value = "Atual";
  elements.reportDialog.showModal();
  elements.reportTitle.focus();
}

async function generateReport(event) {
  event.preventDefault();
  const payload = {
    title: elements.reportTitle.value.trim(), report_type: elements.reportType.value,
    period: elements.reportPeriod.value.trim(), source: elements.reportSource.value,
    indicator: elements.reportIndicator.value.trim(), periodicity: elements.reportPeriodicity.value,
    responsible: elements.reportResponsible.value.trim(), output_format: elements.reportFormat.value,
    notes: elements.reportNotes.value.trim(),
  };
  elements.reportGenerate.disabled = true;
  elements.reportGenerate.textContent = "Gerando localmente";
  try {
    const data = await api("/reports/generate", { method: "POST", json: payload });
    elements.reportDialog.close();
    await loadReports();
    showToast("Relatorio gerado. O arquivo esta pronto para baixar.");
    if (data.item?.downloadable) downloadReport(data.item);
  } catch (error) { showToast(error.message, "error"); }
  finally { elements.reportGenerate.disabled = false; elements.reportGenerate.textContent = "Gerar arquivo"; }
}

async function downloadReport(item) {
  try {
    const blob = await apiBinary(`/reports/${encodeURIComponent(item.id)}/download`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${item.title}.${item.format || "pdf"}`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { showToast(error.message, "error"); }
}

async function deleteReport(item) {
  if (!window.confirm(`Excluir o relatorio "${item.title}" e seu arquivo local?`)) return;
  try {
    await api(`/reports/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    await loadReports();
    showToast("Relatorio removido.");
  } catch (error) { showToast(error.message, "error"); }
}

function formatShortDate(value) {
  if (!value) return "Nao informado";
  const date = new Date(`${value.slice(0, 10)}T12:00:00`);
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("pt-BR").format(date);
}

function renderCases() {
  const items = state.caseItems;
  elements.casesTotal.textContent = String(items.length);
  elements.casesOpen.textContent = String(items.filter((item) => !["Concluido", "Arquivado"].includes(item.status)).length);
  elements.casesDue.textContent = String(items.filter((item) => item.due_soon).length);
  elements.casesOverdue.textContent = String(items.filter((item) => item.overdue).length);
  elements.casesSummary.textContent = `${items.length} acompanhamentos · ${items.filter((item) => item.overdue).length} atrasados`;
  const query = elements.casesFilter.value.trim().toLocaleLowerCase("pt-BR");
  const priority = elements.casesPriorityFilter.value;
  const deadline = elements.casesDeadlineFilter.value;
  const filtered = items.filter((item) => {
    const haystack = `${item.title} ${item.customer} ${item.responsible} ${item.next_step}`.toLocaleLowerCase("pt-BR");
    const deadlineMatch = !deadline || (deadline === "overdue" && item.overdue) || (deadline === "due" && item.due_soon);
    return (!query || haystack.includes(query)) && (!priority || item.priority === priority) && deadlineMatch;
  });
  elements.casesList.replaceChildren();
  elements.casesEmpty.hidden = filtered.length > 0;
  for (const item of filtered) {
    const row = document.createElement("tr");
    const deadlineNote = item.overdue ? `${Math.abs(item.days_remaining)} dias em atraso` : item.due_soon ? `${item.days_remaining} dias restantes` : item.priority;
    row.append(
      workflowPrimaryCell(item.title, item.customer || item.type),
      workflowTextCell(formatShortDate(item.deadline), deadlineNote),
      workflowTextCell(item.responsible, item.priority),
      workflowTextCell(item.next_step, item.type),
      workflowStatusCell(item.overdue ? "Atrasado" : item.status, item.overdue ? "danger" : item.due_soon ? "warning" : item.status === "Concluido" ? "success" : ""),
      workflowActions(
        documentActionButton({ icon: svg.edit, label: `Editar ${item.title}`, handler: () => openCaseDialog(item) }),
        documentActionButton({ icon: svg.trash, label: `Excluir ${item.title}`, className: "delete-action", handler: () => deleteCase(item) }),
      ),
    );
    elements.casesList.append(row);
  }
}

async function loadCases() {
  if (!state.casesVisible) return;
  try {
    const data = await api("/cases-deadlines");
    state.caseItems = data.items || [];
    renderCases();
  } catch (error) { showToast(`Processos e prazos: ${error.message}`, "error"); }
}

function openCaseDialog(item = null) {
  elements.caseForm.reset();
  elements.caseId.value = item?.id || "";
  elements.caseDialogTitle.textContent = item ? "Editar processo ou prazo" : "Novo processo ou prazo";
  if (item) {
    elements.caseTitle.value = item.title; elements.caseCustomer.value = item.customer || "";
    elements.caseType.value = item.type || ""; elements.caseDeadline.value = item.deadline || "";
    elements.casePriority.value = item.priority || "Normal"; elements.caseResponsible.value = item.responsible || "";
    elements.caseStatus.value = item.status || "Novo"; elements.caseNextStep.value = item.next_step || "";
    elements.caseNotes.value = item.notes || "";
  }
  elements.caseDialog.showModal();
  elements.caseTitle.focus();
}

async function saveCase(event) {
  event.preventDefault();
  const id = elements.caseId.value;
  const payload = {
    title: elements.caseTitle.value.trim(), customer: elements.caseCustomer.value.trim(),
    case_type: elements.caseType.value.trim(), deadline: elements.caseDeadline.value,
    priority: elements.casePriority.value, responsible: elements.caseResponsible.value.trim(),
    status: elements.caseStatus.value, next_step: elements.caseNextStep.value.trim(), notes: elements.caseNotes.value.trim(),
  };
  elements.caseSave.disabled = true;
  elements.caseSave.textContent = "Salvando";
  try {
    await api(`/cases-deadlines${id ? `/${encodeURIComponent(id)}` : ""}`, { method: id ? "PATCH" : "POST", json: payload });
    elements.caseDialog.close(); await loadCases(); showToast("Acompanhamento salvo localmente.");
  } catch (error) { showToast(error.message, "error"); }
  finally { elements.caseSave.disabled = false; elements.caseSave.textContent = "Salvar acompanhamento"; }
}

async function deleteCase(item) {
  if (!window.confirm(`Excluir "${item.title}"?`)) return;
  try {
    await api(`/cases-deadlines/${encodeURIComponent(item.id)}`, { method: "DELETE" });
    await loadCases(); showToast("Acompanhamento removido.");
  } catch (error) { showToast(error.message, "error"); }
}

async function loadModels() {
  try {
    const data = await api("/models");
    const saved = localStorage.getItem("celsius-model-id") || "";
    const readyIds = new Set();
    for (const model of data.items || []) {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = model.ready
        ? model.display_name
        : `${model.display_name} - nao instalado`;
      option.disabled = !model.ready;
      option.title = model.notes || model.role;
      elements.modelSelect.append(option);
      if (model.ready) readyIds.add(model.id);
    }
    state.modelId = readyIds.has(saved) ? saved : "";
    elements.modelSelect.value = state.modelId;
  } catch (error) {
    elements.modelSelect.disabled = true;
    showToast(`Modelos: ${error.message}`, "error");
  }
}

function setJarvisMode(mode) {
  state.jarvisMode = mode;
  elements.jarvisVisual.dataset.state = mode;
  const labels = {
    idle: "Jarvis ativo",
    thinking: "Celsius pensando",
    speaking: "Celsius falando",
  };
  elements.jarvisStatus.textContent = labels[mode] || labels.idle;
}

function initializeJarvisParticles() {
  if (state.jarvisParticles.length) return;
  const total = Math.max(240, Math.min(Number(state.jarvisParticleCount || 420), 720));
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  for (let index = 0; index < total; index += 1) {
    const y = 1 - (index / (total - 1)) * 2;
    const radius = Math.sqrt(Math.max(0, 1 - y * y));
    const angle = goldenAngle * index;
    state.jarvisParticles.push({
      x: Math.cos(angle) * radius,
      y,
      z: Math.sin(angle) * radius,
      size: 0.55 + (index % 7) * 0.12,
      phase: (index * 1.618) % (Math.PI * 2),
      band: index % 3,
    });
  }
}

function jarvisPalette() {
  if (state.jarvisMode === "speaking") {
    return { front: [255, 166, 69], back: [218, 55, 69], ring: [255, 118, 58] };
  }
  if (state.jarvisMode === "thinking") {
    return { front: [55, 210, 191], back: [55, 102, 194], ring: [46, 176, 194] };
  }
  return { front: [92, 205, 238], back: [56, 91, 169], ring: [72, 151, 211] };
}

function jarvisColor(back, front, depth, alpha = 1) {
  const mix = (start, end) => Math.round(start + (end - start) * depth);
  return `rgba(${mix(back[0], front[0])}, ${mix(back[1], front[1])}, ${mix(back[2], front[2])}, ${alpha})`;
}

function animateJarvis(timestamp = 0) {
  if (!state.jarvisEnabled) {
    state.jarvisAnimationId = null;
    return;
  }
  const canvas = elements.jarvisCanvas;
  const context = canvas.getContext("2d");
  const palette = jarvisPalette();
  const energy = state.jarvisMode === "speaking" ? 1 : state.jarvisMode === "thinking" ? 0.68 : 0.36;
  const rotationY = timestamp * (0.00026 + energy * 0.00034);
  const rotationX = timestamp * (0.00015 + energy * 0.00015);
  const rotationZ = timestamp * 0.00009;
  const pulsePhase = timestamp * (0.0045 + energy * 0.0025);
  const pulse = 1 + Math.sin(pulsePhase) * (0.025 + energy * 0.045);
  const cosY = Math.cos(rotationY);
  const sinY = Math.sin(rotationY);
  const cosX = Math.cos(rotationX);
  const sinX = Math.sin(rotationX);
  const cosZ = Math.cos(rotationZ);
  const sinZ = Math.sin(rotationZ);
  const center = canvas.width / 2;
  const sphereRadius = canvas.width * (0.29 + energy * 0.025) * pulse;

  context.clearRect(0, 0, canvas.width, canvas.height);
  const projected = state.jarvisParticles.map((point) => {
    const wave = Math.sin(pulsePhase * (1.4 + point.band * 0.24) + point.phase + point.z * 5);
    const displacement = 1 + Math.max(0, wave) * energy * 0.11;
    const bx = point.x * displacement;
    const by = point.y * displacement;
    const bz = point.z * displacement;
    const x1 = bx * cosY - bz * sinY;
    const z1 = bx * sinY + bz * cosY;
    const y1 = by * cosX - z1 * sinX;
    const z2 = by * sinX + z1 * cosX;
    return {
      x: x1 * cosZ - y1 * sinZ,
      y: x1 * sinZ + y1 * cosZ,
      z: z2,
      size: point.size,
      wave,
    };
  }).sort((a, b) => a.z - b.z);

  context.save();
  context.globalCompositeOperation = "lighter";
  for (const point of projected) {
    const depth = (point.z + 1) / 2;
    const alpha = 0.2 + depth * 0.72;
    context.fillStyle = jarvisColor(palette.back, palette.front, depth, alpha);
    context.beginPath();
    context.arc(
      center + point.x * sphereRadius,
      center + point.y * sphereRadius,
      Math.max(0.65, point.size * (0.5 + depth) * (0.9 + energy * 0.42)),
      0,
      Math.PI * 2,
    );
    context.fill();
  }
  const ringPulse = 1 + Math.sin(pulsePhase) * 0.055;
  context.strokeStyle = `rgba(${palette.ring.join(",")}, ${0.18 + energy * 0.3})`;
  context.lineWidth = 1.1 + energy * 0.7;
  context.beginPath();
  context.arc(center, center, sphereRadius * 1.08 * ringPulse, 0, Math.PI * 2);
  context.stroke();
  if (state.jarvisMode !== "idle") {
    context.strokeStyle = `rgba(${palette.front.join(",")}, ${0.08 + energy * 0.12})`;
    context.lineWidth = 0.8;
    context.beginPath();
    context.arc(center, center, sphereRadius * (1.25 + Math.sin(pulsePhase) * 0.08), 0, Math.PI * 2);
    context.stroke();
  }
  context.restore();
  state.jarvisAnimationId = window.requestAnimationFrame(animateJarvis);
}

function setJarvisPosition(left, top, persist = false) {
  const visual = elements.jarvisVisual;
  const width = visual.offsetWidth || 150;
  const height = visual.offsetHeight || 175;
  const maxLeft = Math.max(8, window.innerWidth - width - 8);
  const maxTop = Math.max(8, window.innerHeight - height - 8);
  const safeLeft = Math.max(8, Math.min(Number(left) || 8, maxLeft));
  const safeTop = Math.max(8, Math.min(Number(top) || 8, maxTop));
  visual.style.left = `${safeLeft}px`;
  visual.style.top = `${safeTop}px`;
  visual.style.right = "auto";
  if (persist) {
    const x = maxLeft > 8 ? (safeLeft - 8) / (maxLeft - 8) : 1;
    const y = maxTop > 8 ? (safeTop - 8) / (maxTop - 8) : 0;
    localStorage.setItem("celsius-jarvis-position", JSON.stringify({ x, y }));
  }
}

function resetJarvisPosition() {
  localStorage.removeItem("celsius-jarvis-position");
  const width = elements.jarvisVisual.offsetWidth || 150;
  setJarvisPosition(window.innerWidth - width - (window.innerWidth <= 560 ? 10 : 28), 76);
}

function restoreJarvisPosition() {
  if (!state.jarvisEnabled) return;
  const saved = localStorage.getItem("celsius-jarvis-position");
  if (!saved) {
    resetJarvisPosition();
    return;
  }
  try {
    const position = JSON.parse(saved);
    const width = elements.jarvisVisual.offsetWidth || 150;
    const height = elements.jarvisVisual.offsetHeight || 175;
    const maxLeft = Math.max(8, window.innerWidth - width - 8);
    const maxTop = Math.max(8, window.innerHeight - height - 8);
    setJarvisPosition(8 + Number(position.x || 0) * (maxLeft - 8), 8 + Number(position.y || 0) * (maxTop - 8));
  } catch (_error) {
    resetJarvisPosition();
  }
}

function startJarvisDrag(event) {
  if (!state.jarvisEnabled || event.button !== 0) return;
  const rect = elements.jarvisVisual.getBoundingClientRect();
  state.jarvisDrag = { pointerId: event.pointerId, offsetX: event.clientX - rect.left, offsetY: event.clientY - rect.top };
  elements.jarvisVisual.classList.add("dragging");
  elements.jarvisStatus.setPointerCapture(event.pointerId);
  event.preventDefault();
}

function moveJarvis(event) {
  if (!state.jarvisDrag || state.jarvisDrag.pointerId !== event.pointerId) return;
  setJarvisPosition(event.clientX - state.jarvisDrag.offsetX, event.clientY - state.jarvisDrag.offsetY);
}

function stopJarvisDrag(event) {
  if (!state.jarvisDrag || state.jarvisDrag.pointerId !== event.pointerId) return;
  const rect = elements.jarvisVisual.getBoundingClientRect();
  state.jarvisDrag = null;
  elements.jarvisVisual.classList.remove("dragging");
  setJarvisPosition(rect.left, rect.top, true);
}

function setJarvisEnabled(enabled) {
  state.jarvisEnabled = Boolean(enabled);
  elements.jarvisToggle.checked = state.jarvisEnabled;
  elements.jarvisVisual.hidden = !state.jarvisEnabled;
  localStorage.setItem("celsius-jarvis-enabled", String(state.jarvisEnabled));
  if (state.jarvisEnabled) {
    initializeJarvisParticles();
    window.requestAnimationFrame(restoreJarvisPosition);
    if (!state.jarvisAnimationId) {
      state.jarvisAnimationId = window.requestAnimationFrame(animateJarvis);
    }
  } else if (state.jarvisAnimationId) {
    window.cancelAnimationFrame(state.jarvisAnimationId);
    state.jarvisAnimationId = null;
    elements.jarvisCanvas.getContext("2d")?.clearRect(0, 0, elements.jarvisCanvas.width, elements.jarvisCanvas.height);
  }
}

function nextSpeechChunk(force = false) {
  const text = state.speechBuffer.trim();
  if (!text) return "";
  if (force) {
    state.speechBuffer = "";
    return text;
  }
  let boundary = -1;
  for (const match of text.matchAll(/[.!?;:](?:\s|$)/g)) {
    if (match.index >= 35) {
      boundary = match.index;
      break;
    }
  }
  if (boundary >= 0) {
    const chunk = text.slice(0, boundary + 1).trim();
    state.speechBuffer = text.slice(boundary + 1).trimStart();
    return chunk;
  }
  if (text.length >= 320) {
    const splitAt = Math.max(120, text.lastIndexOf(" ", 300));
    const chunk = text.slice(0, splitAt).trim();
    state.speechBuffer = text.slice(splitAt).trimStart();
    return chunk;
  }
  return "";
}

function stopSpeech() {
  state.speechGeneration += 1;
  state.speechBuffer = "";
  state.speechReceivedChunks = false;
  state.speechAbortController?.abort();
  state.speechAbortController = null;
  state.currentAudioStop?.();
  state.currentAudioStop = null;
  if (state.currentAudio) {
    state.currentAudio.pause();
    state.currentAudio.src = "";
    state.currentAudio = null;
  }
  state.speechSynthesisChain = Promise.resolve();
  state.speechPlaybackChain = Promise.resolve();
  state.speechPendingPlayback = 0;
  if (!state.busy) setJarvisMode("idle");
}

function smoothSpeechBoundary(text, continuation) {
  const clean = text.trim();
  return continuation ? clean.replace(/\.\s*$/, ",") : clean;
}

async function playSpeechBlob(blob, generation) {
  if (!state.voiceEnabled || generation !== state.speechGeneration) return;
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  state.currentAudio = audio;
  setJarvisMode("speaking");
  try {
    await new Promise((resolve, reject) => {
      let settled = false;
      const finish = (error = null) => {
        if (settled) return;
        settled = true;
        state.currentAudioStop = null;
        if (error) reject(error);
        else resolve();
      };
      state.currentAudioStop = () => finish();
      audio.addEventListener("ended", () => finish(), { once: true });
      audio.addEventListener(
        "error",
        () => finish(new Error("Falha ao reproduzir o audio.")),
        { once: true },
      );
      audio.play().catch(finish);
    });
  } finally {
    URL.revokeObjectURL(url);
    if (state.currentAudio === audio) state.currentAudio = null;
    if (generation === state.speechGeneration) {
      state.speechPendingPlayback = Math.max(0, state.speechPendingPlayback - 1);
      if (!state.speechPendingPlayback) setJarvisMode(state.busy ? "thinking" : "idle");
    }
  }
}

function queueSpeech(text, continuation = true) {
  const clean = smoothSpeechBoundary(text, continuation);
  if (!state.voiceEnabled || !clean) return;
  const generation = state.speechGeneration;
  state.speechSynthesisChain = state.speechSynthesisChain.then(async () => {
    if (!state.voiceEnabled || generation !== state.speechGeneration) return;
    const controller = new AbortController();
    state.speechAbortController = controller;
    let blob;
    try {
      blob = await apiBinary("/voice/synthesize", {
        method: "POST",
        json: { text: clean },
        signal: controller.signal,
      });
    } finally {
      if (state.speechAbortController === controller) state.speechAbortController = null;
    }
    if (!state.voiceEnabled || generation !== state.speechGeneration) return;
    state.speechPendingPlayback += 1;
    state.speechPlaybackChain = state.speechPlaybackChain
      .then(() => playSpeechBlob(blob, generation))
      .catch((error) => {
        if (error.name !== "AbortError") showToast(`Voz: ${error.message}`, "error");
      });
  }).catch((error) => {
    if (error.name !== "AbortError") showToast(`Voz: ${error.message}`, "error");
  });
}

function consumeSpeechText(text, force = false) {
  if (!state.voiceEnabled) return;
  if (text) state.speechBuffer += text;
  let chunk = nextSpeechChunk(force);
  while (chunk) {
    queueSpeech(chunk, !force);
    chunk = nextSpeechChunk(force);
  }
}

function setVoiceEnabled(enabled, notify = true) {
  state.voiceEnabled = Boolean(enabled);
  elements.voiceToggle.checked = state.voiceEnabled;
  localStorage.setItem("celsius-voice-enabled", String(state.voiceEnabled));
  if (!state.voiceEnabled) {
    stopSpeech();
  } else if (notify && state.voiceRequiresInternet) {
    showToast("A voz Edge TTS usa internet; o texto e o modelo continuam locais.");
  }
}

async function loadVoiceCapabilities() {
  try {
    const data = await api("/voice");
    state.voiceRequiresInternet = Boolean(data.requires_internet);
    const savedVoice = localStorage.getItem("celsius-voice-enabled") === "true";
    const savedJarvis = localStorage.getItem("celsius-jarvis-enabled");
    state.jarvisParticleCount = Number(data.jarvis?.particle_count || 420);
    state.jarvisParticles = [];
    setVoiceEnabled(savedVoice, false);
    setJarvisEnabled(savedJarvis === null ? Boolean(data.jarvis?.default_enabled) : savedJarvis === "true");
  } catch (error) {
    elements.voiceToggle.disabled = true;
    elements.jarvisToggle.disabled = true;
    showToast(`Voz: ${error.message}`, "error");
  }
}

function autoResizeInput() {
  elements.input.style.height = "auto";
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 180)}px`;
  updateSendState();
}

function updateSendState() {
  const hasContent = Boolean(elements.input.value.trim() || state.files.length);
  elements.sendButton.disabled = state.busy ? false : !hasContent;
  elements.sendButton.classList.toggle("busy", state.busy);
  elements.sendButton.setAttribute(
    "aria-label",
    state.busy ? "Interromper resposta" : "Enviar mensagem",
  );
  elements.attachButton.disabled = state.busy;
  elements.voiceInputButton.disabled = state.busy || state.voiceInputBusy;
}

function isNearBottom() {
  const distance = elements.messages.scrollHeight - elements.messages.scrollTop - elements.messages.clientHeight;
  return distance < 120;
}

function scrollToLatest(force = false) {
  if (force || isNearBottom()) {
    elements.messages.scrollTop = elements.messages.scrollHeight;
    elements.scrollLatest.hidden = true;
  } else {
    elements.scrollLatest.hidden = false;
  }
}

function appendInline(parent, text) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g;
  let position = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > position) {
      parent.append(document.createTextNode(text.slice(position, match.index)));
    }
    const token = match[0];
    if (token.startsWith("**")) {
      const strong = document.createElement("strong");
      strong.textContent = token.slice(2, -2);
      parent.append(strong);
    } else if (token.startsWith("`")) {
      const code = document.createElement("code");
      code.textContent = token.slice(1, -1);
      parent.append(code);
    } else {
      const parts = token.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      const link = document.createElement("a");
      link.textContent = parts[1];
      link.href = parts[2];
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      parent.append(link);
    }
    position = match.index + token.length;
  }
  if (position < text.length) {
    parent.append(document.createTextNode(text.slice(position)));
  }
}

function renderMarkdown(container, text) {
  container.replaceChildren();
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      const content = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        content.push(lines[index]);
        index += 1;
      }
      code.textContent = content.join("\n");
      pre.append(code);
      container.append(pre);
      index += 1;
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const title = document.createElement(`h${heading[1].length}`);
      appendInline(title, heading[2]);
      container.append(title);
      index += 1;
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      const list = document.createElement("ul");
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        const item = document.createElement("li");
        appendInline(item, lines[index].replace(/^[-*]\s+/, ""));
        list.append(item);
        index += 1;
      }
      container.append(list);
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const list = document.createElement("ol");
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        const item = document.createElement("li");
        appendInline(item, lines[index].replace(/^\d+\.\s+/, ""));
        list.append(item);
        index += 1;
      }
      container.append(list);
      continue;
    }
    if (line.startsWith("> ")) {
      const quote = document.createElement("blockquote");
      appendInline(quote, line.slice(2));
      container.append(quote);
      index += 1;
      continue;
    }

    const paragraph = document.createElement("p");
    const paragraphLines = [line];
    index += 1;
    while (
      index < lines.length
      && lines[index].trim()
      && !/^(#{1,3})\s+/.test(lines[index])
      && !/^[-*]\s+/.test(lines[index])
      && !/^\d+\.\s+/.test(lines[index])
      && !lines[index].startsWith("```")
    ) {
      paragraphLines.push(lines[index]);
      index += 1;
    }
    appendInline(paragraph, paragraphLines.join("\n"));
    container.append(paragraph);
  }
}

function attachmentName(item) {
  return item.name || item.filename || "Arquivo";
}

function renderMessageAttachments(container, attachments = []) {
  if (!attachments.length) return;
  const list = document.createElement("div");
  list.className = "message-attachments";
  for (const attachment of attachments) {
    const item = document.createElement("span");
    item.className = "message-file";
    item.innerHTML = svg.file;
    const name = document.createElement("span");
    name.textContent = attachmentName(attachment);
    item.append(name);
    list.append(item);
  }
  container.append(list);
}

function createMessage(role, content = "", attachments = []) {
  elements.emptyState.hidden = true;
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "message-avatar";
  avatar.textContent = role === "assistant" ? "C" : "V";
  const column = document.createElement("div");
  column.className = "message-column";
  const name = document.createElement("div");
  name.className = "message-name";
  name.textContent = role === "assistant" ? "Celsius" : "Voce";
  const status = document.createElement("div");
  status.className = "message-status";
  const body = document.createElement("div");
  body.className = "message-content";
  renderMarkdown(body, content);
  renderMessageAttachments(column, attachments);
  column.prepend(name, status, body);
  article.append(avatar, column);
  elements.messages.append(article);
  scrollToLatest(true);
  return { article, status, body };
}

function setStreamStatus(text) {
  if (!state.streamMessage) {
    state.streamMessage = createMessage("assistant");
  }
  state.streamMessage.status.textContent = text || "";
  state.streamMessage.status.classList.toggle("active", Boolean(text));
  if (text && state.jarvisEnabled && state.jarvisMode !== "speaking") {
    setJarvisMode("thinking");
  }
}

function appendStream(text) {
  if (!state.streamMessage) {
    state.streamMessage = createMessage("assistant");
  }
  state.streamingText += text;
  state.speechReceivedChunks = true;
  consumeSpeechText(text);
  renderMarkdown(state.streamMessage.body, state.streamingText);
  state.streamMessage.body.classList.add("stream-caret");
  scrollToLatest();
}

function finishStream(text, status = "completed") {
  if (!state.streamMessage) {
    state.streamMessage = createMessage("assistant");
  }
  state.streamingText = text || state.streamingText;
  if (status === "completed" && state.voiceEnabled) {
    if (!state.speechReceivedChunks) consumeSpeechText(state.streamingText);
    consumeSpeechText("", true);
  } else if (status !== "completed") {
    stopSpeech();
  }
  renderMarkdown(state.streamMessage.body, state.streamingText);
  state.streamMessage.body.classList.remove("stream-caret");
  state.streamMessage.status.textContent = "";
  state.streamMessage.status.classList.remove("active");
  if (status === "cancelled" && !state.streamingText) {
    renderMarkdown(state.streamMessage.body, "Resposta interrompida.");
  }
  state.busy = false;
  state.sendPending = false;
  state.activeJobId = "";
  window.clearInterval(state.pollTimer);
  state.pollTimer = null;
  updateSendState();
  if (!state.voiceEnabled || !state.speechBuffer) setJarvisMode("idle");
  scrollToLatest(true);
  loadConversations();
}

function resetConversation() {
  stopSpeech();
  state.conversationId = "";
  state.streamingText = "";
  state.streamMessage = null;
  elements.messages.replaceChildren(elements.emptyState);
  elements.emptyState.hidden = false;
  state.chatTitle = "Nova conversa";
  elements.conversationTitle.textContent = state.chatTitle;
  document.querySelectorAll(".conversation-item.active").forEach((item) => item.classList.remove("active"));
  document.querySelectorAll(".conversation-row.active").forEach((item) => item.classList.remove("active"));
  showView("chat");
  elements.input.focus();
}

function renderConversationList(items) {
  elements.conversationList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "conversation-placeholder";
    empty.textContent = "Nenhuma conversa ainda.";
    elements.conversationList.append(empty);
    return;
  }
  for (const conversation of items) {
    const row = document.createElement("div");
    row.className = "conversation-row";
    row.classList.toggle("active", conversation.id === state.conversationId);
    const button = document.createElement("button");
    button.className = "conversation-item";
    button.classList.toggle("active", conversation.id === state.conversationId);
    button.type = "button";
    button.dataset.id = conversation.id;
    button.innerHTML = svg.message;
    const title = document.createElement("span");
    title.textContent = conversation.title || "Nova conversa";
    button.append(title);
    button.addEventListener("click", () => loadConversation(conversation.id));
    const remove = document.createElement("button");
    remove.className = "conversation-delete";
    remove.type = "button";
    remove.title = "Excluir conversa";
    remove.setAttribute("aria-label", `Excluir conversa ${title.textContent}`);
    remove.innerHTML = svg.trash;
    remove.addEventListener("click", () => deleteConversation(conversation));
    row.append(button, remove);
    elements.conversationList.append(row);
  }
}

async function deleteConversation(conversation) {
  if (state.busy && state.conversationId === conversation.id) {
    showToast("Interrompa a resposta atual antes de excluir esta conversa.", "error");
    return;
  }
  if (!window.confirm(`Excluir definitivamente a conversa "${conversation.title || "Nova conversa"}"?`)) return;
  try {
    await api(`/chat/conversations/${encodeURIComponent(conversation.id)}`, {
      method: "DELETE",
    });
    if (state.conversationId === conversation.id) resetConversation();
    await loadConversations();
    showToast("Conversa excluida.");
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadConversations() {
  try {
    const data = await api("/chat/conversations");
    renderConversationList(data.items || []);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadConversation(conversationId) {
  if (state.busy) {
    showToast("Conclua ou interrompa a resposta atual.");
    return;
  }
  try {
    const data = await api(`/chat/conversations/${encodeURIComponent(conversationId)}`);
    const conversation = data.conversation;
    state.conversationId = conversation.id;
    state.streamMessage = null;
    state.streamingText = "";
    elements.messages.replaceChildren();
    for (const message of conversation.messages || []) {
      createMessage(
        message.role === "assistant" ? "assistant" : "user",
        message.content || "",
        message.metadata?.attachments || [],
      );
    }
    if (!(conversation.messages || []).length) {
      elements.messages.append(elements.emptyState);
      elements.emptyState.hidden = false;
    }
    state.chatTitle = conversation.title || "Nova conversa";
    elements.conversationTitle.textContent = state.chatTitle;
    document.querySelectorAll(".conversation-item").forEach((item) => {
      item.classList.toggle("active", item.dataset.id === conversation.id);
    });
    document.querySelectorAll(".conversation-row").forEach((item) => {
      item.classList.toggle("active", item.querySelector(".conversation-item")?.dataset.id === conversation.id);
    });
    scrollToLatest(true);
    showView("chat");
  } catch (error) {
    showToast(error.message, "error");
  }
}

function renderSelectedFiles() {
  elements.attachmentList.replaceChildren();
  state.files.forEach((file, index) => {
    const chip = document.createElement("div");
    chip.className = "attachment-chip";
    chip.innerHTML = svg.file;
    const name = document.createElement("span");
    name.textContent = file.name;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remover ${file.name}`);
    remove.innerHTML = svg.close;
    remove.addEventListener("click", () => {
      state.files.splice(index, 1);
      renderSelectedFiles();
      updateSendState();
    });
    chip.append(name, remove);
    elements.attachmentList.append(chip);
  });
}

function selectFiles(fileList) {
  for (const file of Array.from(fileList)) {
    if (state.files.length >= 10) {
      showToast("Limite de 10 anexos por mensagem.", "error");
      break;
    }
    const duplicate = state.files.some((current) => current.name === file.name && current.size === file.size);
    if (!duplicate) state.files.push(file);
  }
  elements.fileInput.value = "";
  renderSelectedFiles();
  updateSendState();
}

async function uploadFiles(files) {
  const attachmentIds = [];
  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    setStreamStatus(`Enviando anexo ${index + 1} de ${files.length}`);
    const data = await api("/chat/attachments", {
      method: "POST",
      headers: { "X-Celsius-Filename": encodeURIComponent(file.name) },
      body: file,
    });
    attachmentIds.push(data.attachment.id);
  }
  return attachmentIds;
}

function startPolling(jobId) {
  window.clearInterval(state.pollTimer);
  state.pollTimer = window.setInterval(async () => {
    try {
      const data = await api(`/chat/jobs/${jobId}`);
      const job = data.job;
      if (job.status === "completed") finishStream(job.response, "completed");
      if (job.status === "failed") {
        finishStream(`Erro: ${job.error}`, "failed");
      }
      if (job.status === "cancelled") finishStream("", "cancelled");
    } catch (_error) {
      // WebSocket reconnect and the next poll will recover transient failures.
    }
  }, 800);
}

function setVoiceInputStatus(text = "") {
  elements.voiceInputStatus.textContent = text;
  elements.voiceInputStatus.hidden = !text;
  elements.composerDefaultNote.hidden = Boolean(text);
}

function voiceInputRms(samples) {
  let sum = 0;
  for (let index = 0; index < samples.length; index += 1) sum += samples[index] ** 2;
  return Math.sqrt(sum / Math.max(1, samples.length));
}

function flattenVoiceInput(chunks) {
  const length = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const samples = new Float32Array(length);
  let offset = 0;
  chunks.forEach((chunk) => {
    samples.set(chunk, offset);
    offset += chunk.length;
  });
  return samples;
}

function downsampleVoiceInput(samples, sourceRate, targetRate = 16000) {
  if (sourceRate === targetRate) return samples;
  const ratio = sourceRate / targetRate;
  const result = new Float32Array(Math.max(1, Math.round(samples.length / ratio)));
  for (let index = 0; index < result.length; index += 1) {
    const start = Math.floor(index * ratio);
    const end = Math.min(Math.floor((index + 1) * ratio), samples.length);
    let sum = 0;
    for (let cursor = start; cursor < end; cursor += 1) sum += samples[cursor];
    result[index] = sum / Math.max(1, end - start);
  }
  return result;
}

function writeVoiceInputAscii(view, offset, text) {
  for (let index = 0; index < text.length; index += 1) {
    view.setUint8(offset + index, text.charCodeAt(index));
  }
}

function encodeVoiceInputWav(chunks, sourceRate) {
  const samples = downsampleVoiceInput(flattenVoiceInput(chunks), sourceRate);
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  writeVoiceInputAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeVoiceInputAscii(view, 8, "WAVE");
  writeVoiceInputAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeVoiceInputAscii(view, 36, "data");
  view.setUint32(40, samples.length * 2, true);
  let offset = 44;
  samples.forEach((sampleValue) => {
    const sample = Math.max(-1, Math.min(1, sampleValue));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += 2;
  });
  return new Blob([view], { type: "audio/wav" });
}

async function voiceInputBase64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += 32768) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
  }
  return btoa(binary);
}

function cleanupVoiceInputCapture() {
  window.clearTimeout(state.voiceInputTimer);
  if (state.voiceInputProcessor) state.voiceInputProcessor.disconnect();
  if (state.voiceInputSource) state.voiceInputSource.disconnect();
  if (state.voiceInputStream) state.voiceInputStream.getTracks().forEach((track) => track.stop());
  if (state.voiceInputContext) state.voiceInputContext.close().catch(() => {});
  state.voiceInputStream = null;
  state.voiceInputContext = null;
  state.voiceInputSource = null;
  state.voiceInputProcessor = null;
  state.voiceInputRecording = false;
  elements.voiceInputButton.classList.remove("recording");
  elements.voiceInputButton.setAttribute("aria-label", "Fazer pergunta por audio");
  elements.voiceInputButton.title = "Fazer pergunta por audio";
}

async function stopVoiceInput({ send = true } = {}) {
  if (!state.voiceInputRecording || state.voiceInputBusy) return;
  state.voiceInputBusy = true;
  const chunks = [...state.voiceInputChunks];
  const sampleRate = state.voiceInputContext?.sampleRate || 44100;
  cleanupVoiceInputCapture();
  updateSendState();
  if (!send || !chunks.length || !state.voiceInputSpeechDetected) {
    setVoiceInputStatus("Nenhuma fala detectada. Toque no microfone para tentar novamente.");
    state.voiceInputBusy = false;
    updateSendState();
    return;
  }

  try {
    setVoiceInputStatus("Transcrevendo localmente no computador...");
    const wav = encodeVoiceInputWav(chunks, sampleRate);
    const data = await api("/voice/transcribe", {
      method: "POST",
      json: {
        audio_base64: await voiceInputBase64(wav),
        mime_type: "audio/wav",
      },
    });
    elements.input.value = data.transcript || "";
    autoResizeInput();
    setVoiceInputStatus(`Entendido: ${data.transcript}`);
    state.voiceInputBusy = false;
    updateSendState();
    if (elements.input.value.trim()) {
      await sendMessage();
      setVoiceInputStatus("Pergunta enviada por audio.");
      window.setTimeout(() => {
        if (!state.voiceInputRecording) setVoiceInputStatus("");
      }, 1800);
    }
  } catch (error) {
    state.voiceInputBusy = false;
    setVoiceInputStatus(error.message);
    showToast(`Microfone: ${error.message}`, "error");
    updateSendState();
  }
}

async function startVoiceInput() {
  if (state.busy || state.voiceInputBusy) return;
  if (state.voiceInputRecording) {
    await stopVoiceInput();
    return;
  }
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!navigator.mediaDevices?.getUserMedia || !AudioContextClass) {
    showToast("Este navegador nao disponibilizou o microfone.", "error");
    return;
  }
  try {
    state.voiceInputStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
    state.voiceInputContext = new AudioContextClass();
    if (state.voiceInputContext.state === "suspended") await state.voiceInputContext.resume();
    if (state.voiceInputContext.state !== "running") {
      throw new Error("Toque novamente e permita o uso do microfone.");
    }
    state.voiceInputSource = state.voiceInputContext.createMediaStreamSource(state.voiceInputStream);
    state.voiceInputProcessor = state.voiceInputContext.createScriptProcessor(4096, 1, 1);
    state.voiceInputChunks = [];
    state.voiceInputSpeechDetected = false;
    state.voiceInputSilenceStartedAt = 0;
    state.voiceInputProcessor.onaudioprocess = (event) => {
      if (!state.voiceInputRecording) return;
      const samples = new Float32Array(event.inputBuffer.getChannelData(0));
      state.voiceInputChunks.push(samples);
      const level = voiceInputRms(samples);
      if (level > 0.012) {
        state.voiceInputSpeechDetected = true;
        state.voiceInputSilenceStartedAt = 0;
      } else if (state.voiceInputSpeechDetected) {
        if (!state.voiceInputSilenceStartedAt) state.voiceInputSilenceStartedAt = Date.now();
        if (Date.now() - state.voiceInputSilenceStartedAt >= 900) stopVoiceInput();
      }
    };
    state.voiceInputSource.connect(state.voiceInputProcessor);
    state.voiceInputProcessor.connect(state.voiceInputContext.destination);
    state.voiceInputRecording = true;
    elements.voiceInputButton.classList.add("recording");
    elements.voiceInputButton.setAttribute("aria-label", "Parar e enviar pergunta por audio");
    elements.voiceInputButton.title = "Parar e enviar";
    setVoiceInputStatus("Ouvindo... fale e aguarde, ou toque novamente para enviar.");
    state.voiceInputTimer = window.setTimeout(() => stopVoiceInput(), 20000);
  } catch (error) {
    cleanupVoiceInputCapture();
    setVoiceInputStatus("Autorize o microfone deste site HTTPS e tente novamente.");
    showToast(`Microfone: ${error.message}`, "error");
  }
}

async function sendMessage() {
  if (state.busy) {
    await cancelResponse();
    return;
  }
  const typedMessage = elements.input.value.trim();
  if (!typedMessage && !state.files.length) return;
  const message = typedMessage || "Analise o arquivo anexado.";
  stopSpeech();
  const selectedFiles = [...state.files];
  createMessage(
    "user",
    message,
    selectedFiles.map((file) => ({ name: file.name, size: file.size })),
  );
  state.busy = true;
  state.sendPending = true;
    state.streamingText = "";
    state.speechBuffer = "";
    state.speechReceivedChunks = false;
  state.streamMessage = createMessage("assistant");
  setStreamStatus(selectedFiles.length ? "Preparando anexos" : "Enviando mensagem");
  elements.input.value = "";
  elements.input.style.height = "auto";
  state.files = [];
  renderSelectedFiles();
  updateSendState();

  try {
    const attachmentIds = await uploadFiles(selectedFiles);
    const data = await api("/chat/messages", {
      method: "POST",
      json: {
        message,
        conversation_id: state.conversationId,
        attachment_ids: attachmentIds,
        model_id: state.modelId,
      },
    });
    state.activeJobId = data.job.id;
    state.conversationId = data.job.conversation_id;
    state.sendPending = false;
    startPolling(state.activeJobId);
    loadConversations();
  } catch (error) {
    finishStream(`Erro: ${error.message}`, "failed");
    showToast(error.message, "error");
  }
}

async function cancelResponse() {
  stopSpeech();
  if (!state.activeJobId) {
    showToast("A mensagem ainda esta sendo preparada.");
    return;
  }
  try {
    setStreamStatus("Interrompendo resposta");
    await api(`/chat/jobs/${state.activeJobId}/cancel`, { method: "POST" });
  } catch (error) {
    showToast(error.message, "error");
  }
}

function handleChatEvent(event) {
  const payload = event.payload || {};
  const jobId = payload.job_id || "";
  if (event.type === "chat.accepted" && state.sendPending) {
    state.activeJobId = jobId;
    state.conversationId = payload.conversation_id || state.conversationId;
  }
  if (jobId && !state.activeJobId && state.sendPending) {
    state.activeJobId = jobId;
  }
  if (jobId && state.activeJobId && jobId !== state.activeJobId) return;

  if (event.type === "chat.started") setStreamStatus("Pensando");
  if (event.type === "chat.status") setStreamStatus(payload.text || "Pensando");
  if (event.type === "chat.chunk") appendStream(payload.text || "");
  if (event.type === "chat.completed") finishStream(payload.text || "", "completed");
  if (event.type === "chat.failed") finishStream(`Erro: ${payload.error || "Falha local"}`, "failed");
  if (event.type === "chat.cancelled") finishStream("", "cancelled");
  if (event.type === "chat.cancelling") setStreamStatus("Interrompendo resposta");
}

function handleServerEvent(event) {
  if (event.type === "conversation.deleted") {
    if (event.payload?.conversation_id === state.conversationId) resetConversation();
    loadConversations();
    return;
  }
  if (event.type === "inventory.changed") {
    loadInventory();
    return;
  }
  if (event.type === "catalog.changed") {
    loadProducts();
    return;
  }
  if (event.type === "quotes.changed") {
    if (state.activeView === "quotes") loadQuotes();
    return;
  }
  if (event.type === "reports.changed") {
    if (state.activeView === "reports") loadReports();
    return;
  }
  if (event.type === "cases.changed") {
    if (state.activeView === "cases_deadlines") loadCases();
    return;
  }
  if (event.type === "relationships.changed") {
    if (event.payload?.kind === state.relationshipKind) loadRelationships();
    return;
  }
  if (event.type === "documents.changed" || event.type === "documents.job") {
    loadDocuments();
    return;
  }
  if (event.type === "agenda.reminder" && event.payload?.event) {
    showAgendaReminders([event.payload.event]);
    return;
  }
  if (event.type === "agenda.reminder.acknowledged") {
    state.reminderItems.delete(event.payload?.event_id);
    renderAgendaReminder();
    return;
  }
  if (event.type === "agenda.changed") {
    if (state.activeView === "agenda") loadAgenda();
    loadDueReminders();
    return;
  }
  handleChatEvent(event);
}

function connectEvents() {
  if (state.websocket && state.websocket.readyState <= WebSocket.OPEN) return;
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/api/v1/events`);
  state.websocket = socket;

  socket.addEventListener("open", () => {
    setConnected(true);
    state.reconnectDelay = 800;
  });
  socket.addEventListener("message", (message) => {
    try {
      const event = JSON.parse(message.data);
      if (event.type !== "system.connected" && event.type !== "pong") handleServerEvent(event);
    } catch (_error) {
      // Ignore malformed local events and keep the connection alive.
    }
  });
  socket.addEventListener("close", () => {
    setConnected(false);
    window.setTimeout(connectEvents, state.reconnectDelay);
    state.reconnectDelay = Math.min(state.reconnectDelay * 1.7, 8000);
  });
  socket.addEventListener("error", () => socket.close());
}

async function loadSession() {
  try {
    const data = await api("/session");
    const company = data.company || {};
    elements.companyLabel.textContent = company.name || "Celsius Project AI";
    elements.emptySubtitle.textContent = company.name
      ? `Assistente local de ${company.name}.`
      : "Celsius, seu agente multimodal local.";
  } catch (error) {
    showToast(error.message, "error");
  }
}

function bindEvents() {
  elements.themeButtons.forEach((button) => {
    button.addEventListener("click", () => setTheme(button.dataset.themeOption));
  });
  elements.mobilePairButton.addEventListener("click", openMobilePairing);
  elements.mobilePairClose.addEventListener("click", () => elements.mobilePairDialog.close());
  elements.mobilePairDone.addEventListener("click", () => elements.mobilePairDialog.close());
  elements.mobilePairCopy.addEventListener("click", copyMobilePairingLink);
  elements.mobilePairDialog.addEventListener("click", (event) => {
    if (event.target === elements.mobilePairDialog) elements.mobilePairDialog.close();
  });
  elements.jarvisStatus.addEventListener("pointerdown", startJarvisDrag);
  elements.jarvisStatus.addEventListener("pointermove", moveJarvis);
  elements.jarvisStatus.addEventListener("pointerup", stopJarvisDrag);
  elements.jarvisStatus.addEventListener("pointercancel", stopJarvisDrag);
  elements.jarvisStatus.addEventListener("dblclick", resetJarvisPosition);
  window.addEventListener("resize", restoreJarvisPosition);
  elements.menuButton.addEventListener("click", openSidebar);
  elements.sidebarClose.addEventListener("click", closeSidebar);
  elements.backdrop.addEventListener("click", closeSidebar);
  elements.newChat.addEventListener("click", resetConversation);
  elements.chatButton.addEventListener("click", () => showView("chat"));
  elements.agendaButton.addEventListener("click", () => showView("agenda"));
  elements.documentsButton.addEventListener("click", () => showView("documents"));
  elements.customersButton.addEventListener("click", () => showView("customers"));
  elements.suppliersButton.addEventListener("click", () => showView("suppliers"));
  elements.inventoryButton.addEventListener("click", () => showView("inventory"));
  elements.productsButton.addEventListener("click", () => showView("products_services"));
  elements.quotesButton.addEventListener("click", () => showView("quotes"));
  elements.reportsButton.addEventListener("click", () => showView("reports"));
  elements.casesButton.addEventListener("click", () => showView("cases_deadlines"));
  elements.refreshConversations.addEventListener("click", loadConversations);
  elements.memoryButton.addEventListener("click", openMemories);
  elements.memoryClose.addEventListener("click", () => elements.memoryDialog.close());
  elements.memoryForm.addEventListener("submit", saveMemory);
  elements.memoryDialog.addEventListener("click", (event) => {
    if (event.target === elements.memoryDialog) elements.memoryDialog.close();
  });
  elements.agendaRefresh.addEventListener("click", loadAgenda);
  elements.agendaAdd.addEventListener("click", () => openAgendaDialog());
  elements.agendaSearch.addEventListener("input", renderAgenda);
  elements.agendaStatusFilter.addEventListener("change", renderAgenda);
  elements.agendaForm.addEventListener("submit", saveAgendaItem);
  elements.agendaClose.addEventListener("click", () => elements.agendaDialog.close());
  elements.agendaCancel.addEventListener("click", () => elements.agendaDialog.close());
  elements.agendaDialog.addEventListener("click", (event) => {
    if (event.target === elements.agendaDialog) elements.agendaDialog.close();
  });
  elements.agendaAlertDismiss.addEventListener("click", acknowledgeAgendaReminders);
  elements.documentsRefresh.addEventListener("click", loadDocuments);
  elements.documentsAdd.addEventListener("click", openDocumentsDialog);
  elements.documentsFilter.addEventListener("input", renderDocuments);
  elements.documentsStatusFilter.addEventListener("change", renderDocuments);
  elements.knowledgeSearchForm.addEventListener("submit", searchKnowledge);
  elements.knowledgeResultsClose.addEventListener("click", () => {
    elements.knowledgeResults.hidden = true;
  });
  elements.documentsForm.addEventListener("submit", uploadDocuments);
  elements.documentsFiles.addEventListener("change", () => {
    selectDocumentFiles(elements.documentsFiles.files);
  });
  elements.documentsClose.addEventListener("click", () => elements.documentsDialog.close());
  elements.documentsCancel.addEventListener("click", () => elements.documentsDialog.close());
  elements.documentsDialog.addEventListener("click", (event) => {
    if (event.target === elements.documentsDialog) elements.documentsDialog.close();
  });
  elements.relationshipsRefresh.addEventListener("click", loadRelationships);
  elements.relationshipsAdd.addEventListener("click", () => openRelationshipDialog());
  elements.relationshipsFilter.addEventListener("input", renderRelationships);
  elements.relationshipsStatusFilter.addEventListener("change", renderRelationships);
  elements.relationshipForm.addEventListener("submit", saveRelationship);
  elements.relationshipClose.addEventListener("click", () => elements.relationshipDialog.close());
  elements.relationshipCancel.addEventListener("click", () => elements.relationshipDialog.close());
  elements.relationshipDialog.addEventListener("click", (event) => {
    if (event.target === elements.relationshipDialog) elements.relationshipDialog.close();
  });
  elements.inventoryRefresh.addEventListener("click", loadInventory);
  elements.inventoryAdd.addEventListener("click", () => openInventoryDialog());
  elements.inventoryItemsTab.addEventListener("click", () => setInventoryMode("items"));
  elements.inventoryMovementsTab.addEventListener("click", () => setInventoryMode("movements"));
  elements.inventoryFilter.addEventListener("input", renderInventory);
  elements.inventoryHealthFilter.addEventListener("change", renderInventory);
  elements.inventoryForm.addEventListener("submit", saveInventoryItem);
  elements.inventoryClose.addEventListener("click", () => elements.inventoryDialog.close());
  elements.inventoryCancel.addEventListener("click", () => elements.inventoryDialog.close());
  elements.inventoryDialog.addEventListener("click", (event) => {
    if (event.target === elements.inventoryDialog) elements.inventoryDialog.close();
  });
  elements.movementForm.addEventListener("submit", saveMovement);
  elements.movementClose.addEventListener("click", () => elements.movementDialog.close());
  elements.movementCancel.addEventListener("click", () => elements.movementDialog.close());
  elements.movementDialog.addEventListener("click", (event) => {
    if (event.target === elements.movementDialog) elements.movementDialog.close();
  });
  elements.productsRefresh.addEventListener("click", loadProducts);
  elements.productsAdd.addEventListener("click", () => openProductDialog());
  elements.productsFilter.addEventListener("input", renderProducts);
  elements.productsTypeFilter.addEventListener("change", renderProducts);
  elements.productsStatusFilter.addEventListener("change", renderProducts);
  elements.productForm.addEventListener("submit", saveProduct);
  elements.productClose.addEventListener("click", () => elements.productDialog.close());
  elements.productCancel.addEventListener("click", () => elements.productDialog.close());
  elements.productDialog.addEventListener("click", (event) => {
    if (event.target === elements.productDialog) elements.productDialog.close();
  });
  elements.quotesRefresh.addEventListener("click", loadQuotes);
  elements.quotesAdd.addEventListener("click", () => openQuoteDialog());
  elements.quotesFilter.addEventListener("input", renderQuotes);
  elements.quotesStatusFilter.addEventListener("change", renderQuotes);
  elements.quoteForm.addEventListener("submit", saveQuote);
  elements.quoteClose.addEventListener("click", () => elements.quoteDialog.close());
  elements.quoteCancel.addEventListener("click", () => elements.quoteDialog.close());
  elements.quoteDialog.addEventListener("click", (event) => {
    if (event.target === elements.quoteDialog) elements.quoteDialog.close();
  });
  elements.reportsRefresh.addEventListener("click", loadReports);
  elements.reportsAdd.addEventListener("click", openReportDialog);
  elements.reportsFilter.addEventListener("input", renderReports);
  elements.reportsFormatFilter.addEventListener("change", renderReports);
  elements.reportForm.addEventListener("submit", generateReport);
  elements.reportClose.addEventListener("click", () => elements.reportDialog.close());
  elements.reportCancel.addEventListener("click", () => elements.reportDialog.close());
  elements.reportDialog.addEventListener("click", (event) => {
    if (event.target === elements.reportDialog) elements.reportDialog.close();
  });
  elements.casesRefresh.addEventListener("click", loadCases);
  elements.casesAdd.addEventListener("click", () => openCaseDialog());
  elements.casesFilter.addEventListener("input", renderCases);
  elements.casesPriorityFilter.addEventListener("change", renderCases);
  elements.casesDeadlineFilter.addEventListener("change", renderCases);
  elements.caseForm.addEventListener("submit", saveCase);
  elements.caseClose.addEventListener("click", () => elements.caseDialog.close());
  elements.caseCancel.addEventListener("click", () => elements.caseDialog.close());
  elements.caseDialog.addEventListener("click", (event) => {
    if (event.target === elements.caseDialog) elements.caseDialog.close();
  });
  elements.documentDropzone.addEventListener("dragover", (event) => {
    event.preventDefault();
    elements.documentDropzone.classList.add("dragging");
  });
  elements.documentDropzone.addEventListener("dragleave", () => {
    elements.documentDropzone.classList.remove("dragging");
  });
  elements.documentDropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    elements.documentDropzone.classList.remove("dragging");
    selectDocumentFiles(event.dataTransfer.files);
  });
  elements.scrollLatest.addEventListener("click", () => scrollToLatest(true));
  elements.attachButton.addEventListener("click", () => elements.fileInput.click());
  elements.fileInput.addEventListener("change", () => selectFiles(elements.fileInput.files));
  elements.modelSelect.addEventListener("change", () => {
    state.modelId = elements.modelSelect.value;
    localStorage.setItem("celsius-model-id", state.modelId);
  });
  elements.voiceToggle.addEventListener("change", () => setVoiceEnabled(elements.voiceToggle.checked));
  elements.jarvisToggle.addEventListener("change", () => setJarvisEnabled(elements.jarvisToggle.checked));
  elements.sendButton.addEventListener("click", sendMessage);
  elements.voiceInputButton.addEventListener("click", startVoiceInput);
  elements.input.addEventListener("input", autoResizeInput);
  elements.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage();
    }
  });
  elements.messages.addEventListener("scroll", () => {
    elements.scrollLatest.hidden = isNearBottom();
  });
}

async function initialize() {
  const savedTheme = localStorage.getItem("celsius-theme-v2");
  const legacyTheme = localStorage.getItem("celsius-theme");
  setTheme(savedTheme || (legacyTheme === "dark" ? "green" : legacyTheme) || "light");
  bindEvents();
  updateSendState();
  await Promise.all([
    loadSession(),
    loadNavigation(),
    loadConversations(),
    loadModels(),
    loadVoiceCapabilities(),
  ]);
  await Promise.all([loadAgenda(), loadDueReminders(), loadDocuments(), loadInventory(), loadProducts()]);
  state.agendaRefreshTimer = window.setInterval(() => {
    if (state.activeView === "agenda") loadAgenda();
    if (state.activeView === "documents" || state.documentItems.some((item) => item.status === "Processando")) {
      loadDocuments();
    }
    if (state.activeView === "customers" || state.activeView === "suppliers") {
      loadRelationships();
    }
    if (state.activeView === "inventory") loadInventory();
    if (state.activeView === "products_services") loadProducts();
    loadDueReminders();
  }, 15_000);
  connectEvents();
  elements.input.focus();
}

initialize();
