/**
 * @file StatusTag.tsx
 * @description Reusable status tag component - Modern pill style
 * @author Charm
 * @copyright 2025
 */

import React from 'react';
import { useTranslation } from 'react-i18next';

import { TASK_STATUS_MAP } from '@/utils/constants';

interface StatusTagProps {
  /** Status value */
  status: string;
  /** Custom status mapping (overrides default) */
  statusMap?: Record<string, { color: string; text: string }>;
  /** Show unknown status as default tag */
  showUnknown?: boolean;
  /** Custom className */
  className?: string;
}

/**
 * Modern pill-style status color mapping
 */
interface PillStyle {
  bg: string;
  color: string;
  dotColor: string;
  pulse?: boolean;
}

const STATUS_PILL_STYLES: Record<string, PillStyle> = {
  created: {
    bg: 'rgba(0, 0, 0, 0.04)',
    color: '#8c8c8c',
    dotColor: '#bfbfbf',
  },
  running: {
    bg: 'rgba(102, 126, 234, 0.08)',
    color: '#667eea',
    dotColor: '#667eea',
    pulse: true,
  },
  completed: {
    bg: 'rgba(82, 196, 26, 0.08)',
    color: '#52c41a',
    dotColor: '#52c41a',
  },
  stopping: {
    bg: 'rgba(250, 173, 20, 0.08)',
    color: '#d48806',
    dotColor: '#faad14',
    pulse: true,
  },
  stopped: {
    bg: 'rgba(250, 140, 22, 0.08)',
    color: '#d46b08',
    dotColor: '#fa8c16',
  },
  locked: {
    bg: 'rgba(250, 173, 20, 0.08)',
    color: '#d48806',
    dotColor: '#faad14',
  },
  failed: {
    bg: 'rgba(255, 77, 79, 0.08)',
    color: '#ff4d4f',
    dotColor: '#ff4d4f',
  },
  failed_requests: {
    bg: 'rgba(235, 47, 150, 0.08)',
    color: '#c41d7f',
    dotColor: '#eb2f96',
  },
};

const DEFAULT_PILL_STYLE: PillStyle = {
  bg: 'rgba(0, 0, 0, 0.04)',
  color: '#8c8c8c',
  dotColor: '#bfbfbf',
};

/**
 * Reusable status tag component with modern pill styling
 */
export const StatusTag: React.FC<StatusTagProps> = ({
  status,
  statusMap = TASK_STATUS_MAP,
  showUnknown = true,
  className,
}) => {
  const { t } = useTranslation();
  const statusKey = status?.toLowerCase();
  const statusInfo = statusMap[statusKey as keyof typeof statusMap];

  if (!statusInfo && !showUnknown) {
    return null;
  }

  const translatedText = t(`status.${statusKey}`, status || 'Unknown');
  const pillStyle = STATUS_PILL_STYLES[statusKey] || DEFAULT_PILL_STYLE;

  return (
    <span
      className={`status-pill ${className || ''}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 10px 3px 8px',
        borderRadius: 20,
        fontSize: 12,
        fontWeight: 500,
        lineHeight: '18px',
        background: pillStyle.bg,
        color: pillStyle.color,
        whiteSpace: 'nowrap',
      }}
    >
      <span
        className={pillStyle.pulse ? 'status-dot-pulse' : undefined}
        style={{
          display: 'inline-block',
          width: 6,
          height: 6,
          borderRadius: '50%',
          backgroundColor: pillStyle.dotColor,
          flexShrink: 0,
        }}
      />
      {translatedText}
    </span>
  );
};

export default StatusTag;
