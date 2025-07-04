/**
 * @file NotFound.tsx
 * @description Not found page component
 * @author Charm
 * @copyright 2025
 * */
import { Button, Result } from 'antd';
import React from 'react';
import { useNavigate } from 'react-router-dom';

const NotFound: React.FC = () => {
  const navigate = useNavigate();

  return (
    <Result
      status='404'
      title='404'
      subTitle='Sorry, the page you visited does not exist'
      extra={
        <Button type='primary' onClick={() => navigate('/')}>
          Back Home
        </Button>
      }
    />
  );
};

export default NotFound;
