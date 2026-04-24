import { theme } from 'antd';
import React from 'react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

// markdown components
const createMarkdownComponents = (token: any) => ({
  code: ({ inline, className, children, ...props }: any) => {
    const match = /language-(\w+)/.exec(className || '');
    return !inline && match ? (
      <pre
        style={{
          backgroundColor: token.colorBgContainer,
          border: `1px solid ${token.colorBorder}`,
          borderRadius: '6px',
          padding: '16px',
          overflow: 'auto',
          fontSize: '14px',
          lineHeight: '1.5',
          margin: '16px 0',
        }}
      >
        <code
          className={className}
          style={{
            fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
            color: token.colorText,
          }}
          {...props}
        >
          {children}
        </code>
      </pre>
    ) : (
      <code
        className={className}
        style={{
          backgroundColor: token.colorBgContainer,
          padding: '2px 6px',
          borderRadius: '4px',
          fontSize: '0.9em',
          fontFamily: 'Monaco, Menlo, "Ubuntu Mono", monospace',
          color: token.colorText,
        }}
        {...props}
      >
        {children}
      </code>
    );
  },
  h1: ({ children, ...props }: any) => (
    <h1
      style={{
        fontSize: '24px',
        fontWeight: 'bold',
        color: token.colorText,
        margin: '24px 0 16px 0',
        borderBottom: `2px solid ${token.colorBorder}`,
        paddingBottom: '8px',
      }}
      {...props}
    >
      {children}
    </h1>
  ),
  h2: ({ children, ...props }: any) => (
    <h2
      style={{
        fontSize: '20px',
        fontWeight: 'bold',
        color: token.colorText,
        margin: '20px 0 12px 0',
        borderBottom: `1px solid ${token.colorBorder}`,
        paddingBottom: '6px',
      }}
      {...props}
    >
      {children}
    </h2>
  ),
  h3: ({ children, ...props }: any) => (
    <h3
      style={{
        fontSize: '18px',
        fontWeight: 'bold',
        color: token.colorText,
        margin: '16px 0 8px 0',
      }}
      {...props}
    >
      {children}
    </h3>
  ),
  p: ({ children, ...props }: any) => (
    <p
      style={{
        margin: '12px 0',
        lineHeight: '1.6',
        color: token.colorText,
      }}
      {...props}
    >
      {children}
    </p>
  ),
  ul: ({ children, ...props }: any) => (
    <ul
      style={{
        margin: '12px 0',
        paddingLeft: '24px',
        lineHeight: '1.6',
      }}
      {...props}
    >
      {children}
    </ul>
  ),
  ol: ({ children, ...props }: any) => (
    <ol
      style={{
        margin: '12px 0',
        paddingLeft: '24px',
        lineHeight: '1.6',
      }}
      {...props}
    >
      {children}
    </ol>
  ),
  li: ({ children, ...props }: any) => (
    <li
      style={{
        margin: '4px 0',
        lineHeight: '1.6',
        color: token.colorText,
      }}
      {...props}
    >
      {children}
    </li>
  ),
  blockquote: ({ children, ...props }: any) => (
    <blockquote
      style={{
        borderLeft: `4px solid ${token.colorPrimary}`,
        margin: '16px 0',
        padding: '12px 16px',
        backgroundColor: token.colorBgContainer,
        borderRadius: '4px',
        fontStyle: 'italic',
        color: token.colorTextSecondary,
      }}
      {...props}
    >
      {children}
    </blockquote>
  ),
  table: ({ children, ...props }: any) => (
    <div
      style={{
        overflowX: 'auto',
        margin: '16px 0',
        border: `1px solid ${token.colorBorder}`,
        borderRadius: '6px',
        maxWidth: '100%',
      }}
    >
      <table
        style={{
          minWidth: '100%',
          borderCollapse: 'collapse',
          fontSize: '14px',
          whiteSpace: 'nowrap',
        }}
        {...props}
      >
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...props }: any) => (
    <thead
      style={{
        backgroundColor: token.colorBgContainer,
        borderBottom: `2px solid ${token.colorBorder}`,
      }}
      {...props}
    >
      {children}
    </thead>
  ),
  tr: ({ children, ...props }: any) => (
    <tr
      style={{
        borderBottom: `1px solid ${token.colorBorder}`,
      }}
      {...props}
    >
      {children}
    </tr>
  ),
  th: ({ children, ...props }: any) => (
    <th
      style={{
        padding: '12px 16px',
        textAlign: 'left',
        fontWeight: 'bold',
        color: token.colorText,
        backgroundColor: token.colorBgContainer,
        borderRight: `1px solid ${token.colorBorder}`,
        whiteSpace: 'nowrap',
        minWidth: '120px',
      }}
      {...props}
    >
      {children}
    </th>
  ),
  td: ({ children, ...props }: any) => (
    <td
      style={{
        padding: '12px 16px',
        color: token.colorText,
        borderRight: `1px solid ${token.colorBorder}`,
        whiteSpace: 'nowrap',
        minWidth: '120px',
      }}
      {...props}
    >
      {children}
    </td>
  ),
  a: ({ children, ...props }: any) => (
    <a
      style={{
        color: token.colorPrimary,
        textDecoration: 'none',
      }}
      target='_blank'
      rel='noopener noreferrer'
      {...props}
    >
      {children}
    </a>
  ),
  strong: ({ children, ...props }: any) => (
    <strong
      style={{
        fontWeight: 'bold',
        color: token.colorText,
      }}
      {...props}
    >
      {children}
    </strong>
  ),
  em: ({ children, ...props }: any) => (
    <em
      style={{
        fontStyle: 'italic',
        color: token.colorTextSecondary,
      }}
      {...props}
    >
      {children}
    </em>
  ),
  hr: ({ ...props }: any) => (
    <hr
      style={{
        border: 'none',
        height: '1px',
        backgroundColor: token.colorBorder,
        margin: '24px 0',
      }}
      {...props}
    />
  ),
  img: ({ alt, src, title, ...props }: any) => (
    <img
      alt={alt}
      src={src}
      title={title}
      style={{
        maxWidth: '100%',
        height: 'auto',
        display: 'block',
        margin: '16px 0',
        borderRadius: '4px',
        boxShadow: `0 2px 8px ${token.colorTextSecondary}20`,
      }}
      {...props}
    />
  ),
});

const urlTransform = (value: string) => {
  if (value.startsWith('data:image/')) {
    return value;
  }
  return defaultUrlTransform(value);
};

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = '',
}) => {
  const { token } = theme.useToken();
  const components = createMarkdownComponents(token);

  return (
    <div
      className={`markdown-content ${className}`}
      style={{
        color: token.colorText,
        fontSize: '14px',
        lineHeight: '1.6',
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        urlTransform={urlTransform}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownRenderer;
