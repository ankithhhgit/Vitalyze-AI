export interface LocalDailyReminder {
  id?: string;
  _id?: string;
  medicine_name: string;
  times?: string[];
  is_active?: boolean;
  local_notifications_enabled?: boolean;
  refill_date?: string;
}

export interface NotificationAdapter {
  getPermissionsAsync(): Promise<{ granted?: boolean; status?: string; canAskAgain?: boolean }>;
  requestPermissionsAsync(): Promise<{ granted?: boolean; status?: string; canAskAgain?: boolean }>;
  getAllScheduledNotificationsAsync(): Promise<Array<{ identifier: string; content?: { data?: Record<string, unknown> | null } }>>;
  cancelScheduledNotificationAsync(identifier: string): Promise<void>;
  scheduleNotificationAsync(request: any): Promise<string>;
}

export function ensureNotificationPermission(notifications: NotificationAdapter): Promise<boolean>;
export function reconcileLocalDailySchedule(
  reminders: LocalDailyReminder[],
  notifications: NotificationAdapter,
): Promise<number>;
