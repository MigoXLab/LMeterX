/**
 * @file LanguageSwitcher.tsx
 * @description Language switcher component for i18n
 * @author Charm
 * @copyright 2025
 */
import { GlobalOutlined } from '@ant-design/icons';
import { Button, Dropdown, type MenuProps } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';

const LanguageSwitcher: React.FC = () => {
  const { i18n, t } = useTranslation();

  const currentLanguage = i18n.language;

  const handleLanguageChange = (language: string) => {
    i18n.changeLanguage(language);
  };

  const items: MenuProps['items'] = [
    {
      key: 'en',
      label: (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '4px 8px',
          }}
        >
          {/* <span style={{ marginRight: '8px' }}>🇺🇸</span> */}
          {t('header.english')}
          {currentLanguage === 'en' && (
            <span style={{ marginLeft: '8px', color: '#333', fontWeight: 600 }}>
              ✓
            </span>
          )}
        </div>
      ),
      onClick: () => handleLanguageChange('en'),
    },
    {
      key: 'zh',
      label: (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            padding: '4px 8px',
          }}
        >
          {/* <span style={{ marginRight: '8px' }}>🇨🇳</span> */}
          {t('header.chinese')}
          {currentLanguage === 'zh' && (
            <span style={{ marginLeft: '8px', color: '#333', fontWeight: 600 }}>
              ✓
            </span>
          )}
        </div>
      ),
      onClick: () => handleLanguageChange('zh'),
    },
  ];

  return (
    <Dropdown
      menu={{ items }}
      placement='bottomRight'
      trigger={['click']}
      arrow
    >
      <Button
        type='text'
        className='language-switcher-button language-switcher-tech'
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: 'none',
          background: 'transparent',
          color: '#333',
          borderRadius: '8px',
          padding: 0,
          height: '36px',
          width: '36px',
          lineHeight: '1',
          transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
          fontWeight: 500,
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        <GlobalOutlined
          style={{
            fontSize: '16px',
            display: 'flex',
            alignItems: 'center',
          }}
        />
      </Button>
    </Dropdown>
  );
};

export default LanguageSwitcher;
