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
  agentMode: "",
  agentModes: [],
  agentHealth: null,
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
  sidebarCollapsed: false,
  sidebarPreferences: {},
  sidebarModuleDraft: [],
  whatsappPollTimer: null,
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
  // Work Mode
  workMode: localStorage.getItem("celsius-work-mode") === "true",
  workAgents: [],
  workActivity: [],
  // Agent activity stays compact until the user explicitly opens it.
  workActivityExpanded: false,
  workStartedAt: 0,
  workTaskId: "",
  workTask: null,
  // Auth & Admin
  // Access credentials persist only in HttpOnly cookies. Keep the optional
  // bearer token in memory for API clients that return one after login.
  authToken: "",
  refreshPromise: null,
  currentUser: null,
  adminVisible: false,
  adminStats: null,
  adminUsers: [],
  notificationsVisible: false,
  notificationItems: [],
  notificationCount: 0,
};

const elements = {
  body: document.body,
  sidebar: document.querySelector("#sidebar"),
  backdrop: document.querySelector("#sidebar-backdrop"),
  menuButton: document.querySelector("#menu-button"),
  sidebarClose: document.querySelector("#sidebar-close"),
  sidebarCollapse: document.querySelector("#sidebar-collapse"),
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
  modeSelect: document.querySelector("#mode-select"),
  modeHealth: document.querySelector("#mode-health"),
  workModeToggle: document.querySelector("#work-mode-toggle"),
  workIndicator: document.querySelector("#work-indicator"),
  workActivity: document.querySelector("#work-activity"),
  workActivityLabel: document.querySelector("#work-activity-label"),
  workActivitySummary: document.querySelector("#work-activity-summary"),
  workActivityToggle: document.querySelector("#work-activity-toggle"),
  workAgentList: document.querySelector("#work-agent-list"),
  workTimeline: document.querySelector("#work-timeline"),
  workStop: document.querySelector("#work-stop"),
  workDetailsButton: document.querySelector("#work-details-button"),
  workDetails: document.querySelector("#work-details"),
  workDetailsStatus: document.querySelector("#work-details-status"),
  workDetailsObjective: document.querySelector("#work-details-objective"),
  workDetailsPlan: document.querySelector("#work-details-plan"),
  workDetailsSteps: document.querySelector("#work-details-steps"),
  workDetailsArtifacts: document.querySelector("#work-details-artifacts"),
  workDetailsResult: document.querySelector("#work-details-result"),
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
  loginScreen: document.querySelector("#login-screen"),
  appShell: document.querySelector("#app-shell"),
  loginForm: document.querySelector("#login-form"),
  loginEmail: document.querySelector("#login-email"),
  loginPassword: document.querySelector("#login-password"),
  loginError: document.querySelector("#login-error"),
  registerForm: document.querySelector("#register-form"),
  registerName: document.querySelector("#register-name"),
  registerEmail: document.querySelector("#register-email"),
  registerPassword: document.querySelector("#register-password"),
  registerError: document.querySelector("#register-error"),
  showRegister: document.querySelector("#show-register"),
  showLogin: document.querySelector("#show-login"),
  adminButton: document.querySelector("#admin-button"),
  adminView: document.querySelector("#admin-view"),
  adminSummary: document.querySelector("#admin-summary"),
  adminRefresh: document.querySelector("#admin-refresh"),
  adminUsers: document.querySelector("#admin-users"),
  adminConversations: document.querySelector("#admin-conversations"),
  adminMessages: document.querySelector("#admin-messages"),
  adminStorage: document.querySelector("#admin-storage"),
  adminUserList: document.querySelector("#admin-user-list"),
  adminActivityList: document.querySelector("#admin-activity-list"),
  adminHealth: document.querySelector("#admin-health"),
  adminDecisionEnabled: document.querySelector("#decision-enabled"),
  adminDecisionOutcomes: document.querySelector("#decision-outcomes"),
  adminDecisionFallbacks: document.querySelector("#decision-fallbacks"),
  adminDecisionRequests: document.querySelector("#decision-requests"),
  adminDecisionLatency: document.querySelector("#decision-latency"),
  adminDecisionKinds: document.querySelector("#admin-decision-kinds"),
  adminAddUser: document.querySelector("#admin-add-user"),
  adminUsersList: document.querySelector("#admin-users-list"),
  notificationBell: document.querySelector("#notification-bell"),
  notificationBadge: document.querySelector("#notification-badge"),
  notificationsPanel: document.querySelector("#notifications-panel"),
  notificationsRefresh: document.querySelector("#notifications-refresh"),
  notificationsMarkAll: document.querySelector("#notifications-mark-all"),
  notificationsClose: document.querySelector("#notifications-close"),
  notificationsList: document.querySelector("#notifications-list"),
  notificationsEmpty: document.querySelector("#notifications-empty"),
  userMenu: document.querySelector("#user-menu"),
  userAvatarBtn: document.querySelector("#user-avatar-btn"),
  userDisplayName: document.querySelector("#user-display-name"),
  userDropdown: document.querySelector("#user-dropdown"),
  userProfileBtn: document.querySelector("#user-profile-btn"),
  userLogoutBtn: document.querySelector("#user-logout-btn"),
  profileDialog: document.querySelector("#profile-dialog"),
  profileClose: document.querySelector("#profile-close"),
  profileForm: document.querySelector("#profile-form"),
  profileDisplayName: document.querySelector("#profile-display-name"),
  profileDisplayLabel: document.querySelector("#profile-display-label"),
  profileEmail: document.querySelector("#profile-email"),
  profileRole: document.querySelector("#profile-role"),
  profileError: document.querySelector("#profile-error"),
  profileSave: document.querySelector("#profile-save"),
  profilePasswordForm: document.querySelector("#profile-password-form"),
  profileOldPassword: document.querySelector("#profile-old-password"),
  profileNewPassword: document.querySelector("#profile-new-password"),
  profilePasswordConfirm: document.querySelector("#profile-password-confirm"),
  profilePasswordError: document.querySelector("#profile-password-error"),
  profilePasswordSave: document.querySelector("#profile-password-save"),
  profileDialog: document.querySelector("#profile-dialog"),
  profileClose: document.querySelector("#profile-close"),
  settingsBtn: document.querySelector("#settings-btn"),
  settingsDialog: document.querySelector("#settings-dialog"),
  settingsClose: document.querySelector("#settings-close"),
  settingsForm: document.querySelector("#settings-form"),
  settingsUserName: document.querySelector("#settings-user-name"),
  settingsCompanyName: document.querySelector("#settings-company-name"),
  settingsCompanySector: document.querySelector("#settings-company-sector"),
  settingsCompanySize: document.querySelector("#settings-company-size"),
  settingsCompanyDescription: document.querySelector("#settings-company-description"),
  settingsUserRole: document.querySelector("#settings-user-role"),
  settingsPreferredTone: document.querySelector("#settings-preferred-tone"),
  settingsTimezone: document.querySelector("#settings-timezone"),
  settingsBusinessContext: document.querySelector("#settings-business-context"),
  settingsMainNeeds: document.querySelector("#settings-main-needs"),
  settingsVoiceEnabled: document.querySelector("#settings-voice-enabled"),
  settingsVoiceProfile: document.querySelector("#settings-voice-profile"),
  settingsVoice: document.querySelector("#settings-voice"),
  settingsVoiceRate: document.querySelector("#settings-voice-rate"),
  settingsVoicePitch: document.querySelector("#settings-voice-pitch"),
  settingsVoiceVolume: document.querySelector("#settings-voice-volume"),
  "settingsMobileEnabled": document.querySelector("#settings-mobile-enabled"),
  "settingsMobileLAN": document.querySelector("#settings-mobile-lan"),
  "settingsMobileVoice": document.querySelector("#settings-mobile-voice"),
  "settingsMobileHTTPS": document.querySelector("#settings-mobile-https"),
  "settingsMobilePort": document.querySelector("#settings-mobile-port"),
  "settingsMobileToken": document.querySelector("#settings-mobile-token"),
  "settingsNotificationsEnabled": document.querySelector("#settings-notifications-enabled"),
  "settingsNotificationsExternal": document.querySelector("#settings-notifications-external"),
  "settingsNotificationsConfirmation": document.querySelector("#settings-notifications-confirmation"),
  "settingsNotificationChannel": document.querySelector("#settings-notification-channel"),
  "settingsWhatsAppProvider": document.querySelector("#settings-whatsapp-provider"),
  "settingsWhatsAppPhoneId": document.querySelector("#settings-whatsapp-phone-id"),
  "settingsWhatsAppTokenEnv": document.querySelector("#settings-whatsapp-token-env"),
  "settingsEmailProvider": document.querySelector("#settings-email-provider"),
  "settingsEmailFrom": document.querySelector("#settings-email-from"),
  "settingsSmsProvider": document.querySelector("#settings-sms-provider"),
  "settingsSmsSender": document.querySelector("#settings-sms-sender"),
  "settingsAllowedRoots": document.querySelector("#settings-allowed-roots"),
  "settingsModulesGrid": document.querySelector("#settings-modules-grid"),
  "settingsSave": document.querySelector("#settings-save"),
  "settingsCancel": document.querySelector("#settings-cancel"),
  "settingsSuggestModules": document.querySelector("#settings-suggest-modules"),
  "settingsStorageInfo": document.querySelector("#settings-storage-info"),
  profileSave: document.querySelector("#profile-save"),
  profilePasswordForm: document.querySelector("#profile-password-form"),
  profileOldPassword: document.querySelector("#profile-old-password"),
  profileNewPassword: document.querySelector("#profile-new-password"),
  profilePasswordConfirm: document.querySelector("#profile-password-confirm"),
  profilePasswordError: document.querySelector("#profile-password-error"),
  profilePasswordSave: document.querySelector("#profile-password-save"),
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

async function refreshAccessSession() {
  if (state.refreshPromise) return state.refreshPromise;
  state.refreshPromise = fetch("/api/v1/auth/refresh", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  }).then(async (response) => {
    if (!response.ok) return false;
    const data = await response.json();
    state.authToken = data.access_token || "";
    return true;
  }).catch(() => false).finally(() => {
    state.refreshPromise = null;
  });
  return state.refreshPromise;
}

