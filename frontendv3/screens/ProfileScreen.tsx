import React, { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { authService, formatApiError } from '../services/api';
import { buildProfileFields } from '../services/profile.mjs';
import { COLORS, SIZES, moderateScale } from '../constants/theme';

interface ProfileData {
  name?: string | null;
  phone_number?: string | null;
  email?: string | null;
  age?: number | null;
  gender?: string | null;
  phone_verified?: boolean;
  created_at?: string | null;
}

export default function ProfileScreen() {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    authService.getCurrentUser()
      .then((data) => { if (active) setProfile(data); })
      .catch((reason) => { if (active) setError(formatApiError(reason, 'Could not load your profile. Please try again.')); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const fields = profile ? buildProfileFields(profile) : null;

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      {loading ? (
        <View style={styles.center}><ActivityIndicator color={COLORS.primary} /><Text style={styles.muted}>Loading your profile…</Text></View>
      ) : error ? (
        <View style={styles.center}><Text accessibilityRole="alert" style={styles.error}>{error}</Text></View>
      ) : fields ? (
        <View style={styles.card}>
          <Text style={styles.name}>{fields.name}</Text>
          {fields.rows.map((row) => (
            <ProfileRow key={row.label} label={row.label} value={row.value} />
          ))}
        </View>
      ) : (
        <View style={styles.center}><Text style={styles.muted}>Profile information is unavailable.</Text></View>
      )}
    </SafeAreaView>
  );
}

function ProfileRow({ label, value }: { label: string; value: string }) {
  return <View style={styles.row}><Text style={styles.label}>{label}</Text><Text style={styles.value}>{value}</Text></View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.background, padding: moderateScale(SIZES.padding) },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  card: { backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: SIZES.radius, padding: moderateScale(SIZES.padding) },
  name: { color: COLORS.text, fontSize: moderateScale(SIZES.h2), fontWeight: '700', marginBottom: 18 },
  row: { paddingVertical: 12, borderTopWidth: 1, borderTopColor: COLORS.border, gap: 4 },
  label: { color: COLORS.textSecondary, fontSize: moderateScale(SIZES.caption) },
  value: { color: COLORS.text, fontSize: moderateScale(SIZES.body) },
  muted: { color: COLORS.textSecondary, textAlign: 'center' },
  error: { color: COLORS.error, textAlign: 'center' },
});
