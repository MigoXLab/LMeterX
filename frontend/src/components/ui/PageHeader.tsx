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
        <div style={{ flex: 1 }}>
          <Title
            level={level}
            style={{
              marginBottom: description ? '8px' : 0,
              fontSize: level === 3 ? '24px' : undefined,
              fontWeight: 600,
            }}
          >
            {icon && <span className='mr-8'>{icon}</span>}
            {title}
          </Title>
          {description && (
            <Text
              type='secondary'
              style={{
                fontSize: '14px',
                color: '#666',
                display: 'block',
              }}
            >
              {description}
            </Text>
          )}
        </div>
        {extra && <div>{extra}</div>}
      </div>
    </div>
  );
};

export default PageHeader;
