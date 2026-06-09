/**
 * @file StatusTag.tsx
 * @description Reusable status tag component - Modern pill style
 * @author Charm
 * @copyright 2025
 */

import { Tooltip } from 'antd';
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
    bg: 'rgba(140, 140, 140, 0.05)',
    color: '#8c8c8c',
    dotColor: '#bfbfbf',
  },
  running: {
    bg: 'rgba(102, 126, 234, 0.08)',
    color: '#667eea',
    dotColor: '#667eea',
    pulse: true,
  },
  successed: {
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
    bg: 'rgba(89, 89, 89, 0.08)',
    color: '#595959',
    dotColor: '#8c8c8c',
  },
  pending: {
    bg: 'rgba(250, 173, 20, 0.08)',
    color: '#d48806',
    dotColor: '#faad14',
    pulse: true,
  },
  exception: {
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
  const tooltipText = t(`status.desc.${statusKey}`, '');
  const pillStyle = STATUS_PILL_STYLES[statusKey] || DEFAULT_PILL_STYLE;

  const tagElement = (
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
        cursor: tooltipText ? 'help' : 'default',
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

  if (tooltipText) {
    return <Tooltip title={tooltipText}>{tagElement}</Tooltip>;
  }

  return tagElement;
};

export default StatusTag;
