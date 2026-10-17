import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { formatApiError } from '../services/api';
import * as Notifications from 'expo-notifications';
import { ensureNotificationPermission, reconcileLocalDailySchedule } from '../services/localReminderNotifications.mjs';
import { COLORS, SIZES, moderateScale } from '../constants/theme';

type TabType = 'daily' | 'refill';
type TimingType = '10:00' | '14:00' | '21:00';
const DAILY_TIMES: TimingType[] = ['10:00', '14:00', '21:00'];
interface SavedReminder {
  id?: string;
  _id?: string;
  medicine_name: string;
  times?: TimingType[];
  timezone?: string;
  local_notifications_enabled?: boolean;
  whatsapp_opt_in?: boolean;
  is_active?: boolean;
  refill_date?: string;
  kind?: 'Daily' | 'Refill';
}

export default function RemindersScreen() {
  const [activeTab, setActiveTab] = useState<TabType>('daily');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');
  const [msgType, setMsgType] = useState<'success' | 'error'>('success');
  const [savedReminders, setSavedReminders] = useState<SavedReminder[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [deliveryMessage, setDeliveryMessage] = useState('WhatsApp delivery is disabled; saved reminders are not sent.');
  const [notificationState, setNotificationState] = useState('Permission not requested');
  const [selectedTimes, setSelectedTimes] = useState<TimingType[]>([...DAILY_TIMES]);
  const [localNotificationsEnabled, setLocalNotificationsEnabled] = useState(true);
  const [whatsappOptIn, setWhatsappOptIn] = useState(false);

  const loadReminders = async () => {
    setListLoading(true);
    let dailyReminders: SavedReminder[] = [];
    let refillReminders: SavedReminder[] = [];
    try {
      const response = await api.get('/reminders');
      dailyReminders = response.data.daily_reminders || [];
      refillReminders = response.data.refill_reminders || [];
      setSavedReminders([
        ...dailyReminders.map((item) => ({ ...item, kind: 'Daily' as const })),
        ...refillReminders.map((item) => ({ ...item, kind: 'Refill' as const })),
      ]);
    } catch (err) {
      setMsg(formatApiError(err, 'Could not load your saved reminders.'));
      setMsgType('error');
      setListLoading(false);
      return;
    }
    try {
      const status = await api.get('/reminders/status');
      setDeliveryMessage(status.data.message || 'WhatsApp delivery is not configured.');
    } catch {
      setDeliveryMessage('WhatsApp delivery status is unavailable. Saving a reminder does not confirm delivery.');
    }
    try {
      const permission = await Notifications.getPermissionsAsync();
      const allowed = permission.granted || permission.status === 'granted';
      setNotificationState(allowed ? 'Permission granted' : permission.status === 'denied' ? 'Permission denied' : 'Permission not requested');
      const count = await reconcileLocalDailySchedule(
        allowed ? [...dailyReminders, ...refillReminders] : [],
        Notifications,
      );
      if (allowed) {
        setNotificationState(`Scheduled ${count} local notification${count === 1 ? '' : 's'}`);
      }
    } catch {
      setNotificationState('Local notification scheduling failed');
      setMsg('Reminders loaded, but local notification synchronization failed. Review notification permission and try again.');
      setMsgType('error');
    } finally {
      setListLoading(false);
    }
  };

  useEffect(() => { loadReminders(); }, []);

  // Daily Reminder State
  const [dailyForm, setDailyForm] = useState({
    medicine_name: '',
  });

  // Refill Reminder State
  const [refillForm, setRefillForm] = useState({
    medicine_name: '',
    initial_quantity: '10',
    frequency_per_day: '1',
  });

  const handleTimingChange = (time: TimingType) => {
    setSelectedTimes((previous) => previous.includes(time)
      ? previous.filter((item) => item !== time)
      : [...previous, time].sort());
  };

  const handleDailySubmit = async () => {
    setLoading(true);
    setMsg('');

    if (!dailyForm.medicine_name.trim() || selectedTimes.length === 0) {
      setMsg('Please fill medicine name and select at least one timing.');
      setMsgType('error');
      setLoading(false);
      return;
    }

    try {
      let permissionGranted = true;
      if (localNotificationsEnabled) {
        permissionGranted = await ensureNotificationPermission(Notifications);
        setNotificationState(permissionGranted ? 'Permission granted' : 'Permission denied');
      }
      await api.post('/reminders/daily', {
        ...dailyForm,
        medicine_name: dailyForm.medicine_name.trim(),
        timings: [],
        times: selectedTimes,
        timezone: 'Asia/Kolkata',
        local_notifications_enabled: localNotificationsEnabled,
        whatsapp_opt_in: whatsappOptIn,
      });
      setMsgType('success');
      await loadReminders();
      setMsg(permissionGranted || !localNotificationsEnabled
        ? 'Reminder preferences saved. Local schedule reconciled; WhatsApp delivery is not confirmed.'
        : 'Reminder saved. Local notifications are not scheduled because permission was denied; enable them in iPhone Settings. WhatsApp was not sent.');
      setDailyForm({ medicine_name: '' });
      setSelectedTimes([...DAILY_TIMES]);
      setWhatsappOptIn(false);
    } catch (err: any) {
      const errorDetail = formatApiError(err, 'Failed to set reminder. Please try again.');
      setMsg(errorDetail);
      setMsgType('error');
    } finally {
      setLoading(false);
    }
  };

  const handleRefillSubmit = async () => {
    setLoading(true);
    setMsg('');

    const initialQuantity = Number(refillForm.initial_quantity);
    const frequencyPerDay = Number(refillForm.frequency_per_day);
    if (!refillForm.medicine_name.trim() || !Number.isInteger(initialQuantity) || initialQuantity <= 0 || !Number.isInteger(frequencyPerDay) || frequencyPerDay <= 0) {
      setMsg('Enter a medicine name and positive whole-number quantities.');
      setMsgType('error');
      setLoading(false);
      return;
    }

    try {
      const payload = {
        medicine_name: refillForm.medicine_name.trim(),
        initial_quantity: initialQuantity,
        frequency_per_day: frequencyPerDay,
        whatsapp_opt_in: whatsappOptIn,
        local_notifications_enabled: localNotificationsEnabled,
      };

      let permissionGranted = true;
      if (localNotificationsEnabled) {
        permissionGranted = await ensureNotificationPermission(Notifications);
        setNotificationState(permissionGranted ? 'Permission granted' : 'Permission denied');
      }
      const response = await api.post('/reminders/refill', payload);
      const dateStr = response.data.refill_date
        ? new Date(response.data.refill_date).toLocaleDateString()
        : 'soon';

      setMsg(permissionGranted || !localNotificationsEnabled
        ? `Refill reminder saved for ${dateStr}. Local schedule synchronized; WhatsApp delivery is not confirmed.`
        : `Refill reminder saved for ${dateStr}. Local notification permission was denied; enable it in device settings. WhatsApp was not sent.`);
      setMsgType('success');
      setRefillForm({ medicine_name: '', initial_quantity: '10', frequency_per_day: '1' });
      setWhatsappOptIn(false);
      await loadReminders();
    } catch (err: any) {
      const errorDetail = formatApiError(err, 'Failed to set refill reminder. Please try again.');
      setMsg(errorDetail);
      setMsgType('error');
    } finally {
      setLoading(false);
    }
  };

  const updateSavedReminder = async (reminder: SavedReminder, values: Partial<SavedReminder>) => {
    const id = reminder.id ?? reminder._id;
    if (!id) return;
    try {
      if (reminder.kind === 'Refill') {
        await api.patch(`/reminders/refill/${id}`, {
          local_notifications_enabled: values.local_notifications_enabled ?? reminder.local_notifications_enabled ?? true,
          whatsapp_opt_in: values.whatsapp_opt_in ?? reminder.whatsapp_opt_in ?? false,
          is_active: values.is_active ?? reminder.is_active ?? true,
        });
      } else {
        await api.patch(`/reminders/daily/${id}`, {
          times: values.times ?? reminder.times ?? [],
          timezone: values.timezone ?? reminder.timezone ?? 'Asia/Kolkata',
          local_notifications_enabled: values.local_notifications_enabled ?? reminder.local_notifications_enabled ?? true,
          whatsapp_opt_in: values.whatsapp_opt_in ?? reminder.whatsapp_opt_in ?? false,
          is_active: values.is_active ?? reminder.is_active ?? true,
        });
      }
      setMsg('Reminder preferences saved. WhatsApp delivery is not confirmed.');
      setMsgType('success');
      await loadReminders();
    } catch (err) {
      setMsg(formatApiError(err, 'Could not update reminder preferences.'));
      setMsgType('error');
    }
  };

  const deleteSavedReminder = async (reminder: SavedReminder) => {
    const id = reminder.id ?? reminder._id;
    if (!id) return;
    try {
      await api.delete(`/reminders/${reminder.kind === 'Refill' ? 'refill' : 'daily'}/${id}`);
      setMsg('Reminder deleted. Its local notifications were removed during schedule sync.');
      setMsgType('success');
      await loadReminders();
    } catch (err) {
      setMsg(formatApiError(err, 'Could not delete reminder.'));
      setMsgType('error');
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Medicine Reminders</Text>

        {/* Tabs */}
        <View style={styles.tabsContainer}>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'daily' && styles.activeTab]}
            onPress={() => setActiveTab('daily')}
          >
            <Ionicons
              name="time-outline"
              size={18}
              color={activeTab === 'daily' ? COLORS.white : COLORS.primary}
            />
            <Text style={[styles.tabText, activeTab === 'daily' && styles.activeTabText]}>
              Daily Intake
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'refill' && styles.activeTab]}
            onPress={() => setActiveTab('refill')}
          >
            <Ionicons
              name="refresh-outline"
              size={18}
              color={activeTab === 'refill' ? COLORS.white : COLORS.primary}
            />
            <Text style={[styles.tabText, activeTab === 'refill' && styles.activeTabText]}>
              Refill Tracker
            </Text>
          </TouchableOpacity>
        </View>

        {/* Status Message */}
        {msg ? (
          <View style={[styles.msgContainer, msgType === 'error' ? styles.errorBg : styles.successBg]}>
            <Ionicons
              name={msgType === 'error' ? 'close-circle' : 'checkmark-circle'}
              size={20}
              color={msgType === 'error' ? COLORS.error : COLORS.success}
            />
            <Text style={[styles.msgText, msgType === 'error' ? styles.errorText : styles.successText]}>
              {msg}
            </Text>
          </View>
        ) : null}

        <View style={styles.formCard}>
          <Text style={styles.label}>Saved reminders</Text>
          <Text style={styles.helperText}>{deliveryMessage}</Text>
          <Text style={styles.helperText}>Local notification status: {notificationState}</Text>
          {notificationState === 'Permission denied' && (
            <TouchableOpacity onPress={() => Linking.openSettings()}>
              <Text style={styles.linkText}>Open device settings</Text>
            </TouchableOpacity>
          )}
          {listLoading ? <ActivityIndicator color={COLORS.primary} /> : savedReminders.length === 0 ? (
            <Text style={styles.emptyText}>No reminders saved yet.</Text>
          ) : savedReminders.map((reminder, index) => {
            const isDaily = reminder.kind === 'Daily';
            const times = reminder.times || [];
            return (
              <View key={reminder.id ?? reminder._id ?? `${reminder.medicine_name}-${index}`} style={styles.savedReminder}>
                <Text style={styles.savedReminderText}>
                  {reminder.kind || 'Reminder'} · {reminder.medicine_name}
                  {isDaily ? ` · ${times.join(', ') || 'no times enabled'} · ${reminder.timezone || 'Asia/Kolkata'}` : ''}
                  {reminder.refill_date ? ` · refill ${new Date(reminder.refill_date).toLocaleDateString()}` : ''}
                </Text>
                {isDaily && (
                  <>
                    <View style={styles.checkboxGroup}>
                      {DAILY_TIMES.map((time) => (
                        <TouchableOpacity
                          key={time}
                          accessibilityRole="checkbox"
                          accessibilityState={{ checked: times.includes(time) }}
                          style={styles.checkbox}
                          onPress={() => updateSavedReminder(reminder, {
                            times: times.includes(time) ? times.filter((item) => item !== time) : [...times, time].sort(),
                          })}
                        >
                          <Ionicons name={times.includes(time) ? 'checkbox' : 'square-outline'} size={20} color={COLORS.primary} />
                          <Text style={styles.checkboxLabel}>{time}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </>
                )}
                <View style={styles.manageRow}>
                  <TouchableOpacity onPress={() => updateSavedReminder(reminder, { is_active: reminder.is_active === false })}>
                    <Text style={styles.linkText}>{reminder.is_active === false ? 'Enable' : 'Disable'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => updateSavedReminder(reminder, { local_notifications_enabled: !reminder.local_notifications_enabled })}>
                    <Text style={styles.linkText}>{reminder.local_notifications_enabled === false ? 'Enable local alerts' : 'Disable local alerts'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => updateSavedReminder(reminder, { whatsapp_opt_in: !reminder.whatsapp_opt_in })}>
                    <Text style={styles.linkText}>{reminder.whatsapp_opt_in ? 'Revoke WhatsApp consent' : 'Opt in to WhatsApp'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => deleteSavedReminder(reminder)}>
                    <Text style={styles.dangerText}>Delete</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })}
        </View>

        {/* Daily Form */}
        {activeTab === 'daily' && (
          <View style={styles.formCard}>
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Medicine Name</Text>
              <TextInput
                style={styles.input}
                placeholder="e.g., Paracetamol"
                placeholderTextColor={COLORS.textMuted}
                value={dailyForm.medicine_name}
                onChangeText={(text) => setDailyForm({ ...dailyForm, medicine_name: text })}
              />
            </View>

            <View style={styles.inputGroup}>
              <Text style={styles.label}>Daily times · Asia/Kolkata</Text>
              <View style={styles.checkboxGroup}>
                {DAILY_TIMES.map((timing) => (
                  <TouchableOpacity
                    key={timing}
                    style={[
                      styles.checkbox,
                      selectedTimes.includes(timing) && styles.checkboxSelected,
                    ]}
                    onPress={() => handleTimingChange(timing)}
                  >
                    <Ionicons
                      name={selectedTimes.includes(timing) ? 'checkbox' : 'square-outline'}
                      size={22}
                      color={selectedTimes.includes(timing) ? COLORS.primary : COLORS.textSecondary}
                    />
                    <Text style={[styles.checkboxLabel, selectedTimes.includes(timing) && styles.checkboxLabelSelected]}>{timing}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>

            <TouchableOpacity style={styles.preferenceRow} onPress={async () => {
              if (localNotificationsEnabled) {
                setLocalNotificationsEnabled(false);
                return;
              }
              const granted = await ensureNotificationPermission(Notifications);
              setNotificationState(granted ? 'Permission granted' : 'Permission denied');
              if (granted) setLocalNotificationsEnabled(true);
              else setMsg('Notification permission was denied. Enable it in device settings to use local reminders.');
            }}>
              <Ionicons name={localNotificationsEnabled ? 'checkbox' : 'square-outline'} size={22} color={COLORS.primary} />
              <Text style={styles.checkboxLabel}>Use local notification fallback</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.preferenceRow} onPress={() => setWhatsappOptIn((value) => !value)}>
              <Ionicons name={whatsappOptIn ? 'checkbox' : 'square-outline'} size={22} color={COLORS.primary} />
              <Text style={styles.checkboxLabel}>I explicitly opt in to WhatsApp reminders to my account phone</Text>
            </TouchableOpacity>
            <Text style={styles.helperText}>WhatsApp stays disabled until the server, approved template, phone verification, and consent are ready.</Text>

            <TouchableOpacity
              style={[styles.submitButton, loading && styles.buttonDisabled]}
              onPress={handleDailySubmit}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={COLORS.white} />
              ) : (
                <>
                  <Ionicons name="alarm-outline" size={20} color={COLORS.white} />
                  <Text style={styles.submitButtonText}>Set Daily Reminder</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        )}

        {/* Refill Form */}
        {activeTab === 'refill' && (
          <View style={styles.formCard}>
            <TouchableOpacity style={styles.preferenceRow} onPress={async () => {
              if (localNotificationsEnabled) {
                setLocalNotificationsEnabled(false);
                return;
              }
              const granted = await ensureNotificationPermission(Notifications);
              setNotificationState(granted ? 'Permission granted' : 'Permission denied');
              if (granted) setLocalNotificationsEnabled(true);
              else setMsg('Notification permission was denied. Enable it in device settings to use local reminders.');
            }}>
              <Ionicons name={localNotificationsEnabled ? 'checkbox' : 'square-outline'} size={22} color={COLORS.primary} />
              <Text style={styles.checkboxLabel}>Use local notification fallback</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.preferenceRow} onPress={() => setWhatsappOptIn((value) => !value)}>
              <Ionicons name={whatsappOptIn ? 'checkbox' : 'square-outline'} size={22} color={COLORS.primary} />
              <Text style={styles.checkboxLabel}>I explicitly opt in to WhatsApp refill reminders</Text>
            </TouchableOpacity>
            <View style={styles.inputGroup}>
              <Text style={styles.label}>Medicine Name</Text>
              <TextInput
                style={styles.input}
                placeholder="e.g., Metformin"
                placeholderTextColor={COLORS.textMuted}
                value={refillForm.medicine_name}
                onChangeText={(text) => setRefillForm({ ...refillForm, medicine_name: text })}
              />
            </View>

            <View style={styles.row}>
              <View style={[styles.inputGroup, { flex: 1, marginRight: 8 }]}>
                <Text style={styles.label}>Current Quantity</Text>
                <TextInput
                  style={styles.input}
                  placeholder="10"
                  placeholderTextColor={COLORS.textMuted}
                  value={refillForm.initial_quantity}
                  onChangeText={(text) => setRefillForm({ ...refillForm, initial_quantity: text })}
                  keyboardType="numeric"
                />
              </View>
              <View style={[styles.inputGroup, { flex: 1, marginLeft: 8 }]}>
                <Text style={styles.label}>Daily Frequency</Text>
                <TextInput
                  style={styles.input}
                  placeholder="1"
                  placeholderTextColor={COLORS.textMuted}
                  value={refillForm.frequency_per_day}
                  onChangeText={(text) => setRefillForm({ ...refillForm, frequency_per_day: text })}
                  keyboardType="numeric"
                />
              </View>
            </View>

            <TouchableOpacity
              style={[styles.submitButton, loading && styles.buttonDisabled]}
              onPress={handleRefillSubmit}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator color={COLORS.white} />
              ) : (
                <>
                  <Ionicons name="calculator-outline" size={20} color={COLORS.white} />
                  <Text style={styles.submitButtonText}>Set Refill Reminder</Text>
                </>
              )}
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  scrollContent: {
    padding: moderateScale(SIZES.padding),
  },
  title: {
    fontSize: moderateScale(SIZES.h2),
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: moderateScale(20),
  },
  tabsContainer: {
    flexDirection: 'row',
    gap: moderateScale(12),
    marginBottom: moderateScale(20),
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: moderateScale(12),
    borderRadius: SIZES.radius / 2,
    borderWidth: 1,
    borderColor: COLORS.primary,
    backgroundColor: 'transparent',
  },
  activeTab: {
    backgroundColor: COLORS.primary,
  },
  tabText: {
    color: COLORS.primary,
    fontSize: moderateScale(SIZES.small),
    fontWeight: '500',
  },
  activeTabText: {
    color: COLORS.white,
  },
  msgContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    padding: moderateScale(12),
    borderRadius: SIZES.radius / 2,
    marginBottom: moderateScale(16),
  },
  errorBg: {
    backgroundColor: 'rgba(255, 123, 114, 0.1)',
  },
  successBg: {
    backgroundColor: 'rgba(63, 185, 80, 0.1)',
  },
  msgText: {
    flex: 1,
    fontSize: moderateScale(SIZES.small),
  },
  errorText: {
    color: COLORS.error,
  },
  successText: {
    color: COLORS.success,
  },
  formCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  emptyText: {
    color: COLORS.textSecondary,
    fontSize: moderateScale(SIZES.small),
  },
  savedReminderText: {
    color: COLORS.text,
    fontSize: moderateScale(SIZES.small),
    paddingVertical: moderateScale(6),
  },
  savedReminder: {
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    paddingVertical: moderateScale(8),
  },
  helperText: {
    color: COLORS.textSecondary,
    fontSize: moderateScale(SIZES.caption),
    marginBottom: moderateScale(8),
    lineHeight: moderateScale(18),
  },
  linkText: {
    color: COLORS.primary,
    fontSize: moderateScale(SIZES.caption),
    paddingVertical: moderateScale(6),
  },
  dangerText: {
    color: COLORS.error,
    fontSize: moderateScale(SIZES.caption),
    paddingVertical: moderateScale(6),
  },
  manageRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    gap: moderateScale(8),
  },
  preferenceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: moderateScale(8),
  },
  inputGroup: {
    marginBottom: moderateScale(16),
  },
  label: {
    fontSize: moderateScale(SIZES.small),
    fontWeight: '500',
    color: COLORS.text,
    marginBottom: moderateScale(8),
  },
  input: {
    backgroundColor: COLORS.surfaceLight,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: SIZES.radius / 2,
    padding: moderateScale(14),
    fontSize: moderateScale(SIZES.body),
    color: COLORS.text,
  },
  row: {
    flexDirection: 'row',
  },
  checkboxGroup: {
    gap: moderateScale(10),
  },
  checkbox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: moderateScale(8),
  },
  checkboxSelected: {},
  checkboxLabel: {
    fontSize: moderateScale(SIZES.body),
    color: COLORS.textSecondary,
  },
  checkboxLabelSelected: {
    color: COLORS.text,
    fontWeight: '500',
  },
  submitButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: COLORS.primary,
    borderRadius: SIZES.radius / 2,
    padding: moderateScale(16),
    marginTop: moderateScale(8),
  },
  buttonDisabled: {
    opacity: 0.7,
  },
  submitButtonText: {
    color: COLORS.white,
    fontSize: moderateScale(SIZES.body),
    fontWeight: '600',
  },
});
