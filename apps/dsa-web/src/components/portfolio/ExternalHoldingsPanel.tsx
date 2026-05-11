import type React from 'react';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { externalHoldingsApi } from '../../api/externalHoldings';
import type { ParsedApiError } from '../../api/error';
import { getParsedApiError } from '../../api/error';
import { Badge, Card, InlineAlert } from '../common';
import type {
  ExternalHoldingPositionInput,
  ExternalHoldingSnapshotItem,
  ExternalHoldingStatusResponse,
  ExternalHoldingSourcePlatform,
} from '../../types/externalHoldings';

const INPUT_CLASS =
  'input-surface input-focus-glow h-11 w-full rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';
const SELECT_CLASS = `${INPUT_CLASS} appearance-none pr-10`;
const FILE_PICKER_CLASS =
  'input-surface input-focus-glow flex h-11 w-full cursor-pointer items-center justify-center rounded-xl border bg-transparent px-4 text-sm transition-all focus:outline-none disabled:cursor-not-allowed disabled:opacity-60';

const SOURCE_OPTIONS: Array<{ value: ExternalHoldingSourcePlatform; label: string }> = [
  { value: 'ths_stock', label: '同花顺股票 / ETF 持仓' },
  { value: 'alipay_fund', label: '支付宝基金持仓' },
];

