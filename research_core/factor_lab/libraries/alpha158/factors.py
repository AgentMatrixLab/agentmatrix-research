"""
Alpha158 因子完整实现
====================

公式严格还原自 Qlib qlib/contrib/data/loader.py 的 Alpha158DL 定义。
默认配置: kbar=true, price={windows:[0], feature:[OPEN,HIGH,LOW,VWAP]}, rolling={windows:[5,10,20,30,60]}

与 Qlib 内置 Alpha158 在 2018-2020 沪深300 数据上逐因子逐点位对照验证。
"""
import numpy as np
import pandas as pd

# ============================================================
# 因子分类
# ============================================================
FACTOR_CATEGORIES = {
    "K-bar":      ["KMID","KLEN","KMID2","KUP","KUP2","KLOW","KLOW2","KSFT","KSFT2"],
    "Price":      ["OPEN0","HIGH0","LOW0","VWAP0"],
    "ROC":        ["ROC5","ROC10","ROC20","ROC30","ROC60"],
    "MA":         ["MA5","MA10","MA20","MA30","MA60"],
    "STD":        ["STD5","STD10","STD20","STD30","STD60"],
    "BETA":       ["BETA5","BETA10","BETA20","BETA30","BETA60"],
    "RSQR":       ["RSQR5","RSQR10","RSQR20","RSQR30","RSQR60"],
    "RESI":       ["RESI5","RESI10","RESI20","RESI30","RESI60"],
    "MAX":        ["MAX5","MAX10","MAX20","MAX30","MAX60"],
    "MIN":        ["MIN5","MIN10","MIN20","MIN30","MIN60"],
    "QTLU":       ["QTLU5","QTLU10","QTLU20","QTLU30","QTLU60"],
    "QTLD":       ["QTLD5","QTLD10","QTLD20","QTLD30","QTLD60"],
    "RANK":       ["RANK5","RANK10","RANK20","RANK30","RANK60"],
    "RSV":        ["RSV5","RSV10","RSV20","RSV30","RSV60"],
    "IMAX":       ["IMAX5","IMAX10","IMAX20","IMAX30","IMAX60"],
    "IMIN":       ["IMIN5","IMIN10","IMIN20","IMIN30","IMIN60"],
    "IMXD":       ["IMXD5","IMXD10","IMXD20","IMXD30","IMXD60"],
    "CORR":       ["CORR5","CORR10","CORR20","CORR30","CORR60"],
    "CORD":       ["CORD5","CORD10","CORD20","CORD30","CORD60"],
    "CNTP":       ["CNTP5","CNTP10","CNTP20","CNTP30","CNTP60"],
    "CNTN":       ["CNTN5","CNTN10","CNTN20","CNTN30","CNTN60"],
    "CNTD":       ["CNTD5","CNTD10","CNTD20","CNTD30","CNTD60"],
    "SUMP":       ["SUMP5","SUMP10","SUMP20","SUMP30","SUMP60"],
    "SUMN":       ["SUMN5","SUMN10","SUMN20","SUMN30","SUMN60"],
    "SUMD":       ["SUMD5","SUMD10","SUMD20","SUMD30","SUMD60"],
    "VMA":        ["VMA5","VMA10","VMA20","VMA30","VMA60"],
    "VSTD":       ["VSTD5","VSTD10","VSTD20","VSTD30","VSTD60"],
    "WVMA":       ["WVMA5","WVMA10","WVMA20","WVMA30","WVMA60"],
    "VSUMP":      ["VSUMP5","VSUMP10","VSUMP20","VSUMP30","VSUMP60"],
    "VSUMN":      ["VSUMN5","VSUMN10","VSUMN20","VSUMN30","VSUMN60"],
    "VSUMD":      ["VSUMD5","VSUMD10","VSUMD20","VSUMD30","VSUMD60"],
}

ALL_FACTORS = []
for names in FACTOR_CATEGORIES.values():
    ALL_FACTORS.extend(names)

WINDOWS = [5, 10, 20, 30, 60]


def get_factor_names():
    """返回全部 158 个因子名列表"""
    return ALL_FACTORS.copy()


def get_factor_categories():
    """返回因子分类字典 {category: [factor_names]}"""
    return {k: v.copy() for k, v in FACTOR_CATEGORIES.items()}


