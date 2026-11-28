"""Dashboard telesale; dùng lại nguyên luồng UI v2 để giữ các bản freeze có thể kiểm chứng.

    python -m streamlit run ui/dashboard.py --theme.base=light
"""
from pathlib import Path
import runpy
import sys

import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


def report_comparison(report, engine):
    """Chỉ trực quan hóa các tỷ lệ đã có trong report; thiếu baseline thì không dựng giá trị thay thế."""
    import altair as alt

    data = []
    order = []
    for title, baseline, system in engine.metric_table(report):
        if not title.endswith("(%)"):
            continue
        title = title.removesuffix(" (%)")
        order.append(title)
        for series, value in (("Hệ thống (full)", system), ("Baseline", baseline)):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                data.append({"metric": title, "series": series, "value": value})
    if not data:
        return
    series_names = [name for name in ("Hệ thống (full)", "Baseline") if any(row["series"] == name for row in data)]
    with st.container(key="report_comparison", border=True):
        st.subheader("So sánh với baseline")
        st.caption("TSR và CCR cao hơn là tốt hơn. Tỷ lệ hỏi lại và bịa giá, khuyến mãi thấp hơn là tốt hơn. "
                   "Chỉ hiện giá trị có trong báo cáo.")
        chart = alt.Chart(alt.Data(values=data)).mark_bar(cornerRadiusEnd=3, height=12).encode(
            x=alt.X("value:Q", title="Tỷ lệ (%)", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("metric:N", title=None, sort=order, axis=alt.Axis(labelLimit=260)),
            yOffset=alt.YOffset("series:N", sort=["Hệ thống (full)", "Baseline"]),
            color=alt.Color("series:N", title=None,
                            scale=alt.Scale(domain=series_names, range=["#1760A5", "#A1ADB9"][:len(series_names)])),
            tooltip=[alt.Tooltip("metric:N", title="Chỉ số"), alt.Tooltip("series:N", title="Cấu hình"),
                     alt.Tooltip("value:Q", title="Tỷ lệ (%)", format=".1f")],
        ).properties(height=240).configure(
            font="Segoe UI, system-ui, sans-serif", background="transparent"
        ).configure_view(stroke=None).configure_axis(
            labelColor="#4D5E70", titleColor="#4D5E70", gridColor="#E1E6EC", domain=False,
            labelFontSize=11, titleFontSize=11, labelPadding=10, titlePadding=14, ticks=False,
        ).configure_legend(
            orient="top", labelColor="#253447", labelFontSize=12, symbolType="square", padding=0,
        )
        st.altair_chart(chart, use_container_width=True, theme=None)


st.set_page_config(page_title="SUDO CODE | Bàn làm việc telesale", page_icon="💬", layout="wide",
                   initial_sidebar_state="auto")
st.html("<style>" + (HERE / "assets/dashboard.css").read_text(encoding="utf-8") + "</style>")
with st.container(key="workspace_heading"):
    st.html('''<header class="workspace-heading">
      <h1>Bàn làm việc telesale</h1>
      <p>Tư vấn, theo dõi cuộc gọi và xem lịch sử khách hàng.</p>
    </header>''')

# shortcut: tái dùng script v2 đang khóa hash; khi v2 có hàm render công khai thì gọi trực tiếp.
workspace = runpy.run_path(str(HERE / "app_v2.py"))
if not workspace["get_engine"]().calls:
    with workspace["tab_call"]:
        st.html('''<section class="call-empty">
          <h2>Chưa có cuộc gọi</h2>
          <p>Chọn số điện thoại và kênh liên hệ trong phần Thiết lập cuộc gọi.</p>
        </section>''')
if "rep" in workspace:
    with workspace["tab_metrics"]:
        report_comparison(workspace["rep"], workspace["E"])
