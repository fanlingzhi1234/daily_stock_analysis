export type ExternalHoldingSourcePlatform = 'ths_stock' | 'alipay_fund';
export type ExternalHoldingAssetType = 'stock' | 'etf' | 'fund';
export type ExternalHoldingMarket = 'cn' | 'hk' | 'us' | 'fund';
export type ExternalHoldingConfidence = 'high' | 'medium' | 'low';
export type ExternalHoldingSnapshotStatus = 'draft' | 'confirmed' | 'archived';

export interface ExternalHoldingPositionInput {
  assetType: ExternalHoldingAssetType;
  sourcePlatform: ExternalHoldingSourcePlatform;
  symbol?: string | null;
  displayName?: string | null;
  market: ExternalHoldingMarket;
  quantity?: number | null;
  marketValue?: number | null;
  costBasisTotal?: number | null;
  profitAmount?: number | null;
  profitPct?: number | null;
  positionWeight?: number | null;
  price?: number | null;
  priceDate?: string | null;
  confidence: ExternalHoldingConfidence;
  isManuallyEdited: boolean;
  rawPayload?: string | null;
}

export interface ExternalHoldingPositionItem extends ExternalHoldingPositionInput {
  id: number;
}

export interface ExternalHoldingSnapshotItem {
  id: number;
  sourcePlatform: ExternalHoldingSourcePlatform;
  snapshotDate: string;
  capturedAt?: string | null;
  uploadedAt?: string | null;
  status: ExternalHoldingSnapshotStatus;
  totalMarketValue?: number | null;
  totalProfit?: number | null;
  currency: string;
  rawImagePath?: string | null;
  ocrRawText?: string | null;
  warnings: string[];
  reviewNotes?: string | null;
  docUrl?: string | null;
  docTitle?: string | null;
  docSyncStatus?: string | null;
  docSyncError?: string | null;
  docExportedAt?: string | null;
  createdAt?: string | null;
  updatedAt?: string | null;
  positions: ExternalHoldingPositionItem[];
}

export interface ExternalHoldingExtractResponse {
  snapshot: ExternalHoldingSnapshotItem;
}

export interface ExternalHoldingConfirmRequest {
  items: ExternalHoldingPositionInput[];
  reviewNotes?: string | null;
  syncDoc?: boolean;
}

export interface ExternalHoldingDocSyncResponse {
  snapshotId: number;
  docUrl?: string | null;
  docSyncStatus: string;
  docSyncError?: string | null;
}

export interface ExternalHoldingStatusResponse {
  enabled: boolean;
  reminderEnabled: boolean;
  docSyncEnabled: boolean;
  reminderChannels: string[];
  supportedSourcePlatforms: ExternalHoldingSourcePlatform[];
  mobileUploadHint?: string | null;
}
