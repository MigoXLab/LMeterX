import {
  InfoCircleOutlined,
  MinusCircleOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import { Button, Form, Input, Space, Tooltip, theme } from 'antd';
import type { FormInstance } from 'antd';
import React from 'react';

import { useI18n } from '@/hooks/useI18n';

interface Props {
  form: FormInstance;
  title: React.ReactNode;
  tooltip: React.ReactNode;
  redactedHeaderKeys?: string[];
  managedHeaderNames?: Set<string>;
  maxValueLength?: number;
}

const RequestHeadersEditor: React.FC<Props> = ({
  form,
  title,
  tooltip,
  redactedHeaderKeys = [],
  managedHeaderNames,
  maxValueLength = 2000,
}) => {
  const { t } = useI18n();
  const { token } = theme.useToken();
  const redacted = new Set(redactedHeaderKeys.map(key => key.toLowerCase()));

  return (
    <div
      style={{
        marginBottom: 24,
        padding: 16,
        backgroundColor: token.colorFillAlter,
        borderRadius: 8,
      }}
    >
      <div style={{ marginBottom: 12, fontWeight: 600 }}>
        <span>{title}</span>
        <Tooltip title={tooltip}>
          <InfoCircleOutlined style={{ marginLeft: 5 }} />
        </Tooltip>
      </div>
      <Form.List name='headers'>
        {(fields, { add, remove }) => (
          <>
            {fields.map(({ key: fieldKey, name, ...restField }) => {
              const fixed = Boolean(
                form.getFieldValue(['headers', name, 'fixed'])
              );
              const headerKey = String(
                form.getFieldValue(['headers', name, 'key']) || ''
              );
              const inherited = redacted.has(headerKey.toLowerCase());
              return (
                <Space
                  key={fieldKey}
                  align='start'
                  style={{ display: 'flex', marginBottom: 8, width: '100%' }}
                >
                  <Form.Item
                    {...restField}
                    name={[name, 'key']}
                    style={{ flex: 1, minWidth: 180, marginBottom: 0 }}
                    rules={[
                      {
                        required: true,
                        whitespace: true,
                        message: t(
                          'components.createJobForm.headerNameRequired'
                        ),
                      },
                      {
                        max: 100,
                        message: t(
                          'components.createJobForm.headerNameLengthLimit'
                        ),
                      },
                      {
                        validator: async (_, value) => {
                          if (fixed || inherited || !String(value || '').trim())
                            return;
                          const normalized = String(value).trim().toLowerCase();
                          if (
                            managedHeaderNames?.has(normalized) ||
                            normalized.startsWith('mcp-param-')
                          ) {
                            throw new Error(
                              t(
                                'components.createAgentTaskForm.managedHeader',
                                { header: value }
                              )
                            );
                          }
                          const duplicates = (
                            form.getFieldValue('headers') || []
                          ).filter(
                            (item: any) =>
                              String(item?.key || '')
                                .trim()
                                .toLowerCase() === normalized
                          );
                          if (duplicates.length > 1) {
                            throw new Error(
                              t(
                                'components.createAgentTaskForm.duplicateHeader',
                                { header: value }
                              )
                            );
                          }
                        },
                      },
                    ]}
                  >
                    <Input
                      disabled={fixed || inherited}
                      maxLength={100}
                      placeholder={t(
                        fixed
                          ? 'components.createJobForm.systemHeader'
                          : 'components.createJobForm.headerNamePlaceholder'
                      )}
                    />
                  </Form.Item>
                  <Form.Item
                    {...restField}
                    name={[name, 'value']}
                    style={{ flex: 2, marginBottom: 0 }}
                    rules={[
                      {
                        required: true,
                        whitespace: true,
                        message: t(
                          'components.createAgentTaskForm.headerValueRequired',
                          { header: headerKey }
                        ),
                      },
                      {
                        max: maxValueLength,
                        message: t(
                          'components.createAgentTaskForm.headerValueLengthLimit'
                        ),
                      },
                    ]}
                  >
                    <Input
                      disabled={fixed}
                      maxLength={maxValueLength}
                      autoComplete='new-password'
                      placeholder={t(
                        'components.createJobForm.headerValuePlaceholder'
                      )}
                    />
                  </Form.Item>
                  {!fixed && !inherited && (
                    <MinusCircleOutlined
                      aria-label={t(
                        'components.createAgentTaskForm.removeHeader'
                      )}
                      onClick={() => remove(name)}
                      style={{ marginTop: 9, color: token.colorTextTertiary }}
                    />
                  )}
                </Space>
              );
            })}
            <Button
              type='dashed'
              onClick={() => add({ key: '', value: '', fixed: false })}
              block
              icon={<PlusOutlined />}
            >
              {t('components.createJobForm.addHeaderButton')}
            </Button>
          </>
        )}
      </Form.List>
    </div>
  );
};

export default RequestHeadersEditor;
