/**
 * @file LanguageSwitcher.tsx
 * @description Language switcher component for i18n
 * @author Charm
 * @copyright 2025
 */
import { Button } from 'antd';
import React from 'react';
import { useTranslation } from 'react-i18next';

const LanguageSwitcher: React.FC = () => {
  const { i18n } = useTranslation();

  const currentLanguage = i18n.language;

  const toggleLanguage = () => {
    i18n.changeLanguage(currentLanguage === 'zh' ? 'en' : 'zh');
  };

  const langLabel = currentLanguage === 'zh' ? '中' : 'EN';

  return (
    <Button
      type='text'
      className='language-switcher-button language-switcher-tech'
      onClick={toggleLanguage}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: 'none',
        background: 'transparent',
        color: 'var(--color-text-secondary)',
        borderRadius: '8px',
        padding: '0 10px',
        height: '32px',
        minWidth: '36px',
        lineHeight: '1',
        transition: 'all 0.25s ease',
        fontWeight: 600,
        fontSize: '13px',
        letterSpacing: '0.02em',
        gap: 4,
      }}
    >
      <svg
        viewBox='0 0 24 24'
        width='14'
        height='14'
        fill='none'
        stroke='currentColor'
        strokeWidth='2'
        strokeLinecap='round'
        strokeLinejoin='round'
        style={{ flexShrink: 0 }}
      >
        <circle cx='12' cy='12' r='10' />
        <path d='M2 12h20' />
        <path d='M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10A15.3 15.3 0 0 1 12 2z' />
      </svg>
      <span>{langLabel}</span>
    </Button>
  );
};

export default LanguageSwitcher;
