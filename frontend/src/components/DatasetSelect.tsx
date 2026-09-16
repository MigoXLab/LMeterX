import { Select } from 'antd';
import React, { useEffect, useState } from 'react';

import { datasetApi } from '@/api/services';
import { useI18n } from '@/hooks/useI18n';
import { Dataset } from '@/types';

export type DatasetType = 'business' | 'llm' | 'a2a' | 'mcp';

interface DatasetSelectProps {
  value?: string;
  onChange?: (value?: string) => void;
  datasetType: DatasetType;
  placeholder?: string;
  disabled?: boolean;
}

const DatasetSelect: React.FC<DatasetSelectProps> = ({
  value,
  onChange,
  datasetType,
  placeholder,
  disabled,
}) => {
  const { t } = useI18n();
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    datasetApi
      .getAllDatasets({ page: 1, page_size: 100, dataset_type: datasetType })
      .then(response => {
        if (active) setDatasets(response.data.data || []);
      })
      .catch(() => {
        if (active) setDatasets([]);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [datasetType]);

  return (
    <Select
      allowClear
      showSearch
      value={value}
      loading={loading}
      disabled={disabled}
      placeholder={
        placeholder || t('components.createJobForm.pleaseSelectDataset')
      }
      optionFilterProp='label'
      onChange={onChange}
      options={datasets.map(dataset => ({
        value: dataset.id,
        label: `${dataset.name} · ${dataset.file_name} · ${dataset.record_count || 0} 条${dataset.tags?.length ? ` · ${dataset.tags.join('/')}` : ''}`,
        title: dataset.description,
      }))}
    />
  );
};

export default DatasetSelect;
