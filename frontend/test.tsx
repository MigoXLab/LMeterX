import React from 'react';

const TestComponent = () => {
  return (
    <div
      renderSomething={(menu: any) => (
        <div>{menu}</div>
      )}
    />
  );
};
