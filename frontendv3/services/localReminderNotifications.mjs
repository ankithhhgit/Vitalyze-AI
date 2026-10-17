export async function ensureNotificationPermission(notifications) {
  let permission = await notifications.getPermissionsAsync();
  if (!permission.granted && permission.status !== 'granted' && permission.canAskAgain !== false) {
    permission = await notifications.requestPermissionsAsync();
  }
  return permission.granted || permission.status === 'granted';
}

export async function reconcileLocalDailySchedule(reminders, notifications) {
  const scheduled = await notifications.getAllScheduledNotificationsAsync();
  const ours = scheduled.filter((item) => item.content?.data?.vitalyzeReminder === true);
  for (const item of ours) {
    await notifications.cancelScheduledNotificationAsync(item.identifier);
  }

  let created = 0;
  for (const reminder of reminders) {
    if (reminder.is_active === false || reminder.local_notifications_enabled === false) continue;
    const reminderId = String(reminder.id ?? reminder._id ?? '');
    if (reminder.refill_date) {
      const date = new Date(reminder.refill_date);
      if (reminderId && Number.isFinite(date.getTime()) && date.getTime() > Date.now()) {
        await notifications.scheduleNotificationAsync({
          content: {
            title: 'Refill reminder',
            body: `Your refill reminder for ${reminder.medicine_name}.`,
            data: { vitalyzeReminder: true, reminderId, kind: 'refill' },
          },
          trigger: { type: 'date', date },
        });
        created += 1;
      }
      continue;
    }
    for (const clockTime of reminder.times ?? []) {
      const match = /^(\d{2}):(\d{2})$/.exec(clockTime);
      if (!reminderId || !match) continue;
      await notifications.scheduleNotificationAsync({
        content: {
          title: 'Medicine reminder',
          body: `Time for ${reminder.medicine_name}.`,
          data: { vitalyzeReminder: true, reminderId, time: clockTime },
        },
        trigger: {
          type: 'daily',
          hour: Number(match[1]),
          minute: Number(match[2]),
        },
      });
      created += 1;
    }
  }
  return created;
}