async function api(path, options = {}) {
  const { json, retryAuth = true, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});
  if (state.authToken) {
    headers.set("Authorization", `Bearer ${state.authToken}`);
  }
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    fetchOptions.body = JSON.stringify(json);
  }
  const response = await fetch(`/api/v1${path}`, { ...fetchOptions, headers });
  let data = {};
  try {
    data = await response.json();
  } catch (_error) {
    data = {};
  }
  if (!response.ok) {
    const mayRefresh = !["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout"].includes(path);
    if (response.status === 401 && retryAuth && mayRefresh && await refreshAccessSession()) {
      return api(path, { ...options, retryAuth: false });
    }
    if (response.status === 401) showLoginScreen();
    throw new Error(data.error || data.detail || `Erro HTTP ${response.status}`);
  }
  return data;
}

function authHeaders(extra = {}) {
  const headers = new Headers(extra);
  if (state.authToken) headers.set("Authorization", `Bearer ${state.authToken}`);
  return headers;
}

async function apiBinary(path, options = {}) {
  const { json, retryAuth = true, ...fetchOptions } = options;
  const headers = new Headers(fetchOptions.headers || {});
  if (state.authToken) {
    headers.set("Authorization", `Bearer ${state.authToken}`);
  }
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    fetchOptions.body = JSON.stringify(json);
  }
  const response = await fetch(`/api/v1${path}`, { ...fetchOptions, headers });
  if (response.status === 401 && retryAuth && await refreshAccessSession()) {
    return apiBinary(path, { ...options, retryAuth: false });
  }
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
  elements.mobilePairStatus.textContent = "Preparando QR Code...";
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
      ? "QR Code pronto para o modo de voz"
      : "Acesso pela rede ainda nao esta ativo";
    const fingerprint = data.certificate_fingerprint
      ? ` Certificado SHA-256: ${data.certificate_fingerprint}`
      : "";
    elements.mobilePairNote.textContent = data.lan_access_enabled
      ? `Mantenha o computador e o celular conectados a mesma rede.${fingerprint}`
      : "Nao foi possivel abrir o acesso pela rede local.";
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

function isDesktopViewport() {
  return window.matchMedia("(min-width: 821px)").matches;
}

function setSidebarCollapsed(collapsed) {
  state.sidebarCollapsed = collapsed;
  localStorage.setItem("celsius-sidebar-collapsed", collapsed ? "1" : "0");
  if (isDesktopViewport()) {
    elements.body.classList.toggle("sidebar-collapsed", collapsed);
    if (collapsed) {
      elements.body.classList.remove("sidebar-open");
      elements.backdrop.hidden = true;
    }
  }
}

function toggleSidebarCollapsed() {
  setSidebarCollapsed(!state.sidebarCollapsed);
}

function handleMenuButton() {
  if (isDesktopViewport()) {
    setSidebarCollapsed(false);
  } else {
    openSidebar();
  }
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
  const adminActive = view === "admin" && state.adminVisible;
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
                  : adminActive
                    ? "admin"
                    : "chat";
  const moduleActive = agendaActive || documentsActive || relationshipsActive || inventoryActive || productsActive || quotesActive || reportsActive || casesActive;
  elements.chatStage.hidden = moduleActive || adminActive;
  elements.composerBand.hidden = moduleActive || adminActive;
  elements.agendaView.hidden = !agendaActive;
  elements.documentsView.hidden = !documentsActive;
  elements.relationshipsView.hidden = !relationshipsActive;
  elements.inventoryView.hidden = !inventoryActive;
  elements.productsView.hidden = !productsActive;
  elements.quotesView.hidden = !quotesActive;
  elements.reportsView.hidden = !reportsActive;
  elements.casesView.hidden = !casesActive;
  elements.adminView.hidden = !adminActive;
  elements.chatButton.classList.toggle("active", !moduleActive && !adminActive);
  elements.agendaButton.classList.toggle("active", agendaActive);
  elements.documentsButton.classList.toggle("active", documentsActive);
  elements.customersButton.classList.toggle("active", customersActive);
  elements.suppliersButton.classList.toggle("active", suppliersActive);
  elements.inventoryButton.classList.toggle("active", inventoryActive);
  elements.productsButton.classList.toggle("active", productsActive);
  elements.quotesButton.classList.toggle("active", quotesActive);
  elements.reportsButton.classList.toggle("active", reportsActive);
  elements.casesButton.classList.toggle("active", casesActive);
  elements.adminButton.classList.toggle("active", adminActive);
  elements.chatButton.toggleAttribute("aria-current", !moduleActive && !adminActive);
  elements.agendaButton.toggleAttribute("aria-current", agendaActive);
  elements.documentsButton.toggleAttribute("aria-current", documentsActive);
  elements.customersButton.toggleAttribute("aria-current", customersActive);
  elements.suppliersButton.toggleAttribute("aria-current", suppliersActive);
  elements.inventoryButton.toggleAttribute("aria-current", inventoryActive);
  elements.productsButton.toggleAttribute("aria-current", productsActive);
  elements.quotesButton.toggleAttribute("aria-current", quotesActive);
  elements.reportsButton.toggleAttribute("aria-current", reportsActive);
  elements.casesButton.toggleAttribute("aria-current", casesActive);
  elements.adminButton.toggleAttribute("aria-current", adminActive);
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
                    : adminActive
                      ? "Painel Administrativo"
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
  if (adminActive) loadAdminDashboard();
}

