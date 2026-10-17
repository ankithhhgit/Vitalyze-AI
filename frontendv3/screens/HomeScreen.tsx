import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../context/AuthContext';
import { COLORS, SIZES, moderateScale, verticalScale } from '../constants/theme';

interface FeatureCardProps {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  description: string;
}

function FeatureCard({ icon, title, description }: FeatureCardProps) {
  return (
    <View style={styles.featureCard}>
      <View style={styles.featureIconContainer}>
        <Ionicons name={icon} size={32} color={COLORS.primary} />
      </View>
      <Text style={styles.featureTitle}>{title}</Text>
      <Text style={styles.featureDescription}>{description}</Text>
    </View>
  );
}

export default function HomeScreen() {
  const navigation = useNavigation<any>();
  const { user, logout } = useAuth();

  const handleAuthAction = () => {
    if (user) {
      logout();
    } else {
      navigation.navigate('SignIn');
    }
  };

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* Header */}
        <View style={styles.header}>
          <View>
            <Text style={styles.logo}>Vitalyze.ai</Text>
          </View>
          <TouchableOpacity style={styles.authButton} onPress={handleAuthAction}>
            <Ionicons
              name={user ? 'log-out-outline' : 'person-outline'}
              size={20}
              color={COLORS.primary}
            />
            <Text style={styles.authButtonText}>{user ? 'Logout' : 'Sign In'}</Text>
          </TouchableOpacity>
        </View>

        {/* Hero Section */}
        <View style={styles.heroSection}>
          <Text style={styles.heroTitle}>Welcome to Vitalyze</Text>
          <Text style={styles.heroSubtitle}>
            Extract text from a PDF report locally, manage reminders, and open a separate pharmacy search.
            {'\n\n'}
            Smart, fast, and reliable healthcare at your fingertips.
          </Text>
        </View>

        {/* Features Section */}
        <View style={styles.featuresSection}>
          <Text style={styles.sectionTitle}>Why Choose Vitalyze?</Text>
          <View style={styles.featuresGrid}>
            <FeatureCard
              icon="document-text-outline"
              title="Easy Prescription Upload"
              description="Extract text locally. AI interpretation requires backend provider configuration."
            />
            <FeatureCard
              icon="location-outline"
              title="Nearest Medical Stores"
              description="Pharmacy results require Maps configuration; a separate Google Maps search is available."
            />
            <FeatureCard
              icon="chatbubbles-outline"
              title="Integrated Chatbot"
              description="The assistant requires backend AI configuration and does not generate offline answers."
            />
          </View>
        </View>

        {/* CTA Section */}
        <View style={styles.ctaSection}>
          <Text style={styles.ctaTitle}>Start Your Health Journey Today!</Text>
          <TouchableOpacity
            style={styles.ctaButton}
            onPress={() => navigation.navigate('Analyser')}
          >
            <Text style={styles.ctaButtonText}>Upload a Report</Text>
            <Ionicons name="arrow-forward" size={20} color={COLORS.white} />
          </TouchableOpacity>
        </View>

        {/* Footer */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>2025 Vitalyze. All rights reserved.</Text>
        </View>
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
    flexGrow: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: moderateScale(SIZES.padding),
    paddingVertical: moderateScale(16),
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    backgroundColor: COLORS.surface,
  },
  logo: {
    fontSize: moderateScale(SIZES.h3),
    fontWeight: '700',
    color: COLORS.text,
    letterSpacing: 1,
  },
  authButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: moderateScale(12),
    paddingVertical: moderateScale(8),
    borderRadius: SIZES.radius / 2,
    borderWidth: 1,
    borderColor: COLORS.primary,
  },
  authButtonText: {
    color: COLORS.primary,
    fontSize: moderateScale(SIZES.small),
    fontWeight: '500',
  },
  heroSection: {
    paddingHorizontal: moderateScale(SIZES.padding * 1.5),
    paddingVertical: verticalScale(40),
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  heroTitle: {
    fontSize: moderateScale(SIZES.h1),
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: moderateScale(16),
  },
  heroSubtitle: {
    fontSize: moderateScale(SIZES.body),
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: moderateScale(24),
  },
  featuresSection: {
    paddingHorizontal: moderateScale(SIZES.padding),
    paddingVertical: verticalScale(32),
  },
  sectionTitle: {
    fontSize: moderateScale(SIZES.h2),
    fontWeight: '600',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: moderateScale(24),
  },
  featuresGrid: {
    gap: moderateScale(16),
  },
  featureCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(20),
    borderWidth: 1,
    borderColor: COLORS.border,
    alignItems: 'center',
  },
  featureIconContainer: {
    width: moderateScale(64),
    height: moderateScale(64),
    borderRadius: moderateScale(32),
    backgroundColor: 'rgba(0, 188, 212, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: moderateScale(16),
  },
  featureTitle: {
    fontSize: moderateScale(SIZES.h4),
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: moderateScale(8),
    textAlign: 'center',
  },
  featureDescription: {
    fontSize: moderateScale(SIZES.small),
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: moderateScale(20),
  },
  ctaSection: {
    paddingHorizontal: moderateScale(SIZES.padding * 1.5),
    paddingVertical: verticalScale(32),
    alignItems: 'center',
    backgroundColor: COLORS.surface,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
  },
  ctaTitle: {
    fontSize: moderateScale(SIZES.h3),
    fontWeight: '600',
    color: COLORS.text,
    textAlign: 'center',
    marginBottom: moderateScale(20),
  },
  ctaButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.primary,
    paddingHorizontal: moderateScale(24),
    paddingVertical: moderateScale(14),
    borderRadius: SIZES.radius / 2,
  },
  ctaButtonText: {
    color: COLORS.white,
    fontSize: moderateScale(SIZES.body),
    fontWeight: '600',
  },
  footer: {
    paddingVertical: verticalScale(20),
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
  },
  footerText: {
    color: COLORS.textMuted,
    fontSize: moderateScale(SIZES.caption),
  },
});
