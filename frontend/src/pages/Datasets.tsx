import {
  DatabaseOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {
  Button,
  Form,
  Input,
  Modal,
  Progress,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from 'antd';
import type { TablePaginationConfig, UploadFile } from 'antd';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { datasetApi } from '@/api/services';
import { PageHeader } from '@/components/ui/PageHeader';
import { Dataset } from '@/types';

const { Text } = Typography;
const { Search, TextArea } = Input;

const wrapDisabledAction = (
  enabled: boolean,
  disabledReason: string,
  button: React.ReactElement
) =>
  enabled ? (
    button
  ) : (
    <Tooltip title={disabledReason}>
      <span>{button}</span>
    </Tooltip>
  );

const Datasets: React.FC = () => {
  const { t } = useTranslation();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<Dataset | null>(null);
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [search, setSearch] = useState('');
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 20,
    total: 0,
  });
  const [form] = Form.useForm();
  const savingRef = useRef(false);
  const selectedType = Form.useWatch('dataset_type', form);

  const typeOptions = useMemo(
    () => [
      { value: 'business', label: t('pages.datasets.typeBusiness') },
      { value: 'llm', label: t('pages.datasets.typeLlm') },
      { value: 'a2a', label: t('pages.datasets.typeA2a') },
      { value: 'mcp', label: t('pages.datasets.typeMcp') },
    ],
    [t]
  );

  const load = async (
    page = pagination.current,
    keyword = search,
    pageSize = pagination.pageSize
  ) => {
    setLoading(true);
    try {
      const response = await datasetApi.getAllDatasets({
        page,
        page_size: pageSize,
        search: keyword || undefined,
      });
      setDatasets(response.data.data || []);
      setPagination(current => ({
        ...current,
        current: response.data.pagination.page,
        pageSize: response.data.pagination.page_size || pageSize,
        total: response.data.pagination.total,
      }));
    } catch {
      message.error(t('pages.datasets.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleTableChange = (nextPagination: TablePaginationConfig) => {
    const nextPage = nextPagination.current || 1;
    const nextPageSize = nextPagination.pageSize || pagination.pageSize;
    setPagination(current => ({
      ...current,
      current: nextPage,
      pageSize: nextPageSize,
    }));
    load(nextPage, search, nextPageSize);
  };

  useEffect(() => {
    load(1, '');
  }, []);

  const showCreate = () => {
    setEditing(null);
    setFileList([]);
    setUploadProgress(null);
    form.resetFields();
    form.setFieldsValue({
      is_public: false,
      dataset_type: undefined,
      tags: [],
    });
    setOpen(true);
  };

  const showEdit = (dataset: Dataset) => {
    setEditing(dataset);
    setFileList([]);
    setUploadProgress(null);
    form.setFieldsValue({
      name: dataset.name,
      description: dataset.description,
      is_public: dataset.is_public,
      dataset_type: dataset.dataset_types?.[0],
      tags: dataset.tags,
    });
    setOpen(true);
  };

  const save = async () => {
    const values = await form.validateFields();
    const datasetTypes = [values.dataset_type];
    const file = editing ? null : fileList[0]?.originFileObj;

    if (!editing && !file) {
      message.error(t('pages.datasets.selectJsonl'));
      return;
    }

    // React state updates are asynchronous, so use a ref as a synchronous guard
    // against rapid double-clicks starting multiple large uploads.
    if (savingRef.current) {
      return;
    }
    savingRef.current = true;
    setSaving(true);
    setUploadProgress(editing ? null : 0);

    try {
      if (editing) {
        await datasetApi.updateDataset(editing.id, {
          name: values.name,
          description: values.description,
          is_public: values.is_public,
          dataset_types: datasetTypes,
          tags: values.tags || [],
        });
      } else {
        const data = new FormData();
        data.append('name', values.name);
        data.append('description', values.description || '');
        data.append('is_public', String(Boolean(values.is_public)));
        data.append('dataset_types', JSON.stringify(datasetTypes));
        data.append('tags', JSON.stringify(values.tags || []));
        data.append('file', file);
        await datasetApi.createDataset(data, ({ loaded, total }) => {
          if (total) {
            setUploadProgress(
              Math.min(100, Math.round((loaded / total) * 100))
            );
          }
        });
      }
      message.success(
        editing
          ? t('pages.datasets.updateSuccess')
          : t('pages.datasets.uploadSuccess')
      );
      setOpen(false);
      await load(1);
    } catch (error: any) {
      message.error(
        error?.data?.message || t('pages.datasets.operationFailed')
      );
    } finally {
      savingRef.current = false;
      setSaving(false);
      setUploadProgress(null);
    }
  };

  const remove = (dataset: Dataset) => {
    Modal.confirm({
      title: t('pages.datasets.deleteTitle'),
      content: t('pages.datasets.deleteConfirm', { name: dataset.name }),
      okText: t('common.delete'),
      cancelText: t('common.cancel'),
      okType: 'danger',
      onOk: async () => {
        await datasetApi.deleteDataset(dataset.id);
        message.success(t('pages.datasets.deleteSuccess'));
        await load();
      },
    });
  };

  const download = async (dataset: Dataset) => {
    try {
      const blob = await datasetApi.downloadDataset(dataset.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = dataset.file_name;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      message.error(t('pages.datasets.downloadFailed'));
    }
  };

  return (
    <div className='page-container'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={t('pages.datasets.title')}
          description={t('pages.datasets.description')}
          icon={<DatabaseOutlined />}
          level={3}
        />
      </div>

      <div className='jobs-content-wrapper'>
        <div className='jobs-toolbar'>
          <div className='jobs-toolbar-left'>
            <Button
              type='primary'
              className='modern-button-primary'
              icon={<PlusOutlined />}
              onClick={showCreate}
            >
              {t('pages.datasets.upload')}
            </Button>
          </div>
          <div className='jobs-toolbar-right'>
            <Search
              allowClear
              enterButton
              placeholder={t('pages.datasets.searchPlaceholder')}
              className='w-300 modern-search'
              onSearch={value => {
                setSearch(value);
                load(1, value);
              }}
            />
          </div>
        </div>
        <Table
          rowKey='id'
          loading={loading}
          dataSource={datasets}
          pagination={pagination}
          onChange={handleTableChange}
          className='modern-table unified-table'
          columns={[
            { title: t('pages.datasets.columnName'), dataIndex: 'name' },
            {
              title: t('pages.datasets.columnFile'),
              dataIndex: 'file_name',
              ellipsis: true,
            },
            {
              title: t('pages.datasets.columnType'),
              dataIndex: 'dataset_types',
              render: (types: string[]) => (
                <Space size={[0, 4]} wrap>
                  {types.map(type => (
                    <Tag key={type}>
                      {typeOptions.find(item => item.value === type)?.label ||
                        type}
                    </Tag>
                  ))}
                </Space>
              ),
            },
            {
              title: t('pages.datasets.columnRecordCount'),
              dataIndex: 'record_count',
            },
            {
              title: t('pages.datasets.columnTags'),
              dataIndex: 'tags',
              render: (tags: string[]) => (
                <Space size={[0, 4]} wrap>
                  {(tags || []).map(tag => (
                    <Tag color='blue' key={tag}>
                      {tag}
                    </Tag>
                  ))}
                </Space>
              ),
            },
            {
              title: t('pages.datasets.columnCreator'),
              dataIndex: 'created_by',
              render: (value: string, dataset: Dataset) =>
                dataset.is_system || !value ? '-' : value,
            },
            {
              title: t('pages.datasets.columnStatus'),
              dataIndex: 'is_public',
              render: (value: boolean) => (
                <Tag color={value ? 'green' : 'default'}>
                  {value
                    ? t('pages.datasets.public')
                    : t('pages.datasets.private')}
                </Tag>
              ),
            },
            {
              title: t('pages.datasets.columnAction'),
              render: (_: unknown, dataset: Dataset) => {
                const disabledReason = dataset.is_system
                  ? t('pages.datasets.systemDatasetActionDisabled')
                  : t('pages.datasets.ownerOnlyActionDisabled');

                return (
                  <Space>
                    {wrapDisabledAction(
                      dataset.can_download,
                      disabledReason,
                      <Button
                        type='link'
                        icon={<DownloadOutlined />}
                        disabled={!dataset.can_download}
                        onClick={() => download(dataset)}
                      >
                        {t('pages.datasets.download')}
                      </Button>
                    )}
                    {wrapDisabledAction(
                      dataset.can_manage,
                      disabledReason,
                      <Button
                        type='link'
                        icon={<EditOutlined />}
                        disabled={!dataset.can_manage}
                        onClick={() => showEdit(dataset)}
                      >
                        {t('pages.datasets.edit')}
                      </Button>
                    )}
                    {wrapDisabledAction(
                      dataset.can_manage,
                      disabledReason,
                      <Button
                        danger
                        type='link'
                        icon={<DeleteOutlined />}
                        disabled={!dataset.can_manage}
                        onClick={() => remove(dataset)}
                      >
                        {t('pages.datasets.delete')}
                      </Button>
                    )}
                  </Space>
                );
              },
            },
          ]}
        />
      </div>

      <Modal
        title={
          editing
            ? t('pages.datasets.editTitle')
            : t('pages.datasets.uploadTitle')
        }
        open={open}
        onCancel={() => {
          if (!savingRef.current) {
            setOpen(false);
          }
        }}
        onOk={save}
        okText={t('common.confirm')}
        cancelText={t('common.cancel')}
        confirmLoading={saving}
        cancelButtonProps={{ disabled: saving }}
        closable={!saving}
        maskClosable={!saving}
        width={640}
      >
        <Form form={form} layout='vertical' disabled={saving}>
          <Form.Item
            name='name'
            label={t('pages.datasets.nameLabel')}
            rules={[
              { required: true, message: t('pages.datasets.nameRequired') },
            ]}
          >
            <Input maxLength={255} />
          </Form.Item>
          <Form.Item name='description' label={t('pages.datasets.descLabel')}>
            <TextArea rows={3} maxLength={2000} />
          </Form.Item>
          <Form.Item
            name='dataset_type'
            label={t('pages.datasets.typesLabel')}
            rules={[
              {
                required: true,
                message: t('pages.datasets.typesRequired'),
              },
            ]}
          >
            <Select
              options={typeOptions}
              placeholder={t('pages.datasets.typesPlaceholder')}
            />
          </Form.Item>
          <Form.Item
            name='is_public'
            label={t('pages.datasets.visibilityLabel')}
            valuePropName='checked'
          >
            <Switch
              checkedChildren={t('pages.datasets.public')}
              unCheckedChildren={t('pages.datasets.private')}
            />
          </Form.Item>
          <Form.Item name='tags' label={t('pages.datasets.tagsLabel')}>
            <Select
              mode='tags'
              maxCount={10}
              tokenSeparators={[',', '，']}
              placeholder={t('pages.datasets.tagsPlaceholder')}
            />
          </Form.Item>
          {!editing && (
            <Form.Item label={t('pages.datasets.fileLabel')} required>
              <Upload.Dragger
                accept='.jsonl,application/jsonl'
                maxCount={1}
                beforeUpload={() => false}
                fileList={fileList}
                onChange={({ fileList: next }) => setFileList(next.slice(-1))}
              >
                <p className='ant-upload-drag-icon'>
                  <UploadOutlined />
                </p>
                <Text>{t('pages.datasets.fileHint')}</Text>
                {selectedType && (
                  <div style={{ marginTop: 12, whiteSpace: 'pre-line' }}>
                    <Text type='secondary' style={{ fontSize: 12 }}>
                      {t(`pages.datasets.fileFormat.${selectedType}`)}
                    </Text>
                  </div>
                )}
              </Upload.Dragger>
            </Form.Item>
          )}
          {!editing && saving && uploadProgress !== null && (
            <div style={{ marginBottom: 16 }}>
              <Progress percent={uploadProgress} status='active' />
              <Text type='secondary'>
                {uploadProgress < 100
                  ? t('pages.datasets.uploadingProgress', {
                      progress: uploadProgress,
                    })
                  : t('pages.datasets.processingFile')}
              </Text>
            </div>
          )}
        </Form>
      </Modal>
    </div>
  );
};

export default Datasets;
