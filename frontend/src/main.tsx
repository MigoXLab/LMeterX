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
import {
  handleUnauthorizedError,
  waitForLoginRedirect,
} from './utils/sessionExpired';

// Send HttpOnly auth cookies with all requests (including plain axios usage)
axios.defaults.withCredentials = true;
axios.interceptors.response.use(
  response => response,
  error => {
    if (handleUnauthorizedError(error)) {
      return waitForLoginRedirect();
    }
    return Promise.reject(error);
  }
);

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