# ============================================================
# 辅助函数
# ============================================================

def _to_wide(series, index_ref):
    """将 MultiIndex Series 转为 wide matrix (dates × instruments)"""
    return series.unstack(level='instrument')


def _to_long(wide, index_ref):
    """将 wide matrix 转回 MultiIndex Series，对齐 index_ref"""
    result = wide.stack(future_stack=True)
    return result.reindex(index_ref)


def _rolling_ols(wide_c, window):
    """线性回归 slope/rsquare/residual"""
    n_date, n_inst = wide_c.shape
    x_arr = np.arange(window, dtype=float)
    slope = np.full_like(wide_c.values, np.nan)
    rsqr = np.full_like(wide_c.values, np.nan)
    resid = np.full_like(wide_c.values, np.nan)
    for j in range(n_inst):
        col = wide_c.values[:, j]
        for i in range(window - 1, n_date):
            yw = col[i - window + 1 : i + 1]
            mask = ~np.isnan(yw)
            if mask.sum() < 2:
                continue
            yv = yw[mask]; xv = x_arr[mask]
            xc = xv - xv.mean(); yc = yv - yv.mean()
            denom = np.sum(xc ** 2)
            if denom == 0:
                continue
            s = np.sum(xc * yc) / denom
            intercept = yv.mean() - s * xv.mean()
            pred = s * xv + intercept
            ss_res = np.sum((yv - pred) ** 2)
            ss_tot = np.sum(yc ** 2)
            slope[i, j] = s
            rsqr[i, j] = 1.0 - ss_res / ss_tot if ss_tot != 0 else np.nan
            resid[i, j] = col[i] - (s * (window - 1) + intercept)
    return slope, rsqr, resid


def _rolling_rank_wide(wide_c, window):
    """Rank = pandas rolling.rank(pct=True) = (n_below+(n_equal+1)/2)/n"""
    n_date, n_inst = wide_c.shape
    result = np.full_like(wide_c.values, np.nan)
    for j in range(n_inst):
        col = wide_c.values[:, j]
        for i in range(window - 1, n_date):
            w = col[i - window + 1 : i + 1]
            val = col[i]
            valid = w[~np.isnan(w)]
            if len(valid) < window:
                continue
            n_below = np.sum(valid < val)
            n_equal = np.sum(valid == val)
            result[i, j] = (n_below + (n_equal + 1) / 2) / len(valid)
    return result


def _rolling_idx_extreme(wide_h, wide_l, window):
    """IMAX/IMIN: argmax()+1 (1-indexed), oldest→newest"""
    n_date, n_inst = wide_h.shape
    imax = np.full_like(wide_h.values, np.nan)
    imin = np.full_like(wide_l.values, np.nan)
    for j in range(n_inst):
        hcol = wide_h.values[:, j]
        lcol = wide_l.values[:, j]
        for i in range(window - 1, n_date):
            hw = hcol[i - window + 1 : i + 1]
            lw = lcol[i - window + 1 : i + 1]
            if np.all(np.isnan(hw)):
                continue
            mx = np.nanmax(hw); mn = np.nanmin(lw)
            for k in range(window):
                if not np.isnan(hw[k]) and hw[k] == mx:
                    imax[i, j] = k + 1
                    break
            for k in range(window):
                if not np.isnan(lw[k]) and lw[k] == mn:
                    imin[i, j] = k + 1
                    break
    imxd = imax - imin
    return imax, imin, imxd


def _rolling_corr_wide(wide_a, wide_b, window):
    """Pearson correlation over rolling window"""
    n_date, n_inst = wide_a.shape
    result = np.full_like(wide_a.values, np.nan)
    for j in range(n_inst):
        acol = wide_a.values[:, j]; bcol = wide_b.values[:, j]
        for i in range(window - 1, n_date):
            aw = acol[i - window + 1 : i + 1]
            bw = bcol[i - window + 1 : i + 1]
            mask = ~np.isnan(aw) & ~np.isnan(bw)
            if mask.sum() < 2:
                continue
            av = aw[mask]; bv = bw[mask]
            ac = av - av.mean(); bc = bv - bv.mean()
            den = np.sqrt(np.sum(ac**2) * np.sum(bc**2))
            result[i, j] = np.sum(ac * bc) / den if den != 0 else np.nan
    return result


