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
            <span style={{ marginLeft: '8px', color: '#1890ff' }}>✓</span>
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
            <span style={{ marginLeft: '8px', color: '#1890ff' }}>✓</span>
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
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: 'none',
          boxShadow: 'none',
          padding: '4px 8px',
          height: 'auto',
          lineHeight: '1',
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
