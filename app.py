"""
Поиск цен по прайс-листу | Streamlit + Pandas + PostgreSQL/SQLite
"""

import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

TABLE_NAME = "products"

# Локально → SQLite. На Streamlit Cloud → PostgreSQL из секрета DATABASE_URL
_raw_url = os.environ.get("DATABASE_URL", f"sqlite:///price_list.db")
# Neon и Heroku отдают postgres://, SQLAlchemy требует postgresql://
if _raw_url.startswith("postgres://"):
    _raw_url = _raw_url.replace("postgres://", "postgresql://", 1)
engine = create_engine(_raw_url, pool_pre_ping=True)

# ──────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────

CSS = """
<style>
#MainMenu, footer, .stDeployButton { visibility: hidden; }
.block-container { padding: 1.8rem 2.5rem 3rem; max-width: 1400px; }

.app-title { font-size: 26px; font-weight: 700; color: #f0f4ff; margin: 0 0 16px; }

.stats-row { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
.stat-pill {
    background: #1a1f2e; border: 1px solid #2a3045;
    border-radius: 10px; padding: 10px 20px;
    display: flex; flex-direction: column; gap: 2px;
}
.stat-label { font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; }
.stat-value { font-size: 22px; font-weight: 700; color: #60a5fa; line-height: 1.2; }
.stat-value.sm { font-size: 15px; padding-top: 4px; }

.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid #2a3045; }
.stTabs [data-baseweb="tab"] {
    background: transparent; border-radius: 8px 8px 0 0;
    padding: 8px 20px; font-weight: 500; color: #94a3b8;
}
.stTabs [aria-selected="true"] { background: #1e3a5f !important; color: #60a5fa !important; }

.stTextInput input {
    background: #1a1f2e !important; border: 1.5px solid #2a3045 !important;
    border-radius: 8px !important; color: #e2e8f0 !important;
    font-size: 15px !important; padding: 10px 14px !important;
    transition: border-color .2s;
}
.stTextInput input:focus { border-color: #3b82f6 !important; box-shadow: 0 0 0 3px #3b82f620 !important; }

.stButton button { border-radius: 8px !important; font-weight: 500 !important; }

.tbl-wrap {
    border-radius: 10px; overflow: auto;
    border: 1px solid #2a3045; margin-top: 8px; max-height: 62vh;
}
.ptable { width: 100%; border-collapse: collapse; background: #131720; }
.ptable thead tr { position: sticky; top: 0; z-index: 2; }
.ptable th {
    background: #1a2035; color: #64748b;
    padding: 10px 16px; text-align: left;
    font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.6px;
    border-bottom: 2px solid #2a3045; white-space: nowrap;
}
.ptable td { padding: 8px 16px; color: #cbd5e1; border-bottom: 1px solid #1e2435; vertical-align: middle; }
.ptable tr:last-child td { border-bottom: none; }
.ptable tr:hover td { background: #1e2a45; }
.td-cat   { color: #60a5fa !important; font-size: 0.88em; white-space: nowrap; }
.td-qty   { color: #94a3b8 !important; font-size: 0.9em; white-space: nowrap; }
.td-price { color: #34d399 !important; font-weight: 600; text-align: right; white-space: nowrap; }
.td-dash  { color: #374151 !important; text-align: right; }
mark.hl   { background: #f59e0b25; color: #fbbf24; border-radius: 3px; padding: 0 2px; }

.empty-state {
    text-align: center; padding: 52px 0; color: #4b5563;
}
.empty-state .icon { font-size: 40px; margin-bottom: 10px; }
.empty-state .msg  { font-size: 15px; }

.font-badge {
    background: #1a1f2e; border: 1px solid #2a3045;
    border-radius: 6px; padding: 4px 10px;
    color: #94a3b8; font-size: 13px;
    text-align: center; line-height: 1.8;
}
.res-info { font-size: 13px; color: #94a3b8; margin: 10px 0 4px; }
.res-info strong { color: #e2e8f0; }

.tbl-wrap::-webkit-scrollbar { width: 6px; height: 6px; }
.tbl-wrap::-webkit-scrollbar-track { background: #131720; }
.tbl-wrap::-webkit-scrollbar-thumb { background: #2a3045; border-radius: 3px; }
</style>
"""

# ──────────────────────────────────────────────────────
# БД
# ──────────────────────────────────────────────────────

def init_db() -> None:
    with engine.begin() as con:
        con.execute(text(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        ))


def save_products(df: pd.DataFrame) -> int:
    with engine.begin() as con:
        df.to_sql(TABLE_NAME, con, if_exists="replace", index=False)
        con.execute(
            text("INSERT INTO meta (key, value) VALUES ('last_upload', :v) "
                 "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"),
            {"v": datetime.now().strftime("%d.%m.%Y %H:%M")}
        )
    return len(df)


