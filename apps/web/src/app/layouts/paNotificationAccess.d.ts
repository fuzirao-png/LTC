export declare const canAccessMailNotifications: (
  currentUser: { accountType?: string } | null | undefined,
) => boolean;
export declare const dedupeMailNotifications: <T extends {
  id?: string;
  messageId?: string;
  notificationTarget?: { messageId?: string };
}>(notifications: T[]) => T[];
export declare const removeCompletedReminder: <T extends { id: string }>(
  reminders: T[],
  completedId: string,
) => T[];
