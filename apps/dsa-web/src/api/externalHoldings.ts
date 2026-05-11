import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  ExternalHoldingConfirmRequest,
  ExternalHoldingDocSyncResponse,
  ExternalHoldingExtractResponse,
  ExternalHoldingSnapshotItem,
  ExternalHoldingStatusResponse,
  ExternalHoldingSourcePlatform,
} from '../types/externalHoldings';

export const externalHoldingsApi = {
  async getStatus(): Promise<ExternalHoldingStatusResponse> {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/external-holdings/status');
    return toCamelCase<ExternalHoldingStatusResponse>(response.data);
  },

  async extractFromImage(
    sourcePlatform: ExternalHoldingSourcePlatform,
    file: File,
  ): Promise<ExternalHoldingExtractResponse> {
    const formData = new FormData();
    formData.append('source_platform', sourcePlatform);
    formData.append('file', file);
    const response = await apiClient.post<Record<string, unknown>>(
      '/api/v1/external-holdings/extract-from-image',
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return toCamelCase<ExternalHoldingExtractResponse>(response.data);
  },

  async getSnapshot(snapshotId: number): Promise<ExternalHoldingSnapshotItem> {
    const response = await apiClient.get<Record<string, unknown>>(
      `/api/v1/external-holdings/snapshots/${snapshotId}`,
    );
    return toCamelCase<ExternalHoldingSnapshotItem>(response.data);
  },

  async confirmSnapshot(
    snapshotId: number,
    payload: ExternalHoldingConfirmRequest,
  ): Promise<ExternalHoldingSnapshotItem> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/external-holdings/snapshots/${snapshotId}/confirm`,
      {
        items: payload.items.map((item) => ({
          asset_type: item.assetType,
          source_platform: item.sourcePlatform,
          symbol: item.symbol,
          display_name: item.displayName,
          market: item.market,
          quantity: item.quantity,
          market_value: item.marketValue,
          cost_basis_total: item.costBasisTotal,
          profit_amount: item.profitAmount,
          profit_pct: item.profitPct,
          position_weight: item.positionWeight,
          price: item.price,
          price_date: item.priceDate,
          confidence: item.confidence,
          is_manually_edited: item.isManuallyEdited,
          raw_payload: item.rawPayload,
        })),
        review_notes: payload.reviewNotes,
        sync_doc: payload.syncDoc ?? true,
      },
    );
    return toCamelCase<ExternalHoldingSnapshotItem>(response.data);
  },

  async getLatest(
    sourcePlatform?: ExternalHoldingSourcePlatform,
  ): Promise<ExternalHoldingSnapshotItem> {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/external-holdings/latest',
      {
        params: sourcePlatform ? { source_platform: sourcePlatform } : undefined,
      },
    );
    return toCamelCase<ExternalHoldingSnapshotItem>(response.data);
  },

  async syncDoc(snapshotId: number): Promise<ExternalHoldingDocSyncResponse> {
    const response = await apiClient.post<Record<string, unknown>>(
      `/api/v1/external-holdings/snapshots/${snapshotId}/doc-sync`,
    );
    return toCamelCase<ExternalHoldingDocSyncResponse>(response.data);
  },
};
