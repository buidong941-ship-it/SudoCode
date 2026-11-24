"""Dashboard telesale; dùng lại nguyên luồng UI v2 để giữ các bản freeze có thể kiểm chứng.

    python -m streamlit run ui/dashboard.py --theme.base=light
"""
import base64
from pathlib import Path
import runpy
import sys

import streamlit as st

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))


@st.cache_data
def stylesheet():
    fonts = []
    for weight, filename in ((400, "BeVietnamPro-Regular.ttf"), (600, "BeVietnamPro-SemiBold.ttf")):
        data = base64.b64encode((HERE / "assets/fonts" / filename).read_bytes()).decode("ascii")
        fonts.append(f'@font-face {{font-family:"Be Vietnam Pro";font-style:normal;font-weight:{weight};'
                     f'font-display:swap;src:url(data:font/ttf;base64,{data}) format("truetype");}}')
    return "\n".join(fonts) + (HERE / "assets/dashboard.css").read_text(encoding="utf-8")


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
                            scale=alt.Scale(domain=series_names, range=["#007C83", "#A6BDC8"][:len(series_names)])),
            tooltip=[alt.Tooltip("metric:N", title="Chỉ số"), alt.Tooltip("series:N", title="Cấu hình"),
                     alt.Tooltip("value:Q", title="Tỷ lệ (%)", format=".1f")],
        ).properties(height=240).configure(
            font="Be Vietnam Pro", background="transparent"
        ).configure_view(stroke=None).configure_axis(
            labelColor="#536D7A", titleColor="#536D7A", gridColor="#E6EEF2", domain=False,
            labelFontSize=11, titleFontSize=11, labelPadding=10, titlePadding=14, ticks=False,
        ).configure_legend(
            orient="top", labelColor="#20313D", labelFontSize=12, symbolType="square", padding=0,
        )
        st.altair_chart(chart, use_container_width=True, theme=None)


st.set_page_config(page_title="SUDO CODE | Bàn làm việc telesale", page_icon="💬", layout="wide",
                   initial_sidebar_state="expanded")
st.html("<style>" + stylesheet() + "</style>")
with st.container(key="workspace_heading"):
    st.html('''<header class="workspace-heading">
      <div class="workspace-heading__copy">
        <h1>Bàn làm việc telesale</h1>
        <p>Hội thoại được tiếp nối, ngữ cảnh được giữ lại.</p>
      </div>
      <div class="conversation-mark" aria-hidden="true">
        <span></span><span></span><span></span><span></span><span></span><span></span><span></span>
      </div>
    </header>''')

# shortcut: tái dùng script v2 đang khóa hash; khi v2 có hàm render công khai thì gọi trực tiếp.
workspace = runpy.run_path(str(HERE / "app_v2.py"))
if not workspace["get_engine"]().calls:
    with workspace["tab_call"]:
        st.html('''<section class="call-empty">
          <div class="call-empty__signal" aria-hidden="true"><span></span><span></span><span></span></div>
          <div><h2>Mở cuộc gọi để bắt đầu tư vấn</h2>
            <p>Chọn khách hàng và kênh liên hệ ở phần thiết lập phía trên.
            Khi khách quay lại, Call Brief sẽ giúp bạn tiếp nối câu chuyện.</p></div>
        </section>''')
if "rep" in workspace:
    with workspace["tab_metrics"]:
        report_comparison(workspace["rep"], workspace["E"])
