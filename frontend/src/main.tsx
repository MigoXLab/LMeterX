/**
 * @file main.tsx
 * @description The entry point for the React application.
 * @author: Charm
 * @copyright: 2025 Charm
 */
import axios from 'axios';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './i18n'; // Import i18n configuration
import './index.css';

// Send HttpOnly auth cookies with all requests (including plain axios usage)
axios.defaults.withCredentials = true;

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
