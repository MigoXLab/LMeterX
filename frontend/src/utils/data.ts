/**
 * @file data.ts
 * @description Data processing utility functions
 * @author Charm
 * @copyright 2025
 */

/**
 * Safely parse JSON string
 * @param jsonString - JSON string to parse
 * @param defaultValue - Default value if parsing fails
 * @returns Parsed object or default value
 */
export const safeJsonParse = <T = any>(
  jsonString: string | null | undefined,
  defaultValue: T | null = null
): T | null => {
  if (!jsonString) return defaultValue;

  try {
    return JSON.parse(jsonString) as T;
  } catch (error) {
    // Failed to parse JSON
    return defaultValue;
  }
};

/**
 * Safely stringify object to JSON
 * @param obj - Object to stringify
 * @param space - Indentation space (default: 0)
 * @returns JSON string or empty string if failed
 */
export const safeJsonStringify = (obj: any, space: number = 0): string => {
  try {
    return JSON.stringify(obj, null, space);
  } catch (error) {
    // Failed to stringify object
    return '';
  }
};

/**
 * Deep clone an object (using JSON serialization)
 * @param obj - Object to clone
 * @returns Cloned object or null if failed
 */
export const deepClone = <T>(obj: T): T | null => {
  try {
    return JSON.parse(JSON.stringify(obj));
  } catch (error) {
    // Failed to deep clone object
    return null;
  }
};

/**
 * Check if value is empty (null, undefined, empty string, empty array, empty object)
 * @param value - Value to check
 * @returns True if value is empty
 */
export const isEmpty = (value: any): boolean => {
  if (value === null || value === undefined) return true;
  if (typeof value === 'string') return value.trim() === '';
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') return Object.keys(value).length === 0;
  return false;
};

/**
 * Remove empty values from object
 * @param obj - Object to clean
 * @returns Object with empty values removed
 */
export const removeEmptyValues = <T extends Record<string, any>>(
  obj: T
): Partial<T> => {
  const cleaned: Partial<T> = {};

  Object.entries(obj).forEach(([key, value]) => {
    if (!isEmpty(value)) {
      cleaned[key as keyof T] = value;
    }
  });

  return cleaned;
};

/**
 * Generate unique ID
 * @param prefix - Optional prefix
 * @returns Unique ID string
 */
export const generateId = (prefix: string = 'id'): string => {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
};

/**
 * Format file size in human readable format
 * @param bytes - Size in bytes
 * @returns Formatted size string
 */
export const formatFileSize = (bytes: number): string => {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${parseFloat((bytes / k ** i).toFixed(3))} ${sizes[i]}`;
};

/**
 * Truncate string with ellipsis
 * @param str - String to truncate
 * @param maxLength - Maximum length
 * @returns Truncated string
 */
export const truncateString = (str: string, maxLength: number): string => {
  if (!str || str.length <= maxLength) return str;
  return `${str.substring(0, maxLength)}...`;
};

/**
 * Capitalize first letter of string
 * @param str - String to capitalize
 * @returns Capitalized string
 */
export const capitalize = (str: string): string => {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1);
};

/**
 * Convert camelCase to kebab-case
 * @param str - camelCase string
 * @returns kebab-case string
 */
export const camelToKebab = (str: string): string => {
  return str.replace(/([a-z0-9]|(?=[A-Z]))([A-Z])/g, '$1-$2').toLowerCase();
};

/**
 * Convert kebab-case to camelCase
 * @param str - kebab-case string
 * @returns camelCase string
 */
export const kebabToCamel = (str: string): string => {
  return str.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
};

/**
 * Get random integer between min and max (inclusive)
 * @param min - Minimum value
 * @param max - Maximum value
 * @returns Random integer
 */
export const randomInt = (min: number, max: number): number => {
  return Math.floor(Math.random() * (max - min + 1)) + min;
};

/**
 * Clamp number between min and max
 * @param value - Value to clamp
 * @param min - Minimum value
 * @param max - Maximum value
 * @returns Clamped value
 */
export const clamp = (value: number, min: number, max: number): number => {
  return Math.min(Math.max(value, min), max);
};

export default {
  safeJsonParse,
  safeJsonStringify,
  deepClone,
  isEmpty,
  removeEmptyValues,
  generateId,
  formatFileSize,
  truncateString,
  capitalize,
  camelToKebab,
  kebabToCamel,
  randomInt,
  clamp,
};