function formatMoney(value: number | undefined | null, currency = 'CNY'): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${Number(value).toFixed(2)}%`;
}

const ExternalHoldingsPanel: React.FC = () => {
  const [status, setStatus] = useState<ExternalHoldingStatusResponse | null>(null);
  const [isStatusLoading, setIsStatusLoading] = useState(true);
  const [sourcePlatform, setSourcePlatform] = useState<ExternalHoldingSourcePlatform>('ths_stock');
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [draftSnapshot, setDraftSnapshot] = useState<ExternalHoldingSnapshotItem | null>(null);
  const [latestSnapshot, setLatestSnapshot] = useState<ExternalHoldingSnapshotItem | null>(null);
  const [editableItems, setEditableItems] = useState<ExternalHoldingPositionInput[]>([]);
  const [reviewNotes, setReviewNotes] = useState('');
  const [isExtracting, setIsExtracting] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isSyncingDoc, setIsSyncingDoc] = useState(false);
  const [error, setError] = useState<ParsedApiError | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const hasDraft = draftSnapshot != null && editableItems.length > 0;
  const featureEnabled = status?.enabled ?? false;

  const loadLatestSnapshot = useCallback(async (nextSource: ExternalHoldingSourcePlatform) => {
    if (!featureEnabled) {
      setLatestSnapshot(null);
      return;
    }
    try {
      const latest = await externalHoldingsApi.getLatest(nextSource);
      setLatestSnapshot(latest);
    } catch (err) {
      const parsed = getParsedApiError(err);
      const message = parsed.message || '';
      if (message.includes('latest snapshot not found') || message.includes('snapshot not found')) {
        setLatestSnapshot(null);
        return;
      }
      setError(parsed);
    }
  }, [featureEnabled]);

  const loadStatus = useCallback(async () => {
    try {
      setIsStatusLoading(true);
      const nextStatus = await externalHoldingsApi.getStatus();
      setStatus(nextStatus);
      setError(null);
    } catch (err) {
      setError(getParsedApiError(err));
      setStatus(null);
    } finally {
      setIsStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  useEffect(() => {
    if (!featureEnabled) {
      return;
    }
    void loadLatestSnapshot(sourcePlatform);
  }, [featureEnabled, loadLatestSnapshot, sourcePlatform]);

  const warningList = useMemo(() => {
    return draftSnapshot?.warnings?.filter(Boolean) ?? [];
  }, [draftSnapshot]);

  const updateItem = <K extends keyof ExternalHoldingPositionInput>(
    index: number,
    key: K,
    value: ExternalHoldingPositionInput[K],
  ) => {
    setEditableItems((prev) =>
      prev.map((item, itemIndex) =>
        itemIndex === index
          ? {
              ...item,
              [key]: value,
              isManuallyEdited: true,
            }
          : item,
      ),
    );
  };

  const handleExtract = async () => {
    if (!imageFile) return;
    try {
      setIsExtracting(true);
      setError(null);
      setSuccessMessage(null);
      const response = await externalHoldingsApi.extractFromImage(sourcePlatform, imageFile);
      setDraftSnapshot(response.snapshot);
      setEditableItems(
        (response.snapshot.positions || []).map((item) => ({
          assetType: item.assetType,
          sourcePlatform: item.sourcePlatform,
          symbol: item.symbol,
          displayName: item.displayName,
          market: item.market,
          quantity: item.quantity,
          marketValue: item.marketValue,
          costBasisTotal: item.costBasisTotal,
          profitAmount: item.profitAmount,
          profitPct: item.profitPct,
          positionWeight: item.positionWeight,
          price: item.price,
          priceDate: item.priceDate,
          confidence: item.confidence,
          isManuallyEdited: item.isManuallyEdited,
          rawPayload: item.rawPayload,
        })),
      );
      setReviewNotes(response.snapshot.reviewNotes || '');
      setSuccessMessage(`已识别 ${response.snapshot.positions.length} 条候选持仓，请检查后确认。`);
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsExtracting(false);
    }
  };

  const handleConfirm = async () => {
    if (!draftSnapshot || editableItems.length === 0) return;
    try {
      setIsConfirming(true);
      setError(null);
      const confirmed = await externalHoldingsApi.confirmSnapshot(draftSnapshot.id, {
        items: editableItems,
        reviewNotes,
        syncDoc: true,
      });
      setDraftSnapshot(confirmed);
      setLatestSnapshot(confirmed);
      setSuccessMessage('截图快照已确认并落库。');
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsConfirming(false);
    }
  };

  const handleSyncDoc = async () => {
    const snapshotId = latestSnapshot?.id ?? draftSnapshot?.id;
    if (!snapshotId) return;
    try {
      setIsSyncingDoc(true);
      setError(null);
      await externalHoldingsApi.syncDoc(snapshotId);
      await loadLatestSnapshot(sourcePlatform);
      setSuccessMessage('已触发飞书文档同步。');
    } catch (err) {
      setError(getParsedApiError(err));
    } finally {
      setIsSyncingDoc(false);
    }
  };

  if (isStatusLoading) {
    return (
      <Card padding="md">
        <h3 className="text-sm font-semibold text-foreground">外部持仓截图快照</h3>
        <p className="mt-2 text-xs text-secondary">正在读取功能状态...</p>
      </Card>
    );
  }

  if (!featureEnabled) {
    return (
      <Card padding="md">
        <h3 className="text-sm font-semibold text-foreground">外部持仓截图快照</h3>
        <p className="mt-2 text-xs text-secondary">
          当前环境尚未开启该功能。请先在环境配置中设置 <code>EXTERNAL_HOLDINGS_ENABLED=true</code>，
          再刷新页面使用。
        </p>
        {status?.mobileUploadHint ? (
          <p className="mt-2 text-xs text-secondary">{status.mobileUploadHint}</p>
        ) : null}
      </Card>
    );
  }

  return (
    <Card padding="md">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-foreground">外部持仓截图快照</h3>
          <p className="mt-1 text-xs text-secondary">
            适合每天手动上传同花顺股票持仓或支付宝基金持仓截图，先生成候选快照，再确认入库并同步飞书文档。
          </p>
          {status?.mobileUploadHint ? (
            <p className="mt-1 text-xs text-secondary">{status.mobileUploadHint}</p>
          ) : null}
        </div>
        {latestSnapshot ? (
          <div className="flex flex-wrap items-center gap-2 text-xs text-secondary">
            <Badge variant={latestSnapshot.status === 'confirmed' ? 'success' : 'warning'}>
              {latestSnapshot.status === 'confirmed' ? '已确认' : latestSnapshot.status}
            </Badge>
            <span>最近快照：{latestSnapshot.snapshotDate}</span>
            <span>市值：{formatMoney(latestSnapshot.totalMarketValue, latestSnapshot.currency)}</span>
          </div>
        ) : null}
      </div>

      <div className="mt-4 grid grid-cols-1 gap-2 lg:grid-cols-[1.1fr_1fr_auto_auto]">
        <select
          className={SELECT_CLASS}
          value={sourcePlatform}
          onChange={(e) => {
            setSourcePlatform(e.target.value as ExternalHoldingSourcePlatform);
            setDraftSnapshot(null);
            setEditableItems([]);
            setReviewNotes('');
            setSuccessMessage(null);
          }}
        >
          {SOURCE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <label className={FILE_PICKER_CLASS}>
          {imageFile ? imageFile.name : '选择截图'}
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={(e) => setImageFile(e.target.files && e.target.files[0] ? e.target.files[0] : null)}
          />
        </label>
        <button type="button" className="btn-secondary" disabled={!imageFile || isExtracting} onClick={() => void handleExtract()}>
          {isExtracting ? '识别中...' : '识别截图'}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!(latestSnapshot?.id || draftSnapshot?.id) || isSyncingDoc}
          onClick={() => void handleSyncDoc()}
        >
          {isSyncingDoc ? '同步中...' : '同步飞书文档'}
        </button>
      </div>

      <div className="mt-3 space-y-2">
        {error ? <InlineAlert variant="danger" title="截图快照操作失败" message={error.message} className="rounded-lg px-3 py-2 text-xs shadow-none" /> : null}
        {successMessage ? <InlineAlert variant="success" message={successMessage} className="rounded-lg px-3 py-2 text-xs shadow-none" /> : null}
        {warningList.length > 0 ? (
          <InlineAlert
            variant="warning"
            title="识别提醒"
            message={warningList.join('；')}
            className="rounded-lg px-3 py-2 text-xs shadow-none"
          />
        ) : null}
      </div>

      {latestSnapshot ? (
        <div className="mt-4 rounded-xl border border-border/60 bg-background/40 px-4 py-3 text-xs text-secondary">
          <div className="flex flex-wrap items-center gap-3">
            <span>最新来源：{sourcePlatform === 'ths_stock' ? '同花顺股票 / ETF' : '支付宝基金'}</span>
            <span>条目数：{latestSnapshot.positions.length}</span>
            <span>盈亏：{formatMoney(latestSnapshot.totalProfit, latestSnapshot.currency)}</span>
            {latestSnapshot.docUrl ? (
              <a
                href={latestSnapshot.docUrl}
                target="_blank"
                rel="noreferrer"
                className="text-primary underline-offset-2 hover:underline"
              >
                打开飞书文档
              </a>
            ) : (
              <span>飞书文档：{latestSnapshot.docSyncStatus || '未同步'}</span>
            )}
          </div>
        </div>
      ) : null}

      {hasDraft ? (
        <div className="mt-4 space-y-3">
          <div className="overflow-x-auto rounded-xl border border-border/60">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-muted/40 text-secondary">
                <tr>
                  <th className="px-3 py-2">类型</th>
                  <th className="px-3 py-2">名称</th>
                  <th className="px-3 py-2">代码</th>
                  <th className="px-3 py-2">数量/份额</th>
                  <th className="px-3 py-2">市值</th>
                  <th className="px-3 py-2">盈亏</th>
                  <th className="px-3 py-2">收益率</th>
                </tr>
              </thead>
              <tbody>
                {editableItems.map((item, index) => (
                  <tr key={`${index}-${item.symbol || item.displayName || 'holding'}`} className="border-t border-border/50">
                    <td className="px-3 py-2">
                      <select
                        className="h-9 w-28 rounded-lg border border-border/60 bg-transparent px-2 text-xs"
                        value={item.assetType}
                        onChange={(e) => updateItem(index, 'assetType', e.target.value as ExternalHoldingPositionInput['assetType'])}
                      >
                        <option value="stock">股票</option>
                        <option value="etf">ETF</option>
                        <option value="fund">基金</option>
                      </select>
                    </td>
                    <td className="px-3 py-2">
                      <input
                        className="h-9 w-36 rounded-lg border border-border/60 bg-transparent px-2 text-xs"
                        value={item.displayName || ''}
                        onChange={(e) => updateItem(index, 'displayName', e.target.value)}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        className="h-9 w-28 rounded-lg border border-border/60 bg-transparent px-2 text-xs uppercase"
                        value={item.symbol || ''}
                        onChange={(e) => updateItem(index, 'symbol', e.target.value.toUpperCase())}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        className="h-9 w-28 rounded-lg border border-border/60 bg-transparent px-2 text-xs"
                        type="number"
                        step="0.0001"
                        value={item.quantity ?? ''}
                        onChange={(e) => updateItem(index, 'quantity', e.target.value === '' ? null : Number(e.target.value))}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        className="h-9 w-32 rounded-lg border border-border/60 bg-transparent px-2 text-xs"
                        type="number"
                        step="0.01"
                        value={item.marketValue ?? ''}
                        onChange={(e) => updateItem(index, 'marketValue', e.target.value === '' ? null : Number(e.target.value))}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        className="h-9 w-32 rounded-lg border border-border/60 bg-transparent px-2 text-xs"
                        type="number"
                        step="0.01"
                        value={item.profitAmount ?? ''}
                        onChange={(e) => updateItem(index, 'profitAmount', e.target.value === '' ? null : Number(e.target.value))}
                      />
                    </td>
                    <td className="px-3 py-2">
                      <input
                        className="h-9 w-28 rounded-lg border border-border/60 bg-transparent px-2 text-xs"
                        type="number"
                        step="0.01"
                        value={item.profitPct ?? ''}
                        onChange={(e) => updateItem(index, 'profitPct', e.target.value === '' ? null : Number(e.target.value))}
                      />
                      <div className="mt-1 text-[11px] text-secondary">
                        {item.confidence} / 权重 {formatPct(item.positionWeight)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <textarea
            className="input-surface input-focus-glow min-h-[92px] w-full rounded-xl border bg-transparent px-4 py-3 text-sm transition-all focus:outline-none"
            placeholder="可选：补充备注，例如“截图来自收盘后”“基金份额已手工修正”等。"
            value={reviewNotes}
            onChange={(e) => setReviewNotes(e.target.value)}
          />

          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-secondary">
            <span>
              当前草稿：{draftSnapshot?.positions.length ?? 0} 条，来源 {sourcePlatform === 'ths_stock' ? '同花顺股票 / ETF' : '支付宝基金'}
            </span>
            <button type="button" className="btn-secondary" disabled={isConfirming} onClick={() => void handleConfirm()}>
              {isConfirming ? '确认中...' : '确认并保存快照'}
            </button>
          </div>
        </div>
      ) : null}
    </Card>
  );
};

export default ExternalHoldingsPanel;
