import test from 'node:test';
import assert from 'node:assert/strict';
import {
  ensureNotificationPermission,
  reconcileLocalDailySchedule,
} from './localReminderNotifications.mjs';

test('permission denial prevents a notification grant', async () => {
  let requested = 0;
  const granted = await ensureNotificationPermission({
    getPermissionsAsync: async () => ({ granted: false, status: 'denied', canAskAgain: false }),
    requestPermissionsAsync: async () => { requested += 1; return { granted: false }; },
  });
  assert.equal(granted, false);
  assert.equal(requested, 0);
});

test('reconciliation cancels old app reminders and avoids duplicate schedule entries', async () => {
  const calls = { cancelled: [], scheduled: [] };
  const notifications = {
    getAllScheduledNotificationsAsync: async () => [
      { identifier: 'old-vitalyze', content: { data: { vitalyzeReminder: true } } },
      { identifier: 'other-app', content: { data: { vitalyzeReminder: false } } },
    ],
    cancelScheduledNotificationAsync: async (id) => calls.cancelled.push(id),
    scheduleNotificationAsync: async (request) => {
      calls.scheduled.push(request);
      return `scheduled-${calls.scheduled.length}`;
    },
  };
  const reminders = [
    { id: 'reminder-a', medicine_name: 'Synthetic medicine', times: ['10:00', '14:00', '21:00'] },
    { id: 'reminder-b', medicine_name: 'Disabled medicine', times: ['10:00'], is_active: false },
    { id: 'reminder-c', medicine_name: 'No local notice', times: ['10:00'], local_notifications_enabled: false },
    { id: 'refill-a', medicine_name: 'Synthetic refill', refill_date: new Date(Date.now() + 86_400_000).toISOString() },
  ];

  const count = await reconcileLocalDailySchedule(reminders, notifications);
  assert.equal(count, 4);
  assert.deepEqual(calls.cancelled, ['old-vitalyze']);
  assert.equal(calls.scheduled[0].trigger.hour, 10);
  assert.equal(calls.scheduled[1].trigger.hour, 14);
  assert.equal(calls.scheduled[2].trigger.hour, 21);
  assert.equal(calls.scheduled[3].trigger.type, 'date');
  assert.ok(calls.scheduled.every((item) => item.content.data.vitalyzeReminder));
});

test('repeated reconciliation does not accumulate duplicate notifications', async () => {
  const scheduled = [];
  const notifications = {
    getAllScheduledNotificationsAsync: async () => scheduled.slice(),
    cancelScheduledNotificationAsync: async (id) => {
      const index = scheduled.findIndex((item) => item.identifier === id);
      if (index >= 0) scheduled.splice(index, 1);
    },
    scheduleNotificationAsync: async (request) => {
      const identifier = `scheduled-${scheduled.length + 1}`;
      scheduled.push({ identifier, content: request.content, trigger: request.trigger });
      return identifier;
    },
  };
  const reminders = [{ id: 'reminder-a', medicine_name: 'Synthetic medicine', times: ['10:00', '14:00', '21:00'] }];

  await reconcileLocalDailySchedule(reminders, notifications);
  await reconcileLocalDailySchedule(reminders, notifications);

  assert.equal(scheduled.length, 3);
});
