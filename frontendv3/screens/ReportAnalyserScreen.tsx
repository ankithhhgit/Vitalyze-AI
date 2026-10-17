import React, { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import Markdown from 'react-native-markdown-display';
import { Ionicons } from '@expo/vector-icons';
import api from '../services/api';
import { formatApiError } from '../services/api';
import { COLORS, SIZES, moderateScale } from '../constants/theme';

type StatusType = 'idle' | 'uploading' | 'analyzing' | 'completed' | 'error';

interface AnalysisResult {
  simple_summary?: string;
  analysis_mode?: 'ai_analysis' | 'local_extraction_preview';
  report_id?: string;
  raw_text?: string;
  vital_indicators?: Array<{ Indicator: string; Value: string }>;
  structured_entities?: Array<{ Description: string; Confidence: number }>;
}

export default function ReportAnalyserScreen() {
  const [selectedFile, setSelectedFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [status, setStatus] = useState<StatusType>('idle');
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [extractedText, setExtractedText] = useState('');
  const [textPreviewLoading, setTextPreviewLoading] = useState(false);
  const [textPreviewMessage, setTextPreviewMessage] = useState('');
  const [errorMsg, setErrorMsg] = useState('');

  const handleFilePick = async () => {
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: 'application/pdf',
        copyToCacheDirectory: true,
      });

      if (!result.canceled && result.assets && result.assets.length > 0) {
        const file = result.assets[0];
        setSelectedFile(file);
        setErrorMsg('');
        setStatus('idle');
        setAnalysisResult(null);
        setExtractedText('');
        setTextPreviewMessage('');
      }
    } catch (err) {
      console.error('File pick error:', err);
      setErrorMsg('Failed to pick file.');
    }
  };

  const pollTaskStatus = async (taskId: string, filename: string, uploadStartedAt: number) => {
    setStatus('analyzing');
    for (let attempt = 0; attempt < 90; attempt += 1) {
      try {
        const response = await api.get(`/reports/status/${taskId}`);
        const taskState = response.data.status;

        if (taskState === 'SUCCESS') {
          const result: AnalysisResult = response.data.result || {};
          let text = typeof result.raw_text === 'string' ? result.raw_text : '';
          if (!text) {
            setTextPreviewLoading(true);
            try {
              const history = await api.get('/reports/history');
              const reports = Array.isArray(history.data) ? history.data : [];
              const savedReport = reports.find((item: any) => {
                const idMatches = result.report_id != null
                  && String(item?.id ?? item?._id) === String(result.report_id);
                const uploadedAt = new Date(item?.upload_date).getTime();
                const recentMatchingFile = item?.filename === filename
                  && Number.isFinite(uploadedAt)
                  && uploadedAt >= uploadStartedAt - 2 * 60 * 1000;
                return idMatches || recentMatchingFile;
              });
              text = typeof savedReport?.raw_text === 'string' ? savedReport.raw_text : '';
              if (!text) {
                setTextPreviewMessage('The report task completed, but extracted text was not present in the saved history record. AI summary availability is separate from PDF text extraction.');
              }
            } catch (err) {
              setTextPreviewMessage(formatApiError(err, 'The report task completed, but saved PDF text could not be loaded.'));
            } finally {
              setTextPreviewLoading(false);
            }
          }
          setExtractedText(text);
          if (text) setTextPreviewMessage('');
          setAnalysisResult(result);
          setStatus('completed');
          return;
        } else if (taskState === 'FAILURE') {
          setErrorMsg(response.data.error || 'Report processing failed. The report was not saved.');
          setStatus('error');
          return;
        }
      } catch (err) {
        setErrorMsg(formatApiError(err, 'Lost connection to the server while checking status.'));
        setStatus('error');
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 2000));
    }
    setErrorMsg('Report processing timed out. Check Trends or report history before retrying.');
    setStatus('error');
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    const file = selectedFile;
    const uploadStartedAt = Date.now();
    setStatus('uploading');
    setErrorMsg('');
    setExtractedText('');
    setTextPreviewMessage('');

    try {
      const fileUri = file.uri;
      if (!fileUri || !file.name) {
        throw new Error('The selected PDF is missing its file location or filename. Please select it again.');
      }
      if (!file.name.toLowerCase().endsWith('.pdf') || (file.mimeType && file.mimeType !== 'application/pdf')) {
        throw new Error('Choose a PDF document to extract text.');
      }
      if (file.size != null && file.size > 15 * 1024 * 1024) {
        throw new Error('PDF is too large. Maximum size is 15 MB.');
      }
      const fileInfo = await FileSystem.getInfoAsync(fileUri);
      
      if (!fileInfo.exists) {
        throw new Error('The selected PDF is no longer available. Please select it again.');
      }
      if (fileInfo.size != null && fileInfo.size > 15 * 1024 * 1024) {
        throw new Error('PDF is too large. Maximum size is 15 MB.');
      }

      const formData = new FormData();
      formData.append('file', {
        uri: fileUri,
        name: file.name,
        type: file.mimeType || 'application/pdf',
      } as any);

      const response = await api.post('/reports/upload', formData, {
        headers: { Accept: 'application/json' },
      });

      await pollTaskStatus(response.data.task_id, file.name, uploadStartedAt);
    } catch (err: any) {
      setStatus('error');
      setErrorMsg(err?.response
        ? formatApiError(err, 'Failed to upload the PDF. Check your connection and try again.')
        : err instanceof Error ? err.message : 'Failed to upload the PDF. Check your connection and try again.');
    }
  };

  // Filter logic for cleaned data
  const rawData =
    analysisResult?.vital_indicators && analysisResult.vital_indicators.length > 0
      ? analysisResult.vital_indicators
      : analysisResult?.structured_entities || [];

  const hasVitals = analysisResult?.vital_indicators && analysisResult.vital_indicators.length > 0;

  const cleanedData = rawData.filter((item: any) => {
    const label = hasVitals ? item.Indicator : item.Description;
    if (!label) return false;
    const lowerLabel = label.toLowerCase();
    const junkWords = ['qr code', 'scanner', 'page', 'result', 'visit', 'date', 'generated', 'unit'];
    if (junkWords.some((word) => lowerLabel.includes(word))) return false;
    if (!isNaN(parseFloat(label)) && isFinite(Number(label))) return false;
    return true;
  });

  return (
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        <Text style={styles.title}>Report Analyser</Text>
        <Text style={styles.subtitle}>Upload a text-based PDF for local extraction preview. AI interpretation is unavailable until the backend is explicitly configured.</Text>

        {/* Upload Section */}
        <View style={styles.uploadSection}>
          <TouchableOpacity
            style={styles.filePickerButton}
            onPress={handleFilePick}
            disabled={status === 'uploading' || status === 'analyzing'}
          >
            <Ionicons name="document-outline" size={24} color={COLORS.primary} />
            <Text style={styles.filePickerText}>
              {selectedFile ? selectedFile.name : 'Select PDF File'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.uploadButton,
              (!selectedFile || status === 'uploading' || status === 'analyzing') && styles.buttonDisabled,
            ]}
            onPress={handleUpload}
            disabled={!selectedFile || status === 'uploading' || status === 'analyzing'}
          >
            {status === 'uploading' || status === 'analyzing' ? (
              <ActivityIndicator color={COLORS.white} />
            ) : (
              <>
                <Ionicons name="cloud-upload-outline" size={20} color={COLORS.white} />
              <Text style={styles.uploadButtonText}>Extract PDF Text</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        {/* Analyzing Status */}
        {status === 'analyzing' && (
          <View style={styles.statusCard}>
            <ActivityIndicator size="large" color={COLORS.primary} />
            <Text style={styles.statusTitle}>Processing your report...</Text>
            <Text style={styles.statusSubtitle}>
              Extracting PDF text and saving your preview. AI interpretation is not being run in local mode.
            </Text>
          </View>
        )}

        {/* Error Message */}
        {errorMsg ? (
          <View style={styles.errorCard}>
            <Ionicons name="alert-circle" size={24} color={COLORS.error} />
            <Text style={styles.errorText}>{errorMsg}</Text>
          </View>
        ) : null}

        {/* Results */}
        {status === 'completed' && analysisResult && (
          <View style={styles.resultsContainer}>
            {/* Summary Card */}
            <View style={styles.summaryCard}>
              <View style={styles.cardHeader}>
                <Ionicons name={analysisResult.analysis_mode === 'ai_analysis' ? 'sparkles' : 'document-text'} size={20} color={COLORS.primary} />
                <Text style={styles.cardTitle}>AI Summary</Text>
              </View>
              <Markdown
                style={{
                  body: {
                    color: COLORS.text,
                    fontSize: moderateScale(SIZES.small),
                    lineHeight: moderateScale(22),
                  },
                  strong: { fontWeight: '700' },
                  paragraph: { marginVertical: 4 },
                }}
              >
                {analysisResult.simple_summary || 'AI interpretation is unavailable. Extracted PDF text is shown separately below.'}
              </Markdown>
            </View>

            <View style={styles.entitiesCard}>
              <Text style={styles.cardTitle}>Extracted PDF text</Text>
              {textPreviewLoading ? (
                <ActivityIndicator color={COLORS.primary} />
              ) : extractedText ? (
                <Text selectable style={styles.extractedText}>{extractedText}</Text>
              ) : (
                <Text style={styles.noDataText}>{textPreviewMessage || 'No extracted text was returned with this report. This does not indicate whether AI summary generation succeeded.'}</Text>
              )}
              {analysisResult.analysis_mode === 'local_extraction_preview' && (
                <Text style={styles.noDataText}>AI interpretation is unavailable in local extraction mode.</Text>
              )}
            </View>

            {/* AI-derived entities are shown only for a verified AI result. */}
            {analysisResult.analysis_mode === 'ai_analysis' && <>
            <View style={styles.entitiesCard}>
              <View style={styles.cardHeader}>
                <Ionicons name="search" size={20} color={COLORS.primary} />
                <Text style={styles.cardTitle}>Extracted Medical Details</Text>
              </View>

              {cleanedData.length > 0 ? (
                <View style={styles.table}>
                  <View style={styles.tableHeader}>
                    <Text style={[styles.tableHeaderText, { flex: 1 }]}>
                      {hasVitals ? 'Medical Indicator' : 'Detected Entity'}
                    </Text>
                    <Text style={[styles.tableHeaderText, { flex: 1 }]}>
                      {hasVitals ? 'Measured Value' : 'Confidence'}
                    </Text>
                  </View>
                  {cleanedData.map((item: any, idx: number) => (
                    <View key={idx} style={styles.tableRow}>
                      {hasVitals ? (
                        <>
                          <Text style={[styles.tableCell, styles.indicatorCell]}>{item.Indicator}</Text>
                          <Text style={[styles.tableCell, styles.valueCell]}>{item.Value}</Text>
                        </>
                      ) : (
                        <>
                          <Text style={[styles.tableCell, { flex: 1 }]}>{item.Description}</Text>
                          <Text style={[styles.tableCell, styles.confidenceCell]}>
                            {(item.Confidence * 100).toFixed(0)}%
                          </Text>
                        </>
                      )}
                    </View>
                  ))}
                </View>
              ) : (
                <Text style={styles.noDataText}>No specific entities detected.</Text>
              )}
            </View>
            </>}
          </View>
        )}

        {/* Idle Info */}
        {status === 'idle' && (
          <View style={styles.infoCard}>
            <Text style={styles.infoTitle}>Privacy & Tips</Text>
            <View style={styles.infoItem}>
              <Ionicons name="shield-checkmark-outline" size={18} color={COLORS.primary} />
              <Text style={styles.infoText}>Text-based PDFs are extracted locally. No medical interpretation is generated in local mode.</Text>
            </View>
            <View style={styles.infoItem}>
              <Ionicons name="document-outline" size={18} color={COLORS.primary} />
              <Text style={styles.infoText}>We only accept PDF files currently.</Text>
            </View>
            <View style={styles.infoItem}>
              <Ionicons name="medkit-outline" size={18} color={COLORS.primary} />
              <Text style={styles.infoText}>Results are for informational purposes only. Always consult a doctor.</Text>
            </View>
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
    marginBottom: moderateScale(8),
  },
  subtitle: {
    fontSize: moderateScale(SIZES.small),
    color: COLORS.textSecondary,
    textAlign: 'center',
    marginBottom: moderateScale(24),
  },
  uploadSection: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: moderateScale(20),
  },
  filePickerButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    padding: moderateScale(20),
    borderWidth: 2,
    borderStyle: 'dashed',
    borderColor: COLORS.border,
    borderRadius: SIZES.radius / 2,
    marginBottom: moderateScale(12),
  },
  filePickerText: {
    color: COLORS.text,
    fontSize: moderateScale(SIZES.body),
  },
  uploadButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: COLORS.primary,
    borderRadius: SIZES.radius / 2,
    padding: moderateScale(16),
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  uploadButtonText: {
    color: COLORS.white,
    fontSize: moderateScale(SIZES.body),
    fontWeight: '600',
  },
  statusCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(24),
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.border,
    marginBottom: moderateScale(20),
  },
  statusTitle: {
    fontSize: moderateScale(SIZES.h4),
    fontWeight: '600',
    color: COLORS.text,
    marginTop: moderateScale(16),
    marginBottom: moderateScale(8),
  },
  statusSubtitle: {
    fontSize: moderateScale(SIZES.small),
    color: COLORS.textSecondary,
    textAlign: 'center',
  },
  errorCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: 'rgba(255, 123, 114, 0.1)',
    borderRadius: SIZES.radius / 2,
    padding: moderateScale(14),
    marginBottom: moderateScale(20),
  },
  errorText: {
    flex: 1,
    color: COLORS.error,
    fontSize: moderateScale(SIZES.small),
  },
  resultsContainer: {
    gap: moderateScale(16),
  },
  summaryCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: moderateScale(12),
  },
  cardTitle: {
    fontSize: moderateScale(SIZES.h4),
    fontWeight: '600',
    color: COLORS.text,
  },
  entitiesCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  table: {
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: SIZES.radius / 2,
    overflow: 'hidden',
  },
  tableHeader: {
    flexDirection: 'row',
    backgroundColor: COLORS.surfaceLight,
    paddingVertical: moderateScale(10),
    paddingHorizontal: moderateScale(12),
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  tableHeaderText: {
    fontSize: moderateScale(SIZES.small),
    fontWeight: '600',
    color: COLORS.text,
  },
  tableRow: {
    flexDirection: 'row',
    paddingVertical: moderateScale(10),
    paddingHorizontal: moderateScale(12),
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  tableCell: {
    fontSize: moderateScale(SIZES.small),
    color: COLORS.text,
  },
  indicatorCell: {
    flex: 1,
    fontWeight: '600',
  },
  valueCell: {
    flex: 1,
    color: COLORS.primary,
  },
  confidenceCell: {
    flex: 1,
    color: COLORS.textSecondary,
  },
  noDataText: {
    color: COLORS.textSecondary,
    fontSize: moderateScale(SIZES.small),
    textAlign: 'center',
    paddingVertical: moderateScale(16),
  },
  extractedText: {
    color: COLORS.text,
    fontSize: moderateScale(SIZES.small),
    lineHeight: moderateScale(21),
  },
  infoCard: {
    backgroundColor: COLORS.surface,
    borderRadius: SIZES.radius,
    padding: moderateScale(SIZES.padding),
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  infoTitle: {
    fontSize: moderateScale(SIZES.h4),
    fontWeight: '600',
    color: COLORS.text,
    marginBottom: moderateScale(16),
  },
  infoItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    marginBottom: moderateScale(12),
  },
  infoText: {
    flex: 1,
    fontSize: moderateScale(SIZES.small),
    color: COLORS.textSecondary,
    lineHeight: moderateScale(20),
  },
});