def get_meta(key: str) -> str:
    try:
        with engine.connect() as con:
            r = con.execute(
                text("SELECT value FROM meta WHERE key = :k"), {"k": key}
            ).fetchone()
        return r[0] if r else "—"
    except Exception:
        return "—"


def get_total() -> int:
    try:
        with engine.connect() as con:
            return con.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME}")).fetchone()[0]
    except Exception:
        return 0


def get_categories() -> list[str]:
    try:
        with engine.connect() as con:
            rows = con.execute(text(
                f'SELECT DISTINCT "Категория" FROM {TABLE_NAME} ORDER BY "Категория"'
            )).fetchall()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def search_db(query: str, category: str) -> pd.DataFrame:
    conditions, params = [], {}
    if query:
        conditions.append('LOWER("Наименование") LIKE LOWER(:q)')
        params["q"] = f"%{query}%"
    if category:
        conditions.append('"Категория" = :cat')
        params["cat"] = category
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with engine.connect() as con:
        return pd.read_sql_query(
            text(f'SELECT * FROM {TABLE_NAME} {where}'), con, params=params
        )


# ──────────────────────────────────────────────────────
# ПАРСИНГ EXCEL
# ──────────────────────────────────────────────────────

_NAME_KW  = ["наим", "назван", "модел", "товар", "описан"]
_QTY_KW   = ["кол", "количест", "упак", "кор"]
_PRICE_KW = ["цена", "price", "стоим"]


def _match(col: str, kws: list[str]) -> bool:
    return any(k in col.lower() for k in kws)


def detect_header_row(raw: pd.DataFrame) -> int:
    best_row, best_n = 0, 0
    for i in range(min(5, len(raw))):
        n = sum(1 for v in raw.iloc[i].dropna() if isinstance(v, str) and v.strip())
        if n > best_n:
            best_n, best_row = n, i
    return best_row


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    price_cols: list[str] = []
    for col in df.columns:
        if _match(col, _NAME_KW) and "Наименование" not in mapping.values():
            mapping[col] = "Наименование"
        elif _match(col, _QTY_KW) and "Кол-во" not in mapping.values():
            mapping[col] = "Кол-во"
        elif _match(col, _PRICE_KW):
            price_cols.append(col)
    if price_cols:
        mapping[price_cols[0]] = "Цена опт"
    if len(price_cols) >= 2:
        mapping[price_cols[1]] = "Цена розн"
    df = df.rename(columns=mapping)
    # Фолбэк для листов без заголовков — назначаем по позиции
    if "Наименование" not in df.columns:
        names = ["Наименование", "Кол-во", "Цена опт", "Цена розн"]
        fb = {c: n for c, n in zip(df.columns, names) if n not in df.columns}
        df = df.rename(columns=fb)
    keep = [c for c in ["Наименование", "Кол-во", "Цена опт", "Цена розн"] if c in df.columns]
    return df[keep]


def clean_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        series = df[col]
        # При дублях pandas возвращает DataFrame — берём первый столбец
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
            df[col] = series
        if series.dtype == object:
            df[col] = series.apply(lambda x: x.strip() if isinstance(x, str) else x)
            df[col] = df[col].replace(r"^\s*$", pd.NA, regex=True)
    df = df.dropna(how="all")
    if len(df.columns) > 0:
        first = df.columns[0]
        df = df[df[first].notna()]
        df = df[df[first].astype(str).str.strip() != first]
    return df.reset_index(drop=True)


