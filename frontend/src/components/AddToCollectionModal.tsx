import { PlusOutlined } from '@ant-design/icons';
import { App, Divider, Form, Input, Modal, Select, Space, Spin } from 'antd';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/apiClient';
import { Collection } from '../types/collection';
import { getStoredUser } from '../utils/auth';

interface AddToCollectionModalProps {
  open: boolean;
  onCancel: () => void;
  taskIds: string[];
  taskType: 'http' | 'llm';
  onSuccess?: () => void;
}

interface CollectionTaskListItem {
  id: string;
}

const DropdownMenu = ({
  menu,
  searchValue,
  collections,
  onCreateCollection,
  t,
}: {
  menu: React.ReactElement;
  searchValue: string;
  collections: Collection[];
  onCreateCollection: (name: string) => void;
  t: any;
}) => (
  <>
    {menu}
    {searchValue.trim() &&
      !collections.some(
        c => c.name.toLowerCase() === searchValue.trim().toLowerCase()
      ) && (
        <>
          <Divider style={{ margin: '8px 0' }} />
          <Space style={{ padding: '0 8px 4px' }}>
            <div
              style={{
                padding: '4px 8px',
                cursor: 'pointer',
                color: '#1677ff',
                display: 'flex',
                alignItems: 'center',
              }}
              role='button'
              tabIndex={0}
              onMouseDown={e => e.preventDefault()}
              onClick={() => onCreateCollection(searchValue.trim())}
              onKeyDown={e => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onCreateCollection(searchValue.trim());
                }
              }}
            >
              <PlusOutlined style={{ marginRight: 8 }} />
              {t('components.addToCollectionModal.createNew', {
                name: searchValue.trim(),
              })}
            </div>
          </Space>
        </>
      )}
  </>
);

