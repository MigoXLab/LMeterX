/**
 * @file Collections.tsx
 * @description Collections list and management page
 */
import {
  CalendarOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  PlusOutlined,
} from '@ant-design/icons';
import {
  Button,
  Card,
  Col,
  Empty,
  Form,
  Input,
  Modal,
  Pagination,
  Row,
  Space,
  Typography,
  message,
} from 'antd';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api } from '../api/apiClient';
import { PageHeader } from '../components/ui/PageHeader';
import { Collection } from '../types/collection';
import { getStoredUser } from '../utils/auth';

const { Text, Paragraph } = Typography;
const { TextArea, Search } = Input;

const Collections: React.FC = () => {
  const { t } = useTranslation();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [loading, setLoading] = useState(false);
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 10,
    total: 0,
  });
  const [search, setSearch] = useState('');
  const currentUser = getStoredUser();

  const fetchCollections = async (
    page = 1,
    pageSize = 10,
    searchKey = search
  ) => {
    setLoading(true);
    try {
      const response = await api.get<{
        data: Collection[];
        pagination: { page: number; page_size: number; total: number };
      }>('/collections', {
        params: {
          page,
          page_size: pageSize,
          search: searchKey || undefined,
        },
      });
      const { data, pagination: paging } = response.data;
      setCollections(data || []);
      setPagination({
        current: paging.page,
        pageSize: paging.page_size,
        total: paging.total,
      });
    } catch (error) {
      const errMsg =
        error instanceof Error
          ? error.message
          : t('pages.collections.loadFailed');
      message.error(errMsg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCollections();
  }, []);

  const handleCreate = async () => {
    try {
      const values = await form.validateFields();
      await api.post('/collections', { ...values, is_public: true });

      message.success(t('pages.collections.createSuccess'));
      setIsModalVisible(false);
      form.resetFields();
      fetchCollections(1, pagination.pageSize);
    } catch (error) {
      const errMsg =
        error instanceof Error
          ? error.message
          : t('pages.collections.createFailed');
      message.error(errMsg);
    }
  };

  const handleDeleteCollection = (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    Modal.confirm({
      title: t('pages.collectionDetail.deleteConfirmTitle'),
      content: t('pages.collectionDetail.deleteConfirmContent'),
      okText: t('common.delete'),
      okType: 'danger',
      cancelText: t('common.cancel'),
      onOk: async () => {
        try {
          await api.delete(`/collections/${id}`);
          message.success(t('pages.collectionDetail.deleteSuccess'));
          fetchCollections(1, pagination.pageSize);
        } catch (error) {
          message.error(t('pages.collectionDetail.deleteFailed'));
        }
      },
    });
  };

  return (
    <div className='page-container'>
      <div className='page-header-wrapper'>
        <PageHeader
          title={t('pages.collections.title') || 'Collections'}
          description={t('pages.collections.description')}
          icon={<FolderOpenOutlined />}
          level={3}
        />
      </div>

      <div className='jobs-content-wrapper' style={{ padding: '0 24px' }}>
        <div className='jobs-toolbar'>
          <div className='jobs-toolbar-left'>
            <Button
              type='primary'
              className='modern-button-primary'
              icon={<PlusOutlined />}
              onClick={() => setIsModalVisible(true)}
              disabled={loading}
            >
              {t('pages.collections.create')}
            </Button>
          </div>
          <div className='jobs-toolbar-right'>
            <Search
              placeholder={t('pages.collections.searchPlaceholder')}
              value={search}
              allowClear
              enterButton
              className='w-300 modern-search'
              onSearch={val => {
                setSearch(val);
                fetchCollections(1, pagination.pageSize, val);
              }}
              onChange={e => setSearch(e.target.value)}
              onClear={() => {
                setSearch('');
                fetchCollections(1, pagination.pageSize, '');
              }}
            />
          </div>
        </div>

        <div style={{ minHeight: 280 }}>
          {collections.length === 0 && !loading ? (
            <Empty description={t('pages.collections.noCollections')} />
          ) : (
            <Row gutter={[16, 16]}>
              {collections.map(collection => (
                <Col key={collection.id} xs={24} sm={12} lg={8} xl={8}>
                  <Link
                    to={`/collections/${collection.id}`}
                    style={{ display: 'block', height: '100%' }}
                  >
                    <Card
                      hoverable
                      bordered={false}
                      loading={loading}
                      style={{
                        height: '100%',
                        borderRadius: 10,
                      }}
                      styles={{
                        body: {
                          padding: 18,
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 10,
                        },
                      }}
                    >
                      <Space
                        align='start'
                        size={12}
                        style={{
                          width: '100%',
                          justifyContent: 'space-between',
                        }}
                      >
                        <Space align='start' size={10}>
                          <div
                            style={{
                              width: 34,
                              height: 34,
                              borderRadius: 8,
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              background:
                                'linear-gradient(135deg, rgba(102,126,234,0.18) 0%, rgba(118,75,162,0.22) 100%)',
                              color: '#4f46e5',
                              flexShrink: 0,
                            }}
                          >
                            <FolderOpenOutlined />
                          </div>
                          <div style={{ minWidth: 0 }}>
                            <Text
                              strong
                              style={{
                                display: 'block',
                                fontSize: 15,
                                color: '#111827',
                              }}
                              ellipsis
                            >
                              {collection.name}
                            </Text>
                            <Text type='secondary' style={{ fontSize: 12 }}>
                              {collection.created_by || '-'}
                            </Text>
                          </div>
                        </Space>
                        <div
                          style={{
                            fontSize: 16,
                            color: '#6b7280',
                            lineHeight: 1,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                          }}
                        >
                          {(currentUser?.is_admin ||
                            collection.created_by ===
                              currentUser?.username) && (
                            <Button
                              type='text'
                              danger
                              size='small'
                              icon={<DeleteOutlined />}
                              onClick={e =>
                                handleDeleteCollection(e, collection.id)
                              }
                              style={{
                                padding: 4,
                                height: 'auto',
                                background: 'transparent',
                              }}
                              title={t('common.delete')}
                            />
                          )}
                        </div>
                      </Space>

                      <Paragraph
                        type='secondary'
                        style={{ fontSize: 13, marginBottom: 0 }}
                        ellipsis={{ rows: 2 }}
                      >
                        {collection.description ||
                          t('pages.collections.noDescription')}
                      </Paragraph>

                      <Space
                        size={10}
                        style={{ color: '#6b7280', fontSize: 12 }}
                      >
                        <CalendarOutlined />
                        <span>
                          {new Date(collection.created_at).toLocaleDateString()}
                        </span>
                      </Space>

                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          marginTop: 'auto',
                          paddingTop: 8,
                          borderTop: '1px solid #f0f0f0',
                        }}
                      >
                        <Text
                          type='secondary'
                          style={{ fontSize: 12, lineHeight: 1 }}
                        >
                          {t('pages.collections.tasks')}:
                        </Text>
                        <Text
                          strong
                          style={{
                            color: '#2563eb',
                            fontSize: 14,
                            lineHeight: 1,
                          }}
                        >
                          {collection.task_count}
                        </Text>
                      </div>
                    </Card>
                  </Link>
                </Col>
              ))}
            </Row>
          )}
        </div>

        {pagination.total > 10 && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'flex-end',
              marginTop: 20,
            }}
          >
            <Pagination
              current={pagination.current}
              pageSize={pagination.pageSize}
              total={pagination.total}
              showSizeChanger
              hideOnSinglePage
              onChange={(page, pageSize) => fetchCollections(page, pageSize)}
            />
          </div>
        )}
      </div>

      <Modal
        title={t('pages.collections.createTitle')}
        open={isModalVisible}
        onOk={handleCreate}
        onCancel={() => setIsModalVisible(false)}
        okText={t('pages.collections.createBtn')}
        cancelText={t('common.cancel')}
      >
        <Form form={form} layout='vertical' initialValues={{ is_public: true }}>
          <Form.Item
            name='name'
            label={t('pages.collections.nameLabel')}
            rules={[
              { required: true, message: t('pages.collections.nameRequired') },
            ]}
          >
            <Input placeholder={t('pages.collections.namePlaceholder')} />
          </Form.Item>

          <Form.Item
            name='description'
            label={t('pages.collections.descLabel')}
          >
            <TextArea
              rows={3}
              placeholder={t('pages.collections.descPlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default Collections;
