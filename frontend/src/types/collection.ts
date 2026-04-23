export interface Collection {
  id: string;
  name: string;
  description?: string;
  rich_content?: string;
  created_by?: string;
  is_public: boolean;
  created_at: string;
  updated_at: string;
  task_count: number;
}

export interface CollectionTaskItem {
  id: string;
  name: string;
  status: string;
  task_type: 'http' | 'llm';
  created_by?: string;
  created_at: string;
  concurrent_users: number;
  duration: number;
  model?: string;
  api_type?: string;
}