async function loadNavigation() {
  try {
    const [data, catalog] = await Promise.all([api("/navigation"), api("/modules")]);
    state.sidebarPreferences = data.preferences || {};
    elements.memoryButton.hidden = state.sidebarPreferences.show_memories === false;
    document.querySelector(".conversation-section").hidden = state.sidebarPreferences.show_conversations === false;
    const available = (catalog.items || []).filter(item => item.enabled && item.status === "ready");
    const visible = new Set((data.items || []).map(item => item.id));
    state.agendaVisible = available.some((item) => item.id === "agenda");
    state.documentsVisible = available.some((item) => item.id === "knowledge");
    state.customersVisible = available.some((item) => item.id === "customers");
    state.suppliersVisible = available.some((item) => item.id === "suppliers");
    state.inventoryVisible = available.some((item) => item.id === "inventory");
    state.productsVisible = available.some((item) => item.id === "products_services");
    state.quotesVisible = available.some((item) => item.id === "quotes");
    state.reportsVisible = available.some((item) => item.id === "reports");
    state.casesVisible = available.some((item) => item.id === "cases_deadlines");
    elements.agendaButton.hidden = !visible.has("agenda");
    elements.documentsButton.hidden = !visible.has("knowledge");
    elements.customersButton.hidden = !visible.has("customers");
    elements.suppliersButton.hidden = !visible.has("suppliers");
    elements.inventoryButton.hidden = !visible.has("inventory");
    elements.productsButton.hidden = !visible.has("products_services");
    elements.quotesButton.hidden = !visible.has("quotes");
    elements.reportsButton.hidden = !visible.has("reports");
    elements.casesButton.hidden = !visible.has("cases_deadlines");
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

const sidebarModuleIds = ["knowledge", "agenda", "reports", "customers", "suppliers", "inventory", "products_services", "quotes", "cases_deadlines"];
const sidebarModuleDescriptions = {
  knowledge: "Arquivos, materiais de aula e documentos",
  agenda: "Compromissos, aulas e lembretes",
  reports: "Relatórios e resumos",
  customers: "Cadastros de clientes e contatos",
  suppliers: "Cadastros de fornecedores",
  inventory: "Itens, entradas e saídas de estoque",
  products_services: "Catálogo de produtos e serviços",
  quotes: "Orçamentos e propostas",
  cases_deadlines: "Processos e acompanhamento de prazos",
};
const sidebarModuleNames = { products_services: "Produtos e serviços", quotes: "Orçamentos", reports: "Relatórios" };

async function openSidebarPreferences() {
  const dialog = document.querySelector("#sidebar-preferences-dialog");
  const list = document.querySelector("#sidebar-module-list");
  const status = document.querySelector("#sidebar-preferences-status");
  list.replaceChildren();
  status.textContent = "Carregando seu menu…";
  document.querySelector("#sidebar-preferences-save").disabled = true;
  dialog.showModal();
  try {
    const [catalog, navigation] = await Promise.all([api("/modules"), api("/navigation")]);
    if (!dialog.open) return;
    state.sidebarModuleDraft = (catalog.items || []).map(item => ({ ...item }));
    const preferences = navigation.preferences || {};
    document.querySelector("#sidebar-show-memories").checked = preferences.show_memories !== false;
    document.querySelector("#sidebar-show-conversations").checked = preferences.show_conversations !== false;
    renderSidebarModuleChoices();
    document.querySelector("#sidebar-preferences-save").disabled = false;
  } catch (error) {
    status.textContent = `Não foi possível carregar: ${error.message}`;
  }
}

function renderSidebarModuleChoices() {
  const list = document.querySelector("#sidebar-module-list");
  const focusedKey = list.contains(document.activeElement) ? document.activeElement.dataset.choiceKey : null;
  list.replaceChildren();
  for (const id of sidebarModuleIds) {
    const module = state.sidebarModuleDraft.find(item => item.id === id);
    if (!module) continue;
    const row = document.createElement("div");
    row.className = "sidebar-module-row";
    row.classList.toggle("module-disabled", !module.enabled);
    const description = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = sidebarModuleNames[id] || module.name;
    const detail = document.createElement("small");
    detail.textContent = sidebarModuleDescriptions[id];
    description.append(title, detail);
    row.append(description);
    for (const field of ["enabled", "sidebar_visible"]) {
      const label = document.createElement("label");
      label.className = "sidebar-module-toggle";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.choiceKey = `${id}-${field}`;
      input.checked = field === "enabled" ? module.enabled : module.enabled && module.sidebar_visible !== false;
      input.disabled = module.status !== "ready" || (field === "sidebar_visible" && !module.enabled);
      input.setAttribute("aria-label", `${field === "enabled" ? "Ativar" : "Mostrar no menu"} ${title.textContent}`);
      input.addEventListener("change", () => {
        module[field] = input.checked;
        if (field === "enabled" && input.checked) module.sidebar_visible = true;
        renderSidebarModuleChoices();
      });
      label.append(input);
      row.append(label);
    }
    list.append(row);
  }
  const selected = state.sidebarModuleDraft.filter(item => sidebarModuleIds.includes(item.id) && item.enabled);
  const visible = selected.filter(item => item.sidebar_visible !== false);
  document.querySelectorAll("[data-sidebar-preset]").forEach(button => {
    const ids = button.dataset.sidebarPreset === "education" ? ["knowledge", "agenda", "reports"]
      : button.dataset.sidebarPreset === "business" ? sidebarModuleIds : [];
    button.setAttribute("aria-pressed", String(selected.length === ids.length && selected.every(item => ids.includes(item.id))));
  });
  document.querySelector("#sidebar-preferences-status").textContent = `${selected.length} módulos ativos · ${visible.length} atalhos visíveis`;
  if (focusedKey) list.querySelector(`[data-choice-key="${focusedKey}"]`)?.focus({ preventScroll: true });
}

function applySidebarPreset(preset) {
  const selected = preset === "education" ? ["knowledge", "agenda", "reports"]
    : preset === "business" ? sidebarModuleIds : [];
  for (const module of state.sidebarModuleDraft) {
    if (!sidebarModuleIds.includes(module.id)) continue;
    module.enabled = selected.includes(module.id) && module.status === "ready";
    module.sidebar_visible = module.enabled;
  }
  renderSidebarModuleChoices();
}

async function saveSidebarPreferences(event) {
  event.preventDefault();
  const save = document.querySelector("#sidebar-preferences-save");
  save.disabled = true;
  const json = {
    enabled: state.sidebarModuleDraft.filter(item => item.enabled || item.mandatory).map(item => item.id),
    sidebar_visible: Object.fromEntries(state.sidebarModuleDraft.map(item => [item.id, item.sidebar_visible !== false])),
    show_memories: document.querySelector("#sidebar-show-memories").checked,
    show_conversations: document.querySelector("#sidebar-show-conversations").checked,
  };
  try {
    await api("/settings/sidebar", { method: "PATCH", json });
    await loadNavigation();
    document.querySelector("#sidebar-preferences-dialog").close();
    showToast("Seu menu foi salvo. Você pode ajustá-lo quando quiser.", "success");
  } catch (error) {
    document.querySelector("#sidebar-preferences-status").textContent = `Não foi possível salvar: ${error.message}`;
  } finally {
    save.disabled = false;
  }
}

async function openWhatsAppDialog() {
  document.querySelector("#whatsapp-dialog").showModal();
  await refreshWhatsAppConnection();
  if (state.whatsappPollTimer) window.clearInterval(state.whatsappPollTimer);
  state.whatsappPollTimer = window.setInterval(refreshWhatsAppConnection, 4000);
}

async function refreshWhatsAppConnection() {
  const status = document.querySelector("#whatsapp-status");
  const qr = document.querySelector("#whatsapp-qr");
  const frame = document.querySelector("#whatsapp-qr-frame");
  try {
    const data = await api("/whatsapp/status");
    if (!document.querySelector("#whatsapp-dialog").open) return;
    const labels = {disconnected:"Conexão pausada. Clique em Conectar para começar.",
      connecting:"Preparando a conexão…", pairing:"Escaneie o QR Code com seu WhatsApp.",
      connected:data.welcome_sent ? "Conectado. A mensagem inicial foi enviada à conversa com seu próprio número (Você)." : "Conectado. Preparando sua conversa com o Celsius…",
      reconnecting:"Reconectando ao WhatsApp…", error:"Não foi possível conectar. Tente novamente."};
    status.textContent = data.error || data.welcome_error || labels[data.state] || "Verificando conexão…";
    const selfChat = document.querySelector("#whatsapp-self-chat");
    const openChat = document.querySelector("#whatsapp-open-chat");
    // Only accept the canonical link built from this account's connected identity.
    const chatUrl = /^https:\/\/wa\.me\/\d{10,15}$/.test(data.self_chat_url || "") ? data.self_chat_url : "";
    selfChat.hidden = !data.connected || !chatUrl;
    if (chatUrl && data.connected) openChat.href = chatUrl;
    else openChat.removeAttribute("href");
    frame.hidden = !data.qr_image;
    if (data.qr_image && qr.getAttribute("src") !== data.qr_image) qr.src = data.qr_image;
    if (!data.qr_image) qr.removeAttribute("src");
    document.querySelector("#whatsapp-connect").disabled = ["connecting", "pairing", "connected", "reconnecting"].includes(data.state);
    document.querySelector("#whatsapp-pause").disabled = data.state === "disconnected";
    document.querySelector("#whatsapp-button span").textContent = data.connected ? "WhatsApp conectado" : "Conectar WhatsApp";
  } catch (error) {
    frame.hidden = true;
    qr.removeAttribute("src");
    document.querySelector("#whatsapp-self-chat").hidden = true;
    document.querySelector("#whatsapp-open-chat").removeAttribute("href");
    status.textContent = error.message;
  }
}

async function updateWhatsAppConnection(action) {
  const button = document.querySelector(`#whatsapp-${action}`);
  button.disabled = true;
  document.querySelector("#whatsapp-status").textContent = action === "connect" ? "Preparando a conexão…" : "Pausando conexão…";
  try {
    await api(`/whatsapp/${action}`, {method:"POST"});
    await refreshWhatsAppConnection();
  } catch (error) {
    document.querySelector("#whatsapp-status").textContent = error.message;
    button.disabled = false;
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

async function loadAgentModes() {
  if (!elements.modeSelect) return;
  try {
    const data = await api("/agents/modes");
    state.agentModes = data.items || [];
    const saved = localStorage.getItem("celsius-agent-mode") || data.default || "";
    elements.modeSelect.replaceChildren();
    for (const mode of state.agentModes) {
      const option = document.createElement("option");
      option.value = mode.id;
      option.textContent = mode.label;
      option.title = mode.summary;
      elements.modeSelect.append(option);
    }
    const known = state.agentModes.some((mode) => mode.id === saved);
    state.agentMode = known ? saved : data.default || "";
    elements.modeSelect.value = state.agentMode;
  } catch (error) {
    elements.modeSelect.disabled = true;
    showToast(`Modos: ${error.message}`, "error");
  }
  loadAgentHealth();
}

async function loadAgentHealth() {
  if (!elements.modeHealth) return;
  try {
    const data = await api("/agents/health");
    const decision = data.decision || {};
    state.agentHealth = decision;
    if (decision.state === "off") {
      elements.modeHealth.textContent = "";
      elements.modeHealth.title = "Camada de decisao desativada";
      elements.modeHealth.className = "";
      return;
    }
    const available = decision.state === "available";
    elements.modeHealth.textContent = available ? "Jev ok" : "Jev indisponivel";
    elements.modeHealth.className = available ? "health-ok" : "health-warn";
    elements.modeHealth.title = decision.detail || "";
  } catch {
    elements.modeHealth.textContent = "";
    elements.modeHealth.className = "";
  }
}

function toggleWorkMode() {
  state.workMode = !state.workMode;
  const toggle = elements.workModeToggle;
  const indicator = elements.workIndicator;
  localStorage.setItem("celsius-work-mode", String(state.workMode));

  if (state.workMode) {
    toggle.setAttribute("aria-pressed", "true");
    toggle.setAttribute("aria-label", "Desativar modo Work");
    toggle.classList.add("active");
    if (indicator) indicator.hidden = state.workAgents.length === 0;
    showToast("Work ativado. O Celsius mostrara o andamento da tarefa.");
  } else {
    toggle.setAttribute("aria-pressed", "false");
    toggle.setAttribute("aria-label", "Ativar modo Work");
    toggle.classList.remove("active");
    if (indicator) indicator.hidden = true;
    state.workAgents = [];
    updateWorkIndicator();
    if (!state.busy) elements.workActivity.hidden = true;
    showToast("Work desativado.");
  }
}

function syncWorkModeUI() {
  if (!elements.workModeToggle) return;
  elements.workModeToggle.classList.toggle("active", state.workMode);
  elements.workModeToggle.setAttribute("aria-pressed", String(state.workMode));
  elements.workModeToggle.setAttribute("aria-label", state.workMode ? "Desativar modo Work" : "Ativar modo Work");
  elements.workIndicator.hidden = !state.workMode || state.workAgents.length === 0;
  if (!state.workMode && !state.busy) elements.workActivity.hidden = true;
}

function selectAgentsForRequest(message) {
  const agents = [];
  const lower = message.toLowerCase();

  // Map keywords to agent modes
  const agentKeywords = {
    executor: ["fazer", "criar", "executar", "gerar", "construir", "implementar", "automatizar", "script", "código", "programa", "tarefa", "workflow", "processo"],
    documentos: ["documento", "arquivo", "pdf", "texto", "ler", "analisar", "extrair", "resumir", "buscar no documento", "base de conhecimento", "conhecimento"],
    estoque: ["estoque", "produto", "item", "quantidade", "entrada", "saída", "movimentação", "repor", "repor estoque", "baixa", "inventário"],
    pesquisador: ["pesquisar", "buscar", "web", "internet", "notícia", "atual", "recente", "última", "tendência", "mercado", "concorrente"],
    desenvolvedor: ["código", "programar", "debug", "erro", "bug", "função", "classe", "api", "banco de dados", "sql", "git", "deploy", "teste", "refatorar"],
    assistente: ["olá", "oi", "como", "o que", "qual", "quando", "onde", "quem", "explique", "defina", "resumo", "dica", "ajuda"]
  };

  // Score each agent based on keyword matches
  const scores = {};
  for (const [agent, keywords] of Object.entries(agentKeywords)) {
    let score = 0;
    for (const keyword of keywords) {
      if (lower.includes(keyword)) {
        score += 1;
      }
    }
    scores[agent] = score;
  }

  // Find the agent with highest score
  let bestAgent = "assistente";
  let bestScore = 0;
  for (const [agent, score] of Object.entries(scores)) {
    if (score > bestScore) {
      bestScore = score;
      bestAgent = agent;
    }
  }

  // If no clear winner, default to assistente
  if (bestScore === 0) {
    return ["assistente"];
  }

  // Return the best agent (and possibly related agents)
  const selected = [bestAgent];

  // Add related agents based on context
  if (bestAgent === "executor" && (lower.includes("estoque") || lower.includes("produto"))) {
    selected.push("estoque");
  }
  if (bestAgent === "executor" && (lower.includes("documento") || lower.includes("arquivo"))) {
    selected.push("documentos");
  }
  if (bestAgent === "pesquisador" && lower.includes("mercado")) {
    selected.push("executor");
  }

  return [...new Set(selected)]; // Remove duplicates
}

function workModeForRequest() {
  const preferred = ["pesquisador", "documentos", "estoque", "desenvolvedor", "executor"];
  return preferred.find((mode) => state.workAgents.includes(mode)) || "executor";
}

function updateWorkIndicator() {
  const indicator = elements.workIndicator;
  if (!indicator) return;

  if (state.workAgents.length > 0) {
    indicator.textContent = String(state.workAgents.length);
    indicator.hidden = false;
  } else {
    indicator.textContent = "";
    indicator.hidden = true;
  }
  renderWorkAgents();
}

const WORK_AGENT_LABELS = {
  executor: "Executor",
  documentos: "Documentos",
  estoque: "Estoque",
  pesquisador: "Pesquisa",
  desenvolvedor: "Desenvolvimento",
  assistente: "Coordenação",
};

const WORK_TOOL_LABELS = {
  pesquisar_web: "Pesquisando na web",
  pesquisar_google: "Consultando fontes",
  pesquisar_noticias: "Verificando noticias",
  navegar_web: "Lendo uma pagina",
  ler_arquivo: "Lendo arquivo",
  listar_arquivos: "Conferindo arquivos",
  processar_arquivo: "Analisando documento",
  criar_editar_arquivo: "Preparando arquivo",
  executar_codigo: "Executando verificacao local",
  gerar_relatorio_local: "Gerando relatorio",
  gerar_grafico: "Gerando visualizacao",
  listar_estoque: "Consultando estoque",
  buscar_item_estoque: "Buscando item no estoque",
};

function renderWorkAgents() {
  if (!elements.workAgentList) return;
  elements.workAgentList.replaceChildren();
  state.workAgents.forEach((agent, index) => {
      const chip = document.createElement("span");
      chip.className = "work-agent-chip";
      if (index === 0) chip.classList.add("lead");
      // The label comes from the server, so it is data, not markup.
      const mark = document.createElement("span");
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = index === 0 ? "C" : "A";
      chip.append(mark, document.createTextNode(WORK_AGENT_LABELS[agent] || agent));
      elements.workAgentList.append(chip);
  });
}

function resetWorkActivity() {
  state.workActivity = [];
  state.workTaskId = "";
  state.workTask = null;
  state.workStartedAt = Date.now();
  state.workActivityExpanded = false;
  elements.workActivity.classList.remove("done", "failed");
  elements.workActivity.classList.add("collapsed");
  elements.workActivityToggle.setAttribute("aria-expanded", "false");
  elements.workActivityToggle.setAttribute("aria-label", "Expandir atividade");
  elements.workActivityToggle.title = "Expandir atividade";
  elements.workActivityLabel.textContent = "Agentes trabalhando";
  elements.workActivitySummary.textContent = "Preparando a tarefa";
  elements.workStop.hidden = false;
  elements.workDetailsButton.hidden = true;
  elements.workDetails.hidden = true;
  elements.workDetailsResult.textContent = "";
  elements.workActivity.hidden = false;
  elements.workTimeline.replaceChildren();
}

function renderWorkTask(task, verification = null) {
  if (!task || !elements.workDetails) return;
  state.workTask = task;
  state.workTaskId = task.id || state.workTaskId;
  elements.workDetailsStatus.textContent = friendlyTaskState(task.status);
  elements.workDetailsObjective.textContent = task.objective || "Objetivo da tarefa não informado.";
  elements.workDetailsPlan.textContent = `${Array.isArray(task.plan) ? task.plan.length : 0} etapas planejadas`;
  elements.workDetailsSteps.textContent = `${Array.isArray(task.steps) ? task.steps.length : 0} registradas`;
  const evidence = verification || task.verification || {};
  elements.workDetailsArtifacts.textContent = `${Number(evidence.artifact_count || 0)} arquivo(s) verificado(s)`;
  elements.workDetailsResult.textContent = task.result || task.error || "A tarefa ainda não produziu um resumo.";
  elements.workDetailsButton.hidden = false;
}

function renderWorkRun(run) {
  const agents = Array.isArray(run?.agents) ? run.agents : [];
  const requested = Array.isArray(run?.requested_agents) ? run.requested_agents : [];
  if (requested.length) {
    state.workAgents = requested;
    updateWorkIndicator();
  }
  renderWorkTask({
    id: run.id,
    status: run.status,
    objective: run.objective,
    plan: requested.map((id) => ({ agent: id })),
    steps: agents.map((agent) => ({
      tool: agent.label || agent.id,
      status: agent.status,
      result: agent.response || "",
    })),
    result: run.result || "",
    error: run.error || "",
    verification: {},
  });
}

function friendlyTaskState(status) {
  return ({
    completed: "Concluída",
    running: "Em andamento",
    waiting_confirmation: "Aguardando aprovação",
    awaiting_approval: "Aguardando aprovação",
    paused: "Pausada",
    cancelled: "Interrompida",
    failed: "Com erro",
  })[status] || "Registrada";
}

async function loadLatestWorkTask(attempt = 0) {
  if (!state.workMode || !state.conversationId) return;
  try {
    const scope = encodeURIComponent(state.conversationId);
    const [taskList, runList] = await Promise.all([
      api(`/agents/tasks?scope=${scope}&limit=5`),
      api(`/agents/runs?scope=${scope}&limit=5`).catch(() => ({ items: [] })),
    ]);
    const item = (taskList.items || [])[0];
    const run = (runList.items || [])[0];
    if (run && (!item || Number(run.updated || 0) >= Number(item.updated || 0))) {
      renderWorkRun(run);
      return;
    }
    if (!item) {
      if (attempt < 3) setTimeout(() => loadLatestWorkTask(attempt + 1), 450);
      return;
    }
    const detail = await api(`/agents/tasks/${encodeURIComponent(item.id)}?scope=${scope}`);
    let verification = null;
    if (["completed", "failed", "cancelled"].includes(detail.task?.status)) {
      const evidence = await api(`/agents/tasks/${encodeURIComponent(item.id)}/artifacts?scope=${scope}`);
      verification = evidence;
    }
    renderWorkTask(detail.task || item, verification);
  } catch (_error) {
    // A chat can finish before its durable task checkpoint is visible; the retry handles that race quietly.
    if (attempt < 3) setTimeout(() => loadLatestWorkTask(attempt + 1), 650);
  }
}

function toggleWorkTaskDetails() {
  const visible = elements.workDetails.hidden;
  elements.workDetails.hidden = !visible;
  elements.workDetailsButton.textContent = visible ? "Ocultar detalhes" : "Ver detalhes";
}

function friendlyWorkStatus(text) {
  const clean = String(text || "").trim();
  const toolMatch = clean.match(/executando\s+([\w-]+)/i);
  if (toolMatch) {
    const tool = toolMatch[1].replace(/[.]+$/, "");
    return WORK_TOOL_LABELS[tool] || "Usando ferramenta local";
  }
  if (/ativando agentes/i.test(clean)) return "Organizando os agentes";
  if (/anexo/i.test(clean)) return "Preparando os arquivos enviados";
  if (/consultando|pensando|modelo/i.test(clean)) return "Analisando o proximo passo";
  if (/interromp/i.test(clean)) return "Interrompendo com seguranca";
  return clean || "Trabalhando na tarefa";
}

function addWorkActivity(text, status = "running", detail = "") {
  if (!state.workMode || !elements.workActivity) return;
  const label = friendlyWorkStatus(text);
  const previous = state.workActivity.at(-1);
  if (previous?.label === label && previous.status === status) return;
  if (previous?.status === "running") previous.status = "completed";
  state.workActivity.push({ label, status, detail, at: Date.now() });
  if (state.workActivity.length > 8) state.workActivity.shift();
  renderWorkActivity();
}

function renderWorkActivity() {
  if (!elements.workActivity) return;
  elements.workActivity.hidden = false;
  elements.workTimeline.replaceChildren();
  state.workActivity.forEach((item) => {
    const row = document.createElement("li");
    row.className = `work-step ${item.status}`;
    const copy = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = item.label;
    const meta = document.createElement("span");
    meta.textContent = item.detail || (item.status === "running" ? "Em andamento" : "Concluido");
    copy.append(title, meta);
    row.append(copy);
    elements.workTimeline.append(row);
  });
  const current = state.workActivity.at(-1);
  if (current) elements.workActivitySummary.textContent = current.label;
}

function finishWorkActivity(status) {
  if (!state.workMode || !elements.workActivity || elements.workActivity.hidden) return;
  const failed = status === "failed";
  const cancelled = status === "cancelled";
  const label = failed ? "A tarefa encontrou um problema" : cancelled ? "Tarefa interrompida" : "Pronto para revisar";
  if (state.workActivity.at(-1)?.status === "running") state.workActivity.at(-1).status = failed ? "failed" : "completed";
  state.workActivity.push({ label, status: failed ? "failed" : "completed", detail: "", at: Date.now() });
  elements.workActivity.classList.toggle("failed", failed);
  elements.workActivity.classList.toggle("done", !failed);
  elements.workActivityLabel.textContent = label;
  const seconds = Math.max(1, Math.round((Date.now() - state.workStartedAt) / 1000));
  elements.workStop.hidden = true;
  renderWorkActivity();
  elements.workActivitySummary.textContent = cancelled ? "O progresso foi preservado" : `Finalizado em ${seconds}s`;
  void loadLatestWorkTask();
}

function toggleWorkActivity() {
  state.workActivityExpanded = !state.workActivityExpanded;
  elements.workActivity.classList.toggle("collapsed", !state.workActivityExpanded);
  elements.workActivityToggle.setAttribute("aria-expanded", String(state.workActivityExpanded));
  elements.workActivityToggle.setAttribute("aria-label", state.workActivityExpanded ? "Recolher atividade" : "Expandir atividade");
  elements.workActivityToggle.title = state.workActivityExpanded ? "Recolher atividade" : "Expandir atividade";
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

async function downloadChatAttachment(item) {
  try {
    const blob = await apiBinary(`/chat/attachments/${encodeURIComponent(item.id)}`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = attachmentName(item);
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) {
    showToast(error.message || "Nao foi possivel baixar o arquivo.", "error");
  }
}

function renderMessageAttachments(container, attachments = [], downloadable = false) {
  if (!attachments.length) return;
  const list = document.createElement("div");
  list.className = "message-attachments";
  for (const attachment of attachments) {
    // Only files the assistant produced survive the turn; the user's own uploads
    // are deleted once the answer is stored, so those stay as plain labels.
    const canDownload = downloadable && Boolean(attachment.id);
    const item = document.createElement(canDownload ? "a" : "span");
    item.className = "message-file";
    if (canDownload) {
      item.href = "#";
      item.title = "Baixar arquivo";
      item.addEventListener("click", (event) => {
        event.preventDefault();
        downloadChatAttachment(attachment);
      });
    }
    item.innerHTML = svg.file;
    const name = document.createElement("span");
    name.textContent = attachmentName(attachment);
    item.append(name);
    if (canDownload && Number(attachment.size) > 0) {
      const size = document.createElement("small");
      size.className = "message-file-size";
      size.textContent = formatFileSize(attachment.size);
      item.append(size);
    }
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
  column.prepend(name, status, body);
  article.append(avatar, column);
  elements.messages.append(article);
  // Only the assistant's files are still on disk at this point, so only its
  // attachments are offered for download.
  const view = { article, column, status, body, role };
  view.setAttachments = (items = []) => appendMessageAttachments(view, items);
  if (attachments && attachments.length) view.setAttachments(attachments);
  scrollToLatest(true);
  return view;
}

function appendMessageAttachments(view, attachments = []) {
  if (!view?.column || !attachments?.length) return;
  view.column.querySelector(".message-attachments")?.remove();
  renderMessageAttachments(view.column, attachments, view.role === "assistant");
}

function submitWorkCommand(command) {
  if (!command || state.busy) return;
  elements.input.value = command;
  autoResizeInput();
  sendMessage();
}

function renderWorkApproval(container, text) {
  if (!state.workMode || !container || container.querySelector(".work-approval")) return;
  const match = String(text || "").match(/AUTORIZAR\s+([A-Z0-9]{6,12})/i);
  if (!match) return;
  const code = match[1].toUpperCase();
  const card = document.createElement("section");
  card.className = "work-approval";
  card.setAttribute("aria-label", "Confirmacao necessaria");
  const icon = document.createElement("span");
  icon.className = "work-approval-icon";
  icon.textContent = "!";
  const copy = document.createElement("div");
  copy.className = "work-approval-copy";
  copy.innerHTML = "<strong>Sua confirmacao e necessaria</strong><span>Revise a acao descrita acima antes de continuar.</span>";
  const actions = document.createElement("div");
  actions.className = "work-approval-actions";
  const reject = document.createElement("button");
  reject.type = "button";
  reject.className = "work-secondary-button";
  reject.textContent = "Recusar";
  reject.addEventListener("click", () => submitWorkCommand(`CANCELAR ${code}`));
  const approve = document.createElement("button");
  approve.type = "button";
  approve.className = "work-primary-button";
  approve.textContent = "Autorizar e continuar";
  approve.addEventListener("click", () => submitWorkCommand(`AUTORIZAR ${code}`));
  actions.append(reject, approve);
  card.append(icon, copy, actions);
  container.append(card);
}

function setStreamStatus(text) {
  if (!state.streamMessage) {
    state.streamMessage = createMessage("assistant");
  }
  state.streamMessage.status.textContent = text || "";
  state.streamMessage.status.classList.toggle("active", Boolean(text));
  if (text) addWorkActivity(text);
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

function finishStream(text, status = "completed", attachments = []) {
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
  renderWorkApproval(state.streamMessage.column || state.streamMessage.body.parentElement, state.streamingText);
  if (attachments && attachments.length) {
    state.streamMessage.setAttachments?.(attachments);
  }
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
  finishWorkActivity(status);
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
  state.workActivity = [];
  state.workAgents = [];
  state.workTaskId = "";
  state.workTask = null;
  elements.workDetailsButton.hidden = true;
  elements.workDetails.hidden = true;
  elements.workActivity.hidden = true;
  updateWorkIndicator();
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
      if (job.status === "completed") finishStream(job.response, "completed", job.attachments);
      if (job.status === "failed") {
        finishStream(`Erro: ${job.error}`, "failed");
      }
      if (job.status === "cancelled") {
        finishStream(job.response || "", "cancelled", job.attachments);
      }
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
  const workCommand = /^(?:TAREFA\s*:|TAREFAS\s*$|AUTORIZAR\s+|CANCELAR\s+|RETOMAR\s+)/i.test(message);
  const submittedMessage = state.workMode && !workCommand ? `TAREFA: ${message}` : message;
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
  if (state.workMode) resetWorkActivity();
  setStreamStatus(selectedFiles.length ? "Preparando anexos" : "Enviando mensagem");
  elements.input.value = "";
  elements.input.style.height = "auto";
  state.files = [];
  renderSelectedFiles();
  updateSendState();

  // Auto-select agents in Work mode
  if (state.workMode) {
    state.workAgents = selectAgentsForRequest(message);
    updateWorkIndicator();
    // Show which agents are being activated
    if (state.workAgents.length > 0) {
      const labels = {
        executor: "Executor",
        documentos: "Documentos",
        estoque: "Estoque",
        pesquisador: "Pesquisador",
        desenvolvedor: "Desenvolvedor",
        assistente: "Assistente"
      };
      const agentNames = state.workAgents.map(a => labels[a] || a).join(", ");
      setStreamStatus(`Ativando agentes: ${agentNames}`);
    }
  }

  try {
    const attachmentIds = await uploadFiles(selectedFiles);
    const data = await api("/chat/messages", {
      method: "POST",
      json: {
        message: submittedMessage,
        conversation_id: state.conversationId,
        attachment_ids: attachmentIds,
        model_id: state.modelId,
        agent_mode: state.workMode ? workModeForRequest() : state.agentMode,
        work_agents: state.workMode ? state.workAgents : undefined,
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
  if (event.type === "sidebar.updated" && payload.user_id === state.currentUser?.id) {
    loadNavigation();
    return;
  }
  const jobId = payload.job_id || "";
  const messageSource = payload.message?.metadata?.source || "";
  if (event.type === "chat.accepted" && ["mobile", "whatsapp"].includes(messageSource) && !state.sendPending) {
    const origin = messageSource === "whatsapp" ? "WhatsApp" : "celular";
    stopSpeech();
    state.conversationId = payload.conversation_id || "";
    state.activeJobId = jobId;
    state.busy = true;
    state.sendPending = false;
    state.streamingText = "";
    state.speechBuffer = "";
    state.speechReceivedChunks = false;
    elements.messages.replaceChildren();
    createMessage("user", payload.message?.content || `Mensagem recebida do ${origin}`);
    state.streamMessage = createMessage("assistant");
    setStreamStatus(`Recebido do ${origin} — preparando resposta`);
    showView("chat");
    updateSendState();
    loadConversations();
    showToast(`Pedido recebido do ${origin}.`);
    return;
  }
  if (event.type === "chat.accepted" && state.sendPending) {
    state.activeJobId = jobId;
    state.conversationId = payload.conversation_id || state.conversationId;
  }
  if (jobId && !state.activeJobId && state.sendPending) {
    state.activeJobId = jobId;
  }
  if (jobId && state.activeJobId && jobId !== state.activeJobId) return;

  if (event.type === "chat.started") setStreamStatus(state.workMode ? "Planejando a tarefa" : "Pensando");
  if (event.type === "chat.status") setStreamStatus(payload.text || "Pensando");
  if (event.type === "chat.chunk") appendStream(payload.text || "");
  if (event.type === "chat.completed") {
    finishStream(payload.text || "", "completed", payload.attachments);
  }
  if (event.type === "chat.failed") finishStream(`Erro: ${payload.error || "Falha local"}`, "failed");
  if (event.type === "chat.cancelled") {
    finishStream(payload.text || "", "cancelled", payload.attachments);
  }
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
    if (!state.currentUser) return;
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
  document.querySelector("#whatsapp-button").addEventListener("click", openWhatsAppDialog);
  document.querySelector("#whatsapp-close").addEventListener("click", () => document.querySelector("#whatsapp-dialog").close());
  document.querySelector("#whatsapp-dialog").addEventListener("close", () => {
    window.clearInterval(state.whatsappPollTimer);
    state.whatsappPollTimer = null;
    document.querySelector("#whatsapp-qr").removeAttribute("src");
  });
  document.querySelector("#whatsapp-connect").addEventListener("click", () => updateWhatsAppConnection("connect"));
  document.querySelector("#whatsapp-pause").addEventListener("click", () => updateWhatsAppConnection("pause"));
  document.querySelector("#whatsapp-self-chat-send").addEventListener("click", async () => {
    const button = document.querySelector("#whatsapp-self-chat-send");
    button.disabled = true;
    try {
      await api("/whatsapp/self-chat", {method: "POST"});
      await refreshWhatsAppConnection();
    } catch (error) {
      document.querySelector("#whatsapp-status").textContent = error.message;
    } finally { button.disabled = false; }
  });
  document.querySelector("#sidebar-customize").addEventListener("click", openSidebarPreferences);
  const sidebarPreferencesDialog = document.querySelector("#sidebar-preferences-dialog");
  for (const id of ["sidebar-preferences-close", "sidebar-preferences-cancel"]) {
    document.getElementById(id).addEventListener("click", () => sidebarPreferencesDialog.close());
  }
  document.querySelector("#sidebar-preferences-form").addEventListener("submit", saveSidebarPreferences);
  document.querySelectorAll("[data-sidebar-preset]").forEach(button => {
    button.addEventListener("click", () => applySidebarPreset(button.dataset.sidebarPreset));
  });
  for (const [id, visible] of [["sidebar-hide-modules", false], ["sidebar-show-modules", true]]) {
    document.getElementById(id).addEventListener("click", () => {
      state.sidebarModuleDraft.filter(item => sidebarModuleIds.includes(item.id) && item.enabled)
        .forEach(item => { item.sidebar_visible = visible; });
      renderSidebarModuleChoices();
    });
  }
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
  elements.menuButton.addEventListener("click", handleMenuButton);
  elements.settingsBtn.addEventListener("click", openSettingsDialog);
  elements.sidebarCollapse.addEventListener("click", toggleSidebarCollapsed);
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
  if (elements.modeSelect) {
    elements.modeSelect.addEventListener("change", () => {
      state.agentMode = elements.modeSelect.value;
      localStorage.setItem("celsius-agent-mode", state.agentMode);
    });
  }
  if (elements.workModeToggle) {
    elements.workModeToggle.addEventListener("click", toggleWorkMode);
  }
  if (elements.workActivityToggle) {
    elements.workActivityToggle.addEventListener("click", toggleWorkActivity);
  }
  if (elements.workDetailsButton) {
    elements.workDetailsButton.addEventListener("click", toggleWorkTaskDetails);
  }
  if (elements.workStop) {
    elements.workStop.addEventListener("click", cancelResponse);
  }
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
  elements.loginForm.addEventListener("submit", handleLogin);
  elements.registerForm.addEventListener("submit", handleRegister);
  elements.showRegister.addEventListener("click", (event) => {
    event.preventDefault();
    elements.loginForm.hidden = true;
    elements.registerForm.hidden = false;
  });
  elements.showLogin.addEventListener("click", (event) => {
    event.preventDefault();
    elements.loginForm.hidden = false;
    elements.registerForm.hidden = true;
  });
  elements.adminButton.addEventListener("click", () => showView("admin"));
  elements.adminRefresh.addEventListener("click", loadAdminDashboard);
  elements.adminAddUser.addEventListener("click", () => {
    elements.loginScreen.hidden = false;
    elements.appShell.hidden = true;
    elements.loginForm.hidden = true;
    elements.registerForm.hidden = false;
    window.scrollTo(0, 0);
  });
  elements.userAvatarBtn.addEventListener("click", () => {
    elements.userDropdown.hidden = !elements.userDropdown.hidden;
  });
  elements.userProfileBtn.addEventListener("click", () => {
    elements.userDropdown.hidden = true;
    openProfileDialog();
  });
  elements.userLogoutBtn.addEventListener("click", handleLogout);
  document.addEventListener("click", (event) => {
    if (elements.userDropdown && !elements.userDropdown.hidden && !elements.userMenu.contains(event.target)) {
      elements.userDropdown.hidden = true;
    }
  });
  elements.notificationBell.addEventListener("click", toggleNotificationsPanel);
  elements.notificationsClose.addEventListener("click", () => {
    state.notificationsVisible = false;
    elements.notificationsPanel.hidden = true;
  });
  elements.notificationsRefresh.addEventListener("click", () => {
    loadNotifications().then(() => renderNotificationsList());
  });
  elements.notificationsMarkAll.addEventListener("click", markAllNotificationsRead);
  elements.profileClose.addEventListener("click", () => elements.profileDialog.close());
  elements.profileDialog.addEventListener("click", (event) => {
    if (event.target === elements.profileDialog) elements.profileDialog.close();
  });
  elements.profileForm.addEventListener("submit", saveProfile);
  elements.profilePasswordForm.addEventListener("submit", saveProfilePassword);
  window.addEventListener("resize", () => {
    if (state.sidebarCollapsed) setSidebarCollapsed(true);
  });
}

/* ============================================
   SETTINGS DIALOG
   ============================================ */

function openSettingsDialog() {
  const user = state.currentUser || {};
  // Load current settings from backend
  loadSettingsFromBackend().then(settings => {
    // Perfil do cliente/empresa
    elements.settingsUserName.value = settings.customer.user_name || "";
    elements.settingsCompanyName.value = settings.customer.company_name || "";
    elements.settingsCompanySector.value = settings.customer.company_sector || "";
    elements.settingsCompanySize.value = settings.customer.company_size || "";
    elements.settingsCompanyDescription.value = settings.customer.company_description || "";
    elements.settingsUserRole.value = settings.customer.user_role || "";
    elements.settingsPreferredTone.value = settings.customer.preferred_tone || "";
    elements.settingsTimezone.value = settings.customer.timezone || "America/Sao_Paulo";
    elements.settingsBusinessContext.value = settings.customer.business_context || "";
    elements.settingsMainNeeds.value = settings.customer.main_needs || "";
    elements.settingsOffline.checked = settings.customer.local_offline_required;

    // Modo resposta
    elements.settingsResponseMode.value = settings.response.mode || "natural";
    elements.settingsResponseDetail.value = settings.response.detail_level || "detalhado";
    elements.settingsResponseTemperature.value = settings.response.temperature || 0.45;
    elements.settingsResponseTopP.value = settings.response.top_p || 0.9;

    // Voz
    elements.settingsVoiceEnabled.checked = settings.voice.enabled !== false;
    // Populate voice profiles
    loadVoiceProfiles().then(profiles => {
      const profileMap = profiles.reduce((acc, p) => {
        acc[p.id] = p;
        return acc;
      }, {});
      // Set default based on current voice
      const currentVoice = settings.voice.voice || "pt-BR-AntonioNeural";
      const defaultOption = Array.from(elements.settingsVoiceProfile.options).find(o => o.value === currentVoice);
      if (defaultOption) defaultOption.selected = true;
      // Also set the voice select
      elements.settingsVoice.value = currentVoice || "pt-BR-AntonioNeural";
      elements.settingsVoiceRate.value = settings.voice.rate || "+5%";
      elements.settingsVoicePitch.value = settings.voice.pitch || "-2Hz";
      elements.settingsVoiceVolume.value = settings.voice.volume || "+0%";
    });

    // Acesso pelo celular
    elements.settingsMobileEnabled.checked = settings.mobile.enabled !== false;
    elements.settingsMobileLAN.checked = settings.mobile.allow_lan !== false;
    elements.settingsMobileVoice.checked = settings.mobile.voice_commands_enabled !== false;
    elements.settingsMobileHTTPS.checked = settings.mobile.use_https !== false;
    elements.settingsMobilePort.value = settings.mobile.port || 8787;
    elements.settingsMobileToken.value = settings.mobile.pairing_token || "";

    // Notificacoes
    elements.settingsNotificationsEnabled.checked = settings.notifications.enabled !== false;
    elements.settingsNotificationsExternal.checked = settings.notifications.external_services_allowed !== false;
    elements.settingsNotificationsConfirmation.checked = settings.notifications.require_confirmation !== false;
    elements.settingsNotificationChannel.value = settings.notifications.default_channel || "whatsapp";
    elements.settingsWhatsAppProvider.value = settings.notifications.whatsapp_provider || "meta_cloud_api";
    elements.settingsWhatsAppPhoneId.value = settings.notifications.whatsapp_phone_number_id || "";
    elements.settingsWhatsAppTokenEnv.value = settings.notifications.whatsapp_token_env_var || "";
    settingsEmailProvider.value = settings.notifications.email_provider || "";
    settingsEmailFrom.value = settings.notifications.email_from || "";
    elements.settingsSmsProvider.value = settings.notifications.sms_provider || "";
    settingsSmsSender.value = settings.notifications.sms_sender_id || "";

    // Pastas autorizadas
    elements.settingsAllowedRoots.value = settings.security.allowed_file_roots.join("\n") || "";

    // Módulos da empresa
    renderModulesGrid(settings.modules || []);

    // Informacao de armazenamento
    elements.settingsStorageInfo.textContent = "Dados salvos em: data/customer_profile.json e data/celsius_settings.json";

    elements.settingsDialog.showModal();
  });
}

function loadSettingsFromBackend() {
  return fetch("/api/v1/settings", {
    method: "GET",
    headers: authHeaders()
  }).then(async res => {
    if (!res.ok) throw new Error("Nao foi possivel carregar configuracoes");
    return res.json();
  });
}

function loadVoiceProfiles() {
  return fetch("/api/v1/voice/profiles", {
    method: "GET",
    headers: authHeaders()
  }).then(async res => {
    if (!res.ok) return [];
    return res.json();
  });
}

function renderModulesGrid(modules) {
  const grid = elements.settingsModulesGrid;
  grid.innerHTML = "";
  const catalog = Object.values(modules || {});
  // Build a map id -> definition from server payload if available
  const serverModules = modules || {};
  catalog.forEach(module => {
    const enabled = serverModules[module.id] ? serverModules[module.id].enabled !== false : module.show_in_sidebar;
    const div = document.createElement("div");
    div.className = "settings-grid";
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = enabled;
    input.disabled = !!module.mandatory;
    input.dataset.moduleId = module.id;
    input.dataset.moduleName = module.name;
    const name = document.createElement("span");
    name.textContent = module.name;
    label.append(input, name);
    div.append(label);
    grid.appendChild(div);
  });
}

function saveSettings(event) {
  event.preventDefault();

  const settingsPayload = {
    customer: {
      user_name: elements.settingsUserName.value.trim(),
      company_name: elements.settingsCompanyName.value.trim(),
      company_sector: elements.settingsCompanySector.value.trim(),
      company_size: elements.settingsCompanySize.value.trim(),
      company_description: elements.settingsCompanyDescription.value.trim(),
      user_role: elements.settingsUserRole.value.trim(),
      preferred_tone: elements.settingsPreferredTone.value.trim(),
      business_context: elements.settingsBusinessContext.value.trim(),
      main_needs: elements.settingsMainNeeds.value.trim(),
      local_offline_required: elements.settingsOffline.checked,
    },
    response: {
      mode: elements.settingsResponseMode.value,
      detail_level: elements.settingsResponseDetail.value,
      temperature: parseFloat(elements.settingsResponseTemperature.value) || 0.45,
      top_p: parseFloat(elements.settingsResponseTopP.value) || 0.9,
    },
    voice: {
      enabled: elements.settingsVoiceEnabled.checked,
      provider: "edge-tts",
      profile: elements.settingsVoiceProfile.value || "natural_male_br",
      voice: elements.settingsVoice.value || "pt-BR-AntonioNeural",
      rate: elements.settingsVoiceRate.value || "+5%",
      pitch: elements.settingsVoicePitch.value || "-2Hz",
      volume: elements.settingsVoiceVolume.value || "+0%",
    },
    mobile: {
      enabled: elements.settingsMobileEnabled.checked,
      host: "0.0.0.0",
      port: parseInt(elements.settingsMobilePort.value) || 8787,
      pairing_token: elements.settingsMobileToken.value.trim(),
      allow_lan: elements.settingsMobileLAN.checked,
      voice_commands_enabled: elements.settingsMobileVoice.checked,
      use_https: elements.settingsMobileHTTPS.checked,
    },
    notifications: {
      enabled: elements.settingsNotificationsEnabled.checked,
      external_services_allowed: elements.settingsNotificationsExternal.checked,
      require_confirmation: elements.settingsNotificationsConfirmation.checked,
      default_channel: elements.settingsNotificationChannel.value,
      whatsapp_provider: elements.settingsWhatsAppProvider.value.trim(),
      whatsapp_phone_number_id: elements.settingsWhatsAppPhoneId.value.trim(),
      whatsapp_token_env_var: elements.settingsWhatsAppTokenEnv.value.trim(),
      email_provider: elements.settingsEmailProvider.value.trim(),
      email_from: elements.settingsEmailFrom.value.trim(),
      sms_provider: elements.settingsSmsProvider.value.trim(),
      sms_sender_id: elements.settingsSmsSender.value.trim(),
    },
    security: {
      allowed_file_roots: elements.settingsAllowedRoots.value.split("\n")
        .filter(s => s.trim())
        .map(s => s.trim()),
    },
    modules: {}
  };

  // Collect module enabled states from checkboxes
  const moduleCheckboxes = document.querySelectorAll("#settings-modules-grid input[type=checkbox]");
  moduleCheckboxes.forEach(cb => {
    const id = cb.getAttribute("data-module-id");
    if (settingsPayload.modules[id] === undefined) settingsPayload.modules[id] = {};
    settingsPayload.modules[id].id = id;
    settingsPayload.modules[id].name = cb.dataset.moduleName;
    settingsPayload.modules[id].enabled = cb.checked;
  });

  fetch("/api/v1/settings", {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(settingsPayload)
  }).then(async res => {
    if (!res.ok) {
      const err = await res.json();
      showToast("Erro ao salvar configuracoes: " + (err.error || res.statusText), "error");
      return;
    }
    showToast("Configuracoes salvas com sucesso.", "success");
    elements.settingsDialog.close();
    // Refresh the page to reflect changes (or just reload navigation)
    // For now, just reload the app shell
    window.location.reload();
  }).catch(err => {
    showToast("Erro ao salvar configuracoes: " + err.message, "error");
  });
}

function suggestModulesBySegment() {
  const segment = prompt("Digite o segmento da empresa (ex: comercio, industria, servicos):");
  const needs = prompt("Digite as necessidades (separadas por virgula, opcional):");
  if (segment === null) return;
  fetch("/api/v1/modules/suggest", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ segment: segment, needs: needs ? needs.split(",").map(s => s.trim()) : [] })
  }).then(async res => {
    if (!res.ok) {
      const err = await res.json();
      showToast("Erro ao sugerir modulos: " + (err.error || res.statusText), "error");
      return;
    }
    const data = await res.json();
    // Check checkboxes based on suggested list
    const suggested = data.suggested || [];
    const checkboxes = document.querySelectorAll("#settings-modules-grid input[type=checkbox]");
    checkboxes.forEach(cb => {
      cb.checked = cb.disabled || suggested.includes(cb.getAttribute("data-module-id"));
    });
    showToast("Sugestao de modulos aplicada.", "info");
  }).catch(err => {
    showToast("Erro ao sugerir modulos: " + err.message, "error");
  });
}

/* ============================================
   USER PROFILE
   ============================================ */

function openProfileDialog() {
  const user = state.currentUser || {};
  elements.profileDisplayLabel.textContent = user.display_name || user.email?.split("@")[0] || "Usuario";
  elements.profileEmail.textContent = user.email || "";
  elements.profileRole.textContent = user.role ? `Acesso: ${profileRoleLabel(user.role)}` : "";
  elements.profileDisplayName.value = user.display_name || "";
  elements.profileError.hidden = true;
  elements.profilePasswordError.hidden = true;
  elements.profilePasswordForm.reset();
  elements.profileDialog.showModal();
  elements.profileDisplayName.focus();
}

function profileRoleLabel(role) {
  switch (role) {
    case "admin":
      return "administrador";
    case "manager":
      return "gerente";
    case "viewer":
      return "somente leitura";
    default:
      return "usuario";
  }
}

function setProfileSaving(saving) {
  elements.profileSave.disabled = saving;
  elements.profileSave.textContent = saving ? "Salvando..." : "Salvar alteracoes";
}

async function saveProfile(event) {
  event.preventDefault();
  const displayName = elements.profileDisplayName.value.trim();
  if (!displayName) {
    elements.profileError.textContent = "Informe um nome de exibicao.";
    elements.profileError.hidden = false;
    return;
  }
  setProfileSaving(true);
  elements.profileError.hidden = true;
  try {
    const user = await api("/auth/me", {
      method: "PUT",
      json: { display_name: displayName },
    });
    state.currentUser = user;
    elements.userDisplayName.textContent = user.display_name || user.email.split("@")[0];
    elements.profileDisplayLabel.textContent = user.display_name;
    setProfileSaving(false);
    showToast("Dados do perfil atualizados.");
  } catch (error) {
    elements.profileError.textContent = error.message;
    elements.profileError.hidden = false;
    setProfileSaving(false);
  }
}

function setProfilePasswordSaving(saving) {
  elements.profilePasswordSave.disabled = saving;
  elements.profilePasswordSave.textContent = saving ? "Alterando..." : "Alterar senha";
}

async function saveProfilePassword(event) {
  event.preventDefault();
  const oldPassword = elements.profileOldPassword.value;
  const newPassword = elements.profileNewPassword.value;
  const confirmPassword = elements.profilePasswordConfirm.value;
  if (!oldPassword || !newPassword || newPassword.length < 8) {
    elements.profilePasswordError.textContent = "Informe a senha atual e uma nova senha com pelo menos 8 caracteres.";
    elements.profilePasswordError.hidden = false;
    return;
  }
  if (newPassword !== confirmPassword) {
    elements.profilePasswordError.textContent = "A confirmacao nao confere com a nova senha.";
    elements.profilePasswordError.hidden = false;
    return;
  }
  setProfilePasswordSaving(true);
  elements.profilePasswordError.hidden = true;
  try {
    await api("/auth/me/password", {
      method: "PUT",
      json: { old_password: oldPassword, new_password: newPassword },
    });
    elements.profilePasswordForm.reset();
    setProfilePasswordSaving(false);
    showToast("Senha alterada com sucesso.");
  } catch (error) {
    elements.profilePasswordError.textContent = error.message;
    elements.profilePasswordError.hidden = false;
    setProfilePasswordSaving(false);
  }
}

/* ============================================
   AUTH
   ============================================ */

function showLoginScreen() {
  state.authToken = "";
  state.currentUser = null;
  if (state.websocket) {
    state.websocket.close();
    state.websocket = null;
  }
  localStorage.removeItem("celsius_auth_token");
  elements.loginScreen.hidden = false;
  elements.appShell.hidden = true;
  elements.loginForm.hidden = false;
  elements.registerForm.hidden = true;
  elements.loginError.hidden = true;
  elements.registerError.hidden = true;
}

function showAppScreen() {
  elements.loginScreen.hidden = true;
  elements.appShell.hidden = false;
}

function storeTokens(accessToken) {
  state.authToken = accessToken || "";
  localStorage.removeItem("celsius_auth_token");
}

async function handleLogin(event) {
  event.preventDefault();
  const email = elements.loginEmail.value.trim();
  const password = elements.loginPassword.value;
  if (!email || !password) {
    elements.loginError.textContent = "Preencha email e senha.";
    elements.loginError.hidden = false;
    return;
  }
  try {
    const data = await api("/auth/login", {
      method: "POST",
      json: { email, password },
    });
    storeTokens(data.access_token);
    elements.loginForm.reset();
    await enterApp();
  } catch (error) {
    elements.loginError.textContent = error.message;
    elements.loginError.hidden = false;
  }
}

async function handleRegister(event) {
  event.preventDefault();
  const displayName = elements.registerName.value.trim();
  const email = elements.registerEmail.value.trim();
  const password = elements.registerPassword.value;
  if (!email || !password || password.length < 8) {
    elements.registerError.textContent = "Informe email valido e senha com pelo menos 8 caracteres.";
    elements.registerError.hidden = false;
    return;
  }
  try {
    const addingUser = Boolean(state.currentUser && state.currentUser.role === "admin");
    await api("/auth/register", {
      method: "POST",
      json: { email, password, display_name: displayName },
    });
    if (addingUser) {
      elements.registerForm.reset();
      showAppScreen();
      await loadAdminDashboard();
      showToast("Usuario criado.", "success");
      return;
    }
    const data = await api("/auth/login", {
      method: "POST",
      json: { email, password },
    });
    storeTokens(data.access_token);
    elements.registerForm.reset();
    await enterApp();
  } catch (error) {
    elements.registerError.textContent = error.message;
    elements.registerError.hidden = false;
  }
}

async function handleLogout() {
  try {
    await api("/auth/logout", { method: "POST" });
  } catch (_error) {
    // Ignore logout API errors; clear local state regardless.
  }
  showLoginScreen();
  if (elements.userDropdown) elements.userDropdown.hidden = true;
  resetConversation();
}

async function enterApp() {
  showAppScreen();
  elements.userDropdown.hidden = true;
  elements.adminButton.hidden = true;
  state.adminVisible = false;
  try {
    const user = await api("/auth/me");
    state.currentUser = user;
    elements.userDisplayName.textContent = user.display_name || user.email.split("@")[0];
    if (user.role === "admin") {
      elements.adminButton.hidden = false;
      state.adminVisible = true;
    }
  } catch (_error) {
    // If /auth/me fails, keep the app usable and just hide admin.
  }
  await Promise.all([
    loadSession(),
    loadNavigation(),
    loadConversations(),
    loadModels(),
    loadVoiceCapabilities(),
    loadAgentModes(),
  ]);
  await Promise.all([loadAgenda(), loadDueReminders(), loadDocuments(), loadInventory(), loadProducts()]);
  await loadNotifications();
  connectEvents();
  elements.input.focus();
}

/* ============================================
   ADMIN DASHBOARD
   ============================================ */

async function loadAdminDashboard() {
  try {
    const [stats, userActivity, activity, health, decisions] = await Promise.all([
      api("/admin/dashboard/stats"),
      api("/admin/dashboard/users"),
      api("/admin/dashboard/activity?limit=15"),
      api("/admin/dashboard/health"),
      api("/admin/dashboard/decisions"),
    ]);
    elements.adminUsers.textContent = String(stats.total_users);
    elements.adminConversations.textContent = String(stats.total_conversations);
    elements.adminMessages.textContent = String(stats.total_messages);
    elements.adminStorage.textContent = `${stats.storage_used_mb || 0} MB`;
    elements.adminSummary.textContent = `${stats.active_users} usuarios ativos de ${stats.total_users}, ${stats.admin_users} administradores`;
    renderAdminUserActivity(userActivity || []);
    renderAdminRecentActivity(activity || []);
    renderAdminHealth(health);
    renderAdminDecisions(decisions || {});
    await loadAdminUsersTable();
  } catch (error) {
    showToast(`Admin: ${error.message}`, "error");
  }
}

function renderAdminUserActivity(users) {
  elements.adminUserList.innerHTML = "";
  users.slice(0, 8).forEach((user) => {
    const item = document.createElement("div");
    item.className = "admin-user-item";
    item.innerHTML = `
      <div class="user-info">
        <span class="user-email"></span>
        <span class="user-stats"></span>
      </div>
      <span class="user-role ${user.role || "user"}"></span>`;
    item.querySelector(".user-email").textContent = user.display_name || user.email;
    item.querySelector(".user-stats").textContent = `${user.message_count} msgs em ${user.conversation_count} conversas`;
    item.querySelector(".user-role").textContent = user.role || "user";
    elements.adminUserList.appendChild(item);
  });
  if (!(users || []).length) {
    elements.adminUserList.innerHTML = '<p class="muted-note">Nenhum usuario registrado.</p>';
  }
}

function renderAdminRecentActivity(activities) {
  elements.adminActivityList.innerHTML = "";
  (activities || []).forEach((entry) => {
    const item = document.createElement("div");
    item.className = "admin-activity-item";
    item.innerHTML = '<span class="activity-path"></span><div class="activity-time"></div>';
    item.querySelector(".activity-path").textContent = entry.description || entry.activity_type || "";
    item.querySelector(".activity-time").textContent = entry.timestamp || "";
    elements.adminActivityList.appendChild(item);
  });
  if (!(activities || []).length) {
    elements.adminActivityList.innerHTML = '<p class="muted-note">Sem atividade recente.</p>';
  }
}

function renderAdminHealth(health) {
  elements.adminHealth.innerHTML = "";
  const items = [
    ["Status", health.status || "unknown", health.status === "healthy" ? "ok" : "warn"],
    ["Diretorio de dados", health.data_dir_exists ? "ok" : "ausente", health.data_dir_exists ? "ok" : "error"],
    ["Usuarios", health.users_dir_exists ? "ok" : "ausente", health.users_dir_exists ? "ok" : "error"],
    ["Conversas", health.conversations_dir_exists ? "ok" : "ausente", health.conversations_dir_exists ? "ok" : "error"],
    ["Relatorios", health.reports_dir_exists ? "ok" : "ausente", health.reports_dir_exists ? "ok" : "error"],
  ];
  items.forEach(([label, value, cls]) => {
    const row = document.createElement("div");
    row.className = "admin-health-item";
    row.innerHTML = `<span class="health-label"></span><span class="health-status"><span class="health-dot ${cls}"></span><span></span></span>`;
    row.querySelector(".health-label").textContent = label;
    row.querySelector(".health-status span:last-child").textContent = value;
    elements.adminHealth.appendChild(row);
  });
}

function fmtPercent(value) {
  const n = Number(value) || 0;
  return `${(n * 100).toFixed(1)}%`;
}

function renderAdminDecisions(decisions) {
  const enabled = Boolean(decisions.enabled);
  const dot = enabled ? "ok" : "warn";
  elements.adminDecisionEnabled.textContent = enabled ? "ativada" : "desativada";
  elements.adminDecisionEnabled.closest(".health-status").querySelector(".health-dot").className = `health-dot ${dot}`;

  const fallbackRate = Number(decisions.fallback_rate) || 0;
  const latency = decisions.latency_ms || {};
  const requests = decisions.requests_total || {};
  const ok = Number(requests.ok) || 0;
  const error = Number(requests.error) || 0;

  elements.adminDecisionOutcomes.textContent = `${Number(decisions.total_outcomes) || 0} (${fmtPercent(
    1 - fallbackRate,
  )} ok)` || "--";
  elements.adminDecisionFallbacks.textContent = `${Number(decisions.total_provider_fallbacks) || 0} (${fmtPercent(
    fallbackRate,
  )})`;
  elements.adminDecisionRequests.textContent = `${ok} / ${error}`;
  elements.adminDecisionLatency.textContent = `${latency.p95_ms || 0} ms`;

  elements.adminDecisionKinds.innerHTML = "";
  const byKind = decisions.by_kind || {};
  const records = Object.keys(byKind).sort();
  if (!records.length) {
    elements.adminDecisionKinds.innerHTML = '<p class="muted-note">Nenhum resultado registrado.</p>';
    return;
  }
  records.forEach((kind) => {
    const item = byKind[kind];
    const row = document.createElement("div");
    row.className = "admin-activity-item";
    row.innerHTML =
      '<span class="activity-path"></span><div class="activity-time"></div>';
    row.querySelector(".activity-path").textContent =
      `${kind}: ${Number(item.n) || 0} (aprovacao ${fmtPercent(item.rate)})`;
    row.querySelector(".activity-time").textContent = `media ${Number(item.mean_value) || 0}`;
    elements.adminDecisionKinds.appendChild(row);
  });
}

async function loadAdminUsersTable() {
  try {
    const users = await api("/auth/users");
    elements.adminUsersList.innerHTML = "";
    (users || []).forEach((user) => {
      const row = document.createElement("tr");
      const statusLabel = user.is_active ? "Ativo" : "Inativo";
      const roleLabel = user.role || "user";
      row.innerHTML = `
        <td><strong></strong><span class="cell-sub"></span></td>
        <td><span class="user-role ${roleLabel}"></span></td>
        <td></td>
        <td class="cell-time"></td>
        <td><button class="icon-button compact admin-toggle-user" type="button" title="Desativar/Reativar"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 12a8 8 0 1 0-2.34 5.66M20 4v7h-7"/></svg></button></td>`;
      row.querySelector("strong").textContent = user.display_name || user.email;
      row.querySelector(".cell-sub").textContent = user.email;
      row.querySelector(".user-role").textContent = roleLabel;
      row.querySelectorAll("td")[2].textContent = statusLabel;
      row.querySelector(".cell-time").textContent = user.last_login || "Nunca";
      const toggleBtn = row.querySelector(".admin-toggle-user");
      toggleBtn.addEventListener("click", async () => {
        try {
          await api(`/auth/users/${user.id}`, {
            method: "PUT",
            json: { is_active: !user.is_active },
          });
          await loadAdminUsersTable();
          await loadAdminDashboard();
        } catch (error) {
          showToast(`Falha ao atualizar usuario: ${error.message}`, "error");
        }
      });
      elements.adminUsersList.appendChild(row);
    });
  } catch (error) {
    showToast(`Usuarios: ${error.message}`, "error");
  }
}

/* ============================================
   NOTIFICATIONS
   ============================================ */

async function loadNotifications() {
  try {
    const [items, countData] = await Promise.all([
      api("/notifications/?limit=50"),
      api("/notifications/unread-count"),
    ]);
    state.notificationItems = items || [];
    state.notificationCount = (countData && countData.count) || 0;
    elements.notificationBadge.textContent = String(state.notificationCount);
    elements.notificationBadge.hidden = state.notificationCount === 0;
    if (state.notificationsVisible) renderNotificationsList();
  } catch (_error) {
    // Notifications are optional; silence errors during startup.
  }
}

function renderNotificationsList() {
  elements.notificationsList.innerHTML = "";
  elements.notificationsEmpty.hidden = state.notificationItems.length > 0;
  state.notificationItems.forEach((notification) => {
    const item = document.createElement("div");
    item.className = `notification-item${notification.read ? "" : " unread"}`;
    item.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between">
        <span class="notification-title"></span>
        <span class="notification-priority ${notification.priority || "medium"}"></span>
      </div>
      <div class="notification-message"></div>
      <div class="notification-time"></div>`;
    item.querySelector(".notification-title").textContent = notification.title || (notification.type || "Notificacao");
    item.querySelector(".notification-priority").textContent = notification.priority || "medium";
    item.querySelector(".notification-message").textContent = notification.message || "";
    item.querySelector(".notification-time").textContent = notification.created_at || "";
    if (!notification.read) {
      item.addEventListener("click", async () => {
        try {
          await api(`/notifications/${notification.id}/read`, { method: "POST" });
          await loadNotifications();
        } catch (_error) {
          // ignore
        }
      });
    }
    elements.notificationsList.appendChild(item);
  });
}

function toggleNotificationsPanel() {
  state.notificationsVisible = !state.notificationsVisible;
  elements.notificationsPanel.hidden = !state.notificationsVisible;
  if (state.notificationsVisible) {
    loadNotifications().then(() => renderNotificationsList());
  }
}

async function markAllNotificationsRead() {
  try {
    await api("/notifications/read-all", { method: "POST" });
    await loadNotifications();
  } catch (error) {
    showToast(`Notificacoes: ${error.message}`, "error");
  }
}

async function initialize() {
  const savedTheme = localStorage.getItem("celsius-theme-v2");
  const legacyTheme = localStorage.getItem("celsius-theme");
  setTheme(savedTheme || (legacyTheme === "dark" ? "green" : legacyTheme) || "light");
  if (localStorage.getItem("celsius-sidebar-collapsed") === "1") setSidebarCollapsed(true);
  syncWorkModeUI();
  bindEvents();
  updateSendState();
  try {
    const user = await api("/auth/me");
    state.currentUser = user;
    elements.userDisplayName.textContent = user.display_name || user.email.split("@")[0];
    elements.adminButton.hidden = user.role !== "admin";
    state.adminVisible = user.role === "admin";
    showAppScreen();
  } catch (_error) {
    showLoginScreen();
    return;
  }
  await Promise.all([
    loadSession(),
    loadNavigation(),
    loadConversations(),
    loadModels(),
    loadVoiceCapabilities(),
    loadAgentModes(),
  ]);
  await Promise.all([loadAgenda(), loadDueReminders(), loadDocuments(), loadInventory(), loadProducts()]);
  await loadNotifications();
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
    if (state.adminVisible && state.activeView === "admin") loadAdminDashboard();
    loadDueReminders();
    loadNotifications();
  }, 15_000);
  connectEvents();
  elements.input.focus();
}

initialize();
