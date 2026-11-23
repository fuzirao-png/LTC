export const canAccessMailNotifications = (currentUser) => currentUser?.accountType === 'sales';

export const dedupeMailNotifications = (notifications) => {
  const seen = new Set();
  return notifications.filter((notification) => {
    const messageId = String(notification?.messageId || notification?.notificationTarget?.messageId || '').trim();
    const key = messageId
      ? `message:${messageId}`
      : `notification:${String(notification?.id || '').trim()}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
};

export const removeCompletedReminder = (reminders, completedId) =>
  reminders.filter((reminder) => reminder.id !== completedId);
