/**
 * @file PageHeader.tsx
 * @description Reusable page header component
 * @author Charm
 * @copyright 2025
 */

import { Typography } from 'antd';
import React from 'react';

const { Title, Text } = Typography;

interface PageHeaderProps {
  /** Page title */
  title: React.ReactNode;
  /** Page description */
  description?: React.ReactNode;
  /** Icon for the title */
  icon?: React.ReactNode;
  /** Title level (1-5) */
  level?: 1 | 2 | 3 | 4 | 5;
  /** Extra content on the right */
  extra?: React.ReactNode;
  /** Custom className */
  className?: string;
}

/**
 * Reusable page header component
 */
export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  description,
  icon,
  level = 3,
  extra,
  className = 'page-header',
}) => {
  return (
    <div className={className}>
      <div className='flex justify-between align-center'>
        <div
          style={{ flex: 1, display: 'flex', alignItems: 'baseline', gap: 0 }}
        >
          <Title
            level={level}
            style={{
              marginBottom: 0,
              fontSize: level === 3 ? '20px' : undefined,
              fontWeight: 600,
              color: 'var(--color-text)',
              lineHeight: 1.4,
            }}
          >
            {icon && (
              <span
                style={{
                  marginRight: '10px',
                  color: '#667eea',
                  fontSize: '18px',
                }}
              >
                {icon}
              </span>
            )}
            {title}
          </Title>
          {description && (
            <Text
              style={{
                fontSize: '13px',
                color: 'var(--color-text-secondary)',
                marginLeft: '12px',
                whiteSpace: 'nowrap',
              }}
            >
              {description}
            </Text>
          )}
        </div>
        {extra && (
          <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
            {extra}
          </div>
        )}
      </div>
    </div>
  );
};

export default PageHeader;
