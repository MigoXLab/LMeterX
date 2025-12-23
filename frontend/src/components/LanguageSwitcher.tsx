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
            <span style={{ marginLeft: '8px', color: '#667eea' }}>✓</span>
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
            <span style={{ marginLeft: '8px', color: '#667eea' }}>✓</span>
          )}
        </div>
      ),
      onClick: () => handleLanguageChange('zh'),
    },
  ];

  const getCurrentLanguageLabel = () => {
    return currentLanguage === 'zh' ? '中文' : 'English';
  };

  // const getCurrentFlag = () => {
  //   return currentLanguage === 'zh' ? '🇨🇳' : '🇺🇸';
  // };

  return (
    <Dropdown
      menu={{ items }}
      placement='bottomRight'
      trigger={['click']}
      arrow
    >
      <Button
        type='text'
        className='language-switcher-button'
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px solid rgba(0, 0, 0, 0.12)',
          background: '#ffffff',
          color: '#333',
          borderRadius: '8px',
          padding: '4px 12px',
          height: '36px',
          lineHeight: '1',
          transition: 'all 0.2s ease',
          fontWeight: 500,
        }}
        onMouseEnter={e => {
          e.currentTarget.style.background = '#f5f5f5';
          e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.2)';
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = '#ffffff';
          e.currentTarget.style.borderColor = 'rgba(0, 0, 0, 0.12)';
        }}
      >
        <GlobalOutlined
          style={{
            marginRight: '4px',
            fontSize: '14px',
            display: 'flex',
            alignItems: 'center',
          }}
        />
        <span
          style={{
            display: 'flex',
            alignItems: 'center',
            fontSize: '14px',
            lineHeight: '1',
          }}
        >
          {getCurrentLanguageLabel()}
        </span>
      </Button>
    </Dropdown>
  );
};

export default LanguageSwitcher;
