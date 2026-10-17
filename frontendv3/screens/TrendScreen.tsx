import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Dimensions,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LineChart } from 'react-native-gifted-charts';
import { Picker } from '@react-native-picker/picker';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { formatApiError } from '../services/api';
import { COLORS, SIZES, moderateScale } from '../constants/theme';

const screenWidth = Dimensions.get('window').width;

interface MetricOption {
  value: string;
  name: string;
  keywords: string[];
}

const metricOptions: MetricOption[] = [
  { value: 'bp', name: 'Blood Pressure (Sys)', keywords: ['blood pressure', 'bp', 'systolic'] },
  { value: 'sugar', name: 'Blood Sugar / Glucose', keywords: ['sugar', 'glucose', 'fasting'] },
  { value: 'hemoglobin', name: 'Hemoglobin', keywords: ['hemoglobin', 'hb'] },
  { value: 'wbc', name: 'White Blood Cells', keywords: ['wbc', 'white blood'] },
  { value: 'platelet', name: 'Platelet Count', keywords: ['platelet', 'plt'] },
  { value: 'creatinine', name: 'Creatinine', keywords: ['creatinine', 'creat'] },
];
const DEFAULT_METRIC = metricOptions[0].value;

interface DataPoint {
  timestamp: number;
  displayDate: string;
  fileName: string;
  [key: string]: any;
}

