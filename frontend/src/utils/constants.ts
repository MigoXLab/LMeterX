/**
 * @file constants.ts
 * @description Application constants and configuration
 */

// API Configuration
export const API_PATHS = {
  CHAT_COMPLETIONS: '/chat/completions',
  EMBEDDINGS: '/v1/embeddings',
  COMPLETIONS: '/v1/completions',
  MODELS: '/v1/models',
} as const;

// Form field defaults
export const DEFAULT_FORM_VALUES = {
  CONCURRENT_USERS: 1,
  SPAWN_RATE: 1,
  STREAM_MODE: true,
  CHAT_TYPE: 0,
  DATA_FORMAT: 'json',
  DURATION: 60,
  MODEL: 'gpt-3.5-turbo',
  MAX_TOKENS: 1000,
  TEMPERATURE: 0.7,
} as const;

// Chat completions field mapping defaults
export const CHAT_COMPLETIONS_FIELD_MAPPING = {
  STREAMING: {
    prompt: 'messages.0.content',
    stream_prefix: 'data:',
    data_format: 'json',
    content: 'choices.0.delta.content',
    reasoning_content: 'choices.0.delta.reasoning_content',
    prompt_tokens: 'usage.prompt_tokens',
    completion_tokens: 'usage.completion_tokens',
    total_tokens: 'usage.total_tokens',
    end_prefix: 'data:',
    stop_flag: '[DONE]',
    end_field: '',
  },
  NON_STREAMING: {
    prompt: 'messages.0.content',
    stream_prefix: '',
    data_format: 'json',
    content: 'choices.0.message.content',
    reasoning_content: 'choices.0.message.reasoning_content',
    prompt_tokens: 'usage.prompt_tokens',
    completion_tokens: 'usage.completion_tokens',
    total_tokens: 'usage.total_tokens',
    end_prefix: '',
    stop_flag: '',
    end_field: '',
  },
} as const;

// Default headers
export const DEFAULT_HEADERS = [
  { key: 'Content-Type', value: 'application/json', fixed: true },
  { key: 'Authorization', value: '', fixed: false },
] as const;

// Task status mapping - text will be handled by i18n
export const TASK_STATUS_MAP = {
  created: { color: 'default', text: 'status.created' },
  running: { color: 'processing', text: 'status.running' },
  completed: { color: 'success', text: 'status.completed' },
  stopping: { color: 'gold', text: 'status.stopping' },
  stopped: { color: 'orange', text: 'status.stopped' },
  locked: { color: 'warning', text: 'status.locked' },
  failed: { color: 'error', text: 'status.failed' },
  failed_requests: { color: 'magenta', text: 'status.failed_requests' },
} as const;

// File upload configuration
export const FILE_UPLOAD_CONFIG = {
  CERT_FORMATS: '.crt,.pem',
  KEY_FORMATS: '.key,.pem',
  COMBINED_FORMATS: '.pem',
  MAX_COUNT: 1,
  MAX_SIZE: 2 * 1024 * 1024 * 1024, // 2GB
  ALLOWED_TYPES: ['.json', '.txt', '.csv'],
  CERTIFICATE_TYPES: ['.pem', '.crt', '.key'],
  IMAGE_TYPES: ['.jpg', '.jpeg', '.png', '.gif', '.webp'],
} as const;

// UI Configuration
export const UI_CONFIG = {
  FORM_GUTTER: 24,
  CARD_PADDING: 24,
  MESSAGE_DURATION: {
    SUCCESS: 4,
    WARNING: 6,
    ERROR: 5,
  },
  TABLE_SCROLL_X: 1100,
  SEARCH_WIDTH: 300,
  MODAL_WIDTH: {
    SMALL: 520,
    MEDIUM: 720,
    LARGE: 1000,
    EXTRA_LARGE: 1200,
  },
  PAGE_SIZE: {
    SMALL: 10,
    MEDIUM: 20,
    LARGE: 50,
  },
  FORM_LAYOUT: {
    LABEL_COL: { span: 6 },
    WRAPPER_COL: { span: 18 },
  },
  BREAKPOINTS: {
    XS: 480,
    SM: 576,
    MD: 768,
    LG: 992,
    XL: 1200,
    XXL: 1600,
  },
} as const;

// API configuration
export const API_CONFIG = {
  TIMEOUT: 30000, // 30 seconds
  RETRY_ATTEMPTS: 3,
  RETRY_DELAY: 1000, // 1 second
  BASE_HEADERS: {
    'Content-Type': 'application/json',
  },
} as const;

// Validation limits
export const VALIDATION_LIMITS = {
  TASK_NAME_MAX_LENGTH: 100,
  URL_MAX_LENGTH: 2048,
  CONCURRENT_USERS_MAX: 1000,
  DURATION_MAX: 86400, // 24 hours
  SPAWN_RATE_MAX: 100,
  MAX_TOKENS_MAX: 4096,
  TEMPERATURE_MAX: 2,
  TEMPERATURE_MIN: 0,
} as const;

// Common regex patterns
export const REGEX_PATTERNS = {
  URL: /^https?:\/\/.+/,
  EMAIL: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
  PHONE: /^[\d\-+() \s]+$/,
  ALPHANUMERIC: /^[a-zA-Z0-9]+$/,
  API_PATH: /^\/[a-zA-Z0-9/-_]*$/,
} as const;

// Message templates
export const MESSAGE_TEMPLATES = {
  COPY_SUCCESS: 'Task template copied successfully',
  COPY_ERROR: 'Failed to copy task template',
  SAVE_SUCCESS: 'Task saved successfully',
  SAVE_ERROR: 'Failed to save task',
  DELETE_SUCCESS: 'Task deleted successfully',
  DELETE_ERROR: 'Failed to delete task',
  TEST_SUCCESS: 'API test completed successfully',
  TEST_ERROR: 'API test failed',
  UPLOAD_SUCCESS: 'File uploaded successfully',
  UPLOAD_ERROR: 'File upload failed',
} as const;
