#!/usr/bin/env python3
"""
Advances in Financial Machine Learning - Labeling & Modeling
与 afml_labeling_modeling.ipynb 保持逻辑一致
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats as ss_stats
import warnings
import os
warnings.filterwarnings('ignore')

# 全局变量
PICS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pics')
os.makedirs(PICS_DIR, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.style.use('seaborn-v0_8-whitegrid')

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier

# 尝试导入XGBoost和LightGBM
try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

try:
    from lightgbm import LGBMClassifier
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False
    print("Warning: TA-Lib not available")


class PurgedKFold:
    """Purged K-Fold CV - 金融时间序列专用，防止数据泄漏

    基于AFML 7.2的实现，在训练集和测试集之间添加缓冲期(embargo)
    避免使用未来信息
    """
    def __init__(self, n_splits=5, pct_embargo=0.01):
        self.n_splits = n_splits
        self.pct_embargo = pct_embargo

    def split(self, X, t1=None, groups=None):
        """Split indices into train/test, applying embargo between them

        Args:
            X: Features array
            t1: Series of exit times for each observation (used for purging)
            groups: Not used, kept for compatibility
        """
        n = X.shape[0]
        stride = n // self.n_splits

        t1_array = t1.values if t1 is not None else None

        for i in range(self.n_splits):
            low = i * stride
            high = min((i + 1) * stride, n)

            if high - low < 2:
                continue

            train_end = low
            test_start = high

            if self.pct_embargo > 0:
                embargo = int(n * self.pct_embargo)
                test_end = min(high + embargo, n)
            else:
                test_end = high

            train_indices = np.arange(0, train_end)
            test_indices = np.arange(test_start, test_end)

            if len(train_indices) == 0 or len(test_indices) == 0:
                continue

            if t1_array is not None:
                train_times = t1_array[train_indices]
                test_times = t1_array[test_indices]

                for j, test_t in enumerate(test_times):
                    if test_t is not None and not pd.isna(test_t):
                        for k, train_t in enumerate(train_times):
                            if train_t is not None and not pd.isna(train_t):
                                if train_t < test_t and train_t >= test_start:
                                    train_indices = train_indices[train_indices != train_indices[k]]

            yield train_indices, test_indices

    def get_n_splits(self):
        return self.n_splits


def volume_bars(df, volume_threshold):
    """基于成交量生成K线
    
    Args:
        df: 原始交易数据，包含price和volume列
        volume_threshold: 每根K线的成交量阈值
    
    Returns:
        生成的Volume Bars DataFrame
    """
    bars = []
    cum_vol = 0
    open_, high_, low_ = None, -float('inf'), float('inf')
    start_time = None
    
    for row in df.itertuples(index=False):
        price = getattr(row, 'price', getattr(row, 'close', None))
        if price is None:
            continue
        volume = getattr(row, 'volume', 0)
        ts = getattr(row, 'transact_time', getattr(row, 'timestamp', None))
        
        if open_ is None:
            open_ = price
            start_time = ts
        
        high_ = max(high_, price)
        low_ = min(low_, price)
        close_ = price
        
        cum_vol += volume
        
        if cum_vol >= volume_threshold:
            bars.append({
                'open': open_,
                'high': high_,
                'low': low_,
                'close': close_,
                'volume': volume_threshold,
                'start_time': start_time,
                'end_time': ts
            })
            
            cum_vol = 0
            open_, high_, low_ = None, -float('inf'), float('inf')
            start_time = None
    
    bars_df = pd.DataFrame(bars)
    if 'start_time' in bars_df:
        bars_df['start_time'] = pd.to_datetime(bars_df['start_time'], unit='ms')
        bars_df['end_time'] = pd.to_datetime(bars_df['end_time'], unit='ms')
        bars_df.set_index('start_time', inplace=True)
    return bars_df


def dollar_bars(df, dollar_threshold):
    """基于成交金额生成K线
    
    Args:
        df: 原始交易数据，包含price和volume列
        dollar_threshold: 每根K线的成交金额阈值
    
    Returns:
        生成的Dollar Bars DataFrame
    """
    bars = []
    cum_dollar = 0
    open_, high_, low_ = None, -float('inf'), float('inf')
    start_time = None
    
    for row in df.itertuples(index=False):
        price = getattr(row, 'price', getattr(row, 'close', None))
        if price is None:
            continue
        volume = getattr(row, 'volume', 0)
        ts = getattr(row, 'transact_time', getattr(row, 'timestamp', None))
        
        dollar = price * volume
        
        if open_ is None:
            open_ = price
            start_time = ts
        
        high_ = max(high_, price)
        low_ = min(low_, price)
        cum_dollar += dollar
        close_ = price
        
        if cum_dollar >= dollar_threshold:
            bars.append({
                'open': open_,
                'high': high_,
                'low': low_,
                'close': close_,
                'dollar': cum_dollar,
                'start_time': start_time,
                'end_time': ts
            })
            
            cum_dollar = 0
            open_, high_, low_ = None, -float('inf'), float('inf')
            start_time = None
    
    bars_df = pd.DataFrame(bars)
    if 'start_time' in bars_df:
        bars_df['start_time'] = pd.to_datetime(bars_df['start_time'], unit='ms')
        bars_df['end_time'] = pd.to_datetime(bars_df['end_time'], unit='ms')
        bars_df.set_index('start_time', inplace=True)
    return bars_df


def fracDiff(series, d, thres=0.01):
    """Fractional Differentiation - 保持记忆性的同时实现平稳性

    基于AFML 5.1的实现，通过分数阶差分使时间序列平稳
    同时保留部分记忆性信息
    """
    weights = getWeights_fracDiff(d, series.shape[0]).flatten()
    weights_normalized = np.cumsum(abs(weights))
    weights_normalized /= weights_normalized[-1]

    skip = weights_normalized[weights_normalized > thres].shape[0]

    result = pd.Series(index=series.index, dtype=float)

    series_values = series.ffill().dropna().values

    for iloc in range(skip, len(series_values)):
        result.iloc[iloc] = np.dot(weights[-(iloc+1):], series_values[:iloc+1])

    return result


def getWeights_fracDiff(d, size):
    """计算分数阶差分的权重

    Args:
        d: 差分阶数
        size: 输出权重数量

    Returns:
        权重数组
    """
    weights = [1.0]
    for k in range(1, size):
        w = -weights[-1] / k * (d - k + 1)
        weights.append(w)

    weights = np.array(weights[::-1]).reshape(-1, 1)
    return weights


def save_figure(fig, filename):
    """保存图表到指定路径"""
    fig.savefig(os.path.join(PICS_DIR, filename), dpi=150)
    plt.close()
    print(f"已保存: {filename}")


def create_model(model_name, random_state=42, scale_pos_weight=1.0):
    """创建不同的分类模型

    Args:
        model_name: 模型名称 ('rf', 'gb', 'xgb', 'lgbm', 'svm', 'lr', 'knn', 'dt')
        random_state: 随机种子
        scale_pos_weight: XGBoost的正样本权重

    Returns:
        初始化的模型实例
    """
    models = {
        'rf': RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=5,
            class_weight='balanced',
            random_state=random_state,
            n_jobs=-1
        ),
        'gb': GradientBoostingClassifier(
            n_estimators=300,
            max_depth=6,
            min_samples_split=10,
            min_samples_leaf=5,
            learning_rate=0.03,
            random_state=random_state
        ),
        'svm': SVC(
            C=1.0,
            kernel='rbf',
            probability=True,
            class_weight='balanced',
            random_state=random_state
        ),
        'lr': LogisticRegression(
            C=1.0,
            class_weight='balanced',
            random_state=random_state,
            max_iter=1000
        ),
        'knn': KNeighborsClassifier(
            n_neighbors=5,
            weights='distance'
        ),
        'dt': DecisionTreeClassifier(
            max_depth=8,
            min_samples_split=10,
            min_samples_leaf=5,
            class_weight='balanced',
            random_state=random_state
        )
    }

    if XGBOOST_AVAILABLE:
        models['xgb'] = XGBClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=random_state,
            use_label_encoder=False,
            eval_metric='logloss',
            scale_pos_weight=scale_pos_weight
        )

    if LIGHTGBM_AVAILABLE:
        models['lgbm'] = LGBMClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.03,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=random_state,
            class_weight='balanced'
        )

    if model_name not in models:
        raise ValueError(f"不支持的模型: {model_name}。可用模型: {list(models.keys())}")

    return models[model_name]


def load_data():
    """加载数据"""
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(base_dir, '..', 'data', 'test_dollar.csv')
    df = pd.read_csv(data_path)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    return df


def get_triple_barrier_labels(df, price_col='close', lookback=20, pt_sl_multiplier=[2, 2], horizon=20):
    """Triple Barrier Method 标签生成 - 增加horizon以减少中性标签"""
    daily_vol = df[price_col].pct_change().rolling(window=lookback).std()
    
    barriers = pd.DataFrame(index=df.index)
    barriers['t1'] = df.index.to_series().shift(-horizon)
    
    if isinstance(pt_sl_multiplier, (list, tuple)):
        pt = daily_vol * float(pt_sl_multiplier[0])
        sl = daily_vol * float(pt_sl_multiplier[1])
    else:
        pt = daily_vol * float(pt_sl_multiplier)
        sl = daily_vol * float(pt_sl_multiplier)
    
    barriers['upper'] = df[price_col] * (1 + pt)
    barriers['lower'] = df[price_col] * (1 - sl)
    
    labels = pd.Series(index=df.index, dtype=int)
    barriers['exit_time'] = pd.NaT
    barriers['exit_price'] = np.nan
    barriers['barrier_return'] = np.nan
    barriers['barrier_log_return'] = np.nan
    barriers['exit_reason'] = None
    barriers['holding_period'] = 0
    
    for idx in df.index:
        if pd.isna(barriers.loc[idx, 't1']) or pd.isna(barriers.loc[idx, 'upper']):
            continue
        
        start_price = df.loc[idx, price_col]
        upper_barrier = barriers.loc[idx, 'upper']
        lower_barrier = barriers.loc[idx, 'lower']
        end_time = barriers.loc[idx, 't1']
        
        if end_time in df.index:
            price_series = df.loc[idx:end_time, price_col]
        else:
            price_series = df.loc[idx:, price_col]
            if len(price_series) > horizon:
                price_series = price_series.iloc[:horizon+1]
        
        label = 0
        exit_time = price_series.index[-1]
        exit_price = price_series.iloc[-1]
        exit_reason = 'time'
        
        for timestamp, price in price_series.iloc[1:].items():
            if price >= upper_barrier:
                label = 1
                exit_time = timestamp
                exit_price = price
                exit_reason = 'upper'
                break
            elif price <= lower_barrier:
                label = -1
                exit_time = timestamp
                exit_price = price
                exit_reason = 'lower'
                break
        
        realized_return = exit_price / start_price - 1
        realized_log_return = np.log(exit_price / start_price) if start_price > 0 else 0
        
        holding_period = (exit_time - idx).days if isinstance(exit_time, pd.Timestamp) else horizon
        
        labels.loc[idx] = label
        barriers.loc[idx, 'exit_time'] = exit_time
        barriers.loc[idx, 'exit_price'] = exit_price
        barriers.loc[idx, 'barrier_return'] = realized_return
        barriers.loc[idx, 'barrier_log_return'] = realized_log_return
        barriers.loc[idx, 'exit_reason'] = exit_reason
        barriers.loc[idx, 'holding_period'] = holding_period
    
    return labels, barriers


def create_features(df, price_col='close', volume_col='volume'):
    """创建特征"""
    df_feat = df.copy()
    
    close = df_feat[price_col].values.astype(np.float64)
    high = df_feat['high'].values.astype(np.float64)
    low = df_feat['low'].values.astype(np.float64)
    volume = df_feat[volume_col].values.astype(np.float64)
    
    df_feat['vol_5'] = df_feat['log_return'].rolling(window=5).std()
    df_feat['vol_10'] = df_feat['log_return'].rolling(window=10).std()
    df_feat['vol_20'] = df_feat['log_return'].rolling(window=20).std()
    
    df_feat['momentum_3'] = talib.ROC(close, timeperiod=3) / 100
    df_feat['momentum_5'] = talib.ROC(close, timeperiod=5) / 100
    df_feat['momentum_10'] = talib.ROC(close, timeperiod=10) / 100
    df_feat['volume_ma_5'] = talib.SMA(volume, timeperiod=5)
    df_feat['volume_ma_10'] = talib.SMA(volume, timeperiod=10)
    df_feat['rsi'] = talib.RSI(close, timeperiod=14)
    min_20 = talib.MIN(low, timeperiod=20)
    max_20 = talib.MAX(high, timeperiod=20) 
    df_feat['price_position'] = (close - min_20) / (max_20 - min_20)
        
    # 添加MACD
    macd, macd_signal, macd_hist = talib.MACD(close)
    df_feat['macd'] = macd
    df_feat['macd_signal'] = macd_signal
    df_feat['macd_hist'] = macd_hist
    
    # 添加布林带
    upper, middle, lower = talib.BBANDS(close, timeperiod=20)
    df_feat['bb_upper'] = upper
    df_feat['bb_middle'] = middle
    df_feat['bb_lower'] = lower
    df_feat['bb_width'] = (upper - lower) / middle
    
    # 添加ATR
    df_feat['atr'] = talib.ATR(high, low, close, timeperiod=14)
    
    # 添加KDJ
    slowk, slowd = talib.STOCH(high, low, close, fastk_period=9, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
    df_feat['kdj_k'] = slowk
    df_feat['kdj_d'] = slowd
    df_feat['kdj_j'] = 3 * slowk - 2 * slowd
   
    
    df_feat['volume_ratio'] = volume / df_feat['volume_ma_10']
    df_feat['high_low_spread'] = (df_feat['high'] - df_feat['low']) / df_feat['close']
    df_feat['open_close_spread'] = (df_feat['close'] - df_feat['open']) / df_feat['close']

    df_feat['hour'] = df_feat.index.hour
    df_feat['day_of_week'] = df_feat.index.dayofweek
    df_feat['month'] = df_feat.index.month

    close_series = df_feat[price_col].dropna()
    if len(close_series) > 50:
        fd_series = fracDiff(close_series, d=0.4, thres=0.01)
        df_feat['frac_diff_04'] = fd_series.reindex(df_feat.index)

        fd_series_06 = fracDiff(close_series, d=0.6, thres=0.01)
        df_feat['frac_diff_06'] = fd_series_06.reindex(df_feat.index)

    return df_feat


def main(model_name='rf'):
    """主函数 - 运行整个策略流程

    Args:
        model_name: 模型名称 ('rf', 'gb', 'xgb', 'lgbm', 'svm', 'lr', 'knn', 'dt')
    """
    print("=" * 60)
    print("Advances in Financial Machine Learning - Labeling & Modeling")
    print("=" * 60)
    
    print("\n1. 加载数据...")
    df = load_data()
    print(f"数据形状: {df.shape}")
    print(f"时间范围: {df.index.min()} 到 {df.index.max()}")

    # ============================================================
    # 可视化1: 原始数据
    # ============================================================
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))
    axes[0].plot(df.index, df['close'], linewidth=0.8)
    axes[0].set_title('Close Price')
    axes[0].set_xlabel('Time')
    axes[0].set_ylabel('Price')
    axes[0].grid(True, alpha=0.3)
    
    axes[1].plot(df.index, df['volume'], linewidth=0.8, color='orange')
    axes[1].set_title('Volume')
    axes[1].set_xlabel('Time')
    axes[1].set_ylabel('Volume')
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    save_figure(fig, '01_price_volume.png')
    
    print("\n2. Volume Clock 处理 (基于AFML 2.1)...")
    # 检查是否有原始交易数据
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    aggtrades_path = os.path.join(base_dir, '..', 'data', 'aggtrades.csv')
    
    if os.path.exists(aggtrades_path):
        print(f"找到原始交易数据: {aggtrades_path}")
        df_agg = pd.read_csv(aggtrades_path)
        print(f"原始交易数据形状: {df_agg.shape}")
        
        # 生成Volume Bars
        volume_threshold = df_agg['volume'].mean() * 10
        print(f"Volume Bar 阈值: {volume_threshold}")
        
        df_volume = volume_bars(df_agg, volume_threshold)
        print(f"Volume Bars 形状: {df_volume.shape}")
        print(f"Volume Bars 时间范围: {df_volume.index.min()} 到 {df_volume.index.max()}")
        
        # 使用Volume Bars进行后续分析
        df = df_volume
    else:
        print("未找到原始交易数据，使用现有数据")
    
    print("\n3. 计算对数收益率...")
    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    df['returns'] = df['close'].pct_change()
    df_clean = df.dropna().copy()
    print(f"清理后数据形状: {df_clean.shape}")
    
    # ============================================================
    # 可视化2: 收益率分布
    # ============================================================
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    axes[0, 0].hist(df_clean['log_return'], bins=100, density=True, alpha=0.7, color='#3498db', edgecolor='white')
    axes[0, 0].set_title('Log Returns Distribution')
    axes[0, 0].axvline(df_clean['log_return'].mean(), color='red', linestyle='--')
    axes[0, 0].grid(True, alpha=0.3)
    
    axes[0, 1].hist(df_clean['returns'], bins=100, density=True, alpha=0.7, color='#2ecc71', edgecolor='white')
    axes[0, 1].set_title('Simple Returns Distribution')
    axes[0, 1].axvline(df_clean['returns'].mean(), color='red', linestyle='--')
    axes[0, 1].grid(True, alpha=0.3)
    
    ss_stats.probplot(df_clean['log_return'], dist="norm", plot=axes[1, 0])
    axes[1, 0].set_title('Q-Q Plot (Log Returns)')
    axes[1, 0].grid(True, alpha=0.3)
    
    axes[1, 1].plot(df_clean.index, df_clean['log_return'], alpha=0.6, color='#9b59b6')
    axes[1, 1].set_title('Log Returns Time Series')
    axes[1, 1].set_xlabel('Time')
    axes[1, 1].set_ylabel('Log Return')
    axes[1, 1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    save_figure(fig, '02_returns_distribution.png')
    
    print("\n4. Triple Barrier 标签生成...")
    labels, barriers = get_triple_barrier_labels(
        df_clean,
        price_col='close',
        lookback=20,
        pt_sl_multiplier=[0, 1],
        horizon=15
    )
    
    df_clean['label'] = labels
    df_clean['tb_return'] = barriers['barrier_return']
    df_clean['tb_log_return'] = barriers['barrier_log_return']
    df_clean['tb_exit_time'] = barriers['exit_time']
    df_clean['tb_exit_reason'] = barriers['exit_reason']
    
    print("标签分布:")
    print(labels.value_counts())
    print(f"\n标签占比:")
    print(labels.value_counts(normalize=True))
    
    print("\n4. 特征工程...")
    df_featured = create_features(df_clean)
    
    feature_cols = [
        'vol_10', 'vol_20', 'vol_5',
        'atr', 'bb_width', 'bb_upper', 'bb_lower',
        'macd', 'macd_signal', 'macd_hist',
        'hour', 'momentum_5', 'momentum_3',
        'rsi', 'frac_diff_04', 'frac_diff_06'
    ]
    
    model_cols = feature_cols + ['label', 'close', 'log_return', 'returns', 'tb_return', 'tb_log_return', 'tb_exit_time', 'tb_exit_reason']
    df_model = df_featured[model_cols].dropna().copy()
    
    print(f"特征工程后数据形状: {df_model.shape}")
    print(f"特征列表: {feature_cols}")
    
    print("\n5. 模型训练与评估 (使用PurgedKFold交叉验证)...")
    X = df_model[feature_cols].values
    y = df_model['label'].values

    # 转换标签：-1 → 0, 1 → 1
    y = np.where(y == -1, 0, y)

    n_samples = len(X)
    train_end = int(n_samples * 0.7)
    val_end = int(n_samples * 0.85)

    X_train, X_val, X_test = X[:train_end], X[train_end:val_end], X[val_end:]
    y_train, y_val, y_test = y[:train_end], y[train_end:val_end], y[val_end:]

    print(f"\n使用PurgedKFold进行时间序列交叉验证 (n_splits=3, pct_embargo=0.02)")
    purged_kfold = PurgedKFold(n_splits=3, pct_embargo=0.02)
    cv_scores = []
    cv_aucs = []

    for fold_idx, (train_idx, test_idx) in enumerate(purged_kfold.split(X_train)):
        if len(train_idx) < 10 or len(test_idx) < 10:
            continue
        X_cv_train, X_cv_test = X_train[train_idx], X_train[test_idx]
        y_cv_train, y_cv_test = y_train[train_idx], y_train[test_idx]

        scaler_cv = StandardScaler()
        X_cv_train_scaled = scaler_cv.fit_transform(X_cv_train)
        X_cv_test_scaled = scaler_cv.transform(X_cv_test)

        cv_neg_count = np.sum(y_cv_train == 0)
        cv_pos_count = np.sum(y_cv_train == 1)
        cv_scale_pos_weight = cv_neg_count / cv_pos_count if cv_pos_count > 0 else 1.0
        
        cv_model = create_model(model_name, scale_pos_weight=cv_scale_pos_weight)
        cv_model.fit(X_cv_train_scaled, y_cv_train)

        cv_pred = cv_model.predict(X_cv_test_scaled)
        cv_proba = cv_model.predict_proba(X_cv_test_scaled)

        cv_acc = (cv_pred == y_cv_test).mean()

        if len(np.unique(y_cv_test)) == 2:
            pos_idx = list(cv_model.classes_).index(1) if 1 in cv_model.classes_ else 0
            cv_auc = roc_auc_score(y_cv_test, cv_proba[:, pos_idx])
        else:
            cv_auc = roc_auc_score(y_cv_test, cv_proba, multi_class='ovr')

        cv_scores.append(cv_acc)
        cv_aucs.append(cv_auc)
        print(f"  Fold {fold_idx + 1}: Accuracy = {cv_acc:.4f}, AUC = {cv_auc:.4f}")

    if len(cv_scores) > 0:
        print(f"  平均CV Accuracy: {np.mean(cv_scores):.4f} (+/- {np.std(cv_scores):.4f})")
        print(f"  平均CV AUC: {np.mean(cv_aucs):.4f} (+/- {np.std(cv_aucs):.4f})")
    else:
        print("  警告: 交叉验证未产生有效结果")

    print(f"\n训练集大小: {X_train.shape}")
    print(f"验证集大小: {X_val.shape}")
    print(f"测试集大小: {X_test.shape}")
    print(f"\n训练集标签分布: {pd.Series(y_train).value_counts().sort_index().to_dict()}")
    print(f"验证集标签分布: {pd.Series(y_val).value_counts().sort_index().to_dict()}")
    print(f"测试集标签分布: {pd.Series(y_test).value_counts().sort_index().to_dict()}")
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)
    
    print("\n" + "=" * 60)
    print(f"主模型: {model_name.upper()} (二分类)")
    print("=" * 60)
    
    neg_count = np.sum(y_train == 0)
    pos_count = np.sum(y_train == 1)
    scale_pos_weight = neg_count / pos_count if pos_count > 0 else 1.0
    print(f"类别平衡权重: scale_pos_weight = {scale_pos_weight:.4f} (负样本={neg_count}, 正样本={pos_count})")
    
    main_model = create_model(model_name, scale_pos_weight=scale_pos_weight)
    main_model.fit(X_train_scaled, y_train)
    main_val_pred = main_model.predict(X_val_scaled)
    main_val_pred_proba = main_model.predict_proba(X_val_scaled)
    main_test_pred = main_model.predict(X_test_scaled)
    main_test_pred_proba = main_model.predict_proba(X_test_scaled)
    
    classes = main_model.classes_
    print(f"主模型类别: {classes}")
    
    target_names = ['Down', 'Up']
    
    # 评估
    print("\nValidation 分类报告:")
    print(classification_report(y_val, main_val_pred, target_names=target_names))
    val_auc = roc_auc_score(y_val, main_val_pred_proba[:, 1])
    print(f"Validation ROC-AUC: {val_auc:.4f}")
    
    print("\nTest 分类报告:")
    print(classification_report(y_test, main_test_pred, target_names=target_names))
    test_auc = roc_auc_score(y_test, main_test_pred_proba[:, 1])
    print(f"Test ROC-AUC: {test_auc:.4f}")
    
    # 特征重要性 (仅对树模型)
    feature_importance = None
    if hasattr(main_model, 'feature_importances_'):
        feature_importance = pd.DataFrame({
            'feature': feature_cols,
            'importance': main_model.feature_importances_
        }).sort_values('importance', ascending=False)
        print("\n特征重要性:")
        print(feature_importance)
    else:
        print("\n注意: 当前模型不支持特征重要性分析")
    
# ============================================================
    # 6. Meta-Labeling - 使用实际未来收益率
    # ============================================================
    print("\n" + "=" * 60)
    print("6. Meta-Labeling")
    print("=" * 60)
    
  
    
    holding_period_meta = 5
    
    df_val = df_model.iloc[train_end:val_end].copy().reset_index(drop=True)
    df_test_meta = df_model.iloc[val_end:].copy().reset_index(drop=True)
    
    df_val['future_return'] = df_val['log_return'].shift(-holding_period_meta)
    df_test_meta['future_return'] = df_test_meta['log_return'].shift(-holding_period_meta)
    
    df_val['main_pred'] = main_val_pred
    up_idx_val = list(classes).index(1) if 1 in classes else 0
    down_idx_val = list(classes).index(-1) if -1 in classes else 0
    df_val['up_proba'] = main_val_pred_proba[:, up_idx_val]
    df_val['down_proba'] = main_val_pred_proba[:, down_idx_val]
    
    df_val_filtered = df_val[(df_val['main_pred'] == 1) | (df_val['main_pred'] == 0)].copy()
    df_val_filtered = df_val_filtered[df_val_filtered['future_return'].notna()].copy()
    df_val_filtered['meta_label'] = (df_val_filtered['future_return'] > 0).astype(int)
    
    print(f"Validation 主模型方向信号数量: {len(df_val_filtered)}")
    print(f"  - 做多信号: {(df_val_filtered['main_pred'] == 1).sum()}")
    print(f"  - 做空信号: {(df_val_filtered['main_pred'] == 0).sum()}")
    print(f"Validation Meta-Labeling 分布:")
    print(df_val_filtered['meta_label'].value_counts())
    
    X_meta_val = df_val_filtered[feature_cols].values
    direction_proba_val = np.where(
        df_val_filtered['main_pred'].values == 1,
        df_val_filtered['up_proba'].values,
        df_val_filtered['down_proba'].values
    )
    X_meta_train = np.column_stack([direction_proba_val, X_meta_val])
    y_meta_train = df_val_filtered['meta_label'].values
    
    meta_model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        min_samples_split=5,
        class_weight='balanced',
        random_state=42,
        n_jobs=-1
    )
    meta_model.fit(X_meta_train, y_meta_train)
    
    df_test_meta['main_pred'] = main_test_pred
    up_idx_test = list(classes).index(1) if 1 in classes else 0
    down_idx_test = list(classes).index(-1) if -1 in classes else 0
    df_test_meta['up_proba'] = main_test_pred_proba[:, up_idx_test]
    df_test_meta['down_proba'] = main_test_pred_proba[:, down_idx_test]
    
    df_test_meta = df_test_meta[(df_test_meta['main_pred'] == 1) | (df_test_meta['main_pred'] == 0)].copy()
    df_test_meta = df_test_meta[df_test_meta['future_return'].notna()].copy()
    df_test_meta['meta_label'] = (df_test_meta['future_return'] > 0).astype(int)
    
    print(f"\nTest 主模型方向信号数量: {len(df_test_meta)}")
    print(f"  - 做多信号: {(df_test_meta['main_pred'] == 1).sum()}")
    print(f"  - 做空信号: {(df_test_meta['main_pred'] == 0).sum()}")
    print(f"Test Meta-Labeling 分布:")
    print(df_test_meta['meta_label'].value_counts())
    
    X_meta_test_base = df_test_meta[feature_cols].values
    test_direction_proba = np.where(
        df_test_meta['main_pred'].values == 1,
        df_test_meta['up_proba'].values,
        df_test_meta['down_proba'].values
    )
    X_meta_test = np.column_stack([test_direction_proba, X_meta_test_base])
    y_meta_test = df_test_meta['meta_label'].values
    
    meta_pred = meta_model.predict(X_meta_test)
    meta_pred_proba = meta_model.predict_proba(X_meta_test)[:, 1]
    
    print("\nMeta Model Test 分类报告:")
    print(classification_report(y_meta_test, meta_pred, target_names=['Do Not Trade', 'Trade']))
    print(f"Test ROC-AUC: {roc_auc_score(y_meta_test, meta_pred_proba):.4f}")
    
    print("\n=== Meta模型分析 ===")
    print(f"Meta模型准确率: {meta_model.score(X_meta_test, y_meta_test):.4f}")
    print(f"平均预测概率: {meta_pred_proba.mean():.4f}")
    print(f"预测为'交易'的比例: {(meta_pred == 1).mean():.2%}")
    
    # ============================================================
    # 7. 回测 (无数据泄漏 - 使用实际未来收益率)
    # ============================================================
    print("\n" + "=" * 60)
    print("7. 回测")
    print("=" * 60)
    
    def bet_size_z_score(p, k=2):
        """基于AFML 10.1的Bet Sizing - Z-Score方法

        Args:
            p: 预测概率
            k: 类别数量 (默认为2，二分类)

        Returns:
            bet_size: 仓位大小
        """
        from scipy.stats import norm
        
        # 方法三：高置信度信号使用固定大手数
        if p > 0.7:
            return 2.0  # 高置信度使用固定大手数
        
        z = (p - 1/k) / np.sqrt(p * (1-p) + 1e-10)
        bet_size = 2 * norm.cdf(z) - 1
        return np.clip(bet_size, -1, 1)

    def calculate_sr(trade_returns):
        """计算Sharpe比率"""
        if len(trade_returns) < 2 or np.std(trade_returns) == 0:
            return 0.0
        return np.mean(trade_returns) / np.std(trade_returns) * np.sqrt(252)

    def calculate_max_drawdown(cumulative_returns):
        """计算最大回撤"""
        peak = cumulative_returns.cummax()
        drawdown = (cumulative_returns - peak) / (peak + 1e-10)
        return drawdown.min()

    def backtest_strategy(df_model, main_model, meta_model, scaler, feature_cols, test_start_idx, classes,
                         holding_period=10, fee_rate=0.00001, slippage=0.00001,
                         min_confidence=0.55, max_position_size=0.3, use_bet_sizing=True):
        """无泄漏回测 - 使用Bet Sizing方法和完整统计指标

        基于AFML 10.1的Bet Sizing方法，根据预测概率动态调整仓位大小
        """
        from scipy.stats import norm

        df_test = df_model.iloc[test_start_idx:].copy().reset_index(drop=True)

        df_test['future_return'] = df_test['log_return'].shift(-holding_period)

        X_test_primary = scaler.transform(df_test[feature_cols].values)

        main_proba_all = main_model.predict_proba(X_test_primary)

        up_idx = list(classes).index(1) if 1 in classes else 0
        down_idx = list(classes).index(-1) if -1 in classes else 0

        up_proba = main_proba_all[:, up_idx]
        down_proba = main_proba_all[:, down_idx]

        df_test['up_proba'] = up_proba
        df_test['down_proba'] = down_proba
        df_test['confidence'] = np.abs(up_proba - down_proba)
        df_test['max_proba'] = np.maximum(up_proba, down_proba)

        df_test['trade_direction'] = 0
        df_test.loc[(up_proba > down_proba) & (up_proba > min_confidence), 'trade_direction'] = 1
        df_test.loc[(down_proba > up_proba) & (down_proba > min_confidence), 'trade_direction'] = 0

        df_test['trade_decision'] = (df_test['trade_direction'] != 0).astype(int)

        df_test['strategy_return'] = 0.0
        df_test['position_size'] = 0.0
        df_test['bet_size'] = 0.0

        trade_mask = df_test['trade_decision'] == 1
        valid_return_mask = df_test['future_return'].notna()

        execute_trades = trade_mask & valid_return_mask

        if use_bet_sizing:
            df_test.loc[execute_trades, 'bet_size'] = df_test.loc[execute_trades].apply(
                lambda row: bet_size_z_score(row['max_proba'], k=2), axis=1
            )
            df_test.loc[execute_trades, 'position_size'] = (
                np.abs(df_test.loc[execute_trades, 'bet_size']) * max_position_size
            )
        else:
            df_test.loc[execute_trades, 'position_size'] = max_position_size

        df_test.loc[execute_trades, 'strategy_return'] = np.where(
            df_test.loc[execute_trades, 'trade_direction'] == 1,
            df_test.loc[execute_trades, 'future_return'] * df_test.loc[execute_trades, 'position_size'],
            -df_test.loc[execute_trades, 'future_return'] * df_test.loc[execute_trades, 'position_size']
        )

        df_test['strategy_return'] -= fee_rate * 2

        df_test['strategy_return_simple'] = np.exp(df_test['strategy_return']) - 1
        df_test['cumulative_return'] = df_test['strategy_return'].cumsum()
        df_test['equity_curve'] = (1 + df_test['strategy_return_simple']).cumprod()

        peak = df_test['equity_curve'].cummax()
        df_test['drawdown'] = (df_test['equity_curve'] - peak) / peak

        return df_test

    def calculate_full_stats(df_backtest, executed_trades):
        """计算完整的回测统计指标

        基于AFML 14.1的回测统计方法
        """
        stats_dict = {}

        total_trades = df_backtest['trade_decision'].sum()
        winning_trades = (executed_trades['strategy_return'] > 0).sum()
        losing_trades = (executed_trades['strategy_return'] < 0).sum()

        stats_dict['total_trades'] = total_trades
        stats_dict['winning_trades'] = winning_trades
        stats_dict['losing_trades'] = losing_trades
        stats_dict['win_rate'] = winning_trades / total_trades if total_trades > 0 else 0

        avg_win = executed_trades[executed_trades['strategy_return'] > 0]['strategy_return'].mean() if winning_trades > 0 else 0
        avg_loss = executed_trades[executed_trades['strategy_return'] < 0]['strategy_return'].mean() if losing_trades > 0 else 0
        stats_dict['avg_win'] = avg_win
        stats_dict['avg_loss'] = avg_loss
        stats_dict['profit_factor'] = abs(avg_win / avg_loss) if avg_loss != 0 else 0

        stats_dict['total_return_log'] = df_backtest['cumulative_return'].iloc[-1]
        stats_dict['total_return_simple'] = np.exp(stats_dict['total_return_log']) - 1

        returns_array = executed_trades['strategy_return'].values
        stats_dict['sharpe_ratio'] = calculate_sr(returns_array)
        stats_dict['sortino_ratio'] = calculate_sr(returns_array[returns_array < 0]) if len(returns_array[returns_array < 0]) > 0 else 0

        stats_dict['max_drawdown'] = calculate_max_drawdown(df_backtest['equity_curve'])
        stats_dict['calmar_ratio'] = stats_dict['total_return_log'] / abs(stats_dict['max_drawdown']) if stats_dict['max_drawdown'] != 0 else 0

        stats_dict['avg_trade_return'] = executed_trades['strategy_return_simple'].mean() if len(executed_trades) > 0 else 0
        stats_dict['std_trade_return'] = executed_trades['strategy_return_simple'].std() if len(executed_trades) > 0 else 0

        long_trades = ((df_backtest['trade_direction'] == 1) & (df_backtest['trade_decision'] == 1)).sum()
        short_trades = ((df_backtest['trade_direction'] == -1) & (df_backtest['trade_decision'] == 1)).sum()
        stats_dict['long_trades'] = long_trades
        stats_dict['short_trades'] = short_trades

        return stats_dict

    df_backtest = backtest_strategy(df_model, main_model, meta_model, scaler, feature_cols, val_end, classes,
                                     holding_period=30, fee_rate=0.000005,
                                     min_confidence=0.55, max_position_size=0.3, use_bet_sizing=True)

    executed_trades = df_backtest[df_backtest['trade_decision'] == 1].copy()

    print("\n策略表现统计")
    print("=" * 60)

    long_trades = ((df_backtest['trade_direction'] == 1) & (df_backtest['trade_decision'] == 1)).sum()
    short_trades = ((df_backtest['trade_direction'] == 0) & (df_backtest['trade_decision'] == 1)).sum()

    total_trades = df_backtest['trade_decision'].sum()
    winning_trades = (executed_trades['strategy_return'] > 0).sum()
    total_return = df_backtest['cumulative_return'].iloc[-1]
    avg_trade_return = executed_trades['strategy_return_simple'].mean() if len(executed_trades) > 0 else 0

    print(f"做多次数: {long_trades}")
    print(f"做空次数: {short_trades}")
    print(f"总交易次数: {total_trades}")
    print(f"盈利交易次数: {winning_trades}")
    print(f"亏损交易次数: {(executed_trades['strategy_return'] < 0).sum()}")
    print(f"胜率: {winning_trades/total_trades:.2%}" if total_trades > 0 else "胜率: N/A")
    print(f"平均收益: {avg_trade_return:.2%}" if total_trades > 0 else "平均收益: N/A")

    print(f"\n累计收益 (log): {total_return:.4f}")
    print(f"累积收益 (simple): {np.exp(total_return)-1:.2%}")

    stats = calculate_full_stats(df_backtest, executed_trades)
    print(f"\n高级统计指标 (基于AFML 14.1)")
    print("-" * 60)
    print(f"Sharpe比率: {stats['sharpe_ratio']:.4f}")
    print(f"Sortino比率: {stats['sortino_ratio']:.4f}")
    print(f"最大回撤: {stats['max_drawdown']:.2%}")
    print(f"Calmar比率: {stats['calmar_ratio']:.4f}")
    print(f"盈亏比: {stats['profit_factor']:.4f}")
    print(f"平均盈利: {stats['avg_win']:.4f}")
    print(f"平均亏损: {stats['avg_loss']:.4f}")
    print(f"收益标准差: {stats['std_trade_return']:.4f}")
    
    # ============================================================
    # 可视化4: 回测结果
    # ============================================================
    fig, axes = plt.subplots(2, 1, figsize=(14, 10))
    
    axes[0].plot(df_backtest.index, df_backtest['cumulative_return'], 
                color='#2ecc71', linewidth=2, label='Strategy Cumulative Return')
    axes[0].axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    axes[0].set_title('Strategy Cumulative Returns', fontsize=14, fontweight='bold')
    axes[0].set_xlabel('Time')
    axes[0].set_ylabel('Cumulative Log Return')
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()
    
    trade_signals = df_backtest[df_backtest['trade_decision'] == 1]
    colors = ['#2ecc71' if d == 1 else '#e74c3c' for d in trade_signals['trade_direction']]
    axes[1].scatter(trade_signals.index, trade_signals['close'], 
                   c=colors, s=30, alpha=0.6, label='Trade Signals')
    axes[1].plot(df_backtest.index, df_backtest['close'], 
                color='#3498db', alpha=0.3, linewidth=1, label='Close Price')
    axes[1].set_title('Trade Signals on Price Chart', fontsize=14, fontweight='bold')
    axes[1].set_xlabel('Time')
    axes[1].set_ylabel('Price')
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()
    
    plt.tight_layout()
    save_figure(fig, '04_backtest_result.png')
    
    # ============================================================
    # 可视化5: 特征重要性
    # ============================================================
    if feature_importance is not None:
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(feature_importance['feature'], feature_importance['importance'])
        ax.set_title(f'Feature Importance ({model_name.upper()})')
        ax.set_xlabel('Importance')
        plt.tight_layout()
        save_figure(fig, '05_feature_importance.png')
    else:
        print("跳过特征重要性可视化: 当前模型不支持")
    
    # ============================================================
    # 可视化6: 特征与标签相关性
    # ============================================================
    corr_with_label = df_model[feature_cols + ['label']].corr()['label'].drop('label').sort_values(key=abs, ascending=False)
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    axes[0].barh(range(len(corr_with_label)), corr_with_label.values,
             color=['#e74c3c' if x < 0 else '#2ecc71' for x in corr_with_label.values])
    axes[0].set_yticks(range(len(corr_with_label)))
    axes[0].set_yticklabels(corr_with_label.index)
    axes[0].set_xlabel('Correlation with Label')
    axes[0].set_title('Feature Correlation with Label')
    axes[0].axvline(x=0, color='black', linestyle='-', linewidth=0.5)
    axes[0].grid(True, alpha=0.3, axis='x')
    
    corr_matrix = df_model[feature_cols].corr()
    im = axes[1].imshow(corr_matrix, cmap='RdBu_r', aspect='auto', vmin=-1, vmax=1)
    axes[1].set_xticks(range(len(feature_cols)))
    axes[1].set_xticklabels(feature_cols, rotation=45, ha='right')
    axes[1].set_yticks(range(len(feature_cols)))
    axes[1].set_yticklabels(feature_cols)
    axes[1].set_title('Feature Correlation Matrix')
    plt.colorbar(im, ax=axes[1], fraction=0.046, pad=0.04)
    
    plt.tight_layout()
    save_figure(fig, '06_feature_correlation.png')
    
    print("\n" + "=" * 60)
    print("完成! 所有图片已保存.")
    print("=" * 60)
    
    return {
        'main_model': main_model,
        'meta_model': meta_model,
        'scaler': scaler,
        'feature_cols': feature_cols,
        'df_model': df_model,
        'X_test': X_test_scaled,
        'y_test': y_test,
        'classes': classes
    }


if __name__ == '__main__':
    import sys
    #model_name: 模型名称 ('rf', 'gb', 'xgb', 'lgbm', 'svm', 'lr', 'knn', 'dt')
    model_name = 'lgbm'  
    if len(sys.argv) > 1:
        model_name = sys.argv[1].lower()
    print(f"使用模型: {model_name}")
    results = main(model_name)