def read_sheet(xls: pd.ExcelFile, sheet: str) -> pd.DataFrame:
    raw = pd.read_excel(xls, sheet_name=sheet, header=None, dtype=str)
    hr = detect_header_row(raw)
    df = pd.read_excel(xls, sheet_name=sheet, header=hr)
    # Дедублируем колонки: "Цена", "Цена" → "Цена", "Цена.1"
    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for col in df.columns:
        col = str(col).strip()
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}.{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    df.columns = new_cols
    df = clean_df(df)
    return normalize_columns(df)


def parse_excel(file, sheets: list[str]) -> tuple[pd.DataFrame, list[str]]:
    xls = pd.ExcelFile(file)
    frames, warnings = [], []
    for sheet in sheets:
        try:
            df = read_sheet(xls, sheet)
            if df.empty or "Наименование" not in df.columns:
                warnings.append(f"Лист «{sheet}» пропущен — колонка с названием не найдена.")
                continue
            mask = df["Наименование"].notna() & (df["Наименование"].astype(str).str.strip() != "")
            df = df[mask]
            if df.empty:
                warnings.append(f"Лист «{sheet}» пропущен — нет данных.")
                continue
            df.insert(0, "Категория", sheet.strip())
            frames.append(df)
        except Exception as e:
            warnings.append(f"Лист «{sheet}» — ошибка: {e}")
    if not frames:
        return pd.DataFrame(), warnings
    return pd.concat(frames, ignore_index=True, sort=False), warnings


# ──────────────────────────────────────────────────────
# ТАБЛИЦА
# ──────────────────────────────────────────────────────

def highlight(text: str, query: str) -> str:
    if not query:
        return text
    return re.sub(f"({re.escape(query)})", r'<mark class="hl">\1</mark>',
                  text, flags=re.IGNORECASE)


def fmt_price(val) -> tuple[str, str]:
    try:
        f = float(val)
        if f != f:  # NaN check
            return "—", "td-dash"
        # 4 знака после запятой, убираем лишние нули → 0.0039, 0.09, 2.2
        s = f"{f:.4f}".rstrip("0").rstrip(".")
        return s, "td-price"
    except (TypeError, ValueError):
        return "—", "td-dash"


def render_table(df: pd.DataFrame, query: str, font_size: int) -> None:
    has_opt  = "Цена опт"  in df.columns
    has_rozn = "Цена розн" in df.columns
    has_qty  = "Кол-во"    in df.columns

    ths = ["Категория", "Наименование"]
    if has_qty:  ths.append("Кол-во")
    if has_opt:  ths.append("Цена опт")
    if has_rozn: ths.append("Цена розн")
    thead = "".join(f"<th>{h}</th>" for h in ths)

    tbody = ""
    for _, r in df.iterrows():
        cat  = str(r.get("Категория", ""))
        name = highlight(str(r.get("Наименование", "")), query)
        qty  = str(r["Кол-во"]) if has_qty and pd.notna(r.get("Кол-во")) else "—"
        opt_val, opt_cls   = fmt_price(r.get("Цена опт"))  if has_opt  else ("", "")
        rozn_val, rozn_cls = fmt_price(r.get("Цена розн")) if has_rozn else ("", "")

        tbody += "<tr>"
        tbody += f'<td class="td-cat">{cat}</td><td>{name}</td>'
        if has_qty:  tbody += f'<td class="td-qty">{qty}</td>'
        if has_opt:  tbody += f'<td class="{opt_cls}">{opt_val}</td>'
        if has_rozn: tbody += f'<td class="{rozn_cls}">{rozn_val}</td>'
        tbody += "</tr>"

    st.markdown(
        f'<div class="tbl-wrap" style="font-size:{font_size}px;">'
        f'<table class="ptable"><thead><tr>{thead}</tr></thead>'
        f'<tbody>{tbody}</tbody></table></div>',
        unsafe_allow_html=True,
    )


# ──────────────────────────────────────────────────────
# ПРИЛОЖЕНИЕ
# ──────────────────────────────────────────────────────

def init_state() -> None:
    for k, v in {"query": "", "cat": "Все категории", "font_size": 18}.items():
        if k not in st.session_state:
            st.session_state[k] = v


def main():
    st.set_page_config(page_title="Прайс-поиск", page_icon="🔍", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    init_db()
    init_state()

    total      = get_total()
    last_up    = get_meta("last_upload")
    categories = get_categories()

    # ── Шапка + статистика ─────────────────────────
    total_s = f"{total:,}".replace(",", " ")
    cats_s  = str(len(categories)) if categories else "—"

    st.markdown(
        f'<div class="app-title">🔍 Поиск по прайс-листу</div>'
        f'<div class="stats-row">'
        f'  <div class="stat-pill"><span class="stat-label">Товаров в базе</span>'
        f'    <span class="stat-value">{total_s}</span></div>'
        f'  <div class="stat-pill"><span class="stat-label">Последнее обновление</span>'
        f'    <span class="stat-value sm">{last_up}</span></div>'
        f'  <div class="stat-pill"><span class="stat-label">Категорий</span>'
        f'    <span class="stat-value">{cats_s}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    tab_search, tab_upload = st.tabs(["🔎 Поиск товаров", "📤 Загрузить прайс"])

    # ════════════════════════════════════════════════
    # ПОИСК 
    # ════════════════════════════════════════════════
    with tab_search:
        if total == 0:
            st.markdown(
                '<div class="empty-state">'
                '<div class="icon">📋</div>'
                '<div style="font-size:18px;font-weight:600;color:#e2e8f0;margin-bottom:6px">База пуста</div>'
                '<div class="msg">Перейдите на вкладку <b>«Загрузить прайс»</b> и добавьте Excel-файл</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            def do_reset():
                st.session_state.query = ""
                st.session_state.cat   = "Все категории"

            c1, c2, c3 = st.columns([5, 2, 1])
            with c1:
                st.text_input("q", label_visibility="collapsed",
                              placeholder="🔍  Введите название товара...", key="query")
            with c2:
                cat_opts = ["Все категории"] + categories
                if st.session_state.cat not in cat_opts:
                    st.session_state.cat = "Все категории"
                st.selectbox("c", label_visibility="collapsed", options=cat_opts, key="cat")
            with c3:
                st.write("")
                st.button("✕ Сброс", use_container_width=True,
                          help="Очистить фильтры", on_click=do_reset)

            q   = st.session_state.query.strip()
            cat = "" if st.session_state.cat == "Все категории" else st.session_state.cat

            result = search_db(q, cat)
            n = len(result)

            if n == 0 and (q or cat):
                note = f" в категории «{cat}»" if cat else ""
                st.warning(f"Ничего не найдено по запросу **«{q}»**{note}.")
            else:
                # ── Счётчик + шрифт ────────────────────
                meta_l, meta_r = st.columns([4, 1])
                with meta_l:
                    n_s = f"{n:,}".replace(",", " ")
                    parts = []
                    if q:   parts.append(f"<strong>{q}</strong>")
                    if cat: parts.append(f"категория «<strong>{cat}</strong>»")
                    info = " · ".join(parts)
                    label = f" &nbsp;·&nbsp; {info}" if info else ""
                    st.markdown(
                        f'<div class="res-info">Показано <strong>{n_s}</strong> товаров{label}</div>',
                        unsafe_allow_html=True,
                    )
                with meta_r:
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        if st.button("A−", use_container_width=True, help="Уменьшить шрифт"):
                            st.session_state.font_size = max(10, st.session_state.font_size - 1)
                            st.rerun()
                    with b2:
                        st.markdown(
                            f'<div class="font-badge">{st.session_state.font_size}</div>',
                            unsafe_allow_html=True,
                        )
                    with b3:
                        if st.button("A+", use_container_width=True, help="Увеличить шрифт"):
                            st.session_state.font_size = min(22, st.session_state.font_size + 1)
                            st.rerun()

                # ── Таблица ────────────────────────────
                render_table(result, q, st.session_state.font_size)

                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
                csv = result.to_csv(index=False).encode("utf-8-sig")
                st.download_button("⬇️ Скачать CSV", csv,
                                   f"прайс_{datetime.now():%Y%m%d_%H%M%S}.csv", "text/csv")

    # ════════════════════════════════════════════════
    # ЗАГРУЗКА
    # ════════════════════════════════════════════════
    with tab_upload:
        st.subheader("Загрузка нового прайс-листа")
        st.info(
            "Поддерживается Excel с **любым количеством листов**. "
            "Каждый лист — отдельная категория товаров. "
            "⚠️ Новый файл **полностью заменяет** старую базу."
        )

        file = st.file_uploader("Выберите файл (.xlsx или .xls)", type=["xlsx", "xls"])

        if file is not None:
            all_sheets = []
            try:
                xls_info   = pd.ExcelFile(file)
                all_sheets = xls_info.sheet_names
                file.seek(0)
            except Exception as e:
                st.error(f"Не удалось открыть файл: {e}")

            if all_sheets:
                st.success(f"Файл принят. Листов: **{len(all_sheets)}**")

                with st.expander("⚙️ Выбрать конкретные листы (по умолчанию — все)", expanded=False):
                    chosen = st.multiselect("Листы:", all_sheets, default=all_sheets)

                if not chosen:
                    st.warning("Выберите хотя бы один лист.")
                else:
                    prev_sheet = st.selectbox("Предпросмотр листа:", all_sheets)
                    try:
                        file.seek(0)
                        prev_df = read_sheet(pd.ExcelFile(file), prev_sheet)
                        file.seek(0)
                        st.caption(f"Колонки: {list(prev_df.columns)}")
                        st.dataframe(prev_df.head(8), use_container_width=True, hide_index=True)
                    except Exception as e:
                        st.warning(f"Предпросмотр недоступен: {e}")

                    if st.button("💾 Импортировать в базу", type="primary", use_container_width=True):
                        with st.spinner(f"Читаем {len(chosen)} листов…"):
                            file.seek(0)
                            df_final, warns = parse_excel(file, chosen)

                        for w in warns:
                            st.warning(w)

                        if df_final.empty:
                            st.error("Не удалось извлечь данные. Проверьте файл.")
                        else:
                            with st.spinner("Сохраняем в базу…"):
                                saved = save_products(df_final)
                            saved_s = f"{saved:,}".replace(",", " ")
                            st.success(f"✅ Сохранено **{saved_s}** товаров из **{len(chosen)}** листов.")
                            st.balloons()
                            st.rerun()


if __name__ == "__main__":
    main()
