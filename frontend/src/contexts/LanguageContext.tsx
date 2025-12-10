/**
 * @file LanguageContext.tsx
 * @description Language context for global language state management
 * @author Charm
 * @copyright 2025
 */
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useTranslation } from 'react-i18next';

interface LanguageContextType {
  currentLanguage: string;
  changeLanguage: (language: string) => void;
  isLanguageReady: boolean;
}

const LanguageContext = createContext<LanguageContextType | undefined>(
  undefined
);

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { i18n } = useTranslation();
  const [currentLanguage, setCurrentLanguage] = useState(i18n.language);
  const [isLanguageReady, setIsLanguageReady] = useState(false);

  useEffect(() => {
    const handleLanguageChange = (lng: string) => {
      setCurrentLanguage(lng);
    };

    // Listen for language changes
    i18n.on('languageChanged', handleLanguageChange);

    // Set ready state when i18n is initialized
    if (i18n.isInitialized) {
      setIsLanguageReady(true);
    } else {
      i18n.on('initialized', () => {
        setIsLanguageReady(true);
      });
    }

    return () => {
      i18n.off('languageChanged', handleLanguageChange);
    };
  }, [i18n]);

  const changeLanguage = useCallback(
    (language: string) => {
      i18n.changeLanguage(language);
    },
    [i18n]
  );

  const value = useMemo(
    () => ({
      currentLanguage,
      changeLanguage,
      isLanguageReady,
    }),
    [changeLanguage, currentLanguage, isLanguageReady]
  );

  return (
    <LanguageContext.Provider value={value}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = () => {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error('useLanguage must be used within a LanguageProvider');
  }
  return context;
};

export default LanguageContext;
