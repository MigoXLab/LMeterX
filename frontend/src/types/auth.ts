export interface UserInfo {
  username: string;
  display_name?: string | null;
  email?: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserInfo;
}