# ============================================================
# 主计算函数
# ============================================================

def compute_alpha158(raw_df, windows=None):
    """计算全部 Alpha158 因子

    Parameters
    ----------
    raw_df : pd.DataFrame
        MultiIndex (datetime, instrument) 的原始 OHLCV 数据。
        必须包含列: open, high, low, close, vwap, volume
    windows : list[int], optional
        滚动窗口列表，默认 [5, 10, 20, 30, 60]

    Returns
    -------
    pd.DataFrame
        MultiIndex (datetime, instrument) 的 158 个因子值
    """
    if windows is None:
        windows = WINDOWS

    df = raw_df.copy()
    o, h, l, c, vw, vol = df['open'], df['high'], df['low'], df['close'], df['vwap'], df['volume']
    result = {}

    # ---- K-bar (9) ----
    result['KMID']  = (c - o) / o
    result['KLEN']  = (h - l) / o
    result['KMID2'] = (c - o) / (h - l + 1e-12)
    result['KUP']   = (h - np.maximum(o, c)) / o
    result['KUP2']  = (h - np.maximum(o, c)) / (h - l + 1e-12)
    result['KLOW']  = (np.minimum(o, c) - l) / o
    result['KLOW2'] = (np.minimum(o, c) - l) / (h - l + 1e-12)
    result['KSFT']  = (2 * c - h - l) / o
    result['KSFT2'] = (2 * c - h - l) / (h - l + 1e-12)

    # ---- Price (4) ----
    result['OPEN0'] = o / c
    result['HIGH0'] = h / c
    result['LOW0']  = l / c
    result['VWAP0'] = vw / c

    # ---- Rolling (29 × len(windows)) ----
    wide_c = _to_wide(c, df.index)
    wide_h = _to_wide(h, df.index)
    wide_l = _to_wide(l, df.index)
    wide_v = _to_wide(vol, df.index)

    for d in windows:
        rc = c.groupby(level='instrument')
        rh = h.groupby(level='instrument')
        rl = l.groupby(level='instrument')
        rv = vol.groupby(level='instrument')

        close_ma = rc.rolling(d, min_periods=d).mean().droplevel(0)
        close_std = rc.rolling(d, min_periods=d).std().droplevel(0)
        high_max = rh.rolling(d, min_periods=d).max().droplevel(0)
        low_min = rl.rolling(d, min_periods=d).min().droplevel(0)
        close_q80 = rc.rolling(d, min_periods=d).quantile(0.8).droplevel(0)
        close_q20 = rc.rolling(d, min_periods=d).quantile(0.2).droplevel(0)
        shifted_c = rc.shift(d)
        shifted_vol = rv.shift(1)

        # ROC / MA / STD
        result[f'ROC{d}'] = shifted_c / c
        result[f'MA{d}']  = close_ma / c
        result[f'STD{d}'] = close_std / c

        # BETA / RSQR / RESI
        slope_arr, rsqr_arr, resid_arr = _rolling_ols(wide_c, d)
        result[f'BETA{d}'] = _to_long(pd.DataFrame(slope_arr, index=wide_c.index, columns=wide_c.columns), c.index) / c
        result[f'RSQR{d}'] = _to_long(pd.DataFrame(rsqr_arr, index=wide_c.index, columns=wide_c.columns), c.index)
        result[f'RESI{d}'] = _to_long(pd.DataFrame(resid_arr, index=wide_c.index, columns=wide_c.columns), c.index) / c

        # MAX / MIN / QTLU / QTLD / RSV
        result[f'MAX{d}']  = high_max / c
        result[f'MIN{d}']  = low_min / c
        result[f'QTLU{d}'] = close_q80 / c
        result[f'QTLD{d}'] = close_q20 / c
        result[f'RSV{d}']  = (c - low_min) / (high_max - low_min + 1e-12)

        # RANK
        rank_arr = _rolling_rank_wide(wide_c, d)
        result[f'RANK{d}'] = _to_long(pd.DataFrame(rank_arr, index=wide_c.index, columns=wide_c.columns), c.index)

        # IMAX / IMIN / IMXD
        imax_arr, imin_arr, imxd_arr = _rolling_idx_extreme(wide_h, wide_l, d)
        result[f'IMAX{d}'] = _to_long(pd.DataFrame(imax_arr, index=wide_h.index, columns=wide_h.columns), c.index) / d
        result[f'IMIN{d}'] = _to_long(pd.DataFrame(imin_arr, index=wide_l.index, columns=wide_l.columns), c.index) / d
        result[f'IMXD{d}'] = _to_long(pd.DataFrame(imxd_arr, index=wide_h.index, columns=wide_h.columns), c.index) / d

        # CORR
        log_vol = np.log(vol + 1)
        wide_logvol = _to_wide(log_vol, df.index)
        corr_arr = _rolling_corr_wide(wide_c, wide_logvol, d)
        result[f'CORR{d}'] = _to_long(pd.DataFrame(corr_arr, index=wide_c.index, columns=wide_c.columns), c.index)

        # CORD
        ret_c = c / rc.shift(1)
        ret_v = vol / rv.shift(1)
        wide_retc = _to_wide(ret_c, df.index)
        wide_retv = _to_wide(ret_v, df.index)
        log_retv = np.log(wide_retv.values + 1)
        wide_logretv = pd.DataFrame(log_retv, index=wide_retv.index, columns=wide_retv.columns)
        cord_arr = _rolling_corr_wide(wide_retc, wide_logretv, d)
        result[f'CORD{d}'] = _to_long(pd.DataFrame(cord_arr, index=wide_c.index, columns=wide_c.columns), c.index)

        # CNTP / CNTN / CNTD
        up = (c > rc.shift(1)).astype(float)
        dn = (c < rc.shift(1)).astype(float)
        cntp = up.groupby(level='instrument').rolling(d, min_periods=d).mean().droplevel(0)
        cntn = dn.groupby(level='instrument').rolling(d, min_periods=d).mean().droplevel(0)
        result[f'CNTP{d}'] = cntp
        result[f'CNTN{d}'] = cntn
        result[f'CNTD{d}'] = cntp - cntn

        # SUMP / SUMN / SUMD
        delta_c = c - rc.shift(1)
        gain = np.maximum(delta_c, 0)
        loss = np.maximum(-delta_c, 0)
        abs_d = np.abs(delta_c)
        sg = gain.groupby(level='instrument').rolling(d, min_periods=d).sum().droplevel(0)
        sl = loss.groupby(level='instrument').rolling(d, min_periods=d).sum().droplevel(0)
        sa = abs_d.groupby(level='instrument').rolling(d, min_periods=d).sum().droplevel(0)
        result[f'SUMP{d}'] = sg / (sa + 1e-12)
        result[f'SUMN{d}'] = sl / (sa + 1e-12)
        result[f'SUMD{d}'] = (sg - sl) / (sa + 1e-12)

        # VMA / VSTD
        vol_ma = rv.rolling(d, min_periods=d).mean().droplevel(0)
        vol_std = rv.rolling(d, min_periods=d).std().droplevel(0)
        result[f'VMA{d}']  = vol_ma / (vol + 1e-12)
        result[f'VSTD{d}'] = vol_std / (vol + 1e-12)

        # WVMA
        abs_ret_vol = np.abs(c / rc.shift(1) - 1) * vol
        wvma_std = abs_ret_vol.groupby(level='instrument').rolling(d, min_periods=d).std().droplevel(0)
        wvma_mean = abs_ret_vol.groupby(level='instrument').rolling(d, min_periods=d).mean().droplevel(0)
        result[f'WVMA{d}'] = wvma_std / (wvma_mean + 1e-12)

        # VSUMP / VSUMN / VSUMD
        delta_v = vol - shifted_vol
        vg = np.maximum(delta_v, 0)
        vl = np.maximum(-delta_v, 0)
        va = np.abs(delta_v)
        vsg = vg.groupby(level='instrument').rolling(d, min_periods=d).sum().droplevel(0)
        vsl = vl.groupby(level='instrument').rolling(d, min_periods=d).sum().droplevel(0)
        vsa = va.groupby(level='instrument').rolling(d, min_periods=d).sum().droplevel(0)
        result[f'VSUMP{d}'] = vsg / (vsa + 1e-12)
        result[f'VSUMN{d}'] = vsl / (vsa + 1e-12)
        result[f'VSUMD{d}'] = (vsg - vsl) / (vsa + 1e-12)

    return pd.DataFrame(result, index=df.index)
