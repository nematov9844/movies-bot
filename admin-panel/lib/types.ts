export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export type AdminRole = "owner" | "admin" | "moderator";

export interface Movie {
  id: number;
  code: string;
  title: string;
  description: string | null;
  file_id: string;
  quality: string | null;
  duration: number | null;
  file_size: number | null;
  year: number | null;
  is_premium: boolean;
  is_active: boolean;
  view_count: number;
  created_at: string;
  updated_at: string;
}

export interface UserRow {
  id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  language: string;
  is_active: boolean;
  is_blocked: boolean;
  referrer_id: number | null;
  last_seen_at: string | null;
  created_at: string;
}

export interface Channel {
  id: number;
  channel_id: number;
  username: string | null;
  title: string;
  invite_link: string | null;
  priority: number;
  is_active: boolean;
  is_required: boolean;
  start_date: string | null;
  expire_date: string | null;
  daily_start_time: string | null;
  daily_end_time: string | null;
  join_limit: number | null;
  current_joins: number;
  created_at: string;
}

export interface PremiumPlan {
  id: number;
  name: string;
  days: number;
  price: number;
  is_active: boolean;
}

export interface PremiumUserRow {
  id: number;
  user_id: number;
  username: string | null;
  plan_id: number;
  plan_name: string;
  starts_at: string;
  expires_at: string;
  payment_method: string | null;
}

export interface Broadcast {
  id: number;
  admin_id: number;
  target: string;
  status: string;
  total: number;
  sent: number;
  failed: number;
  blocked: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface Setting {
  key: string;
  value: string;
  type: string;
  description: string | null;
  updated_at: string;
}

export interface DashboardSummary {
  total_users: number;
  new_users_today: number;
  total_movies: number;
  active_premium_count: number;
  premium_conversion_percent: number;
}

export interface DailyPoint {
  date: string;
  new_users: number;
  active_users: number;
  movies_sent: number;
}

export interface DashboardResponse {
  summary: DashboardSummary;
  daily: DailyPoint[];
}

export interface AuditLog {
  id: number;
  admin_id: number | null;
  action: string;
  entity: string;
  entity_id: string | null;
  payload: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

export interface Admin {
  id: number;
  user_id: number;
  role: AdminRole;
  is_active: boolean;
  created_at: string;
}

export interface Series {
  id: number;
  title: string;
  description: string | null;
  is_active: boolean;
}

export interface Season {
  id: number;
  series_id: number;
  number: number;
  is_active: boolean;
  episode_count: number;
}

export interface SeriesWithSeasons extends Series {
  seasons: Season[];
}