export default function TrendScreen() {
  const [data, setData] = useState<DataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedMetric, setSelectedMetric] = useState(DEFAULT_METRIC);
  const activeMetric = metricOptions.some((metric) => metric.value === selectedMetric)
    ? selectedMetric
    : DEFAULT_METRIC;

  const findValueInEntities = (entities: any[], keywords: string[]): number | null => {
    if (!entities || !Array.isArray(entities)) return null;

    const match = entities.find((e) => {
      const textToSearch = String(e?.Indicator || e?.Description || '').toLowerCase();
      return keywords.some((k) => textToSearch.includes(k));
    });

    if (match) {
      const valueString = String(match.Value ?? match.value ?? '');
      const numMatch = valueString.match(/-?\d+(\.\d+)?/);
      return numMatch ? parseFloat(numMatch[0]) : null;
    }
    return null;
  };

  const processReportsData = (reports: any[]): DataPoint[] => {
    const sortedReports = [...reports]
      .filter((report) => Number.isFinite(new Date(report.upload_date).getTime()))
      .sort((a, b) => new Date(a.upload_date).getTime() - new Date(b.upload_date).getTime());

    return sortedReports.map((report) => {
      const dateObj = new Date(report.upload_date);

      const dataPoint: DataPoint = {
        timestamp: dateObj.getTime(),
        displayDate: new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(dateObj),
        fileName: report.filename || 'Report',
      };

      metricOptions.forEach((metric) => {
        dataPoint[metric.value] = findValueInEntities(report.structured_entities, metric.keywords);
      });

      return dataPoint;
    });
  };

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await api.get('/reports/history');
        const processed = processReportsData(response.data);
        setData(processed);

      } catch (err) {
        setError(formatApiError(err, 'Failed to load health history. Please try again.'));
      } finally {
        setLoading(false);
      }
    };

    fetchHistory();
  }, []);

  const currentMetricName = metricOptions.find((m) => m.value === activeMetric)?.name || 'Select an indicator';

  // Prepare chart data
  const chartData = data
    .filter((d) => d[activeMetric] !== null)
    .map((d, index) => ({
      value: d[activeMetric] as number,
      label: d.displayDate,
      dataPointText: d[activeMetric]?.toString(),
    }));

  const dataPointsCount = chartData.length;
  const totalReportsCount = data.length;

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Your Health Trends</Text>

        {/* Metric Selector */}
        <View style={styles.controlsCard}>
          <Text style={styles.controlLabel}>Track Indicator:</Text>
          <View style={styles.pickerContainer}>
            <Picker
              selectedValue={activeMetric}
              onValueChange={(value) => {
                if (metricOptions.some((metric) => metric.value === value)) setSelectedMetric(value);
              }}
              style={[styles.picker, { height: Platform.OS === 'ios' ? 150 : 50 }]}
              itemStyle={styles.pickerItem}
              dropdownIconColor={COLORS.text}
            >
              {metricOptions.map((opt) => (
                <Picker.Item key={opt.value} label={opt.name} value={opt.value} />
              ))}
            </Picker>
          </View>
        </View>

        {loading && (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color={COLORS.primary} />
            <Text style={styles.loadingText}>Loading your history...</Text>
          </View>
        )}

        {error && !loading && (
          <View style={styles.errorCard}>
            <Ionicons name="alert-circle" size={24} color={COLORS.error} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        )}

        {!loading && !error && data.length === 0 && (
          <View style={styles.noChartData}>
            <Ionicons name="document-text-outline" size={40} color={COLORS.textMuted} />
            <Text style={styles.noChartText}>No report history yet. Upload a report to see trends.</Text>
          </View>
        )}

        {!loading && !error && data.length > 0 && (
          <>
            {/* Chart Card */}
            <View style={styles.chartCard}>
              <Text style={styles.chartTitle}>{currentMetricName}</Text>
              {chartData.length > 0 ? (
                <View style={styles.chartWrapper}>
                  <LineChart
                    data={chartData}
                    width={screenWidth - moderateScale(80)}
                    height={220}
                    color={COLORS.primary}
                    thickness={3}
                    dataPointsColor={COLORS.primary}
                    dataPointsRadius={5}
                    startFillColor={COLORS.primary}
                    endFillColor={COLORS.background}
                    startOpacity={0.3}
                    endOpacity={0.05}
                    areaChart
                    curved
                    yAxisColor={COLORS.border}
                    xAxisColor={COLORS.border}
                    yAxisTextStyle={styles.axisText}
                    xAxisLabelTextStyle={styles.axisText}
                    hideRules
                    showVerticalLines
                    verticalLinesColor="rgba(48, 54, 61, 0.5)"
                    noOfSections={5}
                    maxValue={Math.max(1, ...chartData.map(d => d.value)) * 1.2}
                    pointerConfig={{
                      pointerStripColor: COLORS.primary,
                      pointerStripWidth: 2,
                      pointerColor: COLORS.primary,
                      radius: 6,
                      pointerLabelWidth: 100,
                      pointerLabelHeight: 90,
                      activatePointersOnLongPress: true,
                      autoAdjustPointerLabelPosition: true,
                      pointerLabelComponent: (items: any) => {
                        return (
                          <View style={styles.tooltipContainer}>
                            <Text style={styles.tooltipValue}>{items[0].value}</Text>
                            <Text style={styles.tooltipLabel}>{items[0].label}</Text>
                          </View>
                        );
                      },
                    }}
                  />
                </View>
              ) : (
                <View style={styles.noChartData}>
                  <Ionicons name="analytics-outline" size={40} color={COLORS.textMuted} />
                  <Text style={styles.noChartText}>
                    No data points found for {currentMetricName}
                  </Text>
                </View>
              )}
            </View>

            {/* Insight Card */}
            <View style={styles.insightCard}>
              <View style={styles.insightHeader}>
                <Ionicons name="bulb-outline" size={20} color={COLORS.primary} />
                <Text style={styles.insightTitle}>Insight</Text>
              </View>
              <View style={styles.insightList}>
                <View style={styles.insightItem}>
                  <View style={styles.bulletPoint} />
                  <Text style={styles.insightText}>
                    Showing data extracted from <Text style={styles.highlight}>{totalReportsCount}</Text> reports.
                  </Text>
                </View>
                <View style={styles.insightItem}>
                  <View style={styles.bulletPoint} />
                  <Text style={styles.insightText}>
                    <Text style={styles.highlight}>{dataPointsCount}</Text> reports contained data for {currentMetricName}.
                  </Text>
                </View>
                {dataPointsCount === 0 && (
                  <View style={styles.insightItem}>
                    <View style={[styles.bulletPoint, { backgroundColor: COLORS.error }]} />
                    <Text style={[styles.insightText, { color: COLORS.error }]}>
                      No data points found for this metric. Try extracting a report that contains {currentMetricName}.
                    </Text>
                  </View>
                )}
              </View>
            </View>
          </>
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
  controlsCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: moderateScale(20),
  },
  controlLabel: {
    fontSize: moderateScale(SIZES.small),
    fontWeight: '500',
    color: COLORS.text,
    marginBottom: moderateScale(10),
  },
  pickerContainer: {
    backgroundColor: COLORS.surfaceLight,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: SIZES.radius / 2,
    overflow: 'hidden',
  },
  picker: {
    color: COLORS.text,
    height: 50,
  },
  pickerItem: {
    color: COLORS.text,
  },
  loadingContainer: {
    paddingVertical: moderateScale(60),
    alignItems: 'center',
    gap: moderateScale(16),
  },
  loadingText: {
    fontSize: moderateScale(SIZES.body),
    color: COLORS.textSecondary,
  },
  errorCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: 'rgba(255, 123, 114, 0.1)',
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
  },
  errorText: {
    flex: 1,
    color: COLORS.error,
    fontSize: moderateScale(SIZES.small),
  },
  chartCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: moderateScale(20),
  },
  chartTitle: {
    fontSize: moderateScale(SIZES.h4),
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: moderateScale(16),
  },
  chartWrapper: {
    alignItems: 'center',
  },
  axisText: {
    color: COLORS.textSecondary,
    fontSize: moderateScale(10),
  },
  tooltipContainer: {
    backgroundColor: COLORS.surface,
    padding: moderateScale(8),
    borderRadius: SIZES.radius / 2,
    borderWidth: 1,
    borderColor: COLORS.primary,
  },
  tooltipValue: {
    fontSize: moderateScale(SIZES.body),
    fontWeight: '600',
    color: COLORS.primary,
  },
  tooltipLabel: {
    fontSize: moderateScale(SIZES.caption),
    color: COLORS.textSecondary,
  },
  noChartData: {
    alignItems: 'center',
    paddingVertical: moderateScale(40),
    gap: moderateScale(12),
  },
  noChartText: {
    fontSize: moderateScale(SIZES.small),
    color: COLORS.textSecondary,
    textAlign: 'center',
  },
  insightCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  insightHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: moderateScale(12),
  },
  insightTitle: {
    fontSize: moderateScale(SIZES.h4),
    fontWeight: '600',
    color: COLORS.text,
  },
  insightList: {
    gap: moderateScale(10),
  },
  insightItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
  },
  bulletPoint: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: COLORS.primary,
    marginTop: moderateScale(6),
  },
  insightText: {
    flex: 1,
    fontSize: moderateScale(SIZES.small),
    color: COLORS.textSecondary,
    lineHeight: moderateScale(20),
  },
  highlight: {
    fontWeight: '700',
    color: COLORS.text,
  },
});