const AddToCollectionModal: React.FC<AddToCollectionModalProps> = ({
  open,
  onCancel,
  taskIds,
  taskType,
  onSuccess,
}) => {
  const { message } = App.useApp();
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [searchValue, setSearchValue] = useState('');
  const currentUser = getStoredUser();
  const hasCollections = collections.length > 0;

  const fetchCollections = async () => {
    setLoading(true);
    try {
      const response = await api.get<{ data: Collection[] }>('/collections', {
        params: { page: 1, page_size: 100 },
      });
      const { data } = response.data;
      const filteredData = (data || []).filter(
        c => currentUser?.is_admin || c.created_by === currentUser?.username
      );
      setCollections(filteredData);
    } catch (error) {
      message.error(t('components.addToCollectionModal.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      fetchCollections();
      form.resetFields();
      setSearchValue('');
    }
  }, [open, form]);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const values = await form.validateFields();
      let collectionId = values.collection_id as string | undefined;

      if (!hasCollections) {
        const response = await api.post<Collection>('/collections', {
          name: values.new_collection_name,
          description: values.new_collection_description || undefined,
        });
        collectionId = response.data.id;
      }

      if (!collectionId) {
        message.error(t('components.addToCollectionModal.selectOrCreate'));
        return;
      }

      let targetTaskIds = taskIds;
      let duplicateTaskCount = 0;

      if (hasCollections) {
        const tasksResponse = await api.get<{ data: CollectionTaskListItem[] }>(
          `/collections/${collectionId}/tasks`
        );
        const existingTaskIds = new Set(
          (tasksResponse.data.data || []).map(item => String(item.id))
        );
        targetTaskIds = taskIds.filter(taskId => !existingTaskIds.has(taskId));
        duplicateTaskCount = taskIds.length - targetTaskIds.length;

        if (duplicateTaskCount > 0) {
          if (targetTaskIds.length === 0) {
            message.warning(
              duplicateTaskCount === 1
                ? t('components.addToCollectionModal.alreadyExistsSingle')
                : t('components.addToCollectionModal.alreadyExistsMultiple', {
                    count: duplicateTaskCount,
                  })
            );
            return;
          }
        }

        if (targetTaskIds.length === 0) {
          return;
        }
      }

      const settledResults = await Promise.allSettled(
        targetTaskIds.map(taskId =>
          api.post(`/collections/${collectionId}/tasks`, {
            task_id: taskId,
            task_type: taskType,
          })
        )
      );
      const addedCount = settledResults.filter(
        result => result.status === 'fulfilled'
      ).length;
      const failedCount = targetTaskIds.length - addedCount;

      if (addedCount > 0) {
        const baseMessage = hasCollections
          ? t('components.addToCollectionModal.addSuccess', {
              count: addedCount,
            })
          : t('components.addToCollectionModal.createAndAddSuccess', {
              count: addedCount,
            });
        if (duplicateTaskCount > 0 || failedCount > 0) {
          const extras = [
            duplicateTaskCount > 0
              ? t('components.addToCollectionModal.skipped', {
                  count: duplicateTaskCount,
                })
              : null,
            failedCount > 0
              ? t('components.addToCollectionModal.failed', {
                  count: failedCount,
                })
              : null,
          ]
            .filter(Boolean)
            .join(', ');
          message.success(`${baseMessage} ${extras}.`);
        } else {
          message.success(baseMessage);
        }
      } else {
        message.warning(t('components.addToCollectionModal.noNewAdded'));
      }

      if (onSuccess) onSuccess();
      onCancel();
    } catch (error) {
      message.error(t('components.addToCollectionModal.addFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateCollection = async (name: string) => {
    setSubmitting(true);
    try {
      const response = await api.post<Collection>('/collections', {
        name,
      });
      const newCollection = response.data;
      setCollections(prev => [newCollection, ...prev]);
      form.setFieldsValue({ collection_id: newCollection.id });
      setSearchValue('');
      message.success(t('collections.createSuccess'));

      // Automatically submit to add tasks to the newly created collection
      await handleSubmit();
    } catch (error) {
      message.error(t('collections.createFailed'));
      setSubmitting(false);
    }
  };

  const renderDropdown = React.useCallback(
    (menu: React.ReactElement) => (
      <DropdownMenu
        menu={menu}
        searchValue={searchValue}
        collections={collections}
        onCreateCollection={handleCreateCollection}
        t={t}
      />
    ),
    [searchValue, collections, handleCreateCollection, t]
  );

  return (
    <Modal
      className='no-footer-border'
      title={t('components.addToCollectionModal.title', {
        count: taskIds.length,
      })}
      open={open}
      onCancel={onCancel}
      onOk={handleSubmit}
      confirmLoading={submitting}
      okText={
        hasCollections
          ? t('components.addToCollectionModal.addBtn')
          : t('components.addToCollectionModal.createAndAddBtn')
      }
      cancelText={t('common.cancel')}
      destroyOnHidden
    >
      <Form form={form} layout='vertical'>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '20px' }}>
            <Spin />
          </div>
        ) : !hasCollections ? (
          <>
            <Form.Item
              name='new_collection_name'
              label={t('components.addToCollectionModal.nameLabel')}
              rules={[
                {
                  required: true,
                  message: t('components.addToCollectionModal.nameRequired'),
                },
              ]}
            >
              <Input
                placeholder={t(
                  'components.addToCollectionModal.namePlaceholder'
                )}
                maxLength={255}
              />
            </Form.Item>
            <Form.Item
              name='new_collection_description'
              label={t('components.addToCollectionModal.descLabel')}
            >
              <Input.TextArea
                rows={3}
                placeholder={t(
                  'components.addToCollectionModal.descPlaceholder'
                )}
                maxLength={2000}
              />
            </Form.Item>
          </>
        ) : (
          <Form.Item
            name='collection_id'
            label={t('components.addToCollectionModal.selectLabel')}
            rules={[
              {
                required: true,
                message: t('components.addToCollectionModal.selectRequired'),
              },
            ]}
          >
            <Select
              showSearch
              searchValue={searchValue}
              onSearch={setSearchValue}
              onSelect={() => setSearchValue('')}
              onBlur={() => setSearchValue('')}
              placeholder={t(
                'components.addToCollectionModal.selectPlaceholder'
              )}
              optionFilterProp='children'
              popupRender={renderDropdown}
            >
              {collections.map(c => (
                <Select.Option key={c.id} value={c.id}>
                  {c.name}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
        )}
      </Form>
    </Modal>
  );
};

export default AddToCollectionModal;
