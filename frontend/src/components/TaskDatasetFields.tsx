import { ExclamationCircleOutlined, UploadOutlined } from '@ant-design/icons';
import {
  Form,
  Input,
  Select,
  theme,
  Typography,
  Upload,
  UploadFile,
} from 'antd';
import React from 'react';

import DatasetSelect, { DatasetType } from '@/components/DatasetSelect';
import { useI18n } from '@/hooks/useI18n';

const { Text } = Typography;

export type TaskDatasetSource = 'none' | 'managed' | 'upload' | 'input';

interface DatasetUploadBoxProps {
  fileName?: string;
  loading?: boolean;
  title: React.ReactNode;
  hint?: React.ReactNode;
  accept?: string;
  onUpload: (options: any) => void;
  onRemove: () => boolean | void;
  showRemoveIcon?: boolean;
}

export const DatasetUploadBox: React.FC<DatasetUploadBoxProps> = ({
  fileName,
  loading,
  title,
  hint,
  accept = '.jsonl,application/x-ndjson',
  onUpload,
  onRemove,
  showRemoveIcon = false,
}) => {
  const { token } = theme.useToken();
  const fileList: UploadFile[] = fileName
    ? [{ uid: '-dataset-file', name: fileName, status: 'done' }]
    : [];

  return (
    <Upload.Dragger
      name='file'
      maxCount={1}
      accept={accept}
      customRequest={onUpload}
      onRemove={onRemove}
      disabled={loading}
      fileList={fileList}
      showUploadList={{ showRemoveIcon }}
      style={{
        borderRadius: 12,
        borderColor: token.colorBorderSecondary,
        background: token.colorFillAlter,
      }}
    >
      <p className='ant-upload-drag-icon' style={{ marginBottom: 12 }}>
        <UploadOutlined style={{ color: token.colorPrimary, fontSize: 24 }} />
      </p>
      <Text strong style={{ fontSize: 16 }}>
        {title}
      </Text>
      {hint && (
        <div
          style={{
            marginTop: 12,
            color: token.colorTextSecondary,
            fontSize: 12,
            whiteSpace: 'pre-line',
          }}
        >
          {hint}
        </div>
      )}
    </Upload.Dragger>
  );
};

interface TaskDatasetFieldsProps {
  source: TaskDatasetSource;
  sourceName: string;
  datasetType: DatasetType;
  allowCustomJsonl?: boolean;
  datasetIdName?: string;
  uploadValueName?: string;
  uploadValueRequired?: boolean;
  uploadFileName?: string;
  uploadLoading?: boolean;
  uploadTitle: React.ReactNode;
  uploadHint?: React.ReactNode;
  uploadAccept?: string;
  showUploadRemoveIcon?: boolean;
  sourceTooltip?: React.ReactNode;
  onSourceChange?: (source: TaskDatasetSource) => void;
  onUpload: (options: any) => void;
  onUploadRemove: () => boolean | void;
  customJsonlContent?: React.ReactNode;
}

/** Shared task dataset selector and conditional dataset-file field. */
const TaskDatasetFields: React.FC<TaskDatasetFieldsProps> = ({
  source,
  sourceName,
  datasetType,
  allowCustomJsonl = false,
  datasetIdName = 'dataset_id',
  uploadValueName,
  uploadValueRequired = true,
  uploadFileName,
  uploadLoading,
  uploadTitle,
  uploadHint,
  uploadAccept,
  showUploadRemoveIcon,
  sourceTooltip,
  onSourceChange,
  onUpload,
  onUploadRemove,
  customJsonlContent,
}) => {
  const { t } = useI18n();
  const options = allowCustomJsonl
    ? [
        {
          label: t('components.createJobForm.systemDataset'),
          value: 'managed',
        },
        {
          label: t('components.createJobForm.noDataset'),
          value: 'none',
        },
        {
          label: t('components.createJobForm.uploadDataset'),
          value: 'upload',
        },
        {
          label: t('components.createJobForm.customJsonlData'),
          value: 'input',
        },
      ]
    : [
        {
          label: t('components.createJobForm.noDataset'),
          value: 'none',
        },
        {
          label: t('components.createJobForm.systemDataset'),
          value: 'managed',
        },
        {
          label: t('components.createJobForm.uploadDataset'),
          value: 'upload',
        },
      ];

  return (
    <>
      <Form.Item
        name={sourceName}
        label={t('components.createJobForm.datasetSource')}
        tooltip={
          sourceTooltip
            ? { title: sourceTooltip, icon: <ExclamationCircleOutlined /> }
            : undefined
        }
        rules={[
          {
            required: true,
            message: t('components.createJobForm.pleaseSelectDatasetSource'),
          },
        ]}
      >
        <Select
          options={options}
          onChange={(value: TaskDatasetSource) => onSourceChange?.(value)}
        />
      </Form.Item>

      {source !== 'none' && (
        <Form.Item label={t('components.createJobForm.datasetFile')} required>
          {source === 'managed' && (
            <Form.Item
              name={datasetIdName}
              noStyle
              rules={[
                {
                  required: true,
                  message: t('components.createJobForm.pleaseSelectDataset'),
                },
              ]}
            >
              <DatasetSelect datasetType={datasetType} />
            </Form.Item>
          )}

          {source === 'upload' && (
            <>
              {uploadValueName && (
                <Form.Item
                  name={uploadValueName}
                  hidden
                  rules={[
                    {
                      required: uploadValueRequired,
                      message: t(
                        'components.createJobForm.pleaseUploadDatasetFile'
                      ),
                    },
                  ]}
                >
                  <Input />
                </Form.Item>
              )}
              <DatasetUploadBox
                fileName={uploadFileName}
                loading={uploadLoading}
                title={uploadTitle}
                hint={uploadHint}
                accept={uploadAccept}
                onUpload={onUpload}
                onRemove={onUploadRemove}
                showRemoveIcon={showUploadRemoveIcon}
              />
            </>
          )}

          {source === 'input' && customJsonlContent}
        </Form.Item>
      )}
    </>
  );
};

export default TaskDatasetFields;
