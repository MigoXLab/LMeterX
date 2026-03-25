/**
 * @file taskAliases.ts
 * @description Type aliases re-exported from job.ts for backward compatibility
 * @author Charm
 * @copyright 2025
 * @deprecated Use imports from './job' instead
 */
import { ApiResponse, LlmTask, Pagination } from './job';

/** @deprecated Use LlmTask from './job' instead */
export type BenchmarkJob = LlmTask;

export type { ApiResponse, Pagination };
