/**
 * @file PageHeader.tsx
 * @description Reusable page header component
 * @author Charm
 * @copyright 2025
 */

import { ArrowLeftOutlined } from '@ant-design/icons';
import { Button, Typography } from 'antd';
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
  /** Optional back action shown at the top-left */
  onBack?: () => void;
  /** Label for the back button */
  backText?: React.ReactNode;
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
  onBack,
  backText,
}) => {
  return (
    <div className={className}>
      {onBack && (
        <Button
          type='link'
          icon={<ArrowLeftOutlined />}
          onClick={onBack}
          style={{ paddingLeft: 0, marginBottom: 4, height: 28 }}
        >
          {backText}
        </Button>
      )}
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
